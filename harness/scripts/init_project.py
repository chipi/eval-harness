#!/usr/bin/env python3
"""Start a project that uses the harness: its folders, a .gitignore, AGENTS.md, and the GUIDE's kit with --tutorial.

    evh init --store files|sqlite [DIR] [--tutorial]

--store is required: a project keeps its data in files or in one database, two equal choices (below), written into
the project's config.yaml. DIR defaults to the current directory. Nothing that already exists is overwritten: a file
already there is kept and named, so running it twice, or in a project that has started,
is safe.

  config.yaml    `store: files` or `store: sqlite`, the choice
  data/sources/  data/systems/  data/goals/  data/fields/   your inputs, systems, goals and item fields
  .gitignore     the harness's derived and private paths (materialized copies, the
                 catalog build, caches, .env, the venv)
  AGENTS.md      how an agent works in the project: the rules, the loop, how to read results
                 (CLAUDE.md beside it imports it, for Claude Code)
  prompts/judge_prompt_example.txt   an example prompt for an LLM judge to copy for your first judge scorer;
                 it must name the scorer's task.dimensions
  tutorial/      with --tutorial: six support tickets, their gold summaries, four arms, a
                 goal and a judge scorer, as docs/GUIDE.md uses them
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import os
import sys
from pathlib import Path

from evaluation_harness import _common, _store
from evaluation_harness._common import die, evh_prog

HERE = Path(__file__).resolve().parent


# Looked up in main, after the store is named: `_store` asks for it, and a package file is read the same in either.
def _kit() -> Path | None:
    """The tutorial kit: package data in an install (evaluation_harness/tutorial), a sibling of scripts/ in a
    checkout (harness/tutorial)."""
    return next(
        (p for p in (HERE / "tutorial", HERE.parent / "tutorial") if _store.is_dir(p / "tickets")), None
    )


def _agents() -> Path | None:
    """The folder of AGENTS.md for a new project: package data in an install (evaluation_harness/project_kit), a
    sibling of scripts/ in a checkout (harness/project_kit)."""
    return next(
        (p for p in (HERE / "project_kit", HERE.parent / "project_kit") if _store.is_file(p / "AGENTS.md")),
        None,
    )


FOLDERS = ("data/sources", "data/systems", "data/goals", "data/fields")
# An example of an LLM judge's prompt, to copy beside a scorer that names the same dimensions.
JUDGE_EXAMPLE = "prompts/judge_prompt_example.txt"
IGNORE = """\
# evaluation-harness: derived or private, never committed
.venv
.env
.build/
.cache/
data/materialized/
__pycache__/
# runs: each run's record, outputs and scores are the results; the pass's checkpoint is not (a throwaway pass is
# `evh run --scratch`, under .build/)
data/runs/*/*
!data/runs/*/run.json
!data/runs/*/outputs.jsonl
!data/runs/*/scores/
data/runs/*/scores/*/*
!data/runs/*/scores/*/score.json
!data/runs/*/scores/*/metrics.json
!data/runs/*/scores/*/predictions.jsonl
# the sqlite store (store: sqlite): the project's data in one database, not in git
data/project.sqlite*
"""


STORE_LINE = {
    "files": "store: files  # every run, label and score a file under data/, in git (evh data-migrate switches)",
    "sqlite": "store: sqlite  # the data in one database, data/project.sqlite, out of git (evh data-migrate switches)",
}


def _named_store(cfg: Path) -> str | None:
    """The `store` a config.yaml names, None when it names none."""
    import yaml  # noqa: PLC0415

    try:
        doc = yaml.safe_load(_store.read_text(cfg, encoding="utf-8")) or {}
    except yaml.YAMLError:
        die(f"{cfg} is not valid YAML", "invalid-file")
    named = doc.get("store") if isinstance(doc, dict) else None
    return str(named) if named else None


def main() -> int:
    """Initialize a new eval project."""
    ap = argparse.ArgumentParser(
        prog=evh_prog(),
        description=f"{__doc__.splitlines()[0]}\n\n--store is required: {_common.STORE_CHOICE}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("dir", nargs="?", default=".", help="the project directory (default: here)")
    ap.add_argument("--store", help="where the project's data lives: files or sqlite (required, no default)")
    ap.add_argument("--tutorial", action="store_true", help="add the GUIDE's kit under tutorial/")
    args = ap.parse_args()
    if args.store is None:
        die(f"--store is required.\n{_common.STORE_CHOICE}", "bad-argument")
    if args.store not in _common.STORES:
        die(f"--store {args.store!r} is not a store.\n{_common.STORE_CHOICE}", "bad-argument")
    # The new project's store, for everything init does below (a package file is read through `_store` too).
    os.environ["EVAL_STORE"] = args.store
    root = Path(args.dir).resolve()
    cfg = root / "config.yaml"
    if _store.exists(cfg):
        named = _named_store(cfg)
        if named not in (None, args.store):
            die(
                f"{cfg} names `store: {named}`, not {args.store}; `evh data-migrate` moves the data, init does not",
                "mismatch",
            )
    _store.mkdir(root, parents=True, exist_ok=True)
    made, kept = [], []
    # data/ is a folder on disk in either store: the database lives in it, and a command run from a subfolder finds
    # the project by it. Its folders are folders only in the files store (in the database a folder is a key prefix).
    _store.data_folder(root)
    # Every write below is the new project's, wherever init runs from: in a SQLite project the store keys a path by the
    # project it is in, and `evh init elsewhere` run inside another project wrote into that one's database.
    os.environ["EVAL_HOME"] = str(root)
    for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
        os.environ.pop(k, None)
    from evaluation_harness import _outputs  # noqa: PLC0415

    _common.project_root.cache_clear()
    _common._paths.cache_clear()
    _outputs.reset()
    for f in FOLDERS:
        _store.mkdir(root / f, parents=True, exist_ok=True)
    in_db = args.store == "sqlite"
    from evaluation_harness import _format  # noqa: PLC0415

    if _store.exists(_format.path(root / "data")):
        kept.append(f"data/{_format.NAME}")
    else:
        _format.stamp(data=root / "data")
        made.append(f"data/{_format.NAME}")
    if _store.exists(cfg) and _named_store(cfg) == args.store:
        kept.append("config.yaml")
    else:
        # A config.yaml that names no store keeps what it has (the catalog's adapter, say) and gains the line.
        had = _store.read_text(cfg, encoding="utf-8") if _store.exists(cfg) else ""
        if had and not had.endswith("\n"):
            had += "\n"
        _store.write_text(cfg, f"{had}{STORE_LINE[args.store]}\n", encoding="utf-8")
        made.append("config.yaml")
    gi = root / ".gitignore"
    if _store.exists(gi):
        kept.append(".gitignore")
    else:
        _store.write_text(gi, IGNORE, encoding="utf-8")
        made.append(".gitignore")
    agents = _agents()
    if agents is None:
        die("AGENTS.md is not in this installation", "missing-dependency")
    for name, text in (
        ("AGENTS.md", _store.read_text(agents / "AGENTS.md", encoding="utf-8")),
        ("CLAUDE.md", "@AGENTS.md\n"),
        (JUDGE_EXAMPLE, _store.read_text(agents / "judge_prompt.txt", encoding="utf-8")),
    ):
        dst = root / name
        if _store.exists(dst):
            kept.append(name)
        else:
            _store.mkdir(dst.parent, parents=True, exist_ok=True)
            _store.write_text(dst, text, encoding="utf-8")
            made.append(name)
    if args.tutorial:
        kit = _kit()
        if kit is None:
            die("the tutorial kit is not in this installation", "missing-dependency")
        for src in sorted(
            p for p in _store.rglob(kit, "*") if _store.is_file(p) and "__pycache__" not in p.parts
        ):
            rel = Path("tutorial") / src.relative_to(kit)
            dst = root / rel
            if _store.exists(dst):
                kept.append(rel.as_posix())
                continue
            _store.mkdir(dst.parent, parents=True, exist_ok=True)
            _store.copy_file(src, dst)
            made.append(rel.as_posix())
    print(f"project: {root}")
    if in_db:
        print("  store    sqlite: the project's data goes into data/project.sqlite")
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
