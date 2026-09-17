"""Pure feedback and independent-sampling policies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional


Usage = Mapping[str, Optional[int]]
Generate = Callable[[int, Optional[str], Optional[str]], "Candidate"]
Evaluate = Callable[[str, int], tuple[bool, str, dict[str, Any]]]


@dataclass(frozen=True)
class Candidate:
    code: str
    usage: Usage = field(default_factory=dict)


def _usage_total(attempts: list[dict[str, Any]], key: str) -> Optional[int]:
    values = [
        item["usage"].get(key)
        for item in attempts
        if item["usage"].get(key) is not None
    ]
    return sum(values) if values else None


def run_attempts(
    generate: Generate,
    evaluate: Evaluate,
    max_attempts: int,
    policy: str,
    stop_on_success: bool,
) -> tuple[dict[str, Any], Optional[str]]:
    """Run one synthesis arm with an auditable prompt-information policy."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    if policy not in {"feedback", "independent"}:
        raise ValueError("policy must be feedback or independent")

    attempts: list[dict[str, Any]] = []
    previous: Optional[str] = None
    feedback: Optional[str] = None
    selected_code: Optional[str] = None
    first_success: Optional[int] = None
    selected_metrics: dict[str, Any] = {}
    error: Optional[str] = None

    for attempt in range(1, max_attempts + 1):
        prompt_iteration = attempt if policy == "feedback" else 1
        prompt_previous = previous if policy == "feedback" else None
        prompt_feedback = feedback if policy == "feedback" else None
        try:
            candidate = generate(prompt_iteration, prompt_previous, prompt_feedback)
        except Exception as exc:  # Persist partial budget evidence.
            error = f"generation_error:{type(exc).__name__}:{exc}"
            break

        duplicate = previous is not None and candidate.code.strip() == previous.strip()
        row: dict[str, Any] = {
            "attempt": attempt,
            "prompt_iteration": prompt_iteration,
            "policy": policy,
            "duplicate": duplicate,
            "usage": dict(candidate.usage),
            "passed": False,
            "measurements": {},
        }
        attempts.append(row)
        selected_code = candidate.code
        if duplicate and policy == "feedback":
            previous = candidate.code
            continue

        try:
            passed, next_feedback, measurements = evaluate(candidate.code, attempt)
        except Exception as exc:
            error = f"evaluation_error:{type(exc).__name__}:{exc}"
            break
        row.update(
            passed=bool(passed),
            feedback=next_feedback,
            measurements=measurements or {},
        )
        if passed and first_success is None:
            first_success = attempt
            selected_code = candidate.code
            selected_metrics = measurements or {}
        elif first_success is None:
            selected_metrics = measurements or {}
        if passed and stop_on_success:
            break
        previous = candidate.code
        if policy == "feedback":
            feedback = next_feedback

    return (
        {
            "passed": first_success is not None,
            "policy": policy,
            "stop_on_success": stop_on_success,
            "llm_calls": len(attempts),
            "iterations": len(attempts),
            "first_success_attempt": first_success,
            "measurements": selected_metrics,
            "attempts": attempts,
            "prompt_tokens": _usage_total(attempts, "prompt_tokens"),
            "completion_tokens": _usage_total(attempts, "completion_tokens"),
            "total_tokens": _usage_total(attempts, "total_tokens"),
            "error": error,
        },
        selected_code,
    )
