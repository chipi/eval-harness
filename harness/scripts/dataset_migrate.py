"""Bring the project's dataset records to this release's format, once (idempotent).

The datasets step of `evh migrate` (`--dry-run`: what would change, per dataset).

0.8.0 (PLAN_0.8.0 E3): each record's `version` is recomputed from its lineage (MAJOR.MINOR: 1.0 made from
nothing or a side of a split; from a parent, MINOR + 1 when items were only added, MAJOR + 1 when any was removed or
changed), parents first, and a split side records its parent's version. E1: a record without a `source` gets the
one its committed profile recorded (data/profiles/<id>.json: name, url, config, split, and per item the source's page
for its row), as the source block and each item's `source_row`, and the profile's `source` becomes the same block.
Nothing unrecorded is guessed: `revision`, `gated` and `description_sha256` stay null. The items' ids and hashes, and
so every run measured on them, are untouched: none of these keys is in a run's fingerprint. `validate` (V22) then
holds the records to the format.
"""

from __future__ import annotations

from typing import Any

from evaluation_harness import _dataset_version, _source, _store
from evaluation_harness._common import DATA, DATASETS, read_json, write_json

PROFILES = DATA / "profiles"


def _order(docs: dict[str, dict[str, Any]]) -> list[str]:
    """Dataset ids, every parent before the datasets made from it (a parent that is gone counts as a root)."""

    def parent(i: str) -> str | None:
        d = docs[i]
        p = (d.get("split") or {}).get("from") or (d.get("derived_from") or {}).get("dataset_id")
        return p if p in docs and p != i else None

    out: list[str] = []
    seen: set[str] = set()
    for i in sorted(docs):
        chain = []
        while i and i not in seen:
            seen.add(i)
            chain.append(i)
            i = parent(i)  # type: ignore[assignment]
        out.extend(reversed(chain))
    return out


def migrate(
    docs: dict[str, dict[str, Any]], profiles: dict[str, dict[str, Any]] | None = None
) -> dict[str, list[str]]:
    """The records (and their profiles) brought to the format, in place: {dataset_id: [what changed]}."""
    changes: dict[str, list[str]] = {}

    def version_of(i: str | None) -> str | None:
        return (docs.get(i) or {}).get("version") if i else None

    for i in _order(docs):
        d, said = docs[i], []
        if d.get("split"):
            pv = version_of(d["split"].get("from"))
            if d["split"].get("from_version") != pv:
                d["split"]["from_version"] = pv
                said.append(f"split.from_version {pv}")
        v = _dataset_version.expected(d, version_of)
        if d.get("version") != v:
            said.append(f"version {d.get('version')!r} -> {v}")
            d["version"] = v
        prof = profiles.get(i) if profiles is not None else None
        if prof is not None and not d.get("source"):
            src, rows = _source.from_profile(prof)
            if src:
                d["source"] = src
                for it in d.get("items") or []:
                    if it["item_id"] in rows:
                        it["source_row"] = rows[it["item_id"]]
                said.append(
                    f"source {src.get('provider')} {src.get('ref')}, {len(rows)} item row(s) from its profile"
                )
        if prof is not None and d.get("source") and prof.get("source") and prof["source"] != d["source"]:
            prof["source"] = d["source"]
            said.append("profile source: the record's block")
        if said:
            changes[i] = said
    return changes


def step(dry_run: bool) -> None:
    """`evh migrate`'s datasets step: every dataset record under data/datasets/."""
    files = {f.stem: f for f in sorted(_store.glob(DATASETS, "*.json"))} if _store.is_dir(DATASETS) else {}
    docs = {i: read_json(f) for i, f in files.items()}
    pfiles = {i: PROFILES / f"{i}.json" for i in docs if _store.is_file(PROFILES / f"{i}.json")}
    profiles = {i: read_json(p) for i, p in pfiles.items()}
    before = {i: dict(p).get("source") for i, p in profiles.items()}
    changes = migrate(docs, profiles)
    for i, said in changes.items():
        print(f"{i}: {'; '.join(said)}")
        if not dry_run:
            write_json(files[i], docs[i])
            if i in profiles and profiles[i].get("source") != before[i]:
                write_json(pfiles[i], profiles[i])
    verb = "would change" if dry_run else "changed"
    print(f"{len(files)} dataset(s), {len(changes)} {verb}" + ("" if changes else ": already in this format"))
