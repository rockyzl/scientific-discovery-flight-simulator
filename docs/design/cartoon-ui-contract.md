# Cartoon CV UI — frozen implementation contract

Date: 2026-07-21  
Status: reconciled design; awaiting independent QA design verdict  
Inputs: scientific-flow review, UX proposal, usability/risk review

## Decision

Build one technical-cartoon workbench followed by one clearly separate synthetic planner replay.
The page teaches this sequence without requiring body-text reading:

```text
published formulation → three-electrode cell ⇄ potentiostat → published CV

================ PHYSICAL CONTEXT ENDS HERE ================

one unnamed virtual sample → planner request → validator → scalar synthetic response
→ belief update → continue or stop
```

This is an implementation contract, not another list of ideas. Text, IDs, states, branches,
interaction semantics, non-claims, and acceptance tests marked **MUST** are frozen until QA either
approves them or records a blocking defect.

## Reconciled choices

The three reviews agree on a persistent physical scene, permanent provenance, explicit
real/synthetic separation, formulation-only sample replacement, parallel planner comparison,
progressive disclosure, and a complete nonanimated path.

Where proposals differed, this contract chooses:

1. **Seven real steps, not five.** The five-state UX sketch was compact, but the scientific review's
   seven states make fresh, same-formulation, and changed-formulation paths testable without hiding
   removal or loading inside narration.
2. **No autoplay on page load.** The full causal chain is visible immediately; motion starts only
   after the visitor presses Replay/Play. This satisfies the five-second view without creating a
   hardware-control or live-measurement impression.
3. **Persistent scene, not seven illustrations.** One SVG keeps the bottle, sample tag, cell,
   electrodes, potentiostat, signals, sweep, and CV display spatially stable. Steps change state and
   emphasis, not object identity or position.
4. **Buttons select samples; sliders scrub replays.** Bottles are not free-drag objects. Native range
   controls are the only required drag interaction, with buttons and keyboard equivalents.
5. **All three planners stay comparable.** Desktop uses three lanes; narrow screens use one detailed
   tab at a time plus a persistent three-row comparison summary. No composite winner is declared.
6. **The synthetic output is scalar.** It is unitless normalized response versus scan rate, never a
   generated CV curve and never current density.

## 1. First viewport contract

At a loaded desktop viewport and at 390 CSS px, the first viewport **MUST** show, without scrolling:

- the page title `How a CV experiment becomes evidence`;
- one compact provenance key:
  - `◆ REAL — published, author-processed CV data`;
  - `◇ SYNTHETIC — saved policy replay, not a lab measurement`;
- the selected bottle with full visible formula and `pH 3.5`;
- one transparent cell with visible `WE`, `RE`, and `CE` labels;
- the cell connected to a box labeled `Potentiostat`;
- `Potential command →` from potentiostat to WE/RE control;
- `← Current signal` from the WE–CE circuit to the instrument/display;
- a triangular sweep strip labeled `0 → −1.2 → 0 V · 10 mV/s`;
- a small real CV plot with both axes and the badge
  `PUBLISHED, AUTHOR-PROCESSED EXPERIMENTAL DATA`;
- `Illustrated replay — no hardware connection` adjacent to the primary action;
- the action `Replay published CV workflow`;
- a small, noninteractive planner preview below a visually closed separator:
  `Fixed Grid · regular`, `Information Gain · targeted`, `Random · scattered`.

Run hashes, event JSON, full metrics, definitions, and long source notes **MUST NOT** occupy the
first viewport. The DOI and license link may be in a compact source line adjacent to the real plot.

The five-second mental model is:

> A named electrolyte is used in a three-electrode CV experiment. A potentiostat sweeps working-
> electrode potential relative to the reference and records current. The visible curve is a
> published result, while the policy comparison is a separate saved simulation.

No motion starts before user input.

## 2. Persistent real-lab SVG contract

The implementation **MUST** use one persistent SVG scene. Objects may change attributes, classes,
labels, opacity, or revealed subparts, but state transitions **MUST NOT** replace the whole scene or
change these IDs. IDs are public implementation/test hooks and must remain unique in the document.

