"""Main-comparison generation adapters.

`AnalogCoderSharedAdapter` preserves the official AnalogCoder two-part prompt
(topology plan plus PySpice code) and its repair loop.  The shared adaptation is
limited to the task projection, stable IN/OUT names, isolated code execution,
raw-deck export, and common evaluation. `SpicePilotPromptAdapter` preserves the
published Prompt Pilot while adding only the shared task interface and artifact
export. `DirectSpiceBaseline` receives only the requirement and emits SPICE.
"""

from __future__ import annotations

import ast
import json
import os
import re
import resource
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from shared_spice_evaluator import EvaluationResult, NodeManifest, evaluate_deck


PYSPICE_INTERFACE = (
    '\nPySpice export syntax: Circuit.X takes the subcircuit name immediately after '
    'the instance name, before all nodes. For the shared op-amp use '
    "circuit.X('U1', 'LM2904', inp, inm, vplus, vminus, out). "
    'This differs from raw SPICE, where the model name is last. '
    "For the single-ended AC input use circuit.V('IN', 'IN', circuit.gnd, 'DC 0 AC 1'). "
    'Element constructors add the device prefix automatically: '
    "circuit.V('DD', ...) creates VDD and circuit.R('LOAD', ...) creates RLOAD. "
    'The fixed models are provided after export; do not define them in Python. '
    'Do not run a private simulator or plotting routine before exporting the circuit.'
)


class ChatClient(Protocol):
    def chat(
        self, messages: list[dict[str, str]], *, temperature: float, seed: int
    ) -> Any: ...


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int
    completion_tokens: int
    response_model_id: str


@dataclass(frozen=True)
class CandidateResult:
    attempt: int
    prompt_path: str
    response_path: str
    submitted_deck: str | None
    node_manifest: NodeManifest
    usage: LLMUsage
    evaluation: EvaluationResult | None
    failure_stage: str | None
    error: str | None


def _usage_value(usage: Any, key: str) -> int:
    value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, 0)
    return int(value or 0)


def _response_content(response: Any) -> str:
    if isinstance(response, dict):
        return str(response["choices"][0]["message"]["content"])
    return str(response.choices[0].message.content)


def _response_usage(response: Any) -> LLMUsage:
    usage = response.get("usage", {}) if isinstance(response, dict) else getattr(response, "usage", None)
    model = response.get("model", "") if isinstance(response, dict) else getattr(response, "model", "")
    return LLMUsage(_usage_value(usage, "prompt_tokens"), _usage_value(usage, "completion_tokens"), str(model))


