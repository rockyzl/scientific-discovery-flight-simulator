# Demo guide

## Start the demo

First create a completed artifact directory with the CLI, then run:

```bash
python demo/serve.py --artifacts outputs/cv-demo
```

Open <http://127.0.0.1:8000>. Use `--host` and `--port` only on a trusted network; the server is a
small local review server, not a production deployment.

## What you are looking at

The banner **SIMULATED RUN — NOT A LAB MEASUREMENT** applies to every value on the page.

1. **Run identity** shows scenario commitment, completion status, versions, public planner seed, and
   manifest identity. Private world/noise/failure seeds remain concealed before reveal.
2. **Planner comparison** shows separate metrics for random, fixed-grid, and
   information-gain policies.
3. **Evidence replay** lets you choose a planner and inspect each recorded event in order.
4. **Downloads** link to the exact JSON artifacts currently displayed.
5. **Hidden truth** is read only from `summary.json.post_run_reveal` and stays concealed until a
   verified, complete artifact set has loaded. Revealing it shows the benchmark answer used by the
   evaluator and private replay seeds, with an explicit synthetic-data warning—not a laboratory
   truth.

## How to compare planners

Do not look only at whether a planner named the hidden mechanism. Also ask:

- How many measurements and attempts did it use?
- Did it propose invalid experiments?
- Did it detect and recover from the injected failure?
- Can its stopping decision be traced to successful observations?
- Would a simpler policy be good enough under the same budget?

## Accessibility

All controls use native buttons or links and are keyboard accessible. Status is written as text and
not encoded by color alone. Tables accompany compact visual summaries. The page respects reduced
motion preferences. A live status region announces artifact loading and errors.

## Troubleshooting

- **Artifacts failed to load:** confirm all five expected JSON files exist beneath the selected
  output directory.
- **Artifact rejected:** core verification detected a schema, hash, identity, commitment, or
  provenance mismatch. Regenerate the bundle; do not edit generated JSON by hand.
- **Hidden truth unavailable:** the artifact set is incomplete or is not marked completed.
- **404 or forbidden:** the demo server intentionally refuses paths outside the static demo and
  selected artifact directory.
