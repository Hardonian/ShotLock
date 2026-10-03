"""Synchronized viewer generation tests."""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.export import export_package  # noqa: E402
from shotlock.viewer import generate_viewer  # noqa: E402

DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64

REPORT = {
    "report_id": "rep-view1",
    "run_id": "01HQRUNEXAMPLE0007",
    "intent_revision": 2,
    "source_digest": DIGEST,
    "candidate_digest": OTHER,
    "generated_at": "2026-10-03T12:00:00Z",
    "findings": [
        {
            "finding_id": "pr-1",
            "constraint": {"kind": "protected_content[prop_position]", "class": "review_signal"},
            "comparison_method": "psnr_registered_region",
            "frame_range": {"start": 12, "end_exclusive": 21},
            "severity": "review",
            "uncertainty": {"level": "medium", "note": "protected region degraded in frames 12–20"},
            "supporting_images": [],
        }
    ],
    "checks_run": [{"check": "media_integrity", "outcome": "pass"}],
    "missing_checks": [{"check": "audio_preservation", "reason": "no decodable audio stream in source or candidate"}],
    "analysis_transforms": [{"kind": "identity_comparison", "parameters": {}}],
}

INTENT = {
    "intent_revision": 2,
    "frame_rate": {"numerator": 24000, "denominator": 1001},
    "frame_range": {"start": 0, "end_exclusive": 48},
    "allowed_edit_region": {"kind": "bbox_per_frame", "x": 10, "y": 10, "width": 24, "height": 24},
}


class Viewer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shotlock-viewer-")
        self.source = Path(self.tmp) / "src.mp4"
        self.candidate = Path(self.tmp) / "cand.mp4"
        self.source.write_bytes(b"source-bytes")
        self.candidate.write_bytes(b"candidate-bytes")

    def test_viewer_page_and_media_are_written(self):
        out = Path(self.tmp) / "pkg"
        entry = generate_viewer(REPORT, INTENT, self.source, self.candidate, out)
        self.assertEqual(entry["status"], "exported")
        page = (out / "viewer.html").read_text()
        self.assertIn("viewer_source.mp4", page)
        self.assertIn("viewer_candidate.mp4", page)
        self.assertTrue((out / "viewer_source.mp4").exists())
        self.assertTrue((out / "viewer_candidate.mp4").exists())

    def test_viewer_uses_rational_frame_rate(self):
        out = Path(self.tmp) / "pkg2"
        generate_viewer(REPORT, INTENT, self.source, self.candidate, out)
        config = json.loads((out / "viewer-config.json").read_text())
        self.assertEqual(config["frame_rate"], {"numerator": 24000, "denominator": 1001})
        self.assertEqual(config["edit_region"]["bbox"], {"x": 10, "y": 10, "width": 24, "height": 24})

    def test_unknown_rate_degrades_honestly(self):
        out = Path(self.tmp) / "pkg3"
        intent = dict(INTENT, frame_rate={})
        generate_viewer(REPORT, intent, self.source, self.candidate, out)
        config = json.loads((out / "viewer-config.json").read_text())
        self.assertEqual(config["frame_rate"], {"numerator": None, "denominator": None})
        page = (out / "viewer.html").read_text()
        self.assertIn("rate unknown", page)

    def test_missing_checks_banner_present(self):
        out = Path(self.tmp) / "pkg4"
        generate_viewer(REPORT, INTENT, self.source, self.candidate, out)
        page = (out / "viewer.html").read_text()
        self.assertIn("did NOT run", page)

    def test_export_includes_viewer_when_source_and_intent_given(self):
        out = Path(self.tmp) / "pkg5"
        manifest = export_package(
            REPORT, str(self.candidate), out, source_path=str(self.source), intent=INTENT
        )
        self.assertEqual(manifest["viewer"]["status"], "exported")
        self.assertTrue((out / "viewer.html").exists())

    def test_export_degrades_without_source(self):
        out = Path(self.tmp) / "pkg6"
        manifest = export_package(REPORT, str(self.candidate), out)
        self.assertEqual(manifest["viewer"]["status"], "unavailable")
        self.assertIn("source_path and intent", manifest["viewer"]["reason"])


if __name__ == "__main__":
    unittest.main()
