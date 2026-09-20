"""Phase-8 typed correlation records and the attack-surface graph primitives
("05_DATA_MODEL.md" entities, "03_RECON_PIPELINE.md" §25 Logical Grouping).

The graph is a *descriptive* view over normalized records: it only links what the recorded
facts support, every node/edge carries the traceable evidence that justifies it, and an
orphaned/unlinkable record is **stored without an edge rather than dropped**
(03 §25 failure condition). Building the graph never grants execution capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class DomainRecord:
    """An in-scope domain or discovered subdomain."""

    hostname: str
    evidence_id: str

    @property
    def key(self) -> str:
        return self.hostname


@dataclass(frozen=True)
class IpRecord:
    """A resolved host -> IP binding."""

    address: str
    hostname: str
    evidence_id: str

    @property
    def key(self) -> str:
        return self.address


@dataclass(frozen=True)
class PortRecord:
    """An open port on an IP with its detected service."""

    ip: str
    number: int
    service: str
    evidence_id: str

    @property
    def key(self) -> str:
        return f"{self.ip}:{self.number}"


@dataclass(frozen=True)
class WebAppRecord:
    """A probed web application on a host:port."""

    host: str
    port: int
    status_code: int
    title: str
    ip: str
    evidence_id: str

    @property
    def key(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass(frozen=True)
class EndpointRecord:
    """A recorded HTTP endpoint (method + URL pattern on a host)."""

    method: str
    pattern: str
    host: str
    evidence_id: str

    @property
    def key(self) -> str:
        return endpoint_key(self.method, self.pattern, self.host)


def endpoint_key(method: str, pattern: str, host: str) -> str:
    """Stable key for an endpoint (also used by parameter/auth records to link back)."""
    return f"{method} {pattern} {host}"


@dataclass(frozen=True)
class ParameterRecord:
    """A recorded endpoint parameter."""

    endpoint_key: str
    name: str
    location: str
    significance: str
    evidence_id: str

    @property
    def key(self) -> str:
        return f"{self.endpoint_key}#{self.name}"


@dataclass(frozen=True)
class AuthRecord:
    """One recorded authentication mechanism for an endpoint."""

    mechanism_type: str
    endpoint_key: str
    evidence_id: str

    @property
    def key(self) -> str:
        return f"{self.endpoint_key}#auth:{self.mechanism_type}"


@dataclass(frozen=True)
class ApiRecord:
    """A documented or inferred API binding on a host."""

    name: str
    api_type: str
    host: str
    documented: bool
    evidence_id: str

    @property
    def key(self) -> str:
        return f"{self.name}@{self.host}"


@dataclass(frozen=True)
class TechnologyRecord:
    """One technology observed on a host."""

    name: str
    category: str
    host: str
    evidence_id: str

    @property
    def key(self) -> str:
        return f"{self.name}@{self.host}"


@dataclass(frozen=True)
class JavaScriptRecord:
    """A JavaScript file of interest and the endpoints it surfaced (if any)."""

    js_url: str
    host: str
    evidence_id: str
    endpoint_keys: tuple[str, ...] = field(default_factory=tuple)

    @property
    def key(self) -> str:
        return self.js_url


@dataclass(frozen=True)
class CertificateRecord:
    """A TLS certificate observed for a host."""

    subject: str
    host: str
    evidence_id: str

    @property
    def key(self) -> str:
        return self.subject


# --- graph primitives ---------------------------------------------------------


@dataclass(frozen=True)
class Node:
    """One graph node; ``kind`` names the record type it mirrors."""

    key: str
    kind: str
    evidence_id: str
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    """One evidence-referenced directed edge between two node keys."""

    source: str
    target: str
    kind: str
    evidence_id: str


@dataclass(frozen=True)
class Graph:
    """A queryable, descriptive attack-surface graph (see module docstring)."""

    nodes: tuple[Node, ...] = field(default_factory=tuple)
    edges: tuple[Edge, ...] = field(default_factory=tuple)

    def nodes_of(self, kind: str) -> tuple[Node, ...]:
        return tuple(n for n in self.nodes if n.kind == kind)

    def find(self, key: str) -> Optional[Node]:
        for node in self.nodes:
            if node.key == key:
                return node
        return None

    def edges_from(self, key: str) -> tuple[Edge, ...]:
        return tuple(e for e in self.edges if e.source == key)

    def edges_to(self, key: str) -> tuple[Edge, ...]:
        return tuple(e for e in self.edges if e.target == key)

    def neighbors(self, key: str) -> tuple[Node, ...]:
        targets = {e.target for e in self.edges_from(key)}
        return tuple(n for n in self.nodes if n.key in targets)

    @property
    def orphan_keys(self) -> tuple[str, ...]:
        """Node keys with no incident edge (stored, unlinked — never dropped)."""
        linked = {e.source for e in self.edges} | {e.target for e in self.edges}
        return tuple(n.key for n in self.nodes if n.key not in linked)


def record_node(record: Any) -> Node:
    """Mirror any correlation record into a graph ``Node`` (kind = record type)."""
    kind = type(record).__name__.removesuffix("Record").lower()
    attributes: dict[str, str] = {}
    for name, value in vars(record).items():
        if name == "evidence_id":
            continue
        if isinstance(value, tuple):
            attributes[name] = "|".join(str(v) for v in value)
        else:
            attributes[name] = str(value)
    return Node(key=record.key, kind=kind, evidence_id=record.evidence_id, attributes=attributes)