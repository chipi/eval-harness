"""A reference's manifest (data/references/<tier>/<dataset>/manifest.json, schemas/reference.schema.json):
what the reference is and, item by item, the checksum of its text.

The manifest is committed even when the text is not: gold this repository does not redistribute
is rebuilt byte for byte by a fetch script, and the manifest is how anyone proves they rebuilt
the same thing (validate's V16).
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import hashlib
from pathlib import Path
from typing import Any

from evaluation_harness import _store
from evaluation_harness._common import write_json

#: What each tier is, said wherever a number scored against it is shown.
CAVEATS = {
    "gold": "GOLD: the answers a decision rests on.",
    "silver": (
        "SILVER: consistent, not a claim that any arm is right. Good enough to RANK arms against each other; "
        "say so wherever a number scored against it is published."
    ),
}


def item_hashes(ref_dir: Path) -> dict[str, str]:
    """{item_id: sha256 of its text} for the reference texts present in `ref_dir`."""
    return {
        f.stem: hashlib.sha256(_store.read_bytes(f)).hexdigest()
        for f in sorted(_store.glob(ref_dir, "*.txt"))
    }


def write_manifest(
    ref_dir: Path, tier: str, dataset_id: str, caveat: str | None = None, **extra: Any
) -> dict[str, Any]:
    """Write the manifest of the reference texts in `ref_dir`, with `extra` fields (the promotion: promoted_from,
    reason, promoted_by; for a model's labels authored_by, model, from_run; source, redistributed, created_at);
    return it. `caveat` replaces the tier's own words: reference-promote and reference-manifest name where the
    labels came from."""
    hashes = item_hashes(ref_dir)
    doc = {
        "dataset_id": dataset_id,
        "tier": tier,
        **extra,
        "n_items": len(hashes),
        "items_sha256": hashes,
        "caveat": caveat or CAVEATS[tier],
    }
    write_json(ref_dir / "manifest.json", doc)
    return doc


def drift(ref_dir: Path, manifest: dict[str, Any]) -> dict[str, list[str]]:
    """How the texts present differ from the manifest: {"changed", "extra", "missing"} item ids.
    No text at all is not drift (a reference fetched elsewhere); a partial set is."""
    want = manifest.get("items_sha256") or {}
    have = item_hashes(ref_dir)
    if not have:
        return {"changed": [], "extra": [], "missing": []}
    return {
        "changed": sorted(i for i in have if i in want and have[i] != want[i]),
        "extra": sorted(set(have) - set(want)),
        "missing": sorted(set(want) - set(have)),
    }
