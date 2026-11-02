#!/usr/bin/env python3
"""Production's recorded decisions as an arm (RFC-023): scored and compared like any arm, no system called.

    evh arm-from-capture --dataset-id orrery_triage_2026_11 --capture orrery_2026_11 \\
        --as production_2026_11_v1 --like examples/triage-fleet/configs/triage_baseline_pro.yaml
    evh arm-from-capture --dataset-id desk_v1 --capture desk_c1 --as desk_production_v1 --field resolution \\
        --labels owner_v1

It writes the arm's config, data/configs/<as>.yaml, with `provider: recorded` and the capture, and runs it: each
item's output is the capture's record of the same id, read by the adapter's `recorded_output(record)` (the
deployed arm's adapter, from --like), else the record's field named by --field. The run is an ordinary run: the
same scorer, references or labels (--labels), fingerprint (the capture's sha256 in its settings) and tests as any
arm; its cost is 0 and its speed is not measured. A config of that name is never overwritten.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
from pathlib import Path

import yaml
from evaluation_harness._common import CAPTURES, CONFIGS, ROOT, dataset_id_ok, die, load_dataset


def main() -> int:
    """Write production's recorded arm and run it."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--capture", required=True, help="the capture whose records hold production's decisions")
    ap.add_argument(
        "--as", required=True, dest="config_id", help="the arm's config_id (e.g. production_2026_11_v1)"
    )
    ap.add_argument("--like", type=Path, help="the deployed arm's config: its adapter and goal are taken")
    ap.add_argument(
        "--field", help="the record's field holding the output, when the adapter has no recorded_output"
    )
    ap.add_argument("--goal", help="the goal the arm is for (default: --like's)")
    ap.add_argument("--labels", metavar="SET", help="score against this label set of the dataset (RFC-023)")
    args = ap.parse_args()

    load_dataset(args.dataset_id)
    if not (CAPTURES / dataset_id_ok(args.capture) / "capture.json").is_file():
        die(f"no capture {args.capture} (evh captures)")
    out = CONFIGS / f"{dataset_id_ok(args.config_id)}.yaml"
    if out.exists():
        die(f"{out} exists: a config is not overwritten. Name the arm another way (--as).")
    cfg: dict = {"config_id": args.config_id, "dataset_id": args.dataset_id}
    if args.like:
        if not args.like.is_file():
            die(f"--like: no config {args.like}")
        like = yaml.safe_load(args.like.read_text(encoding="utf-8")) or {}
        if like.get("adapter"):
            # Written relative to the project (the new config is elsewhere than the one it is like).
            a = (args.like.parent / like["adapter"]).resolve()
            try:
                cfg["adapter"] = str(a.relative_to(ROOT))
            except ValueError:
                cfg["adapter"] = str(a)
        if like.get("goal"):
            cfg["goal"] = like["goal"]
    if args.goal:
        cfg["goal"] = args.goal
    if not args.field:
        # Checked before anything is written: a config left behind by a refused run would block the next try.
        from evaluation_harness._adapter import _module_or_none  # noqa: PLC0415

        spec = cfg.get("adapter")
        mod = _module_or_none(
            Path(spec) if spec and Path(spec).is_absolute() else ROOT / spec if spec else None
        )
        if not callable(getattr(mod, "recorded_output", None)):
            die(
                "a recorded arm reads each output with the adapter's recorded_output(record) or from the record's "
                f"field named by --field; {spec or 'the bundled adapter'} has no recorded_output: pass --field, or --like "
                "the deployed arm's config"
            )
    cfg["params"] = {
        "provider": "recorded",
        "capture": args.capture,
        **({"field": args.field} if args.field else {}),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "# Production's recorded decisions as an arm (evh arm-from-capture, RFC-023): no system is called.\n"
        + yaml.safe_dump(cfg, sort_keys=False),
        encoding="utf-8",
    )
    print(f"{out}: the recorded arm {args.config_id}, from the capture {args.capture}")
    from evaluation_harness.cli import main as evh  # noqa: PLC0415

    return evh(["run", "--config", str(out), *(["--labels", args.labels] if args.labels else [])])


if __name__ == "__main__":
    raise SystemExit(main())
