#!/usr/bin/env python3
"""Check the instrument against the literature: the three fine-tuned AG News classifiers
on the FULL 7,600-item test set, against the accuracy each model card publishes.

    python examples/classification-ag-news/calibrate.py

The experiment scores 200 items (50 per class from the first 1,600 test rows). This runs
the same adapter, with each arm's own config, on all 7,600 and compares with the card:

    bert_mini     mrm8488/bert-mini-finetuned-age_news-classification   0.9339 (HF-verified, test)
    bert_base_ta  textattack/bert-base-uncased-ag-news                  0.9514 ("eval set" = 7,231/7,600)
    bert_base_fy  fabriceyhc/bert-base-uncased-ag_news                  0.9375 ("eval set")

$0, local, ~15 minutes on a 4-core CPU. Needs the example's `local` extra (torch >= 2.6
for the two bert-base checkpoints). Writes docs/evidence/calibration/ag_news.json.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
import calibration as cal  # noqa: E402

ARMS = {
    "bert_mini": {"published": 0.9339, "source": "model card, HF-verified test accuracy"},
    "bert_base_ta": {
        "published": 0.9514,
        "source": "model card, 'eval set accuracy' (0.951447 = 7,231/7,600, i.e. the test split)",
    },
    "bert_base_fy": {"published": 0.9375, "source": "model card, 'evaluation set' accuracy"},
}
#: Allowed gap beyond our own CI: the cards' figures may use other truncation/precision.
TOLERANCE = 0.005


def main() -> int:
    spec = importlib.util.spec_from_file_location("ag_adapter", HERE / "adapter.py")
    adapter = importlib.util.module_from_spec(spec)
    sys.modules["ag_adapter"] = adapter
    spec.loader.exec_module(adapter)
    labels = ["World", "Sports", "Business", "Sci/Tech"]
    test = cal.rows("fancyzhx/ag_news", "default", "test")
    out = {
        "what": "fine-tuned arms on the full fancyzhx/ag_news test split, this repo's adapter and configs",
        "split_rows": len(test),
        "arms": {},
    }
    for arm, pub in ARMS.items():
        params = yaml.safe_load((HERE / "configs" / f"arm_{arm}_n200.yaml").read_text())["params"]
        adapter.warmup(params)
        acc = cal.accuracy(
            lambda t, params=params: adapter.call_system(t, params).output,
            test,
            "text",
            lambda r: labels[r["label"]],
        )
        acc.update(pub, verdict=cal.verdict(acc["value"], acc["ci95"], pub["published"], TOLERANCE))
        out["arms"][arm] = acc
        print(
            f"{arm:13s} full test {acc['value']:.4f} ±{acc['ci95']:.4f}   "
            f"card {pub['published']:.4f}   {acc['verdict']}"
        )
    print(f"wrote {cal.write('ag_news', out).relative_to(cal.ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
