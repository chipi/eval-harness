"""Item fields (ADR-0003): a project declares them in a field set, items carry their values.

The harness defines no field. A field set, `data/fields/<fieldset_id>.yaml`, lists a project's
fields with a type each; a dataset names one field set, and each of its items carries `fields`.
This module is the one place that knows the types: reading values from a CSV or JSONL file,
checking stored values, hashing them, and summarising them for the catalog.

Fields describe an item; they are not its identity. A run's fingerprint hashes item ids and
bytes only, so correcting a field invalidates no run. `fields_sha256` makes the change visible.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import statistics
from pathlib import Path
from typing import Any

import _common

TYPES = ("text", "number", "integer", "boolean", "date", "duration", "url", "choice")
#: Types a comparison can be broken down by: a handful of named groups, never a continuum.
GROUPABLE = ("choice", "boolean")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CLOCK = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$")
_TRUE, _FALSE = {"true", "yes", "1", "y"}, {"false", "no", "0", "n"}


def fieldset_path(fieldset_id: str, fields_dir: Path | None = None) -> Path:
    """Return the path to a field set file (in the project's `data/fields/` by default)."""
    return (fields_dir or _common.FIELDS) / f"{fieldset_id}.yaml"


def load_fieldset(fieldset_id: str, fields_dir: Path | None = None) -> dict[str, Any] | None:
    """The field set's document, or None when there is no such file."""
    import yaml  # noqa: PLC0415

    p = fieldset_path(fieldset_id, fields_dir)
    if not p.is_file():
        return None
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def declared(fieldset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{name: field} in declaration order."""
    return {f["name"]: f for f in fieldset.get("fields") or [] if isinstance(f, dict) and "name" in f}


def parse(field: dict[str, Any], raw: Any) -> Any:
    """`raw` (a CSV cell or a JSON value) as the field's type. Raises ValueError, naming why."""
    t = field.get("type")
    s = raw.strip() if isinstance(raw, str) else raw
    if t == "text":
        return str(s)
    if t == "number":
        if isinstance(s, bool):
            raise ValueError("a boolean is not a number")
        v = float(s)
        return int(v) if v.is_integer() else v
    if t == "integer":
        if isinstance(s, bool) or (isinstance(s, float) and not s.is_integer()):
            raise ValueError(f"{raw!r} is not a whole number")
        return int(s) if not isinstance(s, str) else int(s, 10)
    if t == "boolean":
        if isinstance(s, bool):
            return s
        if str(s).lower() in _TRUE:
            return True
        if str(s).lower() in _FALSE:
            return False
        raise ValueError(f"{raw!r} is not true/false (or yes/no, 1/0)")
    if t == "date":
        if not (isinstance(s, str) and _DATE.match(s)):
            raise ValueError(f"{raw!r} is not a date (YYYY-MM-DD)")
        return s
    if t == "duration":
        if isinstance(s, (int, float)) and not isinstance(s, bool):
            v = float(s)
        else:
            m = _CLOCK.match(str(s))
            v = (int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else float(s)
        if v < 0:
            raise ValueError(f"{raw!r} is a negative duration")
        return int(v) if float(v).is_integer() else v
    if t == "url":
        if not (isinstance(s, str) and re.match(r"^https?://\S+$", s)):
            raise ValueError(f"{raw!r} is not an http(s) URL")
        return s
    if t == "choice":
        if str(s) not in (field.get("values") or []):
            raise ValueError(f"{raw!r} is not one of {', '.join(field.get('values') or [])}")
        return str(s)
    raise ValueError(f"unknown type {t!r}")


def problems(fieldset: dict[str, Any], item_id: str, values: dict[str, Any]) -> list[str]:
    """What is wrong with one item's stored fields: undeclared, mistyped, or a required one missing."""
    out, fields = [], declared(fieldset)
    for name, v in (values or {}).items():
        if name not in fields:
            out.append(
                f"{item_id}: field {name!r} is not declared in field set {fieldset.get('fieldset_id')!r}"
            )
            continue
        try:
            if parse(fields[name], v) != v or (
                fields[name]["type"] in ("text", "date", "url", "choice") and not isinstance(v, str)
            ):
                out.append(f"{item_id}: {name} = {v!r} is not stored as a {fields[name]['type']}")
        except (ValueError, TypeError) as exc:
            out.append(f"{item_id}: {name}: {exc}")
    for name, f in fields.items():
        if f.get("required") and name not in (values or {}):
            out.append(f"{item_id}: required field {name!r} has no value")
    return out


def digest(items: list[dict[str, Any]]) -> str:
    """One hash over every item's fields, in item order: a change to any value moves it."""
    h = hashlib.sha256()
    for it in items:
        h.update(str(it.get("item_id", "")).encode())
        h.update(b"\x00")
        h.update(json.dumps(it.get("fields") or {}, sort_keys=True, separators=(",", ":")).encode())
        h.update(b"\x1e")
    return h.hexdigest()


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Rows of a .csv (header row) or .jsonl file, as dicts."""
    if path.suffix.lower() == ".jsonl":
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def values_from(
    fieldset: dict[str, Any], row: dict[str, Any], skip: tuple[str, ...] = ()
) -> tuple[dict[str, Any], list[str]]:
    """The declared fields' values in one row, typed; and what could not be read. Empty cells are
    absent values. A column that is neither declared nor in `skip` is a problem: a typo in a
    header must not quietly drop a field."""
    fields, vals, bad = declared(fieldset), {}, []
    for col, raw in row.items():
        if col in skip:
            continue
        if col not in fields:
            bad.append(f"column {col!r} is not a field of {fieldset.get('fieldset_id')!r}")
            continue
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        try:
            vals[col] = parse(fields[col], raw)
        except (ValueError, TypeError) as exc:
            bad.append(f"{col}: {exc}")
    return vals, bad


def summary(fieldset: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per field: its declaration, how many items fill it, and, for a `public` field only, a
    summary of the values (counts for a choice or boolean; range and median for numbers,
    durations and dates; the number of distinct values for text and URLs). A field not marked
    public shows no value: the static pages carry no item content unless a project says so."""
    out = []
    for name, f in declared(fieldset).items():
        vals = [it["fields"][name] for it in items if name in (it.get("fields") or {})]
        row = {
            "name": name,
            "type": f["type"],
            "label": f.get("label") or name,
            "description": f.get("description", ""),
            "unit": f.get("unit", ""),
            "public": bool(f.get("public")),
            "filled": len(vals),
            "of": len(items),
        }
        if f.get("public") and vals:
            if f["type"] in GROUPABLE:
                counts: dict[str, int] = {}
                for v in vals:
                    key = str(v).lower() if isinstance(v, bool) else str(v)
                    counts[key] = counts.get(key, 0) + 1
                row["counts"] = counts
            elif f["type"] in ("number", "integer", "duration"):
                row["min"], row["median"], row["max"] = min(vals), statistics.median(vals), max(vals)
            elif f["type"] == "date":
                row["min"], row["max"] = min(vals), max(vals)
            else:
                row["distinct"] = len(set(vals))
        out.append(row)
    return out


def matches(field: dict[str, Any], value: Any, want: str) -> bool:
    """Does an item's value pass the inspector's filter? A choice, boolean, text, URL or date
    field matches its value exactly; a number, integer or duration field takes `lo..hi` (either
    end may be empty) or one exact number."""
    if value is None:
        return False
    t = field.get("type")
    if t in ("number", "integer", "duration"):
        if ".." in want:
            lo, hi = want.split("..", 1)
            return (not lo or value >= parse(field, lo)) and (not hi or value <= parse(field, hi))
        return value == parse(field, want)
    if t == "boolean":
        return value == parse(field, want)
    return str(value) == want
