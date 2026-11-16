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

import argparse
import os
import shutil
import subprocess  # nosec B404 - git status, read-only; this command again on the scratch copy
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _format, _jsonout, _store, migrations
from evaluation_harness._common import evh_prog


def _backup() -> None:
    """The undo before the first change: a copy of the database, or the uncommitted changes named."""
    if _common.store() == "sqlite":
        db = _store.db_path()
        if db.is_file():
            _store.close()
            copy = db.with_name(
                f"{db.name}.before-format-{_format.FORMAT}-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
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
        }
        done = subprocess.run(  # nosec B603 - this script again, fixed arguments, on the copy
            [sys.executable, str(_Path(__file__).resolve()), "--scratch-copy"],
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


def main() -> int:
    """Check the format, or run the steps the data needs."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    how = ap.add_mutually_exclusive_group()
    how.add_argument(
        "--check", action="store_true", help="only compare the data's format with this release's"
    )
    how.add_argument("--dry-run", action="store_true", help="say what each step would change; write nothing")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument("--scratch-copy", action="store_true", help=argparse.SUPPRESS)  # --dry-run's child
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    if args.scratch_copy:  # the steps for real, on the copy --dry-run made: no header, no backup
        have = _format.data_format()
        for m in _todo(have):
            print(f"{m.NUMBER}: {m.ABOUT}")
            m.run(False)
            _format.stamp(m.NUMBER)
        return 0
    with _jsonout.collect("migrate", args.json, live=sys.stderr):
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
        _backup()
        for m in todo:
            print(f"{m.NUMBER}: {m.ABOUT}")
            m.run(False)
            _format.stamp(m.NUMBER)
        print(f"brought the data to format {todo[-1].NUMBER}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
