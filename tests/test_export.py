"""Export package tests: self-contained, honest about gaps."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.export import export_package  # noqa: E402

DIGEST = "sha256:" + "e" * 64
OTHER = "sha256:" + "f" * 64


def make_report(**overrides):
    report = {
        "report_id": "rep-test1",
        "run_id": "01HQRUNEXAMPLE0009",
        "intent_revision": 1,
        "source_digest": DIGEST,
        "candidate_digest": OTHER,
        "generated_at": "2026-10-03T12:00:00Z",
        "findings": [
            {
                "finding_id": "mi-1",
                "constraint": {"kind": "media_integrity", "class": "hard"},
                "comparison_method": "ffprobe_stream_properties",
                "frame_range": {"start": 0, "end_exclusive": 48},
                "severity": "blocking",
                "uncertainty": {"level": "low", "note": "frame_count mismatch: source=48 candidate=24"},
                "supporting_images": [],
            }
        ],
        "checks_run": [{"check": "media_integrity", "outcome": "fail", "detail": "frame_count mismatch"}],
        "missing_checks": [{"check": "protected_region_stability", "reason": "not implemented yet (week 2 deliverable: protected-region checks)"}],
        "analysis_transforms": [{"kind": "identity_comparison", "parameters": {"note": "no resampling"}}],
    }
    report.update(overrides)
    return report


class ExportPackage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shotlock-export-")
        self.candidate = Path(self.tmp) / "candidate.mp4"
        self.candidate.write_bytes(b"fake-media-bytes-for-copy")

    def test_package_is_self_contained(self):
        out = Path(self.tmp) / "pkg"
        manifest = export_package(make_report(), str(self.candidate), out)
        for name in ("report.html", "findings.json", "issues.csv", "manifest.json"):
            self.assertTrue((out / name).exists(), name)
        self.assertTrue(any(out.glob("selected_media*")))

    def test_html_discloses_missing_checks(self):
        out = Path(self.tmp) / "pkg2"
        export_package(make_report(), str(self.candidate), out)
        html_text = (out / "report.html").read_text()
        self.assertIn("did NOT run", html_text)
        self.assertIn("protected_region_stability", html_text)
        self.assertIn("identity_comparison", html_text)
        self.assertIn(DIGEST, html_text)

    def test_manifest_records_otio_status_honestly(self):
        out = Path(self.tmp) / "pkg3"
        manifest = export_package(make_report(), str(self.candidate), out)
        self.assertIn(manifest["otio_timeline"]["status"], ("exported", "unavailable"))
        if manifest["otio_timeline"]["status"] == "unavailable":
            self.assertTrue(manifest["otio_timeline"]["reason"])

    def test_csv_has_every_finding(self):
        out = Path(self.tmp) / "pkg4"
        export_package(make_report(), str(self.candidate), out)
        lines = (out / "issues.csv").read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)  # header + one finding

    def test_findings_json_round_trips(self):
        out = Path(self.tmp) / "pkg5"
        report = make_report()
        export_package(report, str(self.candidate), out)
        self.assertEqual(json.loads((out / "findings.json").read_text()), report)


if __name__ == "__main__":
    unittest.main()
