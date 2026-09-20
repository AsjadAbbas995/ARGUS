"""Endpoint-relationship view of the attack-surface graph
("03_RECON_PIPELINE.md" §25 cross-links, §26 Correlation).

Projects the full graph onto the endpoint-centric relationships (``Endpoint → Parameter``,
``Endpoint → Authentication``, ``JavaScript → Endpoint``, ``API → Endpoint``) so the
relationship engine and the recon loop reason over exactly the endpoint surface.
"""

from __future__ import annotations

from typing import Optional

from correlation.records import Edge, Graph, Node

ENDPOINT_KINDS = frozenset({"endpoint", "parameter", "auth", "javascript", "api"})


def endpoint_subgraph(graph: Graph) -> Graph:
    """Endpoint-centric projection: node/edge sets restricted to ``ENDPOINT_KINDS``."""
    keys = {n.key for n in graph.nodes if n.kind in ENDPOINT_KINDS}
    nodes = tuple(n for n in graph.nodes if n.key in keys)
    edges = tuple(
        e for e in graph.edges if e.source in keys and e.target in keys
    )
    return Graph(nodes=nodes, edges=edges)


def linked_endpoint(graph: Graph, node: Node) -> Optional[Node]:
    """The endpoint a parameter/auth link points back at."""
    for edge in graph.edges_to(node.key):
        if edge.kind in {"has_parameter", "requires_auth"}:
            return graph.find(edge.source)
    return None


def endpoint_with_object_id(graph: Graph) -> tuple[Node, ...]:
    """Endpoints exposing an object-identifier parameter, in graph order."""
    seen: list[Node] = []
    for node in graph.nodes:
        if node.kind != "parameter":
            continue
        if node.attributes.get("significance") == "object_id":
            endpoint = linked_endpoint(graph, node)
            if endpoint is not None and endpoint.key not in {n.key for n in seen}:
                seen.append(endpoint)
    return tuple(seen)


def auth_mechanisms_for(graph: Graph, endpoint_key: str) -> tuple[str, ...]:
    """Recorded authentication mechanisms for one endpoint, in graph order."""
    kinds = []
    for edge in graph.edges_from(endpoint_key):
        if edge.kind != "requires_auth":
            continue
        auth = graph.find(edge.target)
        if auth is not None:
            kinds.append(auth.attributes.get("mechanism_type", ""))
    return tuple(sorted(k for k in kinds if k))