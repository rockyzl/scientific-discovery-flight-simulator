# LangGraph Compatibility Spike

Date: 2026-07-20

## Scope

This was an isolated compatibility spike only. It exercised a deterministic,
human-approved `recommend -> pause -> decision -> execute -> record` graph. It
uses no LLM, tool invocation, hardware control, project source, project tests,
or project dependency files.

## Recommendation

**GO, with production persistence and idempotency conditions.**

`langgraph==1.2.9` is compatible with the project's Python 3.11 floor and
supports the required approval pause and continuation semantics. The successful
proof persisted the pause in SQLite, reconstructed the graph in a fresh Python
process, resumed it, and showed a single execution in state. A repeat resume
returned the completed state without incrementing the execution counter.

Use LangGraph only when all of the following are part of the implementation:

- Pin `langgraph==1.2.9` initially, then upgrade deliberately with this proof
  rerun.
- Use a database-backed checkpointer and a stable, unique `thread_id` per
  approval workflow. `InMemorySaver` is suitable for a unit-level proof only.
- Keep every operation before `interrupt()` pure or idempotent. Put execution
  after the interrupt in its own node.
- Make the real execution/record boundary transactional or idempotent with a
  durable workflow and decision ID. This spike proves the normal sequential
  path, not distributed or crash-safe exactly-once delivery of an external side
  effect.

## Version, License, and Source

