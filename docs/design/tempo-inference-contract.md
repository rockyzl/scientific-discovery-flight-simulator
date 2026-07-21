# TEMPO inference contract — v1

Status: **frozen for implementation**  
Date: 2026-07-21  
Scope: published scalar atlas, synthetic teaching traces, and user-uploaded CV analysis.  
Out of scope: digitized publisher figures, Tang source-data redistribution, automatic peak picking,
reference-scale conversion, categorical reversibility, and `k0` inference.

## 1. Non-negotiable model

The system keeps these evidence classes separate:

| `provenance` | Allowed content | User label |
|---|---|---|
| `published_reported_scalar` | values transcribed from a cited table | `◆ PUBLISHED REPORTED VALUE` |
| `user_uploaded_experimental_unverified` | user-supplied traces/metadata | `■ USER-UPLOADED EXPERIMENTAL · UNVERIFIED` |
| `synthetic_teaching` | generated fixtures | `◇ SYNTHETIC TEACHING DATA · NOT A LAB MEASUREMENT` |
| `derived` | result calculated from identified inputs | `ƒ DERIVED FROM SELECTED DATA` |

`derived` never becomes `published`, even when its inputs are published. Missing fields remain
missing; no typical/default scientific values may be inserted. Every result has an input hash and
method version. A changed input invalidates the result.

## 2. Published atlas schema

`ReferenceDataset` requires:

- `schema_version: "tempo-reference-v1"`
- `dataset_id`, `title`, `citation`, `doi`, `article_url`, `supporting_information_url`
- `license_id`, `license_url`, `reuse_note`, `retrieved_at`, `record_checksum`
- `conditions: ReferenceCondition[]`
- `samples: ReferenceSample[5]`

The conditions are measurement-specific; the product must not attach the direct 25 mV/s CV
condition to D, k0, or solubility:

- `electrochemistry_base`: 1 mM analyte, 0.5 M KCl, 5 mm glassy-carbon RDE working electrode,
  Pt-foil counter, SCE reference, potentials reported vs SHE, room temperature, ≥20 min N2 purge
  and N2 blanket.
- `formal_potential_direct_cv`: base plus pH 7, 25 °C, and 25 mV s⁻¹; 4AT/4CaT pH adjustment
  remains in the source note.
- `diffusion_multi_rate_cv`: base plus rates 5, 10, 25, 50, 100, and 200 mV s⁻¹; method
  `Randles–Sevcik`; do not add an unreported pH.
- `rate_constant_rde`: base plus rotations 200–900 rpm; method `Koutecký–Levich/RDE`.
- `solubility_water` and `solubility_kcl`: UV-visible method after 48 h equilibration at room
  temperature, with medium attached.

`ReferenceSample` requires `sample_id`, `preferred_name`, `source_table`, `provenance`, and typed
quantities `{value, unit, status, condition_id, method_id}`. `status` is `reported` or
`not_reported`; a not-reported value is JSON `null`, never zero.

Frozen Zhou Table 1 values:

| id | name | E0 V vs SHE | D cm²/s | k0 cm/s | water M | 0.5 M KCl M | capacity Ah/L |
|---|---|---:|---:|---:|---:|---:|---:|
| `4ht` | 4-hydroxy-TEMPO | 0.812 | 3.14e-6 | 4.45e-3 | 2.11 | 1.25 | 33.5 |
| `4ot` | 4-oxo-TEMPO | 0.910 | 4.61e-6 | 1.05e-2 | 1.22 | 0.79 | 21.2 |
| `4at` | 4-amino-TEMPO | 0.895 | 3.77e-6 | 4.01e-3 | 5.79 | 4.80 | 128.6 |
| `4cyt` | 4-cyano-TEMPO | 0.881 | 6.23e-6 | 4.29e-3 | 2.6e-2 | null | null |
| `4cat` | 4-carboxy-TEMPO | 0.776 | 2.64e-6 | 2.25e-3 | 2.1e-2 | null | null |

Source DOI is `10.1039/D0RA03424J`; licence is `CC-BY-NC-3.0`. v1 links to the article/SI and does
not ship their plot arrays.

## 3. CV analysis input schema

`CVAnalysisRequest` requires:

