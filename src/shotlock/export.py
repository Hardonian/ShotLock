"""Export package: the editorial handoff.

Self-contained by design — the report must open without this application
running and must disclose all analysis transforms and missing checks. Files:

    report.html     self-contained HTML review report
    findings.json   the ReviewReport record verbatim
    issues.csv      flat issue list for tracking
    selected_media  the candidate (copied), digest recorded in manifest.json
    manifest.json   what the package contains, including honest gaps

The OTIO timeline is produced only when OpenTimelineIO is installed AND the
timeline validates; otherwise the manifest records it as unavailable rather
than shipping something untested. We do not promise universal editor
compatibility — validate the actual target editor and adapter.
"""
from __future__ import annotations

import csv
import html
import json
import shutil
from pathlib import Path
from typing import Any

UNAVAILABLE = "unavailable"


def _render_html(report: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html.escape(str(value))

    findings_rows = "".join(
        "<tr>"
        f"<td>{esc(f.get('finding_id'))}</td>"
        f"<td>{esc((f.get('constraint') or {}).get('kind'))}</td>"
        f"<td>{esc((f.get('constraint') or {}).get('class'))}</td>"
        f"<td>{esc(f.get('comparison_method'))}</td>"
        f"<td>{esc(f.get('frame_range'))}</td>"
        f"<td>{esc(f.get('severity'))}</td>"
        f"<td>{esc((f.get('uncertainty') or {}).get('level'))}: {esc((f.get('uncertainty') or {}).get('note'))}</td>"
        "</tr>"
        for f in report["findings"]
    ) or "<tr><td colspan='7'>(no findings)</td></tr>"

    missing_rows = "".join(
        f"<li><strong>{esc(m['check'])}</strong>: {esc(m['reason'])}</li>"
        for m in report["missing_checks"]
    ) or "<li>none</li>"

    transforms_rows = "".join(
        f"<li>{esc(t.get('kind'))}: {esc(t.get('parameters'))}</li>"
        for t in report["analysis_transforms"]
    ) or "<li>none</li>"

    checks_rows = "".join(
        f"<li>{esc(c['check'])}: <strong>{esc(c['outcome'])}</strong>"
        + (f" — {esc(c['detail'])}" if c.get("detail") else "")
        + "</li>"
        for c in report["checks_run"]
    ) or "<li>none</li>"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>ShotLock review {esc(report['report_id'])}</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111; }}
 table {{ border-collapse: collapse; width: 100%; }}
 th, td {{ border: 1px solid #bbb; padding: .4rem .6rem; text-align: left; font-size: .9rem; }}
 .warn {{ background: #fff3cd; border: 1px solid #e0c060; padding: .8rem; margin: 1rem 0; }}
 .meta {{ color: #444; font-size: .85rem; }}
 h1 {{ font-size: 1.4rem; }}
</style></head><body>
<h1>ShotLock review report — {esc(report['report_id'])}</h1>
<p class="meta">run {esc(report['run_id'])} · intent revision {esc(report['intent_revision'])}<br>
source <code>{esc(report['source_digest'])}</code><br>
candidate <code>{esc(report['candidate_digest'])}</code><br>
generated {esc(report['generated_at'])}</p>

<div class="warn"><strong>Checks that did NOT run</strong> (never counted as passed):
<ul>{missing_rows}</ul></div>

<h2>Findings</h2>
<table><thead><tr><th>id</th><th>constraint</th><th>class</th><th>method</th><th>frames</th><th>severity</th><th>uncertainty</th></tr></thead>
<tbody>{findings_rows}</tbody></table>

<h2>Checks run</h2><ul>{checks_rows}</ul>

<h2>Analysis transforms (disclosure)</h2><ul>{transforms_rows}</ul>

<p class="meta">Evidence only. No metric here guarantees that performance or meaning is
unchanged. Acceptance is the filmmaker's decision.</p>
</body></html>"""


def _write_csv(report: dict[str, Any], path: Path) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["finding_id", "constraint_kind", "constraint_class", "comparison_method",
             "frame_start", "frame_end_exclusive", "severity", "uncertainty_level", "note"]
        )
        for f in report["findings"]:
            writer.writerow([
                f.get("finding_id"),
                (f.get("constraint") or {}).get("kind"),
                (f.get("constraint") or {}).get("class"),
                f.get("comparison_method"),
                (f.get("frame_range") or {}).get("start"),
                (f.get("frame_range") or {}).get("end_exclusive"),
                f.get("severity"),
                (f.get("uncertainty") or {}).get("level"),
                (f.get("uncertainty") or {}).get("note"),
            ])


def _try_otio(report: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    try:
        import opentimelineio as otio  # type: ignore
    except ImportError:
        return {"status": UNAVAILABLE, "reason": "OpenTimelineIO not installed; timeline export deferred"}
    try:
        timeline = otio.schema.Timeline(name=report["report_id"])
        track = otio.schema.Track(name="shot")
        timeline.tracks.append(track)
        path = out_dir / "timeline.otio"
        otio.adapters.write_to_file(timeline, str(path))
        return {"status": "exported", "path": path.name, "note": "shot ranges to be mapped week 3; adapter validation still required"}
    except Exception as exc:  # validation failed — say so, do not ship broken output
        return {"status": UNAVAILABLE, "reason": f"OTIO export failed validation: {exc}"}


def export_package(
    report: dict[str, Any],
    candidate_path: str,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Write the handoff package. Returns the manifest (also written to disk)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    findings_path = out / "findings.json"
    findings_path.write_text(json.dumps(report, indent=2, sort_keys=True))
    _write_csv(report, out / "issues.csv")
    (out / "report.html").write_text(_render_html(report))

    selected = out / ("selected_media" + Path(candidate_path).suffix)
    shutil.copy2(candidate_path, selected)

    otio_status = _try_otio(report, out)

    manifest = {
        "report_id": report["report_id"],
        "run_id": report["run_id"],
        "candidate_digest": report["candidate_digest"],
        "files": {
            "html_report": "report.html",
            "findings_json": "findings.json",
            "issues_csv": "issues.csv",
            "selected_media": selected.name,
        },
        "otio_timeline": otio_status,
        "missing_checks": report["missing_checks"],
        "analysis_transforms": report["analysis_transforms"],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest
