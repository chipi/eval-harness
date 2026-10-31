#!/usr/bin/env python3
"""Migrate every committed run's fingerprint from version 4 to version 5 (RFC-021), once.

    evh fingerprint-migrate [--data-dir data] [--dry-run]

Rewrites only the `fingerprint` of each `<data>/runs*/**/metrics.json`, and the `fingerprint_hash` a
baseline carries from its run (validate V6 compares the two):

  instrument, data   copied
  runner             v4's `host`, and v4's `system_under_test.libraries` when the model did not run in this process
  deployment         from v4's `system_under_test.model` when the adapter declared an identity (source: adapter,
                     in-process, with v4's libraries); else from the run's params (source: params)
  settings           the run's params minus deployment keys and credentials
  hashes             recomputed; a derived run (hash null) keeps the whole hash null

A derived run (rescored, judged, re-parsed) takes its deployment, settings and runner from the run it
derives from when that run is in the tree. A v5 fingerprint is left as it is, so a second run changes
nothing. Run outputs and predictions are not touched. Prints the counts before and after.
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

from evaluation_harness import _fingerprint as fpmod
from evaluation_harness._common import DATA, write_text_atomic

DEPLOYMENT_PARTS = ("deployment", "settings", "runner")


def migrate_fingerprint(fp: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]:
    """The v5 fingerprint of a v4 one. `params` are the run's params when the fingerprint's own `arm.params`
    are missing. A v5 one is brought to v5's current rules (prices and labels out of the settings, the
    instrument hashed by its code) and re-sealed; one already there comes back the same."""
    if fp.get("version") == fpmod.VERSION:
        out: dict[str, Any] = json.loads(json.dumps(fp))
        settings = out.get("settings") or {}
        labels = {k: settings.pop(k) for k in fpmod.LABEL_KEYS if k in settings}
        arm = out.setdefault("arm", {})
        if labels or "labels" not in arm:
            arm["labels"] = {**(arm.get("labels") or {}), **labels} or None
        return fpmod.seal(out, whole=fp.get("hash") is not None)
    if fp.get("version") != 4:
        raise ValueError(f"fingerprint version {fp.get('version')!r}: only 4 is migrated")
    arm = fp.get("arm") or {}
    run_params = dict(arm.get("params") or params or {})
    sut = fp.get("system_under_test") or {}
    declared = dict(sut.get("model") or {})
    libraries = dict(sut.get("libraries") or {})
    if declared.get("identity_declared"):
        deployment = fpmod._adapter_deployment(declared, run_params, libraries)
    else:
        deployment = fpmod._params_deployment(run_params, declared)
    out = {
        "version": fpmod.VERSION,
        "instrument": fp.get("instrument"),
        "data": fp.get("data"),
        "deployment": deployment,
        "settings": fpmod.settings_of(run_params),
        "runner": {**(fp.get("host") or {}), "libraries": None if deployment["in_process"] else libraries},
        "arm": {"config_id": arm.get("config_id"), "labels": fpmod.labels_of(run_params) or None},
    }
    for k, v in fp.items():
        if k not in {"version", "instrument", "data", "system_under_test", "host", "arm", "hash"}:
            out[k] = v
    fpmod.split_declared(out["deployment"], out["settings"])
    return fpmod.seal(out, whole=fp.get("hash") is not None)


def _dump(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def run_files(data: Path) -> list[Path]:
    """Every run's metrics.json under data/runs*/."""
    return sorted(p for d in data.glob("runs*") if d.is_dir() for p in d.rglob("metrics.json"))


def main() -> int:
    """Migrate, print the counts before and after; exit 0."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=DATA,
        help="the project's data root (default: this project's, EVAL_DATA_DIR)",
    )
    ap.add_argument("--dry-run", action="store_true", help="count what would change; write nothing")
    args = ap.parse_args()
    data = args.data_dir.resolve()

    docs: dict[Path, dict[str, Any]] = {}
    before: Counter[str] = Counter()
    for f in run_files(data):
        text = f.read_text(encoding="utf-8")
        doc = json.loads(text)
        docs[f] = doc
        fp = doc.get("fingerprint")
        before["no fingerprint" if not isinstance(fp, dict) else f"v{fp.get('version')}"] += 1
        if isinstance(fp, dict) and _dump(doc) != text:
            before["not in the harness's JSON layout (rewritten in it)"] += 1

    migrated: dict[Path, dict[str, Any]] = {}
    old_hash: dict[Path, str | None] = {}
    for derived in (False, True):
        by_name: dict[str, list[Path]] = {}
        for f in migrated:
            by_name.setdefault(f.parent.name, []).append(f)
        for f, doc in docs.items():
            fp = doc.get("fingerprint")
            if (
                not isinstance(fp, dict)
                or fp.get("version") not in (4, 5)
                or bool(doc.get("derived")) != derived
            ):
                continue
            new = migrate_fingerprint(fp, doc.get("params"))
            if fp.get("version") == 5:
                if new != fp:
                    old_hash[f] = fp.get("hash")
                    migrated[f] = {**doc, "fingerprint": new}
                continue
            if derived:
                sources = by_name.get((doc.get("derived") or {}).get("from", ""), [])
                if len(sources) == 1:
                    src = migrated[sources[0]]["fingerprint"]
                    for part in DEPLOYMENT_PARTS:
                        new[part] = src[part]
                    fpmod.seal(new, whole=fp.get("hash") is not None)
            old_hash[f] = fp.get("hash")
            migrated[f] = {**doc, "fingerprint": new}

    after: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    for f, doc in docs.items():
        fp = (migrated.get(f) or doc).get("fingerprint")
        after["no fingerprint" if not isinstance(fp, dict) else f"v{fp.get('version')}"] += 1
        if f in migrated:
            by_source[migrated[f]["fingerprint"]["deployment"]["source"]] += 1
    if not args.dry_run:
        for f, doc in migrated.items():
            write_text_atomic(f, _dump(doc))

    baselines = 0
    for b in sorted((data / "baselines").glob("*.json")) if (data / "baselines").is_dir() else []:
        doc = json.loads(b.read_text(encoding="utf-8"))
        runs = [
            f
            for f in migrated
            if f.parent.name == doc.get("promoted_from") and old_hash[f] == doc.get("fingerprint_hash")
        ]
        new_hash = migrated[runs[0]]["fingerprint"]["hash"] if len(runs) == 1 else None
        if new_hash:
            baselines += 1
            if not args.dry_run:
                write_text_atomic(b, _dump({**doc, "fingerprint_hash": new_hash}))

    print(f"fingerprint v5 migration of {data}{' (dry run: nothing written)' if args.dry_run else ''}")
    print("  before:", ", ".join(f"{n} {k}" for k, n in sorted(before.items())) or "no runs")
    print("  after: ", ", ".join(f"{n} {k}" for k, n in sorted(after.items())) or "no runs")
    print(f"  runs migrated: {len(migrated)}")
    for src in ("record", "adapter", "params"):
        print(f"    deployment source {src}: {by_source.get(src, 0)}")
    print(f"  baselines whose fingerprint_hash was updated: {baselines}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
