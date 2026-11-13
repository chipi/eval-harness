#!/usr/bin/env python3
"""Production's recorded decisions as a system (RFC-023): scored and compared like any system, nothing called.

    evh arm-from-capture --dataset-id orrery_triage_2026_11 --capture orrery_2026_11 \\
        --as production_2026_11_v1 --like triage_baseline_pro_v1 --goal triage_orrery
    evh arm-from-capture --dataset-id desk_v1 --capture desk_c1 --as desk_production_v1 --field resolution \\
        --labels owner_v1

It writes the system, data/systems/<as>.yaml, with `provider: recorded` and the capture, and runs it on the dataset:
each item's output is the capture's record of the same id, read by the adapter's `recorded_output(record)` (the
deployed system's adapter, from --like), else the record's field named by --field. The run is an ordinary run: the
same scorer, references or labels (--labels), fingerprint (the capture's sha256 in its settings) and tests as any
system; its cost is 0 and its speed is not measured. A system of that name is never overwritten.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import sys
from pathlib import Path

import yaml
from evaluation_harness import _jsonout, _store
from evaluation_harness._common import CAPTURES, DATA, ROOT, dataset_id_ok, die, evh_prog, load_dataset


def main() -> int:
    """Write production's recorded system and run it."""
    ap = argparse.ArgumentParser(prog=evh_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--capture", required=True, help="the capture whose records hold production's decisions")
    ap.add_argument(
        "--as", required=True, dest="config_id", help="the system's id (e.g. production_2026_11_v1)"
    )
    ap.add_argument("--like", help="the deployed system, by its id: its adapter is taken")
    ap.add_argument(
        "--field", help="the record's field holding the output, when the adapter has no recorded_output"
    )
    ap.add_argument("--goal", help="the goal its run is measured for")
    ap.add_argument("--labels", metavar="SET", help="score against this label set of the dataset (RFC-023)")
    from evaluation_harness._actor import add_by  # noqa: PLC0415

    add_by(ap)
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("arm-from-capture", args.json, live=sys.stderr):
        load_dataset(args.dataset_id)
        if not _store.is_file(CAPTURES / dataset_id_ok(args.capture) / "capture.json"):
            die(f"no capture {args.capture} (evh captures)", "not-found")
        from evaluation_harness.model.systems import SYSTEM  # noqa: PLC0415

        out = DATA / "systems" / f"{dataset_id_ok(args.config_id)}.yaml"
        if args.config_id in SYSTEM.ids():
            die(
                f"system {args.config_id} exists: a system is not overwritten. Name it another way (--as).",
                "would-overwrite",
            )
        cfg: dict = {"system_id": args.config_id}
        if args.like:
            from evaluation_harness.model.systems import arm_of  # noqa: PLC0415

            like, like_path = arm_of(args.like, args.dataset_id)
            if like.get("adapter"):
                # Written relative to the project (the new system is elsewhere than the one it is like).
                a = (like_path.parent / like["adapter"]).resolve()
                try:
                    cfg["adapter"] = str(a.relative_to(ROOT))
                except ValueError:
                    cfg["adapter"] = str(a)
        if not args.field:
            # Checked before anything is written: a config left behind by a refused run would block the next try.
            from evaluation_harness._adapter import _module_or_none  # noqa: PLC0415

            spec = cfg.get("adapter")
            mod = _module_or_none(
                Path(spec) if spec and Path(spec).is_absolute() else ROOT / spec if spec else None
            )
            if not callable(getattr(mod, "recorded_output", None)):
                die(
                    "a recorded system reads each output with the adapter's recorded_output(record) or from the record's "
                    f"field named by --field; {spec or 'the bundled adapter'} has no recorded_output: pass --field, or --like "
                    "the deployed system",
                    "bad-argument",
                )
        cfg["params"] = {
            "provider": "recorded",
            "capture": args.capture,
            **({"field": args.field} if args.field else {}),
        }
        _store.mkdir(out.parent, parents=True, exist_ok=True)
        _store.write_text(
            out,
            "# Production's recorded decisions as an arm (evh arm-from-capture, RFC-023): no system is called.\n"
            + yaml.safe_dump(cfg, sort_keys=False),
            encoding="utf-8",
        )
        print(f"{out}: the recorded system {args.config_id}, from the capture {args.capture}")
        from evaluation_harness.cli import main as evh  # noqa: PLC0415

        return evh(
            [
                "run",
                "--system",
                args.config_id,
                "--dataset",
                args.dataset_id,
                *(["--goal", args.goal] if args.goal else []),
                *(["--labels", args.labels] if args.labels else []),
            ]
        )


if __name__ == "__main__":
    raise SystemExit(main())
