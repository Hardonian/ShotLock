"""Evidence store tests: immutability is structural, not conventional."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from shotlock.store import EvidenceStore, new_run_id, sha256_file  # noqa: E402


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="shotlock-store-")
        self.store = EvidenceStore(self.tmp)

    def test_run_record_is_immutable(self):
        run = {"run_id": "01HRRUN0000000001", "measured_cost": {"currency": "CAD", "amount": 1.0}}
        self.store.record_run(run)
        with self.assertRaises(ValueError):
            self.store.record_run(run)

    def test_report_record_is_immutable(self):
        report = {"report_id": "rep-1"}
        self.store.record_report(report)
        with self.assertRaises(ValueError):
            self.store.record_report(report)

    def test_digest_is_stable(self):
        path = Path(self.tmp) / "blob.bin"
        path.write_bytes(b"shotlock")
        self.assertEqual(sha256_file(path), sha256_file(path))
        self.assertTrue(sha256_file(path).startswith("sha256:"))

    def test_asset_registration_is_idempotent(self):
        path = Path(self.tmp) / "blob2.bin"
        path.write_bytes(b"asset")
        first = self.store.record_asset(path)
        second = self.store.record_asset(path)
        self.assertEqual(first, second)

    def test_run_ids_are_unique(self):
        ids = {new_run_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)

    def test_cost_total(self):
        for i, amount in enumerate((100.0, 250.5)):
            self.store.record_run({
                "run_id": f"01HRRUN000000000{i}",
                "measured_cost": {"currency": "CAD", "amount": amount},
            })
        self.assertAlmostEqual(self.store.measured_cost_total("CAD"), 350.5)


if __name__ == "__main__":
    unittest.main()
