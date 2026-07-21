# TEMPO multi-sample CV inference workbench — UX study

Date: 2026-07-21  
Role: Product/UX designer and documentation worker  
Status: UX study complete; scientific and computation contracts are not yet frozen  
Scope: Design only. This document does not authorize implementation or certify a dataset.

## 1. Product decision

Build a separate **study workbench** for comparing named TEMPO-family samples across matched
experimental conditions and multiple scan rates. Do not turn the current illustrated CV tutorial
into a crowded calculator.

The current page succeeds because it tells one short physical story and keeps published data apart
from a synthetic policy replay. The TEMPO feature has a different job: it must help a user answer
three questions in order:

1. **What sample and experimental condition am I looking at?**
2. **Is the evidence sufficient for this estimate?**
3. **What can be compared without silently pooling incompatible measurements?**

The workbench therefore follows this visible sequence:

```text
choose dataset
    → choose multiple named TEMPO-family samples
    → choose one exact condition set
    → inspect each sample's multi-scan-rate CV series
    → extract and review anodic/cathodic peaks
    → choose raw or eligible iR-corrected view
    → inspect supported E1/2 / diffusivity / reversibility evidence
    → optionally add independent conductivity evidence
    → compare matched samples with uncertainty and provenance attached
```

This compact pipeline must appear near the top of the page. It is the one-glance model of the
feature; audit detail follows later.

The primary product rule is:

> Missing required metadata produces an explanation and no estimate. It never produces an assumed
> default, a plausible-looking number, or a silently corrected curve.

## 2. Relationship to the current demo

The feature should be a sibling route linked from the existing CV workbench, not a replacement for
it.

| Current illustrated page | Proposed TEMPO workbench |
| --- | --- |
| Teaches how one CV becomes evidence | Studies several named samples and condition sets |
| Shows a published single-rate reference | Requires multi-rate evidence for rate-dependent inference |
| Replays saved points | Selects, validates, fits, and compares eligible series |
| Separates real reference from synthetic planner replay | Separates measured, corrected, derived, assumed, and unavailable information |
| Avoids iR and transport claims because metadata are absent | Shows them only when their explicit evidence gates pass |

Recommended navigation labels:

- On the existing page: `Open the TEMPO multi-sample study →`
- On the new page: `Back to: How a CV experiment becomes evidence`

The current synthetic planner benchmark must not appear inside the TEMPO result surface. If a
synthetic TEMPO teaching dataset is later provided, it needs its own permanent
`SYNTHETIC TEACHING DATA` provenance rail and must not be mixed with published or uploaded records.

## 3. Core information model shown to the user

The interface must preserve this hierarchy rather than present a flat list of curves:

```text
Dataset
└── Named sample / molecular form
    └── Exact condition set
        └── CV series
            ├── scan rate 1 → raw trace → optional corrected trace
            ├── scan rate 2 → raw trace → optional corrected trace
            └── scan rate n → raw trace → optional corrected trace
```

### Dataset

Visible identity:

- source type: `Published experimental`, `User-uploaded experimental`, or
  `Synthetic teaching data`;
- title, creators or uploader, DOI/file name, license if applicable;
- import/build version and immutable record identifier;
- whether the source contains raw instrument export, author-processed data, or derived tables.

### Named sample

Visible identity:

- preferred name exactly as sourced;
- molecular form, including oxidation state, salt/counterion, and protonation state when relevant;
- stable source sample ID;
- structure identifier only when verified by the source or an explicit resolver step;
- concentration and batch/replicate identity.

Names such as `TEMPO`, `4-hydroxy-TEMPO`, or `4-acetamido-TEMPO` may be used in mockups only after a
source researcher verifies that those exact samples exist in the selected dataset. Until then,
implementation fixtures should use visibly synthetic labels such as `TEMPO teaching sample A`.

### Exact condition set

At minimum, keep these fields attached to every series:

