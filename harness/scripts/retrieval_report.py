#!/usr/bin/env python3
"""Pipeline ceilings, rank movement and hallucination, for ranked-list tasks.

    python scripts/retrieval_report.py --dataset-id scifact_200
    python scripts/retrieval_report.py --dataset-id scifact_200 --arm sf_qwen_s_n200_v1

WHY THIS IS A SCRIPT AND NOT A METRIC

  Same reason `classification_report.py` and `extraction_report.py` are, plus one that is
  specific to this task: a two-stage arm has a CEILING it did not choose. A reranker
  cannot rank a document its first stage never returned, so its achievable recall@10 is
  bounded by the first stage's recall@k, and its nDCG@10 is bounded by what a PERFECT
  reordering of those same candidates would score.

  That ceiling is not a property of any single item's score, and it is the number that
  decides where to spend effort. An arm at 0.73 against a ceiling of 0.74 is done; the
  next gain has to come from the retriever. An arm at 0.73 against a ceiling of 0.95 has
  most of its headroom still on the table and a better reranker would find it.

WHAT "PERFECT REORDERING" MEANS HERE
  Take the arm's first-stage candidates, sort them so every relevant document precedes
  every irrelevant one, and score that. It is an ORACLE: it uses the gold labels, so it
  is not achievable, and it is not a baseline anybody could deploy. It is the bound.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "examples" / "_shared"))

from _common import REFERENCES, RUNS, die, read_json  # noqa: E402

try:
    from retrieval import NDCG_AT, dcg, score_ranking  # noqa: E402
except ImportError:  # pragma: no cover
    die("examples/_shared/retrieval.py not importable — run from the harness root")


def qrels(dataset_id: str) -> dict:
    root = REFERENCES / "gold" / dataset_id
    if not root.is_dir():
        die(f"no gold references at {root}")
    out = {}
    for p in root.glob("*.txt"):
        judged = json.loads(p.read_text(encoding="utf-8"))
        out[p.stem] = {str(j["doc_id"]): int(j.get("score", 1)) for j in judged}
    return out


def runs(dataset_id: str, match: str | None) -> dict:
    out: dict = {}
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
        rows = {}
        for line in pj.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["item_id"]] = r
        out[cid] = (m, rows)
    return out


def oracle_ndcg(candidates: list, rel: dict) -> float:
    """nDCG@10 of a PERFECT reordering of these candidates. The bound, not a baseline."""
    gains = sorted((float(2 ** rel[c] - 1) for c in candidates if c in rel), reverse=True)
    gains += [0.0] * (NDCG_AT - len(gains))
    ideal = sorted((float(2 ** g - 1) for g in rel.values()), reverse=True)[:NDCG_AT]
    idcg = dcg(ideal)
    return dcg(gains[:NDCG_AT]) / idcg if idcg else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--match")
    ap.add_argument("--arm", help="print this arm's rank-movement detail")
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    gold = qrels(args.dataset_id)
    R = runs(args.dataset_id, args.match)
    if not R:
        die(f"no runs on {args.dataset_id!r}")

    print(f"\n  {args.dataset_id}: {len(gold)} queries, {len(R)} arm(s)\n")
    print(f"  {'arm':<26} {'nDCG@10':>8} {'ceiling':>8} {'gap':>7} {'used':>7} "
          f"{'llm_ok':>7} {'invented':>9}")
    print("  " + "-" * 80)

    table = []
    for cid, (m, rows) in R.items():
        ndcg = m["scores"].get("ndcg_10", 0.0)
        ceils, invented, llm_ok, n = [], 0.0, [], 0
        for item, rel in gold.items():
            r = rows.get(item)
            if not r:
                continue
            n += 1
            meta = r.get("_meta") or {}
            cand = meta.get("first_stage") or meta.get("ranking") or []
            ceils.append(oracle_ndcg(list(cand)[:20], rel))
            invented += float(r.get("llm_named_unknown", 0.0) or 0.0)
            if "llm_parsed" in r:
                llm_ok.append(float(r["llm_parsed"]))
        ceiling = sum(ceils) / len(ceils) if ceils else 0.0
        # SHARE OF AVAILABLE HEADROOM ACTUALLY TAKEN. Not the same as nDCG/ceiling: an arm
        # is credited against what its candidates made POSSIBLE, so a pipeline on a weak
        # first stage is not penalised twice for the retriever's misses.
        used = ndcg / ceiling if ceiling else 0.0
        table.append((ndcg, cid, ceiling, used,
                      (sum(llm_ok) / len(llm_ok)) if llm_ok else None,
                      invented / n if n else 0.0))
    for ndcg, cid, ceil, used, ok, inv in sorted(table, key=lambda t: -t[0]):
        oks = f"{ok:>7.3f}" if ok is not None else "      -"
        print(f"  {cid:<26} {ndcg:>8.4f} {ceil:>8.4f} {ceil-ndcg:>7.4f} {used:>6.1%} "
              f"{oks} {inv:>9.2f}")
    print("\n  'ceiling' = nDCG@10 of a PERFECT reordering of this arm's own top-20")
    print("  candidates. An ORACLE: it reads the gold labels and nobody can deploy it.")
    print("  'gap' is what a better reranker could still win WITHOUT a better retriever;")
    print("  'used' is the share of available headroom taken. 'invented' is document ids")
    print("  per query that the LLM named and the first stage never returned.")

    if args.arm:
        if args.arm not in R:
            die(f"{args.arm!r} not among {sorted(R)}")
        m, rows = R[args.arm]
        moved: Counter = Counter()
        for item, rel in gold.items():
            r = rows.get(item)
            if not r:
                continue
            meta = r.get("_meta") or {}
            before = [c for c in (meta.get("first_stage") or [])]
            after = [c for c in (meta.get("ranking") or [])]
            for d in rel:
                if d in before and d in after:
                    moved[before.index(d) - after.index(d)] += 1
        print(f"\n  RANK MOVEMENT OF RELEVANT DOCUMENTS — {args.arm}")
        print("    positive = the reranker moved it UP. 0 = untouched.")
        up = sum(c for k, c in moved.items() if k > 0)
        down = sum(c for k, c in moved.items() if k < 0)
        same = moved.get(0, 0)
        print(f"    moved up {up}   unchanged {same}   moved DOWN {down}")
        for k, c in sorted(moved.items(), key=lambda kv: -kv[1])[:args.top]:
            print(f"      {k:+d} positions  x{c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
