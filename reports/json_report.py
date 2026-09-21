"""JSON report (``09_OUTPUTS.md`` respect: same machine data, one deterministic shape).

Composes ``core/json_summary.build_json_summary`` (the committed single source for run/task/
tool-run facts) with the hypothesis / validated-finding / evidence sections, so the JSON report
is the *one underlying data object* that the Markdown and HTML renderers both project.
Deterministic by construction: every nested list is sorted by a stable key, keys are fixed and
sorted by ``json.dumps(sort_keys=True)``, and value coercion uses a fixed ``default=str`` - the
same inputs always produce byte-identical, machine-valid JSON.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from core.json_summary import build_json_summary
from database.models.entities import Asset, Evidence, Run, Task, ToolRun

_HYPOTHESES_SECTION = "hypotheses"
_FINDINGS_SECTION = "validated_findings"
_EVIDENCE_SECTION = "evidence"

_PRIORITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}


def _hypothesis_key(h: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        h.get("truth_label", ""),
        _PRIORITY_RANK.get(str(h.get("priority", "none")), 5),
        -float(h.get("confidence", 0.0) or 0.0),
        str(h.get("id", "")),
    )


def _evidence_key(e: Evidence) -> tuple[Any, ...]:
    return (e.raw_reference or "", str(e.id))


def _evidence_summary(e: Evidence) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "tool_run_id": str(e.tool_run_id) if e.tool_run_id else None,
        "entity_type": e.entity_type,
        "entity_id": str(e.entity_id) if e.entity_id else None,
        "raw_reference": e.raw_reference,
    }


def build_report(
    run: Run,
    tasks: Iterable[Task] = (),
    tool_runs: Iterable[ToolRun] = (),
    asset_counts: Optional[Mapping[str, int]] = None,
    evidence_count: int = 0,
    hypotheses: Iterable[Mapping[str, Any]] = (),
    validated_findings: Iterable[Mapping[str, Any]] = (),
    evidence: Iterable[Evidence] = (),
) -> dict[str, Any]:
    """Build the full report dict for ``run``.

    The run/task/tool-run surface is delegated verbatim to the committed
    ``core.json_summary.build_json_summary`` (facts), and the hypothesis / validated-finding /
    evidence sections are appended in stable order. Facts and hypotheses stay in *separate,
    correctly labelled* sections; a hypothesis is never promoted into ``validated_findings``.
    """
    base = build_json_summary(
        run,
        tasks=tasks,
        tool_runs=tool_runs,
        evidence_count=evidence_count,
        asset_counts=asset_counts,
    )
    hyp_list = sorted(hypotheses, key=_hypothesis_key)
    finding_list = sorted(validated_findings, key=_hypothesis_key)
    ev_list = sorted(evidence, key=_evidence_key)
    return {
        **base,
        _HYPOTHESES_SECTION: [_normalise(h) for h in hyp_list],
        _FINDINGS_SECTION: [_normalise(f) for f in finding_list],
        _EVIDENCE_SECTION: [_evidence_summary(e) for e in ev_list],
    }


def _normalise(h: Mapping[str, Any]) -> dict[str, Any]:
    """Copy a stored hypothesis/finding item so reports never mutate the source record."""
    return {k: v for k, v in h.items()}


def render(report: Mapping[str, Any]) -> str:
    """Serialise ``report`` to deterministic, machine-valid JSON."""
    import json

    return json.dumps(report, indent=2, sort_keys=True, default=str)
