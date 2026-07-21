# Cartoon CV Workbench — independent UX proposal

Date: 2026-07-21  
Role: UX / Visual Narrative Designer + Doc Worker  
Status: independent intake; design only; no implementation approval implied

## Product decision

Replace the long sequence of explanatory panels with one visual story in two unmistakably separate
worlds:

```text
REAL REFERENCE BENCH                         SYNTHETIC PLANNER RACE

sample bottle → CV cell → potentiostat →    one virtual sample → chosen scan rates
potential sweep → published CV curve         → normalized responses → belief updates
```

The real side teaches what cyclic voltammetry physically does. The synthetic side then teaches what
the benchmark compares. They share a visual vocabulary—sample, instrument operation, measurement,
decision—but never share a curve, provenance badge, or claim.

The style should be a **technical cartoon**, not a children's illustration: simple line art,
recognizable laboratory objects, direct labels, and restrained motion. The objects carry the story;
paragraphs become optional “Why?” drawers.

## What must be visible in the first five seconds

The first viewport should contain the title and a single overview/workbench card. Without scrolling,
a visitor sees:

1. a selected bottle labeled `0.8 M FeCl₂ + 3 M NH₄Cl · pH 3.5`;
2. a transparent three-electrode cell labeled `working / reference / counter`;
3. wires leading to a box labeled `potentiostat`;
4. a bidirectional potential-sweep strip labeled `0 → −1.2 → 0 V · 10 mV/s`;
5. a CV plot labeled `current density measured` and `PUBLISHED EXPERIMENTAL DATA`;
6. one large action: `▶ Replay this CV experiment`;
7. a permanent two-layer key:
   - `REAL: published formulation + CV curve`
   - `SYNTHETIC: three policies test one unnamed virtual sample`;
8. a small planner-race preview showing the three names and their different scan-rate patterns.

The five-second takeaway should be:

> A real electrolyte is loaded into a three-electrode CV cell. The instrument sweeps potential and
> measures current. Below, three policies choose scan rates on a separate virtual sample.

Do not begin with run hashes, benchmark definitions, or a paragraph explaining CV. Those remain in
the audit drawer and accessible help.

## Screen map

Use five progressive layers rather than eight equally weighted document sections.

### Layer 0 — permanent provenance rail

A sticky, compact rail remains visible at all scroll positions:

```text
◆ REAL CURVE: published, author-processed data
◇ POLICY REPLAY: simulated benchmark, not a lab measurement
```

The labels use both shape and text, not color alone. Selecting either label jumps to its layer. This
rail replaces a long warning banner while preserving the warning continuously.

### Layer 1 — the five-second overview

One wide card presents a miniature left-to-right process:

```text
[sample bottle] → [three-electrode cell] ⇄ [potentiostat] → [CV loop]
       REAL / PUBLISHED                              current out

────────────────── separate synthetic world ──────────────────

[Fixed Grid · regular ticks] [Information Gain · spotlight] [Random · scattered dots]
```

The selected real sample name, fixed published protocol, measured axes, and synthetic separation are
all visible. Clicking an object scrolls/focuses its detailed station.

### Layer 2 — real CV workbench

This is the flagship cartoon interaction. Desktop layout is a single lab bench:

```text
SAMPLE SHELF       CELL CUTAWAY          POTENTIOSTAT          CV DISPLAY
3 labeled bottles  electrolyte fill      sweep waveform        published loop
active bottle       WE / RE / CE           phase readout          live cursor
```

Under the bench is one compact workflow stepper and one control row. Sample metadata and source
attribution sit in a collapsible `Sample record & source` drawer, closed by default but always
reachable.

### Layer 3 — explicit world-change gate

A full-width divider prevents conceptual leakage:

```text
LEAVE THE REAL REFERENCE
The published curve ends here. The next panel uses one unnamed virtual sample and normalized
synthetic responses; it does not fit, reproduce, or predict the published CV above.
```

The divider is short, visually strong, and cannot be collapsed.

### Layer 4 — synthetic planner race

Three horizontal lanes share one campaign-step scrubber. Each lane contains:

