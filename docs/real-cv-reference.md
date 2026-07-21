# Real CV reference data

## Why it is included

The original UI compared experiment-selection policies without first showing the physical
measurement being abstracted. The demo now begins with a published cyclic-voltammetry reference so
a visitor can see a real current-density-versus-potential loop, named electrolyte formulations, and
the sample-handling workflow.

This reference layer and the synthetic benchmark remain separate. The real curves do not calibrate,
fit, train, validate, or supply observations to the synthetic response-mechanism world.

## Source and license

- Dataset: *Supplement Data of Anolytes for All-Iron Redox-Flow Batteries*
- Creators: Marius Engler, Michael Stich, Christoph Baumer, Andreas Bund
- DOI: <https://doi.org/10.5281/zenodo.15730784>
- License: CC BY 4.0
- Processed source member: `4_CV_additives.txt`
- Displayed quantities: working-electrode potential versus Ag/AgCl/KCl (sat'd), in V; total current
  density, in mA cm^-2

The viewer includes three pH 3.5 formulations from the source mapping:

1. 0.8 M FeCl2 + 3 M NH4Cl;
2. the same base formulation + 1 M glycine; and
3. the glycine formulation + 1 M lactic acid.

The corresponding raw measurement headers record a 10 mV/s scan to -1.2 V and back and two recorded
cycles. The dataset documentation states that the second cycle was used for analysis and that the
processed plot data were cleaned and smoothed by the authors. The UI therefore calls these
"published, author-processed experimental data," not raw data.

## Rebuild and integrity

Run:

```bash
uv run python scripts/build_real_cv_reference.py
```

The builder downloads the public raw and processed archives, verifies pinned archive and member
SHA-256 checksums, verifies the relevant raw protocol headers, and writes
`demo/data/all_iron_rfb_cv.json`. If any pinned source changes, the builder fails instead of silently
publishing different data.

## Sample-change semantics

Repeated scan-rate measurements for one formulation normally probe the same loaded sample. A sample
change is needed when the formulation changes. The UI therefore separates:

```text
within one formulation: equilibrate -> CV at selected condition -> analyze -> next condition
between formulations: stop -> remove sample -> rinse/prepare -> load and identify new sample
                      -> equilibrate -> resume measurements
```

This is an explanatory workflow only. The browser does not control pumps, electrodes, a
potentiostat, or any laboratory hardware.
