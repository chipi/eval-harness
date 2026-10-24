"""The catalog and the inspector, in the terminal: every page and comparison as a command.

    evh datasets   [--dataset-id ID]                 every dataset, or one: arms, references, versions
    evh references [--reference-id ID]               every reference, or one: who wrote it, what is scored against it
    evh metrics    [--dataset-id ID]                 what each metric measures, which way is better, where it is recorded
    evh goals      [--goal ID]                       every goal, or one: its answer on each of its datasets
    evh inspect    --runs A,B,... [--baseline A]     the inspector's comparison: verdicts, conditions, a breakdown
                   [--metric M] [--where F:V] [--by F] [--item ITEM]

They read the project through the same adapter as the pages (`--adapter`, else config.yaml's
catalog.adapter, else the harness's layout) and compute with the same functions as the pages and
the inspector server, so a number here is the number there. The pages are a comfort; everything
they show is here.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import textwrap

import catalog_build as cb
import catalog_serve as cs
from _common import die
from catalog_adapter import load_catalog_adapter

KINDS = {"t-silver": "silver", "t-judged": "judged", "t-author": "wrote its reference"}


def _table(heads: list, rows: list) -> None:
    cells = [[str(c) for c in r] for r in rows]
    w = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(heads)]
    print("  " + "  ".join(h.ljust(w[i]) for i, h in enumerate(heads)).rstrip())
    print("  " + "  ".join("-" * x for x in w))
    for r in cells:
        print("  " + "  ".join(c.ljust(w[i]) for i, c in enumerate(r)).rstrip())


def _fmt(v) -> str:
    return "—" if v is None else cb.fmt(v)


def _scored(a: dict) -> str:
    return f"judge {a['judge']}" if a.get("judge") else (a.get("reference") or "—")


def _kind(a: dict, tiers: dict) -> str:
    return KINDS.get(cb.row_kind(a, tiers), "")


def _adapter(args):
    A = load_catalog_adapter(getattr(args, "adapter", None))
    return A, cb.collect(A)


def datasets(argv) -> int:
    """evh datasets: every dataset, or one with its versions, references and arms."""
    ap = argparse.ArgumentParser(prog="evh datasets", description="Every dataset, or one in full.")
    ap.add_argument("--dataset-id", help="one dataset: its versions, references and arms")
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    if not args.dataset_id:
        rows = [
            [
                ds,
                v["items"],
                len(v["arms"]),
                ", ".join(r["id"] for r in v["refs"]) or "—",
                (v.get("parent") or {}).get("dataset_id", ""),
            ]
            for ds, v in sorted(by_ds.items())
        ]
        _table(["dataset", f"{A.item_word}s", "arms", "references", "made from"], rows)
        return 0
    v = by_ds.get(args.dataset_id)
    if v is None:
        die(f"no dataset {args.dataset_id!r} in the catalog: one of {', '.join(sorted(by_ds))}")
    print(f"{args.dataset_id}: {v['items']} {A.item_word}s, {len(v['arms'])} arms\n")
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
    for b in v.get("baselines", [])[-1:]:
        print(f"\nbaseline: {b.get('arm') or b['run']} (promoted {(b['promoted_at'] or '')[:10]})")
        print(textwrap.fill(b["reason"], width=92, initial_indent="  ", subsequent_indent="  "))
    tiers = {r["id"]: r["tier"] for r in v["refs"]}
    arms = sorted(v["arms"], key=lambda a: (a["metric"], -(a["mean"] or 0) * (-1 if a["lower"] else 1)))
    print()
    if not arms:
        print("no arm has run on it yet")
        return 0
    _table(
        ["arm", "metric", "mean", f"{A.item_word}s", "runs", "scored against", "row", "arm id (for inspect)"],
        [
            [
                a["label"],
                a["metric"] or "—",
                _fmt(a["mean"]),
                a["n"],
                a["runs"],
                _scored(a),
                _kind(a, tiers),
                a["arm"],
            ]
            for a in arms
        ],
    )
    return 0


def references(argv) -> int:
    """evh references: every reference, or one with its provenance and what is scored against it."""
    ap = argparse.ArgumentParser(prog="evh references", description="Every reference, or one in full.")
    ap.add_argument(
        "--reference-id", help="one reference: who wrote it, from which run, what is scored against it"
    )
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    refs = [(ds, r) for ds, v in by_ds.items() for r in v["refs"]]
    if not args.reference_id:
        _table(
            ["reference", "tier", "dataset", f"{A.item_word}s", "written by"],
            [
                [r["id"], r["tier"], ds, r.get("items", "—"), r.get("author") or "—"]
                for ds, r in sorted(refs, key=lambda x: x[1]["id"])
            ],
        )
        return 0
    hit = next(((ds, r) for ds, r in refs if r["id"] == args.reference_id), None)
    if hit is None:
        die(f"no reference {args.reference_id!r}: one of {', '.join(sorted(r['id'] for _, r in refs))}")
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
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    fn = getattr(A, "metric_descriptions", None)
    project = fn() if callable(fn) else {}
    idx = cb.metric_index(A, by_ds)
    for m in sorted(idx, key=lambda k: (k.startswith(("total_", "self_family_", "resumed")), k)):
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
    return 0


def goals(argv) -> int:
    """evh goals: every goal, or one with its arms on each of its datasets."""
    ap = argparse.ArgumentParser(
        prog="evh goals", description="Every goal, or one with its answer per dataset."
    )
    ap.add_argument("--goal", help="one goal: what it is for, and its arms on each dataset")
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A, by_ds = _adapter(args)
    gs = A.goals()
    if not args.goal:
        _table(
            ["goal", "decides", "datasets", "title"],
            [
                [
                    g["goal_id"],
                    ((g.get("success_criteria") or {}).get("primary") or {}).get("measure", ""),
                    ", ".join(d.get("dataset_id", "") for d in g.get("datasets") or []),
                    g.get("title", ""),
                ]
                for g in gs
            ],
        )
        return 0
    g = next((x for x in gs if x["goal_id"] == args.goal), None)
    if g is None:
        die(f"no goal {args.goal!r}: one of {', '.join(x['goal_id'] for x in gs) or '(none)'}")
    prim = (g.get("success_criteria") or {}).get("primary") or {}
    print(f"{g.get('title') or g['goal_id']}\n")
    print(textwrap.fill(g.get("statement", ""), width=96))
    print(
        f"\n  decision   {g.get('decision', '')}\n  decides    {prim.get('measure', '')}, {prim.get('direction', '')} is better"
    )
    print("\nthe answer so far:")
    for d in g.get("datasets") or []:
        ds = d.get("dataset_id", "")
        bl = [
            b
            for b in (by_ds.get(ds) or {}).get("baselines", [])
            if not b.get("goal") or b.get("goal") == g["goal_id"]
        ]
        if bl:
            b = bl[-1]
            print(f"  {ds}: baseline {b.get('arm') or b['run']} (promoted {(b['promoted_at'] or '')[:10]})")
            print(textwrap.fill(b["reason"], width=92, initial_indent="    ", subsequent_indent="    "))
        else:
            print(f'  {ds}: no decision yet (evh run-promote --run <run_id> --reason "...")')
    for ans in cb.goal_answers(g, by_ds):
        ds = ans["dataset"]
        tiers = {r["id"]: r["tier"] for r in (by_ds.get(ds) or {}).get("refs", [])}
        print(f"\n{ds}" + (f" · {ans['role']}" if ans["role"] else ""))
        if not ans["groups"]:
            print(f"  no arm records {prim.get('measure', '')}")
        for grp in ans["groups"]:
            what = grp["key"]
            print(f"\n  {'scored by ' + what if what.startswith('judge ') else 'scored against ' + what}")
            _table(
                ["arm", f"mean {prim.get('measure', '')}", f"{A.item_word}s", "row", "flags", ""],
                [
                    [
                        r["label"] + (" [baseline]" if r.get("baseline") else ""),
                        _fmt(r["mean"]),
                        r["n"],
                        _kind(r, tiers),
                        "; ".join(r["flags"]) or "—",
                        "leader" if grp["leader"] and r is grp["leader"] else "",
                    ]
                    for r in grp["rows"]
                ],
            )
    return 0


def _arm_ids(A, tokens: list, from_dir: str) -> list:
    """Arm ids from what the user typed: a full arm id, or a config id looked up under `from_dir`."""
    known = A.arms()
    out = []
    for t in tokens:
        if t in known:
            out.append(t)
            continue
        hits = [a for a in known if a.rsplit("/", 1)[-1] == t and a.split("/", 1)[0] == from_dir]
        if len(hits) != 1:
            near = [a for a in known if a.rsplit("/", 1)[-1] == t]
            die(
                f"{t!r}: "
                + (
                    f"{len(hits)} arms under {from_dir}/ match; name the arm id: {', '.join(near)}"
                    if near
                    else "no arm with that id; `evh datasets --dataset-id <id>` lists them"
                )
            )
        out.append(hits[0])
    return out


def inspect(argv) -> int:
    """evh inspect: the inspector's comparison, conditions, breakdown or one item, in the terminal."""
    ap = argparse.ArgumentParser(
        prog="evh inspect", description="The inspector's comparison, in the terminal."
    )
    pick = ap.add_mutually_exclusive_group(required=True)
    pick.add_argument("--runs", help="arms: config ids (looked up under --from) or arm ids, comma-separated")
    pick.add_argument("--round", help="the arms in play in this round of a goal (rN; ADR-0004)")
    ap.add_argument("--goal", help="the goal --round belongs to, when several goals have one")
    ap.add_argument("--baseline", help="the arm the others are tested against (default: the first)")
    ap.add_argument("--metric", help="default: the arms' primary metric")
    ap.add_argument(
        "--from",
        dest="from_dir",
        default="runs",
        help="where config ids are looked up: runs, runs-silver, runs-judged/<scorer> (default: runs)",
    )
    ap.add_argument(
        "--where",
        action="append",
        default=[],
        help="FIELD:VALUE or FIELD:LO..HI, keep only matching items (repeatable)",
    )
    ap.add_argument("--by", help="break the comparison down by a choice or yes/no field")
    ap.add_argument("--item", help="show one item: each arm's output beside the reference")
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: the catalog's)")
    args = ap.parse_args(argv)
    A = load_catalog_adapter(args.adapter)
    cs.set_adapter(A)
    if args.round:
        from _rounds import arms_of, resolve  # noqa: PLC0415

        tokens = arms_of(resolve(args.round, args.goal))
        if not tokens:
            die(f"round {args.round} has no arms in play yet")
    else:
        tokens = [t.strip() for t in args.runs.split(",") if t.strip()]
    arms = _arm_ids(A, tokens, args.from_dir)
    base = _arm_ids(A, [args.baseline], args.from_dir)[0] if args.baseline else arms[0]
    label = {a: A.describe(a)["label"] for a in arms}
    if args.item:
        ref = A.describe(base).get("reference", "")
        got = cs.item({"arms": [",".join(arms)], "item": [args.item], "ref": [ref] if ref else [""]})
        if got.get("error"):
            die(got["error"])
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
            print(
                f"\n== {label[a]}{'  (baseline)' if a == base else ''}\n{view.get('text') or view.get('note', '(none)')}"
            )
        return 0
    params = {
        "runs": [",".join(arms)],
        "baseline": [base],
        "metric": [args.metric or ""],
        "where": args.where,
        "by": [args.by or ""],
    }
    d = cs.compare(params)
    if d.get("error"):
        die(d["error"])
    for w in d.get("warnings") or []:
        print(f"NOTE: {w}")
    if d.get("state") == "not scorable":
        return 1
    label = {a["id"]: a["label"] for a in d.get("arms") or []} | label
    vals = list((d.get("series") or {}).get(d["baseline"], {}).values())
    better = "higher" if d.get("higher_is_better") else "lower"
    print(
        f"{d['metric']} ({better} is better) · baseline {label.get(d['baseline'], d['baseline'])}: mean {_fmt(statistics.fmean(vals) if vals else None)} · Holm across {d['family_size']}\n"
    )
    _table(
        ["run vs baseline", "verdict", "n", "mean", "Δ", "wins–losses", "p", "Holm threshold"],
        [
            [
                label.get(r["arm"], r["arm"]),
                r["verdict"],
                r["n"],
                _fmt(r["mean"]),
                _fmt(r["delta"]),
                f"{r['wins']}–{r['losses']}" + (f" ({r['ties']} tied)" if r.get("ties") else ""),
                "—" if r.get("p") is None else f"{r['p']:.4g}",
                "—" if not r.get("threshold") else f"{r['threshold']:.4f}",
            ]
            for r in sorted(d["rows"], key=lambda r: r.get("p") if r.get("p") is not None else 9)
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
                [[f["name"], *[str(f["values"].get(a, "—"))[:16] for a in order]] for f in c["differ"]],
            )
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
                    "—" if r.get("p") is None else f"{r['p']:.4g}",
                ]
                for g in br["groups"]
                for r in g["rows"]
            ],
        )
    return 0


VIEWS = {
    "datasets": datasets,
    "references": references,
    "metrics": metrics,
    "goals": goals,
    "inspect": inspect,
}


def run(view: str) -> int:
    """Entry point for the per-view scripts (`evh <view>` runs one each)."""
    return VIEWS[view](sys.argv[1:])
