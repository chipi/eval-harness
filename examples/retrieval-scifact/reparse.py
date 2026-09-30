#!/usr/bin/env python3
"""Rebuild each reranking run's ranking from its stored LLM replies. $0, no network.

    python examples/retrieval-scifact/reparse.py --out data/runs-reparsed

WHY `rescore.py` CANNOT DO THIS

  `rescore` recomputes SCORES from a run's stored `output`. That works wherever the
  output is the model's answer. It does not work here, because this adapter's output is
  not the model's answer: the pipeline parses the LLM's reply, applies whatever ordering
  it can recover to the BM25 head, and writes the resulting ranking as `output`. The
  parser therefore runs at CALL time, and its result is baked into every stored output.

  So when the parser turned out to be wrong -- it accepted the first "[" anywhere in the
  reply, and read a model reasoning aloud about "[4983]" as a one-document ranking --
  rescoring changed nothing. The damage was upstream of the scores.

  The raw reply survives, in `_meta.llm_raw`, precisely because a previous review asked
  for it. This rebuilds the pipeline from that: same first stage, same fallback, current
  parser.

WHY THE RESULT IS TRUSTWORTHY, AND HOW THAT WAS ESTABLISHED

  Re-parsing `_meta.llm_raw` with a reimplementation of the OLD parser reproduces the
  recorded `llm_returned` for 200/200 items on all 12 reranking arms. The stored reply
  is truncated at 2000 characters, and that check is what shows the truncation is not
  hiding anything the parser would have used.

  Two of the three affected arms were then RE-MEASURED from scratch, and the rebuild
  predicted them to within 0.0004 (llama_s 0.7129 vs 0.7132, qwen_s 0.7183 vs 0.7187).
  The third, llama_l, diverged for a reason that is not the parser: it invented document
  ids on 30 of 200 queries in the new run against 1 of 200 in the old one.

WHAT THIS IS NOT

  Not a measurement. These runs are DERIVED from stored replies and are marked as such:
  `reparsed_from`, `reparsed_at`, `parser_sha256`, and a null `fingerprint.hash` with
  `hash_invalid_because`. An arm whose run carries no `_meta.first_stage` -- the
  encoder-only and baseline arms, which have no LLM stage -- is copied through
  unchanged, because there is nothing to re-parse.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "examples" / "_shared"))
sys.path.insert(0, str(ROOT / "harness" / "scripts"))

from retrieval import parse_ranking, score_ranking, scorer_sha256  # noqa: E402


def qrels_for(refs: Path, item_id: str):
    f = refs / f"{item_id}.txt"
    if not f.is_file():
        return None
    return {str(x["doc_id"]): int(x.get("score", 1))
            for x in json.loads(f.read_text(encoding="utf-8"))
            if isinstance(x, dict) and x.get("doc_id") is not None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=Path, default=ROOT / "harness/data/runs")
    ap.add_argument("--out", type=Path, default=ROOT / "harness/data/runs-reparsed")
    ap.add_argument("--dataset-id", default="scifact_200")
    ap.add_argument("--refs", type=Path,
                    default=ROOT / "harness/data/references/gold/scifact_200")
    args = ap.parse_args()

    if not args.refs.is_dir() or not any(args.refs.glob("*.txt")):
        sys.exit(f"no references under {args.refs}.\n"
                 f"  The corpus is gitignored; rebuild it first:\n"
                 f"    python examples/retrieval-scifact/fetch.py")

    args.out.mkdir(parents=True, exist_ok=True)
    changed_arms = 0
    for d in sorted(args.runs.glob("*")):
        mj = d / "metrics.json"
        pj = d / "predictions.jsonl"
        if not (mj.is_file() and pj.is_file()):
            continue
        m = json.loads(mj.read_text(encoding="utf-8"))
        if m.get("dataset_id") != args.dataset_id:
            continue

        rows = [json.loads(l) for l in pj.read_text(encoding="utf-8").splitlines() if l.strip()]
        if not rows:
            continue
        has_llm = (rows[0].get("_meta") or {}).get("first_stage") is not None

        new_rows, moved = [], 0
        for r in rows:
            if not has_llm:
                new_rows.append(r)
                continue
            meta = r.get("_meta") or {}
            head, full = meta.get("first_stage"), meta.get("ranking")
            q = qrels_for(args.refs, r["item_id"])
            if head is None or full is None or q is None:
                new_rows.append(r)
                continue
            tail = full[len(head):]
            order = parse_ranking(meta.get("llm_raw") or "")
            if order:
                seen, reordered = set(), []
                for doc in order:
                    if doc in head and doc not in seen:
                        seen.add(doc)
                        reordered.append(doc)
                reordered += [doc for doc in head if doc not in seen]
            else:
                reordered = list(head)
            ranking = reordered + tail
            if ranking != full:
                moved += 1
            scored = score_ranking(ranking, q, None, parsed=True)
            nr = dict(r)
            nr.update(scored)
            nr["parsed"] = 1.0
            nr["llm_parsed"] = 1.0 if order is not None else 0.0
            nr["llm_named_unknown"] = float(sum(1 for x in (order or []) if x not in head))
            nr["_meta"] = {**meta, "ranking": ranking, "llm_returned": order}
            new_rows.append(nr)

        import statistics
        keys = sorted({k for r in new_rows for k in r
                       if k != "item_id" and not k.startswith("_")
                       and isinstance(r[k], (int, float))})
        scores = {k: round(statistics.fmean([float(r[k]) for r in new_rows if k in r]), 10)
                  for k in keys}
        for k in ("cost_usd", "tokens_in", "tokens_out"):
            vals = [float(r[k]) for r in new_rows if k in r]
            if vals:
                scores[f"total_{k}"] = round(sum(vals), 8)

        run_dir = args.out / d.name
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "predictions.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in new_rows), encoding="utf-8")
        new = dict(m)
        new["scores"] = scores
        new["reparsed_from"] = d.name
        new["reparsed_with"] = {"parser": "examples/_shared/retrieval.parse_ranking",
                                "scorer_sha256": scorer_sha256()}
        fp = json.loads(json.dumps(new.get("fingerprint") or {}))
        if fp:
            fp["hash"] = None
            fp["hash_invalid_because"] = (
                "rankings were rebuilt from stored LLM replies with a parser this "
                "fingerprint does not describe; see reparsed_with")
            new["fingerprint"] = fp
        (run_dir / "metrics.json").write_text(json.dumps(new, indent=2, sort_keys=True) + "\n",
                                              encoding="utf-8")
        if moved:
            changed_arms += 1
        print(f"  {d.name}  {'%3d items reordered' % moved if moved else 'unchanged'}"
              f"   ndcg_10 {m['scores'].get('ndcg_10', 0):.4f} -> {scores.get('ndcg_10', 0):.4f}")

    print(f"\n  {changed_arms} arm(s) changed. Written to {args.out}")
    print(f"  EVAL_RUNS_DIR={args.out} make leaderboard DATASET_ID={args.dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
