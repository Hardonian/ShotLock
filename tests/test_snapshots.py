"""Finding-snapshot extraction tests (real generated media via ffmpeg)."""
from __future__ import annotations

import shutil
import subprocess  # nosec B404 — ffmpeg invoked with fixed argument lists in tests
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.export import export_package  # noqa: E402
from shotlock.snapshots import attach_finding_snapshots  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))
DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64

REPORT = {
    "report_id": "rep-snap1",
    "run_id": "01HQRUNEXAMPLE0009",
    "intent_revision": 1,
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
        },
        {
            "finding_id": "pr-noframes",
            "constraint": {"kind": "protected_content[other]", "class": "review_signal"},
            "comparison_method": "psnr_registered_region",
            "frame_range": {"start": 0, "end_exclusive": 0},
            "severity": "review",
            "uncertainty": {"level": "medium", "note": "degenerate range"},
            "supporting_images": [],
        },
    ],
    "checks_run": [{"check": "media_integrity", "outcome": "pass"}],
    "missing_checks": [{"check": "audio_preservation", "reason": "no decodable audio stream"}],
    "analysis_transforms": [{"kind": "identity_comparison", "parameters": {}}],
}


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required for snapshot tests")
class FindingSnapshots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="shotlock-snap-")
        cls.ffmpeg = str(shutil.which("ffmpeg"))
        root = Path(cls.tmp)
        cls.source = root / "src.mp4"
        cls.candidate = root / "cand.mp4"
        subprocess.run(  # nosec B603
            [cls.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
             "testsrc=duration=2:size=128x72:rate=24",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-c:a", "aac", str(cls.source)],
            check=True, timeout=120)
        subprocess.run(  # nosec B603
            [cls.ffmpeg, "-v", "error", "-y", "-i", str(cls.source),
             "-vf", "drawbox=x=10:y=10:w=24:h=24:color=red@1:t=fill:enable='between(n\\,12\\,20)'",
             "-c:v", "libx264", "-c:a", "copy", str(cls.candidate)],
            check=True, timeout=120)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _fresh_report(self):
        import copy
        return copy.deepcopy(REPORT)

    def test_snapshot_generated_and_linked(self):
        report = self._fresh_report()
        out = Path(self.tmp) / "pkg-gen"
        entry = attach_finding_snapshots(report, self.source, self.candidate, out)
        self.assertIn(entry["status"], ("exported", "partial"))
        self.assertEqual(entry["generated"], 1)
        finding = report["findings"][0]
        self.assertEqual(finding["supporting_images"], ["snapshots/pr-1.png"])
        self.assertEqual(finding["inspect_path"], "snapshots/pr-1.png")
        png = out / "snapshots" / "pr-1.png"
        self.assertTrue(png.is_file())
        self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_degenerate_frame_range_yields_no_snapshot_but_no_crash(self):
        report = self._fresh_report()
        out = Path(self.tmp) / "pkg-noframes"
        entry = attach_finding_snapshots(report, self.source, self.candidate, out)
        # the degenerate-range finding gets no image and is disclosed as a gap
        self.assertEqual(report["findings"][1]["supporting_images"], [])
        self.assertTrue(entry.get("gaps"))
        self.assertEqual(entry["generated"], 1)

    def test_ffmpeg_missing_degrades_honestly(self):
        report = self._fresh_report()
        out = Path(self.tmp) / "pkg-noff"
        with mock.patch("shotlock.snapshots._ffmpeg", return_value=None):
            entry = attach_finding_snapshots(report, self.source, self.candidate, out)
        self.assertEqual(entry["status"], "unavailable")
        self.assertEqual(entry["generated"], 0)
        for finding in report["findings"]:
            self.assertEqual(finding["supporting_images"], [])

    def test_export_package_writes_snapshots_and_links_html(self):
        report = self._fresh_report()
        out = Path(self.tmp) / "pkg-export"
        manifest = export_package(
            report, str(self.candidate), out, source_path=str(self.source), intent={}
        )
        self.assertIn(manifest["snapshots"]["status"], ("exported", "partial"))
        self.assertTrue((out / "snapshots" / "pr-1.png").is_file())
        page = (out / "report.html").read_text()
        self.assertIn("snapshots/pr-1.png", page)
        # findings.json carries the links too
        self.assertIn("snapshots/pr-1.png", (out / "findings.json").read_text())

    def test_export_without_source_reports_snapshots_unavailable(self):
        report = self._fresh_report()
        out = Path(self.tmp) / "pkg-nosrc"
        manifest = export_package(report, str(self.candidate), out)
        self.assertEqual(manifest["snapshots"]["status"], "unavailable")
        self.assertIn("source_path", manifest["snapshots"]["reason"])


if __name__ == "__main__":
    unittest.main()
