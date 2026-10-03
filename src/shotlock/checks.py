"""Deterministic preservation checks.

Every check returns an explicit outcome: "pass", "fail", or "unavailable".
A check that did not run goes to missing_checks with a reason — it must never
appear as passed. Hard failures block acceptance; review signals route to a
human; nothing here claims creative correctness.

Findings follow schemas/review-report.schema.json exactly: constraint,
comparison method, frame range, severity, uncertainty.
"""
from __future__ import annotations

import shutil
import subprocess  # nosec B404 — ffmpeg invoked with fixed argument lists, never a shell
from dataclasses import dataclass, field
from typing import Any

from .media import UNAVAILABLE, FfprobeMissing, compare_integrity, inspect_media

CHECK_MEDIA_INTEGRITY = "media_integrity"
CHECK_AUDIO_PRESERVATION = "audio_preservation"
CHECK_PROTECTED_REGION = "protected_region_stability"

WEEK2_REASON = "not implemented yet (week 2 deliverable: protected-region checks)"


@dataclass
class CheckResult:
    check: str
    outcome: str  # "pass" | "fail" | "unavailable"
    findings: list[dict[str, Any]] = field(default_factory=list)
    detail: str | None = None


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


def _decoded_audio_md5(path: str) -> tuple[str | None, str | None]:
    """MD5 of the decoded first audio stream (content comparison, not container
    hash: container bytes can differ while audio is equivalent).

    Returns (md5, unavailable_reason). (None, None) means the file genuinely
    has no decodable audio stream — a real absence, not a tooling gap.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None, "ffmpeg not installed; decoded-audio comparison unavailable"
    proc = subprocess.run(  # nosec B603 — fixed argument list, no shell
        [ffmpeg, "-v", "error", "-i", path, "-map", "0:a:0", "-vn", "-f", "md5", "-"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        return None, None
    value = proc.stdout.strip()
    return (value or None), None


def audio_preservation_check(source_path: str, candidate_path: str, intent: dict[str, Any]) -> CheckResult:
    """Hard constraint when policy says retain: decoded audio must match."""
    policy_mode = intent["audio_policy"]["mode"]
    frame_range = intent["frame_range"]
    if policy_mode in ("replace", "mute"):
        return CheckResult(
            CHECK_AUDIO_PRESERVATION,
            "pass",
            detail=f"audio_policy={policy_mode}: source retention not required",
        )

    source_md5, source_gap = _decoded_audio_md5(source_path)
    candidate_md5, candidate_gap = _decoded_audio_md5(candidate_path)

    tool_gap = source_gap or candidate_gap
    if tool_gap:
        return CheckResult(CHECK_AUDIO_PRESERVATION, "unavailable", detail=tool_gap)

    if source_md5 is None and candidate_md5 is None:
        return CheckResult(
            CHECK_AUDIO_PRESERVATION,
            "unavailable",
            detail="no decodable audio stream in source or candidate",
        )
    if source_md5 is None:
        return CheckResult(
            CHECK_AUDIO_PRESERVATION,
            "unavailable",
            detail="source has no decodable audio stream; retention cannot be verified",
        )

    if candidate_md5 is None:
        finding = _finding(
            "ap-1",
            "audio_policy",
            "hard",
            "decoded_audio_md5",
            frame_range,
            "blocking",
            "low",
            f"candidate has no decodable audio stream but audio_policy={policy_mode}",
        )
        return CheckResult(CHECK_AUDIO_PRESERVATION, "fail", [finding], detail="candidate audio missing")

    if candidate_md5 != source_md5:
        finding = _finding(
            "ap-1",
            "audio_policy",
            "hard",
            "decoded_audio_md5",
            frame_range,
            "blocking",
            "low",
            f"decoded audio differs (source={source_md5[:12]}… candidate={candidate_md5[:12]}…) but audio_policy={policy_mode}",
        )
        return CheckResult(CHECK_AUDIO_PRESERVATION, "fail", [finding], detail="decoded audio mismatch")
    return CheckResult(CHECK_AUDIO_PRESERVATION, "pass", detail="decoded audio identical")


def protected_region_check(*_args: Any, **_kwargs: Any) -> CheckResult:
    """Registered region comparison — week 2. Reported as unavailable, never
    as passed."""
    return CheckResult(CHECK_PROTECTED_REGION, "unavailable", detail=WEEK2_REASON)


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
        protected_region_check(),
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
        findings.extend(result.findings)
    return {"checks_run": checks_run, "findings": findings, "missing_checks": missing_checks}
