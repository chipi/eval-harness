"""Shared plumbing for each example's `calibrate.py`: check the instrument against a
published number, on the protocol that number was measured on.

Every experiment here scores a 200-ish item slice. A calibration row runs ONE known model
or baseline on the benchmark's full test set (or a large seeded sample of it, stated as
such) and compares the result with the value its authors published. It answers the
question no separation test can: is this instrument, on this data, measuring what the
field measures? The summarisation slice's CNN-only bias went unnoticed until one existed.

Stdlib only. Results land in docs/evidence/calibration/<experiment>.json, which
check_report_claims reads, so a calibration figure quoted in a report cannot drift.
"""

from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "docs" / "evidence" / "calibration"
ROWS_API = "https://datasets-server.huggingface.co/rows"


def page(dataset: str, config: str, split: str, offset: int, length: int = 100) -> list:
    """One page of rows from the HF datasets-server, retried on transient errors."""
    q = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": split,
                                "offset": offset, "length": length})
    last: Optional[Exception] = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(f"{ROWS_API}?{q}", timeout=60) as r:
                return [x["row"] for x in (json.loads(r.read()).get("rows") or [])]
        except Exception as exc:  # noqa: BLE001 - retried, then raised
            last = exc
            time.sleep(2 * (attempt + 1))
    raise SystemExit(f"datasets-server unreachable at offset {offset}: {last}")


def rows(dataset: str, config: str, split: str, limit: Optional[int] = None) -> list:
    """Every row of a split (or the first `limit`), paged."""
    out: list = []
    while limit is None or len(out) < limit:
        got = page(dataset, config, split, len(out))
        if not got:
            break
        out.extend(got)
    return out[:limit] if limit else out


def proportion(hits: int, n: int) -> dict:
    """A proportion with its normal-approximation 95% half-width, rounded for reading."""
    p = hits / n if n else float("nan")
    return {"n": n, "value": round(p, 4),
            "ci95": round(1.96 * math.sqrt(p * (1 - p) / n), 4) if n else None}


def verdict(measured: float, ci95: float, published: float, tolerance: float) -> str:
    """'consistent' when the published value is within our CI plus a stated tolerance
    for protocol differences; otherwise 'differs', which is a finding, not a failure."""
    return "consistent" if abs(measured - published) <= ci95 + tolerance else "differs"


def write(experiment: str, result: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{experiment}.json"
    path.write_text(json.dumps(result, indent=2) + "\n")
    return path


def accuracy(predict: Callable[[str], str], items: list, text_key: str, gold: Callable) -> dict:
    hits = sum(predict(r[text_key]).strip() == gold(r) for r in items)
    return proportion(hits, len(items))
