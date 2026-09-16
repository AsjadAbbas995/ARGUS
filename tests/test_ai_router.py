"""Phase-6 oracle: hybrid router-selection + structured-output schema validation
("10_IMPLEMENTATION_PLAN.md" §Phase 6 — AI Layer; "07_AI_AGENTS.md" §Hybrid Model Routing +
§Common Output Contract; "12_AI_PROMPTS.md" §Output Schemas; "05_DATA_MODEL.md" §hypotheses).

Byte-locked oracle — do **not** edit. It is the deterministic contract the Phase-6 DoD locks to:
*router-selection unit tests* (hybrid local vs. cloud per the documented criteria) and
*structured-output schema-validation tests* (schema-valid proposal accepted; off-schema /
unreferenced output rejected). No live target and no live model — everything is a pure
call through the router and the validator.
"""

from __future__ import annotations

import pytest

from ai import cloud_model, local_model, router, validator


# ----------------------------------------------------------------------------------------------
# Router-selection unit tests (07_AI_AGENTS.md §Hybrid Model Routing — the documented criteria).
# ----------------------------------------------------------------------------------------------


def test_hybrid_routes_simple_classification_to_local():
    p = router.TaskProfile(task_type="classification", complexity="low", context_tokens=50)
    d = router.select(p, router.RouteConfig())
    assert d.model == "local"


def test_hybrid_routes_extraction_to_local():
    p = router.TaskProfile(task_type="extraction", complexity="low", context_tokens=60)
    d = router.select(p, router.RouteConfig())
    assert d.model == "local"


def test_hybrid_routes_dedup_to_local():
    p = router.TaskProfile(task_type="deduplication", complexity="low", context_tokens=40)
    d = router.select(p, router.RouteConfig())
    assert d.model == "local"


def test_hybrid_routes_knowledge_normalization_to_local():
    p = router.TaskProfile(task_type="normalization", complexity="medium", context_tokens=200)
    d = router.select(p, router.RouteConfig())
    assert d.model == "local"


def test_hybrid_routes_cloud_pressure_task_to_cloud():
    p = router.TaskProfile(task_type="complex_correlation", complexity="high", context_tokens=200)
    d = router.select(p, router.RouteConfig())
    assert d.model == "cloud"
    assert d.rationale


def test_hybrid_routes_multi_source_analysis_to_cloud():
    p = router.TaskProfile(task_type="multi_source_analysis", complexity="high", context_tokens=300)
    d = router.select(p, router.RouteConfig())
    assert d.model == "cloud"


def test_hybrid_routes_hypothesis_generation_to_cloud():
    p = router.TaskProfile(task_type="hypothesis_generation", complexity="high", context_tokens=200)
    d = router.select(p, router.RouteConfig())
    assert d.model == "cloud"


def test_hybrid_routes_to_cloud_when_local_unavailable():
    p = router.TaskProfile(
        task_type="classification",
        complexity="low",
        context_tokens=50,
        local_available=False,
    )
    with pytest.raises(router.RoutingError):
        router.select(p, router.RouteConfig())


def test_force_local_never_routes_to_cloud():
    cfg = router.RouteConfig(mode="local")
    for task_type in ("classification", "extraction", "complex_correlation", "hypothesis_generation"):
        p = router.TaskProfile(task_type=task_type, complexity="high", context_tokens=9_000)
        d = router.select(p, cfg)
        assert d.model == "local"


def test_force_cloud_never_routes_to_local():
    cfg = router.RouteConfig(mode="cloud")
    for task_type in ("classification", "extraction", "deduplication"):
        p = router.TaskProfile(task_type=task_type, complexity="low", context_tokens=20)
        d = router.select(p, cfg)
        assert d.model == "cloud"


def test_hybrid_respects_context_size_ceiling():
    p = router.TaskProfile(task_type="classification", complexity="low", context_tokens=60_000)
    d = router.select(p, router.RouteConfig())
    assert d.model == "cloud"


