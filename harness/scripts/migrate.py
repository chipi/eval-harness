#!/usr/bin/env python3
"""Bring a project's data to this release's format (RFC-032), by its numbered steps.

    evh migrate --check       the data's format against this release's; exit 1 when they differ (a deploy's gate)
    evh migrate --dry-run     what each step would change; nothing written to the project
    evh migrate               write it

The project's format is one number, `data/project.yaml`'s `format` (0 when it has none: the data releases before
0.8.0 wrote). Each step in `evaluation_harness.migrations` brings it one format on, and the format is recorded after
each, so a step that fails leaves the project at the last one that held. Before the first change a SQLite project's
database is copied beside it (the undo); a files project's undo is git, and uncommitted changes under data/ are named
first. There is no way back down: a rollback restores that copy, or git.

A dry run runs the real steps on a scratch copy of the project's data (and of config.yaml and the config folders it
names) in the project's own ignored `.build/`, prints each step's counts from that, and deletes the copy: a later step
reads what an earlier one wrote, so no step can be run on the untouched data. The copy is as large as the data, on the
project's disk, for the duration. The project itself is not written.

Moving the data between files and the SQLite database is `evh data-migrate`, not a format step.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import os
import shutil
import subprocess  # nosec B404 - git status, read-only; this command again on the scratch copy
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _format, _jsonout, _store, migrations
from evaluation_harness.ops import legacy

#: Set by a dry run to its scratch copy (EVAL_HOME of the child): what lets this file run the steps there.
SCRATCH_MARK = "EVH_MIGRATE_SCRATCH_COPY"


def _backup(have: int) -> None:
    """The undo before the first change: a copy of the database, or the uncommitted changes named. The copy is
    `project.sqlite-before-format-<the data's format>-<when>` beside the database: a name the store keeps out of the
    project's data (as its -wal and -shm), so validate does not take it for a stray file nor data-migrate move it in."""
    if _common.store() == "sqlite":
        db = _store.db_path()
        if db.is_file():
            _store.close()
            copy = db.with_name(
                f"{db.name}-before-format-{have}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
            )
            shutil.copy2(db, copy)
            print(f"backup: {copy} (restore it to undo)")
        return
    try:
        out = subprocess.run(  # nosec B603 B607 - git, fixed arguments
            ["git", "status", "--porcelain", "--", str(_common.DATA)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=_common.DATA,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("backup: git not found; the files have no undo but a copy you make", file=sys.stderr)
        return
    if out.returncode != 0:
        print("backup: data/ is not in git; the files have no undo but a copy you make", file=sys.stderr)
    elif out.stdout.strip():
        n = len(out.stdout.splitlines())
        print(
            f"backup: {n} uncommitted change(s) under data/: git cannot tell them from the migration's",
            file=sys.stderr,
        )


def _todo(have: int) -> list[Any]:
    """The steps the data needs. A step may be `unfinished` for data already stamped with its number (format 7 of an
    early build kept a SQLite project's rows where the final one does not): it runs again for that project, and only
    that."""
    return [
        m
        for m in migrations.steps()
        if have < m.NUMBER or (have == m.NUMBER and getattr(m, "unfinished", lambda: False)())
    ]


def _extras(root: Path, data: Path) -> list[Path]:
    """What the steps read or write outside data/: the folders config.yaml's `configs:` lists and the files
    validate.json's `configs` / `systems` globs name (both inside the project)."""
    import json  # noqa: PLC0415

    from evaluation_harness.migrations import m0003_systems  # noqa: PLC0415

    found = list(m0003_systems._config_dirs())
    policy = data / "validate.json"
    if _store.is_file(policy):
        doc = json.loads(_store.read_text(policy, encoding="utf-8"))
        for key in ("configs", "systems"):
            for pattern in doc.get(key) or []:
                found += [f for f in root.glob(pattern) if f.is_file()]
    return [f for f in found if f.resolve().is_relative_to(root) and not f.resolve().is_relative_to(data)]


def _scratch_copy(scratch: Path, root: Path, data: Path) -> Path:
    """Copy what the steps read into `scratch` as a project of its own, laid out as the project is; the data folder's
    path relative to the project's root is returned (for EVAL_DATA_DIR)."""
    in_root = data.is_relative_to(root)
    rel = data.relative_to(root) if in_root else Path("data")
    if _common.store() == "sqlite":
        _store.close()  # the database's write-ahead log settled into the file before it is copied
    shutil.copytree(data, scratch / rel, symlinks=True)
    cfg = root / "config.yaml"
    if cfg.is_file():
        shutil.copy2(cfg, scratch / "config.yaml")
    for src in _extras(root, data):
        dst = scratch / src.resolve().relative_to(root)
        if src.is_dir():
            shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return rel


def _dry_run(todo: list[Any]) -> None:
    """The real steps on a scratch copy of the project, each one's counts as it printed them; the copy is deleted."""
    root, data = _common.ROOT.resolve(), _common.DATA.resolve()
    build = root / ".build"
    made_build = not build.exists()
    build.mkdir(exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="migrate-dry-run-", dir=build)).resolve()
    try:
        print(
            f"dry run on a copy of the data in {scratch}, as large as the data until it is deleted; "
            "the project is not written"
        )
        rel = _scratch_copy(scratch, root, data)
        env = {
            **os.environ,
            "EVAL_HOME": str(scratch),
            "EVAL_DATA_DIR": str(rel),
            "EVAL_STORE": _common.store(),
            SCRATCH_MARK: str(scratch),
        }
        done = subprocess.run(  # nosec B603 - this script again, fixed arguments, on the copy
            [sys.executable, str(_Path(__file__).resolve())],
            env=env,
            cwd=scratch,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=None,
            check=False,
        )
        out, err = (t.replace(str(scratch), str(root)) for t in (done.stdout, done.stderr))
        sys.stdout.write(out)
        if done.returncode:
            raise SystemExit(err.strip() or f"the dry run's steps failed (exit {done.returncode})")
        if err.strip():
            print(err.rstrip(), file=sys.stderr)
        print(f"would bring the data to format {todo[-1].NUMBER}")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        if made_build:
            try:
                build.rmdir()
            except OSError:
                pass


def body(**inputs: Any) -> int:
    """Check the format, or run the steps the data needs."""
    args = legacy.namespace(inputs, "migrate")
    have = _format.data_format()
    _jsonout.values({"format": have, "release_format": _format.FORMAT})
    print(f"data format {have}; this release reads {_format.FORMAT}")
    todo = _todo(have)
    if args.check or have > _format.FORMAT:
        _format.require()
        if args.check and todo:
            _common.die(
                f"step {todo[0].NUMBER} is not finished for this project ({todo[0].ABOUT}): run evh migrate",
                "old-format",
            )
        return 0
    if not todo:
        print("nothing to do")
        return 0
    if args.dry_run:
        _dry_run(todo)
        return 0
    # The steps rewrite the database (the last drops a table and VACUUMs): a server or a run that has it open would
    # go on with what it read before, or be cut off mid-write. As a job the server lets go when it sees the migration.
    if _common.store() == "sqlite" and _store.held_after(30 if os.environ.get("EVH_JOB") else 0):
        _common.die(
            f"{_store.db_path().name} is open in another process (a catalog-serve, a run): stop it first, or run "
            "the migration as a job (evh jobs-start migrate), which the server lets go of the database for",
            "not-allowed",
        )
    _backup(have)
    for m in todo:
        print(f"{m.NUMBER}: {m.ABOUT}")
        m.run(False)
        _format.stamp(m.NUMBER)
    print(f"brought the data to format {todo[-1].NUMBER}")
    return 0


def _steps_on_copy() -> int:
    """The steps for real, on the copy a dry run made (this file run by it): no header, no backup. Refused unless the
    dry run named this project as its copy, so the file run by hand never writes a project without its backup."""
    if not os.environ.get(SCRATCH_MARK) or os.environ.get(SCRATCH_MARK) != os.environ.get("EVAL_HOME"):
        _common.die("this file is the dry run's own: run `evh migrate`", "not-allowed")
    have = _format.data_format()
    for m in _todo(have):
        print(f"{m.NUMBER}: {m.ABOUT}")
        m.run(False)
        _format.stamp(m.NUMBER)
    return 0


if __name__ == "__main__":
    raise SystemExit(_steps_on_copy())
