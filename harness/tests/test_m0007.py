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
still says format 6 (an interrupted migration) changes nothing. In the SQLite project the same counts, and, moved back
to files, every file byte-identical to the files store's.
"""

import copy
import hashlib
import json
import os
import re
import shutil
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
        "FAIL V28" in r.stdout and "aaaaaaaaaaaa@gold.ds line 1" in r.stdout,
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
        "rows: one not in key order is made canonical; a line that is not a row is left as it is; a score with no rows stays empty",
        zl[1] == '{"_extra": {}, "a": 2, "b": 1, "item_id": "z2"}'
        and zl[2] == "not a json row"
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

    # ── the SQLite store ────────────────────────────────────────────────────────────────────────────────────────────
    sql = base / "sql"
    shutil.copytree(FIXTURE, sql / "data")
    r = evh(sql, "sqlite", "data-migrate", "--to", "sqlite")
    check(
        "setup: the fixture project moved into its database",
        r.returncode == 0 and "23 row(s)" in r.stdout,
        r.stdout + r.stderr[-300:],
    )
    r = evh(sql, "sqlite", "migrate", "--dry-run")
    check(
        "sqlite --dry-run: the same counts",
        r.returncode == 0 and counts(r.stdout) == COUNTS,
        r.stdout + r.stderr[-300:],
    )
    r = evh(sql, "sqlite", "migrate")
    check(
        "sqlite migrate: the same counts, backed up first, at format 7",
        r.returncode == 0
        and counts(r.stdout) == COUNTS
        and "backup:" in r.stdout
        and "brought the data to format 7" in r.stdout,
        r.stdout + r.stderr[-300:],
    )
    check(
        "sqlite migrate: a second run has nothing to do",
        evh(sql, "sqlite", "migrate").stdout.strip().endswith("nothing to do"),
    )
    r = evh(sql, "files", "data-migrate", "--to", "files")
    check("the migrated database moved back to files", r.returncode == 0, r.stdout + r.stderr[-300:])
    back = tree(sql / "data")
    check(
        "both stores: every file of the data, byte for byte, as the files store's migration left it",
        back == after,
        sorted(k for k in set(back) | set(after) if back.get(k) != after.get(k)),
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
