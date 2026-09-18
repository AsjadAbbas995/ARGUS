"""ARGUS AI structured-output validator ("07_AI_AGENTS.md" §Common Output Contract + §Output
Schemas, "12_AI_PROMPTS.md" §Output Schemas, "05_DATA_MODEL.md" §hypotheses/§evidence).

Phase-6 acceptance ("10_IMPLEMENTATION_PLAN.md" §Phase 6): every agent's structured output must
be schema-valid before it reaches the Task Planner, and **invalid agent output is rejected**
rather than silently accepted. This validator enforces the Common Output Contract byte-exactly:

* all required fields present (``type``/``target``/``observation``/``reasoning``/
  ``potential_issue``/``evidence``/``confidence``/``priority``/``validation_step``)
  with the correct types;
* ``confidence`` within ``[0.0, 1.0]``;
* ``priority`` one of ``low|medium|high``;
* ``truth_label`` drawn from the documented label set (``FACT``, ``OBSERVATION``,
  ``INFERENCE``, ``HYPOTHESIS``, ``UNVERIFIED_CLAIM``, ``VALIDATED_FINDING``);
* a non-empty ``evidence`` list whose items are themselves schema-valid evidence records
  (each with ``statement`` + ``source``), so unreferenced claims are rejected;
* truth-label/type coherence — a ``hypothesis`` may never be labelled
  ``VALIDATED_FINDING`` (only validation may promote a hypothesis).

The validator is deterministic and pure: same object in, same verdict out. It never executes
anything; every agent output is a *proposal* (07_AI_AGENTS.md "AI Safety Boundary").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

# Documented truth-label vocabulary (01_PRODUCT_SPEC.md §truth labels, 04_SCOPE_SAFETY,
# 12_AI_PROMPTS.md §Output Schemas). Labels outside this set are rejected.
TRUTH_LABELS = frozenset(
    {"FACT", "OBSERVATION", "INFERENCE", "HYPOTHESIS", "UNVERIFIED_CLAIM", "VALIDATED_FINDING"}
)

_PRIORITIES = frozenset({"low", "medium", "high"})

# Structured-output types an agent may emit (07_AI_AGENTS.md agent contracts).
_OUTPUT_TYPES = frozenset({"hypothesis", "observation", "unverified_claim", "finding", "task"})

# Required fields of the Common Output Contract, each mapped to its allowed type.
_REQUIRED_FIELDS: tuple[tuple[str, type], ...] = (
    ("type", str),
    ("target", str),
    ("observation", str),
    ("reasoning", str),
    ("potential_issue", str),
    ("evidence", list),
    ("confidence", float),
    ("priority", str),
    ("validation_step", str),
)

# Fields whose value must be a non-empty str.
_NONEMPTY_STR_FIELDS = ("type", "target", "observation", "reasoning", "validation_step")

# A hypothesis-liked output must never claim to already be a finding.
_FINDING_AS_HYPOTHESIS = ("VALIDATED_FINDING",)


@dataclass(frozen=True)
class ValidationFailure:
    """A single documented validation violation."""

    field: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    """Byte-deterministic verdict for one structured object."""

    valid: bool
    failures: tuple[ValidationFailure, ...] = field(default_factory=tuple)

    def reason(self) -> str:
        return "; ".join(f"{f.field}: {f.message}" for f in self.failures) if self.failures else "ok"


def _validate_evidence(evidence: Any) -> tuple[ValidationFailure, ...]:
    failures: list[ValidationFailure] = []
    if not isinstance(evidence, list) or not evidence:
        return (ValidationFailure("evidence", "missing or empty evidence (unreferenced claim)"),)
    for i, item in enumerate(evidence):
        if not isinstance(item, Mapping):
            failures.append(ValidationFailure(f"evidence[{i}]", "evidence item is not an object"))
            continue
        statement = item.get("statement")
        source = item.get("source")
        if not isinstance(statement, str) or not statement.strip():
            failures.append(
                ValidationFailure(f"evidence[{i}].statement", "missing statement in evidence")
            )
        if not isinstance(source, str) or not source.strip():
            failures.append(ValidationFailure(f"evidence[{i}].source", "missing source in evidence"))
    return tuple(failures)


def validate_structured_output(output: Mapping[str, Any]) -> ValidationResult:
    """Validate one agent output against the Common Output Contract.

    Deterministic: pure function of ``output`` alone. Returns a ``ValidationResult``; invalid
    output is *rejected* (never silently re-serialised into a valid shape).
    """
    failures: list[ValidationFailure] = []
    if not isinstance(output, Mapping):
        return ValidationResult(False, (ValidationFailure("output", "output is not an object"),))

    for name, expected_type in _REQUIRED_FIELDS:
        if name not in output:
            failures.append(ValidationFailure(name, f"missing required field `{name}`"))
            continue
        value = output[name]
        if not isinstance(value, expected_type):
            failures.append(
                ValidationFailure(name, f"`{name}` must be {expected_type.__name__}")
            )

    for name in _NONEMPTY_STR_FIELDS:
        value = output.get(name)
        if value is not None and not isinstance(value, str):
            continue
        if value is not None and not value.strip() and name in output:
            failures.append(ValidationFailure(name, f"`{name}` must not be empty"))

    type_value = output.get("type")
    if isinstance(type_value, str) and type_value not in _OUTPUT_TYPES:
        failures.append(
            ValidationFailure("type", f"unknown structured-output type `{type_value}`")
        )

    truth_label = output.get("truth_label")
    if truth_label is not None and (
        not isinstance(truth_label, str) or truth_label not in TRUTH_LABELS
    ):
        failures.append(
            ValidationFailure("truth_label", f"invalid truth label `{truth_label}`")
        )

    # A hypothesis/unverified-claim output may never assert it is already a validated finding;
    # only the validator/validated-promotion path may mark a finding (07_AI_AGENTS.md §ReconAgent
    # forbidden actions; 12_AI_PROMPTS.md §Output Schemas).
    if isinstance(type_value, str) and isinstance(truth_label, str):
        if (
            type_value in ("hypothesis", "unverified_claim", "observation")
            and truth_label in _FINDING_AS_HYPOTHESIS
        ):
            failures.append(
                ValidationFailure(
                    "truth_label",
                    f"`{type_value}` output cannot be labelled `{truth_label}`",
                )
            )

    confidence = output.get("confidence")
    if isinstance(confidence, float) and not (0.0 <= confidence <= 1.0):
        failures.append(ValidationFailure("confidence", "confidence must be within [0.0, 1.0]"))

    priority = output.get("priority")
    if isinstance(priority, str) and priority not in _PRIORITIES:
        failures.append(
            ValidationFailure("priority", f"invalid priority `{priority}` "
                                          f"(expected one of {sorted(_PRIORITIES)})")
        )

    failures.extend(_validate_evidence(output.get("evidence")))

    return ValidationResult(not failures, tuple(failures))