- a planner identity icon;
- its next chosen scan rate on a 5–500 mV/s log rail;
- request state (`PROPOSED`, `BLOCKED`, `MEASURED`, `FAILED`, or `STOPPED`);
- attempts and executed-operation cost;
- three compact belief bars;
- its final conclusion when complete.

A shared plot above the lanes shows the three **synthetic response hypotheses** as dashed guide
curves. Selecting a lane overlays only that planner's revealed measurement dots. It must be titled
`Normalized response vs scan rate — synthetic teaching model`, never “CV curve.”

### Layer 5 — result and audit drawer

The visual result is a three-card finish line:

```text
Fixed Grid          Information Gain       Random
5 attempts          4 attempts              6 attempts
regular coverage    targeted separation     scattered exploration
final hypothesis    final hypothesis        final hypothesis
```

Below it, one collapsed `Audit this replay` drawer contains the detailed metrics table, event JSON,
run identity, commitments, downloads, and post-run truth reveal. This keeps rigor without making
the audit surface the teaching surface.

## Objects and visual language

### Real laboratory objects

| Object | What it communicates | Visual treatment |
| --- | --- | --- |
| Three sample bottles | Formulation identity and true sample switching | Formula on bottle; active bottle is on bench; inactive bottles remain on shelf |
| Waste/rinse tray | A new formulation requires removal and rinse | Appears only during a real sample change |
| Transparent cell | One physical electrolyte currently loaded | Liquid fill color tied to bottle; persistent sample label under cell |
| Working electrode | Potential is controlled and current is measured here | `WE` tag plus click/tap hotspot |
| Reference electrode | Potential reference | `RE` tag; visually distinct shape |
| Counter electrode | Completes circuit | `CE` tag; visually distinct shape |
| Potentiostat | Applies sweep and measures response | Two ports/arrows: `potential command` and `current signal` |
| Sweep strip | Forward and reverse potential sweep | Phase path `0 → −1.2 → 0 V`; draggable replay handle |
| CV display | Published current density vs potential | Real curve retains sample color and experimental provenance badge |

Do not invent pumps, robots, molecule structures, gas lines, or automatic sample handling that the
source data do not establish.

### Synthetic planner identities

Use icons plus names, not personality mascots:

- **Fixed Grid:** ruler/grid icon; markers appear in predetermined regular log spacing.
- **Information Gain:** spotlight/target icon; candidate rate glows only after the previous beliefs
  are shown, communicating targeted discrimination.
- **Random:** dice/scatter icon; selections visibly lack a fixed pattern.

Colors may differ, but line pattern and icon must also distinguish each planner.

## Real-workbench interactions

### 1. Choose a sample

The three bottle controls are buttons with full accessible names. Selecting a bottle changes the
loaded formulation and published curve only after the sample-change sequence completes.

- Selecting the already-loaded bottle shows `Same formulation remains loaded — no sample change`.
- Selecting a different bottle raises a visible `NEW FORMULATION` gate and queues:
  `stop → remove → rinse/prepare → load & identify → equilibrate`.
- On the first visit, the cell is a fresh start: do not animate removal of a nonexistent previous
  sample.

The previous curve can remain as a faint, clearly labeled comparison only if the user explicitly
turns on `Compare previous formulation`; it should not linger by default and imply a mixture.

### 2. Replay the physical workflow

Primary controls:

- `Play / Pause`
- `Previous step`
- `Next step`
- `Reset`

The stepper contains five observable states:

1. `Sample selected`
2. `Change check` — either `same sample` or the remove/rinse/load substeps
3. `Cell ready` — sample identity and three electrodes checked
4. `Potential sweep` — cursor advances around the published second-cycle curve
5. `Curve retained` — author-processed result and source badge remain visible

Each step has a text state (`PENDING`, `ACTIVE`, `DONE`, `SKIPPED`, `NEEDS SAMPLE CHANGE`), an icon,
and a one-line narration. State cannot be encoded through fill color alone.

### 3. Drag the sweep replay

Use a native range control labeled `Sweep position, 0 to 100 percent`. It scrubs through acquisition
order, not through potential alone, because the same potential occurs on forward and reverse legs.

