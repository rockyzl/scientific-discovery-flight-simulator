# Cartoon CV scientific-flow review

Date: 2026-07-21  
Role: Scientific Workflow Designer  
Status: design proposal only; no implementation approval implied

## Scientific story in one sentence

The page should first show what a physical three-electrode CV measurement does, then cross a clear
visual boundary into a separate synthetic benchmark where three policies choose scan rates for an
unnamed virtual sample and receive scalar, normalized teaching-emulator responses.

The two layers answer different questions:

- **Published experimental layer:** What does a real CV curve and its physical measurement workflow
  look like for the selected all-iron RFB formulation?
- **Synthetic benchmark layer:** Given the same hidden toy response mechanism and budget, which
  policy chooses the most informative scan-rate experiments?

There must be no visual data-flow arrow from the published curve into the synthetic benchmark. The
published data provide physical context only; they do not fit, calibrate, train, validate, or supply
observations to the simulator.

## 1. Accurate physical CV workflow

### A. Switching to a different electrolyte formulation

This is the only branch in which the cartoon should show a sample replacement.

```text
select a different named formulation
→ stop the previous measurement state
→ remove the previous electrolyte
→ rinse / prepare the cell and electrodes according to the laboratory protocol
→ load and identify the new formulation
→ assemble / connect the three-electrode cell
→ allow the cell to reach the protocol-defined ready state
→ set the potential window, scan direction, scan rate, and cycle count
→ sweep working-electrode potential while measuring current
→ retain the source-defined analysis cycle
→ save the curve with sample, electrode, protocol, units, source, and processing metadata
```

For this published reference, the visible protocol may state only what the source supports:

- working-electrode potential swept from `0 V` toward `−1.2 V` and back;
- scan rate `10 mV/s`;
- two recorded cycles;
- the authors' processed second-cycle curve is displayed;
- potential is versus `Ag/AgCl/KCl (sat'd)`;
- total current density is reported in `mA cm⁻²`.

The rinse/preparation cartoon must remain generic. It must not invent a rinse solvent, polishing
method, purge gas, stabilization time, temperature, uncompensated-resistance procedure, or electrode
area that is not in the verified source record.

### B. Running several scan rates on one formulation

This is a within-sample measurement series. The bottle, liquid identity, sample ID, and cell contents
stay visibly unchanged.

```text
same loaded formulation and electrode configuration
→ choose the next scan rate
→ validate scan rate and potential window
→ run the potential sweep and record current
→ attach scan-rate and run-order metadata
→ perform any protocol-defined wait / conditioning / reference check
→ choose another scan rate or stop
```

The only prominently changing control is the scan-rate setting. A small persistent badge should say:

> SAME LOADED FORMULATION — SCAN RATE CHANGED

Do not show a bottle swap, drain, rinse, recoloring liquid, or a new sample barcode between scan
rates. However, wording should not say that the chemical and electrode state is perfectly unchanged:
repeated cycling can introduce time, history, surface-conditioning, or degradation effects. The
accurate claim is **same loaded formulation and cell**, not **identical physical state**.

The displayed published dataset is not itself a multi-scan-rate series: the three selected
formulations are shown at the reported `10 mV/s`. The scan-rate series belongs to the separate
synthetic teaching task unless a verified experimental scan-rate dataset is added later.

## 2. Cartoon storyboard: objects, states, and labels

The physical workflow should use one persistent left-to-right laboratory scene rather than seven
unrelated illustrations. Each step highlights only the object currently changing.

### Step 1 — Select formulation

**Objects**

- Three labeled electrolyte bottles or sample cards.
- A sample-record clipboard.
- An initially empty or previously occupied cell.

**State**

- Selected bottle/card receives a strong outline.
- Cell badge shows either `EMPTY / FRESH START` or `CURRENTLY LOADED: <prior formulation>`.

**Visible labels**

- `Choose a published formulation`
- Exact composition and pH from the source record.
- `Selection does not run an experiment yet`.

### Step 2 — Decide whether replacement is required

This must be a conditional cartoon state, not an unconditional “remove sample” animation.

**Same formulation**

- Cell remains filled and sample tag remains locked.
- Green route: `Same formulation → keep sample loaded`.

**Different formulation**

- Prior sample tag and selected sample tag appear side by side.
- Amber route: `Different formulation → replace sample before measurement`.

**Fresh start**

- Empty cell icon.
- Label: `No previous sample to remove`.

### Step 3 — Remove and prepare, only when switching formulations

**Objects**

- Waste/removal vessel icon.
- Rinse bottle with generic label `protocol-defined rinse`.
- Cell and removable working-electrode icon.

**State**

- Old sample tag moves to `removed`.
- Cell progresses through `previous sample removed` and `cell/electrodes prepared`.
- No animation in the same-formulation branch; show `not required` instead.

**Visible labels**

- `Prevent carryover between formulations`
- `Exact cleaning procedure depends on the laboratory protocol`.

### Step 4 — Load and identify the sample

