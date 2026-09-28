#!/usr/bin/env python3
"""Download a seeded-random slice of Few-NERD into the harness, sources and GOLD references.

    python examples/ner-few-nerd/fetch.py --n 280

STDLIB ONLY, like the other fetchers: the HuggingFace datasets-server rows API over HTTPS.

WHY THE DRAW IS A PLAIN RANDOM SAMPLE AND NOT STRATIFIED
  The two classification fetchers stratify by class, because there an item HAS a class.
  A sentence here carries several entities of several types at once, so there is no class
  to stratify on -- the unit of sampling is the sentence. Measured on the first 300 test
  rows, the split is also NOT sorted by anything visible (unlike DBpedia, whose test split
  is fully class-ordered), so a random draw is both necessary and sufficient.

  Seeded, so the same --n and --seed reproduce the same items, and nested: --n 56 takes a
  prefix of the same permutation --n 280 does, which is what
  `holdout_significance --exclude-dataset` needs.

WHAT THE CORPUS LOOKS LIKE (measured, first 300 test rows)
  22 tokens median, 66 max. 2.50 entities per sentence on average -- and 15% of sentences
  have NO entities at all. That last figure matters more than it looks: it is where an arm
  that invents entities gets caught, and it fixes the floor. An arm predicting nothing
  scores exactly the empty-gold rate, which is a calibration check on the harness in the
  same way `constant` was for classification.

  Types are naturally imbalanced and are left that way -- location 223, organization 165,
  person 164, other 62, event 38, building 34, product 34, art 29 in that sample.
  Rebalancing would make the slice unrepresentative of the task.

DEGENERATE ITEMS ARE FILTERED, AND WHY THAT IS NOT CHERRY-PICKING
  `--min-tokens` (default 3) drops sentences too short to pose the task. The dev slice
  contained one whose entire text was the single character "p".

  It is a real row in Few-NERD's test split, and keeping it would have been defensible on
  faithfulness grounds -- except for what it actually measures. Three of 24 hosted arms
  failed it, and the two that failed WORST were right: llama_l and llama_s replied "You
  didn't provide the sentence." deepseek_s tagged the letter p as an entity and scored
  better for it. An arm that blindly answers `[]` scores 1.0.

  So the item rewards not looking and punishes noticing. That is backwards, and it is a
  different thing from the label noise the classification examples kept -- a mislabelled
  item still poses the task and every arm meets the same question. A one-character
  sentence poses no task at all.

  The filter is declared, its threshold is a flag, and what it removed is printed at the
  end of every fetch. A silent drop would be the cherry-pick.

TWO CAVEATS IN THE DATA ITSELF, BOTH VISIBLE IN THE FIRST THREE SENTENCES
  IO TAGGING. Few-NERD tags with IO rather than BIO, so two adjacent entities of the same
  type merge into one span. Some gold boundaries are therefore wrong by construction, and
  no arm can recover the intended ones.

  ANNOTATION NOISE. `("C-USA play", "event")` includes the trailing word "play". This is
  the same class of problem the classification examples found, and
  `classification_report.py`'s ITEMS THE FIELD MISSED section is the tool for it.

WHY THIS DATASET
  CC BY-SA 4.0, stated on the dataset card -- an actual grant, and the cleanest licence of
  the four corpora in this repo. The usual alternatives do not offer one: CoNLL-2003's
  Reuters text needs a separate agreement, `tner/wnut2017` is licensed `other`, and
  OntoNotes is behind LDC. WNUT would have been closer to podcast-style noisy speech,
  which is the relevance this example gives up to keep the licence clean.

  Nothing is committed regardless: the slice downloads to whoever runs this, and is
  gitignored.

WHY THE REFERENCE IS GOLD
  Few-NERD is expert-annotated, not model-generated. A reference file here holds a JSON
  array of {text, type} objects rather than one word, because the answer to this task is
  a SET.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "harness"
ROWS_API = "https://datasets-server.huggingface.co/rows"
DATASET = "DFKI-SLT/few-nerd"
CONFIG = "supervised"
SPLIT_ROWS = 37648  # `supervised` test split; re-checked at fetch time

#: The dataset's coarse label order. Index IS the stored integer; 0 is "no entity".
COARSE = ["O", "art", "building", "event", "location", "organization", "other",
          "person", "product"]

#: Copied from the DBpedia fetcher, where both were found by an actual failure: one
#: transient 502 lost a whole draw, then HTTP 429 showed the limiter is on request RATE.
_TRANSIENT_STATUS = frozenset({500, 502, 503, 504})
_RATE_LIMIT_BACKOFF = (5, 15, 30, 60, 60, 60)
_MAX_ATTEMPTS = 7
DEFAULT_DELAY = 0.35


def _get(offset: int, length: int, delay: float = DEFAULT_DELAY) -> list[dict]:
    query = urllib.parse.urlencode(
        {"dataset": DATASET, "config": CONFIG, "split": "test",
         "offset": offset, "length": length}
    )
    last = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(f"{ROWS_API}?{query}", timeout=60) as resp:
                rows = [r["row"] for r in (json.loads(resp.read()).get("rows") or [])]
            time.sleep(delay)
            return rows
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code == 429:
                wait = _RATE_LIMIT_BACKOFF[min(attempt - 1, len(_RATE_LIMIT_BACKOFF) - 1)]
            elif exc.code in _TRANSIENT_STATUS:
                wait = min(2 ** attempt, 30)
            else:
                break
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            wait = min(2 ** attempt, 30)
        if attempt < _MAX_ATTEMPTS:
            print(f"      {last} at offset {offset}; retry {attempt}/{_MAX_ATTEMPTS - 1} "
                  f"in {wait}s", flush=True)
            time.sleep(wait)
    sys.exit(f"datasets-server failed at offset {offset} after {_MAX_ATTEMPTS} attempt(s): "
             f"{last}\n  check connectivity, then retry — or raise --delay.")


def entities(tokens: list, tags: list) -> list:
    """Contiguous same-tag runs, as {text, type}.

    IO tagging, so this is all the structure there is: a run ends when the tag changes or
    goes to O. Two adjacent entities of the same type are indistinguishable from one long
    entity, here and in the original data.
    """
    out, cur, cur_tag = [], [], 0
    for tok, tag in zip(tokens, tags):
        tag = int(tag)
        if tag and tag == cur_tag:
            cur.append(tok)
            continue
        if cur:
            out.append({"text": " ".join(cur), "type": COARSE[cur_tag]})
        cur, cur_tag = ([tok], tag) if tag else ([], 0)
    if cur:
        out.append({"text": " ".join(cur), "type": COARSE[cur_tag]})
    return out


def item_id(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:40]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=280, help="sentences to draw (default: 280)")
    ap.add_argument("--dataset-id", default=None, help="harness dataset_id (default: few_nerd_<n>)")
    ap.add_argument("--seed", type=int, default=20260928,
                    help="draw seed; same --n and --seed reproduce the same items")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                    help=f"seconds between requests (default: {DEFAULT_DELAY})")
    ap.add_argument("--min-tokens", type=int, default=3,
                    help="skip sentences shorter than this (default: 3); see DEGENERATE "
                         "ITEMS in the module docstring")
    ap.add_argument("--force", action="store_true", help="overwrite an existing slice")
    args = ap.parse_args()

    dataset_id = args.dataset_id or f"few_nerd_{args.n}"
    sources = ROOT / "data" / "sources" / dataset_id
    golds = ROOT / "data" / "references" / "gold" / dataset_id
    if sources.exists() and not args.force:
        print(f"{sources} already exists — pass --force to refetch")
        return 0

    # ONE permutation, seeded independently of --n, so a smaller slice is a strict PREFIX
    # of a larger one and the two are nested for holdout analysis.
    rng = random.Random(args.seed)
    permutation = list(range(SPLIT_ROWS))
    rng.shuffle(permutation)
    # Walk the permutation until n KEPT items, rather than taking the first n and
    # filtering after: that would silently return fewer than --n asked for, and the two
    # slices would stop being nested.
    rows, skipped, cursor = [], [], 0
    while len(rows) < args.n and cursor < len(permutation):
        off = permutation[cursor]
        cursor += 1
        got = _get(off, 1, args.delay)
        if not got:
            sys.exit(f"no row at offset {off} — the split is smaller than {SPLIT_ROWS}")
        row = got[0]
        if len(row["tokens"]) < args.min_tokens:
            skipped.append(" ".join(row["tokens"]))
            continue
        rows.append(row)
        if len(rows) % 50 == 0:
            print(f"  {len(rows)}/{args.n}", flush=True)
    if len(rows) < args.n:
        sys.exit(f"exhausted the split at {len(rows)} of {args.n} items")

    # CLEAR BEFORE WRITING. --force used to overwrite files and leave orphans, so a
    # refetch that dropped an item left the old copy on disk and dataset-create picked it
    # straight back up: the first filtered run produced 57 items from a 56-item draw, and
    # the one item it re-admitted was exactly the one --min-tokens had just removed.
    # Silent, and it would have poisoned the frozen dataset.
    for directory in (sources, golds):
        if directory.exists():
            for stale in directory.glob("*.txt"):
                stale.unlink()
    sources.mkdir(parents=True, exist_ok=True)
    golds.mkdir(parents=True, exist_ok=True)
    counts: collections.Counter = collections.Counter()
    empty = 0
    for row in rows:
        text = " ".join(row["tokens"])
        ents = entities(row["tokens"], row["ner_tags"])
        counts.update(e["type"] for e in ents)
        empty += not ents
        item = item_id(text)
        (sources / f"{item}.txt").write_text(text, encoding="utf-8")
        # A JSON array, not a word: the answer to this task is a SET. Sorted and
        # separator-normalised so the file is byte-stable for the dataset hash.
        (golds / f"{item}.txt").write_text(
            json.dumps(ents, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    n_ents = sum(counts.values())
    print(f"\n{len(rows)} sentence(s) written, seed {args.seed}")
    print(f"  texts      {sources}")
    print(f"  gold refs  {golds}")
    print(f"  entities   {n_ents} total, {n_ents / len(rows):.2f} per sentence")
    print(f"  types      {dict(counts.most_common())}")
    print(f"  no-entity  {empty} of {len(rows)} sentences ({empty / len(rows):.1%})")
    if skipped:
        print(f"  skipped    {len(skipped)} sentence(s) under --min-tokens "
              f"{args.min_tokens}: {skipped[:5]}")
    print(f"\n  An arm that predicts NOTHING scores about {empty / len(rows):.4f} — that is"
          f" the floor,")
    print("  and a calibration check on the scorer before it is a baseline on the task.")
    print("  ABOUT, not exactly: the scorer's normaliser strips punctuation, so a gold")
    print("  entity that is only punctuation normalises to nothing and its item behaves")
    print("  as empty-gold too. few_nerd_280 has one — Few-NERD tags the bare symbol '£'")
    print("  as an entity, twice, in the same sentence — which moves the floor from")
    print("  0.1214 to 0.1250. `extraction_report.py` prints these; this fetcher is")
    print("  stdlib-only and cannot import the normaliser to count them here.")
    print("\nNext:")
    print(f"  make dataset-create DATASET_ID={dataset_id} ARGS='--source-dir data/sources/{dataset_id}'")
    print(f"  make dataset-materialize DATASET_ID={dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
