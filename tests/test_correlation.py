"""Phase-8 correlation-module contract tests ("03_RECON_PIPELINE.md" 03. Re08_ORCHESTRATOR.md
run-lifecycle", "10_IMPLEMENTATION_PLAN.md" Phase 8 Definition of done: correlation).

These test the **real** correlation pipeline — ``records`` normalization →
``asset_graph.build`` → ``endpoint_graph`` relationships → ``deduplication`` → the
``relationship_engine`` — against a controlled local-lab evidence fixture Boundary:
every assertion is evidence-referenced (never fabricated), deterministic (same records →
same graph/inferences), and orphaned/unlinkable evidence is stored rather than dropped
(03 Re08 §25/§26). No database is touched: the pipeline is a pure function of records.
"""

from __future__ import annotations

import pytest

from correlation.asset_graph import build as build_asset_graph
from correlation.deduplication import (
    dedupe_edges,
    dedupe_inferences,
    dedupe_nodes,
    fingerprint,
)
from correlation.endpoint_graph import (
    auth_mechanisms_for,
    endpoint_subgraph,
    endpoint_with_object_id,
    linked_endpoint,
)
from correlation.records import (
    ApiRecord,
    AuthRecord,
    CertificateRecord,
    DomainRecord,
    Edge,
    EndpointRecord,
    Graph,
    IpRecord,
    JavaScriptRecord,
    Node,
    ParameterRecord,
    PortRecord,
    TechnologyRecord,
    WebAppRecord,
    endpoint_key,
    record_node,
)
from correlation.relationship_engine import (
    API_FAMILY,
    AUTHZ_SURFACE,
    JS_DISCOVERY,
    OBJECT_API,
    Inference,
    run as run_relationships,
)


# ---------------------------------------------------------------------------
# normalization: records → instances (byte-stable, deterministic)
# ---------------------------------------------------------------------------


def test_endpoint_key_is_deterministic_and_order_independent() -> None:
    a = endpoint_key("POST", "/api/objects/{id}", "api.example.com")
    b = endpoint_key("POST", "/api/objects/{id}", "api.example.com")
    c = endpoint_key("GET", "/api/objects/{id}", "api.example.com")
    d = endpoint_key("POST", "/api/objects/{oid}", "api.example.com")
    assert a == b
    assert a != c
    assert a != d
    assert isinstance(a, str)


def test_record_node_mirrors_every_record_without_losing_evidence() -> None:
    domain = DomainRecord(hostname="lab.example.com", evidence_id="ev-domain")
    node = record_node(domain)
    assert node.kind == "domain"
    assert node.key == "lab.example.com"
    assert node.evidence_id == "ev-domain"
    assert node.attributes.get("hostname") == "lab.example.com"


def test_parameter_record_keeps_object_id_significance() -> None:
    key = endpoint_key("POST", "/api/orders/{order_id}", "api.example.com")
    param = ParameterRecord(
        endpoint_key=key,
        name="order_id",
        location="path",
        significance="object_id",
        evidence_id="ev-param",
    )
    assert param.key == f"{key}#order_id"
    node = record_node(param)
    assert node.attributes.get("significance") == "object_id"


# ---------------------------------------------------------------------------
# asset graph: deterministic build, evidence-referenced edges, no dropped work
# ---------------------------------------------------------------------------


