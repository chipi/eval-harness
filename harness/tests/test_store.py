#!/usr/bin/env python3
"""A project's data in files or in one database (RFC-025): `_store`, `evh data-migrate`, never both.

    python tests/test_store.py

The setting: files with no key, `store: sqlite` in config.yaml, EVAL_STORE winning over it, any other value refused.
`_store` on both stores: write, read, exists, a directory as the files it holds, glob, rglob, iterdir, stat, open for
reading, writing and appending, copy into a directory, copy a tree, replace, unlink, and rmtree, which in the
database removes a run's outputs and rows too (a run made again at the same path never reads the old one's). An
object that is not a path keeps its own methods. `data-migrate` to the database and back on a project with a run
(outputs, rows, a row checkpoint), a dataset, nested folders and binary bytes: every file byte-identical, nothing
under data/ on disk but the database in between, V23 saying so; refused while the store is not the target, while
data/ holds Python, while a run is in the layout before 0.8.0. Two writers and a reader at once. A release of a
project in its database: the same files layout, a hidden dataset's outputs left out and its rows cut to the call.
No module but the few named below does path I/O itself.
"""

import ast
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
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_STORE"):
    os.environ.pop(k, None)
from evaluation_harness import _common, _outputs, _store  # noqa: E402
from evaluation_harness import validate_tree as vt  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

data = proj / "data"
env = dict(os.environ, EVAL_BUILD_REF="test-store")


def evh(*args, store=None, extra=None):
    e = {k: v for k, v in env.items() if k != "EVAL_STORE"}
    if store:
        e["EVAL_STORE"] = store
    e.update(extra or {})
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=e, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


def use(store):
    os.environ["EVAL_STORE"] = store
    _outputs.reset()


def setting(value=None, config=None):
    cfg = proj / "config.yaml"
    if config is None:
        cfg.unlink(missing_ok=True)
    else:
        cfg.write_text(config)
    os.environ.pop("EVAL_STORE", None)
    if value is not None:
        os.environ["EVAL_STORE"] = value
    try:
        return _common.store()
    except SystemExit as e:
        return str(e)
    finally:
        os.environ.pop("EVAL_STORE", None)


def v23():
    vt.problems.clear()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        vt.v23_run_outputs()
    return list(vt.problems), out.getvalue()


def disk_files():
    return sorted(str(p.relative_to(data)) for p in data.rglob("*") if p.is_file()) if data.is_dir() else []


