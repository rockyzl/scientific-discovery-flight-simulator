# Demo guide

This guide describes the implemented closed-loop CV diagnosis and the two supporting experiences
that remain below it. The diagnosis follows the independently approved restricted-v1 contract; it
is a synthetic benchmark, not a diagnosis of a real sample or a hardware-control interface.

## Start the local review demo

First create a completed artifact directory with the CLI, then run:

```bash
python demo/serve.py --artifacts outputs/cv-demo
```

Open <http://127.0.0.1:8000>. Use `--host` and `--port` only on a trusted network. This is a small
local review server, not a production deployment and not a connection to laboratory hardware.

The server creates private diagnosis state outside the public artifact directory. Every diagnosis
API response uses `Cache-Control: no-store`; private truth, seeds, nonce, and future failure schedule
remain server-side until an explicit terminal-state reveal.

## The first screen: one closed-loop diagnosis

The main question is:

> What best explains the increase in apparent peak separation from the frozen synthetic
> healthy/control comparator to the initial abnormal synthetic CV?

Five predefined explanations begin with equal working belief: slow kinetics, uncompensated
resistance, reference drift, electrode fouling, and concentration/preparation error. These are
probabilities only inside the stated five-hypothesis synthetic model.

The restricted-v1 Gaussian likelihoods are deliberately small and sharply separated. A single
successful synthetic observation can therefore produce a posterior numerically very close to
`0`/`1`. That is a limitation of this toy benchmark, not calibrated confidence that a real sample
has or does not have a mechanism. The campaign still requires its independent success, distinct-
operation, budget, and stopping gates.

On page load, the browser:

1. requests the frozen public scenario;
2. validates the closed Envelope/Payload schema and cryptographic hashes;
3. checks both 122-point comparator/trigger curves, their discrete peak summaries, units, and QC;
4. creates a new isolated campaign; and
5. renders only the server-issued beliefs, budgets, recommendation, reason, and costs.

Before replacing a verified screen, it also reconciles endpoint and campaign identity, event-hash
continuity, version transitions, attempt/measurement costs, beliefs, successful operations, latest
curve, and the full ledger against the returned State. A self-consistent object that contradicts
another object is rejected, and the previous verified screen remains unchanged.

The browser does not calculate a posterior, score actions, write a reason, choose controls, repair a
belief vector, or reconstruct a curve from peak markers.

## Running the next experiment

`Run recommended experiment` submits the exact server-issued recommendation identity and controls.
The request's idempotency identity binds the uppercase HTTP method, canonical route path, campaign
ID, request ID, and SHA-256 hash of the exact serialized request bytes.

- A valid observation may add one verified full synthetic CV or one supporting scalar.
- A timeout or QC failure is shown explicitly; it never becomes zero or a fake curve.
- A parseable 422 rejection consumes one attempt, no measurement, preserves beliefs, increments
  state version, and appears in the timeline with the server's exact reason.
- After an ambiguous network failure, the page checks campaign state and ledger, then retries only
  with the same scoped identity and exact retained bytes.
- A stale or unverifiable response leaves the previous verified screen unchanged.

The central chart always uses the backend's full arrays. A screen-reader table contains every
verified potential, current, and sweep-direction point. Scalar actions leave the last valid curve
unchanged.

## Stop and truth reveal

The server applies the frozen order: budget exhaustion, confident-diagnosis gate, then low expected
information. The browser only renders the returned terminal reason and final five-value belief
vector.

Truth is never revealed automatically. After the campaign stops, the user may open Expert & audit
details and select `Reveal synthetic benchmark truth`. The returned private payload must
cryptographically open the commitment published with the original scenario:

```text
commitment = SHA-256(JCS({
  scenario_id,
  scenario_version,
  hidden_truth,
  seed_bundle,
  reveal_nonce
}))
```

The nonce is generated once from 32 cryptographically secure random bytes for the frozen scenario
version and persists across campaigns/redeploys. Before reveal, the preimage is absent from public
responses and browser storage. After reveal, publishing it intentionally makes the completed
synthetic replay reproducible.

## Supporting measurements

Independent Ru is a simulated diagnostic action inside this benchmark. Conductivity remains a
separate provenance-controlled workflow at `/tempo/#conductivity`; it is not inferred from the CV
and is never a sixth diagnosis hypothesis.

## Supporting material below the diagnosis

The older page material remains available beneath the flagship loop and has two separate provenance
layers:

- **Real context:** published, author-processed CV data from named all-iron redox-flow-battery
  electrolyte formulations.
- **Synthetic replay:** saved policy campaigns in a transparent teaching emulator.

The real curves make the physical measurement understandable. They are not inputs to the synthetic
benchmark. The planners do not fit, train, calibrate, validate, or choose actions from the published
curves.

## What the physical experiment shows

