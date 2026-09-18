"""AuthZAgent ("07_AI_AGENTS.md" §AuthZAgent).

For the first recorded endpoint that exposes an object-identifier parameter *and* has a
recorded authentication mechanism, emits one authorization hypothesis (Common Output
``type="hypothesis"``, ``truth_label="HYPOTHESIS"``). Insufficient evidence (no such
endpoint) → no hypothesis. The hypothesis is never labelled a finding and never tested
automatically (07_AI_AGENTS.md "forbidden actions").
"""

from __future__ import annotations

from typing import Optional

from .context import AuthzContext, EndpointRecord, ParameterRecord
from .contract import evidence, proposal
from .route import route
from .router import RouteConfig

ROUTE_TASK = "hypothesis_generation"


def run(ctx: AuthzContext, cfg: Optional[RouteConfig] = None) -> Optional[dict]:
    """Return one schema-valid authorization hypothesis, or ``None`` when unsupported."""
    route(ROUTE_TASK, complexity="high", reasoning_depth="high", cfg=cfg)

    for endpoint in ctx.endpoints:
        if "{" not in endpoint.pattern:
            continue
        param = _first_object_id_param(ctx, endpoint.evidence_id)
        if param is None:
            continue
        auth = next(
            (a for a in ctx.auth_mechanisms if a.endpoint_id == endpoint.evidence_id), None
        )
        if auth is None:
            continue
        return _propose(ctx, endpoint, param, auth)
    return None


def _first_object_id_param(
    ctx: AuthzContext, endpoint_id: str
) -> Optional[ParameterRecord]:
    for param in ctx.parameters:
        if param.endpoint_id == endpoint_id and param.significance == "object_id":
            return param
    return None


def _propose(ctx: AuthzContext, endpoint: EndpointRecord, param, auth) -> dict:
    observation = (
        f"object-identifier parameter `{param.name}` in `{endpoint.method} {endpoint.pattern}` "
        f"(`{endpoint.host}`), protected by `{auth.mechanism_type}`"
    )
    return proposal(
        type="hypothesis",
        target=endpoint.host,
        observation=observation,
        reasoning=(
            "object-identifier endpoint with a recorded auth mechanism points to potential "
            "broken-object-level authorization; validate with a second account"
        ),
        potential_issue="hypothesis only; must be validated by an authenticated second-user comparison, never asserted as a finding",
        evidence=[
            evidence(statement=observation, source=endpoint.evidence_id),
            evidence(statement=f"parameter `{param.name}`", source=param.evidence_id),
            evidence(statement=f"auth `{auth.mechanism_type}`", source=auth.evidence_id),
        ],
        confidence=0.7,
        priority="medium",
        validation_step="authenticated second-account request comparison on a sandboxed instance, DevMode; never automated, never live",
        truth_label="HYPOTHESIS",
    )