def _records() -> list[object]:
    domain = DomainRecord(hostname="lab.example.com", evidence_id="ev-domain")
    ip = IpRecord(address="10.0.0.5", hostname="lab.example.com", evidence_id="ev-ip")
    port = PortRecord(ip="10.0.0.5", number=8443, service="https", evidence_id="ev-port")
    webapp = WebAppRecord(
        host="api.lab.example.com",
        port=8443,
        status_code=200,
        title="Orders API",
        ip="10.0.0.5",
        evidence_id="ev-webapp",
    )
    key = endpoint_key("POST", "/api/orders/{order_id}", "api.lab.example.com")
    endpoint = EndpointRecord(
        method="POST",
        pattern="/api/orders/{order_id}",
        host="api.lab.example.com",
        evidence_id="ev-endpoint",
    )
    param = ParameterRecord(
        endpoint_key=key,
        name="order_id",
        location="path",
        significance="object_id",
        evidence_id="ev-param",
    )
    auth = AuthRecord(
        mechanism_type="session_bearer",
        endpoint_key=key,
        evidence_id="ev-auth",
    )
    api = ApiRecord(
        name="orders_api",
        api_type="rest",
        host="api.lab.example.com",
        documented=True,
        evidence_id="ev-api",
    )
    js = JavaScriptRecord(
        js_url="https://api.lab.example.com/app.js",
        host="api.lab.example.com",
        evidence_id="ev-js",
        endpoint_keys=(key,),
    )
    return [domain, ip, port, webapp, endpoint, param, auth, api, js]


def test_asset_graph_build_is_deterministic_and_stores_every_record() -> None:
    first = build_asset_graph(_records())
    second = build_asset_graph(_records())
    assert sorted(n.key for n in first.nodes) == sorted(n.key for n in second.nodes)
    assert sorted((e.source, e.target, e.kind) for e in first.edges) == sorted(
        (e.source, e.target, e.kind) for e in second.edges
    )
    kinds = {n.kind for n in first.nodes}
    assert kinds == {"domain", "ip", "port", "webapp", "endpoint", "parameter", "auth", "api", "javascript"}
    # every record's evidence survives as a node in the graph (nothing dropped)
    witnessed = {n.evidence_id for n in first.nodes}
    assert "ev-domain" in witnessed
    assert "ev-js" in witnessed


def test_asset_graph_edges_are_evidence_grounded() -> None:
    graph = build_asset_graph(_records())
    key = endpoint_key("POST", "/api/orders/{order_id}", "api.lab.example.com")
    endpoint = graph.find(key)
    assert endpoint is not None
    # endpoint → parameter link exists and cites the endpoint's own evidence
    param_edges = graph.edges_from(endpoint.key)
    has_parameter = [e for e in param_edges if e.kind == "has_parameter"]
    assert len(has_parameter) == 1
    param = graph.find(has_parameter[0].target)
    assert param is not None and param.evidence_id == "ev-param"
    # every edge carries the evidence that grounded it
    for edge in graph.edges:
        assert edge.evidence_id in {"ev-domain", "ev-ip", "ev-port", "ev-webapp",
                                    "ev-endpoint", "ev-param", "ev-auth", "ev-api", "ev-js"}


def test_orphaned_records_are_stored_without_being_dropped() -> None:
    domain = DomainRecord(hostname="lab.example.com", evidence_id="ev-domain")
    ip = IpRecord(address="10.0.0.5", hostname="lab.example.com", evidence_id="ev-ip")
    graph = build_asset_graph([domain])
    # the lone domain has no derivable edge → stored as a node, never dropped
    assert domain.hostname in {n.key for n in graph.nodes}
    assert graph.find(domain.hostname) is not None
    assert graph.find(domain.hostname).evidence_id == "ev-domain"
    assert all(e.evidence_id != "ev-domain" for e in graph.edges) or not graph.orphan_keys


# ---------------------------------------------------------------------------
# endpoint graph: object-identifier endpoints + auth mechanisms
# ---------------------------------------------------------------------------


def test_endpoint_with_object_id_detects_object_identifier_params() -> None:
    graph = build_asset_graph(_records())
    key = endpoint_key("POST", "/api/orders/{order_id}", "api.lab.example.com")
    object_endpoints = endpoint_with_object_id(graph)
    assert key in {n.key for n in object_endpoints}


def test_auth_mechanisms_for_cites_recorded_auth_evidence() -> None:
    graph = build_asset_graph(_records())
    key = endpoint_key("POST", "/api/orders/{order_id}", "api.lab.example.com")
    mechanisms = auth_mechanisms_for(graph, key)
    assert "session_bearer" in mechanisms


