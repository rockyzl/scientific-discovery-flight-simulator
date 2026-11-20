# Virtual RFB Cell workbench guide

## Scope

The Virtual RFB Cell Campaign workbench is a local interface for a simulated
0D virtual redox-flow-battery (RFB) cell campaign. It is not a digital twin,
real measurement system, self-driving laboratory, hardware controller,
material-discovery claim, or network service. The virtual oracle produces only
the frozen scenario's simulated outcomes.

The command below starts the completed local workbench server and browser UI.

```bash
python demo/rfb_workbench.py --scenario scenarios/rfbzero_cell_v0.json --data-dir <state-dir> [--host 127.0.0.1] [--port 8001]
```

Use a dedicated local `<state-dir>`. The directory contains the SQLite
campaign and checkpoint data plus a private local scenario commitment key. It
is not a shareable artifact and must not be published, copied to public storage,
or otherwise shared.

The default bind address and port are `127.0.0.1` and `8001`. The API is local
to the workbench and is not intended to be exposed or operated as a remote
service.

Verification: `uv run --extra dev pytest -q` passed with 188 tests; `ruff`
passed; and the Node UI test suite passed with 3 tests.

## Campaign workflow

The intended browser path is:

1. Create or load a campaign.
2. Review the pending recommendation.
3. Record an approval or rejection.
4. Explicitly resume an unchanged approved decision.
5. Inspect the public campaign journal.

An approval is a record of the human decision only. It does not execute an
action, reserve costs, call the virtual oracle, or create an outcome. A
separate explicit resume is the only operation that can advance an approved
simulated action.

Resume is bound to the decision being resumed. Repeating the same matching
resume is idempotent: it returns the already advanced result rather than
creating another execution or charging another cost.

V1 presents approve and reject controls. A rejection is human intervention;
the campaign becomes a `workflow_case_study` and is unrankable under the strict
benchmark rules. The underlying workflow also treats an edit as human
intervention with the same consequence. Human-intervened cases may be inspected
as workflow case studies but must not be used for strict ranking.

## Stop and reset

Stop the local server with `Ctrl-C`. To reset the workbench, stop it and start
again with a new, empty `<state-dir>`. Do not manually edit, delete records
from, or otherwise mutate the SQLite database; doing so can break campaign and
event-chain integrity.

The public journal is for inspecting public campaign state and canonical events.
It does not make the private local scenario commitment key or private execution
material public.
