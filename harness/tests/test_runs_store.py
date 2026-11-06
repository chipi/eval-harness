#!/usr/bin/env python3
"""The project's runs store (RFC-025): files by default, sqlite by one key, moved either way by run-migrate --to.
Outputs and rows (predictions.jsonl, its checkpoint) both.

    python tests/test_runs_store.py

The setting: files with no key, `runs.store: sqlite` in config.yaml, EVAL_RUNS_STORE winning over it, any other value
refused. The move: refused while the project's store is not the target; files to sqlite and back, every output, its
order, its sha256 and V5's signature equal, nothing left behind; a move a crash stopped after the write is finished
by the next; a run in both stores with different outputs is refused, nothing changed. V23 names outputs left in the
store the project does not use. A release keeps a hidden dataset's rows cut to the call. One item's row across runs
reads the same from either store. Two processes writing at once while a third reads: every output committed. No
module but _outputs (and the migration) builds a predictions.jsonl path.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
proj = Path(tempfile.mkdtemp(prefix="evh-store-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_RUNS_STORE"):
    os.environ.pop(k, None)
from evaluation_harness import _common, _outputs  # noqa: E402
from evaluation_harness import validate_tree as vt  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

env = dict(os.environ, EVAL_BUILD_REF="test-runs-store")


def evh(*args, store=None):
    e = dict(env)
    e.pop("EVAL_RUNS_STORE", None)
    if store:
        e["EVAL_RUNS_STORE"] = store
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=e, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


def setting(value=None, config=None):
    """runs_store() for this EVAL_RUNS_STORE and config.yaml; the refusal's text when it refuses."""
    cfg = proj / "config.yaml"
    if config is None:
        cfg.unlink(missing_ok=True)
    else:
        cfg.write_text(config)
    if value is None:
        os.environ.pop("EVAL_RUNS_STORE", None)
    else:
        os.environ["EVAL_RUNS_STORE"] = value
    try:
        return _common.runs_store()
    except SystemExit as e:
        return str(e)
    finally:
        os.environ.pop("EVAL_RUNS_STORE", None)


def use(store):
    os.environ["EVAL_RUNS_STORE"] = store
    _outputs.reset()


def v23():
    vt.problems.clear()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        vt.v23_run_outputs()
    return list(vt.problems), out.getvalue()


