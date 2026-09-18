"""Phase-7 AI agent contract tests ("13_TESTING_STRATEGY.md" §AI Contract Tests,
"10_IMPLEMENTATION_PLAN.md" §Phase 7 DoD).

Every Phase-7 agent must pass the contract suite against **recorded evidence fixtures**:
emitted proposals are validator-valid, cite only caller-supplied evidence (never fabricated),
use correct truth labels, never self-validate, never propose out-of-scope targets, and are
byte-deterministic. Agents emit ``None`` (no proposal) when the documented no-evidence
condition holds.
"""

from __future__ import annotations

import pytest

from ai import (
    api_agent,
    authz_agent,
    cloud_model,
    context,
    hypothesis_agent,
    js_agent,
    local_model,
    logic_agent,
    recon_agent,
    route as route_seam,
    triage_agent,
    validator,
)
from ai.contract import proposal

_AGENTS = (
    recon_agent,
    api_agent,
    js_agent,
    authz_agent,
    logic_agent,
    triage_agent,
    hypothesis_agent,
)


def _scope() -> context.ScopeRef:
    return context.ScopeRef(
        program="argus-test",
        root="example.com",
        allowed_hosts=("example.com", "app.example.com", "api.example.com"),
    )


# --- recorded-evidence fixtures --------------------------------------------------


def _recon_gap() -> context.ReconContext:
    return context.ReconContext(
        scope=_scope(),
        assets=(context.AssetRecord("app.example.com", "asset-0001"),),
        observations=(
            context.ObservationRecord(
                "no JS files recorded for app.example.com", "obs-0001", "js_analysis"
            ),
            context.ObservationRecord(
                "GraphQL introspection unresolved", "obs-0002", "graphql_recon"
            ),
        ),
        gaps=("graphql_recon", "js_analysis"),
    )


def _recon_all_covered() -> context.ReconContext:
    return context.ReconContext(
        scope=_scope(),
        assets=(context.AssetRecord("app.example.com", "asset-0001"),),
        observations=(context.ObservationRecord("JS present", "obs-0001", "js_analysis"),),
        gaps=(),
    )


def _recon_no_evidence() -> context.ReconContext:
    return context.ReconContext(scope=_scope(), assets=(), observations=(), gaps=("subdomain_enum",))


def _api(documented: bool) -> context.ApiContext:
    return context.ApiContext(
        scope=_scope(),
        endpoints=(
            context.EndpointRecord("GET", "/orders/{id}", "api.example.com", "ep-0001", "openapi"),
            context.EndpointRecord("POST", "/orders", "api.example.com", "ep-0002", "openapi"),
        ),
        apis=(context.ApiRecord("orders-api", "rest", documented, "api-0001"),),
        parameters=(context.ParameterRecord("id", "path", "object_id", "ep-0001", "prm-0001"),),
    )


def _api_empty() -> context.ApiContext:
    return context.ApiContext(scope=_scope())


def _js(*records) -> context.JsContext:
    return context.JsContext(scope=_scope(), extractions=records)


_J_SECRET = context.JsExtractionRecord(
    "https://app.example.com/js/main.js", "L42", "secret_candidate", "AKIA-SK", "js-0001"
)
_J_ENDPOINT = context.JsExtractionRecord(
    "https://app.example.com/js/admin.js", "L7", "endpoint", "/admin/users", "js-0002"
)
_J_ROUTE = context.JsExtractionRecord(
    "https://app.example.com/js/main.js", "L90", "route", "#/reports", "js-0003"
)


def _authz_object_id() -> context.AuthzContext:
    return context.AuthzContext(
        scope=_scope(),
        endpoints=(context.EndpointRecord("GET", "/api/users/{id}", "api.example.com", "ep-a1", "crawl"),),
        parameters=(context.ParameterRecord("id", "path", "object_id", "ep-a1", "prm-a1"),),
        auth_mechanisms=(context.AuthMechanismRecord("bearer", "ep-a1", "am-a1"),),
    )


def _authz_not_parameterized() -> context.AuthzContext:
    return context.AuthzContext(
        scope=_scope(),
        endpoints=(context.EndpointRecord("POST", "/login", "app.example.com", "ep-a2", "crawl"),),
        auth_mechanisms=(context.AuthMechanismRecord("cookie", "ep-a2", "am-a2"),),
    )


