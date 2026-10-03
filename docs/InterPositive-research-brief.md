# InterPositive research and ShotLock build brief

Prepared for Scott Hardie  Research date: October 2, 2026, America/Toronto
Status: researched opportunity and implementation specification. No application, model training, performance benchmark, partnership, or outreach has been executed. ShotLock is a working name; naming availability has not been checked.

## Recommendation

Develop ShotLock: an independent toolkit that converts an approved edit request into measurable preservation constraints and gives a filmmaker evidence about what an AI edit changed. Its first use case should be object removal from existing footage, evaluated alongside the surrounding cut.

The proposition is concrete: change the requested part of a shot, identify unintended changes, preserve the source and revision history, and leave acceptance to the filmmaker. Build one complete, inspectable workflow before expanding into model training or studio-wide automation.

This fits Scott's combination of customer-facing architecture, integration work, local AI infrastructure, and practical prototyping. Credibility will depend on learning real editorial and VFX workflows with practitioners, especially color management, frame accuracy, and review conventions.

## Public evidence and its limits

| Evidence | Verified observation | Limit |
|---|---|---|
| Netflix acquisition announcement | Netflix announced the acquisition on March 5, 2026. The team joined Netflix; Affleck became a senior advisor. The announcement describes controlled soundstage data and filmmaker control. | No public implementation or benchmark accompanies these claims. |
| Bloomberg Live interview excerpt and transcript | Affleck describes adapting existing open video models with cinematic training, followed by discrete production-specific models whose learning remains proprietary to filmmakers. | Last layer does not identify a precise neural-network module, training recipe, or released checkpoint. |
| US12322036B1 | The disclosure discusses filmmaking metadata, LiDAR, and transfer learning. | A patent describes proposed embodiments; it is not a verified account of the deployed system. |
| US12511837B1 | The claims describe paired comparisons for visual styles and feedback refinement. | Do not infer a specific commercial model architecture or proven results. |
| US12511904B1 | The disclosure concerns captioner training for cinematic elements and metadata. | A disclosure does not establish deployment or accuracy. |
| Netflix VOID repository | Public implementation and checkpoints are available. The quick start specifies 40 GB or more GPU memory, and the repository invites community demonstrations. | VOID should not be represented as InterPositive's production model. |
| VOID paper | The research targets object removal and associated physical interactions using a vision-language model and video diffusion. | Plausible counterfactual motion does not establish fidelity to every director's intention. |
| Netflix specialist job description | Responsibilities cover inference execution, repeatable runs, output review, and quality control. | Listing availability can change; it is evidence of operational needs, not a guaranteed opening. |
| Jian Ren's personal site | He identifies himself as Netflix's Head of Creative Tech Research and InterPositive's former founding chief science officer. | This identifies a relevant technical audience; it does not imply interest in an unsolicited proposal. |

The public material supports a layered adaptation strategy. It does not disclose the exact base checkpoint, which weights are trainable, whether LoRA is used, production training costs, data volume per project, or the internal agent architecture. A system that runs multiple ML tools is not automatically an autonomous agent.

Distinguish proprietary control from several different technical properties: access to assets, permission to perform a particular edit, access to weights, isolation of training data, retention policies, and approval authority. Each needs its own enforcement and evidence.

## Why this adjacency makes sense

My strategic interpretation is that production-specific adaptation makes models more useful but multiplies the number of combinations a production must trust. Every checkpoint, conditioning asset, mask, sampler, preprocessing step, and revision can affect the result. A workflow that records these combinations and catches unwanted changes can be useful even as the underlying generator improves.

The important distinction is between a pleasing image and an acceptable edit. A beautiful shot can still alter an actor's expression, move a prop, reverse an eyeline, change a logo, shift a cut's timing, or introduce a new color mismatch.

The proposed commercial value is less review effort, fewer avoidable render iterations, and faster reproduction of accepted versions. These are hypotheses to validate with editors and post-production teams. There is no evidence here that InterPositive lacks internal quality-control tools.

## Adjacent options

| Candidate | Fit for Scott | Demonstrability | Main obstacle | Decision |
|---|---|---|---|---|
| ShotLock preservation review and run evidence | Strong integration and product fit | Real clips, localized findings, reproducible reports | Calibrating useful checks without distracting false alarms | Build first |
| Dailies preparation and adaptation registry | Strong infrastructure fit | Dataset manifests and checkpoint lineage | Access to representative production data and competition with internal tools | Add after pilot demand |
| Lower-memory VOID inference work | Strong local-infrastructure interest | Reproducible quality, runtime, and memory comparison | Optimization can degrade quality; hardware validation required | Useful upstream contribution if a real improvement emerges |
| New cinematic foundation model | Weak initial economics | Difficult to prove independently | Compute, data, research depth, distribution | Defer |
| General multi-agent filmmaking suite | Broad but diffuse | Easy to demonstrate superficially | Crowded scope and weak evidence of unique value | Defer |