- solvent;
- supporting electrolyte and concentration;
- analyte concentration;
- reference electrode and potential reference scale;
- working-electrode material and geometric area;
- counter electrode;
- temperature;
- scan-rate units and potential/current units;
- cycle-selection and preprocessing record;
- replicate ID;
- uncompensated resistance source and value, when provided;
- iR correction fraction, when requested;
- conductivity-cell constant/geometry and resistance measurement, when provided separately.

Changing any condition creates or selects a different condition set. It does not quietly append
the new trace to the current fit.

## 4. Page architecture

Use six progressive regions. The first four form the routine study path; comparison and audit are
progressive disclosure.

### Region A — permanent provenance and scope rail

Exact labels:

```text
SOURCE · PUBLISHED EXPERIMENTAL
VIEW · RAW MEASURED POTENTIAL
ESTIMATES · DERIVED, NOT DIRECT MEASUREMENTS
```

Each label is updated from the active selection and is independently focusable. Shape and text,
not color alone, distinguish the three concepts.

Use one permanent provenance grammar everywhere:

| Marker and color | Exact local label | Meaning |
| --- | --- | --- |
| solid green diamond | `◆ PUBLISHED EXPERIMENTAL` | Published measurement or author-processed experimental record |
| solid amber square | `■ USER-UPLOADED EXPERIMENTAL · UNVERIFIED` | User input; not independently verified by the project |
| hollow indigo diamond | `◇ SYNTHETIC TEACHING DATA` | Simulation/fixture; never a lab measurement |
| blue function badge | `ƒ DERIVED FROM SELECTED DATA` | E1/2, fit, diagnostic, or uncertainty computed from identified inputs |
| blue transform badge | `↔ iR-CORRECTED VIEW` | A reversible transform; raw measurement remains preserved |
| gray blocked badge | `— NO ESTIMATE` | Required evidence is absent or failed QC |

Every plot line, result card, comparison row, tooltip, text alternative, and download repeats its
local marker. Color is redundant; the symbol and exact words carry the meaning. A user-derived
result is never given the green published-data treatment merely because its inputs were published.

If data are uploaded, the first label becomes:

```text
SOURCE · USER-UPLOADED EXPERIMENTAL · NOT INDEPENDENTLY VERIFIED
```

If the data are synthetic:

```text
SOURCE · SYNTHETIC TEACHING DATA · NOT A LAB MEASUREMENT
```

### Region B — dataset, sample, and condition selector

Desktop uses a three-column selection shelf:

1. `1 · Dataset`
2. `2 · Sample`
3. `3 · Condition set`

Exact controls:

- `Choose dataset`
- `Choose sample`
- `Choose condition set`
- `Show full sample identity`
- `Show condition differences`
- `Add to comparison`

Directly below it, keep a visible multi-sample study tray:

```text
Study samples (3)
[TEMPO · active] [4-hydroxy-TEMPO] [4-acetamido-TEMPO] [+ Add sample]
```

Names above are illustrative until source verification. Adding several samples defines the study
set; one sample-condition record remains active for curve review and peak assignment. This avoids
trying to edit several fits in one plot while still making the multi-sample purpose obvious.

Every sample row includes name, molecular-form note, source ID, number of condition sets, and a
small completeness indicator. Every condition row summarizes solvent, electrolyte, concentration,
reference, temperature, and number of usable scan rates.

Selection is single-choice at this stage. Comparison is an explicit later action; selecting a new
active sample never overlays it automatically. The study tray itself is multi-select and shows
which named samples will be reviewed and compared.

### Region C — evidence readiness gate

This is the most important new component. It appears before any numerical result.

Heading:

```text
What can this evidence support?
```

It contains one row per output:

