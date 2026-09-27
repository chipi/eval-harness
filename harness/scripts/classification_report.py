#!/usr/bin/env python3
"""Confusion matrix, macro-F1 and per-class precision/recall, from stored predictions.

    python scripts/classification_report.py --dataset-id ag_news_200
    python scripts/classification_report.py --dataset-id ag_news_200 --arm ag_keyword_v1

WHY THIS IS A SCRIPT AND NOT A METRIC

  The harness scores each item and averages. That is exactly right for accuracy -- score
  an item 1 or 0, take the mean, and the mean IS accuracy -- and it cannot express F1 at
  all. Precision for a class needs every prediction of that class across the whole run;
  it is a property of the SET, not of any item, so there is no per-item number whose
  average is macro-F1.

  The tempting workaround is a per-item pseudo-F1 that averages to something F1-shaped.
  It does not equal macro-F1, it has no interpretation, and it would sit in the
  leaderboard looking exactly as authoritative as the real thing. So: accuracy stays the
  per-item metric and the ranking metric, and everything requiring a confusion matrix
  lives here, computed from `_meta.predicted` in each run's predictions.jsonl.

WHY MACRO AND NOT MICRO
  Micro-F1 on a single-label problem equals accuracy, so reporting both would be
  reporting one number twice. Macro-F1 weights every class equally, which is the one that
  disagrees with accuracy -- an arm that is excellent on three classes and hopeless on the
  fourth looks fine on accuracy and bad here. On a balanced slice they track closely and
  the GAP is the interesting part: it is the signal that an arm has a blind spot rather
  than a uniform error rate.

  On a balanced set accuracy is also micro-recall, so a large accuracy/macro-F1 gap means
  the errors are concentrated, not that the arm is worse than it looked.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _common import REFERENCES, RUNS, SOURCES, die, read_json  # noqa: E402

#: Predictions the adapter could not parse into a label are counted, never dropped. An arm
#: that returns prose on a fifth of the items has a real problem, and silently excluding
#: those items would raise its precision by removing its failures from the denominator.
UNPARSED = "<unparsed>"


def gold_labels(dataset_id: str) -> dict:
    """item_id -> gold label, from the tracked gold reference files."""
    root = REFERENCES / "gold" / dataset_id
    if not root.is_dir():
        die(f"no gold references at {root}")
    return {p.stem: p.read_text(encoding="utf-8").strip() for p in root.glob("*.txt")}


def predictions(dataset_id: str, match: str | None) -> dict:
    """config_id -> {item_id: predicted label}, over every matching run on disk."""
    out: dict = defaultdict(dict)
    for d in sorted(RUNS.glob("*")):
        mj, pj = d / "metrics.json", d / "predictions.jsonl"
        if not (mj.is_file() and pj.is_file()):
            continue
        m = read_json(mj)
        cid = m.get("config_id")
        if m.get("dataset_id") != dataset_id or not cid:
            continue
        if match and match not in cid:
            continue
        for line in pj.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            item = row.get("item_id")
            if not item:
                continue
            pred = (row.get("_meta") or {}).get("predicted")
            out[cid][item] = pred if pred else UNPARSED
    return out


def per_class(pairs: list, labels: list) -> dict:
    """precision / recall / f1 / support per class, from (gold, predicted) pairs."""
    stats = {}
    for label in labels:
        tp = sum(1 for g, p in pairs if g == label and p == label)
        fp = sum(1 for g, p in pairs if g != label and p == label)
        fn = sum(1 for g, p in pairs if g == label and p != label)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        stats[label] = {"p": prec, "r": rec, "f1": f1, "support": tp + fn}
    return stats


def _report_consensus_misses(rows: list, gold: dict, dataset_id: str, threshold: float) -> None:
    """Items that nearly every arm got wrong. Usually the LABEL, not the models.

    WHY THIS IS IN THE REPORT AND NOT IN A NOTEBOOK. On DBpedia-14 fourteen arms reported
    byte-identical accuracy, macro-F1 AND worst class. The reason was one item: "Dukart's
    Canal", gold `NaturalPlace`, which 20 of 24 arms called `MeanOfTransportation` and 4
    called `Building`. It is a man-made waterway built to move coal — the models are
    right and the ontology's label is the odd one out.

    One such item put a ceiling under every arm and made a 14-way tie look like agreement
    between models when it was agreement about a bad label. Finding it took a bespoke
    script, which is exactly the kind of thing that does not get written when it matters.

    Baseline arms are excluded: `constant` gets 13 of 14 classes wrong by construction and
    would drown the signal.
    """
    learned = [r for r in rows if not r["arm"].endswith(("constant_v1", "constant_n200_v1"))
               and "keyword" not in r["arm"]]
    if len(learned) < 3:
        return
    missed: dict = defaultdict(list)
    for r in learned:
        for item, (g, p) in zip(r["items"], r["pairs"]):
            if g != p:
                missed[item].append(p)
    n = len(learned)
    consensus = sorted(((len(v), i, v) for i, v in missed.items() if len(v) >= threshold * n),
                       reverse=True)
    if not consensus:
        print(f"\n    No item was missed by >= {threshold:.0%} of the {n} learned arms.")
        return
    print(f"\n  ITEMS THE FIELD MISSED — >= {threshold:.0%} of {n} learned arms wrong")
    print("    A near-universal miss is evidence about the LABEL or the item, not about")
    print("    the models. Read these before reading the ranking.")
    src = SOURCES / dataset_id
    for count, item, preds in consensus[:10]:
        tally = ", ".join(f"{lab} x{c}" for lab, c in
                          sorted(Counter(preds).items(), key=lambda kv: -kv[1]))
        print(f"\n    {item}  missed by {count}/{n}")
        print(f"      gold {gold[item]}   predicted {tally}")
        f = src / f"{item}.txt"
        if f.is_file():
            snippet = " ".join(f.read_text(encoding="utf-8").split())[:150]
            print(f"      {snippet}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--match", help="only config_ids containing this substring")
    ap.add_argument("--arm", help="print this arm's full confusion matrix")
    ap.add_argument("--sort", default="macro_f1", choices=("macro_f1", "accuracy"))
    ap.add_argument("--miss-threshold", type=float, default=0.8,
                    help="flag items missed by at least this share of learned arms")
    args = ap.parse_args()

    gold = gold_labels(args.dataset_id)
    labels = sorted(set(gold.values()))
    preds = predictions(args.dataset_id, args.match)
    if not preds:
        die(f"no runs for {args.dataset_id}" + (f" matching {args.match}" if args.match else ""))

    rows = []
    for cid, by_item in sorted(preds.items()):
        pairs = [(gold[i], p) for i, p in by_item.items() if i in gold]
        if not pairs:
            continue
        stats = per_class(pairs, labels)
        n = len(pairs)
        rows.append({
            "arm": cid,
            "n": n,
            "accuracy": sum(1 for g, p in pairs if g == p) / n,
            "macro_f1": sum(s["f1"] for s in stats.values()) / len(labels),
            "unparsed": sum(1 for _, p in pairs if p == UNPARSED) / n,
            # The worst class is the number a single accuracy figure hides. An arm at 0.92
            # accuracy with a class at 0.55 is not a 0.92 arm for anyone who cares about
            # that class.
            "worst_f1": min(s["f1"] for s in stats.values()),
            "worst_class": min(stats.items(), key=lambda kv: kv[1]["f1"])[0],
            "stats": stats,
            "pairs": pairs,
            "items": [i for i in by_item if i in gold],
        })
    rows.sort(key=lambda r: -r[args.sort])

    width = max(len(r["arm"]) for r in rows) + 2
    print(f"\n  dataset: {args.dataset_id}   {len(labels)} classes   sorted by {args.sort}")
    print(f"\n    {'arm':{width}} {'n':>5} {'accuracy':>9} {'macro_f1':>9} "
          f"{'unparsed':>9} {'worst_f1':>9}  worst class")
    for r in rows:
        print(f"    {r['arm']:{width}} {r['n']:>5} {r['accuracy']:9.4f} {r['macro_f1']:9.4f} "
              f"{r['unparsed']:9.4f} {r['worst_f1']:9.4f}  {r['worst_class']}")

    gaps = [(r["accuracy"] - r["macro_f1"], r["arm"]) for r in rows]
    worst_gap, worst_arm = max(gaps)
    print(f"\n    Largest accuracy - macro_f1 gap: {worst_gap:+.4f} ({worst_arm}).")
    print("    A gap means the errors are concentrated in some classes rather than spread;")
    print("    accuracy alone would call that arm uniformly good.")

    _report_consensus_misses(rows, gold, args.dataset_id, args.miss_threshold)

    if args.arm:
        row = next((r for r in rows if r["arm"] == args.arm), None)
        if row is None:
            die(f"no run for arm {args.arm}")
        print(f"\n  CONFUSION MATRIX — {args.arm}   rows = gold, columns = predicted")
        cols = labels + [UNPARSED]
        cw = max(len(c) for c in cols) + 2
        lw = max(len(x) for x in labels) + 2
        print(f"    {'':{lw}}" + "".join(f"{c:>{cw}}" for c in cols))
        for g in labels:
            counts = [sum(1 for gg, pp in row["pairs"] if gg == g and pp == c) for c in cols]
            print(f"    {g:{lw}}" + "".join(f"{v:>{cw}}" for v in counts))
        print(f"\n    {'class':{lw}} {'precision':>10} {'recall':>8} {'f1':>8} {'support':>8}")
        for label, s in row["stats"].items():
            print(f"    {label:{lw}} {s['p']:10.4f} {s['r']:8.4f} {s['f1']:8.4f} "
                  f"{s['support']:8d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