try:
    check("no key: the files store", setting() == "files")
    check("runs.store: sqlite in config.yaml", setting(config="runs:\n  store: sqlite\n") == "sqlite")
    check(
        "EVAL_RUNS_STORE wins over the file", setting("files", config="runs:\n  store: sqlite\n") == "files"
    )
    bad = setting("postgres")
    check("an unknown store in EVAL_RUNS_STORE is refused", bad.startswith("ERROR (bad-argument)"), bad)
    bad = setting(config="runs:\n  store: duckdb\n")
    check("an unknown store in config.yaml is refused", bad.startswith("ERROR (invalid-file)"), bad)
    (proj / "config.yaml").unlink()

    # Three runs in the files store: two measured, one derived reading the first's outputs.
    use("files")
    runs = proj / "data" / "runs"
    a, b = runs / "arm_a_v1_x", runs / "arm_b_v1_x"
    texts_a = {f"i{n}": f"answer {n} é\n" * (n % 3 + 1) for n in range(30, 0, -1)}
    texts_b = {"j1": "", "j2": "two"}
    for d, texts in ((a, texts_a), (b, texts_b)):
        w = _outputs.writer(d)
        for item, t in texts.items():
            w.add(item, t)
        (d / "metrics.json").write_text(json.dumps({"run_id": d.name}))
    j = proj / "data" / "runs-judged" / "judge1" / a.name
    j.mkdir(parents=True)
    (j / "metrics.json").write_text(
        json.dumps({"derived": {"kind": "judge", "from": a.name, "from_dir": "runs/" + a.name}})
    )
    # Rows: a finished run's, a derived run's (rows only), a stopped run's checkpoint (no predictions.jsonl yet).
    _outputs.write_rows(
        a, [{"item_id": i, "score": n / 7, "_meta": {"usage": {"t": n}}} for n, i in enumerate(texts_a)]
    )
    _outputs.write_rows(j, [{"item_id": "i1", "judge": 1.0}, {"item_id": "i2", "judge": 0.5}])
    _outputs.append_partial(b, {"item_id": "j1", "score": 1})
    _outputs.append_partial(b, {"item_id": "j2", "score": 0})
    before = {d: (_outputs.lines(d), _outputs.signature(d)) for d in (a, b)}
    sig_j = _outputs.signature(j)
    rows_before = {(d, pt): _outputs.rows_text(d, pt) for d in (a, b, j) for pt in (False, True)}
    bytes_before = {
        f: f.read_bytes() for f in (a / "predictions.jsonl", j / "predictions.jsonl", b / _outputs.ROWS)
    }
    across_files = _outputs.item_across([a, j, b], "i2")

    r = evh("run-migrate", "--to", "sqlite", store="files")
    check(
        "--to sqlite while the project's store is files is refused, nothing moved",
        r.returncode != 0 and "ERROR (not-allowed)" in r.stderr and (a / _outputs.FILE).is_file(),
        r.stderr[-300:],
    )
    r = evh("run-migrate", "--to", "sqlite", "--dry-run", store="sqlite")
    check(
        "--to sqlite --dry-run counts and moves nothing",
        r.returncode == 0
        and "3 run(s), 32 output(s), 34 row(s) would move" in r.stdout
        and (a / _outputs.FILE).is_file(),
        (r.stdout + r.stderr)[-300:],
    )
    use("sqlite")
    problems, out = v23()
    check(
        "V23 names an outputs file left while the store is sqlite",
        len(problems) == 1 and "--to sqlite" in out,
        out,
    )

    r = evh("run-migrate", "--to", "sqlite", store="sqlite")
    use("sqlite")
    check(
        "--to sqlite: every output, its order and sha256, and V5's signature as before; no outputs file left",
        r.returncode == 0
        and all(_outputs.lines(d) == before[d][0] and _outputs.signature(d) == before[d][1] for d in (a, b))
        and _outputs.signature(j) == sig_j
        and not any((d / _outputs.FILE).exists() for d in (a, b))
        and (proj / "data" / _outputs.DB).is_file(),
        (r.stdout + r.stderr)[-300:],
    )
    check(
        "--to sqlite: every run's rows and checkpoint exactly as written; no predictions.jsonl or checkpoint file left",
        all(_outputs.rows_text(d, pt) == t for (d, pt), t in rows_before.items())
        and not any(f.exists() for f in bytes_before),
        {f"{d.name}:{pt}": _outputs.rows_text(d, pt) == t for (d, pt), t in rows_before.items()},
    )
    check(
        "one item's row across runs: the same from either store",
        _outputs.item_across([a, j, b], "i2") == across_files and set(across_files) == {a, j},
        (across_files, _outputs.item_across([a, j, b], "i2")),
    )
    problems, out = v23()
    check("V23 passes on the sqlite store", not problems, out)
    use("files")
    problems, out = v23()
    check(
        "V23 names runs.sqlite's outputs while the store is files",
        len(problems) == 1 and "--to files" in out,
        out,
    )

    r = evh("run-migrate", "--to", "files", store="files")
    use("files")
    check(
        "--to files: back in each run's outputs.jsonl, equal, the database emptied",
        r.returncode == 0
        and all(_outputs.lines(d) == before[d][0] and _outputs.signature(d) == before[d][1] for d in (a, b))
        and _outputs.db_runs(proj / "data" / _outputs.DB) == []
        and _outputs.db_runs(proj / "data" / _outputs.DB, "rows") == []
        and all(f.read_bytes() == v for f, v in bytes_before.items()),
        (r.stdout + r.stderr)[-300:],
    )

    # A move a crash stopped after writing the target: the run is in both stores; the next --to finishes it.
    sq = _outputs.store_named("sqlite")
    sq.write_all(a, texts_a, list(texts_a))
    _outputs.reset()
    r = evh("run-migrate", "--to", "sqlite", store="sqlite")
    use("sqlite")
    check(
        "a stopped move is finished by the next: written once, the old copy deleted",
        r.returncode == 0
        and "(1 a stopped move had already written)" in r.stdout
        and not (a / _outputs.FILE).exists()
        and _outputs.lines(a) == before[a][0],
        (r.stdout + r.stderr)[-300:],
    )
    # A run in both stores with different outputs: refused, neither copy touched.
    _outputs.store_named("files").write_all(a, {**texts_a, "i1": "different"}, list(texts_a))
    _outputs.reset()
    r = evh("run-migrate", "--to", "sqlite", store="sqlite")
    use("sqlite")
    check(
        "a run in both stores with different outputs is refused; both copies kept",
        r.returncode != 0
        and "ERROR (would-overwrite)" in r.stderr
        and (a / _outputs.FILE).is_file()
        and _outputs.lines(a) == before[a][0],
        r.stderr[-300:],
    )
    (a / _outputs.FILE).unlink()

    # A release of a sqlite project: refused while git does not track runs.sqlite; then a copy without the hidden
    # dataset's runs, their text in none of its bytes.
    from evaluation_harness._release import copy_data

    data = proj / "data"
    (data / "datasets").mkdir(parents=True, exist_ok=True)
    (data / "datasets" / "h.json").write_text(json.dumps({"dataset_id": "h", "text": "hidden"}))
    (data / "datasets" / "s.json").write_text(json.dumps({"dataset_id": "s"}))
    for name, ds, text in (("rel_h", "h", "HIDDEN-MARK-7781"), ("rel_s", "s", "SHOWN-MARK-2213")):
        d = runs / name
        _outputs.writer(d).add("x1", text)
        _outputs.write_rows(
            d, [{"item_id": "x1", "score": 0.25, "_meta": {"usage": {"t": 3}, "prompt": text}}]
        )
        (d / "metrics.json").write_text(json.dumps({"run_id": name, "dataset_id": ds}))
    _outputs.reset()  # the writer's connection closed, so git sees the whole database
    git = ["git", "-C", str(proj), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "data/runs", "data/runs-judged", "data/datasets"], check=True)
    subprocess.run([*git, "commit", "-qm", "runs"], check=True)
    try:
        copy_data(data, proj / ".release1")
        refused = ""
    except SystemExit as exc:
        refused = str(exc)
    check("release: a runs.sqlite git does not track is refused", "runs.sqlite holds" in refused, refused)
    subprocess.run([*git, "add", "data/runs.sqlite"], check=True)
    rel = proj / ".release2"
    copy_data(data, rel)
    blob = (rel / _outputs.DB).read_bytes() if (rel / _outputs.DB).is_file() else b""
    check(
        "release: runs.sqlite copied with the shown run's outputs, none of the hidden one's bytes, one file",
        b"SHOWN-MARK-2213" in blob
        and b"HIDDEN-MARK-7781" not in blob
        and _outputs.db_runs(rel / _outputs.DB)
        == sorted(k for k in _outputs.db_runs(data / _outputs.DB) if k != "runs/rel_h")
        and not list(rel.glob(_outputs.DB + "-*")),
        (_outputs.db_runs(rel / _outputs.DB), sorted(p.name for p in rel.iterdir())),
    )
    import sqlite3

    con = sqlite3.connect(str(rel / _outputs.DB))
    hid = [json.loads(x) for (x,) in con.execute("SELECT row FROM rows WHERE run = 'runs/rel_h' AND n > 0")]
    con.close()
    check(
        "release: the hidden run's rows stay, cut to the call (its score and usage, no prompt)",
        hid == [{"item_id": "x1", "score": 0.25, "_meta": {"usage": {"t": 3}}}],
        hid,
    )

    # Where a run's data lives depends only on where the run is, never on which project's process asks: a run in
    # another project's runs folder is in THAT project's runs.sqlite (the stray-database bug of 2026-11-06: test runs
    # in temporary folders landed in this repository's data/runs.sqlite); a run under no runs* folder keeps its files.
    use("sqlite")
    far = proj / "elsewhere" / "runs" / "far_v1_x"
    _outputs.writer(far).add("f1", "far away")
    _outputs.write_rows(far, [{"item_id": "f1", "score": 1}])
    keys = _outputs.db_runs(data / _outputs.DB) + _outputs.db_runs(data / _outputs.DB, "rows")
    far_db = proj / "elsewhere" / _outputs.DB
    check(
        "sqlite store: a run in another runs folder is in that folder's database, never the project's",
        not (far / _outputs.FILE).exists()
        and _outputs.output(far, "f1") == "far away"
        and _outputs.db_runs(far_db) == ["runs/far_v1_x"]
        and not any("far_v1_x" in k for k in keys),
        (keys, _outputs.db_runs(far_db)),
    )
    loose = proj / "loose" / "lone_v1_x"
    _outputs.writer(loose).add("l1", "alone")
    _outputs.write_rows(loose, [{"item_id": "l1", "score": 1}])
    check(
        "sqlite store: a run under no runs* folder keeps its files",
        (loose / _outputs.FILE).is_file()
        and (loose / _outputs.PREDICTIONS).is_file()
        and _outputs.output(loose, "l1") == "alone",
    )
    _outputs.reset()
    env["EVAL_RUNS_DIR"] = str(loose.parent)
    r = evh("run-migrate", "--to", "sqlite", store="sqlite")
    env.pop("EVAL_RUNS_DIR")
    check(
        "--to sqlite leaves a run under no runs* folder in its files (none deleted) and says so",
        r.returncode == 0
        and "1 run(s) under no runs* folder keep their files" in r.stdout
        and (loose / _outputs.FILE).read_text().count("alone") == 1
        and (loose / _outputs.PREDICTIONS).is_file(),
        (r.stdout + r.stderr)[-300:],
    )

    # Two processes writing their own runs at once while a third reads one of them: every output committed.
    worker = proj / "worker.py"
    worker.write_text(
        "import os, sys, time\n"
        f"sys.path.insert(0, {str(HARNESS)!r})\n"
        "from pathlib import Path\n"
        "from evaluation_harness import _outputs\n"
        "d, n, mode = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]\n"
        "if mode == 'write':\n"
        "    w = _outputs.writer(d)\n"
        "    for i in range(n):\n"
        "        w.add(f'c{i:04d}', f'text {i} ' * 20)\n"
        "else:\n"
        "    seen = 0\n"
        "    for _ in range(400):\n"
        "        seen = max(seen, _outputs.count(d))\n"
        "        time.sleep(0.002)\n"
        "    print(seen)\n"
    )
    wenv = dict(env, EVAL_RUNS_STORE="sqlite")
    c1, c2 = runs / "conc_1", runs / "conc_2"
    procs = [
        subprocess.Popen(
            [sys.executable, str(worker), str(c), "300", "write"], env=wenv, stderr=subprocess.PIPE
        )
        for c in (c1, c2)
    ]
    reader = subprocess.Popen(
        [sys.executable, str(worker), str(c1), "0", "read"],
        env=wenv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    errs = [p.communicate(timeout=300)[1].decode() for p in procs]
    rout, rerr = reader.communicate(timeout=300)
    use("sqlite")
    check(
        "two writers at once and a reader: all 600 outputs committed, no error, the reader saw them arrive",
        all(p.returncode == 0 for p in procs)
        and reader.returncode == 0
        and _outputs.count(c1) == 300
        and _outputs.count(c2) == 300
        and 0 < int(rout.decode().strip() or 0) <= 300,
        (errs, rerr.decode()[-300:], rout),
    )
finally:
    _outputs.reset()
    shutil.rmtree(proj, ignore_errors=True)

# No module but _outputs builds a predictions.jsonl path (RFC-025: one reader and writer for rows); the migration
# reads the old layout's beside its outputs/ folder.
import re  # noqa: E402

pat = re.compile(r'/ "predictions\.jsonl"|"predictions\.jsonl"\s*\)|\(\s*"predictions\.jsonl"')
stray = [
    f"{f.name}:{n}"
    for f in sorted(HERE.glob("*.py"))
    if f.name not in ("_outputs.py", "run_migrate.py")
    for n, line in enumerate(f.read_text().splitlines(), 1)
    if pat.search(line) and not line.lstrip().startswith("#")
]
check("no module but _outputs.py (and the migration) builds a predictions.jsonl path", not stray, stray)
sys.exit(summary())
