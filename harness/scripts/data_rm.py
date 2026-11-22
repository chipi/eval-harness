"""Delete a setting, or a whole run, from the project's data, in either store (UXS-004: the data page's delete).

    evh data-rm --path goals/old_goal.yaml --dry-run   what would go
    evh data-rm --path goals/old_goal.yaml             the setting
    evh data-rm --path runs/arm_v1_20261106T101010Z    the run: its record, outputs, scores and rows

Anything else under data/ is written by the harness's own commands and is refused here. A delete cannot be undone.
"""

from __future__ import annotations

from typing import Any

from evaluation_harness import _data_page, _jsonout
from evaluation_harness.ops import legacy


def body(**inputs: Any) -> int:
    """Delete a setting or a run."""
    args = legacy.namespace(inputs, "data-rm")
    try:
        norm, _ = _data_page.resolve(args.path)
        if args.dry_run:
            kind = _data_page.deletable(norm)  # refuses what remove would refuse, deleting nothing
            if kind == "run":
                s = _data_page.run_summary(norm)
                print(
                    f"would delete the run {norm}: {s['files']} file(s), {s['outputs']} output(s), {s['rows']} row(s)"
                )
                _jsonout.value("would_delete", s)
            else:
                print(f"would delete {norm}")
                _jsonout.value("would_delete", {"path": norm})
            return 0
        gone = _data_page.remove(norm)
        if gone["kind"] == "run":
            print(
                f"deleted the run {norm}: {gone['files']} file(s), {gone['outputs']} output(s), {gone['rows']} row(s)"
            )
        else:
            print(f"deleted {norm}")
        _jsonout.value("deleted", gone)
    except _data_page.Refused as exc:
        _data_page.refuse(exc)
    return 0
