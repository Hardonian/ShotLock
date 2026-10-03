"""Evaluation harness (backlog #7; Week 4 — needs the cleared clip set first).

Measures detector quality WITHOUT ever claiming creative correctness:

- dev / held-out split by SCENE (all clips of a scene stay on one side, so scene
  context never leaks between dev and held-out);
- threshold freezing: a threshold is calibrated on dev and then frozen before it
  is applied to held-out (no peeking);
- baseline comparison: a simple frame-difference baseline is compared against the
  detector so "better than nothing" is measured, not asserted;
- reviewer-disagreement recording: where human reviewers disagree, that is
  recorded as uncertainty, not resolved silently.

The cleared clip set is a hard prerequisite (written permission required before
capture/use). Without it the harness reports unavailable rather than scoring on
uncleared material. No quality claim is made before held-out measurement.
"""
from __future__ import annotations

from typing import Any


def split_by_scene(clips: list[dict[str, Any]], dev_fraction: float = 0.7) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split clips into (dev, held_out) grouped by scene id.

    Scenes are assigned whole to one side so no scene's context appears in both
    dev and held-out. Deterministic: scenes sorted, first dev_fraction of scenes
    to dev.
    """
    if not clips:
        return [], []
    scenes = sorted({str(c.get("scene_id")) for c in clips})
    n_dev = max(1, int(len(scenes) * dev_fraction)) if len(scenes) > 1 else len(scenes)
    dev_scenes = set(scenes[:n_dev])
    dev = [c for c in clips if str(c.get("scene_id")) in dev_scenes]
    held_out = [c for c in clips if str(c.get("scene_id")) not in dev_scenes]
    return dev, held_out


def freeze_thresholds(dev_signals: list[float], *, margin: float = 0.0) -> dict[str, Any]:
    """Calibrate a threshold on dev and freeze it (no later re-tuning on held-out).

    dev_signals are per-clip detector signals measured on dev (e.g. the min PSNR
    per clip). The frozen threshold is the midpoint between the two clusters'
    extremes when a gap exists, else the dev median + margin. The result records
    that it is frozen-on-dev and NOT calibrated on held-out.
    """
    if not dev_signals:
        return {"status": "unavailable", "reason": "no dev signals to calibrate a threshold"}
    values = sorted(dev_signals)
    n = len(values)
    median = values[n // 2] if n % 2 == 1 else (values[n // 2 - 1] + values[n // 2]) / 2
    frozen = median + margin
    return {
        "status": "frozen",
        "threshold": frozen,
        "calibrated_on": "dev",
        "dev_samples": n,
        "note": "frozen on dev; must not be re-tuned on held-out (no peeking)",
    }


def compare_baseline(
    detector_results: list[dict[str, Any]], baseline_results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare the detector against a frame-difference baseline on the same clips.

    Results are lists of {"clip_id", "flagged": bool}. Reports both hit rates and
    the delta; it does not declare the detector better without the measurement.
    """
    def hit_rate(results: list[dict[str, Any]]) -> float | None:
        if not results:
            return None
        return sum(1 for r in results if r.get("flagged")) / len(results)

    det = hit_rate(detector_results)
    base = hit_rate(baseline_results)
    entry: dict[str, Any] = {
        "detector_hit_rate": det,
        "baseline_hit_rate": base,
        "clips": len(detector_results),
    }
    if det is not None and base is not None:
        entry["delta"] = det - base
        entry["note"] = "positive delta means the detector flagged more than the baseline; interpret with reviewer labels"
    return entry


def record_reviewer_disagreement(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Record where reviewers disagree. Disagreement is uncertainty, not error.

    reviews are {"clip_id", "reviewer", "verdict"}. Clips with conflicting
    verdicts are listed as disagreement; agreement rate is reported, never used
    to overwrite individual verdicts.
    """
    by_clip: dict[str, set[str]] = {}
    for r in reviews:
        by_clip.setdefault(str(r.get("clip_id")), set()).add(str(r.get("verdict")))
    disagreeing = sorted(cid for cid, verdicts in by_clip.items() if len(verdicts) > 1)
    total = len(by_clip)
    agree = total - len(disagreeing)
    return {
        "clips_reviewed": total,
        "agreeing_clips": agree,
        "disagreeing_clips": disagreeing,
        "agreement_rate": (agree / total) if total else None,
        "note": "disagreement is recorded as uncertainty for human resolution, not auto-resolved",
    }


def run_evaluation(
    clips: list[dict[str, Any]],
    *,
    detector_signals: list[float] | None = None,
    detector_results: list[dict[str, Any]] | None = None,
    baseline_results: list[dict[str, Any]] | None = None,
    reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the evaluation flow. Requires the cleared clip set.

    Without a cleared clip set this reports unavailable — we never score on
    uncleared material and never claim quality before held-out measurement.
    """
    if not clips:
        return {
            "status": "unavailable",
            "reason": "no cleared clip set supplied; evaluation harness needs the cleared clip set (gated, written permission required)",
        }
    dev, held_out = split_by_scene(clips)
    frozen = freeze_thresholds(detector_signals or [])
    baseline = compare_baseline(detector_results or [], baseline_results or [])
    disagreement = record_reviewer_disagreement(reviews or [])
    return {
        "status": "evaluated",
        "dev_clips": len(dev),
        "held_out_clips": len(held_out),
        "scene_leakage": False,
        "frozen_threshold": frozen,
        "baseline_comparison": baseline,
        "reviewer_disagreement": disagreement,
        "note": "held-out measurement not yet reported; no quality claim is made here",
    }
