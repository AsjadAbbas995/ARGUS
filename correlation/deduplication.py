"""Correlation-level deduplication ("03_RECON_PIPELINE.md" §26 Correlation tools).

Deduplicates graph primitives and correlation inferences so repeated re-analysis over the
same recorded evidence cannot grow the graph or generate duplicate inferences forever. The
deterministic ``fingerprint`` digest is the anti-infinite-loop key used by the adaptive loop.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Iterable, Sequence, TypeVar

from correlation.records import Edge, Graph, Node

_T = TypeVar("_T")


def fingerprint(value: Any) -> str:
    """Deterministic content digest (stable across processes/machines)."""
    digest = hashlib.sha256()
    digest.update(repr(_stable(value)).encode("utf-8"))
    return digest.hexdigest()


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _stable(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_stable(item) for item in value]
    return value


def _dedupe(items: Iterable[_T], key: Callable[[_T], Any]) -> tuple[_T, ...]:
    """Drop later items sharing a key, preserving first-occurrence order."""
    seen: set = set()
    kept: list[_T] = []
    for item in items:
        k = key(item)
        if k in seen:
            continue
        seen.add(k)
        kept.append(item)
    return tuple(kept)


def dedupe_nodes(nodes: Iterable[Node]) -> tuple[Node, ...]:
    """Deduplicate nodes by ``key`` (first occurrence wins)."""
    return _dedupe(nodes, lambda n: n.key)


def dedupe_edges(edges: Iterable[Edge]) -> tuple[Edge, ...]:
    """Deduplicate edges by ``(source, target, kind)`` (first occurrence wins)."""
    return _dedupe(edges, lambda e: (e.source, e.target, e.kind))


def dedupe_inferences(inferences: Iterable[_T]) -> tuple[_T, ...]:
    """Deduplicate inferences by their fingerprint (first occurrence wins)."""
    return _dedupe(inferences, lambda i: fingerprint(i))


def merge_graphs(graphs: Sequence[Graph]) -> Graph:
    """Union of several graphs with nodes/edges deduplicated by identity."""
    nodes = dedupe_nodes(n for graph in graphs for n in graph.nodes)
    edges = dedupe_edges(e for graph in graphs for e in graph.edges)
    return Graph(nodes=nodes, edges=edges)