Dragging or arrow-keying the handle updates together:

- the potentiostat waveform cursor;
- direction (`toward −1.2 V` or `returning toward 0 V`);
- instantaneous potential;
- instantaneous current density; and
- the highlighted point and revealed portion of the published CV.

The label must say `Replay position`; it must not imply the browser is commanding an instrument.

### 4. Inspect the electrodes

WE, RE, and CE labels are buttons placed next to—not on top of—the SVG drawing. Clicking or focusing
one opens a two-line popover. A visible `Close` button and Escape dismiss it. These popovers replace
a paragraph of electrochemical setup prose.

## Synthetic campaign interactions

### Shared experiment-step control

A global slider/buttons move all three planner lanes to campaign event `0…N`. This makes comparison
honest: at event 3, the visitor sees what each policy knew and chose at its own third recorded event.
If a planner has already stopped, its lane stays at `STOPPED` while the others continue.

Provide:

- `Previous event`
- `Next event`
- `Play all`
- a native `Campaign event` range input
- `Select lane for details`

Autoplay is never required. It pauses when the browser tab loses focus and after any manual
interaction.

### Five microstates per request

Within a request event, a small state row explains the loop:

```text
SELECT RATE → VALIDATE → EXECUTE VIRTUAL OPERATION → UPDATE BELIEFS → CONTINUE / STOP
```

Only states supported by the ledger are shown. Calibration is labeled `CALIBRATION OPERATION`, not
an experiment at a scan rate. A rejected request consumes attempt cost but creates no observation.
A failed executed operation consumes attempt and measurement cost and shows its QC flag; it must not
create a fake zero-valued point.

### Link the decision to the response plot

For the selected planner lane:

1. its chosen scan rate gains a vertical marker on the log x-axis;
2. the virtual operation state changes from proposed to measured or failed;
3. a successful normalized response dot appears;
4. belief bars update from `beliefs_before` to `beliefs_after`;
5. a one-line reason explains what changed.

The response plot and lane share focus state, but the real published CV plot never changes in
response to a synthetic event.

### Planner comparison at a glance

Each finish card uses the same four rows:

- `Choice pattern`: regular / targeted / scattered
- `Attempts`: includes calibration and rejected proposals
- `Executed-operation cost`: includes calibration, successful, and failed operations
- `Conclusion`: predicted synthetic mechanism + correct/incorrect benchmark result

Do not declare a universal winner. A short prompt asks: `Which strategy learned enough with the
fewest valid operations, and what did it sacrifice?`

## Progressive disclosure and exact short labels

Use object labels and one-line state narration on the main path. Move definitions into help drawers.
Recommended visible copy:

- `Potential command →`
- `← Current signal`
- `Published CV · 10 mV/s · second cycle`
- `Same sample: repeat without replacement`
- `New formulation: remove, rinse, load`
- `Synthetic response — not the published CV`
- `One virtual sample for every scan-rate request`
- `Attempts ≠ successful measurements`
- `Why this rate?`
- `Why did it stop?`
- `Audit this replay`

Avoid using `run experiment` without a qualifier. Use `Replay published CV workflow` for the real
reference and `Replay synthetic campaign` for planner artifacts.

## Visual state contract

| Meaning | Icon / pattern | Text | Suggested color |
| --- | --- | --- | --- |
| Published experimental | solid diamond + solid curve | `PUBLISHED EXPERIMENTAL` | dark green |
| Synthetic benchmark | hollow diamond + dashed hypothesis | `SYNTHETIC` | indigo |
| Active step | ring/pointer | `ACTIVE` | blue |
| Completed step | check | `DONE` | green |
| Skipped because same sample | skip arrow | `SKIPPED — SAME SAMPLE` | gray |
| Blocked request | barrier | `BLOCKED` | amber |
| Failed operation | broken pulse | `FAILED · measurement cost charged` | red |
| Stopped campaign | stop square | `STOPPED` | charcoal |

Real curves use the three source-sample colors. Synthetic planners use a separate palette and line
patterns. Never reuse a sample color as the sole identity of a planner.

## Mobile design

