"""The catalog and the inspector, in the terminal: every page and comparison as a command.

    evh overview   [--period P]                      the home page: tiles with trends, goals at a glance, activity, spend, coverage
    evh datasets   [--dataset-id ID]                 every dataset, or one: arms, references, versions
    evh arms       [--dataset-id ID] [--arm ID]      every arm, or one: its metrics, runs, system, conditions, rounds
                   [--by G] [--where W] [--tier T] [--weights K] [--quality Q] [--systems]
                                                     the arms page: grouped, filtered; the systems
    evh models     [--kind K] [--where W] [--status S] [--model ID]
                                                     every model record, or one: deployments, onboarding, history, arms
    evh references [--reference-id ID]               every reference, or one: who wrote it, what is scored against it
    evh metrics    [--dataset-id ID] [--metric M]    what each metric measures, or one in full with the arms recording it
    evh goals      [--goal ID [--arms P] [--top N]]  every goal, or one: its answer on each of its datasets
    evh activity   [--period P]                      runs, spend and tokens by dataset, arm and kind, against the period before

Every list (datasets, arms, references, metrics, goals) takes --period P too: the page's columns
for that period, counted from today, with their trends against the period before.
    evh inspect    --runs A,B,... [--baseline A]     the inspector's comparison: verdicts, conditions, a breakdown
                   [--metric M] [--where F:V] [--by F] [--item ITEM] [--analysis [--x M]]
    evh inspect    --sheet --dataset-id D --runs A,B,... [--metric M] [--csv FILE [--fill label|pick|scores]]
                                                      one sheet: the items down, a column per arm: outputs, scores, labels, the winner
    evh search     TEXT                              the catalog's search box: datasets, arms, references, metrics, goals

They read the project through the same adapter as the pages (`--adapter`, else config.yaml's
catalog.adapter, else the harness's layout) and compute with the same functions as the pages and
the inspector server, so a number here is the number there. The pages are a comfort; everything
they show is here.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import json
import os
import re
import statistics
import sys
import textwrap
from datetime import date
from pathlib import Path

from evaluation_harness import _goal_view, _jsonout, _outputs, _sheet, _store
from evaluation_harness import catalog_build as cb
from evaluation_harness import catalog_models as cm
from evaluation_harness import catalog_periods as cp
from evaluation_harness import catalog_serve as cs
from evaluation_harness._common import die
from evaluation_harness.axes import (
    STRATEGIES,
    axis_title,
    builtin_axes,
    cell_of,
    cell_text,
    strategy_of,
    tie_break_of,
)
from evaluation_harness.catalog_adapter import load_catalog_adapter, scores_once
from evaluation_harness.model import runs as model_runs
from evaluation_harness.stats import fmt_p

KINDS = {"t-silver": "silver", "t-judged": "judged", "t-author": "wrote its reference"}


def _table(heads: list, rows: list) -> None:
    if _jsonout.table(heads, rows):  # under --json: kept as data, not printed
        return
    cells = [[str(c) for c in r] for r in rows]
    w = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(heads)]
    print("  " + "  ".join(h.ljust(w[i]) for i, h in enumerate(heads)).rstrip())
    print("  " + "  ".join("-" * x for x in w))
    for r in cells:
        print("  " + "  ".join(c.ljust(w[i]) for i, c in enumerate(r)).rstrip())


def _condition_value(v) -> str:
    """A field's value in the conditions table: whole, except a digest, whose first 16 characters tell it apart."""
    text = str(v)
    return text[:16] if re.fullmatch(r"[0-9a-f]{24,}", text) else text


def _fmt(v) -> str:
    return "—" if v is None else cb.fmt(v)


def _scored(a: dict) -> str:
    return f"judge {a['judge']}" if a.get("judge") else (a.get("reference") or "—")


def _kind(a: dict, tiers: dict) -> str:
    return KINDS.get(cb.row_kind(a, tiers), "")


def _adapter(args):
    # One view, one process: each arm's scores read once.
    A = scores_once(load_catalog_adapter(getattr(args, "adapter", None)))
    return A, cb.collect(A)


def _period_option(ap) -> None:
    """--period: the page's period columns, counted from today (catalog_periods.PERIODS)."""
    ap.add_argument(
        "--period",
        choices=[k for k, *_ in cp.PERIODS],
        help="add the page's columns for a period counted from today: "
        + ", ".join(f"{k} ({label})" for k, label, _ in cp.PERIODS),
    )


def _period(A, by_ds: dict, rows: dict, key: str | None) -> tuple:
    """(each row's period numbers, a line saying the period and what trends compare with), or
    ({}, "") without --period."""
    if not key:
        return {}, ""
    first = cb.window(A, by_ds)["first"]
    b = cp.bounds(key, date.today(), first)
    label, against = next((lb, ag) for k, lb, ag in cp.PERIODS if k == key)
    line = f"{label}, {b['since']} to {b['until']}" + (
        f"; ▲▼ against {against}, {b['prev'][0]} to {b['prev'][1]}" if b["prev"] else ""
    )
    return cp.in_period(rows, key, date.today(), first), line


def _pcells(p: dict, flows: tuple) -> list:
    """A row's period cells: new, then each flow with its trend (usd as money, tokens with commas)."""
    fmts = {
        "usd": lambda v: cb.fmt_amount(v, "usd") if v else "—",
        "tokens": lambda v: f"{round(v):,}" if v else "—",
    }
    return ["new" if p["new"] else ""] + [cp.cell(p[f], p[f"{f}_prev"], fmts.get(f, str)) for f in flows]


PERIOD_HEADS = {
    "runs": "runs in period",
    "arms": "arms in period",
    "usd": "spend in period",
    "tokens": "tokens in period",
    "events": "changes in period",
}


def datasets(argv) -> int:
    """evh datasets: every dataset, or one with its versions, reference sets and arms."""
    ap = argparse.ArgumentParser(prog="evh datasets", description="Every dataset, or one in full.")
    ap.add_argument("--dataset-id", help="one dataset: its versions, reference sets and arms")
    ap.add_argument(
        "--tag", action="append", default=[], metavar="K=V", help="only datasets with this tag (repeatable)"
    )
    _period_option(ap)
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    want = []
    for t in args.tag:
        k, sep, val = t.partition("=")
        if not sep or not k:
            die(f"--tag {t!r}: KEY=VALUE", "bad-argument")
        want.append((k, val))
    if want:
        by_ds = {
            d: v for d, v in by_ds.items() if all((v.get("tags") or {}).get(k) == val for k, val in want)
        }
    if not args.dataset_id:
        per, line = _period(A, by_ds, cb.period_datasets(A, by_ds), args.period)
        flows = ("runs", "usd")
        if line:
            print(line)
        rows = [
            [
                ds,
                v["items"],
                len(v["arms"]),
                cb._n_systems({ds: v}),
                ", ".join(r["id"] for r in v["refs"]) or "—",
                (v.get("parent") or {}).get("dataset_id", "") or v.get("origin", ""),
                " ".join(f"{k}={t}" for k, t in sorted((v.get("tags") or {}).items())),
                *(_pcells(per[ds], flows) if per else []),
            ]
            for ds, v in sorted(by_ds.items())
        ]
        heads = ["dataset", f"{A.item_word}s", "arms", "systems", "reference sets", "made from", "tags"]
        _table(heads + (["", *(PERIOD_HEADS[f] for f in flows)] if per else []), rows)
        return 0
    v = by_ds.get(args.dataset_id)
    if v is None:
        die(f"no dataset {args.dataset_id!r} in the catalog: one of {', '.join(sorted(by_ds))}", "not-found")
    print(
        f"{args.dataset_id}: {v['items']} {A.item_word}s, {len(v['arms'])} arms from "
        f"{cb._n_systems({args.dataset_id: v})} systems (a system rescored against silver or by a judge is an arm of its own)\n"
    )
    if v.get("tags"):
        print("tags: " + ", ".join(f"{k}={t}" for k, t in sorted(v["tags"].items())))
    if v.get("origin") and not v.get("parent"):
        print(f"made from {v['origin']}")
    lin = v.get("parent")
    if lin:
        print(
            f"made from {lin['dataset_id']}: "
            + ", ".join(f"{len(lin[k])} {k}" for k in ("added", "removed", "changed"))
        )
        for k in ("added", "removed", "changed"):
            if lin[k]:
                print(f"  {k}: {', '.join(lin[k])}")
    for c in v.get("children") or []:
        cl = by_ds[c]["parent"]
        print(f"made into {c}: " + ", ".join(f"{len(cl[k])} {k}" for k in ("added", "removed", "changed")))
    if v["refs"]:
        print("\nreferences: " + ", ".join(f"{r['id']} ({r['tier']})" for r in v["refs"]))
    _fields_block(A, args.dataset_id)
    for b in v.get("baselines", []):
        of = f"{b['goal']}'s baseline" if b.get("goal") else "the dataset's own baseline"
        print(
            f"\n{of}, version {b.get('version')}: {b.get('arm') or b['run']} (promoted {(b['promoted_at'] or '')[:10]})"
        )
        print(textwrap.fill(b["reason"], width=92, initial_indent="  ", subsequent_indent="  "))
    tiers = {r["id"]: r["tier"] for r in v["refs"]}
    arms = sorted(
        v["arms"],
        key=lambda a: (
            cb.scored_by_rank(a, tiers),
            a.get("reference") or "",
            a["metric"],
            -(a["mean"] or 0) * (-1 if a["lower"] else 1),
        ),
    )
    print()
    if not arms:
        print("no arm has run on it yet")
        return 0
    # Cost and speed per arm, as the dataset page shows them (the goal pages decide with them).
    bax = builtin_axes()
    _table(
        [
            "arm",
            "metric",
            "mean",
            f"{A.item_word}s",
            *(axis_title(ax) for ax in bax),
            "runs",
            "scored against",
            "row",
            "arm id (for inspect)",
        ],
        [
            [
                a["label"],
                a["metric"] or "—",
                _fmt(a["mean"]),
                a["n"],
                *(cell_text(ax, cell_of(ax, A.scores(a["arm"]))) for ax in bax),
                a["runs"],
                _scored(a),
                _kind(a, tiers),
                a["arm"],
            ]
            for a in arms
        ],
    )
    return 0


def _fields_block(A, dataset: str) -> None:
    """The dataset page's item fields: each field, its coverage, and a summary of a public one."""
    from evaluation_harness import _fields  # noqa: PLC0415
    from evaluation_harness.catalog_adapter import item_fields  # noqa: PLC0415

    fl = item_fields(A, dataset)
    fs = fl.get("fieldset")
    if not fs:
        return
    items = [{"item_id": i, "fields": f} for i, f in (fl.get("values") or {}).items()]
    rows = []
    for x in _fields.summary(fs, items):
        if not x["public"]:
            vals = "not public"
        elif "counts" in x:
            vals = " · ".join(f"{k} {c}" for k, c in sorted(x["counts"].items(), key=lambda kv: -kv[1]))
        elif "median" in x:
            vals = f"{x['min']} – {x['max']}, median {x['median']}"
        elif "min" in x:
            vals = f"{x['min']} – {x['max']}"
        elif "distinct" in x:
            vals = f"{x['distinct']} distinct"
        else:
            vals = "—"
        rows.append(
            [
                x["name"],
                x["type"] + (f" ({x['unit']})" if x.get("unit") else ""),
                f"{x['filled']} of {x['of']}",
                vals,
            ]
        )
    print(f"\nfields (field set {fs.get('fieldset_id', '')}; values of public fields only):")
    _table(["field", "type", "filled", "values"], rows)


