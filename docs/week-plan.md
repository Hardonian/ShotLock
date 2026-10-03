# Implementation plan

The four-week prototype schedule from the research brief, with week-1 detail
and the honest completion evidence for each week. Subject to footage
availability and practitioner feedback.

| Week | Deliverable | Completion evidence |
|---|---|---|
| 1 | Cleared scene, intent schema, source/candidate ingestion, synchronized viewer | Real media can be reviewed at exact frames; missing data is handled visibly. |
| 2 | Protected-region checks, run manifests, HTML/JSON reports | Labeled defects and actual render issues can be traced to evidence. |
| 3 | One real inference integration or imported-render pipeline; bounded retry; editorial export | End-to-end demonstration includes a failed candidate and a human-approved handoff. |
| 4 | Held-out evaluation, practitioner review, documentation, short demo | Published methodology distinguishes test fixtures, model outputs, limitations, and measured outcomes. |

## Status

| Piece | State |
|---|---|
| Intent schema + validation | done (`schemas/intent-record.schema.json`, `intent.py`, tests) |
| Run manifests (immutable) | done (`schemas/run-record.schema.json`, `store.py`, tests) |
| HTML/JSON/CSV reports | done (`export.py`, tests) |
| Imported-render pipeline + bounded retry + budget stop | done (`pipeline.py`, `backends.py`, tests) |
| Media/audio integrity checks | done (`checks.py`, real-media tests) |
| Protected-region checks | week 2 (explicitly reported as `missing_checks`, never as passed) |
| Synchronized viewer | week 1 remaining |
| Cleared three-shot scene | week 1 remaining (requires written permission before capture/use) |
| Real inference backend (VOID adapter) | week 3, behind `RenderBackend`; blocked on hardware/licensing validation |
| OTIO timeline with shot ranges | week 3 (exporter already degrades honestly without OpenTimelineIO) |
| Held-out evaluation | week 4 |

## Week 1 remaining tasks

1. **Cleared scene.** Three-shot scene with written permission for the
   demonstration and any model adaptation. Distracting background object,
   protected foreground performance, prop visible across two shots. Nothing is
   captured or used without this permission — the pipeline refuses unsigned
   digests.
2. **Synchronized viewer.** Source and candidate on the same frame clock with
   an overlay of the approved edit area; scrubbing is frame-exact (rational
   frame rate, not decimal). Missing data (unknown frame counts, absent audio)
   is shown as `unavailable`, never as green.

## Ninety-second demonstration outline

| Time | Screen | Message |
|---|---|---|
| 0–15 s | Three-shot scene and director's request | Establish the requested edit and what must remain. |
| 15–30 s | Approved regions and constraints | Intent becomes inspectable before rendering. |
| 30–55 s | Two actual candidates with frame-level findings | One succeeds at removal but creates an unwanted change. |
| 55–75 s | Source comparison and adjacent shot | The evidence that makes the issue worth reviewing. |
| 75–90 s | Human approval and exported record | A usable handoff with full revision history. |

Show actual model outputs (good and poor, labeled with model, settings, run
history) SEPARATELY from deliberately injected defects (labeled test fixtures:
one duplicated frame, an altered audio track, a localized prop change). End
with the filmmaker selecting a candidate and exporting the review package, and
include one unsuccessful run with the reason it was not accepted. No metric is
presented as a guarantee.

## Evaluation protocol (week 4)

- ~20 short cleared clips (planning target): static/moving cameras, occlusion,
  lighting variation, protected text, interacting objects, varied edit-region
  sizes. Grouped by scene into dev and held-out splits — adjacent shots never
  leak across splits. Thresholds calibrated on dev, frozen, then held-out runs.
- Baselines: frame-difference baseline AND established editing metrics
  (credit CoVEBench, OmniEdit-Bench, FiVE-Bench — do not claim to invent the
  concepts). The unchanged video is an important baseline: perfect preservation
  with no completed edit is a failed task.
- Report disagreements with human reviewers, false alarms, misses, and
  unsupported cases. Pilot with at least two experienced reviewers, preserve
  disagreements, counterbalance tasks with/without the tool, report sample
  sizes. Never market a single aggregate score as production readiness.

## Verification and release gates

See README. The decisive smoke test is the complete filmmaker flow: approve an
intent, process real footage, inspect evidence, reject a flawed version,
approve a revised candidate, and open the exported package.

## Constraints

- Compute ceiling CAD 300–500 (proposed, not authorization); stop at the
  ceiling, retain run evidence. No hardware purchase before a filmmaker
  confirms the review workflow is useful.
- Hardware: EPYC for media prep/queues/orchestration; HX370 for development
  and review. Validate model-specific inference on each GPU before relying on
  it.
- The minimum release is a working review SDK and demonstration — not a new
  foundation model, not a studio-wide SaaS platform.
