"""What a dataset source holds, before a dataset is made from it (the Workbench's step 2a/2b; owner, 2026-11-17).

    evh source-preview --source huggingface --query '{"ref": "abisee/cnn_dailymail", "config": "3.0.0", "split": "test"}'

The source's own description (`describe`: where it is pinned, its licence, card, features) and its first items as the
source gives them (`items`: the id, the text cut to a few hundred characters, or the file or URL it points at, the
row and the fields), the same reading `evh dataset-create --source` does, with nothing written under data/. An
operation run as a job (`POST /api/v1/source-previews`): a public source is read over the network.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

from evaluation_harness import _jsonout, _sources, _store
from evaluation_harness._common import die
from evaluation_harness.ops import legacy

#: How much of an item's text a preview shows.
TEXT_CHARS = 600


def body(**inputs: Any) -> int:
    """Read the source's description and its first items; print them and give them as values."""
    args = legacy.namespace(inputs, "source-preview")
    try:
        query = json.loads(args.query or "{}")
    except ValueError as e:
        die(f"--query is not JSON: {e}", "bad-argument")
    if not isinstance(query, dict):
        die("--query is a JSON object", "bad-argument")
    cls, _path = _sources.resolve(args.source)
    src = cls({})
    try:
        said = src.describe(query) or {}
        items = src.items(query)
        try:
            first = list(itertools.islice(items, args.rows))
        finally:
            # A source read only in part is closed here: a generator left suspended was finalized at the interpreter's
            # exit, after pyarrow's runtime, and the process aborted (CI on e02a0989e: the first preview of a Hub split).
            close = getattr(items, "close", None)
            if close:
                close()
    except (ValueError, OSError) as e:
        die(f"--source {args.source}: {e}", "invalid-file")
    rows = [_row(it) for it in first]
    print(f"{args.source}: {json.dumps(said.get('source') or {}, sort_keys=True)}")
    if said.get("licence"):
        print(f"  licence {said['licence']}")
    if said.get("features"):
        print("  columns " + ", ".join(f"{k} ({v})" for k, v in said["features"].items()))
    for r in rows:
        shown = r.get("text") or r.get("file") or r.get("source_url") or ""
        print(f"  {r['item_id']}: {shown[:120]!r}" + (f"  fields {r['fields']}" if r.get("fields") else ""))
    print(f"  {len(rows)} item(s) shown; nothing written")
    _jsonout.values({"source": args.source, "described": said, "items": rows, "written": False})
    return 0


def _row(it: dict[str, Any]) -> dict[str, Any]:
    """One item as a preview shows it: its id, its text cut to TEXT_CHARS (with its full length), or the file or URL
    it points at; its row and fields."""
    out: dict[str, Any] = {"item_id": str(it.get("item_id") or "")}
    if it.get("text") is not None:
        text = str(it["text"])
        out.update(text=text[:TEXT_CHARS], chars=len(text))
    elif it.get("file"):
        f = Path(str(it["file"]))
        out["file"] = f.name
        try:
            text = _store.read_bytes(f).decode("utf-8")
            out.update(text=text[:TEXT_CHARS], chars=len(text))
        except (OSError, UnicodeDecodeError):
            pass
    elif it.get("source_url"):
        out["source_url"] = str(it["source_url"])
    if it.get("answer") is not None:
        out["answer"] = str(it["answer"])[:TEXT_CHARS]
    for k in ("row", "fields"):
        if it.get(k) not in (None, {}, ""):
            out[k] = it[k]
    return out