## Existing work to build on

Runway already offers controlled editing through Aleph and Edit Studio. Autodesk offers editable scenes and creative control in Flow Studio. A generic editing interface would compete directly with these products.

Evaluation is also established. CoVEBench, OmniEdit-Bench, and FiVE-Bench address editing, preservation, and consistency. Credit and evaluate relevant methods rather than claiming to invent these concepts.

The proposed distinction is a production workflow around explicit protected content, neighboring shots, human-approved instructions, revision history, and evidence that can be handed back to editorial. This is a product hypothesis, not an assertion that no existing tool covers it.

## The first demonstration

Use an original, licensed three-shot scene, with written permission for the demonstration and any model adaptation. Include a distracting background object, a protected foreground performance, and a prop whose position is visible across two shots.

The filmmaker asks to remove only the distracting object while retaining the foreground performance, camera movement, cut timing, and production sound. The interface converts that request into a draft specification. The filmmaker reviews the editable region, protected regions, affected interactions, and priorities before rendering.

Show two kinds of examples separately:

1. Actual model outputs, including good and poor results, labeled with the exact model, settings, and run history.
2. Deliberately injected defects used to validate detectors, labeled as test fixtures. These may include one duplicated frame, an altered audio track, or a localized prop change.

The reviewer sees the source and candidate synchronized to the same frame, with an overlay showing the approved edit area. Findings point to specific frame ranges. An uncertain finding asks for review rather than claiming that the model has established creative correctness.

The demonstration should end with a filmmaker selecting a candidate and exporting a review package. Include an unsuccessful run and explain the reason it was not accepted. No metric should be presented as a guarantee that performance or meaning is unchanged.

### Ninety-second demonstration outline

| Time | Screen | Message |
|---|---|---|
| 0–15 seconds | Three-shot scene and director's request | Establish the requested edit and what must remain. |
| 15–30 seconds | Approved regions and constraints | Show that intent becomes inspectable before rendering. |
| 30–55 seconds | Two actual candidates with frame-level findings | One succeeds at removal but creates an unwanted change. |
| 55–75 seconds | Source comparison and adjacent shot | Show the evidence that makes the issue worth reviewing. |
| 75–90 seconds | Human approval and exported record | Demonstrate a usable handoff with full revision history. |

## Minimum product specification

### Intent record

Each approved request contains a project identifier, shot identifier, source digest, frame range, rational frame rate, requested operation, allowed edit region, allowed consequence region, protected content, audio policy, reference shots, revision number, and approver.

The allowed consequence region is essential. Removing an object may legitimately require changing a shadow or an interacting object. A preservation checker that treats every changed pixel as a failure would reject correct results.

Separate hard constraints from review signals:

- Hard: source identity, authorization scope, output duration, frame count, audio retention policy, and reproducible configuration capture.
- Review signals: background drift, prop motion, expression change, lighting mismatch, eyeline concerns, or physical plausibility.

An LLM can help parse language and suggest checks. It cannot silently expand the authorized edit area or declare an uncertain creative requirement satisfied.

### Run record

Record source and conditioning digests, model and adapter identifiers, checkpoint digest, seed, sampler, inference parameters, dependency versions, hardware, precision, preprocessing transforms, start and finish times, exit state, generated media digest, measured cost, and reviewer decisions.

Reproducibility means the run can be reconstructed. Bit-identical output across hardware or nondeterministic kernels is a separate property and must be reported honestly.

### Review report

Every finding should include the constraint it refers to, the comparison method, frame range, affected region, severity, confidence or uncertainty, supporting images, and a path to inspect the source and candidate. Reviewers can mark it actionable, acceptable, or a false alarm.

Provide a summary of missing checks. A check that did not run must not appear as passed. Store results under immutable run identities so a retry cannot overwrite evidence from an earlier version.

### Architecture

Start with Python analysis tools, a small API, and a browser review interface. Keep source media and inference workers on a controlled workstation or private environment. A public demonstration can use explicitly cleared sample assets.