- `schema_version: "tempo-inference-v1"`, `request_id`
- `source: {provenance, source_id, checksum}`; provenance is upload or synthetic only in v1
- `sample: {sample_id, preferred_name, molecular_form, concentration_mol_cm3}`
- `condition: CVCondition`
- `traces: CVTrace[]`
- `peak_assignments: PeakAssignment[]`
- `requested: ("peak_descriptors" | "diffusion" | "ir_correction")[]`
- optional `ir_correction: IRCorrectionInput`

`CVCondition` requires:

- solvent; supporting-electrolyte identity and concentration
- pH or explicit `not_measured`; `temperature_K`
- working-electrode material and `working_electrode_area_cm2`
- counter electrode; reference electrode and `potential_scale`
- `electron_count`; atmosphere; preprocessing description
- original units plus canonical-unit conversion record

`CVTrace` requires `trace_id`, `scan_rate_v_s`, `replicate_id`, `cycle_number`, equal-length
`potential_v[]` and `current_a[]`, `potential_scale`, and `transformation: "raw"`. Arrays require at
least 20 finite points; scan rate is positive. Duplicate trace IDs fail validation.

`PeakAssignment` requires `trace_id`, `epa_v`, `epc_v`, `ipa_a`, `ipc_a`, `assignment_source`
(`manual` or `imported`), and `reviewed: true`. v1 does not automatically choose peaks.

Canonical compute units are V, A, Ω, K, cm², mol cm⁻³, cm² s⁻¹, and V s⁻¹. The boundary converts
declared units once and records the conversion. Unitless scientific inputs are rejected.

## 4. Peak descriptors

For each reviewed compatible assignment:

- `delta_ep_v = epa_v - epc_v`
- `e_half_v = (epa_v + epc_v) / 2`
- `peak_current_ratio = abs(ipa_a / ipc_a)`

Require finite values, `epa_v >= epc_v`, `ipa_a > 0`, `ipc_a < 0`, matching trace/reference scale,
and nonzero currents. Failure returns no descriptor for that trace plus a reason.

Across eligible traces, report individual descriptors, arithmetic mean, sample standard deviation,
and count. With fewer than two values, dispersion is `unavailable`; do not show `±0`. Do not label
the result simply `redox potential`; use `apparent midpoint potential (E1/2)`.

## 5. Reversibility evidence

v1 reports only per-rate and range/trend descriptors:

- `delta_ep_v`
- `peak_current_ratio`
- anodic/cathodic peak-position change with scan rate
- missing/excluded assignments and iR-correction status

The response wording is `PARTIAL EVIDENCE` or `INCONCLUSIVE`. The API has no reversible,
quasi-reversible, irreversible, score, rank, or pass threshold. Approximately 59 mV for an ideal
one-electron reversible couple at 298 K may appear only as explanatory context, never a classifier.

## 6. Diffusion estimate

v1 uses the 298.15 K Randles–Sevcik equation only:

`ip = 2.69e5 * n^(3/2) * A * C * sqrt(D) * sqrt(v)`

where `ip` is A, `A` cm², `C` mol cm⁻³, `D` cm² s⁻¹, and `v` V s⁻¹.

Rules:

1. Require temperature `298.15 K ± 0.50 K`, positive finite `n`, `A`, `C`, and at least three
   distinct eligible scan rates; five are preferred but not mandatory.
2. Fit ordinary least squares **with intercept** to `y = abs(ip)` versus `x = sqrt(v)`, separately
   for anodic and cathodic assignments. Never silently average branches.
3. Require positive slope. Compute `D = (slope / (2.69e5*n^(3/2)*A*C))^2`.
4. Return slope, intercept, `R²`, residuals, included/excluded trace IDs, D, and method version.
5. `R² < 0.98` withholds D as `FIT_QC_FAILED`. `R² >= 0.98` is a software QC gate, not proof of
   diffusion control. Always display that limitation.
6. Use OLS slope standard error and a two-sided 95% Student-t interval (`df = N-2`); transform both
   non-negative slope bounds through the D equation. If a lower slope bound is negative, D lower
   bound is zero and the result receives `BOUNDARY_SENSITIVE`.
