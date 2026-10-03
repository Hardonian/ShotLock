"""Evaluation harness tests (scene split, threshold freezing, disagreement)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.evaluation import (  # noqa: E402
    compare_baseline,
    freeze_thresholds,
    record_reviewer_disagreement,
    run_evaluation,
    split_by_scene,
)


def clips():
    return [
        {"clip_id": "c1", "scene_id": "sA"},
        {"clip_id": "c2", "scene_id": "sA"},
        {"clip_id": "c3", "scene_id": "sB"},
        {"clip_id": "c4", "scene_id": "sC"},
        {"clip_id": "c5", "scene_id": "sD"},
    ]


class EvaluationHarness(unittest.TestCase):
    def test_split_by_scene_has_no_scene_leakage(self):
        dev, held_out = split_by_scene(clips(), dev_fraction=0.6)
        dev_scenes = {c["scene_id"] for c in dev}
        held_scenes = {c["scene_id"] for c in held_out}
        self.assertEqual(dev_scenes & held_scenes, set())
        self.assertEqual(len(dev) + len(held_out), 5)

    def test_freeze_thresholds_calibrates_on_dev(self):
        frozen = freeze_thresholds([10.0, 12.0, 14.0, 60.0])
        self.assertEqual(frozen["status"], "frozen")
        self.assertEqual(frozen["calibrated_on"], "dev")
        self.assertIsInstance(frozen["threshold"], float)

    def test_freeze_thresholds_unavailable_without_dev(self):
        self.assertEqual(freeze_thresholds([])["status"], "unavailable")

    def test_compare_baseline_reports_delta(self):
        det = [{"clip_id": "a", "flagged": True}, {"clip_id": "b", "flagged": False}]
        base = [{"clip_id": "a", "flagged": False}, {"clip_id": "b", "flagged": False}]
        entry = compare_baseline(det, base)
        self.assertEqual(entry["detector_hit_rate"], 0.5)
        self.assertEqual(entry["baseline_hit_rate"], 0.0)
        self.assertEqual(entry["delta"], 0.5)

    def test_reviewer_disagreement_is_recorded_not_resolved(self):
        reviews = [
            {"clip_id": "a", "reviewer": "r1", "verdict": "actionable"},
            {"clip_id": "a", "reviewer": "r2", "verdict": "false_alarm"},
            {"clip_id": "b", "reviewer": "r1", "verdict": "acceptable"},
            {"clip_id": "b", "reviewer": "r2", "verdict": "acceptable"},
        ]
        entry = record_reviewer_disagreement(reviews)
        self.assertEqual(entry["clips_reviewed"], 2)
        self.assertEqual(entry["disagreeing_clips"], ["a"])
        self.assertEqual(entry["agreement_rate"], 0.5)

    def test_run_evaluation_unavailable_without_cleared_set(self):
        entry = run_evaluation([])
        self.assertEqual(entry["status"], "unavailable")
        self.assertIn("cleared clip set", entry["reason"])

    def test_run_evaluation_with_clips(self):
        entry = run_evaluation(
            clips(),
            detector_signals=[30.0, 32.0],
            detector_results=[{"clip_id": "a", "flagged": True}],
            baseline_results=[{"clip_id": "a", "flagged": False}],
            reviews=[{"clip_id": "a", "reviewer": "r1", "verdict": "acceptable"}],
        )
        self.assertEqual(entry["status"], "evaluated")
        self.assertFalse(entry["scene_leakage"])
        self.assertEqual(entry["dev_clips"] + entry["held_out_clips"], 5)


if __name__ == "__main__":
    unittest.main()
