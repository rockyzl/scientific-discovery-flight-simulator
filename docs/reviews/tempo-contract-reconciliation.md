# TEMPO restricted-v1 contract reconciliation

Date: 2026-07-21  
Decision owner: independent scientific architecture reconciliation  
Reviewed inputs:

- [`tempo-electrochemistry-evidence.md`](../study/tempo-electrochemistry-evidence.md)
- [`tempo-multisample-ux-plan.md`](../design/tempo-multisample-ux-plan.md)
- [`tempo-inference-contract.md`](../design/tempo-inference-contract.md)
- [`tempo-plan-review.md`](tempo-plan-review.md)

## Verdict

**APPROVE the restricted v1 defined in this document. BLOCK every broader interpretation of the UX
study.**

The approved release is exactly:

1. a five-sample Zhou scalar atlas for 4HT, 4OT, 4AT, 4CyT, and 4CaT;
2. source, licence, method, and condition context beside every published value;
3. links to the Zhou article and supporting information, with no embedded or digitized Zhou curves;
4. a permanently separate synthetic teaching calculator and/or manual-entry/user-upload calculator;
5. transparent peak descriptors, optional Randles–Sevcik calculation, and optional pointwise iR
   preview only when the frozen contract's inputs and refusal gates pass; and
6. conductivity only from an independent resistance measurement and a calibrated conductivity-cell
   constant.

This reconciliation is binding when wording in the earlier UX study is broader than the evidence or
computation contract. It does not authorize Tang ingestion, publisher-figure redistribution,
reference conversion, automatic peak picking, `k0` inference, a hard reversibility class, or any
CV-derived estimate of `Ru` or conductivity.

## Reconciled release matrix

| Surface or calculation | v1 decision | Binding interpretation |
| --- | --- | --- |
| Zhou five-sample atlas | **APPROVED** | Immutable reported scalar values only; `null` remains `not reported` |
| Zhou/SI CV curves | **BLOCKED** | Link to article/SI; do not embed, trace, digitize, reconstruct, or simulate them as published curves |
| Tang source data | **BLOCKED** | Licence/reuse decision is not complete |
| Synthetic CV teaching traces | **APPROVED** | Permanent `SYNTHETIC TEACHING DATA · NOT A LAB MEASUREMENT` provenance |
| Manual-entry/user-upload traces | **APPROVED** | `USER-UPLOADED EXPERIMENTAL · UNVERIFIED`; active-request processing only |
| Automatic peak detection | **BLOCKED** | v1 accepts only reviewed `manual` or `imported` peak assignments |
| `E1/2`, `ΔEp`, `abs(ipa/ipc)` | **APPROVED** | Derived, condition-bound descriptors; never an unqualified redox potential |
| Reversibility | **APPROVED AS DESCRIPTORS ONLY** | `PARTIAL EVIDENCE` or `INCONCLUSIVE`; no categorical class, score, threshold, or rank |
| Randles–Sevcik `D` | **APPROVED WITH GATES** | Synthetic/manual-entry inputs only; fixed 298.15 K model and contract refusal rules |
| Pointwise iR preview | **APPROVED WITH GATES** | Independently measured eligible `Ru`; raw arrays immutable; no inferred/default resistance |
| Conductivity | **APPROVED AS A SEPARATE CALCULATOR** | Independent resistance plus calibrated cell constant only; never a CV-derived property |
| `k0`, stability, lifetime, battery performance | **BLOCKED** | The atlas may display Zhou's reported `k0`; the application does not infer these properties |

## Exact inconsistencies and their resolution

### 1. Published scalar atlas versus published multi-rate curves

**Inconsistency:** The UX path says users choose named samples and then inspect each sample's
multi-scan-rate CV series. Its first-load target also says the page is showing measured CVs. The
evidence review establishes that Zhou supplies table values and figure-level multi-rate evidence,
but no reusable raw current-potential arrays. The computation contract correctly excludes digitized
publisher figures.

**Resolution:** The default published route is a scalar atlas, not a curve workbench. It shows the
five reported rows, exact condition/method notes, and links to the paper/SI. A curve surface appears
only after the user explicitly enters the synthetic or user-upload route. No published badge may
appear on those traces.

### 2. Published provenance wording

**Inconsistency:** The UX grammar uses `◆ PUBLISHED EXPERIMENTAL`, which can imply a published trace
or direct measurement even when the object is a transcribed table value. The contract uses the more
precise `published_reported_scalar` and `◆ PUBLISHED REPORTED VALUE`.

**Resolution:** The contract wording wins. Each atlas quantity also repeats its Zhou condition ID
and method. A derived value keeps `ƒ DERIVED FROM SELECTED DATA`; it never inherits the published
marker from an input.

### 3. Peak assignment

**Inconsistency:** The UX audit and failure text refer to automatic peak detection and preserving
automatic versus edited assignments. Automatic peak picking is explicitly out of scope in the v1
contract.

**Resolution:** v1 accepts only reviewed `manual` or `imported` assignments. The UI may allow an edit
and preserve the prior imported/manual value in the audit record, but it must not claim automatic
detection. No reviewed assignment means `NO ESTIMATE`.

### 4. Reversibility language

**Inconsistency:** The UX card contains a placeholder for a future contract-defined assessment, and
the QA review conditionally discusses `consistent with reversible behavior`. The frozen computation
contract intentionally has no class or numeric pass threshold.