def _extract_code(response: str, language: str | None = None) -> str:
    tag = language or r"(?:python|pyspice|spice|sp)"
    match = re.search(rf"```{tag}\s*(.*?)```", response, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        raise ValueError("response does not contain a required fenced code block")
    return match.group(1).strip() + "\n"


def _safe_preexec() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    # RLIMIT_NPROC is counted across every process owned by the host user. A
    # low value can prevent bubblewrap from creating its already-isolated PID
    # namespace on shared experiment servers.
    os.setsid()


def _sandbox_command(python: str, script: Path) -> list[str]:
    """Build a no-network, minimal-filesystem command for generated Python."""

    bwrap = shutil.which("bwrap")
    executable = shutil.which(python) if not Path(python).is_absolute() else python
    if not bwrap:
        raise RuntimeError("generated Python execution requires bubblewrap (bwrap)")
    if not executable:
        raise RuntimeError(f"Python executable not found: {python}")
    executable_path = Path(executable)
    resolved = executable_path.resolve()
    command = [
        bwrap,
        "--die-with-parent",
        "--new-session",
        "--unshare-net",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
    ]
    runtime_rootfs_value = os.environ.get("EDA_RUNTIME_ROOTFS")
    runtime_rootfs = Path(runtime_rootfs_value) if runtime_rootfs_value else None
    for system_path in (Path("/usr"), Path("/bin"), Path("/lib"), Path("/lib64")):
        rootfs_path = (
            runtime_rootfs / system_path.relative_to("/")
            if runtime_rootfs is not None else None
        )
        source = rootfs_path if rootfs_path is not None and rootfs_path.exists() else system_path
        if source.exists():
            command.extend(["--ro-bind", str(source), str(system_path)])
    runtime_executable = str(resolved)
    if not str(executable_path).startswith(("/usr/", "/bin/")):
        environment_root = executable_path.parent.parent
        if not environment_root.is_dir():
            raise RuntimeError(f"invalid Python environment root: {environment_root}")
        command.extend(["--ro-bind", str(environment_root), "/runtime"])
        runtime_executable = f"/runtime/bin/{executable_path.name}"
    command.extend([
        "--bind", str(script.parent), "/work",
        "--chdir", "/work",
        "--clearenv",
        "--setenv", "PATH", "/runtime/bin:/usr/bin:/bin",
        "--setenv", "HOME", "/work",
        "--setenv", "TMPDIR", "/tmp",
        "--setenv", "PYTHONNOUSERSITE", "1",
        "--",
        runtime_executable,
        "-I",
        f"/work/{script.name}",
    ])
    return command


def _run_pyspice_export(code: str, workspace: Path, *, timeout_seconds: int) -> tuple[Path, str | None]:
    """Execute generated PySpice with no credentials and export `str(circuit)`."""

    workspace.mkdir(parents=True, exist_ok=True)
    script = workspace / "generated.py"
    deck = workspace / "submitted.cir"
    stdout_path = workspace / "generated.stdout"
    stderr_path = workspace / "generated.stderr"
    marker_start = "__SHARED_SPICE_START__"
    marker_end = "__SHARED_SPICE_END__"
    try:
        tree = ast.parse(code)
        simulator_line = next(
            (
                statement.lineno
                for statement in tree.body
                if any(
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "simulator"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "circuit"
                    for node in ast.walk(statement)
                )
            ),
            None,
        )
        construction_code = (
            "".join(code.splitlines(keepends=True)[: simulator_line - 1])
            if simulator_line is not None else code
        )
    except SyntaxError:
        construction_code = code
    script.write_text(
        construction_code
        + f"\nprint('{marker_start}')\nprint(str(circuit))\nprint('{marker_end}')\n",
        encoding="utf-8",
    )
    environment = {
        "PATH": os.environ.get("PATH", ""),
    }
    try:
        completed = subprocess.run(
            _sandbox_command(sys.executable, script),
            cwd=workspace,
            env=environment,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            preexec_fn=_safe_preexec,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        stderr_path.write_text(str(exc), encoding="utf-8")
        return deck, f"sandbox execution failed: {exc}"
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        return deck, f"generated PySpice exited with {completed.returncode}: {completed.stderr[-1200:]}"
    match = re.search(
        rf"{marker_start}\s*(.*?)\s*{marker_end}", completed.stdout, flags=re.DOTALL
    )
    if not match:
        return deck, "generated PySpice did not expose a circuit object"
    deck.write_text(match.group(1).strip() + "\n", encoding="utf-8")
    return deck, None


class OpenAICompatibleClient:
    """Small adapter that makes OpenAI-compatible responses easy to record."""

    def __init__(
        self, model: str, api_key: str, base_url: str, *, thinking_disabled: bool = False
    ) -> None:
        from openai import OpenAI

        self.model = model
        self.thinking_disabled = thinking_disabled
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(
        self, messages: list[dict[str, str]], *, temperature: float, seed: int
    ) -> Any:
        request = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "seed": seed,
        }
        if self.thinking_disabled:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        return self.client.chat.completions.create(**request)


class _BaseAdapter:
    def __init__(
        self,
        client: ChatClient,
        *,
        temperature: float,
        max_calls: int,
        ngspice: str,
        timeout_seconds: int,
        evaluator: Any = None,
    ) -> None:
        self.client = client
        self.temperature = temperature
        self.max_calls = max_calls
        self.ngspice = ngspice
        self.timeout_seconds = timeout_seconds
        self.evaluator = evaluator

    def _evaluate_spice(
        self,
        deck: Path,
        manifest: NodeManifest,
        target: dict[str, Any],
        workspace: Path,
    ) -> EvaluationResult:
        outcome = (self.evaluator(deck, workspace / "evaluation", ngspice=self.ngspice)
                   if self.evaluator else evaluate_deck(
                       deck, manifest, target, workspace / "evaluation", ngspice=self.ngspice,
                       timeout_seconds=self.timeout_seconds))
        (workspace / "common_evaluation.json").write_text(
            json.dumps(outcome.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
        return outcome


class DirectSpiceBaseline(_BaseAdapter):
    """True direct LLM baseline: requirement to raw SPICE, no EDA Last state."""

    def run(
        self, case: dict[str, Any], workspace: Path, *, seed: int
    ) -> list[CandidateResult]:
        manifest = NodeManifest("IN", "OUT", "0", "VLOAD" if case["targets"]["metric"] == "load_current_a" else None)
        if case.get('checks'):
            manifest = NodeManifest(**case['checks'][0]['nodes'])
        prompt = (
            "Generate a complete raw Ngspice deck for the following circuit requirement. "
            "Use node IN for the signal input, OUT for output, and 0 for ground. "
            "Include a 1-V AC input source between IN and 0 for AC circuits. "
            "For a load-current circuit, include a 0-V sensing source named VLOAD "
            "in series with the LED or load branch. "
            "Return only one fenced ```spice``` block.\n\nRequirement:\n"
            + case["user_requirement"]
        )
        if case.get('interface'):
            prompt = ('Generate a complete raw Ngspice deck for the following circuit requirement. '
                      'Return only one fenced spice block.\n' + case['user_requirement'] + '\n' + case['interface'])
        results: list[CandidateResult] = []
        for attempt in range(1, self.max_calls + 1):
            attempt_root = workspace / f"attempt_{attempt}"
            attempt_root.mkdir(parents=True, exist_ok=True)
            messages = [
                {"role": "system", "content": "You are a circuit designer."},
                {"role": "user", "content": prompt},
            ]
            (attempt_root / "prompt.json").write_text(json.dumps(messages, indent=2) + "\n", encoding="utf-8")
            try:
                response = self.client.chat(
                    messages, temperature=self.temperature, seed=seed + attempt - 1
                )
            except Exception as exc:
                response_path = attempt_root / "response.txt"
                response_path.write_text(f"API call failed: {exc}\n", encoding="utf-8")
                results.append(CandidateResult(
                    attempt, str(attempt_root / "prompt.json"), str(response_path),
                    None, manifest, LLMUsage(0, 0, "unavailable_no_response"),
                    None, "generation", str(exc),
                ))
                continue
            answer = _response_content(response)
            usage = _response_usage(response)
            (attempt_root / "response.txt").write_text(answer, encoding="utf-8")
            try:
                deck = attempt_root / "submitted.cir"
                raw_deck = _extract_code(answer, "(?:spice|sp)")
                (attempt_root / "raw_submitted.cir").write_text(
                    raw_deck, encoding="utf-8"
                )
                deck.write_text(raw_deck, encoding="utf-8")
                evaluation = self._evaluate_spice(deck, manifest, case["targets"], attempt_root)
                result = CandidateResult(attempt, str(attempt_root / "prompt.json"), str(attempt_root / "response.txt"), str(deck), manifest, usage, evaluation, evaluation.failure_stage, evaluation.detail)
            except Exception as exc:
                result = CandidateResult(attempt, str(attempt_root / "prompt.json"), str(attempt_root / "response.txt"), None, manifest, usage, None, "generation", str(exc))
            results.append(result)
            if result.evaluation and result.evaluation.passed:
                break
        return results


class AnalogCoderSharedAdapter(_BaseAdapter):
    """Adapt official AnalogCoder prompting without exposing evaluator targets."""

    def __init__(self, *args: Any, analogcoder_root: Path, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.template = (analogcoder_root / "prompt_template.txt").read_text(encoding="utf-8")

    def _prompt(self, requirement: str, interface: str | None = None, input_node: str = 'IN') -> str:
        if interface:
            return (self.template.replace('[TASK]', requirement).replace('[INPUT]', input_node)
                    .replace('[OUTPUT]', 'OUT') + '\n\nShared-adapter interface:\n' + interface
                    + PYSPICE_INTERFACE + '\nThe returned Python must define a complete `circuit` object.')
        return (
            self.template.replace("[TASK]", requirement).replace("[INPUT]", "IN").replace("[OUTPUT]", "OUT")
            + "\n\nShared-adapter interface: use IN, OUT, and ground 0 exactly. "
            "For an AC circuit, include a 1-V AC source between IN and 0. "
            "For a load-current circuit, include a 0-V sensing source named VLOAD "
            "in series with the LED or load branch. "
            "The returned Python must define a complete `circuit` object."
        )

    def run(
        self, case: dict[str, Any], workspace: Path, *, seed: int
    ) -> list[CandidateResult]:
        manifest = NodeManifest("IN", "OUT", "0", "VLOAD" if case["targets"]["metric"] == "load_current_a" else None)
        if case.get('checks'):
            manifest = NodeManifest(**case['checks'][0]['nodes'])
        original_prompt = self._prompt(case['user_requirement'], case.get('interface'), manifest.input)
        messages = [
            {"role": "system", "content": "You are an analog integrated circuits expert."},
            {"role": "user", "content": original_prompt},
        ]
        results: list[CandidateResult] = []
        for attempt in range(1, self.max_calls + 1):
            attempt_root = workspace / f"attempt_{attempt}"
            attempt_root.mkdir(parents=True, exist_ok=True)
            (attempt_root / "prompt.json").write_text(json.dumps(messages, indent=2) + "\n", encoding="utf-8")
            try:
                response = self.client.chat(
                    messages, temperature=self.temperature, seed=seed + attempt - 1
                )
            except Exception as exc:
                response_path = attempt_root / "response.txt"
                response_path.write_text(f"API call failed: {exc}\n", encoding="utf-8")
                results.append(CandidateResult(
                    attempt, str(attempt_root / "prompt.json"), str(response_path),
                    None, manifest, LLMUsage(0, 0, "unavailable_no_response"),
                    None, "generation", str(exc),
                ))
                continue
            answer = _response_content(response)
            usage = _response_usage(response)
            (attempt_root / "response.txt").write_text(answer, encoding="utf-8")
            try:
                code = _extract_code(answer, "(?:python|pyspice)")
                deck, error = _run_pyspice_export(code, attempt_root / "sandbox", timeout_seconds=self.timeout_seconds)
                if error:
                    raise RuntimeError(error)
                (attempt_root / "raw_submitted.cir").write_bytes(deck.read_bytes())
                evaluation = self._evaluate_spice(deck, manifest, case["targets"], attempt_root)
                result = CandidateResult(attempt, str(attempt_root / "prompt.json"), str(attempt_root / "response.txt"), str(deck), manifest, usage, evaluation, evaluation.failure_stage, evaluation.detail)
            except Exception as exc:
                result = CandidateResult(attempt, str(attempt_root / "prompt.json"), str(attempt_root / "response.txt"), None, manifest, usage, None, "generation", str(exc))
            results.append(result)
            if result.evaluation and result.evaluation.passed:
                break
            if result.evaluation is not None:
                # Functional evaluation is terminal for the adapted external
                # method. Only its native Python execution errors are repairable.
                break
            messages.extend([
                {"role": "assistant", "content": answer},
                {"role": "user", "content": "The previous Python code failed to execute: " + (result.error or "unknown code error") + ". Rewrite the complete corrected PySpice code."},
            ])
        return results


class SpicePilotPromptAdapter(_BaseAdapter):
    """Adapt SPICEPilot's published Prompt Pilot to the shared evaluator."""

    def __init__(self, *args: Any, spicepilot_root: Path, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.pilot_prompt = (spicepilot_root / "Pilot_prompt.md").read_text(
            encoding="utf-8"
        )

    def run(
        self, case: dict[str, Any], workspace: Path, *, seed: int
    ) -> list[CandidateResult]:
        manifest = NodeManifest(
            "IN", "OUT", "0",
            "VLOAD" if case["targets"]["metric"] == "load_current_a" else None,
        )
        if case.get('checks'):
            manifest = NodeManifest(**case['checks'][0]['nodes'])
        task_prompt = (
            self.pilot_prompt
            + "\n\nShared-adapter task:\n"
            + case["user_requirement"]
            + "\nUse IN for signal input, OUT for output, and 0 for ground. "
            "For an AC circuit include a 1-V AC source between IN and 0. "
            "For a load-current circuit include a 0-V sensing source named "
            "VLOAD in series with the load branch. Return one fenced Python "
            "block that defines a PySpice `circuit` object."
        )
        if case.get('interface'):
            task_prompt = (self.pilot_prompt + '\n\nShared-adapter task:\n' + case['user_requirement']
                           + '\n' + case['interface'] + PYSPICE_INTERFACE
                           + '\nReturn one fenced Python block defining a PySpice `circuit` object.')
        messages = [
            {"role": "system", "content": "Follow the supplied SPICEPilot instructions."},
            {"role": "user", "content": task_prompt},
        ]
        results: list[CandidateResult] = []
        for attempt in range(1, self.max_calls + 1):
            attempt_root = workspace / f"attempt_{attempt}"
            attempt_root.mkdir(parents=True, exist_ok=True)
            prompt_path = attempt_root / "prompt.json"
            response_path = attempt_root / "response.txt"
            prompt_path.write_text(
                json.dumps(messages, indent=2) + "\n", encoding="utf-8"
            )
            try:
                response = self.client.chat(
                    messages, temperature=self.temperature, seed=seed + attempt - 1
                )
            except Exception as exc:
                response_path.write_text(f"API call failed: {exc}\n", encoding="utf-8")
                results.append(CandidateResult(
                    attempt, str(prompt_path), str(response_path), None, manifest,
                    LLMUsage(0, 0, "unavailable_no_response"), None,
                    "generation", str(exc),
                ))
                continue
            answer = _response_content(response)
            usage = _response_usage(response)
            response_path.write_text(answer, encoding="utf-8")
            try:
                code = _extract_code(answer, "(?:python|pyspice)")
                deck, error = _run_pyspice_export(
                    code, attempt_root / "sandbox", timeout_seconds=self.timeout_seconds
                )
                if error:
                    raise RuntimeError(error)
                (attempt_root / "raw_submitted.cir").write_bytes(deck.read_bytes())
                evaluation = self._evaluate_spice(
                    deck, manifest, case["targets"], attempt_root
                )
                result = CandidateResult(
                    attempt, str(prompt_path), str(response_path), str(deck), manifest,
                    usage, evaluation, evaluation.failure_stage, evaluation.detail,
                )
            except Exception as exc:
                result = CandidateResult(
                    attempt, str(prompt_path), str(response_path), None, manifest,
                    usage, None, "generation", str(exc),
                )
            results.append(result)
            if result.evaluation and result.evaluation.passed:
                break
        return results


def candidates_to_json(candidates: list[CandidateResult]) -> dict[str, Any]:
    return {
        "generation_calls": len(candidates),
        "prompt_tokens": sum(item.usage.prompt_tokens for item in candidates),
        "completion_tokens": sum(item.usage.completion_tokens for item in candidates),
        "response_model_ids": sorted({item.usage.response_model_id for item in candidates if item.usage.response_model_id}),
        "candidates": [
            {
                **asdict(item),
                "node_manifest": asdict(item.node_manifest),
                "evaluation": item.evaluation.as_dict() if item.evaluation else None,
            }
            for item in candidates
        ],
    }
