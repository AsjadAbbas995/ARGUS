"""LogicAgent ("07_AI_AGENTS.md" §LogicAgent).

Flags a workflow inconsistency in one sequenced request flow: a step that is re-entered after
its initial occurrence. The anomaly is emitted as a low-ceremony ``observation`` with
``truth_label="INFERENCE"`` — it is a reasoned conclusion from the recorded sequence, not a
confirmed defect. A clean or too-short flow produces no proposal.
"""

from __future__ import annotations

from typing import Optional

from .context import EndpointRecord, LogicContext
from .contract import evidence, proposal
from .route import route
from .router import RouteConfig

ROUTE_TASK = "complex_correlation"


def run(ctx: LogicContext, cfg: Optional[RouteConfig] = None) -> Optional[dict]:
    """Return one schema-valid workflow-observation, or ``None`` when the flow is clean."""
    route(ROUTE_TASK, complexity="medium", reasoning_depth="medium", cfg=cfg)

    first_seen: dict[tuple[str, str], EndpointRecord] = {}
    for endpoint in ctx.flow:
        key = (endpoint.method, endpoint.pattern)
        if key in first_seen:
            initial = first_seen[key]
            return _propose(ctx, initial, endpoint)
        first_seen[key] = endpoint
    return None


def _propose(ctx: LogicContext, initial: EndpointRecord, repeated: EndpointRecord) -> dict:
    observation = (
        f"workflow re-enters completed step `{initial.method} {initial.pattern}` "
        "after its initial invocation"
    )
    return proposal(
        type="observation",
        target=initial.host,
        observation=observation,
        reasoning=(
            f"{ROUTE_TASK}: repeated step detected in the recorded {len(ctx.flow)}-step flow; "
            "worth investigating (possible re-auth or state reset)"
        ),
        potential_issue="may be legitimate; kept as an observation, not a confirmed defect",
        evidence=[
            evidence(statement=f"initial `{initial.method} {initial.pattern}`", source=initial.evidence_id),
            evidence(statement=f"repeat `{repeated.method} {repeated.pattern}`", source=repeated.evidence_id),
        ],
        confidence=0.75,
        priority="medium",
        validation_step="review the recorded sequence; re-validate with a manual trace if it recurs",
        truth_label="INFERENCE",
    )