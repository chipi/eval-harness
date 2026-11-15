#!/usr/bin/env python3
"""A deployment's release in either store (RFC-032 step 9): built, sealed, read, and checked as it is deployed.

    python tests/test_release_store.py

In a throwaway git project (tracked silver and gold manifest, a hidden dataset with a run, two goals), whose data is
files and, migrated, a SQLite database:

- `_release.py copy-data --store files|sqlite` from either source: the release is the same data in either store (every
  file's bytes, each run's outputs and each score's rows), a hidden dataset's outputs are left out of both, and every
  refusal (a reference text git does not track, one whose manifest says it is not redistributed) refuses before
  anything is written, in each store.
- A SQLite release is one sealed file: `data/` holds `project.sqlite` alone, out of write-ahead logging, its
  config.yaml says `store: sqlite`; a files release has neither.
- The same data makes the same bytes: a second build of it, its files a checkout later, is the same database byte for
  byte, and every file in it has the one release modification time.
- The database is sealed at 16 KiB pages (RFC-033), whatever page size the one it was made from had: `PRAGMA page_size`
  says it, `check` refuses a release at another size, and the bytes stay the same for the same data.
- A hidden dataset's run.json `call` holds the run settings only: one with another key is refused before anything is
  written, in each store.
- `_release.py check`, render.sh's last word, on each store: passes on a good release, and fails on each planted
  leak (a reference text git does not track, a materialized item, a goal the MCP answers do not cover, a missing p
  cache); on a SQLite release also a stray -wal, setup lock or file, and a database still in write-ahead logging.
  The planted leaks are put where each store keeps files, never found by looking at a folder a database release does
  not have.
- `evh migrate --check`, render.sh's format check, on each store: passes, and fails on a release from before.
- Reading a release changes none of its bytes; render.sh and compose.yml say what the checks above rely on.
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

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
ROOT = HARNESS.parent
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
tmp = Path(tempfile.mkdtemp(prefix="evh-release-store-"))
for k in ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_STORE", "EVAL_STORE_READONLY"):
    os.environ.pop(k, None)
os.environ["EVAL_STORE"] = "files"
import _runstore  # noqa: E402
from evaluation_harness import _format, _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

GIT = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def run(args, env=None, cwd=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_")}
    e.update(env or {})
    return subprocess.run(
        [sys.executable, *map(str, args)], env=e, cwd=cwd, capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL
    )  # fmt: skip


def git(src, *args):
    subprocess.run(["git", "-C", str(src), *args], env=GIT, check=True, capture_output=True, timeout=60)


# ── the project: files, in git ────────────────────────────────────────────────────────────────────────────────────
def build_source(src: Path) -> None:
    (src / "data").mkdir(parents=True)
    with _runstore._InProject(src):
        w = lambda rel, text: _runstore.write_text(src, rel, text)  # noqa: E731
        w(_format.NAME, f"format: {_format.FORMAT}\n")
        w("goals/g1.yaml", "goal_id: g1\n")
        w("goals/g2.yaml", "goal_id: g2\n")
        w(
            "datasets/ds1.json",
            json.dumps({"dataset_id": "ds1", "items": [{"item_id": "a"}, {"item_id": "b"}]}),
        )
        w(
            "datasets/dsh.json",
            json.dumps({"dataset_id": "dsh", "text": "hidden", "items": [{"item_id": "a"}]}),
        )
        w("references/silver/ds1/manifest.json", json.dumps({"dataset_id": "ds1", "redistributed": True}))
        w("references/silver/ds1/a.txt", "silver answer a\n")
        w("references/gold/ds1/manifest.json", json.dumps({"dataset_id": "ds1", "redistributed": True}))
        shown = {"a": "shown output a", "b": "shown output b"}
        rows = [
            {"item_id": "a", "correct": 1.0, "_meta": {"usage": {"n": 1}}},
            {"item_id": "b", "correct": 0.0},
        ]
        _runstore.make_run(
            src / "data" / "runs", "r1", {"dataset_id": "ds1"}, outputs=shown,
            scores=[{"scorer": "s1", "reference": "gold.ds1", "first": True, "metrics": {"correct": 0.5}, "rows": rows}],
        )  # fmt: skip
        _runstore.make_run(
            src / "data" / "runs", "rh", {"dataset_id": "dsh", "call": {"generation_config": {"temperature": 0}}},
            outputs={"a": "HIDDEN output"},
            scores=[{"scorer": "s1", "reference": "gold.dsh", "first": True, "metrics": {}, "rows": [
                {"item_id": "a", "correct": 1.0, "_meta": {"usage": {"n": 1}, "predicted": "HIDDEN guess"}}]}],
        )  # fmt: skip
    git(src, "init", "-q")
    git(src, "add", "-A")
    git(src, "commit", "-qm", "the project", "--no-gpg-sign")


def tracked_refs(src: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(src), "ls-files", "--", "data/references"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return "".join(line.removeprefix("data/") + "\n" for line in out.splitlines())


def migrate_source(files_src: Path, dst: Path) -> None:
    """The same project with its data in the database (what `evh data-migrate --to sqlite` makes)."""
    shutil.copytree(files_src, dst, ignore=shutil.ignore_patterns(".git"))
    r = run([HERE / "data_migrate.py", "--to", "sqlite"], env={"EVAL_HOME": dst, "EVAL_STORE": "sqlite"})
    assert r.returncode == 0, r.stdout + r.stderr


# ── reading a release without the package: files from the disk, a database through sqlite3 ────────────────────────
def read_release(root: Path) -> dict:
    """{files: {path: sha256}, outputs: {run: [(item, text, sha)]}, rows: {(run, partial): text}}: what a release holds."""
    data = root / "data"
    db = data / "project.sqlite"
    files: dict[str, str] = {}
    outs: dict[str, list] = {}
    rows: dict[tuple, str] = {}
    if db.is_file():
        c = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
        files = dict(c.execute("SELECT path, sha256 FROM files"))
        for run_key, item, text, sha in c.execute(
            "SELECT run, item_id, text, sha256 FROM outputs ORDER BY rowid"
        ):
            outs.setdefault(run_key, []).append((item, text, sha))
        # a score's rows are tables: assembled by the package's own reader, then their canonical lines
        names: dict[int, str] = {}
        for (key,) in c.execute("SELECT key FROM score_sets ORDER BY key").fetchall():
            made = _outputs.read_set(c, key, names)
            rows[(key, False)] = "".join(_outputs.row_line(r) for r in made[0]) if made else ""
        for run_key, line in c.execute("SELECT run, line FROM rows_partial WHERE n > 0 ORDER BY run, n"):
            rows[(run_key, True)] = rows.get((run_key, True), "") + line
        c.close()
        return {"files": files, "outputs": outs, "rows": rows}
    for p in sorted(data.rglob("*")):
        if not p.is_file():
            continue
        key = p.relative_to(data).as_posix()
        if p.name == "outputs.jsonl":
            outs[p.parent.relative_to(data).as_posix()] = [
                (d["item_id"], d["text"], d["sha256"]) for d in map(json.loads, p.read_text().splitlines())
            ]
        elif p.name in ("predictions.jsonl", "rows.partial.jsonl"):
            rows[(p.parent.relative_to(data).as_posix(), p.name == "rows.partial.jsonl")] = p.read_text()
        else:
            files[key] = hashlib.sha256(p.read_bytes()).hexdigest()
    return {"files": files, "outputs": outs, "rows": rows}


def fingerprint(root: Path) -> list:
    """Every file under a release, its path and bytes: whether anything changed."""
    return [
        (str(p.relative_to(root)), hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted(root.rglob("*"))
        if p.is_file()
    ]


# ── a release: the copy, and what render.sh adds beside it ────────────────────────────────────────────────────────
def make_release(src: Path, store: str, dst: Path, source_store: str) -> subprocess.CompletedProcess:
    return run(
        [HERE / "_release.py", "copy-data", src / "data", dst / "data", "--store", store],
        env={"EVAL_HOME": src, "EVAL_STORE": source_store},
        cwd=src,
    )


def add_caches(root: Path, goals: int = 2) -> None:
    (root / "cache").mkdir(exist_ok=True)
    (root / "cache" / "evh-p.jsonl").write_text(json.dumps({"k": "a" * 64, "p": (0.5).hex()}) + "\n")
    answer = {"result": {"blocks": [{"rows": [{"goal": f"g{i}"} for i in range(goals)]}]}}
    lines = [
        {"tool": "goals", "argv": [], "out": json.dumps(answer), "harness": "x"},
        {"tool": "leaderboard", "argv": ["--dataset-id", "ds1"], "out": "{}", "harness": "x"},
    ]
    (root / "cache" / "mcp-answers.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))


def run_check(root: Path, tracked: Path):
    return run([HERE / "_release.py", "check", root, tracked], env={"EVAL_HOME": root}, cwd=tmp)


def run_format(root: Path):
    return run([HERE / "migrate.py", "--check"], env={"EVAL_HOME": root, "EVAL_STORE_READONLY": "1"}, cwd=tmp)


def plant(root: Path, store: str, key: str, data: bytes) -> None:
    """A file put into a release where its store keeps it: a row of the database, or a file."""
    if store == "sqlite":
        c = sqlite3.connect(str(root / "data" / "project.sqlite"))
        c.execute(
            "INSERT OR REPLACE INTO files VALUES (?, ?, ?, 1)", (key, data, hashlib.sha256(data).hexdigest())
        )
        c.commit()
        c.close()
    else:
        (root / "data" / key).parent.mkdir(parents=True, exist_ok=True)
        (root / "data" / key).write_bytes(data)


def said(r) -> str:
    return (r.stdout + r.stderr).strip()[-300:]


try:
    files_src, sqlite_src = tmp / "src-files", tmp / "src-sqlite"
    build_source(files_src)
    migrate_source(files_src, sqlite_src)
    tracked = tmp / "tracked.txt"
    tracked.write_text(tracked_refs(files_src))
    check(
        "setup: the project's tracked references are the silver text and the two manifests",
        len(tracked.read_text().split()) == 3,
        tracked.read_text(),
    )

    # ── the build: both sources, both stores ─────────────────────────────────────────────────────────────────────
    releases = {}
    for source, src in (("files", files_src), ("sqlite", sqlite_src)):
        for store in ("files", "sqlite"):
            dst = tmp / f"rel-{source}-{store}"
            r = make_release(src, store, dst / "inspector", source)
            releases[(source, store)] = dst / "inspector"
            check(f"a {store} release of a {source} project is built", r.returncode == 0, said(r))
    ff, fs, sf, ss = (
        releases[k]
        for k in (("files", "files"), ("files", "sqlite"), ("sqlite", "files"), ("sqlite", "sqlite"))
    )
    want = read_release(ff)
    check(
        "the files release holds the shown run's outputs and rows, and the hidden run's rows cut to the call, no outputs",
        [o[0] for o in want["outputs"].get("runs/r1", [])] == ["a", "b"]
        and "runs/rh" not in want["outputs"]
        and "HIDDEN" not in str(want)
        and ("runs/r1/scores/s1@gold.ds1", False) in want["rows"],
        {k: list(v) for k, v in want.items()},
    )
    for label, root in (
        ("files project", fs),
        ("sqlite project, to files", sf),
        ("sqlite project, to sqlite", ss),
    ):
        got = read_release(root)
        check(
            f"the same data in the release of a {label}: every file's bytes, outputs and rows",
            got == want,
            {k: (set(got[k]) ^ set(want[k])) for k in got},
        )

    # ── a SQLite release is one sealed file; a files release has neither it nor the setting ─────────────────────
    for label, root in (("of a files project", fs), ("of a sqlite project", ss)):
        db = root / "data" / "project.sqlite"
        check(
            f"a SQLite release {label}: data/ holds the database alone, out of write-ahead logging, and says so in config.yaml",
            sorted(os.listdir(root / "data")) == ["project.sqlite"]
            and db.read_bytes()[18:20] == b"\x01\x01"
            and (root / "config.yaml").read_text() == "store: sqlite\n",
            (sorted(os.listdir(root / "data")), db.read_bytes()[18:20]),
        )
    c = sqlite3.connect(f"file:{fs / 'data' / 'project.sqlite'}?mode=ro&immutable=1", uri=True)
    have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    c.close()
    check(
        "a SQLite release has the per-item tables (a read-only open creates none)",
        {"files", *_outputs.TABLES} <= have and "rows" not in have,
        have,
    )
    check(
        "a files release has no database and its config.yaml says `store: files`",
        not (ff / "data" / "project.sqlite").exists()
        and (ff / "config.yaml").read_text() == "store: files\n",
    )

    # ── the same data makes the same bytes (rsync re-sends a deploy's database unless it does) ───────────────────
    later = 1_900_000_000
    for p in files_src.joinpath("data").rglob("*"):
        if p.is_file():
            os.utime(p, (later, later))  # a later checkout of the same commit: every file's time differs
    again = tmp / "again"
    r = make_release(files_src, "sqlite", again / "inspector", "files")
    check(
        "a second build of the same data, its files a checkout later, is the same database, byte for byte",
        r.returncode == 0
        and (again / "inspector" / "data" / "project.sqlite").read_bytes()
        == (fs / "data" / "project.sqlite").read_bytes(),
        said(r),
    )
    c = sqlite3.connect(f"file:{fs / 'data' / 'project.sqlite'}?mode=ro&immutable=1", uri=True)
    stamps = {r[0] for r in c.execute("SELECT mtime_ns FROM files")}
    c.close()
    check("every file in a SQLite release has the one release time", stamps == {946_684_800 * 10**9}, stamps)

    from evaluation_harness import _release_store

    for label, root in (
        ("of a files project", fs),
        ("of a sqlite project", ss),
        ("a build later", again / "inspector"),
    ):
        db = root / "data" / "project.sqlite"
        c = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
        pragma = c.execute("PRAGMA page_size").fetchone()[0]
        pages = c.execute("PRAGMA page_count").fetchone()[0]
        c.close()
        check(
            f"a SQLite release {label} has 16 KiB pages: PRAGMA page_size, the header, and the file's length",
            pragma == 16384 == _release_store.RELEASE_PAGE_SIZE
            and int.from_bytes(db.read_bytes()[16:18], "big") == 16384
            and db.stat().st_size == pages * 16384,
            (pragma, pages, db.stat().st_size),
        )

    sealed = []
    for name, commits in (("one", 1), ("many", 7)):  # the same rows, in one transaction and in seven
        db = tmp / f"seal-{name}.sqlite"
        c = sqlite3.connect(str(db), isolation_level=None)
        c.execute("PRAGMA page_size=4096")  # sealing takes a database of any page size to the release's
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(f"PRAGMA wal_autocheckpoint={1000 if commits == 1 else 3}")
        c.execute("CREATE TABLE files (path TEXT PRIMARY KEY, data BLOB, sha256 TEXT, mtime_ns INTEGER)")
        for i in range(70):
            if i % (70 // commits) == 0:
                c.execute("BEGIN")
            c.execute("INSERT INTO files VALUES (?, ?, 'x', 1)", (f"f{i:03}", b"d" * 900))
            if i % (70 // commits) == 70 // commits - 1:
                c.execute("COMMIT")
        c.close()
        _release_store.seal(db)
        sealed.append(db.read_bytes())
    check(
        "a sealed database's bytes do not depend on how it was written (its file change counter, its page layout)",
        sealed[0] == sealed[1]
        and len(sealed[0]) > 16384
        and all(
            int.from_bytes(b[24:28], "big") == 1 for b in sealed
        )  # written whole once: the change counter is 1
        and all(int.from_bytes(b[16:18], "big") == 16384 and len(b) % 16384 == 0 for b in sealed),
        [(len(b), int.from_bytes(b[24:28], "big"), int.from_bytes(b[16:18], "big")) for b in sealed],
    )

    # ── the refusals, in each store, before anything is written ──────────────────────────────────────────────────
    (files_src / "data" / "references" / "gold" / "ds1" / "x.txt").write_text(
        "a gold text git does not track\n"
    )
    r = make_release(files_src, "sqlite", tmp / "refused-f" / "inspector", "files")
    r2 = make_release(files_src, "files", tmp / "refused-g" / "inspector", "files")
    check(
        "an untracked reference text is refused, for a SQLite release and for a files release, nothing written",
        r.returncode == 1 and r2.returncode == 1 and "ERROR (not-allowed)" in r.stderr + r2.stderr
        and "git does not track" in r.stderr and not (tmp / "refused-f").exists() and not (tmp / "refused-g").exists(),
        said(r),
    )  # fmt: skip
    (files_src / "data" / "references" / "gold" / "ds1" / "x.txt").unlink()
    # a hidden run's run.json is copied whole: its `call` holds the run settings and nothing else
    hidden_run_json = files_src / "data" / "runs" / "rh" / "run.json"
    good_text = hidden_run_json.read_text()
    good_doc = json.loads(good_text)
    for planted in (
        {"provider": "p"},
        {"generation_config": {"temperature": 0}, "predicted": "HIDDEN guess"},
        "HIDDEN",
    ):
        hidden_run_json.write_text(json.dumps({**good_doc, "call": planted}))
        rs = [
            make_release(files_src, store, tmp / f"refused-call-{store}" / "inspector", "files")
            for store in ("files", "sqlite")
        ]
        check(
            f"a hidden run's call holding {str(planted)[:40]} is refused for each store, nothing written",
            all(r.returncode == 1 and "not just the run settings" in r.stderr for r in rs)
            and not any((tmp / f"refused-call-{s}").exists() for s in ("files", "sqlite"))
            and "HIDDEN" not in "".join(r.stdout for r in rs),
            said(rs[0]),
        )  # fmt: skip
    hidden_run_json.write_text(good_text)
    check(
        "a hidden run's call of run settings only is released",
        make_release(files_src, "sqlite", tmp / "ok-call" / "inspector", "files").returncode == 0,
    )
    os.environ["EVAL_STORE"] = "sqlite"  # the fixture is written where this project keeps its data
    try:
        with _runstore._InProject(sqlite_src):
            _runstore.write_text(
                sqlite_src,
                "references/gold/ds1/manifest.json",
                json.dumps({"dataset_id": "ds1", "redistributed": False}),
            )
            _runstore.write_text(
                sqlite_src, "references/gold/ds1/x.txt", "a gold text the manifest does not release\n"
            )
    finally:
        os.environ["EVAL_STORE"] = "files"
        _outputs.reset()
    r = make_release(sqlite_src, "sqlite", tmp / "refused-s" / "inspector", "sqlite")
    check(
        "a reference whose manifest says it is not redistributed is refused for a SQLite release of a sqlite project",
        r.returncode == 1 and "not redistributed" in r.stderr and not (tmp / "refused-s").exists(),
        said(r),
    )

    # ── the checks, on each store ────────────────────────────────────────────────────────────────────────────────
    def checks_on(store, base):
        good = tmp / f"good-{store}"
        shutil.copytree(base.parent, good)
        root = good / "inspector"
        add_caches(root)
        before = fingerprint(root)
        r = run_check(root, tracked)
        check(f"[{store}] check: a good release passes", r.returncode == 0 and not r.stdout.strip(), said(r))
        r = run_format(root)
        check(f"[{store}] the format check passes on the release as it is", r.returncode == 0, said(r))
        check(f"[{store}] checking and reading it changed none of its files", fingerprint(root) == before)

        def case(name, mutate, expect, checker=run_check):
            d = tmp / f"case-{store}-{name}"
            shutil.copytree(good, d)
            root = d / "inspector"
            mutate(root)
            r = checker(root, tracked) if checker is run_check else checker(root)
            check(f"[{store}] {name}", r.returncode != 0 and expect in r.stdout + r.stderr, said(r))
            shutil.rmtree(d, ignore_errors=True)

        case(
            "a reference text git does not track, planted, fails check",
            lambda root: plant(root, store, "references/gold/ds1/leak.txt", b"gold text"),
            "reference text(s) git does not track",
        )
        case(
            "a tracked reference moved to an untracked name fails check",
            lambda root: plant(
                root, store, "references/silver/ds1/other.txt", b"silver text under another name"
            ),
            "references/silver/ds1/other.txt",
        )
        case(
            "a materialized item, planted, fails check",
            lambda root: plant(root, store, "materialized/ds1/items.json", b"{}"),
            "materialized items in the release",
        )
        case(
            "a goal the MCP answers do not cover fails check",
            lambda root: add_caches(root, goals=1),
            "goals answers 1 of the release's 2",
        )
        case(
            "a goal added after the answers were written fails check",
            lambda root: plant(root, store, "goals/g3.yaml", b"goal_id: g3\n"),
            "goals answers 2 of the release's 3",
        )
        case(
            "no MCP answers at all fails check",
            lambda root: (root / "cache" / "mcp-answers.jsonl").unlink(),
            "goals answers 0 of the release's 2",
        )
        case(
            "an empty p cache fails check",
            lambda root: (root / "cache" / "evh-p.jsonl").write_text(""),
            "p cache",
        )
        case(
            "a missing p cache fails check",
            lambda root: (root / "cache" / "evh-p.jsonl").unlink(),
            "p cache",
        )
        stamp = "project.yaml"
        old = f"format: {_format.FORMAT - 1}\n".encode()
        case(
            "a release from before the format fails the format check",
            lambda root: plant(root, store, stamp, old),
            "old-format",
            checker=run_format,
        )
        if store == "files":
            case(
                "a database in a files release fails check",
                lambda root: (root / "data" / "project.sqlite").write_bytes(b""),
                "a files release holds project.sqlite",
            )
        else:
            case(
                "a stray -wal beside a SQLite release fails check",
                lambda root: (root / "data" / "project.sqlite-wal").write_bytes(b""),
                "holds ['project.sqlite', 'project.sqlite-wal']",
            )
            case(
                "a setup lock beside a SQLite release fails check",
                lambda root: (root / "data" / "project.sqlite-setup-lock").write_bytes(b""),
                "project.sqlite-setup-lock",
            )

            def wal(root):
                c = sqlite3.connect(str(root / "data" / "project.sqlite"))
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("INSERT OR REPLACE INTO meta VALUES ('x', 'y')")
                c.commit()
                c.close()
                for s in ("-wal", "-shm"):
                    (root / "data" / f"project.sqlite{s}").unlink(missing_ok=True)

            case("a database left in write-ahead logging fails check", wal, "still in write-ahead logging")

            def small_pages(root):
                c = sqlite3.connect(str(root / "data" / "project.sqlite"), isolation_level=None)
                c.execute("PRAGMA page_size=4096")
                c.execute("VACUUM")
                c.close()

            case("a database at another page size fails check", small_pages, "4096-byte pages")
            case(
                "a file of the release's data/ left on disk beside the database fails check",
                lambda root: (root / "data" / "references.txt").write_text("a leak"),
                "not just project.sqlite",
            )

    for store_, base_ in (("files", ff), ("sqlite", fs)):
        checks_on(store_, base_)

    # ── the command line ─────────────────────────────────────────────────────────────────────────────────────────
    r = run([HERE / "_release.py", "check", fs, tracked], env={"EVAL_HOME": tmp}, cwd=tmp)
    check(
        "check run from another project is refused as a bad argument",
        r.returncode == 1 and "ERROR (bad-argument)" in r.stderr,
        said(r),
    )
    r = run(
        [HERE / "_release.py", "copy-data", files_src / "data", tmp / "elsewhere", "--store", "sqlite"],
        env={"EVAL_HOME": files_src, "EVAL_STORE": "files"},
        cwd=files_src,
    )
    check(
        "a SQLite release must be a project's data/ folder",
        r.returncode == 1 and "ERROR (bad-argument)" in r.stderr,
        said(r),
    )
    # render.sh runs from the repository's root, which names no store: copy-data reads the source through the project
    # EVAL_HOME names, or it is refused (the deploy failed this way when the files default went, 2026-11-15).
    # Run as render.sh runs it: the package copied out of the checkout (so the checkout's harness/ is not its project).
    bare = tmp / "repo-root"
    pkg = tmp / "pkg" / "evaluation_harness"
    shutil.copytree(HERE, pkg, ignore=shutil.ignore_patterns("__pycache__"))
    bare.mkdir()
    r = run(
        [pkg / "_release.py", "copy-data", files_src / "data", tmp / "r1" / "data", "--store", "sqlite"],
        cwd=bare,
    )
    check(
        "copy-data from a folder that names no store, without EVAL_HOME, is refused (not-configured)",
        r.returncode == 1 and "ERROR (not-configured)" in r.stderr,
        said(r),
    )
    (files_src / "config.yaml").write_text(
        "store: files\n"
    )  # as this repository's harness/config.yaml names it
    r = run(
        [pkg / "_release.py", "copy-data", files_src / "data", tmp / "r2" / "data", "--store", "sqlite"],
        env={"EVAL_HOME": files_src},
        cwd=bare,
    )
    check(
        "copy-data from that folder with EVAL_HOME naming the source project makes the release",
        r.returncode == 0 and (tmp / "r2" / "data" / "project.sqlite").is_file(),
        said(r),
    )

    # ── what render.sh and compose.yml say ───────────────────────────────────────────────────────────────────────
    render = ROOT / "infra" / "deploy" / "render.sh"
    if not render.is_file():
        print("  --   render.sh not here (not a checkout)")
    else:
        sh, compose = render.read_text(), (ROOT / "infra" / "compose.yml").read_text()
        check(
            "render.sh builds the release in the store EVALS_STORE names (sqlite unless said), through copy-data",
            'STORE="${EVALS_STORE:-sqlite}"' in sh and '--store "$STORE"' in sh and "files|sqlite" in sh,
        )
        check(
            "render.sh reads the release as the box does (read-only) and checks it through its own store, never `find`",
            "export EVAL_STORE_READONLY=1" in sh and "_release.py\" check" in sh and "find references" not in sh
            and "data/goals/*.yaml" not in sh and "EVAL_STORE=files" not in sh,
        )  # fmt: skip
        check(
            "render.sh: copy-data reads the source through harness/ (its config.yaml names the store); the check writes no .pyc",
            'EVAL_HOME="$ROOT/harness" python3 "$OUT/inspector/pkg/evaluation_harness/_release.py" copy-data'
            in sh
            and 'PYTHONDONTWRITEBYTECODE=1 python3 "$OUT/inspector/pkg/evaluation_harness/_release.py" check'
            in sh,
        )
        inspector = compose.split("  inspector:")[1].split("\n  mcp:")[0]
        mcp = compose.split("\n  mcp:")[1]
        check(
            "compose.yml: the inspector and the MCP server both keep the goals' tests in the release's cache, and name no store",
            "EVH_P_CACHE: /srv/evals/current/inspector/cache/evh-p.jsonl" in inspector
            and "EVH_P_CACHE: /srv/evals/current/inspector/cache/evh-p.jsonl" in mcp
            and "EVAL_STORE" not in compose,
        )
finally:
    _outputs.reset()
    shutil.rmtree(tmp, ignore_errors=True)

sys.exit(summary())
