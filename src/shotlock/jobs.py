"""Job state ledger: the one mutable surface in ShotLock.

Evidence (runs, reports, assets, clearances) is immutable and append-only.
Job state is different: it records the liveness of ONE pipeline invocation so
an interrupted worker leaves a clearly marked trail instead of silence.

States: running -> completed | failed | interrupted.
- completed / failed are set by the worker itself before it exits.
- "interrupted" is set ONLY by recover_jobs(), at startup or after a crash,
  when no worker process is alive to contradict it.
Job state never contains findings — it points at run ids. A retry is always a
new job AND a new run id; a finished job is never rewritten.

Layout: <store root>/jobs/<job_id>/state.json (written atomically).
"""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

JOB_STATES = ("running", "completed", "failed", "interrupted")
TERMINAL_STATES = ("completed", "failed", "interrupted")


def new_job_id() -> str:
    """Time-sortable unique id. One per invocation, never reused."""
    ts = int(time.time() * 1000)
    return f"job-{ts:012x}{secrets.token_hex(8)}"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class JobLedger:
    """Mutable liveness records for pipeline invocations. Everything else in
    the store stays immutable."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root) / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def _state_path(self, job_id: str) -> Path:
        return self.root / job_id / "state.json"

    def _write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        os.replace(tmp, path)  # atomic on POSIX: never a half-written state

    def load(self, job_id: str) -> dict[str, Any]:
        return json.loads(self._state_path(job_id).read_text())

    def job_ids(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    def begin(
        self,
        *,
        project_id: Any,
        source_digest: str | None,
        intent_revision: Any,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """Open a job. Refuses to reuse a job identity: a retry is a new job."""
        job_id = job_id or new_job_id()
        if self._state_path(job_id).exists():
            raise ValueError(f"job_id {job_id!r} already exists; a retry must use a new job identity")
        state = {
            "job_id": job_id,
            "state": "running",
            "project_id": project_id,
            "source_digest": source_digest,
            "intent_revision": intent_revision,
            "started_at": _now(),
            "updated_at": _now(),
            "run_id": None,
            "detail": None,
        }
        self._write(self._state_path(job_id), state)
        return state

    def finish(
        self,
        job_id: str,
        state: str,
        *,
        run_id: str | None = None,
        detail: str | None = None,
    ) -> dict[str, Any]:
        """Close a job as completed or failed. A finished job is never rewritten."""
        if state not in ("completed", "failed"):
            raise ValueError(f"worker may only finish a job as 'completed' or 'failed', not {state!r}")
        current = self.load(job_id)
        if current["state"] in TERMINAL_STATES:
            raise ValueError(
                f"job {job_id!r} already finished as {current['state']!r}; "
                "a retry must use a new job identity"
            )
        current["state"] = state
        current["run_id"] = run_id
        current["detail"] = detail
        current["updated_at"] = _now()
        self._write(self._state_path(job_id), current)
        return current

    def recover_jobs(self) -> list[str]:
        """Mark every still-running job 'interrupted' (clearly failed).

        Call ONLY at startup or after a crash, when no pipeline worker is
        alive. Prior evidence is never modified — this touches job state only.
        Returns the recovered job ids.
        """
        recovered: list[str] = []
        for job_id in self.job_ids():
            state = self.load(job_id)
            if state["state"] == "running":
                state["state"] = "interrupted"
                state["detail"] = (
                    "worker did not finish; marked interrupted by recover_jobs() "
                    "(prior evidence untouched; retry as a new job + new run id)"
                )
                state["updated_at"] = _now()
                self._write(self._state_path(job_id), state)
                recovered.append(job_id)
        return recovered
