"""Run fixtures in the format 4 layout (RFC-032 step 4): a run, and a score of it, written into a test project's data/.

    _runfix.put_run(proj / "data", {"run_id": "a_1", "config_id": "a", "dataset_id": "ds", "scores": {"acc": 0.5}}, rows)

`rec` is a run's whole record as `model.runs.record` reads it back: what belongs to the pass goes to run.json, what the
score measured (model.runs.SCORE_KEYS) to the score's metrics.json, its rows to the score's predictions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import _runstore
from evaluation_harness import _store
from evaluation_harness.model import runs as R


def _put_run(
    data: Path,
    rec: dict[str, Any],
    rows: str | list[dict[str, Any]] | None = None,
    *,
    purpose: str = "run",
    label: str = "",
    scorer: str = "0" * 12,
    reference: str | None = None,
    first: bool = True,
    machine: str | None = None,
) -> Path:
    """A run (when it is not there yet) with one score of it, in `data`; the score's directory. `rows` is the score's
    rows, as text or as dicts."""
    rec = dict(rec)
    run_id = rec["run_id"]
    rd = Path(data) / "runs" / run_id
    if not _store.is_file(rd / R.RUN):
        run_rec = R.run_part(rec)
        run_rec["purpose"] = purpose
        if machine:
            run_rec["machine"] = machine
        _store.mkdir(rd, parents=True, exist_ok=True)
        _store.write_text(rd / R.RUN, json.dumps(run_rec, indent=2) + "\n")
    key = R.key(scorer, reference)
    sd = rd / "scores" / key
    _store.mkdir(sd, parents=True, exist_ok=True)
    meta: dict[str, Any] = {"scorer": scorer, "reference": reference, "label": label}
    if first:
        meta["first"] = True
    _store.write_text(sd / R.SCORE, json.dumps(meta, indent=2) + "\n")
    _store.write_text(
        sd / R.METRICS, json.dumps({k: v for k, v in rec.items() if k in R.SCORE_KEYS}, indent=2) + "\n"
    )
    if rows is not None:
        if not isinstance(rows, str):
            rows = "".join(json.dumps(r) + "\n" for r in rows)
        _runstore.put_rows_text(sd, rows)
    return sd


def put_run(
    data: Path, rec: dict[str, Any], rows: str | list[dict[str, Any]] | None = None, **kw: Any
) -> Path:
    """`_put_run` in the test project `data` is the data of, in the store the suite runs in (its database in the
    sqlite store, not this process's project's)."""
    with _runstore._InProject(Path(data).parent):
        return _put_run(data, rec, rows, **kw)
