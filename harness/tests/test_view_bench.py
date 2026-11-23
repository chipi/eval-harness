#!/usr/bin/env python3
"""tools/view_bench.py: what a view costs in both stores (RFC-032 step 9).

    python tests/test_view_bench.py

On a throwaway project `evh init` makes: the benchmark copies its data/ into a scratch directory twice (a files copy and
a SQLite copy made by `evh data-migrate`, whose data/ then holds the database and no files), runs each named view in a
process of its own through the real `evh` entry point, twice per view (round 2 after round 1), and prints a table per
store; `--json` gives the rows. Each row says what a cold and a warm call cost and whether the two answers are byte
for byte the same. The copies are kept while the source's data/ is what they were made from, made again when it
changed or `--rebuild` says so; a view that fails is a row with its exit code, and the run exits 1.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
TOOL = HARNESS / "tools" / "view_bench.py"
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _tmp
import _tmp  # noqa: E402

tmp = Path(_tmp.mkdtemp(prefix="evh-bench-"))
proj, scratch = tmp / "project", tmp / "scratch"
proj.mkdir()
env = {
    k: v
    for k, v in os.environ.items()
    if k not in ("EVAL_STORE", "EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVH_P_CACHE")
}
env.update(EVAL_HOME=str(proj), EVAL_BUILD_REF="test-view-bench")


def run(*args: str, home: Path | None = None) -> subprocess.CompletedProcess:
    e = dict(env)
    if home:
        e["EVAL_HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(TOOL), "--project", str(proj), "--scratch", str(scratch), *args],
        cwd=tmp, env=e, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600, encoding="utf-8",
    )  # fmt: skip


init = subprocess.run(
    [sys.executable, str(HARNESS / "scripts" / "cli.py"), "init", "--store", "files"], cwd=proj, env=env, capture_output=True, text=True,
    stdin=subprocess.DEVNULL, timeout=300, encoding="utf-8",
)  # fmt: skip
check(
    "setup: a project", init.returncode == 0 and (proj / "data").is_dir(), (init.stdout + init.stderr)[-300:]
)

r = run("--views", "goal-list;dataset-list", "--rounds", "2", "--json")
rows = json.loads(r.stdout) if r.returncode == 0 else []
check("the benchmark runs and exits 0", r.returncode == 0 and bool(rows), (r.stdout + r.stderr)[-400:])
check(
    "one row per store, view and round: 2 stores x 2 views x 2 rounds",
    sorted((x["store"], x["view"], x["round"]) for x in rows)
    == sorted((s, v, n) for s in ("files", "sqlite") for v in ("goal-list", "dataset-list") for n in (1, 2)),
    [(x["store"], x["view"], x["round"]) for x in rows],
)
check(
    "each row has what a cold and a warm call cost, the process's wall time and its peak memory",
    all(
        {"s", "cpu_s", "rc", "bytes", "sha"} <= set(x["cold"])
        and x["warm"]["s"] >= 0
        and x["process_s"] > 0
        and x["peak_rss_mb"] > 0
        for x in rows
    ),
)
check("every view exited 0, cold and warm", all(x["cold"]["rc"] == 0 and x["warm"]["rc"] == 0 for x in rows))
check(
    "the cold and the warm answer are the same bytes",
    all(x["same"] for x in rows),
    [x for x in rows if not x["same"]][:1],
)
check(
    "and the two stores answered the same bytes",
    len({(x["view"], x["cold"]["sha"]) for x in rows}) == 2,
    {(x["view"], x["store"], x["cold"]["sha"]) for x in rows},
)
check(
    "the SQLite copy is the database: data/project.sqlite and no files beside it; the files copy has the files",
    (scratch / "sqlite" / "data" / "project.sqlite").is_file()
    and not [
        p
        for p in (scratch / "sqlite" / "data").rglob("*")
        if p.is_file() and not p.name.startswith("project.sqlite")
    ]
    and (scratch / "files" / "data").is_dir()
    and not (scratch / "files" / "data" / "project.sqlite").exists(),
)
check(
    "the sqlite copy's config says store: sqlite",
    "store: sqlite" in (scratch / "sqlite" / "config.yaml").read_text(encoding="utf-8"),
)

# the copies are kept while the source is what they were made from, made again when it changed
marker = scratch / "sqlite.stamp"
was = (marker.stat().st_mtime_ns, (scratch / "sqlite" / "data" / "project.sqlite").stat().st_ino)
time.sleep(0.05)
r = run("--views", "goal-list", "--rounds", "1", "--stores", "sqlite", "--json")
now = (marker.stat().st_mtime_ns, (scratch / "sqlite" / "data" / "project.sqlite").stat().st_ino)
check("a second run reuses the copies", r.returncode == 0 and now == was, (was, now))
(proj / "data" / "a_new_file.txt").write_text("the source changed", encoding="utf-8")
r = run("--views", "goal-list", "--rounds", "1", "--stores", "sqlite", "--json")
check(
    "the source's data/ changed: the copy is made again (and holds the new file)",
    r.returncode == 0 and marker.stat().st_mtime_ns != was[0],
    (r.stdout + r.stderr)[-300:],
)
r = run("--views", "goal-list", "--rounds", "1", "--rebuild", "--json")
check("--rebuild makes them again", r.returncode == 0 and marker.stat().st_mtime_ns > was[0])

# the table: one per store, the columns the evidence needs
r = run("--views", "goal-list", "--rounds", "1")
head = [ln for ln in r.stdout.splitlines() if ln.startswith("round")]
check(
    "the table: a section per store, with the view, cold s, cold CPU s, warm s, process s and peak memory",
    r.stdout.count("== files ==") == 1
    and r.stdout.count("== sqlite ==") == 1
    and len(head) == 2
    and all(c in head[0] for c in ("view", "cold s", "cold CPU s", "warm s", "process s", "RSS MB")),
    r.stdout[-400:],
)

# a view that fails is a row, and the run says so
r = run("--views", "goal-show no_such_goal", "--rounds", "1", "--stores", "files", "--json")
bad = json.loads(r.stdout) if r.stdout.strip().startswith("[") else []
check(
    "a view that is refused: its exit code is in the row and the run exits 1",
    r.returncode == 1 and bad and bad[0]["cold"]["rc"] != 0,
    (r.returncode, r.stdout[-200:]),
)

sys.exit(summary())
