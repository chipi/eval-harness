#!/usr/bin/env python3
"""One arm against a declared family of opponents, Holm step-down over the whole family.

    python scripts/family_test.py --dataset-id cnn_dailymail_200 \
        --a cnn_bart_l_n200_v1 --against _n200_v1 --metric coverage

WHY THIS AND NOT k(k-1)/2
  `leaderboard.py --significance` asks "which of all 325 pairs differ?" and pays Nemenyi's
  multiplicity price for every one of them. That is the right price for that question. But
  "how does the local model compare to the hosted field?" is 25 comparisons, not 325, and
  correcting for 300 nobody made throws away the power to answer the one that was asked.

  `pair_test.py` handles ONE pre-registered pair and applies Bonferroni (alpha/m) because a
  single pair cannot do better: Holm's step-down needs every p-value in the family at once.
  This script has them all, so it runs the real thing.

HOLM, AND WHY IT IS STRICTLY BETTER THAN BONFERRONI HERE
  Sort the family's p-values ascending. Compare the smallest to alpha/m, the next to
  alpha/(m-1), ... the largest to alpha/1. Stop at the first failure; everything from there
  down is not significant. Every step after the first is LOOSER than Bonferroni's alpha/m, so
  Holm rejects at least everything Bonferroni does and sometimes more, with the same
  family-wise error guarantee. Nothing is traded away for it.

THE HONESTY CONDITION
  The family is declared by `--against`, before the p-values are read, and printed in the
  output. A family assembled after seeing which opponents looked beatable is a search
  wearing a test's clothes, and no correction repairs that.

  `--items` restricts every comparison to the same stratum -- see pair_test.py for why the
  BART truncation split needs it.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import contextlib
import hashlib
import io
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

from evaluation_harness import (  # noqa: E402
    _jsonout,
    _outputs,
    _store,
)
from evaluation_harness._common import (  # noqa: E402
    GOALS,
    ROOT,
    ROUNDS,
    RUNS,
    dataset_item_ids,
    die,
    evh_prog,
    item_clusters,
    item_selection,
)
from evaluation_harness._fingerprint import measuring_modules  # noqa: E402
from evaluation_harness._runs import (  # noqa: E402 -- one implementation of "score per item"
    default_metric,
    direction,
    per_item,
    refuse_run_level,
    runs_on,
    warn_on_ambiguous_runs,
)
from evaluation_harness.model import runs as model_runs  # noqa: E402
from evaluation_harness.stats import (  # noqa: E402 -- one implementation of the paired test
    EXACT_UP_TO,
    LARGE_SAMPLE,
    clustered,
    fmt_p,
    holm,
    p_method,
    sign_flip_family,
)


def _opponents(runs: list, against: str, exclude: str) -> list[str]:
    """The family: a comma-separated list names its system ids exactly; one value is a substring of
    every opponent's system id (`--against ag_` for every ag_ arm)."""
    names = [x.strip() for x in against.split(",") if x.strip()]
    if len(names) > 1:
        return sorted(
            {m["config_id"] for _d, m in runs if m["config_id"] != exclude and m["config_id"] in names}
        )
    return sorted(
        {m["config_id"] for _d, m in runs if m["config_id"] != exclude and against in m["config_id"]}
    )


# Under the PROJECT, not beside the code: installed, the code sits in site-packages.
CACHE = ROOT / ".cache" / "family_test"


