"""Markdown projection of the committed JSON report (``09_OUTPUTS.md`` :Report Structure).

Projects the **same** underlying report dict that ``reports.json_report.build_report`` builds
(so JSON / Markdown / HTML all render one data object) and keeps the truth-label contract:

- Facts (run metadata, assets, task surface, tool runs, dedup) are rendered from their own
  committed sections.
- Hypotheses stay in a clearly labelled ``# Hypotheses`` section; each item carries its stored
  ``truth_label`` and ``confidence`` - never re-ranked, never merged with validated findings.
- Validated findings and the evidence chain are separate, labelled sections.

Deterministic by construction: no wall-clock, no randomness, no module state; every nested list
is rendered in the exact order already fixed by ``build_report``; the emitted text depends only
on the report dict. Byte-reproducible for identical inputs.
"""

from __future__ import annotations

from typing import Any, Mapping

_TOP = "# ARGUS Run Report\n"
_DIVIDER = "\n---\n"

_HYPOTHESES = "hypotheses"
_FINDINGS = "validated_findings"
_EVIDENCE = "evidence"
_TASKS = "tasks"
_TOOL_RUNS = "tool_runs"
_DEDUP = "dedup"
_ASSETS = "assets"
_RUN = "run"

_LABELS = {"HYPOTHESIS", "UNVERIFIED_CLAIM", "VALIDATED_FINDING"}


def render(report: Mapping[str, Any]) -> str:
    """Render ``report`` to deterministic, facts-vs-hypotheses-separated Markdown."""
    parts: list[str] = [_TOP]
    parts.append(_facts_section(report))
    parts.append(_hypotheses_section(report))
    parts.append(_findings_section(report))
    parts.append(_evidence_section(report))
    return "".join(parts)


def _facts_section(report: Mapping[str, Any]) -> str:
    out: list[str] = ["# Facts\n"]
    run = report.get(_RUN)
    if isinstance(run, Mapping):
        out.append(f"- **Run:** {run.get('id', ('missing',))}")
        out.append(f"- **Program:** {run.get('program_id', ('missing',))}")
        out.append(f"- **Status:** {run.get('status', ('missing',))}")
        out.append(f"- **Target:** {run.get('target', ('missing',))}")
    assets = report.get(_ASSETS)
    if isinstance(assets, Mapping) and assets:
        out.append("\n## Asset Counts\n")
        for name, count in sorted(assets.items()):
            out.append(f"- {name}: {int(count)}")
    tasks = report.get(_TASKS)
    _nested_section(out, "## Tasks", tasks)
    _nested_section(out, "## Tool Runs", report.get(_TOOL_RUNS))
    dedup = report.get(_DEDUP)
    if isinstance(dedup, Mapping) and dedup:
        out.append("\n## Deduplication\n")
        out.append(f"- suppressed_completed_fingerprints: {dedup.get('suppressed_completed_fingerprints', 0)}")
    return "".join(out) + _DIVIDER


def _nested_section(out: list[str], heading: str, section: Any) -> None:
    if not isinstance(section, Mapping):
        return
    total = section.get("total", 0)
    by = section.get("by_status") or section.get("by_tool")
    items = section.get("items")
    out.append(f"\n{heading} (total={int(total)})\n")
    if isinstance(by, Mapping):
        for k, v in sorted(by.items()):
            out.append(f"- {k}: {int(v)}")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            label = str(item.get("type", item.get("tool_name", item.get("id", ""))))
            status = str(item.get("status", ""))
            out.append(f"- {label} [{status}]: {str(item.get('target', ''))}")


def _hypotheses_section(report: Mapping[str, Any]) -> str:
    out: list[str] = ["# Hypotheses\n"]
    items = report.get(_HYPOTHESES)
    if isinstance(items, list) and items:
        for h in items:
            if not isinstance(h, Mapping):
                continue
            truth = str(h.get("truth_label", "UNVERIFIED_CLAIM"))
            if truth not in _LABELS:
                truth = "UNVERIFIED_CLAIM"
            statement = str(h.get("statement", h.get("reasoning", "")))
            out.append(f'- **{truth}** - {statement}')
            out.append(f"  priority={h.get('priority', 'none')} confidence={h.get('confidence', 0.0)}")
            ev = h.get("evidence")
            if isinstance(ev, list) and ev:
                ids = ", ".join(str(e) for e in ev)
                out.append(f"  evidence=[{ids}]")
    else:
        out.append("_No hypotheses recorded._")
    return "".join(out) + _DIVIDER


def _findings_section(report: Mapping[str, Any]) -> str:
    out: list[str] = ["# Validated Findings\n"]
    items = report.get(_FINDINGS)
    if isinstance(items, list) and items:
        for f in items:
            if not isinstance(f, Mapping):
                continue
            truth = str(f.get("truth_label", "VALIDATED_FINDING"))
            statement = str(f.get("statement", f.get("reasoning", "")))
            out.append(f'- **{truth}** - {statement}')
            ev = f.get("evidence")
            if isinstance(ev, list) and ev:
                ids = ", ".join(str(e) for e in ev)
                out.append(f"  evidence=[{ids}]")
    else:
        out.append("_No validated findings recorded._")
    return "".join(out) + _DIVIDER


def _evidence_section(report: Mapping[str, Any]) -> str:
    out: list[str] = ["# Evidence\n"]
    items = report.get(_EVIDENCE)
    if isinstance(items, list) and items:
        for e in items:
            if not isinstance(e, Mapping):
                continue
            ref = str(e.get("raw_reference", ""))
            ent = str(e.get("entity_type", ""))
            idx = f"{e.get('entity_id') or '_'}/{e.get('tool_run_id') or '_'}"
            out.append(f"- `{ref}` ({ent}: {idx})")
    else:
        out.append("_No evidence recorded._")
    return "".join(out) + _DIVIDER
