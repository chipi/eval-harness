#!/usr/bin/env python3
"""One pre-registered pair, tested on its own: sign-flip permutation on paired deltas.

    python scripts/pair_test.py --dataset-id cnn_dailymail_200 \
        --a cnn_deepseek_m_n200_v1 --b cnn_anthropic_m_n200_v1 --metric coverage

WHY A SECOND TEST, WHEN leaderboard.py ALREADY HAS ONE
  `_significance` answers "which of all k(k-1)/2 pairs differ?" and pays the Nemenyi
  multiplicity price for every one of them. That is the right price for that question and
  the wrong question for a decision. A comparison fixed BEFORE looking -- "is the 67x
  dearer arm better?" -- is one test, and correcting it for 275 comparisons nobody made
  is throwing away power to answer a question that was never asked.

  The honesty condition is that the pair is named in advance. Six pairs picked after
  reading the table are a search, not a test; EVAL_REPORT.md section 3.1b says so about its
  own six and Holm-corrects them. A `hypothesis:` in A's config (ADR-0025) is the record: when A's run
  carries one against B on this metric, the output says whether it was committed before the run and
  whether the result agrees with it. With --round and no --a, A is the table's leader, chosen after
  reading: the test is corrected for the arms in play. --family N applies BONFERRONI (alpha/N) here, which is
  Holm's strictest step applied to every member: conservative, never the reverse. Holm's
  step-down needs every p-value in the family at once, which one pair does not have.

THE TEST
  Per item, delta = A - B (items both arms scored, means over repeats). Under the null the
  sign of each delta is a coin flip, so: flip each sign at random, recompute the mean,
  repeat. p = how often |mean| of a flipped sample reaches the observed |mean| (counted
  over every sign pattern up to 30 items, estimated above that: stats.py). No
  distributional assumption, and it keeps the pairing -- which matters here, where ~74% of
  the variance is between articles.

TWO VERSIONS OF ONE DATASET (--b-dataset)
  `--dataset-id D1 --a A --b B --b-dataset D2` tests A's runs on D1 against B's runs on D2, paired by
  item id. It is allowed only when the two datasets pair by item: every item the test uses is in both,
  the reference each arm was scored against says the same thing for each of them (compared item by item,
  by checksum), and both arms are scored on one metric in one direction. Otherwise it refuses and names
  why. What it establishes: the difference is the effect of the dataset change plus the arm's run-to-run
  noise (A and B the same arm: what the change did to it). What it does not: that the change caused it
  (no repeats, no way to separate the two), or anything about items only one version has.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent

from evaluation_harness import _hypothesis, _jsonout  # noqa: E402
from evaluation_harness._common import (  # noqa: E402
    RUNS,
    data_rel,
    dataset_item_ids,
    die,
    evh_prog,
    item_clusters,
    read_item_ids,
    scored_against_dir,
)
from evaluation_harness._runs import default_metric, direction, per_item, runs_on, warn_on_ambiguous_runs  # noqa: E402  # noqa: E402
from evaluation_harness.stats import EXACT_UP_TO, clustered, fmt_p, sign_flip_p  # noqa: E402


def _round_values(dataset_id: str) -> Any:
    """values(config_id, metric) -> {item_id: value} as the round reads the arm (RFC-022): its latest re-score when
    one stands in for its runs. Read from data/runs alone, an arm scored before a measure existed had none, and a
    test the round itself had run (production's run on triage_cost) found 0 shared items."""
    from evaluation_harness import rounds as rd  # noqa: PLC0415
    from evaluation_harness.catalog_adapter import load_catalog_adapter  # noqa: PLC0415

    ca = load_catalog_adapter(None)
    read = rd._reader(ca)

    def values(config_id: str, metric: str) -> dict:
        arm = read(dataset_id, config_id)
        return dict((ca.scores(arm).get(metric) or {}).get("values") or {}) if arm else {}

    return values


def _round_defaults(args: argparse.Namespace, runs: list, values: Any) -> tuple[bool, int]:
    """--round: the round's goal measure, its leader as A and the baseline it started from as B,
    and a refusal for an arm that is not in play in it. Returns (whether A was chosen here from the
    table, how many arms were in play: the candidates it was chosen from)."""
    from evaluation_harness import _common  # noqa: PLC0415
    from evaluation_harness._rounds import arms_of, resolve  # noqa: PLC0415

    rnd = resolve(args.round, args.goal)
    if rnd["dataset_id"] != args.dataset_id:
        die(f"round {args.round} is on {rnd['dataset_id']}, not {args.dataset_id}", "mismatch")
    in_play = arms_of(rnd)
    goal = _common.load_goals().get(rnd["goal"]) or {}
    # The goal's tests flip one sign per cluster: so does this one, unless --cluster names another field.
    args.cluster = args.cluster or _common.goal_cluster(goal, args.dataset_id)
    prim = (goal.get("success_criteria") or {}).get("primary") or {}
    args.metric = args.metric or prim.get("measure")
    for x in (args.a, args.b):
        if x and x not in in_play:
            die(f"{x} is not in play in round {args.round} ({', '.join(in_play)})", "not-found")
    chose = not args.a
    if not args.a:
        means = {}
        for c in in_play:
            v = values(c, args.metric)
            if v:
                means[c] = statistics.fmean(v.values())
        if not means:
            die(f"no arm in round {args.round} records {args.metric} yet", "not-enough")
        args.a = (min if prim.get("direction") == "lower" else max)(means, key=lambda c: means[c])
    if not args.b:
        base = rnd.get("baseline")
        args.b = next((m["config_id"] for d, m in runs if d.name == base), None)
        if not args.b or args.b == args.a:
            die(f"round {args.round} records no other baseline run: name --b", "not-enough")
    print(f"  round {args.round}: {args.a}{' (its leader)' if chose else ''} against {args.b}")
    # The comparisons the leader could have been: every arm in play but B, whether or not B is in play.
    return chose, len([c for c in in_play if c != args.b])


def _hypothesis_of(args: argparse.Namespace, runs: list) -> dict | None:
    """A's hypothesis against B on the tested metric, as its runs recorded it, with whether it was named in
    advance; or, when the config now carries one its runs do not, that it was added after the run."""
    import yaml  # noqa: PLC0415
    from evaluation_harness import _hypothesis  # noqa: PLC0415

    a_runs = [m for _d, m in runs if m["config_id"] == args.a]

    def same(h: Any) -> bool:
        return isinstance(h, dict) and h.get("against") == args.b and h.get("measure") == args.metric

    # Every run of A averaged into the test must carry it (see _hypothesis.across_runs).
    found = _hypothesis.across_runs(a_runs, against=args.b, measure=args.metric)
    if found:
        return found
    path = _hypothesis.config_ids().get(args.a) if a_runs else None
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) if path else None
    if same((cfg or {}).get("hypothesis")):
        return {
            **(cfg or {})["hypothesis"],
            "named": False,
            "commit": None,
            "why": "the config's hypothesis is not on the run: added after it",
        }
    return None


