#!/usr/bin/env python3
"""Create or change a setting under data/, in either store, checked first (UXS-004: the data page's form).

    evh data-put systems/x.yaml --set params.sentences=2       one field, as the form's Save: the file's comments
    evh data-put goals/g.yaml --set datasets.0.role=test --unset context   and the rest of it are kept
    evh data-put goals/support_triage.yaml goal.yaml --check   only check a whole file: it parses, matches its
                                                                schema, its id is its file name
    evh data-put goals/support_triage.yaml goal.yaml           check it, then save it (nothing saved on a problem)
    evh data-put systems/new_system.yaml arm.yaml --new           refuse a name already taken

KEY is a dotted path (datasets.0.role: a list's item by its number); VALUE is read as YAML (3, 0.5, true, null, or
text). A missing group or the next item of a list is made.

A setting is a system, a goal, a fieldset, a judge scorer, a model record, a failure-mode list or the validate
policy; anything else under data/ is written by the harness's own commands and is refused here. FILE `-` reads the
text from standard input.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _data_page, _jsonout, _settings_form, _store
from evaluation_harness._common import die, evh_prog


def main() -> int:
    """Check, then save, one setting of the project."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "path", help="the setting, relative to data/ (goals/x.yaml, systems/x.yaml, validate.json, ...)"
    )
    ap.add_argument(
        "file", nargs="?", type=_Path, help="the file holding its whole new text, or - for standard input"
    )
    ap.add_argument(
        "--set", action="append", default=[], metavar="KEY=VALUE", help="set one field (repeatable)"
    )
    ap.add_argument(
        "--unset", action="append", default=[], metavar="KEY", help="remove one field (repeatable)"
    )
    ap.add_argument("--check", action="store_true", help="only check it; save nothing")
    ap.add_argument("--new", action="store_true", help="refuse a setting that exists already")
    ap.add_argument("--json", action="store_true", help="the answer as one JSON object")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    args = ap.parse_args()
    if (args.file is None) == (not (args.set or args.unset)):
        die("give a FILE, or fields with --set / --unset (not both)", "bad-argument")
    if args.file is None:
        return _fields(args)
    if str(args.file) == "-":
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
        _data_page.refuse(exc)
    return 0


def _fields(args: argparse.Namespace) -> int:
    """--set / --unset: the form's Save, a field at a time."""
    import yaml  # noqa: PLC0415

    sets = []
    for item in args.set:
        key, eq, raw = item.partition("=")
        if not eq or not key.strip():
            die(f"--set {item!r}: write it KEY=VALUE", "bad-argument")
        try:
            value = _settings_form.plain(yaml.safe_load(raw)) if raw.strip() else ""
        except yaml.YAMLError:
            value = raw
        sets.append((key.strip(), value))
    try:
        with _jsonout.collect("data-put", args.json):
            norm, f = _data_page.resolve(args.path)
            exists = _store.is_file(f)
            if args.new and exists:
                raise _data_page.Refused(f"{norm} exists: open it to edit it.", "would-overwrite")
            if not exists and not args.new:
                raise _data_page.Refused(
                    f"No file {norm} in the project's data (--new creates it).", "not-found"
                )
            if _data_page.kind_of(norm) != "setting":
                raise _data_page.Refused(_data_page._not_edited(norm), "not-allowed")
            values = _settings_form.set_values(
                _settings_form.values_of(norm) if exists else {}, sets, args.unset
            )
            problems = _settings_form.problems(norm, values)
            for p in problems:
                print(f"  {'.'.join(map(str, p['path'])) or '(top)'}: {p['message']}")
            _jsonout.value("problems", problems)
            if args.check or problems:
                print(
                    f"{norm}: "
                    + (f"{len(problems)} problem(s); nothing saved" if problems else "passes the check")
                )
                return 1 if problems else 0
            saved = _settings_form.save(norm, values, new=args.new)
            print(
                f"{norm}: nothing changed"
                if saved["unchanged"]
                else f"saved {saved['path']} · {saved['size']} bytes · sha256 {saved['sha256'][:12]}"
            )
            _jsonout.value("file", saved)
    except _data_page.Refused as exc:
        _data_page.refuse(exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
