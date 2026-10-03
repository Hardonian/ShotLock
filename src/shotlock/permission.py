"""Project permission / clearance validation.

Step 1 of the processing flow: a project may not process a source unless a
recorded clearance/permission record covers it. This is a legal/ethical gate,
not a heuristic — without a recorded clearance for THIS source digest and THIS
project, the pipeline refuses. A clearance record for one source never clears a
different one.

The record shape (validated here; kept in the RunRecord's evidence trail):

    {
      "clearance_id": "clr-...",
      "project_id": "p-...",
      "source_digest": "sha256:<64 hex>",
      "cleared_by": "Rights Holder / Owner",
      "cleared_at": "2026-10-03T12:00:00Z",
      "scope": "edit_review",          # what the clearance permits
    }
"""
from __future__ import annotations

import re
from typing import Any

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate_clearance(
    clearance: Any, source_digest: str, project_id: str | None
) -> list[str]:
    """Return problems with a clearance/permission record. Empty = acceptable."""
    if clearance is None:
        return [
            "no recorded clearance/permission for this source; "
            "refusing to process without a clearance record"
        ]
    if not isinstance(clearance, dict):
        return ["clearance record must be an object"]

    errors: list[str] = []
    for field in ("clearance_id", "cleared_by", "cleared_at", "source_digest"):
        if not clearance.get(field):
            errors.append(f"clearance.{field} is required")

    recorded_digest = clearance.get("source_digest")
    if recorded_digest and not DIGEST_RE.match(str(recorded_digest)):
        errors.append("clearance.source_digest must be sha256:<64 hex>")
    elif recorded_digest and recorded_digest != source_digest:
        errors.append(
            f"clearance covers {recorded_digest}, not this source {source_digest}; "
            "a clearance for one source never clears a different one"
        )

    if project_id and clearance.get("project_id") and clearance.get("project_id") != project_id:
        errors.append(
            f"clearance is for project {clearance.get('project_id')!r}, not {project_id!r}"
        )
    return errors