def references(argv) -> int:
    """evh references: every reference set, or one with its provenance and what is scored against it."""
    ap = argparse.ArgumentParser(prog="evh references", description="Every reference set, or one in full.")
    ap.add_argument(
        "--reference-id", help="one reference set: who wrote it, from which run, what is scored against it"
    )
    _period_option(ap)
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    refs = [(ds, r) for ds, v in by_ds.items() for r in v["refs"]]
    if not args.reference_id:
        per, line = _period(A, by_ds, cb.period_references(A, by_ds), args.period)
        flows = ("arms", "runs")
        if line:
            print(line)
        _table(
            ["reference", "tier", "dataset", f"{A.item_word}s", "written by"]
            + (["", *(PERIOD_HEADS[f] for f in flows)] if per else []),
            [
                [
                    r["id"],
                    r["tier"],
                    ds,
                    r.get("items", "—"),
                    r.get("author") or "—",
                    *(_pcells(per[r["id"]], flows) if per else []),
                ]
                for ds, r in sorted(refs, key=lambda x: x[1]["id"])
            ],
        )
        return 0
    hit = next(((ds, r) for ds, r in refs if r["id"] == args.reference_id), None)
    if hit is None:
        die(
            f"no reference set {args.reference_id!r}: one of {', '.join(sorted(r['id'] for _, r in refs))}",
            "not-found",
        )
    ds, r = hit
    print(f"{r['id']}\n  {cb.TIER_WORDS.get(r['tier'], '')}\n")
    for k, label in (
        ("dataset", "dataset"),
        ("items", f"{A.item_word}s"),
        ("author", "written by"),
        ("from_run", "from the run"),
        ("model", "model"),
        ("created_at", "created"),
    ):
        val = ds if k == "dataset" else r.get(k)
        if val not in (None, ""):
            print(f"  {label:13} {val}")
    tiers = {x["id"]: x["tier"] for x in by_ds[ds]["refs"]}
    scored = [a for a in by_ds[ds]["arms"] if a["reference"] == r["id"] and not a["judge"]]
    print(f"\nscored against it: {len(scored)}")
    if scored:
        _table(
            ["arm", "metric", "mean", f"{A.item_word}s", "row"],
            [
                [a["label"], a["metric"], _fmt(a["mean"]), a["n"], _kind(a, tiers)]
                for a in sorted(scored, key=lambda a: -(a["mean"] or 0))
            ],
        )
    return 0


def metrics(argv) -> int:
    """evh metrics: what each metric measures, which way is better, where it is recorded."""
    ap = argparse.ArgumentParser(
        prog="evh metrics", description="What each metric measures, and where it is recorded."
    )
    ap.add_argument("--dataset-id", help="only the metrics recorded on this dataset")
    ap.add_argument(
        "--metric", help="one metric in full: how it is computed, and the arms recording it, best first"
    )
    _period_option(ap)
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    fn = getattr(A, "metric_descriptions", None)
    project = fn() if callable(fn) else {}
    idx = cb.metric_index(A, by_ds)
    if args.metric:
        return _metric(A, by_ds, project, idx, args.metric, args.dataset_id)
    per, line = _period(A, by_ds, cb.period_metrics(A, by_ds), args.period)
    if line:
        print(line + "\n")
    for m in sorted(idx, key=lambda k: (k.startswith(("total_", "self_family_", "resumed", "failed")), k)):
        where = idx[m]
        if args.dataset_id and args.dataset_id not in where["datasets"]:
            continue
        lower = any(A.lower_is_better(m, ds) for ds in where["datasets"])
        better = "lower" if lower else ("neutral" if A.is_neutral(m) else "higher")
        text = cb.describe_metric(m, project) or "not described: add it to the adapter's METRIC_DESCRIPTIONS"
        print(f"{m}  ({better} is better)" if better != "neutral" else f"{m}  (neutral: a description)")
        print(textwrap.fill(text, width=96, initial_indent="    ", subsequent_indent="    "))
        print(
            "    recorded on: " + ", ".join(f"{ds} ({n} arms)" for ds, n in sorted(where["datasets"].items()))
        )
        if where["goals"]:
            print("    decides: " + ", ".join(g["goal_id"] for g in where["goals"]))
        if where["weighs"]:
            print("    weighed by: " + ", ".join(g["goal_id"] for g in where["weighs"]))
        if per:
            p = per[m]
            print(
                f"    in the period: {cp.cell(p['arms'], p['arms_prev'])} arms recording it"
                + ("  [new]" if p["new"] else "")
            )
    return 0


def _metric(A, by_ds: dict, project: dict, idx: dict, m: str, only: str | None) -> int:
    """One metric, as its page shows it."""
    where = idx.get(m)
    if where is None:
        die(f"no metric {m!r} is recorded: one of {', '.join(sorted(idx))}", "not-found")
    lower = any(A.lower_is_better(m, ds) for ds in where["datasets"])
    better = "lower" if lower else ("neutral: a description" if A.is_neutral(m) else "higher")
    print(m)
    for text in (
        cb.describe_metric(m, project) or "not described: add it to the adapter's METRIC_DESCRIPTIONS",
        cb.metric_details(m, project),
    ):
        if text:
            print(textwrap.fill(text, width=96, initial_indent="  ", subsequent_indent="  ") + "\n")
    print(f"  better       {better}")
    print(f"  kind         {cb._kind_of(A, m, where['datasets'])}")
    print("  decides      " + (", ".join(g["goal_id"] for g in where["goals"]) or "no goal"))
    print("  weighed by   " + (", ".join(g["goal_id"] for g in where["weighs"]) or "no goal"))
    for ds in sorted(where["datasets"]):
        if only and ds != only:
            continue
        v = by_ds[ds]
        tiers = {r["id"]: r["tier"] for r in v["refs"]}
        arms = [a for a in v["arms"] if m in a["means"]]
        arms.sort(
            key=lambda a: (
                cb.scored_by_rank(a, tiers),
                a.get("reference") or "",
                a["means"][m][0] * (1 if lower else -1),
            )
        )
        print(f"\non {ds}:")
        _table(
            ["arm", f"mean {m}", f"{A.item_word}s", "scored against", "row"],
            [
                [
                    a["label"],
                    cb.metric_value(A, m, a["means"][m][0]),
                    a["means"][m][1],
                    _scored(a),
                    _kind(a, tiers),
                ]
                for a in arms
            ],
        )
    return 0


def overview(argv) -> int:
    """evh overview: the catalog's home page in the terminal."""
    ap = argparse.ArgumentParser(
        prog="evh overview", description="The whole catalog at a glance, as the home page."
    )
    ap.add_argument(
        "--period",
        default=cp.DEFAULT,
        choices=[k for k, *_ in cp.PERIODS],
        help="counted from today: "
        + ", ".join(f"{k} ({label})" for k, label, _ in cp.PERIODS)
        + f"; default {cp.DEFAULT}",
    )
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    w = cb.window(A, by_ds)
    rounds_fn = getattr(A, "rounds", None)
    data = cp.home_data(A, by_ds, w["spend"], A.goals(), rounds_fn() if callable(rounds_fn) else [])
    today = date.today()
    b = cp.bounds(args.period, today, data["first"])
    since, until = b["since"], b["until"]
    label, against = next((lb, ag) for k, lb, ag in cp.PERIODS if k == args.period)
    span = f"{label}, {since} to {until}"
    print(f"{span}" + (f"; trends against {against}, {b['prev'][0]} to {b['prev'][1]}" if b["prev"] else ""))
    for t in cp.tiles(data, args.period, today):
        if t["kind"] == "stock":
            line = f"+{t['new']} new" if t["new"] else "none new"
            value = str(t["value"])
        else:
            line = t["trend"]["text"] + (f" vs {against}" if t["trend"]["pct"] is not None else "")
            value = cb.fmt_amount(t["value"], "usd") if t["what"] == "billed" else f"{round(t['value']):,}"
        print(f"  {cb.TILE_LABEL.get(t['what'], t['what']):15} {value:>16}  {line}".rstrip())
    print(
        "\ngoals at a glance (the leader of the gold group against the baseline, one test, threshold 0.05):"
    )
    rows = cb.glance(A, by_ds)
    if rows:
        _table(
            ["goal", "dataset", "decides", "baseline", "leader", "leader vs baseline", "recommended"],
            [
                [
                    r["goal"]["goal_id"],
                    r["dataset"],
                    r["measure"]
                    + (" (lower)" if r["lower"] else "")
                    + (f" [no gold: {r['group']}]" if r["group"] and not r["gold"] else ""),
                    f"{r['baseline_label']} {_fmt(r['baseline_mean'])}" if r["baseline"] else "none promoted",
                    f"{r['leader_label']} {_fmt(r['leader_mean'])}" if r["leader"] else "—",
                    cb.glance_verdict(r),
                    (
                        r["recommended_label"]
                        + (f" ({' · '.join(r['vs_baseline'])} vs baseline)" if r["vs_baseline"] else "")
                    )
                    if r["recommended"]
                    else "none yet",
                ]
                for r in rows
            ],
        )
        print(
            "  recommended: what each goal's strategy picks once its limits and the tie-break (cost, then"
            " speed, by default) are applied; evh goals --goal G says why."
        )
    else:
        print("  no goals yet")
    if data["first"]:
        print(f"\nactivity, {span}: measured runs per day")
        counts = {
            ds: {d: n for d, n in per.items() if d <= until}
            for ds, per in cb.activity_counts(by_ds, since).items()
            if any(d <= until for d in per)
        }
        days = sorted({d for c in counts.values() for d in c})
        if days:
            _table(
                ["day", *sorted(counts), "total"],
                [
                    [
                        d,
                        *(counts[x].get(d, 0) for x in sorted(counts)),
                        sum(counts[x].get(d, 0) for x in counts),
                    ]
                    for d in days
                ],
            )
        else:
            print("  none")
        for unit in cb.SPEND_UNITS:
            per = {
                name: {d: v for d, v in days_.items() if d <= until}
                for name, days_ in cb.spend_by_day(w["spend"], since, unit).items()
                if any(d <= until for d in days_)
            }
            print(f"\nspend in {'USD' if unit == 'usd' else 'tokens'}, {span}:")
            if not per:
                print("  none recorded")
                continue
            for name, d in per.items():
                print(f"  {name:20} {cb.fmt_amount(sum(d.values()), unit)}")
    else:
        print("\nactivity and spend: nothing is recorded with a date yet")
    print("\ncoverage:")
    _table(
        [
            "dataset",
            f"{A.item_word}s",
            "arms scored against",
            "reference sets",
            "metrics",
            "goals",
            "last run",
        ],
        [
            [
                c["dataset"] + (f" (from {c['parent']})" if c["parent"] else ""),
                c["items"],
                " · ".join(f"{k} {n}" for k, n in c["scored"].items()) or "—",
                ", ".join(c["references"]) or "—",
                len(c["metrics"]),
                ", ".join(g["goal_id"] for g in c["goals"]) or "—",
                c["last"][:10] or "—",
            ]
            for c in cb.coverage(A, by_ds)
        ],
    )
    if since:
        ev = [x for x in w["events"] if x["at"][:10] >= since]
        print(f"\nrecorded, {span}: {len(ev)}")
        _table(
            ["when", "what", "kind"],
            [[x["at"][:16].replace("T", " "), cb.plain(x["html"]), x["kind"]] for x in ev],
        )
    return 0


