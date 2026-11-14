#!/usr/bin/env python3
"""Where a dataset's item files are, and materialize (RFC-032 step 6): one place works out `source_dir`, a failed
materialize leaves what was there, and a dataset made from a folder outside the project keeps its items in it.

    python tests/test_dataset_source.py

In throwaway projects ($0, offline), in whichever store the suite runs in: dataset-materialize --force from a subfolder
of the project (the source folder was read against the directory the command ran in: every item MISSING and the
verified copy deleted, 2026-11-14); a materialize that fails (a changed item, a missing one) leaves the old copy with
--force and makes no empty folder without it; dataset-create from a folder outside the project copies the items the
dataset takes into data/sources/<id>/ and records that folder, refuses (writing nothing) when the folder holds other
content, and records a folder inside the project as it is.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _common, _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-source-"))
outside = Path(tempfile.mkdtemp(prefix="evh-outside-"))
_common.project_root.cache_clear()
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-source")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=cwd or proj,
        env=env,
        capture_output=True,
        text=True,
    )


def out(r):
    return r.stdout + r.stderr


def record(ds):
    return _runstore.read_json(proj, f"datasets/{ds}.json")


ITEMS = {"a.txt": "alpha\n", "b.txt": "beta\n", "c.txt": "gamma\n"}
try:
    (proj / "data").mkdir(parents=True)
    (proj / "sub" / "deeper").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")

    # ── a folder in the project: materialize from anywhere in it ──────────────────────────────────────────────
    for name, text in ITEMS.items():
        _runstore.write_text(proj, f"sources/demo_v1/{name}", text)
    r = evh("dataset-create", "--dataset-id", "demo_v1", "--source-dir", "data/sources/demo_v1")
    check("a folder in the project: dataset-create", r.returncode == 0, out(r)[-300:])
    check(
        "  its record names it relative to the project, and nothing was copied",
        record("demo_v1").get("source_dir") == "data/sources/demo_v1" and "copied" not in out(r),
        record("demo_v1").get("source_dir"),
    )
    r = evh("dataset-materialize", "--dataset-id", "demo_v1")
    check(
        "  materialize from the project root",
        r.returncode == 0 and "hashes verified" in out(r),
        out(r)[-300:],
    )
    r = evh("dataset-materialize", "--dataset-id", "demo_v1", "--force", cwd=proj / "sub" / "deeper")
    check(
        "  materialize --force from a subfolder: exit 0, hashes verified",
        r.returncode == 0 and "hashes verified" in out(r) and "MISSING" not in out(r),
        out(r)[-400:],
    )
    check(
        "  ... and the copy is there, whole",
        all(_runstore.is_file(proj, f"materialized/demo_v1/{n}") for n in (*ITEMS, "meta.json")),
        _runstore.files_under(proj, "materialized"),
    )

    # ── a failed materialize leaves what was there ────────────────────────────────────────────────────────────
    before = {f: _runstore.read_bytes(proj, f) for f in _runstore.files_under(proj, "materialized/demo_v1")}
    _runstore.write_text(proj, "sources/demo_v1/b.txt", "beta changed\n")
    r = evh("dataset-materialize", "--dataset-id", "demo_v1", "--force")
    check(
        "a changed item with --force: exit 1, CHANGED",
        r.returncode == 1 and "CHANGED  b.txt" in out(r),
        out(r)[-300:],
    )
    after = {f: _runstore.read_bytes(proj, f) for f in _runstore.files_under(proj, "materialized/demo_v1")}
    check("  the old verified copy is untouched", after == before and bool(before), sorted(after))
    _runstore.unlink(proj, "sources/demo_v1/c.txt")
    r = evh("dataset-materialize", "--dataset-id", "demo_v1", "--force")
    check(
        "a missing item with --force: exit 1, MISSING",
        r.returncode == 1 and "MISSING  c.txt" in out(r),
        out(r)[-300:],
    )
    after = {f: _runstore.read_bytes(proj, f) for f in _runstore.files_under(proj, "materialized/demo_v1")}
    check("  the old copy is untouched again", after == before, sorted(after))
    check(
        "  no half-built copy is left beside it",
        not [n for n in _runstore.listdir(proj, "materialized") if n != "demo_v1"],
        _runstore.listdir(proj, "materialized"),
    )

    _runstore.rmtree(proj, "materialized/demo_v1")
    r = evh("dataset-materialize", "--dataset-id", "demo_v1")
    check(
        "a missing item, no copy yet: exit 1", r.returncode == 1 and "MISSING  c.txt" in out(r), out(r)[-300:]
    )
    check(
        "  no copy stays no copy (no empty folder)",
        not _runstore.exists(proj, "materialized/demo_v1") and not _runstore.listdir(proj, "materialized"),
        _runstore.listdir(proj, "materialized"),
    )
    _runstore.write_text(proj, "sources/demo_v1/c.txt", ITEMS["c.txt"])
    _runstore.write_text(proj, "sources/demo_v1/b.txt", ITEMS["b.txt"])
    r = evh("dataset-materialize", "--dataset-id", "demo_v1")
    check(
        "  the next run builds it (not `exists - nothing to do`)",
        r.returncode == 0
        and "hashes verified" in out(r)
        and _runstore.is_file(proj, "materialized/demo_v1/meta.json"),
        out(r)[-300:],
    )

    # ── a folder outside the project is copied in ─────────────────────────────────────────────────────────────
    for name, text in {**ITEMS, "README.md": "docs\n", "skip.csv": "x\n"}.items():
        (outside / name).write_text(text)
    r = evh("dataset-create", "--dataset-id", "ext_v1", "--source-dir", str(outside), "--glob", "*.txt")
    check("an outside folder: dataset-create", r.returncode == 0, out(r)[-400:])
    rec = record("ext_v1") if r.returncode == 0 else {}
    check(
        "  its record names data/sources/<id>, not the folder's bare name",
        rec.get("source_dir") == "data/sources/ext_v1",
        rec.get("source_dir"),
    )
    said = [ln for ln in out(r).splitlines() if "copied" in ln]
    check(
        "  one line says what was copied, from where, to where",
        len(said) == 1 and "3" in said[0] and str(outside) in said[0] and "data/sources/ext_v1" in said[0],
        said,
    )
    check(
        "  only the items the glob takes were copied, byte for byte",
        sorted(_runstore.files_under(proj, "sources/ext_v1")) == sorted(f"sources/ext_v1/{n}" for n in ITEMS)
        and all(_runstore.read_bytes(proj, f"sources/ext_v1/{n}") == t.encode() for n, t in ITEMS.items()),
        _runstore.files_under(proj, "sources/ext_v1"),
    )
    r = evh("dataset-materialize", "--dataset-id", "ext_v1")
    check(
        "  materialize from the project root: exit 0, hashes verified",
        r.returncode == 0 and "hashes verified" in out(r),
        out(r)[-300:],
    )
    r = evh(
        "dataset-create", "--dataset-id", "ext_v1", "--source-dir", str(outside), "--glob", "*.txt", "--force"
    )
    check("  the same create again is accepted (same content)", r.returncode == 0, out(r)[-300:])

    # refused before anything is written
    _runstore.write_text(proj, "sources/ext_v2/b.txt", "not beta\n")
    r = evh("dataset-create", "--dataset-id", "ext_v2", "--source-dir", str(outside), "--glob", "*.txt")
    check(
        "data/sources/<id>/ holding other content: refused, exit 1, no traceback",
        r.returncode == 1 and "Traceback" not in out(r) and "data/sources/ext_v2" in out(r),
        out(r)[-300:],
    )
    check(
        "  nothing written: no record, the other file as it was, no other item copied",
        not _runstore.exists(proj, "datasets/ext_v2.json")
        and _runstore.files_under(proj, "sources/ext_v2") == ["sources/ext_v2/b.txt"]
        and _runstore.read_text(proj, "sources/ext_v2/b.txt") == "not beta\n",
        _runstore.files_under(proj, "sources/ext_v2"),
    )

    # a manifest of files in an outside folder
    (outside / "m.csv").write_text("item_id,source_path\nfirst,a.txt\nsecond,c.txt\n")
    r = evh(
        "dataset-create",
        "--dataset-id",
        "ext_m1",
        "--source-dir",
        str(outside),
        "--manifest",
        str(outside / "m.csv"),
    )
    check("an outside folder with a manifest: dataset-create", r.returncode == 0, out(r)[-300:])
    rec = record("ext_m1") if r.returncode == 0 else {}
    check(
        "  its record names data/sources/<id> and only the files the manifest names were copied",
        rec.get("source_dir") == "data/sources/ext_m1"
        and _runstore.files_under(proj, "sources/ext_m1") == ["sources/ext_m1/a.txt", "sources/ext_m1/c.txt"],
        (rec.get("source_dir"), _runstore.files_under(proj, "sources/ext_m1")),
    )
    r = evh("dataset-materialize", "--dataset-id", "ext_m1", cwd=proj / "sub")
    check(
        "  materialize from a subfolder: exit 0",
        r.returncode == 0 and "hashes verified" in out(r),
        out(r)[-300:],
    )

    # an absolute record (kept as stored) is read as it says
    d = json.loads(json.dumps(record("ext_v1")))
    d["dataset_id"] = "abs_v1"
    d["source_dir"] = str(outside)
    _runstore.write_text(proj, "datasets/abs_v1.json", json.dumps(d))
    r = evh("dataset-materialize", "--dataset-id", "abs_v1")
    check(
        "a record naming an absolute folder is read there",
        r.returncode == 0 and "hashes verified" in out(r),
        out(r)[-300:],
    )
finally:
    import shutil

    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(outside, ignore_errors=True)

sys.exit(summary())
