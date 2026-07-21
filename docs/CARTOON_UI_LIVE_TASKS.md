# Cartoon CV UI — live design tasks

Status date: 2026-07-21
State: final QA approved

## Goal

Make the experiment understandable without reading long explanatory text. A visitor should be able
to see the sample, cell, electrodes, potentiostat, potential sweep, measured current, sample change,
and policy decision loop as one interactive cartoon process.

## Non-negotiable boundaries

- Published experimental CV curves remain labeled and attributed as real, author-processed data.
- Planner outputs remain labeled as a separate synthetic teaching benchmark.
- The cartoon must not imply that the browser controls real laboratory hardware.
- Repeated scan rates on one formulation do not falsely show a sample change.
- A sample change appears only when switching electrolyte formulation.
- Animation cannot be the only way to access information; keyboard, text, and reduced-motion paths
  remain available.

## Team

- Scientific workflow designer: physical and synthetic process accuracy.
- UX/visual narrative designer: interactive cartoon layout and progressive disclosure.
- QA/user representative: comprehension, accessibility, motion, and scientific-claim risks.
- UX/visual narrative designer also serves as documentation worker and consolidates the durable
  design proposal after independent intake.

## Tasks

- [x] Independent scientific workflow proposal.
- [x] Independent UX/cartoon interaction proposal.
- [x] Independent usability and risk review.
- [x] Reconcile proposals into one implementation-ready design contract.
- [x] Obtain QA verdict on the reconciled design — Quick-tier QA approved the frozen contract.
- [x] Implement the cartoon UI after the design contract was frozen.

## Final QA acceptance test

The frozen, executable test protocol is in `docs/design/cartoon-ui-contract.md`, Section 13.

After five seconds, a first-time visitor should identify:

1. CV / an electrochemical potential-sweep experiment;
2. the changed potential/condition and measured current; and
3. the coexistence of a published real-data reference and a separate saved simulation, while
   rejecting the idea that the browser controls live hardware.

After 30 seconds, the visitor should additionally identify when the sample is replaced, which data
are published, why the synthetic layer is independent, how the three planners choose differently,
and why one saved replay proves neither a universally best planner nor a real-sample mechanism.