| Exact output label | Ready state | Missing state |
| --- | --- | --- |
| `Apparent midpoint potential (E1/2)` | `READY · paired anodic/cathodic peaks available` | `NO ESTIMATE · paired peaks not resolved` |
| `Peak-separation and current-ratio evidence` | `READY · required peak assignments available` | `NO ASSESSMENT · peak assignments incomplete` |
| `Scan-rate dependence` | `READY · multiple eligible scan rates` | `NO ESTIMATE · one eligible scan rate` |
| `Diffusion-coefficient estimate` | `READY · metadata and model gate passed` | `NO ESTIMATE · missing: …` |
| `iR-corrected view` | `AVAILABLE · resistance source recorded` | `UNAVAILABLE · uncompensated resistance not provided` |
| `Electrolyte conductivity` | `READY · independent resistance and cell constant available` | `NO ESTIMATE · CV alone is not a conductivity measurement` |

The missing row lists concrete fields as buttons or links, for example:

```text
NO ESTIMATE · missing working-electrode area, temperature, and electron count
[Show required metadata]
```

There is no disabled result card showing `0`, `N/A`, or a dash where a number would normally sit.
The explanatory no-estimate state replaces the number entirely.

### Region D — CV series and inference surface

Desktop is a two-column workbench:

- left: CV plot and scan-rate/replicate controls;
- right: evidence cards and fit diagnostics.

Controls above the plot:

- segmented view: `Raw measured potential` / `iR-corrected potential`;
- `Scan rates shown` multi-select;
- `Replicates` selector;
- `Overlay all eligible rates` checkbox;
- `Normalize current for display only` checkbox, off by default;
- `Show peak assignments` checkbox;
- `Show uncertainty band` checkbox, on by default when available.

The visible analysis sequence immediately above the result cards is:

```text
MULTI-RATE CV → REVIEW PEAKS → E1/2 / RATE FIT / REVERSIBILITY EVIDENCE
                                      ↓
                         optional iR-corrected recomputation

SEPARATE INPUT → CONDUCTIVITY (never inferred from CV alone)
```

The chart title always includes sample and condition:

```text
TEMPO · condition C-03 · cyclic voltammograms
```

The subtitle states the active data transform:

```text
RAW MEASURED POTENTIAL · measured current · 5 eligible scan rates
```

or:

```text
iR-CORRECTED POTENTIAL · Ru = 18.2 Ω from EIS HFR · 85% correction
Raw traces remain available
```

Never label an iR-corrected axis simply `Potential`. Use
`iR-corrected working-electrode potential vs [reference] / V`.

### Region E — matched comparison

The comparison tray is empty until the user presses `Add to comparison` for at least two eligible
sample-condition records.

Exact heading and gate:

```text
Compare matched evidence
Only records with compatible reference scales, units, and selected condition fields are overlaid.
```

Before overlay, show a difference table with each field categorized as:

- `MATCHED`
- `DIFFERENT — KEEP SEPARATE`
- `CONVERTIBLE — REVIEW CONVERSION`
- `MISSING — CANNOT COMPARE`

The user may choose which scientific condition fields must match, but the defaults come from the
frozen scientific contract. Reference-scale conversion requires an explicit reviewed transform and
must retain both original and converted values.

Comparison views:

1. `CV overlay`
2. `E1/2 with uncertainty`
3. `Peak separation vs scan rate`
4. `Peak current vs square root of scan rate`
5. `Reversibility evidence matrix`
6. `Conductivity` only when independently supported for every selected record

No overall winner score is shown. The comparison summary says what differs and where evidence is
missing.

### Region F — method and provenance audit

Collapsed by default under:

```text
Audit this estimate
Inputs, transformations, exclusions, fit diagnostics, assumptions, and source records
```

It contains:

- exact included and excluded trace IDs with reasons;
- original units and conversions;
- raw-data checksums;
- peak-detection method/version and editable assignments;
- resistance source, correction fraction, and sensitivity settings;
- inference equation/method identifier and applicability checks;
- fit diagnostics and uncertainty method;
- all assumptions accepted by the user;
- source citation and license;
- downloadable machine-readable result manifest.