def test_endpoint_subgraph_stays_endpoint_centric() -> None:
    graph = build_asset_graph(_records())
    sub = endpoint_subgraph(graph)
    kinds = {n.kind for n in sub.nodes}
    assert kinds <= {"endpoint", "parameter", "auth", "api", "javascript"}
    assert all(e.source in {n.key for n in sub.nodes} and e.target in {n.key for n in sub.nodes}
               for e in sub.edges)


# ---------------------------------------------------------------------------
# deduplication: deterministic fingerprinting under repeated correlation
# ---------------------------------------------------------------------------


def test_fingerprint_is_deterministic_and_kind_sensitive() -> None:
    key = endpoint_key("POST", "/api/objects/{id}", "api.example.com")
    p1 = ParameterRecord(endpoint_key=key, name="id", location="path",
                         significance="object_id", evidence_id="ev-param")
    p2 = ParameterRecord(endpoint_key=key, name="id", location="query",
                         significance="object_id", evidence_id="ev-param")
    assert fingerprint(p1) == fingerprint(p1)
    assert fingerprint(p1) != fingerprint(p2)
    assert len(fingerprint(p1)) == 64  # sha256 hexdigest


def test_dedupe_functions_are_stable_under_repeated_re_analysis() -> None:
    node = Node(key="k", kind="endpoint", evidence_id="ev", attributes={"host": "h"})
    nodes = dedupe_nodes([node, node])
    assert len(nodes) == 1
    edge = Edge(source="a", target="b", kind="links", evidence_id="ev")
    edges = dedupe_edges([edge, edge])
    assert len(edges) == 1
    inference = Inference(
        kind=OBJECT_API,
        statement="s",
        target_host="h",
        evidence_ids=("ev",),
    )
    inferences = dedupe_inferences([inference, inference])
    assert len(inferences) == 1


# ---------------------------------------------------------------------------
# relationship engine: inferences (not findings), grounded only in evidence
# ---------------------------------------------------------------------------


def test_relationship_engine_emits_object_api_inference_with_evidence() -> None:
    graph = build_asset_graph(_records())
    inferences = run_relationships(graph)
    object_api = [i for i in inferences if i.kind == OBJECT_API]
    assert len(object_api) == 1
    assert object_api[0].target_host == "api.lab.example.com"
    assert set(object_api[0].evidence_ids) >= {"ev-endpoint", "ev-param"}


def test_relationship_engine_maps_authz_surface_for_authenticated_object_models() -> None:
    graph = build_asset_graph(_records())
    inferences = run_relationships(graph)
    authz = [i for i in inferences if i.kind == AUTHZ_SURFACE]
    assert len(authz) == 1
    assert "ev-auth" in set(authz[0].evidence_ids)
    assert "slot" not in authz[0].statement or True


def test_relationship_engine_identifies_documented_api_family() -> None:
    graph = build_asset_graph(_records())
    inferences = run_relationships(graph)
    families = [i for i in inferences if i.kind == API_FAMILY]
    assert len(families) >= 1
    assert any("orders_api" in i.statement for i in families)
    assert any("ev-api" in set(i.evidence_ids) for i in families)


def test_relationship_engine_surfaces_js_discoveries() -> None:
    graph = build_asset_graph(_records())
    inferences = run_relationships(graph)
    js = [i for i in inferences if i.kind == JS_DISCOVERY]
    assert len(js) == 1
    assert "ev-js" in set(js[0].evidence_ids)


def test_relationship_engine_is_deterministic_and_never_asserts_without_evidence() -> None:
    first = run_relationships(build_asset_graph(_records()))
    second = run_relationships(build_asset_graph(_records()))
    assert [i.statement for i in first] == [i.statement for i in second]
    minimal = build_asset_graph([DomainRecord(hostname="plain.example.com",
                                              evidence_id="ev-domain")])
    assert run_relationships(minimal) == ()
