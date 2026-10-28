#!/usr/bin/env python3
"""Download SummEval into the harness: one item per article, expert scores as GOLD.

    python examples/summeval-judging/fetch.py

STDLIB ONLY, like every fetch recipe here: the HuggingFace datasets-server rows API over
HTTPS, no `datasets` library.

WHAT AN ITEM IS
  One CNN/DailyMail test article, the 16 machine summaries SummEval collected for it (from
  2019-era summarisers), and the 11 human reference summaries. The system under test reads
  the article and the 16 summaries and scores each summary on four dimensions. The 11 human
  references are in the item too, because the reference-based metric arms (ROUGE, this
  repo's `coverage`) need them -- the LLM judges are never shown them (adapter.py builds
  their prompt from the article and the summaries only).

WHY THE REFERENCE IS GOLD
  Each summary's score on each dimension is the mean of three EXPERT annotators
  (Fabbri et al. 2021, "SummEval: Re-evaluating Summarization Evaluation"). People, not a
  model, so `references/gold/`. The crowd ratings are not used: the paper shows they
  disagree with the experts.

LICENCE
  mteb/summeval is MIT; so is the original Yale-LILY/SummEval repository, which states no
  separate licence for the annotations. The articles are CNN's (CNN/DailyMail is
  Apache-2.0). Nothing fetched here is committed; see docs/DATA.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "harness"
DATASET = "mteb/summeval"
CONFIG, SPLIT = "default", "test"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from hf_rows import Sources  # noqa: E402
from hf_rows import page as _rows_page  # noqa: E402 - the one retry/pacing schedule

DIMS = ("coherence", "consistency", "fluency", "relevance")


def _rows() -> list[dict]:
    rows: list[dict] = []
    while True:
        page = _rows_page(DATASET, CONFIG, SPLIT, len(rows), 100)
        if not page:
            return rows
        rows.extend(page)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", default="summeval_100")
    ap.add_argument("--force", action="store_true", help="replace an existing slice")
    args = ap.parse_args()
    sources = ROOT / "data" / "sources" / args.dataset_id
    golds = ROOT / "data" / "references" / "gold" / args.dataset_id
    if sources.exists() and not args.force:
        print(f"{sources} already exists -- pass --force to refetch")
        return 0

    rows = _rows()
    # Every row must be complete: 16 summaries, a score for each on every dimension, and
    # the human references. A partial row would be scored on fewer pairs than the others
    # and quietly weighted differently -- refuse instead.
    for r in rows:
        n = len(r["machine_summaries"])
        if n != 16 or any(len(r[d]) != n for d in DIMS) or not r["human_summaries"]:
            sys.exit(f"row {r.get('id')}: incomplete ({n} summaries) -- refusing a partial item")
    # Only the item files go: the gold's committed manifest.json (its checksums) stays.
    for d in (sources, golds):
        for stale in d.glob("*.txt") if d.exists() else ():
            stale.unlink()
        d.mkdir(parents=True, exist_ok=True)
    where = Sources(DATASET, CONFIG, SPLIT)
    for r in rows:
        item = str(r["id"])
        where.record(item, r)
        src = {"article": r["text"], "summaries": r["machine_summaries"], "references": r["human_summaries"]}
        gold = {d: [round(float(v), 10) for v in r[d]] for d in DIMS}
        (sources / f"{item}.txt").write_text(json.dumps(src, ensure_ascii=False, indent=1), encoding="utf-8")
        (golds / f"{item}.txt").write_text(json.dumps(gold, indent=1), encoding="utf-8")
    where.write(ROOT, args.dataset_id)
    refs = sum(len(r["human_summaries"]) for r in rows) / len(rows)
    print(
        f"{len(rows)} articles written ({DATASET}, {SPLIT}): 16 summaries each, "
        f"{refs:.1f} human references on average, expert scores on {len(DIMS)} dimensions"
    )
    print(f"  sources    {sources}\n  gold       {golds}")
    if (ROOT / "data" / "datasets" / f"{args.dataset_id}.json").is_file():
        print(f"\nNext: cd {ROOT} && make dataset-materialize DATASET_ID={args.dataset_id}")
    else:
        print(
            f"\nNext: make dataset-create DATASET_ID={args.dataset_id} "
            f"ARGS='--source-dir data/sources/{args.dataset_id}'"
        )
        print(f"      make dataset-materialize DATASET_ID={args.dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
