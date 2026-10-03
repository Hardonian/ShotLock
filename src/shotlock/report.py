"""Review-report validation: evidence discipline.

Two rules are enforced structurally here, not just documented:

- a check that did not run must not appear as passed (it belongs in
  missing_checks with a reason);
- findings are evidence: each cites a constraint, a comparison method, and a
  frame range, and high-uncertainty findings ask for review instead of
  asserting creative correctness.
"""
from __future__ import annotations

import re
from typing import Any

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

REQUIRED_REPORT_FIELDS = (
    "report_id",
    "run_id",
    "intent_revision",
    "source_digest",
    "candidate_digest",
    "generated_at",
    "findings",
    "missing_checks",
    "checks_run",
    "analysis_transforms",
)

SEVERITIES = {"blocking", "review", "informational"}
CHECK_OUTCOMES = {"pass", "fail", "unavailable"}
VERDICTS = {"actionable", "acceptable", "false_alarm"}


def validate_report(report: dict) -> list[str]:
    """Return problems with a review report. Empty list = valid."""
    if not isinstance(report, dict):
        return ["review report must be an object"]
    errors: list[str] = []
    for field in REQUIRED_REPORT_FIELDS:
        if field not in report:
            errors.append(f"missing required field: {field}")
    if errors:
        return errors

    for key in ("source_digest", "candidate_digest"):
        value = report[key]
        if not isinstance(value, str) or not DIGEST_RE.match(value):
            errors.append(f"{key} must be sha256:<64 hex>")

    if not isinstance(report["findings"], list):
        errors.append("findings must be an array")
    else:
        for i, finding in enumerate(report["findings"]):
            errors += _check_finding(i, finding)

    if not isinstance(report["missing_checks"], list):
        errors.append("missing_checks must be an array (possibly empty; never omitted)")
    else:
        for i, item in enumerate(report["missing_checks"]):
            if not isinstance(item, dict) or not item.get("check") or not item.get("reason"):
                errors.append(f"missing_checks[{i}] must name a check and a reason")

    if not isinstance(report["checks_run"], list):
        errors.append("checks_run must be an array")
    else:
        for i, item in enumerate(report["checks_run"]):
            if not isinstance(item, dict) or item.get("outcome") not in CHECK_OUTCOMES:
                errors.append(f"checks_run[{i}].outcome must be one of {sorted(CHECK_OUTCOMES)}")

    if not isinstance(report["analysis_transforms"], list):
        errors.append("analysis_transforms must be an array (all transforms are disclosed)")
    return errors


def _check_finding(index: int, finding: Any) -> list[str]:
    prefix = f"findings[{index}]"
    if not isinstance(finding, dict):
        return [f"{prefix} must be an object"]
    errors: list[str] = []
    constraint = finding.get("constraint")
    if not isinstance(constraint, dict) or not constraint.get("kind") or constraint.get("class") not in ("hard", "review_signal"):
        errors.append(f"{prefix}.constraint needs kind and class ('hard' | 'review_signal')")
    if not finding.get("comparison_method"):
        errors.append(f"{prefix}.comparison_method is required")
    fr = finding.get("frame_range")
    if not isinstance(fr, dict) or not isinstance(fr.get("start"), int) or not isinstance(fr.get("end_exclusive"), int):
        errors.append(f"{prefix}.frame_range must have integer start/end_exclusive")
    elif fr["end_exclusive"] <= fr["start"]:
        errors.append(f"{prefix}.frame_range must be non-empty")
    if finding.get("severity") not in SEVERITIES:
        errors.append(f"{prefix}.severity must be one of {sorted(SEVERITIES)}")
    uncertainty = finding.get("uncertainty")
    if not isinstance(uncertainty, dict) or uncertainty.get("level") not in ("low", "medium", "high"):
        errors.append(f"{prefix}.uncertainty.level must be low|medium|high")
    elif uncertainty["level"] == "high" and not uncertainty.get("note"):
        errors.append(f"{prefix}: high-uncertainty findings must ask for review (uncertainty.note)")
    if "reviewer_verdict" in finding and finding["reviewer_verdict"] not in VERDICTS:
        errors.append(f"{prefix}.reviewer_verdict must be one of {sorted(VERDICTS)}")
    return errors


def crosscheck_report(report: dict) -> list[str]:
    """Cross-list consistency: nothing may be both run-and-passed and missing."""
    errors: list[str] = []
    run_names = {
        item.get("check")
        for item in report.get("checks_run", [])
        if isinstance(item, dict)
    }
    missing_names = {
        item.get("check")
        for item in report.get("missing_checks", [])
        if isinstance(item, dict)
    }
    for name in sorted(run_names & missing_names):
        errors.append(
            f"check {name!r} appears in both checks_run and missing_checks; "
            "a check that did not run must not appear as passed"
        )
    return errors
