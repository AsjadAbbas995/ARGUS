"""Relationship engine ("03_RECON_PIPELINE.md" §26 Correlation).

Cross-references the attack-surface graph to produce ``INFERENCE``-labelled statements
grounded in cited evidence (never findings). Every inference cites only caller-supplied
evidence IDs; when supporting evidence is insufficient, **no inference is asserted**
(§26 failure condition). Deterministic: same graph → same inferences.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from correlation.deduplication import dedupe_inferences
from correlation.endpoint_graph import (
    auth_mechanisms_for,
    endpoint_with_object_id,
    linked_endpoint,
)
from correlation.records import Graph, Node

# Inference kinds the recon loop maps to proposed tasks.
OBJECT_API = "object_api"
AUTHZ_SURFACE = "authz_surface"
API_FAMILY = "api_family"
JS_DISCOVERY = "js_discovery"


@dataclass(frozen=True)
class Inference:
    """One evidence-grounded inference (03 §26: inferences, not findings)."""

    kind: str
    statement: str
    target_host: str
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    truth_label: str = "INFERENCE"


def run(graph: Graph) -> tuple[Inference, ...]:
    """Derive all supported inferences from ``graph`` in deterministic order."""
    inferences: list[Inference] = []
    for endpoint in endpoint_with_object_id(graph):
        param = _object_id_param(graph, endpoint)
        if param is None:
            continue
        host = endpoint.attributes.get("host", "")
        endpoint_label = _endpoint_label(endpoint)
        inferences.append(
            Inference(
                kind=OBJECT_API,
                statement=(
                    f"the application appears to use object-based API access patterns: "
                    f"object-identifier parameter `{param.attributes.get('name')}` in "
                    f"`{endpoint_label}`"
                ),
                target_host=host,
                evidence_ids=(endpoint.evidence_id, param.evidence_id),
            )
        )
        mechanisms = auth_mechanisms_for(graph, endpoint.key)
        if mechanisms:
            inferences.append(
                Inference(
                    kind=AUTHZ_SURFACE,
                    statement=(
                        f"object-identifier endpoint `{endpoint_label}` with "
                        f"`{', '.join(mechanisms)}` auth warrants authorization testing "
                        "(broken-object-level-authorization surface)"
                    ),
                    target_host=host,
                    evidence_ids=(
                        endpoint.evidence_id,
                        param.evidence_id,
                        *(_auth_evidence_ids(graph, endpoint.key)),
                    ),
                )
            )
    inferences.extend(_api_families(graph))
    inferences.extend(_js_discoveries(graph))
    return dedupe_inferences(inferences)


def _object_id_param(graph: Graph, endpoint: Node) -> Optional[Node]:
    for edge in graph.edges_from(endpoint.key):
        if edge.kind != "has_parameter":
            continue
        param = graph.find(edge.target)
        if param is not None and param.attributes.get("significance") == "object_id":
            return param
    return None


def _auth_evidence_ids(graph: Graph, endpoint_key: str) -> tuple[str, ...]:
    ids = []
    for edge in graph.edges_from(endpoint_key):
        if edge.kind == "requires_auth":
            auth = graph.find(edge.target)
            if auth is not None:
                ids.append(auth.evidence_id)
    return tuple(ids)


def _api_families(graph: Graph) -> list[Inference]:
    inferences: list[Inference] = []
    for api in graph.nodes_of("api"):
        if api.attributes.get("documented") != "True":
            continue
        host = api.attributes.get("host", "")
        documented = [
            graph.find(e.target)
            for e in graph.edges_from(api.key)
            if e.kind == "documents"
        ]
        documented = [n for n in documented if n is not None]
        if not documented:
            continue
        inferences.append(
            Inference(
                kind=API_FAMILY,
                statement=(
                    f"API `{api.attributes.get('name')}` "
                    f"({api.attributes.get('api_type')}) documents "
                    f"{len(documented)} endpoint(s) on `{host}`"
                ),
                target_host=host,
                evidence_ids=(api.evidence_id, *(n.evidence_id for n in documented)),
            )
        )
    return inferences


def _js_discoveries(graph: Graph) -> list[Inference]:
    inferences: list[Inference] = []
    for js in graph.nodes_of("javascript"):
        for edge in graph.edges_from(js.key):
            if edge.kind != "references":
                continue
            endpoint = graph.find(edge.target)
            if endpoint is None:
                continue
            inferences.append(
                Inference(
                    kind=JS_DISCOVERY,
                    statement=(
                        f"endpoint `{_endpoint_label(endpoint)}` surfaced from "
                        f"JavaScript analysis of `{js.attributes.get('js_url')}`"
                    ),
                    target_host=endpoint.attributes.get("host", ""),
                    evidence_ids=(js.evidence_id, endpoint.evidence_id),
                )
            )
    return inferences


def _endpoint_label(endpoint: Node) -> str:
    return f"{endpoint.attributes.get('method')} {endpoint.attributes.get('pattern')}"