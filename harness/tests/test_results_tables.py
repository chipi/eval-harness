#!/usr/bin/env python3
"""A score's per-item results as tables in the SQLite store (RFC-033 step d).

    python tests/test_results_tables.py

The project's store is sqlite for the whole file. The schema is the RFC's, table by table and column by column. Every
type a row can hold round-trips: an int stays an int and a float a float (1 and 1.0, -0.0, int64's bounds), a bool, None,
NaN, the infinities and an integer past int64 come back as they were (kept as JSON in `rest`), the row comes back with its
keys sorted, and no field is lost or added. `_meta`: absent stays absent, `{}` stays `{}`, call facts equal to the ones
the run holds for the item leave the row (`facts` = 1) and are put back on read, facts that differ keep the row's whole
`_meta`, a `_meta` left empty keeps `{}`, a row's own key wins over the held one, a score set that is not under
runs/<run>/scores/<key> has no call facts; `_extra` absent is NULL, `{}` is kept. A score set's id is its key's hash, the
next free one upward on a collision (wrapping), a row's is `score_set * 2^20 + n`; more rows than that are refused.
A write is one transaction (a row that cannot be written leaves the score set as it was). Deleting a score set (and a
folder under which there are some) takes its rows and values, and a run's call facts go with its last score set.
`item_across` uses the item index. V9 reads the database: every score set with a record has rows, as many as the record
says, and each committed arm meets its floor; each failure is planted. A project of every case moved to files and back
by `data-migrate` comes back byte for byte, and every score set's canonical text is the same on the way.
"""

import contextlib
import hashlib
import io
import json
import math
import os
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-tables-"))
os.environ["EVAL_HOME"] = str(proj)
os.environ["EVAL_STORE"] = "sqlite"
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR"):
    os.environ.pop(k, None)
import _runstore  # noqa: E402
from evaluation_harness import _format, _outputs, _runs, _store  # noqa: E402
from evaluation_harness import validate_tree as vt  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

DATA = proj / "data"
RUNS = DATA / "runs"
# this file is a script: a name below is used for what it is where it is, so it is not typed by its first use
d: Any
sd: Any
got: Any
before: Any
after: Any
r1: Any
r2: Any
s1: Any
s2: Any
ra: Any
rb: Any
a: Any
b: Any
across: Any
key: Any


def line(row: Any) -> str:
    return json.dumps(row, sort_keys=True)


def db() -> sqlite3.Connection:
    conn = _store.connect()
    assert conn is not None
    return conn


TABLES = ("score_sets", "metrics", "call_facts", "score_rows", "score_values", "rows_partial")


def table_rows(conn: sqlite3.Connection, t: str, what: str = "*", order: str = "1, 2") -> list[Any]:
    """`what` of every row of table `t` (one of TABLES, or outputs), in `order`: the tables' names are fixed here."""
    assert t in (*TABLES, "outputs")
    return conn.execute(f"SELECT {what} FROM {t} ORDER BY {order}").fetchall()  # noqa: S608  # nosec B608 - one of this file's tables


def fresh() -> None:
    """What the process kept of the database forgotten, so the next read is the database's."""
    _outputs.reset()


def new_project() -> None:
    _outputs.reset()  # the database closed, then the project's data removed whole: a fresh database on the next write
    shutil.rmtree(DATA, ignore_errors=True)
    DATA.mkdir(parents=True)
    _store.mkdir(DATA / "systems", parents=True)
    _format.stamp(data=DATA)


def run_with(run_id: str, rows_by_score: dict[str, list[dict]], **rec: Any) -> Path:
    scores = [
        {
            "scorer": f"{i:012x}",
            "reference": "gold.ds",
            "first": i == 0,
            "rows": rows,
            "metrics": {"n_items": len(rows)},
        }
        for i, rows in enumerate(rows_by_score.values())
    ]
    return _runstore.make_run(
        RUNS,
        run_id,
        {"system_id": run_id.rsplit("_v1", 1)[0] + "_v1", "dataset_id": "ds", **rec},
        scores=scores,
    )


def score_dirs(d: Path) -> list[Path]:
    return model_runs.scores_of(d)


def v9() -> tuple[list[str], str]:
    vt.problems.clear()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        vt.v9_no_committed_evidence_is_missing()
    return [p for p in vt.problems if "V9" in p], out.getvalue()


def dm(store: str, *args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR")}
    env.update(EVAL_HOME=str(cwd), EVAL_STORE=store)
    return subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), *args], cwd=cwd, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


