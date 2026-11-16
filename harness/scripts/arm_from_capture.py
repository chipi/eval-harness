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

from pathlib import Path
from typing import Any

import yaml
from evaluation_harness import _store
from evaluation_harness._common import CAPTURES, DATA, ROOT, dataset_id_ok, die, load_dataset
from evaluation_harness.ops import legacy


def body(**inputs: Any) -> int:
    """Write production's recorded system and run it."""
    args = legacy.namespace(inputs, "arm-from-capture", {"as": "system_id"})
    load_dataset(args.dataset_id)
    if not _store.is_file(CAPTURES / dataset_id_ok(args.capture) / "capture.json"):
        die(f"no capture {args.capture} (evh capture-list)", "not-found")
    from evaluation_harness.model.systems import SYSTEM  # noqa: PLC0415

    out = DATA / "systems" / f"{dataset_id_ok(args.system_id)}.yaml"
    if args.system_id in SYSTEM.ids():
        die(
            f"system {args.system_id} exists: a system is not overwritten. Name it another way (--as).",
            "would-overwrite",
        )
    cfg: dict = {"system_id": args.system_id}
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
        # Checked before anything is written: a system left behind by a refused run would block the next try.
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
    print(f"{out}: the recorded system {args.system_id}, from the capture {args.capture}")
    from evaluation_harness.cli import main as evh  # noqa: PLC0415

    return evh(
        [
            "run",
            "--system",
            args.system_id,
            "--dataset",
            args.dataset_id,
            *(["--goal", args.goal] if args.goal else []),
            *(["--labels", args.labels] if args.labels else []),
        ]
    )