7. Refuse non-finite data, fewer than three distinct rates, zero/negative metadata, incompatible
   conditions/reference scales, unresolved peaks, or unknown units.

No other temperature, Nicholson analysis, RDE `k0`, or diffusion-controlled claim is in v1.

## 7. iR-corrected view

`IRCorrectionInput` requires positive finite `ru_ohm`, `fraction` in `[0,1]`, and the following
structured provenance (generic free text is not accepted):

```json
{
  "resistance_source": {
    "operation_id": "operation-eis-17",
    "provenance": "independent_resistance_measurement"
  },
  "measurement_method": "EIS high-frequency resistance",
  "measurement_context": {
    "reviewed": true,
    "resistance": {
      "operation_id": "operation-eis-17",
      "sample_id": "tempo-teaching",
      "cell_id": "cell-tempo-01",
      "geometry_id": "geometry-gce-5mm",
      "electrolyte_id": "electrolyte-kcl-05m",
      "condition_id": "condition-298k"
    },
    "cv": {
      "sample_id": "tempo-teaching",
      "cell_id": "cell-tempo-01",
      "geometry_id": "geometry-gce-5mm",
      "electrolyte_id": "electrolyte-kcl-05m",
      "condition_id": "condition-298k"
    }
  }
}
```

`measurement_method` is exactly `EIS high-frequency resistance` or `current interruption`.
`resistance_source.provenance` is exactly `independent_resistance_measurement`. Operation IDs must
match across source and resistance context. The reviewed resistance and CV records must match on
`sample_id`, `cell_id`, `geometry_id`, `electrolyte_id`, and `condition_id`; the CV sample and
condition must also match the enclosing analysis request. Identifiers are 6–128 characters,
contain a namespace separator (`-`, `_`, `:`, or `.`), and are not placeholders such as `x`,
`test`, `sample`, `cell`, `condition`, or `banana`. Validation trims outer whitespace, compares
case-insensitively, and tokenizes on the allowed separators so suffixes do not make placeholder
tokens valid: for example, `test-01`, `banana-01`, and `unknown-01` are rejected. Domain-qualified
IDs such as `tempo-sample-01` and `conductivity-cell-01` remain valid.

With anodic-positive current, transform each raw point without mutation:

`corrected_potential_v[i] = raw_potential_v[i] - fraction * current_a[i] * ru_ohm`

The response contains raw and corrected arrays, Ru, fraction, source/method/context, formula version,
and separate hashes. No Ru default is allowed. Unknown units, absent provenance, incompatible array
lengths, invalid/generic provenance, a context mismatch, `ru_ohm <= 0`, or fraction outside `[0,1]`
returns raw only with `NO_IR_CORRECTION` and `RESISTANCE_INELIGIBLE` where applicable.
`fraction = 0` is a valid identity preview; 100% is not labelled automatically safe.

## 8. Independent conductivity input

Conductivity is a separate request, never a CV inference:

`ConductivityRequest = {schema_version, request_id, resistance_ohm, cell_constant_m_inv,
calibration_source, measurement_context, temperature_K}`, with these structured records:

```json
{
  "calibration_source": {
    "calibration_id": "calibration-kcl-2026-01",
    "method": "certified_cell_constant",
    "cell_id": "conductivity-cell-01",
    "geometry_id": "conductivity-geometry-01",
    "reviewed": true
  },
  "measurement_context": {
    "calibration_id": "calibration-kcl-2026-01",
    "reviewed": true,
    "resistance": {
      "operation_id": "resistance-operation-01",
      "independent": true,
      "resistance_kind": "conductivity_cell",
      "sample_id": "tempo-sample-01",
      "cell_id": "conductivity-cell-01",
      "geometry_id": "conductivity-geometry-01",
      "condition_id": "conductivity-condition-298k"
    },
    "measurement": {
      "sample_id": "tempo-sample-01",
      "cell_id": "conductivity-cell-01",
      "geometry_id": "conductivity-geometry-01",
      "condition_id": "conductivity-condition-298k"
    }
  }
}
```

