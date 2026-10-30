"""Importers (RFC-019): read records from a system a project already has, for a capture.

An importer is a class with `records(query) -> Iterator[dict]`; its constructor takes the
importer's options (a dict, possibly empty). A record is
`{id, body, fields, created_at, source: {system, url}, labels, outcome}`: `id` is the record's own
id in its system, `body` its content (text, or a JSON document), `outcome` what happened to it
afterwards, when the system knows. Only `id`, and `body` or `fields`, are required.

Where an importer comes from, by `--importer NAME`:
  - a built-in one, `evaluation_harness/importers/<NAME>.py` (jsonl, ...);
  - the project's own: <data>/importers/<NAME>.py, class `Importer`;
  - a path: path/to/file.py:Class.
The core imports no built-in importer until one is asked for by name.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import importlib
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from evaluation_harness._common import CODE, DATA, die, load_module

RECORD_KEYS = {"id", "body", "fields", "created_at", "source", "labels", "outcome"}
#: A record's id becomes a file name and an item id: no path separators, no leading dot, at most
#: 200 characters. `:` is allowed (the triage fleet's ids are `source:ISSUE@time`), so captures are
#: not supported on Windows.
RECORD_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+=-]{0,199}")
#: A project importer's name, as a dataset id is checked: it names a file under <data>/importers/.
IMPORTER_NAME = re.compile(r"[a-z0-9][a-z0-9_]*")


def builtin_names() -> list[str]:
    """The importers that come with the harness."""
    return sorted(p.stem for p in (CODE / "importers").glob("*.py") if not p.stem.startswith("_"))


def resolve(name: str) -> tuple[type, Path]:
    """(the importer class, the file it is defined in) for `--importer NAME`."""
    if name in builtin_names():
        mod = importlib.import_module(f"evaluation_harness.importers.{name}")
        return mod.Importer, Path(mod.__file__ or "")
    if ":" in name:
        file, _, cls_name = name.rpartition(":")
        path = Path(file).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
    else:
        if not IMPORTER_NAME.fullmatch(name):
            die(f"--importer {name!r}: lowercase letters, digits and _, or path/to/importer.py:Class")
        path, cls_name = DATA / "importers" / f"{name}.py", "Importer"
        if not path.is_file():
            die(
                f"--importer {name}: not a built-in importer ({', '.join(builtin_names())}), and no "
                f"{path} with a class Importer; or name a file: path/to/importer.py:Class"
            )
    if not path.is_file():
        die(f"--importer {name}: no file {path}")
    mod = load_module(path, f"evh_importer_{hashlib.sha256(str(path).encode()).hexdigest()[:12]}")
    cls = getattr(mod, cls_name, None)
    if cls is None or not callable(getattr(cls, "records", None)):
        die(f"--importer {name}: {path} has no class {cls_name} with a records(query) method")
    return cls, path


def code_sha256(path: Path) -> str:
    """The sha256 of an importer's source file: a capture records which code read it."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> bytes:
    """The bytes a value is hashed and stored as: text as UTF-8, anything else as canonical JSON
    (sorted keys), so the same content always has the same hash."""
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def body_sha256(rec: dict) -> str:
    """The hash of what becomes the item: a record's body, else its fields."""
    return hashlib.sha256(
        canonical(rec["body"] if rec.get("body") is not None else rec["fields"])
    ).hexdigest()


def record_sha256(rec: dict) -> str:
    """The hash of the whole normalised record, outcome included, so an edited outcome (which a
    reference is built from) is caught as surely as an edited body."""
    return hashlib.sha256(canonical(rec)).hexdigest()


def parse_time(value: Any) -> _dt.datetime | None:
    """An ISO time (or epoch seconds) as an aware UTC datetime; None when absent or unparsable."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return _dt.datetime.fromtimestamp(value, tz=_dt.timezone.utc)
    s = str(value).strip().replace("Z", "+00:00")
    try:
        t = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=_dt.timezone.utc)


def problems(rec: Any) -> list[str]:
    """What is wrong with one record (empty when nothing)."""
    if not isinstance(rec, dict):
        return [f"a record is a dict, not {type(rec).__name__}"]
    rid = rec.get("id")
    out = []
    if not isinstance(rid, str) or not RECORD_ID.fullmatch(rid):
        out.append(
            f"id {rid!r}: 1-200 letters, digits and . _ : @ + = -, starting with a letter or digit "
            "(it becomes a file name)"
        )
    extra = set(rec) - RECORD_KEYS
    if extra:
        out.append(f"{rid}: unknown key(s) {sorted(extra)}; a record has {sorted(RECORD_KEYS)}")
    if rec.get("body") is None and not rec.get("fields"):
        out.append(f"{rid}: neither a body nor fields")
    for key in ("fields", "source", "labels"):
        if rec.get(key) is not None and not isinstance(rec[key], dict):
            out.append(f"{rid}: {key} is a dict")
    if rec.get("created_at") not in (None, "") and parse_time(rec["created_at"]) is None:
        out.append(f"{rid}: created_at {rec['created_at']!r} is not an ISO time")
    return out


def normalise(rec: dict) -> dict:
    """A record with every key present, created_at as UTC ISO ending in Z."""
    t = parse_time(rec.get("created_at"))
    return {
        "id": rec["id"],
        "body": rec.get("body"),
        "fields": rec.get("fields") or {},
        "created_at": t.astimezone(_dt.timezone.utc).isoformat().replace("+00:00", "Z") if t else None,
        "source": rec.get("source") or {},
        "labels": rec.get("labels") or {},
        "outcome": rec.get("outcome"),
    }


def read(name: str, query: dict, options: dict | None = None) -> tuple[Iterator[dict], Path]:
    """(the records an importer yields for a query, the importer's file)."""
    cls, path = resolve(name)
    return iter(cls(options or {}).records(query)), path


def window_of(query: dict) -> dict:
    """The time window a query asks for (`since`, `until`), as a capture records it."""
    return {k: query[k] for k in ("since", "until") if query.get(k)}
