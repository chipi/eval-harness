"""The licences a dataset most often carries, by SPDX id, a line each (PLAN_0.8.0 E2, owner 2026-11-05).

A dataset's `licence` is optional. When given it is one of these ids, `unknown` (the source states none, as Hugging
Face's `license: unknown`), or a `LicenseRef-<name>` for a licence of its own (SPDX's form for one not on its list),
which the card then describes. The list ships with the package, so `evh licences` works offline; it is a picker, not
legal advice: each line says what the licence lets a user do, and the text at its URL is what binds.
"""

from __future__ import annotations

import re

#: (SPDX id, what it allows in one line). The URL is SPDX's page for the id.
LICENCES: tuple[tuple[str, str], ...] = (
    ("CC0-1.0", "public domain dedication: any use, no conditions"),
    ("PDDL-1.0", "public domain dedication for databases: any use, no conditions"),
    ("CC-BY-4.0", "any use, commercial too, adapted or not; credit the source"),
    ("CC-BY-SA-4.0", "as CC-BY-4.0, and adaptations shared under the same licence"),
    ("CC-BY-SA-3.0", "as CC-BY-SA-4.0, its earlier version (Wikipedia and DBpedia text)"),
    ("CC-BY-NC-4.0", "credit the source; no commercial use"),
    ("CC-BY-NC-SA-4.0", "credit the source; no commercial use; adaptations under the same licence"),
    ("CC-BY-ND-4.0", "credit the source; shared unchanged only"),
    ("CC-BY-NC-ND-4.0", "credit the source; no commercial use; shared unchanged only"),
    ("ODC-By-1.0", "databases: any use; credit the source"),
    ("ODbL-1.0", "databases: any use; credit the source; an adapted database shared under the same licence"),
    ("CDLA-Permissive-2.0", "data: any use, adapted or not; keep the licence with the data you share"),
    ("CDLA-Sharing-1.0", "data: any use; data you share, adapted or not, under the same licence"),
    ("Apache-2.0", "any use, commercial too; keep the notices, state your changes; a patent grant"),
    ("MIT", "any use, commercial too; keep the copyright notice"),
    ("BSD-3-Clause", "any use; keep the notice; the authors' names not used to endorse"),
    ("BSD-2-Clause", "any use; keep the notice"),
    ("GPL-3.0-or-later", "any use; what you distribute built on it, under the GPL with its source"),
    ("LGPL-3.0-or-later", "as GPL-3.0, but a work that only links to it may use another licence"),
    ("MPL-2.0", "any use; changed files of it shared under the MPL"),
)
UNKNOWN = "unknown"
CUSTOM = re.compile(r"^LicenseRef-[A-Za-z0-9.-]+$")
_IDS = {i.lower(): i for i, _ in LICENCES}


def url(licence_id: str) -> str | None:
    """SPDX's page for a listed id; None for `unknown` and a LicenseRef."""
    return f"https://spdx.org/licenses/{licence_id}.html" if licence_id in dict(LICENCES) else None


def canonical(given: str) -> str | None:
    """The licence id as recorded (a listed id in SPDX's spelling, whatever case it was given in, `unknown`, or a
    LicenseRef-...), or None when it is none of these."""
    g = (given or "").strip()
    if g.lower() == UNKNOWN:
        return UNKNOWN
    if CUSTOM.match(g):
        return g
    return _IDS.get(g.lower())


def problem(given: str) -> str | None:
    """Why a licence id is refused, None when it is fine; the refusal names the nearest listed ids."""
    if canonical(given) is not None:
        return None
    near = [i for i, _ in LICENCES if given and given.lower().split("-")[0] in i.lower()][:5]
    return (
        f"licence {given!r} is not on the list (evh licences shows it)"
        + (f"; did you mean {', '.join(near)}?" if near else "")
        + f"; `{UNKNOWN}` when the source states none, LicenseRef-<name> for a licence of its own"
    )
