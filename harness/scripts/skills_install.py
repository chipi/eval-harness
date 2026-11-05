#!/usr/bin/env python3
"""Copy the harness's agent skills into a project, for an agent harness to load.

    evh skills-install [--target DIR] [--force]

Each skill is a folder with a SKILL.md (the Agent Skills format: a name, a description that says
when to use it, the procedure). The default target is .claude/skills/ in the current directory;
any agent's skill directory works. A copy you changed is kept unless --force: re-running it after
an upgrade brings the unchanged ones up to date and names the ones it left alone.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

from evaluation_harness._common import die, evh_prog

HERE = Path(__file__).resolve().parent
#: The skills are package data in an install (evaluation_harness/skills) and a sibling of
#: scripts/ in a checkout (harness/skills).
SKILLS = next((p for p in (HERE / "skills", HERE.parent / "skills") if any(p.glob("*/SKILL.md"))), None)
#: Where a copy records what it was copied from, so a later run can tell "unchanged" from "edited".
STAMP = ".evh-skill.sha256"


def _digest(folder: Path) -> str:
    """One hash over a skill's files (not the stamp), path by path."""
    h = hashlib.sha256()
    for f in sorted(p for p in folder.rglob("*") if p.is_file() and p.name != STAMP):
        h.update(f.relative_to(folder).as_posix().encode() + b"\0" + f.read_bytes() + b"\0")
    return h.hexdigest()


def main() -> int:
    """Install the skills; print what was written, updated and kept."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--target", type=Path, default=Path(".claude/skills"), help="default: .claude/skills")
    ap.add_argument("--force", action="store_true", help="overwrite copies you changed")
    args = ap.parse_args()
    if SKILLS is None:
        die("the skills are not in this installation", "missing-dependency")
    args.target.mkdir(parents=True, exist_ok=True)
    wrote, updated, same, kept = [], [], [], []
    for src in sorted(p.parent for p in SKILLS.glob("*/SKILL.md")):
        dst = args.target / src.name
        new = _digest(src)
        if dst.exists():
            stamp = dst / STAMP
            was = stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else ""
            if _digest(dst) == new:
                same.append(src.name)
                continue
            if _digest(dst) != was and not args.force:
                kept.append(src.name)  # edited after it was installed
                continue
            shutil.rmtree(dst)
            updated.append(src.name)
        else:
            wrote.append(src.name)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
        (dst / STAMP).write_text(new + "\n", encoding="utf-8")
    print(f"skills: {args.target}")
    for word, names in (("wrote", wrote), ("updated", updated), ("current", same)):
        if names:
            print(f"  {word:8} {', '.join(names)}")
    if kept:
        print(f"  kept     {', '.join(kept)}: changed since installed; --force replaces them")
    return 0


if __name__ == "__main__":
    sys.exit(main())
