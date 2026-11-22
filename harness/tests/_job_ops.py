"""Synthetic decisions and work operations for the tests of the job machinery (RFC-032 step 9 P3): each declares a feature
the two pilots do not (a spend, a system, a file, a resume, a lock function, an exclusive group), so the checks that guard
them are shown on something that has it. Not registered: a test adds them to `ops.registry.OPS` for the block that uses
them. The bodies print their inputs and answer 0."""

from __future__ import annotations

import json
import time

from evaluation_harness.ops.registry import Op

_S = "_job_ops"


def body(**inputs) -> int:
    """A job's body: prints its inputs, answers 0."""
    print(json.dumps(inputs, sort_keys=True))
    return 0


def extra_locks(inputs) -> list[tuple[str, bool]]:
    """A lock the inputs name by a rule a template cannot say."""
    return [(f"extra:{inputs.get('system')}", True)]


SPEND = Op(
    "t-spend", "work", "synthetic: a work operation that spends, names a system, takes files and can be resumed",
    "POST", "/t/{system}/spend", f"{_S}:body", "",
    locks=(("system:{system}", True), ("dataset:{dataset}", False)), locks_fn=f"{_S}:extra_locks", spends=True,
    required=("system",), resume=("resume", "run_id"), exclusive=(("name", "kind"),),
    inputs={
        "system": {"type": "string", "x-ref": "system", "description": "the system"},
        "dataset": {"type": "string", "description": "the dataset"},
        "repeat": {"type": "integer", "default": 1, "description": "how many times"},
        "resume": {"type": "string", "description": "the run to continue"},
        "run_id": {"type": "string", "description": "the run it writes"},
        "recall_failed": {"type": "boolean", "description": "call again what the run called once and did not finish"},
        "kind": {"type": "string", "enum": ["a", "b"], "description": "which kind"},
        "name": {"type": "string", "pattern": "^[a-z]+$", "description": "a name"},
        "sheet": {"type": "string", "x-file": "upload", "description": "a sheet the call carries"},
        "out": {"type": "string", "x-file": "artifact", "description": "a file the job writes"},
    },
)  # fmt: skip

PLAIN = Op(
    "t-plain", "work", "synthetic: a work operation that writes nothing another job writes",
    "POST", "/t/plain", f"{_S}:body", "", locks=(), inputs={"note": {"type": "string"}},
)  # fmt: skip

DECIDE = Op(
    "t-decide", "decision", "synthetic: a decision with its reason as an input and a composite part",
    "POST", "/t/{goal}/{study}/decide", f"{_S}:body", "",
    locks=(("study:{study}", True),), why="reason", required=("study", "reason"),
    parts={"goal": "study", "study": "study"}, parts_fn=f"{_S}:study_of",
    inputs={"study": {"type": "string", "description": "goal/study"}, "reason": {"type": "string"}},
)  # fmt: skip


def study_of(goal: str, study: str) -> dict[str, str]:
    """A composite part: the two parts of the route are one input."""
    return {"study": f"{goal}/{study}"}


MIGRATE = Op(
    "t-migrate", "work", "synthetic: a migration holds the whole project", "POST", "/t/migrate", f"{_S}:body", "",
    locks="project", inputs={},
)  # fmt: skip


def slow_body(**inputs) -> int:
    """Prints a line, takes a while, prints another: a log that is live shows the first while the job still runs."""
    print("first", flush=True)
    time.sleep(1.5)
    print("second")
    return 0


LIVE = Op(
    "t-live", "work", "synthetic: prints, waits, prints", "POST", "/t/live", f"{_S}:slow_body", "", locks=(), inputs={},
)  # fmt: skip

ALL = (SPEND, PLAIN, DECIDE, MIGRATE, LIVE)
