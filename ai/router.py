"""ARGUS hybrid AI router ("07_AI_AGENTS.md" §Hybrid Model Routing + §AI Router,
"02_ARCHITECTURE.md" §hybrid routing, "14_CONFIG_EXAMPLE.md" §`ai`).

Phase-6 DoD ("10_IMPLEMENTATION_PLAN.md" §Phase 6 — AI Layer): the router chooses local vs. cloud
**per the documented criteria** and never guesses. This implementation is a pure, deterministic
pure function: same profile + config ⇒ same ``RoutingDecision``, every timecars never any live
call, never any target, never any wall-clock. It is the deterministic core the Phase-6 test
oracle locks onto.

Documented criteria (07_AI_AGENTS.md:41-42): task complexity, context size, expected reasoning
requirements, cost, latency, and local-model availability. The hybrid ballot resolves as:

* ``mode="local"``  → always local (never cloud); local unavailable ⇒ ``RoutingError`` (rejected,
  not silently routed).
* ``mode="cloud"``  → always cloud.
* ``mode="hybrid"`` → local when the task fits the documented local carve-out (classification,
  extraction, deduplication, simple technology identification, keyword classification, lightweight
  normalization, basic summarization, repetitive analysis) AND is not high-complexity AND its
  context is under the documented threshold AND local is available; otherwise cloud (complex
  correlation, attack-surface reasoning, multi-source analysis, complicated API relationships,
  hypothesis generation, prioritization, complex reconnaissance planning, or any
  high-complexity/large-context/local-unavailable task).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

# --- Documented task taxonomy (07_AI_AGENTS.md:33-39) -------------------------------

LOCAL_TASK_TYPES = frozenset(
    {
        "classification",
        "extraction",
        "deduplication",
        "tech_identification",      # simple technology identification
        "keyword_classification",
        "normalization",            # lightweight normalization
        "summarization",            # basic summarization
        "repetitive_analysis",
    }
)

CLOUD_TASK_TYPES = frozenset(
    {
        "complex_correlation",
        "attack_surface_reasoning",
        "multi_source_analysis",
        "api_relationship_analysis",   # complicated API relationships
        "hypothesis_generation",
        "prioritization",
        "complex_recon_planning",
    }
)

# Documented local-model context-size ceiling (token-estimate) before the router escalates to
# cloud for a hybrid task. Chosen from the spec's cost/latency guidance; kept as a named
# constant so the test oracle can assert the boundary deterministically.
CONTEXT_SIZE_CEILING = 8_000

ModelKind = Literal["local", "cloud"]


class RoutingError(Exception):
    """A documented routing rule was violated (e.g. forced-local with no local model)."""


@dataclass(frozen=True)
class TaskProfile:
    """Deterministic view of one agent task, as the router's documented inputs."""

    task_type: str
    complexity: Literal["low", "medium", "high"] = "medium"
    context_tokens: int = 512
    reasoning_depth: Literal["low", "medium", "high"] = "medium"
    local_available: bool = True


@dataclass(frozen=True)
class RouteConfig:
    """Router configuration mirroring ``14_CONFIG_EXAMPLE.md`` ``ai.*`` keys."""

    mode: Literal["local", "cloud", "hybrid"] = "hybrid"
    local_model: str = "local"
    cloud_model: str = "cloud"


@dataclass(frozen=True)
class RoutingDecision:
    """The router's structured decision; always schema-shaped for ``ai/validator.py``."""

    model: ModelKind
    model_id: str
    rationale: str
    task_type: str


def select(p: TaskProfile, cfg: RouteConfig) -> RoutingDecision:
    """Select local vs. cloud for ``p`` under ``cfg`` — deterministic, documented, no I/O."""

    if cfg.mode == "local":
        if not p.local_available:
            raise RoutingError("forced-local routing requested but no local model is available")
        return _decision("local", cfg, p, "mode=local forces the local model")

    if cfg.mode == "cloud":
        return _decision("cloud", cfg, p, "mode=cloud forces the cloud model")

    # hybrid: apply the documented ballot.
    if not p.local_available:
        return _decision("cloud", cfg, p, "local model unavailable → cloud")

    if p.task_type in CLOUD_TASK_TYPES:
        return _decision("cloud", cfg, p, f"`{p.task_type}` requires cloud reasoning")

    if p.complexity == "high":
        return _decision("cloud", cfg, p, "high task complexity → cloud")

    if p.context_tokens > CONTEXT_SIZE_CEILING:
        return _decision("cloud", cfg, p, "context size exceeds local ceiling → cloud")

    if p.task_type in LOCAL_TASK_TYPES:
        return _decision("local", cfg, p, f"`{p.task_type}` fits the documented local carve-out")

    # Unknown task type with modest profile: default to local (repetitive/light baseline),
    # matching the spec's default bias toward cost/latency efficiency when nothing forces cloud.
    average = p.reasoning_depth in {"low", "medium"} and p.complexity in {"low", "medium"}
    return _decision(
        "local" if average else "cloud",
        cfg,
        p,
        "hybrid default (no forcing criterion) → local"
        if average
        else "hybrid default (high reasoning depth) → cloud",
    )


def _decision(kind: ModelKind, cfg: RouteConfig, p: TaskProfile, rationale: str) -> RoutingDecision:
    model_id = cfg.local_model if kind == "local" else cfg.cloud_model
    return RoutingDecision(model=kind, model_id=model_id, rationale=rationale, task_type=p.task_type)
