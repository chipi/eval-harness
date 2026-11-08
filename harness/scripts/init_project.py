#!/usr/bin/env python3
"""Start a project that uses the harness: its folders, a .gitignore, AGENTS.md, and the GUIDE's kit with --tutorial.

    evh init [DIR] [--tutorial]

DIR defaults to the current directory. Nothing that already exists is overwritten: a file
already there is kept and named, so running it twice, or in a project that has started,
is safe.

  data/sources/  data/configs/  data/goals/  data/fields/   your inputs, arms, goals and item fields
  .gitignore     the harness's derived and private paths (materialized copies, the
                 catalog build, caches, .env, the venv)
  AGENTS.md      how an agent works in the project: the rules, the loop, how to read results
                 (CLAUDE.md beside it imports it, for Claude Code)
  tutorial/      with --tutorial: six support tickets, their gold summaries, four arms, a
                 goal and a judge scorer, as docs/GUIDE.md uses them
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys
from pathlib import Path

from evaluation_harness import _common, _store
from evaluation_harness._common import die, evh_prog

HERE = Path(__file__).resolve().parent
#: The kit is package data in an install (evaluation_harness/tutorial) and a sibling of
#: scripts/ in a checkout (harness/tutorial).
KIT = next((p for p in (HERE / "tutorial", HERE.parent / "tutorial") if _store.is_dir(p / "tickets")), None)
#: AGENTS.md for a new project: package data in an install (evaluation_harness/project_kit), a
#: sibling of scripts/ in a checkout (harness/project_kit).
AGENTS = next(
    (p for p in (HERE / "project_kit", HERE.parent / "project_kit") if _store.is_file(p / "AGENTS.md")), None
)
FOLDERS = ("data/sources", "data/configs", "data/goals", "data/fields")
IGNORE = """\
# evaluation-harness: derived or private, never committed
.venv
.env
.build/
.cache/
data/materialized/
__pycache__/
# throwaway passes (smoke runs, sweeps): never results, never in the catalog
data/runs-smoke*/
data/runs-tune*/
# the sqlite store (store: sqlite): the project's data in one database, not in git
data/project.sqlite*
"""


def main() -> int:
    """Initialize a new eval project."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("dir", nargs="?", default=".", help="the project directory (default: here)")
    ap.add_argument("--tutorial", action="store_true", help="add the GUIDE's kit under tutorial/")
    args = ap.parse_args()
    root = Path(args.dir).resolve()
    _store.mkdir(root, parents=True, exist_ok=True)
    made, kept = [], []
    # data/ is a folder on disk in either store: the database lives in it, and a command run from a subfolder finds
    # the project by it. Its folders are folders only in the files store (in the database a folder is a key prefix).
    _store.data_folder(root)
    for f in FOLDERS:
        _store.mkdir(root / f, parents=True, exist_ok=True)
    in_db = _common.store() == "sqlite"
    gi = root / ".gitignore"
    if _store.exists(gi):
        kept.append(".gitignore")
    else:
        _store.write_text(gi, IGNORE, encoding="utf-8")
        made.append(".gitignore")
    if AGENTS is None:
        die("AGENTS.md is not in this installation", "missing-dependency")
    for name, text in (
        ("AGENTS.md", _store.read_text(AGENTS / "AGENTS.md", encoding="utf-8")),
        ("CLAUDE.md", "@AGENTS.md\n"),
    ):
        dst = root / name
        if _store.exists(dst):
            kept.append(name)
        else:
            _store.write_text(dst, text, encoding="utf-8")
            made.append(name)
    if args.tutorial:
        if KIT is None:
            die("the tutorial kit is not in this installation", "missing-dependency")
        for src in sorted(
            p for p in _store.rglob(KIT, "*") if _store.is_file(p) and "__pycache__" not in p.parts
        ):
            rel = Path("tutorial") / src.relative_to(KIT)
            dst = root / rel
            if _store.exists(dst):
                kept.append(rel.as_posix())
                continue
            _store.mkdir(dst.parent, parents=True, exist_ok=True)
            _store.copy_file(src, dst)
            made.append(rel.as_posix())
    print(f"project: {root}")
    if in_db:
        print("  store    sqlite: the project's data goes into data/project.sqlite, made on the first write")
    else:
        print(f"  folders  {', '.join(FOLDERS)}")
    if made:
        print(
            f"  wrote    {len(made)} file(s)"
            + (", the tutorial kit under tutorial/" if args.tutorial else "")
        )
    if kept:
        print(
            f"  kept     {len(kept)} existing file(s), unchanged: {', '.join(kept[:5])}"
            + (" ..." if len(kept) > 5 else "")
        )
    print(
        "Next: docs/GUIDE.md step 1, `evh dataset-create`."
        if args.tutorial
        else "Next: put your inputs in data/sources/<name>/ and freeze them with `evh dataset-create`."
    )
    print("An agent working here: read AGENTS.md first.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
