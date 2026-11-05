"""One page of rows of a Hugging Face Hub split, the way every fetcher here needs it, through the harness's
`huggingface` source (PLAN_0.8.0 P4).

    from hf_rows import page
    rows = page("fancyzhx/ag_news", "default", "test", offset=0, length=100)

The rows come from the Hub's parquet conversion of the split at one commit, the files the datasets-server itself
reads them from: the source pins the commit once a process, fetches each file once and checks it against the sha256
the Hub lists, so every page of one fetch reads the same bytes, and the datasets-server's `/rows` (whose outage of
2026-11-02 held back a release) is not needed. The row numbers are the split's own. Whatever is written is still
checked against the frozen dataset's hashes.

Each row remembers where it came from (`row.row_idx`, the split's own row number) without that changing its
content: a `Row` is a dict, and serialises as one. `Sources` collects the item ids a fetcher writes with their rows
and writes `data/sources/<dataset_id>.rows.json` (the source block, with the commit read as its revision), which
`evh dataset-create` reads into the dataset record. The text stays at the source; only row numbers are recorded.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness"))  # the harness's own package
from evaluation_harness.sources import huggingface as _hf

VIEWER = "https://huggingface.co/datasets/{dataset}/viewer/{config}/{split}?row={row}"
#: (dataset, config, split) -> the parquet conversion's commit read, pinned for the process.
_REVISIONS: dict[tuple[str, str, str], str] = {}


class Row(dict):
    """One row of a split, with its row number in that split."""

    row_idx: int | None = None


def revision(dataset: str, config: str, split: str) -> str:
    """The commit of the Hub's parquet conversion this process reads the split at (pinned on first use)."""
    key = (dataset, config, split)
    if key not in _REVISIONS:
        try:
            _REVISIONS[key] = _hf.Source({})._revision(dataset, {})
        except ValueError as e:
            sys.exit(f"{dataset} {config}/{split}: {e}")
    return _REVISIONS[key]


def page(dataset: str, config: str, split: str, offset: int, length: int) -> list[Row]:
    """Rows [offset, offset + length) of one split ([] past its end), each with its row number. Exits with one
    message, naming the offset, when the Hub cannot be read."""
    query = {
        "ref": dataset,
        "config": config,
        "split": split,
        "offset": offset,
        "limit": length,
        "revision": revision(dataset, config, split),
    }
    out = []
    try:
        for n, r in _hf.Source({}).rows(query):
            row = Row(r)
            row.row_idx = n
            out.append(row)
    except ValueError as e:
        sys.exit(f"{dataset} {config}/{split} at offset {offset}: {e}")
    return out


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
        which is what a dataset freezes: an item gets its row only when the bytes match, so an
        item id that recurs in another dataset never borrows this one's row."""
        src = harness_root / "data" / "sources" / dataset_id
        rows = {}
        for item, idx in sorted(self.rows.items()):
            f = src / f"{item}.txt"
            if f.is_file():
                rows[item] = {"row": idx, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
        doc = {
            # The harness's source block (E1): the commit read is the revision; gated and the description's
            # sha256 are not read here: null.
            "source": {
                "provider": "huggingface",
                "ref": self.dataset,
                "url": f"https://huggingface.co/datasets/{self.dataset}",
                "revision": _REVISIONS.get((self.dataset, self.config, self.split)),
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