## 5. Desktop wireframe

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ TEMPO multi-sample CV study                                                  │
│ Compare only what the selected evidence supports.                            │
├────────────── SOURCE ────────────── VIEW ───────────── ESTIMATES ─────────────┤
│ PUBLISHED EXPERIMENTAL          RAW MEASURED POTENTIAL     DERIVED / AUDITABLE│
├────────────────────┬────────────────────┬────────────────────────────────────┤
│ 1 · Dataset        │ 2 · Sample         │ 3 · Condition set                  │
│ TEMPO study…       │ TEMPO              │ C-03                               │
│ DOI / license      │ molecular form     │ solvent · electrolyte · reference  │
│ [change]           │ [identity]         │ 5 rates · 2 replicates [differences]│
└────────────────────┴────────────────────┴────────────────────────────────────┘
│ Study samples (3): [TEMPO · active] [4-OH-TEMPO] [4-acetamido-TEMPO] [+ Add]│

  multiple scan-rate CV → review peaks → E1/2 · D · reversibility evidence
                                              └→ optional iR-corrected view
  independent resistance + cell constant ─────→ optional conductivity

┌─ What can this evidence support? ────────────────────────────────────────────┐
│ ✓ E1/2 ready     ✓ reversibility evidence     ✓ scan-rate dependence         │
│ ! Diffusivity: NO ESTIMATE · missing electrode area                         │
│ ! iR correction: UNAVAILABLE · Ru not provided                              │
│ ! Conductivity: NO ESTIMATE · CV alone is not conductivity                  │
└──────────────────────────────────────────────────────────────────────────────┘

┌─ CV series ─────────────────────────────────┬─ Evidence, not answers ─────────┐
│ [Raw measured potential] [iR-corrected ⓘ]   │ Apparent E1/2                   │
│ rates [10] [25] [50] [100] [200] mV/s       │ estimate ± uncertainty          │
│                                             │ measured peaks → derivation      │
│     current                                 ├─────────────────────────────────┤
│       ↑       overlaid measured CVs         │ Reversibility evidence           │
│       └──────── potential                   │ ΔEp · ipa/ipc · drift · caveats  │
│                                             ├─────────────────────────────────┤
│ [show peaks] [show uncertainty]             │ Diffusivity                      │
│ trace provenance: measured / excluded       │ NO ESTIMATE · missing area       │
└─────────────────────────────────────────────┴─────────────────────────────────┘

┌─ Comparison tray (2) ────────────────────────────────────────────────────────┐
│ TEMPO · C-03     4-OH-TEMPO · C-02        [Review condition differences]     │
│ [CV overlay] [E1/2] [ΔEp vs rate] [ip vs √rate] [evidence matrix]            │
└──────────────────────────────────────────────────────────────────────────────┘

