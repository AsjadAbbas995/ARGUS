"""HypothesisAgent ("07_AI_AGENTS.md" §HypothesisAgent).

Generates exactly one attack-surface hypothesis (Common Output ``type="hypothesis"``,
``truth_label="HYPOTHESIS"``) from the caller-supplied correlated observations. Every
observation is preserved as evidence — nothing is invented and never self-validated
(07_AI_AGENTS.md "AI Safety Boundary"). Emits no proposal with no observations.
"""

from __future__ import annotations

from typing import Optional

from .context import HypothesisContext
from .contract import evidence, proposal
from .route import route
from .router import RouteConfig

ROUTE_TASK = "hypothesis_generation"


def run(ctx: HypothesisContext, cfg: Optional[RouteConfig] = None) -> Optional[dict]:
    """Return one schema-valid hypothesis, or ``None`` when there is no observation to cite."""
    route(ROUTE_TASK, complexity="medium", reasoning_depth="medium", cfg=cfg)

    if not ctx.observations:
        return None

    cited = [
        evidence(statement=obs.statement, source=obs.evidence_id)
        for obs in ctx.observations
    ]
    return proposal(
        type="hypothesis",
        target=ctx.scope.root,
        observation=ctx.observations[0].statement,
        reasoning=(
            f"{ROUTE_TASK}: correlated {len(ctx.observations)} caller-supplied observations "
            "into one attack-surface hypothesis; every observation preserved as evidence"
        ),
        potential_issue="hypothesis only; requires human-approved validation before promotion",
        evidence=cited,
        confidence=0.6,
        priority="medium",
        validation_step="safe, non-invasive observation confirmation before any action",
        truth_label="HYPOTHESIS",
    )