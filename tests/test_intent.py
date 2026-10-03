import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.intent import (  # noqa: E402
    assert_new_run_id,
    approval_covers,
    validate_intent,
    validate_run_record,
)

DIGEST = "sha256:" + "a" * 64
OTHER_DIGEST = "sha256:" + "b" * 64


def make_intent(**overrides):
    record = {
        "intent_revision": 1,
        "project_id": "p1",
        "shot_id": "sh-03",
        "source_digest": DIGEST,
        "frame_range": {"start": 0, "end_exclusive": 240},
        "frame_rate": {"numerator": 24000, "denominator": 1001},
        "requested_operation": {"verb": "remove_object", "target": "background sign"},
        "allowed_edit_region": {"kind": "bbox_per_frame", "path": "masks/sign.bin"},
        "allowed_consequence_region": {"kind": "bbox_per_frame", "rationale": "shadow of the removed sign"},
        "protected_content": [{"kind": "foreground_performance", "region": {"kind": "bbox_per_frame"}}],
        "audio_policy": {"mode": "retain_source"},
        "reference_shots": ["sh-02", "sh-04"],
        "approver": {"name": "Director Name", "approved_at": "2026-10-02T15:00:00Z"},
    }
    record.update(overrides)
    return record


class ValidateIntent(unittest.TestCase):
    def test_valid_record_passes(self):
        self.assertEqual(validate_intent(make_intent()), [])

    def test_missing_fields_are_reported(self):
        errors = validate_intent({"project_id": "p1"})
        self.assertTrue(any("missing required field: approver" in e for e in errors))

    def test_bad_digest_rejected(self):
        errors = validate_intent(make_intent(source_digest="not-a-digest"))
        self.assertTrue(any("source_digest" in e for e in errors))

    def test_empty_frame_range_rejected(self):
        errors = validate_intent(make_intent(frame_range={"start": 5, "end_exclusive": 5}))
        self.assertTrue(any("greater than start" in e for e in errors))

    def test_rational_frame_rate_required(self):
        errors = validate_intent(make_intent(frame_rate={"numerator": 24, "denominator": 0}))
        self.assertTrue(any("frame_rate.denominator" in e for e in errors))

    def test_unknown_audio_mode_rejected(self):
        errors = validate_intent(make_intent(audio_policy={"mode": "whatever"}))
        self.assertTrue(any("audio_policy.mode" in e for e in errors))

    def test_approver_is_mandatory(self):
        errors = validate_intent(make_intent(approver={}))
        self.assertTrue(any("approval is a human act" in e for e in errors))


class ApprovalBinding(unittest.TestCase):
    def test_binds_exact_digest(self):
        record = make_intent()
        self.assertTrue(approval_covers(record, DIGEST))
        self.assertFalse(approval_covers(record, OTHER_DIGEST))

    def test_binds_operation(self):
        record = make_intent()
        self.assertTrue(approval_covers(record, DIGEST, requested_operation=record["requested_operation"]))
        self.assertFalse(
            approval_covers(record, DIGEST, requested_operation={"verb": "remove_object", "target": "a different object"})
        )

    def test_no_approver_no_coverage(self):
        record = make_intent()
        del record["approver"]
        self.assertFalse(approval_covers(record, DIGEST))


def make_run(**overrides):
    run = {
        "run_id": "01HQRUNEXAMPLE0001",
        "intent_revision": 1,
        "project_id": "p1",
        "shot_id": "sh-03",
        "source_digest": DIGEST,
        "mode": "inference",
        "started_at": "2026-10-02T15:01:00Z",
        "finished_at": "2026-10-02T15:02:00Z",
        "exit_state": "completed",
        "configuration": {
            "backend": {"name": "void", "model_identifier": "void-demo"},
            "seed": 7,
            "preprocessing_transforms": [{"kind": "scale", "parameters": {"width": 1280}}],
        },
        "output_digest": OTHER_DIGEST,
        "analysis_transforms": [{"kind": "analysis_proxy"}],
    }
    run.update(overrides)
    return run


class ValidateRunRecord(unittest.TestCase):
    def test_valid_run_passes(self):
        self.assertEqual(validate_run_record(make_run()), [])

    def test_completed_run_requires_output_digest(self):
        errors = validate_run_record(make_run(output_digest=None))
        self.assertTrue(any("completed runs must carry output_digest" in e for e in errors))

    def test_failed_run_claims_no_output(self):
        errors = validate_run_record(make_run(exit_state="failed", output_digest=OTHER_DIGEST))
        self.assertTrue(any("must be null" in e for e in errors))

    def test_retry_cannot_overwrite_evidence(self):
        with self.assertRaises(ValueError):
            assert_new_run_id(["01HQRUNEXAMPLE0001"], "01HQRUNEXAMPLE0001")
        assert_new_run_id(["01HQRUNEXAMPLE0001"], "01HQRUNEXAMPLE0002")  # no raise


if __name__ == "__main__":
    unittest.main()
