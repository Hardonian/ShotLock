"""OTIO timeline export tests (source_range from the intent frame_range)."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.export import _try_otio  # noqa: E402

HAVE_OTIO = importlib.util.find_spec("opentimelineio") is not None

REPORT = {"report_id": "rep-otio1", "run_id": "01HQRUNEXAMPLE0011"}
INTENT = {
    "frame_range": {"start": 12, "end_exclusive": 21},
    "frame_rate": {"numerator": 24, "denominator": 1},
}


class OtioTimeline(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix="shotlock-otio-"))

    @unittest.skipIf(HAVE_OTIO, "only applies when opentimelineio is NOT installed")
    def test_export_unavailable_without_otio(self):
        entry = _try_otio(REPORT, self.out, INTENT)
        self.assertEqual(entry["status"], "unavailable")
        self.assertIn("OpenTimelineIO not installed", entry["reason"])

    def test_source_range_mapped_from_intent(self):
        fake = mock.MagicMock()
        with mock.patch.dict(sys.modules, {"opentimelineio": fake}):
            entry = _try_otio(REPORT, self.out, INTENT)
        self.assertEqual(entry["status"], "exported")
        self.assertEqual(entry["source_range"], {"start": 12, "end_exclusive": 21, "rate": 24.0})
        # RationalTime must be built as (start, fps) then (duration, fps)
        rt_calls = fake.opentime.RationalTime.call_args_list
        self.assertEqual(rt_calls[0].args, (12, 24.0))
        self.assertEqual(rt_calls[1].args, (9, 24.0))
        # the written timeline is re-read for validation
        fake.adapters.read_from_file.assert_called_once()

    def test_empty_frame_range_notes_no_clip(self):
        fake = mock.MagicMock()
        intent = {"frame_range": {"start": 0, "end_exclusive": 0}, "frame_rate": {"numerator": 24, "denominator": 1}}
        with mock.patch.dict(sys.modules, {"opentimelineio": fake}):
            entry = _try_otio(REPORT, self.out, intent)
        self.assertEqual(entry["status"], "exported")
        self.assertIn("no clip source_range", entry["note"])

    def test_validate_failure_is_unavailable_not_shipped(self):
        fake = mock.MagicMock()
        fake.adapters.write_to_file.side_effect = RuntimeError("boom")
        with mock.patch.dict(sys.modules, {"opentimelineio": fake}):
            entry = _try_otio(REPORT, self.out, INTENT)
        self.assertEqual(entry["status"], "unavailable")
        self.assertIn("failed validation", entry["reason"])


if __name__ == "__main__":
    unittest.main()
