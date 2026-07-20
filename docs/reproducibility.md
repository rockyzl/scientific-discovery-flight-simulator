# Reproducibility

## Reproducibility target

For a supported Python/NumPy environment, the same frozen scenario, implementation versions, and
explicit private replay key should produce the same logical campaign and artifact identity. This is
a software benchmark property, not proof that the scientific emulator is correct.

## Recorded identity

Manifest schema version `1` records or binds:

- schema, provenance, and run status;
- package name and version;
- world ID and version;
- planner names and versions;
- runtime/environment provenance (`python`, `numpy`, and `platform`);
- scenario identity;
- public planner seed and HMAC commitments to private world, noise, and failure seeds; and
- artifact paths and hashes, plus the manifest payload hash.

The manifest does not record separate instrument, runner, or evaluator versions, and it does not
claim a source-revision identity.

All artifacts declare `provenance: simulated`. A completed `post_run_reveal` contains the replay key
and private seeds; verification checks that they open the recorded commitments before serving.

## Reproduce a run

The default CLI invocation securely generates a new private replay key. That new key changes the
private-seed commitments and bundle hashes, so two default invocations are **not** byte-identical.

First generate the original run in a new directory:

```bash
python -m discovery_flight_simulator.cli compare \
  --scenario scenarios/cv_mechanism_v0.json \
  --output outputs/original
```

After completion, read `post_run_reveal.replay_key` from `outputs/original/summary.json`. Reuse that
exact revealed key with the same scenario, code, and environment, again writing to a new directory:

```bash
python -m discovery_flight_simulator.cli compare \
  --scenario scenarios/cv_mechanism_v0.json \
  --output outputs/exact-replay \
  --private-seed-key '<revealed-key>'
```

Only the second command is an exact-replay request. Compare the manifests and their declared
artifact hashes while holding the package version, Python/NumPy environment, scenario, and replay
key fixed. The core
`verify_artifact_bundle(Path)` function is the fail-closed verifier used by the demo server: it
checks the manifest payload hash, serialized file hashes, summary payload hash, each ledger payload
and event chain, cross-file world/planner/seed/scenario identities, and the scenario commitment.

## Random-stream separation

World parameters, measurement noise, failure injection, and planner exploration use separate RNG
streams. Condition-indexed noise and attempt-indexed failures prevent a policy's internal branching
from changing the benchmark another policy experiences. The web page displays only the public
planner seed and commitment before reveal. Private replay seeds may be shown only after explicit
post-run reveal, with a warning that they reproduce a synthetic benchmark.

## Artifact handling

- Keep original artifacts immutable.
- Generate a new directory for every rerun.
- Treat hash mismatch as a changed artifact, not as a harmless display difference.
- Refuse to serve a bundle when core verification fails.
- Verify `provenance: simulated` before rendering or analysis.
- Do not compare artifacts from different schema versions without an explicit migration.

## Demo replay

`demo/serve.py --artifacts <OUTPUT_DIR>` verifies, then serves existing artifacts. Replaying them in
the browser does not execute the campaign. Download links expose the same JSON used to build the
visible cards, table, and event timeline.