_ESTABLISHES = "the effect of the dataset change plus the arms' run-to-run noise"
_DOES_NOT = "tell the two apart, or speak for items only one version has"

#: How many items a refusal names: enough to find them, not a page.
_NAMED = 5


def _reference_ids(runs: list, config_id: str) -> set[str]:
    """The reference ids an arm's runs were scored against (the fingerprint's data.reference_id)."""
    return {
        str(((m.get("fingerprint") or {}).get("data") or {}).get("reference_id") or "")
        for _d, m in runs
        if m["config_id"] == config_id
    }


def _reference_hashes(reference_id: str, items: list[str]) -> dict[str, str]:
    """{item_id: sha256 of its reference text} for `items`: from the text where it is on this machine, else from
    the checksum the reference's manifest.json or label set's labels.json records. An item with neither is left
    out."""
    root = scored_against_dir(reference_id)
    if root is None:
        return {}
    recorded: dict = {}
    for name, key in (("manifest.json", "items_sha256"), ("labels.json", "items")):
        f = root / name
        if f.is_file():
            try:
                recorded = json.loads(f.read_text(encoding="utf-8")).get(key) or {}
            except ValueError:
                recorded = {}
            break
    out: dict[str, str] = {}
    for i in items:
        t = root / f"{i}.txt"
        if t.is_file():
            out[i] = hashlib.sha256(t.read_bytes()).hexdigest()
            continue
        got = recorded.get(i)
        got = got.get("sha256") if isinstance(got, dict) else got
        if isinstance(got, str) and got:
            out[i] = got
    return out


