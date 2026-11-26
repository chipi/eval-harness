"""Item fields (ADR-0003): a project declares them in a field set, items carry their values.

The harness defines no field. A field set, `data/fields/<fieldset_id>.yaml`, lists a project's
fields with a type each; a dataset names one field set, and each of its items carries `fields`.
This module is the one place that knows the types: reading values from a CSV or JSONL file,
checking stored values, hashing them, and summarising them for the catalog.

Fields describe an item; they are not its identity. A run's fingerprint hashes item ids and
bytes only, so correcting a field invalidates no run. `fields_sha256` makes the change visible.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import csv
import hashlib
import json
import re
import statistics
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _store
from evaluation_harness._common import jsonl_lines

TYPES = ("text", "number", "integer", "boolean", "date", "datetime", "duration", "url", "choice")
#: Types a comparison can be broken down by: a handful of named groups, never a continuum.
GROUPABLE = ("choice", "boolean")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: A moment (RFC-030): an ISO 8601 date and time of day with its offset (Z or +hh:mm), seconds and fractions optional.
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})$")
_CLOCK = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$")
_TRUE, _FALSE = {"true", "yes", "1", "y"}, {"false", "no", "0", "n"}


def fieldset_path(fieldset_id: str, fields_dir: Path | None = None) -> Path:
    """Return the path to a field set file (in the project's `data/fields/` by default)."""
    return (fields_dir or _common.FIELDS) / f"{fieldset_id}.yaml"


def load_fieldset(fieldset_id: str, fields_dir: Path | None = None) -> dict[str, Any] | None:
    """The field set's document, or None when there is no such file."""
    import yaml  # noqa: PLC0415

    p = fieldset_path(fieldset_id, fields_dir)
    if not _store.is_file(p):
        return None
    doc = yaml.safe_load(_store.read_text(p, encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def fieldset_problems(fieldset_id: str, fs: dict[str, Any]) -> list[str]:
    """What is wrong with a loaded field set: its `fieldset_id` is not its file name, or it
    breaks schemas/fieldset.schema.json (not checked when jsonschema is not installed).
    dataset-create refuses on these and validate (V15) reports them."""
    out = []
    if fs.get("fieldset_id") != fieldset_id:
        out.append(f"fieldset_id {fs.get('fieldset_id')!r} is not its file name")
    out += _item_key_problems(fs)
    try:
        import jsonschema  # noqa: PLC0415
    except ImportError:
        return out
    import json  # noqa: PLC0415

    try:
        jsonschema.validate(fs, json.loads(_store.read_text(_common.SCHEMAS / "fieldset.schema.json")))
    except jsonschema.ValidationError as exc:
        out.append(exc.message)
    return out


def _item_key_problems(fs: dict[str, Any]) -> list[str]:
    """What is wrong with the keys only --fields-from-item reads, `from` and `reduce`: checked here as well as by the
    schema, which a project without jsonschema never runs, and so that the field is named."""
    out = []
    for f in fs.get("fields") or []:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        if "from" in f:
            why = pointer_problem(f["from"])
            if why:
                out.append(f"field {name!r}: from {f['from']!r} {why}")
        if "reduce" in f:
            if f["reduce"] != "count":
                out.append(f"field {name!r}: reduce {f['reduce']!r} is not one the harness knows (count)")
            elif f.get("type") != "integer":
                out.append(
                    f"field {name!r}: reduce: count is a number, so the field's type is integer, not {f.get('type')}"
                )
    return out


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
    if t == "datetime":
        if not (isinstance(s, str) and _DATETIME.match(s) and moment(s) is not None):
            raise ValueError(
                f"{raw!r} is not a date and time with its offset (YYYY-MM-DDThh:mm:ss+hh:mm, or Z)"
            )
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


def moment(value: str) -> Any:
    """A `datetime` field's value as an aware datetime, None when it is not one (Python 3.10 reads no `Z`)."""
    import datetime as dt  # noqa: PLC0415

    try:
        t = dt.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo is not None else None


def _moment_key(value: str) -> Any:
    return moment(value)


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
                fields[name]["type"] in ("text", "date", "datetime", "url", "choice")
                and not isinstance(v, str)
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


def pointer_problem(pointer: Any) -> str | None:
    """Why `pointer` is not a JSON pointer (RFC 6901) a field may name, or None. The empty pointer is the whole item,
    which is no scalar, so a field may not name it."""
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        return "is not a JSON pointer: it starts with / (/start/x)"
    if re.search(r"~(?![01])", pointer):
        return "has a ~ that is not ~0 or ~1"
    return None


def resolve(doc: Any, pointer: str) -> tuple[bool, Any]:
    """(found, value) of the JSON pointer `pointer` in `doc`: a key of an object, an index of a list. Nothing found is
    not an error: the item has no such value."""
    cur = doc
    for raw in pointer[1:].split("/"):
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        elif (
            isinstance(cur, list)
            and key.isascii()
            and key.isdigit()
            and (key == "0" or key[0] != "0")
            and int(key) < len(cur)
        ):
            cur = cur[int(key)]
        else:
            return False, None
    return True, cur


def values_from_item(fieldset: dict[str, Any], doc: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The declared fields' values in one JSON item, typed as `values_from` types a row's. Each field reads the item's
    key of its own name, or the value its `from` pointer lands on; `reduce: count` makes a list's (or an object's) length
    of it. A value not found, or null, is missing, as an empty cell is. Other keys are not read. An object or a list is
    refused unless counted: fields are scalar (RFC-006)."""
    row: dict[str, Any] = {}
    bad = []
    for name, f in declared(fieldset).items():
        pointer = f.get("from") or "/" + name.replace("~", "~0").replace("/", "~1")
        found, v = resolve(doc, pointer)
        if not found or v is None:
            continue
        nested = isinstance(v, (dict, list))
        if f.get("reduce") == "count":
            if not nested:
                bad.append(f"{name}: reduce: count needs a list or an object, and {pointer} holds {v!r}")
                continue
            v = len(v)
        elif nested:
            bad.append(
                f"{name}: {pointer} is {'an object' if isinstance(v, dict) else 'a list'}, and a field is a scalar "
                "(reduce: count takes its length)"
            )
            continue
        row[name] = v
    vals, errs = values_from(fieldset, row)
    return vals, bad + errs


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Rows of a .csv (header row) or .jsonl file, as dicts."""
    if path.suffix.lower() == ".jsonl":
        return [json.loads(x) for x in jsonl_lines(_store.read_text(path, encoding="utf-8")) if x.strip()]
    with _store.open_file(
        path, newline="", encoding="utf-8-sig"
    ) as fh:  # a spreadsheet's CSV may begin with a BOM
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
            elif f["type"] == "datetime":
                row["min"], row["max"] = min(vals, key=_moment_key), max(vals, key=_moment_key)
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
