"""One page of rows from the Hugging Face datasets-server, the way every fetcher here needs it.

    from hf_rows import page
    rows = page("fancyzhx/ag_news", "default", "test", offset=0, length=100)

Each example's fetch.py used to carry its own loop, on three different retry schedules. Two of
them treated an HTTP 429 like any glitch, retried for ~40 s and gave up: the DailyMail slice's
random draw (~115 pages back to back) failed that way for a night. The schedule here is the one
the DBpedia fetcher arrived at after losing whole draws to it:

- requests are paced (DEFAULT_DELAY): the limiter is on request RATE, not volume;
- a 429 waits on RATE_LIMIT_BACKOFF, long enough for a limit already tripped;
- a 5xx, a timeout or a reset backs off 2, 4, 8 ... 30 s;
- any other 4xx stops at once: it will not fix itself.

Fetching is not scoring: the bytes it returns are pinned by each dataset's hashes afterwards.

Each row remembers where it came from (`row.row_idx`, the split's own row number) without that
changing its content: a `Row` is a dict, and serialises as one. `Sources` collects the item ids a
fetcher writes with their rows and writes `data/sources/<dataset_id>.rows.json`, from which
`evh dataset-profile` links each item to its row in the Hugging Face dataset viewer. The text
stays at the source; only row numbers are recorded.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROWS_API = "https://datasets-server.huggingface.co/rows"
TRANSIENT_STATUS = frozenset({500, 502, 503, 504})
RATE_LIMIT_BACKOFF = (5, 15, 30, 60, 60, 60)
MAX_ATTEMPTS = 7
DEFAULT_DELAY = 0.35
VIEWER = "https://huggingface.co/datasets/{dataset}/viewer/{config}/{split}?row={row}"


class Row(dict):
    """One row of a split, with its row number in that split."""

    row_idx: int | None = None


class Sources:
    """Where each written item came from: `record(item_id, row)` as each item is written, then
    `write(harness_root, dataset_id)`. Fetchers that write several items from one row (none
    today) record each."""

    def __init__(self, dataset: str, config: str, split: str):
        self.dataset, self.config, self.split = dataset, config, split
        self.rows: dict[str, int] = {}

    def record(self, item_id: str, row: dict) -> None:
        idx = getattr(row, "row_idx", None)
        if idx is not None:
            self.rows[item_id] = idx

    def write(self, harness_root, dataset_id: str) -> None:
        """Each row with the sha256 of the file written for it (data/sources/<dataset_id>/<item>.txt),
        which is what a dataset freezes: a profile links an item only when the bytes match, so an
        item id that recurs in another dataset never borrows this one's row."""
        src = harness_root / "data" / "sources" / dataset_id
        rows = {}
        for item, idx in sorted(self.rows.items()):
            f = src / f"{item}.txt"
            if f.is_file():
                rows[item] = {"row": idx, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
        doc = {
            "source": {
                "name": self.dataset,
                "url": f"https://huggingface.co/datasets/{self.dataset}",
                "config": self.config,
                "split": self.split,
            },
            "item_url": VIEWER.format(
                dataset=self.dataset, config=self.config, split=self.split, row="{row}"
            ),
            "rows": rows,
        }
        out = harness_root / "data" / "sources" / f"{dataset_id}.rows.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")


def page(
    dataset: str,
    config: str,
    split: str,
    offset: int,
    length: int,
    *,
    delay: float = DEFAULT_DELAY,
    timeout: float = 60,
) -> list[dict]:
    """Rows [offset, offset + length) of one split ([] past its end). Exits with one message,
    naming the offset, when the server keeps refusing."""
    query = urllib.parse.urlencode(
        {"dataset": dataset, "config": config, "split": split, "offset": offset, "length": length}
    )
    last = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(f"{ROWS_API}?{query}", timeout=timeout) as resp:  # noqa: S310 — a constant https URL  # nosec B310
                rows = []
                for r in json.loads(resp.read()).get("rows") or []:
                    row = Row(r["row"])
                    row.row_idx = r.get("row_idx")
                    rows.append(row)
            time.sleep(delay)
            return rows
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code == 429:
                wait = RATE_LIMIT_BACKOFF[min(attempt - 1, len(RATE_LIMIT_BACKOFF) - 1)]
            elif exc.code in TRANSIENT_STATUS:
                wait = min(2**attempt, 30)
            else:
                break
        except Exception as exc:  # noqa: BLE001 - timeouts, resets, DNS
            last = f"{type(exc).__name__}: {exc}"
            wait = min(2**attempt, 30)
        if attempt < MAX_ATTEMPTS:
            print(
                f"      {last} at offset {offset}; retry {attempt}/{MAX_ATTEMPTS - 1} in {wait}s", flush=True
            )
            time.sleep(wait)
    sys.exit(
        f"datasets-server failed at offset {offset} of {dataset} after {MAX_ATTEMPTS} attempt(s): {last}\n"
        "  it is an HTTPS API; check connectivity, then retry."
    )