def arms(argv) -> int:
    """evh arms: every arm, or one in full as its page shows it."""
    ap = argparse.ArgumentParser(prog="evh arms", description="Every arm, or one in full.")
    from evaluation_harness import catalog_arms as ca  # noqa: PLC0415

    ap.add_argument("--dataset-id", help="only the arms on this dataset")
    ap.add_argument("--arm", help="one arm in full: its arm id, or a system id (its arm under runs/)")
    ap.add_argument(
        "--by",
        choices=[*("dataset" if k == "set" else k for k, _ in ca.GROUPS if k), "none"],
        default="dataset",
        help="group the arms, as the arms page does (default dataset; scored: what each is scored against; none)",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="every arm of each group (by default a group shows three, what a goal decided on first, as the page does)",
    )
    ap.add_argument("--where", choices=("local", "hosted"), help="only arms run locally, or only hosted ones")
    ap.add_argument("--tier", help="only arms of this price tier (free, small, mid, large, ...)")
    ap.add_argument(
        "--weights",
        choices=("open", "proprietary"),
        help="only arms whose model's weights are open, or proprietary (the model records, data/models/)",
    )
    ap.add_argument(
        "--quality",
        choices=("contender", "below"),
        help="only arms a goal counts as contenders beside its quality leader, or only those it ranks below the leader",
    )
    ap.add_argument(
        "--systems",
        action="store_true",
        help="one row per system across the datasets it ran on, with its rank on each goal",
    )
    _period_option(ap)
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    if not args.arm:
        rows = [
            r
            for r in ca.arm_rows(A, by_ds)
            if (not args.dataset_id or r["dataset"] == args.dataset_id)
            and (not args.where or r["local"] == (args.where == "local"))
            and (not args.tier or r["tier"] == args.tier)
            and (not args.weights or r["weights"] == args.weights)
            and (
                not args.quality
                or r["quality"] == {"contender": "a contender", "below": "below the leader"}[args.quality]
            )
        ]
        if not rows:
            why = []
            if args.weights:
                why.append(
                    "an arm's weights come from the model records (data/models/, the adapter's model_facts)"
                )
            if args.quality:
                why.append("only arms a goal's decision weighs have a place against its quality leader")
            print("no arm matches" + (f": {'; '.join(why)}" if why else ""))
            return 0
        per, line = _period(A, by_ds, ca.period_arms(A, by_ds, rows), args.period)
        flows = ("runs", "usd")
        if line:
            print(line)
        heads_p = ["", *(PERIOD_HEADS[f] for f in flows)] if per else []
        if args.systems:
            _table(
                ["system", "model", "provider", "datasets", "arms", "spend", "rank on each goal", *heads_p],
                [
                    [
                        c["system"],
                        c["model"] or "—",
                        c["provider"] or "—",
                        ", ".join(c["datasets"]),
                        c["arms"],
                        cb.fmt_amount(c["usd"], "usd") if c["usd"] else "—",
                        "; ".join(f"{g['goal_id']} #{i} of {n}" for g, _d, i, n in c["ranks"]) or "—",
                        *(_pcells(per[f"c:{c['system']}"], flows) if per else []),
                    ]
                    for c in ca.system_rows(A, by_ds, rows, cb.window(A, by_ds)["spend"])
                ],
            )
            return 0
        # "dataset" groups by what can be ranked together, as the page does: a dataset, scored one way, on one measure.
        key = "" if args.by == "none" else "set" if args.by == "dataset" else args.by
        # One dataset asked for is that group opened; otherwise a group shows its first three, as the page does.
        fold = 0 if args.all or args.dataset_id or not key else 3
        groups: dict = {}
        for r in sorted(rows, key=ca._reading_order):
            groups.setdefault((ca.set_key(r) if key == "set" else r[key]) if key else "", []).append(r)
        has_record = any(r["record"] for r in rows)
        for name in sorted(groups):
            if key:
                print(
                    f"\n{dict(ca.GROUPS)[key]} {name or '—'} ({len(groups[name])} arm{'' if len(groups[name]) == 1 else 's'})"
                )
            _table(
                [
                    "arm id",
                    "how measured",
                    "dataset",
                    "model",
                    "provider",
                    *(["model record"] if has_record else []),
                    "role",
                    "deciding measure",
                    "cost / item",
                    "latency",
                    *heads_p,
                ],
                [
                    [
                        r["arm"],
                        r["how"]
                        + (" (wrote its own reference)" if r["kind"] == "t-author" else "")
                        + (f" ({r['moved']:+.3f} vs measured)" if r["moved"] is not None else "")
                        + ("; the goals read its re-score" if r["superseded_by"] else ""),
                        r["dataset"],
                        r["model"] or "—",
                        (r["provider"] or "—") + (" (local)" if r["local"] else ""),
                        *(
                            [
                                f"{r['record']}{'@' + r['deployment'] if r['deployment'] else ''} ({cm.SMOKE_WORDS[r['smoke']]})"
                                if r["record"]
                                else "—"
                            ]
                            if has_record
                            else []
                        ),
                        ", ".join(dict.fromkeys(r["roles"])) or "—",
                        f"{r['measure']} {_fmt(r['value'])} {'↓' if r['lower'] else '↑'}"
                        if r["measure"]
                        else "—",
                        "—" if r["cost"] is None else "$0" if r["cost"] == 0 else f"${r['cost']:.4f}",
                        "—"
                        if not r["latency"]
                        else f"{r['latency'] / 1000:.1f} s"
                        if r["latency"] >= 1000
                        else f"{r['latency']:.0f} ms",
                        *(_pcells(per[r["arm"]], flows) if per else []),
                    ]
                    for r in (groups[name][:fold] if fold else groups[name])
                ],
            )
            if fold and len(groups[name]) > fold:
                ds = groups[name][0]["dataset"]
                more = (
                    f"evh arms --dataset-id {ds} lists them, with the dataset's other groups "
                    f"({sum(r['dataset'] == ds for r in rows)} arms)"
                    if key == "set"
                    else "evh arms --all"
                )
                print(f"  … and {len(groups[name]) - fold} more: {more}")
        if any(r["roles"] for r in rows):
            print(
                "\nroles: leader, first on the goal's deciding measure among the arms its decision weighs (not "
                "significantly ahead of N: N it cannot be told apart from); recommended, what the goal's rule picks; "
                "baseline, the arm the goal promoted. ×N after an arm: N runs of it, averaged per item."
            )
        return 0
    want = _arm_ids(A, [args.arm], "runs")[0]
    hit = next(((ds, a) for ds, v in by_ds.items() for a in v["arms"] if a["arm"] == want), None)
    if hit is None:
        die(f"no arm {args.arm!r}: `evh arms` lists them", "not-found")
    ds, a = hit
    v = by_ds[ds]
    goals = {g["goal_id"]: g for g in A.goals()}
    print(a["label"] + ("  [baseline]" if a.get("baseline") else ""))
    for k, x in (
        ("dataset", ds),
        ("scored against", _scored(a)),
        ("goal", a.get("goal") or "—"),
        ("runs", a["runs"]),
        ("headline", f"{a['metric']} {_fmt(a['mean'])}"),
        ("last run", a["last"][:16].replace("T", " ") or "—"),
    ):
        print(f"  {k:15} {x}")
    if a.get("wrote"):
        print(
            "  note            wrote the reference it is scored against: its row measures agreement with itself"
        )
    if a.get("superseded_by"):
        print(f"  re-scored       the goals read its re-score, {a['superseded_by']}")
    sc = A.scores(a["arm"])
    cs = [(ax, cell_of(ax, sc)) for ax in builtin_axes()]
    if any(c["n"] or (c.get("tokens") or {}).get("n") for _, c in cs):
        print("\ncost and speed, per " + A.item_word + ":")
        for ax, c in cs:
            print(f"  {axis_title(ax):16} {cell_text(ax, c)}")
    print("\nmetrics:")
    _table(
        ["metric", "mean", f"{A.item_word}s", "better"],
        [
            [
                m,
                cb.metric_value(A, m, mean),
                k,
                "lower" if A.lower_is_better(m, ds) else ("neutral" if A.is_neutral(m, ds) else "higher"),
            ]
            for m, (mean, k) in sorted(a["means"].items(), key=lambda kv: (kv[0] != a["metric"], kv[0]))
        ],
    )
    if a["run_list"]:
        print("\nruns:")
        _table(
            ["run", "made", f"{A.item_word}s", "cost", "how"],
            [
                [
                    r["run_id"],
                    (r.get("created_at") or "")[:16].replace("T", " "),
                    r.get("items") if r.get("items") is not None else "—",
                    f"${r['cost_usd']:.6f}" if isinstance(r.get("cost_usd"), (int, float)) else "—",
                    r.get("derived") or "measured",
                ]
                for r in a["run_list"]
            ],
        )
    cfg_fn = getattr(A, "arm_config", None)
    cfg = cfg_fn(a["arm"]) if callable(cfg_fn) else {}
    if cfg.get("params"):
        print(
            f"\nconfig {cfg.get('config_id', '')} (adapter {cfg.get('adapter') or '—'}"
            + (f"; deployment {cfg['deployment']}" if cfg.get("deployment") else "")
            + "; credentials are never shown):"
        )
        for k, x in sorted(cfg["params"].items()):
            print(f"  {k:20} {x}")
    cond_fn = getattr(A, "conditions", None)
    cond = cond_fn(a["arm"]) if callable(cond_fn) else {}
    if cond:
        print("\nconditions:")
        for k, x in sorted(cond.items()):
            print(f"  {k:28} {x}")
    sib = cb._siblings(by_ds, a, ds)
    if sib:
        tiers = {r["id"]: r["tier"] for r in v["refs"]}
        print("\nthe same system, scored other ways:")
        _table(
            ["arm id", "scored against", "headline", "mean", "row"],
            [[x["arm"], _scored(x), x["metric"], _fmt(x["mean"]), _kind(x, tiers)] for x in sib],
        )
    rfn = getattr(A, "rounds", None)
    cid = a["arm"].rsplit("/", 1)[-1]
    for r in rfn() if callable(rfn) else []:
        retired = a["arm"] in cb._retired_arms(r) or cid in cb._retired_arms(r)
        if a["arm"] in (r.get("arms") or []) or retired:
            g = goals.get(r.get("goal", ""), {})
            print(
                f"round {r['round_id']} of {g.get('goal_id', r.get('goal', ''))}: {'retired' if retired else 'in play'}, {r.get('status', '')}"
            )
    for note in A.notes(a["arm"]):
        print(f"note: {note}")
    return 0


def _onboarding(r: dict) -> str:
    if r["kind"] == "code":  # code under test is replayed, not onboarded: its versions, as the page says
        vs = [x for x in r["record"].get("versions") or [] if isinstance(x, dict)]
        checked = sum(1 for x in vs if (x.get("faithfulness") or {}).get("items"))
        return f"{len(vs)} version(s), {checked} checked for faithfulness"
    if r["status"] == "none":
        return "none"
    return f"{ {'vetted': 'pass', 'onboarded': 'probed'}.get(r['status'], 'check') } {r['onboarded']}"


def _best(r: dict) -> str:
    return "; ".join(f"{g['goal_id']} #{i} of {n}" for g, _ds, i, n in r["best"]) or "—"


