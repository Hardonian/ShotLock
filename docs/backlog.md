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
3. **OTIO timeline with shot ranges.** Optional `opentimelineio` dependency
   (pyproject extra `otio`); export clip with source_range from intent
   frame_range; validate before shipping or report unavailable. Week 3.
4. **Audio track mapping check.** Handle multi-track/production-sound
   containers: map tracks explicitly, compare per track; report unmapped
   tracks as missing checks.
5. **Mask-sequence regions.** Support `mask_sequence` region kind (per-frame
   mask asset referenced by digest); fall back to unavailable until present.
6. **Project permission validation.** Step 1 of the processing flow: refuse
   projects without a recorded clearance/permission record for the source.
7. **Evaluation harness.** Dev/held-out split by scene, threshold freezing,
   baseline frame-difference comparison, reviewer-disagreement recording.
   Week 4; needs the cleared clip set first.

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
