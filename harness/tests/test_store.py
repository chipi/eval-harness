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
import fnmatch
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
    _outputs.reset()  # the setting is kept for the process: read again
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
        # read first, as a running catalog-serve has: what it keeps must go with the run (advisor review,
        # 2026-11-06: the same process kept answering with the deleted run's outputs and rows)
        was = (_outputs.outputs(run), _outputs.rows_text(run))
        _store.rmtree(run)
        _store.mkdir(run, parents=True, exist_ok=True)
        _store.write_text(run / "run.json", "{}")
        check(
            f"{store}: rmtree of a run read before takes its outputs and rows, in this process too; made again, it starts empty",
            was[0] == {"i1": "old output"}
            and was[1] is not None
            and _outputs.outputs(run) == {}
            and _outputs.rows_text(run) is None
            and not _store.is_file(run / "metrics.json"),
            (was, _outputs.outputs(run), _outputs.rows_text(run)),
        )
        if store == "sqlite":
            # A COMMIT that fails (a full disk): the shared connection is not left in a transaction that every later
            # write in the process would join and never commit (advisor review, 2026-11-06).
            import sqlite3

            real = _store.connect()
            assert real is not None

            class FailsCommitOnce:
                failed = False
                inner = real  # bound now: the loop moves on

                def execute(self, sql, *a):
                    if sql == "COMMIT" and not FailsCommitOnce.failed:
                        FailsCommitOnce.failed = True
                        raise sqlite3.OperationalError("database or disk is full")
                    return self.inner.execute(sql, *a)

                def __getattr__(self, name):
                    return getattr(self.inner, name)

            key = next(k for k, v in _store._CONN.items() if v is real)
            _store.write_text(data / "gone" / "a.txt", "a")
            _store._CONN[key] = FailsCommitOnce()  # type: ignore[assignment]
            try:
                _store.rmtree(data / "gone")
                raised = False
            except sqlite3.OperationalError:
                raised = True
            finally:
                _store._CONN[key] = real
            left_open = real.in_transaction
            _store.write_text(data / "after.txt", "kept")
            other = sqlite3.connect(str(data / _store.DB))
            seen = other.execute("SELECT data FROM files WHERE path = 'after.txt'").fetchone()
            other.close()
            check(
                "sqlite: a COMMIT that fails rolls back; the connection is not left in a transaction, later writes commit",
                raised and not left_open and seen is not None and bytes(seen[0]) == b"kept",
                (raised, left_open, seen),
            )
            _store.unlink(data / "after.txt")
            _store.rmtree(data / "gone", ignore_errors=True)
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

    # A directory is a key prefix: listed, found and deleted by a range on the primary key, which the index serves
    # (a LIKE pattern scanned the whole table: 11.6 ms against 0.045 ms on disk for one glob, architecture review
    # 2026-11-06), and only the keys under it, whatever the name holds (_ and % are LIKE's wildcards; . and 0 sort
    # either side of /).
    use("sqlite")
    for k in ("p/a/s", "p/a_b/x", "p/aXb/y", "p/a%b/z", "p/a.b/q", "p/a0/r"):
        _store.write_text(data / k, k)
    conn = _store.connect()
    assert conn is not None
    seen_sql: list[str] = []
    conn.set_trace_callback(seen_sql.append)
    try:
        listed = (
            _store.is_dir(data / "p" / "a"),
            _store.is_dir(data / "p" / "a_"),
            sorted(x.name for x in _store.iterdir(data / "p" / "a")),
            sorted(x.name for x in _store.iterdir(data / "p" / "a_b")),
            sorted(str(x.relative_to(data)) for x in _store.glob(data / "p", "a*/*")),
        )
        _store.rmtree(data / "p" / "a")
        left = sorted(str(x.relative_to(data)) for x in _store.rglob(data / "p", "*") if _store.is_file(x))
    finally:
        conn.set_trace_callback(None)
    check(
        "sqlite: a directory is exactly the keys under it: _ and % are not wildcards, a.b and a0 are other folders",
        listed == (True, False, ["s"], ["x"], ["p/a%b/z", "p/a.b/q", "p/a/s", "p/a0/r", "p/aXb/y", "p/a_b/x"])
        and left == ["p/a%b/z", "p/a.b/q", "p/a0/r", "p/aXb/y", "p/a_b/x"],
        (listed, left),
    )
    under = [q for q in seen_sql if " path >" in q or " run >" in q or "LIKE" in q]
    plans = {q: " ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + q)) for q in under}
    check(
        "sqlite: every prefix query is a SEARCH on the index, none a LIKE or a SCAN of the table",
        under and all("LIKE" not in q for q in under) and all("SCAN" not in v for v in plans.values()),
        plans or seen_sql[:6],
    )
    _store.rmtree(data / "p", ignore_errors=True)

    # A path relative to a setting climbs out through a folder that is only a key in the database (a config's
    # `adapter: ../../bonus_adapter.py`): found on disk all the same (the store matrix, 2026-11-08: "adapter not found").
    (proj / "beside.py").write_text("x = 1\n")
    via = data / "configs" / ".." / ".." / "beside.py"
    check(
        "sqlite: a file outside data/ reached through a folder in the database (data/configs/../../x.py) is found",
        _store.is_file(via)
        and _store.exists(via)
        and _store.read_text(via) == "x = 1\n"
        and _store.stat(via).st_size == 6,
        (_store.is_file(via), (data / "configs").exists()),
    )
    (proj / "beside.py").unlink()

    # What the database cannot do is refused out loud, never done half (architecture review, 2026-11-06).
    refused: list[str | None] = []
    for mode in ("r+", "w+", "x", "rb+"):
        try:
            _store.open_file(data / "x.txt", mode).close()
            refused.append(None)
        except Exception as e:  # noqa: BLE001 - the check reports whatever was raised
            refused.append(f"{type(e).__name__}: {e}")
    check(
        "sqlite: open in r+, w+, x refused (a read-only copy lost every write before)",
        all(x and x.startswith("ValueError") and "the project's database" in x for x in refused),
        refused,
    )
    run = data / "runs" / "arm_v9_y"
    _store.write_text(run / "metrics.json", "{}")
    _outputs.writer(run).add("i1", "kept")
    try:
        _store.copy_tree(run, data / "runs" / "arm_v9_copy")
        copied = None
    except Exception as e:  # noqa: BLE001
        copied = f"{type(e).__name__}: {e}"
    try:
        _store.replace(run, data / "runs" / "arm_v9_moved")
        moved = None
    except Exception as e:  # noqa: BLE001
        moved = f"{type(e).__name__}: {e}"
    check(
        "sqlite: a run is not copied or moved without its outputs and rows: refused, and nothing written",
        copied
        and copied.startswith("ValueError")
        and "outputs" in copied
        and moved
        and moved.startswith("ValueError")
        and not _store.exists(data / "runs" / "arm_v9_copy")
        and not _store.exists(data / "runs" / "arm_v9_moved"),
        (copied, moved),
    )
    _store.rmtree(run)

    # A label set written in the database: it was built in a folder made on disk under data/, which does not exist
    # there (advisor review, 2026-11-06: FileNotFoundError on every label-import in SQLite mode).
    from evaluation_harness import _label_sets

    use("sqlite")
    _store.write_text(
        data / "datasets" / "lbl.json",
        json.dumps({"dataset_id": "lbl", "items": [{"item_id": "i1", "input": "x"}]}),
    )
    try:
        _label_sets.write_set("lbl", "s1", {"i1": "yes"}, {"kind": sorted(_label_sets.SOURCES)[0]})
        said = ""
    except (SystemExit, OSError) as exc:
        said = f"{type(exc).__name__}: {exc}"
    out = _label_sets.set_dir("lbl", "s1")
    staged = _common.ROOT / ".build" / "staging"
    check(
        "sqlite: a label set is written into the database, listed, and nothing of it left on disk",
        not said
        and _store.is_file(out / "labels.json")
        and _store.read_text(out / "i1.txt") == "yes\n"
        and "s1" in [x.get("set") for x in _label_sets.sets()]
        and not _store.stray_files()
        and not (staged.is_dir() and any(staged.iterdir())),
        said or _store.stray_files()[:3],
    )
    _store.rmtree(data / "labels", ignore_errors=True)
    _store.unlink(data / "datasets" / "lbl.json")

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
    # A reference has a manifest (V16, ADR-0022); with no `redistributed: false` in it, a release publishes its texts.
    (data / "references" / "gold" / "ds" / "manifest.json").write_text(
        json.dumps({"dataset_id": "ds"}) + "\n"
    )
    before = {f: (data / f).read_bytes() for f in disk_files()}
    # a file's time goes with it, both ways (advisor review, 2026-11-06: every file showed the migration's)
    old_ns = 1_600_000_000 * 10**9
    os.utime(data / "datasets" / "ds.json", ns=(old_ns, old_ns))

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
        "--to sqlite: nothing under data/ on disk but the database; every file, output and row read back the same, a file's time kept",
        r.returncode == 0
        and all(f.startswith(_store.DB) for f in disk_files())
        and _store.read_bytes(data / "references" / "gold" / "ds" / "i1.txt")
        == before["references/gold/ds/i1.txt"]
        and _outputs.outputs(run) == {"i2": "two é\r\n", "i1": ""}
        and _outputs.rows_text(run) == before["runs/arm_v1_x/predictions.jsonl"].decode()
        and _outputs.rows_text(stopped, partial=True)
        == before["runs/arm_v1_stopped/rows.partial.jsonl"].decode()
        and _store.is_file(run / "metrics.json")
        and _store.stat(data / "datasets" / "ds.json").st_mtime_ns == old_ns,
        ((r.stdout + r.stderr)[-300:], disk_files(), _store.stat(data / "datasets" / "ds.json").st_mtime_ns),
    )
    problems, out = v23()
    check("V23 passes on the database", not problems, out)

    # Moving back unlinks the database: refused while another process has it open (a running catalog-serve kept
    # writing to the unlinked file, architecture review 2026-11-06). This process is that other process here.
    _store.connect()
    held = evh("data-migrate", "--to", "files", store="files")
    check(
        "--to files refused while another process has the database open, nothing moved",
        held.returncode == 1
        and "ERROR (not-allowed)" in held.stderr
        and "open" in held.stderr
        and (data / _store.DB).is_file()
        and all(f.startswith(_store.DB) for f in disk_files()),
        (held.stderr[-300:], disk_files()[:5]),
    )
    _store.close()
    r = evh("data-migrate", "--to", "files", store="files")
    use("files")
    after = {f: (data / f).read_bytes() for f in disk_files()}
    check(
        "--to files: every file byte-identical, its time kept, the database gone",
        r.returncode == 0
        and after == before
        and not (data / _store.DB).exists()
        and (data / "datasets" / "ds.json").stat().st_mtime_ns == old_ns,
        ((r.stdout + r.stderr)[-300:], sorted(set(before) ^ set(after))),
    )

    # A migration a crash stopped after it had moved a run's record, before the run's outputs and rows: the next one
    # finishes it, the outputs and rows into their own tables (advisor review, 2026-11-06: they went into the files
    # table, and the run read empty).
    use("sqlite")
    for name in ("metrics.json", "run.json"):
        _store.write_bytes(run / name, (run / name).read_bytes())
        (run / name).unlink()
    _store.close()
    r = evh("data-migrate", "--to", "sqlite", store="sqlite")
    use("sqlite")
    check(
        "--to sqlite resumed after a crash: the run's outputs and rows go to their tables, not the files",
        r.returncode == 0
        and _outputs.outputs(run) == {"i2": "two é\r\n", "i1": ""}
        and _outputs.rows_text(run) == before["runs/arm_v1_x/predictions.jsonl"].decode()
        and not _store.is_file(run / _outputs.FILE)
        and not _store.is_file(run / _outputs.PREDICTIONS),
        ((r.stdout + r.stderr)[-300:], _outputs.outputs(run)),
    )
    _store.close()  # this process read the database just now: moving back is refused while it has it open
    r = evh("data-migrate", "--to", "files", store="files")
    use("files")
    check(
        "--to files after the resumed migration: every file byte-identical again",
        r.returncode == 0 and {f: (data / f).read_bytes() for f in disk_files()} == before,
        (r.stdout + r.stderr)[-300:],
    )

    # A symbolic link under data/ (a big corpus kept elsewhere): os.walk does not follow it into a folder, so the
    # migration reported success with the folder's files never in the database, and V23 saw nothing (advisor review,
    # 2026-11-06). The migration refuses it by name; V23's files-on-disk check names it.
    elsewhere = proj / "corpus-elsewhere"
    elsewhere.mkdir()
    (elsewhere / "big.txt").write_text("a corpus\n")
    (data / "sources").mkdir(exist_ok=True)
    (data / "sources" / "big").symlink_to(elsewhere, target_is_directory=True)
    r = evh("data-migrate", "--to", "sqlite", store="sqlite")
    use("sqlite")
    linked = data / "sources" / "big"
    check(
        "--to sqlite refuses a symbolic link under data/, naming it; V23 names it on disk",
        r.returncode != 0
        and "symbolic links" in r.stderr
        and "sources/big" in r.stderr
        and linked in _store.stray_files(),
        (r.stderr[-300:], _store.stray_files()[:3]),
    )
    use("files")
    linked.unlink()
    shutil.rmtree(elsewhere)
    if not any((data / "sources").iterdir()):
        (data / "sources").rmdir()

    old = data / "runs" / "arm_v1_old"
    (old / "outputs").mkdir(parents=True)
    (old / "metrics.json").write_text("{}")
    (old / "outputs" / "i1.txt").write_text("x")
    r = evh("data-migrate", "--to", "sqlite", store="sqlite")
    check(
        "--to sqlite refuses a run in the layout before 0.8.0 (evh migrate first)",
        r.returncode != 0 and "evh migrate first" in r.stderr and (old / "outputs" / "i1.txt").is_file(),
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
        "    seen, end = 0, time.monotonic() + 30\n"  # until all n are seen: a fixed 0.8 s missed slow writers (2026-11-11)
        "    while seen < n and time.monotonic() < end:\n"
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
        [sys.executable, str(worker), str(c1), "300", "read"],
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
#: The files that do path I/O themselves, and why: the store, and files that never touch a project's data/ (the site's
#: own build, packaging, the file a person names to a source or an importer, code beside its prompts). Keyed by the
#: path from the repository root; a `*` matches one name. Any other file must go through _store.
ALLOWED = {
    "harness/scripts/_store.py": "the store",
    "harness/scripts/_outputs.py": "its files store is the disk by definition (data-migrate reads the disk through it)",
    "harness/scripts/data_migrate.py": "moves between the disk and the database",
    "harness/scripts/run_migrate.py": "reads the layout before 0.8.0 on disk",
    "harness/scripts/exposure_check.py": "checks the public git checkouts config.yaml names: outside data/, on disk",
    "harness/scripts/_common.py": "finds the project on disk (data/, .env, config.yaml) before any store exists",
    "harness/scripts/stats.py": "standard library only; its p cache is outside data/",
    "harness/scripts/skills_install.py": "copies the harness's own skill files, never data",
    "harness/scripts/_fetch.py": "its download cache is .cache/items, outside data/",
    "harness/scripts/_api.py": "the API's token and a job's uploads, under .build/, outside data/ (RFC-026)",
    "harness/scripts/_jobs.py": "jobs and their lock files, under .build/, outside data/ (RFC-026)",
    "harness/scripts/jobs_supervisor.py": "a job's own folder under .build/jobs, outside data/ (RFC-026)",
    "harness/scripts/_prompts.py": "reads the prompt files a config names and copies a prompt root under .build/, outside data/; versions go through _store (RFC-028)",
    "harness/scripts/_coderec.py": "unpacks each commit of a code record's checkout under .build/code, outside data/; records go through _store (RFC-030)",
    "harness/scripts/_coverage.py": "reads the source files of the version copies a replay ran, under .build/code (RFC-030)",
    "harness/scripts/faithfulness.py": "a replay's outputs while it runs, under .build/faithfulness, removed after (RFC-030)",
    "harness/scripts/_spend.py": "a round's ledger under .build/rounds and a child's spend in a temp file, outside data/ (RFC-026)",
    "harness/scripts/sources/*.py": "a dataset source reads the file or folder a person names to it, outside data/",
    "harness/scripts/importers/*.py": "an importer reads the file a person names to it",
    "harness/tools/_wheel.py": "packaging: copies the harness's own files",
    "harness/tools/store_matrix.py": "writes the test runs' logs under .build/, never data/",
    "site/*.py": "the public site's own build and checks: its pages and the docs, never a project's data",
    "examples/*/fetch.py": "an example's fetch writes its sources as files; in SQLite data-migrate moves them in (RFC-025)",
    "examples/*/adapter.py": "an adapter reads its prompt file beside its code",
    "examples/*/calibrate.py": "reads the example's arm configs beside its code",
    "examples/_shared/classification.py": "reads a prompt file beside the example's code",
    "examples/_shared/calibration.py": "writes docs/evidence/calibration, outside data/",
    "examples/_shared/gateway.py": "reads examples/models.json beside the code",
    "examples/_shared/hf_identity.py": "reads the Hugging Face cache, outside the project",
    "examples/triage-fleet/*.py": "reads and writes the sheets and decision files a person names",
    "examples/replay-filing/system/*/filing.py": "the example's system under test: its own ledger file, which a replay points at a temp file",
    "examples/replay-filing/*.py": "makes the example's system repository and frozen history in a folder a person names, outside data/; data files go through _store (RFC-030)",
    "examples/audit_locks.py": "checks the examples' lock files",
    "examples/signal-fleet-dedup/test_dedup.py": "a test of the example's own fixtures",
}
METHODS = {"read_text", "read_bytes", "write_text", "write_bytes", "is_file", "is_dir", "exists", "glob", "rglob",
           "iterdir", "unlink", "mkdir", "stat", "open", "rename", "rmdir", "chmod", "touch"}  # fmt: skip
#: (`.replace()` is left out: a str's and a Path's cannot be told apart here.)
FUNCS = (
    {("shutil", f) for f in ("rmtree", "copy", "copy2", "copyfile", "copytree", "move")}
    | {
        ("os", f)
        for f in (
            "replace",
            "rename",
            "remove",
            "unlink",
            "makedirs",
            "listdir",
            "walk",
            "scandir",
            "mkdir",
            "rmdir",
            "stat",
            "lstat",
            "chmod",
            "utime",
            "symlink",
            "link",
            "truncate",
        )
    }
    | {("os.path", f) for f in ("exists", "isfile", "isdir", "getmtime", "getsize")}
    | {(m, f) for m in ("glob", "_glob") for f in ("glob", "iglob")}
)
#: A temporary file or folder made in a given directory: under data/ in SQLite mode that directory does not exist
#: (finding 2 of the 2026-11-06 review: label sets and capture restore did this). One made in the system's own
#: temporary directory (no dir=) is not the project's data.
TEMP = {"mkdtemp", "mkstemp", "NamedTemporaryFile", "TemporaryDirectory", "TemporaryFile"}
REPO = HARNESS.parent


# A file on disk is written whole (RFC-026 step 1): a reader sees the old file or the new one, never a half.
with tempfile.TemporaryDirectory() as td:
    target = Path(td) / "a.json"
    _store._replace(target, b"old\n")
    umask_now = os.umask(0o022)
    os.umask(umask_now)
    file_mode = target.stat().st_mode & 0o777
    from unittest import mock

    with mock.patch("os.replace", side_effect=OSError("disk full")):
        try:
            _store._replace(target, b"new, and long enough to be cut half way\n")
            raised = False
        except OSError:
            raised = True
    check(
        "a whole-file write: the mode a plain write gives; a write that fails leaves the old file and no temp file",
        file_mode == 0o666 & ~umask_now
        and raised
        and target.read_bytes() == b"old\n"
        and sorted(Path(td).iterdir()) == [target],
        (oct(file_mode), raised, sorted(x.name for x in Path(td).iterdir())),
    )


def dotted(n):
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute):
        d = dotted(n.value)
        return f"{d}.{n.attr}" if d else None
    return None


