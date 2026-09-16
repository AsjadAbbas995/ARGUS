"""Deterministic cloud-model demo ("07_AI_AGENTS.md" §Cloud/stronger model, "12_AI_PROMPTS.md"
§Output Schemas — ARGUS hybrid AI layer, Phase 6).

Phase-6 DoD ("10_IMPLEMENTATION_PLAN.md" §Phase 6): the AI layer produces schema-valid structured
output end-to-end through the test harness with **no live target and no live model** — every
output is a deterministic *proposal*. This module is the cloud half of that harness
("07_AI_AGENTS.md" §Cloud/stronger model): complex correlation, attack-surface reasoning,
multi-source analysis, complicated API relationships, hypothesis generation, prioritization, and
complex reconnaissance planning.

The output contract is byte-exact with the Common Output Contract (07_AI_AGENTS.md:44-61) and is
identical in shape to `local_model.simulate` — the router's decision changes which model id runs,
never the shape. Cloud outputs cite real (in-run) evidence ids; hypotheses are never self-labelled
``VALIDATED_FINDING`` (07_AI_AGENTS.md §forbidden actions).
"""

from __future__ import annotations

from typing import Any, FrozenSet, Mapping, Optional, Sequence

from ai.local_model import _iso_now  # noqa: PLC2701 (private sibling reuse, same package)

# Documented cloud-model task taxonomy (07_AI_AGENTS.md:37-39); anything else is *not* a cloud task.
CLOUD_TASK_TYPES: FrozenSet[str] = frozenset(
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

_MODEL_ID = "ARGUS-cloud-01"

_PRIORITIES = frozenset({"low", "medium", "high"})


class CloudModelError(Exception):
    """The cloud model rejected input it may not reason about (07_AI_AGENTS.md §forbidden)."""


def simulate(
    task_type: str,
    target: str,
    observations: Sequence[str],
    /,
    confidence: Optional[float] = None,
) -> dict[str, Any]:
    """Deterministically produce one schema-valid cloud-model proposal.

    Local to Phase-6 harness: no live model, no target I/O — the proposal aggregates the
    ``observations`` it is given and must be supported by them (Common Output Contract
    §evidence). Raises ``CloudModelError`` for off-taxonomy task types, empty/missing evidence
    observations, or an out-of-range ``confidence`` — deterministic, and the output never leaves
    this function unless it is already schema-valid.
    """
    if task_type not in CLOUD_TASK_TYPES:
        raise CloudModelError(
            f"`{task_type}` is not a documented cloud-model task "
            f"(07_AI_AGENTS.md §Cloud/stronger model; got one of {sorted(CLOUD_TASK_TYPES)})"
        )
    if not target or not isinstance(target, str):
        raise CloudModelError("cloud tasks require a non-empty string `target`")
    if not observations or not all(isinstance(o, str) and o.strip() for o in observations):
        raise CloudModelError("cloud tasks require at least one non-empty observation (evidence)")
    if confidence is not None and not (0.0 <= float(confidence) <= 1.0):
        raise CloudModelError(f"confidence must lie within [0.0, 1.0], got {confidence!r}")

    used = float(confidence) if confidence is not None else 0.8
    priority = "high" if task_type in ("complex_recon_planning", "hypothesis_generation") else "medium"

    return {
        "type": "hypothesis",
        "target": target,
        "observation": observations[0],
        "reasoning": (
            f"cloud model `{_MODEL_ID}`: `{task_type}` requires complex correlation/"
            f"attack-surface reasoning across {len(observations)} observation(s)"
            " (07_AI_AGENTS.md §Cloud/stronger model)"
        ),
        "potential_issue": "proposal only; requires a human-approved validation step",
        "evidence": [
            {"statement": o, "source": f"cloud-model observation {i + 1} (in-run evidence)"}
            for i, o in enumerate(observations)
        ],
        "confidence": used,
        "priority": priority,
        "validation_step": "schema-validated by ai/validator.py (Phase 6)",
        "truth_label": "HYPOTHESIS",
        "model_used": _MODEL_ID,
    }
</content>
