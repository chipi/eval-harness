#!/usr/bin/env python3
"""Create or change a setting under data/, in either store, checked first (UXS-004: the data page's editor).

    evh data-put goals/support_triage.yaml goal.yaml --check   only check it: it parses, matches its schema, its id
                                                                is its file name
    evh data-put goals/support_triage.yaml goal.yaml           check it, then save it (nothing saved on a problem)
    evh data-put configs/new_arm.yaml arm.yaml --new           refuse a name already taken

A setting is an arm config, a goal, a fieldset, a judge scorer, a model record, a failure-mode list or the validate
policy; anything else under data/ is written by the harness's own commands and is refused here. FILE `-` reads the
text from standard input.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _data_page, _jsonout, _store
from evaluation_harness._common import die, evh_prog


def main() -> int:
    """Check, then save, one setting of the project."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "path", help="the setting, relative to data/ (goals/x.yaml, configs/x.yaml, validate.json, ...)"
    )
    ap.add_argument("file", help="the file holding its new text, or - for standard input")
    ap.add_argument("--check", action="store_true", help="only check it; save nothing")
    ap.add_argument("--new", action="store_true", help="refuse a setting that exists already")
    ap.add_argument("--json", action="store_true", help="the answer as one JSON object")
    args = ap.parse_args()
    if args.file == "-":
        text = _sys.stdin.read()
    else:
        src = _Path(args.file)
        if not _store.is_file(src):
            die(f"no file {args.file}", "not-found")
        text = _store.read_text(src)
    try:
        with _jsonout.collect("data-put", args.json):
            if args.check:
                problems = _data_page.check(args.path, text)
                for p in problems:
                    print(f"  {p}")
                print(
                    f"{args.path}: "
                    + (
                        f"passes the check: {_data_page.checked(args.path)}"
                        if not problems
                        else f"{len(problems)} problem(s)"
                    )
                )
                _jsonout.value("problems", problems)
                return 0 if not problems else 1
            f = _data_page.put(args.path, text, new=args.new)
            print(f"saved {f['path']} · {f['size']} bytes · sha256 {f['sha256'][:12]}")
            _jsonout.value("file", f)
    except _data_page.Refused as exc:
        die(str(exc), exc.kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
