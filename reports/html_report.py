"""HTML projection of the committed JSON report (``09_OUTPUTS.md`` :Report Structure).

Projects the **same** underlying report dict that ``build_report`` builds in
``reports/json_report.py`` (so JSON / Markdown / HTML all render one data object) and keeps the
truth-label contract: run/task/tool-run/asset/dedup facts in their own section, hypotheses in a
clearly labelled ``# Hypotheses`` block with stored ``truth_label`` and ``confidence``, validated
findings separate, and the evidence chain traceable - facts are never blended with hypotheses.

Deterministic by construction: no wall-clock, no randomness, no module state; every list is
rendered in the exact order fixed by ``build_report``; every emitted string is HTML-escaped so the
output depends only on the report dict. Byte-reproducible for identical inputs.
"""

from __future__ import annotations

from html import escape
from typing import Any, Iterable, Mapping

_SECTIONS = ("hypotheses", "validated_findings", "evidence")
_FACTS = ("run", "assets", "tasks", "tool_runs", "dedup")


def render(report: Mapping[str, Any]) -> str:
    """Render ``report`` to deterministic, escaped, facts-vs-hypotheses-separated HTML."""
    out: list[str] = [
        "<!DOCTYPE html>\n",
        "<html lang=\"en\">\n",
        "<head>\n",
        "<meta charset=\"utf-8\">\n",
        "<title>ARGUS Run Report</title>\n",
        "</head>\n",
        "<body>\n",
        "<h1>ARGUS Run Report</h1>\n",
        _facts_section(report),
        _hypotheses_section(report),
        _findings_section(report),
        _evidence_section(report),
        "</body>\n",
        "</html>\n",
    ]
    return "".join(out)


def _facts_section(report: Mapping[str, Any]) -> str:
    out: list[str] = ["<section id=\"facts\">\n", "<h2>Facts</h2>\n"]
    run = report.get("run")
    if isinstance(run, Mapping):
        out.append("<dl>\n")
        for k in ("id", "program_id", "status", "target"):
            if k in run:
                out.append("<dt>{0}</dt><dd>{1}</dd>\n".format(escape(k), escape(str(run[k]))))
        out.append("</dl>\n")
    assets = report.get("assets")
    if isinstance(assets, Mapping) and assets:
        out.append("<h3>Asset Counts</h3>\n<ul>\n")
        for name, count in sorted(assets.items()):
            out.append("<li>{0}: {1}</li>\n".format(escape(str(name)), escape(str(count))))
        out.append("</ul>\n")
    for key in ("tasks", "tool_runs", "dedup"):
        section = report.get(key)
        if isinstance(section, Mapping):
            out.append(_nested_section(key, section))
    out.append("</section>\n")
    return "".join(out)


def _nested_section(name: str, section: Mapping[str, Any]) -> str:
    out: list[str] = [f"<h3>{escape(name)}</h3>\n", "<ul>\n"]
    total = section.get("total")
    if total is not None:
        out.append("<li>total: {0}</li>\n".format(escape(str(total))))
    for k, v in section.items():
        if k == "total":
            continue
        if isinstance(v, list) and v:
            out.append("<li>{0}: {1} item(s)</li>\n".format(escape(k), len(v)))
        else:
            out.append("<li>{0}: {1}</li>\n".format(escape(k), escape(str(v))))
    out.append("</ul>\n")
    return "".join(out)


def _hypotheses_section(report: Mapping[str, Any]) -> str:
    out: list[str] = ["<section id=\"hypotheses\">\n", "<h2>Hypotheses</h2>\n"]
    items = report.get("hypotheses")
    if isinstance(items, list) and items:
        out.append("<ul>\n")
        for item in items:
            if not isinstance(item, Mapping):
                continue
            out.append(_hypothesis_item(item))
        out.append("</ul>\n")
    else:
        out.append("<p>No hypotheses recorded.</p>\n")
    out.append("</section>\n")
    return "".join(out)


def _hypothesis_item(item: Mapping[str, Any]) -> str:
    truth = escape(str(item.get("truth_label", "UNVERIFIED_CLAIM")))
    statement = escape(str(item.get("statement", item.get("reasoning", ""))))
    priority = escape(str(item.get("priority", "none")))
    confidence = escape(str(item.get("confidence", 0.0)))
    out: list[str] = [
        "<li><strong>{0}</strong> - {1}<br/>".format(truth, statement),
        "<em>priority={0} confidence={1}</em></li>\n".format(priority, confidence),
    ]
    return "".join(out)


def _findings_section(report: Mapping[str, Any]) -> str:
    out: list[str] = ["<section id=\"validated_findings\">\n", "<h2>Validated Findings</h2>\n"]
    items = report.get("validated_findings")
    if isinstance(items, list) and items:
        out.append("<ul>\n")
        for item in items:
            if not isinstance(item, Mapping):
                continue
            truth = escape(str(item.get("truth_label", "VALIDATED_FINDING")))
            statement = escape(str(item.get("statement", item.get("reasoning", ""))))
            out.append("<li><strong>{0}</strong> - {1}</li>\n".format(truth, statement))
        out.append("</ul>\n")
    else:
        out.append("<p>No validated findings recorded.</p>\n")
    out.append("</section>\n")
    return "".join(out)


def _evidence_section(report: Mapping[str, Any]) -> str:
    out: list[str] = ["<section id=\"evidence\">\n", "<h2>Evidence</h2>\n"]
    items = report.get("evidence")
    if isinstance(items, list) and items:
        out.append("<ul>\n")
        for item in items:
            if not isinstance(item, Mapping):
                continue
            ref = escape(str(item.get("raw_reference", "")))
            entity = escape(str(item.get("entity_type", "")))
            entity_id = escape(str(item.get("entity_id", "")))
            run_id = escape(str(item.get("tool_run_id", "")))
            out.append(
                "<li>{0} ({1}: {2} / tool_run {3})</li>\n".format(ref, entity, entity_id, run_id)
            )
        out.append("</ul>\n")
    else:
        out.append("<p>No evidence recorded.</p>\n")
    out.append("</section>\n")
    return "".join(out)