def _cache_key(argv: list[str], args) -> str:
    """Everything the answer depends on: this script and every module it imports (read from
    the source, as the run code hash is: a hand-kept list missed an import added later), the exact
    arguments, the bytes of every score read of this dataset (its run.json, score.json, metrics.json + predictions.jsonl),
    the project's goals (a goal sets a metric's direction, so it moves the wins and "ahead"
    counts), and any --items / --exclude-dataset input. Change any of them and the key
    changes, so a hit is the same computation, already done -- the test is seeded and
    deterministic."""
    h = hashlib.sha256()
    for f in measuring_modules(Path(__file__).resolve().parent, ("family_test.py",)):
        h.update(f.name.encode() + b"\0" + _store.read_bytes(f))
    h.update("\0".join(argv).encode())
    for d, _m in runs_on(args.dataset_id, label=args.label):
        run = model_runs.run_of(d)
        for f in (run / model_runs.RUN, d / model_runs.SCORE, d / model_runs.METRICS):
            h.update(f"{run.name}/{d.name}/{f.name}".encode() + b"\0" + _store.read_bytes(f))
        h.update((_outputs.rows_text(d) or "").encode("utf-8"))
    for g in sorted(_store.glob(GOALS, "*.yaml")) if _store.is_dir(GOALS) else []:
        h.update(g.name.encode() + b"\0" + _store.read_bytes(g))
    # A round's record decides which arms --round keeps (its retirements, its carried arms).
    for r in sorted(_store.glob(ROUNDS, "*/*.yaml")) if _store.is_dir(ROUNDS) else []:
        h.update(r.as_posix().encode() + b"\0" + _store.read_bytes(r))
    if args.round:  # a re-score stands in for its run in the round's reading, and picks its leader
        for d, _m in model_runs.scored(args.dataset_id, label_is=None):
            if model_runs.label(d, _m).startswith("rescored"):
                key = f"{model_runs.run_of(d).name}/{d.name}"
                h.update(key.encode() + b"\0" + _store.read_bytes(d / model_runs.METRICS))
    if args.items:
        h.update(_store.read_bytes(args.items))
    if args.exclude_dataset:
        h.update("\0".join(sorted(dataset_item_ids(args.exclude_dataset))).encode())
    return h.hexdigest()


def main() -> int:
    """Run the family test, or replay its output when the exact same test has already run.

    Each run is ~20,000 seeded permutations per opponent in pure Python (~18 s for a family
    of 29), and the report checker, the self-test and the site build ask the same questions
    dozens of times per `make ci`. EVAL_NO_CACHE=1 forces a recomputation."""
    ap = _parser()
    args = ap.parse_args()
    if not args.round and not (args.a and args.against):
        ap.error("--a and --against are required (or --round, which defaults them)")
    use_cache = not os.environ.get("EVAL_NO_CACHE") and _store.is_dir(RUNS)
    if use_cache:
        hit = CACHE / f"{_cache_key(sys.argv[1:], args)}.json"
        if _store.is_file(hit):
            c = json.loads(_store.read_text(hit, encoding="utf-8"))
            sys.stdout.write(c["stdout"])
            sys.stderr.write(c["stderr"])
            return c["rc"]
    out, err = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
        _jsonout.collect("family-test", args.json),
    ):
        rc = _run(args)
    sys.stdout.write(out.getvalue())
    sys.stderr.write(err.getvalue())
    if use_cache:
        # Best effort: the answer is in hand, and a read-only project (a server's copy) only loses the speed-up.
        try:
            _store.mkdir(CACHE, parents=True, exist_ok=True)
            tmp = hit.with_suffix(".tmp")
            _store.write_text(
                tmp,
                json.dumps({"stdout": out.getvalue(), "stderr": err.getvalue(), "rc": rc}),
                encoding="utf-8",
            )
            tmp.replace(hit)  # atomic: a concurrent reader never sees half a file
        except OSError:
            pass
    return rc


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--a", help="config_id of the arm under test (with --round: default its leader)")
    ap.add_argument(
        "--against",
        help="the opponent family, declared in advance: a substring of their system ids, or a comma-separated "
        "list of system ids (with --round: default every other arm in play in it)",
    )
    ap.add_argument("--metric", help="default: the primary metric the runs recorded")
    ap.add_argument(
        "--label",
        default="",
        help='the arm label the runs are read under (default: "", the plain runs; `evh runs-list` shows the '
        "labels present)",
    )
    ap.add_argument("--exclude-dataset", help="drop items this dataset also contains")
    ap.add_argument("--items", type=Path, help="file of item_ids; restrict to exactly these")
    ap.add_argument(
        "--reduce",
        default=None,
        help="how an arm's repeats make one score per item: mean (the default), majority or at_least_K, for 0/1 "
        "scores (with --round: default the goal's primary.reduce)",
    )
    ap.add_argument(
        "--cluster",
        metavar="FIELD",
        help="an item field whose items are not independent: flip one sign per value of it, so related items "
        "count once (with --round: default the goal's `cluster:`)",
    )
    ap.add_argument("--permutations", type=int, default=20000)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument(
        "--asc",
        action="store_true",
        help="lower is better: wins and 'ahead' count the lower score "
        "(default: inferred from the metric and the runs)",
    )
    ap.add_argument("--desc", action="store_true", help="higher is better, whatever the runs declare")
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument("--round", help="only opponents in play in this round of a goal (rN; ADR-0004)")
    ap.add_argument("--goal", help="the goal --round belongs to, when several goals have one")
    ap.add_argument(
        "--json",
        action="store_true",
        help="the same answer as one JSON object: the printed lines as blocks, the opponents table as "
        "data, and the result by name under result.values",
    )
    return ap