def allowed(rel: str) -> bool:
    return any(fnmatch.fnmatchcase(rel, pat) and pat.count("/") == rel.count("/") for pat in ALLOWED)


scanned = sorted(
    f
    for f in {
        *HARNESS.glob("scripts/**/*.py"),
        *HARNESS.glob("tools/**/*.py"),
        *REPO.glob("site/**/*.py"),
        *REPO.glob("examples/**/*.py"),
    }
    if not {".venv", "__pycache__", "node_modules"} & set(f.parts)
)
stray = []
for f in scanned:
    where = f.relative_to(REPO).as_posix()
    if allowed(where):
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
            stray.append(f"{where}:{n.lineno} open()")
        elif isinstance(fn, ast.Attribute):
            recv = dotted(fn.value)
            if (recv, fn.attr) in FUNCS:
                stray.append(f"{where}:{n.lineno} {recv}.{fn.attr}")
            elif recv == "tempfile" and fn.attr in TEMP and any(k.arg == "dir" for k in n.keywords):
                stray.append(f"{where}:{n.lineno} tempfile.{fn.attr}(dir=)")
            # a module's own function (os.path.exists, glob.glob) is not path I/O; a path a module holds
            # (_common.DATASETS.glob) is
            elif fn.attr in METHODS and recv != "_store" and not (recv in mods or recv == "os.path"):
                stray.append(f"{where}:{n.lineno} .{fn.attr}()")
check(
    f"the path-I/O guard reads {len(scanned)} files: scripts/ (with sources/ and importers/), tools/, site/, examples/",
    len(scanned) > 150,
    len(scanned),
)
check(
    "no file but the store and the ones named above does path I/O itself (everything else through _store)",
    not stray,
    stray[:15],
)
sys.exit(summary())
