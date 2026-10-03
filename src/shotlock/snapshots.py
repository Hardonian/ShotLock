"""Supporting-image extraction for findings (evidence snapshots).

For each finding with a machine-readable frame range, grab a representative
frame from source and candidate and compose them side-by-side so a reviewer can
see the comparison at a glance. This is evidence extraction, not a check: it
never asserts correctness. If a snapshot cannot be produced, the finding keeps
an empty ``supporting_images`` list and the gap is disclosed in the manifest —
we never link an image that was not generated, and never fabricate one.

Per the brief, findings carry constraint, method, frame range, severity and
uncertainty; snapshots are attached to those findings as supporting evidence and
linked from the HTML report. Extraction is disclosed in the report manifest the
same way the viewer and OTIO export are, so an absent image is honest rather
than silently missing.
"""
from __future__ import annotations

import shutil
import subprocess  # nosec B404 — ffmpeg invoked with a fixed argument list, never a shell
from pathlib import Path
from typing import Any

UNAVAILABLE = "unavailable"
SNAPSHOT_DIR = "snapshots"


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def _representative_frame(frame_range: dict[str, Any]) -> int | None:
    """First affected frame index, or None when the range is not machine-readable."""
    start = frame_range.get("start")
    end = frame_range.get("end_exclusive")
    if isinstance(start, int) and isinstance(end, int) and end > start >= 0:
        return start
    return None


def _grab_side_by_side(
    ffmpeg: str, source: str, candidate: str, frame_index: int, out_png: Path
) -> bool:
    """Write source|candidate at frame_index. True only when a real PNG is produced."""
    select = f"select='eq(n\\,{frame_index})'"
    filter_complex = (
        f"[0:v]{select},scale=320:-2,setsar=1[a];"
        f"[1:v]{select},scale=320:-2,setsar=1[b];"
        "[a][b]hstack=inputs=2"
    )
    try:
        proc = subprocess.run(  # nosec B603 — fixed argument list, no shell
            [
                ffmpeg, "-v", "error", "-y",
                "-i", source, "-i", candidate,
                "-filter_complex", filter_complex,
                "-frames:v", "1", "-update", "1", str(out_png),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0 and out_png.is_file() and out_png.stat().st_size > 0


def attach_finding_snapshots(
    report: dict[str, Any],
    source_path: str | Path,
    candidate_path: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Populate each finding's ``supporting_images`` / ``inspect_path`` with a
    side-by-side snapshot, and describe the result for the manifest.

    Findings whose frames cannot be captured keep empty ``supporting_images`` —
    never a broken or fabricated link. Returns a manifest entry; status is
    "exported" when every finding is illustrated, "partial" when some are, and
    "unavailable" when none can be (with the reason).
    """
    out = Path(out_dir)
    findings = report.get("findings", [])
    if not isinstance(findings, list) or not findings:
        return {"status": "exported", "generated": 0, "note": "no findings to illustrate"}

    ffmpeg = _ffmpeg()
    if not ffmpeg:
        for finding in findings:
            if isinstance(finding, dict):
                finding.setdefault("supporting_images", [])
        return {
            "status": UNAVAILABLE,
            "reason": "ffmpeg not installed; finding snapshots could not be generated",
            "generated": 0,
        }

    snap_dir = out / SNAPSHOT_DIR
    snap_dir.mkdir(parents=True, exist_ok=True)
    generated = 0
    gaps: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        finding.setdefault("supporting_images", [])
        finding_id = str(finding.get("finding_id") or f"finding-{generated + 1}")
        frame_index = _representative_frame(finding.get("frame_range") or {})
        if frame_index is None:
            gaps.append(f"{finding_id}: no machine-readable frame range; no snapshot")
            continue
        rel = f"{SNAPSHOT_DIR}/{finding_id}.png"
        ok = _grab_side_by_side(
            ffmpeg, str(source_path), str(candidate_path), frame_index, snap_dir / f"{finding_id}.png"
        )
        if ok:
            finding["supporting_images"] = [rel]
            finding["inspect_path"] = rel
            generated += 1
        else:
            gaps.append(f"{finding_id}: frame {frame_index} could not be captured")

    if generated == 0:
        status = UNAVAILABLE
    elif gaps:
        status = "partial"
    else:
        status = "exported"
    entry: dict[str, Any] = {"status": status, "generated": generated, "snapshots_dir": SNAPSHOT_DIR}
    if gaps:
        entry["gaps"] = gaps
    return entry
