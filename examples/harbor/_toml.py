"""The few keys of a Harbor task's `task.toml` the example reads, parsed by hand.

`tomllib` is Python 3.11+ and the harness runs on 3.10 (RFC-038, owner 2026-11-20: parse the keys needed, add no
dependency). This reads a table's scalar keys (strings, numbers, booleans) under its dotted name, and skips what it does
not need: arrays, inline tables, `[[array of tables]]` (a task's authors live there, and are never read).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_KEY = re.compile(r"""^\s*([A-Za-z0-9_-]+|"[^"]*")\s*=\s*(.*?)\s*$""")


def _scalar(raw: str) -> Any:
    """A TOML string, number or boolean, or None for anything else (an array, an inline table, a multi-line string)."""
    if raw.startswith('"') and raw.count('"') >= 2 and not raw.startswith('"""'):
        end = raw.index('"', 1)
        while raw[end - 1] == "\\":
            end = raw.index('"', end + 1)
        return raw[1:end].replace('\\"', '"').replace("\\\\", "\\")
    raw = raw.split("#", 1)[0].strip()
    if raw in ("true", "false"):
        return raw == "true"
    try:
        return int(raw.replace("_", ""))
    except ValueError:
        pass
    try:
        return float(raw.replace("_", ""))
    except ValueError:
        return None


def read(path: Path) -> dict[str, dict[str, Any]]:
    """{"table.name": {key: scalar}} of the file at `path`; {} when there is none. Keys before any table are under ""."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return {}
    tables: dict[str, dict[str, Any]] = {"": {}}
    here: str | None = ""
    depth = 0  # inside a multi-line array: its lines are skipped
    for line in text.splitlines():
        if depth:
            depth += line.count("[") - line.count("]")
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[["):
            here = None  # a table of an array: its keys are not read
            continue
        if stripped.startswith("["):
            here = stripped.strip("[]").split("#", 1)[0].strip().strip("[]").strip()
            tables.setdefault(here, {})
            continue
        m = _KEY.match(line)
        if not m or here is None:
            continue
        raw = m.group(2)
        if raw.startswith("[") and raw.count("[") != raw.count("]"):
            depth = raw.count("[") - raw.count("]")
            continue
        value = _scalar(raw)
        if value is not None:
            tables[here][m.group(1).strip('"')] = value
    return tables


def get(tables: dict[str, dict[str, Any]], table: str, key: str, default: Any = None) -> Any:
    """One key of one table, or `default`."""
    return tables.get(table, {}).get(key, default)
