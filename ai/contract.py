"""Deterministic Common Output Contract shapers ("07_AI_AGENTS.md" §Output Schemas,
"12_AI_PROMPTS.md" §Output Schemas).

Phase-7 agents never hand-build output dicts: they shape every proposal through ``evidence``
and ``proposal`` below so the required fields and types stay byte-stable and
validator-compliant. Each shaped object is immediately run through
``validator.validate_structured_output`` — an off-contract shape is **rejected at
construction** (never silently re-serialised), mirroring the Phase-6 validator philosophy.

Outputs are always *proposals*: a proposal may never label itself ``VALIDATED_FINDING``
unless it is relaying an already-validated finding (07_AI_AGENTS.md "AI Safety Boundary").
"""

from __future__ import annotations

from typing import Any, Mapping

from .validator import validate_structured_output


def evidence(statement: str, source: str) -> dict[str, str]:
    """Shape one confirmed-format evidence item referencing caller-supplied content."""
    return {"statement": statement, "source": source}


def proposal(
    *,
    type: str,
    target: str,
    observation: str,
    reasoning: str,
    potential_issue: str,
    evidence: list[Mapping[str, str]],
    confidence: float,
    priority: str,
    validation_step: str,
    truth_label: str,
) -> dict[str, Any]:
    """Shape and verify one Common Output Contract proposal.

    Raises ``ValueError`` if the shape is off-contract or the proposal self-validates.
    """
    if truth_label == "VALIDATED_FINDING" and type != "finding":
        raise ValueError(
            "agents may never label their own proposal VALIDATED_FINDING (07_AI_AGENTS.md)"
        )
    if not evidence:
        raise ValueError("a proposal must cite at least one caller-supplied evidence item")

    shaped = {
        "type": type,
        "target": target,
        "observation": observation,
        "reasoning": reasoning,
        "potential_issue": potential_issue,
        "evidence": list(evidence),
        "confidence": confidence,
        "priority": priority,
        "validation_step": validation_step,
        "truth_label": truth_label,
    }
    result = validate_structured_output(shaped)
    if not result.valid:
        raise ValueError(
            f"off-contract proposal rejected at construction: {result.reason()}"
        )
    return shaped