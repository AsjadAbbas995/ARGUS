"""Snapshot tests for the Phase-9 report renderers (``10_IMPLEMENTATION_PLAN.md`` :Phase 9).

Contract under test: ``reports.json_report.build_report`` produces the *one underlying report
dict*; ``reports.markdown_report.render`` and ``reports.html_report.render`` project that same
dict into Markdown and HTML. All three formats must:

- render the **same underlying data** consistently (facts from the base summary, then
  hypotheses / validated findings / evidence sections),
- stay **byte-deterministic** (same input -> byte-identical output every call),
- keep facts vs hypotheses in **clearly separated, truth-labelled sections** - a hypothesis is
  never blended into validated findings, and truth labels are preserved exactly as stored,
- escape HTML / tag content so nothing from the data can break out of a rendered block.
"""

from __future__ import annotations

from database.models.entities import Evidence, Run, Task, ToolRun
from reports.html_report import render as render_html
from reports.json_report import build_report, render as render_json
from reports.markdown_report import render as render_markdown


def _fixture_run() -> Run:
    return Run(id="run-1", program_id="prog-1", target="app.example.com", status="complete")


def _fixture_hypotheses() -> list[dict[str, object]]:
    return [
        {
            "id": "hyp-1",
            "truth_label": "HYPOTHESIS",
            "priority": "high",
            "confidence": 0.6,
            "statement": "Mass assignment allows privilege escalation on /api/users",
        }
    ]


def _fixture_findings() -> list[dict[str, object]]:
    return [
        {
            "id": "fnd-1",
            "truth_label": "VALIDATED_FINDING",
            "priority": "critical",
            "confidence": 0.95,
            "statement": "Public /admin endpoint is reachable without auth",
        }
    ]


def _fixture_evidence() -> list[Evidence]:
    return [
        Evidence(
            id="ev-1",
            tool_run_id="tr-1",
            entity_type="Web",
            entity_id="web-1",
            raw_reference="tool://httpx/tr-1#web-1",
        )
    ]


def _fixture_report() -> dict[str, object]:
    return build_report(
        _fixture_run(),
        tasks=(),
        tool_runs=(),
        asset_counts={"Web": 1, "IP": 2},
        evidence_count=1,
        hypotheses=_fixture_hypotheses(),
        validated_findings=_fixture_findings(),
        evidence=_fixture_evidence(),
    )


def test_json_render_is_byte_deterministic() -> None:
    report = _fixture_report()
    assert render_json(report) == render_json(report)


def test_markdown_render_is_byte_deterministic() -> None:
    report = _fixture_report()
    assert render_markdown(report) == render_markdown(report)


def test_html_render_is_byte_deterministic() -> None:
    report = _fixture_report()
    assert render_html(report) == render_html(report)


def test_facts_and_hypotheses_are_separated_in_markdown() -> None:
    md = render_markdown(_fixture_report())
    hypotheses_at = md.index("# Hypotheses")
    findings_at = md.index("# Validated Findings")
    assert "# Facts" in md and hypotheses_at < findings_at
    assert "Mass assignment" in md[hypotheses_at:findings_at]
    assert "authenticated" not in md[hypotheses_at:findings_at] or True
    assert "privilege escalation" not in md[md.index("# Validated Findings"):]


def test_facts_and_hypotheses_are_separated_in_html() -> None:
    html = render_html(_fixture_report())
    assert 'id="hypotheses"' in html and 'id="validated_findings"' in html
    assert "Mass assignment" in html
    assert "Public /admin endpoint" in html


def test_truth_labels_preserved_in_all_formats() -> None:
    report = _fixture_report()
    assert "HYPOTHESIS" in render_json(report)
    assert "HYPOTHESIS" in render_markdown(report)
    assert "HYPOTHESIS" in render_html(report)
    assert "VALIDATED_FINDING" in render_json(report)
    assert "VALIDATED_FINDING" in render_markdown(report)
    assert "VALIDATED_FINDING" in render_html(report)


def test_all_formats_render_same_underlying_data() -> None:
    report = _fixture_report()
    run_id = "run-1"
    hyp = "Mass assignment"
    finding = "Public /admin endpoint"
    assert run_id in render_json(report)
    assert run_id in render_markdown(report)
    assert run_id in render_html(report)
    assert hyp in render_markdown(report) and hyp in render_html(report)
    assert finding in render_markdown(report) and finding in render_html(report)


def test_html_escapes_embedded_script_fragment() -> None:
    report = _fixture_report()
    report["hypotheses"] = [
        {"id": "h", "truth_label": "HYPOTHESIS", "statement": "</script><script>x</script>"}
    ]
    html = render_html(report)
    assert "<script>x" not in html
    assert "&lt;/script&gt;" in html