def models(argv) -> int:
    """evh models: every model record, or one in full as its page shows it."""
    ap = argparse.ArgumentParser(prog="evh models", description="Every model record, or one in full.")
    ap.add_argument("--model", help="one model in full: its record id")
    ap.add_argument("--kind", choices=("llm", "ml", "baseline"), help="only models of this kind")
    ap.add_argument(
        "--where",
        choices=("self-hosted", "hosted"),
        help="only models that run on our machines (a deployment with a server or device, no provider id), or only hosted ones",
    )
    ap.add_argument(
        "--status",
        choices=("vetted", "onboarded", "check", "none"),
        help="only models whose onboarding passed and an arm passed its smoke (vetted), whose onboarding passed with no arm smoked (onboarded), any flagged something (check), or none ran (none)",
    )
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    rows = cm.model_rows(A, by_ds)
    if not args.model:
        rows = [
            r
            for r in rows
            if (not args.kind or r["kind"] == args.kind)
            and (not args.where or r["hosting"] == args.where)
            and (not args.status or r["status"] == args.status)
        ]
        if not rows:
            print("no model matches" if cm.entries(A) else "no model records: data/models/<model_id>.yaml")
            return 0
        _table(
            [
                "model",
                "kind",
                "where",
                "weights",
                "build",
                "deployments",
                "settings",
                "onboarding",
                "arms",
                "goals",
                "best result",
            ],
            [
                [
                    r["id"],
                    r["kind"],
                    r["hosting"] or "—",
                    r["weights"] or "—",
                    ", ".join(r["build"]) + (" (differs)" if r["differs"] else "") if r["build"] else "—",
                    ", ".join(b["id"] for b in r["deployments"]) or "—",
                    r["settings"],
                    _onboarding(r),
                    len(r["arms"]),
                    ", ".join(g["goal_id"] for g in r["goals"]) or "—",
                    _best(r),
                ]
                for r in rows
            ],
        )
        return 0
    r = next((x for x in rows if x["id"] == args.model), None)
    if r is None:
        die(f"no model {args.model!r}: `evh models` lists them", "not-found")
    rec = r["record"]
    print(r["name"] + f"  [{r['kind']}]")
    for k, x in (
        ()
        if rec.get("kind") == "code"
        else (
            ("weights", r["weights"] or "—"),
            ("licence", r["licence"] or "—"),
            ("aliases", ", ".join(rec.get("aliases") or [])),
            ("where", r["hosting"] or "—"),
            ("onboarding", _onboarding(r)),
        )
    ):
        print(f"  {k:15} {x}")
    why = rec.get("settings_why") or {}
    for k, x in (rec.get("settings") or {}).items():
        print(f"  setting {k:12} {x}" + (f"  ({why[k]})" if why.get(k) else ""))
    if rec.get("kind") == "code":  # code under test (the fleet's feedback 27): its versions, not deployments
        print(f"  {'repository':15} {rec.get('repo') or '—'}")
        print("\nversions:")
        vrows = cm.version_rows(rec)
        if vrows:
            _table(["version", "in production", "what changed", "faithfulness"], vrows)
        else:
            print("  none recorded: list its commits under `versions`")
        return 0
    print("\ndeployments:")
    if r["deployments"]:
        _table(
            [
                "deployment",
                "where",
                "server or device",
                "build",
                "matches the record",
                "checked",
                "onboarding",
            ],
            [
                [
                    b["id"],
                    b["where"] + (f" ({b['backend']})" if b.get("backend") else ""),
                    b.get("server") or b.get("device") or b.get("backend") or "—",
                    cm.build_text(b),
                    f"differs: {diff}" if diff else "yes",
                    cm.day(b.get("checked_at")) or "—",
                    f"{o['status']} {cm.day(o.get('at'))}" if (o := b.get("onboarding") or {}) else "none",
                ]
                for b, diff in zip(r["deployments"], r["diffs"], strict=True)
            ],
        )
    else:
        print("  none recorded")
    print("\nonboarding:")
    if r["deployments"]:
        for dep in r["deployments"]:
            onb = dep.get("onboarding") or {}
            if not onb:
                print(f"  {dep['id']}: not onboarded: evh model-onboard {r['id']} --deployment {dep['id']}")
                continue
            print(
                f"  {dep['id']}: {onb.get('status')} {cm.day(onb.get('at'))}"
                + (f" on {onb['where']}" if onb.get("where") else "")
            )
            for k, v in (onb.get("report") or {}).items():
                print(f"    {k.replace('_', ' '):16} {cm.kv(v) if isinstance(v, dict) else v}")
            for f in onb.get("flags") or []:
                print(f"    flag: {f}")
    else:
        print(f"  not onboarded: evh model-onboard {r['id']}")
    print("\nsettings history:")
    hist = sorted(rec.get("history") or [], key=lambda h: str(h.get("at")), reverse=True)
    if hist:
        _table(
            ["when", "what changed", "why"],
            [
                [
                    cm.day(h.get("at")),
                    f"{h.get('what')}: {h.get('from', '—')} → {h.get('to', '—')}"
                    if "from" in h or "to" in h
                    else h.get("what"),
                    h.get("why") or "—",
                ]
                for h in hist
            ],
        )
    else:
        print("  none recorded")
    print("\narms:")
    if r["arms"]:
        cfg_fn = getattr(A, "arm_config", None)
        _table(
            ["arm id", "goal", "its settings", "arm smoke", "result"],
            [
                [
                    a["arm"],
                    a["goal"]["goal_id"] if a["goal"] else "—",
                    ", ".join(
                        cm.arm_settings(
                            rec, ((cfg_fn(a["arm"]) if callable(cfg_fn) else {}) or {}).get("params") or {}
                        )
                    )
                    or "—",
                    cm.SMOKE_WORDS[a["smoke"]],
                    f"{a['measure']} {_fmt(a['value'])}" if a["measure"] else "—",
                ]
                for a in r["arms"]
            ],
        )
    else:
        print("  none")
    return 0


def goals(argv) -> int:
    """evh goals: every goal, or one with its arms on each of its datasets."""
    ap = argparse.ArgumentParser(
        prog="evh goals", description="Every goal, or one with its answer per dataset."
    )
    ap.add_argument("--goal", help="one goal: what it is for, and its arms on each dataset")
    ap.add_argument(
        "--arms",
        action="append",
        metavar="PATTERN",
        help="with --goal: only arms whose arm or system id contains PATTERN (or fits it, as a glob when it has "
        "* ? or [); repeatable or comma-separated. The baseline, the leader and the recommended arm stay",
    )
    ap.add_argument(
        "--top",
        type=int,
        metavar="N",
        help="with --goal: only the first N arms in the goal's own order (the same arms stay)",
    )
    _period_option(ap)
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    if (args.arms or args.top is not None) and not args.goal:
        die("--arms and --top need --goal: they choose among one goal's arms", "bad-argument")
    if args.top is not None and args.top < 1:
        die(f"--top must be at least 1, not {args.top}", "bad-argument")
    arm_pats = _goal_view.patterns(args.arms)
    A, by_ds = _adapter(args)
    gs = A.goals()
    if not args.goal:
        seen = cb.glance(A, by_ds)
        rows_p = cb.period_goals(A, by_ds)
        per, line = _period(A, by_ds, rows_p, args.period)
        flows = ("runs", "usd", "events")
        if line:
            print(line)
        _table(
            ["goal", "decides", "datasets", "systems filed", "recommended", "title"]
            + (["", *(PERIOD_HEADS[f] for f in flows)] if per else []),
            [
                [
                    g["goal_id"],
                    ((g.get("success_criteria") or {}).get("primary") or {}).get("measure", ""),
                    ", ".join(d.get("dataset_id", "") for d in g.get("datasets") or []),
                    cb.systems_filed(by_ds, g),
                    "; ".join(
                        r["recommended_label"]
                        + (f" ({' · '.join(r['vs_baseline'])} vs baseline)" if r["vs_baseline"] else "")
                        for r in seen
                        if r["goal"]["goal_id"] == g["goal_id"] and r["recommended"]
                    )
                    or "none yet",
                    g.get("title", ""),
                    *(_pcells(per[g["goal_id"]], flows) if per else []),
                ]
                for g in gs
            ],
        )
        if per:
            b = cp.bounds(args.period, date.today(), cb.window(A, by_ds)["first"])
            happened = sorted(
                (
                    (day, g["goal_id"], cb.plain(h))
                    for g in gs
                    for day, h in rows_p[g["goal_id"]]["events"]
                    if b["since"] <= day <= b["until"]
                ),
                reverse=True,
            )
            print("\nwhat happened in the period:")
            if happened:
                _table(["when", "goal", "what"], [list(x) for x in happened])
            else:
                print("  nothing")
        return 0
    g = next((x for x in gs if x["goal_id"] == args.goal), None)
    if g is None:
        die(f"no goal {args.goal!r}: one of {', '.join(x['goal_id'] for x in gs) or '(none)'}", "not-found")
    prim = (g.get("success_criteria") or {}).get("primary") or {}
    rfn = getattr(A, "rounds", None)
    rounds = [r for r in (rfn() if callable(rfn) else []) if r.get("goal") == g["goal_id"]]
    retired_in = cb.retired_in_of(A, g)
    print(f"{g.get('title') or g['goal_id']}\n")
    print(textwrap.fill(g.get("statement", ""), width=96))
    print(
        f"\n  decision   {g.get('decision', '')}\n  decides    {prim.get('measure', '')}, {prim.get('direction', '')} is better"
    )
    print(f"  strategy   {strategy_of(g)}: {STRATEGIES[strategy_of(g)]}")
    print(f"  tie-break  {', '.join(tie_break_of(g))}")
    for gr in (g.get("success_criteria") or {}).get("guardrails") or []:
        src = f" ({gr['source']})" if gr.get("source") else ""
        print(
            textwrap.fill(
                f"guardrail  {gr['name']}: {gr['rule']}{src}",
                width=96,
                initial_indent="  ",
                subsequent_indent="             ",
            )
        )
    for x in g.get("links") or []:
        if x.get("url"):
            print(f"  link       {x['note'] + ': ' if x.get('note') else ''}{x['url']}")
    from evaluation_harness import _study  # noqa: PLC0415

    for s in _study.of_goal(g["goal_id"]):
        print(f"\nstudy {s['study']}: {s['status']}, from {s['baseline']}, ${s['spent_usd']:.4f} spent"
              + (f"; ended: {s['end']}" if s["end"] else ""))  # fmt: skip
        for r in s["rows"]:
            print(f"  t{r['k']}  {r['outcome']!s:<9} {r['change'] or r['hypothesis']}  — {r['reason']}")
        for c in s["confirms"]:
            print(
                f"  confirmed on {c.get('test')}: {c.get('outcome')} (look {(c.get('look') or {}).get('number')})"
            )
    print("\nthe answer so far:")
    for d in g.get("datasets") or []:
        ds = d.get("dataset_id", "")
        bl = [b for b in (by_ds.get(ds) or {}).get("baselines", []) if b.get("goal") == g["goal_id"]]
        if bl:
            b = bl[-1]
            print(f"  {ds}: baseline {b.get('arm') or b['run']} (promoted {(b['promoted_at'] or '')[:10]})")
            print(textwrap.fill(b["reason"], width=92, initial_indent="    ", subsequent_indent="    "))
        else:
            print(f'  {ds}: no decision yet (evh run-promote --run <run_id> --reason "...")')
    by_group: list = []  # --json: each table's decision as named values
    for ans in cb.goal_answers(g, by_ds):
        ds = ans["dataset"]
        tiers = {r["id"]: r["tier"] for r in (by_ds.get(ds) or {}).get("refs", [])}
        print(f"\n{ds}" + (f" · {ans['role']}" if ans["role"] else ""))
        if ans["notes"]:
            print(textwrap.fill(ans["notes"], width=96, initial_indent="  ", subsequent_indent="  "))
        from evaluation_harness import _looks  # noqa: PLC0415

        looks_line = _looks.said(ds)
        if looks_line:
            print(f"  {looks_line}")
        from evaluation_harness import _exposure  # noqa: PLC0415

        if read_line := _exposure.line(ds):
            print(f"  {read_line}")
        if not ans["groups"]:
            print(f"  no arm records {prim.get('measure', '')}")
        for grp in ans["groups"]:
            what = grp["key"]
            gm = (grp["rows"][0].get("measure") if grp["rows"] else None) or prim.get("measure", "")
            dec = cb.group_decision(
                A,
                g,
                ds,
                grp["rows"],
                gm,
                retired_in,
                cb.gold_beside(tiers, ans["groups"], what),
            )
            shown = cb.shown_axes(dec)
            leader = dec["leader"]  # the decision's: never a retired or flagged arm
            base_arm = next((r["arm"] for r in grp["rows"] if r.get("baseline")), None)
            # The decision above was made over every arm; the filter only chooses the rows printed.
            on_show = _goal_view.select(
                grp["rows"], arm_pats, args.top, {x for x in (base_arm, leader, dec["recommended"]) if x}
            )
            hyps = {r["arm"]: _goal_view.hypothesis_of(A, r["arm"]) for r in on_show}
            hyps = {a: h for a, h in hyps.items() if h}
            print(f"\n  {'scored by ' + what if what.startswith('judge ') else 'scored against ' + what}")
            # The row kind (silver, judged, wrote its reference) is a column only when some row has one: a header
            # over a column of blanks reads as a misaligned table.
            with_kind = any(_kind(r, tiers) for r in on_show)
            _table(
                [
                    "arm",
                    f"mean {gm}",
                    f"{A.item_word}s",
                    "vs leader (paired test)",
                    "contender test (within the margin)",
                    *(axis_title(ax) for ax in shown),
                    *(["row"] if with_kind else []),
                    "flags",
                    "decision",
                    *(["hypothesis"] if hyps else []),
                ],
                [
                    [
                        r["label"]
                        + (" [baseline]" if r.get("baseline") else "")
                        + (" [recommended]" if dec["recommended"] == r["arm"] else "")
                        + (
                            f" [retired in {cb.retired_round(retired_in, r['arm'])}]"
                            if cb.retired_round(retired_in, r["arm"])
                            else ""
                        ),
                        _fmt(r["mean"]),
                        r["n"],
                        _goal_view.vs_text((dec["rows"][r["arm"]]["quality"]).get("vs_leader")),
                        _goal_view.ni_text((dec["rows"][r["arm"]]["quality"]).get("noninferior")),
                        *(cell_text(ax, dec["rows"][r["arm"]][ax["name"]]) for ax in shown),
                        *([_kind(r, tiers)] if with_kind else []),
                        "; ".join(r["flags"] + dec["out"].get(r["arm"], [])) or "—",
                        "leader" if r["arm"] == leader else "",
                        *([_goal_view.hypothesis_text(hyps.get(r["arm"]))] if hyps else []),
                    ]
                    for r in on_show
                ],
            )
            if len(on_show) < len(grp["rows"]):
                print(
                    f"  {len(on_show)} of {len(grp['rows'])} arms shown, {len(grp['rows']) - len(on_show)} left out by "
                    + " ".join(
                        [f"--arms {p}" for p in arm_pats]
                        + ([f"--top {args.top}"] if args.top is not None else [])
                    )
                    + " (the baseline, the leader and the recommended arm are always shown)"
                )
            by_group.append(
                _goal_view.group_values(
                    dataset=ds,
                    scored_against=what,
                    measure=gm,
                    dec=dec,
                    rows=grp["rows"],
                    shown=on_show,
                    axes=shown,
                    baseline=base_arm,
                    hypotheses=hyps,
                    retired={r["arm"]: cb.retired_round(retired_in, r["arm"]) for r in on_show},
                    arms_filter=arm_pats,
                    top=args.top,
                )
            )
            rec = dec["recommended"]
            label = {r["arm"]: r["label"] for r in grp["rows"]}
            print(
                f"\n  recommended: {label[rec]}"
                if rec
                else "\n  shown, not recommended"
                if dec.get("shown_only")
                else "\n  no single arm recommended" + (" yet" if dec["leader"] else ": no arm is eligible")
            )
            for w in [*dec["why"], cb.baseline_gap(A, dec, grp["rows"], gm)]:
                if w:
                    print(textwrap.fill(w, width=96, initial_indent="    - ", subsequent_indent="      "))
    # The group the goal decides on (the first that recommends), else the first: its answer by name.
    head = next((x for x in by_group if not x["shown_only"]), by_group[0] if by_group else {})
    _jsonout.values(
        {
            "goal": g["goal_id"],
            **{
                k: head.get(k)
                for k in ("leader", "baseline", "contenders", "recommended", "vs_leader")
                if head
            },
            "groups": by_group,
        }
    )
    # The goal page's rounds, as `evh rounds --goal` lists them (it has the evidence in full).
    if rounds:
        print("\nrounds (evh rounds --goal " + g["goal_id"] + " for the evidence):")
        for r in rounds:
            c = (r.get("conclusion") or {}).get("text", "")
            print(
                f"  {r['round_id']:4} {r.get('status', ''):7} {len(r.get('arms') or [])} arm(s), {len(r.get('retired') or [])} retired  {c[:70]}"
            )
    return 0