try:
    new_project()
    # ── the schema, as the RFC gives it ─────────────────────────────────────────────────────────────────────────────
    d0 = run_with("arm_a_v1", {"s": [{"item_id": "i"}]})
    info = {t: [tuple(r[1:6]) for r in db().execute(f"PRAGMA table_info({t})")] for t in TABLES}
    want = {
        "score_sets": [("id", "INTEGER", 0, None, 1), ("key", "TEXT", 1, None, 0)],
        "metrics": [("id", "INTEGER", 0, None, 1), ("name", "TEXT", 1, None, 0)],
        "call_facts": [("run", "TEXT", 1, None, 1), ("item_id", "TEXT", 1, None, 2), ("meta", "TEXT", 1, None, 0)],
        "score_rows": [
            ("id", "INTEGER", 0, None, 1), ("score_set", "INTEGER", 1, None, 0), ("n", "INTEGER", 1, None, 0),
            ("item_id", "TEXT", 1, None, 0), ("facts", "INTEGER", 1, None, 0), ("meta", "TEXT", 0, None, 0),
            ("extra", "TEXT", 0, None, 0), ("rest", "TEXT", 0, None, 0),
        ],
        "score_values": [("row", "INTEGER", 1, None, 1), ("metric", "INTEGER", 1, None, 2), ("value", "", 1, None, 0)],
        "rows_partial": [("run", "TEXT", 1, None, 1), ("n", "INTEGER", 1, None, 2), ("line", "TEXT", 1, None, 0)],
    }  # fmt: skip
    check(
        "the tables have the RFC's columns, types, NOT NULLs and keys",
        info == want,
        {t: (info[t], want[t]) for t in want if info[t] != want[t]},
    )
    sql = dict(db().execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL"))
    check(
        "call_facts and score_values are WITHOUT ROWID, score_rows has UNIQUE (score_set, n), the item index is score_rows_item",
        "WITHOUT ROWID" in sql["call_facts"]
        and "WITHOUT ROWID" in sql["score_values"]
        and "UNIQUE (score_set, n)" in sql["score_rows"]
        and "ON score_rows (item_id)" in sql["score_rows_item"]
        and "rows" not in {r[0] for r in db().execute("SELECT name FROM sqlite_master WHERE type = 'table'")},
        sorted(sql),
    )

    # ── every type, and the keys' order ─────────────────────────────────────────────────────────────────────────────
    ALL = {
        "item_id": "t1",
        "i": 1, "f": 1.0, "negzero": -0.0, "zero": 0, "fzero": 0.0, "frac": 0.1 + 0.2, "huge": 1.7976931348623157e308,
        "tiny": 5e-324, "hi": 2**63 - 1, "lo": -(2**63), "past": 2**63, "pastneg": -(2**63) - 1, "enormous": 10**40,
        "yes": True, "no": False, "none": None, "nan": float("nan"), "inf": float("inf"), "ninf": float("-inf"),
        "text": "é \"'", "empty": "", "list": [1, 2.0, None, {"k": [True]}], "obj": {"b": 1, "a": 1.0}, "_commit": "abc",
        "_meta": {"provider": "p", "usage": {"cost": 1, "prompt_tokens": 2}, "predicted": [3, 1]},
        "_extra": {"x": 1},
    }  # fmt: skip
    rows = [ALL, {"item_id": "t2", "i": 2}]
    d = run_with("arm_b_v1", {"s": rows})
    sd = score_dirs(d)[0]
    fresh()
    got = _outputs.rows(sd)
    assert got is not None
    g = got[0]
    check(
        "every field comes back, as JSON the same row (NaN and the infinities included)",
        [line(r) for r in got] == [line(r) for r in rows],
        line(got[0])[:200],
    )
    check(
        "an int stays an int and a float a float (1 and 1.0, 0 and 0.0), -0.0 keeps its sign, int64's bounds are exact",
        type(g["i"]) is int
        and type(g["f"]) is float
        and g["i"] == 1
        and type(g["zero"]) is int
        and type(g["fzero"]) is float
        and math.copysign(1, g["negzero"]) == -1.0
        and g["hi"] == 2**63 - 1
        and g["lo"] == -(2**63)
        and g["frac"] == 0.1 + 0.2
        and g["huge"] == 1.7976931348623157e308
        and g["tiny"] == 5e-324,
        {k: (type(v).__name__, v) for k, v in g.items() if k in ("i", "f", "zero", "fzero", "negzero")},
    )
    check(
        "a bool stays a bool, None None, NaN and the infinities come back; an integer past int64 stays an integer",
        g["yes"] is True
        and g["no"] is False
        and g["none"] is None
        and math.isnan(g["nan"])
        and g["inf"] == math.inf
        and g["ninf"] == -math.inf
        and g["past"] == 2**63
        and type(g["past"]) is int
        and g["pastneg"] == -(2**63) - 1
        and g["enormous"] == 10**40
        and type(g["enormous"]) is int,
    )
    check(
        "a row's keys are sorted, at the top and in `_meta`; a list and an object keep their types",
        list(g) == sorted(g)
        and list(g["_meta"]) == sorted(g["_meta"])
        and g["list"] == [1, 2.0, None, {"k": [True]}]
        and type(g["list"][1]) is float
        and g["obj"] == {"a": 1.0, "b": 1},
        list(g),
    )
    sid = db().execute("SELECT id FROM score_sets WHERE key = ?", (_store.rel(sd),)).fetchone()[0]
    names = dict(db().execute("SELECT id, name FROM metrics"))
    vals = {
        names[m]: v
        for m, v in db().execute("SELECT metric, value FROM score_values WHERE row = ?", (sid << 20,))
    }
    types = {
        k: db()
        .execute(
            "SELECT typeof(value) FROM score_values WHERE row = ? AND metric = (SELECT id FROM metrics WHERE name = ?)",
            (sid << 20, k),
        )
        .fetchone()[0]
        for k in vals
    }
    check(
        "the type rule: score_values holds the ints and the finite floats (and nothing else), kept as integer and real",
        set(vals) == {"i", "f", "negzero", "zero", "fzero", "frac", "huge", "tiny", "hi", "lo"}
        and {k: t for k, t in types.items() if t == "integer"}
        == {"i": "integer", "zero": "integer", "hi": "integer", "lo": "integer"}
        and all(types[k] == "real" for k in ("f", "negzero", "fzero", "frac", "huge", "tiny")),
        types,
    )
    rest = json.loads(db().execute("SELECT rest FROM score_rows WHERE id = ?", (sid << 20,)).fetchone()[0])
    check(
        "the type rule: `rest` holds the bool, None, NaN, infinities, integers past int64, text, lists, objects and other `_` keys, and not item_id, _meta, _extra",
        set(rest)
        == {
            "yes",
            "no",
            "none",
            "nan",
            "inf",
            "ninf",
            "past",
            "pastneg",
            "enormous",
            "text",
            "empty",
            "list",
            "obj",
            "_commit",
        },
        sorted(rest),
    )
    check(
        "a row with only numbers and its item has `rest` NULL; `_extra` NULL when absent",
        db().execute("SELECT rest, extra FROM score_rows WHERE id = ?", ((sid << 20) + 1,)).fetchone()
        == (None, None),
    )

    def cells() -> list[Any]:
        return [
            db().execute("SELECT * FROM score_rows ORDER BY id").fetchall(),
            db().execute("SELECT * FROM score_values ORDER BY row, metric").fetchall(),
            db().execute("SELECT * FROM metrics ORDER BY id").fetchall(),
        ]

    before = cells()
    _outputs.store().put_rows(sd, [dict(reversed(list(r.items()))) for r in rows])
    check(
        "the same rows with their keys in the other order write the same tables, cell for cell (nothing depends on a dict's order)",
        repr(cells()) == repr(before),
    )
    fresh()
    check("and read back the same", [line(r) for r in _outputs.rows(sd) or []] == [line(r) for r in rows])

    # ── the numbers without `_meta` and `_extra` (meta=False): a third of a read, for the readers of numbers ────────
    fresh()
    sk = (_store.rel(sd), False)
    lite = _outputs.rows(sd, meta=False) or []
    full_keys = {k for r in rows for k in r}
    check(
        "meta=False: the rows lack `_meta` and `_extra` and hold every other field as the full rows do (NaN, text, `_commit` included)",
        len(lite) == 2
        and all("_meta" not in r and "_extra" not in r for r in lite)
        and [line({k: v for k, v in r.items() if k not in ("_meta", "_extra")}) for r in rows]
        == [line(r) for r in lite]
        and all(list(r) == sorted(r) for r in lite)
        and set(lite[0]) == full_keys - {"_meta", "_extra"},
        [line(r)[:120] for r in lite],
    )
    held_light = _outputs._SQLITE._rows[sk]
    check("meta=False: the cache keeps the set as light", held_light.light and held_light.rows is not None)
    check(
        "meta=False twice: the same dicts (served by the cache)",
        (_outputs.rows(sd, meta=False) or [{}])[0] is lite[0],
    )
    full = _outputs.rows(sd) or []
    check(
        "a full read after a light one reads the set again (the light one is not served to it), and is whole",
        full[0] is not lite[0]
        and [line(r) for r in full] == [line(r) for r in rows]
        and not _outputs._SQLITE._rows[sk].light,
    )
    check(
        "a light read after a full one is served the full rows (a superset, the same objects)",
        (_outputs.rows(sd, meta=False) or [{}])[0] is full[0]
        and _outputs.rows_text(sd) == "".join(_outputs.row_line(r) for r in rows),
    )
    fresh()
    _outputs.rows(sd, meta=False)
    check(
        "rows_text after a light read is the full canonical text (never derived from the light rows)",
        _outputs.rows_text(sd) == "".join(_outputs.row_line(r) for r in rows)
        and "_meta" in (_outputs.rows(sd) or [{}])[0],
    )
    fresh()
    light_rows = list(_runs.item_rows(sd, meta=False))
    full_rows = list(_runs.item_rows(sd))
    check(
        "item_rows(meta=False) yields the light rows (no `_meta`), item_rows the full ones; the numbers are the same",
        [r["item_id"] for r in light_rows] == [r["item_id"] for r in full_rows] == ["t1", "t2"]
        and "_meta" not in light_rows[0]
        and "_meta" in full_rows[0]
        and [_runs.score_of(r, "i") for r in light_rows]
        == [_runs.score_of(r, "i") for r in full_rows]
        == [1.0, 2.0],
    )

    # ── a random mix of types, the same text through the store as through json ──────────────────────────────────────
    rng = random.Random(33)
    pool = [0, 1, -1, 7, 2**31, 2**62, 2**63 - 1, -(2**63), 2**63, 0.0, -0.0, 1.0, 0.5, 1e-300, 1e300, float("inf"), float("-inf"),
            float("nan"), True, False, None, "s", "", [1], {"a": 1}, [None, 1.5]]  # fmt: skip
    fuzz = []
    for n in range(400):
        fr: dict[str, Any] = {"item_id": f"f{n}"}
        for k in rng.sample(["a", "b", "c", "d", "e", "_k", "z"], rng.randint(0, 6)):
            fr[k] = rng.choice(pool)
        if rng.random() < 0.3:
            fr["_meta"] = rng.choice([{}, {"provider": "p"}, {"usage": {"cost": 1}, "x": 1}, {"x": None}])
        if rng.random() < 0.3:
            fr["_extra"] = rng.choice([{}, {"k": 1}])
        fuzz.append(fr)
    d = run_with("arm_c_v1", {"s": fuzz})
    sd2 = score_dirs(d)[0]
    fresh()
    back = _outputs.rows(sd2) or []
    check(
        "400 rows of random types (every value of the pool, in any field) read back as the same JSON, keys sorted",
        [line(r) for r in back] == [line(r) for r in fuzz] and all(list(r) == sorted(r) for r in back),
        next(((line(a), line(b)) for a, b in zip(back, fuzz, strict=False) if line(a) != line(b)), None),
    )

    # ── `_meta`, `_extra` and the call facts ────────────────────────────────────────────────────────────────────────
    new_project()
    CALL = {"provider": "p", "response_model": "m", "usage": {"cost": 0.5}, "finish_reason": "stop"}
    s1 = [
        {
            "item_id": "a",
            "x": 1,
            "_meta": {**CALL, "predicted": "A"},
            "_extra": {},
        },  # facts held for the item, its own meta
        {"item_id": "b", "x": 2, "_meta": {}},  # `{}` kept
        {"item_id": "c", "x": 3},  # no `_meta`
        {"item_id": "d", "x": 4, "_meta": dict(CALL)},  # only call facts: `_meta: {}` left, kept
        {
            "item_id": "e",
            "x": 5,
            "_meta": {"generation_config": {"t": 0}, "ranking": [2, 1]},
        },  # a setting is score-level
    ]
    s2 = [
        {"item_id": "a", "x": 1, "_meta": {**CALL, "gates": [1]}},  # equal facts, other score-level meta
        {
            "item_id": "b",
            "x": 2,
            "_meta": {**CALL},
        },  # b's first facts: held by s1? no (s1's b has none): inserted here
        {
            "item_id": "c",
            "x": 3,
            "_meta": {**CALL, "usage": {"cost": 0.9}},
        },  # c's facts: inserted here (s1 had none)
        {
            "item_id": "d",
            "x": 4,
            "_meta": {**CALL, "usage": {"cost": 0.7}},
        },  # differs from s1's d: whole `_meta` stays
    ]
    d = run_with("arm_d_v1", {"s1": s1, "s2": s2})
    a, b = score_dirs(d)
    fresh()
    ra, rb = _outputs.rows(a) or [], _outputs.rows(b) or []
    check(
        "every `_meta` reads back as written: absent absent, `{}` `{}`, call facts put back, a differing row's own",
        [line(r) for r in ra] == [line(r) for r in s1] and [line(r) for r in rb] == [line(r) for r in s2],
        ([line(r) for r in ra], [line(r) for r in rb]),
    )
    run_key = _store.rel(d)
    ka, kb = _store.rel(a), _store.rel(b)

    def stored(key: str | None, item: str) -> tuple[Any, ...]:
        sid = db().execute("SELECT id FROM score_sets WHERE key = ?", (key,)).fetchone()[0]
        return (
            db()
            .execute(
                "SELECT facts, meta, extra FROM score_rows WHERE score_set = ? AND item_id = ?", (sid, item)
            )
            .fetchone()
        )

    check(
        "absent `_meta`: meta NULL and facts 0; `{}`: meta `{}`, facts 0; only call facts: facts 1 and meta `{}`",
        stored(ka, "c") == (0, None, None)
        and stored(ka, "b")[:2] == (0, "{}")
        and stored(ka, "d")[:2] == (1, "{}"),
        [stored(ka, i) for i in "bcd"],
    )
    check(
        "call facts equal to the held ones leave the row (facts 1), the score-level meta stays; `_extra` `{}` is kept, absent NULL",
        stored(ka, "a") == (1, '{"predicted": "A"}', "{}") and stored(kb, "a")[:2] == (1, '{"gates": [1]}'),
        (stored(ka, "a"), stored(kb, "a")),
    )
    check(
        "facts that differ from the held ones: facts 0 and the row's whole `_meta` stays",
        json.loads(stored(kb, "d")[1]) == {**CALL, "usage": {"cost": 0.7}} and stored(kb, "d")[0] == 0,
        stored(kb, "d"),
    )
    held = dict(db().execute("SELECT item_id, meta FROM call_facts WHERE run = ?", (run_key,)))
    check(
        "call_facts: one row per run and item that has facts, inserted by the first row that has them (a setting is not a call fact)",
        set(held) == {"a", "b", "c", "d"}
        and held["a"] == line(CALL)
        and json.loads(held["c"])["usage"] == {"cost": 0.9}
        and "generation_config" not in "".join(held.values()),
        held,
    )
    check(
        "a call fact written by the run's second score set is held for the first too: `e`'s setting stays in its row",
        stored(ka, "e")[0] == 0 and "generation_config" in stored(ka, "e")[1],
    )
    db().execute(
        "UPDATE score_rows SET meta = ? WHERE score_set = (SELECT id FROM score_sets WHERE key = ?) AND item_id = 'a'",
        ('{"provider": "mine", "predicted": "A"}', ka),
    )
    fresh()
    own = (_outputs.rows(a) or [])[0]["_meta"]
    check(
        "a row's own key wins over the held call fact, the others come from `call_facts`",
        own["provider"] == "mine"
        and own["usage"] == {"cost": 0.5}
        and own["predicted"] == "A"
        and list(own) == sorted(own),
        own,
    )
    # a score set that is not under runs/<run>/scores/<key>
    scratch = DATA / "scratch" / "x"
    _outputs.store().put_rows(scratch, [{"item_id": "a", "_meta": {**CALL, "predicted": 1}}])
    fresh()
    check(
        "a score set outside runs/<run>/scores/<key> has no call facts: its rows keep their `_meta` whole (facts 0)",
        _outputs.rows(scratch) == [{"item_id": "a", "_meta": {**CALL, "predicted": 1}}]
        and db()
        .execute(
            "SELECT facts FROM score_rows WHERE item_id = 'a' AND score_set = (SELECT id FROM score_sets WHERE key = 'scratch/x')"
        )
        .fetchone()
        == (0,)
        and db().execute("SELECT count(*) FROM call_facts WHERE run NOT LIKE 'runs/%'").fetchone() == (0,),
    )
    # a run's facts read for a row whose pair is gone: an error that names the row, not a silent half row
    db().execute("DELETE FROM call_facts WHERE run = ? AND item_id = 'd'", (run_key,))
    fresh()
    try:
        _outputs.rows(a)
        said = ""
    except ValueError as exc:
        said = str(exc)
    check(
        "a row that says it has call facts the run lacks: a ValueError naming the row",
        "call facts" in said and "'d'" not in said and "d " in said,
        said,
    )

    # ── ids ─────────────────────────────────────────────────────────────────────────────────────────────────────────
    new_project()
    d = run_with("arm_e_v1", {"s": [{"item_id": "i", "x": 1}, {"item_id": "j", "x": 2}]})
    sd = score_dirs(d)[0]
    key = _store.rel(sd)
    want_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") >> 21
    got_id = db().execute("SELECT id FROM score_sets WHERE key = ?", (key,)).fetchone()[0]
    rids = [r[0] for r in db().execute("SELECT id FROM score_rows ORDER BY id")]
    check(
        "a score set's id is the first 43 bits of its key's sha256; a row's is score_set * 2^20 + n, from n = 0",
        got_id == want_id
        and want_id < 2**43
        and rids == [got_id << 20, (got_id << 20) + 1]
        and rids[-1] < 2**63,
        (got_id, want_id, rids),
    )
    keep = _outputs._set_hash
    try:
        _outputs._set_hash = lambda key: 77  # every key collides
        ks = [DATA / "scratch" / n for n in ("c", "a", "b")]
        for kd in ks:
            _outputs.store().put_rows(kd, [{"item_id": "i", "x": 1}])
        ids = dict(db().execute("SELECT key, id FROM score_sets WHERE key LIKE 'scratch/%'"))
        check(
            "a collision takes the next free id upward, in the order the keys come",
            ids == {"scratch/c": 77, "scratch/a": 78, "scratch/b": 79},
            ids,
        )
        _outputs.store().put_rows(ks[1], [{"item_id": "i", "x": 2}, {"item_id": "k", "x": 3}])
        fresh()
        check(
            "a key found by what it is, not by its hash: a rewritten probed set keeps its id and reads back, its neighbours untouched",
            dict(db().execute("SELECT key, id FROM score_sets WHERE key LIKE 'scratch/%'")) == ids
            and [r["x"] for r in _outputs.rows(ks[1]) or []] == [2, 3]
            and [r["x"] for r in _outputs.rows(ks[0]) or []] == [1]
            and [r["x"] for r in _outputs.rows(ks[2]) or []] == [1],
        )
        _outputs._set_hash = lambda key: 2**43 - 1
        _outputs.store().put_rows(DATA / "scratch" / "w1", [{"item_id": "i"}])
        _outputs.store().put_rows(DATA / "scratch" / "w2", [{"item_id": "i"}])
        w = dict(db().execute("SELECT key, id FROM score_sets WHERE key LIKE 'scratch/w%'"))
        check("an id past 2^43 - 1 wraps to 0", w == {"scratch/w1": 2**43 - 1, "scratch/w2": 0}, w)
        check(
            "a score set at the last id has its rows under 2^63",
            db().execute("SELECT max(id) FROM score_rows").fetchone()[0] < 2**63,
        )
    finally:
        _outputs._set_hash = keep
    said = ""
    try:
        _outputs.store().put_rows(DATA / "scratch" / "big", [{"item_id": "i"}] * (2**20 + 1))
    except SystemExit as exc:
        said = str(exc)
    check(
        "a score set over 2^20 rows is refused (invalid-file), nothing written",
        said.startswith("ERROR (invalid-file)")
        and db().execute("SELECT 1 FROM score_sets WHERE key = 'scratch/big'").fetchone() is None,
        said,
    )
    _outputs.store().put_rows(DATA / "scratch" / "full", [{"item_id": "i"}] * 2**20)
    check(
        "a score set of exactly 2^20 rows is written, its last row id inside its own range",
        db()
        .execute(
            "SELECT count(*) FROM score_rows WHERE score_set = (SELECT id FROM score_sets WHERE key = 'scratch/full')"
        )
        .fetchone()[0]
        == 2**20
        and db().execute("SELECT max(id) FROM score_rows").fetchone()[0] < 2**63,
    )

    # ── one transaction ─────────────────────────────────────────────────────────────────────────────────────────────
    new_project()
    d = run_with("arm_f_v1", {"s": [{"item_id": "i", "x": 1}, {"item_id": "j", "x": 2}]})
    sd = score_dirs(d)[0]
    before = {t: table_rows(db(), t) for t in TABLES[:-1]}
    try:
        _outputs.store().put_rows(
            sd, [{"item_id": "i", "x": 9, "new_metric": 1}, {"item_id": "j", "_meta": {"x": object()}}]
        )
        raised = False
    except TypeError:
        raised = True
    after = {t: db().execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in before}  # noqa: S608  # nosec B608 - fixed table names
    fresh()
    check(
        "a write that fails half way leaves the score set, the metrics and the call facts as they were, and the connection free",
        raised
        and after == before
        and not db().in_transaction
        and [r["x"] for r in _outputs.rows(sd) or []] == [1, 2],
    )
    try:
        _outputs.store().put_rows(sd, [{"item_id": "i"}, {"acc": 1}])
        said = ""
    except SystemExit as exc:
        said = str(exc)
    check(
        "a row without an item_id is refused before anything is written",
        said.startswith("ERROR (invalid-file)") and {t: table_rows(db(), t) for t in before} == before,
    )

    # ── deleting ────────────────────────────────────────────────────────────────────────────────────────────────────
    new_project()
    c1 = {"provider": "p", "usage": {"cost": 1}}
    r1 = run_with(
        "arm_g_v1",
        {
            "s1": [{"item_id": "i", "x": 1, "_meta": dict(c1)}],
            "s2": [{"item_id": "i", "x": 2, "_meta": dict(c1)}],
        },
    )
    r2 = run_with("arm_h_v1", {"s1": [{"item_id": "i", "x": 3, "_meta": dict(c1)}]})
    _outputs.store().write_all(r1, {"i": "text"}, ["i"])
    _outputs.append_partial(r1, {"item_id": "i", "x": 1})
    g1, g2 = score_dirs(r1)
    h1 = score_dirs(r2)[0]

    def counts() -> dict[str, int]:
        return {
            t: db().execute(f"SELECT count(*) FROM {t}").fetchone()[0]  # noqa: S608  # nosec B608 - fixed table names
            for t in (
                "score_sets",
                "score_rows",
                "score_values",
                "call_facts",
                "outputs",
                "rows_partial",
                "metrics",
            )
        }

    c0 = counts()
    check(
        "setup: three score sets of two runs, one call fact per run and item",
        c0
        == {
            "score_sets": 3,
            "score_rows": 3,
            "score_values": 3,
            "call_facts": 2,
            "outputs": 1,
            "rows_partial": 2,
            "metrics": 1,
        },
        c0,
    )
    _outputs.store().drop_rows(g1)
    c1_ = counts()
    check(
        "a score set dropped: its rows, values and key go; the run's call facts stay while another score set is left",
        c1_["score_sets"] == 2
        and c1_["score_rows"] == 2
        and c1_["score_values"] == 2
        and c1_["call_facts"] == 2
        and not _outputs.has_rows(g1)
        and _outputs.rows(g1) is None
        and (_outputs.rows(g2) or [{}])[0]["_meta"] == c1,
        c1_,
    )
    _outputs.store().drop_rows(g2)
    c2_ = counts()
    check(
        "the run's last score set dropped: its call facts go with it, the other run's stay; metrics stay",
        c2_["call_facts"] == 1
        and c2_["score_sets"] == 1
        and c2_["metrics"] == 1
        and db().execute("SELECT run FROM call_facts").fetchone() == (_store.rel(r2),),
        c2_,
    )
    _outputs.store().put_rows(g1, [{"item_id": "i", "x": 1, "_meta": dict(c1)}])
    _outputs.store().put_rows(g2, [{"item_id": "i", "x": 2, "_meta": dict(c1)}])
    _store.rmtree(g1)
    check(
        "rmtree of one score set's folder: its rows go through the key, the sibling's and the run's call facts stay",
        counts()["score_sets"] == 2
        and counts()["call_facts"] == 2
        and _outputs.rows(g1) is None
        and len(_outputs.rows(g2) or []) == 1,
        counts(),
    )
    _store.rmtree(r1)
    c3_ = counts()
    check(
        "rmtree of a run: its score sets' rows and values, its call facts, its outputs and its checkpoint go; the other run is whole",
        c3_["score_sets"] == 1
        and c3_["score_rows"] == 1
        and c3_["call_facts"] == 1
        and c3_["outputs"] == 0
        and c3_["rows_partial"] == 0
        and _outputs.rows(g2) is None
        and (_outputs.rows(h1) or [{}])[0].get("x") == 3
        and _outputs.rows_text(r1, partial=True) is None,
        c3_,
    )
    try:
        _store.replace(r2, DATA / "elsewhere")
        moved, said_moved = True, ""
    except ValueError as exc:
        moved, said_moved = False, str(exc)
    check(
        "a run with score sets under it cannot be moved as files (its rows are not files, a move would leave them behind)",
        not moved
        and said_moved.endswith("leave them behind; a release copies a run with them, a folder copy cannot")
        and _outputs.rows(h1) is not None,
        said_moved,
    )
    db().execute(
        "INSERT INTO call_facts VALUES ('runs/never_scored', 'x', '{}')"
    )  # facts of a run no score set is of
    db().execute("INSERT INTO call_facts VALUES ('runs/other_orphan', 'x', '{}')")
    kept_facts = [
        r[0] for r in db().execute("SELECT run FROM call_facts WHERE run != 'runs/never_scored' ORDER BY run")
    ]
    _store.rmtree(DATA / "runs" / "never_scored", ignore_errors=True)
    check(
        "rmtree of a run takes its call facts whether or not a score set of it is left, and no other run's",
        [r[0] for r in db().execute("SELECT run FROM call_facts ORDER BY run")] == kept_facts
        and "runs/other_orphan" in kept_facts,
        db().execute("SELECT run FROM call_facts ORDER BY run").fetchall(),
    )
    db().execute("DELETE FROM call_facts")
    last = run_with("arm_n_v1", {"s": [{"item_id": "i", "x": 1, "_meta": dict(c1)}]})
    _outputs.store().write_all(last, {"i": "text"}, ["i"])
    _outputs.append_partial(last, {"item_id": "i"})
    _store.rmtree(RUNS)
    check(
        "rmtree of runs/: every score set, value, call fact and output is gone; the metrics' names stay",
        {k: v for k, v in counts().items() if k != "metrics"}
        == dict.fromkeys(
            ("score_sets", "score_rows", "score_values", "call_facts", "outputs", "rows_partial"), 0
        ),
        counts(),
    )

    # ── the item index ──────────────────────────────────────────────────────────────────────────────────────────────
    new_project()
    ra = run_with(
        "arm_i_v1",
        {"s": [{"item_id": "p", "x": 1.5, "_meta": dict(c1), "_extra": {}}, {"item_id": "q", "x": 2}]},
    )
    rb = run_with("arm_j_v1", {"s": [{"item_id": "q", "x": 3, "k": "v"}, {"item_id": "q", "x": 4}]})
    sa, sb = score_dirs(ra)[0], score_dirs(rb)[0]
    plan = " | ".join(
        str(r[3])
        for r in db().execute(
            "EXPLAIN QUERY PLAN SELECT s.key, r.id FROM score_rows r JOIN score_sets s ON s.id = r.score_set WHERE r.item_id = ? ORDER BY s.key, r.n",
            ("q",),
        )
    )
    fresh()
    across = _outputs.item_across([sa, sb], "p")
    across_q = _outputs.item_across([sa, sb], "q")
    check(
        "item_across: the item's row in every set that has it (the first, when a set has it twice), assembled as rows() gives it",
        across == {sa: (_outputs.rows(sa) or [])[0]}
        and across_q == {sa: (_outputs.rows(sa) or [])[1], sb: (_outputs.rows(sb) or [])[0]}
        and across_q[sb]["x"] == 3,
        across_q,
    )
    check("item_across searches the item index", "score_rows_item" in plan, plan)
    across["x"] = 1
    check(
        "item_across's rows are the caller's own, not the cache's",
        (_outputs.rows(sa) or [{}])[0].get("x") == 1.5,
    )
    check(
        "row_runs: every score set, and every run with a checkpoint; runs: the runs that hold outputs",
        _outputs._SQLITE.row_runs() == [(_store.rel(sa), False), (_store.rel(sb), False)]
        and _outputs._SQLITE.runs() == [],
        _outputs._SQLITE.row_runs(),
    )
    _outputs.append_partial(ra, {"item_id": "p"})
    _outputs.store().write_all(ra, {"p": "t"}, ["p"])
    check(
        "row_runs and runs after a checkpoint and outputs",
        _outputs._SQLITE.row_runs()
        == sorted([(_store.rel(sa), False), (_store.rel(sb), False), (_store.rel(ra), True)])
        and _outputs._SQLITE.runs() == [_store.rel(ra)],
    )

    # ── V9 in SQLite ────────────────────────────────────────────────────────────────────────────────────────────────
    new_project()
    _store.write_text(DATA / "validate.json", json.dumps({"floors": {"runs": 2}}))
    r1 = run_with("arm_k_v1", {"s": [{"item_id": "a"}, {"item_id": "b"}, {"item_id": "c"}]})
    r2 = run_with("arm_l_v1", {"s": [{"item_id": "a"}, {"item_id": "b"}]})
    bad, out = v9()
    check(
        "V9 on a database whose score sets all have their rows, as many as n_items, and an arm at its floor: passes (both checks run)",
        not bad
        and "ok   V9 every score set with a record has its rows" in out
        and "ok   V9 each committed arm meets its floor" in out,
        out,
    )
    s1, s2 = score_dirs(r1)[0], score_dirs(r2)[0]
    _outputs.store().drop_rows(s1)
    bad, out = v9()
    check(
        "V9: a score set with a record and no rows fails, naming it",
        len(bad) == 1 and f"{_store.rel(s1)} has no rows" in out and "FAIL V9 every score set" in out,
        out,
    )
    _outputs.store().put_rows(s1, [])
    bad, out = v9()
    check("V9: an empty score set fails, naming it", len(bad) == 1 and "an empty score set" in out, out)
    _outputs.store().put_rows(s1, [{"item_id": "a"}, {"item_id": "b"}])
    bad, out = v9()
    check(
        "V9: fewer rows than n_items fails, naming both numbers",
        len(bad) == 1 and f"{_store.rel(s1)} has 2 rows, its record says n_items=3" in out,
        out,
    )
    _outputs.store().put_rows(s1, [{"item_id": "a"}, {"item_id": "b"}, {"item_id": "c"}, {"item_id": "d"}])
    bad, out = v9()
    check(
        "V9: more rows than n_items fails too",
        len(bad) == 1 and "has 4 rows, its record says n_items=3" in out,
        out,
    )
    _outputs.store().put_rows(s1, [{"item_id": "a"}, {"item_id": "b"}, {"item_id": "c"}])
    _store.rmtree(r2)
    bad, out = v9()
    check(
        "V9: an arm below its floor fails, naming it (the rows being whole)",
        len(bad) == 1
        and "runs: 1 scores, expected at least 2" in out
        and "FAIL V9 each committed arm meets its floor" in out,
        out,
    )
    run_with("arm_l_v1", {"s": [{"item_id": "a"}, {"item_id": "b"}]})
    bad, out = v9()
    check("V9 passes again once the score sets are back", not bad, out)
    db().execute("DELETE FROM score_sets WHERE key = ?", (_store.rel(score_dirs(r1)[0]),))
    fresh()
    bad, out = v9()
    check(
        "V9: a score set whose database entry is deleted (its record is not) fails as having no rows",
        len(bad) == 1 and "has no rows" in out,
        out,
    )

    # ── data-migrate: there and back ────────────────────────────────────────────────────────────────────────────────
    files = Path(tempfile.mkdtemp(prefix="evh-tables-files-"))
    try:
        (files / "config.yaml").write_text("store: files\n")
        fdata = files / "data"
        fdata.mkdir()
        _format.stamp(data=fdata)
        (fdata / "systems").mkdir()
        (fdata / "systems" / "arm_m_v1.yaml").write_text("system_id: arm_m_v1\n")
        for rid, cases in (("arm_m_v1", [ALL, {"item_id": "z"}]), ("arm_n_v1", fuzz[:50])):
            rd = fdata / "runs" / rid
            sdir = rd / "scores" / "aaaaaaaaaaaa@gold.ds"
            sdir.mkdir(parents=True)
            (rd / "run.json").write_text(
                json.dumps({"run_id": rid, "system_id": "arm_m_v1", "dataset_id": "ds"}) + "\n"
            )
            (sdir / "metrics.json").write_text("{}\n")
            (sdir / "predictions.jsonl").write_text("".join(line(r) + "\n" for r in cases))
        (fdata / "runs" / "arm_m_v1" / "rows.partial.jsonl").write_text('{"item_id": "z"}\n{"item_id": "y"')
        (fdata / "runs" / "arm_n_v1" / "outputs.jsonl").write_text(
            json.dumps({"item_id": "i", "text": "t", "sha256": hashlib.sha256(b"t").hexdigest()}) + "\n"
        )

        def tree(p: Path) -> dict[str, bytes]:
            return {str(f.relative_to(p)): f.read_bytes() for f in sorted(p.rglob("*")) if f.is_file()}

        held = tree(fdata)
        (files / "config.yaml").write_text("store: sqlite\n")
        r = dm("sqlite", "data-migrate", "--to", "sqlite", cwd=files)
        check(
            "data-migrate --to sqlite: the 52 rows and the checkpoint's 2 lines move in",
            r.returncode == 0 and "54 row(s)" in r.stdout,
            r.stdout + r.stderr[-400:],
        )
        conn = sqlite3.connect(fdata / "project.sqlite")
        got = {
            t: table_rows(conn, t, "count(*)", "1")[0][0]
            for t in ("score_sets", "score_rows", "rows_partial")
        }
        conn.close()
        check(
            "the database holds both score sets, 52 rows and the checkpoint, and no file but itself is left in data/",
            got == {"score_sets": 2, "score_rows": 52, "rows_partial": 3}
            and [p.name for p in fdata.iterdir() if not p.name.startswith("project.sqlite")] == [],
            got,
        )
        (files / "config.yaml").write_text("store: files\n")
        r = dm("files", "data-migrate", "--to", "files", cwd=files)
        check(
            "data-migrate --to files: the data back, every file byte for byte (the rows canonical, as they went in)",
            r.returncode == 0 and tree(fdata) == held,
            (
                r.stdout + r.stderr[-400:],
                sorted(k for k in set(tree(fdata)) | set(held) if tree(fdata).get(k) != held.get(k)),
            ),
        )
    finally:
        shutil.rmtree(files, ignore_errors=True)
finally:
    _outputs.reset()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
