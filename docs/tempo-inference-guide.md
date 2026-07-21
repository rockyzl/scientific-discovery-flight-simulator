# TEMPO v1 inference guide

## Plain-language workflow

The page makes two things available without mixing them:

1. **Look up reported values.** Select any of five Zhou TEMPO derivatives and compare the attributed
   scalar values. The page does not rank them.
2. **Test a calculation workflow.** Edit six rows of explicitly synthetic peak assignments and send
   them to the same-origin analysis API.

The analysis path is:

```text
six scan rates → reviewed Epa/Epc/ipa/ipc
               → E1/2, ΔEp, and current-ratio descriptors
               → separate anodic/cathodic Randles–Sevcik fits when eligible
               → descriptor-only reversibility evidence
               → optional pointwise iR preview when independent Ru evidence is eligible
```

Conductivity follows another path:

```text
independently measured resistance + calibrated cell constant → conductivity
```

It is never inferred from the CV table.

## What the descriptors mean

For each reviewed peak pair:

- apparent midpoint potential: `E1/2 = (Epa + Epc) / 2`;
- peak separation: `ΔEp = Epa − Epc`;
- peak-current ratio: `abs(ipa / ipc)`.

The result remains labelled `ƒ DERIVED FROM SELECTED DATA`. It is not renamed a published value,
even when a future calculation uses published input.

Across eligible rows, v1 may report the arithmetic mean, sample standard deviation, and count. If
only one value exists, dispersion is unavailable; the UI must not show `±0`.

## Reversibility is evidence, not a hard class

The page may show ΔEp, current ratio, peak-position changes with scan rate, exclusions, and iR
status. The only summary states are:

- `PARTIAL EVIDENCE`
- `INCONCLUSIVE`

v1 does not label a sample reversible, quasi-reversible, or irreversible and does not generate a
score, winner, or rank. The ideal one-electron 59 mV value at 298 K may be explanatory context, not
a classifier.

## Diffusion-coefficient gate

v1 uses the 298.15 K Randles–Sevcik equation:

```text
ip = 2.69e5 × n^(3/2) × A × C × sqrt(D) × sqrt(v)
```

Canonical compute units are A, cm², mol cm⁻³, cm² s⁻¹, and V s⁻¹. At the request boundary, the
declared equivalents `mV`, `mA`, `uA`/`µA`/`μA`, and `mV/s` are converted once to V, A, and V/s.
Although the frozen field names carry canonical suffixes, their numeric values are interpreted in
the explicitly declared units. The original request stays unchanged and every identity or scaling
conversion is recorded in `audit.unit_conversions`. Unknown or missing units fail closed.

The calculation requires:

- temperature within 298.15 ± 0.50 K;
- positive electron count, electrode area, and concentration;
- at least three distinct eligible scan rates;
- reviewed, valid peak assignments under one compatible condition and potential scale.

The API fits `abs(ip)` against `sqrt(v)` with an intercept, separately for anodic and cathodic
branches. A positive slope and R² of at least 0.98 are software QC gates. They do not prove that the
real experiment is diffusion controlled. v1 reports fit diagnostics, residuals, included/excluded
trace IDs, branch-specific D, and the frozen slope-based 95% interval.

Missing metadata, too few rates, invalid peaks, incompatible conditions, a nonpositive slope, or
R² below the gate returns `NO ESTIMATE` with a reason. The browser never supplies typical defaults.

## Optional iR preview

Raw potential remains the default and is never mutated. If eligible resistance evidence is
provided, the API may calculate:

```text
Ecorrected = Emeasured − fraction × I × Ru
```

with anodic-positive current in A, Ru in Ω, and fraction from 0 to 1.

Ru must come from an independent operation such as EIS high-frequency resistance or current
interruption and must match the sample, cell, geometry, electrolyte, and measurement context. A
value guessed or fitted from the same ordinary CV is ineligible. Every corrected result repeats Ru,
method, source, context, fraction, raw hash, and corrected hash. A 100% fraction is not labelled
automatically safe.

