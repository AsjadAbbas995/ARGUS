"""Cloud/stronger-model demo ("07_AI_AGENTS.md" §Cloud/stronger model:37-39, "12_AI_PROMPTS.md"
§Output Schemas; Phase 6).

Deterministic stand-in for the cloud/stronger model in the Phase-6 hybrid demo. It is a pure
function: given a documented *cloud* task type plus the observation set it is asked to reason
over, it produces exactly one Common Output Contract object labelled ``HYPOTHESIS`` — it may
never label its own output ``VALIDATED_FINDING``, may never execute anything, and may never
invent observations (07_AI_AGENTS.md "AI Safety Boundary", "05_DATA_MODEL.md" §hypotheses).
Used only by the test harness; no live target is required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

# Cloud-model task taxonomy (07_AI_AGENTS.md:37-39). Deterministic demo only.
CLOUD_TASK_TYPES = frozenset(
    {
        "complex_correlation",
        "attack_surface_reasoning",
        "multi_source_analysis",
        "api_relationship_analysis",
        "hypothesis_generation",
        "prioritization",
        "complex_recon_planning",
    }
)

_MODEL_ID = "argus-cloud-demo-01"

_TRUTH_LABEL = "HYPOTHESIS"


class CloudModelError(Exception):
    """Rejected a cloud-model request that is not part of the documented demo contract."""


@dataclass(frozen=True)
class CloudProposal:
    """One schema-shaped structured-output proposal from the cloud model."""

    type: str
    target: str
    observation: str
    reasoning: str
    potential_issue: str
    evidence_value: tuple[str, ...]
    confidence: float
    priority: str
    validation_step: str
    truth_label: str
    model_used: str


def simulate_cloud(
    task_type: str,
    target: str,
    observations: Sequence[str],
    /,
    *,
    confidence: float = 0.8,
    priority: str = "high",
) -> CloudProposal:
    """Deterministically propose one structured hypothesis for a documented cloud task.

    Deterministic: identical (task_type, target, observations) always yields an identical ddd
    proposal. Never validates itself and never asserts a finding.
    """
    if task_type not in CLOUD_TASK_TYPES:
        raise CloudModelError(f"`{task_type}` is not a documented cloud task")
    if not target or not observations:
        raise CloudModelError("cloud tasks require a target and >=1 observation")
    if not (0.0 <= confidence <= 1.0):
        raise CloudModelError("confidence must be within [0.0, 1.0]")

    return CloudProposal(
        type="hypothesis",
        target=target,
        observation=observations[0],
        reasoning=(
            f"{task_type} correlates {len(observations)} observations; cloud model {_MODEL_ID} "
            "proposes the following (schema-shaped, hypothesis only)."
        ),
        potential_issue=(
            "attack-surface hypothesis; requires human-reviewed validation before promotion."
        ),
        evidence_value=tuple(observations),
        confidence=confidence,
        priority=priority,
        validation_step="human-approved validation of the proposed hypothesis",
        truth_label=_TRUTH_LABEL,
        model_used=_MODEL_ID,
    )


def simulate(
    task_type: str,
    target: str,
    observations: Sequence[str],
    *,
    confidence: float = 0.8,
    priority: str = "high",
) -> dict[str, Any]:
    """Deterministically propose one schema-valid Common Output Contract object for a cloud task.

    Returns a plain ``dict`` shaped exactly as the Common Output Contract (the ``CloudProposal``
    dataclass above is not a ``Mapping`` and would not validate). Evidence references only the
    caller-supplied ``observations`` — nothing is fabricated (07_AI_AGENTS.md "AI Safety
    Boundary"). Deterministic: identical inputs always yield identical output; never labels its
    own proposal ``VALIDATED_FINDING`` and never executes anything.
    """
    if task_type not in CLOUD_TASK_TYPES:
        raise CloudModelError(f"`{task_type}` is not a documented cloud task")
    if not target or not observations:
        raise CloudModelError("cloud tasks require a target and at least one observation")
    if not (0.0 <= confidence <= 1.0):
        raise CloudModelError("confidence must be within [0.0, 1.0]")
    if priority not in {"low", "medium", "high"}:
        raise CloudModelError("priority must be one of low | medium | high")

    return {
        "type": "hypothesis",  # demos never self-validate
        "target": target,
        "observation": observations[0],
        "reasoning": (
            f"{task_type} correlates {len(observations)} observations; cloud model {_MODEL_ID} "
            "proposes the following (schema-shaped, hypothesis only)."
        ),
        "potential_issue": (
            "attack-surface hypothesis; requires human-reviewed validation before promotion."
        ),
        "evidence": [
            {
                "statement": obs,
                "source": f"cloud_model({_MODEL_ID}) demo (caller-supplied observation)",
            }
            for obs in observations
        ],
        "confidence": confidence,
        "priority": priority,
        "validation_step": "human-approved validation of the proposed hypothesis",
        "truth_label": _TRUTH_LABEL,
    }
