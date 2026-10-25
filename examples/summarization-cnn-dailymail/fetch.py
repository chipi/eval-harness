#!/usr/bin/env python3
"""Download a slice of CNN/DailyMail into the harness, sources and GOLD references.

    python examples/summarization-cnn-dailymail/fetch.py --n 50

STDLIB ONLY. It reads the HuggingFace datasets-server rows API over HTTPS rather than
using the `datasets` library, so getting the data costs no pyarrow, no pandas and no
2GB of transitive dependencies. For a 50-row eval slice that is the whole job.

WHY THIS DATASET
  abisee/cnn_dailymail is apache-2.0 — the only clearly-licensed option among the usual
  summarisation benchmarks (XSum's licence is listed "unknown") — and it is the most-cited
  summarisation baseline, so published ROUGE numbers exist to sanity-check ours against.
  That is the point of using a standard set instead of inventing data: somebody else's
  baseline is a check on our instrument.

WHY THE REFERENCE IS GOLD
  `highlights` are the bullet summaries written by the journalists who filed the article.
  Human-authored, so `references/gold/`. Every run scored against them says tier=gold,
  which is a stronger claim than this harness's bundled demo can make — that one authors
  a silver reference with a model, because its placeholder items have no human summary to
  use. Here there is one.

THE DEFAULT SLICE IS THE FIRST N ROWS, AND THEY ARE ALMOST ALL CNN
  The test split puts CNN's articles first (1,093 of 11,490), DailyMail after. So
  `--n 200` -- the slice every committed run measured -- is all CNN (196 with CNN's
  dateline, 4 partner pieces CNN republished),
  while the test split as a whole is mostly DailyMail. Measured 2026-10-14: lead-3
  scores ROUGE-1 0.30 on that slice and about 0.40 on DailyMail articles, which is why
  this repo's absolute ROUGE sat ~0.09 below published numbers and nobody noticed.

  The default is unchanged, so the committed slice still reproduces byte for byte.
  `--draw random --seed S` draws uniformly from the whole split instead, and
  `--source dailymail|cnn` restricts the draw to one outlet:

      python examples/summarization-cnn-dailymail/fetch.py --n 200 \
          --draw random --seed 20261014 --source dailymail --dataset-id cnn_dailymail_dm200

  A random draw reads the whole split (~115 pages) once, because a uniform sample
  cannot be taken from a prefix. Source is inferred from the dateline: CNN articles
  open with a parenthesised dateline ("(CNN)", or a partner's for pieces CNN
  republished); DailyMail articles never do. Checked against the published split
  counts: 1,093 CNN and 10,397 DailyMail. The script prints the composition so the
  inference is visible, not assumed.

NOTHING IS COMMITTED
  The fetched slice is gitignored. Redistributing a third-party corpus is a licence
  question nobody should inherit by cloning a repo, so each example downloads its own.
"""

from __future__ import annotations

import argparse
import random
import re
import shutil
import sys
from pathlib import Path

# parents[2] is the repo root, so this resolves to <root>/harness — the harness this
# example feeds. Getting the level wrong silently creates a SECOND data tree somewhere
# else and everything appears to work, which is exactly what it did the first time.
ROOT = Path(__file__).resolve().parents[2] / "harness"
DATASET = "abisee/cnn_dailymail"
CONFIG = "1.0.0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from hf_rows import page as _rows_page  # noqa: E402 - the one retry/pacing schedule

#: The API caps a single request; ask in pages rather than assuming one call is enough.
PAGE = 100


def _page(split: str, offset: int, length: int) -> list[dict]:
    """One page of rows, paced, retried (hf_rows: the shared schedule)."""
    return _rows_page(DATASET, CONFIG, split, offset, length)


def fetch_rows(n: int, split: str) -> list[dict]:
    """The first `n` rows of the split, paged."""
    rows: list[dict] = []
    while len(rows) < n:
        page = _page(split, len(rows), min(PAGE, n - len(rows)))
        if not page:
            break  # the split ran out before n — say so below rather than loop forever
        rows.extend(page)
    return rows[:n]


def source_of(row: dict) -> str:
    """'cnn' or 'dailymail', from the dateline. The dataset has no source field.

    CNN's articles carry "(CNN)" in their dateline ("Washington (CNN) --"); partner pieces
    CNN republished open with the partner's instead -- "(The Hollywood Reporter)",
    "(Billboard)". DailyMail articles do neither. The first version tested for "(CNN)" alone and counted
    1,067 CNN rows against the published 1,093, putting CNN's partner pieces into the
    DailyMail pool; three landed in the first draw of the DailyMail slice.
    """
    a = row["article"]
    return "cnn" if "(CNN)" in a[:300] or re.match(r"\s*\([^)]{2,40}\)", a) else "dailymail"


