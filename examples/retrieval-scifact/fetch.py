#!/usr/bin/env python3
"""Download BEIR SciFact — a query slice, its qrels, and the WHOLE corpus.

    python examples/retrieval-scifact/fetch.py --n 200

STDLIB ONLY, like the other three fetchers: the HuggingFace datasets-server rows API.

THIS FETCHER WRITES THREE THINGS, AND THE THIRD IS NEW
  The other examples write items and references. Retrieval needs a third: the documents
  an arm searches. It is the same for every item and every arm, and no arm is scored on
  it, so it is not an item — see `harness/data/corpora/README.md` for why it does not
  belong in sources/, references/ or materialized/ either.

      data/sources/scifact_<n>/<qid>.txt            the query text
      data/references/gold/scifact_<n>/<qid>.txt    JSON [{doc_id, score}] — the qrels
      data/corpora/scifact/corpus.jsonl             all 5,183 abstracts, ALWAYS all of them

THE CORPUS IS NEVER SLICED, AND THAT IS NOT AN OVERSIGHT
  `--n` slices the QUERIES. The corpus stays at 5,183 documents whatever `--n` says.

  Sampling it would be the single most damaging shortcut available here. Retrieval
  difficulty is a property of the haystack: drop 90% of the documents and every arm's
  nDCG rises, because most of what it could have wrongly ranked above the answer is gone.
  A 200-query run and a 40-query run over the same corpus are comparable; over different
  corpora they are two different tasks wearing one name.

  It also means the dev slice is genuinely cheap in the only dimension that costs money
  (queries) and free in the one that costs time (indexing, which `warmup()` pays once).

WHY THE SLICE IS A SEEDED PREFIX
  Same reason as the other three: `--n 40` takes a prefix of the same permutation `--n 200`
  does, so the two are NESTED and `holdout_significance --exclude-dataset` can ask whether
  the dev slice's winner survives on queries it never saw.

WHAT THE DATA LOOKS LIKE
  SciFact is scientific claim verification repurposed as retrieval: the query is a claim
  ("0-dimensional biomaterials lack inductive properties"), and the relevant documents are
  the abstracts that support or refute it. 300 test queries, 339 relevance judgments — so
  most queries have exactly one relevant document and a few have two or three.

  RELEVANCE IS BINARY. Every qrels score in this split is 1. nDCG's graded machinery
  therefore collapses to "is the relevant document near the top", and `score` is carried
  through anyway so the scorer does not silently assume binary on the next corpus.

  THE ONE-RELEVANT-DOC MAJORITY IS WHY Recall@k IS REPORTED BESIDE nDCG@10. With a single
  relevant document, nDCG@10 takes one of eleven values and is a disguised reciprocal
  rank. Recall@100 asks the different question a two-stage pipeline actually cares about:
  did the first stage put the answer anywhere the reranker could reach it.

WHY THIS DATASET
  CC BY-SA 4.0, and small enough that every arm can index the full corpus on a laptop CPU
  in under a minute — which is what makes an honest `warmup_ms` column possible. The
  larger BEIR sets (MS MARCO, HotpotQA) would need a vector database and would turn this
  example into an infrastructure exercise.

  Nothing is committed: the slice and the corpus download to whoever runs this, and both
  are gitignored.
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
DATASET = "BeIR/scifact"
QRELS = "BeIR/scifact-qrels"
CORPUS_ID = "scifact"
N_CORPUS = 5183  # re-checked at fetch time
PAGE = 100       # the rows API's maximum

_TRANSIENT_STATUS = frozenset({500, 502, 503, 504})
_RATE_LIMIT_BACKOFF = (5, 15, 30, 60, 60, 60)
_MAX_ATTEMPTS = 7
DEFAULT_DELAY = 0.35


def _get(dataset: str, config: str, split: str, offset: int, length: int,
         delay: float = DEFAULT_DELAY) -> list[dict]:
    query = urllib.parse.urlencode(
        {"dataset": dataset, "config": config, "split": split,
         "offset": offset, "length": length})
    last = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(f"{ROWS_API}?{query}", timeout=90) as resp:
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
            print(f"      {last} at {config}/{split}+{offset}; "
                  f"retry {attempt}/{_MAX_ATTEMPTS - 1} in {wait}s", flush=True)
            time.sleep(wait)
    sys.exit(f"datasets-server failed on {dataset} {config}/{split} at offset {offset} "
             f"after {_MAX_ATTEMPTS} attempt(s): {last}")


def _page_all(dataset: str, config: str, split: str, delay: float, label: str) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while True:
        batch = _get(dataset, config, split, offset, PAGE, delay)
        if not batch:
            break
        out.extend(batch)
        offset += len(batch)
        if offset % 1000 == 0 or len(batch) < PAGE:
            print(f"  {label}: {len(out)}", flush=True)
        if len(batch) < PAGE:
            break
    return out


def corpus_sha256(docs: list[dict]) -> str:
    """Hash of the corpus CONTENT, order-independent.

    Computed over doc_id + title + text of every document, sorted by doc_id — not over
    the file. Re-downloading in a different page order must produce the same hash, and a
    corpus that differs by one word must not.
    """
    h = hashlib.sha256()
    for d in sorted(docs, key=lambda x: x["doc_id"]):
        h.update(d["doc_id"].encode())
        h.update(b"\x00")
        h.update(d["title"].encode())
        h.update(b"\x00")
        h.update(d["text"].encode())
        h.update(b"\x1e")
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=200, help="QUERIES to draw (default: 200)")
    ap.add_argument("--dataset-id", default=None, help="default: scifact_<n>")
    ap.add_argument("--seed", type=int, default=20260928,
                    help="draw seed; same --n and --seed reproduce the same queries")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY)
    ap.add_argument("--force", action="store_true", help="overwrite an existing slice")
    ap.add_argument("--skip-corpus", action="store_true",
                    help="queries only; the corpus is already downloaded and unchanged")
    args = ap.parse_args()

    dataset_id = args.dataset_id or f"scifact_{args.n}"
    sources = ROOT / "data" / "sources" / dataset_id
    golds = ROOT / "data" / "references" / "gold" / dataset_id
    corpus_dir = ROOT / "data" / "corpora" / CORPUS_ID
    if sources.exists() and not args.force:
        print(f"{sources} already exists — pass --force to refetch")
        return 0

    # ── the corpus, always in full ───────────────────────────────────────────
    corpus_file = corpus_dir / "corpus.jsonl"
    if args.skip_corpus and corpus_file.is_file():
        docs = [json.loads(l) for l in corpus_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"corpus: reusing {len(docs)} document(s) already on disk")
    else:
        print(f"corpus: downloading all {N_CORPUS} documents (~52 requests)")
        raw = _page_all(DATASET, "corpus", "corpus", args.delay, "corpus")
        docs = [{"doc_id": str(r["_id"]), "title": r.get("title") or "",
                 "text": r.get("text") or ""} for r in raw]
        if len(docs) != N_CORPUS:
            print(f"  NOTE: got {len(docs)} documents, expected {N_CORPUS} — the split "
                  f"has changed upstream. The hash below records what was ACTUALLY used.")
        corpus_dir.mkdir(parents=True, exist_ok=True)
        # Sorted on disk so the file is byte-stable, though the hash does not depend on it.
        with corpus_file.open("w", encoding="utf-8") as fh:
            for d in sorted(docs, key=lambda x: x["doc_id"]):
                fh.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")

    csha = corpus_sha256(docs)
    (corpus_dir / "manifest.json").write_text(json.dumps({
        "corpus_id": CORPUS_ID,
        "n_docs": len(docs),
        "corpus_sha256": csha,
        "source": {"dataset": DATASET, "config": "corpus", "split": "corpus"},
        "licence": "CC BY-SA 4.0",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  corpus_sha256 {csha[:16]}  ({len(docs)} docs)")

    # ── qrels define the test set, so they come before the queries ───────────
    print("qrels: downloading the test judgments")
    qrels_rows = _page_all(QRELS, "default", "test", args.delay, "qrels")
    rel: dict = collections.defaultdict(list)
    for r in qrels_rows:
        rel[str(r["query-id"])].append(
            {"doc_id": str(r["corpus-id"]), "score": int(r["score"])})
    print(f"  {len(qrels_rows)} judgment(s) over {len(rel)} query/queries")

    print("queries: downloading")
    q_rows = _page_all(DATASET, "queries", "queries", args.delay, "queries")
    text_of = {str(r["_id"]): (r.get("text") or "").strip() for r in q_rows}
    test_ids = sorted(qid for qid in rel if text_of.get(qid))
    missing = [qid for qid in rel if not text_of.get(qid)]
    if missing:
        print(f"  WARNING: {len(missing)} judged query id(s) have no text and are dropped")
    print(f"  {len(test_ids)} test query/queries have both text and judgments")

    if args.n > len(test_ids):
        sys.exit(f"--n {args.n} exceeds the {len(test_ids)} available test queries")

    # ONE permutation, seeded independently of --n, so a smaller slice is a strict PREFIX.
    rng = random.Random(args.seed)
    permutation = list(test_ids)
    rng.shuffle(permutation)
    chosen = permutation[:args.n]

    # Clear before writing — a --force that overwrites and leaves orphans re-admits items
    # a later filter removed. The NER fetcher lost a day to exactly that.
    for directory in (sources, golds):
        if directory.exists():
            for stale in directory.glob("*.txt"):
                stale.unlink()
    sources.mkdir(parents=True, exist_ok=True)
    golds.mkdir(parents=True, exist_ok=True)

    n_rel = collections.Counter()
    for qid in chosen:
        (sources / f"{qid}.txt").write_text(text_of[qid], encoding="utf-8")
        judged = sorted(rel[qid], key=lambda d: d["doc_id"])
        (golds / f"{qid}.txt").write_text(
            json.dumps(judged, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        n_rel[len(judged)] += 1

    in_corpus = {d["doc_id"] for d in docs}
    dangling = sum(1 for qid in chosen for d in rel[qid] if d["doc_id"] not in in_corpus)

    print(f"\n{len(chosen)} query/queries written, seed {args.seed}")
    print(f"  queries    {sources}")
    print(f"  qrels      {golds}")
    print(f"  corpus     {corpus_file}  ({len(docs)} docs, NOT sliced)")
    print(f"  relevant docs per query: {dict(sorted(n_rel.items()))}")
    grades = {d["score"] for qid in chosen for d in rel[qid]}
    print(f"  relevance grades present: {sorted(grades)}"
          f"{'  (binary)' if grades == {1} else '  (GRADED — nDCG is doing real work)'}")
    if dangling:
        print(f"  WARNING: {dangling} judged document(s) are not in the corpus — those are "
              f"unreachable and cap every arm's recall.")
    else:
        print("  every judged document is present in the corpus: recall@all = 1.0 is reachable")
    print("\nNext:")
    print(f"  make dataset-create DATASET_ID={dataset_id} ARGS='--source-dir data/sources/{dataset_id}'")
    print(f"  make dataset-materialize DATASET_ID={dataset_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