Use FFmpeg and ffprobe for decoding and metadata inspection; add computer-vision methods only where they improve the review task. Keep inference backends behind a capability interface. The first backend can use VOID where resources and licensing permit. Also support importing existing renders, which makes the reviewer useful without live generation.

Suggested entities: Project, Asset, Shot, IntentRevision, Run, Finding, ReviewDecision, and Export. Assets are referenced by immutable digests. Runs refer to specific intent revisions. Human decisions refer to both a candidate digest and the reviewed intent revision.

### Processing flow

1. Validate the source and project permissions.
2. Draft the edit specification and require filmmaker approval.
3. Validate backend capability, input formats, masks, and frame ranges.
4. Submit a bounded render job or import a candidate.
5. Normalize source and candidate for comparison, recording every transform.
6. Run deterministic checks and calibrated review detectors.
7. Present evidence; permit a human-approved retry.
8. Export the selected revision and its review record.

The agent's role is operational: choose an available backend, prepare an approved job, run checks, explain failures, and propose a bounded retry. Enforce retry limits and compute budgets outside the language model. Publication, delivery, new training jobs, and expanded edit permissions require their own authorized transitions.

For later multi-project deployment, isolate assets, checkpoints, caches, queues, and logs by project. Restrict worker credentials to assigned assets. Do not transmit private media to a hosted vision model without explicit project permission. Record model and dataset license information separately from contributor permissions.

### Editorial handoff

Use OpenTimelineIO for shot timing, references, and markers where appropriate. OTIO references external media; it is not a substitute for copying or packaging that media. Validate the actual target editor and adapter rather than promising universal compatibility.

For the first release, export a self-contained HTML review report, structured JSON findings, CSV issue list, selected media, and an OTIO timeline when validated. A later Nuke or production-tracking integration should follow a real pilot requirement.

Treat color as part of the input contract. Record source color space and transforms. Preserve original source media and handle analysis proxies separately from finishing outputs. The first release can honestly support a narrow, declared SDR workflow; do not claim full ACES or EXR production support until it is verified.

## Evaluation protocol

Build a small, cleared dataset before setting headline accuracy targets. Aim for approximately 20 short source clips spanning static and moving cameras, occlusion, lighting variation, protected text, interacting objects, and varied edit-region sizes. This is a planning target, not an existing dataset.

Group clips by scene into development and held-out evaluation splits. Adjacent shots from the same scene should not leak between those splits. Calibrate thresholds on development data, freeze them, and then run the held-out evaluation.

Evaluate against both a simple frame-difference baseline and selected established editing metrics. Report disagreements with human reviewers, false alarms, misses, and unsupported cases. An unchanged video is an important baseline: perfect preservation with no requested edit completed is still a failed task.

| Dimension | Example method | Limit to expose |
|---|---|---|
| Media integrity | Frame count, duration, rational frame rate, decode validity | Variable-frame-rate and intentional retiming need explicit handling. |
| Edit completion | Human labels plus task-specific region checks | Disappearance alone does not prove a convincing replacement. |
| Protected-region stability | Registered region comparison | Compression, grain, relighting, and camera motion can cause false alarms. |
| Temporal stability | Track continuity and flow residuals | Occlusion and cuts can invalidate comparisons. |
| Text and prop retention | OCR or tracked-object comparisons | Detector confidence may be poor; route uncertainty to review. |
| Performance preservation | Protected performance crops and blinded human review | Similarity scores do not establish equivalent acting or identity. |
| Adjacent-shot continuity | Scene-specific prop and timing checklists | Narrative meaning and intentional discontinuity require human judgment. |
| Audio preservation | Track mapping and decoded audio comparison | Container hashes can differ even when retained audio is equivalent. |
| Operational value | Reviewer minutes, accepted revisions, render attempts, cost | A small study does not justify universal cost-saving claims. |

For the first pilot, use at least two experienced reviewers and preserve disagreements. Compare review with and without the tool on counterbalanced tasks. Report sample sizes and task composition; do not market a single aggregate score as production readiness.

## Verification and release gates

- A source/candidate frame mismatch is detected and localized without silently resampling the evidence.
- The system distinguishes allowed interaction changes from protected content.
- Missing or failed detectors produce an explicit unavailable result.
- A worker interruption leaves a resumable or clearly failed job and retains prior evidence.
- A retry receives a new run identity and cannot overwrite the prior candidate.
- Project A cannot read Project B's source, adapter, cache, or findings in a multi-project deployment.
- Approval of one revision cannot authorize a different media digest or an expanded edit.
- Reports open without the application running and disclose all analysis transforms.
- Editor handoff preserves the tested shot ranges, rate, and references.
- No claims of quality improvement are published until measured on held-out footage.

