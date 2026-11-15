"""A run's per-item results as a model (RFC-033): what a row's `_meta` holds that is the run's, what is the call's, and
what of the provider's billing object is kept.

    run settings   `generation_config`, `generation_requested`, `encoder_window`: the run's, not an item's. A run whose
                   rows all hold one value for a setting keeps it once, in run.json's `call`, and not in its rows.
    call facts     what one call was (`CALL_META` less the run settings): provider, response_model, usage, ...
    usage          the provider's billing object, slimmed to what is read: `cost`, `prompt_tokens`,
                   `completion_tokens`, and when nonzero `cached_tokens` and `cache_write_tokens`.

`CALL_META` is also what a release keeps of a hidden dataset's `_meta` (`_release.py`). Nothing here reads the store:
`_outputs` applies `prepare` on every write of a score's rows, `migrations/m0007_results.py` keeps its own frozen copy
of all of this, as a migration must.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

#: What a hidden dataset's prediction rows keep of `_meta`: what describes the call (its cost, model, finish), never what
#: the system answered or the parser made of it (`predicted`, `llm_raw`, ...).
CALL_META = (
    "provider",
    "response_model",
    "usage",
    "finish_reason",
    "reasoning_tokens_reported",
    "system_fingerprint",
    "generation_config",
    "generation_requested",
    "encoder_window",
    "resumed_from_disk",
)
#: The run's settings among them: constant over a run, so run.json's `call` keeps each once.
RUN_SETTINGS = ("generation_config", "generation_requested", "encoder_window")
#: What a slimmed `usage` holds: the first three as the provider gave them, the others when nonzero.
USAGE_KEPT = ("cost", "prompt_tokens", "completion_tokens", "cached_tokens", "cache_write_tokens")


def slim_usage(usage: Any) -> Any:
    """`usage` with only what is read. `cached_tokens` and `cache_write_tokens` come from `prompt_tokens_details` (or
    are already at the top, so slimming twice gives the same); `None` and anything that is not a dict pass through."""
    if not isinstance(usage, dict):
        return usage
    out = {k: usage[k] for k in ("cost", "prompt_tokens", "completion_tokens") if k in usage}
    details = usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    for k in ("cached_tokens", "cache_write_tokens"):
        v = usage.get(k) or details.get(k)
        if v:
            out[k] = v
    return out


def _same(a: Any, b: Any) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def slim_row(row: dict[str, Any]) -> dict[str, Any]:
    """The row with its `_meta.usage` slimmed (the row itself when there is nothing to slim)."""
    meta = row.get("_meta")
    if not isinstance(meta, dict) or "usage" not in meta:
        return row
    usage = slim_usage(meta["usage"])
    if _same(usage, meta["usage"]):
        return row
    return {**row, "_meta": {**meta, "usage": usage}}


def run_call(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The run settings every one of `rows` holds, with one value, in its `_meta`: {setting: value}. A setting a row
    lacks, or holds with another value, is not the run's, so it is left in the rows."""
    first: dict[str, Any] = {}
    alive = set(RUN_SETTINGS)
    n = 0
    for row in rows:
        n += 1
        meta = row.get("_meta")
        meta = meta if isinstance(meta, dict) else {}
        for k in list(alive):
            if k not in meta or (k in first and not _same(first[k], meta[k])):
                alive.discard(k)
            elif k not in first:
                first[k] = meta[k]
    return {k: first[k] for k in RUN_SETTINGS if n and k in alive and k in first}


def strip_call(row: dict[str, Any], call: dict[str, Any] | None) -> dict[str, Any]:
    """The row without the run settings it holds with the run's own value; one that differs stays."""
    meta = row.get("_meta")
    if not call or not isinstance(meta, dict):
        return row
    same = [k for k in RUN_SETTINGS if k in call and k in meta and _same(call[k], meta[k])]
    if not same:
        return row
    return {**row, "_meta": {k: v for k, v in meta.items() if k not in same}}


def prepare(row: dict[str, Any], call: dict[str, Any] | None = None) -> dict[str, Any]:
    """A row as it is written: usage slimmed, the run settings the run holds taken off."""
    return strip_call(slim_row(row), call)


def problems(row: Any, call: dict[str, Any] | None = None) -> list[str]:
    """What a stored row holds that format 7 does not: a run setting equal to its run's `call`, a `usage` key outside
    `USAGE_KEPT`. [] for a row that is not an object with a `_meta` object."""
    meta = row.get("_meta") if isinstance(row, dict) else None
    if not isinstance(meta, dict):
        return []
    out = [
        f"_meta.{k} equals its run's call.{k}"
        for k in RUN_SETTINGS
        if call and k in call and k in meta and _same(call[k], meta[k])
    ]
    usage = meta.get("usage")
    if isinstance(usage, dict):
        out += [f"_meta.usage.{k} is not kept" for k in usage if k not in USAGE_KEPT]
    return out
