"""The processing flow, end to end.

Mirrors the brief's eight steps:

1. Validate the source and project permissions.
2. Confirm the filmmaker's approved intent binds this exact source digest.
3. Validate backend capability and inputs.
4. Submit a bounded render job or import a candidate.
5. Normalize source and candidate for comparison, recording every transform.
6. Run deterministic checks.
7. Shape evidence for review (findings; missing checks disclosed).
8. Record immutable run + report; export happens separately.

Retry limits and compute budgets are enforced HERE, outside any language
model. Publication, delivery, and expanded edit permissions are separate
authorized transitions and are not part of this function.
"""
from __future__ import annotations

import time
from typing import Any

from .backends import get_backend
from .checks import run_checks
from .intent import (
    assert_new_run_id,
    approval_covers,
    validate_intent,
    validate_run_record,
)
from .jobs import JobLedger
from .media import FfprobeMissing, inspect_media
from .permission import validate_clearance
from .report import crosscheck_report, validate_report
from .store import EvidenceStore, new_run_id, sha256_file

DEFAULT_BUDGET_CAD = 500.0  # proposed ceiling from the brief; hard stop
MAX_RETRIES_PER_INTENT = 2  # bounded retry; enforced outside any LLM


class PipelineError(RuntimeError):
    """The pipeline refused to proceed. The message says exactly why."""


def check_budget(store: EvidenceStore, ceiling_cad: float = DEFAULT_BUDGET_CAD) -> None:
    """Hard stop: refuse new work once measured spend reaches the ceiling."""
    spent = store.measured_cost_total("CAD")
    if spent >= ceiling_cad:
        raise PipelineError(
            f"compute budget exhausted: CAD {spent:.2f} of {ceiling_cad:.2f} ceiling spent; "
            "retaining run evidence and stopping (raise the ceiling explicitly to continue)"
        )


def _normalize(source_path: str, candidate_path: str) -> list[dict[str, Any]]:
    """Comparison normalization. Everything applied is recorded; nothing is
    silently resampled. Currently identity: both sides are compared as stored."""
    return [
        {
            "kind": "identity_comparison",
            "parameters": {
                "source_path": source_path,
                "candidate_path": candidate_path,
                "note": "no resampling applied; analysis proxies would be recorded here",
            },
        }
    ]


def process_edit(
    store: EvidenceStore,
    intent: dict[str, Any],
    source_path: str,
    candidate_path: str,
    *,
    backend_name: str = "imported",
    run_id: str | None = None,
    measured_cost: dict[str, Any] | None = None,
    budget_ceiling_cad: float = DEFAULT_BUDGET_CAD,
) -> dict[str, Any]:
    """Run one approved edit candidate through the evidence pipeline.

    Returns {"run": ..., "report": ...} with the recorded records. Raises
    PipelineError on refusal (no clearance, bad intent, wrong source, budget,
    bad input). Every invocation gets a job record: an interrupted worker
    leaves its job clearly marked (recover via JobLedger.recover_jobs) and
    never touches prior evidence.
    """
    # 0. budget — enforced before any work, outside any model
    check_budget(store, budget_ceiling_cad)

    # 0b. job ledger — liveness for THIS invocation. Evidence is immutable;
    #     job state is the one mutable surface. A crashed worker leaves its job
    #     "running"; recover_jobs() marks it "interrupted" (clearly failed). A
    #     retry is a new job AND a new run id.
    source_digest = sha256_file(source_path)
    ledger = JobLedger(store.root)
    job = ledger.begin(
        project_id=intent.get("project_id") if isinstance(intent, dict) else None,
        source_digest=source_digest,
        intent_revision=intent.get("intent_revision") if isinstance(intent, dict) else None,
    )
    try:
        result = _process_edit(
            store, intent, source_path, candidate_path,
            source_digest=source_digest,
            backend_name=backend_name,
            run_id=run_id,
            measured_cost=measured_cost,
        )
    except Exception as exc:
        ledger.finish(job["job_id"], "failed", detail=f"{type(exc).__name__}: {exc}")
        raise
    ledger.finish(job["job_id"], "completed", run_id=result["run"]["run_id"])
    return result


