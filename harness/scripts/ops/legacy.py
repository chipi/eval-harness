"""Operations made from a command's body that prints (RFC-032 step 9): the body runs in the caller's process, its printing
collected as `--json` always collected it, so the answer is what `evh <command> --json` gave: `{"blocks": [...],
"values": {...}}`, the printed lines and tables in the order they were printed and the command's named values.

`pair(body)` gives an operation's two functions from one body: `run(**inputs)`, the collected answer every surface but
the terminal takes, and `print_text(**inputs)`, the body printing as it always printed, which the command line uses for
its text answer (so a table fitted to the terminal stays so). One call at a time runs a body: the printing is collected
by swapping the process's stdout and the held-out reads of a call are module state, and a server answers many calls."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator
from typing import Any

_LOCK = threading.RLock()

#: The result of an operation made from a body that prints, as JSON Schema (for the API's description).
BLOCKS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "blocks": {
            "type": "array",
            "description": "what the command prints, in order: {lines: [...]} text, or {columns, rows} a table",
            "items": {"type": "object"},
        },
        "values": {"type": "object", "description": "the command's named results, when it gives some"},
    },
    "required": ["blocks"],
}


#: The joins as an operation takes them (the API, the MCP tools): one object per outside capture (`_outcome_join.joins_of`).
OUTCOMES: dict[str, Any] = {
    "type": "array",
    "description": "the outside captures the outcome is read from (an outside system's records), each joined to a "
    "decision; the rules read each under its own name",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["capture", "join"],
        "properties": {
            "capture": {"type": "string", "description": "another capture holding the outcome"},
            "join": {
                "type": "string",
                "description": "ITEM_FIELD=RECORD_FIELD: what ties a decision to the other capture's record",
            },
            "as": {
                "type": "string",
                "description": "the name the rules read its fields under, NAME.field (default: the capture's id)",
            },
            "within": {
                "type": "string",
                "description": "a window after the item's time, -1m,+15m: only records made in it match",
            },
            "identity": {
                "type": "string",
                "description": "ITEM_FIELD=RECORD_FIELD that must also agree: a reused id is gone, not another's outcome",
            },
            "gone_if_missing": {
                "type": "boolean",
                "description": "an item whose key no record of the other capture carries is gone from the source",
            },
        },
    },
}


@contextlib.contextmanager
def refusing() -> Iterator[None]:
    """What the commands' helpers refuse with `die` (an exit that names the kind), as the model's own refusal: the
    server answers it, the command prints it as it always did."""
    import re  # noqa: PLC0415

    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    try:
        yield
    except SystemExit as exc:
        m = re.fullmatch(r"ERROR \(([a-z-]+)\): (.*)", str(exc.code or ""), re.S)
        if m is None:
            raise
        raise Problem(m.group(2), m.group(1)) from None


def pair(
    body: Callable[..., int | None], as_json: str = ""
) -> tuple[Callable[..., dict[str, Any]], Callable[..., int]]:
    """(run, print_text) of one body that prints; the body may return the command's exit code. `as_json` names the
    input a body that behaves differently when its answer is data (`--json`) takes: true for `run`, false for the text."""

    def run(**inputs: Any) -> dict[str, Any]:
        from evaluation_harness import _jsonout  # noqa: PLC0415

        with _LOCK, refusing(), _jsonout.capture() as c:
            body(**inputs, **({as_json: True} if as_json else {}))
        return c.result()

    def print_text(**inputs: Any) -> int:
        from evaluation_harness import _jsonout  # noqa: PLC0415

        with refusing():
            code = body(**inputs, **({as_json: False} if as_json else {}))
            _jsonout._say_exposed()
        return code or 0

    return run, print_text


def of(
    module: str, fn: str = "body", as_json: str = ""
) -> tuple[Callable[..., dict[str, Any]], Callable[..., int]]:
    """`pair` of the body `fn` of `module`, loaded when the operation is called."""
    import importlib  # noqa: PLC0415

    def body(**inputs: Any) -> int | None:
        return getattr(importlib.import_module(module), fn)(**inputs)

    return pair(body, as_json)


def table_text(cols: list[str], rows: list[list[str]]) -> list[str]:
    """A table as lines: the heads, a rule, a line a row, the columns aligned."""
    w = [max([len(c)] + [len(r[i]) for r in rows]) for i, c in enumerate(cols)]
    out = ["  " + "  ".join(c.ljust(w[i]) for i, c in enumerate(cols)).rstrip()]
    out.append("  " + "  ".join("-" * x for x in w))
    out.extend("  " + "  ".join(c.ljust(w[i]) for i, c in enumerate(r)).rstrip() for r in rows)
    return out


def say_blocks(result: dict[str, Any]) -> str:
    """An answer made of blocks as text: the lines as printed, a table as aligned columns."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    def cell(v: Any) -> str:
        return "—" if v is None else cb.fmt(v) if isinstance(v, float) else str(v)

    out: list[str] = []
    for b in result.get("blocks") or []:
        if "lines" in b:
            out.extend(b["lines"])
        else:
            cols = b.get("columns") or []
            out.extend(table_text(cols, [[cell(r.get(c)) for c in cols] for r in b.get("rows") or []]))
    return "\n".join(out)


def namespace(inputs: dict[str, Any], command: str, dests: dict[str, str] | None = None) -> Any:
    """A job's body called with its inputs, as the Namespace its old parser gave it: every input of the operation, the
    schema's default (a flag false, a repeatable option an empty list, anything else None) where the call gave none, a
    path as a `Path`, under the name its option stored it as (`dests`: `from` was `from_`)."""
    import argparse  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from evaluation_harness.ops.registry import OPS  # noqa: PLC0415

    op = OPS[command]
    unknown = sorted(set(inputs) - set(op.inputs))
    if unknown:
        raise TypeError(f"{command}: not inputs: {', '.join(unknown)}")
    out: dict[str, Any] = {}
    for name, spec in op.inputs.items():
        if name in inputs:
            value = inputs[name]
        elif "default" in spec:
            value = spec["default"]
        elif spec.get("type") == "boolean":
            value = False
        elif spec.get("type") == "array" and spec.get("x-nargs") != "+":
            value = []
        elif spec.get("type") == "object":
            value = {}
        else:
            value = None
        if spec.get("format") == "path" and isinstance(value, str):
            value = Path(value)
        out[(dests or {}).get(name, name)] = value
    return argparse.Namespace(**out)
