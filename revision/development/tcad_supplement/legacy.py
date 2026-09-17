"""Delayed-import adapter for EDA_Last-like project layouts.

Only this module knows legacy internal names. The experiment logic remains in
the portable package, so a collaborator can point it at a different checkout
with ``--project-root`` instead of replacing package files.
"""

from __future__ import annotations

import importlib
import inspect
import json
import math
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, Mapping, Optional

from .policy import Candidate, run_attempts


REQUIRED_PATHS = (
    "framework/core/netlist_engine.py",
    "framework/core/spice_engine.py",
    "framework/orchestrator.py",
    "baselines/pipeline_methods/plan_methods.py",
    "baselines/pipeline_methods/retrieval_methods.py",
)


def discover_legacy_project(project_root: Path | str) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    found = {path: (root / path).is_file() for path in REQUIRED_PATHS}
    dataset_candidates = [
        root / "experiments" / "datasets" / "test_cases_v3.json",
        root / "experiments" / "datasets" / "test_cases.json",
    ]
    dataset = next((path for path in dataset_candidates if path.is_file()), None)
    return {
        "project_root": str(root),
        "compatible_layout": all(found.values()),
        "required_files": found,
        "dataset": str(dataset) if dataset else None,
        "imports_attempted": False,
    }


@contextmanager
def _project_import_path(root: Path) -> Iterator[None]:
    additions = [str(root), str(root / "framework")]
    original = list(sys.path)
    sys.path[:0] = [path for path in additions if path not in sys.path]
    try:
        yield
    finally:
        sys.path[:] = original


def _call_supported(function: Any, *args: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(function)
    supported = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return function(*args, **supported)


def _infer_circuit_type(target: Mapping[str, Any]) -> str:
    metric = str(target.get("metric", "")).lower()
    if "cutoff" in metric:
        return "filter"
    if "midband_gain" in metric:
        return "opamp_amplifier"
    if "gain" in metric:
        return "bjt_amplifier"
    if "led_current" in metric:
        return "led_constant_current"
    if "v_out" in metric or "voltage" in metric:
        return "zener_regulator"
    raise ValueError(f"cannot infer circuit type from target metric: {metric}")


def _normalize_circuit_type(requirement: str, raw_type: str) -> str:
    """Map method-visible functional intent to the registered expert taxonomy."""

    lowered = requirement.lower()
    if "low-pass filter" in lowered or "low pass filter" in lowered:
        return "filter"
    if "constant-current led" in lowered or "constant current led" in lowered:
        return "led_constant_current"
    if "zener" in lowered:
        return "zener_regulator"
    if "common-emitter" in lowered or "common emitter" in lowered:
        return "bjt_amplifier"
    aliases = {
        "filter": "filter",
        "bjt_amplifier": "bjt_amplifier",
        "opamp_amplifier": "opamp_amplifier",
        "zener_regulator": "zener_regulator",
        "led_constant_current": "led_constant_current",
    }
    if raw_type in aliases:
        return aliases[raw_type]
    if raw_type == "amplifier":
        return "bjt_amplifier" if "transistor" in lowered or "npn" in lowered else "opamp_amplifier"
    # The 40-task artifact-coverage profile contains timing, control, sensor,
    # and driver families outside the five quantitative expert routes. Keep
    # them runnable through a declared generic route; the 10-task functional
    # profile never uses this fallback.
    return "generic_circuit"


def _number(pattern: str, text: str, label: str) -> float:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"could not parse {label} from visible requirement")
    return float(match.group(1))