def _round_defaults(args, runs: list) -> Any:
    """--round: the round's goal measure, its leader as A and every other arm in play as the family, each as the
    round reads the arm (a re-score stands in for its run, as pair-test --round reads it). Returns values(config_id,
    metric) -> {item_id: value}. The family is the round's own list of arms, fixed before any p-value is computed."""
    from evaluation_harness import _common  # noqa: PLC0415
    from evaluation_harness._rounds import arms_of, resolve  # noqa: PLC0415
    from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415
    from evaluation_harness.pair_test import _round_values  # noqa: PLC0415

    rnd = resolve(args.round, args.goal)
    if rnd["dataset_id"] != args.dataset_id:
        die(f"round {args.round} is on {rnd['dataset_id']}, not {args.dataset_id}", "mismatch")
    in_play = arms_of(rnd)
    goal = _common.load_goals().get(rnd["goal"]) or {}
    prim = (goal.get("success_criteria") or {}).get("primary") or {}
    args.metric = args.metric or prim.get("measure")
    args.cluster = args.cluster or _common.goal_cluster(goal, args.dataset_id)
    args.reduce = args.reduce or (prim.get("reduce") if isinstance(prim, dict) else None)
    if args.a and args.a not in in_play:
        die(f"{args.a} is not in play in round {args.round} ({', '.join(in_play)})", "not-found")
    values = _round_values(args.dataset_id, args)
    chose = not args.a
    if chose:
        leader = model_rounds.evidence(rnd["goal"], rnd).get("leader")
        if not leader:
            die(f"no arm in round {args.round} records {args.metric} yet", "not-enough")
        args.a = leader.rsplit("/", 1)[-1]
    declared = bool(args.against)
    if not declared:
        rest = [c for c in in_play if c != args.a]
        if not rest:
            die(
                f"round {args.round} has no other arm in play to test {args.a} against: name --against",
                "not-enough",
            )
        args.against = ",".join(rest)
    print(
        f"  round {args.round}: {args.a}{' (its leader)' if chose else ''} against "
        + ("the family named" if declared else f"every other arm in play ({len(args.against.split(','))})")
    )
    args.family_label = None if declared else f"the {len(args.against.split(','))} other arms in play"
    return values


