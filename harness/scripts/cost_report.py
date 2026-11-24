"""What each arm actually cost, from the provider's bill rather than a price table. $0.

    evh cost-report --dataset-id few_nerd_280

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

from pathlib import Path

from evaluation_harness import _jsonout, _runs
from evaluation_harness._common import die
from evaluation_harness._runs import left_out, runs_on
from evaluation_harness.axes import with_coverage
from evaluation_harness.model.spend import judge_costs


def billed_and_recorded(run_dir: Path) -> tuple[float, float | None, int, int]:
    """(billed, recorded, items with a bill, items total) for one run. `recorded` is None when no item recorded a cost:
    an unknown cost is not $0 (RFC-041 F3); a known $0 is."""
    billed = 0.0
    recorded: float | None = None
    with_bill = total = 0
    for r in _runs.item_rows(run_dir):
        total += 1
        if r.get("cost_usd") is not None:
            recorded = (recorded or 0.0) + float(r["cost_usd"])
        b = ((r.get("_meta") or {}).get("usage") or {}).get("cost")
        if b is not None:
            with_bill += 1
            billed += float(b)
    return billed, recorded, with_bill, total


def _usd(v: float | None) -> str:
    """A recorded cost in the table's column: four places, "—" for none recorded."""
    return "—" if v is None else f"{v:.4f}"


def _ratio(r: float | None) -> str:
    """The ratio column: `billed / recorded`, or "—" where nothing was recorded to divide by: 0 billed against 0
    recorded is no ratio (not 0), and a bill against nothing recorded is not an infinite one."""
    return f"{r:>8.2f}x" if r is not None else f"{'—':>8} "


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
    (r1, r2, r3: the pass the run records as its `repeat_index`, else the next number no run of the system has), so no
    two rows read alike."""
    seen: dict[str, int] = {}
    taken: dict[str, set[int]] = {}
    for _d, m in runs:
        seen[m["system_id"]] = seen.get(m["system_id"], 0) + 1
        if m.get("repeat_index"):
            taken.setdefault(m["system_id"], set()).add(int(m["repeat_index"]))
    out = {}
    for d, m in runs:
        cid = m["system_id"]
        n = int(m["repeat_index"]) if m.get("repeat_index") else 0
        while not n:
            n = next(i for i in range(1, len(runs) + 2) if i not in taken.setdefault(cid, set()))
            taken[cid].add(n)
        out[d] = f"{cid} r{n}" if seen[cid] > 1 else cid
    return out


def body(dataset_id: str | None = None, match: str | None = None) -> int:
    """Report cost metrics for runs: what the provider billed against what the run recorded, and what judging cost."""
    rows = []
    no_bill = []
    runs = runs_on(dataset_id or None, match=match)
    for line in left_out(dataset_id or None, match=match):
        print(f"  WARNING: {line}: its cost is not in this report.")
    names = _repeat_names(runs)
    for d, m in runs:
        cid = names[d]
        billed, recorded, with_bill, total = billed_and_recorded(d)
        if total == 0:
            continue
        if with_bill == 0:
            no_bill.append((cid, recorded, m.get("dataset_id"), m.get("cost_coverage")))
            continue
        if with_bill != total:
            # Half a bill is not a bill. Say so rather than summing a mixture.
            no_bill.append(
                (
                    f"{cid} (only {with_bill}/{total} items billed)",
                    recorded,
                    m.get("dataset_id"),
                    m.get("cost_coverage"),
                )
            )
            continue
        rows.append((billed, recorded, cid, m.get("dataset_id")))

    judging = [] if match else judge_costs(dataset_id or None)
    if not rows and not no_bill and not judging:
        die("no runs matched", "not-found")

    rows.sort(key=lambda r: -r[0])
    if rows or no_bill:
        w = max((len(r[2]) for r in rows), default=20) + 2
        print(f"  {'arm':{w}}{'billed':>11}{'recorded':>11}{'ratio':>9}")
        print("  " + "-" * (w + 31))
        tb, known = 0.0, []
        for billed, recorded, cid, _ds in rows:
            ratio = (billed / recorded) if recorded else None
            differs = recorded is not None and (billed > 0 if ratio is None else abs(ratio - 1) > 0.01)
            flag = "  <-- recorded is the price table" if differs else ""
            print(f"  {cid:{w}}{billed:>11.4f}{_usd(recorded):>11}{_ratio(ratio)}{flag}")
            tb += billed
            if recorded is not None:
                known.append(recorded)
        print("  " + "-" * (w + 31))
        # The recorded total is of the runs that recorded one, and says how many did not: an unknown is not $0.
        tr = sum(known) if known else None
        unrecorded = len(rows) - len(known)
        print(
            f"  {'TOTAL':{w}}{tb:>11.4f}{_usd(tr):>11}{_ratio((tb / tr) if tr else None)}"
            + (f"  ({unrecorded} run{'s' if unrecorded != 1 else ''} recorded no cost)" if unrecorded else "")
        )

    if no_bill:
        print(
            f"\n  {len(no_bill)} run(s) with NO provider bill — the price table is all "
            f"there is, and they are NOT in the total above:"
        )
        for cid, recorded, ds, coverage in no_bill:
            print(
                f"    {cid}  {'—' if recorded is None else with_coverage(f'${recorded:.4f}', coverage)}  ({ds})"
            )

    if rows or no_bill:
        print("\n  'billed' is the sum of _meta.usage.cost over every item: what the provider")
        print("  charged. 'recorded' is the run's own cost_usd, which for runs measured")
        print("  before 2026-09-29 is tokens x the rate in the arm's yaml. Where they differ,")
        print("  the bill is the measurement and the price table was the guess.")
    if judging:
        _print_judging(judging)
        _jsonout.value("judging", judging)
    return 0
