"""Attack-Surface Graph builder ("03_RECON_PIPELINE.md" §25 Logical Grouping).

Turns normalized correlation records into a queryable ``Graph`` spanning
``Domain → Subdomain → IP → Port → Service → Web App → URL → Endpoint → Parameter →
API/Authentication/Technology`` plus cross-links (``JavaScript → Endpoint``,
``Certificate → Domain``, ``API → Endpoint``). Every edge is evidence-referenced, and a
record with no derivable link is still stored as a node — never dropped.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from correlation.deduplication import dedupe_edges, dedupe_nodes
from correlation.records import (
    Edge,
    Graph,
    Node,
    record_node,
)


def build(records: Iterable[Any]) -> Graph:
    """Build the evidence-referenced attack-surface graph over ``records``.

    Deterministic: the same records always yield the same node/edge sets. Orphaned nodes
    remain stored without an edge (03 §25 failure condition).
    """
    nodes = dedupe_nodes([record_node(r) for r in records])
    by_key = {n.key: n for n in nodes}
    edges: list[Edge] = []
    for node in nodes:
        edges.extend(_edges_for(node, by_key))
    return Graph(nodes=dedupe_nodes(nodes), edges=dedupe_edges(edges))


def _edges_for(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    if node.kind == "domain":
        return _domain_edges(node, by_key)
    if node.kind == "ip":
        return _ip_edges(node, by_key)
    if node.kind == "port":
        return _port_edges(node, by_key)
    if node.kind == "webapp":
        return _webapp_edges(node, by_key)
    if node.kind == "endpoint":
        return _endpoint_edges(node, by_key)
    if node.kind == "parameter":
        return _parameter_edges(node, by_key)
    if node.kind == "auth":
        return _auth_edges(node, by_key)
    if node.kind == "api":
        return _api_edges(node, by_key)
    if node.kind == "javascript":
        return _javascript_edges(node, by_key)
    if node.kind == "certificate":
        return _certificate_edges(node, by_key)
    if node.kind == "technology":
        return _technology_edges(node, by_key)
    return []


def _host_node(by_key: dict[str, Node], host: str) -> Optional[Node]:
    """A domain/webapp node standing for ``host`` (prefer the exact domain node)."""
    if host in by_key:
        return by_key[host]
    for node in by_key.values():
        if node.kind == "webapp" and node.key.startswith(f"{host}:"):
            return node
    return None


def _domain_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    parts = node.key.split(".")
    parent = ".".join(parts[1:]) if len(parts) > 1 else ""
    if parent and parent in by_key:
        return [Edge(parent, node.key, "parent_of", node.evidence_id)]
    return []


def _ip_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    host = _attr(node, "hostname")
    target = _host_node(by_key, host)
    if target is not None:
        return [Edge(target.key, node.key, "resolves_to", node.evidence_id)]
    return []


def _port_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    ip = _attr(node, "ip")
    if ip in by_key:
        return [Edge(ip, node.key, "hosts", node.evidence_id)]
    return []


def _webapp_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    port = by_key.get(f"{_attr(node, 'ip')}:{_attr(node, 'port')}")
    if port is not None:
        return [Edge(port.key, node.key, "serves", node.evidence_id)]
    return []


def _endpoint_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    host = _attr(node, "host")
    target = _host_node(by_key, host)
    if target is not None:
        return [Edge(target.key, node.key, "serves_url", node.evidence_id)]
    return []


def _parameter_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    endpoint = _attr(node, "endpoint_key")
    if endpoint in by_key:
        return [Edge(endpoint, node.key, "has_parameter", node.evidence_id)]
    return []


def _auth_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    endpoint = _attr(node, "endpoint_key")
    if endpoint in by_key:
        return [Edge(endpoint, node.key, "requires_auth", node.evidence_id)]
    return []


def _api_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    host = _attr(node, "host")
    edges: list[Edge] = []
    hostnode = _host_node(by_key, host)
    if hostnode is not None:
        edges.append(Edge(hostnode.key, node.key, "hosts_api", node.evidence_id))
    if _attr(node, "documented") == "True":
        for other in by_key.values():
            if other.kind == "endpoint" and other.attributes.get("host") == host:
                edges.append(Edge(node.key, other.key, "documents", node.evidence_id))
    return edges


def _javascript_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    edges: list[Edge] = []
    for endpoint in node.attributes.get("endpoint_keys", "").split("|"):
        if endpoint and endpoint in by_key:
            edges.append(Edge(node.key, endpoint, "references", node.evidence_id))
    return edges


def _certificate_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    target = _host_node(by_key, _attr(node, "host"))
    if target is not None:
        return [Edge(node.key, target.key, "identity_of", node.evidence_id)]
    return []


def _technology_edges(node: Node, by_key: dict[str, Node]) -> list[Edge]:
    target = _host_node(by_key, _attr(node, "host"))
    if target is not None:
        return [Edge(target.key, node.key, "runs", node.evidence_id)]
    return []


def _attr(node: Node, name: str) -> str:
    return node.attributes.get(name, "")