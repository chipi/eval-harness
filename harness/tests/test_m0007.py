#!/usr/bin/env python3
"""`evh migrate`'s format 7 step (RFC-033): the run's settings once on the run, the usage slimmed, rows canonical.

    python tests/test_m0007.py

A copy of tests/fixtures/formats/6 (what 0.8.0 wrote before RFC-033: seven runs with every shape of the rule) in each
store. --dry-run prints each count and writes nothing; the migration then: a setting every row of every score holds
goes to run.json's `call` (all three, one, none; a run of one row; a run whose second score holds another value; a run
whose `call` an interrupted migration began, its rows cleaned of the value it holds and keeping the one that differs),
every usage is slimmed (full, zero cache counts, no cost, `null`, not an object, already slim), a row not in key order
is made canonical, a line that is not a row and a score with no rows are left as they are, a run with no setting to
hoist is not written; project.yaml says format 7; a second `migrate` has nothing to do; the same step run on data that
still says format 6 (an interrupted migration) changes nothing. In a SQLite project the same counts, the rows
moved from table `rows` (format 6's) into the results tables, in one transaction; those tables, made from the lines
raw by the step's own frozen code, equal cell for cell the ones `data-migrate` makes from files (the live code);
moved back to files, every file byte-identical to the files store's. A project at format 7 that still holds `rows`
(the first build of this step kept the lines there) is finished by `migrate`, which `--check` and the store itself
refuse until then.
"""

import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
FIXTURE = HARNESS / "tests" / "fixtures" / "formats" / "6" / "data"
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

base = Path(tempfile.mkdtemp(prefix="evh-m0007-"))
GC = {"max_tokens": 300, "temperature": 0}
GR = {"max_tokens": 300, "reasoning": {"effort": "none"}, "temperature": 0}
SETTINGS = ("generation_config", "generation_requested", "encoder_window")
ALL = {"generation_config": GC, "generation_requested": GR, "encoder_window": 512}
CALLS = {
    "alpha_20261101T000000Z": ALL,
    "beta_20261101T000000Z": {"generation_requested": GR},
    "gamma_20261101T000000Z": ALL,
    "delta_20261101T000000Z": {"generation_config": GC, "generation_requested": GR},
    "epsilon_20261101T000000Z": {"generation_config": GC, "generation_requested": GR, "encoder_window": 512},
    "zeta_20261101T000000Z": None,
}
COUNTS = {
    "rows made canonical": 1,
    "run setting encoder_window, rows": 12,
    "run setting encoder_window, runs": 3,
    "run setting generation_config, rows": 15,
    "run setting generation_config, runs": 3,
    "run setting generation_requested, rows": 19,
    "run setting generation_requested, runs": 5,
    "run.json given a call": 5,
    "score sets rewritten": 8,
    "score sets that lost a run setting": 7,
    "score sets with usage slimmed": 7,
    "usage objects slimmed": 16,
    "usage objects without a cost (kept without one)": 1,
}


