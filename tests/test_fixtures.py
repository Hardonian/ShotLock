"""Fixture injection + protected-region detector validation on real media."""
from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 — ffmpeg invoked with fixed argument lists in tests
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.checks import (  # noqa: E402
    audio_preservation_check,
    protected_region_check,
)
from shotlock.fixtures import (  # noqa: E402
    FIXTURE_KIND,
    inject_all,
    inject_localized_prop_change,
)
from shotlock.media import inspect_media  # noqa: E402

HAVE_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")

SOURCE_GEN = [
    "ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
    "testsrc=duration=2:size=128x72:rate=24",
    "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
    "-c:v", "libx264", "-c:a", "aac",
]


def make_intent(**overrides):
    record = {
        "intent_revision": 1,
        "project_id": "p-fix",
        "shot_id": "sh-01",
        "source_digest": "sha256:" + "0" * 64,
        "frame_range": {"start": 0, "end_exclusive": 48},
        "frame_rate": {"numerator": 24, "denominator": 1},
        "requested_operation": {"verb": "remove_object", "target": "sign"},
        "allowed_edit_region": {"kind": "bbox_per_frame", "x": 10, "y": 10, "width": 24, "height": 24},
        "allowed_consequence_region": {"kind": "empty"},
        "protected_content": [
            {
                "kind": "prop_position",
                "region": {"kind": "bbox_per_frame", "x": 10, "y": 10, "width": 24, "height": 24},
            }
        ],
        "audio_policy": {"mode": "retain_source"},
        "reference_shots": [],
        "approver": {"name": "Fixture Director", "approved_at": "2026-10-03T12:00:00Z"},
    }
    record.update(overrides)
    return record


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg/ffprobe required")
class Fixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="shotlock-fixtures-")
        cls.source = str(Path(cls.tmp) / "source.mp4")
        subprocess.run(SOURCE_GEN + [cls.source], check=True, timeout=120)  # nosec B603

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_fixture_set_is_generated_and_labeled(self):
        out = Path(self.tmp) / "set1"
        records = inject_all(self.source, out)
        self.assertEqual(len(records), 3)
        for record in records:
            self.assertEqual(record["kind"], FIXTURE_KIND)
            sidecar = out / (record["file"] + ".fixture.json")
            self.assertTrue(sidecar.exists())
            self.assertEqual(json.loads(sidecar.read_text())["kind"], FIXTURE_KIND)

    def test_duplicated_frame_fixture_has_extra_frame(self):
        out = Path(self.tmp) / "set2"
        records = inject_all(self.source, out)
        dup = next(r for r in records if r["defect"] == "duplicated_frame")
        info = inspect_media(str(out / dup["file"]))
        base = inspect_media(self.source)
        self.assertEqual(info["frame_count"], base["frame_count"] + 1)

    def test_region_check_localizes_prop_change(self):
        out = Path(self.tmp) / "set3"
        record = inject_localized_prop_change(
            self.source, out, x=10, y=10, width=24, height=24,
            frame_start=12, frame_end_exclusive=21,
        )
        result = protected_region_check(self.source, str(out / record["file"]), make_intent())
        self.assertEqual(result.outcome, "fail")
        self.assertTrue(result.findings)
        covered = set()
        for finding in result.findings:
            self.assertEqual(finding["constraint"]["class"], "review_signal")
            self.assertEqual(finding["comparison_method"], "psnr_registered_region")
            covered.update(range(finding["frame_range"]["start"], finding["frame_range"]["end_exclusive"]))
        # the injected change spans frames 12..20 — findings must cover it
        self.assertTrue({12, 16, 20}.issubset(covered))

    def test_region_check_passes_on_identical_media(self):
        result = protected_region_check(self.source, self.source, make_intent())
        self.assertEqual(result.outcome, "pass")

    def test_region_check_unreadable_region_is_unavailable_not_pass(self):
        intent = make_intent(protected_content=[{"kind": "prop_position", "region": {"kind": "bbox_per_frame"}}])
        result = protected_region_check(self.source, self.source, intent)
        self.assertEqual(result.outcome, "unavailable")
        self.assertIn("machine-readable", result.detail)
        self.assertEqual(result.findings, [])

    def test_altered_audio_violates_retention(self):
        out = Path(self.tmp) / "set4"
        records = inject_all(self.source, out)
        altered = next(r for r in records if r["defect"] == "altered_audio")
        result = audio_preservation_check(self.source, str(out / altered["file"]), make_intent())
        self.assertEqual(result.outcome, "fail")
        self.assertTrue(any(f["constraint"]["kind"] == "audio_policy" for f in result.findings))


if __name__ == "__main__":
    unittest.main()
