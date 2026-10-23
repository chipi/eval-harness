#!/usr/bin/env python3
"""How good is a MODEL-AUTHORED reference as a stand-in for a trusted one?

Most of the time you have no gold. The usual move is to have a strong model write the
references — "silver" — and rank your candidates against those. This asks the question
nobody asks: **does that ranking match the one real ground truth would have given?**

It costs nothing. "Author silver with model X, same prompt and settings as the arms" is
exactly what X already produced on this dataset, so every arm on disk is a candidate
silver author and all of them can be tried at once.

For each candidate author A:
    use A's outputs as the reference set
    score every OTHER arm against them, and rank those arms
    compare that ranking to the one the TRUSTED reference gives for the same arms

A's own row is excluded throughout — an author that also competes scores itself first,
and that artifact is not the interesting part.

    make silver-calibrate DATASET_ID=my_v1 REF_MATCH=_v1 ARM_MATCH=_v2

Read the output against the CEILING it prints. Two runs of the same arms against the
same gold do not rank identically either, so the gold-vs-gold retest correlation is the
best any proxy could score. A silver at rho 0.5 against a ceiling of 0.93 is not "fairly
good"; it is about half of the available agreement.

`--group-by` (default `family`) reports the bias that matters most and that excluding the
author does NOT remove: whether a silver author systematically promotes models of its own
kind.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from _adapter import load_recorded_adapter, score_wants_source
from _common import (
    MATERIALIZED,
    REFERENCES,
    RUNS,
    adapter_search_dirs,
    die,
)
from _runs import runs_on, warn_on_ambiguous_runs
from stats import spearman


def _collect(dataset_id: str, match: str | None) -> dict[str, dict[str, Any]]:
    """arm -> {"texts": {item: [text, ...]}, "params": {...}, "adapter": str}"""
    acc: dict[str, dict[str, Any]] = {}
    # SORTED. The reference set is whichever repeat comes first, and glob order is the
    # filesystem's, not the run's: one author's rho moved 0.238 -> 0.391 purely by which
    # repeat the directory happened to list first. A result that changes when you copy the
    # directory is not a result.
    for d, m in runs_on(dataset_id, match=match):
        cid = m["config_id"]
        # Strip ANY numeric version suffix, not a hardcoded three: `_v10` was kept while
        # `_v1` was stripped, so the same arm appeared twice under different names.
        arm = re.sub(r"_v\d+$", "", cid)
        entry = acc.setdefault(
            arm, {"texts": defaultdict(list), "params": m.get("params") or {}, "adapter": m.get("adapter")}
        )
        for f in sorted((d / "outputs").glob("*.txt")):
            entry["texts"][f.stem].append(f.read_text(encoding="utf-8").strip())
    return acc


def main() -> int:
    """Calibrate silver reference outputs."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--ref-match", help="config_id substring for runs used AS references")
    ap.add_argument("--arm-match", help="config_id substring for runs used AS arms")
    ap.add_argument(
        "--reference-id",
        help="trusted reference dir under data/references (default: the one the runs recorded)",
    )
    ap.add_argument("--metric", default=None, help="default: the adapter's PRIMARY_METRIC")
    ap.add_argument("--group-by", default="family", help="params key for the sibling-bias report; '' to skip")
    args = ap.parse_args()
    # Two runs sharing a config_id are averaged together below without
    # saying so. See _runs.warn_on_ambiguous_runs.
    warn_on_ambiguous_runs(RUNS, args.dataset_id, label=RUNS.name)

    refs_side = _collect(args.dataset_id, args.ref_match)
    arms_side = _collect(args.dataset_id, args.arm_match)
    arms = sorted(set(refs_side) & set(arms_side))
    # FOUR, NOT THREE. Each arm takes a turn as the silver AUTHOR and is judged on how
    # it ranks THE OTHERS, so the subject group is always one smaller than the field.
    # With exactly 3 arms every subject group is 2, every author is skipped by the
    # `len(subject) < 3` guard below, `rows` ends up empty, and the script died on
    #   ValueError: max() arg is an empty sequence
    # while formatting a table with no rows. The gate said 3 because it was counting the
    # field instead of the comparison. Found by external review.
    if len(arms) < 4:
        die(
            f"need at least 4 arms present on both sides; found {len(arms)}.\n"
            f"  Each arm authors a silver reference and is scored on how it ranks the "
            f"OTHER {len(arms) - 1 if arms else 0}, so the comparison needs 3 subjects "
            f"plus the author."
        )

    spec = arms_side[arms[0]]["adapter"]
    if not spec:
        die("runs record no adapter — cannot score")
    # One lookup for every tool that scores a finished run again (experiment_run): this
    # script once joined ROOT.parent unconditionally and could never find the bundled
    # adapter, and later, with its own copy of the lookup, not in a pinned project either.
    found = load_recorded_adapter(spec)
    if found is None:
        die(
            f"adapter not found: {spec!r} is under none of {', '.join(str(d) for d in adapter_search_dirs())}"
        )
    _call, score, _aid, adapter_path, _w, _fp = found
    wants_source = score_wants_source(score)
    metric = args.metric
    if not metric:
        from _adapter import primary_metric  # noqa: PLC0415

        metric = primary_metric(adapter_path) or "overlap_f1"

    ref_id = args.reference_id
    # GOLD WHEN IT EXISTS -- the rule every run follows (experiment_run._reference_for).
    # The default used to be whichever reference the first run in glob order recorded, so a
    # dataset whose early runs predate its gold set was "calibrated" against SILVER: a
    # proxy measured against a proxy, printed as if against ground truth. Found by writing
    # the tutorial (docs/GUIDE.md) and following it.
    if not ref_id and (REFERENCES / "gold" / args.dataset_id).is_dir():
        ref_id = f"gold/{args.dataset_id}"
    if not ref_id:
        # In run order, not the filesystem's: which run names the reference was unsorted.
        for _d, m in runs_on(args.dataset_id):
            ref_id = ((m.get("fingerprint") or {}).get("data") or {}).get("reference_id")
            if ref_id:
                break
    if not ref_id:
        die(
            "no trusted reference found — this measures a proxy AGAINST ground truth, "
            "so there is nothing to calibrate without one"
        )
    if ref_id.startswith("silver/"):
        print(
            f"  WARNING: the trusted reference is SILVER ({ref_id}). This compares one "
            "proxy with another;\n           author gold for this dataset, or pass "
            "--reference-id, for a calibration."
        )
    trusted = {
        os.path.basename(f)[:-4]: Path(f).read_text(encoding="utf-8").strip()
        for f in glob.glob(str(REFERENCES / ref_id / "*.txt"))
    }
    mat = MATERIALIZED / args.dataset_id
    sources = {
        os.path.basename(f)[:-4]: Path(f).read_text(encoding="utf-8", errors="replace")
        for f in glob.glob(str(mat / "*.txt"))
    }
    items = sorted(trusted)

    def rank_against(
        refs: dict[str, str], side: dict[str, dict[str, Any]], subject: list[str]
    ) -> dict[str, float]:
        out = {}
        for a in subject:
            vals = []
            for i in items:
                if i not in refs:
                    continue
                for text in side[a]["texts"].get(i, []):
                    s = score(text, refs[i], sources.get(i)) if wants_source else score(text, refs[i])
                    if metric in s:
                        vals.append(s[metric])
            if vals:
                out[a] = statistics.fmean(vals)
        return out

    print(f"silver calibration on {args.dataset_id}   metric={metric}   arms={len(arms)}")
    print(f"  trusted reference: {ref_id}")

    gold_arm = rank_against(trusted, arms_side, arms)
    gold_ref = rank_against(trusted, refs_side, arms)
    common = sorted(set(gold_arm) & set(gold_ref))
    ceiling = spearman([gold_ref[a] for a in common], [gold_arm[a] for a in common], constant=0.0)
    print(
        f"\n  CEILING — the same arms scored against the same trusted reference, from two\n"
        f"  different sets of runs, agree at rho = {ceiling:+.3f}. No proxy can beat this."
    )

    key = args.group_by or None
    group = {a: (arms_side[a]["params"].get(key) if key else None) for a in arms}

    rows = []
    for author in arms:
        refs = {i: t[0] for i, t in refs_side[author]["texts"].items() if t}
        subject = [a for a in arms if a != author]
        silver = rank_against(refs, arms_side, subject)
        subject = sorted(set(silver) & set(gold_arm))
        if len(subject) < 3:
            continue
        rho = spearman([gold_arm[a] for a in subject], [silver[a] for a in subject], constant=0.0)
        g = {a: i for i, a in enumerate(sorted(subject, key=lambda x: -gold_arm[x]), 1)}
        s = {a: i for i, a in enumerate(sorted(subject, key=lambda x: -silver[x]), 1)}
        sibs = [a for a in subject if key and group[a] and group[a] == group[author]]
        lift = statistics.fmean(g[a] - s[a] for a in sibs) if sibs else None
        rows.append((rho, lift, author, len(sibs)))

    rows.sort(key=lambda r: -r[0])
    if not rows:
        # Belt and braces: the gate above makes this unreachable for arm COUNT, but a
        # field where the two sides barely overlap can still leave every subject group
        # under three. Say which, rather than dying in the table formatter.
        die(
            f"no author had 3+ subject arms in common between the two reference sides; "
            f"{len(arms)} arm(s) were present on both, and the overlap is what decides "
            f"this, not the total."
        )
    w = max(len(r[2]) for r in rows) + 2
    print(f"\n  {'silver author':{w}}{'rho vs trusted':>16}{'sibling lift':>14}")
    print("  " + "-" * (w + 30))
    for rho, lift, author, n in rows:
        lift_s = f"{lift:+.1f}" if lift is not None else "—"
        print(f"  {author:{w}}{rho:>16.3f}{lift_s:>14}   ({n} sibling(s))")

    rr = [r[0] for r in rows]
    ll = [r[1] for r in rows if r[1] is not None]
    print(
        f"\n  rho: min {min(rr):+.3f}  mean {statistics.fmean(rr):+.3f}  max {max(rr):+.3f}"
        f"   (ceiling {ceiling:+.3f})"
    )
    if ll:
        pos = sum(1 for x in ll if x > 0)
        print(
            f"  sibling lift: mean {statistics.fmean(ll):+.1f} rank positions, positive for"
            f" {pos} of {len(ll)} authors"
        )
        if pos > len(ll) * 0.7:
            print(
                f"\n  A silver author systematically PROMOTES models grouped with it by"
                f" {args.group_by!r}.\n"
                "  Excluding the author's own row does not remove this: the bias is not an\n"
                "  author scoring itself, it is an author rewarding its own kind's style.\n"
                "  A silver-ranked leaderboard is therefore not merely noisier than a gold\n"
                "  one -- it is biased in a direction you can predict from who wrote it."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
