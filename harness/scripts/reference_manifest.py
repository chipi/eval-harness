"""Promote the labels a script builds (a fetch script's gold) where they are, and write their manifest.

    evh reference-manifest --reference-id gold/<dataset> --source examples/<example>/fetch.py \\
        --labelled-by "the dataset's authors" --reason "…" --by <you> [--not-redistributed]

A reference is made only by promoting labels (ADR-0022). Labels a script fetches are not a label set here (their
text may not be redistributed), so this records the promotion in the manifest itself: whose labels they are (the
source, `--labelled-by` and `--kind`, and how they are built, `--source`), why they are the yardstick and who
said so. The manifest (schemas/reference.schema.json) also holds the checksum of every item's text and is committed
even when the text is not: anyone who rebuilds the reference proves they rebuilt the same one (validate's V16).
Labels a person, a model or a rule gives in the harness are promoted with `evh reference-promote`.
"""

from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness._actor import stated
from evaluation_harness._common import die, now
from evaluation_harness._label_sets import source_line
from evaluation_harness._references import write_manifest
from evaluation_harness.ops import legacy
from evaluation_harness.reference_promote import CAVEAT


def body(**inputs: Any) -> int:
    """Write the manifest of the named reference from the texts in its directory."""
    args = legacy.namespace(inputs, "reference-manifest")
    args.by = stated("evh reference-manifest")
    if len(args.reason.split()) < 3:
        die(
            'REFUSED: --reason must be a sentence, not a word. It answers "why is this the yardstick?" later.',
            "bad-argument",
        )
    tier, _, name = args.reference_id.partition("/")
    if tier not in ("gold", "silver") or not name:
        die(f"--reference-id {args.reference_id!r}: expected gold/<name> or silver/<name>", "bad-argument")
    dataset_id = args.dataset_id or name
    ref_dir = _common.DATA / "references" / tier / name
    if not any(_store.glob(ref_dir, "*.txt")):
        die(f"{ref_dir} has no reference texts: build them first ({args.source})", "not-found")
    source = {"kind": args.kind, "by": args.labelled_by, "via": args.source}
    doc = write_manifest(
        ref_dir,
        tier,
        dataset_id,
        caveat=CAVEAT[tier].format(set="the labels its script fetches", source=source_line(source)),
        source=args.source,
        redistributed=not args.not_redistributed,
        created_at=now(),
        promoted_from={"labels": None, "dataset_id": dataset_id, "source": source},
        reason=args.reason,
        promoted_by=args.by,
    )
    print(
        f"{ref_dir / 'manifest.json'}  ({doc['n_items']} item(s), {tier}, promoted from {source_line(source)})"
    )
    return 0
