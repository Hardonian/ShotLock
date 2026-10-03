import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.report import crosscheck_report, validate_report  # noqa: E402

DIGEST = "sha256:" + "c" * 64
OTHER = "sha256:" + "d" * 64


def make_report(**overrides):
    report = {
        "report_id": "rep-0001",
        "run_id": "01HQRUNEXAMPLE0001",
        "intent_revision": 1,
        "source_digest": DIGEST,
        "candidate_digest": OTHER,
        "generated_at": "2026-10-02T15:03:00Z",
        "findings": [
            {
                "finding_id": "f1",
                "constraint": {"kind": "protected_content[prop_position]", "class": "review_signal"},
                "comparison_method": "registered_region",
                "frame_range": {"start": 100, "end_exclusive": 118},
                "severity": "review",
                "uncertainty": {"level": "medium", "note": "shadows changed near the removed object"},
                "inspect_path": "evidence/f1",
            }
        ],
        "checks_run": [
            {"check": "media_integrity", "outcome": "pass"},
            {"check": "protected_region_stability", "outcome": "fail", "detail": "see f1"},
        ],
        "missing_checks": [
            {"check": "audio_preservation", "reason": "no audio stream in the analysis proxy"}
        ],
        "analysis_transforms": [{"kind": "analysis_proxy"}],
    }
    report.update(overrides)
    return report


class ValidateReport(unittest.TestCase):
    def test_valid_report_passes(self):
        self.assertEqual(validate_report(make_report()), [])
        self.assertEqual(crosscheck_report(make_report()), [])

    def test_missing_checks_never_omitted(self):
        errors = validate_report(make_report(missing_checks=None))
        self.assertTrue(any("missing_checks must be an array" in e for e in errors))

    def test_check_cannot_be_passed_and_missing(self):
        report = make_report(
            missing_checks=[{"check": "media_integrity", "reason": "not run"}],
        )
        errors = crosscheck_report(report)
        self.assertTrue(any("must not appear as passed" in e for e in errors))

    def test_high_uncertainty_asks_for_review(self):
        report = make_report()
        report["findings"][0]["uncertainty"] = {"level": "high"}
        errors = validate_report(report)
        self.assertTrue(any("must ask for review" in e for e in errors))

    def test_findings_need_frame_ranges(self):
        report = make_report()
        del report["findings"][0]["frame_range"]
        errors = validate_report(report)
        self.assertTrue(any("frame_range" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
