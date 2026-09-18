"""Phase-7 typed context records ("05_DATA_MODEL.md" assets/endpoints/parameters/auth/JS
extractions, "07_AI_AGENTS.md" per-agent inputs and failure behavior, "03_RECON_PIPELINE.md"
recon stages).

The AI-agent layer is a pure, deterministic consumer: each ``run`` turns the *caller-supplied*
records below into exactly one Common Output Contract proposal (or ``None`` when the
documented no-proposal condition holds). Records are frozen dataclasses; the only strings an
agent may use as an evidence ``source`` are the ``evidence_id`` values present on the records
in its context. A claim with no caller-supplied evidence is never composed (07_AI_AGENTS.md
"AI Safety Boundary").
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScopeRef:
    """Authorized program scope. Agent outputs must never target anything outside it."""

    program: str
    root: str
    allowed_hosts: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AssetRecord:
    """One discovered in-scope asset host."""

    hostname: str
    evidence_id: str
    source: str = "subfinder"


@dataclass(frozen=True)
class TechnologyRecord:
    """One technology observation attached to the asset surface."""

    name: str
    category: str
    evidence_id: str


@dataclass(frozen=True)
class EndpointRecord:
    """One recorded HTTP endpoint (method + URL pattern)."""

    method: str
    pattern: str
    host: str
    evidence_id: str
    source: str = "crawl"


@dataclass(frozen=True)
class ParameterRecord:
    """One recorded endpoint parameter."""

    name: str
    location: str
    significance: str
    endpoint_id: str
    evidence_id: str


@dataclass(frozen=True)
class AuthMechanismRecord:
    """One recorded authentication mechanism for an endpoint."""

    mechanism_type: str
    endpoint_id: str
    evidence_id: str


@dataclass(frozen=True)
class ApiRecord:
    """One documented or inferred API binding."""

    name: str
    api_type: str
    documented: bool
    evidence_id: str


@dataclass(frozen=True)
class JsExtractionRecord:
    """One string extracted from a JavaScript file during JS analysis."""

    js_file: str
    region: str
    kind: str
    value: str
    evidence_id: str


@dataclass(frozen=True)
class ObservationRecord:
    """One caller-supplied observation from tool output or recorded evidence."""

    statement: str
    evidence_id: str
    source: str = "tool_run"


@dataclass(frozen=True)
class HypothesisRecord:
    """One open hypothesis available to the triage agent."""

    statement: str
    truth_label: str
    confidence: float
    priority: str
    severity: str
    target: str
    evidence: tuple[tuple[str, str], ...]
    validation_step: str = ""
    hypothesis_id: str = ""


# --- agent input bundles -----------------------------------------------------


@dataclass(frozen=True)
class ReconContext:
    """Inputs to ReconAgent: recorded assets, observations, and evidenced coverage gaps."""

    scope: ScopeRef
    assets: tuple[AssetRecord, ...] = field(default_factory=tuple)
    observations: tuple[ObservationRecord, ...] = field(default_factory=tuple)
    existing_tasks: tuple[str, ...] = field(default_factory=tuple)
    gaps: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ApiContext:
    """Inputs to APIAgent: recorded endpoints, API bindings, and parameters."""

    scope: ScopeRef
    endpoints: tuple[EndpointRecord, ...] = field(default_factory=tuple)
    apis: tuple[ApiRecord, ...] = field(default_factory=tuple)
    parameters: tuple[ParameterRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class JsContext:
    """Inputs to JSAgent: recorded JS extraction results."""

    scope: ScopeRef
    extractions: tuple[JsExtractionRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AuthzContext:
    """Inputs to AuthZAgent: recorded endpoints, parameters, and auth mechanisms."""

    scope: ScopeRef
    endpoints: tuple[EndpointRecord, ...] = field(default_factory=tuple)
    parameters: tuple[ParameterRecord, ...] = field(default_factory=tuple)
    auth_mechanisms: tuple[AuthMechanismRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LogicContext:
    """Inputs to LogicAgent: one sequenced request flow."""

    scope: ScopeRef
    flow: tuple[EndpointRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TriageContext:
    """Inputs to TriageAgent: all open hypotheses."""

    scope: ScopeRef
    hypotheses: tuple[HypothesisRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HypothesisContext:
    """Inputs to HypothesisAgent: correlated observations."""

    scope: ScopeRef
    observations: tuple[ObservationRecord, ...] = field(default_factory=tuple)