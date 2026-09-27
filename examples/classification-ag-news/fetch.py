#!/usr/bin/env python3
"""Download a STRATIFIED slice of AG News into the harness, sources and GOLD references.

    python examples/classification-ag-news/fetch.py --n 200

STDLIB ONLY, like the summarisation example's fetcher: it reads the HuggingFace
datasets-server rows API over HTTPS rather than pulling in `datasets`, pyarrow and pandas
to move a few hundred short strings.

WHY THIS ONE STRATIFIES AND THE SUMMARISATION ONE DOES NOT
  AG News's test split is not shuffled. Paging from offset 0, as the summarisation fetcher
  does, gives this:

      first  20: {'Business': 1, 'Sci/Tech': 19}
      first 200: {'Business': 29, 'Sci/Tech': 57, 'Sports': 53, 'World': 61}

  A 20-item slice that is 95% one class is not a hard eval, it is a broken one: an arm that
  always answers "Sci/Tech" scores 0.95 and the table ranks constants above models. Even at
  200 the 1.7:1 spread between Business and World would make macro-F1 and accuracy disagree
  for a reason that is an artefact of paging rather than a property of any arm.

  So this fetcher takes n/4 per class, in split order. Deterministic (same --n, same items),
  and NESTED the way the harness's holdout analysis needs: the 5-per-class slice is a subset
  of the 50-per-class one, so `holdout_significance.py --exclude-dataset` still means what it
  says.

WHY THIS DATASET
  AG News is the most-cited news topic-classification baseline, so published accuracies
  exist to check our instrument against -- the same reason the summarisation example uses
  CNN/DailyMail. Four coarse classes, short texts, and fine-tuned BERT-class models in the
  94-95% range with zero-shot LLMs well below that. A gap that wide is a good instrument
  test: if our harness cannot see it, the harness is wrong.

LICENCE -- READ THIS, IT IS WEAKER THAN THE SUMMARISATION EXAMPLE'S
  The HuggingFace dataset card lists the licence as `unknown`. The corpus's own description
  says it is "provided by the academic community for research purposes ... and any other
  NON-COMMERCIAL activity". That is not a grant of rights, it is a statement of intent by
  the people who assembled it.

  This script therefore does what the CNN/DailyMail one does and no more: it downloads a
  slice to YOUR machine, and the slice is gitignored. We redistribute nothing. But
  CNN/DailyMail carried an explicit apache-2.0 grant and this does not, so anyone wanting to
  use AG News commercially has to resolve that themselves. Do not read permission into the
  fact that this example exists.

WHY THE REFERENCE IS GOLD
  The labels are human-assigned editorial categories from the source news feeds, not model
  output -- so `references/gold/`. A reference file here holds one word.

A CAVEAT WORTH KNOWING BEFORE READING ANY RESULT
  Many AG News texts carry their syndication tag inline: "(AP)", "(Reuters)",
  "(SPACE.com)". Those tags correlate with the label -- SPACE.com is Sci/Tech essentially
  always -- so an arm can score well by reading the byline rather than the article. That is
  a property of the corpus, it affects every arm, and it caps how much "understanding" any
  accuracy number here can be said to demonstrate.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# parents[2] is the repo root -> <root>/harness, the harness this example feeds. Getting
# the level wrong silently creates a SECOND data tree and everything appears to work.
ROOT = Path(__file__).resolve().parents[2] / "harness"
ROWS_API = "https://datasets-server.huggingface.co/rows"
DATASET = "fancyzhx/ag_news"
CONFIG = "default"

#: The API caps a single request; page rather than assume one call is enough.
PAGE = 100

#: The dataset's own label order. Index IS the stored integer, so this list must not be
#: reordered -- it is the mapping between the corpus and every reference file we write.
LABELS = ["World", "Sports", "Business", "Sci/Tech"]


def fetch_rows(limit: int, split: str) -> list[dict]:
    """Up to `limit` rows from the datasets-server, paged."""
    rows: list[dict] = []
    while len(rows) < limit:
        want = min(PAGE, limit - len(rows))
        query = urllib.parse.urlencode(
            {"dataset": DATASET, "config": CONFIG, "split": split,
             "offset": len(rows), "length": want}
        )
        try:
            with urllib.request.urlopen(f"{ROWS_API}?{query}", timeout=60) as resp:
                payload = json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001 - one message, not a traceback
            sys.exit(
                f"could not reach the datasets-server: {type(exc).__name__}: {exc}\n"
                "  it is an HTTPS API; check connectivity, then retry."
            )
        page = payload.get("rows") or []
        if not page:
            break  # the split ran out before the pool filled; reported by the caller
        rows.extend(r["row"] for r in page)
    return rows


def stratify(rows: list[dict], per_class: int) -> list[dict]:
    """First `per_class` rows of each label, in split order.

    Order matters twice. Taking the FIRST of each class rather than a random sample makes
    the slice reproducible without carrying a seed, and makes a smaller slice a strict
    subset of a larger one -- which is what lets the 20-item set be held out of the
    200-item set later.
    """
    kept: dict[int, list[dict]] = collections.defaultdict(list)
    for row in rows:
        bucket = kept[int(row["label"])]
        if len(bucket) < per_class:
            bucket.append(row)
    # Emitted class by class rather than interleaved: item ids are content hashes, so file
    # order carries no meaning anyway, and grouping makes a short listing readable.
    out: list[dict] = []
    for label in range(len(LABELS)):
        out.extend(kept.get(label, []))
    return out


def item_id(text: str) -> str:
    """Content-addressed id.

    AG News rows carry no id of their own -- unlike CNN/DailyMail, where the published row
    id is used. Hashing the text keeps an item traceable to its exact bytes and stable
    across paging, refetches and --n changes. 40 hex chars to match the other example's
    id shape.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:40]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=200,
                    help="total items; split evenly across the 4 classes (default: 200)")
    ap.add_argument("--split", default="test", help="dataset split (default: test)")
    ap.add_argument("--dataset-id", default=None, help="harness dataset_id (default: ag_news_<n>)")
    ap.add_argument("--pool", type=int, default=None,
                    help="rows to scan for the stratified draw (default: 8x n, min 400)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing slice")
    args = ap.parse_args()

    if args.n % len(LABELS):
        sys.exit(f"--n must divide by {len(LABELS)} so the classes stay balanced; got {args.n}")
    per_class = args.n // len(LABELS)

    dataset_id = args.dataset_id or f"ag_news_{args.n}"
    sources = ROOT / "data" / "sources" / dataset_id
    golds = ROOT / "data" / "references" / "gold" / dataset_id

    if sources.exists() and not args.force:
        print(f"{sources} already exists — pass --force to refetch")
        return 0

    # The pool has to be bigger than n because the split is class-clustered: the first 20
    # rows hold one Business item, so a pool of n would starve the rarer classes.
    pool_size = args.pool or max(8 * args.n, 400)
    pool = fetch_rows(pool_size, args.split)
    if not pool:
        sys.exit("no rows returned — nothing written")
    rows = stratify(pool, per_class)

    got = collections.Counter(LABELS[int(r["label"])] for r in rows)
    short = {lab: per_class - got.get(lab, 0) for lab in LABELS if got.get(lab, 0) < per_class}
    if short:
        print(f"  NOTE: scanned {len(pool)} rows and still short: {short}")
        print(f"        raise --pool above {pool_size} for a balanced slice")

    sources.mkdir(parents=True, exist_ok=True)
    golds.mkdir(parents=True, exist_ok=True)
    for row in rows:
        text = str(row["text"])
        item = item_id(text)
        (sources / f"{item}.txt").write_text(text, encoding="utf-8")
        # One word. The scorer compares against it exactly, so no trailing newline: a
        # reference that differs from the model's answer by whitespace is a scoring bug
        # waiting to be blamed on the model.
        (golds / f"{item}.txt").write_text(LABELS[int(row["label"])], encoding="utf-8")

    words = sorted(len(str(r["text"]).split()) for r in rows)
    print(f"{len(rows)} item(s) written, {per_class} per class")
    print(f"  texts      {sources}")
    print(f"  gold refs  {golds}")
    print(f"  classes    {dict(sorted(got.items()))}")
    print(f"  words      min {words[0]}  median {words[len(words) // 2]}  max {words[-1]}")
    print(f"\n  Balanced by construction, so the majority-class floor is exactly "
          f"{1 / len(LABELS):.2f}.")
    print("  Any arm below that is worse than a constant, which is worth knowing.")
    print("\nNext:")
    print(f"  make dataset-create DATASET_ID={dataset_id} ARGS='--source-dir data/sources/{dataset_id}'")
    print(f"  make dataset-materialize DATASET_ID={dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
