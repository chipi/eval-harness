#!/usr/bin/env python3
"""Replay a system at the commits production ran and compare it with production's arm, item by item (RFC-030).

    evh faithfulness --config data/configs/filing_replay_v1.yaml --production production_v1_20261105T120000
    evh faithfulness --config data/configs/filing_replay_v1.yaml --production <run> --dry-run

Every item of the dataset runs, in the replay's order, at the commit its code record says ran it then; each output is
compared with production's (a recorded arm's run on the same dataset) by the adapter's `same(a, b)`, else as text.
The result is written once, data/faithfulness/<model_id>/<n>.json: the counts, every disagreement with both sides, the
hashes the gate checks (items, the record's deployed versions, adapter and its support modules), and the coverage:
per commit, the functions of the system's code the replay entered and those it never did. Each version's summary
goes into the code record (`faithfulness`), which the Models page and `evh models` show. It measures: exit 0
whatever it found. A disagreement whose cause is outside the system is named with `evh faithfulness-name`.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml
from evaluation_harness import (
    _codeload,
    _coderec,
    _coverage,
    _faith,
    _jsonout,
    _outputs,
    _replay,
    _store,
)
from evaluation_harness._common import (
    DATA,
    EXIT_STOPPED,
    ROOT,
    RUNS,
    die,
    evh_prog,
    load_dataset,
    now,
    read_json,
)

#: Disagreements printed; the record keeps every one.
SHOWN = 30


def main() -> int:
    """Replay at the recorded commits and compare with production."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "--config", required=True, type=Path, help="the replay config (replay:, model_record: a code record)"
    )
    ap.add_argument(
        "--production",
        required=True,
        metavar="RUN_ID",
        help="production's arm: a run on the same dataset holding what production did (a recorded arm)",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="the plan (items, commits) without calling anything"
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="progress on stderr, and one JSON object on stdout: result.values.faithfulness (the record, its n), "
        "or result.values.plan with --dry-run",
    )
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    args = ap.parse_args()
    with _jsonout.collect("faithfulness", args.json, live=sys.stderr):
        return _faithfulness(args)


def _production(run_id: str, ds: dict[str, Any]) -> dict[str, str]:
    from evaluation_harness._fingerprint import items_digest  # noqa: PLC0415

    d = RUNS / run_id
    if not _store.is_file(d / "metrics.json"):
        die(f"--production {run_id}: no finished run at {d}", "not-found")
    m = read_json(d / "metrics.json")
    if m.get("dataset_id") != ds["dataset_id"]:
        die(
            f"--production {run_id} ran on {m.get('dataset_id')}, the replay on {ds['dataset_id']}",
            "mismatch",
        )
    have = ((m.get("fingerprint") or {}).get("data") or {}).get("items_sha256")
    if have and have != items_digest(ds):
        die(
            f"--production {run_id} ran on other items of {ds['dataset_id']} (its items hash differs)",
            "mismatch",
        )
    out = _outputs.outputs(d)
    if not out:
        die(f"--production {run_id} has no outputs", "not-found")
    return out


