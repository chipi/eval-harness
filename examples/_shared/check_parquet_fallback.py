"""The parquet fallback reads the same rows as the datasets-server's /rows: the same fields, values and row
numbers, at the start, the middle and the end of each split the examples fetch (hf_rows.parquet_page).

    uv run --project examples/classification-ag-news python examples/_shared/check_parquet_fallback.py

Needs the network and pyarrow (each example's environment has it). Run by the rerun workflow; exits 1 on any
difference.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hf_rows

CASES = [
    ("fancyzhx/ag_news", "default", "test", [0, 1500, 7590]),
    ("abisee/cnn_dailymail", "3.0.0", "test", [0, 5000, 11480]),
    ("BeIR/scifact", "corpus", "corpus", [0, 3000, 5180]),
    ("BeIR/scifact", "queries", "queries", [0, 600]),
]


def main() -> int:
    bad = 0
    for ds, cfg, split, offsets in CASES:
        for off in offsets:
            a = hf_rows.page(ds, cfg, split, off, 5)
            b = hf_rows.parquet_page(ds, cfg, split, off, 5)
            same = (
                b is not None
                and [dict(r) for r in a] == [dict(r) for r in b]
                and [r.row_idx for r in a] == [r.row_idx for r in b]
            )
            bad += not same
            print(f"{ds} {cfg}/{split} @{off}: {len(a)} rows; parquet {'the same' if same else 'DIFFERENT'}")
    print(f"{bad} difference(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