| Item | Observed value |
| --- | --- |
| Project Python requirement | `>=3.11` |
| Shell `python3` | `Python 3.12.12` |
| Isolated Python 3.12 run | `Python 3.12.3` |
| Isolated compatibility-floor run | `Python 3.11.15` |
| Latest PyPI version observed | `langgraph 1.2.9` |
| Tested LangGraph | `1.2.9` |
| Tested base checkpointer | `langgraph-checkpoint 4.1.1` |
| Tested durable local checkpointer | `langgraph-checkpoint-sqlite 3.1.0` |
| Package `Requires-Python` | `>=3.10` |
| Package license metadata | `MIT` |
| Package source metadata | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph/tree/main/libs/langgraph) |
| License text | [MIT LICENSE](https://github.com/langchain-ai/langgraph/blob/main/LICENSE) |

`1.2.9` was the highest version from `python3 -m pip index versions langgraph`
on the spike date and is a non-prerelease 1.x release. The installed package
metadata independently reported `License-Expression: MIT`,
`Requires-Python: >=3.10`, and the source URL above.

## Exact Reproduction

All commands ran outside this repository. `uv` obtained CPython 3.11.15 for the
minimum supported project version; the resulting virtual environment contains
only spike dependencies.

```bash
python3 --version
# Python 3.12.12

python3 -m pip index versions langgraph
# langgraph (1.2.9)

SPIKE_DIR="$(mktemp -d /tmp/langgraph-compatibility-XXXXXX)"
uv venv --python 3.11 "$SPIKE_DIR/.venv-py311"
# Using CPython 3.11.15

uv pip install --python "$SPIKE_DIR/.venv-py311/bin/python" \
  langgraph==1.2.9 \
  langgraph-checkpoint-sqlite==3.1.0
# langgraph==1.2.9
# langgraph-checkpoint==4.1.1
# langgraph-checkpoint-sqlite==3.1.0
```

The following command is the complete successful durable proof. `run_phase`
starts a new Python process each time, while all phases use the same SQLite
file and `thread_id`.

```bash
run_phase() {
  "$SPIKE_DIR/.venv-py311/bin/python" - "$1" "$2" <<'PY'
import sqlite3
import sys
from typing import Literal

from typing_extensions import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

mode, db_path = sys.argv[1:]


class State(TypedDict, total=False):
    proposal: str
    recommendation: str
    approved: bool
    executions: int
    record: str


def recommend(state: State) -> dict:
    return {"recommendation": f"approve: {state['proposal']}"}


def decision(state: State) -> dict:
    answer = interrupt({"recommendation": state["recommendation"]})
    return {"approved": answer["approved"]}


def route(state: State) -> Literal["execute", "record"]:
    return "execute" if state["approved"] else "record"


def execute(state: State) -> dict:
    return {"executions": state.get("executions", 0) + 1}


def record(state: State) -> dict:
    return {"record": "executed" if state.get("approved") else "declined"}


connection = sqlite3.connect(db_path, check_same_thread=False)
checkpointer = SqliteSaver(connection)
checkpointer.setup()
builder = StateGraph(State)
builder.add_node("recommend", recommend)
builder.add_node("decision", decision)
builder.add_node("execute", execute)
builder.add_node("record", record)
builder.add_edge(START, "recommend")
builder.add_edge("recommend", "decision")
builder.add_conditional_edges("decision", route)
builder.add_edge("execute", "record")
builder.add_edge("record", END)
graph = builder.compile(checkpointer=checkpointer)
config = {"configurable": {"thread_id": "durable-spike-1"}}

if mode == "pause":
    output = graph.invoke({"proposal": "run deterministic simulator"}, config)
    snapshot = graph.get_state(config)
    assert len(output["__interrupt__"]) == 1
    assert snapshot.next == ("decision",)
    assert "executions" not in snapshot.values
    print("pause", snapshot.values, snapshot.next)
elif mode == "resume":
    output = graph.invoke(Command(resume={"approved": True}), config)
    snapshot = graph.get_state(config)
    assert output["executions"] == 1
    assert output["record"] == "executed"
    assert snapshot.next == ()
    print("resume", output, snapshot.next)
else:
    raise SystemExit(f"unknown phase: {mode}")

connection.close()
PY
}

DB_PATH="$(mktemp /tmp/langgraph-durable-repro-XXXXXX.sqlite)"
run_phase pause "$DB_PATH"
run_phase resume "$DB_PATH"
run_phase resume "$DB_PATH"
```

Observed output:

```text
pause {'proposal': 'run deterministic simulator', 'recommendation':
'approve: run deterministic simulator'} ('decision',)
resume {'proposal': 'run deterministic simulator', 'recommendation':
'approve: run deterministic simulator', 'approved': True, 'executions': 1,
'record': 'executed'} ()
resume {'proposal': 'run deterministic simulator', 'recommendation':
'approve: run deterministic simulator', 'approved': True, 'executions': 1,
'record': 'executed'} ()
```

The initial invocation paused after recommendation and before the `execute`
node, exposing exactly one interrupt. Its snapshot had no `executions` value.
The next process supplied the human approval through `Command(resume=...)` and
ended with `executions == 1` and the final record. The third process repeated
the resume command against the completed thread and retained `executions == 1`.

The same graph also passed with `InMemorySaver` on Python 3.12.3 and Python
3.11.15. The SQLite run is the durability proof because the pause and resume
crossed process boundaries.

## Durability Limits

- `InMemorySaver` loses all checkpoints on process exit. It does not meet the
  persistence requirement for a human approval that may wait across restarts.
- The SQLite checkpointer persisted the demonstrated pause and final state, but
  the LangGraph documentation positions SQLite for experimentation and local
  workflows. Use a database-backed production checkpointer such as Postgres for
  a multi-process service.
- `interrupt()` restarts the node that contains it when resumed. Any code before
  that call can run again. The proof deliberately performs no side effect before
  the interrupt; `execute` is a separate, post-approval node.
- A retained graph state counter is not a general exactly-once guarantee for an
  external system. Crashes, retries, and concurrent approval submissions still
  require an application-owned idempotency key and transactional record of the
  approval and execution result.
- Interrupt and resume payloads should remain JSON-serializable so that the
  chosen durable saver can serialize them reliably.

Relevant upstream references: [interrupt and resume semantics](https://docs.langchain.com/oss/python/langgraph/interrupts), [persistence and checkpointers](https://docs.langchain.com/oss/python/langgraph/persistence), and [database-backed production persistence](https://docs.langchain.com/oss/python/langgraph/add-memory).
