"""The harness's huggingface source reads the same rows as the datasets-server's /rows: the same fields, values and
row numbers, at the start, the middle and the end of every split the examples fetch (hf_rows.page).

    uv run --project examples/classification-ag-news python examples/_shared/check_hf_source.py

Needs the network and pyarrow (each example's environment has it). Run by the rerun workflow; exits 1 on any
difference. /rows is read here only to compare: the fetchers no longer use it.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hf_rows

ROWS_API = "https://datasets-server.huggingface.co/rows"
#: Every split a fetcher reads, at the start, the middle and near the end.
CASES = [
    ("fancyzhx/ag_news", "default", "test", [0, 3800, 7590]),
    ("abisee/cnn_dailymail", "1.0.0", "test", [0, 5000, 11480]),
    ("fancyzhx/dbpedia_14", "dbpedia_14", "test", [0, 35000, 69990]),
    ("DFKI-SLT/few-nerd", "supervised", "test", [0, 18000, 37640]),
    ("BeIR/scifact", "corpus", "corpus", [0, 3000, 5180]),
    ("BeIR/scifact", "queries", "queries", [0, 600]),
    ("BeIR/scifact-qrels", "default", "test", [0, 330]),
    ("mteb/summeval", "default", "test", [0, 95]),
]


def rows_api(ds: str, cfg: str, split: str, offset: int, length: int) -> list[tuple[int, dict]]:
    """(row number, row) from /rows, retried a few times on a transient failure."""
    q = urllib.parse.urlencode(
        {"dataset": ds, "config": cfg, "split": split, "offset": offset, "length": length}
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"{ROWS_API}?{q}", timeout=60) as resp:  # noqa: S310 — a constant https URL  # nosec B310
                return [(r["row_idx"], r["row"]) for r in json.loads(resp.read()).get("rows") or []]
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    return []


def main() -> int:
    bad = 0
    for ds, cfg, split, offsets in CASES:
        for off in offsets:
            a = [(r.row_idx, dict(r)) for r in hf_rows.page(ds, cfg, split, off, 5)]
            b = rows_api(ds, cfg, split, off, 5)
            same = a == b
            bad += not same
            print(
                f"{ds} {cfg}/{split} @{off}: {len(a)} rows at {hf_rows.revision(ds, cfg, split)[:12]}; /rows {'the same' if same else 'DIFFERENT'}"
            )
    print(f"{bad} difference(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
