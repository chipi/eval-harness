#!/usr/bin/env python3
"""Check the instrument against the literature: `bert_base_fy` on a large seeded sample
of the DBpedia-14 test split, against the 0.9903 its model card publishes.

    python examples/classification-dbpedia-14/calibrate.py

The experiment scores 280 items (20 per class). The test split has 70,000; scoring all of
them takes over an hour on a CPU, so this scores 5,600 drawn as 56 seeded random pages of
100 across the whole split. Sample error at that size is about ±0.003, smaller than any
gap that would matter. The sample design is stated in the output rather than implied.

    bert_base_fy  fabriceyhc/bert-base-uncased-dbpedia_14   0.9903 (card, "evaluation set")

$0, local, ~6 minutes. Needs torch >= 2.6. Writes docs/evidence/calibration/dbpedia.json.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
import calibration as cal  # noqa: E402
from modules import load_module  # noqa: E402

PUBLISHED = {"published": 0.9903, "source": "model card, 'evaluation set' accuracy"}
SEED, PAGES, SPLIT_ROWS = 20261014, 56, 70_000
TOLERANCE = 0.005


def main() -> int:
    adapter = load_module(HERE / "adapter.py", "db_adapter")
    params = yaml.safe_load((HERE / "configs" / "arm_bert_base_fy_n200.yaml").read_text())["params"]
    labels = params["label_order"]
    offsets = sorted(random.Random(SEED).sample(range(0, SPLIT_ROWS, 100), PAGES))
    sample = [r for o in offsets for r in cal.page("fancyzhx/dbpedia_14", "dbpedia_14", "test", o)]
    adapter.warmup(params)
    acc = cal.accuracy(
        lambda t: adapter.call_system(t, params).output, sample, "content", lambda r: labels[r["label"]]
    )
    acc.update(PUBLISHED, verdict=cal.verdict(acc["value"], acc["ci95"], PUBLISHED["published"], TOLERANCE))
    out = {
        "what": "bert_base_fy on a seeded sample of fancyzhx/dbpedia_14 test, this repo's adapter and config",
        "sample": f"{PAGES} random 100-row pages of {SPLIT_ROWS}, seed {SEED}",
        "arms": {"bert_base_fy": acc},
    }
    print(
        f"bert_base_fy  sample {acc['value']:.4f} ±{acc['ci95']:.4f} (n={acc['n']})   "
        f"card {PUBLISHED['published']:.4f}   {acc['verdict']}"
    )
    print(f"wrote {cal.write('dbpedia', out).relative_to(cal.ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
