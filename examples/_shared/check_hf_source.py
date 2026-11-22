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
import urllib.error
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


#: Seconds slept before each retry: seven tries, about two minutes in all.
BACKOFF = (5, 10, 15, 20, 25, 45)


class RowsUnavailable(Exception):
    """/rows did not answer: its message is the one line the job ends in."""


def rows_api(
    ds: str, cfg: str, split: str, offset: int, length: int, sleep=time.sleep
) -> list[tuple[int, dict]]:
    """(row number, row) from /rows. A 5xx, a refused or reset connection and a timeout are retried with a bounded
    backoff, each retry on stderr; a 4xx is the request's own fault and fails at once."""
    q = urllib.parse.urlencode(
        {"dataset": ds, "config": cfg, "split": split, "offset": offset, "length": length}
    )
    tries = len(BACKOFF) + 1
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(f"{ROWS_API}?{q}", timeout=60) as resp:  # noqa: S310 — a constant https URL  # nosec B310
                return [(r["row_idx"], r["row"]) for r in json.loads(resp.read()).get("rows") or []]
        except urllib.error.HTTPError as e:
            code: object = e.code
            if e.code < 500:
                raise RowsUnavailable(
                    f"datasets-server /rows unavailable ({code}) after {attempt} tries: not a difference"
                ) from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            code = type(e.reason if isinstance(e, urllib.error.URLError) else e).__name__
        if attempt == tries:
            raise RowsUnavailable(
                f"datasets-server /rows unavailable ({code}) after {attempt} tries: not a difference"
            )
        print(
            f"/rows {code}, attempt {attempt} of {tries}: retrying in {BACKOFF[attempt - 1]} s",
            file=sys.stderr,
        )
        sleep(BACKOFF[attempt - 1])
    return []


def main() -> int:
    bad = 0
    for ds, cfg, split, offsets in CASES:
        for off in offsets:
            a = [(r.row_idx, dict(r)) for r in hf_rows.page(ds, cfg, split, off, 5)]
            try:
                b = rows_api(ds, cfg, split, off, 5)
            except RowsUnavailable as e:
                print(e, file=sys.stderr)
                return 1
            same = a == b
            bad += not same
            print(
                f"{ds} {cfg}/{split} @{off}: {len(a)} rows at {hf_rows.revision(ds, cfg, split)[:12]}; /rows {'the same' if same else 'DIFFERENT'}"
            )
    print(f"{bad} difference(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
