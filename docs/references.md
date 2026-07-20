# References and attribution

## Project status

This is an independent research prototype. No affiliation with or endorsement by Argonne National
Laboratory, the U.S. Department of Energy, or any referenced project is implied.

## Current implementation

The v0 implementation is self-contained. It does not import, wrap, or control MADSci, Bluesky,
ophyd, PyLabRobot, PRISM, Olympus, Summit, ChemGymRL, or a laboratory instrument. It uses no LLM.

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