def _run(args) -> int:
    # Two runs sharing a config_id are averaged together below without
    # saying so. See _runs.warn_on_ambiguous_runs.
    warn_on_ambiguous_runs(args.label, args.dataset_id)
    args.metric = args.metric or default_metric(args.dataset_id, label=args.label)
    runs = runs_on(args.dataset_id, label=args.label)
    refuse_run_level(runs, args.metric, "family-test")
    values = None
    if args.round:
        from evaluation_harness._rounds import arms_of, resolve  # noqa: PLC0415

        values = _round_defaults(args, runs)
        keep_arms = set(arms_of(resolve(args.round, args.goal))) | {args.a}
        runs = [(d, m) for d, m in runs if m["config_id"] in keep_arms]
    lower = direction(runs, args.metric, args.asc, args.desc)
    if values is not None:
        A = values(args.a, args.metric)
    else:
        A = per_item(
            [r for r in runs if r[1]["config_id"] == args.a], args.metric, reduce=args.reduce or "mean"
        )
    if not A:
        die(f"no runs for {args.a} on {args.dataset_id}", "not-found")

    drop, keep = item_selection(args.exclude_dataset, args.items)

    keys = item_clusters(args.dataset_id, args.cluster) if args.cluster else None
    rows: list[dict] = []
    for opp in _opponents(runs, args.against, args.a):
        B = (
            values(opp, args.metric)
            if values is not None
            else per_item(
                [r for r in runs if r[1]["config_id"] == opp], args.metric, reduce=args.reduce or "mean"
            )
        )
        items = sorted(set(A) & set(B) - drop)
        if keep is not None:
            items = [i for i in items if i in keep]
        if len(items) < 3:
            continue
        deltas = [A[i] - B[i] for i in items]
        # The unit the test flips: an item, or with --cluster a cluster's summed difference.
        units = clustered(dict(zip(items, deltas, strict=True)), keys)[0] if keys is not None else deltas
        if len(units) < 2:
            continue
        rows.append(
            {
                "opp": opp,
                "n": len(items),
                "units": len(units),
                "delta": statistics.fmean(deltas),
                "wins": sum(1 for d in deltas if (d < 0 if lower else d > 0)),
                "unit_values": units,
            }
        )
    if not rows:
        die("no opponents with enough shared items", "not-enough")
    # In opponent order, from the one stream. An opponent past LARGE_SAMPLE takes the normal limit; the stream still
    # moves past it when a later opponent is drawn from it, so that one's p is what it was (ADR-0028).
    # The sampled ones are summed in child processes at once, each from the stream state it starts at: the same p's.
    for r, p in zip(
        rows,
        sign_flip_family([r.pop("unit_values") for r in rows], args.permutations, args.seed),
        strict=True,
    ):
        r["p"] = p

    # HOLM STEP-DOWN. Sorted ascending, threshold alpha/(m-i), and the moment one fails
    # every larger p-value fails with it -- that carry-forward is the whole procedure, and
    # dropping it turns Holm into a per-test comparison with no family-wise guarantee.
    m = len(rows)
    rows.sort(key=lambda r: r["p"])
    verdicts = holm({r["opp"]: r["p"] for r in rows}, alpha=args.alpha)
    for r in rows:
        r["thresh"], r["sep"] = verdicts[r["opp"]]

    # Opponents can share different numbers of items with A; then no one n is the family's.
    ns = sorted({r["n"] for r in rows})
    n_items = ns[0] if len(ns) == 1 else None
    stratum = (
        f"{n_items} items" if n_items is not None else f"{ns[0]}-{ns[-1]} items (each opponent's n below)"
    )
    if args.items:
        stratum += f" (from {args.items.name})"
    elif args.exclude_dataset:
        stratum += f" (excluding {args.exclude_dataset})"
    print(
        f"  {args.a}  vs family '{getattr(args, 'family_label', None) or args.against}'   metric={args.metric}  {stratum}"
    )
    print(f"  family size m={m}, declared before the p-values were read")
    if args.cluster:
        print(
            f"  clustered by {args.cluster}: items that share a value count as one (n is items, p is per cluster)"
        )
    print(f"  Holm step-down at alpha={args.alpha}" + ("  (lower is better)" if lower else ""))
    # SAY WHICH p. Up to EXACT_UP_TO items it is exact, and every command prints the same number.
    # Above that it is a seeded estimate drawn from one random stream for the whole family, so
    # pair-test or the inspector, which draw one per pair, can differ in the third decimal.
    # Per row: opponents can share different numbers of items, so one family can hold both.
    est = [r["units"] > EXACT_UP_TO for r in rows]
    kinds = {p_method(r["units"]) for r in rows}
    if "normal limit" in kinds:
        parts = {
            "exact": f"exact up to {EXACT_UP_TO} units",
            "sampled": f"a seeded estimate below {LARGE_SAMPLE:,} ({args.permutations} permutations, one random "
            "stream for the family) -- marked ~",
            "normal limit": f"the permutation distribution's normal limit from {LARGE_SAMPLE:,} units (ADR-0028)"
            + (" -- marked *" if len(kinds) > 1 else ""),
        }
        print(
            "  p: " + "; ".join(parts[k] for k in ("exact", "sampled", "normal limit") if k in kinds) + "\n"
        )
    elif any(est) and not all(est):
        print(
            f"  p: exact up to {EXACT_UP_TO} shared items, a seeded estimate above ({args.permutations} "
            "permutations, one random stream for the family) -- marked ~\n"
        )
    elif not any(est):
        print(
            f"  p: exact, over all 2^{n_items} sign patterns\n"
            if n_items is not None
            else "  p: exact, over all sign patterns of each opponent's shared items\n"
        )
    else:
        print(
            f"  p: a seeded estimate ({args.permutations} permutations, one random stream for the family);\n"
            "     pair-test and the inspector estimate one pair at a time and can differ in the third decimal\n"
        )
    # The adjusted p of Holm's step-down: p x (m - i) for the i-th smallest, never below an earlier one.
    # It is at or under alpha exactly when the step-down rejects that opponent.
    running = 0.0
    for i, r in enumerate(rows):
        running = max(running, min(1.0, r["p"] * (m - i)))
        r["p_holm"] = running
    width = max(len(r["opp"]) for r in rows) + 2
    if not _jsonout.table(
        ["opponent", "n", "delta", "wins", "p", "p_exact", "p_holm", "threshold", "significant", "p_method"],
        [
            [
                r["opp"],
                r["n"],
                r["delta"],
                r["wins"],
                r["p"],
                r["units"] <= EXACT_UP_TO,
                r["p_holm"],
                r["thresh"],
                bool(r["sep"]),
                p_method(r["units"]),
            ]
            for r in rows
        ],
    ):
        print(f"    {'opponent':{width}} {'delta':>9} {'A wins':>9} {'p':>8} {'thresh':>8}   verdict")
        for r in rows:
            how = p_method(r["units"])
            mark = {"sampled": "~", "normal limit": "*"}.get(how, "") if len(kinds) > 1 else ""
            pv = mark + fmt_p(r["p"])
            print(
                f"    {r['opp']:{width}} {r['delta']:+9.4f} {r['wins']:>4}/{r['n']:<4} "
                f"{pv:>8} {r['thresh']:8.4f}   {'SIGNIFICANT' if r['sep'] else '--'}"
            )
    sep = sum(1 for r in rows if r["sep"])
    ahead = sum(1 for r in rows if (r["delta"] < 0 if lower else r["delta"] > 0))
    _jsonout.values(
        {
            "a": args.a,
            "against": args.against,
            "dataset_id": args.dataset_id,
            "metric": args.metric,
            "direction": "lower" if lower else "higher",
            "n": n_items,  # None when the opponents share different numbers of items
            "n_range": [ns[0], ns[-1]],
            "cluster": args.cluster or None,
            "family_size": m,
            "alpha": args.alpha,
            "correction": "holm",
            "method": next(iter(kinds)) if len(kinds) == 1 else "mixed",
            "permutations": args.permutations if "sampled" in kinds else None,
            "seed": args.seed,
            "significant": sep,
            "ahead": ahead,
        }
    )
    print(
        f"\n    significantly different from {sep} of {m} opponents; ahead on the point estimate against {ahead} of {m}"
    )
    # The gap between those two numbers is the finding most of the time: an ordering the
    # means assert and the data cannot support.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
