"""Multi-track audio mapping tests (per-track comparison + unmapped disclosure)."""
from __future__ import annotations

import shutil
import subprocess  # nosec B404 — ffmpeg invoked with fixed argument lists in tests
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.checks import audio_preservation_check  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))


def make_intent(mode="retain_source"):
    return {
        "frame_range": {"start": 0, "end_exclusive": 48},
        "audio_policy": {"mode": mode},
    }


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required")
class MultiTrackAudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="shotlock-attrack-")
        cls.ffmpeg = str(shutil.which("ffmpeg"))
        root = Path(cls.tmp)
        cls.src2 = root / "src2.mp4"       # 2 audio tracks
        cls.src1 = root / "src1.mp4"       # 1 audio track
        cls.cand_same = root / "same.mp4"  # 2 identical tracks
        cls.cand1 = root / "cand1.mp4"     # 1 track (drops track 2)
        cls.cand2extra = root / "extra.mp4"  # 2 tracks (src1 + added track)

        def build(dest, audio_freqs):
            args = [cls.ffmpeg, "-v", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc=duration=2:size=128x72:rate=24"]
            for freq in audio_freqs:
                args += ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration=2"]
            args += ["-map", "0:v"]
            for i in range(len(audio_freqs)):
                args += ["-map", f"{i + 1}:a"]
            args += ["-c:v", "libx264", "-c:a", "aac", str(dest)]
            subprocess.run(args, check=True, timeout=120)  # nosec B603

        build(cls.src2, [440, 880])
        build(cls.src1, [440])
        shutil.copy2(cls.src2, cls.cand_same)
        build(cls.cand1, [440])
        build(cls.cand2extra, [440, 660])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_mapped_tracks_compare_per_track(self):
        result = audio_preservation_check(str(self.src2), str(self.cand_same), make_intent())
        self.assertEqual(result.outcome, "pass")
        self.assertIn("2 mapped track(s)", result.detail or "")
        self.assertEqual(result.missing, [])

    def test_dropped_source_track_is_hard_violation(self):
        result = audio_preservation_check(str(self.src2), str(self.cand1), make_intent())
        self.assertEqual(result.outcome, "fail")
        hard = [f for f in result.findings if f["constraint"]["class"] == "hard"]
        self.assertTrue(any("dropped source audio track 1" in f["uncertainty"]["note"] for f in hard))

    def test_unmapped_candidate_track_is_disclosed_as_missing(self):
        result = audio_preservation_check(str(self.src1), str(self.cand2extra), make_intent())
        self.assertEqual(result.outcome, "pass")
        self.assertTrue(any("track 1" in m["check"] for m in result.missing))
        self.assertIn("unmapped", result.detail or "")

    def test_replace_policy_skips_retention(self):
        result = audio_preservation_check(str(self.src2), str(self.cand1), make_intent("replace"))
        self.assertEqual(result.outcome, "pass")


if __name__ == "__main__":
    unittest.main()