**Resolution:** v1 displays `ΔEp`, `abs(ipa/ipc)`, peak drift, exclusions, and iR status. Its only
summary states are `PARTIAL EVIDENCE` and `INCONCLUSIVE`. Approximately 59 mV at 298 K for an ideal
one-electron system may be explanatory context only. The words `reversible`, `quasi-reversible`, and
`irreversible` must not be emitted as a sample class, score, winner, or ranking.

### 5. Uncertainty wording

**Inconsistency:** The UX promises uncertainty bands, propagated/resampling uncertainty, and a
generic `value ± uncertainty` card. The contract freezes sample standard deviation for repeated
peak descriptors and an OLS slope interval for `D`; it does not freeze a general peak-location or
E1/2 resampling model.

**Resolution:** Show only uncertainty/dispersion actually produced by the frozen method. For a
single peak pair, show the descriptor without `±0` and state `dispersion unavailable`. Do not draw a
generic uncertainty band or call model disagreement calibrated uncertainty. New bootstrap,
peak-location, or replicate-aggregation methods require a later contract.

### 6. iR resistance eligibility

**Inconsistency:** The contract requires resistance source/method/context but leaves those fields as
free text. Without a binding interpretation, a client could submit `estimated from this CV`, which
would violate the evidence and QA boundary.

**Resolution:** For iR preview, `Ru` must come from an independent resistance operation such as EIS
high-frequency resistance or current interruption and must match the sample, cell, geometry,
electrolyte, and relevant measurement context. A value fitted or guessed from the same ordinary CV
trace is `RESISTANCE_INELIGIBLE`. Empty, generic, or mismatched provenance also fails closed. The
approved transform remains:

```text
Ecorrected = Emeasured - fraction * I * Ru
```

with anodic-positive `I` in A, `Ru` in ohms, fraction in `[0, 1]`, and immutable raw arrays. This is
a pointwise preview, not a claim that dynamic CV distortion has been fully reversed.

### 7. Conductivity must not reuse CV `Ru`

**Inconsistency:** The UX correctly calls conductivity a separate input, but broad phrases such as
`independent resistance and cell constant` could still allow an uncompensated resistance measured
for a different CV geometry. The contract's generic `measurement_context` needs the stricter QA
meaning.

**Resolution:** Conductivity requires both:

- resistance measured independently for the conductivity measurement cell and sample condition;
- a positive calibrated cell constant for that same cell/context.

The sole v1 equation is:

```text
conductivity = cell_constant / resistance
```

A normal CV trace, a CV-fitted resistance, or a same-project `Ru` from an unrelated geometry is
`RESISTANCE_INELIGIBLE` or `CELL_CONSTANT_INELIGIBLE`. No conductivity value may appear in the
CV-derived results group.

### 8. Published comparison versus curve comparison

**Inconsistency:** The UX comparison tray offers CV overlay and rate-fit views for named published
samples. The approved published source does not provide reusable arrays.

**Resolution:** The Zhou atlas compares reported scalars only, with missing entries visible and no
overall winner. Curve overlays and derived comparisons are limited to records within the same
synthetic dataset or compatible user-upload condition set. Published, synthetic, and uploaded
records must never share an unlabeled overlay or pooled fit.

### 9. Source record checksum

**Potential ambiguity:** The contract requires `record_checksum`, but the Zhou atlas is a curated
transcription rather than a downloaded raw-data file.

**Resolution:** Label it as the checksum of the deterministic local reference record, not a checksum
of publisher raw data. The audit must include DOI, Table 1 identity, retrieval date, builder/version,
and exact five-row integrity tests. A checksum proves local byte identity, not scientific authorship
or publisher endorsement.

### 10. Deferred features shown in the UX study

**Inconsistency:** The UX presents matched curve overlays, iR sensitivity, conductivity, and
diffusivity as one complete routine journey, while the QA review permits all of these to be deferred.

**Resolution:** Empty future cards are not required. The product may ship the atlas first, then the
synthetic/manual-entry descriptors, then gated optional calculations. An absent slice must be absent
or say `NO ESTIMATE`; it must not display sample numbers, disabled placeholder values, or fabricated
demo results.

## Binding computation and refusal checks

The formulas and numerical vectors in the computation contract and QA review are consistent and are
approved without modification:

- `E1/2 = (Epa + Epc) / 2`
- `ΔEp = Epa - Epc`
- current ratio `= abs(ipa / ipc)` with division-by-zero refusal
- 298.15 K Randles–Sevcik fit and inversion, separately for anodic/cathodic branches
- immutable pointwise iR transform above
- independent conductivity `κ = Kcell / R`

At minimum, implementation must test QA vectors A through F and fail closed for missing units,
invalid peaks, fewer than three distinct rates, invalid metadata, `R² < 0.98`, ineligible
resistance/cell constant, source-integrity failure, and stale input hashes. `R² >= 0.98` remains a
software QC gate, not proof of diffusion control.

## Implementation start condition

Implementation may begin for the approved restricted v1 if the team treats this document as the
precedence rule for the older UX study. It is **BLOCKED** if any implementation:

- embeds or reconstructs Zhou/Tang curves;
- shows the scalar atlas as a measured multi-rate trace dataset;
- automatically assigns peaks;
- issues a hard reversibility class;
- infers `Ru` or conductivity from ordinary CV;
- substitutes missing values or metadata;
- mixes provenance classes; or
- allows a stale derived result to survive an upstream input change.

No broader inference is approved by this reconciliation.