def _arm_ids(A, tokens: list, label: str) -> list:
    """Arm ids from what the user typed: a full arm id, or a system id looked up among the arms read under `label`."""
    known = A.arms()
    out = []
    for t in tokens:
        if t in known:
            out.append(t)
            continue
        prefix = model_runs.arm_prefix(label)
        hits = [a for a in known if a.rsplit("/", 1)[-1] == t and a.split("/", 1)[0] == prefix]
        if len(hits) != 1:
            near = [a for a in known if a.rsplit("/", 1)[-1] == t]
            die(
                f"{t!r}: "
                + (
                    f"{len(hits)} arms read as {label or 'the plain label'} match; name the arm id: {', '.join(near)}"
                    if near
                    else "no arm with that id; `evh datasets --dataset-id <id>` lists them"
                ),
                "not-found",
            )
        out.append(hits[0])
    return out


def inspect(argv) -> int:
    """evh inspect: the inspector's comparison, conditions, breakdown or one item, in the terminal."""
    ap = argparse.ArgumentParser(
        prog="evh inspect",
        description="The inspector's comparison, in the terminal.",
        # No abbreviations: `--items` (removed for the sheet) would otherwise be read as `--items-out`.
        allow_abbrev=False,
    )
    pick = ap.add_mutually_exclusive_group()
    pick.add_argument("--runs", help="arms: system ids (looked up under --label) or arm ids, comma-separated")
    pick.add_argument("--round", help="the arms in play in this round of a goal (rN; ADR-0004)")
    ap.add_argument("--goal", help="the goal --round belongs to, when several goals have one")
    ap.add_argument(
        "--baseline",
        help="the arm the others are tested against (default: a round's leader, else the first)",
    )
    ap.add_argument("--metric", help="default: a round's goal measure, else the arms' primary metric")
    ap.add_argument(
        "--label",
        default="",
        help='the label system ids are looked up under: "", silver, repeats, "rescored cd35dc1f", '
        "judged/<scorer> (default: the plain arm); `evh runs-list` shows what is there",
    )
    ap.add_argument(
        "--where",
        action="append",
        default=[],
        help="FIELD:VALUE or FIELD:LO..HI, keep only matching items (repeatable)",
    )
    ap.add_argument("--by", help="break the comparison down by a choice or yes/no field")
    ap.add_argument(
        "--disagree",
        action="store_true",
        help="only the items where the arms decided differently from the baseline (with --sheet: from the first run; the adapter's same(a, b))",
    )
    ap.add_argument("--item", help="show one item: each arm's output beside the reference")
    ap.add_argument(
        "--no-rescore",
        action="store_true",
        help="read only what is on record (the inspector's re-score box unticked; an adapter that can re-score)",
    )
    ap.add_argument(
        "--analysis",
        action="store_true",
        help="the analysis charts as numbers: spread per arm, difference from the baseline",
    )
    ap.add_argument(
        "--x", dest="xmetric", help="with --analysis: each arm's mean on this metric too (the scatter)"
    )
    ap.add_argument(
        "--sheet",
        action="store_true",
        help="one sheet of --dataset-id: its items down, a column per run in --runs (the first is production's): what it wrote, its scores, the labels, the winner, the signals, and a footer per run",
    )
    ap.add_argument("--dataset-id", help="with --sheet: the dataset whose items are shown")
    ap.add_argument(
        "--scores-only",
        action="store_true",
        help="with --sheet: leave the runs' outputs out, keep their scores",
    )
    ap.add_argument(
        "--wrong-against",
        metavar="SET",
        help="with --sheet: only the items where the first run's decision is not this label set's (SET or DATASET/SET)",
    )
    ap.add_argument(
        "--new-vs",
        metavar="DATASET",
        help="with --sheet: only the items with a field value this dataset has never had",
    )
    ap.add_argument(
        "--split",
        action="store_true",
        help="with --sheet: only the items the candidates (the runs after the first) decided differently among themselves",
    )
    ap.add_argument(
        "--unlabelled", action="store_true", help="with --sheet: only the items no label set labels yet"
    )
    ap.add_argument(
        "--csv",
        type=Path,
        metavar="FILE",
        help="with --sheet: write the sheet as CSV (UTF-8 with the mark Excel needs) instead of printing it",
    )
    ap.add_argument(
        "--fill",
        choices=_sheet.FILLS,
        help="with --csv: add the columns to fill. label: label, also right, note. pick, scores: the outputs as blind columns A, B, C… shuffled per row, a key beside the sheet (sheet.key.json), the rubric as its first row; tags: a failure_modes column beside each arm's output (with --modes), a key beside the sheet; evh sheet-import reads it back",
    )
    ap.add_argument(
        "--modes",
        help="with --fill tags: the failure-mode list the tags name (data/failure-modes/<id>.yaml)",
    )
    ap.add_argument(
        "--choices",
        help="with --fill label: the allowed answers, comma-separated (e.g. file,dismiss,escalate), written into the label column's header",
    )
    ap.add_argument(
        "--seed", type=int, default=None, help="with --fill pick or scores: the shuffle's seed (default 0)"
    )
    ap.add_argument(
        "--rubric",
        type=Path,
        help="with --fill pick or scores: a file saying what to judge (default: a plain one)",
    )
    ap.add_argument(
        "--scale",
        help="with --fill scores: the scores' range, LO..HI (default 1..5)",
    )
    ap.add_argument(
        "--crosstab",
        metavar="A,B",
        help="two per-item scores of the runs: per group, a table of item counts, A's values down, B's across, and the items off the diagonal",
    )
    ap.add_argument(
        "--group",
        metavar="FIELD",
        help="with --crosstab: group by this field of the run's prediction rows (a dotted path, e.g. _meta.gates); default: one group",
    )
    ap.add_argument(
        "--group-match",
        metavar="REGEX",
        help="with --group: the group is the first (...) of the regex found in the field's text, else the whole match; no match: none",
    )
    ap.add_argument(
        "--max-ids",
        type=int,
        default=8,
        help="with --crosstab: item ids listed per cell (default 8; --json: all)",
    )
    ap.add_argument(
        "--items-out",
        action="store_true",
        help="per item of --runs: each run's whole output and scores beside the reference and labels (with --disagree: only the items the runs decided differently from the first)",
    )
    ap.add_argument(
        "--max-chars",
        type=int,
        default=300,
        help="with --items-out: characters of each output printed (default 300, 0 = all; --json: all)",
    )
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A = load_catalog_adapter(args.adapter)
    cs.set_adapter(A)
    if os.environ.get("EVH_PUBLIC"):
        # Run for a public MCP server: the inspector's public rules, so a --where or --by on a
        # field not marked public is refused instead of leaking its values through the counts.
        cs.LIMITS["hosts"] = ("public",)
    only_sheet = [
        f
        for f, on in (
            ("--dataset-id", args.dataset_id),
            ("--wrong-against", args.wrong_against),
            ("--new-vs", args.new_vs),
            ("--split", args.split),
            ("--unlabelled", args.unlabelled),
            ("--scores-only", args.scores_only),
            ("--csv", args.csv),
            ("--fill", args.fill),
            ("--choices", args.choices),
            ("--modes", args.modes),
            ("--seed", args.seed is not None),
            ("--rubric", args.rubric),
            ("--scale", args.scale),
        )
        if on
    ]
    if args.crosstab or args.items_out:
        return _crosstab_or_items(A, args, only_sheet)
    for flag, on in (
        ("--group", args.group),
        ("--group-match", args.group_match),
        ("--max-ids", args.max_ids != 8),
        ("--max-chars", args.max_chars != 300),
    ):
        if on:
            die(
                f"{flag}: with --crosstab A,B" if flag != "--max-chars" else f"{flag}: with --items-out",
                "bad-argument",
            )
    if args.sheet:
        return _sheet_view(A, args)
    if only_sheet:
        die(
            f"{', '.join(only_sheet)}: with --sheet (evh inspect --sheet --dataset-id D --runs A,B …)",
            "bad-argument",
        )
    if not (args.runs or args.round):
        die("one of --runs, --round or --sheet (with --dataset-id) is required", "bad-argument")
    round_leader = None
    if args.round:
        from evaluation_harness._rounds import arms_of, resolve  # noqa: PLC0415
        from evaluation_harness.rounds import _best, _goal  # noqa: PLC0415

        rnd = resolve(args.round, args.goal)
        tokens = arms_of(rnd)
        if not tokens:
            die(f"round {args.round} has no arms in play yet", "not-enough")
        # A round is read on its goal's measure, against its leader (as `evh rounds` reads it):
        # defaulting to the first arm made an arm with no score the baseline and fell back to
        # cost_usd.
        prim = (_goal(rnd["goal"]).get("success_criteria") or {}).get("primary") or {}
        if not args.metric and prim.get("measure"):
            args.metric = prim["measure"]
        known = set(A.arms())
        from evaluation_harness.rounds import _arm  # noqa: PLC0415

        in_play = [a for a in (_arm(A, rnd["dataset_id"], c) for c in tokens) if a in known]
        unscored = [
            a.rsplit("/", 1)[-1] for a in in_play if not (A.scores(a).get(args.metric) or {}).get("values")
        ]
        if unscored:
            print(f"NOTE: no {args.metric} recorded for {', '.join(unscored)}: left out of the comparison")
            tokens = [t for t in tokens if t not in unscored]
            if not tokens:
                die(f"no arm of round {args.round} records {args.metric} yet", "not-enough")
        round_leader = _best(
            A,
            [a for a in in_play if a.rsplit("/", 1)[-1] in tokens],
            args.metric,
            prim.get("direction") == "lower",
        )
    else:
        tokens = [t.strip() for t in args.runs.split(",") if t.strip()]
    arms = _arm_ids(A, tokens, args.label)
    base = (
        _arm_ids(A, [args.baseline], args.label)[0]
        if args.baseline
        else (round_leader if round_leader and round_leader in arms else arms[0])
    )
    label = {a: A.describe(a)["label"] for a in arms}
    if args.item:
        ref = A.describe(base).get("reference", "")
        got = cs.item({"arms": [",".join(arms)], "item": [args.item], "ref": [ref] if ref else [""]})
        if got.get("error"):
            die(got["error"], "bad-argument")
        for f in got.get("fields") or []:
            print(f"  {f.get('label') or f['name']}: {f['value']}")
        src = got.get("source") or {}
        if src.get("kind") == "text":
            print(f"\n== {args.item} (the {A.item_word} itself)\n{src['text'].rstrip()}")
        elif src.get("note"):
            print(f"\n({src['note']})")
        if got.get("reference"):
            print(f"\n== {ref} (reference)\n{(got['reference']['view'] or {}).get('text', '(none)')}")
        for a, view in got["views"].items():
            # What the page prints above an output: which run it is, and for a repeated arm that
            # it is one repeat beside the mean of all of them.
            info = " · ".join(f"{k} {v}" for k, v in (view.get("info") or {}).items())
            print(
                f"\n== {label[a]}{'  (baseline)' if a == base else ''}"
                + (f"\n({info})" if info else "")
                + f"\n{view.get('text') or view.get('note', '(none)')}"
            )
        return 0
    params = {
        "runs": [",".join(arms)],
        "baseline": [base],
        "metric": [args.metric or ""],
        "where": args.where,
        "disagree": ["1" if args.disagree else ""],
        "by": [args.by or ""],
        "rescore": ["0" if args.no_rescore else "1"],
    }
    d = cs.compare(params)
    if d.get("error"):
        die(d["error"], "bad-argument")
    for w in d.get("warnings") or []:
        print(f"NOTE: {w}")
    if d.get("state") == "not scorable":
        return 1
    label = {a["id"]: a["label"] for a in d.get("arms") or []} | label
    vals = list((d.get("series") or {}).get(d["baseline"], {}).values())
    better = "higher" if d.get("higher_is_better") else "lower"
    # The round's leader stands in as the baseline unless the round started from a promoted one.
    what = ""
    if round_leader and not args.baseline and d["baseline"] == round_leader:
        from evaluation_harness.rounds import _dirs  # noqa: PLC0415

        if not any(model_runs.run_of(x).name == rnd.get("baseline") for x in _dirs(A, round_leader)):
            what = " (the round's leader)"
    print(
        f"{d['metric']} ({better} is better) · baseline {label.get(d['baseline'], d['baseline'])}{what}: mean {_fmt(statistics.fmean(vals) if vals else None)} · Holm across {d['family_size']}\n"
    )
    _table(
        ["run vs baseline", "verdict", "n", "mean", "Δ", "95% CI of Δ", "wins–losses", "p", "Holm threshold"],
        [
            [
                label.get(r["arm"], r["arm"]),
                r["verdict"],
                r["n"],
                _fmt(r["mean"]),
                _fmt(r["delta"]),
                "—" if not r.get("ci") else f"{r['ci'][0]:+.3f} to {r['ci'][1]:+.3f}",
                f"{r['wins']}–{r['losses']}" + (f" ({r['ties']} ties)" if r.get("ties") else ""),
                "—" if r.get("p") is None else fmt_p(r["p"]),
                "—" if not r.get("threshold") else f"{r['threshold']:.4f}",
            ]
            for r in sorted(d["rows"], key=lambda r: r.get("p") if r.get("p") is not None else 9)
        ],
    )
    avgs = d.get("averages") or {}
    if avgs:
        base_vals = list((d.get("series") or {}).get(d["baseline"], {}).values())
        base_mean = statistics.fmean(base_vals) if base_vals else None
        print(f"\nAverage only · {len(avgs)}: no per-{A.item_word} scores, so no test")
        _table(
            ["run", "recorded average", "vs the baseline's mean"],
            [
                [label.get(a, a), _fmt(v), "—" if base_mean is None else f"{v - base_mean:+.3f}"]
                for a, v in sorted(
                    avgs.items(), key=lambda kv: -kv[1] if d.get("higher_is_better") else kv[1]
                )
            ],
        )
    c = d.get("conditions")
    if c and c.get("fields"):
        if not c["differ"]:
            print(
                f"\nSame conditions: all {c['fields']} recorded fields match (machine, libraries, harness, scorer, items, reference bytes)."
            )
        else:
            print(f"\nConditions: {len(c['differ'])} of {c['fields']} fields differ")
            for w in c["warnings"]:
                print(f"  NOTE: {w}")
            order = list(d["series"])
            _table(
                ["field", *[label.get(a, a) for a in order]],
                [
                    [f["name"], *[_condition_value(f["values"].get(a, "—")) for a in order]]
                    for f in c["differ"]
                ],
            )
    if args.analysis:
        _analysis(d, label, args.xmetric)
    br = d.get("breakdown")
    if br:
        print(f"\nby {args.by} (Holm across {br['family_size']}):")
        _table(
            [args.by, "run vs baseline", "verdict", "n", "Δ", "p"],
            [
                [
                    g["group"],
                    label.get(r["arm"], r["arm"]),
                    r["verdict"],
                    r["n"],
                    _fmt(r["delta"]),
                    "—" if r.get("p") is None else fmt_p(r["p"]),
                ]
                for g in br["groups"]
                for r in g["rows"]
            ],
        )
    return 0


