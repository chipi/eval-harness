"""Create or change a setting under data/, in either store, checked first (UXS-004: the data page's form).

    evh data-put --path systems/x.yaml --set params.sentences=2      one field, as the form's Save: the file's
    evh data-put --path goals/g.yaml --set datasets.0.role=test --unset context   comments and the rest are kept
    evh data-put --path goals/support_triage.yaml --file goal.yaml --check   only check a whole file: it parses,
                                                                       matches its schema, its id is its file name
    evh data-put --path goals/support_triage.yaml --file goal.yaml   check it, then save it (nothing saved on a problem)
    evh data-put --path systems/new_system.yaml --file arm.yaml --new   refuse a name already taken

KEY is a dotted path (datasets.0.role: a list's item by its number); VALUE is read as YAML (3, 0.5, true, null, or
text). A missing group or the next item of a list is made.

A setting is a system, a goal, a fieldset, a judge scorer, a model record, a failure-mode list or the validate
policy; anything else under data/ is written by the harness's own commands and is refused here. `--file -` reads the
text from standard input.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from evaluation_harness import _data_page, _jsonout, _settings_form, _store
from evaluation_harness._common import die
from evaluation_harness.ops import legacy


def body(**inputs: Any) -> int:
    """Check, then save, one setting of the project."""
    args = legacy.namespace(inputs, "data-put")
    if (args.file is None) == (not (args.set or args.unset)):
        die("give a FILE, or fields with --set / --unset (not both)", "bad-argument")
    if args.file is None:
        return _fields(args)
    if str(args.file) == "-":
        text = sys.stdin.read()
    else:
        src = Path(args.file)
        if not _store.is_file(src):
            die(f"no file {args.file}", "not-found")
        text = _store.read_text(src)
    try:
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


def _fields(args: Any) -> int:
    """--set / --unset: the form's Save, a field at a time."""
    try:
        norm, f = _data_page.resolve(args.path)
        exists = _store.is_file(f)
        if args.new and exists:
            raise _data_page.Refused(f"{norm} exists: open it to edit it.", "would-overwrite")
        if not exists and not args.new:
            raise _data_page.Refused(f"No file {norm} in the project's data (--new creates it).", "not-found")
        if _data_page.kind_of(norm) != "setting":
            raise _data_page.Refused(_data_page._not_edited(norm), "not-allowed")
        values = _settings_form.set_values(
            _settings_form.values_of(norm) if exists else {},
            list(args.set.items()),
            args.unset,
            _settings_form.schema_of(_settings_form.folder_of(norm)),
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
