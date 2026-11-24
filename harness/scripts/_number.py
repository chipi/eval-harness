"""The one rule for a score that is not a number, on read as on write (RFC-041 F7, owner 2026-11-23).

A score that is not a number (NaN, an infinity, None) is a failed item, scored 0. `evh run` records it so, and names it
(`_record.non_number`); a run recorded before that can hold one, and every reader counts it the same: `_runs.score_of`,
`model.runs.record`, `stats` (the sign-flip tests and `compare`). Standard library only, and no import of the package:
`stats` and `model.runs` import it, and `_common` loads the project's .env when it is first imported.
"""

from __future__ import annotations

import math
from typing import Any


def is_number(v: Any) -> bool:
    """Whether a recorded score is a number: an int or a float that is finite, never a boolean."""
    # the tests read a million values a catalog build: a plain float or int is answered before the general rule
    t = type(v)
    if t is float:
        return math.isfinite(v)
    if t is int:
        return True
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def is_scored(v: Any) -> bool:
    """Whether a row's field holds a score at all: a number, or a value that is a score that is not a number (NaN, an
    infinity, None). A boolean, text or a list is no item's score: the item is not scored on it."""
    t = type(v)
    if t is float or t is int:
        return True
    return v is None or (not isinstance(v, (bool, str, list, dict)) and isinstance(v, (int, float)))


def counted(v: Any) -> float:
    """What a recorded score counts as: its own value when it is a number, 0.0 when it is not (NaN, an infinity, None):
    the score of a failed item, as `evh run` records an item whose score is not a number."""
    t = type(v)
    if t is float:
        return v if math.isfinite(v) else 0.0
    if t is int:
        return float(v)
    return float(v) if is_number(v) else 0.0
