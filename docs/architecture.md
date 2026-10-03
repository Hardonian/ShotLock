# Architecture

ShotLock converts an approved edit request into measurable preservation
constraints and evidence. Nothing in the pipeline decides creative
acceptance — the filmmaker does.

## Entities (from the brief)

| Entity | Where it lives | Identity |
|---|---|---|
| Project | `projects/<project_id>/project.json` | `project_id` |
| Asset | `assets/<sha256>.ref` | content digest (immutable) |
| Shot | intent records reference it | `(project_id, shot_id)` |
| IntentRevision | intent record JSON | `intent_revision` (monotonic) |
| Run | `runs/<run_id>/run.json` | `run_id` — one per attempt, never reused |
| Finding | inside a report | `finding_id` within a report |
| ReviewDecision | `run.json: reviewer_decisions[]` | binds candidate digest + intent revision |
| Export | `export_package()` output | manifest.json |

## Processing flow ↔ code

| Step (brief) | Module |
|---|---|
| 1. Validate source and permissions | `pipeline.process_edit` (digest check) |
| 2. Draft + approve the specification | `intent.validate_intent` + `intent.approval_covers` |
| 3. Validate backend capability and inputs | `backends.RenderBackend.validate_input` |
| 4. Submit bounded job or import candidate | `backends.ImportedRenderBackend.submit` |
| 5. Normalize + record transforms | `pipeline._normalize` → `RunRecord.analysis_transforms` |
| 6. Deterministic checks | `checks.run_checks` |
| 7. Present evidence | `checks` → findings shaped to `schemas/review-report.schema.json` |
| 8. Export + immutable records | `store.EvidenceStore` + `export.export_package` |

## Invariants enforced in code (not just documented)

- **Approval binds the exact source digest.** A different media digest or an
  expanded edit requires a new intent revision and a new approval
  (`intent.approval_covers`, enforced in `pipeline.process_edit`).
- **A retry gets a new run identity** and can never overwrite evidence
  (`store.EvidenceStore._record` refuses overwrites; `intent.assert_new_run_id`).
- **A check that did not run is never reported as passed** — it lands in
  `missing_checks` with a reason (`checks.run_checks`), and
  `report.crosscheck_report` rejects any check appearing as both run and
  missing.
- **Unavailable beats false confidence.** Unknown frame counts, undecodable
  audio, and unimplemented checks are reported as `unavailable`.
- **Budget and retry limits live outside any language model**
  (`pipeline.check_budget`, `MAX_RETRIES_PER_INTENT`).
- **All transforms are disclosed** in both the run record and the HTML report.

## Constraint classes

- **Hard** (block acceptance): source identity, authorization scope, duration,
  frame count, audio retention policy, reproducible configuration capture.
- **Review signals** (route to a human): background drift, prop motion,
  expression change, lighting mismatch, eyeline concerns, physical
  plausibility. High-uncertainty findings must ask for review
  (`uncertainty.note` is required at level `high`).

## Backends

`backends.py` defines the capability interface (`RenderBackend`) and ships one
fully working backend: `imported` (ingest renders produced elsewhere). A VOID
adapter belongs behind the same interface once hardware and licensing are
validated (quick start needs 40 GB+ VRAM; the lab's single GPUs cannot run it
as-is). Quantization and offloading are experiments until measured.

## Multi-project isolation (later deployment)

Assets, checkpoints, caches, queues, and logs isolate per project; worker
credentials restrict to assigned assets; private media never goes to a hosted
vision model without explicit project permission. Model/dataset licenses are
recorded separately from contributor permissions.

## Editorial handoff

`export.export_package` writes the self-contained HTML report, findings JSON,
CSV issue list, selected media, and an OTIO timeline only when OpenTimelineIO
is installed and the output validates — otherwise the manifest says
`unavailable` rather than shipping something untested. Color: source color
space and transforms are part of the input contract; the first release supports
a narrow declared SDR workflow and does not claim ACES/EXR support.
