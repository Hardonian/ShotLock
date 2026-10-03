"""End-to-end pipeline tests on real generated media (ffmpeg)."""
from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 — ffmpeg invoked with fixed argument lists in tests
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.pipeline import PipelineError, check_budget, process_edit  # noqa: E402
from shotlock.report import crosscheck_report, validate_report  # noqa: E402
from shotlock.store import EvidenceStore, sha256_file  # noqa: E402

HAVE_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
DIGEST_LEN = 71  # "sha256:" + 64 hex


def make_intent(source_digest: str, **overrides):
    record = {
        "intent_revision": 1,
        "project_id": "p-test",
        "shot_id": "sh-01",
        "source_digest": source_digest,
        "frame_range": {"start": 0, "end_exclusive": 48},
        "frame_rate": {"numerator": 24, "denominator": 1},
        "requested_operation": {"verb": "remove_object", "target": "background sign"},
        "allowed_edit_region": {"kind": "bbox_per_frame"},
        "allowed_consequence_region": {"kind": "bbox_per_frame", "rationale": "shadow"},
        "protected_content": [{"kind": "foreground_performance", "region": {"kind": "bbox_per_frame"}}],
        "audio_policy": {"mode": "retain_source"},
        "reference_shots": [],
        "approver": {"name": "Test Director", "approved_at": "2026-10-03T12:00:00Z"},
    }
    record.update(overrides)
    return record


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required for pipeline tests")
class ProcessEdit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="shotlock-test-")
        cls.ffmpeg = shutil.which("ffmpeg")
        root = Path(cls.tmp)
        cls.source = root / "source.mp4"
        cls.identical = root / "identical.mp4"
        cls.shorter = root / "shorter.mp4"
        cls.muted = root / "muted.mp4"
        # 2s of test video + sine audio
        subprocess.run(  # nosec B603
            [cls.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
             "testsrc=duration=2:size=128x72:rate=24",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-c:a", "aac", str(cls.source)],
            check=True, timeout=120)
        shutil.copy2(cls.source, cls.identical)
        subprocess.run(  # nosec B603
            [cls.ffmpeg, "-v", "error", "-y", "-i", str(cls.source),
             "-t", "1", "-c", "copy", str(cls.shorter)],
            check=True, timeout=120)
        subprocess.run(  # nosec B603
            [cls.ffmpeg, "-v", "error", "-y", "-i", str(cls.source),
             "-an", "-c:v", "copy", str(cls.muted)],
            check=True, timeout=120)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        # a fresh store per test: evidence (and budget ledgers) must not leak
        self.store = EvidenceStore(tempfile.mkdtemp(prefix="store-", dir=self.tmp))
        self.digest = sha256_file(self.source)
        self.intent = make_intent(self.digest)

    def test_identical_candidate_passes_hard_checks(self):
        result = process_edit(self.store, self.intent, str(self.source), str(self.identical))
        report = result["report"]
        self.assertEqual(validate_report(report), [])
        self.assertEqual(crosscheck_report(report), [])
        hard = [f for f in report["findings"] if f["constraint"]["class"] == "hard"]
        self.assertEqual(hard, [])
        outcomes = {c["check"]: c["outcome"] for c in report["checks_run"]}
        self.assertEqual(outcomes.get("media_integrity"), "pass")
        self.assertEqual(outcomes.get("audio_preservation"), "pass")

    def test_missing_checks_disclosed_not_passed(self):
        result = process_edit(self.store, self.intent, str(self.source), str(self.identical))
        missing = {m["check"]: m["reason"] for m in result["report"]["missing_checks"]}
        self.assertIn("protected_region_stability", missing)
        self.assertIn("week 2", missing["protected_region_stability"])
        run_names = {c["check"] for c in result["report"]["checks_run"]}
        self.assertNotIn("protected_region_stability", run_names)

    def test_shorter_candidate_is_hard_failure(self):
        result = process_edit(self.store, self.intent, str(self.source), str(self.shorter))
        hard = [f for f in result["report"]["findings"] if f["constraint"]["class"] == "hard"]
        self.assertTrue(any("frame_count" in f["uncertainty"]["note"] for f in hard))

    def test_muted_candidate_violates_audio_policy(self):
        result = process_edit(self.store, self.intent, str(self.source), str(self.muted))
        hard = [f for f in result["report"]["findings"] if f["constraint"]["class"] == "hard"]
        self.assertTrue(any(f["constraint"]["kind"] == "audio_policy" for f in hard))

    def test_approval_binds_exact_source_digest(self):
        intent = make_intent("sha256:" + "0" * 64)
        with self.assertRaises(PipelineError) as ctx:
            process_edit(self.store, intent, str(self.source), str(self.identical))
        self.assertIn("approval does not cover source", str(ctx.exception))

    def test_retry_never_overwrites_evidence(self):
        process_edit(self.store, self.intent, str(self.source), str(self.identical))
        with self.assertRaises(ValueError):
            process_edit(
                self.store, self.intent, str(self.source), str(self.identical),
                run_id=self.store.run_ids()[0],
            )
        self.assertEqual(len(self.store.run_ids()), 1)

    def test_budget_ceiling_is_a_hard_stop(self):
        self.store.record_run({
            "run_id": "01HPRIORRUN00000001", "intent_revision": 1,
            "project_id": "p-test", "shot_id": "sh-01",
            "source_digest": self.digest, "mode": "imported_render",
            "started_at": "2026-10-03T12:00:00Z", "finished_at": "2026-10-03T12:00:01Z",
            "exit_state": "completed",
            "configuration": {"backend": {"name": "imported", "model_identifier": "imported"},
                              "preprocessing_transforms": []},
            "output_digest": self.digest, "analysis_transforms": [],
            "measured_cost": {"currency": "CAD", "amount": 500.0},
            "reviewer_decisions": [],
        })
        with self.assertRaises(PipelineError) as ctx:
            check_budget(self.store, ceiling_cad=500.0)
        self.assertIn("compute budget exhausted", str(ctx.exception))

    def test_records_are_valid_json(self):
        result = process_edit(self.store, self.intent, str(self.source), str(self.identical))
        stored = self.store.load_run(result["run"]["run_id"])
        self.assertEqual(stored["output_identity"], "not_claimed")
        self.assertEqual(len(stored["analysis_transforms"]), 1)


if __name__ == "__main__":
    unittest.main()
