# ShotLock

**An independent toolkit that converts an approved edit request into measurable
preservation constraints and gives a filmmaker evidence about what an AI edit
changed.** First use case: object removal from existing footage, evaluated
alongside the surrounding cut.

Change the requested part of a shot, identify unintended changes, preserve the
source and revision history, and leave acceptance to the filmmaker.

## Status (honest)

- Researched opportunity and implementation specification — see
  `docs/InterPositive-research-brief.md` (prepared 2026-10-02).
- No application, model training, performance benchmark, partnership, or
  outreach has been executed.
- `ShotLock` is a working name; naming availability has **not** been checked.
- This repository currently holds the specification, data contracts
  (`schemas/`), and the first analysis tooling. The review UI, inference
  integration, and evaluation dataset are build work per `docs/week-plan.md`.

## Principles

- **Hard constraints vs review signals.** Source identity, authorization scope,
  duration/frame count, audio policy, and reproducible configuration capture are
  hard failures. Background drift, prop motion, expression change, lighting
  mismatch, and plausibility are *review signals* routed to a human.
- **The allowed consequence region is first-class.** Removing an object may
  legitimately change its shadow or an interacting object. A checker that flags
  every changed pixel would reject correct results.
- **Evidence, not verdicts.** Every finding cites a constraint, a comparison
  method, and a frame range. Uncertain findings ask for review. No metric
  guarantees that performance or meaning is unchanged.
- **A check that did not run must not appear as passed.** Reports carry a
  summary of missing checks.
- **Immutable run identities.** A retry gets a new run id and can never
  overwrite earlier evidence.
- **An unchanged video is a failed task.** Perfect preservation with no
  requested edit completed is still a failure.

## Repository layout

```
docs/InterPositive-research-brief.md  The research brief (verbatim source document)
docs/week-plan.md                     Four-week implementation plan + demo outline
schemas/                              Intent, run, and review-report data contracts
src/shotlock/                          Python analysis tooling (stdlib-first)
tests/                                Unit tests (python -m unittest)
```

## Contracts

The three JSON Schemas in `schemas/` are the product's spine:

| Schema | Purpose |
|---|---|
| `intent-record.schema.json` | The filmmaker's approved edit request, including allowed edit region, allowed consequence region, protected content, and audio policy |
| `run-record.schema.json` | Full reproducibility manifest for one render/import: digests, model, seed, sampler, hardware, transforms, cost, exit state |
| `review-report.schema.json` | Findings with frame ranges and severity, reviewer decisions, and explicit missing-check disclosure |

## Getting started

```bash
cd shotlock
python3 -m unittest discover -s tests -v     # run the test suite (stdlib only)
python3 -m shotlock.media path/to/clip.mov   # inspect a clip via ffprobe
```

Requirements: Python 3.11+, `ffprobe` on PATH for media inspection. The
analysis tooling is dependency-free by design; heavier CV methods and inference
backends (e.g. VOID where resources and licensing permit) come behind a
capability interface later.

## Hardware and spending plan

- EPYC machine: media preparation, queues, orchestration, analysis workloads.
- HX370: development and review.
- The documented VOID quick-start requires 40 GB+ GPU memory — more than any
  single GPU in the listed setup (V100 16 GB, P40 24 GB, RTX 3060 12 GB). Begin
  with imported renders and lightweight analysis. Quantization and offloading
  are experiments until quality, latency, and memory are measured.
- Compute budget ceiling for initial work: **CAD 300–500** (proposed constraint,
  not a quote or spending authorization). Stop at the ceiling; retain run
  evidence. No hardware purchase is justified before a filmmaker confirms the
  review workflow is useful.

## Verification and release gates

- [ ] A source/candidate frame mismatch is detected and localized without
      silently resampling the evidence.
- [ ] The system distinguishes allowed interaction changes from protected content.
- [ ] Missing or failed detectors produce an explicit unavailable result.
- [ ] A worker interruption leaves a resumable or clearly failed job and retains
      prior evidence.
- [ ] A retry receives a new run identity and cannot overwrite the prior candidate.
- [ ] Project A cannot read Project B's source, adapter, cache, or findings.
- [ ] Approval of one revision cannot authorize a different media digest or an
      expanded edit.
- [ ] Reports open without the application running and disclose all analysis
      transforms.
- [ ] Editor handoff preserves the tested shot ranges, rate, and references.
- [ ] No claims of quality improvement are published until measured on held-out
      footage.
