"""Format 6, RFC-032 step 8: a run's `config_id` names its system, so the stored key is `system_id` ("config" is no
longer the name of anything). Every stored record whose key is not part of a hash is renamed.

It reads the stored files as format 5 kept them, not through the model:

- Renamed: a run's run.json and a score's metrics.json (and the `unset` list of its score.json), a faithfulness
  record (`data/faithfulness/<model>/<n>.json`), a study log's lines (`data/studies/<goal>/<id>.events.jsonl`) and a
  sealed dataset's unseals (`unsealed` in `data/datasets/<id>.json`). Each file is written as it was (its keys in the
  order it kept, its layout), only the key changed.
- Kept: `fingerprint.arm.config_id` (the fingerprint is hashed whole), a judging set's `arms[].config_id` (the set's id
  is a hash of its content), a label set's `source.config_id` (a set is hashed whole into every fingerprint of a run
  scored against it) and a reference manifest's `from_run.config_id` and `promoted_from.source.config_id` (`from_run`
  is hashed with the reference; `promoted_from.source` is a copy of the label set's source).

Refused, writing nothing: a record holding both keys, and a value that is not the id of a system of the project (a
study's imported trials, which name none, are not).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store

NUMBER = 6
ABOUT = "RFC-032 step 8: a run's config_id is its system_id in every stored record that is not hashed"

OLD, NEW = "config_id", "system_id"


def _rename(doc: dict[str, Any]) -> dict[str, Any]:
    """The record with its `config_id` key named `system_id`, in the same place."""
    return {(NEW if k == OLD else k): v for k, v in doc.items()}


def _dump_like(text: str, doc: Any, *, line: bool = False) -> Any:
    """How `text` was written: the first of the layouts the harness writes that gives `text` back from its parsed
    document. Returns a function that writes a document that way (a plain indented dump when none does)."""
    layouts: list[dict[str, Any]] = [
        {"indent": None if line else 2, "sort_keys": s, "ensure_ascii": a}
        for s in (True, False)
        for a in (True, False)
    ]
    tail = "" if line else "\n"
    for kw in layouts:
        if json.dumps(doc, default=str, **kw) + tail == text:
            return lambda d, kw=kw: json.dumps(d, default=str, **kw) + tail
    plain: dict[str, Any] = {"indent": None if line else 2, "sort_keys": False, "ensure_ascii": False}
    return lambda d: json.dumps(d, default=str, **plain) + tail


def _json(p: Path) -> tuple[str, Any]:
    text = _store.read_text(p, encoding="utf-8")
    try:
        return text, json.loads(text)
    except ValueError:
        return text, None


def _systems() -> set[str]:
    return {f.stem for f in _common.system_files()}


def _check(
    where: str,
    rec: dict[str, Any],
    systems: set[str],
    refused: list[str],
    *,
    imported: bool = False,
    keep: bool = False,
) -> bool:
    """Whether `rec` carries the old key; refuses a record holding both and a value that is no system's id, unless
    `keep` (an imported run: `evh import-run` writes a system_id that names no system file)."""
    if OLD not in rec:
        return False
    if NEW in rec:
        refused.append(f"{where}: has both `{OLD}` and `{NEW}`")
        return False
    value = rec[OLD]
    if imported and not value:
        return True
    if keep and isinstance(value, str) and value:
        return True
    if not isinstance(value, str) or value not in systems:
        refused.append(f"{where}: `{OLD}` is {value!r}, which is not the id of a system of this project")
        return False
    return True


def _rel(p: Path) -> str:
    return p.relative_to(_common.DATA).as_posix()


def plan() -> dict[str, Any]:
    """{"changes": [(file, new text)], "counts": {kind: files}, "refused": [...]}; reads the stored records only."""
    systems = _systems()
    changes: list[tuple[Path, str]] = []
    counts: Counter[str] = Counter()
    refused: list[str] = []

    def whole(p: Path, kind: str, fix: Any) -> None:
        """A JSON file whose `fix(doc)` returns the document with the key renamed, or None when it holds none."""
        text, doc = _json(p)
        if not isinstance(doc, (dict, list)):
            return
        new = fix(doc)
        if new is not None:
            changes.append((p, _dump_like(text, doc)(new)))
            counts[kind] += 1

    def top(where: Path, *, run_record: bool = False) -> Any:
        def fix(doc: Any) -> Any:
            if not isinstance(doc, dict):
                return None
            is_import = run_record and bool(
                doc.get("imported") or (doc.get("fingerprint") or {}).get("imported")
            )
            if _check(_rel(where), doc, systems, refused, keep=is_import):
                return _rename(doc)
            return None

        return fix

    runs = _common.DATA / "runs"
    for d in sorted(_store.iterdir(runs)) if _store.is_dir(runs) else []:
        if not _store.is_dir(d):
            continue
        if _store.is_file(d / "run.json"):
            whole(d / "run.json", "run records", top(d / "run.json", run_record=True))
        sdir = d / "scores"
        for s in sorted(_store.iterdir(sdir)) if _store.is_dir(sdir) else []:
            if _store.is_file(s / "metrics.json"):
                whole(s / "metrics.json", "score records", top(s / "metrics.json", run_record=True))
            if _store.is_file(s / "score.json"):

                def unset(doc: Any) -> Any:
                    gone = doc.get("unset") if isinstance(doc, dict) else None
                    if isinstance(gone, list) and OLD in gone:
                        return {**doc, "unset": [NEW if x == OLD else x for x in gone]}
                    return None

                whole(s / "score.json", "score records", unset)

    faith = _common.DATA / "faithfulness"
    for f in sorted(_store.glob(faith, "*/*.json")) if _store.is_dir(faith) else []:
        whole(f, "faithfulness records", top(f))

    datasets = _common.DATA / "datasets"
    for f in sorted(_store.glob(datasets, "*.json")) if _store.is_dir(datasets) else []:

        def unseals(doc: Any, f: Path = f) -> Any:
            entries = doc.get("unsealed") if isinstance(doc, dict) else None
            if not isinstance(entries, list) or not any(isinstance(e, dict) and OLD in e for e in entries):
                return None
            out = []
            for i, e in enumerate(entries):
                if isinstance(e, dict) and _check(f"{_rel(f)} unsealed[{i}]", e, systems, refused):
                    e = _rename(e)
                out.append(e)
            return {**doc, "unsealed": out}

        whole(f, "unseals' datasets", unseals)

    studies = _common.DATA / "studies"
    for f in sorted(_store.glob(studies, "*/*.events.jsonl")) if _store.is_dir(studies) else []:
        text = _store.read_text(f, encoding="utf-8")
        lines, hit = [], False
        for n, raw in enumerate(text.split("\n"), 1):
            try:
                ev = json.loads(raw) if raw.strip() else None
            except ValueError:
                ev = None
            if isinstance(ev, dict) and _check(
                f"{_rel(f)}:{n}", ev, systems, refused, imported=bool(ev.get("imported"))
            ):
                raw, hit = _dump_like(raw, ev, line=True)(_rename(ev)), True
            lines.append(raw)
        if hit:
            changes.append((f, "\n".join(lines)))
            counts["study logs"] += 1

    return {"changes": changes, "counts": counts, "refused": refused}


def run(dry_run: bool) -> None:
    """Rename the key in every stored record that is not hashed; refuse first, writing nothing."""
    p = plan()
    if p["refused"]:
        _common.die(
            "records whose `config_id` cannot become `system_id`:\n  " + "\n  ".join(p["refused"]),
            "invalid-file",
        )
    if not p["changes"]:
        print("  0 changed: already in this format")
        return
    print(f"  {len(p['changes'])} file(s) renamed `{OLD}` to `{NEW}`")
    for kind, n in sorted(p["counts"].items()):
        print(f"    {n:>4}  {kind}")
    if dry_run:
        return
    for f, text in p["changes"]:
        _common.write_text_atomic(f, text)
