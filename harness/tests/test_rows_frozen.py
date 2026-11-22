#!/usr/bin/env python3
"""The safeguard for the rows the cache shares (RFC-033 step d): `EVH_FREEZE_ROWS=1`.

    python tests/test_rows_frozen.py

The rows `_outputs.rows` returns are the kept-rows cache's own, shared by every caller: one that changes a row changes
what the next caller reads, in a process that lives on (catalog-serve, the MCP server). With `EVH_FREEZE_ROWS=1` every
row the cache holds, and what it holds (a `_meta`, a list), is frozen: a change to it raises a TypeError at the line that
makes it, and a copy (`copy.copy`, `copy.deepcopy`, `dict(row)`, `{**row}`, pickle) is a plain dict a caller may change.
The suite runs under it (`tests/self_test.py` and `tools/store_matrix.py` set it), so a view or a command that changes a
cached row fails its test. Here: both stores; every kind of change raises and none changes the row; what is read from a
frozen row is the same (equal to the plain row, the same JSON, the same canonical text); a copy is changeable; without the
variable the cache's rows are plain dicts; `item_across` and `rows_text` do not freeze what they give.
"""

import copy
import json
import os
import pickle
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-frozen-"))
os.environ["EVAL_HOME"] = str(proj)
os.environ.pop("EVAL_STORE", None)
for k in ("EVAL_DATA_DIR",):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
from evaluation_harness import _format, _outputs, _runs, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

ROWS = [
    {"item_id": "i1", "acc": 1.0, "n": 2, "ok": True, "_meta": {"provider": "p", "usage": {"cost": 0.5}, "ranking": [1, 2]}, "_extra": {"k": [1]}},
    {"item_id": "i2", "acc": 0.0, "list": [1, {"a": 2}], "_meta": {"provider": "p"}},
]  # fmt: skip


def raises(fn: Any) -> bool:
    try:
        fn()
    except TypeError as exc:
        return "EVH_FREEZE_ROWS" in str(exc)
    return False


