# ShotLock backlog (overnight + beyond)

Ordered by value. Every item: real implementation + tests + honest
unavailable/missing-check behavior. Run `python3 -m unittest discover -s tests`
and `bandit -q -r src/ tests/` before every commit; push to origin main.

## Overnight candidates

1. ~~**Finding snapshots.**~~ **DONE** (2026-10-03). `src/shotlock/snapshots.py`
   (`attach_finding_snapshots`) grabs source|candidate side-by-side at each
   finding's frame range, links `supporting_images`/`inspect_path`, and renders
   an `evidence` column in `report.html`. Honest degradation: uncapturable
   frames keep empty `supporting_images` + a manifest gap. 5 tests.
2. ~~**Frame-duplicate detector.**~~ **DONE** (2026-10-03).
   `frame_duplicate_check` (checks.py) compares consecutive candidate frames via
   ffmpeg PSNR, excludes the allowed edit region, and localizes near-identical
   pairs as review signals. Validated against `fixtures.inject_duplicated_frame`
   (injected repeat detected + localized). 6 tests.
3. ~~**OTIO timeline with shot ranges.**~~ **DONE** (2026-10-03). `_try_otio`
   maps the intent frame_range into a clip `source_range` at the intent rational
   rate, validates by re-reading before reporting exported; optional `otio`
   extra added. 4 tests.
4. ~~**Audio track mapping check.**~~ **DONE** (2026-10-03). Per-track decoded
   md5 comparison (track i -> track i); dropped source tracks are hard retention
   violations, unmapped additions/tooling gaps are disclosed as missing
   sub-checks. 4 tests.
5. ~~**Mask-sequence regions.**~~ **DONE** (2026-10-03). Recognizes
   `mask_sequence` regions (per-frame mask asset by digest); falls back to
   unavailable with a precise reason until a validated mask asset exists. 5 tests.
6. ~~**Project permission validation.**~~ **DONE** (2026-10-03). Step 1 gate:
   `permission.validate_clearance` refuses to process a source without a
   RECORDED clearance covering this source digest + project. 6 tests.
7. ~~**Evaluation harness.**~~ **DONE (scaffold)** (2026-10-03). Scene-split dev/
   held-out (no leakage), threshold freezing on dev, baseline comparison,
   reviewer-disagreement recording. Reports unavailable without the cleared clip
   set (still gated). 7 tests.

## Gated (needs humans/hardware)

- Cleared three-shot scene (written permission required before capture/use).
- VOID backend adapter (40 GB+ VRAM quick-start; validate on real hardware and
  licensing first; the capability interface is ready).
- Practitioner review session (at least two experienced reviewers).

## Rules for every change

- A check that did not run must never appear as passed.
- Findings carry constraint, method, frame range, severity, uncertainty.
- A retry gets a new run id; evidence is immutable.
- Budget/retry limits enforced outside any language model.
- No quality claims before held-out measurement.
