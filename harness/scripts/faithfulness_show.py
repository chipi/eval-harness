#!/usr/bin/env python3
"""A faithfulness record (RFC-030): its counts, every disagreement and who named which, and its coverage.

evh faithfulness-show --model signal_fleet
evh faithfulness-show --model signal_fleet --n 2 --json
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse

from evaluation_harness import _coderec, _faith, _jsonout
from evaluation_harness._common import die, evh_prog


def main() -> int:
    """Print one faithfulness record."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--model", required=True, help="the code record (data/models/<id>.yaml, kind: code)")
    ap.add_argument("--n", type=int, help="the faithfulness record's number (default: the newest)")
    ap.add_argument("--json", action="store_true", help="the record as result.values.record")
    args = ap.parse_args()
    with _jsonout.collect("faithfulness-show", args.json):
        _coderec.load(args.model)
        nums = _faith.numbers(args.model)
        n = args.n or (nums[-1] if nums else None)
        if n is None:
            die(f"no faithfulness record of {args.model}", "not-found")
        rec = _faith.load(args.model, n)
        c = rec["counts"]
        named = {e["item_id"]: e for e in rec.get("exceptions") or []}
        print(
            f"{args.model}/{n}: replay of {rec['config_id']} on {rec['dataset_id']} at {len(rec['commits'])} commit(s), "
            f"against {rec['production_run']}, {rec['at']} by {(rec.get('actor') or {}).get('name', '?')}"
        )
        print(
            f"  {c['agree']} of {c['items']} agree; {c['differ']} differ, {c['replay_errors']} replay error(s), "
            f"{c['production_missing']} without a production output; {len(named)} named, "
            f"{len(_faith.unnamed(rec))} unnamed"
        )
        for d in rec.get("disagreements") or []:
            e = named.get(d["item_id"])
            print(
                f"  {d['kind']:18} {d['item_id']}"
                + (f"  NAMED by {e['actor'].get('name')}: {e['cause']}" if e else "")
            )
        for commit, v in (rec.get("coverage") or {}).items():
            print(
                f"  coverage {commit[:12]}: {v['entered']} of {v['defined']} functions entered; never: {v['never_count']}"
            )
            for name in v["never"]:
                print(f"      {name}")
        _jsonout.value("record", rec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
