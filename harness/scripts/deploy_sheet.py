#!/usr/bin/env python3
"""What production must match to run what was measured (RFC-023, PRD-005 FR3), and whether a capture says it did.

    evh deploy-sheet --config triage_baseline_pro_v1
    evh deploy-sheet --config triage_baseline_pro_v1 --capture orrery_2026_11

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

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation_harness import _models, _runs
from evaluation_harness._adapter import adapter_module
from evaluation_harness._common import BASELINES, DATA, EXIT_PROBLEMS, RUNS, die, evh_prog, read_json
from evaluation_harness._runs import runs_on
from evaluation_harness.dataset_from_capture import load_capture

#: A `_meta` key is shown as what the system reported when its items give at most this many values (a model, a
#: prompt's hash), not a per-item account (the gates each item passed).
FEW = 3


def promoted_run(
    config_id: str, data_dir: Path | None = None, runs_dir: Path | None = None
) -> tuple[Path, dict[str, Any] | None]:
    """(the run, the baseline it was promoted as, or None): the latest baseline whose run is this arm's, else the
    arm's latest run. The project's directories, or `data_dir` and `runs_dir` (the catalog's)."""
    baselines = (data_dir / "baselines") if data_dir else BASELINES
    runs = runs_dir or RUNS
    best: tuple[str, Path, dict[str, Any]] | None = None
    for f in sorted(baselines.glob("*.json")) if baselines.is_dir() else []:
        b = read_json(f)
        run = runs / str(b.get("promoted_from") or "")
        if (
            b.get("promoted_from")
            and (run / "metrics.json").is_file()
            and read_json(run / "metrics.json").get("config_id") == config_id
            and (best is None or str(b.get("promoted_at")) > best[0])
        ):
            best = (str(b.get("promoted_at")), run, b)
    if best:
        return best[1], best[2]
    found = runs_on(config_id=config_id, runs_dir=runs)
    if not found:
        die(f"--config {config_id}: no run of that config (evh runs-list)", "not-found")
    return found[-1][0], None


def reported(run: Path) -> dict[str, list[str]]:
    """{key: values}: what the system reported per item (`_meta` in predictions.jsonl), the keys with few values."""
    seen: dict[str, set[str]] = {}
    for row in _runs.item_rows(run):
        meta = row.get("_meta") or {}
        for k, v in meta.items():
            if isinstance(v, (str, int, float)) and not isinstance(v, bool):
                seen.setdefault(k, set()).add(str(v))
    return {k: sorted(v) for k, v in sorted(seen.items()) if len(v) <= FEW}


def sheet(config_id: str, data_dir: Path | None = None, runs_dir: Path | None = None) -> dict[str, Any]:
    """Everything production must match, as a dict."""
    run, base = promoted_run(config_id, data_dir, runs_dir)
    data_root = data_dir or DATA
    m = read_json(run / "metrics.json")
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
        "config_id": config_id,
        "run_id": run.name,
        "promoted": None
        if base is None
        else {k: base.get(k) for k in ("baseline_id", "dataset_id", "promoted_at", "reason")},
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


def main() -> int:
    """Print the deploy sheet, and the capture check."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--config", required=True, help="the arm's config_id (its promoted run, else its latest)")
    ap.add_argument(
        "--capture", help="a capture whose records say what production ran (the adapter's production_ran)"
    )
    ap.add_argument("--json", action="store_true", help="print JSON")
    args = ap.parse_args()

    s = sheet(args.config)
    c = check(s, args.capture) if args.capture else None
    ok = c is None or (
        bool(c["keys"]) and all(not k["differ"] and not k["missing"] for k in c["keys"].values())
    )
    if args.json:
        out = {k: v for k, v in s.items() if not k.startswith("_")}
        if c is not None:
            out["capture_check"] = {**c, "ok": ok}
        print(json.dumps(out, indent=2, default=dict))
        return 0 if ok else EXIT_PROBLEMS
    p = s["promoted"]
    print(f"deploy sheet: {s['config_id']}")
    ref = s.get("reference") or {}
    against = f"{ref['id']} ({ref.get('tier') or 'no tier'})" if ref.get("id") else "no reference"
    print(f"  measured by   {s['run_id']} on {s['dataset_id']}, against {against}")
    print(
        f"  promoted      as {p['baseline_id']} on {p['dataset_id']}, {p['promoted_at']}"
        if p
        else "  promoted      no: this is the arm's latest run, not a baseline"
    )
    mm = s["model"]
    print(f"\nmodel\n  sent          {mm['sent']}")
    print(f"  record        {mm['record'] or '(no model record names it)'}")
    if mm["deployment"]:
        for k, v in mm["deployment"].items():
            print(f"  {k:<13} {json.dumps(v) if isinstance(v, dict) else v}")
    print(f"  provider      {mm['provider']}")
    print(f"  server        {mm['server'] or '(not recorded)'}")
    print(f"  build         {mm['build'] or '(none recorded: a hosted model has no digest)'}")
    print("\nsettings the arm sent")
    for k, v in s["sent"].items():
        print(f"  {k:<22} {v}")
    if s["not_sent"]:
        print(f"  (bookkeeping, not sent: {', '.join(s['not_sent'])})")
    for k, v in s["record_settings_not_sent"].items():
        print(f"  NOTE: the record sets {k}: {v}; this arm did not send it (it names no model_record)")
    print("\ndeclared")
    for part, kv in s["declared"].items():
        for k, v in kv.items():
            print(f"  {part}.{k:<14} {v}")
    print("\nwhat the system reported per item")
    for k, vs in s["reported"].items():
        print(f"  {k:<22} {', '.join(vs)}")
    if not s["reported"]:
        print("  (nothing: the adapter records no _meta)")
    print(f"\nadapter         {s['adapter'].get('id')} {s['adapter'].get('sha256') or ''}".rstrip())
    print(f"harness         {s['harness']['version']} {s['harness']['commit'] or ''}".rstrip())
    if c is not None:
        print(f"\ncapture {c['capture']}: {c['records']} record(s)")
        for k, row in c["keys"].items():
            if row["missing"] == c["records"] and not row["match"] and not row["differ"]:
                print(f"  {k:<12} production recorded none, so it cannot be checked")
                continue
            line = f"  {k:<12} {row['match']} match"
            if row["differ"]:
                line += "; differ: " + ", ".join(f"{v} ({n})" for v, n in row["differ"].most_common(5))
            if row["missing"]:
                line += f"; not recorded: {row['missing']}"
            print(line + f"   (expected: {', '.join(row['expected']) or 'nothing the run reported'})")
        if not c["keys"]:
            print("  the adapter's production_ran said nothing for any record")
        print(
            "\nevery captured decision was made by the promoted model and prompt"
            if ok
            else "\nNOT every captured decision was made by the promoted model and prompt (above: what differs)"
        )
    return 0 if ok else EXIT_PROBLEMS


if __name__ == "__main__":
    raise SystemExit(main())