def _check_same_reference(args: argparse.Namespace, runs_a: list, runs_b: list, items: list[str]) -> str:
    """Refuse unless both arms were scored against one reference each, and those give the same answer for every
    item the test uses. Returns the two reference ids, as one line for the output."""
    ids = []
    for arm, ds, runs in ((args.a, args.dataset_id, runs_a), (args.b, args.b_dataset, runs_b)):
        got = _reference_ids(runs, arm) - {""}
        if len(got) != 1 or ".." in next(iter(got), ""):
            die(
                f"{arm} on {ds} records "
                + (f"{len(got)} different references ({', '.join(sorted(got))})" if got else "no reference")
                + ": a cross-version comparison needs the one reference each arm was scored against, to check "
                "that it says the same on both sides",
                "mismatch",
            )
        ids.append(next(iter(got)))
    ha, hb = (_reference_hashes(r, items) for r in ids)
    unread = sorted(i for i in items if i not in ha or i not in hb)
    if unread:
        die(
            f"cannot compare the references item by item: {len(unread)} item(s) have no reference text or "
            f"checksum in {ids[0]} or {ids[1]} (e.g. {', '.join(unread[:_NAMED])})",
            "not-enough",
        )
    differ = [i for i in items if ha[i] != hb[i]]
    if differ:
        die(
            f"the reference differs between {args.dataset_id} ({ids[0]}) and {args.b_dataset} ({ids[1]}) on "
            f"{len(differ)} of {len(items)} item(s), e.g. {', '.join(differ[:_NAMED])}: the score does not "
            "mean the same on both sides, so this is not a paired comparison",
            "mismatch",
        )
    return f"{ids[0]} / {ids[1]}"