| Stable ID | Persistent object | Required meaning |
| --- | --- | --- |
| `real-lab-scene` | root SVG/group | explanatory schematic; not to scale |
| `real-sample-shelf` | three source sample controls/cards | published formulation choices |
| `real-sample-base` | base-electrolyte bottle/card | exact composition from source |
| `real-sample-glycine` | glycine bottle/card | exact composition from source |
| `real-sample-lactic` | lactic-acid bottle/card | exact composition from source |
| `real-sample-record` | sample/source clipboard | composition, pH, provenance |
| `real-waste-tray` | generic removal vessel | visible only for different-formulation branch |
| `real-rinse-tool` | generic preparation/rinse symbol | says `protocol-defined`; no invented solvent |
| `real-cell` | electrochemical cell | one persistent physical cell |
| `real-cell-liquid` | current liquid fill | derives only from loaded sample state |
| `real-cell-sample-tag` | persistent sample identity | exact loaded formulation or `EMPTY / FRESH START` |
| `real-electrode-we` | working electrode | controlled potential / measured-current electrode |
| `real-electrode-re` | reference electrode | potential reference; not main current path |
| `real-electrode-ce` | counter electrode | completes main current path |
| `real-lead-we` | WE lead | potentiostat connection |
| `real-lead-re` | RE lead | reference-sense connection |
| `real-lead-ce` | CE lead | counter/current connection |
| `real-potentiostat` | instrument box | applies potential program and measures response |
| `real-potential-command` | directional command path | control of WE potential relative to RE |
| `real-current-signal` | directional signal path | measured current through WE–CE circuit |
| `real-sweep-waveform` | triangular potential-time strip | fixed source program `0 → −1.2 → 0 V` |
| `real-sweep-cursor` | acquisition-order marker | forward/return replay position |
| `real-scan-rate` | setting/readout | `10 mV/s` for published reference |
| `real-cycle-counter` | cycle state | `1 / 2`, then `2 / 2` |
| `real-cv-display` | plot frame | experimental current density vs potential |
| `real-cv-path` | selected published curve | existing author-processed data points only |
| `real-cv-cursor` | highlighted acquired point | synchronized to replay position |
| `real-provenance-badge` | plot-adjacent badge | permanent real-data label |

The SVG root needs an updated `<title>` and `<desc>` for the current formulation and step. Every
interactive SVG concept must also have a native HTML control next to the drawing; pointer-only SVG
hotspots are not sufficient.

The scene **MUST NOT** add pumps, robotic arms, gas lines, molecule drawings, precise volume,
precise electrode spacing, a rinse solvent, polishing, temperature, purge, equilibration duration,
electrode area, or iR-compensation details unless a later verified source explicitly supplies them.

## 3. Sample state machine

State is determined from `loadedSampleId`, `selectedSampleId`, and whether the cell has ever been
loaded in the current reset cycle. Sample buttons choose; they do not immediately redraw the curve
as if a measurement occurred.

### Branch A — fresh cell

Condition: `loadedSampleId` is empty.

```text
select → fresh-start decision → removal/preparation skipped → load and identify
→ assemble/check → replay sweep → retain published record
```

Required visible messages:

- `EMPTY / FRESH START`
- `No previous sample to remove`
- Step 3: `SKIPPED — NO PREVIOUS SAMPLE`
- Step 4 loads the selected formulation and writes its exact identity to
  `real-cell-sample-tag`.

The scene must not animate removal, disposal, rinsing, or an old-sample tag.

### Branch B — same formulation

Condition: `selectedSampleId === loadedSampleId`.

```text
select → same-formulation decision → removal/preparation skipped → loading skipped
→ connection/readiness check → replay sweep → retain published record
```

Required visible messages:

- `SAME LOADED FORMULATION — CONDITION REPLAY`
- `Same formulation → keep sample loaded`
- Step 3: `SKIPPED — SAME FORMULATION`
- Step 4: `SKIPPED — ALREADY LOADED`

The liquid, bottle identity, sample tag, and cell contents remain visibly fixed. The wording must
not claim `identical physical state`; history, time, surface conditioning, or degradation may
matter. The current published data are all at `10 mV/s`; this branch must not invent a real
multi-scan-rate series.

### Branch C — different formulation

Condition: both IDs exist and differ.

```text
select → different-formulation decision → stop prior replay → remove previous electrolyte
→ generic protocol-defined preparation → load and identify selected formulation
→ assemble/check → replay sweep → retain published record
```

Required visible messages:

- `NEW FORMULATION — SAMPLE REPLACEMENT REQUIRED`
- `Different formulation → remove, prepare, and load before measurement`
- `Previous sample removed`
- `Cell/electrodes prepared — exact cleaning follows the laboratory protocol`

The old sample tag becomes `REMOVED` before the new liquid or identity appears. The selected
published curve can become active only after Step 4 completes. A previous curve may remain only
when the visitor explicitly enables `Compare previous formulation`, and must be labeled as a prior
record rather than a mixture.

