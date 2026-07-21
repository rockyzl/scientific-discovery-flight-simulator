# Independent QA review — TEMPO multi-sample plan

Date: 2026-07-21  
Reviewer role: independent scientific and product QA  
Inputs reviewed:

- [`docs/study/tempo-electrochemistry-evidence.md`](../study/tempo-electrochemistry-evidence.md)
- [`docs/design/tempo-multisample-ux-plan.md`](../design/tempo-multisample-ux-plan.md)
- scientific/data computation contract: pending at first review; final verdict must be rechecked against it before implementation

## Verdict

**APPROVE only the restricted v1 defined below. BLOCK all broader scientific inference until the computation contract is present, independently reviewed, and covered by the numerical tests in this document.**

The evidence supports a useful and honest first release: a five-sample published-value atlas under one clearly displayed Zhou et al. condition set, source links, an explicitly synthetic teaching calculator, and/or analysis of user-uploaded CV data. It does not support redistributing the Zhou supporting-information plots as raw data, manufacturing experimental-looking curves from Table 1, deriving conductivity or uncompensated resistance from CV, or assigning an unconditional molecular label such as “reversible.”

This split verdict is deliberate. It lets the team ship a meaningful product without waiting for a permissively licensed raw-data corpus, while preventing attractive UI from outrunning the evidence.

## Release blockers

Any one of the following makes the release **BLOCKED**:

1. A curve reconstructed from Table 1 or digitized from the Zhou SI is labelled `measured`, `raw`, or `published experimental curve`.
2. A Zhou or Tang curve/source file is mirrored, transformed, or redistributed without a documented licence decision. Zhou is CC BY-NC 3.0; Tang is CC BY-NC-ND 4.0. A public recruiting/portfolio site cannot silently assume that `NC` is satisfied, and `ND` creates additional risk for normalized or repackaged data.
3. A sample value is shown without its condition and reference scale. `0.812 V` alone is not acceptable; `0.812 V vs SHE, reported in 0.5 M KCl under the Zhou protocol` is.
4. `NA` is converted to zero, an empty numeric value, or a value inferred from a neighboring molecule.
5. Conductivity or `Ru` is inferred from a CV trace. Conductivity requires independently measured resistance and a calibrated cell constant.
6. iR correction is applied with an assumed/default `Ru`, hidden current-unit conversion, or destructive replacement of raw potential.
7. Diffusion coefficient is calculated without electron count, electrode area, concentration, temperature/model form, scan-rate units, sufficient eligible rates, and diagnostic output.
8. The product hard-codes `reversible`, `quasi-reversible`, or `irreversible` from a single ΔEp threshold or a single curve.
9. Published, uploaded, derived, and synthetic values share an unlabeled plot/card/download or acquire one another's provenance badge.
10. Changing sample or condition leaves stale peaks, fits, corrections, or results on screen.
11. A source-integrity failure falls back to a plausible synthetic curve.
12. The browser page claims that published values validate, calibrate, fit, or train a synthetic calculator when they do not.

## Scientific corrections and thresholds

### Terminology

- For the Zhou table, use **`reported formal/equilibrium potential`** because that is how the source frames `E0`.
- For a user-derived midpoint, use **`apparent midpoint potential (E1/2)`**, calculated from reviewed paired peaks. Do not shorten either quantity to an unqualified `redox potential`.
- Use `mean diffusion coefficient reported by the authors` for Zhou Table 1. It is the reported average of oxidized- and reduced-state coefficients, not a new estimate made by this application.
- Use `heterogeneous electron-transfer rate constant reported from RDE analysis`; do not imply that `k0` came from ordinary CV.

### Published-value acceptance

The following Zhou values are acceptable only as immutable, attributed source values:

| Sample | E0 (V vs SHE) | D (cm² s⁻¹) | k0 (cm s⁻¹) | Solubility in 0.5 M KCl (M) |
|---|---:|---:|---:|---:|
| 4HT | 0.812 | 3.14 × 10⁻⁶ | 4.45 × 10⁻³ | 1.25 |
| 4OT | 0.910 | 4.61 × 10⁻⁶ | 1.05 × 10⁻² | 0.79 |
| 4AT | 0.895 | 3.77 × 10⁻⁶ | 4.01 × 10⁻³ | 4.80 |
| 4CyT | 0.881 | 6.23 × 10⁻⁶ | 4.29 × 10⁻³ | not reported |
| 4CaT | 0.776 | 2.64 × 10⁻⁶ | 2.25 × 10⁻³ | not reported |