**Objects**

- Selected bottle pours into the cell.
- Sample barcode/tag attaches to the cell.
- Composition, pH, and source-record card.

**State**

- Cell badge becomes `LOADED: <formulation>`.
- This badge must remain unchanged for every scan-rate measurement on that formulation.

**Visible labels**

- `Physical sample in cell`
- `Formulation`, `pH`, `source record`.

### Step 5 — Assemble the three-electrode measurement

**Objects**

- Electrochemical cell with three visually distinct electrodes.
- Potentiostat with three correctly connected leads.
- Protocol card.

**Required labels**

- `WE — working electrode`
- `RE — reference electrode`
- `CE — counter electrode`
- `Potentiostat controls WE potential relative to RE`
- `Current flows through the WE–CE circuit`.

The reference electrode must not be drawn as the electrode that carries the main measured current.
The counter electrode must not be labeled as the voltage reference.

**Ready-state labels**

- `Cell assembled`
- `Connections checked`
- `Protocol-defined equilibration / reference check`.

Avoid asserting a specific equilibration duration or that open-circuit potential must meet a
particular numerical threshold unless a verified protocol supplies it.

### Step 6 — Set and run the potential sweep

**Objects**

- A potential-versus-time triangular sweep graphic.
- Scan-rate dial.
- Potentiostat display.
- Current channel leading to the live CV plot.

**State**

- Moving marker travels `0 → −1.2 → 0 V` for this source example.
- Scan-rate dial reads `10 mV/s` for the published curve.
- During a future verified scan-rate series, only this dial changes.
- Current trace is drawn progressively against potential.

**Visible labels**

- Input: `working-electrode potential vs Ag/AgCl/KCl (sat'd)`.
- Sweep speed: `scan rate = 10 mV/s`.
- Measured signal: `total current density / mA cm⁻²`.
- `Potential goes forward and back; current is recorded throughout`.

Do not label this as “applying voltage to the electrolyte.” The controlled electrochemical quantity
is working-electrode potential relative to the reference electrode.

### Step 7 — Complete cycles and retain the source-defined curve

**Objects**

- Cycle counter `1 / 2`, then `2 / 2`.
- Full CV plot.
- Save/archive card with attribution.

**State**

- Cycle 1 becomes `recorded` but not displayed as the analysis curve.
- Cycle 2 becomes `author-selected analysis cycle`.
- Plot receives an `EXPERIMENTAL DATA` badge.

**Visible labels**

- `Published, author-processed second-cycle curve`.
- `Not raw data`.
- DOI, authors, `CC BY 4.0`.
- Both axes with quantities, units, and reference-electrode basis.

The animation must not imply that second-cycle selection is a universal CV rule. It is the analysis
choice documented for this particular source dataset.

## 3. Separate synthetic planner-loop cartoon

The benchmark needs a different visual grammar from the physical experiment:

- use a dashed frame, blueprint/grid background, or translucent “virtual” apparatus;
- label the section and apparatus `SYNTHETIC TEACHING EMULATOR`;
- use normalized response units, not `mA cm⁻²`;
- show saved replay events, not a live hardware connection;
- retain the global `SIMULATED RUN — NOT A LAB MEASUREMENT` banner.

### One loop iteration

```text
policy card
→ scan-rate request
→ public validator gate
→ virtual response model + virtual instrument
→ scalar noisy normalized observation with QC flags
→ public belief bars
→ next request or stop
```

#### 1. Policy chooses

**Object:** one of three policy tokens: `Random`, `Fixed Grid`, or `Information Gain`.  
**Label:** `Chooses the next virtual scan rate from 5–500 mV/s`.  
**State:** highlight the requested scan-rate card and the recorded rationale.

#### 2. Validator checks

**Object:** gate with the public range `5 ≤ scan rate ≤ 500 mV/s`.  
**State:** accepted requests pass; rejected requests turn amber and consume attempt cost only.  
**Label:** `Public protocol check — no hidden truth available`.

#### 3. Virtual instrument returns an observation

**Object:** transparent/outlined virtual cell and simulator block, never photoreal laboratory
hardware.  
**State:** returns one dot on a `scan rate → normalized response` chart, or a recorded timeout,
saturation, or reference-check flag.  
**Label:** `SIMULATED NORMALIZED RESPONSE`.

The synthetic event does **not** return a complete current-versus-potential CV curve. Drawing a full
CV here would falsely equate the teaching emulator's scalar response with the published experimental
curve.

#### 4. Beliefs update

**Objects:** three probability bars labeled `diffusion-like`, `surface-like`, and `mixed toy model`.
  
**State:** animate old probability as a faint outline and new probability as the solid bar.  
**Label:** `Posterior within three predefined candidate models`.

Avoid the stronger label `mechanism discovered`. The true process is selected from three models
that the benchmark designer supplied in advance.

#### 5. Continue or stop

