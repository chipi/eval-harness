#!/usr/bin/env python3
"""evh exposure: a held-out side's exposure register, in counts (RFC-031 H1).

    evh exposure --dataset-id triage_v1_test
    evh exposure --dataset-id triage_v1_test --ids      # a person only: the ids read, with who and what

How many of the side's items were read, and by whom and what (counts: a held-out side's ids stay off the terminal).
`--ids` lists each read with its item id, for a person deciding what to do about it; an agent is refused. Every held-out
side is listed when no dataset is named.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys
from collections import Counter

from evaluation_harness import _exposure, _jsonout, _store
from evaluation_harness._common import die, evh_prog, load_dataset


def _held_out() -> list[str]:
    from evaluation_harness import _common  # noqa: PLC0415

    root = _common.DATA / "datasets"
    ids = sorted(p.stem for p in _store.glob(root, "*.json")) if _store.is_dir(root) else []
    return [i for i in ids if _exposure.applies(i)]


def main() -> int:
    """Show a held-out side's register."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", help="the held-out side (default: every one)")
    ap.add_argument("--ids", action="store_true", help="each read with its item id (a person only)")
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("exposure", args.json, live=sys.stderr):
        if args.ids:
            from evaluation_harness._actor import actor  # noqa: PLC0415

            if actor()["type"] != "person":
                die(
                    "--ids prints a held-out side's item ids: a person's command (an agent reads the counts)",
                    "not-allowed",
                )
            if not args.dataset_id:
                die("--ids needs --dataset-id", "bad-argument")
        names = [args.dataset_id] if args.dataset_id else _held_out()
        if args.dataset_id and not _exposure.applies(args.dataset_id):
            die(
                f"{args.dataset_id} is not a held-out side (no seal): it has no exposure register",
                "not-allowed",
            )
        if not names:
            print("No held-out sides (dataset-split --seal makes one).")
        out = []
        for ds in names:
            rows = _exposure.rows(ds)
            n_items = len(load_dataset(ds)["items"])
            read = {str(r.get("item_id")) for r in rows}
            by = Counter(str(r.get("by")) for r in rows)
            what = Counter(str(r.get("what")) for r in rows)
            print(
                f"{ds}: {len(read)} of {n_items} item(s) exposed ({n_items - len(read)} unread), {len(rows)} read(s)"
            )
            for k, n in by.most_common():
                print(f"  by {k}: {n}")
            for k, n in what.most_common():
                print(f"  what: {k}: {n}")
            if args.ids:
                for r in rows:
                    print(
                        f"  {r.get('item_id')}  {r.get('at')}  {r.get('by')}  {r.get('what')}  ({r.get('source')})"
                    )
            out.append(
                {
                    "dataset_id": ds,
                    "items": n_items,
                    "exposed": len(read),
                    "reads": len(rows),
                    "by": dict(by),
                    "what": dict(what),
                    **({"rows": rows} if args.ids else {}),
                }
            )
        _jsonout.value("exposure", out)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