## 4. Seven real steps and exact visible states

Exactly seven top-level steps remain visible in the stepper. Every step exposes a text status plus
an icon; color is supplemental. Allowed status strings are `PENDING`, `ACTIVE`, `DONE`, and the
branch-specific `SKIPPED — …` strings below.

| # | Exact step label | ACTIVE state visible in persistent scene | Completion/branch state |
| --- | --- | --- | --- |
| 1 | `1 · Select formulation` | chosen source bottle outlined; sample record shows exact formula and pH; cell shows current loaded identity or fresh state | `DONE — FORMULATION SELECTED`; narration `Selection does not run an experiment yet` |
| 2 | `2 · Check sample change` | side-by-side selected and loaded tags; branch route is highlighted | `DONE — FRESH START`, `DONE — SAME FORMULATION`, or `DONE — REPLACEMENT REQUIRED` |
| 3 | `3 · Remove and prepare` | only different branch shows old tag moving to waste then generic preparation symbol | different: `DONE — PREVIOUS SAMPLE REMOVED AND CELL PREPARED`; fresh: `SKIPPED — NO PREVIOUS SAMPLE`; same: `SKIPPED — SAME FORMULATION` |
| 4 | `4 · Load and identify` | only fresh/different branches reveal selected liquid and attach exact sample tag | fresh/different: `DONE — SAMPLE LOADED AND IDENTIFIED`; same: `SKIPPED — ALREADY LOADED` |
| 5 | `5 · Assemble and check cell` | WE/RE/CE and leads highlight in order; ready card shows `Cell assembled`, `Connections checked`, `Protocol-defined equilibration / reference check` | `DONE — CELL READY`; no unsupported duration or numeric threshold |
| 6 | `6 · Sweep potential and record current` | waveform and CV cursors move together in acquisition order; direction, potential and current density update; counter shows cycle 1 then cycle 2 | `DONE — TWO CYCLES RECORDED`; visible input `working-electrode potential vs Ag/AgCl/KCl (sat'd)` and output `total current density / mA cm⁻²` |
| 7 | `7 · Retain the published curve` | full second-cycle curve, axes, sample, protocol and provenance are visible | `DONE — AUTHOR-SELECTED SECOND CYCLE SHOWN`; labels `Published, author-processed second-cycle curve` and `Not raw data` |

Step 7 must say that second-cycle retention is the choice documented for this source dataset, not a
universal CV rule. The permanent source area includes Engler, Stich, Baumer, Bund; DOI
`10.5281/zenodo.15730784`; and `CC BY 4.0`.

## 5. Non-collapsible boundary

Between the last real object and the first synthetic object, render a full-width boundary that is
always visible, focusable as a heading, and never a disclosure/accordion:

```text
PHYSICAL CONTEXT ENDS HERE

Above: published, author-processed experimental curves from named formulations at 10 mV/s.
Below: a separate synthetic response-scaling benchmark using one unnamed virtual sample.
The published curves are context only. They do not fit, train, calibrate, validate, or supply
observations to the synthetic benchmark.
```

There must be no visual data-flow arrow crossing this boundary. Background, border pattern, icons,
units, and palette all change across it. The synthetic section and every synthetic plot/result/
failure must repeat `SYNTHETIC BENCHMARK` or `SYNTHETIC` locally; a top-of-page disclaimer alone is
not sufficient.

## 6. Synthetic scene and five-state loop

The synthetic region uses a dashed/blueprint visual grammar and the permanent label:

`SYNTHETIC TEACHING EMULATOR · SAVED REPLAY · NOT A LAB MEASUREMENT`

Every planner lane starts from the same public world contract, attempt/measurement budgets, and
committed world/noise/failure scenario, but uses a fresh environment instance and isolated planner
random stream. Lanes never share observations or a consumable liquid state.

Stable region IDs:

- `synthetic-scene`
- `synthetic-virtual-sample`
- `synthetic-response-plot`
- `synthetic-planner-fixed-grid`
- `synthetic-planner-information-gain`
- `synthetic-planner-random`
- `synthetic-validator`
- `synthetic-virtual-instrument`
- `synthetic-belief-bars`
- `synthetic-budget-status`
- `synthetic-post-run-reveal`

The exact per-request loop is:

