#!/usr/bin/env python3
"""Add a field a held-out side's counts may be grouped by (RFC-031 H2): a person's decision, recorded.

    evh dataset-seal-counts --dataset-id triage_v1_test --add gate --reason "the safety watch needs which gate fired"

The fields were fixed when the side was sealed (`dataset-split --seal --count-by`), so whoever reads the counts does
not choose what they show. Adding one is a person's command with a reason, kept on the record beside who and when;
an agent is refused. Nothing is ever removed.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys

from evaluation_harness import _exposure, _jsonout
from evaluation_harness._common import DATASETS, die, evh_prog, load_dataset, now, read_json, write_json
from evaluation_harness.sealed_counts import allowed


def main() -> int:
    """Add a field."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True, help="the held-out side")
    ap.add_argument("--add", required=True, help="the item field to allow")
    ap.add_argument("--reason", required=True, help="why the counts need it")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("dataset-seal-counts", args.json, live=sys.stderr):
        from evaluation_harness._actor import require_named  # noqa: PLC0415

        who = require_named("widening what a held-out side's counts show")
        if who["type"] != "person":
            die(
                "what a held-out side's counts may show is a person's decision: an agent is refused",
                "not-allowed",
            )
        if not _exposure.applies(args.dataset_id):
            die(f"{args.dataset_id} is not a held-out side (no seal)", "not-allowed")
        if args.add in allowed(args.dataset_id):
            print(f"{args.dataset_id}: {args.add} is already allowed")
            return 0
        doc = load_dataset(args.dataset_id)
        if not any(args.add in (it.get("fields") or {}) for it in doc["items"]):
            die(f"no item of {args.dataset_id} has the field {args.add}", "not-found")
        path = DATASETS / f"{args.dataset_id}.json"
        rec = read_json(path)
        rec["sealed"].setdefault("count_by_added", []).append(
            {"field": args.add, "at": now(), "reason": args.reason, "actor": who}
        )
        write_json(path, rec)
        print(f"{args.dataset_id}: counts may now be grouped by {args.add} ({args.reason})")
        _jsonout.values({"dataset_id": args.dataset_id, "allowed": allowed(args.dataset_id)})
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
