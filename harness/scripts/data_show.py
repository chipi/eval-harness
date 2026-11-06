#!/usr/bin/env python3
"""Show one file the project keeps under data/, in either store (UXS-004: the data page's file view).

evh data-show goals/support_triage.yaml          its text, then its size, date, sha256 and kind
evh data-show configs/x.yaml --text              its text only (to edit and put back)
evh data-show configs/x.yaml --fields            a setting's fields, one dotted key a line (what --set takes)
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _data_page, _jsonout, _settings_form
from evaluation_harness._common import die, evh_prog


def main() -> int:
    """Show a file of the project's data."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("path", help="the file, relative to data/")
    ap.add_argument("--text", action="store_true", help="its text only, nothing else")
    ap.add_argument("--fields", action="store_true", help="a setting's fields, one KEY: value a line")
    ap.add_argument("--json", action="store_true", help="the answer as one JSON object")
    args = ap.parse_args()
    try:
        f = _data_page.show(args.path)
    except _data_page.Refused as exc:
        _data_page.refuse(exc)
    if args.fields:
        if not f["editable"]:
            die(f"{f['path']} is not a setting: it has no fields to show (--text shows it)", "bad-argument")
        try:
            values = _settings_form.values_of(f["path"])
        except _data_page.Refused as exc:
            _data_page.refuse(exc)
        with _jsonout.collect("data-show", args.json):
            for key, value in _settings_form.flat(values):
                print(
                    f"{key}: {value if not isinstance(value, (dict, list)) else ('{}' if isinstance(value, dict) else '[]')}"
                )
            print(
                f"\n{f['path']} · {f['setting_kind']} · change a field with evh data-put {f['path']} --set KEY=VALUE"
            )
            _jsonout.value("values", values)
        return 0
    if args.text and not args.json:
        if f["text"] is None:
            die(f"{f['path']} is binary ({f['size']} bytes): it has no text to show", "bad-argument")
        _sys.stdout.write(f["text"])
        return 0
    with _jsonout.collect("data-show", args.json):
        print(f["text"] if f["text"] is not None else f"binary, {f['size']} bytes")
        print(f"\n{f['path']} · {f['size']} bytes · {f['modified']} · sha256 {f['sha256'][:12]}")
        if f["editable"]:
            note = f" · {f['runs_made']} run(s) were made with this config" if "runs_made" in f else ""
            print(
                f"a setting: its fields with --fields; change one with evh data-put {f['path']} --set KEY=VALUE{note}"
            )
        else:
            print(f"written by {f['written_by']}; not edited here")
        _jsonout.value("file", f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
