"""Intent and run-record validation.

Stdlib-only on purpose: the contracts (schemas/*.json) are the product's spine
and must be checkable anywhere. These helpers enforce the IN VARIANTS the
schemas cannot express:

- an approval binds the exact source digest; a different media digest or an
  expanded edit requires a new intent revision and a new approval;
- a run gets a fresh immutable run_id; a retry can never overwrite evidence;
- exit_state and output_digest are consistent (no output claimed for a run
  that did not complete).

An LLM may draft an intent record. Validation never expands the authorized edit
area; that is exclusively the approver's act, recorded in the record itself.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

AUDIO_MODES = {"retain_source", "retain_container_audio", "replace", "mute"}
EXIT_STATES = {"completed", "failed", "interrupted"}

REQUIRED_INTENT_FIELDS = (
    "intent_revision",
    "project_id",
    "shot_id",
    "source_digest",
    "frame_range",
    "frame_rate",
    "requested_operation",
    "allowed_edit_region",
    "allowed_consequence_region",
    "protected_content",
    "audio_policy",
    "approver",
)

REQUIRED_RUN_FIELDS = (
    "run_id",
    "intent_revision",
    "project_id",
    "shot_id",
    "source_digest",
    "mode",
    "started_at",
    "finished_at",
    "exit_state",
    "configuration",
    "output_digest",
    "analysis_transforms",
)


def _check_frame_range(fr: Any) -> list[str]:
    if not isinstance(fr, dict):
        return ["frame_range must be an object"]
    errors = []
    start, end = fr.get("start"), fr.get("end_exclusive")
    if not isinstance(start, int) or start < 0:
        errors.append("frame_range.start must be an integer >= 0")
    if not isinstance(end, int) or end < 1:
        errors.append("frame_range.end_exclusive must be an integer >= 1")
    if isinstance(start, int) and isinstance(end, int) and end <= start:
        errors.append("frame_range.end_exclusive must be greater than start")
    return errors


def _check_rational_fps(rate: Any) -> list[str]:
    if not isinstance(rate, dict):
        return ["frame_rate must be an object with integer numerator/denominator"]
    errors = []
    for key in ("numerator", "denominator"):
        value = rate.get(key)
        if not isinstance(value, int) or value < 1:
            errors.append(f"frame_rate.{key} must be an integer >= 1")
    return errors


def validate_intent(record: dict) -> list[str]:
    """Return a list of problems with an intent record. Empty list = valid."""
    if not isinstance(record, dict):
        return ["intent record must be an object"]
    errors: list[str] = []
    for field in REQUIRED_INTENT_FIELDS:
        if field not in record:
            errors.append(f"missing required field: {field}")
    if errors:
        return errors

    if not isinstance(record["intent_revision"], int) or record["intent_revision"] < 1:
        errors.append("intent_revision must be an integer >= 1")
    digest = record["source_digest"]
    if not isinstance(digest, str) or not DIGEST_RE.match(digest):
        errors.append("source_digest must be sha256:<64 hex>")
    errors += _check_frame_range(record["frame_range"])
    errors += _check_rational_fps(record["frame_rate"])

    operation = record["requested_operation"]
    if not isinstance(operation, dict) or not operation.get("verb"):
        errors.append("requested_operation.verb is required")

    for region_field in ("allowed_edit_region", "allowed_consequence_region"):
        region = record[region_field]
        if not isinstance(region, dict) or not region.get("kind"):
            errors.append(f"{region_field}.kind is required")

    protected = record["protected_content"]
    if not isinstance(protected, list):
        errors.append("protected_content must be an array")
    else:
        for i, item in enumerate(protected):
            if not isinstance(item, dict) or not item.get("kind"):
                errors.append(f"protected_content[{i}].kind is required")

    audio = record["audio_policy"]
    if not isinstance(audio, dict) or audio.get("mode") not in AUDIO_MODES:
        errors.append(f"audio_policy.mode must be one of {sorted(AUDIO_MODES)}")

    approver = record["approver"]
    if not isinstance(approver, dict) or not approver.get("name") or not approver.get("approved_at"):
        errors.append("approver.name and approver.approved_at are required (approval is a human act)")
    return errors


def approval_covers(record: dict, source_digest: str, *, requested_operation: dict | None = None) -> bool:
    """True only when this approval binds the exact source digest being edited.

    A different media digest is a different edit: it requires re-approval.
    When requested_operation is given it must match the approved verb — an
    approval can never authorize an operation that was not requested of the
    approver.
    """
    if not isinstance(record, dict) or not record.get("approver"):
        return False
    if record.get("source_digest") != source_digest:
        return False
    if requested_operation is not None and record.get("requested_operation") != requested_operation:
        return False
    return True


def validate_run_record(run: dict) -> list[str]:
    """Return problems with a run record. Empty list = valid."""
    if not isinstance(run, dict):
        return ["run record must be an object"]
    errors: list[str] = []
    for field in REQUIRED_RUN_FIELDS:
        if field not in run:
            errors.append(f"missing required field: {field}")
    if errors:
        return errors

    run_id = run["run_id"]
    if not isinstance(run_id, str) or len(run_id) < 8:
        errors.append("run_id must be a string of at least 8 characters")

    state = run["exit_state"]
    if state not in EXIT_STATES:
        errors.append(f"exit_state must be one of {sorted(EXIT_STATES)}")
    output = run["output_digest"]
    if state == "completed":
        if not isinstance(output, str) or not DIGEST_RE.match(output):
            errors.append("completed runs must carry output_digest (sha256:<64 hex>)")
    elif output is not None:
        errors.append("output_digest must be null for runs that did not complete")

    config = run["configuration"]
    if not isinstance(config, dict) or not config.get("backend"):
        errors.append("configuration.backend is required")
    elif not config["backend"].get("model_identifier") and run["mode"] == "inference":
        errors.append("configuration.backend.model_identifier is required for inference runs")
    if not isinstance(config, dict) or not isinstance(config.get("preprocessing_transforms"), list):
        errors.append("configuration.preprocessing_transforms must be an array (transforms are disclosed, not implicit)")
    return errors


def assert_new_run_id(existing_run_ids: Iterable[str], run_id: str) -> None:
    """Guard immutability: a retry gets a NEW identity and never overwrites evidence."""
    if run_id in set(existing_run_ids):
        raise ValueError(f"run_id {run_id!r} already exists; a retry must use a new run identity")
