"""TriageAgent ("07_AI_AGENTS.md" §TriageAgent).

Ranks all open hypotheses by priority weight, then confidence, then evidence breadth, and
emits the top-ranked item. The underlying hypothesis's ``truth_label`` and evidence are
preserved verbatim — ranking may never change them to make an item rank higher. An
already-validated hypothesis is relayed as-is (``type="finding"``), never re-labelled. Emits
no proposal with no open hypotheses.
"""

from __future__ import annotations

from typing import Optional

from .context import HypothesisRecord, TriageContext
from .contract import evidence, proposal
from .route import route
from .router import RouteConfig

ROUTE_TASK = "prioritization"

_PRIORITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}

# Relayed type follows the preserved truth label (validator coherence rule: a
# hypothesis/unverified-claim/observation output may never carry ``VALIDATED_FINDING``).
_TYPE_BY_LABEL = {
    "VALIDATED_FINDING": "finding",
    "HYPOTHESIS": "hypothesis",
    "UNVERIFIED_CLAIM": "unverified_claim",
    "OBSERVATION": "observation",
    "INFERENCE": "observation",
    "FACT": "observation",
}


def run(ctx: TriageContext, cfg: Optional[RouteConfig] = None) -> Optional[dict]:
    """Return a schema-valid relay of the top-ranked hypothesis, or ``None`` when empty."""
    route(ROUTE_TASK, complexity="medium", reasoning_depth="medium", cfg=cfg)

    if not ctx.hypotheses:
        return None

    top = max(
        ctx.hypotheses,
        key=lambda h: (
            _PRIORITY_WEIGHT.get(h.priority, 0),
            h.confidence,
            len(h.evidence),
        ),
    )
    return _relay(ctx, top)


def _relay(ctx: TriageContext, top: HypothesisRecord) -> dict:
    cited = [
        evidence(statement=statement, source=source)
        for statement, source in top.evidence
    ]
    return proposal(
        type=_TYPE_BY_LABEL.get(top.truth_label, "observation"),
        target=top.target,
        observation=top.statement,
        reasoning=(
            f"{ROUTE_TASK}: ranked #1 by priority/confidence among "
            f"{len(ctx.hypotheses)} open hypotheses"
        ),
        potential_issue="ranking reflects prioritization only; it does not change validation status",
        evidence=cited,
        confidence=top.confidence,
        priority=top.priority,
        validation_step=top.validation_step or "preserve prior validation status; validate before acting",
        truth_label=top.truth_label,
    )