def main() -> int:
    """Test a pre-registered pair with sign-flip permutation."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--a", help="config_id of the arm under test (with --round: default its leader)")
    ap.add_argument(
        "--b", help="config_id it is compared against (with --round: default the baseline it started from)"
    )
    ap.add_argument(
        "--b-dataset",
        help="a second version of --dataset-id: B's runs are read on it, A's on --dataset-id, paired by item id. "
        "Refused unless the items, the reference they are scored against and the metric agree (a cross-version "
        "comparison: the effect of the dataset change plus run-to-run noise)",
    )
    ap.add_argument("--round", help="test within this round of a goal (rN): arms must be in play in it")
    ap.add_argument("--goal", help="the goal --round belongs to, when several goals have one")
    ap.add_argument(
        "--metric",
        help="default: the round's goal measure with --round, else the primary metric the runs recorded",
    )
    ap.add_argument("--runs-dir", type=Path, default=None, help="default: EVAL_RUNS_DIR, else data/runs")
    ap.add_argument("--exclude-dataset", help="drop items this dataset also contains")
    ap.add_argument(
        "--items",
        type=Path,
        help="file of item_ids (one per line); restrict the test to exactly these",
    )
    ap.add_argument(
        "--cluster",
        metavar="FIELD",
        help="an item field whose items are not independent (one thread's comments): flip one sign per value of "
        "it, so related items count once (with --round: default the goal's `cluster:`)",
    )
    ap.add_argument("--permutations", type=int, default=20000)
    ap.add_argument(
        "--family",
        type=int,
        default=None,
        help="how many pairs were tested together (Bonferroni: alpha/family); default 1, or with --round "
        "when A was chosen as the round's leader, the arms in play minus 1",
    )
    ap.add_argument("--seed", type=int, default=20260926)
    ap.add_argument(
        "--asc",
        action="store_true",
        help="lower is better: 'A wins' counts items where A scored lower "
        "(default: inferred from the metric and the runs)",
    )
    ap.add_argument("--desc", action="store_true", help="higher is better, whatever the runs declare")
    ap.add_argument(
        "--json",
        action="store_true",
        help="the same answer as one JSON object: the printed lines as blocks, and the result by name "
        "under result.values (a, b, metric, n, delta, wins, ties, p, method, verdict, threshold, ...)",
    )
    args = ap.parse_args()
    if args.b_dataset and args.round:
        ap.error("--b-dataset and --round cannot be combined: a round is on one dataset")
    if args.b_dataset and not (args.a and args.b):
        ap.error("--b-dataset needs --a and --b")
    if args.family is not None and args.family < 1:
        ap.error(f"--family must be at least 1 (the number of pairs tested together), not {args.family}")
    with _jsonout.collect("pair-test", args.json):
        return _run(args, ap)


def _run(args: argparse.Namespace, ap: argparse.ArgumentParser) -> int:
    # The directory read is the directory warned about: --runs-dir, else EVAL_RUNS_DIR.
    runs_dir = args.runs_dir or RUNS
    # Two runs sharing a config_id are averaged together below without
    # saying so. See _runs.warn_on_ambiguous_runs.
    warn_on_ambiguous_runs(runs_dir, args.dataset_id, label=runs_dir.name)
    runs = runs_on(args.dataset_id, runs_dir=runs_dir)
    cross = bool(args.b_dataset)
    runs_b = []
    if cross:
        if args.b_dataset == args.dataset_id:
            die(
                f"--b-dataset is {args.dataset_id} itself: drop it, both arms are on one dataset",
                "bad-argument",
            )
        ids_a, ids_b = dataset_item_ids(args.dataset_id), dataset_item_ids(args.b_dataset)
        warn_on_ambiguous_runs(runs_dir, args.b_dataset, label=runs_dir.name)
        runs_b = runs_on(args.b_dataset, runs_dir=runs_dir)
    values = _round_values(args.dataset_id) if args.round else None
    chose, candidates = False, None
    if args.round:
        chose, candidates = _round_defaults(args, runs, values)
        if args.family is None and chose:
            args.family = max(candidates, 1)
    elif not (args.a and args.b):
        ap.error("--a and --b are required (or --round, which defaults them)")
    if args.family is None:
        args.family = 1
    _named_metric = bool(args.metric)
    args.metric = args.metric or default_metric(args.dataset_id, runs_dir=runs_dir)
    if cross and not _named_metric:
        other = default_metric(args.b_dataset, runs_dir=runs_dir)
        if other != args.metric:
            die(
                f"the two datasets' runs record different primary metrics ({args.dataset_id}: {args.metric}, "
                f"{args.b_dataset}: {other}): name the one to test with --metric",
                "mismatch",
            )
    if cross:
        arm_a = [r for r in runs if r[1]["config_id"] == args.a]
        arm_b = [r for r in runs_b if r[1]["config_id"] == args.b]
        lower = direction(arm_a, args.metric, args.asc, args.desc)
        lower_b = direction(arm_b, args.metric, args.asc, args.desc)
        if lower != lower_b:
            die(
                f"{args.metric} is {'lower' if lower else 'higher'}-is-better for {args.a} on {args.dataset_id} "
                f"but {'lower' if lower_b else 'higher'}-is-better for {args.b} on {args.b_dataset}: not one "
                "metric (pass --asc or --desc to decide)",
                "mismatch",
            )
        A, B = per_item(arm_a, args.metric), per_item(arm_b, args.metric)
        # A measure that is not stored per item (the goal computes it at re-score) is a missing metric, not an
        # item mismatch: say which side, what is stored, and how to get it (2026-11-04, the first real use).
        for arm, ds, got, rs in ((args.a, args.dataset_id, A, arm_a), (args.b, args.b_dataset, B, arm_b)):
            if rs and not got:
                stored = sorted({k for _d, m in rs for k in (m.get("scores") or {})})
                die(
                    f"{args.metric} is not stored per item in {arm}'s runs on {ds} (stored: {', '.join(stored)}). "
                    "A measure computed at re-score is stored only in the re-scored runs (`evh rescore`): "
                    "point --runs-dir at them.",
                    "not-enough",
                )
    else:
        lower = direction(runs, args.metric, args.asc, args.desc)
        if values is not None:
            A, B = values(args.a, args.metric), values(args.b, args.metric)
        else:
            A = per_item([r for r in runs if r[1]["config_id"] == args.a], args.metric)
            B = per_item([r for r in runs if r[1]["config_id"] == args.b], args.metric)
    items = sorted(set(A) & set(B))
    if args.exclude_dataset:
        prior = dataset_item_ids(args.exclude_dataset)
        items = [i for i in items if i not in prior]
    # AN EXPLICIT ITEM SET, because some strata are not datasets. The one this was added
    # for: the 154 articles that fitted inside BART's 1024-token encoder. On the other 46
    # the local arm summarised two thirds of an article and was scored against a reference
    # written from all of it, so "bart vs an LLM over all 200" averages two different
    # tasks. The stratum is a property of a RUN, not of a dataset, so --exclude-dataset
    # cannot express it. Passing the ids in a file rather than recomputing them inside each
    # script means the leaderboard, the pair tests and the report all use provably the same
    # set -- and a reader can diff it.
    if args.items:
        keep = read_item_ids(args.items)
        items = [i for i in items if i in keep]
    cross_note: list[str] = []
    if cross:
        shared = ids_a & ids_b
        if not shared:
            die(
                f"{args.dataset_id} and {args.b_dataset} share no item id: they do not pair by item",
                "mismatch",
            )
        items = [i for i in items if i in shared]
        if len(items) < 3:
            die(
                f"only {len(items)} item(s) exist in both {args.dataset_id} ({len(ids_a)} items) and "
                f"{args.b_dataset} ({len(ids_b)} items; {len(shared)} ids shared) and are scored for both arms: "
                "nothing to test",
                "not-enough",
            )
        refs = _check_same_reference(args, arm_a, arm_b, items)
        ids_run_a = sorted({d.name for d, _m in arm_a})
        ids_run_b = sorted({d.name for d, _m in arm_b})
        n_a, n_b = len(ids_run_a), len(ids_run_b)
        cross_note = [
            f"  CROSS-VERSION comparison: {args.a} on {args.dataset_id}  vs  {args.b} on {args.b_dataset}",
            f"    item ids shared    {len(shared)} of {len(ids_a)} / {len(ids_b)}; {len(items)} used",
            f"    same reference     {refs}: the same text for each of the {len(items)} items",
            f"    runs averaged      {args.a}: {n_a}, {args.b}: {n_b}; an arm's repeats are averaged per item",
            # Which runs stand for an arm decides the verdict: name them, and where they were read from.
            f"    runs of A          {', '.join(ids_run_a)}",
            f"    runs of B          {', '.join(ids_run_b)}",
            (
                f"    read from          {data_rel(Path(runs_dir))} (another set of an arm's runs, e.g. a repeat set: "
                "--runs-dir)"
            ),
            f"    establishes        {_ESTABLISHES}",
            f"    does not           {_DOES_NOT}",
        ]
    elif len(items) < 3:
        die(f"only {len(items)} shared item(s): nothing to test", "not-enough")

    deltas = [A[i] - B[i] for i in items]
    obs = statistics.fmean(deltas)
    wins = sum(1 for d in deltas if (d < 0 if lower else d > 0))
    ties = sum(1 for d in deltas if d == 0)

    units, n_units = deltas, len(deltas)
    if args.cluster:
        units, _sizes = clustered(
            dict(zip(items, deltas, strict=True)), item_clusters(args.dataset_id, args.cluster)
        )
        n_units = len(units)
        if n_units < 2:
            die(
                f"--cluster {args.cluster}: the {len(items)} items are {n_units} cluster: nothing to test",
                "not-enough",
            )
    p = sign_flip_p(units, permutations=args.permutations, seed=args.seed)
    # BONFERRONI, not Holm. One pair cannot do Holm: the step-down procedure compares the
    # smallest p to alpha/m, the next to alpha/(m-1), and so on, which needs the whole
    # family's p-values at once. alpha/m applied to every member is the strictest step
    # applied throughout -- always conservative relative to Holm, never anti-conservative,
    # so a pair that clears this has cleared Holm too. A pair that does NOT clear it may
    # still clear Holm; run the family's p-values through the step-down to find out.
    thresh = 0.05 / args.family

    for ln in cross_note:
        print(ln)
    print(f"  {args.a}  vs  {args.b}    metric={args.metric}  N={len(items)}")
    print(f"    delta (A - B)      {obs:+.4f}")
    print(
        f"    items A wins       {wins}/{len(items)}"
        + (" (lower is better)" if lower else "")
        + (f" ({ties} exact tie(s))" if ties else "")
    )
    exact = n_units <= EXACT_UP_TO
    how = f"exact, all 2^{n_units} sign patterns" if exact else f"{args.permutations} permutations"
    if args.cluster:
        print(f"    clusters           {n_units} by {args.cluster}: items that share a value count as one")
    print(f"    sign-flip p        {fmt_p(p)}  ({how})")
    hyp = None if cross else _hypothesis_of(args, runs)
    in_advance = bool(hyp and hyp["named"] is True)
    chosen_note = (
        f"    (A was chosen from the table: corrected for the {candidates} comparisons it could have been)"
        if chose and args.family > 1
        else "    (A was chosen from the table: one comparison it could have been: nothing to correct)"
        if chose
        else None
    )
    if args.family > 1:
        # The same rule as Holm and the inspector: p at or below the threshold is significant.
        verdict = "SIGNIFICANT" if p <= thresh else "NOT-SIGNIFICANT"
        print(f"    Bonferroni/{args.family}     threshold {thresh:.4f} -> {verdict}")
        if chosen_note:
            print(chosen_note)
        if p > thresh:
            print("    (conservative: Holm's later steps are looser — check the family)")
    else:
        verdict = "SIGNIFICANT" if p <= 0.05 else "NOT-SIGNIFICANT"
        print(f"    verdict            {verdict} at 0.05")
        print(
            chosen_note
            or (
                "    (uncorrected: valid because the hypothesis was committed before the run)"
                if in_advance
                else "    (uncorrected: valid only if this pair was named before the table was read)"
            )
        )
    if hyp:
        agrees = _hypothesis.agreement(hyp["direction"], obs, lower, p <= thresh)
        shown = {"better": "better than", "worse": "worse than", "no-worse": "no worse than"}[
            hyp["direction"]
        ]
        print(f"    hypothesis         {args.a} {shown} {args.b} on {args.metric}: {hyp['statement']}")
        print(f"    named in advance   {_hypothesis.said(hyp)}")
        print(
            f"    result agrees      {agrees}"
            + (" (no proof of equivalence)" if hyp["direction"] == "no-worse" else "")
        )
    _jsonout.values(
        {
            **(
                {
                    "cross_version": True,
                    "b_dataset_id": args.b_dataset,
                    "items_shared": len(shared),
                    "items_in_a_dataset": len(ids_a),
                    "items_in_b_dataset": len(ids_b),
                    "reference_checked": True,
                    "runs_a": n_a,
                    "run_ids_a": ids_run_a,
                    "run_ids_b": ids_run_b,
                    "runs_b": n_b,
                    "averaged": "per item over each arm's repeats",
                    "establishes": _ESTABLISHES,
                    "does_not_establish": _DOES_NOT,
                }
                if cross
                else {}
            ),
            "a": args.a,
            "b": args.b,
            "metric": args.metric,
            "dataset_id": args.dataset_id,
            "n": len(items),
            "cluster": args.cluster or None,
            "clusters": n_units if args.cluster else None,
            "direction": "lower" if lower else "higher",
            "delta": obs,
            "wins": wins,
            "ties": ties,
            "p": p,
            "method": "exact" if exact else "sampled",
            "permutations": None if exact else args.permutations,
            "seed": args.seed,
            "correction": "bonferroni" if args.family > 1 else "none",
            "family": args.family,
            "alpha": 0.05,
            "threshold": thresh,
            "verdict": verdict,
            "selection": "leader" if chose else "named",
            "candidates": candidates if chose else None,
            "hypothesis": {
                "against": hyp["against"],
                "measure": hyp["measure"],
                "direction": hyp["direction"],
                "statement": hyp["statement"],
                "named_in_advance": _hypothesis.YES
                if hyp["named"]
                else _hypothesis.NO
                if hyp["named"] is False
                else _hypothesis.UNDETERMINED,
                "commit": hyp["commit"],
                "why": hyp["why"],
                "agrees": agrees,
            }
            if hyp
            else None,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
