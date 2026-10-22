#!/usr/bin/env python3
"""Check the instrument against the literature: BM25 on ALL 300 SciFact test queries,
against BEIR's published BM25 nDCG@10 of 0.665.

    python examples/retrieval-scifact/fetch.py --n 300 --dataset-id scifact_test300
    python examples/retrieval-scifact/calibrate.py

The experiment scores 200 of the 300 test queries (seeded); the reports compared its
BM25 0.6451 with BEIR's 0.665 without saying that one is over 200 queries and the other
over 300. This scores all 300 with this repo's BM25 arm and scorer.

It is not expected to match exactly, and the gap is the point of recording it: BEIR's
BM25 is Elasticsearch over title and abstract as separate fields with its own analyser;
ours is `rank_bm25` over one concatenated field, no stemming, default k1/b. A gap
beyond sample error is a fact about the instrument that the reports should state.

$0, local, ~1 minute after the fetch. Writes docs/evidence/calibration/scifact.json.
"""

from __future__ import annotations

import importlib.util
import math
import statistics as st
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
import calibration as cal  # noqa: E402

DATA = cal.ROOT / "harness" / "data"
DATASET = "scifact_test300"
PUBLISHED = {"published": 0.665, "source": "Thakur et al. 2021, BEIR, Table 2 (BM25, SciFact, nDCG@10)"}
#: Allowed gap beyond our CI for a different BM25 implementation and field handling.
TOLERANCE = 0.02


def main() -> int:
    spec = importlib.util.spec_from_file_location("sf_adapter", HERE / "adapter.py")
    adapter = importlib.util.module_from_spec(spec)
    sys.modules["sf_adapter"] = adapter
    spec.loader.exec_module(adapter)
    params = yaml.safe_load((HERE / "configs" / "arm_bm25_n200.yaml").read_text())["params"]
    src, gold = DATA / "sources" / DATASET, DATA / "references" / "gold" / DATASET
    queries = sorted(src.glob("*.txt"))
    if len(queries) != 300:
        sys.exit(
            f"expected 300 queries under {src}, found {len(queries)} — run fetch.py "
            f"--n 300 --dataset-id {DATASET} first"
        )
    adapter.warmup(params)
    ndcg = []
    for q in queries:
        out = adapter.call_system(q.read_text(encoding="utf-8"), params).output
        ndcg.append(adapter.score(out, (gold / q.name).read_text(encoding="utf-8"))["ndcg_10"])
    n = len(ndcg)
    res = {
        "n": n,
        "value": round(st.mean(ndcg), 4),
        "ci95": round(1.96 * st.pstdev(ndcg) / math.sqrt(n), 4),
        **PUBLISHED,
    }
    res["verdict"] = cal.verdict(res["value"], res["ci95"], PUBLISHED["published"], TOLERANCE)
    out = {
        "what": "this repo's BM25 arm (rank_bm25, one field, no stemming) on all 300 "
        "BeIR/scifact test queries, full 5,183-doc corpus",
        "arms": {"bm25": res},
    }
    print(
        f"bm25  all 300 queries nDCG@10 {res['value']:.4f} ±{res['ci95']:.4f}   "
        f"BEIR {PUBLISHED['published']}   {res['verdict']}"
    )
    print(f"wrote {cal.write('scifact', out).relative_to(cal.ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
