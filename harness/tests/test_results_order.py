#!/usr/bin/env python3
"""The order a SQLite project's per-item tables are built in (RFC-033): by the run's time, then the key.

    python tests/test_results_order.py

`data-migrate --to sqlite` (what makes a release's database, and what a project moving into SQLite runs) writes each run's
outputs, each score set's rows and values, and so numbers the score sets and the metrics, in the order of the run's time
(run.json's `started_at`, else `created_at`, as an instant: a zone counts, a time with none is UTC), then the key; a run
with neither as an ISO time comes first, by its key. A run added since lands after every older one in each table, which is
what keeps a deploy's rsync of the database small. A score set's id is its place in that order (1, 2, ...); the metrics'
ids are the order their names are first met, the names of one score set sorted. The same data gives the same tables
whatever order its files were made in and wherever the project is; a score set added to an old run sits with that run when
the database is built again.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
base = Path(tempfile.mkdtemp(prefix="evh-order-"))
os.environ["EVAL_HOME"] = str(base)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_STORE"):
    os.environ.pop(k, None)
from evaluation_harness import _format, data_migrate  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

SCORES = ("aaaaaaaaaaaa", "bbbbbbbbbbbb")

#: (run id, the fields run.json holds besides its ids), written in this order or the reverse, which must not matter.
RUNS: list[tuple[str, dict[str, Any]]] = [
    ("a_late", {"started_at": "2026-03-01T00:00:00Z"}),
    ("b_tie", {"created_at": "2026-02-01T00:00:00Z"}),
    ("c_zone", {"created_at": "2026-02-01T02:00:00+02:00"}),  # the same instant as b_tie: the key decides
    ("d_naive", {"created_at": "2026-01-15T00:00:00"}),  # no zone: UTC
    (
        "e_both",
        {"created_at": "2026-04-01T00:00:00Z", "started_at": "2026-01-01T00:00:00Z"},
    ),  # started_at counts
    (
        "w_late_bad_start",
        {"started_at": "soon", "created_at": "2026-03-15T00:00:00Z"},
    ),  # a bad one falls to the next
    ("x_number", {"created_at": 12345}),  # not an ISO time: none
    ("y_bad", {"created_at": "yesterday"}),
    ("z_none", {}),
]
#: The order they come in: no time first (by key), then by instant (by key for a tie).
ORDER = ["x_number", "y_bad", "z_none", "e_both", "d_naive", "b_tie", "c_zone", "a_late", "w_late_bad_start"]


def build(root: Path, runs: list[tuple[str, dict[str, Any]]], extra: tuple[str, str] | None = None) -> Path:
    """A project of files in `root` (store: sqlite named, its data still files): every run with one output and two scores.
    `extra` is (run id, scorer): one more score set on that run."""
    root.mkdir(parents=True)
    (root / "config.yaml").write_text("store: sqlite\n")
    data = root / "data"
    data.mkdir(parents=True)
    _format.stamp(data=data)
    for rid, fields in runs:
        rd = data / "runs" / rid
        rd.mkdir(parents=True)
        (rd / "run.json").write_text(
            json.dumps({"run_id": rid, "system_id": "s_v1", "dataset_id": "ds", **fields}) + "\n"
        )
        (rd / "outputs.jsonl").write_text(
            json.dumps({"item_id": "i1", "text": rid, "sha256": hashlib.sha256(rid.encode()).hexdigest()})
            + "\n"
        )
        scorers = [*SCORES, *([extra[1]] if extra and extra[0] == rid else [])]
        for scorer in scorers:
            sd = rd / "scores" / f"{scorer}@gold.ds"
            sd.mkdir(parents=True)
            (sd / "metrics.json").write_text("{}\n")
            tag = "u" if scorer == SCORES[0] else "v"
            row = {"item_id": "i1", "common": 1, f"{tag}_{rid}": 2.5}
            (sd / "predictions.jsonl").write_text(json.dumps(row, sort_keys=True) + "\n")
    return data


def migrate(root: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR")}
    env.update(EVAL_HOME=str(root), EVAL_STORE="sqlite")
    return subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "cli.py"), "data-migrate", "--to", "sqlite"],
        cwd=root, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300, check=False,
    )  # fmt: skip


def tables(root: Path) -> dict[str, list[Any]]:
    """The per-item tables, cell for cell, each in the order it is stored in."""
    c = sqlite3.connect(root / "data" / "project.sqlite")
    try:
        return {
            "score_sets": c.execute("SELECT * FROM score_sets ORDER BY id").fetchall(),
            "metrics": c.execute("SELECT * FROM metrics ORDER BY id").fetchall(),
            "score_rows": c.execute("SELECT * FROM score_rows ORDER BY id").fetchall(),
            "score_values": c.execute("SELECT * FROM score_values ORDER BY 1, 2").fetchall(),
            "call_facts": c.execute("SELECT * FROM call_facts ORDER BY 1, 2").fetchall(),
            "outputs": c.execute("SELECT * FROM outputs ORDER BY rowid").fetchall(),
        }
    finally:
        c.close()


def runs_of(keys: list[str]) -> list[str]:
    """The run ids of score set or output keys, each once, in order."""
    out: list[str] = []
    for k in keys:
        r = k.split("/")[1]
        if r not in out:
            out.append(r)
    return out


try:
    # ── the time of a run ───────────────────────────────────────────────────────────────────────────────────────────
    t = data_migrate.run_time
    z = t('{"created_at": "2026-02-01T00:00:00Z"}')
    check(
        "a run's time: `Z` and an offset are the same instant, a time with no zone is UTC",
        z is not None
        and t('{"created_at": "2026-02-01T02:00:00+02:00"}') == z
        and t('{"created_at": "2026-02-01T00:00:00"}') == z
        and t(b'{"created_at": "2026-02-01T00:00:00Z"}') == z,
        z,
    )
    check(
        "a run's time: `started_at` before `created_at`, and `created_at` when `started_at` is no ISO time",
        t('{"started_at": "2026-01-01T00:00:00Z", "created_at": "2026-02-01T00:00:00Z"}')
        == t('{"started_at": "2026-01-01T00:00:00Z"}')
        != z
        and t('{"started_at": "soon", "created_at": "2026-02-01T00:00:00Z"}') == z
        and t('{"started_at": 5, "created_at": "2026-02-01T00:00:00Z"}') == z,
    )
    check(
        "a run's time: none for text that is no JSON object, or holds neither field as an ISO time",
        all(
            t(x) is None
            for x in (
                None,
                "",
                b"",
                "not json",
                "[]",
                "5",
                "null",
                "{}",
                '{"created_at": 5}',
                '{"created_at": "x"}',
            )
        ),
    )

    # ── the order the tables are built in ───────────────────────────────────────────────────────────────────────────
    one = base / "one"
    build(one, RUNS)
    r = migrate(one)
    check(
        "data-migrate --to sqlite moves a project of nine runs", r.returncode == 0, r.stdout + r.stderr[-400:]
    )
    got = tables(one)
    keys = [k for _i, k in got["score_sets"]]
    check(
        "score sets in the order of their run's time, then the key: no time first, `started_at` before `created_at`, "
        "a tie by key, a bad `started_at` falling to `created_at`; a run's own sets by key",
        runs_of(keys) == ORDER and keys == [f"runs/{r}/scores/{s}@gold.ds" for r in ORDER for s in SCORES],
        keys,
    )
    check(
        "a score set's id is its place in that order, from 1",
        [i for i, _k in got["score_sets"]] == list(range(1, 2 * len(RUNS) + 1)),
        [i for i, _k in got["score_sets"]],
    )
    check(
        "the outputs fill their table in the same order (rowid)",
        [r[0] for r in got["outputs"]] == [f"runs/{r}" for r in ORDER],
        [r[0] for r in got["outputs"]],
    )
    check(
        "the metrics are numbered as first met in that order, a score set's new names sorted",
        [n for _i, n in got["metrics"]] == ["common", *[f"{tag}_{r}" for r in ORDER for tag in ("u", "v")]],
        [n for _i, n in got["metrics"]],
    )
    check(
        "the rows follow their score set: ids in the set's range, in the order the sets are",
        [r[0] for r in got["score_rows"]] == [(i << 20) for i in range(1, 2 * len(RUNS) + 1)],
        [r[0] for r in got["score_rows"]][:4],
    )

    # ── the same data, the same tables ──────────────────────────────────────────────────────────────────────────────
    two = base / "elsewhere" / "two"
    build(two, list(reversed(RUNS)))
    r = migrate(two)
    check(
        "the same runs made in the other order, in another place",
        r.returncode == 0,
        r.stdout + r.stderr[-400:],
    )
    check(
        "the same data gives the same tables, cell for cell, whatever order its files were made in",
        tables(two) == got,
        [k for k, v in tables(two).items() if v != got[k]],
    )

    # ── a score set added to an old run ─────────────────────────────────────────────────────────────────────────────
    three = base / "three"
    build(three, RUNS, extra=("d_naive", "cccccccccccc"))
    r = migrate(three)
    keys3 = [k for _i, k in tables(three)["score_sets"]]
    want3 = [f"runs/{r}/scores/{s}@gold.ds" for r in ORDER for s in SCORES]
    at = want3.index("runs/d_naive/scores/bbbbbbbbbbbb@gold.ds") + 1
    want3.insert(at, "runs/d_naive/scores/cccccccccccc@gold.ds")
    check(
        "a score set added to an old run sits with that run when the database is built again (its later neighbours' ids move up)",
        r.returncode == 0 and keys3 == want3,
        keys3,
    )
finally:
    shutil.rmtree(base, ignore_errors=True)
sys.exit(summary())