def fetch_random(n: int, split: str, seed: int, source: str) -> list[dict]:
    """`n` rows drawn uniformly (seeded) from the whole split, optionally one outlet."""
    rows: list[dict] = []
    while True:
        page = _page(split, len(rows), PAGE)
        if not page:
            break
        rows.extend(page)
    by = {"cnn": 0, "dailymail": 0}
    for r in rows:
        by[source_of(r)] += 1
    print(f"  split {split}: {len(rows)} rows — {by['cnn']} CNN, {by['dailymail']} DailyMail")
    pool = [r for r in rows if source in ("any", source_of(r))]
    pick = sorted(random.Random(seed).sample(range(len(pool)), min(n, len(pool))))
    return [pool[i] for i in pick]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=50, help="items to fetch (default: 50)")
    ap.add_argument("--split", default="test", help="dataset split (default: test)")
    ap.add_argument("--dataset-id", default=None, help="harness dataset_id (default: cnn_dailymail_<n>)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing slice")
    ap.add_argument(
        "--draw",
        choices=("head", "random"),
        default="head",
        help="head = the first n rows (default; the committed slice); "
        "random = a seeded uniform draw from the whole split",
    )
    ap.add_argument("--seed", type=int, default=20261014, help="seed for --draw random")
    ap.add_argument(
        "--source",
        choices=("any", "cnn", "dailymail"),
        default="any",
        help="restrict --draw random to one outlet",
    )
    args = ap.parse_args()

    dataset_id = args.dataset_id or f"cnn_dailymail_{args.n}"
    sources = ROOT / "data" / "sources" / dataset_id
    golds = ROOT / "data" / "references" / "gold" / dataset_id

    if sources.exists() and not args.force:
        print(f"{sources} already exists — pass --force to refetch")
        return 0

    if args.draw == "head" and args.source != "any":
        sys.exit("--source needs --draw random: the first n rows are whatever the split starts with")
    rows = (
        fetch_rows(args.n, args.split)
        if args.draw == "head"
        else fetch_random(args.n, args.split, args.seed, args.source)
    )
    cnn = sum(source_of(r) == "cnn" for r in rows)
    print(f"  slice: {cnn} CNN, {len(rows) - cnn} DailyMail")
    if len(rows) < args.n:
        print(f"  NOTE: asked for {args.n}, the split gave {len(rows)}")
    if not rows:
        sys.exit("no rows returned — nothing written")

    # --force REPLACES the slice. It used to write into the existing directories, so a
    # redraw left the previous draw's files beside the new ones (584 files after three
    # draws of 200) and `dataset-create` would have frozen all of them.
    for d in (sources, golds):
        if d.exists():
            shutil.rmtree(d)
    sources.mkdir(parents=True, exist_ok=True)
    golds.mkdir(parents=True, exist_ok=True)
    for row in rows:
        # The dataset's own id, so an item is traceable back to the published row rather
        # than to our enumeration order.
        item = str(row["id"])
        (sources / f"{item}.txt").write_text(row["article"], encoding="utf-8")
        (golds / f"{item}.txt").write_text(row["highlights"], encoding="utf-8")

    article_words = sum(len(r["article"].split()) for r in rows) / len(rows)
    summary_words = sum(len(r["highlights"].split()) for r in rows) / len(rows)
    print(f"{len(rows)} item(s) written")
    print(f"  articles   {sources}      (mean {article_words:.0f} words)")
    print(f"  gold refs  {golds}  (mean {summary_words:.0f} words)")
    print(f"\n  Long inputs are the point: a {article_words:.0f}-word article is where a local")
    print("  model's context limit and an LLM's price per token both start to bite.")
    print("\nNext:")
    if (ROOT / "data" / "datasets" / f"{dataset_id}.json").is_file():
        # Frozen and committed: check the fetched bytes against it, never re-create it.
        print(f"  cd {ROOT} && make dataset-materialize DATASET_ID={dataset_id}")
        print("  (or, from the repository root: make data EXP=<experiment> does all of this)")
    else:
        print(f"  make dataset-create DATASET_ID={dataset_id} ARGS='--source-dir data/sources/{dataset_id}'")
        print(f"  make dataset-materialize DATASET_ID={dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