Cyclic voltammetry uses a three-electrode cell connected to a potentiostat:

- the **working electrode (WE)** is the electrode whose potential is controlled and where current
  is measured;
- the **reference electrode (RE)** supplies the potential reference and is not the main current
  path; and
- the **counter electrode (CE)** completes the main current circuit.

The potentiostat sweeps working-electrode potential relative to the reference electrode and records
the resulting current. The curve plots current density against potential. In the published example,
the visible protocol is `0 → −1.2 → 0 V` at `10 mV/s`, with potential reported versus
`Ag/AgCl/KCl (sat'd)` and total current density in `mA cm⁻²`.

The physical scene is an explanatory cartoon, not a scale drawing. It does not establish exact
volume, geometry, cleaning chemistry, temperature, purge procedure, equilibration time, electrode
area, or iR compensation.

## The seven physical-workflow steps

The same cell, electrodes, potentiostat, sample tag, waveform, and chart stay in place while these
seven states progress:

1. **`1 · Select formulation`** — choose a named published formulation and display its exact
   composition, pH, and source record. Selecting it does not yet perform a measurement.
2. **`2 · Check sample change`** — compare the selected formulation with the formulation currently
   loaded in the cell and choose the correct branch.
3. **`3 · Remove and prepare`** — remove the prior electrolyte and perform generic,
   protocol-defined preparation only when a different formulation was previously loaded.
4. **`4 · Load and identify`** — load the selected formulation and attach its identity to the cell.
   This is skipped when that formulation is already loaded.
5. **`5 · Assemble and check cell`** — show WE, RE, CE, their potentiostat connections, and a
   protocol-defined readiness/reference check without inventing a duration or threshold.
6. **`6 · Sweep potential and record current`** — replay the forward and return potential sweep in
   acquisition order while the waveform cursor and published CV cursor move together. The cycle
   counter records two cycles.
7. **`7 · Retain the published curve`** — show the authors' processed second-cycle curve with the
   sample, protocol, axes, reference electrode, DOI, authors, and license.

The second cycle is shown because that is the source dataset's documented analysis choice. It is
not presented as a universal rule for cyclic voltammetry.

## The three sample-change branches

The cartoon must distinguish these cases because changing a scan setting is not the same as changing
a physical formulation.

### Fresh cell

The cell begins as `EMPTY / FRESH START`. There is no previous sample to remove. Removal and rinse
are marked `SKIPPED — NO PREVIOUS SAMPLE`; the selected formulation is then loaded and identified.

### Same formulation already loaded

The sample tag and liquid remain fixed. The UI says
`SAME LOADED FORMULATION — CONDITION REPLAY` and
`Same formulation → keep sample loaded`. Removal is `SKIPPED — SAME FORMULATION`, and loading is
`SKIPPED — ALREADY LOADED`.

This means the same formulation remains in the same cell; it does not claim an identical physical
state over time. Repeated cycling, time, electrode conditioning, contamination, or degradation can
matter.

### Different formulation

The UI shows `NEW FORMULATION — SAMPLE REPLACEMENT REQUIRED`. It stops the prior replay, marks the
old sample as removed, shows generic protocol-defined preparation, and only then loads and identifies
the new formulation. The new published curve becomes active after the new sample is loaded; it is
not drawn as a mixture with the previous sample.

The three published reference curves are different formulations measured at the reported
`10 mV/s`. They are not a real multi-scan-rate experiment series.

## What the published CV means

The reference data come from Engler, Stich, Baumer, and Bund,
*Supplement Data of Anolytes for All-Iron Redox-Flow Batteries*,
<https://doi.org/10.5281/zenodo.15730784>, licensed CC BY 4.0.

The visible curve contains published experimental points that the authors cleaned and smoothed. It
must therefore be called **published, author-processed experimental data**, not raw data. The
animation reveals saved points in acquisition order; it does not generate a measurement or rerun a
potentiostat.

## The hard boundary

After the physical workflow, a permanent divider says `PHYSICAL CONTEXT ENDS HERE`.

Above the divider are named formulations and published current-density curves. Below it is one
unnamed virtual sample and unitless synthetic response. No arrow crosses this boundary, because no
experimental curve is passed into the benchmark.

The synthetic area remains labeled:

> SYNTHETIC TEACHING EMULATOR · SAVED REPLAY · NOT A LAB MEASUREMENT

## The earlier five-state planner replay

Each saved request is explained with the same five states:

1. **`1 · SELECT RATE`** — a policy proposes a legal scan rate from `5–500 mV/s` and records why it
   chose that rate.
2. **`2 · VALIDATE REQUEST`** — a public range check accepts or blocks the request. A blocked request
   consumes attempt cost but creates no observation.
