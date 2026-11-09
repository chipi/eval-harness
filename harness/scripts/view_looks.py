#!/usr/bin/env python3
"""The looks a test set allows (RFC-029): each test set's looks, its next level, its limit and its prior use.

evh looks
evh looks --dataset triage_v1_test --json
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _jsonout, _looks, _store
from evaluation_harness._common import die, evh_prog


def _test_sets() -> list[str]:
    from evaluation_harness._common import _paths  # noqa: PLC0415

    d = _paths()["DATASETS"]
    ids = sorted(p.stem for p in _store.glob(d, "*.json")) if _store.is_dir(d) else []
    return [i for i in ids if _looks.is_test_set(i)]


def main() -> int:
    """List every test set's looks."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", help="one test set (default: every one)")
    ap.add_argument("--json", action="store_true", help="the same as one JSON object (result.values.sets)")
    args = ap.parse_args()
    with _jsonout.collect("looks", args.json):
        sets = [args.dataset] if args.dataset else _test_sets()
        if args.dataset and not _looks.is_test_set(args.dataset):
            die(
                f"{args.dataset} is not a test set (a goal's role: test, or a sealed side of a split)",
                "not-found",
            )
        out = []
        for ds in sets:
            s = _looks.summary(ds)
            out.append(s)
            print(
                f"{ds}: {len({x.get('key') for x in s['looks']})} look(s) of {s['limit']}; the next is look {s['next']}, "
                f"one-sided at {s['next_level']:.4%}"
                + (
                    f"; used {s['prior_use']} time(s) before looks were counted (0.8.0)"
                    if s["prior_use"]
                    else ""
                )
            )
            for x in s["looks"]:
                lv = x.get("level")
                print(
                    f"  look {x.get('number')}  {lv:.4%}  {x.get('what')}  by {(x.get('actor') or {}).get('name', '?')}"
                    f"  {x.get('at') or ''}" + (f"  {x['verdict']}" if x.get("verdict") else "")
                )
        if not sets:
            print(
                "no test sets: a goal's dataset with role: test, or a split's sealed side (dataset-split --seal)"
            )
        _jsonout.value("sets", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
