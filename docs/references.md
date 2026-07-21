# References and attribution

## Project status

This is an independent research prototype. No affiliation with or endorsement by Argonne National
Laboratory, the U.S. Department of Energy, or any referenced project is implied.

## Current implementation

The synthetic v0 benchmark implementation is self-contained. It does not import, wrap, or control MADSci, Bluesky,
ophyd, PyLabRobot, PRISM, Olympus, Summit, ChemGymRL, or a laboratory instrument. It uses no LLM.

## Published experimental CV reference

The browser includes a separately labeled reference viewer derived from:

> Engler, M.; Stich, M.; Baumer, C.; Bund, A. *Supplement Data of Anolytes for All-Iron
> Redox-Flow Batteries*. Zenodo, 2025. DOI: `10.5281/zenodo.15730784`.

The record is distributed under CC BY 4.0. The bundled JSON contains three author-processed curves
from `4_CV_additives.txt`: FeCl2/NH4Cl, the glycine formulation, and the glycine/lactic-acid
formulation at pH 3.5. The corresponding raw headers record a 10 mV/s scan to -1.2 V and back; the
dataset documentation states that the second cycle was used for analysis and describes its
processing and smoothing. Exact source/archive SHA-256 values are pinned in both the builder and
bundled JSON.

The real curves are **not inputs to the synthetic planner benchmark**. Their purpose is to show what
a physical CV measurement and formulation change look like before the page introduces the abstract
mechanism-selection exercise. See [real CV reference data](real-cv-reference.md).

## Candidate context requiring verification

The research memo identified the following as possible context for later literature comparison:
PRISM, MADSci, Bluesky/ophyd, PyLabRobot, Olympus, Summit, ChemGymRL, and autonomous microscopy
work. These names are retained as a research checklist only. Before a public article claims a
technical relationship, a reviewer must independently verify:

- the primary source and exact version;
- what the source actually implements or demonstrates;
- current maintenance status;
- code and data licenses;
- whether reuse requires attribution or redistribution conditions; and
- whether any institutional name could imply an endorsement.

Until that review is complete, those projects are not described as foundations, integrations, or
validation for this repository.

## Scientific wording

The qualitative CV response families in the flagship world are encoded as transparent synthetic
hypotheses for a teaching benchmark. They must not be cited as a complete account of real cyclic
voltammetry. Any future scientific reference section should distinguish textbook motivation from
claims about the implemented emulator.
