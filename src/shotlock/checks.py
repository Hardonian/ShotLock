"""Deterministic preservation checks.

Every check returns an explicit outcome: "pass", "fail", or "unavailable".
A check that did not run goes to missing_checks with a reason — it must never
appear as passed. Hard failures block acceptance; review signals route to a
human; nothing here claims creative correctness.

Findings follow schemas/review-report.schema.json exactly: constraint,
comparison method, frame range, severity, uncertainty.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess  # nosec B404 — ffmpeg invoked with fixed argument lists, never a shell
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .media import UNAVAILABLE, FfprobeMissing, compare_integrity, inspect_media

CHECK_MEDIA_INTEGRITY = "media_integrity"
CHECK_AUDIO_PRESERVATION = "audio_preservation"
CHECK_PROTECTED_REGION = "protected_region_stability"
CHECK_FRAME_DUPLICATE = "frame_duplicate"


@dataclass
class CheckResult:
    check: str
    outcome: str  # "pass" | "fail" | "unavailable"
    findings: list[dict[str, Any]] = field(default_factory=list)
    detail: str | None = None
    # Per-item sub-checks that did not run (e.g. an unmapped audio track). These
    # merge into the report's missing_checks so a gap is disclosed, never passed.
    missing: list[dict[str, Any]] = field(default_factory=list)


def _finding(
    finding_id: str,
    constraint_kind: str,
    constraint_class: str,
    comparison_method: str,
    frame_range: dict[str, int],
    severity: str,
    uncertainty_level: str,
    note: str,
    affected_region: dict[str, Any] | None = None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "finding_id": finding_id,
        "constraint": {"kind": constraint_kind, "class": constraint_class},
        "comparison_method": comparison_method,
        "frame_range": frame_range,
        "severity": severity,
        "uncertainty": {"level": uncertainty_level, "note": note},
        "supporting_images": [],
    }
    if affected_region is not None:
        finding["affected_region"] = affected_region
    return finding


def media_integrity_check(source_path: str, candidate_path: str, intent: dict[str, Any]) -> CheckResult:
    """Hard constraints: frame count, duration, rational frame rate, decode."""
    frame_range = intent["frame_range"]
    try:
        source_info = inspect_media(source_path)
        candidate_info = inspect_media(candidate_path)
    except (FfprobeMissing, ValueError) as exc:
        return CheckResult(CHECK_MEDIA_INTEGRITY, "unavailable", detail=str(exc))

    comparison = compare_integrity(source_info, candidate_info)
    findings: list[dict[str, Any]] = []
    for i, message in enumerate(comparison["hard_failures"]):
        findings.append(
            _finding(
                f"mi-{i + 1}",
                "media_integrity",
                "hard",
                "ffprobe_stream_properties",
                frame_range,
                "blocking",
                "low",
                message,
            )
        )
    for i, message in enumerate(comparison["review_signals"]):
        findings.append(
            _finding(
                f"mi-r{i + 1}",
                "media_integrity",
                "review_signal",
                "ffprobe_stream_properties",
                frame_range,
                "review",
                "medium",
                message,
            )
        )
    if comparison["unavailable"]:
        detail = "; ".join(comparison["unavailable"])
        outcome = "fail" if findings else "unavailable"
        return CheckResult(CHECK_MEDIA_INTEGRITY, outcome, findings, detail=detail)
    return CheckResult(
        CHECK_MEDIA_INTEGRITY,
        "fail" if comparison["hard_failures"] else ("pass" if not comparison["review_signals"] else "pass"),
        findings,
        detail="; ".join(comparison["hard_failures"]) or None,
    )


def _audio_stream_count(path: str) -> tuple[int | None, str | None]:
    """Number of audio streams in a container. (None, gap) on a tooling failure."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None, "ffprobe not found on PATH; audio track mapping unavailable"
    try:
        proc = subprocess.run(  # nosec B603 — fixed argument list, no shell
            [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries",
             "stream=index", "-of", "json", path],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return None, "audio stream enumeration timed out"
    if proc.returncode != 0:
        return None, f"ffprobe could not read audio streams from {path!r}"
    try:
        streams = json.loads(proc.stdout or "{}").get("streams") or []
    except json.JSONDecodeError:
        return None, "ffprobe returned unparseable audio stream data"
    return len(streams), None


def _decoded_audio_md5_at(path: str, audio_index: int) -> tuple[str | None, str | None]:
    """MD5 of the decoded audio stream at relative index `audio_index` (content
    comparison, not container hash: container bytes can differ while audio is
    equivalent).

    Returns (md5, unavailable_reason). (None, None) means that stream genuinely
    has no decodable audio — a real absence, not a tooling gap.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None, "ffmpeg not installed; decoded-audio comparison unavailable"
    proc = subprocess.run(  # nosec B603 — fixed argument list, no shell
        [ffmpeg, "-v", "error", "-i", path, "-map", f"0:a:{audio_index}", "-vn", "-f", "md5", "-"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        return None, None
    value = proc.stdout.strip()
    return (value or None), None


def audio_preservation_check(source_path: str, candidate_path: str, intent: dict[str, Any]) -> CheckResult:
    """Hard constraint when policy says retain: every mapped audio track matches.

    Production-sound containers often carry multiple audio tracks. Tracks are
    mapped explicitly by index and compared per track. A track with no
    counterpart (unmapped) cannot be verified and is disclosed as a missing
    sub-check — never silently passed.
    """
    policy_mode = intent["audio_policy"]["mode"]
    frame_range = intent["frame_range"]
    if policy_mode in ("replace", "mute"):
        return CheckResult(
            CHECK_AUDIO_PRESERVATION,
            "pass",
            detail=f"audio_policy={policy_mode}: source retention not required",
        )

    src_count, src_gap = _audio_stream_count(source_path)
    cand_count, cand_gap = _audio_stream_count(candidate_path)
    tool_gap = src_gap or cand_gap
    if tool_gap:
        return CheckResult(CHECK_AUDIO_PRESERVATION, "unavailable", detail=tool_gap)
    if src_count is None or cand_count is None:
        return CheckResult(
            CHECK_AUDIO_PRESERVATION, "unavailable",
            detail="audio stream count could not be determined",
        )
    if not src_count:
        return CheckResult(
            CHECK_AUDIO_PRESERVATION,
            "unavailable",
            detail="source has no audio stream; retention cannot be verified",
        )

    findings: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    compared = 0
    mismatched = 0
    # Map source track i -> candidate track i explicitly and compare per track.
    for i in range(src_count):
        if i >= cand_count:
            # Source audio track dropped by the candidate: under a retain policy
            # this is a hard retention violation, not merely an unmapped gap.
            findings.append(_finding(
                f"ap-{i + 1}", "audio_policy", "hard", "decoded_audio_md5", frame_range,
                "blocking", "low",
                f"candidate dropped source audio track {i} but audio_policy={policy_mode}",
            ))
            mismatched += 1
            continue
        s_md5, s_gap = _decoded_audio_md5_at(source_path, i)
        c_md5, c_gap = _decoded_audio_md5_at(candidate_path, i)
        gap = s_gap or c_gap
        if gap:
            missing.append({"check": f"{CHECK_AUDIO_PRESERVATION}[track {i}]", "reason": gap})
            continue
        if s_md5 is None:
            missing.append({
                "check": f"{CHECK_AUDIO_PRESERVATION}[track {i}]",
                "reason": "source track has no decodable audio; retention cannot be verified",
            })
            continue
        if c_md5 is None:
            findings.append(_finding(
                f"ap-{i + 1}", "audio_policy", "hard", "decoded_audio_md5", frame_range,
                "blocking", "low",
                f"candidate audio track {i} missing but audio_policy={policy_mode}",
            ))
            mismatched += 1
            continue
        compared += 1
        if c_md5 != s_md5:
            findings.append(_finding(
                f"ap-{i + 1}", "audio_policy", "hard", "decoded_audio_md5", frame_range,
                "blocking", "low",
                f"decoded audio track {i} differs (source={s_md5[:12]}… candidate={c_md5[:12]}…) "
                f"but audio_policy={policy_mode}",
            ))
            mismatched += 1
    # Candidate tracks beyond the source count are unmapped additions.
    for i in range(src_count, cand_count):
        missing.append({
            "check": f"{CHECK_AUDIO_PRESERVATION}[track {i}]",
            "reason": f"candidate audio track {i} has no source counterpart (unmapped addition); not compared",
        })

    if mismatched:
        detail = f"{mismatched} of {src_count} audio track(s) violated retention"
    else:
        detail = f"decoded audio identical on {compared} mapped track(s)"
    if missing:
        detail += f"; {len(missing)} track(s) unmapped or unverified"
    if mismatched:
        return CheckResult(CHECK_AUDIO_PRESERVATION, "fail", findings, detail=detail, missing=missing)
    if compared == 0:
        return CheckResult(
            CHECK_AUDIO_PRESERVATION, "unavailable",
            detail="no source audio track could be compared", missing=missing,
        )
    return CheckResult(CHECK_AUDIO_PRESERVATION, "pass", detail=detail, missing=missing)


REGION_PSNR_THRESHOLD = 30.0  # provisional default; frozen only after dev-set calibration


def _region_psnr(
    source_path: str, candidate_path: str, box: dict[str, Any]
) -> tuple[list[tuple[int, float]], str | None]:
    """Per-frame PSNR of the registered region crop. Returns (frames, error).

    Frames are (frame_index, psnr_db) pairs over the compared range; psnr is
    inf where the crop is bit-identical. An error means the comparison did not
    run — callers must report that as unavailable, never as passed.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return [], "ffmpeg not installed; registered region comparison unavailable"
    crop = f"crop={int(box['width'])}:{int(box['height'])}:{int(box['x'])}:{int(box['y'])}"
    filter_complex = f"[0:v]{crop},format=gray[a];[1:v]{crop},format=gray[b];[a][b]psnr=stats_file=-"
    try:
        proc = subprocess.run(  # nosec B603 — fixed argument list, no shell
            [ffmpeg, "-v", "error", "-i", source_path, "-i", candidate_path,
             "-filter_complex", filter_complex, "-f", "null", "-"],
            capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return [], "psnr comparison timed out"
    if proc.returncode != 0:
        return [], f"psnr comparison failed: {proc.stderr.strip()[:200]}"
    frames: list[tuple[int, float]] = []
    for line in proc.stdout.splitlines():
        match = re.match(r"\s*n:\s*(\d+)\s+.*?psnr_avg:\s*([0-9.]+|inf)", line)
        if match:
            value = float("inf") if match.group(2) == "inf" else float(match.group(2))
            # psnr stats n: is 1-based; frame indices in findings are 0-based
            frames.append((int(match.group(1)) - 1, value))
    return frames, None


def _frame_ranges(indices: list[int]) -> list[dict[str, int]]:
    """Group contiguous frame indices into [start, end_exclusive) ranges."""
    ranges: list[dict[str, int]] = []
    for n in sorted(set(indices)):
        if ranges and n == ranges[-1]["end_exclusive"]:
            ranges[-1]["end_exclusive"] = n + 1
        else:
            ranges.append({"start": n, "end_exclusive": n + 1})
    return ranges


def protected_region_check(source_path: str, candidate_path: str, intent: dict[str, Any]) -> CheckResult:
    """Registered region comparison over protected content.

    Uses per-frame PSNR on the region crop and localizes degraded frames to
    ranges. The threshold is a provisional default (REGION_PSNR_THRESHOLD) and
    findings carry that uncertainty: they are review signals routed to a human,
    not verdicts on the performance or meaning.
    """
    region = None
    region_kind = None
    constraint_kind = "protected_content"
    for item in intent.get("protected_content", []):
        candidate_region = item.get("region") or {}
        if candidate_region.get("kind") == "bbox_per_frame" and all(
            isinstance(candidate_region.get(k), (int, float)) for k in ("x", "y", "width", "height")
        ):
            region = candidate_region
            region_kind = "bbox_per_frame"
            constraint_kind = f"protected_content[{item.get('kind', 'region')}]"
            break
        if candidate_region.get("kind") == "mask_sequence" and region is None:
            region = candidate_region
            region_kind = "mask_sequence"
            constraint_kind = f"protected_content[{item.get('kind', 'region')}]"
    if region is None:
        return CheckResult(
            CHECK_PROTECTED_REGION,
            "unavailable",
            detail="protected region has no machine-readable x/y/width/height; comparison not run",
        )

    if region_kind == "mask_sequence":
        # Per-frame mask sequence referenced by digest. Masked comparison runs only
        # against a present, digest-verified mask asset; until then we report
        # unavailable rather than a hollow pass.
        from .store import sha256_file

        mask_path = region.get("path")
        recorded_digest = region.get("digest")
        if not mask_path:
            detail = "mask_sequence region has no mask asset path; masked comparison not run"
        elif not Path(mask_path).is_file():
            detail = (
                "mask_sequence mask asset not present; masked comparison not run "
                "(falls back to unavailable until the per-frame mask asset is supplied)"
            )
        else:
            actual = sha256_file(mask_path)
            if recorded_digest and actual != recorded_digest:
                detail = (
                    f"mask_sequence mask asset digest mismatch (recorded {recorded_digest}, "
                    f"actual {actual}); masked comparison not run"
                )
            else:
                detail = (
                    "mask_sequence mask asset present but per-frame masked comparison is not "
                    "yet validated on a real mask set; reporting unavailable rather than a hollow pass"
                )
        return CheckResult(CHECK_PROTECTED_REGION, "unavailable", detail=detail)

    frames, error = _region_psnr(source_path, candidate_path, region)
    if error:
        return CheckResult(CHECK_PROTECTED_REGION, "unavailable", detail=error)
    if not frames:
        return CheckResult(
            CHECK_PROTECTED_REGION, "unavailable", detail="no comparable frames in the region crop"
        )

    degraded = [n for n, psnr in frames if psnr < REGION_PSNR_THRESHOLD]
    minimum = min((p for _, p in frames if p != float("inf")), default=float("inf"))
    detail = (
        f"region PSNR min={minimum if minimum != float('inf') else 'inf'} dB "
        f"over {len(frames)} compared frames; provisional threshold {REGION_PSNR_THRESHOLD} dB"
    )
    if not degraded:
        return CheckResult(CHECK_PROTECTED_REGION, "pass", detail=detail)

    findings = [
        _finding(
            f"pr-{i + 1}",
            constraint_kind,
            "review_signal",
            "psnr_registered_region",
            frame_range,
            "review",
            "medium",
            (
                f"protected region degraded in frames "
                f"{frame_range['start']}–{frame_range['end_exclusive'] - 1} "
                f"(provisional threshold {REGION_PSNR_THRESHOLD} dB; not yet calibrated on a dev set)"
            ),
            affected_region={"kind": "bbox_per_frame", **{k: region[k] for k in ("x", "y", "width", "height")}},
        )
        for i, frame_range in enumerate(_frame_ranges(degraded))
    ]
    return CheckResult(CHECK_PROTECTED_REGION, "fail", findings, detail=detail)


def _edit_region_box(intent: dict[str, Any]) -> dict[str, Any] | None:
    """The allowed edit region as a machine-readable bbox, or None if it has none."""
    region = intent.get("allowed_edit_region") or {}
    if region.get("kind") == "bbox_per_frame" and all(
        isinstance(region.get(k), (int, float)) for k in ("x", "y", "width", "height")
    ):
        return region
    return None


def _consecutive_psnr(
    path: str, box: dict[str, Any] | None
) -> tuple[list[tuple[int, float]], str | None]:
    """Per-consecutive-frame-pair PSNR of a clip. Returns (pairs, error).

    pairs are (n, psnr_db) where output n compares frame n vs frame n+1 (psnr is
    inf when a pair is bit-identical). When a box is given, that region is masked
    to black in both sides so only the preserved content drives the comparison
    (the allowed edit region is excluded). An error means the comparison did not
    run — callers must report that as unavailable, never as passed.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return [], "ffmpeg not installed; frame-duplicate comparison unavailable"
    if box is not None:
        mask = (
            f"drawbox=x={int(box['x'])}:y={int(box['y'])}"
            f":w={int(box['width'])}:h={int(box['height'])}:color=black:t=fill"
        )
        filter_complex = (
            f"[0:v]split[a][b];[a]{mask}[m];"
            f"[b]trim=start_frame=1,setpts=PTS-STARTPTS,{mask}[n];"
            "[m][n]psnr=stats_file=-"
        )
    else:
        filter_complex = (
            "[0:v]split[a][b];[b]trim=start_frame=1,setpts=PTS-STARTPTS[d];"
            "[a][d]psnr=stats_file=-"
        )
    try:
        proc = subprocess.run(  # nosec B603 — fixed argument list, no shell
            [ffmpeg, "-v", "error", "-i", path, "-filter_complex", filter_complex, "-f", "null", "-"],
            capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return [], "consecutive-frame comparison timed out"
    if proc.returncode != 0:
        return [], f"consecutive-frame comparison failed: {proc.stderr.strip()[:200]}"
    pairs: list[tuple[int, float]] = []
    for line in proc.stdout.splitlines():
        match = re.match(r"\s*n:\s*(\d+)\s+.*?psnr_avg:\s*([0-9.]+|inf)", line)
        if match:
            value = float("inf") if match.group(2) == "inf" else float(match.group(2))
            pairs.append((int(match.group(1)), value))
    # The framesync comparison emits an unreliable trailing value for the one
    # unpaired frame at the clip end (observed as `inf`); discard it so it is not
    # mistaken for a duplicated frame.
    if pairs and pairs[-1][1] == float("inf"):
        pairs.pop()
    return pairs, None


DUPLICATE_PSNR_THRESHOLD = 55.0  # provisional: re-encoded repeats measure ~71 dB vs ~46 dB for distinct frames


def frame_duplicate_check(source_path: str, candidate_path: str, intent: dict[str, Any]) -> CheckResult:
    """Detect duplicated (near-identical consecutive) frames in the candidate.

    Compares consecutive decoded frames with the allowed edit region excluded,
    and localizes suspected repeats to frame ranges as REVIEW SIGNALS routed to a
    human. The threshold is provisional (DUPLICATE_PSNR_THRESHOLD) and findings
    carry that uncertainty: near-identical consecutive frames can also be a
    legitimate static hold, so this is evidence for review — not a verdict. This
    check analyzes the candidate alone (a candidate that inserts a repeat shifts
    frame alignment, so an index-aligned source comparison would be unreliable).
    """
    box = _edit_region_box(intent)
    pairs, error = _consecutive_psnr(candidate_path, box)
    if error:
        return CheckResult(CHECK_FRAME_DUPLICATE, "unavailable", detail=error)
    if not pairs:
        return CheckResult(
            CHECK_FRAME_DUPLICATE, "unavailable", detail="fewer than two comparable candidate frames"
        )

    exclusion = "allowed edit region excluded" if box else "full frame (allowed edit region had no machine-readable bbox)"
    duplicate_ns = [n for n, psnr in pairs if psnr == float("inf") or psnr >= DUPLICATE_PSNR_THRESHOLD]
    if not duplicate_ns:
        return CheckResult(
            CHECK_FRAME_DUPLICATE, "pass",
            detail=f"no consecutive near-identical candidate frames; {exclusion}",
        )

    findings = [
        _finding(
            f"fd-{i + 1}",
            "temporal_integrity",
            "review_signal",
            "consecutive_frame_psnr",
            {"start": group["start"], "end_exclusive": group["end_exclusive"] + 1},
            "review",
            "medium",
            (
                f"consecutive candidate frames {group['start']}–{group['end_exclusive']} are near-identical "
                f"(possible duplicated/held frame; provisional threshold {DUPLICATE_PSNR_THRESHOLD} dB, "
                f"{exclusion}; may be a legitimate static hold — human review required)"
            ),
        )
        for i, group in enumerate(_frame_ranges(duplicate_ns))
    ]
    detail = (
        f"{len(duplicate_ns)} near-identical consecutive frame pair(s) in the candidate; "
        f"provisional threshold {DUPLICATE_PSNR_THRESHOLD} dB; {exclusion}"
    )
    return CheckResult(CHECK_FRAME_DUPLICATE, "fail", findings, detail=detail)


def run_checks(
    source_path: str,
    candidate_path: str,
    intent: dict[str, Any],
) -> dict[str, Any]:
    """Run the deterministic suite and shape it for the review report.

    Returns {"checks_run": [...], "findings": [...], "missing_checks": [...]}.
    """
    results = [
        media_integrity_check(source_path, candidate_path, intent),
        audio_preservation_check(source_path, candidate_path, intent),
        protected_region_check(source_path, candidate_path, intent),
        frame_duplicate_check(source_path, candidate_path, intent),
    ]
    checks_run: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    missing_checks: list[dict[str, Any]] = []
    for result in results:
        if result.outcome == "unavailable":
            missing_checks.append(
                {"check": result.check, "reason": result.detail or "check did not run"}
            )
        else:
            entry: dict[str, Any] = {"check": result.check, "outcome": result.outcome}
            if result.detail:
                entry["detail"] = result.detail
            checks_run.append(entry)
        missing_checks.extend(result.missing)
        findings.extend(result.findings)
    return {"checks_run": checks_run, "findings": findings, "missing_checks": missing_checks}
