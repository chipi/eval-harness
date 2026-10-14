#!/usr/bin/env python3
"""Check the instrument against the literature: LEAD-3 on the FULL CNN/DailyMail test set.

    python examples/summarization-cnn-dailymail/calibrate.py

WHY THIS EXISTS
  Every experiment here scores a 200-item slice, and nothing compared a known baseline
  with its published value on the protocol the literature uses. Had anything done so,
  the summarisation slice's bias would have shown at once: LEAD-3 scored ROUGE-1 0.30
  on it, against ~0.40 published, because the first 200 test rows are all CNN's
  and the split is ~91% DailyMail. A calibration row is that check, made permanent.

WHAT IT MEASURES
  LEAD-3 -- this repo's own `_lead_k`, the code the `lead3` arm runs -- on all 11,490
  test articles of abisee/cnn_dailymail 3.0.0, the version the literature reports on,
  scored with `rouge_score` F1 (stemmed), the de-facto standard implementation:

    * ROUGE-1 and ROUGE-2 F1 are comparable to published figures as they stand.
    * ROUGE-Lsum depends on sentence splitting, so it is reported but not compared.

  Also reported per outlet and on this repo's two committed slices, so the slice effect
  is a number rather than a sentence.

  $0: no model, no network beyond fetching the split (~115 pages, stdlib), ~2 minutes.
  Writes docs/evidence/calibration/summarization.json, which check_report_claims reads.
"""

from __future__ import annotations

import importlib.util
import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "docs" / "evidence" / "calibration" / "summarization.json"

#: As published, ROUGE-1 / ROUGE-2 / ROUGE-L F1 x100, non-anonymised CNN/DailyMail test.
PUBLISHED = {
    "lead3": {"rouge1": 40.34, "rouge2": 17.70, "source": "See et al. 2017, "
              "'Get To The Point', Table 1 (lead-3 baseline, non-anonymised)"},
}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    from rouge_score import rouge_scorer  # noqa: PLC0415 - the example's own dependency

    fetch = _load(HERE / "fetch.py", "cnndm_fetch")
    adapter = _load(HERE / "adapter.py", "cnndm_adapter")
    fetch.CONFIG = "3.0.0"
    rows: list[dict] = []
    while True:
        page = fetch._page("test", len(rows), fetch.PAGE)
        if not page:
            break
        rows.extend(page)
    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2"], use_stemmer=True)

    def score(subset: list[dict]) -> dict:
        r1, r2 = [], []
        for r in subset:
            out = adapter._lead_k(r["article"], {"sentences": 3}).output
            s = scorer.score(r["highlights"], out)
            r1.append(s["rouge1"].fmeasure)
            r2.append(s["rouge2"].fmeasure)
        n = len(subset)
        return {"n": n,
                "rouge1": round(100 * st.mean(r1), 2),
                "rouge1_ci95": round(196 * st.pstdev(r1) / n ** 0.5, 2),
                "rouge2": round(100 * st.mean(r2), 2),
                "rouge2_ci95": round(196 * st.pstdev(r2) / n ** 0.5, 2)}

    by_id = {str(r["id"]): r for r in rows}
    slices = {}
    for ds in ("cnn_dailymail_200", "cnn_dailymail_dm200"):
        items = json.loads((ROOT / "harness" / "data" / "datasets" / f"{ds}.json")
                           .read_text())["items"]
        ids = [Path(i["source_path"]).stem for i in items]
        slices[ds] = score([by_id[i] for i in ids if i in by_id])

    result = {
        "what": "lead3 (this repo's _lead_k) on abisee/cnn_dailymail 3.0.0 test, "
                "rouge_score F1 x100, use_stemmer=True",
        "split_rows": len(rows),
        "full_test": score(rows),
        "by_outlet": {
            "cnn": score([r for r in rows if fetch.source_of(r) == "cnn"]),
            "dailymail": score([r for r in rows if fetch.source_of(r) == "dailymail"]),
        },
        "committed_slices": slices,
        "published": PUBLISHED,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    f, p = result["full_test"], PUBLISHED["lead3"]
    print(f"lead3 full test (n={f['n']}): R1 {f['rouge1']} ±{f['rouge1_ci95']}  "
          f"R2 {f['rouge2']} ±{f['rouge2_ci95']}   published R1 {p['rouge1']} R2 {p['rouge2']}")
    for k, v in {**result["by_outlet"], **slices}.items():
        print(f"  {k:22s} n={v['n']:5d}  R1 {v['rouge1']}  R2 {v['rouge2']}")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