Application linting, type checks, builds, and automated integrity tests should accompany implementation. The decisive smoke test is the complete filmmaker flow: approve an intent, process real footage, inspect evidence, reject a flawed version, approve a revised candidate, and open the exported package.

## Hardware and spending plan

Use Scott's EPYC machine for media preparation, queues, orchestration, and analysis workloads that fit its available accelerators. Use the HX370 for development and review. Validate model-specific inference on each GPU before relying on it.

The documented VOID quick-start memory requirement exceeds any single GPU in the listed V100 16 GB, P40 24 GB, and RTX 3060 12 GB setup. Their VRAM does not simply become a shared allocation. Begin with imported renders and lightweight analysis; reserve rented compute for a small number of actual demonstrations if needed. Quantization and offloading are experiments until output quality, latency, and memory have been measured.

Define a compute budget before starting jobs. For initial planning, a ceiling of CAD 300–500 is a proposed constraint, not a quote or spending authorization. Stop when the ceiling is reached and retain run evidence. No hardware purchase is justified before a filmmaker confirms that the review workflow is useful.

## Four-week implementation plan

This is a proposed focused prototype schedule, subject to footage availability and practitioner feedback.

| Week | Deliverable | Completion evidence |
|---|---|---|
| 1 | Cleared scene, intent schema, source/candidate ingestion, synchronized viewer | Real media can be reviewed at exact frames; missing data is handled visibly. |
| 2 | Protected-region checks, run manifests, HTML/JSON reports | Labeled defects and actual render issues can be traced to evidence. |
| 3 | One real inference integration or imported-render pipeline; bounded retry; editorial export | End-to-end demonstration includes a failed candidate and a human-approved handoff. |
| 4 | Held-out evaluation, practitioner review, documentation, short demo | Published methodology distinguishes test fixtures, model outputs, limitations, and measured outcomes. |

The minimum release is a working review SDK and demonstration, not a new foundation model or a studio-wide SaaS platform. Adaptation management and a second backend follow only when the first workflow demonstrates value.

## Getting noticed

Make the first public package easy for an engineer and a filmmaker to inspect: repository, cleared clips, exact run manifests, frame-level reports, a short demonstration, and a concise technical note explaining failures as well as successes.

An appropriate route is to contribute something genuinely useful around Netflix's public VOID project, respecting its contribution practices. A tool can be submitted for community consideration once it works; a README mention is neither promised nor a partnership.

For InterPositive, direct the technical proposition toward Creative Technology engineering and research. Jian Ren is one publicly identifiable relevant leader. A concise approach should ask for feedback on the review problem, with demonstrated evidence attached. Do not imply a private InterPositive integration, model access, affiliation, or endorsement.

Scott's position should emphasize translating creative requests into dependable production workflows. The job material also makes the experience gap clear: media formats, GPU inference debugging, and time-sensitive production support. Build proof of those skills; do not substitute existing enterprise experience for claimed feature-film credits.

Use the Toronto Film School connection as a possible introduction to a willing editor or filmmaker, subject to their interest and permission. It is a way to learn and validate the workflow, not an assumption of access to student or institutional media.

## Commercial path and decision criteria

Sell a narrow paid pilot around one recurring review problem if practitioners confirm value. Candidate customers include post-production houses, commercial production teams, and organizations adapting video models for private projects. Netflix is a potential audience, not the only viable customer.

Start with scoped integration and evaluation work. A managed private deployment may later support recurring revenue. Keep the review specification and SDK open where that aids adoption; charge for integration, deployment, workflow support, and private operations. Do not charge for a public generator without understanding all applicable model and asset licenses.

Measure unit economics per accepted shot, not just per inference call:

value = avoided review and rework cost − added compute, integration, operation, and review cost.

Illustrative arithmetic only: saving 10 reviewer minutes across 300 shots is 50 hours. At an assumed CAD 100 per reviewer-hour, that is CAD 5,000 before added costs. Actual pilot data must establish both the minutes saved and the relevant labor cost.

Continue if reviewers repeatedly find the evidence useful, false alarms remain manageable, and at least one team wants to apply it to another project. Narrow or stop if the report creates extra work, equivalent tooling already covers the use case, or the system needs confidential assets it cannot access. A measured negative result still strengthens a technical portfolio when explained honestly.

The first commitment should be one approved edit, one real scene, one actionable review report, and one clean editorial handoff. That gives the eventual conversation a concrete basis.