try:
    check("no key: the files store", setting() == "files")
    check("store: sqlite in config.yaml", setting(config="store: sqlite\n") == "sqlite")
    check("EVAL_STORE wins over the file", setting("files", config="store: sqlite\n") == "files")
    bad = setting("postgres")
    check("an unknown store in EVAL_STORE is refused", bad.startswith("ERROR (bad-argument)"), bad)
    bad = setting(config="store: duckdb\n")
    check("an unknown store in config.yaml is refused", bad.startswith("ERROR (invalid-file)"), bad)
    (proj / "config.yaml").unlink()

    # _store on both stores: the same answers.
    for store in ("files", "sqlite"):
        use(store)
        shutil.rmtree(data, ignore_errors=True)
        _store.close()
        data.mkdir()
        a = data / "x" / "a.txt"
        _store.mkdir(a.parent, parents=True, exist_ok=True)
        _store.write_text(a, "één\n")
        _store.mkdir(data / "x" / "y", parents=True, exist_ok=True)
        _store.write_bytes(data / "x" / "y" / "b.bin", bytes(range(256)))
        with _store.open_file(data / "x" / "c.log", "w") as fh:
            fh.write("one\n")
        with _store.open_file(data / "x" / "c.log", "a") as fh:
            fh.write("two\n")
        _store.copy_file(a, data / "x" / "y")
        _store.copy_tree(data / "x" / "y", data / "z")
        _store.replace(data / "z" / "a.txt", data / "z" / "moved.txt")
        listing = (
            _store.read_text(a),
            _store.read_bytes(data / "x" / "y" / "b.bin") == bytes(range(256)),
            _store.read_text(data / "x" / "c.log"),
            _store.exists(data / "x"),
            _store.is_dir(data / "x" / "y"),
            _store.is_file(data / "x" / "y"),
            sorted(p.name for p in _store.iterdir(data / "x")),
            sorted(str(p.relative_to(data)) for p in _store.glob(data, "*/*.txt")),
            sorted(str(p.relative_to(data)) for p in _store.rglob(data, "*.bin")),
            _store.stat(a).st_size,
            sorted(str(p.relative_to(data)) for p in _store.rglob(data / "z", "*")),
        )
        expect = (
            "één\n",
            True,
            "one\ntwo\n",
            True,
            True,
            False,
            ["a.txt", "c.log", "y"],
            ["x/a.txt", "z/moved.txt"],
            ["x/y/b.bin", "z/b.bin"],
            len("één\n".encode()),
            ["z/b.bin", "z/moved.txt"],
        )
        check(f"{store}: _store's reads, writes, listings and copies", listing == expect, listing)
        on_disk = disk_files()
        check(
            f"{store}: "
            + ("every file on disk" if store == "files" else "nothing under data/ on disk but the database"),
            (len(on_disk) == 6) if store == "files" else all(f.startswith(_store.DB) for f in on_disk),
            on_disk,
        )
        # A run deleted with its directory takes its outputs and rows; made again it starts empty.
        run = data / "runs" / "arm_v1_x"
        _store.mkdir(run, parents=True, exist_ok=True)
        _store.write_text(run / "metrics.json", "{}")
        _outputs.writer(run).add("i1", "old output")
        _outputs.write_rows(run, [{"item_id": "i1", "score": 1}])
        _store.rmtree(run)
        _store.mkdir(run, parents=True, exist_ok=True)
        _store.write_text(run / "run.json", "{}")
        check(
            f"{store}: rmtree of a run takes its outputs and rows; made again, it starts empty",
            _outputs.outputs(run) == {}
            and _outputs.rows_text(run) is None
            and not _store.is_file(run / "metrics.json"),
            (_outputs.outputs(run), _outputs.rows_text(run)),
        )
        missing = None
        try:
            _store.read_text(data / "nope.txt")
        except FileNotFoundError as e:
            missing = e
        check(f"{store}: a missing file raises FileNotFoundError", missing is not None)

        class Own:
            def read_text(self, encoding=None, errors=None):
                return "its own"

            def is_file(self):
                return True

        check(
            f"{store}: an object that is not a path keeps its own methods",
            _store.read_text(Own()) == "its own" and _store.is_file(Own()) is True,
        )

    # data-migrate there and back.
    use("files")
    shutil.rmtree(data, ignore_errors=True)
    _store.close()
    run = data / "runs" / "arm_v1_x"
    run.mkdir(parents=True)
    (run / "metrics.json").write_text(json.dumps({"run_id": run.name, "dataset_id": "ds"}))
    (run / "run.json").write_text(json.dumps({"config_id": "arm_v1"}))
    w = _outputs.writer(run)
    for i, t in (("i2", "two é\r\n"), ("i1", "")):
        w.add(i, t)
    _outputs.write_rows(run, [{"item_id": "i1", "s": 1.5}, {"item_id": "i2", "s": 0}])
    stopped = data / "runs" / "arm_v1_stopped"
    stopped.mkdir()
    (stopped / "run.json").write_text("{}")
    _outputs.append_partial(stopped, {"item_id": "i1", "s": 1})
    (data / "datasets").mkdir()
    (data / "datasets" / "ds.json").write_text(json.dumps({"dataset_id": "ds", "items": []}, indent=2))
    (data / "references" / "gold" / "ds").mkdir(parents=True)
    (data / "references" / "gold" / "ds" / "i1.txt").write_bytes("gold\r\nline\xa0".encode() + b"\x00\xff")
    before = {f: (data / f).read_bytes() for f in disk_files()}

    r = evh("data-migrate", "--to", "sqlite", store="files")
    check(
        "--to sqlite while the store is files is refused, nothing moved",
        r.returncode != 0 and "ERROR (not-allowed)" in r.stderr and disk_files() == sorted(before),
        r.stderr[-300:],
    )
    (data / "scorers").mkdir()
    (data / "scorers" / "mine.py").write_text("x = 1\n")
    r = evh("data-migrate", "--to", "sqlite", store="sqlite")
    check(
        "--to sqlite refuses while data/ holds Python, naming it",
        r.returncode != 0
        and "scorers/mine.py" in r.stderr
        and disk_files() == sorted([*before, "scorers/mine.py"]),
        r.stderr[-300:],
    )
    shutil.rmtree(data / "scorers")
    r = evh("data-migrate", "--to", "sqlite", "--dry-run", store="sqlite")
    check(
        "--to sqlite --dry-run counts and moves nothing",
        r.returncode == 0 and "would move" in r.stdout and disk_files() == sorted(before),
        (r.stdout + r.stderr)[-300:],
    )
    use("sqlite")
    problems, out = v23()
    check(
        "V23: files under data/ while the store is sqlite are named", problems and "--to sqlite" in out, out
    )

    r = evh("data-migrate", "--to", "sqlite", store="sqlite")
    use("sqlite")
    check(
        "--to sqlite: nothing under data/ on disk but the database; every file, output and row read back the same",
        r.returncode == 0
        and all(f.startswith(_store.DB) for f in disk_files())
        and _store.read_bytes(data / "references" / "gold" / "ds" / "i1.txt")
        == before["references/gold/ds/i1.txt"]
        and _outputs.outputs(run) == {"i2": "two é\r\n", "i1": ""}
        and _outputs.rows_text(run) == before["runs/arm_v1_x/predictions.jsonl"].decode()
        and _outputs.rows_text(stopped, partial=True)
        == before["runs/arm_v1_stopped/rows.partial.jsonl"].decode()
        and _store.is_file(run / "metrics.json"),
        ((r.stdout + r.stderr)[-300:], disk_files()),
    )
    problems, out = v23()
    check("V23 passes on the database", not problems, out)

    r = evh("data-migrate", "--to", "files", store="files")
    use("files")
    after = {f: (data / f).read_bytes() for f in disk_files()}
    check(
        "--to files: every file byte-identical, the database gone",
        r.returncode == 0 and after == before and not (data / _store.DB).exists(),
        ((r.stdout + r.stderr)[-300:], sorted(set(before) ^ set(after))),
    )

    old = data / "runs" / "arm_v1_old"
    (old / "outputs").mkdir(parents=True)
    (old / "metrics.json").write_text("{}")
    (old / "outputs" / "i1.txt").write_text("x")
    r = evh("data-migrate", "--to", "sqlite", store="sqlite")
    check(
        "--to sqlite refuses a run in the layout before 0.8.0 (evh run-migrate first)",
        r.returncode != 0 and "run-migrate" in r.stderr and (old / "outputs" / "i1.txt").is_file(),
        r.stderr[-300:],
    )
    shutil.rmtree(old)

    # Two processes writing their own runs at once while a third reads one of them: every output committed.
    r = evh("data-migrate", "--to", "sqlite", store="sqlite")
    use("sqlite")
    worker = proj / "worker.py"
    worker.write_text(
        "import sys, time\n"
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
    wenv = {**env, "EVAL_STORE": "sqlite"}
    c1, c2 = data / "runs" / "conc_1", data / "runs" / "conc_2"
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
    errs = [pr.communicate(timeout=300)[1].decode() for pr in procs]
    rout, rerr = reader.communicate(timeout=300)
    use("sqlite")
    check(
        "two writers at once and a reader: all 600 outputs committed, no error, the reader saw them arrive",
        all(pr.returncode == 0 for pr in procs)
        and reader.returncode == 0
        and _outputs.count(c1) == 300
        and _outputs.count(c2) == 300
        and 0 < int(rout.decode().strip() or 0) <= 300,
        (errs, rerr.decode()[-300:], rout),
    )

    # A release of a project in its database: the files layout, a hidden dataset's text out.
    from evaluation_harness._release import copy_data

    for name, ds, text in (("rel_h", "h", "HIDDEN-MARK-7781"), ("rel_s", "s", "SHOWN-MARK-2213")):
        d = data / "runs" / name
        _store.write_text(d / "metrics.json", json.dumps({"run_id": name, "dataset_id": ds}))
        _outputs.writer(d).add("x1", text)
        _outputs.write_rows(
            d, [{"item_id": "x1", "score": 0.25, "_meta": {"usage": {"t": 3}, "prompt": text}}]
        )
    _store.write_text(data / "datasets" / "h.json", json.dumps({"dataset_id": "h", "text": "hidden"}))
    _store.write_text(data / "datasets" / "s.json", json.dumps({"dataset_id": "s"}))
    rel = proj / ".release"
    copy_data(data, rel)
    blob = b"".join(p.read_bytes() for p in rel.rglob("*") if p.is_file())
    hid = [json.loads(x) for x in (rel / "runs" / "rel_h" / "predictions.jsonl").read_text().splitlines()]
    check(
        "release from the database: the files layout, the shown run's outputs, none of the hidden run's text",
        b"SHOWN-MARK-2213" in blob
        and b"HIDDEN-MARK-7781" not in blob
        and (rel / "runs" / "rel_s" / "outputs.jsonl").is_file()
        and not (rel / "runs" / "rel_h" / "outputs.jsonl").exists()
        and hid == [{"item_id": "x1", "score": 0.25, "_meta": {"usage": {"t": 3}}}]
        and not (rel / _store.DB).exists(),
        (hid, sorted(str(p.relative_to(rel)) for p in rel.rglob("*") if p.is_file())[:20]),
    )
finally:
    _outputs.reset()
    shutil.rmtree(proj, ignore_errors=True)

# No module does path I/O itself but these: everything else goes through _store, which keeps a path under data/
# in the project's store and any other path on the disk.
ALLOWED = {
    "_store.py": "the store",
    "_outputs.py": "its files store is the disk by definition (data-migrate reads the disk through it)",
    "data_migrate.py": "moves between the disk and the database",
    "run_migrate.py": "reads the layout before 0.8.0 on disk",
    "_common.py": "finds the project on disk (data/, .env, config.yaml) before any store exists",
    "stats.py": "standard library only; its p cache is outside data/",
    "skills_install.py": "copies the harness's own skill files, never data",
}
METHODS = {"read_text", "read_bytes", "write_text", "write_bytes", "is_file", "is_dir", "exists", "glob", "rglob",
           "iterdir", "unlink", "mkdir", "stat", "open"}  # fmt: skip
FUNCS = (
    {("shutil", f) for f in ("rmtree", "copy", "copy2", "copyfile", "copytree", "move")}
    | {("os", f) for f in ("replace", "rename", "remove", "unlink", "makedirs", "listdir", "walk", "scandir")}
    | {("os.path", f) for f in ("exists", "isfile", "isdir", "getmtime", "getsize")}
)


def dotted(n):
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute):
        d = dotted(n.value)
        return f"{d}.{n.attr}" if d else None
    return None


stray = []
for f in sorted(HERE.glob("*.py")):
    if f.name in ALLOWED:
        continue
    tree = ast.parse(f.read_text())
    mods = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {(a.asname or a.name).split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods |= {a.asname or a.name for a in n.names if a.name[:1].islower() or a.name.startswith("_")}
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        fn = n.func
        if isinstance(fn, ast.Name) and fn.id == "open":
            stray.append(f"{f.name}:{n.lineno} open()")
        elif isinstance(fn, ast.Attribute):
            recv = dotted(fn.value)
            if (recv, fn.attr) in FUNCS:
                stray.append(f"{f.name}:{n.lineno} {recv}.{fn.attr}")
            elif fn.attr in METHODS and recv != "_store" and not (recv and recv.split(".")[0] in mods):
                stray.append(f"{f.name}:{n.lineno} .{fn.attr}()")
check(
    "no module but the store's own does path I/O itself (everything else through _store)",
    not stray,
    stray[:15],
)
sys.exit(summary())
