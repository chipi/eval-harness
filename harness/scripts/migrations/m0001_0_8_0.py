"""Format 1, 0.8.0: the four steps 0.8.0 shipped before the format existed, in their order (runs, datasets, records,
fingerprints), each recognising its old data by its shape. The data any release before 0.8.0 wrote is format 0."""

from __future__ import annotations

from evaluation_harness import baselines_migrate, dataset_migrate, fingerprint_migrate, run_migrate

NUMBER = 1
ABOUT = "0.8.0: runs in one outputs.jsonl, dataset versions and sources, records per goal with who acted, fingerprints at 5"

#: The records step comes before the fingerprints step: a baseline's hash is updated where the records step puts it.
PARTS = (
    ("runs", run_migrate.step),
    ("datasets", dataset_migrate.step),
    ("records", baselines_migrate.step),
    ("fingerprints", fingerprint_migrate.step),
)


def run(dry_run: bool) -> None:
    """The four parts in their order, each printing what it changes, writing nothing when `dry_run`."""
    for name, step in PARTS:
        print(f"  {name}:")
        step(dry_run)
