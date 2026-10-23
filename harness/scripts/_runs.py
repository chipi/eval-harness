"""Reading runs: which runs are on a dataset, and what each scored per item.

Every command that reads runs used to walk the runs directory itself, about fifteen times,
with different filters and orderings: some sorted and some not, some fell back to the
directory name for a missing config_id, one crashed on a malformed line where another
skipped it, one counted a boolean as 1.0 where another dropped it. The inspector's p
agreed with pair-test's because the committed data is clean, not because the code was
shared. It is now: every reader goes through these functions.

    runs = runs_on("ag_news_200", match="_v2")            # [(run dir, metrics.json)], sorted
    M = matrix(runs, "accuracy")                           # config_id -> item_id -> mean
    lower = lower_is_better_on(runs, "wer")                # the direction the runs declare
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Iterable, Iterator
from pathlib import Path

from _common import RUNS, lower_is_better

Run = tuple[Path, dict]


def read_metrics(run_dir: Path) -> dict | None:
    """A run's metrics.json, or None when it is missing, unreadable or not an object."""
    mj = run_dir / "metrics.json"
    try:
        m = json.loads(mj.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m if isinstance(m, dict) else None


def runs_on(
    dataset_id: str | None = None,
    *,
    runs_dir: Path | None = None,
    match: str | None = None,
    config_id: str | None = None,
) -> list[Run]:
    """Every run in `runs_dir` (default: the runs directory) with a readable metrics.json and
    a config_id, in directory-name order; optionally only one dataset, config_ids containing
    `match`, or exactly `config_id`."""
    base = runs_dir or RUNS
    out: list[Run] = []
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        m = read_metrics(d) if d.is_dir() else None
        if m is None or not m.get("config_id"):
            continue
        if dataset_id is not None and m.get("dataset_id") != dataset_id:
            continue
        if match and match not in m["config_id"]:
            continue
        if config_id is not None and m["config_id"] != config_id:
            continue
        out.append((d, m))
    return out


def by_arm(runs: Iterable[Run]) -> dict[str, list[Run]]:
    """config_id -> its runs (repeats, or anything else sharing the id), in sorted order."""
    out: dict[str, list[Run]] = {}
    for d, m in runs:
        out.setdefault(m["config_id"], []).append((d, m))
    return dict(sorted(out.items()))


def item_rows(run_dir: Path, strict: bool = True) -> Iterator[dict]:
    """The rows of a run's predictions.jsonl that name an item. A malformed line raises
    (naming the file and line) unless `strict` is False, when it is skipped: a statistical
    test must not quietly drop an item, a page that shows a run may."""
    pj = run_dir / "predictions.jsonl"
    if not pj.is_file():
        return
    for n, line in enumerate(
        pj.read_text(encoding="utf-8", errors="strict" if strict else "replace").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            if strict:
                raise ValueError(f"{pj}:{n}: not JSON ({exc})") from exc
            continue
        if isinstance(row, dict) and "item_id" in row:
            yield row


def score_of(row: dict, metric: str) -> float | None:
    """The row's value for `metric` when it is a number; a boolean is not a score."""
    v = row.get(metric)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def per_item(
    runs: Iterable[Run],
    metric: str,
    *,
    keep: set[str] | None = None,
    raw: list[float] | None = None,
    strict: bool = True,
) -> dict[str, float]:
    """item_id -> the mean of `metric` over the given runs (an arm's repeats). `keep`
    restricts the items; `raw` collects every value as stored, before averaging (the
    leaderboard measures stored precision on it)."""
    acc: dict[str, list[float]] = {}
    for d, _m in runs:
        for row in item_rows(d, strict=strict):
            v = score_of(row, metric)
            if v is None or (keep is not None and row["item_id"] not in keep):
                continue
            acc.setdefault(row["item_id"], []).append(v)
            if raw is not None:
                raw.append(v)
    return {i: statistics.fmean(v) for i, v in acc.items() if v}


def matrix(
    runs: Iterable[Run], metric: str, *, keep: set[str] | None = None, raw: list[float] | None = None
) -> dict[str, dict[str, float]]:
    """config_id -> item_id -> mean `metric`; arms with no value for it are left out."""
    out = {cid: per_item(rs, metric, keep=keep, raw=raw) for cid, rs in by_arm(runs).items()}
    return {cid: items for cid, items in out.items() if items}


def lower_is_better_on(runs: Iterable[Run], metric: str) -> bool:
    """Whether a decrease in `metric` is an improvement: a cost, speed or token count, or a
    primary metric the runs declare ascending (`import-run --asc` records
    `primary_metric_asc`, which nothing read before)."""
    if lower_is_better(metric):
        return True
    return any(m.get("primary_metric") == metric and m.get("primary_metric_asc") for _d, m in runs)


def direction(runs: Iterable[Run], metric: str, asc: bool = False, desc: bool = False) -> bool:
    """True when lower is better for `metric` on these runs: `asc` / `desc` when the caller
    passed one, else what `lower_is_better_on` reads from the metric and the runs. Every
    command that counts wins or ranks arms asks this, so "A wins 180/200" on latency means
    A was faster without anyone remembering --asc."""
    if asc and desc:
        raise SystemExit("ERROR: --asc and --desc contradict each other")
    if asc or desc:
        return asc
    return lower_is_better_on(runs, metric)
