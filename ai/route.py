"""Deterministic agent-to-provider seam ("07_AI_AGENTS.md" §AI Router, Phase-7 acceptance).

Each Phase-7 agent's ``run`` consults the Phase-6 router for its documented task type so every
proposal carries the router's local/cloud decision through the pipeline. Pure and
deterministic: a fixed, documented profile per task type under the caller's ``RouteConfig``.
"""

from __future__ import annotations

from typing import Optional

from .router import RouteConfig, RoutingDecision, TaskProfile, select


def route(
    task_type: str,
    *,
    complexity: str = "medium",
    context_tokens: int = 1024,
    reasoning_depth: str = "medium",
    cfg: Optional[RouteConfig] = None,
) -> RoutingDecision:
    """Route ``task_type`` under ``cfg`` using the Phase-6 hybrid ballot."""
    return select(
        TaskProfile(
            task_type=task_type,
            complexity=complexity,
            context_tokens=context_tokens,
            reasoning_depth=reasoning_depth,
        ),
        cfg if cfg is not None else RouteConfig(),
    )