def _show(heads: list, rows: list) -> None:
    """A table of the sheet: under --json its values as they are, in the terminal numbers rounded and gaps a dash."""
    if _jsonout.table(heads, rows):
        return
    _table(heads, [["—" if v is None else _fmt(v) if isinstance(v, float) else v for v in r] for r in rows])


def _sheet_view(A, args) -> int:
    """evh inspect --sheet --dataset-id D --runs A,B: the dataset's items down, a column per run: printed, or written
    as a CSV to fill (RFC-023, _sheet)."""
    from evaluation_harness import _picks  # noqa: PLC0415

    if os.environ.get("EVH_PUBLIC"):
        die("--sheet shows the items' outputs and labels: not served publicly", "not-public")
    if not args.dataset_id:
        die("--sheet: name the dataset with --dataset-id", "bad-argument")
    if args.round:
        die(
            "--sheet takes --runs (run ids, or system ids: their latest run on the dataset), not --round",
            "bad-argument",
        )
    for flag, on in (("--item", args.item), ("--analysis", args.analysis), ("--baseline", args.baseline)):
        if on:
            die(
                f"{flag}: not with --sheet (the sheet is a view of every item; the first run stands for production)",
                "bad-argument",
            )
    runs = [t.strip() for t in (args.runs or "").split(",") if t.strip()]
    for flag, n, on in (
        ("--disagree", 2, args.disagree),
        ("--split", 3, args.split),
        ("--wrong-against", 1, args.wrong_against),
    ):
        if on and len(runs) < n:
            die(f"{flag} needs {n} run(s) or more in --runs (the first is production's)", "bad-argument")
    if args.fill and not args.csv:
        die("--fill: with --csv FILE (the sheet to fill in)", "bad-argument")
    if args.choices and args.fill != "label":
        die("--choices: with --fill label", "bad-argument")
    if (args.fill == "tags") != bool(args.modes):
        die("--fill tags and --modes go together: name the failure-mode list the tags use", "bad-argument")
    if args.fill not in ("pick", "scores") and (args.seed is not None or args.rubric or args.scale):
        die("--seed, --rubric and --scale: with --fill pick or scores", "bad-argument")
    if args.scale and args.fill != "scores":
        die("--scale: with --fill scores", "bad-argument")
    model = _sheet.build(
        args.dataset_id,
        runs,
        cs._fields_of,
        metric=args.metric,
        label=args.label,
        wrong_against=args.wrong_against,
        new_vs=args.new_vs,
    )
    found = _sheet.by_where(model, args.where)
    if args.by and args.by not in model["decl"]:
        die(f"--by {args.by}: no field {args.by!r} on {args.dataset_id}", "not-found")
    wanted = [
        s
        for s, on in (
            ("wrong", args.wrong_against),
            ("disagree", args.disagree),
            ("split", args.split),
            ("new", args.new_vs),
            ("unlabelled", args.unlabelled),
        )
        if on
    ]
    shown = _sheet.by_signals(found, wanted)
    from evaluation_harness import _exposure  # noqa: PLC0415

    _exposure.read_by_harness(
        args.dataset_id, [r["item"] for r in shown], "inspect --sheet" + (" (a CSV)" if args.csv else "")
    )
    if args.csv:
        return _sheet_csv(args, model, shown)
    counts = _sheet.counts(found)
    way = (
        f"{model['metric']} ({'lower' if model['lower'] else 'higher'} is better)" if model["metric"] else ""
    )
    print(
        f"{args.dataset_id}: {len(shown)} of {len(found)} {A.item_word}(s)"
        + (f" ({', '.join(wanted)})" if wanted else "")
        + "".join(f" · {s} {n}" for s, n in counts.items() if n)
        + (f" · read on {way}" if way else "")
        + "\n"
    )
    state = _picks.state()

    def picked(item: str) -> str:
        p = state.get((args.dataset_id, item)) or {}
        if p.get("action") != "pick":
            return ""
        return f"for {', '.join(p['for'])}" if p.get("for") else "no target yet"

    head, body, _ = _sheet.flat(model, shown, scores_only=args.scores_only, short=True, picked=picked)
    _show(head, body)
    if runs and model["metric"]:
        fhead, flines = _sheet.footer_table(model, _sheet.footer(model, shown))
        print(f"\nper run, over the {len(shown)} row(s) shown:")
        _show(fhead, flines)
    if args.by:
        groups: dict[str, list] = {}
        for r in shown:
            groups.setdefault(str(r["fields"].get(args.by, "—")), []).append(r)
        print(f"\nby {args.by}:")
        _table(
            [args.by, "rows", *_sheet.SIGNALS],
            [[g, len(rs), *_sheet.counts(rs).values()] for g, rs in groups.items()],
        )
    if shown:
        items = " ".join(f"--item {r['item']}" for r in shown)
        print(
            f'\npick them:  evh pick --dataset-id {args.dataset_id} {items} [--for V] [--tag k=v] [--note "…"]'
        )
        print(
            f"label them: evh label-sheet --dataset-id {args.dataset_id} {items} --out sheet.csv"
            + (f" --runs {','.join(runs)}" if runs else "")
        )
    return 0


