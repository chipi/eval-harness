#!/usr/bin/env python3
"""What production must match to run what was measured (RFC-023, PRD-005 FR3), and whether a capture says it did.

    evh deploy-sheet triage_baseline_pro_v1
    evh deploy-sheet triage_baseline_pro_v1 --capture orrery_2026_11

The sheet is read from the run the arm was promoted with (the latest baseline whose run is the arm's), else the
arm's latest run: the model, its record and the deployment (tag, endpoint, server, build), every setting the arm
sent (and a record setting it did not), what the system reported per item (`_meta`: its model, its prompt's hash),
the declared settings and deployment, the adapter and the harness, and the dataset and reference it was measured on.

With --capture, each record's account of what production ran comes from the adapter's `production_ran(record)`
({"model": ..., "prompt_sha": ...}). A key is matched against what the run's own items reported for it (`_meta`),
and the model also against the model record's id, aliases and deployment tags. It ends with "every captured
decision was made by the promoted model and prompt", or what differs on how many records; it exits 1 when anything
differs or is not recorded. Nothing is written.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

from collections import Counter
from pathlib import Path
from typing import Any

from evaluation_harness import _models, _runs, _store
from evaluation_harness._adapter import adapter_module
from evaluation_harness._common import DATA, die
from evaluation_harness.dataset_from_capture import load_capture
from evaluation_harness.model import runs as _model_runs

#: A `_meta` key is shown as what the system reported when its items give at most this many values (a model, a
#: prompt's hash), not a per-item account (the gates each item passed).
FEW = 3


def promoted_run(
    system_id: str, data_dir: Path | None = None, runs_dir: Path | None = None
) -> tuple[Path, dict[str, Any] | None]:
    """(the run as the score it made when it ran, the baseline it was promoted as, or None): of the current baselines
    of every goal and every dataset's own (RFC-027), the latest whose run is this arm's, else the arm's latest run.
    The project's directories, or `data_dir` and `runs_dir` (the catalog's)."""
    from evaluation_harness import _baselines  # noqa: PLC0415

    runs = runs_dir or _model_runs.root()
    best: tuple[str, Path, dict[str, Any]] | None = None
    for b in _baselines.all_current(data_dir):
        first = _model_runs.first_score(runs / str(b.get("promoted_from") or "x"))
        rec = _model_runs.record(first) if first else None
        if (
            b.get("promoted_from")
            and first is not None
            and rec is not None
            and rec.get("system_id") == system_id
            and (best is None or str(b.get("promoted_at")) > best[0])
        ):
            best = (str(b.get("promoted_at")), first, b)
    if best:
        return best[1], best[2]
    found = []
    for run in sorted(_store.iterdir(runs)) if _store.is_dir(runs) else []:
        first = _model_runs.first_score(run)
        rec = _model_runs.record(first) if first else None
        if first is None or rec is None:
            continue
        if rec.get("system_id") == system_id and _model_runs.label(first, rec) == "":
            found.append(first)
    if not found:
        die(f"--system {system_id}: no run of that system (evh runs-list)", "not-found")
    return found[-1], None


def reported(run: Path) -> dict[str, list[str]]:
    """{key: values}: what the system reported per item (`_meta` in predictions.jsonl), the keys with few values."""
    seen: dict[str, set[str]] = {}
    for row in _runs.item_rows(run):
        meta = row.get("_meta") or {}
        for k, v in meta.items():
            if isinstance(v, (str, int, float)) and not isinstance(v, bool):
                seen.setdefault(k, set()).add(str(v))
    return {k: sorted(v) for k, v in sorted(seen.items()) if len(v) <= FEW}


def sheet(system_id: str, data_dir: Path | None = None, runs_dir: Path | None = None) -> dict[str, Any]:
    """Everything production must match, as a dict."""
    run, base = promoted_run(system_id, data_dir, runs_dir)
    data_root = data_dir or DATA
    m = _model_runs.record(run) or {}
    fp = m.get("fingerprint") or {}
    params = m.get("params") or {}
    not_sent = set(((fp.get("arm") or {}).get("labels") or {}).keys())
    dep = fp.get("deployment") or {}
    data = fp.get("data") or {}
    inst = fp.get("instrument") or {}
    rec = (
        _models.find(data_root, params["model_record"])
        if params.get("model_record")
        else _models.by_alias(data_root).get(str(params.get("model")))
    )
    deployment = None
    if rec:
        deployment = _models.deployment_of(rec, params.get("deployment") or "") or next(
            (d for d in rec.get("deployments") or [] if d.get("tag") == params.get("model")), None
        )
    rec_settings = (rec or {}).get("settings") or {}
    weights = dep.get("weights") or {}
    return {
        "system_id": system_id,
        "run_id": m.get("run_id"),
        "promoted": None
        if base is None
        else {k: base.get(k) for k in ("goal", "version", "dataset_id", "promoted_at", "reason")},
        "dataset_id": data.get("dataset_id") or m.get("dataset_id"),
        "reference": {"id": data.get("reference_id"), "tier": data.get("reference_tier")},
        "model": {
            "sent": params.get("model"),
            "record": (rec or {}).get("model_id"),
            "deployment": None
            if deployment is None
            else {k: deployment.get(k) for k in ("id", "where", "tag", "endpoint") if deployment.get(k)},
            "server": dep.get("server"),
            "build": weights.get("digest") or weights.get("revision") or weights.get("file_hash"),
            "provider": dep.get("provider"),
        },
        "sent": {k: v for k, v in sorted(params.items()) if k not in not_sent},
        "not_sent": sorted(not_sent),
        "record_settings_not_sent": {k: v for k, v in sorted(rec_settings.items()) if k not in params},
        "declared": {
            "settings": (fp.get("settings") or {}).get("declared") or {},
            "deployment": dep.get("declared") or {},
        },
        "reported": reported(run),
        "adapter": inst.get("adapter") or {"id": m.get("adapter")},
        "harness": {k: (inst.get("harness") or {}).get(k) for k in ("version", "commit")},
        "_names": sorted(
            {
                str(x)
                for x in [
                    params.get("model"),
                    (rec or {}).get("model_id"),
                    *((rec or {}).get("aliases") or []),
                ]
                if x
            }
            | {str(d.get("tag")) for d in (rec or {}).get("deployments") or [] if d.get("tag")}
        ),
        "_adapter_spec": m.get("adapter"),
    }


def check(s: dict[str, Any], capture_id: str, captures_dir: Path | None = None) -> dict[str, Any]:
    """Each record's account of what production ran, against the sheet: per key, matched, differing, missing."""
    mod = adapter_module(s["_adapter_spec"])
    fn = getattr(mod, "production_ran", None)
    if not callable(fn):
        die(
            f"--capture: the adapter {s['_adapter_spec']} has no production_ran(record): it cannot say what production"
            " ran",
            "invalid-file",
        )
    _, recs = load_capture(capture_id, captures_dir)
    per: dict[str, dict[str, Any]] = {}
    for r in recs:
        for k, v in (fn(r) or {}).items():
            want = set(s["reported"].get(k) or []) | (set(s["_names"]) if k == "model" else set())
            row = per.setdefault(k, {"expected": sorted(want), "match": 0, "differ": Counter(), "missing": 0})
            if v is None or v == "":
                row["missing"] += 1
            elif not want:
                row["differ"][str(v)] += 1
            elif str(v) in want:
                row["match"] += 1
            else:
                row["differ"][str(v)] += 1
    return {"capture": capture_id, "records": len(recs), "keys": per}