Their shared visible condition summary must include `1 mM analyte · 0.5 M KCl · glassy carbon RDE, 5 mm diameter · Pt counter · SCE reference, values reported vs SHE · nitrogen purge · room temperature`; the direct five-sample CV comparison additionally specifies `pH 7 · 25 °C · 25 mV s⁻¹`.

### Peak and midpoint rules

- Define anodic and cathodic current sign convention in the contract.
- Define `ΔEp = Epa − Epc` in volts and require it to be non-negative for an accepted paired assignment.
- Define `E1/2 = (Epa + Epc)/2` on the same potential scale.
- Define the current ratio explicitly, preferably `abs(ipa / ipc)`, and reject division by zero.
- Preserve user-edited and automatically detected peak assignments as separate audit entries.
- Withhold a midpoint if peaks are unresolved, outside the acquired window, assigned to different cycles/replicates without an explicit rule, or fail contract-defined quality checks.

### Reversibility

At 25 °C an ideal reversible one-electron couple is commonly associated with an approximately 59 mV peak separation, near-unity absolute peak-current ratio, and limited peak-position drift with scan rate. These are reference expectations, **not universal classification cutoffs**. Uncompensated resistance, electrode kinetics, diffusion, adsorption, chemical follow-up, temperature, and peak-picking uncertainty can move the observed values.

For v1:

- publish the measured descriptors and their trends;
- allow wording such as `consistent with reversible behavior under this protocol` only if the contract combines ΔEp, current ratio, scan-rate drift, replicate behavior, iR status, and QC;
- otherwise use `reversibility evidence: partial/inconclusive`;
- do not rank molecules by a categorical reversibility class.

No numeric reversible/quasi/irreversible threshold is approved in this review. A future threshold requires a cited method, temperature/electron-count handling, simulated boundary tests, and an `inconclusive` region.

### Diffusion coefficient

If the contract uses the 298 K Randles–Sevcik form

`ip = 2.69 × 10^5 n^(3/2) A C D^(1/2) v^(1/2)`,

the required units are `ip` in A, `A` in cm², `C` in mol cm⁻³, `D` in cm² s⁻¹, and `v` in V s⁻¹. If other temperatures are accepted, the implementation must use the temperature-dependent equation rather than the fixed 298 K coefficient.

Minimum v1 gate:

- at least three distinct eligible scan rates; five or more is preferred for a published inference;
- positive finite `n`, `A`, `C`, `T`, and scan rates;
- current units converted before fitting;
- an explicitly chosen anodic or cathodic series, or separately reported estimates—not silent averaging;
- slope sign consistent with the selected peak convention;
- fit intercept, residuals, `R²`, included/excluded trace IDs, and sensitivity/uncertainty shown;
- no “diffusion controlled” claim based on `R²` alone.

Do not turn an `R²` threshold into proof of model validity. A provisional computational QC threshold such as `R² ≥ 0.98` may be used to withhold unstable fits, but it must be labelled a software quality gate and paired with residual inspection; it is not a law of electrochemistry.

### iR correction

The contract must state the sign convention and equation. Under the conventional anodic-positive current definition, the pointwise transform is:

`Ecorrected = Emeasured − f × I × Ru`,

with `I` in A, `Ru` in Ω, and correction fraction `f` in `[0, 1]`. Raw potential must remain immutable. Values outside `[0, 1]`, non-positive/unknown `Ru`, missing resistance provenance, or mixed current units must fail closed. `100%` compensation can be displayed only as a user-requested calculation, not as automatically safe; defaulting to any nonzero compensation is not approved.

The UI should report sensitivity at minimum for `f = 0`, selected `f`, and a bounded nearby value. A corrected trace that produces obvious oscillation, peak inversion, discontinuity, or extreme dependence on small `Ru/f` changes should be withheld rather than assigned a corrected kinetic label.

### Conductivity

Use the IUPAC relationship `Kcell = κR`, hence `κ = Kcell/R`. `Kcell` and `R` must use compatible units. Reject zero/negative resistance, absent cell-constant calibration, and `Ru` borrowed from an unrelated CV geometry. Keep conductivity under an independent-measurement section, not under CV-derived properties.

## Minimum publishable v1

The smallest release approved by QA is:

1. A separate TEMPO study route linked to and from the current CV explainer.
2. A five-card/table atlas for 4HT, 4OT, 4AT, 4CyT, and 4CaT using the exact Zhou Table 1 values above.
3. Persistent source, licence, condition, measurement-method, and `reported value` labels.
4. Direct links to the Zhou article and SI; no embedded/digitized Zhou curve arrays.
5. A clear statement that supporting Figure S2 contains six scan rates (5, 10, 25, 50, 100, 200 mV s⁻¹) but the project does not have author-supplied raw x-y data.
6. A synthetic teaching calculator in a visually separate region, or a user-upload calculator. Synthetic traces must say `SYNTHETIC TEACHING DATA · NOT A LAB MEASUREMENT` on plot, card, tooltip, text alternative, and download.
7. For uploads, fail-closed metadata readiness and only the calculations frozen in the reviewed contract.
8. A separate conductivity calculator that accepts independently measured resistance and cell constant, if included at all.
9. No categorical reversibility label and no `k0` inference in the first release.
10. A provenance/audit manifest for every derived output.

The following may be deferred without weakening v1: Tang source-data ingestion, reference-scale conversion, automated peak picking, replicate aggregation, iR correction, matched curve overlay, conductivity, and diffusivity. Truthful `NO ESTIMATE` states are acceptable and preferable to placeholder calculations.

## Required numerical test vectors

All tolerances below assume double-precision calculations. The frozen contract may tighten them but may not silently change definitions.

### A. Published-value integrity

1. Load the five-sample source fixture and assert exact decimal/scientific-notation values from the table above.
2. Assert `4CyT.solubility_kcl` and `4CaT.solubility_kcl` are null/not-reported, never `0`.
3. Assert every source record retains `0.5 M KCl`, `vs SHE`, DOI `10.1039/D0RA03424J`, source-table identity, and published-value provenance.
4. Assert no curve record can be created from only these scalar rows with experimental provenance.

### B. Peak descriptors

Vector B1:

- input: `Epa = 0.842 V`, `Epc = 0.782 V`, `ipa = +0.150 mA`, `ipc = −0.147 mA`;
- expected: `E1/2 = 0.812 V`, `ΔEp = 0.060 V`, `abs(ipa/ipc) = 1.0204081633`;
- tolerance: `1 × 10⁻¹² V` for arithmetic values and `1 × 10⁻⁹` for ratio.

Vector B2 refusal cases:

- missing `Epc` → no E1/2 and exact missing-peak reason;
- `Epa < Epc` under the defined convention → rejected/flagged assignment;
- `ipc = 0` → no ratio, not infinity;
- peaks on incompatible reference scales → no pooled midpoint.

### C. Randles–Sevcik inversion at 298 K

Use a 5 mm-diameter electrode (`A = π × 0.25² = 0.19634954084936207 cm²`), `n = 1`, `C = 1.0 × 10⁻⁶ mol cm⁻³` (1 mM), and target `D = 3.14 × 10⁻⁶ cm² s⁻¹`. For scan rates in V s⁻¹, the exact synthetic peak-current series from the fixed-coefficient equation is:

| v (V s⁻¹) | ip (A) |
|---:|---:|
| 0.005 | 6.618079750015135 × 10⁻⁶ |
| 0.010 | 9.359378139338148 × 10⁻⁶ |
| 0.025 | 1.479847620154866 × 10⁻⁵ |
| 0.050 | 2.092820574668560 × 10⁻⁵ |
| 0.100 | 2.959695240309732 × 10⁻⁵ |
| 0.200 | 4.185641149337120 × 10⁻⁵ |

Expected fit through the generated data:

- slope `9.359378139338147 × 10⁻⁵ A (V s⁻¹)^−1/2`;
- recovered `D = 3.14 × 10⁻⁶ cm² s⁻¹`;
- `R² = 1` within floating-point tolerance;
- recovered-D relative tolerance `≤ 1 × 10⁻¹⁰` for this noiseless fixture.

Unit-equivalence vector C2: the same rates entered as `5, 10, 25, 50, 100, 200 mV s⁻¹` and currents in μA must recover the same D within `1 × 10⁻¹⁰` relative error.

Refusal vectors C3:

- one scan rate, two scan rates, duplicate-only rates, `A = 0`, `C = 0`, `n = 0`, unknown temperature, or non-finite current → no estimate;
- changing concentration from `1 mM` to `1 mol cm⁻³` through a unit bug must be caught by schema/range checks, not allowed to return a tiny D;
- a curved synthetic series that passes a loose correlation but has structured residuals must be flagged for review.

### D. iR transform

Vector D1, using anodic-positive current:

- `Emeasured = [0.800, 0.900] V`;
- `I = [+0.001, −0.001] A`;
- `Ru = 20 Ω`, `f = 0.85`;
- expected `Ecorrected = [0.783, 0.917] V` exactly within `1 × 10⁻¹² V`;
- input arrays remain byte-for-byte unchanged.

Unit-equivalence vector D2: currents `[+1, −1] mA` produce the same corrected potentials after explicit conversion.

Refusal vectors D3: `Ru = null`, `Ru ≤ 0`, `f < 0`, `f > 1`, absent method/source, mismatched array lengths, or unknown current unit → no corrected view.

### E. Conductivity

Vector E1:

- `Kcell = 1.000 cm⁻¹`, `R = 100.0 Ω`;
- expected `κ = 0.01000 S cm⁻¹`.

Vector E2 in SI:

- `Kcell = 120 m⁻¹`, `R = 30 Ω`;
- expected `κ = 4.0 S m⁻¹`.

Vector E3 conversion: E1 converted to SI gives `1.000 S m⁻¹`.

Refusal vectors E4: missing calibration/source, `R ≤ 0`, `Kcell ≤ 0`, or an `Ru` value tagged as CV-only/unrelated geometry → no conductivity estimate.

### F. State and provenance

- Switching sample, condition, replicate, current unit, peak assignment, `Ru`, or correction fraction invalidates all downstream cached results whose input hash changes.
- A derived value from published inputs retains `DERIVED`, not `PUBLISHED`, provenance.
- A synthetic fixture cannot enter a published comparison even if its sample name matches.
- Downloads reproduce original and transformed values separately and include formula/method version, units, inputs, exclusions, source, and hash.

## Browser acceptance

Test at desktop plus 390 × 844 and 320 × 568 CSS-pixel viewports, at 100% and 200% zoom where feasible.

### First-load comprehension

- The route explains in its first viewport that this is a TEMPO evidence study, not a live measurement instrument.
- Source type, active sample, exact condition set, and `reported/derived/synthetic` state appear before any result.
- No placeholder scientific number or substitute curve flashes while data validate.

### Five-sample atlas

- All five exact names and Table 1 values render correctly.
- Selecting each sample updates name, condition, values, method note, and accessible description together.
- 4CyT and 4CaT show `not reported` for KCl solubility/capacity rather than zero or an empty numeric card.
- Article, DOI, SI, and licence links have correct destinations.
- If a source file/checksum fails, the page shows `DATASET UNAVAILABLE` and no substitute.

### Synthetic/upload separation

- Synthetic plots, tooltips, cards, screen-reader text, and downloads all repeat `SYNTHETIC TEACHING DATA · NOT A LAB MEASUREMENT`.
- The synthetic area cannot acquire the solid-green published marker through selection history.
- Uploaded data are labelled unverified and cannot overwrite bundled published records.
- Removing one required upload metadata field immediately replaces the affected result with `NO ESTIMATE` and names the field.

### Calculation behavior

- One or two scan rates never produce D.
- Raw potential is the default view and remains recoverable after every correction preview.
- iR controls are unavailable until eligible resistance provenance exists; no default `Ru` is inserted.
- Every corrected chart repeats `Ru`, method/source, correction fraction, reference scale, and corrected-axis wording.
- Conductivity remains unavailable when only CV data are loaded.
- Changing any upstream selection clears stale cards before the next record renders.

### Comparison

- Incompatible condition sets show a field-level difference matrix and are not automatically overlaid.
- Original reference scale/value remains visible after any reviewed conversion.
- Missing values remain in the evidence matrix with reasons and do not become zeros.
- No overall winner/rank appears.

### Accessibility and responsive behavior

- Keyboard-only users can select dataset/sample/condition, inspect readiness, operate raw/corrected controls, review results, open audit, and remove comparison items.
- Focus order follows visible causal order; autoplay/animation never steals focus.
- Readiness changes use one polite live region and do not announce every plot point.
- Plot lines have direct labels/patterns plus color, and every plot has a text/table equivalent.
- All controls have an accessible name and at least 44 × 44 CSS-pixel targets.
- At 320 px there is no document-level horizontal overflow; wide tables scroll only inside labelled containers.
- At 200% zoom, source, condition, no-estimate reason, and audit actions remain readable and operable.
- Reduced-motion mode preserves all states and evidence meaning.

## Final QA condition

Implementation may begin on the restricted v1 after the architect's contract is added and this review is reconciled against it. Any computation or claim beyond the scalar atlas and clearly synthetic/upload boundary remains blocked until its exact method, units, eligibility gates, provenance, and numerical tests are frozen.
