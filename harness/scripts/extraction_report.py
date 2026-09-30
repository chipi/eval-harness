#!/usr/bin/env python3
"""Corpus micro-F1, per-type breakdown, type confusion and annotation noise, for set tasks.

    python scripts/extraction_report.py --dataset-id few_nerd_280
    python scripts/extraction_report.py --dataset-id few_nerd_280 --arm fn_span_marker_n200_v1

WHY THIS IS A SCRIPT AND NOT A METRIC

  The same reason `classification_report.py` is. The harness scores each item and
  averages, and for extraction that IS a legitimate metric -- an item has its own gold
  set, so its F1 is well defined and the mean of those is an honest per-item number.

  What the mean cannot express is the CORPUS figure: pool every tp, fp and fn across the
  run and compute one F1. Mean-of-per-item-F1 and corpus micro-F1 answer different
  questions -- "how did it do on a typical sentence" versus "how did it do over all the
  entities" -- and they disagree whenever an arm's errors are concentrated in
  entity-dense sentences. Neither is a per-item number, so neither can be a metric, and
  the gap between them is the interesting part.

  Per-type precision and recall have the same shape as macro-F1 did there: they need
  every prediction of that type across the whole run.

WHAT AN ANNOTATION ERROR LOOKS LIKE HERE, AND WHY IT IS NOT THE CLASSIFICATION CASE

  In classification, a near-universal miss means the item's single LABEL is probably
  wrong. There is exactly one thing to be wrong about.

  A set has two, and they are not symmetric:

    CONSENSUS MISS       a gold entity almost no arm found. Either genuinely hard, or the
                         span boundary is an artifact -- Few-NERD is IO-tagged, so two
                         adjacent entities of one type merge into a single span that no
                         arm can reproduce because the intended one is not recoverable.

    CONSENSUS INVENTION  an entity almost every arm predicted that is NOT in gold. This
                         has no analogue in classification, and it is the stronger
                         signal: independent models do not agree on a hallucination. When
                         twenty arms all tag something the annotator left out, the
                         annotation is incomplete.

  Both are printed. The second is the one to read first.

BASELINE ARMS ARE EXCLUDED FROM THE CONSENSUS PASS
  `nothing` predicts the empty set on every item and would count as missing every gold
  entity; `capitalized` emits every capitalised run and would count as inventing
  hundreds. Either would drown the signal, in opposite directions.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "examples" / "_shared"))

from _common import REFERENCES, RUNS, SOURCES, die, read_json, warn_on_ambiguous_runs  # noqa: E402

try:
    from extraction import as_members, match_one_to_one, normalize  # noqa: E402
except ImportError:  # pragma: no cover
    die("examples/_shared/extraction.py not importable — run from the harness root")

#: Arms whose job is to be a floor or a ceiling, not to be right. Excluded from the
#: consensus pass only; they still appear in the ranking, which is what they are for.
_BASELINES = ("_nothing", "_capitalized")


def gold_sets(dataset_id: str) -> dict:
    """item_id -> the gold list of {text, type}, from the tracked gold references."""
    root = REFERENCES / "gold" / dataset_id
    if not root.is_dir():
        die(f"no gold references at {root}")
    out = {}
    for p in root.glob("*.txt"):
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            die(f"gold reference {p.name} is not JSON — is this a set-valued dataset?")
    return out


def predictions(dataset_id: str, match: str | None) -> dict:
    """config_id -> {item_id: predicted list or None}. None means unreadable output.

    None and `[]` are kept apart here for the same reason the scorer now keeps them
    apart: an arm that could not be read did not predict the empty set.
    """
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
            if row.get("item_id"):
                out[cid][row["item_id"]] = (row.get("_meta") or {}).get("predicted")
    return out


def corpus_prf(pred_by_item: dict, gold: dict, typed: bool) -> dict:
    """One pooled precision/recall/F1 over every entity in the run."""
    tp = fp = fn = 0
    for item, g in gold.items():
        if item not in pred_by_item:
            continue
        p = pred_by_item[item]
        gm = as_members(g, typed)
        pm = as_members(p or [], typed) if p is not None else []
        hit = match_one_to_one(pm, gm)
        tp += hit
        fp += len(pm) - hit
        fn += len(gm) - hit
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"p": prec, "r": rec,
            "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
            "tp": tp, "fp": fp, "fn": fn}


def per_type(pred_by_item: dict, gold: dict) -> dict:
    """Precision / recall / F1 / support for each gold entity type."""
    tp: Counter = Counter()
    fp: Counter = Counter()
    fn: Counter = Counter()
    for item, g in gold.items():
        if item not in pred_by_item:
            continue
        p = pred_by_item[item] or []
        remaining = as_members(g, True)
        for m in as_members(p, True):
            if m in remaining:
                remaining.remove(m)
                tp[m[1]] += 1
            else:
                fp[m[1]] += 1
        for m in remaining:
            fn[m[1]] += 1
    stats = {}
    for t in sorted(set(tp) | set(fp) | set(fn)):
        prec = tp[t] / (tp[t] + fp[t]) if tp[t] + fp[t] else 0.0
        rec = tp[t] / (tp[t] + fn[t]) if tp[t] + fn[t] else 0.0
        stats[t] = {"p": prec, "r": rec,
                    "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
                    "support": tp[t] + fn[t]}
    return stats


def type_confusion(pred_by_item: dict, gold: dict) -> Counter:
    """(gold type, predicted type) for spans found but MISTYPED.

    Only spans that matched untyped are counted, so this isolates the type head from the
    detector -- which is the whole point of reporting `type_penalty` per item.
    """
    conf: Counter = Counter()
    for item, g in gold.items():
        if item not in pred_by_item:
            continue
        gt = {normalize(e.get("text", "")): (e.get("type") or "").casefold()
              for e in g if isinstance(e, dict)}
        for e in (pred_by_item[item] or []):
            if not isinstance(e, dict):
                continue
            key = normalize(e.get("text", ""))
            if key in gt:
                got = (e.get("type") or "").casefold()
                if got != gt[key]:
                    conf[(gt[key], got or "<none>")] += 1
    return conf


def _consensus(preds: dict, gold: dict, threshold: float, top: int,
               dataset_id: str) -> dict:
    learned = {a: p for a, p in preds.items() if not any(b in a for b in _BASELINES)}
    if len(learned) < 3:
        print(f"\n  {len(learned)} learned arm(s) — need at least 3 for a consensus pass.")
        return
    n = len(learned)
    src = SOURCES / dataset_id

    def snippet(item: str) -> str:
        f = src / f"{item}.txt"
        return " ".join(f.read_text(encoding="utf-8").split())[:150] if f.is_file() else ""

    # ARMS, not occurrences. Counting occurrences let one arm that emitted the same span
    # twice contribute two votes, and the report printed "25/17" -- a consensus figure
    # larger than the field. The claim being made is "N independent arms agree", so the
    # unit has to be the arm.
    missed: dict = defaultdict(set)
    invented: dict = defaultdict(set)
    for arm, by_item in learned.items():
        for item, g in gold.items():
            if item not in by_item:
                continue
            p = by_item[item]
            gm = as_members(g, True)
            pm = as_members(p or [], True) if p is not None else []
            # Which specific members matched, so a miss and an invention can be named.
            rem = list(gm)
            matched_p = []
            for m in pm:
                if m in rem:
                    rem.remove(m)
                    matched_p.append(m)
            for m in rem:
                missed[(item, m)].add(arm)
            for m in pm:
                if m in matched_p:
                    matched_p.remove(m)
                    continue
                invented[(item, m)].add(arm)

    # THE SAME SPAN IN BOTH LISTS. When a span is in gold, is predicted by nearly every
    # arm, and still counts as both a miss AND an invention, the only thing they disagree
    # about is the TYPE -- and the field is unanimous on the other side. That is the
    # highest-confidence annotation error this script can produce, and it was previously
    # split across the two sections below where a reader had to notice it twice and join
    # it up. "Georgia Dome", gold `location`, called `building` by all 17 arms, is one.
    type_rows = []
    for (item, (text, kind)), arms in missed.items():
        for (item2, (text2, kind2)), arms2 in invented.items():
            if item2 == item and text2 == text and kind2 != kind and len(arms2) >= threshold * n:
                type_rows.append((len(arms2), item, text, kind, kind2))
    type_rows.sort(reverse=True)
    print(f"\n  TYPE DISAGREEMENTS — same span, gold says one type, >= {threshold:.0%} of"
          f" {n} arms say another")
    print("    The span is not in dispute; only its label is, and the field is unanimous")
    print("    against the annotation. Read these before concluding an arm is weak on a type.")
    if not type_rows:
        print("    None.")
    for c, item, text, gk, pk in type_rows[:top]:
        print(f"    {c}/{n}  \"{text}\"   gold {gk}  ->  arms {pk}   item {item[:12]}")
    relabel = {(item, text): pk for _, item, text, _gk, pk in type_rows}

    print(f"\n  CONSENSUS INVENTIONS — predicted by >= {threshold:.0%} of {n} learned arms,"
          f" ABSENT from gold")
    print("    Independent models do not agree on a hallucination. Where they all tag the")
    print("    same span, the ANNOTATION is the thing most likely to be incomplete.")
    rows = sorted(((len(v), k) for k, v in invented.items() if len(v) >= threshold * n),
                  reverse=True)
    if not rows:
        print(f"    None. No span was invented by >= {threshold:.0%} of the arms.")
    for c, (item, (text, kind)) in rows[:top]:
        print(f"\n    {c}/{n}  \"{text}\" as {kind}   item {item[:12]}")
        print(f"      gold: {[ (e.get('text'), e.get('type')) for e in gold[item] ]}")
        print(f"      {snippet(item)}")

    print(f"\n  CONSENSUS MISSES — in gold, found by < {1 - threshold:.0%} of {n} learned arms")
    print("    Either genuinely hard, or a span no arm can reproduce. Few-NERD is")
    print("    IO-tagged, so two adjacent entities of one type merge into one gold span.")
    rows = sorted(((len(v), k) for k, v in missed.items() if len(v) >= threshold * n),
                  reverse=True)
    if not rows:
        print(f"    None. Every gold span was found by > {1 - threshold:.0%} of the arms.")
    for c, (item, (text, kind)) in rows[:top]:
        print(f"\n    missed by {c}/{n}  \"{text}\" as {kind}   item {item[:12]}")
        print(f"      {snippet(item)}")
    return relabel


def _ceiling(preds: dict, gold: dict, relabel: dict) -> dict:
    """Typed mean F1 if every unanimous type disagreement were resolved the arms' way.

    AN UPPER BOUND, NOT AN ESTIMATE, and the distinction is the whole point. Resolving a
    disagreement in favour of the arms necessarily raises the arms' scores -- that is
    what "in favour of" means -- so this number cannot be read as what the field would
    score against perfect annotation. It answers one narrower question: how much of the
    typed/untyped gap could annotation account for AT MOST.

    If the answer is small, `type_penalty` is a real modelling problem and the type head
    is where to spend effort. If it is large, a chunk of what looks like type confusion
    is the corpus disagreeing with itself.
    """
    fixed = {}
    for item, ents in gold.items():
        out = []
        for e in ents:
            if not isinstance(e, dict):
                out.append(e)
                continue
            key = (item, normalize(e.get("text", "")))
            out.append({**e, "type": relabel[key]} if key in relabel else e)
        fixed[item] = out
    return {arm: _mean_item_f1(by_item, fixed) for arm, by_item in preds.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--match", help="only config_ids containing this substring")
    ap.add_argument("--arm", help="print this arm's per-type table and type confusion")
    ap.add_argument("--miss-threshold", type=float, default=0.8,
                    help="share of learned arms that must agree (default: 0.8)")
    ap.add_argument("--top", type=int, default=10, help="rows per consensus section")
    args = ap.parse_args()
    # Two runs sharing a config_id are averaged together below without
    # saying so. See _common.warn_on_ambiguous_runs.
    warn_on_ambiguous_runs(RUNS, args.dataset_id, label=RUNS.name)

    gold = gold_sets(args.dataset_id)
    preds = predictions(args.dataset_id, args.match)
    if not preds:
        die(f"no runs on {args.dataset_id!r}"
            + (f" matching {args.match!r}" if args.match else ""))

    n_ent = sum(len(v) for v in gold.values())
    empty = sum(1 for v in gold.values() if not v)
    # GOLD THAT THE NORMALISER DELETES. An entity whose text survives normalisation as
    # the empty string is not comparable to anything, so the item behaves as empty-gold
    # for every arm: predict nothing and score 1.0, predict anything and score 0.0.
    #
    # Not hypothetical, and not a bug in either half. few_nerd_280 item a68981540c14 is
    # "Its revenue quickly increased, from £ 4,424 in 1901 to £ 274,989 in 1910", and
    # Few-NERD tags the bare currency symbol "£" as an entity of type `other`, twice.
    # Stripping punctuation is the right call for comparing entity mentions; calling a
    # currency sign an entity is the odd end of it. Neither side is worth changing for
    # one item -- but the FLOOR moves, and an unexplained 1/280 discrepancy between the
    # `nothing` arm and the empty-gold rate is the kind of thing that gets rationalised
    # away instead of looked at. So it is printed.
    ghosts = [i for i, v in gold.items() if v and not as_members(v, True)]
    print(f"\n  {args.dataset_id}: {len(gold)} item(s), {n_ent} gold entities, "
          f"{len(preds)} arm(s)")
    print(f"  {empty} item(s) have no gold entities")
    if ghosts:
        print(f"  {len(ghosts)} further item(s) have gold that NORMALISES AWAY entirely, so")
        print(f"  the floor an empty prediction scores is "
              f"{(empty + len(ghosts)) / len(gold):.4f}, not {empty / len(gold):.4f}:")
        for i in ghosts:
            raw = ", ".join(f"{e.get('text')!r}/{e.get('type')}" for e in gold[i])
            print(f"    {i[:12]}  gold {raw}")
    print()

    print(f"  {'arm':<26} {'mean f1':>8} {'micro f1':>9} {'micro P':>8} {'micro R':>8} "
          f"{'unt micro':>10} {'unread':>7}")
    print("  " + "-" * 82)
    table = []
    for arm, by_item in preds.items():
        rows = [v for v in by_item.values()]
        unread = sum(1 for v in rows if v is None)
        mean_f1 = _mean_item_f1(by_item, gold)
        c = corpus_prf(by_item, gold, True)
        cu = corpus_prf(by_item, gold, False)
        table.append((mean_f1, arm, c, cu, unread, len(rows)))
    for mean_f1, arm, c, cu, unread, n in sorted(table, reverse=True):
        print(f"  {arm:<26} {mean_f1:>8.4f} {c['f1']:>9.4f} {c['p']:>8.4f} {c['r']:>8.4f} "
              f"{cu['f1']:>10.4f} {unread:>4}/{n}")
    print("\n  'mean f1' is the harness metric: the mean of each item's own F1.")
    print("  'micro f1' pools every tp/fp/fn in the run. They answer different questions;")
    print("  where micro is the lower of the two, the arm is worse on entity-dense items.")

    if args.arm:
        if args.arm not in preds:
            die(f"{args.arm!r} not among {sorted(preds)}")
        by_item = preds[args.arm]
        print(f"\n  PER TYPE — {args.arm}")
        print(f"    {'type':<16} {'P':>7} {'R':>7} {'F1':>7} {'support':>8}")
        for t, s in sorted(per_type(by_item, gold).items(), key=lambda kv: -kv[1]["support"]):
            print(f"    {t or '<none>':<16} {s['p']:>7.4f} {s['r']:>7.4f} {s['f1']:>7.4f} "
                  f"{s['support']:>8}")
        conf = type_confusion(by_item, gold)
        print(f"\n  TYPE CONFUSION — {args.arm} (span found, type wrong)")
        if not conf:
            print("    None: every span it found, it typed correctly.")
        for (g, p), c in conf.most_common(15):
            print(f"    {g:<16} -> {p:<16} {c:>4}")

    relabel = _consensus(preds, gold, args.miss_threshold, args.top, args.dataset_id)
    if relabel:
        ceil = _ceiling(preds, gold, relabel)
        print(f"\n  UPPER BOUND ON THE ANNOTATION SHARE OF `type_penalty`")
        print(f"    Typed mean F1 if all {len(relabel)} unanimous type disagreements were")
        print("    resolved the arms' way. An upper bound, not an estimate: resolving them")
        print("    in the arms' favour is what raises the number. Read the SIZE of the")
        print("    move, not the value.")
        print(f"\n    {'arm':<26} {'as measured':>12} {'bound':>8} {'move':>8}")
        for arm, v in sorted(ceil.items(), key=lambda kv: -kv[1]):
            base = _mean_item_f1(preds[arm], gold)
            print(f"    {arm:<26} {base:>12.4f} {v:>8.4f} {v - base:>+8.4f}")
    return 0


def _mean_item_f1(by_item: dict, gold: dict) -> float:
    tot = 0.0
    n = 0
    for item, g in gold.items():
        if item not in by_item:
            continue
        n += 1
        p = by_item[item]
        if p is None:
            continue  # unreadable scores 0, per the scorer
        gm, pm = as_members(g, True), as_members(p, True)
        if not gm and not pm:
            tot += 1.0
            continue
        hit = match_one_to_one(pm, gm)
        prec = hit / len(pm) if pm else 0.0
        rec = hit / len(gm) if gm else 0.0
        if prec + rec:
            tot += 2 * prec * rec / (prec + rec)
    return tot / n if n else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