3. **`3 · EXECUTE VIRTUAL OPERATION`** — an accepted request returns one scalar, unitless normalized
   response or a recorded synthetic failure/QC flag. It does not return a generated CV curve. A
   failed executed operation consumes attempt and executed-operation cost but does not create a fake
   zero-valued response.
4. **`4 · UPDATE BELIEFS`** — a successful observation updates probabilities for three predefined
   synthetic models: diffusion-like, surface-like, and mixed toy model.
5. **`5 · CONTINUE OR STOP`** — the replay shows budget, confidence, and the recorded stop reason,
   then either requests another virtual operation or freezes the completed lane.

The response chart is `Normalized response vs scan rate — synthetic teaching model`; its vertical
axis is `Unitless normalized response`. It is not experimental current density.

## What the earlier three planners mean

All three planners receive the same public scenario contract and budgets. Each has a fresh
environment replay and cannot see hidden truth or another planner's observations.

- **Fixed Grid** follows a predetermined, regularly spaced scan-rate schedule.
- **Information Gain** chooses a scan rate expected to distinguish the remaining predefined models
  based on its current beliefs.
- **Random** selects a legal scan rate from its isolated random stream.

At a shared event position, each lane displays its own recorded event. A lane that has already
stopped stays marked `STOPPED` while the others continue. These are three matched counterfactual
campaigns, not three agents sharing or consuming one physical sample.

Do not judge a planner only by whether its final label matches the hidden synthetic label. Also ask:

- How many attempts and executed operations did it use?
- Were any requests blocked?
- Did it detect and respond to an injected failure?
- Does its conclusion follow from successful observations?
- What did it sacrifice to use fewer operations?

One fixed replay does not establish a universally best planner.

## Controls and accessibility

The UI uses ordinary buttons for sample selection, Previous, Next, Play/Pause/Resume, and Reset.
Motion never starts on page load. Manual selection, scrubbing, Previous/Next, Reset, or hiding the
browser tab pauses playback; returning to the tab does not silently resume it.

The real replay has a range control labeled `Replay position, 0 to 100 percent`. It follows
acquisition order rather than potential alone, because the same potential occurs on the forward and
return parts of a CV. The synthetic replay has one `Campaign event` range that advances all three
planner lanes to comparable event numbers. Both ranges retain Previous/Next buttons, current-value
text, and native keyboard behavior, so precise dragging is never required.

Keyboard users can select formulations, inspect WE/RE/CE help, move through all seven physical
steps, choose planner details, move through all five synthetic states, and open audit information.
Charts have text summaries. Status and provenance are written explicitly rather than encoded only
through color or animation. Meaningful changes use a polite live region; individual animation frames
are not announced and autoplay never moves focus.

When reduced motion is requested, timers stop, liquids and wires do not animate, CV and belief
updates use discrete states, and the complete manual path remains available. Motion changes pacing,
not evidence.

## Hidden synthetic truth and artifacts

Hidden truth stays unavailable to the planners and remains concealed in the interface until all
verified campaign artifacts are complete. The post-run reveal is labeled `Synthetic truth, not
experimental truth` and may include the private replay key and private seeds needed to reproduce the
synthetic scenario.

The audit area links to the exact manifest, summary, and planner ledgers. The local server verifies
their schema, hashes, identities, commitments, completion status, and provenance before serving a
campaign. An invalid bundle is rejected; the page must not substitute plausible-looking events.

## Limitations

- This is an illustrated replay. It makes no instrument call and performs no laboratory control.
- The closed-loop diagnosis returns full synthetic teaching curves but is not a physical or
  experimentally calibrated CV simulator. The earlier three-planner benchmark separately returns a
  scalar normalized response.
- The three predefined labels are teaching hypotheses. Classifying among them is not open-ended
  mechanism discovery and is not a diagnosis of a named real formulation.
- One CV or one scan-rate scaling relationship does not prove mechanism. Real interpretation can be
  affected by transport, adsorption, kinetics, background current, iR drop, coupled reactions,
  geometry, scan order, time, and surface history.
- A belief bar is a model probability within this synthetic scenario, not calibrated scientific
  certainty.
- No LLM is used. There is no real instrument call, autonomous laboratory, or institutional
  endorsement.

## Troubleshooting the local review

- **Artifacts failed to load:** confirm all five expected JSON files exist beneath the selected
  output directory.
- **Real CV reference failed to load:** confirm `demo/data/all_iron_rfb_cv.json` exists. Rebuild it
  with `uv run python scripts/build_real_cv_reference.py`; the builder verifies pinned SHA-256
  checksums before writing.
- **Artifact rejected:** core verification detected a schema, hash, identity, commitment, or
  provenance mismatch. Regenerate the bundle; do not edit generated JSON by hand.
- **Hidden truth unavailable:** the artifact set is incomplete or is not marked completed.
- **404 or forbidden:** the demo server intentionally refuses paths outside the static demo and
  selected artifact directory.
