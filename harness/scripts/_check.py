"""The test scripts' one `check` and their verdict.

    from evaluation_harness._check import check, summary
    check("what is claimed", condition, detail_shown_on_failure)
    sys.exit(summary())

A script that ran no checks fails. Before this, most test scripts kept their own copy of
`check` and ended with `all(...)`, which is True for an empty list: one that imported nothing
or skipped every branch reported green while asserting nothing.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

#: (label, passed) for every check this process made.
results: list[tuple[str, bool]] = []


def check(label: str, cond: object, detail: object = "") -> bool:
    """Record and print one check; the detail is shown only when it fails."""
    passed = bool(cond)
    results.append((label, passed))
    print(f"  {'ok  ' if passed else 'FAIL'} {label}" + (f"  ({detail})" if detail and not passed else ""))
    return passed


def summary(noun: str = "assertions") -> int:
    """Print the tally and the failures; the exit code: 1 if any failed or none ran."""
    failed = [label for label, passed in results if not passed]
    if not results:
        print(f"FAIL  no {noun} ran at all: a check that asserts nothing must not pass")
        return 1
    print(f"\n{len(results) - len(failed)}/{len(results)} {noun} passed")
    if failed:
        print("FAILED:", *failed, sep="\n  ")
    return 1 if failed else 0
