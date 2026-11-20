# RFBzero compatibility spike

**Status:** GO for a narrow, optional, version-pinned batch adapter.  
**Date run:** 2026-07-20  
**Scope:** package/API compatibility in an isolated temporary environment only.

This spike does not calibrate, validate, or make any physical-performance claim
about an RFB chemistry, cell, stack, instrument, or operating protocol. It does
not establish that RFBzero is a digital twin or that its numerical outputs
transfer beyond a frozen synthetic scenario.

## Decision

`rfbzero==1.0.1` is installable and importable in the current Python 3.12.12
environment, which is within this project's `>=3.11` requirement. Its metadata
declares `Requires-Python: >=3.10`, so the declared support range includes the
project floor. The spike directly executed only Python 3.12.12; Python 3.11 was
not separately exercised.

The package's `ConstantCurrent` API accepts each of the proposed protocol's
five inputs, including independently signed charge and discharge currents. Its
`CyclingResults` trace is sufficient for a project-owned reducer to derive
synthetic outcome observables. It does not return the project's desired energy,
efficiency, retention, QC, or provenance schema directly.

**GO:** add an optional adapter only when it pins the distribution and resolved
environment, validates the project protocol before calling RFBzero, constructs
a fresh cell model for every execution, owns result reduction and serialization,
and records the package/artifact provenance below. Do not use RFBzero itself as
the campaign persistence or replay mechanism.

## Environment and isolation

The current `python3` was:

```text
Python 3.12.12
/home/lu2/dev/personal/records/job-hunting/.venv/bin/python3
pip 25.0.1 from .../job-hunting/.venv/lib/python3.12/site-packages/pip
```

The standard-library isolation attempt failed before package installation:

```console
$ python3 -m venv "$SPIKE_ROOT/venv"
/home/lu2/dev/personal/records/job-hunting/.venv/bin/python3: No module named venv
```

No project environment, lockfile, or source file was changed. The successful
isolation used `uv 0.10.10`, a fresh directory under `/tmp`, no project
discovery, no Python download, and the current `python3` path:

```console
$ SPIKE_ROOT="$(mktemp -d /tmp/rfbzero-compatibility.XXXXXX)"
$ uv venv --no-project --no-managed-python --no-python-downloads --seed \
    --python "$(command -v python3)" "$SPIKE_ROOT/venv"
$ uv pip install --no-cache --python "$SPIKE_ROOT/venv/bin/python" \
    'rfbzero==1.0.1'
```

Observed resolver output:

```text
Using CPython 3.12.12 interpreter at:
  /home/lu2/dev/personal/records/job-hunting/.venv/bin/python3
Resolved 3 packages
Installed:
  numpy==2.5.1
  rfbzero==1.0.1
  scipy==1.18.0
```

The temporary interpreter reported `Python 3.12.12`, with
`sys.executable` in the new `/tmp/.../venv`; its `sys.base_prefix` was
`/home/lu2/.local/share/uv/python/cpython-3.12.12-linux-x86_64-gnu`. Thus the
tested environment is isolated and version-matched to the active interpreter,
but it is not a test of every Python implementation or platform covered by
`>=3.11`.

The following commands reproduce the version and import checks with the same
package pins:

```console
$ "$SPIKE_ROOT/venv/bin/python" --version
$ uv pip freeze --python "$SPIKE_ROOT/venv/bin/python"
$ "$SPIKE_ROOT/venv/bin/python" - <<'PY'
import rfbzero
from importlib.metadata import metadata, version

print(version("rfbzero"))
print(rfbzero.__file__)
for key in ("Requires-Python", "Project-URL", "Classifier", "Requires-Dist"):
    print(key, metadata("rfbzero").get_all(key))
PY
```

Observed result:

```text
1.0.1
.../site-packages/rfbzero/__init__.py
Requires-Python ['>=3.10']
Project-URL ['Homepage, https://github.com/ericfell/rfbzero',
             'Documentation, https://rfbzero.readthedocs.io/en/latest/index.html#']
Classifier ['License :: OSI Approved :: MIT License', ...]
Requires-Dist ['scipy']
```

The top-level `import rfbzero` succeeded; it intentionally exports no public
names. The tested classes import from `rfbzero.redox_flow_cell` and
`rfbzero.experiment`.

## Version, artifact, and license evidence

Primary package and source metadata accessed on 2026-07-20:

- [PyPI project 1.0.1](https://pypi.org/project/rfbzero/1.0.1/) and its
  [PyPI JSON metadata](https://pypi.org/pypi/rfbzero/json) report current
  version `1.0.1`, `Requires-Python: >=3.10`, and the project homepage.
- The PyPI JSON free-form `license` field was `null`; this is not enough to
  identify the license on its own.
- The [1.0.1 wheel](https://files.pythonhosted.org/packages/3c/65/3720913496f8becadbf2d9bdb1b1b279cdc7bf743becaafd111608a6a9ee/rfbzero-1.0.1-py3-none-any.whl)
  has SHA-256
  `9f777cda041406654f19901a63bc4b5e42ce7a411ace14c3dece6d6335f65e42`.
  The corresponding
  [sdist](https://files.pythonhosted.org/packages/3d/8c/7badcee723c3532c3a714c25871b3e1b438044cb90e96e2f5c0141cb2f9d/rfbzero-1.0.1.tar.gz)
  has SHA-256
  `0d6330f7c4af6eb1f26b9056f710e9df3b098c84a58028641cfbfae1d8210ed1`.
- The installed wheel's `METADATA` has the `License :: OSI Approved :: MIT
  License` classifier and includes `License-File: LICENSE`. Its bundled
  `LICENSE` begins `MIT License`, copyright 2023 The rfbzero Authors.
- The upstream [tagged 1.0.1 source
  metadata](https://github.com/ericfell/rfbzero/blob/v1.0.1/pyproject.toml)
  repeats `version = "1.0.1"`, `requires-python = ">=3.10"`, the MIT
  classifier, and dependency `scipy`. The tag resolves to commit
  `691daa0066874e967e27a8f10783176c37c70c03`; its [tagged
  LICENSE](https://github.com/ericfell/rfbzero/blob/v1.0.1/LICENSE) is MIT.

**License conclusion:** MIT, based on the installed release artifact and
tagged upstream repository metadata. The `null` PyPI free-form field is a
metadata omission, not contrary license evidence.

## Callable protocol evidence

The installed 1.0.1 callable signatures were inspected with:

```console
$ "$SPIKE_ROOT/venv/bin/python" - <<'PY'
from inspect import signature
from rfbzero.experiment import ConstantCurrent
from rfbzero.redox_flow_cell import ZeroDModel

print(signature(ZeroDModel))
print(signature(ConstantCurrent))
print(signature(ConstantCurrent.run))
PY
```

Observed signatures:

```text
ZeroDModel(volume_cls, volume_ncls, c_ox_cls, c_red_cls, c_ox_ncls,
           c_red_ncls, ocv_50_soc, resistance, k_0_cls, k_0_ncls, ...,
           time_step=0.01, ..., temperature=298.0)
ConstantCurrent(voltage_limit_charge, voltage_limit_discharge, current=None,
                current_charge=None, current_discharge=None, charge_first=True)
ConstantCurrent.run(self, duration: int, cell_model: ZeroDModel,
                    degradation=None, cls_degradation=None,
                    ncls_degradation=None, crossover=None) -> CyclingResults
```

The tagged [`CyclingProtocol`](https://github.com/ericfell/rfbzero/blob/v1.0.1/src/rfbzero/experiment.py#L514-L644)
and [`ConstantCurrent`](https://github.com/ericfell/rfbzero/blob/v1.0.1/src/rfbzero/experiment.py#L647-L755)
source supplies this direct mapping:

| Project protocol field | RFBzero argument | Observed behavior / adapter requirement |
| --- | --- | --- |
| charge current | `current_charge` | Must be strictly positive amperes. |
| discharge current | `current_discharge` | Must be strictly negative amperes. |
| charge voltage limit | `voltage_limit_charge` | Voltage above which the model switches to discharge. |
| discharge voltage limit | `voltage_limit_discharge` | Voltage below which the model switches to charge. |
| duration | `run(duration=..., cell_model=...)` | Documented and annotated as integer seconds; adapter must require a positive, declared unit/value. |

The charge/discharge voltage limits are also checked against the cell's
`ocv_50_soc`: `voltage_limit_discharge < ocv_50_soc <
voltage_limit_charge`. Full cells require a nonnegative discharge voltage
limit. The adapter must keep all `ZeroDModel` inputs, including its numerical
`time_step`, in the immutable scenario/oracle configuration rather than infer
them from the five-field protocol.

The following minimal call ran successfully twice from freshly constructed
models. It intentionally uses synthetic values from the upstream packaged
example only to exercise the software API.

```python
from rfbzero.experiment import ConstantCurrent
from rfbzero.redox_flow_cell import ZeroDModel

cell = ZeroDModel(
    volume_cls=0.005, volume_ncls=0.010,
    c_ox_cls=0.01, c_red_cls=0.01,
    c_ox_ncls=0.01, c_red_ncls=0.01,
    ocv_50_soc=1.0, resistance=0.5,
    k_0_cls=1e-3, k_0_ncls=1e-3, time_step=0.1,
)
protocol = ConstantCurrent(
    voltage_limit_charge=1.5,
    voltage_limit_discharge=0.5,
    current_charge=0.10,
    current_discharge=-0.08,
)
results = protocol.run(cell_model=cell, duration=240)
```

Observed output/state from each run:

```text
Simulation stopped after 2400 time steps: time duration reached.
results.end_status: TIME_DURATION_REACHED
results.steps: 2400
results.half_cycles: 2
results.half_cycle_is_charge: [True, False]
results.half_cycle_capacity: [4.819999999999942, 9.639999999999825]
trace lengths for time/current/voltage/phase: 2400 each
```

Input failures were also exercised:

```text
current_discharge=0.08 -> ValueError: 'current_discharge' must be < 0.0
voltage_limit_charge=0.9 with ocv_50_soc=1.0
  -> ValueError: Ensure that 'voltage_limit_discharge' < 'ocv_50_soc' < 'voltage_limit_charge'
duration=0 -> IndexError: list assignment index out of range
```

The last case is a package edge-case failure, not acceptable project protocol
validation. The project validator must reject nonpositive duration before the
adapter calls RFBzero.

## Outcome and replay evidence

[`CyclingResults`](https://github.com/ericfell/rfbzero/blob/v1.0.1/src/rfbzero/experiment.py#L16-L219)
contains per-step `step_time`, `step_is_charge`, `current`, `cell_v`, and
`ocv`, plus `half_cycle_is_charge`, `half_cycle_capacity`, `end_status`, and
other state/trace fields. A source search for `energy`, `efficien`, and
`retention` found no result-level calculation or public API. Therefore the
adapter can map the package output to the planned outcome only by owning the
reduction contract:

- delivered discharge energy: integrate `-current * cell_v * time_step` over
  discharge trace entries;
- round-trip energy efficiency: define and serialize the pairing and treatment
  of partial half-cycles before calculating a ratio;
- capacity retention: select/compare `half_cycle_capacity` against a
  scenario-declared reference;
- elapsed virtual duration: use the trace and configured duration, including
  early termination handling; and
- execution/QC status: map `end_status` plus adapter-side exception handling
  to project-defined status/QC flags.

For the minimal synthetic run, the first reduction formula produced
`12.921998073831311 J` charge energy,
`9.038510059146773 J` discharge energy, and a trace energy ratio of
`0.6994669096454135`. These are test-harness calculations, not package output,
calibration data, or validation evidence.

Two independent fresh-model runs produced byte-identical canonical JSON of
`vars(results)` in this exact environment:

```text
fresh_run_json_equal: True
SHA-256: f2af6ce8933b40a0865503476c595f5d9f14a46f8ac76803d9fae03997b05f0c
```

The library mutates the supplied `ZeroDModel`; after the sample run its four
concentrations differed from a new model. It must therefore be reconstructed
from frozen initial configuration for a replay, never reused from a prior run.
The installed source contains no `random`, `rng`, `seed`, `pickle`, `json`,
`to_dict`, `serialize`, `save`, `load`, `__getstate__`, or `__setstate__`
matches. The three tested public classes (`ZeroDModel`, `ConstantCurrent`, and
`CyclingResults`) expose no named serialization/state methods.

`json.dumps(vars(results), sort_keys=True)` did succeed for the sample
(`636127` bytes), and a generic Python `pickle` round trip of the protocol,
mutated cell, and results succeeded (`328079` bytes). Neither is a supported,
versioned RFBzero persistence or replay contract. Pickle must not be used as a
durable public artifact. Project-owned JSON serialization must capture the
five-field protocol, initial model configuration, exact environment/artifact
identity, reducer version, and result trace/summary; an exact replay must
rebuild a new model and re-run under a pinned environment.

## Remaining unknowns and integration gates

- This spike demonstrates Python 3.12.12 only. Test Python 3.11 explicitly
  before claiming it as a supported runtime in CI.
- Byte-identical results were observed for one frozen input and one
  NumPy/SciPy/platform combination. RFBzero documents no deterministic replay
  guarantee, so replay must pin Python, RFBzero, NumPy, SciPy, numerical
  settings, scenario configuration, and the adapter reducer, then verify
  recorded hashes.
- The package has no direct outcome schema for the planned five observables and
  no QC/provenance semantics. Define those conversions and failure rules in the
  project adapter and scenario, with focused tests for partial cycles and every
  `CyclingStatus`.
- The package's own duration-zero failure confirms that project-owned protocol
  validation is mandatory. Validate all units, finite values, polarity,
  voltage ordering, candidate-set membership, and positive duration before
  importing/executing a model.
- Record the wheel or sdist hash above, source tag/commit, MIT license record,
  resolved dependency versions, and adapter version in every campaign manifest.