| # | Exact state label | Required state/evidence |
| --- | --- | --- |
| 1 | `1 · SELECT RATE` | planner proposes `5–500 mV/s`; show chosen rate and saved rationale; Fixed Grid is predetermined, Information Gain is belief-dependent, Random is legal random selection |
| 2 | `2 · VALIDATE REQUEST` | public range gate accepts or blocks; block consumes attempt cost only and creates no observation; no hidden truth is visible |
| 3 | `3 · EXECUTE VIRTUAL OPERATION` | accepted request returns one scalar, unitless normalized response or recorded synthetic timeout/saturation/reference-check flag; calibration is explicitly `CALIBRATION OPERATION`; failed execution consumes attempt and executed-operation cost but creates no fake zero point |
| 4 | `4 · UPDATE BELIEFS` | successful observation updates bars from `beliefs_before` to `beliefs_after` for `diffusion-like`, `surface-like`, `mixed toy model`; label `Planner belief within three predefined synthetic models` |
| 5 | `5 · CONTINUE OR STOP` | show attempts, executed-operation cost, confidence and recorded stop reason; stopped lane freezes; hidden label appears only after all verified completed artifacts load |

The plot title is exactly `Normalized response vs scan rate — synthetic teaching model`. The y-axis
is `Unitless normalized response`; it must never say `current`, `current density`, `mA`, or
`mA cm⁻²`. A successful request adds one dot; rejected and failed events use status markers but no
response dot.

Desktop shows three simultaneous lanes. At the same global event index, each lane displays its own
recorded event or `STOPPED`. Final cards use the same four rows: `Choice pattern`, `Attempts`,
`Executed-operation cost`, `Conclusion`. Counts must come from verified artifacts; do not hard-code
illustrative values. No podium, trophy, composite score, or universal winner language is allowed.

## 7. Replay controls and interaction semantics

### Real workflow controls

- Native buttons: `Previous step`, `Replay`/`Pause`/`Resume`, `Next step`, `Reset lab`.
- Native range: `Replay position, 0 to 100 percent` for Step 6.
- The range represents acquisition order, not voltage; the same potential occurs on forward and
  reverse legs.
- Scrubbing synchronously updates waveform cursor, direction, potential, current density, revealed
  published points, and CV cursor.
- `Reset lab` pauses timers, clears prior interaction state, sets cell to `EMPTY / FRESH START`,
  retains the default selected formulation as a choice, and returns to Step 1. It does not delete or
  hide the published reference plot/source record.

### Synthetic replay controls

- Native buttons: `Previous event`, `Play all`/`Pause`/`Resume`, `Next event`,
  `Reset synthetic replay`.
- Native range: `Campaign event, 0 to N`.
- A single global event position advances all three isolated lanes. A completed lane remains
  `STOPPED`; other lanes continue.
- `Reset synthetic replay` returns all lanes to their verified event-zero states and does not alter
  any real-lab state.

### Shared playback rules

- No autoplay on load.
- Play is user initiated. Pause is always visible while playing.
- A sequence longer than five seconds supports Pause, Resume, Previous/Next, and Reset throughout.
- Any manual sample/planner choice, scrub, Previous/Next, or Reset pauses active playback.
- Playback pauses when the document becomes hidden and does not silently resume on return.
- Playback never scrolls the page or moves keyboard focus.
- Controls that are temporarily unavailable use a real `disabled` state and a visible explanation.
- No control text may say `Start instrument`, `Run potentiostat`, or unqualified `Run experiment`.

## 8. Keyboard, screen-reader, and live-region contract

- Story-order tab sequence: real sample group → real step controls → sweep scrubber/electrode help
  → boundary → synthetic planner tabs/lanes → campaign controls → audit details.
- Sample selection uses native radio/buttons with visible selected state. Arrow keys may move within
  the group; Tab leaves the group.
- Planner detail uses the WAI-ARIA tab pattern: Left/Right moves, Home/End jumps, Enter/Space
  activates when selection does not follow focus.
- Native ranges support Arrow, Page Up/Down, Home, and End and have adjacent current-value text.
- Every primary range also has Previous/Next buttons; precise drag is never required.
- WE/RE/CE help uses native buttons. Enter/Space opens; Escape closes and returns focus.
- Every dynamic SVG has a current `<title>`, `<desc>`, and equivalent text summary outside SVG.
- Tooltips, units, source, state, and failure meaning are never hover-only.
- Focus indicators remain visible and unobscured, with at least 3:1 contrast.

Use one polite, atomic live region with stable ID `cartoon-status-live` for meaningful user-triggered
transitions only:

- formulation selected and branch chosen;
- sample removed/loaded;
- real step changed or replay completed;
- request blocked or virtual operation failed;
- planner stopped; and
- synthetic replay completed.

