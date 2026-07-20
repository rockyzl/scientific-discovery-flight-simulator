# Limitations and non-claims

## What this project does not establish

This project does not establish that:

- any policy can operate a real laboratory or instrument;
- synthetic measurements match a particular CV experiment;
- the candidate mechanisms are complete or mechanistically causal;
- expected information gain is generally superior to simpler designs;
- an LLM can reason scientifically;
- results transfer to unseen scientific domains;
- the simulator is synchronized with a physical system; or
- a molecule, material, formulation, or operating condition has been discovered or validated.

## Simulator bias

A planner can appear capable because its assumptions match the simulator. The candidate hypotheses,
noise distribution, failure model, action grid, and stopping rule were all authored. Performance may
disappear when any of those assumptions change. Stronger future studies would use held-out response
families, adversarial parameterizations, multiple seeds, and external experimental datasets where
their provenance and licenses permit.

## Simplified scientific response

The CV world deliberately uses small, interpretable response families. Real measurements can depend
on transport, kinetics, uncompensated resistance, capacitance, electrode history, temperature,
concentration, instrumentation, data processing, and other effects not represented here. The world
is a teaching emulator, not a validated electrochemical model.

## Failure model

Injected failures are deterministic benchmark events, not an empirical reliability model for any
instrument. Recovering from them demonstrates handling of the encoded cases only.

## Metrics

Calibration and information metrics are meaningful only relative to the emulator's probability
model. Artifact hashes detect changes but are not authorship signatures. Deterministic replay does
not prove scientific validity.

## Public demo

The demo reads frozen JSON artifacts. It is not a live experiment, a model-training session, or a
real-time agent. Hidden truth is benchmark truth and is revealed only for post-run interpretation.
Do not use these outputs for chemical, laboratory, operational, or safety decisions.
