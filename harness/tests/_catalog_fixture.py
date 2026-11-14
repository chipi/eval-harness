"""A run and its scores as the catalog tests write them: data/runs/<run_id>/run.json, each score under scores/<key>/.

`put` is what a test that wrote `<folder>/<run_id>/metrics.json` calls: the full record, the label it is read under
("" for a pass's own score, "silver", "rescored cd35dc1f", "judged/sc1"), the purpose of the pass. A second call for
one run id adds a score to it, as a re-score does; the run's own facts are written once, by the first.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import _runstore
from evaluation_harness import _outputs, _store
from evaluation_harness.model import runs as model_runs


def runs_in(data: Path | str) -> Path:
    """The directory of runs of a test project's data directory."""
    return Path(data) / "runs"


def put(
    data: Path | str,
    run_id: str,
    rec: dict[str, Any],
    rows_text: str | None = None,
    *,
    label: str = "",
    purpose: str = "run",
    scorer: str | None = None,
    reference: str | None = None,
    first: bool | None = None,
    outputs: dict[str, str] | None = None,
) -> Path:
    """Write `rec` as a score of run `run_id` read under `label`; returns the score's directory. The run's record
    (run.json) is the first call's `rec` less what a score measured; `outputs` ({item: text}) go to a new run."""
    rd = runs_in(data) / run_id
    run_json = rd / model_runs.RUN
    if not _store.is_file(run_json):
        _store.mkdir(rd, parents=True, exist_ok=True)
        run_rec = {
            **model_runs.run_part(rec),
            "run_id": run_id,
            "purpose": purpose,
            "machine": model_runs.machine_of(rec.get("fingerprint")),
        }
        _store.write_text(run_json, json.dumps(run_rec, indent=2) + "\n")
        for item, text in (outputs or {}).items():
            _outputs.writer(rd).add(item, text)
    run_rec = json.loads(_store.read_text(run_json, encoding="utf-8"))
    scorer = scorer or (re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "base")
    ref = (
        reference
        if reference is not None
        else ((rec.get("fingerprint") or {}).get("data") or {}).get("reference_id")
    )
    sd = rd / "scores" / model_runs.key(scorer, ref)
    _store.mkdir(sd, parents=True, exist_ok=True)
    full = {**rec, "run_id": run_id}
    own, unset = model_runs.split(full, run_rec)
    meta: dict[str, Any] = {"scorer": scorer, "reference": ref, "label": label}
    if first if first is not None else not label:
        meta["first"] = True
    if unset:
        meta["unset"] = unset
    _store.write_text(sd / model_runs.SCORE, json.dumps(meta, indent=2) + "\n")
    _store.write_text(sd / model_runs.METRICS, json.dumps(own, indent=2) + "\n")
    if rows_text is not None:
        _runstore.put_rows_text(sd, rows_text)
    return sd


def score_dir(data: Path | str, run_id: str, label: str = "") -> Path:
    """The score of a run read under `label`."""
    for sd in model_runs.scores_of(runs_in(data) / run_id):
        if str(model_runs.meta(sd).get("label") or "") == label:
            return sd
    raise KeyError(f"{run_id}: no score read as {label!r}")


def patch(data: Path | str, run_id: str, extra: dict[str, Any], label: str = "") -> None:
    """`extra` merged over a score's record (a fingerprint, a derived block), written back as the score's own."""
    sd = score_dir(data, run_id, label)
    full = {
        k: v for k, v in {**(model_runs.record(sd) or {}), **extra}.items() if k not in model_runs.RUN_ONLY
    }
    own, unset = model_runs.split(full, model_runs.run(model_runs.run_of(sd)))
    meta = model_runs.meta(sd)
    if unset:
        meta["unset"] = unset
    _store.write_text(sd / model_runs.SCORE, json.dumps(meta, indent=2) + "\n")
    _store.write_text(sd / model_runs.METRICS, json.dumps(own, indent=2) + "\n")
