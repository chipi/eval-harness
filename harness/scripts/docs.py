#!/usr/bin/env python3
"""Where the harness's own docs are: the ones that ship in the package, and the docs site.

    evh docs [NAME] [--print]

With no name: the shipped docs, with their installed paths, and the docs site's address. With one (upgrading,
runbook, integration; case and .md do not matter): its installed path and its page on the site; --print writes
its text to stdout instead.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys
from pathlib import Path

from evaluation_harness import _store
from evaluation_harness._common import die, evh_prog

HERE = Path(__file__).resolve().parent
SITE = "https://evals.humancopilot.eu/docs/"
#: What ships (package-data in pyproject.toml), and each one's page on the site (mkdocs.yml: harness/<NAME>.md).
SHIPPED = ("UPGRADING", "RUNBOOK", "INTEGRATION")
#: The docs are package data in an install (evaluation_harness/docs) and harness/docs in a checkout.
DOCS = next((p for p in (HERE / "docs", HERE.parent / "docs") if _store.is_file(p / "RUNBOOK.md")), None)


def _url(name: str) -> str:
    return f"{SITE}harness/{name}/"


def main() -> int:
    """List the shipped docs, or locate or print one."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("name", nargs="?", help="one of: " + ", ".join(n.lower() for n in SHIPPED))
    ap.add_argument("--print", action="store_true", dest="show", help="write the doc's text to stdout")
    args = ap.parse_args()
    if DOCS is None:
        die("the docs are not in this installation", "missing-dependency")
    if args.name is None:
        if args.show:
            die("--print needs a name: " + ", ".join(n.lower() for n in SHIPPED), "bad-argument")
        print(f"docs site: {SITE}")
        for n in SHIPPED:
            print(f"  {n.lower():12} {DOCS / (n + '.md')}")
        return 0
    key = args.name.upper().removesuffix(".MD")
    if key not in SHIPPED:
        die(
            f"no doc {args.name!r}; the shipped ones are: " + ", ".join(n.lower() for n in SHIPPED),
            "not-found",
        )
    path = DOCS / f"{key}.md"
    if args.show:
        sys.stdout.write(_store.read_text(path, encoding="utf-8"))
        return 0
    print(f"{path}\n{_url(key)}")
    return 0


if __name__ == "__main__":
    from evaluation_harness._console import degrade_unencodable

    degrade_unencodable()
    sys.exit(main())