def _target_from_requirement(requirement: str, circuit_type: str) -> dict[str, Any]:
    """Build the legacy expert target from method-visible requirement text only."""

    if circuit_type in {"opamp_amplifier", "bjt_amplifier"}:
        gain = abs(
            _number(
                r"gain(?:\s+of)?\s*(?:~|about)?\s*([+-]?\d+(?:\.\d+)?)",
                requirement,
                "gain",
            )
        )
        if gain <= 0:
            raise ValueError("gain magnitude must be positive")
        return {
            "metric": "midband_gain_db" if circuit_type == "opamp_amplifier" else "max_gain_db",
            "value": 20.0 * math.log10(gain),
            "source_unit": "V/V",
        }
    if circuit_type == "filter":
        match = re.search(r"(?:~\s*)?(\d+(?:\.\d+)?)\s*(k?hz)", requirement, re.IGNORECASE)
        if not match:
            raise ValueError("could not parse cutoff from visible requirement")
        value = float(match.group(1)) * (1000.0 if match.group(2).lower() == "khz" else 1.0)
        return {"metric": "cutoff_freq_hz", "value": value, "source_unit": "Hz"}
    if circuit_type == "zener_regulator":
        value = _number(r"(\d+(?:\.\d+)?)\s*V\s+Zener", requirement, "voltage")
        return {"metric": "v_out_avg_v", "value": value, "source_unit": "V"}
    if circuit_type == "led_constant_current":
        value = _number(r"(?:about\s+)?(\d+(?:\.\d+)?)\s*mA", requirement, "current")
        return {"metric": "led_current_ma", "value": value, "source_unit": "mA"}
    if circuit_type == "generic_circuit":
        return {
            "metric": "artifact_only",
            "value": None,
            "source_unit": "not_applicable",
        }
    raise ValueError(f"unsupported circuit type: {circuit_type}")


def _load_required_expert_factory() -> Any:
    """Load only experts used by the benchmark, tolerating stale unused imports."""
    from experts.bjt_amplifier_expert import BjtAmplifierExpert
    from experts.filter_expert import FilterExpert
    from experts.led_constant_current_expert import LedConstantCurrentExpert
    from experts.opamp_amplifier_expert import OpAmpAmplifierExpert
    from experts.zener_regulator_expert import ZenerRegulatorExpert

    class GenericCircuitExpert:
        """Artifact-only fallback for benchmark families without a native expert."""

        def set_targets(self, target: Mapping[str, Any] | None) -> None:
            self.target = dict(target or {})

        def get_netlist_prompts(
            self,
            requirement: str,
            uid_hint: str,
            iteration: int = 1,
            previous_spice: Optional[str] = None,
            feedback: Optional[str] = None,
        ) -> tuple[str, str]:
            system = (
                "You are a circuit designer generating a complete self-contained "
                "Ngspice deck. Return only one fenced ```spice``` block. Do not "
                "use external include or library files."
            )
            user = (
                f"Requirement:\n{requirement}\n\n"
                "Use node IN for a signal input when present, OUT for the primary "
                "output, and 0 for ground. Include component models directly in "
                "the deck. The retrieved component hints are:\n"
                f"{uid_hint or '(none)'}"
            )
            if previous_spice and feedback:
                user += (
                    "\n\nThe previous candidate and execution feedback follow. "
                    "Return a complete corrected deck.\nPrevious candidate:\n"
                    f"{previous_spice}\nFeedback:\n{feedback}"
                )
            return system, user

    experts = {
        "filter": FilterExpert,
        "bjt_amplifier": BjtAmplifierExpert,
        "opamp_amplifier": OpAmpAmplifierExpert,
        "zener_regulator": ZenerRegulatorExpert,
        "led_constant_current": LedConstantCurrentExpert,
        "generic_circuit": GenericCircuitExpert,
    }

    class RequiredExpertFactory:
        @classmethod
        def get_expert(cls, circuit_type: str) -> Any:
            return experts.get(circuit_type, GenericCircuitExpert)()

    return RequiredExpertFactory


