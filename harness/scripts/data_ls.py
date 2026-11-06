#!/usr/bin/env python3
"""List what the project keeps under data/, in either store (UXS-004: the data page's overview and folders).

evh data-ls                 the store, the settings folders, the other folders, with their file counts
evh data-ls configs         a folder: its sub-folders (a run with its dataset and items), then its files
evh data-ls --find triage   every file whose path holds the text
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _data_page, _jsonout
from evaluation_harness._common import evh_prog


def _size(n: int | None) -> str:
    if n is None:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return ""


def main() -> int:
    """List the project's data: the overview, one folder, or the files a name matches."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("path", nargs="?", default="", help="a folder under data/ (default: the overview)")
    ap.add_argument("--find", metavar="TEXT", help="every file whose path holds TEXT")
    ap.add_argument("--offset", type=int, default=0, help="the first entry of a long folder to list")
    ap.add_argument("--json", action="store_true", help="the answer as one JSON object")
    args = ap.parse_args()
    try:
        with _jsonout.collect("data-ls", args.json):
            if args.find:
                hits = _data_page.search(args.find)
                for p in hits["paths"]:
                    print(p)
                if hits["total"] > len(hits["paths"]):
                    print(f"... and {hits['total'] - len(hits['paths'])} more")
                print(f"{hits['total']} file(s) match {args.find!r}")
                _jsonout.value("search", hits)
            elif not args.path:
                o = _data_page.overview()
                where = f" · {o['database']} ({_size(o['database_bytes'])})" if o["database"] else ""
                print(f"store: {o['store']}{where}")
                print("\nsettings (edit them with evh data-put; delete with evh data-rm)")
                for s in o["settings"]:
                    print(f"  {s['folder']:<16} {s['files']:>6}  {s['kind']}")
                print("\ndata (written by evh commands; read-only here)")
                for d in o["data"]:
                    print(f"  {d['folder']:<16} {d['files']:>6}  {d['kind']}")
                _jsonout.value("overview", o)
            else:
                ls = _data_page.listing(args.path, args.offset)
                for e in ls["entries"]:
                    if e["type"] == "run":
                        done = "" if e["finished"] else "  (not finished)"
                        print(
                            f"  {e['name']}/  run · {e['dataset']} · {e['items']} item(s) · {e['made']}{done}"
                        )
                    elif e["type"] == "folder":
                        print(f"  {e['name']}/  {e['files']} file(s)")
                    else:
                        print(f"  {e['name']}  {_size(e['size'])}  {e['modified']}")
                shown = len(ls["entries"])
                more = (
                    f" (from {ls['offset'] + 1}; --offset {ls['offset'] + shown} for the next)"
                    if ls["total"] > ls["offset"] + shown
                    else ""
                )
                print(f"{ls['path']}: {ls['total']} entr(ies){more}")
                _jsonout.value("listing", ls)
    except _data_page.Refused as exc:
        _data_page.refuse(exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
