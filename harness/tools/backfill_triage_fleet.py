#!/usr/bin/env python3
"""Backfill the triage runs' fingerprints with the fleet they replayed (Fable review A2, 2026-10-31).

The triage adapter's fingerprint() hook came after the runs, so their deployments name the model but not
the fleet code, its commit or the prompt. Every run was made from one extracted checkout of the fleet at
f07efa9 (the runner scripts' TRIAGE_FLEET_SRC), whose four modules match `git show f07efa9:signal-fleet/mvp/*`
byte for byte, and every decided item recorded the fleet's own prompt hash c2ece738 (sha1[:8] of the same
system prompt the hook hashes with sha256). This rebuilds each run's deployment with the run-time code
(_fingerprint.deployment_of, the real hook against that checkout), moves the prompt hash to the settings,
and re-seals: each run's deployment is then the one it would record today. It refuses a change to the
server, the machine, the provider, or a model the run already named; what follows from the params and the
hook (its source, a hosted route's fill, `revision_source`) may change.

    TRIAGE_FLEET_SRC=<checkout of f07efa9>/signal-fleet .venv/bin/python tools/backfill_triage_fleet.py [--apply]
"""

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "examples" / "triage-fleet"))
import adapter  # noqa: E402
from evaluation_harness import _fingerprint as fpmod  # noqa: E402
from evaluation_harness._runs import item_rows  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

DATA = HERE / "data"
COMMIT, PROMPT_SHA = "f07efa9", "c2ece738"


def item_prompt_shas(score: Path) -> set:
    """The fleet's prompt hashes the decided items of a run's score recorded."""
    shas = set()
    for row in item_rows(score):
        sha = (row.get("_meta") or {}).get("prompt_sha")
        if sha:
            shas.add(sha)
    return shas


def backfill(m: dict) -> dict:
    """The run's record (run.json) with the fleet in its fingerprint; refuses any other change."""
    fp = json.loads(json.dumps(m["fingerprint"]))
    params = m.get("params") or {}
    cfg = {"model_record": m.get("model_record"), "deployment": m.get("deployment_id")}
    old = fp["deployment"]
    libs = (fp.get("runner") or {}).get("libraries") or old.get("libraries") or {}
    dep = fpmod.deployment_of(params=params, cfg=cfg, data_dir=DATA, hook=adapter.fingerprint, libraries=libs)
    settings = dict(fp.get("settings") or {})
    fpmod.split_declared(dep, settings)
    # What the hook decides may change (who declared it, the fleet, a stub's in-process model); the server,
    # the machine and the provider may not, and a model the run already named may not be renamed.
    fixed = ["server", "where", "provider"] + (["model"] if old.get("model") else [])
    moved = [k for k in fixed if old.get(k) != dep.get(k)]
    if moved:
        raise SystemExit(f"{m['run_id']}: would change {moved}: not what the hook decides")
    if set(settings) - set(fp.get("settings") or {}) - {"declared"}:
        raise SystemExit(f"{m['run_id']}: settings would change beyond `declared`")
    fp["deployment"], fp["settings"] = dep, settings
    if dep["in_process"] and fp.get("runner"):
        fp["runner"]["libraries"] = None  # the libraries ran the model: they are the deployment's now
    return {**m, "fingerprint": fpmod.seal(fp, whole=m["fingerprint"].get("hash") is not None)}


def main() -> int:
    """Check the fleet checkout, then backfill (or count) every triage run; exit 1 on any refusal."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="write the metrics (default: report only)")
    args = ap.parse_args()
    os.environ.setdefault("TRIAGE_FLEET_COMMIT", COMMIT)
    if adapter._fleet().PROMPT_SHA != PROMPT_SHA:
        raise SystemExit(
            f"TRIAGE_FLEET_SRC is not the fleet the runs used: prompt {adapter._fleet().PROMPT_SHA}"
        )
    counts = {"backfilled": 0, "already": 0}
    for rid in model_runs.run_ids():
        if not rid.startswith("triage_"):
            continue
        m = model_runs.run(rid)
        first = model_runs.first_score(rid)
        if m is None or first is None:
            continue
        if item_prompt_shas(first) != {PROMPT_SHA}:
            raise SystemExit(f"{rid}: items recorded {item_prompt_shas(first)}, not {PROMPT_SHA}")
        new = backfill(m)
        if new == m:
            counts["already"] += 1
            continue
        counts["backfilled"] += 1
        if args.apply:
            model_runs.write_run(rid, new)
    print(("applied" if args.apply else "dry run"), counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
