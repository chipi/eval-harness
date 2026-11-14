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

JUDGING

  A judge's calls are not in any run: each verdict stored under data/judge-verdicts/ records its own cost_usd. So the
  report ends with what judging cost, per scorer and judging set and per judge, summed from the verdicts: `billed` where
  the provider reported the cost, `estimated` (the scorer's price table on the token counts) where it did not.
  --dataset-id keeps the judging sets of that dataset; --match, which names arms, leaves judging out.

WHAT IT CANNOT TELL YOU

  An arm whose provider returned no `usage.cost` has no bill to report, and its price
  table figure is all there is. Those are listed separately rather than mixed in, so a
  total is never half-measured and half-estimated without saying so.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

from evaluation_harness import _common, _jsonout, _runs, _store  # noqa: E402
from evaluation_harness._common import (  # noqa: E402
    die,
    evh_prog,
)
from evaluation_harness._runs import runs_on  # noqa: E402
from evaluation_harness.model import scorers as _scorers  # noqa: E402


def billed_and_recorded(run_dir: Path) -> tuple[float, float, int, int]:
    """(billed, recorded, items with a bill, items total) for one run."""
    billed = recorded = 0.0
    with_bill = total = 0
    for r in _runs.item_rows(run_dir):
        total += 1
        recorded += float(r.get("cost_usd") or 0.0)
        b = ((r.get("_meta") or {}).get("usage") or {}).get("cost")
        if b is not None:
            with_bill += 1
            billed += float(b)
    return billed, recorded, with_bill, total


def _json_of(path: Path) -> dict:
    try:
        doc = json.loads(_store.read_text(path, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def judge_costs(dataset_id: str | None = None) -> list[dict]:
    """What judging cost, from the stored verdicts: one row per scorer, judging set and judge, sorted,
    {scorer, set, dataset, judge, verdicts, billed, estimated, estimated_verdicts}. A verdict whose provider reported
    no cost is counted at the scorer's price table (`cost_known` false): that is `estimated`, never added to `billed`.
    With `dataset_id`, only the judging sets of that dataset (a set names its dataset); a set no longer on disk has no
    dataset, so only an unfiltered report counts its verdicts."""
    root = _common.DATA / "judge-verdicts"
    datasets: dict[str, str] = {}
    rows: dict[tuple[str, str, str], dict] = {}
    for f in sorted(_store.glob(root, "*/*/*/*.json")) if _store.is_dir(root) else []:
        scorer, set_id, judge = f.parts[-4:-1]
        if set_id not in datasets:
            datasets[set_id] = str(_json_of(_scorers.judging_set_file(set_id)).get("dataset_id") or "")
        if dataset_id and datasets[set_id] != dataset_id:
            continue
        v = _json_of(f)
        row = rows.setdefault(
            (scorer, set_id, judge),
            {
                "scorer": scorer,
                "set": set_id,
                "dataset": datasets[set_id],
                "judge": judge,
                "verdicts": 0,
                "billed": 0.0,
                "estimated": 0.0,
                "estimated_verdicts": 0,
            },
        )
        row["verdicts"] += 1
        cost = float(v.get("cost_usd") or 0.0)
        if v.get("cost_known", True):
            row["billed"] += cost
        else:
            row["estimated"] += cost
            row["estimated_verdicts"] += 1
    return [
        {**r, "billed": round(r["billed"], 8), "estimated": round(r["estimated"], 8)}
        for _k, r in sorted(rows.items())
    ]


def _print_judging(rows: list[dict]) -> None:
    """The judging table: a line per scorer and judging set, its judges under it, and the total."""
    sets: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        sets.setdefault((r["scorer"], r["set"]), []).append(r)
    w = max(len(f"{s}@{k}") for s, k in sets) + 2
    print("\n  what judging cost, from the verdicts in data/judge-verdicts/")
    print(f"  {'scorer@judging set':{w}}{'verdicts':>10}{'billed':>11}{'estimated':>11}")
    print("  " + "-" * (w + 32))
    for (scorer, set_id), rs in sets.items():
        ds = next((r["dataset"] for r in rs if r["dataset"]), "")
        line = [sum(r["verdicts"] for r in rs), sum(r["billed"] for r in rs), sum(r["estimated"] for r in rs)]
        print(
            f"  {scorer + '@' + set_id:{w}}{line[0]:>10}{line[1]:>11.4f}{line[2]:>11.4f}  ({ds or 'no such judging set'})"
        )
        for r in rs:
            print(f"    {r['judge']:{w - 2}}{r['verdicts']:>10}{r['billed']:>11.4f}{r['estimated']:>11.4f}")
    print("  " + "-" * (w + 32))
    print(
        f"  {'TOTAL':{w}}{sum(r['verdicts'] for r in rows):>10}{sum(r['billed'] for r in rows):>11.4f}"
        f"{sum(r['estimated'] for r in rows):>11.4f}"
    )
    n = sum(r["estimated_verdicts"] for r in rows)
    if n:
        print(f"\n  {n} verdict(s) had no provider bill: 'estimated' prices them from the scorer's table.")


def _repeat_names(runs: list) -> dict[Path, str]:
    """{score dir: the name its row carries}: the system id, and for a system that ran more than once the repeat
    (r1, r2, r3: the run id's own _rN, else its place in run order), so no two rows read alike."""
    seen: dict[str, int] = {}
    for _d, m in runs:
        seen[m["config_id"]] = seen.get(m["config_id"], 0) + 1
    nth: dict[str, int] = {}
    out = {}
    for d, m in runs:
        cid = m["config_id"]
        nth[cid] = nth.get(cid, 0) + 1
        own = re.search(r"_(r\d+)$", m["run_id"])
        out[d] = f"{cid} {own.group(1) if own else f'r{nth[cid]}'}" if seen[cid] > 1 else cid
    return out


def main() -> int:
    """Report cost metrics for runs."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", help="only this dataset; default every dataset")
    ap.add_argument(
        "--match",
        help="only runs whose config_id contains this (judging, which is not by arm, is then left out)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("cost-report", args.json, live=sys.stderr):
        rows = []
        no_bill = []
        runs = runs_on(args.dataset_id or None, match=args.match)
        names = _repeat_names(runs)
        for d, m in runs:
            cid = names[d]
            billed, recorded, with_bill, total = billed_and_recorded(d)
            if total == 0:
                continue
            if with_bill == 0:
                no_bill.append((cid, recorded, m.get("dataset_id")))
                continue
            if with_bill != total:
                # Half a bill is not a bill. Say so rather than summing a mixture.
                no_bill.append(
                    (f"{cid} (only {with_bill}/{total} items billed)", recorded, m.get("dataset_id"))
                )
                continue
            rows.append((billed, recorded, cid, m.get("dataset_id")))

        judging = [] if args.match else judge_costs(args.dataset_id or None)
        if not rows and not no_bill and not judging:
            die("no runs matched", "not-found")

        rows.sort(key=lambda r: -r[0])
        if rows or no_bill:
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
            print(f"  {'TOTAL':{w}}{tb:>11.4f}{tr:>11.4f}{(tb / tr) if tr else float('nan'):>8.2f}x")

        if no_bill:
            print(
                f"\n  {len(no_bill)} run(s) with NO provider bill — the price table is all "
                f"there is, and they are NOT in the total above:"
            )
            for cid, recorded, ds in no_bill:
                print(f"    {cid}  ${recorded:.4f}  ({ds})")

        if rows or no_bill:
            print("\n  'billed' is the sum of _meta.usage.cost over every item: what the provider")
            print("  charged. 'recorded' is the run's own cost_usd, which for runs measured")
            print("  before 2026-09-29 is tokens x the rate in the arm's yaml. Where they differ,")
            print("  the bill is the measurement and the price table was the guess.")
        if judging:
            _print_judging(judging)
            _jsonout.value("judging", judging)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
