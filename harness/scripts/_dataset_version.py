"""A dataset's content version, MAJOR.MINOR (PLAN_0.8.0 E3, owner 2026-11-05).

The id is the identity; the version says how far the items moved along a lineage. Two integers, so 1.10 follows
1.9. A dataset made from nothing (a folder, a manifest, a capture) is 1.0. Made from another (`derived_from`):
only items added is the parent's MAJOR, MINOR + 1; any item removed or changed is MAJOR + 1, MINOR 0; the same
items under a new id keep the parent's version. A side of a split is a new dataset, 1.0, whatever it removed: a
split removes by design. A card, licence or description change is no new version (the items are the same). A
source's own version is `source.revision`, never this.
"""

from __future__ import annotations

import re
from typing import Any

FIRST = "1.0"
VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def parse(v: Any) -> tuple[int, int] | None:
    """(MAJOR, MINOR) of a version string, None when it is not one."""
    m = VERSION.match(str(v)) if isinstance(v, str) else None
    return (int(m.group(1)), int(m.group(2))) if m else None


def next_version(parent_version: Any, lineage: dict[str, Any] | None) -> str:
    """The version a dataset made from a parent at `parent_version` gets, given what changed (`derived_from`)."""
    major, minor = parse(parent_version) or (1, 0)
    if not lineage:
        return FIRST
    if lineage.get("removed") or lineage.get("changed"):
        return f"{major + 1}.0"
    if lineage.get("added"):
        return f"{major}.{minor + 1}"
    return f"{major}.{minor}"


def expected(doc: dict[str, Any], version_of: Any) -> str:
    """The version a dataset record should carry, from its own lineage. `version_of(dataset_id)` gives a parent's
    stored version (None when the parent is gone: then its version is taken as 1.0)."""
    if doc.get("split"):
        return FIRST
    lin = doc.get("derived_from")
    if not lin:
        return FIRST
    return next_version(version_of(lin.get("dataset_id")), lin)