Compute `conductivity_s_m = cell_constant_m_inv / resistance_ohm`, following IUPAC `Kcell = κR`.
Require positive finite resistance and cell constant. Calibration must be reviewed and use exactly
`certified_cell_constant` or `standard_solution_calibration`. Its ID, cell, and geometry must match
the reviewed measurement context. The independent resistance record must have
`resistance_kind: "conductivity_cell"`; resistance and measurement records must match on sample,
cell, geometry, and condition. All identifiers obey the non-placeholder rule in section 7. A
CV-only Ru is ineligible. Invalid calibration returns `CELL_CONSTANT_INELIGIBLE`; invalid or
mismatched resistance context returns `RESISTANCE_INELIGIBLE`. Preserve inputs, units, and method
version.

## 9. Refusal response

Every calculation returns either `status: "estimate_available"` or `status: "no_estimate"`.
No-estimate requires:

`{code, message, missing_fields[], invalid_fields[], excluded_trace_ids[], audit_id}`.

Frozen codes: `SCHEMA_INVALID`, `UNIT_MISSING`, `METADATA_MISSING`, `INSUFFICIENT_RATES`,
`INCOMPATIBLE_CONDITIONS`, `PEAKS_INVALID`, `FIT_QC_FAILED`, `RESISTANCE_INELIGIBLE`,
`CELL_CONSTANT_INELIGIBLE`, `SOURCE_INTEGRITY_FAILED`.

The browser replaces the numeric result with this explanation. It never renders zero, infinity,
`N/A` in a numeric slot, a cached stale value, or a synthetic fallback.

## 10. Browser calculation API

Transport is JSON over same-origin HTTP:

- `GET /tempo/reference-v1.json` → `ReferenceDataset`; immutable static file, checksum validated.
- `POST /api/tempo/analyze` with `CVAnalysisRequest` → `CVAnalysisResponse`.
- `POST /api/tempo/conductivity` with `ConductivityRequest` → `ConductivityResponse`.

Success response requires `schema_version`, `request_id`, `status`, `provenance: "derived"`,
`method_version`, `input_hash`, `results`, `warnings[]`, `limitations[]`, and `audit` containing exact
inputs, conversions, exclusions, formulas, and source identity. Validation failure uses HTTP 422;
integrity failure uses 409; malformed JSON uses 400. No response may omit status or provenance.

The browser treats responses as untrusted: validate schema/request ID/input hash before rendering.
Changing dataset, sample, condition, trace, peak assignment, units, Ru, or fraction clears current
results before issuing a new request. Late responses with an old request ID are discarded.

Uploaded arrays are processed for the active request only and are not persisted by v1. Downloads
contain original inputs and derived outputs separately.

## 11. Frozen numerical acceptance vectors

- Peaks: `Epa=.842`, `Epc=.782`, `ipa=.000150`, `ipc=-.000147` → `E1/2=.812`, `ΔEp=.060`,
  ratio `1.0204081633`.
- Randles–Sevcik: `A=0.19634954084936207`, `n=1`, `C=1e-6`, `D=3.14e-6`, rates
  `[.005,.01,.025,.05,.1,.2]` produce currents
  `[6.618079750015135e-6,9.359378139338148e-6,1.479847620154866e-5,
  2.092820574668560e-5,2.959695240309732e-5,4.185641149337120e-5]` A; recovered D is `3.14e-6`
  with relative error ≤ `1e-10`.
- iR: `E=[.800,.900]` V, `I=[.001,-.001]` A, `Ru=20`, `fraction=.85` → `[.783,.917]` V; raw
  arrays unchanged.
- Conductivity: `Kcell=100 m⁻¹`, `R=100 Ω` → `κ=1.0 S m⁻¹`; `Kcell=120 m⁻¹`, `R=30 Ω` →
  `κ=4.0 S m⁻¹`.

Arithmetic tolerance is `1e-12` absolute for direct V calculations and `1e-9` for ratios. Unit-
equivalent mV/mA/μA inputs must produce the same canonical results. All refusal cases in the QA
review are mandatory tests.

## 12. Release boundary

v1 may publish the five reported scalar records and run the frozen calculations on synthetic or
user-uploaded traces. It may truthfully show `NO ESTIMATE` for unsupported outputs. It may not embed
digitized Zhou curves, ingest Tang data, infer conductivity/Ru from CV, calculate `k0`, convert
reference scales, or issue categorical reversibility claims without a new contract and review.
