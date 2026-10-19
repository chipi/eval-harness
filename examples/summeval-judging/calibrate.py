#!/usr/bin/env python3
"""Check the instrument against the literature: ROUGE and UniEval against the SummEval experts.

    examples/summeval-judging/.venv/bin/python examples/summeval-judging/calibrate.py

WHY NO NEW RUN
  Every other calibration scores a known system on a benchmark's full test set, because
  the experiment itself scores a 200-item slice. Here there is no slice: the 100
  annotated articles ARE the benchmark, the set G-Eval reports on. So the calibration
  rows are the committed ROUGE arms themselves, read from harness/data/runs, and this
  script only puts an interval on them and sets them beside the published figures.

WHAT IT COMPARES
  Kendall tau-b per article against the expert means, averaged over the four dimensions,
  for ROUGE-1, ROUGE-2 and ROUGE-L F1 (each averaged over the 11 references) and for
  UniEval on UniEval's own published inputs (the `unievalpub` arm), against G-Eval (Liu
  et al. 2023), Table 1. The interval is the normal-approximation 95% half-width over the
  100 per-article values. The `unieval` arm, on this experiment's inputs, is not a
  calibration row: its inputs differ from the published protocol on purpose.

WHY AVERAGED OVER THE REFERENCES
  Each article has 11 human references, and the paper does not say how it combined them.
  ROUGE-1 is also recomputed here, through the adapter's own item loader and scorer, with
  the maximum over references and with the first reference alone. Only the average
  reproduces the published row, which is why the arms average.

  $0, no network; needs the example's environment (rouge_score) and the materialized
  dataset (`make data EXP=summeval`). Writes docs/evidence/calibration/summeval.json,
  which check_report_claims reads.
"""

from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNS = ROOT / "harness" / "data" / "runs"
SOURCE = "G-Eval (Liu et al. 2023), Table 1, tau averaged over the four dimensions"
#: Kendall tau against the SummEval experts, as published: the four-dimension average, then
#: coherence, consistency, fluency, relevance. Read from arXiv 2303.16634v3, Table 1.
PUBLISHED = {"rouge1": (0.150, 0.126, 0.130, 0.094, 0.252),
             "rouge2": (0.161, 0.139, 0.155, 0.128, 0.219),
             "rougeL": (0.128, 0.099, 0.092, 0.084, 0.237),
             "unievalpub": (0.377, 0.442, 0.371, 0.371, 0.325)}
DIMS = ("coherence", "consistency", "fluency", "relevance")
#: For protocol differences the paper leaves unstated: how the 11 references are combined
#: and which ROUGE implementation and stemming were used. The same allowance as the other
#: rank- and set-based calibrations here (NER, SciFact).
TOLERANCE = 0.02


def _shared():
    spec = importlib.util.spec_from_file_location("calibration", ROOT / "examples" / "_shared" / "calibration.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["calibration"] = mod
    spec.loader.exec_module(mod)
    return mod


def run_dir(arm: str) -> Path:
    hits = sorted(RUNS.glob(f"se_{arm}_n100_v1_*/predictions.jsonl"))
    if len(hits) != 1:
        raise SystemExit(f"expected one committed run for se_{arm}_n100_v1, found {len(hits)}")
    return hits[0].parent


def per_article(arm: str, key: str = "tau") -> list:
    pj = run_dir(arm) / "predictions.jsonl"
    return [json.loads(ln)[key] for ln in pj.read_text(encoding="utf-8").splitlines() if ln.strip()]


def reference_combinations() -> dict:
    """ROUGE-1 rho and tau under three ways of combining the 11 references."""
    spec = importlib.util.spec_from_file_location("se_adapter", HERE / "adapter.py")
    adapter = importlib.util.module_from_spec(spec)
    sys.modules["se_adapter"] = adapter
    spec.loader.exec_module(adapter)
    from rouge_score import rouge_scorer  # noqa: PLC0415 - the example's own dependency

    data = ROOT / "harness" / "data"
    items = json.loads((data / "datasets" / "summeval_100.json").read_text())["items"]
    scorer = rouge_scorer.RougeScorer(["rouge1"], use_stemmer=True)
    rules = {"mean": statistics.fmean, "max": max, "first": lambda v: v[0]}
    got: dict = {k: [] for k in rules}
    for it in items:
        text = (data / "materialized" / "summeval_100" / it["source_path"]).read_text(encoding="utf-8")
        ref = (data / "references" / "gold" / "summeval_100" / it["source_path"]).read_text(encoding="utf-8")
        item = adapter._item(text)
        per = [[scorer.score(r, s)["rouge1"].fmeasure for r in item["references"]]
               for s in item["summaries"]]
        for k, rule in rules.items():
            res = adapter.score(adapter._broadcast([rule(v) for v in per]), ref, text)
            got[k].append((res["rho"], res["tau"]))
    return {k: {"rho": round(statistics.fmean(x[0] for x in v), 4),
                "tau": round(statistics.fmean(x[1] for x in v), 4)} for k, v in got.items()}


def interval(values: list) -> tuple:
    """Mean and normal-approximation 95% half-width, both rounded for reading."""
    return (round(statistics.fmean(values), 4),
            round(1.96 * statistics.stdev(values) / math.sqrt(len(values)), 4))


def main() -> int:
    cal = _shared()
    arms = {}
    for arm, (pub, *pub_dims) in PUBLISHED.items():
        value, ci95 = interval(per_article(arm))
        dims = {}
        for d, p in zip(DIMS, pub_dims):
            v, c = interval(per_article(arm, f"tau_{d}"))
            dims[d] = {"value": v, "ci95": c, "published": p,
                       "verdict": cal.verdict(v, c, p, TOLERANCE)}
        # A row is consistent only if the average AND every dimension are. The intervals
        # are over articles, and G-Eval scored these same 100, so a gap inside the interval
        # can still be a protocol difference rather than sampling: ROUGE-L's coherence sits
        # 0.054 above the paper, outside its interval and inside interval + TOLERANCE. The
        # per-dimension values are kept
        # so the reports can say so.
        ok = (cal.verdict(value, ci95, pub, TOLERANCE) == "consistent"
              and all(x["verdict"] == "consistent" for x in dims.values()))
        arms[arm] = {"n": len(per_article(arm)), "value": value, "ci95": ci95,
                     "published": pub, "source": SOURCE,
                     "verdict": "consistent" if ok else "differs", "by_dimension": dims}
    path = cal.write("summeval", {
        "what": "ROUGE-1/2/L F1 and UniEval (published inputs) arms on all 100 SummEval "
                "articles (the committed runs), "
                "Kendall tau-b against the expert means",
        "split_rows": 100, "arms": arms,
        "rouge1_reference_combination": reference_combinations()})
    for arm, r in arms.items():
        print(f"  {arm:10s} tau {r['value']:.4f} +/-{r['ci95']:.4f}  vs {r['published']:.3f} published  {r['verdict']}")
        for d, x in r["by_dimension"].items():
            print(f"          {d:11s} {x['value']:.4f} +/-{x['ci95']:.4f} vs {x['published']:.3f}"
                  f"  ({x['value'] - x['published']:+.4f})  {x['verdict']}")
    combos = json.loads(path.read_text())["rouge1_reference_combination"]
    print("  ROUGE-1 by reference combination: " + "  ".join(
        f"{k} rho {v['rho']:.4f} tau {v['tau']:.4f}" for k, v in combos.items()))
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