def body(store: str) -> None:
    os.environ["EVAL_STORE"] = store
    _outputs.reset()
    if _store.exists(proj / "data"):
        _store.rmtree(proj / "data")
    _store.mkdir(proj / "data" / "systems", parents=True)
    _format.stamp(data=proj / "data")
    d = _runstore.make_run(
        proj / "data" / "runs",
        "arm_a_v1_x",
        {"system_id": "arm_a_v1", "dataset_id": "ds"},
        scores=[{"scorer": "abcdefabcdef", "reference": "gold.ds", "first": True, "rows": ROWS}],
    )
    sd = model_runs.first_score(d)
    assert sd is not None
    plain = [json.loads(json.dumps(r)) for r in ROWS]

    os.environ.pop("EVH_FREEZE_ROWS", None)
    _outputs.reset()
    r = (_outputs.rows(sd) or [])[0]
    check(
        f"{store}: without the variable the cache's rows are plain dicts",
        type(r) is dict and type(r["_meta"]) is dict,
    )
    r["extra_key"] = (
        1  # a plain row is changeable (and this changes the cache's: the very thing the variable catches)
    )
    _outputs.reset()

    os.environ["EVH_FREEZE_ROWS"] = "1"
    got = _outputs.rows(sd) or []
    row, other = got[0], got[1]
    check(
        f"{store}: a frozen row is the row: equal to the plain one, the same JSON and the same canonical text, keys as before",
        got == plain
        and [json.dumps(x, sort_keys=True) for x in got] == [json.dumps(x, sort_keys=True) for x in plain]
        and _outputs.rows_text(sd) == "".join(_outputs.row_line(x) for x in plain)
        and isinstance(row, dict)
        and list(row) == sorted(row),
    )
    changes = {
        "an assignment": lambda: row.__setitem__("acc", 2.0),
        "a new key": lambda: row.__setitem__("new", 1),
        "a deletion": lambda: row.__delitem__("acc"),
        "update": lambda: row.update(acc=3),
        "pop": lambda: row.pop("acc"),
        "popitem": row.popitem,
        "setdefault": lambda: row.setdefault("new", 1),
        "clear": row.clear,
        "|=": lambda: row.__ior__({"a": 1}),
        "a change inside `_meta`": lambda: row["_meta"].__setitem__("provider", "q"),
        "a change inside `_meta.usage`": lambda: row["_meta"]["usage"].update(cost=9),
        "a list's append": lambda: row["_meta"]["ranking"].append(3),
        "a list's item assigned": lambda: row["_meta"]["ranking"].__setitem__(0, 9),
        "a list's sort": row["_meta"]["ranking"].sort,
        "a list's extend": lambda: row["_meta"]["ranking"].extend([1]),
        "a list's `+=`": lambda: row["_meta"]["ranking"].__iadd__([1]),
        "a change inside a list of the row": lambda: other["list"][1].__setitem__("a", 5),
        "`_extra`": lambda: row["_extra"].__setitem__("k", 1),
        "a shallow copy's nested dict (dict.copy shares what it holds)": lambda: row.copy()["_meta"].__setitem__("x", 1),
        "a shallow `dict(row)`'s nested dict": lambda: dict(row)["_meta"].__setitem__("x", 1),
    }  # fmt: skip
    for what, fn in changes.items():
        check(f"{store}: {what} on a cached row raises, naming the variable", raises(fn), what)
    check(
        f"{store}: none of them changed the row",
        _outputs.rows(sd) == plain and row == plain[0] and other == plain[1],
        row,
    )
    mine = copy.deepcopy(row)
    mine["acc"] = 5.0
    mine["_meta"]["usage"]["cost"] = 7
    mine["_meta"]["ranking"].append(3)
    shallow = dict(row)
    shallow["acc"] = 6.0
    spread = {**row, "acc": 7.0}
    assert type(spread) is dict
    cp = copy.copy(row)
    cp["acc"] = 8.0
    back = pickle.loads(pickle.dumps(row))  # noqa: S301  # nosec B301 - this test's own object
    back["acc"] = 9.0
    check(
        f"{store}: a deep copy, `dict(row)`, `{{**row}}`, copy.copy and a pickle round trip are plain dicts a caller may change, and the cache's row is untouched",
        type(mine) is dict
        and type(mine["_meta"]) is dict
        and type(mine["_meta"]["ranking"]) is list
        and type(back) is dict
        and _outputs.rows(sd) == plain
        and row["_meta"]["usage"] == {"cost": 0.5},
    )
    check(
        f"{store}: item_rows yields the cache's rows (frozen), and the list `rows` gives is the caller's (sortable, appendable)",
        raises(lambda: next(iter(_runs.item_rows(sd))).__setitem__("x", 1)) and _sortable(sd),
    )
    across = _outputs.item_across([sd], "i1").get(sd)
    if across is not None:
        across["acc"] = 4.0
    check(
        f"{store}: item_across's row is the caller's own (changeable), and changing it changes nothing the cache holds",
        across is not None and (_outputs.rows(sd) or [])[0]["acc"] == 1.0,
    )
    check(
        f"{store}: rows_text is a string; a freshly written set is frozen on its next read",
        isinstance(_outputs.rows_text(sd), str) and _written_is_frozen(sd),
    )


def _sortable(sd: Path) -> bool:
    lst = _outputs.rows(sd) or []
    lst.sort(key=lambda r: r["item_id"], reverse=True)
    lst.append({"item_id": "x"})
    return len(_outputs.rows(sd) or []) == 2


def _written_is_frozen(sd: Path) -> bool:
    _outputs.store().put_rows(sd, [{"item_id": "n", "_meta": {"a": [1]}}])
    fresh = (_outputs.rows(sd) or [])[0]
    return raises(lambda: fresh["_meta"]["a"].append(2)) and raises(lambda: fresh.__setitem__("z", 1))


try:
    for s in ("files", "sqlite"):
        body(s)
finally:
    _outputs.reset()
    shutil.rmtree(proj, ignore_errors=True)
raise SystemExit(summary())
