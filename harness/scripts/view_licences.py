#!/usr/bin/env python3
"""The licences a dataset can name, a line each: pick one for `--licence` (PLAN_0.8.0 E2).

    evh licences                  every one, by SPDX id
    evh licences --search sa      those whose id or line matches
    evh licences --json

`unknown` is for a source that states none; `LicenseRef-<name>` for a licence of its own, described in the card.
A line says what the licence lets a user do; the text at its URL is what binds.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json

from evaluation_harness._common import evh_prog
from evaluation_harness._licences import LICENCES, UNKNOWN, url


def main() -> int:
    """Print the licence list, or the ones matching --search."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.split("\n\n")[0])
    ap.add_argument("--search", help="keep the licences whose id or line contains this (any case)")
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args()
    q = (args.search or "").lower()
    rows = [(i, line) for i, line in LICENCES if q in i.lower() or q in line.lower()]
    if args.json:
        print(
            json.dumps({"licences": [{"id": i, "allows": line, "url": url(i)} for i, line in rows]}, indent=2)
        )
        return 0
    if not rows:
        print(
            f"No licence matches {args.search!r}. `{UNKNOWN}` when the source states none; LicenseRef-<name> for your own."
        )
        return 0
    width = max(len(i) for i, _ in rows)
    for i, line in rows:
        print(f"{i:<{width}}  {line}")
    print(f"\n{UNKNOWN:<{width}}  the source states no licence")
    print(f"{'LicenseRef-<name>':<{width}}  a licence of its own, described in the dataset's card")
    print(
        "\nSet it: evh dataset-create … --licence ID, or on a dataset: evh dataset-describe --dataset-id D --licence ID"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
