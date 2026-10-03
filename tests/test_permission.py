"""Project permission / clearance gate tests."""
from __future__ import annotations

import shutil
import subprocess  # nosec B404 — ffmpeg invoked with fixed argument lists in tests
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.permission import validate_clearance  # noqa: E402
from shotlock.pipeline import PipelineError, process_edit  # noqa: E402
from shotlock.store import EvidenceStore, sha256_file  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))


def make_intent(source_digest: str):
    return {
        "intent_revision": 1,
        "project_id": "p-test",
        "shot_id": "sh-01",
        "source_digest": source_digest,
        "frame_range": {"start": 0, "end_exclusive": 48},
        "frame_rate": {"numerator": 24, "denominator": 1},
        "requested_operation": {"verb": "remove_object", "target": "sign"},
        "allowed_edit_region": {"kind": "bbox_per_frame"},
        "allowed_consequence_region": {"kind": "bbox_per_frame", "rationale": "shadow"},
        "protected_content": [{"kind": "foreground_performance", "region": {"kind": "bbox_per_frame"}}],
        "audio_policy": {"mode": "retain_source"},
        "reference_shots": [],
        "approver": {"name": "Test Director", "approved_at": "2026-10-03T12:00:00Z"},
    }


class ClearanceValidation(unittest.TestCase):
    def test_absent_clearance_is_refused(self):
        self.assertTrue(validate_clearance(None, "sha256:" + "a" * 64, "p"))

    def test_clearance_for_other_source_is_refused(self):
        clearance = {"clearance_id": "c", "cleared_by": "x", "cleared_at": "t",
                     "source_digest": "sha256:" + "b" * 64}
        errors = validate_clearance(clearance, "sha256:" + "a" * 64, "p")
        self.assertTrue(any("never clears a different one" in e for e in errors))

    def test_clearance_for_other_project_is_refused(self):
        clearance = {"clearance_id": "c", "cleared_by": "x", "cleared_at": "t",
                     "project_id": "p-other", "source_digest": "sha256:" + "a" * 64}
        errors = validate_clearance(clearance, "sha256:" + "a" * 64, "p-test")
        self.assertTrue(any("not 'p-test'" in e for e in errors))

    def test_valid_clearance_passes(self):
        clearance = {"clearance_id": "c", "cleared_by": "x", "cleared_at": "t",
                     "project_id": "p-test", "source_digest": "sha256:" + "a" * 64}
        self.assertEqual(validate_clearance(clearance, "sha256:" + "a" * 64, "p-test"), [])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required")
class PipelinePermissionGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="shotlock-perm-")
        cls.ffmpeg = str(shutil.which("ffmpeg"))
        cls.source = Path(cls.tmp) / "src.mp4"
        cls.candidate = Path(cls.tmp) / "cand.mp4"
        subprocess.run(  # nosec B603
            [cls.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
             "testsrc=duration=2:size=128x72:rate=24",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-c:a", "aac", str(cls.source)],
            check=True, timeout=120)
        shutil.copy2(cls.source, cls.candidate)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_process_refuses_without_recorded_clearance(self):
        store = EvidenceStore(tempfile.mkdtemp(prefix="store-", dir=self.tmp))
        digest = sha256_file(self.source)
        with self.assertRaises(PipelineError) as ctx:
            process_edit(store, make_intent(digest), str(self.source), str(self.candidate))
        self.assertIn("clearance", str(ctx.exception))

    def test_process_proceeds_with_recorded_clearance(self):
        store = EvidenceStore(tempfile.mkdtemp(prefix="store-", dir=self.tmp))
        digest = sha256_file(self.source)
        store.record_clearance({
            "clearance_id": "clr-1", "project_id": "p-test", "source_digest": digest,
            "cleared_by": "Rights Holder", "cleared_at": "2026-10-03T12:00:00Z", "scope": "edit_review",
        })
        result = process_edit(store, make_intent(digest), str(self.source), str(self.candidate))
        self.assertIn("report", result)


if __name__ == "__main__":
    unittest.main()
