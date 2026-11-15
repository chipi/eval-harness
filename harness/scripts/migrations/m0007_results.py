"""Format 7, RFC-033: a run's per-item results as a model. The run's settings move onto the run, the provider's billing
object is kept to what is read, and the rows are canonical text.

It reads the stored rows as format 6 kept them, not through the model: each score's `predictions.jsonl` (the files
store) or the rows text the database keeps for it, and the run's run.json. The key names, the slim and the kept usage
keys below are frozen copies of `model/results.py`'s as they are written here; this file imports nothing from `model/`.

- Run settings. For each run, a setting (`generation_config`, `generation_requested`, `encoder_window`) that every row
  of every score of the run holds with one value (canonical JSON) goes to run.json's `call` and leaves the rows. A
  run whose rows differ keeps the setting in its rows; a run that already has a `call` (an interrupted migration) has
  the rows that hold its value cleaned, and rows that hold another value keep it.
- Usage. `_meta.usage` keeps `cost`, `prompt_tokens`, `completion_tokens`, and when nonzero `cached_tokens` and
  `cache_write_tokens` (both read from `prompt_tokens_details`); a `usage` that is not an object is left as it is.
  A usage with no `cost` gets none.
- Rows canonical: `json.dumps(row, sort_keys=True)` and a newline. A score whose rows come out as they went in is not
  written again.
- A SQLite project: for this step the rows in today's `rows` table are rewritten in place, through the same rows API
  the files use (`stored_text` reads them as they were written; `put_rows` writes dicts). The tables RFC-033 adds (score sets, metrics, per-item values, the call's facts) are step d's: it
  extends this step to fill them from that text.

`--dry-run` prints each count; nothing is written. Refused, writing nothing: a run.json whose `call` is not an object,
rows that are not UTF-8, and a line of a score's rows that is not a JSON object with an `item_id` (the store refuses to
write one: correct the file first).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _outputs, _store

NUMBER = 7
ABOUT = "RFC-033: the run's settings once in run.json, the provider's usage slimmed, rows canonical"

RUN_SETTINGS = ("generation_config", "generation_requested", "encoder_window")


def _slim(usage: Any) -> Any:
    """`usage` with only `cost`, `prompt_tokens`, `completion_tokens`, and when nonzero `cached_tokens` and
    `cache_write_tokens` (from `prompt_tokens_details`, or already at the top: slimming twice gives the same)."""
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


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _rel(p: Path) -> str:
    return p.relative_to(_common.DATA).as_posix()


def _dump_like(text: str, doc: Any) -> Any:
    """How run.json was written: the first of the layouts the harness writes that gives `text` back from its parsed
    document. Returns a function that writes a document that way (indent 2, keys in order, when none does)."""
    for sort in (False, True):
        for ascii_ in (False, True):
            kw: dict[str, Any] = {"indent": 2, "sort_keys": sort, "ensure_ascii": ascii_}
            if json.dumps(doc, **kw) + "\n" == text:
                return lambda d, kw=kw: json.dumps(d, **kw) + "\n"
    return lambda d: json.dumps(d, indent=2, ensure_ascii=False) + "\n"


def _lines(text: str) -> list[tuple[str, Any]]:
    """(line, its row or None) for each line of a rows text; a row is a JSON object."""
    out = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            row = None
        out.append((line, row if isinstance(row, dict) else None))
    return out


def _held(run: Path, refused: list[str]) -> tuple[Any, dict[str, Any], str | None]:
    """(run.json's document, its `call`, its text); (None, {}, None) when it has none."""
    p = run / "run.json"
    if not _store.is_file(p):
        return None, {}, None
    text = _store.read_text(p, encoding="utf-8")
    try:
        doc = json.loads(text)
    except ValueError:
        return None, {}, None
    if not isinstance(doc, dict):
        return None, {}, None
    call = doc.get("call", {})
    if not isinstance(call, dict):
        refused.append(f"{_rel(p)}: `call` is not an object")
        return None, {}, None
    return doc, call, text


def plan() -> dict[str, Any]:
    """{"changes": [(run.json path, text, [(rows path, text)])], "counts": Counter, "refused": [...]}; reads only."""
    runs_dir = _common.DATA / "runs"
    changes: list[tuple[Path, str | None, list[tuple[Path, str]]]] = []
    counts: Counter[str] = Counter()
    refused: list[str] = []
    store = _outputs.store()
    for run in sorted(_store.iterdir(runs_dir)) if _store.is_dir(runs_dir) else []:
        if not _store.is_dir(run):
            continue
        doc, call, run_text = _held(run, refused)
        sets: list[tuple[Path, list[tuple[str, Any]]]] = []
        sdir = run / "scores"
        for sd in sorted(_store.iterdir(sdir)) if _store.is_dir(sdir) else []:
            try:
                text = store.stored_text(sd)
            except UnicodeDecodeError as exc:
                refused.append(f"{_rel(sd)}: its rows are not UTF-8 ({exc.reason})")
                continue
            if text is not None:
                lines = _lines(text)
                bad = [
                    n
                    for n, (_l, row) in enumerate(lines, 1)
                    if row is None or not isinstance(row.get("item_id"), str)
                ]
                if bad:
                    refused.append(
                        f"{_rel(sd)}: line {bad[0]}{f' (and {len(bad) - 1} more)' if len(bad) > 1 else ''} is not a "
                        "JSON object with an item_id"
                    )
                    continue
                sets.append((sd, lines))
        # a setting is the run's when every row of every score holds one value for it
        new_call = dict(call)
        if doc is not None:
            for k in RUN_SETTINGS:
                if k in call:
                    continue
                seen: set[str] = set()
                first: Any = None
                everywhere = bool(sets)
                for _sd, lines in sets:
                    for _line, row in lines:
                        if row is None:
                            continue
                        meta = row.get("_meta")
                        if not isinstance(meta, dict) or k not in meta:
                            everywhere = False
                            break
                        if not seen:
                            first = meta[k]
                        seen.add(_canon(meta[k]))
                        if len(seen) > 1:
                            everywhere = False
                            break
                    if not everywhere:
                        break
                if everywhere and len(seen) == 1:
                    new_call[k] = first
                    counts[f"run setting {k}, runs"] += 1
        run_sets: list[tuple[Path, str]] = []
        for sd, lines in sets:
            out: list[str] = []
            changed = False
            lost = slimmed = False
            for line, row in lines:
                if row is None:
                    out.append(line + "\n")
                    continue
                new = row
                meta = new.get("_meta")
                if isinstance(meta, dict):
                    drop = [
                        k
                        for k in RUN_SETTINGS
                        if k in new_call and k in meta and _canon(meta[k]) == _canon(new_call[k])
                    ]
                    if "usage" in meta:
                        usage = _slim(meta["usage"])
                        if _canon(usage) != _canon(meta["usage"]):
                            counts["usage objects slimmed"] += 1
                            meta = {**meta, "usage": usage}
                            slimmed = True
                        if isinstance(usage, dict) and "cost" not in usage:
                            counts["usage objects without a cost (kept without one)"] += 1
                    if drop:
                        meta = {k: v for k, v in meta.items() if k not in drop}
                        for k in drop:
                            counts[f"run setting {k}, rows"] += 1
                        lost = True
                    new = {**new, "_meta": meta}
                text = _canon(new) + "\n"
                if text != line + "\n":
                    changed = True
                    if new is row or _canon(new) == _canon(row):
                        counts["rows made canonical"] += 1
                out.append(text)
            if changed:
                run_sets.append((sd, "".join(out)))
                counts["score sets rewritten"] += 1
                if lost:
                    counts["score sets that lost a run setting"] += 1
                if slimmed:
                    counts["score sets with usage slimmed"] += 1
        call_new = new_call != call
        if call_new and doc is not None and run_text is not None:
            new_doc = {**doc, "call": new_call}
            counts["run.json given a call"] += 1
            changes.append((run / "run.json", _dump_like(run_text, doc)(new_doc), run_sets))
        elif run_sets:
            changes.append((run / "run.json", None, run_sets))
    return {"changes": changes, "counts": counts, "refused": refused}


def run(dry_run: bool) -> None:
    """Hoist the run settings, slim the usage, make the rows canonical; refuse first, writing nothing."""
    p = plan()
    if p["refused"]:
        _common.die("runs this step cannot read:\n  " + "\n  ".join(p["refused"]), "invalid-file")
    if not p["changes"]:
        print("  0 changed: already in this format")
        return
    for kind, n in sorted(p["counts"].items()):
        print(f"    {n:>7}  {kind}")
    if dry_run:
        return
    store = _outputs.store()
    for path, text, row_sets in p["changes"]:
        if text is not None:  # run.json first: a score's rows only lose a setting once the run holds it
            _common.write_text_atomic(path, text)
        for sd, text in row_sets:
            rows, _skipped = _outputs.parse_rows(text, _rel(sd))
            store.put_rows(sd, rows)
