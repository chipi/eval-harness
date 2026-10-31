"""Whether text from a dataset may be shown publicly (RFC-019 §4): `text: hidden` on a dataset.

A dataset whose file says `"text": "hidden"` shows no text that comes from it on any public surface:
its items' sources, every arm's outputs on it, its references' texts and per-item labels, judge
reasons, its items' source links, and its text and URL field values. Counts, scores, ids and the
totals of public fields stay. A person's own local views show everything, as before.

Every public surface asks `text_shown(dataset_id, public=...)`: the catalog's pages (always public:
they are what gets published), the inspector and MCP in public mode, `evh dataset-items` and
`evh inspect` under EVH_PUBLIC, and a deployment's copy of the data (_release.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from evaluation_harness._common import DATASETS

_CACHE: dict[str, tuple[float, bool]] = {}


def hidden(dataset_id: str | None, datasets_dir: Path | None = None) -> bool:
    """True when the dataset's file says `"text": "hidden"`. A dataset this project does not have
    is not hidden (nothing of its text is here to show)."""
    if not dataset_id:
        return False
    f = (datasets_dir or DATASETS) / f"{dataset_id}.json"
    try:
        mtime = f.stat().st_mtime
    except OSError:
        return False
    key = str(f)
    if key not in _CACHE or _CACHE[key][0] != mtime:
        try:
            _CACHE[key] = (mtime, json.loads(f.read_text(encoding="utf-8")).get("text") == "hidden")
        except (OSError, ValueError):
            _CACHE[key] = (mtime, False)
    return _CACHE[key][1]


def public_env() -> bool:
    """A command run by a public server (MCP --public sets EVH_PUBLIC for its child processes)."""
    return bool(os.environ.get("EVH_PUBLIC"))


def public_profile(p: dict) -> dict:
    """A hidden dataset's profile as a public surface may show it: per item its id and length only;
    the source link, the text, the per-item labels and links gone; the gold's shape (counts) kept."""
    return {
        **{k: v for k, v in p.items() if k not in ("rows", "source")},
        "rows": [
            {"item_id": r["item_id"], "words": r.get("words"), "reference": {}} for r in p.get("rows") or []
        ],
        "text_hidden": True,
    }


def text_shown(dataset_id: str | None, *, public: bool) -> bool:
    """May text derived from this dataset be shown? Always locally; publicly unless it is hidden."""
    return not (public and hidden(dataset_id))