def test_router_decision_is_deterministic():
    p = router.TaskProfile(task_type="classification", complexity="low", context_tokens=50)
    cfg = router.RouteConfig()
    first = router.select(p, cfg)
    second = router.select(p, cfg)
    assert first == second


# ----------------------------------------------------------------------------------------------
# Structured-output schema-validation tests (07_AI_AGENTS.md §Common Output Contract;
# 12_AI_PROMPTS.md §Output Schemas).
# ----------------------------------------------------------------------------------------------


def _valid_proposal() -> dict:
    return {
        "type": "hypothesis",
        "target": "api/users/{id}",
        "observation": "The `{id}` path parameter is reflected unescaped in the response body.",
        "reasoning": "Parameter reflection suggests object references are not validated per-object.",
        "potential_issue": "Object-level authorization may be missing on `api/users/{id}`.",
        "evidence": [
            {"statement": "Path parameter `{id}` is echo back in the body.", "source": "crawl:users.js:41"},
        ],
        "confidence": 0.6,
        "priority": "medium",
        "validation_step": "re-send the request as an authenticated second user and compare",
    }


def test_validator_accepts_schema_valid_proposal():
    result = validator.validate_structured_output(_valid_proposal())
    assert result.valid
    assert not result.failures


def test_validator_rejects_missing_required_field():
    output = _valid_proposal()
    del output["confidence"]
    result = validator.validate_structured_output(output)
    assert not result.valid
    assert any(f.field == "confidence" for f in result.failures)


def test_validator_rejects_empty_evidence():
    output = _valid_proposal()
    output["evidence"] = []
    result = validator.validate_structured_output(output)
    assert not result.valid
    assert any(f.field == "evidence" or f.field.startswith("evidence[") for f in result.failures)


def test_validator_rejects_invalid_truth_label():
    output = _valid_proposal()
    output["truth_label"] = "CONFIRMED"
    result = validator.validate_structured_output(output)
    assert not result.valid
    assert any(f.field == "truth_label" for f in result.failures)


def test_validator_rejects_hypothesis_passed_as_finding():
    output = _valid_proposal()
    output["truth_label"] = "VALIDATED_FINDING"
    result = validator.validate_structured_output(output)
    assert not result.valid
    assert any(f.field == "truth_label" for f in result.failures)


def test_validator_rejects_confidence_out_of_range():
    output = _valid_proposal()
    output["confidence"] = 1.5
    result = validator.validate_structured_output(output)
    assert not result.valid
    assert any(f.field == "confidence" for f in result.failures)


def test_validator_rejects_unreferenced_claim():
    output = _valid_proposal()
    output["evidence"] = []
    result = validator.validate_structured_output(output)
    assert not result.valid


# ----------------------------------------------------------------------------------------------
# End-to-end: schema-valid structured output through the full Phase-6 harness (no live target).
# ----------------------------------------------------------------------------------------------


def test_e2e_local_model_output_is_schema_valid():
    p = router.TaskProfile(task_type="classification", complexity="low", context_tokens=50)
    decision = router.select(p, router.RouteConfig())
    assert decision.model == "local"
    proposal = local_model.simulate(
        task_type="classification",
        target="https://a.example/login",
        observation="`/login` returns a 200 with a login form and a CSRF token field.",
    )
    proposal["truth_label"] = "OBSERVATION"
    result = validator.validate_structured_output(proposal)
    assert result.valid
    assert not result.failures


def test_e2e_cloud_model_output_is_schema_valid():
    p = router.TaskProfile(task_type="complex_correlation", complexity="high", context_tokens=200)
    decision = router.select(p, router.RouteConfig())
    assert decision.model == "cloud"
    proposal = cloud_model.simulate(
        task_type="complex_correlation",
        target="https://a.example",
        observations=[
            "`/api/users/{id}` reflects `{id}` unescaped; `api/v1/users/{id}` behaves differently.",
            "Two separate endpoints accept an object identifier that is also returned by `/auth/me`.",
        ],
    )
    result = validator.validate_structured_output(proposal)
    assert result.valid
    assert not result.failures