def _faithfulness(args: argparse.Namespace) -> int:
    from evaluation_harness import _models, _prompts, _seal  # noqa: PLC0415
    from evaluation_harness import run as _run  # noqa: PLC0415
    from evaluation_harness._actor import actor  # noqa: PLC0415
    from evaluation_harness._adapter import load_adapter, same_at  # noqa: PLC0415
    from evaluation_harness._fingerprint import items_digest  # noqa: PLC0415

    if not _store.is_file(args.config):
        die(f"no config at {args.config}", "not-found")
    cfg = yaml.safe_load(_store.read_text(args.config, encoding="utf-8")) or {}
    try:
        cfg = _models.resolve(cfg, DATA)
    except ValueError as exc:
        die(f"{args.config}: {exc}", "invalid-file")
    if not _replay.is_replay(cfg):
        die(f"{args.config} is not a replay config (it has no replay:)", "invalid-file")
    call_system, score, adapter_id, adapter_path, warmup, _hook = load_adapter(
        cfg.get("adapter"), args.config
    )
    ds = load_dataset(cfg["dataset_id"])
    plan = _replay.prepare(cfg, args.config, ds, adapter_path)
    assert plan is not None
    if plan.candidate:
        die(
            f"{args.config} runs every item at the candidate {plan.candidate[:12]}: faithfulness replays the commits "
            "production ran. Use the replay config the candidate was made from.",
            "bad-argument",
        )
    production = _production(args.production, ds)
    commits = plan.commits()
    print(
        f"faithfulness of {plan.model_id} on {ds['dataset_id']}: {len(plan.items)} items at {len(commits)} commit(s)"
    )
    for c, k in commits.items():
        have = (_coderec.copies_dir(plan.model_id) / c / ".evh-commit").is_file()
        print(f"  {c[:12]}  {k} item(s)" + ("" if have else "  (to unpack)"))
    if args.dry_run:
        print("DRY RUN: nothing was called")
        _jsonout.value(
            "plan",
            {
                "model_id": plan.model_id,
                "dataset_id": ds["dataset_id"],
                "items": len(plan.items),
                "commits": commits,
            },
        )
        return 0
    _seal.refuse_if_sealed(cfg["dataset_id"], "a faithfulness replay", cfg["config_id"])
    _replay.environment()
    resolved = _prompts.resolve(cfg, args.config, cfg["config_id"])
    if resolved is not None:
        import atexit  # noqa: PLC0415

        atexit.register(_prompts.remove_copy, resolved)
    call_cfg = {**cfg, "params": {**dict(cfg.get("params") or {}), **(resolved or {}).get("params", {})}}
    if warmup is not None:
        warmup(dict(call_cfg["params"]))
    live = ROOT / ".build" / "faithfulness" / plan.model_id / f"{now().replace(':', '')}-{os.getpid()}"
    try:
        with _coverage.Tracer(_coderec.copies_dir(plan.model_id)) as tracer:
            result = _run.one_pass(
                {**ds, "items": plan.items},
                call_cfg,
                0,
                live_dir=live,
                call_system=call_system,
                score=score,
                scored_against=(None, None),
                per_item=_replay.item_params(plan),
                once=True,
            )
    except (_run.SystematicFailure, _run.ServerUnreachable) as exc:
        die(f"the replay stopped: {exc}; nothing was recorded", "failed")
    finally:
        shutil.rmtree(live, ignore_errors=True)
    if result["capped_at"]:
        print(f"STOPPED by the cost cap at item {result['capped_at']}: a partial replay is not recorded")
        return EXIT_STOPPED
    failed = {f["item_id"]: f["error"] for f in result.get("failed_items") or []}
    counts, disagreements = _faith.compare(
        [it["item_id"] for it in plan.items],
        result["outputs"],
        failed,
        production,
        same_at(adapter_path),
        plan.commit_of,
    )

    def version(f: str) -> tuple[str | None, str]:
        v = _codeload.version_of(Path(f))
        return (v.name, str(Path(f).resolve().relative_to(v))) if v is not None else (None, f)

    coverage = _coverage.report(tracer.entered, version)
    from evaluation_harness._replay import adapter_identity  # noqa: PLC0415

    rec = {
        "model_id": plan.model_id,
        "config_id": cfg["config_id"],
        "dataset_id": ds["dataset_id"],
        "items_sha256": items_digest(ds),
        "versions_sha256": _coderec.versions_sha256(plan.record),
        "adapter_sha256": adapter_identity(adapter_id, adapter_path, plan)["sha256"],
        "commits": commits,
        "production_run": args.production,
        "counts": counts,
        "disagreements": disagreements,
        "coverage": coverage,
        "at": now(),
        "actor": actor(),
    }
    n = _faith.write(rec)
    _coderec.record_faithfulness(plan.model_id, n, {**rec, "exceptions": []})
    agree = counts["agree"]
    print(
        f"\nrecord {plan.model_id}/{n}: {agree} of {counts['items']} agree with production"
        f" ({counts['differ']} differ, {counts['replay_errors']} replay error(s), "
        f"{counts['production_missing']} without a production output)"
    )
    for d in disagreements[:SHOWN]:
        print(
            f"  {d['kind']:18} {d['item_id']}  at {str(d.get('commit') or '')[:12]}"
            f"\n      production: {str(d.get('production'))[:120]!r}\n      replay:     "
            + (d.get("error") or repr(str(d.get("replay"))[:120]))
        )
    if len(disagreements) > SHOWN:
        print(f"  … {len(disagreements) - SHOWN} more in the record")
    print("coverage (functions of the system's code the replay entered):")
    for c, v in coverage.items():
        print(
            f"  {c[:12]}  {v['entered']} of {v['defined']} in {v['files']} file(s); never entered: {v['never_count']}"
        )
        for name in v["never"][:8]:
            print(f"      {name}")
    if disagreements:
        print(
            "A replay is scored against a reference only once every disagreement is fixed or named (evh "
            f"faithfulness-name --model {plan.model_id} --item ITEM --cause ...)."
        )
    _jsonout.value("faithfulness", {**rec, "n": n})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
