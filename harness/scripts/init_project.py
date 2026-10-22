#!/usr/bin/env python3
"""Start a project that uses the harness: the data folders, a .gitignore, and with
--tutorial the GUIDE's kit.

    evh init [DIR] [--tutorial]

DIR defaults to the current directory. Nothing that already exists is overwritten: a file
already there is kept and named, so running it twice, or in a project that has started,
is safe.

  data/sources/  data/configs/  data/goals/   your inputs, arms and goals
  .gitignore     the harness's derived and private paths (materialized copies, the
                 catalog build, caches, .env, the venv)
  tutorial/      with --tutorial: six support tickets, their gold summaries, four arms, a
                 goal and a judge scorer, as docs/GUIDE.md uses them
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
#: The kit is package data in an install (evaluation_harness/tutorial) and a sibling of
#: scripts/ in a checkout (harness/tutorial).
KIT = next((p for p in (HERE / "tutorial", HERE.parent / "tutorial") if (p / "tickets").is_dir()), None)
FOLDERS = ("data/sources", "data/configs", "data/goals")
IGNORE = """\
# evaluation-harness: derived or private, never committed
.venv
.env
.build/
.cache/
data/materialized/
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dir", nargs="?", default=".", help="the project directory (default: here)")
    ap.add_argument("--tutorial", action="store_true", help="add the GUIDE's kit under tutorial/")
    args = ap.parse_args()
    root = Path(args.dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    made, kept = [], []
    for f in FOLDERS:
        (root / f).mkdir(parents=True, exist_ok=True)
    gi = root / ".gitignore"
    if gi.exists():
        kept.append(".gitignore")
    else:
        gi.write_text(IGNORE, encoding="utf-8")
        made.append(".gitignore")
    if args.tutorial:
        if KIT is None:
            print("ERROR: the tutorial kit is not in this installation", file=sys.stderr)
            return 1
        for src in sorted(p for p in KIT.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
            rel = Path("tutorial") / src.relative_to(KIT)
            dst = root / rel
            if dst.exists():
                kept.append(rel.as_posix())
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            made.append(rel.as_posix())
    print(f"project: {root}")
    print(f"  folders  {', '.join(FOLDERS)}")
    if made:
        print(f"  wrote    {len(made)} file(s)" + (f", the tutorial kit under tutorial/" if args.tutorial else ""))
    if kept:
        print(f"  kept     {len(kept)} existing file(s), unchanged: {', '.join(kept[:5])}"
              + (" ..." if len(kept) > 5 else ""))
    print("Next: docs/GUIDE.md step 1, `evh dataset-create`." if args.tutorial
          else "Next: put your inputs in data/sources/<name>/ and freeze them with `evh dataset-create`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