At widths below 720 px:

- the real bench becomes a vertical physical path: bottle shelf → cell → potentiostat → CV plot;
- wires and arrows remain visible between stacked objects;
- the selected sample formula remains pinned above the cell;
- the replay controls become a sticky bottom bar with `Previous`, `Play/Pause`, and `Next`;
- the sweep range input spans the full width;
- planner lanes become keyboard/touch tabs for detailed replay;
- a compact three-row comparison table remains below the tabs so all policies can still be compared
  without switching repeatedly;
- audit details stay collapsed.

Do not create a horizontally scrollable lab bench on phones. Minimum target size is 44 × 44 CSS px.

## Keyboard and screen-reader behavior

- Sample bottles: native buttons in a labeled group; Left/Right optionally moves and selects.
- Electrode hotspots: native buttons; Enter/Space opens; Escape closes and restores focus.
- Sweep and campaign scrubbers: native range inputs with current value text and Arrow/Home/End
  behavior.
- Planner lanes: WAI-ARIA tablist/tab/tabpanel with roving tabindex.
- Step controls: native buttons; disabled state is programmatic and visible.
- Each chart has a static description plus a dynamically updated text summary outside the SVG.
- `aria-live="polite"` announces only meaningful transitions: sample change, active step, operation
  failure, planner stop, and replay completion. It does not announce every animated point.
- Focus never moves during autoplay. Explicit sample change or reveal may move focus to the new
  status heading after the user action.
- All provenance badges and status labels remain text-readable at 200% zoom.

## Reduced-motion experience

When `prefers-reduced-motion: reduce` is active—or the visitor selects `Low motion`—the same controls
and states remain available, but:

- the sample and rinse sequence changes in discrete frames;
- the CV curve appears by completed segment rather than drawing continuously;
- wires do not pulse and liquids do not flow;
- planner events advance only on explicit action unless the visitor presses Play;
- belief bars jump to the new numeric value without tweening; and
- no auto-scroll or focus movement occurs.

The low-motion version must preserve sample-change semantics, sweep direction, costs, failures,
belief values, and stopping state. Animation is decoration and pacing, not evidence.

## Loading, error, and provenance states

- While real data loads, show empty object silhouettes and `Loading published reference…`; do not
  draw an invented placeholder curve.
- If real data fails but synthetic artifacts load, disable the real bench and keep the synthetic
  planner race usable with a clear error.
- If the verified synthetic bundle fails, the server should not start; the page therefore never
  presents unverified planner results.
- If JavaScript is unavailable, the permanent real/synthetic distinction and a short static purpose
  statement should remain in HTML.
- Source attribution stays adjacent to the real CV plot and is repeated in its audit drawer.

## Scope cuts for the first cartoon release

Do not add:

- a chat box or LLM character;
- 3D glassware or a game engine;
- drag-and-drop sample bottles into arbitrary locations;
- editable chemical concentrations;
- a simulated full CV waveform for the planner benchmark;
- automatic liquid handling, pumps, robots, or claims of hardware control;
- sound effects;
- a single composite score or podium winner; or
- an always-expanded raw JSON/event table.

The only drag interactions should be native replay scrubbers. Sample choice remains a button action,
which is clearer, safer, and fully keyboard equivalent.

## Implementation acceptance checklist

Before this proposal becomes implementation-ready, the reconciled contract should require that a
first-time usability reviewer can answer, without reading body paragraphs:

- which named formulation is physically loaded;
- that a potentiostat sweeps potential and measures current;
- that the visible CV loop is published, author-processed experimental data;
- that switching formulation—and only switching formulation—triggers remove/rinse/load;
- that repeated scan rates in the synthetic campaign probe the same virtual sample;
- that the synthetic plot is normalized response versus scan rate, not a generated CV curve;
- how Fixed Grid, Information Gain, and Random choose differently;
- whether an event was rejected, executed, failed, or stopped and what it cost; and
- where the evidence ledger and source attribution can be audited.

Recommended UX verdict: **approve with conditions**. Freeze the real/synthetic separation, native
scrubber semantics, sample-change state machine, and accessible no-motion path before implementation.