It must not announce every curve point, scrubber tick, timer frame, belief-bar tween, or decorative
highlight. Autoplay never moves focus. The current step/event and chart summary remain readable
outside the live region, so missed announcements do not remove information.

## 9. Reduced motion

Both CSS and JavaScript **MUST** honor `prefers-reduced-motion: reduce`. The preference is evaluated
at load and listened to for changes while the page is open.

In reduced motion:

- no timer starts automatically or continues when the preference changes to reduce;
- Replay selects the current static state; visitors advance with Next, or may use
  `Show all steps` if implemented;
- removal/preparation/loading use discrete state frames;
- waveform and CV reveal update by completed segments;
- wires do not pulse, liquid does not flow, and belief bars do not tween;
- synthetic events remain fully operable manually;
- no auto-scroll or focus movement occurs; and
- sample branch, sweep direction, numeric values, costs, failures, beliefs, and stop reason remain
  available as text.

Motion is pacing, never evidence.

## 10. Responsive and zoom contract

At `320 CSS px` viewport width and at `200%` browser zoom:

- there is no page-level horizontal scrolling;
- the real scene reflows to bottle → cell → potentiostat → CV plot vertically; it is not a scaled-
  down desktop canvas;
- causal arrows remain visible and labeled;
- the loaded/selected formulation stays adjacent to the cell;
- labels remain readable and are not truncated to unexplained initials;
- controls wrap vertically and remain at least `44 × 44 CSS px`;
- the sweep/campaign range uses available width and retains buttons/current value;
- planner details become tabs, while a three-row summary keeps all policies comparable;
- audit details remain collapsed by default; and
- zoom and pinch zoom are not disabled.

If an individual chart needs internal horizontal scrolling, it must have a visible instruction and
scroll affordance; the surrounding page must still not scroll horizontally. Rotation/reflow retains
current formulation, real step, planner selection, and event state.

## 11. Exact non-claims

The following labels **MUST** be present at the relevant objects/regions:

- `Illustrated replay — no hardware connection`
- `Explanatory schematic — not to scale`
- `Published, author-processed experimental data`
- `The animation reveals saved published points; it does not generate measurements.`
- `The published curves are context only — not simulator input.`
- `Synthetic teaching emulator — saved replay, not a lab measurement`
- `One unnamed virtual sample for every scan-rate request`
- `Unitless normalized response — not experimental current density`
- `Planner belief within three predefined synthetic models`
- `Injected synthetic failure`
- `One fixed synthetic scenario/run — not evidence of a universally best planner`
- `Synthetic truth, not experimental truth`
- `No LLM, no real instrument call, no laboratory control, and no institutional endorsement.`

The UI **MUST NOT** claim or visually imply:

- that the browser controls hardware or generates the published values;
- that the published curves fit, train, calibrate, validate, or feed the synthetic benchmark;
- that a changed scan rate automatically replaces the formulation;
- that a same loaded formulation has an identical physical state over time;
- that the three published formulations form a real scan-rate series;
- that the simulator returns a full CV or experimentally calibrated current density;
- that `diffusion-like`, `surface-like`, or `mixed` diagnoses a named real formulation;
- that classification among three supplied models is open-ended mechanism discovery;
- that one CV/scaling exponent proves mechanism;
- that a belief bar is calibrated scientific certainty;
- that a failed operation is a zero response;
- that second-cycle selection is a universal CV rule;
- any unsupported cleaning, geometry, operating-condition, or apparatus detail; or
- a universal planner winner from one fixed replay.

## 12. Progressive disclosure and failure behavior

Main view contains the objects, seven states, five synthetic states, short reasons, and final
comparison. `Audit this replay` contains manifest identity, complete metrics, event ledger/hashes,
downloads, commitments, and post-run reveal.

- Real-reference loading shows silhouettes and `Loading published reference…`, never a substitute
  curve.
- Real data render only after `provenance: published_processed_experimental_data` validates.
- A real-data failure disables the real replay with a clear error; a separately valid synthetic
  replay may remain usable.
- An invalid verified synthetic bundle prevents that replay from rendering; no plausible invented
  events are substituted.
- Rejected requests consume attempt cost only and produce no observation.
- Failed executed operations consume attempt and executed-operation cost, display their exact
  injected synthetic failure/QC flag, and produce no fake point.
- Without JavaScript, static HTML preserves the first-view causal explanation, both provenance
  labels, the hard boundary, source citation, and a planner-strategy summary.

