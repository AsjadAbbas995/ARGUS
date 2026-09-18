"""APIAgent ("07_AI_AGENTS.md" §APIAgent).

Summarises one recorded API relationship from caller-supplied endpoint/parameter/schema
records (Common Output ``type="observation"``). Marks undocumented or incomplete schema
coverage as ``UNKNOWN`` rather than filling the gap from imagination; emits no proposal when
no endpoints are recorded.
"""

from __future__ import annotations

from typing import Optional

from .context import ApiContext, EndpointRecord, ParameterRecord
from .contract import evidence, proposal
from .route import route
from .router import RouteConfig

ROUTE_TASK = "api_relationship_analysis"


def run(ctx: ApiContext, cfg: Optional[RouteConfig] = None) -> Optional[dict]:
    """Return one schema-valid API-relationship observation, or ``None``."""
    route(ROUTE_TASK, complexity="medium", reasoning_depth="high", cfg=cfg)

    if not ctx.endpoints:
        return None

    endpoint = ctx.endpoints[0]
    param = _first_object_id_param(ctx, endpoint.evidence_id)
    parameterized = param is not None

    if parameterized:
        observation = (
            f"`{endpoint.method} {endpoint.pattern}` exposes object-identifier parameter "
            f"`{param.name}` ({param.location}); relationship subject to authorization review"
        )
    else:
        observation = f"`{endpoint.method} {endpoint.pattern}` recorded with no object-identifier parameters"

    documented = any(api.documented for api in ctx.apis)
    if not documented:
        observation += " — schema not documented, coverage UNKNOWN"

    cited = [evidence(statement=observation, source=endpoint.evidence_id)]
    if param is not None:
        cited.append(
            evidence(statement=f"parameter `{param.name}`", source=param.evidence_id)
        )
    if ctx.apis:
        cited.append(
            evidence(
                statement=f"api binding `{ctx.apis[0].name}` ({ctx.apis[0].api_type})",
                source=ctx.apis[0].evidence_id,
            )
        )

    return proposal(
        type="observation",
        target=endpoint.host,
        observation=observation,
        reasoning=f"{ROUTE_TASK}: summarized the first recorded relationship; incomplete coverage marked UNKNOWN",
        potential_issue="summary reflects recorded evidence only; missing schema data is flagged, never guessed",
        evidence=cited,
        confidence=0.85 if documented else 0.6,
        priority="medium",
        validation_step="confirm against recorded crawl/schema evidence before further analysis",
        truth_label="OBSERVATION",
    )


def _first_object_id_param(ctx: ApiContext, endpoint_id: str) -> Optional[ParameterRecord]:
    for param in ctx.parameters:
        if param.endpoint_id == endpoint_id and param.significance == "object_id":
            return param
    return None