# TEMPO final independent QA

Date: 2026-07-21  
Verdict: **APPROVE**

The restricted TEMPO v1 implementation is approved for the reviewed local release scope. The two
original audit/normalization blockers, the second-round provenance blocker, and the third-round
tokenized-placeholder bypass are resolved. Core, HTTP, browser-contract, and visible-browser checks
now agree on the same fail-closed boundaries.

## Structured iR provenance: PASS

The authoritative core now requires all of the following before returning corrected potentials:

- `measurement_method` is exactly `EIS high-frequency resistance` or `current interruption`;
- source provenance is exactly `independent_resistance_measurement`;
- the source and resistance records use the same valid operation ID;
- the measurement context is explicitly reviewed;
- resistance and CV records match on `sample_id`, `cell_id`, `geometry_id`, `electrolyte_id`, and
  `condition_id`;
- the CV record's sample and condition also match the enclosing analysis request.

Independent adversarial tests confirmed that every one of the five context mismatches returns
`RESISTANCE_INELIGIBLE`. Unknown method, wrong provenance, operation mismatch, an unreviewed record,
and the previous legacy free-text payload are also refused.

The identifier validator trims and case-folds input and rejects generic tokens separated by `-`,
`_`, `:`, or `.`. These attempted operation IDs all failed closed:

```text
test-01
banana-01
unknown-01
"  TeSt-01  "
"  UNKNOWN-01  "
```

Valid structured identifiers such as `operation-eis-17` remain eligible. Both allowed iR methods
were independently exercised successfully.

For an eligible record, the frozen numerical vector remains correct and immutable:

```text
raw potential         [0.800, 0.900] V
current               [+0.001, -0.001] A
Ru                    20 ohm
fraction              0.85
corrected potential   [0.783, 0.917] V
original request      unchanged
```

Raw and corrected arrays retain separate hashes. The output is labelled a pointwise preview and
does not claim that dynamic CV distortion has been fully reversed.

## Structured conductivity provenance: PASS

The independent conductivity endpoint now requires:

- a reviewed calibration using exactly `certified_cell_constant` or
  `standard_solution_calibration`;
- valid calibration, cell, and geometry IDs;
- a reviewed resistance/measurement context;
- `independent: true` and `resistance_kind: "conductivity_cell"`;
- identical `sample_id`, `cell_id`, `geometry_id`, and `condition_id` in resistance and measurement
  records;
- calibration ID, cell ID, and geometry ID linked to the same measurement context.

Independent tests changed each of the four matching fields one at a time; all were refused with
`RESISTANCE_INELIGIBLE`. Unreviewed calibration, unreviewed measurement, non-independent resistance,
CV Ru, calibration-link mismatch, generic legacy records, and tokenized placeholder operation IDs
also failed closed.

The valid frozen vectors remain:

```text
Kcell=100 m-1, R=100 ohm -> 1.0 S/m
Kcell=120 m-1, R=30 ohm  -> 4.0 S/m
```

Conductivity remains a separate request using only `conductivity = cell_constant / resistance`; no
conductivity value is inferred from CV.

## Browser workflow: PASS

Visible Chrome was used to exercise the actual page served at `/tempo/`:

- the published atlas loaded all five expected samples;
- loading the structured iR teaching record left its review checkbox false;
- after manual review confirmation, analysis completed and showed an 85% iR preview using 20 ohm
  across six corrected traces;
- changing Ru immediately replaced all prior analysis cards with `NO ESTIMATE`, cleared both audit
  panes, and invalidated the pending/current request;
- loading the conductivity teaching record left both calibration and resistance review boxes false;
- after manually checking both, the page returned `1 S/m` and explicitly labelled it independent
  and not derived from CV;
- changing the cell constant immediately cleared the conductivity result and both audit panes.

The frontend builds the same structured records required by the API. It does not infer review from
clicking a teaching loader. Form input events abort in-flight requests, clear stored request IDs and
numeric outputs, and reset audit text; response request ID and input hash are checked before any
new value is rendered.

A final visible-browser corroboration found no document overflow at either 390 px or 320 px.

## Previous blockers and scientific boundaries: PASS

### Unit conversion and original-request audit

I independently rescaled the frozen six-rate C2 vector to `mV`, `mV/s`, and each supported current
unit: `mA`, ASCII `uA`, micro sign `µA`, and Greek mu `μA`. Every case returned:

```text
anodic D   = 3.1400000000000017e-06 cm2/s
cathodic D = 3.1400000000000017e-06 cm2/s
input object unchanged                     true
input_hash remains hash of original input  true
```

`audit.unit_conversions` records exactly one conversion to canonical units: potential and scan rate
use factor `1e-3`; mA uses `1e-3`; all three microamp spellings use `1e-6`. The untouched original is
retained in `audit.exact_input`. The HTTP boundary hashes the exact UTF-8 request bytes and rejects a
mismatched `X-Tempo-Input-Hash`.

### Excluded traces

With six valid traces and only three reviewed assignments, exclusions agree at every level:

```text
anodic.excluded_trace_ids   [trace-4, trace-5, trace-6]
cathodic.excluded_trace_ids [trace-4, trace-5, trace-6]
audit.excluded_trace_ids    [trace-4, trace-5, trace-6]
```

### Reversibility and model limits

- Reversibility output is descriptor-only: `PARTIAL EVIDENCE` or `INCONCLUSIVE`, with
  `classification: null`.
- No sample is emitted as reversible, quasi-reversible, irreversible, a winner, or a rank.
- `R2 >= 0.98` is displayed only as a software QC gate, never proof of diffusion control or
  mechanism.
- Published Zhou scalars, synthetic teaching traces, and independent measurement inputs remain
  visibly and structurally separated.
- The page does not digitize or reconstruct publisher CV curves, perform reference-scale
  conversion, pick peaks automatically, or infer `k0`.

## Automated verification

All commands were run from the isolated TEMPO worktree after the final placeholder fix.

```text
.venv/bin/pytest tests/test_tempo_science.py tests/test_tempo_server.py tests/test_tempo_ui_contract.py -q
75 passed in 7.39s

.venv/bin/pytest -q
147 passed in 10.07s

.venv/bin/ruff check .
All checks passed!

node --check demo/tempo.js
exit 0

git diff --check
exit 0
```

The tests include direct core and real HTTP refusal vectors for generic legacy provenance,
tokenized placeholders, review flags, method allowlists, operation links, five-field iR mismatches,
four-field conductivity mismatches, calibration links, CV Ru, raw-body hashes, stale response
contracts, and the prior unit/exclusion regressions.

## Residual limits, not release blockers

- Structured records and review confirmations provide an auditable software boundary; they do not
  cryptographically prove that a physical instrument produced the supplied record.
- Teaching presets are synthetic fixtures, not laboratory measurements. Review checkboxes must
  continue to require an explicit user action.
- iR correction remains a pointwise preview. It does not establish absence of over-compensation or
  recovery from dynamic distortion.
- The conductivity calculation assumes the supplied calibrated cell constant and independent
  resistance are scientifically appropriate; the v1 software verifies the reviewed linkage and
  allowed metadata, not the physical calibration procedure itself.
- This approval covers the reviewed local build. It is not evidence of a production deployment,
  production monitoring, or a license decision for future commercial reuse of CC BY-NC source
  material.

## Release decision

**APPROVE.** No unresolved blocker remains within the frozen TEMPO v1 scope. Release should preserve
the reviewed structured schemas, explicit review gates, adversarial regression vectors, stale-output
clearing, and the existing scientific limitation language.