## 13. Acceptance tests and release blocks

Implementation does not pass by matching screenshots alone. QA must record evidence for all tests.

### A. Deterministic state tests

1. Stable-ID test: every ID in Sections 2 and 6 exists exactly once before and after every state
   transition; the root scene is not replaced.
2. Fresh branch: Reset → select formulation → replay shows Step 3 skipped, Step 4 loaded, and never
   shows removal/rinse of an old sample.
3. Same branch: complete/load one formulation → choose it again → replay shows Steps 3 and 4 skipped;
   sample tag/liquid identity never changes.
4. Different branch: load A → select B → replay orders old removal/preparation before B loading and
   before B curve activation.
5. Real protocol: Step 6 shows `0 → −1.2 → 0 V`, `10 mV/s`, two cycles, reference basis, current-
   density units; Step 7 identifies the author-processed second cycle.
6. World isolation: synthetic event/scrubber/reset never changes real sample, real curve, or real
   step; real controls never change planner state.
7. Synthetic accounting: blocked, failed, calibration, successful, and stopped events render the
   correct observation/cost semantics from verified artifacts.
8. Hidden truth: it remains unavailable until all verified completed summaries permit post-run
   reveal and is still labeled synthetic after reveal.

### B. Interaction tests

1. No load-time autoplay; user Play/Pause/Resume/Previous/Next/Reset work for both replays.
2. Manual action and hidden-tab event pause playback; return does not silently resume.
3. Sweep scrubber follows acquisition order and distinguishes forward/return at repeated potential.
4. Campaign scrubber advances all lanes by comparable event index and freezes stopped lanes.
5. Reset lab reaches fresh state without removing source data; synthetic reset is independent.
6. No required action depends on drag, hover, high pointer precision, or motion.

### C. Accessibility and responsive tests

1. Keyboard-only completion of sample selection, all seven real steps, electrode help, all planner
   comparisons, all five synthetic states, and audit access.
2. Screen-reader check confirms meaningful names/states, chart summaries, and restrained live-region
   announcements without frame-by-frame noise.
3. Reduced-motion enabled before load and toggled during play: timers stop; manual path retains all
   evidence.
4. `320 CSS px`, 390 px, and `200% zoom`: no page-level horizontal scroll; no clipped provenance,
   units, labels, focus, or controls; targets are at least 44 px.
5. Contrast: body text 4.5:1, large text/key graphics 3:1, focus 3:1.
6. Grayscale and common color-vision simulation: real/synthetic, planners, hypotheses, and
   success/failure remain distinguishable by text, icon, shape, and line pattern.

### D. Comprehension tests

Five-second test: at least five first-time visitors, at least two without electrochemistry
background; test desktop and 390 px. At least 80% identify CV/electrochemical potential sweep,
changed potential/condition and measured current, and coexistence of real reference plus simulation;
100% must reject the idea of live hardware control.

Thirty-second test: each participant answers at least 6/7 and every question reaches 80% overall:

1. the physical named all-iron RFB formulation;
2. WE potential relative to RE is swept and current/current density is recorded;
3. only formulation switching triggers remove/prepare/load;
4. the full CV is published and author-processed;
5. the synthetic benchmark is independent and receives no real-CV input;
6. Fixed Grid is predetermined, Information Gain adapts to beliefs, Random samples legally at
   random; and
7. one synthetic replay proves neither a universal planner winner nor a real formulation mechanism.

Questions 4 and 5 are safety-critical: one participant attributing synthetic output to the
published experiment or describing the real CV as benchmark input fails the test round.

### E. Immediate release blocks

Block release if any of the following occurs:

- a tester believes the browser is controlling real hardware;
- real and synthetic plots share an unqualified unit, legend, or visual grammar;
- an arrow crosses the boundary as real-to-synthetic data flow;
- scan-rate change triggers remove/prepare/load;
- a synthetic conclusion is attached to a named real formulation;
- reduced-motion mode continues automatic timers;
- provenance, state, unit, or failure meaning exists only in color, hover, or motion;
- keyboard/mobile users cannot complete sample selection, step progression, and planner comparison;
- an invalid source or synthetic bundle is replaced by plausible-looking data; or
- any exact non-claim in Section 11 is absent from its relevant region.

## QA gate

The design team recommendation is **APPROVE WITH CONDITIONS**. The implementation remains blocked
until an independent QA reviewer evaluates this contract and checks `Obtain QA verdict on the
reconciled design`. Only after that verdict may the implementation checkbox be changed.
