"""Region-kind handling tests (mask_sequence fallback)."""
from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.checks import protected_region_check  # noqa: E402

DIGEST = "sha256:" + "a" * 64


def make_intent(region):
    return {
        "frame_range": {"start": 0, "end_exclusive": 48},
        "protected_content": [{"kind": "prop_position", "region": region}],
    }


class MaskSequenceRegions(unittest.TestCase):
    def test_mask_sequence_without_path_is_unavailable(self):
        result = protected_region_check("s.mp4", "c.mp4", make_intent({"kind": "mask_sequence"}))
        self.assertEqual(result.outcome, "unavailable")
        self.assertIn("no mask asset path", result.detail or "")

    def test_mask_sequence_asset_absent_falls_back(self):
        result = protected_region_check(
            "s.mp4", "c.mp4", make_intent({"kind": "mask_sequence", "path": "/nonexistent/mask.png"})
        )
        self.assertEqual(result.outcome, "unavailable")
        self.assertIn("not present", result.detail or "")
        self.assertEqual(result.findings, [])

    def test_mask_sequence_digest_mismatch_is_unavailable(self):
        tmp = Path(tempfile.mkdtemp(prefix="shotlock-mask-"))
        mask = tmp / "mask.png"
        mask.write_bytes(b"mask-bytes")
        region = {"kind": "mask_sequence", "path": str(mask), "digest": DIGEST}
        result = protected_region_check("s.mp4", "c.mp4", make_intent(region))
        self.assertEqual(result.outcome, "unavailable")
        self.assertIn("digest mismatch", result.detail or "")

    def test_mask_sequence_present_still_unavailable_until_validated(self):
        tmp = Path(tempfile.mkdtemp(prefix="shotlock-mask-"))
        mask = tmp / "mask.png"
        mask.write_bytes(b"mask-bytes")
        actual = "sha256:" + hashlib.sha256(b"mask-bytes").hexdigest()
        region = {"kind": "mask_sequence", "path": str(mask), "digest": actual}
        result = protected_region_check("s.mp4", "c.mp4", make_intent(region))
        self.assertEqual(result.outcome, "unavailable")
        self.assertIn("not", result.detail or "")

    def test_bbox_region_still_runs_psnr_path(self):
        # a bbox region is unaffected by the mask_sequence work
        region = {"kind": "bbox_per_frame", "x": 10, "y": 10, "width": 24, "height": 24}
        result = protected_region_check("s.mp4", "c.mp4", make_intent(region))
        # ffmpeg is present in this environment, but s.mp4/c.mp4 are not real
        # media here — the point is that it does not take the mask_sequence branch
        self.assertNotIn("mask", (result.detail or "").lower())


if __name__ == "__main__":
    unittest.main()