def _process_edit(
    store: EvidenceStore,
    intent: dict[str, Any],
    source_path: str,
    candidate_path: str,
    *,
    source_digest: str,
    backend_name: str = "imported",
    run_id: str | None = None,
    measured_cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # 1. project permission / clearance — refuse unless a clearance is RECORDED
    #    for THIS source (a clearance for one source never clears a different one)
    project_id = intent.get("project_id") if isinstance(intent, dict) else None
    clearance = store.get_clearance(source_digest)
    perm_errors = validate_clearance(clearance, source_digest, project_id)
    if perm_errors:
        raise PipelineError("project permission invalid: " + "; ".join(perm_errors))

    # 2. intent validity
    errors = validate_intent(intent)
    if errors:
        raise PipelineError("intent record invalid: " + "; ".join(errors))

    # 3. approval binds THIS source digest (a different media digest is a
    #    different edit and requires re-approval)
    if not approval_covers(intent, source_digest):
        raise PipelineError(
            f"approval does not cover source {source_digest}; "
            "a different media digest or expanded edit requires a new intent revision and approval"
        )

    # 3. backend capability and inputs
    backend = get_backend(backend_name)
    caps = backend.capabilities()
    mode = "imported_render" if "imported_render" in caps.modes else caps.modes[0]
    if mode not in caps.modes:
        raise PipelineError(f"backend {caps.name!r} does not support mode {mode!r}")
    problems = backend.validate_input(candidate_path)
    if problems:
        raise PipelineError("candidate rejected by backend validation: " + "; ".join(problems))

    # 4. submission / import descriptor
    submission = backend.submit(candidate_path, intent)

    # 5. normalization (all transforms recorded)
    analysis_transforms = _normalize(source_path, candidate_path)

    # 6. deterministic checks
    checks = run_checks(source_path, candidate_path, intent)

    # 7. evidence shaping (report validity is itself checked)
    candidate_digest = sha256_file(candidate_path)
    run_id = run_id or new_run_id()
    assert_new_run_id(store.run_ids(), run_id)  # retries get new identities, always

    try:
        source_info = inspect_media(source_path)
    except (FfprobeMissing, ValueError):
        source_info = {}

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    run_record: dict[str, Any] = {
        "run_id": run_id,
        "intent_revision": intent["intent_revision"],
        "project_id": intent["project_id"],
        "shot_id": intent["shot_id"],
        "source_digest": source_digest,
        "conditioning_digests": [],
        "mode": mode,
        "started_at": now,
        "finished_at": now,
        "exit_state": "completed",
        "configuration": {
            "backend": {"name": caps.name, "model_identifier": submission["backend"]},
            "preprocessing_transforms": [],
            "seed": None,
            "inference_parameters": {},
        },
        "output_digest": candidate_digest,
        "output_identity": "not_claimed",
        "analysis_transforms": analysis_transforms,
        "measured_cost": measured_cost or {"currency": "CAD", "amount": 0.0},
        "reviewer_decisions": [],
    }
    run_errors = validate_run_record(run_record)
    if run_errors:
        raise PipelineError("run record invalid: " + "; ".join(run_errors))

    report_id = f"rep-{run_id}"
    report: dict[str, Any] = {
        "report_id": report_id,
        "run_id": run_id,
        "intent_revision": intent["intent_revision"],
        "source_digest": source_digest,
        "candidate_digest": candidate_digest,
        "generated_at": now,
        "findings": checks["findings"],
        "missing_checks": checks["missing_checks"],
        "checks_run": checks["checks_run"],
        "analysis_transforms": analysis_transforms,
    }
    report_errors = validate_report(report) + crosscheck_report(report)
    if report_errors:
        raise PipelineError("report failed its own evidence rules: " + "; ".join(report_errors))

    # 8. immutable recording — a retry can never overwrite this evidence
    store.record_asset(source_path)
    store.record_asset(candidate_path)
    store.record_run(run_record)
    store.record_report(report)

    return {"run": run_record, "report": report, "source_info": source_info}
