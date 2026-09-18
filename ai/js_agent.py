"""JSAgent ("07_AI_AGENTS.md" §JSAgent, "12_AI_PROMPTS.md" §keyword classification).

Classifies recorded JS extraction results by a fixed significance order. A token-like
``secret_candidate`` is emitted as an ``unverified_claim`` (Common Output
``truth_label="UNVERIFIED_CLAIM"``) — the agent may never assert a token-like string is a
confirmed secret. All other classifications are direct observations of recorded extractions.
Emits no proposal when there are no extraction results.
"""

from __future__ import annotations

from typing import Optional

from .context import JsContext
from .contract import evidence, proposal
from .route import route
from .router import RouteConfig

ROUTE_TASK = "keyword_classification"

_KIND_PRIORITY = {
    "secret_candidate": 5,
    "endpoint": 4,
    "config_reference": 3,
    "route": 2,
    "domain_reference": 1,
    "other": 0,
}

_CONFIDENCE = {
    "secret_candidate": 0.35,
    "endpoint": 0.9,
    "config_reference": 0.75,
    "route": 0.6,
    "domain_reference": 0.6,
    "other": 0.3,
}


def run(ctx: JsContext, cfg: Optional[RouteConfig] = None) -> Optional[dict]:
    """Return one schema-valid classification of the most significant extraction, or ``None``."""
    route(ROUTE_TASK, complexity="low", context_tokens=512, reasoning_depth="low", cfg=cfg)

    if not ctx.extractions:
        return None

    rec = max(ctx.extractions, key=lambda r: _KIND_PRIORITY.get(r.kind, 0))
    statement = (
        f"{rec.kind} reference `{rec.value}` in {rec.js_file} at {rec.region}"
    )
    cited = [evidence(statement=statement, source=rec.evidence_id)]

    if rec.kind == "secret_candidate":
        return proposal(
            type="unverified_claim",
            target=ctx.scope.root,
            observation=statement,
            reasoning=f"{ROUTE_TASK}: token-like value classified as a candidate, not a confirmed secret",
            potential_issue="token-like value is a candidate only; must be confirmed by the infra/asset owner, never from JS content alone",
            evidence=cited,
            confidence=_CONFIDENCE[rec.kind],
            priority="high",
            validation_step="confirm the value with the asset owner before any use (DevMode)",
            truth_label="UNVERIFIED_CLAIM",
        )

    return proposal(
        type="observation",
        target=ctx.scope.root,
        observation=statement,
        reasoning=f"{ROUTE_TASK}: extraction classified by documented significance order",
        potential_issue="observation of recorded JS content; reachability/scope not asserted here",
        evidence=cited,
        confidence=_CONFIDENCE.get(rec.kind, 0.3),
        priority="medium" if rec.kind == "endpoint" else "low",
        validation_step="confirm against the recorded JS extraction before further use",
        truth_label="OBSERVATION",
    )