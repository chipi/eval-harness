#!/usr/bin/env python3
"""Check the instrument against the literature: `span_marker` on a large seeded sample of
the Few-NERD supervised test split, scored the way the field scores it, against the 0.7040
F1 its model card publishes.

    python examples/ner-few-nerd/calibrate.py [--n 2000]

WHY A DIFFERENT METRIC FROM THE EXPERIMENT. The experiment's primary metric is the MEAN
of per-sentence F1 over 8 coarse types, matched on normalised surface strings -- chosen so
an LLM's free-text answer can be scored at all. The literature reports entity-level
MICRO-F1 over the 66 fine types, matched on token spans. They are different numbers, and
no published figure is comparable to ours. This scores the standard way, so the instrument
can be checked against a published value even though the experiment's metric cannot.

    span_marker  guishe/span-marker-generic-ner-v1-fewnerd-fine-super   F1 0.7040 (card)

The test split has 37,648 sentences; this scores a seeded sample of `--n` (default 2,000)
and reports a bootstrap 95% interval. Gold entities are maximal runs of one fine tag, the
dataset's own IO convention. $0, local, ~5-10 minutes. Writes
docs/evidence/calibration/few_nerd.json.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_shared"))
import calibration as cal  # noqa: E402

DATASET, CONFIG, SPLIT_ROWS = "DFKI-SLT/few-nerd", "supervised", 37648
PUBLISHED = {"published": 0.7040, "source": "model card (model-index F1, few-nerd "
             "fine-grained, split listed as 'eval')"}
SEED = 20261014
TOLERANCE = 0.02


def _fine_names() -> list:
    url = f"https://datasets-server.huggingface.co/info?dataset={DATASET}&config={CONFIG}"
    with urllib.request.urlopen(url, timeout=60) as r:
        feats = json.loads(r.read())["dataset_info"]["features"]
    tag = feats["fine_ner_tags"]
    return (tag[0] if isinstance(tag, list) else tag["feature"])["names"]


def _spans(tags: list, names: list) -> set:
    """Maximal runs of one non-O tag -> {(start, end_exclusive, label)}."""
    out, i = set(), 0
    while i < len(tags):
        if tags[i] == 0:
            i += 1
            continue
        j = i
        while j < len(tags) and tags[j] == tags[i]:
            j += 1
        out.add((i, j, names[tags[i]]))
        i = j
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    args = ap.parse_args()
    params = yaml.safe_load((HERE / "configs" / "arm_span_marker_n200.yaml").read_text())["params"]
    from span_marker import SpanMarkerModel  # noqa: PLC0415 - the example's local extra

    model = SpanMarkerModel.from_pretrained(params["model"])
    names = _fine_names()
    offsets = sorted(random.Random(SEED).sample(range(0, SPLIT_ROWS, 100), args.n // 100))
    rows = [r for o in offsets for r in cal.page(DATASET, CONFIG, "test", o)]
    per = []
    for r in rows:
        gold = _spans(r["fine_ner_tags"], names)
        # word_end_index is EXCLUSIVE (checked: "Barack Obama" -> 0, 2), as _spans is.
        pred = {(e["word_start_index"], e["word_end_index"], e["label"])
                for e in model.predict(r["tokens"])} if r["tokens"] else set()
        per.append((len(gold & pred), len(pred - gold), len(gold - pred)))

    def f1(sample):
        tp, fp, fn = (sum(x[k] for x in sample) for k in range(3))
        return 2 * tp / (2 * tp + fp + fn) if tp else 0.0

    point = f1(per)
    rng = random.Random(SEED)
    boots = sorted(f1([per[rng.randrange(len(per))] for _ in per]) for _ in range(1000))
    lo, hi = boots[25], boots[974]
    res = {"n_sentences": len(per), "value": round(point, 4),
           "ci95": round((hi - lo) / 2, 4), "ci95_bounds": [round(lo, 4), round(hi, 4)],
           **PUBLISHED}
    res["verdict"] = cal.verdict(res["value"], res["ci95"], PUBLISHED["published"], TOLERANCE)
    out = {"what": "span_marker, entity-level micro-F1 on 66 fine types, exact token spans, "
                   "on a seeded sample of the Few-NERD supervised test split",
           "sample": f"{len(offsets)} random 100-row pages of {SPLIT_ROWS}, seed {SEED}",
           "arms": {"span_marker": res}}
    print(f"span_marker  micro-F1 (fine) {res['value']:.4f} ±{res['ci95']:.4f} "
          f"(n={len(per)} sentences)   card {PUBLISHED['published']}   {res['verdict']}")
    print(f"wrote {cal.write('few_nerd', out).relative_to(cal.ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
