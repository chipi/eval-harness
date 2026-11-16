"""Add a field a held-out side's counts may be grouped by (RFC-031 H2): a person's decision, recorded.

    evh dataset-seal-counts --dataset-id triage_v1_test --add gate --reason "the safety watch needs which gate fired"

The fields were fixed when the side was sealed (`dataset-split --seal --count-by`), so whoever reads the counts does
not choose what they show. Adding one is a person's command with a reason, kept on the record beside who and when;
an agent is refused. Nothing is ever removed.
"""

from __future__ import annotations

from typing import Any

from evaluation_harness import _exposure, _jsonout
from evaluation_harness._common import DATASETS, die, load_dataset, now, read_json, write_json
from evaluation_harness.ops import legacy
from evaluation_harness.sealed_counts import allowed


def body(**inputs: Any) -> int:
    """Add a field."""
    args = legacy.namespace(inputs, "dataset-seal-counts")
    from evaluation_harness._actor import require_named  # noqa: PLC0415

    who = require_named("widening what a held-out side's counts show")
    if who["type"] != "person":
        die(
            "what a held-out side's counts may show is a person's decision: an agent is refused",
            "not-allowed",
        )
    if not _exposure.applies(args.dataset_id):
        die(f"{args.dataset_id} is not a held-out side (no seal)", "not-allowed")
    if args.add in allowed(args.dataset_id):
        print(f"{args.dataset_id}: {args.add} is already allowed")
        return 0
    doc = load_dataset(args.dataset_id)
    if not any(args.add in (it.get("fields") or {}) for it in doc["items"]):
        die(f"no item of {args.dataset_id} has the field {args.add}", "not-found")
    path = DATASETS / f"{args.dataset_id}.json"
    rec = read_json(path)
    rec["sealed"].setdefault("count_by_added", []).append(
        {"field": args.add, "at": now(), "reason": args.reason, "actor": who}
    )
    write_json(path, rec)
    print(f"{args.dataset_id}: counts may now be grouped by {args.add} ({args.reason})")
    _jsonout.values({"dataset_id": args.dataset_id, "allowed": allowed(args.dataset_id)})
    return 0
