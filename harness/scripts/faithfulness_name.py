#!/usr/bin/env python3
"""Name a replay's disagreement with production whose cause is outside the system (RFC-030).

    evh faithfulness-name --model signal_fleet --item d0412 --cause "the freezer lost this issue's labels" --by person:ana

The name is appended beside the record (data/faithfulness/<model_id>/<n>.exceptions.jsonl, who and when), never edited
into it, and every page and command that shows the record shows it. A named disagreement no longer holds back the gate.
It is a person's decision: an agent is refused, as for `evh run --unfaithful`.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json
import os
import sys

from evaluation_harness import _coderec, _faith, _jsonout, _store
from evaluation_harness._common import die, evh_prog, now


def main() -> int:
    """Append one named exception to a faithfulness record."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True, help="the code record (data/models/<id>.yaml, kind: code)")
    ap.add_argument("--n", type=int, help="the faithfulness record's number (default: the newest)")
    ap.add_argument("--item", required=True, help="the item whose disagreement is named")
    ap.add_argument("--cause", required=True, help="what outside the system caused it, in words")
    ap.add_argument("--json", action="store_true", help="the exception written, as result.values.exception")
    from evaluation_harness._actor import add_by, require_named  # noqa: PLC0415

    add_by(ap)
    args = ap.parse_args()
    with _jsonout.collect("faithfulness-name", args.json, live=sys.stderr):
        _coderec.load(args.model)
        who = require_named("naming a replay's disagreement")
        if who["type"] != "person":
            die(
                "an agent cannot name a disagreement; it lets a replay be scored (RFC-030). A person names it.",
                "not-allowed",
            )
        if not args.cause.strip():
            die("--cause: say what outside the system caused the disagreement", "bad-argument")
        nums = _faith.numbers(args.model)
        n = args.n or (nums[-1] if nums else None)
        if n is None:
            die(f"no faithfulness record of {args.model}: run evh faithfulness first", "not-found")
        rec = _faith.load(args.model, n)
        if args.item not in {d["item_id"] for d in rec.get("disagreements") or []}:
            die(f"{args.item} is not a disagreement of record {args.model}/{n}", "not-found")
        if args.item in {e.get("item_id") for e in rec.get("exceptions") or []}:
            die(f"{args.item} is named already in record {args.model}/{n}", "would-overwrite")
        ev = {"item_id": args.item, "cause": args.cause.strip(), "actor": who, "at": now()}
        from evaluation_harness import _jobs  # noqa: PLC0415

        key = f"faithfulness:{args.model}"
        with _jobs.holding(
            [(key, True)], os.environ.get("EVH_JOB") or f"pid {os.getpid()}", _jobs.say_waiting
        ):
            p = _faith.records_dir(args.model) / f"{n}.exceptions.jsonl"
            before = _store.read_text(p, encoding="utf-8") if _store.is_file(p) else ""
            if before and not before.endswith("\n"):
                before += "\n"
            _store.write_text(p, before + json.dumps(ev, sort_keys=True) + "\n")
        now_rec = _faith.load(args.model, n)
        _coderec.record_faithfulness(args.model, n, now_rec)
        left = _faith.unnamed(now_rec)
        print(f"named {args.item} in record {args.model}/{n}: {args.cause.strip()}")
        print(f"  {len(left)} disagreement(s) of the record left unnamed")
        _jsonout.value("exception", {**ev, "record": f"{args.model}/{n}", "unnamed_left": len(left)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