This is enforced with records, not a checkbox or a note such as `same sample`. The request names an
independent resistance operation and supplies separate resistance and CV records. Their sample,
cell, geometry, electrolyte, and condition IDs must agree, and the CV IDs must agree with the main
analysis request. The method is limited to `EIS high-frequency resistance` or
`current interruption`. Short or generic placeholders such as `x`, `test`, or `banana` fail closed.
Adding a suffix does not bypass the check: identifier tokens are compared case-insensitively after
outer whitespace is trimmed, so `test-01`, `banana-01`, and `unknown-01` are also rejected.

### Browser flow for iR

1. Turn on **Optional pointwise iR preview**.
2. Enter Ru, correction fraction, allowed method, operation ID, cell ID, geometry ID, and
   electrolyte ID—or load the clearly labelled structured teaching record.
3. The page pairs those IDs with the visible fixed teaching sample and condition and creates two
   matching records: the independent resistance record and the CV record.
4. Inspect the record and explicitly check the review confirmation. The preset never checks it.
5. Submit. Without confirmation or with invalid IDs, the result remains `NO ESTIMATE` and raw
   potentials remain unchanged.

## Independent conductivity

The conductivity form calls a different endpoint and uses only:

```text
κ = Kcell / R
```

where Kcell is a positive calibrated cell constant in m⁻¹ and R is a positive independently measured
resistance in Ω for the same conductivity cell/sample context. The output is S m⁻¹. Calibration
source, context, and temperature are required.

The calibration record must be reviewed, identify the calibration, cell, and geometry, and use
either a certified cell constant or a standard-solution calibration. A separate reviewed context
must identify an independent conductivity-cell resistance operation. Its sample, cell, geometry,
and condition IDs must exactly match the measurement record; calibration ID, cell, and geometry
must also match. Generic prose or boolean-only evidence is not auditable and is rejected.

### Browser flow for conductivity

1. Enter resistance, cell constant, temperature, calibration method/ID, resistance-operation ID,
   and sample/cell/geometry/condition IDs—or load the clearly labelled structured teaching record.
2. The page constructs a calibration record plus matching resistance and measurement records from
   those visible IDs.
3. Explicitly confirm both reviews: one for the calibration and one for the independent resistance
   and matching context. The preset leaves both unchecked.
4. Calculate. A missing confirmation, invalid identifier, or mismatched record is refused rather
   than replaced by a default.

Changing any field aborts an in-flight request, clears the old request/response audit display, and
returns the result card to `NO ESTIMATE`. The user must submit the current record again.

A CV-fitted resistance or Ru from unrelated CV geometry is not eligible. The conductivity result
never appears in the CV-derived result group.

## API and refusal behavior

The page uses:

- `GET /tempo/reference-v1.json`
- `POST /api/tempo/analyze`
- `POST /api/tempo/conductivity`

Analysis and conductivity requests use `schema_version: "tempo-inference-v1"`. The browser first
serializes the entire request with recursive object keys sorted, compact JSON separators, UTF-8,
and unescaped Unicode. Those exact bytes become the POST body. The browser sends their SHA-256 in
`X-Tempo-Input-Hash`; the server independently hashes the received bytes, rejects a mismatched
header, and returns its own byte hash. This avoids JavaScript/Python number-serialization drift.
The browser accepts a successful result only when schema, request ID, `derived`
provenance, method version, input hash, warnings, limitations, and audit all validate. A response
for an earlier request is discarded.

The response audit preserves the exact original request, lists every unit conversion, and aggregates
the trace IDs excluded by the separate anodic/cathodic diffusion branches. Branch and response-level
exclusion records must agree.

Every calculation ends in `estimate_available` or `no_estimate`. A refusal includes:

- code and plain-language message;
- missing and invalid fields;
- excluded trace IDs;
- audit ID.

Frozen refusal codes cover invalid schema/units/metadata, insufficient rates, incompatible
conditions, invalid peaks, failed fit QC, ineligible resistance or cell constant, and source
integrity failure. In a refusal, the numeric card is replaced by `NO ESTIMATE`; it never displays
zero, infinity, a cached prior value, or a synthetic fallback.

## Exact release limits

v1 does not provide digitized Zhou curves, Tang data ingestion, automatic peak picking,
reference-scale conversion, k0 inference, a hard reversibility class, CV-derived Ru, CV-derived
conductivity, battery-performance prediction, or a sample ranking.
