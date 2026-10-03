"""Frame-duplicate detector tests (real generated media via ffmpeg)."""
from __future__ import annotations

import shutil
import subprocess  # nosec B404 — ffmpeg invoked with fixed argument lists in tests
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.checks import (  # noqa: E402
    CHECK_FRAME_DUPLICATE,
    frame_duplicate_check,
    run_checks,
)
from shotlock.fixtures import inject_duplicated_frame  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))


def make_intent(**overrides):
    record = {
        "intent_revision": 1,
        "frame_range": {"start": 0, "end_exclusive": 48},
        "frame_rate": {"numerator": 24, "denominator": 1},
        "allowed_edit_region": {"kind": "bbox_per_frame", "x": 10, "y": 10, "width": 24, "height": 24},
        "audio_policy": {"mode": "retain_source"},
    }
    record.update(overrides)
    return record


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required for frame-duplicate tests")
class FrameDuplicates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="shotlock-dup-")
        cls.ffmpeg = str(shutil.which("ffmpeg"))
        root = Path(cls.tmp)
        cls.source = root / "src.mp4"
        cls.fixture = root / "fixture.mp4"
        subprocess.run(  # nosec B603
            [cls.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
             "testsrc=duration=2:size=128x72:rate=24",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-c:a", "aac", str(cls.source)],
            check=True, timeout=120)
        rec = inject_duplicated_frame(cls.source, cls.tmp, at_frame=12)
        shutil.move(str(Path(cls.tmp) / "fixture_duplicated_frame.mp4"), cls.fixture)
        cls.at_frame = rec["parameters"]["at_frame"]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_injected_duplicate_is_detected_and_localized(self):
        result = frame_duplicate_check(str(self.source), str(self.fixture), make_intent())
        self.assertEqual(result.outcome, "fail")
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual(finding["constraint"]["class"], "review_signal")
        self.assertEqual(finding["severity"], "review")
        self.assertEqual(finding["uncertainty"]["level"], "medium")
        # localized to the injection point (allow ±1 for codec/framesync indexing)
        start = finding["frame_range"]["start"]
        self.assertLessEqual(abs(start - self.at_frame), 2)

    def test_clean_candidate_has_no_duplicate_findings(self):
        result = frame_duplicate_check(str(self.source), str(self.source), make_intent())
        self.assertEqual(result.outcome, "pass")
        self.assertEqual(result.findings, [])

    def test_edit_region_exclusion_is_disclosed(self):
        result = frame_duplicate_check(str(self.source), str(self.fixture), make_intent())
        self.assertIn("allowed edit region excluded", result.detail or "")

    def test_no_bbox_reports_full_frame_disclosure(self):
        intent = make_intent(allowed_edit_region={"kind": "bbox_per_frame"})
        result = frame_duplicate_check(str(self.source), str(self.fixture), intent)
        self.assertIn("full frame", result.detail or "")

    def test_ffmpeg_missing_degrades_honestly(self):
        with mock.patch("shotlock.checks.shutil.which", return_value=None):
            result = frame_duplicate_check(str(self.source), str(self.fixture), make_intent())
        self.assertEqual(result.outcome, "unavailable")
        self.assertIn("ffmpeg not installed", result.detail or "")
        self.assertEqual(result.findings, [])

    def test_run_checks_includes_frame_duplicate(self):
        out = run_checks(str(self.source), str(self.fixture), make_intent())
        names = {c["check"] for c in out["checks_run"]} | {m["check"] for m in out["missing_checks"]}
        self.assertIn(CHECK_FRAME_DUPLICATE, names)


if __name__ == "__main__":
    unittest.main()