def _authz_object_id_without_auth() -> context.AuthzContext:
    return context.AuthzContext(
        scope=_scope(),
        endpoints=(context.EndpointRecord("GET", "/api/orders/{id}", "api.example.com", "ep-a3", "crawl"),),
        parameters=(context.ParameterRecord("id", "path", "object_id", "ep-a3", "prm-a3"),),
        auth_mechanisms=(),
    )


def _logic_repeated() -> context.LogicContext:
    return context.LogicContext(
        scope=_scope(),
        flow=(
            context.EndpointRecord("GET", "/orders", "api.example.com", "ep-l1", "flow"),
            context.EndpointRecord("POST", "/orders", "api.example.com", "ep-l2", "flow"),
            context.EndpointRecord("GET", "/orders", "api.example.com", "ep-l3", "flow"),
        ),
    )


def _logic_clean() -> context.LogicContext:
    return context.LogicContext(
        scope=_scope(),
        flow=(
            context.EndpointRecord("GET", "/login", "app.example.com", "ep-l4", "flow"),
            context.EndpointRecord("POST", "/session", "app.example.com", "ep-l5", "flow"),
            context.EndpointRecord("GET", "/dash", "app.example.com", "ep-l6", "flow"),
        ),
    )


def _logic_short() -> context.LogicContext:
    return context.LogicContext(
        scope=_scope(),
        flow=(context.EndpointRecord("GET", "/login", "app.example.com", "ep-l7", "flow"),),
    )


def _triage() -> context.TriageContext:
    return context.TriageContext(
        scope=_scope(),
        hypotheses=(
            context.HypothesisRecord(
                "self-service order read", "HYPOTHESIS", 0.5, "medium", "high",
                "api.example.com", (("stmt", "ev1"), ("stmt", "ev2")),
                validation_step="manual", hypothesis_id="h1",
            ),
            context.HypothesisRecord(
                "public profile idor", "HYPOTHESIS", 0.95, "low", "medium",
                "app.example.com", (("stmt", "ev3"),),
                validation_step="manual", hypothesis_id="h2",
            ),
            context.HypothesisRecord(
                "admin token leak", "HYPOTHESIS", 0.8, "high", "critical",
                "app.example.com", (("stmt", "ev4"),),
                validation_step="manual", hypothesis_id="h3",
            ),
        ),
    )


def _triage_empty() -> context.TriageContext:
    return context.TriageContext(scope=_scope())


def _triage_finding_relay() -> context.TriageContext:
    return context.TriageContext(
        scope=_scope(),
        hypotheses=(
            context.HypothesisRecord(
                "already-validated idor", "VALIDATED_FINDING", 0.9, "high", "critical",
                "api.example.com", (("stmt-original", "ev-find"),),
                validation_step="human-approved", hypothesis_id="h-find",
            ),
        ),
    )


def _hypothesis_multi() -> context.HypothesisContext:
    return context.HypothesisContext(
        scope=_scope(),
        observations=(
            context.ObservationRecord("object-id param in profile", "obs-c1", "auth_intel"),
            context.ObservationRecord("bearer token reused across accounts", "obs-c2", "js_analysis"),
        ),
    )


def _hypothesis_empty() -> context.HypothesisContext:
    return context.HypothesisContext(scope=_scope())


# --- positive contract cases ------------------------------------------------------

_POSITIVE_CASES = (
    pytest.param(recon_agent.run, _recon_gap, {"obs-0001"}, id="recon-gap"),
    pytest.param(api_agent.run, lambda: _api(True), {"ep-0001", "prm-0001", "api-0001"}, id="api-documented"),
    pytest.param(api_agent.run, lambda: _api(False), {"ep-0001", "prm-0001", "api-0001"}, id="api-undocumented"),
    pytest.param(js_agent.run, lambda: _js(_J_ENDPOINT), {"js-0002"}, id="js-endpoint"),
    pytest.param(js_agent.run, lambda: _js(_J_SECRET), {"js-0001"}, id="js-secret"),
    pytest.param(js_agent.run, lambda: _js(_J_ROUTE, _J_ENDPOINT, _J_SECRET), {"js-0001", "js-0002", "js-0003"}, id="js-most-significant"),
    pytest.param(authz_agent.run, _authz_object_id, {"ep-a1", "prm-a1", "am-a1"}, id="authz-object-id"),
    pytest.param(logic_agent.run, _logic_repeated, {"ep-l1", "ep-l2", "ep-l3"}, id="logic-repeated-step"),
    pytest.param(triage_agent.run, _triage, {"ev3", "ev1", "ev2", "ev4"}, id="triage-top-ranked"),
    pytest.param(triage_agent.run, _triage_finding_relay, {"ev-find"}, id="triage-finding-relay"),
    pytest.param(hypothesis_agent.run, _hypothesis_multi, {"obs-c1", "obs-c2"}, id="hypothesis-multi"),
)


