"""Common raw-SPICE evaluator for every main-comparison method.

The evaluator consumes a submitted deck and a public node manifest.  It creates
its own Ngspice control deck, preserving both decks and every measurement so a
method cannot rely on its private simulator-side acceptance rule.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


AC_METRICS = {"gain_magnitude_v_per_v", "cutoff_freq_hz"}

CANONICAL_OPAMP_NAMES = frozenset({"LM2904", "LM358", "LM324", "OPAMP"})


def _canonical_opamp(name: str) -> str:
    return (
        f".subckt {name} INP INM VCC VEE OUT PARAMS: A=1\n"
        "RIN INP INM 1G\n"
        "RVCC VCC 0 1G\n"
        "RVEE VEE 0 1G\n"
        "EGAIN NINT 0 INP INM {A*1MEG}\n"
        "ROUT NINT OUT 100\n"
        f".ends {name}\n"
    )


@dataclass(frozen=True)
class NodeManifest:
    input: str
    output: str
    ground: str = "0"
    load_element: str | None = None
    input_negative: str = "0"


@dataclass(frozen=True)
class AnalysisCondition:
    """Public testbench settings, identical for all methods on a task."""

    frequency_hz: float = 1000.0
    dc_sources: dict[str, float] = field(default_factory=dict)
    resistances: dict[str, float] = field(default_factory=dict)
    ac_sources: dict[str, tuple[float, float]] = field(default_factory=dict)


def _condition_commands(condition: AnalysisCondition, deck: str) -> list[str]:
    top_level = {}
    depth = 0
    for line in deck.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        if tokens[0].lower() == ".subckt":
            depth += 1
        elif tokens[0].lower() == ".ends":
            depth -= 1
        elif depth == 0 and tokens[0][0].upper() in {"V", "I", "R"}:
            name = tokens[0].upper()
            if name in top_level:
                raise ValueError(f"duplicate testbench element: {name}")
            top_level[name] = tokens
    commands = []

    def checked_name(name, prefixes):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise ValueError("invalid testbench element identifier")
        if name[0].upper() not in prefixes or name.upper() not in top_level:
            raise ValueError(f"required testbench element absent or wrong type: {name}")
        return name

    def number(value, *, positive=False):
        value = float(value)
        if not math.isfinite(value) or (positive and value <= 0):
            raise ValueError("invalid testbench numerical setting")
        return f"{value:.17g}"

    number(condition.frequency_hz, positive=True)
    for name, value in condition.dc_sources.items():
        commands.append(f"alter {checked_name(name, {'V', 'I'})} dc = {number(value)}")
    for name, value in condition.resistances.items():
        commands.append(f"alter {checked_name(name, {'R'})} = {number(value, positive=True)}")
    for name, (magnitude, phase) in condition.ac_sources.items():
        if magnitude < 0:
            raise ValueError("AC magnitude must be nonnegative")
        checked_name(name, {'V', 'I'})
        commands.extend([f"alter {name} acmag = {number(magnitude)}",
                         f"alter {name} acphase = {number(phase)}"])
    return commands


@dataclass(frozen=True)
class EvaluationResult:
    status: str
    failure_stage: str | None
    metric: str
    target: float
    tolerance: float
    measured: float | None
    passed: bool
    submitted_deck_sha256: str
    evaluated_deck_sha256: str | None
    artifacts: dict[str, str]
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sanitize_deck(deck: str) -> str:
    """Remove candidate-owned analyses while preserving circuit definitions."""

    forbidden_directives = {
        ".ac", ".dc", ".end", ".endc", ".four", ".meas", ".measure",
        ".op", ".plot", ".print", ".save", ".sens", ".tf", ".tran",
    }
    lines: list[str] = []
    in_control = False
    first_content = True
    for line in deck.splitlines():
        stripped = line.strip()
        if stripped and first_content:
            first_content = False
            # Accept a short conventional title without discarding the first
            # component of the title-free decks accepted by this interface.
            if not stripped.startswith(('*', '.', '+')) and len(stripped.split()) < 4:
                line = '* ' + line
                stripped = line.strip()
        directive = stripped.split(maxsplit=1)[0].lower() if stripped else ""
        if directive == ".control":
            in_control = True
            continue
        if in_control:
            if directive == ".endc":
                in_control = False
            continue
        if directive in {".include", ".inc", ".lib"}:
            raise ValueError("submitted deck must be self-contained; external includes are forbidden")
        if directive in forbidden_directives:
            continue
        lines.append(line)
    if in_control:
        raise ValueError("submitted deck contains an unterminated .control block")
    return "\n".join(lines).rstrip() + "\n"


def _required_canonical_subcircuits(deck: str) -> str:
    defined: set[str] = set()
    referenced: set[str] = set()
    for line in deck.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        tokens = stripped.split()
        if tokens[0].lower() == ".subckt" and len(tokens) >= 2:
            defined.add(tokens[1].upper())
        elif tokens[0][0].upper() == "X" and len(tokens) >= 2:
            # Known model names may precede PARAMS: or parameter assignments.
            referenced.update(token.upper() for token in tokens[1:] if token.upper() in CANONICAL_OPAMP_NAMES)
    needed = sorted((referenced - defined) & CANONICAL_OPAMP_NAMES)
    if not needed:
        return ""
    return "* frozen canonical device models\n" + "".join(
        _canonical_opamp(name) for name in needed
    )


def _spice_number(token: str) -> float:
    suffixes = {
        "T": 1e12, "G": 1e9, "MEG": 1e6, "K": 1e3,
        "M": 1e-3, "U": 1e-6, "N": 1e-9, "P": 1e-12, "F": 1e-15,
    }
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([a-zA-Z]*)', token.strip())
    if not match:
        raise ValueError(f'invalid SPICE number: {token}')
    number, upper = float(match.group(1)), match.group(2).upper()
    if upper.startswith('MIL'):
        return number * 25.4e-6
    for suffix in sorted(suffixes, key=len, reverse=True):
        if upper.startswith(suffix):
            return number * suffixes[suffix]
    return number


def _validate_canonical_opamp_supplies(deck: str) -> None:
    sources: dict[str, float] = {"0": 0.0}
    instances: list[tuple[str, str, str]] = []
    defined: set[str] = set()
    for line in deck.splitlines():
        tokens = line.strip().split()
        if not tokens or tokens[0].startswith("*"):
            continue
        if tokens[0].lower() == ".subckt" and len(tokens) >= 2:
            defined.add(tokens[1].upper())
            continue
        if tokens[0][0].upper() == "V" and len(tokens) >= 4 and "0" in tokens[1:3]:
            value_index = 4 if tokens[3].upper() == "DC" and len(tokens) >= 5 else 3
            try:
                value = _spice_number(tokens[value_index])
            except (ValueError, IndexError):
                continue
            positive, negative = tokens[1].upper(), tokens[2].upper()
            if negative == "0":
                sources[positive] = value
            elif positive == "0":
                sources[negative] = -value
        if tokens[0][0].upper() == "X":
            model_index = next(
                (index for index, token in enumerate(tokens) if token.upper() in CANONICAL_OPAMP_NAMES),
                None,
            )
            if model_index is not None and model_index >= 6:
                instances.append((tokens[model_index].upper(), tokens[model_index - 3].upper(), tokens[model_index - 2].upper()))
    for model, vcc_node, vee_node in instances:
        if model in defined:
            continue
        if vcc_node not in sources or vee_node not in sources:
            raise ValueError(f"{model} requires explicit supply sources for {vcc_node}/{vee_node}")
        if sources[vcc_node] <= sources[vee_node] or sources[vcc_node] == 0:
            raise ValueError(f"{model} supply rails must be nonzero and ordered VCC > VEE")


def _relative_pass(measured: float, target: float, tolerance: float) -> bool:
    if not all(math.isfinite(value) for value in (measured, target, tolerance)):
        return False
    if tolerance <= 0 or target == 0:
        return False
    return abs(measured - target) <= tolerance * abs(target)


def _acceptance(measured: float, target: dict[str, Any]) -> tuple[bool, str | None]:
    if "minimum" in target or "maximum" in target:
        lower, upper = float(target["minimum"]), float(target["maximum"])
        if not all(math.isfinite(value) for value in (lower, upper)) or lower > upper:
            raise ValueError("invalid acceptance interval")
        passed = math.isfinite(measured) and lower <= measured <= upper
        return passed, None if passed else f"measured={measured:.8g}; required interval=[{lower:.8g}, {upper:.8g}]"
    value, tolerance = float(target["value"]), float(target["tolerance"])
    passed = _relative_pass(measured, value, tolerance)
    return passed, None if passed else (
        f"measured={measured:.8g}, target={value:.8g}, relative tolerance={tolerance:.8g}; "
        "acceptance condition: abs(measured-target) <= tolerance*abs(target)"
    )


def _numeric_rows(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        values: list[float] = []
        for token in line.replace(",", " ").split():
            try:
                values.append(float(token))
            except ValueError:
                continue
        if values:
            rows.append(values)
    return rows


def _ac_trace(path: Path) -> list[tuple[float, float]]:
    trace: list[tuple[float, float]] = []
    for row in _numeric_rows(path):
        if len(row) < 2:
            continue
        frequency, db = row[0], row[-1]
        if frequency > 0 and math.isfinite(db):
            trace.append((frequency, db))
    if len(trace) < 2:
        raise ValueError("AC trace contains fewer than two usable points")
    return trace


def _cutoff_frequency(trace: list[tuple[float, float]]) -> float:
    peak_index = max(range(len(trace)), key=lambda index: trace[index][1])
    threshold = trace[peak_index][1] - 3.0
    previous_frequency, previous_db = trace[peak_index]
    for frequency, db in trace[peak_index + 1 :]:
        if db <= threshold <= previous_db and db != previous_db:
            fraction = (threshold - previous_db) / (db - previous_db)
            return math.exp(
                math.log(previous_frequency)
                + fraction * (math.log(frequency) - math.log(previous_frequency))
            )
        previous_frequency, previous_db = frequency, db
    raise ValueError("no -3 dB crossing after the passband peak")


def _measurement_from_trace(metric: str, trace_path: Path) -> float:
    if metric == "gain_magnitude_v_per_v":
        peak_db = max(db for _, db in _ac_trace(trace_path))
        return 10.0 ** (peak_db / 20.0)
    if metric == "cutoff_freq_hz":
        return _cutoff_frequency(_ac_trace(trace_path))
    rows = _numeric_rows(trace_path)
    if not rows:
        raise ValueError("DC trace contains no numeric measurement")
    value = abs(rows[-1][-1]) if metric == "load_current_a" else rows[-1][-1]
    if not math.isfinite(value):
        raise ValueError("DC measurement is non-finite")
    return value


def _control_block(metric: str, manifest: NodeManifest, trace_path: Path,
                   condition: AnalysisCondition | None = None,
                   commands: list[str] | None = None) -> str:
    escaped = str(trace_path).replace("\\", "\\\\")
    for node in (manifest.input, manifest.input_negative, manifest.output, manifest.ground):
        if not re.fullmatch(r"[A-Za-z0-9_]+", node):
            raise ValueError("unsupported node identifier")
    if metric in {"gain_real_v_per_v", "gain_at_frequency_v_per_v", "output_ac_magnitude_v"}:
        frequency = (condition or AnalysisCondition()).frequency_hz
        output_voltage = (f"v({manifest.output})" if manifest.ground == "0" else
                          f"(v({manifest.output})-v({manifest.ground}))")
        input_voltage = (f"v({manifest.input})" if manifest.input_negative == "0" else
                         f"(v({manifest.input})-v({manifest.input_negative}))")
        ratio = f"{output_voltage}/{input_voltage}"
        expression = (f"real({ratio})" if metric == "gain_real_v_per_v" else
                      f"mag({ratio})" if metric == "gain_at_frequency_v_per_v" else
                      f"mag({output_voltage})")
        command = f"ac lin 1 {frequency:.17g} {frequency:.17g}"
    elif metric in AC_METRICS:
        expression = f"vdb({manifest.output})"
        command = "ac dec 20 1 10000000"
    elif metric == "dc_voltage_v":
        expression = f"v({manifest.output})"
        command = "op"
    elif metric == "load_current_a":
        if not manifest.load_element:
            raise ValueError("load_current_a requires node_manifest.load_element")
        if not re.fullmatch(r"V[A-Za-z0-9_]+", manifest.load_element, re.IGNORECASE):
            raise ValueError("load current requires a named voltage-source ammeter")
        expression = f"i({manifest.load_element})"
        command = "op"
    else:
        raise ValueError(f"unsupported metric: {metric}")
    return (
        "\n.control\n"
        "set filetype=ascii\n"
        + "".join(line + "\n" for line in (commands or []))
        +
        f"{command}\n"
        f"wrdata {escaped} {expression}\n"
        "quit\n.endc\n.end\n"
    )


def _simulation_diagnostics(log_path: Path, stderr: str, stdout: str) -> str:
    """Keep error context bounded while leaving complete logs in artifacts."""
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    lines = (log + "\n" + stderr + "\n" + stdout).splitlines()
    markers = ("error", "fatal", "unknown", "not found", "can't find", "cannot",
               "failed", "singular", "timestep too small", "no such", "undefined")
    selected: list[str] = []
    for index, line in enumerate(lines):
        if any(marker in line.lower() for marker in markers):
            for context in lines[max(0, index - 1):index + 3]:
                context = context.strip()
                if context and context not in selected:
                    selected.append(context)
    if not selected:
        selected = [line.strip() for line in lines if line.strip()][-8:]
    return "\n".join(selected[:24])[:2400]


def evaluate_deck(
    submitted_deck: Path,
    node_manifest: NodeManifest,
    target: dict[str, Any],
    output_dir: Path,
    *,
    ngspice: str = "ngspice",
    timeout_seconds: int = 90,
    condition: AnalysisCondition | None = None,
) -> EvaluationResult:
    """Evaluate one raw deck under the frozen cross-method contract."""

    output_dir.mkdir(parents=True, exist_ok=True)
    metric = str(target["metric"])
    target_value = float(target["value"])
    tolerance = float(target["tolerance"])
    submitted_hash = _sha256(submitted_deck)
    trace_path = output_dir / "numeric_trace.txt"
    evaluated_deck = output_dir / "evaluated.cir"
    log_path = output_dir / "ngspice.log"
    stdout_path = output_dir / "ngspice.stdout"
    stderr_path = output_dir / "ngspice.stderr"
    manifest_path = output_dir / "node_manifest.json"
    manifest_path.write_text(json.dumps(asdict(node_manifest), indent=2) + "\n", encoding="utf-8")

    try:
        submitted_text = submitted_deck.read_text(encoding="utf-8", errors="replace")
        if not submitted_text.strip():
            raise ValueError("submitted deck is empty")
        sanitized_text = _sanitize_deck(submitted_text)
        _validate_canonical_opamp_supplies(sanitized_text)
        commands = _condition_commands(condition, sanitized_text) if condition else []
        evaluated_deck.write_text(
            "* shared evaluator deck\n"
            + sanitized_text
            + _required_canonical_subcircuits(sanitized_text)
            + _control_block(metric, node_manifest, trace_path, condition, commands),
            encoding="utf-8",
        )
    except Exception as exc:
        return EvaluationResult(
            "failed", "parse", metric, target_value, tolerance, None, False,
            submitted_hash, None, {"node_manifest": str(manifest_path)}, str(exc),
        )

    try:
        completed = subprocess.run(
            [ngspice, "-b", "-o", str(log_path), str(evaluated_deck)],
            cwd=output_dir,
            env={
                key: os.environ[key]
                for key in (
                    "PATH", "LD_LIBRARY_PATH", "SPICE_LIB_DIR", "LANG", "LC_ALL"
                )
                if key in os.environ
            }
            | {"HOME": str(output_dir), "TMPDIR": str(output_dir)},
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired as exc:
        stderr_path.write_text(str(exc), encoding="utf-8")
        return EvaluationResult(
            "failed", "timeout", metric, target_value, tolerance, None, False,
            submitted_hash, _sha256(evaluated_deck),
            {"evaluated_deck": str(evaluated_deck), "stderr": str(stderr_path)}, str(exc),
        )
    except OSError as exc:
        stderr_path.write_text(str(exc), encoding="utf-8")
        return EvaluationResult(
            "failed", "simulation", metric, target_value, tolerance, None, False,
            submitted_hash, _sha256(evaluated_deck),
            {"evaluated_deck": str(evaluated_deck), "stderr": str(stderr_path)}, str(exc),
        )

    artifacts = {
        "submitted_deck": str(submitted_deck),
        "evaluated_deck": str(evaluated_deck),
        "node_manifest": str(manifest_path),
        "simulator_log": str(log_path),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }
    if trace_path.is_file():
        artifacts["numeric_trace"] = str(trace_path)
    if completed.returncode != 0 or not trace_path.is_file():
        diagnostics = _simulation_diagnostics(log_path, completed.stderr, completed.stdout)
        detail = f"ngspice return code {completed.returncode}"
        if not trace_path.is_file():
            detail += "; numeric trace was not produced"
        if diagnostics:
            detail += "\n" + diagnostics
        return EvaluationResult(
            "failed", "simulation", metric, target_value, tolerance, None, False,
            submitted_hash, _sha256(evaluated_deck), artifacts,
            detail,
        )
    try:
        measured = _measurement_from_trace(metric, trace_path)
    except (OSError, ValueError) as exc:
        return EvaluationResult(
            "failed", "evaluation", metric, target_value, tolerance, None, False,
            submitted_hash, _sha256(evaluated_deck), artifacts, str(exc),
        )
    passed, detail = _acceptance(measured, target)
    result = EvaluationResult(
        "success", None, metric, target_value, tolerance, measured,
        passed, submitted_hash,
        _sha256(evaluated_deck), artifacts, detail,
    )
    (output_dir / "measurement.json").write_text(
        json.dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8"
    )
    return result


def evaluate_conditions(submitted_deck: Path, checks: list[dict[str, Any]],
                        output_dir: Path, *, ngspice: str = "ngspice") -> dict[str, Any]:
    """Execute every declared condition; task acceptance requires all checks."""
    if not checks:
        raise ValueError("at least one acceptance check is required")
    observations = []
    for index, check in enumerate(checks, 1):
        result = evaluate_deck(
            submitted_deck, NodeManifest(**check["nodes"]), check["target"],
            output_dir / f"condition_{index:02d}", ngspice=ngspice,
            condition=AnalysisCondition(**check.get("condition", {})),
        )
        observations.append({"check": check, "result": result.as_dict()})
    summary = {"passed": all(row["result"]["passed"] for row in observations),
               "checks": observations, "submitted_deck_sha256": _sha256(submitted_deck)}
    (output_dir / "conditions.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
