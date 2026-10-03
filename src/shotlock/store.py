"""Filesystem-backed evidence store.

Immutability is structural: a run_id or report_id can be recorded exactly once.
A retry gets a new identity and can never overwrite earlier evidence. Every
asset is referenced by digest (sha256), never by mutable path alone.

Layout under the store root:

    projects/<project_id>/project.json
    runs/<run_id>/run.json
    reports/<report_id>/report.json
    assets/<sha256>.ref        (a reference record: original path + size)
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Digest of a file's bytes, formatted as the schemas expect."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def new_run_id() -> str:
    """Time-sortable unique id (ULID-style). One per attempt, never reused."""
    ts = int(time.time() * 1000)
    return f"{ts:012x}{secrets.token_hex(8)}"


class EvidenceStore:
    """Append-only store for projects, runs, reports, and asset references."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        for sub in ("projects", "runs", "reports", "assets", "clearances"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    # -- generic json records -------------------------------------------------
    def _record(self, rel: Path, payload: dict[str, Any]) -> Path:
        target = self.root / rel
        if target.exists():
            raise ValueError(f"refusing to overwrite immutable record: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return target

    def _load(self, rel: Path) -> dict[str, Any]:
        return json.loads((self.root / rel).read_text())

    # -- entities -------------------------------------------------------------
    def record_project(self, project: dict[str, Any]) -> Path:
        return self._record(Path("projects") / project["project_id"] / "project.json", project)

    def record_run(self, run: dict[str, Any]) -> Path:
        return self._record(Path("runs") / run["run_id"] / "run.json", run)

    def record_report(self, report: dict[str, Any]) -> Path:
        return self._record(Path("reports") / report["report_id"] / "report.json", report)

    def record_asset(self, path: str | os.PathLike[str]) -> str:
        """Register an asset by digest. Returns the digest; safe to call twice."""
        digest = sha256_file(path)
        ref = self.root / "assets" / f"{digest.split(':', 1)[1]}.ref"
        if not ref.exists():
            stat = os.stat(path)
            ref.write_text(
                json.dumps(
                    {"digest": digest, "original_path": str(path), "size_bytes": stat.st_size},
                    indent=2,
                )
            )
        return digest

    def record_clearance(self, clearance: dict[str, Any]) -> Path:
        """Record a clearance/permission record keyed by its source digest.

        Immutable: a clearance for a given source is recorded exactly once. This
        is the "recorded clearance" the pipeline requires before processing.
        """
        digest = clearance["source_digest"]
        return self._record(Path("clearances") / f"{digest.split(':', 1)[1]}.json", clearance)

    def get_clearance(self, source_digest: str) -> dict[str, Any] | None:
        """The recorded clearance covering this source digest, or None."""
        rel = Path("clearances") / f"{source_digest.split(':', 1)[1]}.json"
        if not (self.root / rel).is_file():
            return None
        return self._load(rel)

    def load_run(self, run_id: str) -> dict[str, Any]:
        return self._load(Path("runs") / run_id / "run.json")

    def load_report(self, report_id: str) -> dict[str, Any]:
        return self._load(Path("reports") / report_id / "report.json")

    def run_ids(self) -> list[str]:
        return sorted(p.name for p in (self.root / "runs").iterdir() if p.is_dir())

    def measured_cost_total(self, currency: str = "CAD") -> float:
        """Sum of measured costs across all recorded runs (budget enforcement
        lives here, outside any language model)."""
        total = 0.0
        for run_id in self.run_ids():
            cost = self.load_run(run_id).get("measured_cost") or {}
            if cost.get("currency") == currency and isinstance(cost.get("amount"), (int, float)):
                total += float(cost["amount"])
        return total