class LegacyEDALastAdapter:
    """Duck-typed bridge to one local EDA_Last checkout."""

    def __init__(self, project_root: Path | str) -> None:
        self.root = Path(project_root).expanduser().resolve()
        report = discover_legacy_project(self.root)
        if not report["compatible_layout"]:
            missing = [path for path, exists in report["required_files"].items() if not exists]
            raise ValueError(f"unsupported project layout; missing: {', '.join(missing)}")
        with _project_import_path(self.root):
            planner_module = importlib.import_module("circuit_planner_v")
            self.retrieval_module = importlib.import_module("baselines.pipeline_methods.retrieval_methods")
            spec = importlib.util.spec_from_file_location(
                "eda_last_runtime_netlist_engine",
                self.root / "framework" / "core" / "netlist_engine.py",
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("cannot load reviewed netlist engine overlay")
            self.netlist_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.netlist_module)
            self.orchestrator_module = SimpleNamespace(
                ExpertFactory=_load_required_expert_factory()
            )
        class OursPlanMethod:
            def __init__(self) -> None:
                self.planner = planner_module.CircuitPlannerFinal()
                self.planner.system_prompt += """
【\u7535\u6e90\u4e0e\u63a5\u5730\u5f3a\u5236\u89c4\u5219】
- \u6bcf\u4e2a\u7535\u8def\u65b9\u6848\u5fc5\u987b\u5305\u542b VCC（\u7535\u6e90\u6b63）\u548c GND（\u5730\u7ebf）\u4e24\u4e2a\u5143\u5668\u4ef6
- search_query \u5206\u522b\u4f7f\u7528 "VCC" \u548c "GND"
- \u8fd9\u662f\u5f3a\u5236\u8981\u6c42，\u65e0\u4f8b\u5916
"""

            def generate_plan(
                self, user_requirement: str, *, seed: Optional[int] = None
            ) -> Optional[dict[str, Any]]:
                return self.planner.generate_plan(
                    user_requirement, num_candidates=3, seed=seed
                )

        def create_plan_method(method: str) -> OursPlanMethod:
            if method != "Ours":
                raise ValueError(f"unsupported method: {method}")
            return OursPlanMethod()

        self.plan_module = SimpleNamespace(create_plan_method=create_plan_method)
        disable_thinking = os.environ.get("EDA_DISABLE_THINKING", "0") == "1"
        self.netlist_module.THINKING_ENABLED = False
        self.netlist_module.EXPLICIT_DISABLE_THINKING = disable_thinking
        self.last_planning_usage: list[dict[str, Any]] = []

    def prepare(
        self,
        requirement: str,
        target: Optional[Mapping[str, Any]] = None,
        *,
        artifact_only: bool = False,
        seed: Optional[int] = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        plan_method = self.plan_module.create_plan_method("Ours")
        retrieval_method = self.retrieval_module.create_retrieval_method("Ours")
        plan = _call_supported(plan_method.generate_plan, requirement, seed=seed)
        planner = getattr(plan_method, "planner", None)
        self.last_planning_usage = [
            dict(row) for row in getattr(planner, "usage_records", [])
        ]
        if not isinstance(plan, dict) or not isinstance(plan.get("components"), list):
            raise RuntimeError("legacy planner did not return a component plan")
        plan = dict(plan)
        planner_elaboration = str(plan.get("elaborated_requirement", "")).strip()
        plan["_visible_requirement"] = requirement
        plan["_planner_elaboration"] = planner_elaboration
        plan["elaborated_requirement"] = (
            f"Original user requirement:\n{requirement}\n\n"
            f"Planner elaboration:\n{planner_elaboration}"
        )
        raw_circuit_type = str(plan.get("circuit_type", ""))
        circuit_type = (
            "generic_circuit"
            if artifact_only
            else _normalize_circuit_type(requirement, raw_circuit_type)
        )
        plan["_raw_circuit_type"] = raw_circuit_type
        plan["circuit_type"] = circuit_type
        plan["_benchmark_targets"] = (
            {"metric": "artifact_only", "value": None, "source_unit": "not_applicable"}
            if artifact_only
            else (
                dict(target)
                if target is not None
                else _target_from_requirement(requirement, circuit_type)
            )
        )
        retrieved: dict[str, Any] = {}
        for component in plan["components"]:
            uid = component.get("uid")
            query = component.get("search_query")
            if not uid or not query:
                continue
            result = retrieval_method.search_component(query)
            if not result or result.get("status") != "success":
                retrieved[uid] = None
                continue
            data = result["data"]
            retrieved[uid] = {
                "uid": uid,
                "planned_value": component.get("parameters", {}).get("value", ""),
                "lib_id": data.get("lib_id", "Unknown"),
                "source_library": data.get("source_library", "Project_Lib"),
                "pins": data.get("pins", []),
                "raw_symbol_definition": data.get("raw_symbol_definition", ""),
                "description": data.get("description", ""),
                "match_score": data.get("match_score", 0.0),
            }
        return plan, retrieved

    def _raw_engine_class(self) -> type:
        module = self.netlist_module
        base = module.NetlistEngine

        class RawNetlistEngine(base):
            def generate_spice(
                self,
                plan_data: dict[str, Any],
                expert: Any,
                iteration: int = 1,
                previous_spice: Optional[str] = None,
                feedback: Optional[str] = None,
                retrieved_path: Optional[str] = None,
                temperature: float = 0.1,
                seed: Optional[int] = None,
            ) -> str:
                requirement = plan_data.get("elaborated_requirement", "")
                uid_model_map: dict[str, str] = {}
                if retrieved_path:
                    try:
                        retrieved_data = json.loads(
                            Path(retrieved_path).read_text(encoding="utf-8")
                        )
                        uid_model_map = {
                            str(uid): str(info["lib_id"])
                            for uid, info in retrieved_data.items()
                            if info and info.get("lib_id")
                        }
                    except (OSError, json.JSONDecodeError, TypeError):
                        uid_model_map = {}
                uid_parts = []
                for component in plan_data.get("components", []):
                    uid = component.get("uid")
                    if not uid:
                        continue
                    uid_parts.append(
                        f"{uid}({uid_model_map[uid]})" if uid in uid_model_map else str(uid)
                    )
                uid_hint = "、".join(uid_parts)
                system_prompt, user_prompt = expert.get_netlist_prompts(
                    requirement, uid_hint, iteration, previous_spice, feedback
                )
                request = {
                    "model": module.MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                }
                if seed is not None:
                    request["seed"] = seed
                if getattr(module, "THINKING_ENABLED", False):
                    request["extra_body"] = {"thinking": {"type": "enabled"}}
                elif getattr(module, "EXPLICIT_DISABLE_THINKING", False):
                    request["extra_body"] = {"thinking": {"type": "disabled"}}
                response = self.client.chat.completions.create(**request)
                raw = response.choices[0].message.content
                self.last_request = request
                self.last_response = raw
                usage = getattr(response, "usage", None)
                def usage_value(key: str) -> Any:
                    return usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
                self.last_usage = {
                    key: usage_value(key)
                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    if usage_value(key) is not None
                }
                self.last_usage["response_model_id"] = str(getattr(response, "model", ""))
                match = re.search(r"```spice\s*(.*?)\s*```", raw, re.I | re.S)
                return match.group(1).strip() if match else raw.replace("```", "").strip()

        return RawNetlistEngine

    def run_arm(
        self,
        plan: Mapping[str, Any],
        retrieved: Mapping[str, Any],
        workspace: Path,
        max_attempts: int,
        temperature: float,
        policy: str = "feedback",
        shield: bool = True,
    ) -> dict[str, Any]:
        raise RuntimeError(
            "native legacy evaluation is disabled; use run_arm_with_common_evaluator"
        )
        workspace.mkdir(parents=True, exist_ok=True)
        retrieved_path = workspace / "retrieved.json"
        retrieved_path.write_text(json.dumps(retrieved, indent=2, ensure_ascii=False), encoding="utf-8")
        plan_data = dict(plan)
        engine_type = self.netlist_module.NetlistEngine if shield else self._raw_engine_class()
        netlist_engine = engine_type()
        spice_engine = self.spice_module.SpiceEngine()
        expert = self.orchestrator_module.ExpertFactory.get_expert(plan_data.get("circuit_type", "filter"))
        if hasattr(expert, "set_targets"):
            expert.set_targets(plan_data.get("_benchmark_targets"))
        generation_index = 0

        def generate(iteration: int, previous: Optional[str], feedback: Optional[str]) -> Candidate:
            nonlocal generation_index
            generation_index += 1
            code = _call_supported(
                netlist_engine.generate_spice,
                plan_data,
                expert,
                iteration=iteration,
                previous_spice=previous,
                feedback=feedback,
                retrieved_path=str(retrieved_path),
                temperature=temperature,
            )
            return Candidate(code, dict(getattr(netlist_engine, "last_usage", {})))

        def evaluate(code: str, attempt: int) -> tuple[bool, str, dict[str, Any]]:
            result = _call_supported(
                spice_engine.evaluate,
                code,
                plan_data,
                expert,
                str(workspace),
                attempt,
                use_hard_threshold=True,
            )
            if len(result) == 2:
                passed, feedback = result
                return bool(passed), str(feedback), {}
            passed, feedback, measurements = result
            return bool(passed), str(feedback), measurements or {}

        result, selected_code = run_attempts(
            generate,
            evaluate,
            max_attempts,
            policy,
            stop_on_success=policy == "feedback",
        )
        if selected_code:
            (workspace / "selected.cir").write_text(selected_code, encoding="utf-8")
        result["response_model_ids"] = sorted(
            {
                str(attempt["usage"].get("response_model_id"))
                for attempt in result["attempts"]
                if attempt["usage"].get("response_model_id")
            }
        )
        return result

    def run_arm_with_common_evaluator(
        self,
        plan: Mapping[str, Any],
        retrieved: Mapping[str, Any],
        workspace: Path,
        max_attempts: int,
        temperature: float,
        evaluate_candidate: Any,
        policy: str = "feedback",
        seed: Optional[int] = None,
    ) -> dict[str, Any]:
        """Generate with the native workflow, but select only by a shared evaluator."""

        workspace.mkdir(parents=True, exist_ok=True)
        retrieved_path = workspace / "retrieved.json"
        retrieved_path.write_text(
            json.dumps(retrieved, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        plan_data = dict(plan)
        netlist_engine = self.netlist_module.NetlistEngine()
        expert = self.orchestrator_module.ExpertFactory.get_expert(
            plan_data.get("circuit_type", "filter")
        )
        if hasattr(expert, "set_targets"):
            expert.set_targets(plan_data.get("_benchmark_targets"))
        generation_index = 0

        def generate(iteration: int, previous: Optional[str], feedback: Optional[str]) -> Candidate:
            nonlocal generation_index
            generation_index += 1
            code = _call_supported(
                netlist_engine.generate_spice,
                plan_data,
                expert,
                iteration=iteration,
                previous_spice=previous,
                feedback=feedback,
                retrieved_path=str(retrieved_path),
                temperature=temperature,
                seed=(seed + generation_index - 1) if seed is not None else None,
            )
            attempt_root = workspace / f"attempt_{generation_index}"
            attempt_root.mkdir(parents=True, exist_ok=True)
            request = getattr(netlist_engine, "last_request", None)
            response = getattr(netlist_engine, "last_response", None)
            if request is not None:
                (attempt_root / "prompt.json").write_text(
                    json.dumps(request, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            if response is not None:
                (attempt_root / "response.txt").write_text(str(response), encoding="utf-8")
            return Candidate(code, dict(getattr(netlist_engine, "last_usage", {})))

        def evaluate(code: str, attempt: int) -> tuple[bool, str, dict[str, Any]]:
            return evaluate_candidate(code, attempt)

        result, selected_code = run_attempts(
            generate,
            evaluate,
            max_attempts,
            policy,
            stop_on_success=policy == "feedback",
        )
        if selected_code:
            (workspace / "selected.cir").write_text(selected_code, encoding="utf-8")
        result["response_model_ids"] = sorted(
            {
                str(attempt["usage"].get("response_model_id"))
                for attempt in result["attempts"]
                if attempt["usage"].get("response_model_id")
            }
        )
        return result

    def direct_plan(
        self,
        requirement: str,
        target: Optional[Mapping[str, Any]] = None,
        circuit_type: Optional[str] = None,
    ) -> dict[str, Any]:
        route = circuit_type or _infer_circuit_type(target or {})
        return {
            "elaborated_requirement": requirement,
            "components": [],
            "circuit_type": route,
            "_benchmark_targets": (
                dict(target)
                if target is not None
                else _target_from_requirement(requirement, route)
            ),
            "control": "direct_spec_to_spice_same_derived_expert_no_planner_or_retriever",
        }