▶ Audit this estimate — inputs, transformations, exclusions, assumptions
```

## 6. Exact result-card language

Every derived card has the same five-part anatomy:

1. status: `ESTIMATE AVAILABLE`, `PARTIAL EVIDENCE`, or `NO ESTIMATE`;
2. quantity and value, only when available;
3. uncertainty/range and method;
4. `Based on` evidence summary;
5. `Limits` and `Audit` actions.

### Apparent midpoint potential

```text
ESTIMATE AVAILABLE
Apparent midpoint potential (E1/2)
[value] ± [uncertainty] [unit] vs [reference]
Based on paired anodic and cathodic peak assignments from [n] traces.
[Inspect peak assignments] [Audit estimate]
```

Do not shorten the result to `Redox potential` because the meaning depends on the measurement and
reference context.

### Reversibility

```text
PARTIAL EVIDENCE
Reversibility evidence
Observed: ΔEp [range], ipa/ipc [range], peak-position drift [value]
Assessment within the selected protocol: [contract-defined wording]
This is not a universal molecular label.
[Why this assessment?]
```

The eventual scientific contract must define the assessment wording and thresholds. The UX must
not hard-code `reversible`, `quasi-reversible`, or `irreversible` before that review.

### Diffusion coefficient

Available state:

```text
ESTIMATE AVAILABLE · MODEL-DEPENDENT
Diffusion-coefficient estimate
[value] with [confidence interval / sensitivity range]
Model: [approved method] · [n] scan rates · fit [diagnostic]
Assumes: [approved regime and required assumptions]
[Inspect fit] [Test sensitivity] [Audit estimate]
```

Missing state:

```text
NO ESTIMATE
Diffusion coefficient
The selected series has multiple scan rates, but the calculation is missing:
working-electrode area, temperature, and electron count.
No defaults were inserted.
[Show required metadata]
```

### Conductivity

```text
NO ESTIMATE
Electrolyte conductivity
CV alone is not a conductivity measurement. Add an independent resistance measurement and a
verified cell constant or defensible geometry.
[Show accepted evidence]
```

If available, its card must remain under `Independent transport measurement`; do not place it under
`CV-derived properties`.

## 7. Raw and iR-corrected interaction contract

Raw is always the initial and recoverable view. The corrected control has these states:

| State | Control behavior | Exact message |
| --- | --- | --- |
| Ru absent | Disabled with explanation | `Unavailable — uncompensated resistance not provided` |
| Ru present, provenance incomplete | Disabled | `Unavailable — resistance source or measurement context missing` |
| Ru eligible, fraction unset | Opens setup panel | `Set correction fraction` |
| Eligible and configured | Switches view without replacing raw | `Showing iR-corrected potential; raw traces preserved` |
| Sensitivity warning | Corrected view remains marked | `Result is sensitive to the selected Ru or correction fraction` |
| Over-correction/QC failure | Do not publish corrected estimate | `Correction failed quality checks — raw view only` |

The setup panel exact fields are:

- `Uncompensated resistance (Ru)`
- `Resistance source`
- `Measurement method`
- `Correction fraction`
- `Apply to selected series`
- `Preview correction`
- `Cancel — keep raw`

The preview overlays raw and corrected traces, repeats Ru and fraction directly beside the plot,
and shows a sensitivity range. Applying the view never mutates or downloads over the raw record.

## 8. Interaction states and failure behavior

### Initial

```text
Choose a dataset to begin
No sample, curve, or estimate is selected.
```

### Loading and validation

```text
Validating sample identities, condition sets, units, and trace provenance…
```

Skeletons may reserve space, but must not contain placeholder scientific values.

### Ready

The selector, readiness gate, and raw traces appear together. Derived values appear only after the
gate result is known.

### Partial series

```text
PARTIAL SERIES · 3 of 5 traces eligible
Two traces are excluded from inference. The raw records remain inspectable.
[Review exclusions]
```

### Mixed conditions

```text
SERIES NOT POOLED
These traces differ in reference electrode and temperature. Select one condition set or review an
explicit conversion before comparison.
```

### Missing metadata

The result card is replaced with `NO ESTIMATE`, the exact missing fields, and a link back to their
source/edit location. No warning can be dismissed while leaving an estimate visible.

### Invalid peak assignment or fit

```text
ESTIMATE WITHHELD
Peak assignment / fit quality did not pass the approved check.
[Inspect traces and diagnostics]
```

The user may edit a peak assignment, but the audit log must preserve automatic and edited values,
the editor timestamp, and the downstream estimates recomputed from the edit.

### Selection change

Changing sample or condition clears the active curve, corrections, fits, and result cards before
loading the next selection. The previous record remains only in the explicit comparison tray.

### Source failure

```text
DATASET UNAVAILABLE
The selected source or integrity record could not be verified. No cached substitute or synthetic
trace is shown.
```

## 9. Comparison and uncertainty behavior

### Uncertainty is local, not a generic warning

Show uncertainty beside the value it qualifies:

- peak-location uncertainty beside Epa/Epc;
- propagated or resampling uncertainty beside E1/2;
- confidence interval and residual diagnostics beside a scan-rate fit;
- Ru/fraction sensitivity beside corrected outputs;
- replicate variation beside sample comparisons.

The interface must distinguish:

- `Measurement variation`
- `Fit uncertainty`
- `Sensitivity to assumptions`
- `Missing information`

Do not merge them into one confidence score.

### Comparison defaults

- compare identical quantities on one declared reference scale;
- show raw values before converted values;
- use points and interval bars, not only bars;
- show each sample-condition record, not only a group mean;
- keep excluded or unavailable samples visible in the evidence matrix with the reason;
- never rank samples by a property that is missing for some selected records;
- never describe disagreement as calibrated uncertainty unless it is actually calibrated.

## 10. Mobile behavior

At widths up to 420 CSS px, preserve the causal order rather than squeezing the desktop grid.

```text
[provenance rail]
[dataset]
↓
[sample]
↓
[condition set]
↓
[what this evidence supports]
↓
[raw / corrected control]
[one plot]
[scan-rate chips in a horizontal scroll container]
↓
[one result card at a time]
↓
[comparison tray]
[audit disclosure]
```

Mobile requirements:

- provenance rail remains two or three short stacked rows and never truncates source type;
- selector opens a full-width bottom sheet or native dialog with one decision per screen;
- active sample and condition summary remains visible above the plot;
- scan-rate chips have at least 44 px targets and show unit in the group label;
- chart has an accessible text/table alternative and never depends on hover;
- raw/corrected choice remains adjacent to the correction provenance;
- readiness rows appear before result cards;
- `NO ESTIMATE` reason is never hidden in a tooltip;
- result cards use a `Previous result` / `Next result` control or vertical stack, not a tiny carousel;
- comparison uses a field-by-field stack first; overlay charts follow only after compatibility review;
- all controls and disclosure summaries have at least 44 × 44 CSS px targets;
- no document-level horizontal overflow at 320 CSS px; a data table may scroll inside a labeled
  container.

## 11. Accessibility and comprehension

- Use native radio groups, checkboxes, buttons, details, and range inputs.
- Sample selection announces full name, molecular form, and source ID.
- Condition selection announces the fields that changed from the prior selection.
- Chart lines use direct labels and line patterns as well as color.
- Raw and corrected traces use different line styles and explicit legend text.
- Readiness changes announce through one polite live region; errors receive focus only after a user
  action that caused them.
- Each derived value has a text equivalent containing value, unit, reference, uncertainty, evidence,
  and limitations.
- Keyboard users can reach scan-rate selection, peak assignment review, result cards, comparison,
  and audit in the same order as the visible page.
- Reduced-motion mode removes transitions without removing state changes.

Five-second comprehension target:

> I selected a named TEMPO-family sample under one specific condition. The page is showing measured
> CVs and will calculate only what the available evidence supports.

Thirty-second comprehension target:

> Raw and corrected curves are different views of preserved data; correction needs a sourced Ru.
> Diffusivity needs a multi-rate series and metadata. Conductivity needs an independent measurement.
> Comparisons are allowed only after condition compatibility is visible.

## 12. Implementation file plan

This is a proposed file map for the implementation team after the scientific and data contracts are
frozen. It is not an instruction to start coding now.

### New public workbench surface

- `demo/tempo.html` — semantic page structure, selectors, readiness gate, plots, results, comparison,
  and audit disclosure.
- `demo/tempo.js` — selection state, fail-closed artifact loading, rendering, accessible announcements,
  and request wiring. Numerical scientific logic should not live here.
- `demo/tempo.css` — workbench-specific responsive layout; reuse shared tokens and 44 px target rules
  from `demo/styles.css` where practical.
- `demo/data/tempo/` — verified static dataset manifests and records only; synthetic fixtures live in
  a visibly separate path.
- `demo/serve.py` — add explicit, traversal-safe routes for the new page/data after artifact
  verification is defined.

### Scientific core

- `src/discovery_flight_simulator/tempo_contracts.py` — dataset, sample, condition, trace, correction,
  result, exclusion, and provenance schemas.
- `src/discovery_flight_simulator/cv_inference.py` — approved peak, E1/2, rate-dependence,
  diffusivity, uncertainty, and QC calculations.
- `src/discovery_flight_simulator/ir_correction.py` — immutable raw/corrected transforms,
  provenance, fraction validation, and sensitivity.
- `src/discovery_flight_simulator/conductivity.py` — optional independent conductivity calculation,
  kept separate from CV inference.
- `scripts/build_tempo_reference.py` — fetch/parse only the frozen, pinned public source; verify
  checksums and emit deterministic records.

Final names may change to match the architect's module plan, but separation of contracts,
calculation, correction, conductivity, and UI must remain.

### Tests and documentation

- `tests/test_tempo_contracts.py` — metadata and provenance gates.
- `tests/test_cv_inference.py` — numerical fixtures, units, missing-data refusal, exclusions, and
  uncertainty.
- `tests/test_ir_correction.py` — raw immutability, source/fraction checks, and sensitivity.
- `tests/test_conductivity.py` — independent evidence requirements and CV-only refusal.
- `tests/test_tempo_demo.py` — exact labels, missing-state behavior, source failure, and no synthetic
  fallback.
- `tests/test_tempo_browser.py` or the established browser QA harness — keyboard, 390/320 layout,
  focus, 44 px targets, selectors, correction, and comparison.
- `docs/tempo-data-reference.md` — source, license, sample/condition inventory, transforms, checksums.
- `docs/tempo-inference-guide.md` — plain-language methods, boundaries, uncertainty, and examples.

## 13. Recommended implementation slices

1. **Evidence browser:** dataset/sample/condition selection, raw curves, provenance, readiness gate,
   and missing-metadata refusal. No scientific estimate beyond verified display fields.
2. **Peak evidence:** reviewed peak assignments, apparent E1/2, ΔEp, current ratio, drift, uncertainty,
   and exclusions.
3. **Rate-dependent inference:** eligible multi-rate fits, diagnostics, model gate, diffusivity only
   after the scientific contract passes.
4. **iR correction:** raw-preserving corrected view, resistance provenance, fraction, QC, and
   sensitivity.
5. **Matched comparison:** compatibility matrix, overlays, uncertainty plots, and evidence matrix.
6. **Optional conductivity:** only if a verified independent resistance/cell-constant data path is
   available.

Each slice needs an independently reviewed artifact and browser state. Do not ship an empty numeric
card for a later slice; ship the truthful `NO ESTIMATE` state instead.

## 14. UX acceptance criteria before implementation approval

- A first-time user cannot reach a diffusivity number from one scan rate.
- Removing any required metadata replaces the affected value with `NO ESTIMATE` and names the field.
- Raw traces remain retrievable after enabling, changing, or rejecting iR correction.
- Ru value, source, method, and correction fraction remain adjacent to every corrected plot/result.
- Conductivity cannot be produced from CV data alone.
- Changing condition set clears stale fits and values before the new record renders.
- Incompatible condition sets cannot be overlaid without a visible reviewed conversion/separation
  decision.
- Every value retains sample, molecular form, condition, source, units, method, uncertainty, and
  audit link.
- Published, uploaded, and synthetic data cannot share an unlabeled plot or result.
- A 390 px user sees active sample, condition, readiness, and raw/corrected state before any estimate.
- A 320 px page has no document-level horizontal overflow.
- All interactive targets are at least 44 × 44 CSS px and every chart has a nonvisual equivalent.

## 15. Open decisions owned by other study roles

UX is complete, but implementation remains blocked until the team freezes:

1. the verified TEMPO-family dataset and exact names/molecular forms;
2. supported property and required-metadata matrix;
3. peak assignment and cycle/replicate inclusion rules;
4. exact E1/2 terminology and uncertainty method;
5. permitted electrochemical regimes and calculation for diffusivity;
6. reversibility evidence language and any thresholds;
7. valid Ru measurement sources, correction limits, and QC rules;
8. conductivity evidence contract;
9. reference-scale conversion policy;
10. numerical fixtures and independent validation tolerances.

Until those are resolved, this document freezes the interaction principle—**evidence before
estimate**—but not the scientific computation.