**Objects:** budget tokens and a fork: `choose another experiment` / `stop and report`.  
**Labels:** attempts used, measurements used, confidence, and stop reason.  
**State:** on stop, freeze the final belief bars; only after all three planner replays are complete
may the UI reveal the hidden synthetic label.

### Comparing the three planners

The three planners are three separate counterfactual replays of the same committed scenario, not
three agents taking turns on one shared, changing physical sample.

Use three parallel lanes or tabs with identical initial badges:

- same public world contract;
- same attempt and measurement budgets;
- same committed world/noise/failure scenario;
- separate isolated planner random stream;
- fresh environment instance for each replay.

Do not visually pass observations from one planner lane into another. Do not show one shared liquid
level being consumed across the three lanes.

## 4. Required transition between layers

Insert a full-width boundary card after the published CV workflow:

```text
PHYSICAL CONTEXT ENDS HERE

Above: published, author-processed experimental curves from named formulations at 10 mV/s.
Below: a separate synthetic response-scaling benchmark using an unnamed virtual sample.
The published curves are not simulator inputs.
```

The visitor should need an explicit `Enter synthetic benchmark` action, or encounter an equally
prominent noninteractive divider, before the planner loop appears.

## 5. Scientific errors the implementation must avoid

1. **Replacing the sample for every scan rate.** Multiple scan rates normally form a measurement
   series on the same loaded formulation; replacement occurs when formulation changes.
2. **Calling the same loaded sample perfectly unchanged.** CV cycling, time, electrode conditioning,
   contamination, and degradation can create history effects.
3. **Showing the published 10 mV/s curves as a scan-rate mechanism series.** They are different
   formulations at the reported scan rate, not the synthetic benchmark observations.
4. **Feeding published data into the synthetic model.** The two layers are explicitly independent.
5. **Showing a full synthetic CV for every planner action.** The frozen emulator returns a scalar
   normalized response for a requested scan rate.
6. **Calling normalized synthetic response current density.** It has no experimental `mA cm⁻²`
   calibration.
7. **Claiming that one CV or one scaling exponent proves a mechanism.** Real diagnosis may be
   affected by mass transport, adsorption, electron-transfer kinetics, background current, iR drop,
   coupled reactions, electrode geometry, and scan-order/history effects.
8. **Calling predefined-model classification mechanism discovery.** The benchmark distinguishes
   among three supplied toy hypotheses; it does not invent or discover an unanticipated mechanism.
9. **Misrepresenting the three-electrode circuit.** The potentiostat controls WE potential relative
   to RE; the main current path is through WE and CE.
10. **Omitting the reference electrode from the potential axis.** `V` alone is scientifically
    incomplete; display `vs Ag/AgCl/KCl (sat'd)` for the reference data.
11. **Using current and current density interchangeably.** The source plot reports total current
    density in `mA cm⁻²`; do not relabel it as current in `mA`.
12. **Reversing electrochemical interpretation from screen direction alone.** Do not infer universal
    oxidation/reduction sign conventions merely from the visual direction of the plotted loop.
13. **Inventing physical protocol details.** Do not add unsupported temperature, purge, rinse,
    electrode area, polishing, equilibration-time, or iR-compensation claims.
14. **Calling author-processed data raw.** The reference curve is published and author-processed;
    preserve that description and attribution.
15. **Presenting the authors' second-cycle choice as a universal rule.** It belongs to this dataset.
16. **Implying browser-to-instrument control.** Buttons replay a cartoon and saved JSON; they do not
    send commands to pumps, cells, electrodes, or potentiostats.
17. **Revealing hidden truth during planner action selection.** Hidden mechanism, private seeds,
    future failure schedule, and evaluator remain inaccessible until all completed artifacts load.
18. **Treating the three planners as one collaborative experiment.** They are independently reset,
    matched counterfactual campaigns.

## 6. Minimum comprehension and accessibility checks

The future cartoon is scientifically acceptable only if a first-time visitor can answer, without
reading the long documentation:

1. The named electrolyte formulation currently loaded in the physical cell.
2. That WE potential relative to RE is swept and current is measured.
3. That changing scan rate does not itself replace the formulation.
4. That selecting another formulation does require a replacement/preparation branch.
5. That the displayed full CV is published, author-processed experimental data at `10 mV/s`.
6. That planner dots and belief bars belong to a separate synthetic normalized-response world.
7. That Random, Fixed Grid, and Information Gain differ in experiment selection, not in access to
   hidden truth.

All stages need persistent text labels and a numbered list equivalent. Motion should enhance state
changes but never carry the only explanation. Under reduced motion, the same steps, branches,
labels, current sample, scan-rate setting, and layer boundary must remain visible. Keyboard focus
must follow the selected step without automatically advancing or moving focus during autoplay.

## Recommendation

Approve a cartoon implementation only if it preserves the two independent layers and implements the
sample-change branch explicitly. The strongest single visual is not an animated CV curve; it is a
persistent sample tag on the physical cell that stays fixed while scan rate changes, followed by a
hard boundary before the synthetic planner loop.