def _sheet_csv(args, model: dict, shown: list) -> int:
    """--csv FILE: the sheet written as CSV for a spreadsheet (UTF-8 with the mark Excel needs), with the columns to
    fill when --fill says so; for a blind fill the key beside it (sheet.key.json). Never over a file that exists."""
    import re  # noqa: PLC0415

    from evaluation_harness._common import write_json  # noqa: PLC0415
    from evaluation_harness._sheets import write_csv  # noqa: PLC0415

    key_file = _sheet.key_path(args.csv)
    blind = args.fill in ("pick", "scores")
    for f in (args.csv, key_file if blind or args.fill == "tags" else None):
        if f is not None and _store.exists(f):
            die(f"{f} exists: a sheet is not overwritten (you may have filled it)", "would-overwrite")
    if args.fill == "tags":
        from evaluation_harness import _tags  # noqa: PLC0415

        modes = _tags.load_modes(args.modes)
        head, body, key = _tags.tag_sheet(model, shown, modes)
        write_csv(head, body, args.csv)
        write_json(key_file, key)
        print(
            f"{args.csv}: {len(body) - 1} row(s), a failure_modes column beside each of {len(model['arms'])} arm(s)' "
            f"outputs; the key is {key_file}"
        )
        print(
            f"  fill each failure_modes cell with modes of {args.modes} ({', '.join(_tags.mode_ids(modes))}; mode|mode "
            "for several), `ok` when the output is fine, blank when not read; then: "
            f"evh sheet-import {args.csv} --dataset-id {args.dataset_id} --by <who> --tags <name> --modes {args.modes}"
        )
        return 0
    if not blind:
        choices = [c.strip() for c in (args.choices or "").split(",") if c.strip()] or None
        head, body = _sheet.csv_sheet(
            model, shown, scores_only=args.scores_only, fill=args.fill, choices=choices
        )
        write_csv(head, body, args.csv)
        print(f"{args.csv}: {len(shown)} row(s), {len(head)} column(s)")
        if args.fill == "label":
            print(
                "  fill `label` (answers just as right in `also right`, separated by |), then: "
                f"evh sheet-import {args.csv} --dataset-id {args.dataset_id} --by <you> --set <name>"
            )
        return 0
    scale = (1, 5)
    if args.scale:
        m = re.fullmatch(r"(-?\d+)\.\.(-?\d+)", args.scale.strip())
        if not m or int(m.group(1)) >= int(m.group(2)):
            die(f"--scale {args.scale}: LO..HI, two whole numbers, LO below HI (e.g. 1..5)", "bad-argument")
        scale = (int(m.group(1)), int(m.group(2)))
    if args.rubric and not _store.is_file(args.rubric):
        die(f"--rubric: no file {args.rubric}", "not-found")
    rubric = _sheet.rubric_text(
        args.fill, scale, _store.read_text(args.rubric, encoding="utf-8") if args.rubric else None
    )
    head, body, key, left_out = _sheet.blind(
        model, shown, args.fill, seed=args.seed or 0, rubric=rubric, scale=scale
    )
    if len(body) < 2:
        die(
            f"--fill {args.fill}: no row has outputs to judge (a pick needs two outputs on a row)",
            "not-enough",
        )
    write_csv(head, body, args.csv)
    write_json(key_file, key)
    print(
        f"{args.csv}: {len(body) - 1} row(s) to judge, {len(model['arms'])} blind column(s)"
        + (f" ({left_out} row(s) left out: too few outputs)" if left_out else "")
        + f"\n  the key (which letter was which run on each row) is {key_file}: keep it here, not with the sheet"
    )
    what = "`pick` (the best letter, `A|B` for a tie)" if args.fill == "pick" else "`score: A`, `score: B`…"
    print(
        f"  fill {what}, then: evh sheet-import {args.csv} --dataset-id {args.dataset_id} --by <who> --scorer <name>"
    )
    return 0


def _crosstab_or_items(A, args, only_sheet: list) -> int:
    """--crosstab A,B / --items-out: the per-item reads of --runs (the prediction rows, the outputs)."""
    mode = "--crosstab" if args.crosstab else "--items-out"
    if args.crosstab and args.items_out:
        die("--crosstab and --items-out are two views: one at a time", "bad-argument")
    if os.environ.get("EVH_PUBLIC") and (args.items_out or args.group):
        # A recorded field can hold text; the counts of two scores are numbers and ids.
        die(
            f"{'--items-out' if args.items_out else '--group'} shows recorded texts: not served publicly",
            "not-public",
        )
    clash = [
        f
        for f, on in (
            ("--sheet", args.sheet),
            ("--item", args.item),
            ("--analysis", args.analysis),
            ("--round", args.round),
            ("--by", args.by),
            *([("--disagree", args.disagree)] if args.crosstab else []),
            *[(f, True) for f in only_sheet],
        )
        if on
    ]
    if clash:
        die(
            f"{', '.join(clash)}: not with {mode} (it reads the --runs given, one item at a time)",
            "bad-argument",
        )
    if not args.runs:
        die(f"{mode}: name the runs with --runs", "bad-argument")
    if args.group_match and not args.group:
        die("--group-match: with --group FIELD", "bad-argument")
    if args.crosstab:
        _crosstab(A, args)
    else:
        _items_out(A, args)
    return 0


def _run_of(A, arm: str):
    """(dataset id, the run folder) of an arm id."""
    from evaluation_harness.label_sheet import run_dir  # noqa: PLC0415

    ds = A.describe(arm).get("dataset", "")
    return ds, run_dir(arm, ds)


def _is_score(v) -> bool:
    """A per-item score's value: a number, true/false, or none (an item it was not scored on)."""
    return v is None or isinstance(v, (bool, int, float))


def _label(v) -> str:
    """A value as a table names it: whole numbers without the .0, a gap `none`."""
    if v is None:
        return "none"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)


def _path(row: dict, dotted: str):
    """The value at a dotted path in a prediction row (`_meta.gates`), None when any step is missing."""
    cur = row
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _order(vals) -> list:
    """Labels in the order a table reads: numbers ascending, then text, `none` last."""

    def key(v: str):
        try:
            return (1 if v == "none" else 0, 0, float(v), "")
        except ValueError:
            return (1 if v == "none" else 0, 1, 0.0, v)

    return sorted(set(vals), key=key)


def _crosstab(A, args) -> None:
    """evh inspect --runs R --crosstab A,B [--group FIELD [--group-match REGEX]] [--where F:V]: per group, the items
    counted by their value of score A (down) and score B (across); the items off the diagonal are named."""
    from evaluation_harness._runs import item_rows  # noqa: PLC0415

    names = [m.strip() for m in args.crosstab.split(",") if m.strip()]
    if len(names) != 2:
        die(
            "--crosstab A,B: two per-item scores, comma-separated (e.g. model_false_dismiss,false_dismiss)",
            "bad-argument",
        )
    ma, mb = names
    rx = None
    if args.group_match:
        try:
            rx = re.compile(args.group_match)
        except re.error as exc:
            die(f"--group-match {args.group_match!r}: {exc}", "bad-argument")
    arms = _arm_ids(A, [t.strip() for t in args.runs.split(",") if t.strip()], args.label)
    out = []
    for arm in arms:
        ds, d = _run_of(A, arm)
        rows = list(item_rows(d, strict=False))
        if not rows:
            die(f"{arm}: no predictions.jsonl rows to cross", "not-enough")
        for m in (ma, mb, *([args.group.split(".")[0]] if args.group else [])):
            if not any(m in r for r in rows):
                have = sorted({k for r in rows for k in r if k != "item_id"})
                die(f"{arm}: no per-item {m!r} on record (recorded: {', '.join(have)})", "not-enough")
        # Two per-item SCORES: numbers, true/false or nothing. A `_`-field or one holding text or a record (`_meta`
        # holds the arm's output) would label rows with that content and name each item: the outputs, readable,
        # on a public server too. Such a field is a --group (refused publicly), never a score.
        scores = sorted({k for r in rows for k, v in r.items() if not k.startswith("_") and _is_score(v)})
        for m in (ma, mb):
            if m.startswith("_") or not all(_is_score(r.get(m)) for r in rows):
                die(
                    f"--crosstab {m}: not a per-item score (numbers or true/false); "
                    f"a recorded field belongs in --group. Scores on record: {', '.join(scores)}",
                    "bad-argument",
                )
        keep = None
        if args.where:
            decl, values = cs._fields_of(ds)
            kept, err = cs._filter({"_": {r["item_id"]: 1 for r in rows}}, decl, values, args.where)
            if err:
                die(err, "bad-argument")
            keep = set(kept["_"])
        groups: dict[str, list] = {}
        for r in rows:
            if keep is not None and r["item_id"] not in keep:
                continue
            g = "all"
            if args.group:
                raw = _path(r, args.group)
                text = None if raw is None else _label(raw)
                if rx is not None and text is not None:
                    m = rx.search(text)
                    text = None if not m else (m.group(1) if rx.groups else m.group(0))
                g = _label(text)
            groups.setdefault(g, []).append((r["item_id"], _label(r.get(ma)), _label(r.get(mb))))
        out.append((arm, groups))
    cells_json = []
    for arm, groups in out:
        for g in _order(groups):
            items = groups[g]
            ra, cb_ = _order(a for _, a, _b in items), _order(b for _, _a, b in items)
            n: dict[tuple[str, str], list[str]] = {(a, b): [] for a in ra for b in cb_}
            for i, a, b in items:
                n[(a, b)].append(i)
            head = (f"{A.describe(arm)['label']}: " if len(arms) > 1 else "") + (
                f"{args.group} = {g}" if args.group else "all items"
            )
            print(f"\n{head} · {len(items)} {A.item_word}(s)")
            _table(
                [f"{ma} \\ {mb}", *cb_, "total"],
                [[a, *[len(n[(a, b)]) for b in cb_], sum(len(n[(a, b)]) for b in cb_)] for a in ra]
                + [["total", *[sum(len(n[(a, b)]) for a in ra) for b in cb_], len(items)]],
            )
            off = [(a, b) for a in ra for b in cb_ if a != b and n[(a, b)]]
            for a, b in off:
                ids = n[(a, b)]
                more = len(ids) - args.max_ids
                shown = ids if args.max_ids < 0 else ids[: args.max_ids]
                print(
                    f"  {ma}={a}, {mb}={b}: {len(ids)}  "
                    + ", ".join(shown)
                    + (f" … and {more} more" if more > 0 else "")
                )
            cells_json.append(
                {
                    "arm": arm,
                    "group": g if args.group else None,
                    "items": len(items),
                    "rows": ra,
                    "columns": cb_,
                    "counts": [[len(n[(a, b)]) for b in cb_] for a in ra],
                    "cells": [
                        {"a": a, "b": b, "n": len(n[(a, b)]), "diagonal": a == b, "item_ids": n[(a, b)]}
                        for a in ra
                        for b in cb_
                        if n[(a, b)]
                    ],
                }
            )
    _jsonout.values(
        {
            "crosstab": {
                "a": ma,
                "b": mb,
                "group": args.group,
                "group_match": args.group_match,
                "groups": cells_json,
            }
        }
    )


