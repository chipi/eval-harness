#!/usr/bin/env python3
"""JSON-lines files hold text JSON keeps raw (U+2028, U+2029, U+0085), and are read whole.

    python tests/test_jsonl_lines.py

A JSON-lines file is written with `ensure_ascii=False`, so those characters stay raw inside a line, and `str.splitlines`
splits on them: a reader that used it dropped a run's output in `data-migrate` (both ways), made the exposure register
unreadable (every command scoring a held-out dataset failed), and split a record's history line in two when the next
save rewrote it (an independent review, 2026-11-17). `_common.jsonl_lines` splits on "\\n" only. Checked here: the helper
against splitlines on plain text; a held-out item's exposure whose `what` holds U+2028, a pick's note, and a record's
history line (read back, and rewritten by the next save), in a throwaway project of the store
the suite runs in. The run outputs' round trip through `data-migrate` is test_store.py's.
"""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
SEP = "a b c\x85d"
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _tmp
import _tmp  # noqa: E402

proj = Path(_tmp.mkdtemp(prefix="evh-jsonl-"))
store = os.environ.get("EVAL_STORE") or "files"
env = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_")}
env.update(EVAL_HOME=str(proj), EVH_ACTOR="person:test")


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


init = evh("init", "--store", store)
os.environ.update(EVAL_HOME=str(proj), EVH_ACTOR="person:test")
os.environ.pop("EVAL_STORE", None)
sys.path.insert(0, str(HERE.parent))
from evaluation_harness import _common, _exposure, _picks  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

check(
    "the throwaway project is made in the store the suite runs in", init.returncode == 0, init.stderr[-300:]
)

text = "{}\r\n" + '{"t": "' + SEP + '"}\n\n{}\n'
check(
    "jsonl_lines splits on newlines only: the line holding U+2028/U+2029/U+0085 stays one; \\r\\n and an empty line "
    "as splitlines gives them",
    _common.jsonl_lines(text) == ["{}", '{"t": "' + SEP + '"}', "", "{}"] and len(text.splitlines()) == 7,
    (_common.jsonl_lines(text), text.splitlines()),
)

_exposure.append("ds_test", [{"item_id": "i1", "what": SEP, "read_by": "agent:x", "at": "2026-11-17"}])
try:
    rows = _exposure.rows("ds_test")
except ValueError as exc:
    rows = [{"raised": str(exc)}]
check(
    "an exposure whose `what` holds U+2028 is read back whole (the register was unreadable, and with it every score "
    "of the held-out dataset)",
    len(rows) == 1 and rows[0].get("what") == SEP and rows[0].get("item_id") == "i1",
    rows,
)

_picks.append([{"dataset_id": "ds", "item_id": "i1", "note": SEP, "by": "person:test"}])
_picks.append([{"dataset_id": "ds", "item_id": "i2", "note": "plain", "by": "person:test"}])
picks = _picks.lines()
check(
    "a pick whose note holds U+2028 is read back whole, the next one after it",
    [p.get("note") for p in picks] == [SEP, "plain"],
    picks,
)

# A record's history is a JSON-lines file every save reads and rewrites. A goal's YAML file folds these characters to
# spaces when it is read, so the history is written here as a save writes it, through the model, with a raw one.
goal = ["--set", "title=T", "--set", "decision=D", "--set", "success_criteria.primary.measure=overlap_f1",
        "--set", "success_criteria.primary.direction=higher", "--set", "datasets=[]", "--set", "statement=S"]  # fmt: skip
made = evh("goal-new", "g1", *goal)
from evaluation_harness.model.goals import GOAL  # noqa: E402

GOAL._remember("g1", {"statement": SEP}, "person:test")
GOAL._remember("g1", {"statement": "after"}, "person:test")  # reads the history, then rewrites it whole
was = [(e.get("was") or {}).get("statement") for e in GOAL.history("g1")]
check(
    "a record's history whose line holds U+2028: read back whole, and the next save that rewrote it kept it one line",
    made.returncode == 0 and was == ["after", SEP, None],
    (made.stderr[-200:], was),
)

sys.exit(summary())