def legacy_db(src_data, proj, extra=None):
    """proj/data/project.sqlite as a project of format 6 kept `src_data`'s files: every file a row of `files`, each score's
    `predictions.jsonl` the lines of table `rows` (with its n = 0 marker), a checkpoint's partial = 1; written here by
    raw SQL, by no code of the harness. `extra` is {(key, partial): text} more of them."""
    (proj / "data").mkdir(parents=True)
    c = sqlite3.connect(proj / "data" / "project.sqlite")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(
        "CREATE TABLE files (path TEXT PRIMARY KEY, data BLOB NOT NULL, sha256 TEXT NOT NULL, mtime_ns INTEGER NOT NULL)"
    )
    c.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("INSERT INTO meta VALUES ('schema_version', '1')")
    c.execute(
        "CREATE TABLE outputs (run TEXT NOT NULL, item_id TEXT NOT NULL, text TEXT NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY (run, item_id))"
    )
    c.execute(
        "CREATE TABLE rows (run TEXT NOT NULL, partial INTEGER NOT NULL, n INTEGER NOT NULL, item_id TEXT, row TEXT NOT NULL,"
        " PRIMARY KEY (run, partial, n))"
    )
    c.execute("CREATE INDEX rows_item ON rows (item_id, run) WHERE partial = 0")
    lines = {}
    for p in sorted(src_data.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(src_data)
        if p.name in ("predictions.jsonl", "rows.partial.jsonl"):
            lines[(rel.parent.as_posix(), int(p.name == "rows.partial.jsonl"))] = p.read_text()
        else:
            b = p.read_bytes()
            c.execute(
                "INSERT INTO files VALUES (?, ?, ?, ?)", (rel.as_posix(), b, hashlib.sha256(b).hexdigest(), 1)
            )
    lines.update(extra or {})
    for (key, partial), text in lines.items():
        c.execute("INSERT INTO rows VALUES (?, ?, 0, NULL, '')", (key, partial))
        c.executemany(
            "INSERT INTO rows VALUES (?, ?, ?, NULL, ?)",
            [(key, partial, n, ln) for n, ln in enumerate(text.splitlines(keepends=True), 1)],
        )
    c.commit()
    c.close()


def evh(proj, store, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR")}
    env.update(EVAL_HOME=str(proj), EVAL_STORE=store, EVAL_BUILD_REF="test-m0007")
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


def tree(data):
    """{path under data/: bytes} of every file, but the database and its copies."""
    return {
        str(p.relative_to(data)): p.read_bytes()
        for p in sorted(data.rglob("*"))
        if p.is_file() and not p.name.startswith("project.sqlite")
    }


def digest(t):
    h = hashlib.sha256()
    for k, v in t.items():
        h.update(k.encode() + b"\0" + v + b"\1")
    return h.hexdigest()


def counts(stdout):
    return {m.group(2): int(m.group(1)) for m in re.finditer(r"^\s+(\d+)  (.+)$", stdout, re.M)}


def slim(u):
    """The expected usage, written here again from the RFC, not imported."""
    if not isinstance(u, dict):
        return u
    out = {k: u[k] for k in ("cost", "prompt_tokens", "completion_tokens") if k in u}
    det = u.get("prompt_tokens_details") if isinstance(u.get("prompt_tokens_details"), dict) else {}
    for k in ("cached_tokens", "cache_write_tokens"):
        if u.get(k) or det.get(k):
            out[k] = u.get(k) or det.get(k)
    return out


def expected_rows(text, call):
    """What a score's rows text becomes: each row's usage slimmed, each setting equal to the run's call off, canonical."""
    out = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            out.append(line + "\n")
            continue
        row = copy.deepcopy(row)
        meta = row.get("_meta")
        if isinstance(meta, dict):
            if "usage" in meta:
                meta["usage"] = slim(meta["usage"])
            for k in SETTINGS:
                if k in (call or {}) and k in meta and meta[k] == call[k]:
                    del meta[k]
        out.append(json.dumps(row, sort_keys=True) + "\n")
    return "".join(out)


try:
    pre = {str(p.relative_to(FIXTURE)): p.read_bytes() for p in sorted(FIXTURE.rglob("*")) if p.is_file()}
    check("the fixture is at format 6", b"format: 6" in pre["project.yaml"])

    # ── the files store ─────────────────────────────────────────────────────────────────────────────────────────────
    files = base / "files"
    shutil.copytree(FIXTURE, files / "data")
    r = evh(files, "files", "migrate", "--dry-run")
    check(
        "--dry-run: each count, and the data it would bring to format 7",
        r.returncode == 0 and counts(r.stdout) == COUNTS and "would bring the data to format 7" in r.stdout,
        r.stdout + r.stderr[-300:],
    )
    check("--dry-run: nothing written", tree(files / "data") == pre)

    # A line that is no row (a hand-edited file) is refused, writing nothing: the stores refuse to write one.
    junk = base / "junk"
    shutil.copytree(FIXTURE, junk / "data")
    zp = junk / "data" / "runs/zeta_20261101T000000Z/scores/aaaaaaaaaaaa@gold.ds/predictions.jsonl"
    zl_ = zp.read_text().splitlines()
    zp.write_text("\n".join([*zl_[:2], "not a json row", *zl_[2:]]) + "\n")
    held = tree(junk / "data")
    r = evh(junk, "files", "migrate")
    check(
        "a line that is not a row: migrate refuses, naming the score set and the line, and writes nothing",
        r.returncode != 0
        and "aaaaaaaaaaaa@gold.ds: line 3 is not a JSON object with an item_id" in r.stderr
        and tree(junk / "data") == held,
        r.stdout + r.stderr[-400:],
    )

    r = evh(files, "files", "migrate")
    after = tree(files / "data")
    check(
        "migrate: the same counts, and the data at format 7",
        r.returncode == 0 and counts(r.stdout) == COUNTS and b"format: 7" in after["project.yaml"],
        r.stdout + r.stderr[-300:],
    )
    check(
        "migrate: a second run has nothing to do",
        evh(files, "files", "migrate").stdout.strip().endswith("nothing to do"),
    )
    r = evh(files, "files", "validate")
    check(
        "validate: V28 is one of its checks, and holds on the migrated data",
        "ok   V28 rows — 9 score set(s)" in r.stdout,
        r.stdout[-600:],
    )
    held_key = "runs/alpha_20261101T000000Z/scores/aaaaaaaaaaaa@gold.ds/predictions.jsonl"
    (files / "data" / held_key).write_bytes(pre[held_key])
    r = evh(files, "files", "validate")
    check(
        "validate: a score's rows put back as format 6 wrote them, beside the run's call, fail V28, naming the score and the line",
        "FAIL V28" in r.stdout and "aaaaaaaaaaaa@gold.ds row 1" in r.stdout,
        r.stdout[-800:],
    )
    (files / "data" / held_key).write_bytes(after[held_key])

    for run, call in CALLS.items():
        rj = f"runs/{run}/run.json"
        old, new = json.loads(pre[rj]), json.loads(after[rj])
        got = new.pop("call", None)
        check(
            f"{run}: run.json `call` is {call}",
            got == call and new == {k: v for k, v in old.items() if k != "call"},
            got,
        )
        if call is None:
            check(f"{run}: a run with nothing to hoist is not written", after[rj] == pre[rj])
        scores = sorted(
            {k.split("/scores/")[1].split("/")[0] for k in pre if k.startswith(f"runs/{run}/scores/")}
        )
        for s in scores:
            key = f"runs/{run}/scores/{s}/predictions.jsonl"
            want = expected_rows(pre[key].decode(), json.loads(after[rj]).get("call"))
            check(
                f"{run} {s}: rows are the fixture's less the moved settings, usage slimmed, canonical",
                after[key].decode() == want,
            )

    def rows_of(run, s):
        return [
            json.loads(x)
            for x in after[f"runs/{run}/scores/{s}/predictions.jsonl"].decode().splitlines()
            if x.startswith("{")
        ]

    a1, a2 = (
        rows_of("alpha_20261101T000000Z", "aaaaaaaaaaaa@gold.ds"),
        rows_of("alpha_20261101T000000Z", "bbbbbbbbbbbb@gold.ds"),
    )
    kept = {
        "cached_tokens": 40,
        "cache_write_tokens": 10,
        "completion_tokens": 20,
        "cost": 0.0012,
        "prompt_tokens": 100,
    }
    check(
        "usage: full keeps the five (cached and cache-write from the details); zero counts keep neither; no cost keeps none; "
        "already slim is as it was",
        a1[0]["_meta"]["usage"] == kept
        and a1[1]["_meta"]["usage"] == {"completion_tokens": 20, "cost": 0.0012, "prompt_tokens": 100}
        and a1[2]["_meta"]["usage"] == {"completion_tokens": 0, "prompt_tokens": 0}
        and a1[3]["_meta"]["usage"]
        == {"cached_tokens": 3, "completion_tokens": 2, "cost": 0.5, "prompt_tokens": 1},
        [r["_meta"]["usage"] for r in a1],
    )
    check(
        "usage: null and a string stay as they were",
        a2[0]["_meta"]["usage"] is None and a2[1]["_meta"]["usage"] == "n/a",
        [r["_meta"]["usage"] for r in a2],
    )
    check(
        "settings: the rows keep what is not a setting (provider, finish_reason, the parser's `predicted`, `ranking`)",
        a1[0]["_meta"]
        == {
            "finish_reason": "stop",
            "predicted": "x",
            "provider": "p",
            "response_model": "m-1",
            "usage": kept,
        }
        and a2[0]["_meta"]["ranking"] == [1, 2],
        a1[0]["_meta"],
    )
    e = rows_of("epsilon_20261101T000000Z", "aaaaaaaaaaaa@gold.ds")
    check(
        "an interrupted migration's run: rows holding the call's value lose it, the row that holds another keeps it",
        "generation_config" not in e[0]["_meta"]
        and "generation_config" not in e[1]["_meta"]
        and e[2]["_meta"]["generation_config"] == {"max_tokens": 50, "temperature": 0},
        [r["_meta"].get("generation_config") for r in e],
    )
    d1 = rows_of("delta_20261101T000000Z", "aaaaaaaaaaaa@gold.ds")
    d2 = rows_of("delta_20261101T000000Z", "bbbbbbbbbbbb@gold.ds")
    check(
        "a run whose second score holds another value: that setting stays in the rows of both scores",
        all(x["_meta"]["encoder_window"] == 512 for x in d1)
        and all(x["_meta"]["encoder_window"] == 1024 for x in d2),
    )
    b = rows_of("beta_20261101T000000Z", "aaaaaaaaaaaa@gold.ds")
    check(
        "a setting that differs on a row, and one a row lacks, stay in every row that has it",
        [("generation_config" in x["_meta"], "encoder_window" in x["_meta"]) for x in b]
        == [(True, True), (True, True), (True, False)],
        [x["_meta"].keys() for x in b],
    )
    zk = "runs/zeta_20261101T000000Z/scores/aaaaaaaaaaaa@gold.ds/predictions.jsonl"
    zl = after[zk].decode().splitlines()
    check(
        "rows: one not in key order is made canonical; a score with no rows stays empty",
        zl[1] == '{"_extra": {}, "a": 2, "b": 1, "item_id": "z2"}'
        and len(zl) == 3
        and after["runs/zeta_20261101T000000Z/scores/bbbbbbbbbbbb@gold.ds/predictions.jsonl"] == b"",
        zl,
    )

    # an interrupted migration: the data still says format 6, the run.json calls are there, the rows are done
    (files / "data" / "project.yaml").write_bytes(pre["project.yaml"])
    before_again = tree(files / "data")
    r = evh(files, "files", "migrate")
    check(
        "the step run again on data that says format 6: 0 changed, then format 7",
        r.returncode == 0
        and "0 changed: already in this format" in r.stdout
        and {k: v for k, v in tree(files / "data").items() if k != "project.yaml"}
        == {k: v for k, v in before_again.items() if k != "project.yaml"}
        and b"format: 7" in (files / "data" / "project.yaml").read_bytes(),
        r.stdout + r.stderr[-300:],
    )

    # a run.json whose `call` is not an object, and rows that are not UTF-8, are refused with nothing written
    refused = base / "refused"
    shutil.copytree(FIXTURE, refused / "data")
    held_rj = refused / "data" / "runs" / "alpha_20261101T000000Z" / "run.json"
    doc = json.loads(held_rj.read_text())
    doc["call"] = "nope"
    held_rj.write_text(json.dumps(doc, indent=2) + "\n")
    held = tree(refused / "data")
    r = evh(refused, "files", "migrate")
    check(
        "a `call` that is not an object: refused, naming the file, nothing written",
        r.returncode != 0
        and "run.json: `call` is not an object" in r.stdout + r.stderr
        and tree(refused / "data") == held,
        r.stdout + r.stderr[-300:],
    )
    held_rj.write_text(json.dumps({k: v for k, v in doc.items() if k != "call"}, indent=2) + "\n")
    (
        refused
        / "data"
        / "runs"
        / "zeta_20261101T000000Z"
        / "scores"
        / "bbbbbbbbbbbb@gold.ds"
        / "predictions.jsonl"
    ).write_bytes(b'{"item_id": "\xff"}\n')
    held = tree(refused / "data")
    r = evh(refused, "files", "migrate")
    check(
        "rows that are not UTF-8: refused, naming the score, nothing written",
        r.returncode != 0
        and "its rows are not UTF-8" in r.stdout + r.stderr
        and tree(refused / "data") == held,
        r.stdout + r.stderr[-300:],
    )

    # ── the SQLite store: a project as format 6 kept it, its rows the lines of table `rows` ─────────────────────────
    def dump(proj):
        """Every table the rows live in, cell for cell, by the order each is read in."""
        c = sqlite3.connect(proj / "data" / "project.sqlite")
        try:
            out = {
                t: c.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall()  # noqa: S608  # nosec B608 - fixed table names
                for t in ("score_sets", "metrics", "call_facts", "score_rows", "score_values", "rows_partial")
            }
            out["tables"] = sorted(
                r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            )
        finally:
            c.close()
        return out

    sql = base / "sql"
    legacy_db(FIXTURE, sql)
    held = (sql / "data" / "project.sqlite").read_bytes()
    r = evh(sql, "sqlite", "migrate", "--dry-run")
    n_sets = sum(1 for k in after if k.endswith("/predictions.jsonl"))
    n_rows = sum(v.count(b"\n") for k, v in after.items() if k.endswith("/predictions.jsonl"))
    moved = {
        "score sets moved into the results tables": n_sets,
        "rows moved into the results tables": n_rows,
        "checkpoint lines moved": 0,
    }
    check(
        "sqlite --dry-run: the files store's counts, and the score sets and rows it would move into the results tables",
        r.returncode == 0 and counts(r.stdout) == {**COUNTS, **moved},
        r.stdout + r.stderr[-300:],
    )
    check("sqlite --dry-run: nothing written", (sql / "data" / "project.sqlite").read_bytes() == held)
    r = evh(sql, "sqlite", "migrate")
    check(
        "sqlite migrate: the same counts, backed up first, at format 7",
        r.returncode == 0
        and counts(r.stdout) == {**COUNTS, **moved}
        and "backup:" in r.stdout
        and "brought the data to format 7" in r.stdout,
        r.stdout + r.stderr[-300:],
    )
    vc = sqlite3.connect(f"file:{sql / 'data' / 'project.sqlite'}?mode=ro", uri=True)
    free = vc.execute("PRAGMA freelist_count").fetchone()[0]
    vc.close()
    check(
        "sqlite migrate: the pages `rows` held are given back (vacuumed, no free page left)",
        "vacuumed the database:" in r.stdout and free == 0,
        (free, [x for x in r.stdout.splitlines() if "vacuum" in x]),
    )
    got = dump(sql)
    check(
        "sqlite migrate: table `rows` is gone, the results tables hold every score set (an empty one too)",
        "rows" not in got["tables"]
        and len(got["score_sets"]) == n_sets
        and len(got["score_rows"]) == n_rows - 0,
        (got["tables"], len(got["score_sets"]), len(got["score_rows"])),
    )
    check(
        "sqlite migrate: a second run has nothing to do",
        evh(sql, "sqlite", "migrate").stdout.strip().endswith("nothing to do"),
    )
    live = base / "live"
    shutil.copytree(files / "data", live / "data")
    r = evh(live, "sqlite", "data-migrate", "--to", "sqlite")
    check(
        "the files store's migrated data moved into SQLite by data-migrate",
        r.returncode == 0,
        r.stdout + r.stderr[-300:],
    )
    check(
        "the step's frozen code and data-migrate's live code make the same tables, cell for cell",
        dump(live) == got,
        [t for t in got if dump(live)[t] != got[t]],
    )
    r = evh(sql, "files", "data-migrate", "--to", "files")
    check("the migrated database moved back to files", r.returncode == 0, r.stdout + r.stderr[-300:])
    back = tree(sql / "data")
    check(
        "both stores: every file of the data, byte for byte, as the files store's migration left it",
        back == after,
        sorted(k for k in set(back) | set(after) if back.get(k) != after.get(k)),
    )

    # ── a SQLite project of the first build of this step: at format 7, its rows still the lines of table `rows` ─────
    early = base / "early"
    legacy_db(files / "data", early)
    r = evh(early, "sqlite", "migrate", "--check")
    check(
        "format 7 with table `rows`: --check refuses it (the step is not finished), naming the step",
        r.returncode != 0 and "step 7 is not finished" in r.stdout + r.stderr,
        r.stdout + r.stderr[-300:],
    )
    r = evh(early, "files", "data-migrate", "--to", "files", "--dry-run")
    check(
        "format 7 with table `rows`: the store refuses it (migrate first)",
        r.returncode != 0 and "evh migrate first" in r.stdout + r.stderr,
        r.stdout + r.stderr[-300:],
    )
    r = evh(early, "sqlite", "arm-list", "--json")
    check(
        "format 7 with table `rows`: a command that reads rows refuses it too, from the store (ERROR (old-format))",
        r.returncode != 0
        and "ERROR (old-format)" in r.stdout + r.stderr
        and "table `rows`" in r.stdout + r.stderr,
        r.stdout[-200:] + r.stderr[-300:],
    )
    r = evh(early, "sqlite", "migrate", "--dry-run")
    check(
        "format 7 with table `rows`: --dry-run says what it moves and changes nothing else (no setting hoisted, no usage slimmed)",
        r.returncode == 0
        and counts(r.stdout) == {**moved, "usage objects without a cost (kept without one)": 1},
        r.stdout + r.stderr[-300:],
    )
    r = evh(early, "sqlite", "migrate")
    check(
        "format 7 with table `rows`: migrate moves the rows, and the tables are those an uninterrupted migration makes",
        r.returncode == 0
        and dump(early) == got
        and evh(early, "sqlite", "migrate").stdout.strip().endswith("nothing to do"),
        r.stdout + r.stderr[-300:],
    )
    check(
        "format 7 with the tables: --check passes", evh(early, "sqlite", "migrate", "--check").returncode == 0
    )

    # ── a crash while the rows move: the move is one transaction ───────────────────────────────────────────────────
    crash2 = base / "crash2"
    legacy_db(FIXTURE, crash2)
    helper2 = base / "crash_fill.py"
    helper2.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(HARNESS)!r})\n"
        "from evaluation_harness.migrations import m0007_results as m\n"
        "real = m._write_set\n"
        "calls = []\n"
        "def crashing(conn, key, rows):\n"
        "    calls.append(key)\n"
        "    if len(calls) == 4:\n"
        "        raise RuntimeError('crash while the rows move')\n"
        "    return real(conn, key, rows)\n"
        "m._write_set = crashing\n"
        "m.run(False)\n"
    )
    c = sqlite3.connect(crash2 / "data" / "project.sqlite")
    n_before = c.execute("SELECT count(*) FROM rows").fetchone()[0]
    c.close()
    env = {k: v for k, v in os.environ.items() if k not in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR")}
    env.update(EVAL_HOME=str(crash2), EVAL_STORE="sqlite")
    r = subprocess.run(
        [sys.executable, str(helper2)], cwd=crash2, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
        timeout=300,
    )  # fmt: skip
    c = sqlite3.connect(crash2 / "data" / "project.sqlite")
    tables = {r_[0] for r_ in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    n_after = c.execute("SELECT count(*) FROM rows").fetchone()[0]
    c.close()
    check(
        "a crash on the fourth score set: nothing of the move is kept (table `rows` whole, no results table)",
        r.returncode != 0
        and "crash while the rows move" in r.stderr
        and "rows" in tables
        and not ({"score_sets", "score_rows", "score_values", "call_facts", "rows_partial"} & tables)
        and n_after == n_before,
        (r.stderr[-200:], sorted(tables), n_before, n_after),
    )
    r = evh(crash2, "sqlite", "migrate")
    check(
        "the next migrate finishes it: the tables an uninterrupted migration makes",
        r.returncode == 0 and dump(crash2) == got,
        r.stdout + r.stderr[-300:],
    )

    # ── a checkpoint and a score set that is not a run's: kept as they are ──────────────────────────────────────────
    odd = base / "odd"
    legacy_db(
        FIXTURE,
        odd,
        extra={
            ("scratch/x", 1): '{"item_id": "p1", "acc": 1}\n{"item_id": "p2"',
            ("scratch/s", 0): '{"item_id": "s1", "_meta": {"provider": "p"}}\n',
        },
    )
    r = evh(odd, "sqlite", "migrate")
    c = sqlite3.connect(odd / "data" / "project.sqlite")
    parts = c.execute("SELECT run, n, line FROM rows_partial ORDER BY n").fetchall()
    sets = {k for (k,) in c.execute("SELECT key FROM score_sets")}
    facts = c.execute("SELECT count(*) FROM call_facts WHERE run NOT LIKE 'runs/%'").fetchone()[0]
    c.close()
    check(
        "sqlite migrate: a checkpoint is copied as it is (a torn last line too), a score set outside runs/ moves with no call facts",
        r.returncode == 0
        and parts
        == [
            ("scratch/x", 0, ""),
            ("scratch/x", 1, '{"item_id": "p1", "acc": 1}\n'),
            ("scratch/x", 2, '{"item_id": "p2"'),
        ]
        and "scratch/s" in sets
        and facts == 0,
        (r.stdout + r.stderr[-300:], parts, facts),
    )

    # ── a crash between a run's run.json and its rows ───────────────────────────────────────────────────────────────
    # run.json is written first, so a crash before the rows leaves the settings in both places, never in neither; the
    # next `evh migrate` finishes the job. The crash: the store's put_rows raises on its first call.
    crash = base / "crash"
    shutil.copytree(FIXTURE, crash / "data")
    helper = base / "crash_once.py"
    helper.write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(HARNESS)!r})\n"
        "from evaluation_harness import _outputs\n"
        "real = _outputs.store\n"
        "class Crashing:\n"
        "    def __init__(self, s):\n"
        "        self.s = s\n"
        "    def put_rows(self, *a, **k):\n"
        "        raise RuntimeError('crash before the rows')\n"
        "    def __getattr__(self, name):\n"
        "        return getattr(self.s, name)\n"
        "_outputs.store = lambda: Crashing(real())\n"
        "from evaluation_harness.migrations import m0007_results\n"
        "m0007_results.run(False)\n"
    )
    env = {k: v for k, v in os.environ.items() if k not in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR")}
    env.update(EVAL_HOME=str(crash), EVAL_STORE="files")
    r = subprocess.run(
        [sys.executable, str(helper)], cwd=crash, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
        timeout=300,
    )  # fmt: skip
    mid = tree(crash / "data")
    first_run = "runs/alpha_20261101T000000Z/run.json"
    check(
        "a crash before the rows: the first run's run.json holds its call, its rows still hold the settings",
        r.returncode != 0 and b'"call"' in mid[first_run] and mid[held_key] == pre[held_key],
        (r.stderr[-300:], mid[first_run][:200]),
    )
    r = evh(crash, "files", "migrate")
    check(
        "the next migrate finishes it: the data as an uninterrupted migration leaves it",
        r.returncode == 0 and tree(crash / "data") == after,
        sorted(k for k, v in tree(crash / "data").items() if after.get(k) != v)[:5],
    )
finally:
    shutil.rmtree(base, ignore_errors=True)

sys.exit(summary())
