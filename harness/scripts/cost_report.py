#!/usr/bin/env python3
"""What each arm actually cost, from the provider's bill rather than a price table. $0.

    python scripts/cost_report.py --dataset-id few_nerd_280

WHY THIS EXISTS

  Every run records `cost_usd`. For runs measured before the adapters learned to prefer
  `usage.cost`, that number is the PRICE TABLE -- tokens multiplied by the rate written
  in the arm's yaml. The provider's actual charge was recorded too, in the same
  prediction row, under `_meta.usage.cost`, and nothing read it.

  The two are not close. Across the committed measurement runs the bill is 1.25x the
  price table in total ($9.78 recorded against $12.28 billed), and per arm the ratio
  runs from 0.67x to 3.76x -- `db_openai_m` cost $0.2380 and was recorded at $0.0634.
  An alias is not a price: a provider routes, discounts, caches and rounds, and the
  yaml rate is a guess about what it will do.

  So every cost column, every dollars-per-month figure and every cost-per-quality-point
  computed from `cost_usd` on those runs is wrong, in a direction that varies by arm --
  which is worse than a constant bias, because it reorders the cost ranking.

  This reads the bill straight out of the committed runs. No network, no re-running,
  nothing to regenerate: the number was always there.

WHAT IT CANNOT TELL YOU

  An arm whose provider returned no `usage.cost` has no bill to report, and its price
  table figure is all there is. Those are listed separately rather than mixed in, so a
  total is never half-measured and half-estimated without saying so.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _common import RUNS, read_json  # noqa: E402


def billed_and_recorded(run_dir: Path) -> tuple[float, float, int, int]:
    """(billed, recorded, items with a bill, items total) for one run."""
    pj = run_dir / "predictions.jsonl"
    if not pj.is_file():
        return 0.0, 0.0, 0, 0
    billed = recorded = 0.0
    with_bill = total = 0
    for line in pj.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        total += 1
        recorded += float(r.get("cost_usd") or 0.0)
        b = ((r.get("_meta") or {}).get("usage") or {}).get("cost")
        if b is not None:
            with_bill += 1
            billed += float(b)
    return billed, recorded, with_bill, total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", help="only this dataset; default every dataset")
    ap.add_argument("--match", help="only runs whose config_id contains this")
    args = ap.parse_args()

    rows = []
    no_bill = []
    for d in sorted(RUNS.glob("*")):
        mj = d / "metrics.json"
        if not mj.is_file():
            continue
        m = read_json(mj)
        if args.dataset_id and m.get("dataset_id") != args.dataset_id:
            continue
        cid = m.get("config_id", d.name)
        if args.match and args.match not in cid:
            continue
        billed, recorded, with_bill, total = billed_and_recorded(d)
        if total == 0:
            continue
        if with_bill == 0:
            no_bill.append((cid, recorded, m.get("dataset_id")))
            continue
        if with_bill != total:
            # Half a bill is not a bill. Say so rather than summing a mixture.
            no_bill.append((f"{cid} (only {with_bill}/{total} items billed)",
                            recorded, m.get("dataset_id")))
            continue
        rows.append((billed, recorded, cid, m.get("dataset_id")))

    if not rows and not no_bill:
        print("no runs matched")
        return 1

    rows.sort(key=lambda r: -r[0])
    w = max((len(r[2]) for r in rows), default=20) + 2
    print(f"  {'arm':{w}}{'billed':>11}{'recorded':>11}{'ratio':>9}")
    print("  " + "-" * (w + 31))
    tb = tr = 0.0
    for billed, recorded, cid, _ds in rows:
        ratio = (billed / recorded) if recorded else float("nan")
        flag = "  <-- recorded is the price table" if abs(ratio - 1) > 0.01 else ""
        print(f"  {cid:{w}}{billed:>11.4f}{recorded:>11.4f}{ratio:>8.2f}x{flag}")
        tb += billed
        tr += recorded
    print("  " + "-" * (w + 31))
    print(f"  {'TOTAL':{w}}{tb:>11.4f}{tr:>11.4f}"
          f"{(tb / tr) if tr else float('nan'):>8.2f}x")

    if no_bill:
        print(f"\n  {len(no_bill)} run(s) with NO provider bill — the price table is all "
              f"there is, and they are NOT in the total above:")
        for cid, recorded, ds in no_bill:
            print(f"    {cid}  ${recorded:.4f}  ({ds})")

    print("\n  'billed' is the sum of _meta.usage.cost over every item: what the provider")
    print("  charged. 'recorded' is the run's own cost_usd, which for runs measured")
    print("  before 2026-09-29 is tokens x the rate in the arm's yaml. Where they differ,")
    print("  the bill is the measurement and the price table was the guess.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