def _items_out(A, args) -> None:
    """evh inspect --runs A,B --items-out [--disagree] [--where F:V]: each item's output of every run, its scores, the
    recorded facts, beside the reference and the labels (the sheet's model, read as records, the texts whole)."""

    tokens = [t.strip() for t in args.runs.split(",") if t.strip()]
    if args.disagree and len(tokens) < 2:
        die(
            "--disagree needs two runs or more in --runs (the first is the one the others are compared to)",
            "bad-argument",
        )
    arms = _arm_ids(A, tokens, args.label)
    if args.baseline:
        base = _arm_ids(A, [args.baseline], args.label)[0]
        if base not in arms:
            die(f"--baseline {args.baseline}: not among --runs", "bad-argument")
        tokens.insert(0, tokens.pop(arms.index(base)))
    dss = {A.describe(a).get("dataset", "") for a in arms}
    if len(dss) != 1:
        die(
            f"--items-out: the runs are on {len(dss)} datasets ({', '.join(sorted(dss))}); one dataset at a time",
            "bad-argument",
        )
    ds = dss.pop()
    model = _sheet.build(ds, tokens, cs._fields_of, metric=args.metric, label=args.label)
    found = _sheet.by_where(model, args.where)
    shown = _sheet.by_signals(found, ["disagree"] if args.disagree else [])
    # Only the shown items' rows: one query per item in the sqlite store, each run's rows indexed once in files.
    tok_of = {d: a["token"] for a, (d, _m) in zip(model["arms"], model["_runs"], strict=True)}
    meta: dict[str, dict[str, object]] = {a["token"]: {} for a in model["arms"]}
    for r in shown:
        for d, row in _outputs.item_across(list(tok_of), r["item"]).items():
            meta[tok_of[d]][r["item"]] = row.get("_meta")
    records = []
    for r in shown:
        records.append(
            {
                "item_id": r["item"],
                "item": r["text"],
                "fields": r["fields"],
                "signals": r["signals"],
                "arms": {
                    a["token"]: {
                        "run": a["run"],
                        "decision": r["shown"].get(a["token"]),
                        "output": r["decisions"].get(a["token"]),
                        "scores": r["scores"].get(a["token"], {}),
                        "meta": meta[a["token"]].get(r["item"]),
                    }
                    for a in model["arms"]
                },
                "references": r["references"],
                "labels": r["label_text"],
            }
        )
    _jsonout.values(
        {"items_out": {"dataset_id": ds, "runs": [a["run"] for a in model["arms"]], "items": records}}
    )
    from evaluation_harness import _exposure  # noqa: PLC0415

    _exposure.read_by_harness(ds, [r["item_id"] for r in records], "inspect --items-out")
    print(f"{ds}: {len(shown)} of {len(found)} {A.item_word}(s)" + (" (disagree)" if args.disagree else ""))
    cut = args.max_chars
    for rec in records:
        print(f"\n== {rec['item_id']}" + (f"  {rec['item']}" if rec["item"] else ""))
        for k, v in rec["references"].items():
            print(f"  reference {k}: {_clip(v, cut)}")
        for k, v in rec["labels"].items():
            print(f"  label {k}: {v}")
        for t, x in rec["arms"].items():
            sc = " ".join(f"{k}={_label(v)}" for k, v in x["scores"].items())
            print(
                f"  [{t}] {_clip(x['decision'], 80) if x['decision'] is not None else '(none)'}  {sc}".rstrip()
            )
            if x["meta"]:
                print(f"    meta: {_clip(json.dumps(x['meta'], ensure_ascii=False), cut)}")
            if x["output"] is not None:
                print(f"    output: {_clip(_readable(x['output']), cut)}")


def _readable(output: str) -> str:
    """An output that is a JSON object, as the terminal reads it: without the `_`-keys (a trace of the run's probes),
    which --json keeps; any other output as it is."""
    try:
        got = json.loads(output)
    except ValueError:
        return output
    if not isinstance(got, dict):
        return output
    kept = {k: v for k, v in got.items() if not k.startswith("_")}
    left = len(got) - len(kept)
    return json.dumps(kept, ensure_ascii=False) + (f" (+ {left} `_` key(s): --json)" if left else "")


def _clip(text, n: int) -> str:
    """One line of a text, cut at n characters with how long it was (n 0: whole)."""
    one = " ".join(str(text or "").split())
    return one if not n or len(one) <= n else one[: n - 1] + f"… ({len(one)} chars)"


def _quantiles(vals: list) -> str:
    v = sorted(vals)
    q = statistics.quantiles(v, n=4, method="inclusive") if len(v) > 1 else [v[0]] * 3
    return f"min {_fmt(v[0])}  p25 {_fmt(q[0])}  median {_fmt(q[1])}  p75 {_fmt(q[2])}  max {_fmt(v[-1])}"


def _analysis(d: dict, label: dict, xmetric: str | None) -> None:
    """The inspector's analysis charts as numbers: each arm's spread over the items, each arm's
    per-item difference from the baseline, and (with --x) each arm's mean on a second metric."""
    print(f"\nspread per run ({d['metric']}, one line per arm):")
    _table(
        ["arm", "mean", "spread over the items"],
        [
            [label.get(a, a), _fmt(statistics.fmean(s.values())), _quantiles(list(s.values()))]
            for a, s in d["series"].items()
            if s
        ],
    )
    base = d["series"].get(d["baseline"], {})
    rows = []
    for a, s in d["series"].items():
        if a == d["baseline"]:
            continue
        diffs = [s[i] - base[i] for i in s if i in base]
        if diffs:
            rows.append([label.get(a, a), _fmt(statistics.fmean(diffs)), _quantiles(diffs)])
    if rows:
        print(f"\ndifference from the baseline ({label.get(d['baseline'], d['baseline'])}), per item:")
        _table(["arm", "mean Δ", "spread of Δ over the items"], rows)
    shape = d.get("shape") or {}
    xm = xmetric or next(iter(shape), None)
    if xmetric and xmetric not in shape:
        print(
            f"\n(--x {xmetric}: not recorded per item on these arms; recorded: {', '.join(shape) or 'none'})"
        )
    elif xm:
        # The scatter's crosses: each arm's mean over the items that have both numbers.
        rows = []
        for a, ys in d["series"].items():
            pts = [(shape[xm].get(a, {})[i], y) for i, y in ys.items() if i in shape[xm].get(a, {})]
            if pts:
                rows.append(
                    [
                        label.get(a, a),
                        _fmt(statistics.fmean(y for _, y in pts)),
                        _fmt(statistics.fmean(x for x, _ in pts)),
                        len(pts),
                    ]
                )
        if rows:
            print(f"\n{d['metric']} against {xm}, each arm's mean (the scatter's crosses):")
            _table(["arm", d["metric"], xm, "items"], rows)


def activity(argv) -> int:
    """evh activity: the activity page in the terminal."""
    ap = argparse.ArgumentParser(
        prog="evh activity",
        description="Runs, spend and tokens in a period, by dataset, by arm and by kind, against the period before.",
    )
    ap.add_argument(
        "--period",
        default=cp.DEFAULT,
        choices=[k for k, *_ in cp.PERIODS],
        help=f"counted from today; default {cp.DEFAULT}",
    )
    ap.add_argument(
        "--arms",
        type=int,
        default=20,
        help="how many arms to list, what moved most against the period before first (default 20)",
    )
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    rows = cb.period_activity(A, by_ds)
    per, line = _period(A, by_ds, rows, args.period)
    print(line)
    flows = ("runs", "usd", "tokens")

    def busy(prefix: str) -> list:
        # What moved most against the period before first, up or down (as the page sorts), then the
        # busiest; for all time, with no period before, the busiest.
        ks = [k for k in per if k.startswith(prefix)]

        def moved(k: str) -> int:
            prev = per[k]["runs_prev"]
            return 0 if prev is None else abs(per[k]["runs"] - prev)

        return sorted(ks, key=lambda k: (-moved(k), -per[k]["runs"], -per[k]["usd"], k))

    print("\nby dataset:")
    _table(
        ["dataset", "", *(PERIOD_HEADS[f] for f in flows)],
        [[k[2:], *_pcells(per[k], flows)] for k in busy("d:")],
    )
    active = [k for k in busy("a:") if per[k]["runs"] or per[k]["usd"] or per[k]["tokens"]]
    print(
        f"\nby arm ({len(active)} active in the period; the {min(args.arms, len(active))} that moved most):"
    )
    if active:
        _table(
            ["arm", "", *(PERIOD_HEADS[f] for f in flows)],
            [[k[2:], *_pcells(per[k], flows)] for k in active[: args.arms]],
        )
    else:
        print("  none")
    print("\nby kind:")
    names = dict(cb.SPEND_KINDS)
    _table(
        ["what was billed", "", *(PERIOD_HEADS[f] for f in ("usd", "tokens"))],
        [
            [names[k[2:]], *_pcells(per[k], ("usd", "tokens"))]
            for k in sorted(k for k in per if k.startswith("k:"))
        ],
    )
    return 0


def search(argv) -> int:
    """evh search: the catalog's search box, with the command that shows each hit."""
    ap = argparse.ArgumentParser(
        prog="evh search", description="Search datasets, arms, reference sets, metrics and goals."
    )
    ap.add_argument("text", nargs="+")
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    words = " ".join(args.text).lower().split()

    def score(x: dict) -> int:
        # The page's ranking: a word in the title counts more than one in the description.
        t = x["t"].lower()
        return sum(
            4 if t.startswith(w) else 3 if w in t else 1 if w in x["d"].lower() else 0 for w in words
        ) + (x["k"] == "goal")

    hits = sorted(
        (x for x in cb.search_index(A, by_ds) if all(w in x["s"] for w in words)), key=score, reverse=True
    )[:40]
    if not hits:
        print("No match.")
        return 1
    cmd = {
        "dataset": lambda x: f"evh datasets --dataset-id {x['t']}",
        "arm": lambda x: f"evh inspect --runs {x.get('id', x['t'])}",
        "reference": lambda x: f"evh references --reference-id {x['t']}",
        "metric": lambda x: "evh metrics",
        "goal": lambda x: f"evh goals --goal {x.get('id', x['t'])}",
    }
    _table(["kind", "name", "about", "see it with"], [[x["k"], x["t"], x["d"], cmd[x["k"]](x)] for x in hits])
    return 0


VIEWS = {
    "overview": overview,
    "arms": arms,
    "models": models,
    "datasets": datasets,
    "references": references,
    "metrics": metrics,
    "goals": goals,
    "inspect": inspect,
    "search": search,
    "activity": activity,
}


def run(view: str) -> int:
    """Entry point for the per-view scripts (`evh <view>` runs one each). `--json`: the same output
    as one JSON object (`_jsonout`: its tables as data, its other lines as text)."""
    argv, as_json = _jsonout.take_flag(sys.argv[1:])
    if any(a in ("-h", "--help") for a in argv):  # --json is taken before the view's parser sees it
        try:
            return VIEWS[view](argv)
        finally:
            print(
                '\n  --json                the same answer as one JSON object: {"command", "version", "result": '
                '{"blocks": [...]}}, each table as columns and rows (0.8.0 replaces blocks)'
            )
    if not as_json:
        return VIEWS[view](argv)
    with _jsonout.collect(view):
        rc = VIEWS[view](argv)
    return rc