@pytest.mark.parametrize("agent_run,ctx_factory,allowed_sources", _POSITIVE_CASES)
def test_agent_emissions_pass_the_common_output_contract(agent_run, ctx_factory, allowed_sources):
    ctx = ctx_factory()
    emitted = agent_run(ctx)
    assert emitted is not None, "a positive fixture must emit exactly one proposal"

    result = validator.validate_structured_output(emitted)
    assert result.valid, result.reason()

    assert emitted["type"] in {"hypothesis", "observation", "unverified_claim", "finding", "task"}
    assert emitted["truth_label"] != "VALIDATED_FINDING" or emitted["type"] == "finding"
    assert 0.0 <= emitted["confidence"] <= 1.0
    assert emitted["priority"] in {"low", "medium", "high"}

    assert emitted["evidence"], "a proposal must cite caller-supplied evidence"
    for item in emitted["evidence"]:
        assert item["source"] in allowed_sources, f"fabricated evidence source {item['source']!r}"

    target_host = emitted["target"].split("/")[0].split(":")[0]
    assert target_host in _scope().allowed_hosts, f"out-of-scope target {emitted['target']!r}"


@pytest.mark.parametrize("agent_run,ctx_factory,allowed_sources", _POSITIVE_CASES)
def test_agent_output_is_byte_deterministic(agent_run, ctx_factory, allowed_sources):
    ctx = ctx_factory()
    assert agent_run(ctx) == agent_run(ctx)


# --- per-agent documented behavior --------------------------------------------------

def test_recon_proposes_highest_priority_uncovered_stage():
    out = recon_agent.run(_recon_gap())
    assert out["type"] == "task"
    assert out["truth_label"] == "INFERENCE"
    assert out["target"] == "example.com"
    assert "js_analysis" in out["observation"]


def test_api_flagged_undocumented_schema_no_fabrication():
    documented = api_agent.run(_api(True))
    undocumented = api_agent.run(_api(False))
    assert documented["confidence"] == 0.85
    assert "UNKNOWN" not in documented["observation"]
    assert undocumented["confidence"] == 0.6
    assert "UNKNOWN" in undocumented["observation"]


def test_js_secret_candidate_is_unverified_and_not_confirmed():
    out = js_agent.run(_js(_J_SECRET))
    assert out["type"] == "unverified_claim"
    assert out["truth_label"] == "UNVERIFIED_CLAIM"
    assert out["priority"] == "high"
    assert "candidate" in out["potential_issue"]


def test_js_endpoint_classification_is_direct_observation():
    out = js_agent.run(_js(_J_ENDPOINT))
    assert out["type"] == "observation"
    assert out["truth_label"] == "OBSERVATION"
    assert out["priority"] == "medium"


def test_authz_object_id_hypothesis_never_self_validates():
    out = authz_agent.run(_authz_object_id())
    assert out["type"] == "hypothesis"
    assert out["truth_label"] == "HYPOTHESIS"
    assert {item["source"] for item in out["evidence"]} == {"ep-a1", "prm-a1", "am-a1"}
    assert "second-account" in out["validation_step"]


def test_logic_repeated_step_is_an_inference_observation():
    out = logic_agent.run(_logic_repeated())
    assert out["type"] == "observation"
    assert out["truth_label"] == "INFERENCE"
    assert "re-enters" in out["observation"]


def test_triage_keeps_truth_label_and_evidence_verbatim():
    out = triage_agent.run(_triage())
    assert out["truth_label"] == "HYPOTHESIS"
    assert out["confidence"] == 0.8
    assert out["priority"] == "high"
    assert {item["source"] for item in out["evidence"]} == {"ev4"}
    assert "ranked #1" in out["reasoning"]


