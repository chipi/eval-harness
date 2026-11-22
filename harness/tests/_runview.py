"""A test project's runs and scores, read back in the format 4 layout (RFC-032 step 4): the record of a run's first
score, a run's scores with their labels, a score's rows. Every read is made inside the project (`_runstore`), whatever
this process's own project is."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import _runstore
from evaluation_harness.model import runs as R


def run_id(proj: Path | str, prefix: str) -> str:
    """The id of the first run whose id starts with `prefix`."""
    return next(n for n in _runstore.listdir(proj, "runs") if n.startswith(prefix))


def record_of(proj: Path | str, prefix: str) -> tuple[str, dict[str, Any]]:
    """(run id, the record of the score the run made when it ran) of the first run whose id starts with `prefix`."""
    with _runstore._InProject(proj):
        rid = next(n for n in R.run_ids() if n.startswith(prefix))
        first = R.first_score(rid)
        return rid, (R.record(first) if first else None) or {}


def scores_of(proj: Path | str, rid: str) -> list[tuple[str, str, dict[str, Any]]]:
    """[(key, label as it is read, record)] for each score of the run, by key."""
    with _runstore._InProject(proj):
        return [(sd.name, R.label(sd), R.record(sd) or {}) for sd in R.scores_of(rid)]


def labelled(proj: Path | str, rid: str, label: str) -> list[tuple[str, dict[str, Any]]]:
    """[(key, record)] of the run's scores read under `label` (the label of the run's purpose included)."""
    return [(k, rec) for k, lb, rec in scores_of(proj, rid) if lb == label]


def rows_of(proj: Path | str, rid: str, key: str | None = None) -> list[dict[str, Any]]:
    """The rows of a run's score (its first when no key is given), each line parsed."""
    with _runstore._InProject(proj):
        sd = R.run_dir(rid) / "scores" / key if key else R.first_score(rid)
        return _runstore.rows(sd) if sd else []
