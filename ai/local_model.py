"""Deterministic local-model demo (``07_AI_AGENTS.md`` §Local model, ``12_AI_PROMPTS.md``
§Output Schemas, ``10_IMPLEMENTATION_PLAN.md`` Phase 6).

The local model owns the lightweight, repetitive, low-reasoning work the Phase-6 spec assigns it:
classification, extraction, deduplication, simple technology identification, keyword
classification, lightweight normalization, basic summarization, and repetitive analysis.

This is a **pure, deterministic demo** — it never calls a live model and never touches a target.
It is a stand-in for "a locally-installed model" so the router and validator can be exercised by
the test harness (Phase-6 acceptance: structured output end-to-end against a test harness, no
live target required). Outputs are emitted in the Common Output Contract shape and are therefore
schema-valid by construction; they are always **proposals**, never validated findings.
"""

from __future__ import annotations

from typing import Any

# Lightweight, repetitive analysis this model is documented to own (07_AI_AGENTS.md:33-35).
LOCAL_TASK_TYPES = frozenset(
    {
        "classification",
        "extraction",
        "deduplication",
        "tech_identification",
        "keyword_classification",
        "normalization",
        "basic_summarization",
        "repetitive_analysis",
    }
)

MODEL_ID = "argus-local-demo"


class LocalModelError(Exception):
    """A local-model demo rejected its input."""


def _iso_now() -> str:
    return "1970-01-01T00:00:00+00:00"


def simulate(task_type: str, target: str, observation: str) -> dict[str, Any]:
    """Deterministically produce a Common-Output-Contract proposal for a local task.

    Returns a schema-valid structured object (``type``/``target``/``observation``/``reasoning``/
    ``potential_issue``/``evidence``/``confidence``/``priority``/``truth_label``/
    ``validation_step``). One evidence item referencing the observed ``observation`` is always
    produced, so claims are always referenced — anything the validator would reject is never
    emitted here.
    """
    if task_type not in LOCAL_TASK_TYPES:
        raise LocalModelError(f"`{task_type}` is not a local-model task (07_AI_AGENTS.md:33-35)")
    if not target or not observation:
        raise LocalModelError("local demo requires non-empty `target` and `observation`")

    confidence = 0.9
    priority = "low"
    validation_step = "local_model: classification/extraction/dedup, simple tech id, keyword"

    return {
        "type": "hypothesis",  # demos never self-validate
        "target": target,
        "observation": observation,
        "reasoning": f"local model assigned `{task_type}` under 07_AI_AGENTS.md:33-35",
        "potential_issue": "proposal only; requires human-approved validation",
        "evidence": [
            {
                "statement": observation,
                "source": f"local_model({MODEL_ID}) demo: {_iso_now()}",
                "truth_label": "OBSERVATION",
            }
        ],
        "confidence": confidence,
        "priority": priority,
        "truth_label": "HYPOTHESIS",
        "validation_step": validation_step,
    }