def test_triage_relays_validated_finding_without_revalidating():
    out = triage_agent.run(_triage_finding_relay())
    assert out["type"] == "finding"
    assert out["truth_label"] == "VALIDATED_FINDING"
    assert validator.validate_structured_output(out).valid


# --- no-evidence failure behavior ---------------------------------------------------

_NO_OUTPUT_CASES = (
    pytest.param(recon_agent.run, _recon_all_covered, id="recon-all-covered"),
    pytest.param(recon_agent.run, _recon_no_evidence, id="recon-no-evidence"),
    pytest.param(api_agent.run, _api_empty, id="api-no-endpoints"),
    pytest.param(js_agent.run, lambda: _js(), id="js-no-extractions"),
    pytest.param(authz_agent.run, _authz_not_parameterized, id="authz-no-object-id"),
    pytest.param(authz_agent.run, _authz_object_id_without_auth, id="authz-no-auth-evidence"),
    pytest.param(logic_agent.run, _logic_clean, id="logic-clean-flow"),
    pytest.param(logic_agent.run, _logic_short, id="logic-too-short"),
    pytest.param(triage_agent.run, _triage_empty, id="triage-no-hypotheses"),
    pytest.param(hypothesis_agent.run, _hypothesis_empty, id="hypothesis-no-observations"),
)


@pytest.mark.parametrize("agent_run,ctx_factory", _NO_OUTPUT_CASES)
def test_agents_emit_nothing_when_evidence_is_insufficient(agent_run, ctx_factory):
    assert agent_run(ctx_factory()) is None


# --- construction-time contract enforcement (AI Safety Boundary) -----------------------

def test_contract_rejects_self_validating_proposal():
    with pytest.raises(ValueError, match="VALIDATED_FINDING"):
        proposal(
            type="hypothesis", target="example.com", observation="o", reasoning="r",
            potential_issue="p", evidence=[{"statement": "s", "source": "x"}],
            confidence=0.5, priority="low", validation_step="v",
            truth_label="VALIDATED_FINDING",
        )


def test_contract_rejects_uncited_proposal():
    with pytest.raises(ValueError, match="evidence"):
        proposal(
            type="hypothesis", target="example.com", observation="o", reasoning="r",
            potential_issue="p", evidence=[], confidence=0.5, priority="low",
            validation_step="v", truth_label="HYPOTHESIS",
        )


def test_validator_rejects_unhashable_truth_label_without_crashing():
    base = proposal(
        type="hypothesis", target="example.com", observation="o", reasoning="r",
        potential_issue="p", evidence=[{"statement": "s", "source": "x"}],
        confidence=0.5, priority="low", validation_step="v", truth_label="HYPOTHESIS",
    )
    base["truth_label"] = ["not", "hashable"]
    result = validator.validate_structured_output(base)
    assert result.valid is False
    assert any(f.field == "truth_label" for f in result.failures)


# --- Phase-6 regression guards for the W-fixes ------------------------------------------

def test_cloud_model_has_no_duplicate_simulate_surrogate():
    assert not hasattr(cloud_model, "simulate_cloud")
    assert not hasattr(cloud_model, "CloudProposal")
    out = cloud_model.simulate("complex_correlation", "api.example.com", ["obs"])
    assert validator.validate_structured_output(out).valid


def test_local_model_accepts_the_router_summarization_token():
    assert "summarization" in local_model.LOCAL_TASK_TYPES
    assert "basic_summarization" not in local_model.LOCAL_TASK_TYPES
    out = local_model.simulate("summarization", "app.example.com", "obs")
    assert validator.validate_structured_output(out).valid


# --- router integration seam ---------------------------------------------------------------

def test_every_phase7_agent_exports_run_and_route_task():
    for module in _AGENTS:
        assert callable(module.run)
        assert isinstance(module.ROUTE_TASK, str) and module.ROUTE_TASK


def test_agents_route_to_their_documented_provider():
    local = route_seam.route(
        js_agent.ROUTE_TASK, complexity="low", context_tokens=512, reasoning_depth="low"
    )
    assert local.model == "local"
    for module in _AGENTS:
        if module is js_agent:
            continue
        assert route_seam.route(module.ROUTE_TASK).model == "cloud"