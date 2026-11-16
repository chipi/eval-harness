"""What a decision or a work operation must declare (RFC-032 step 9 P3), as a list of what is wrong with a declaration:
the test of the declarations (tests/test_op_declarations.py) fails an operation added without its locks, its route, its
why, or an input that names a file with no word on how the call carries it. No free path argument is the rule behind
the last one: a job takes a file as an upload or writes it in its own folder, or only the command line takes it
(`tool_hidden`)."""

from __future__ import annotations

import re
from typing import Any

from evaluation_harness.ops import locks as op_locks
from evaluation_harness.ops.registry import Op, _load

#: A decision that has no reason of its own to give: it opens something, and says what it opens in its inputs.
NO_WHY = frozenset({"round-open", "round-carry"})
#: The words that name an input a file may be behind, as a whole word of its name (`items`, `scorer_file`), or `path`
#: anywhere in it.
FILE_WORDS = frozenset({"out", "file", "dir", "items", "spec", "sheet", "map", "guideline", "proposal"})
#: `no`: the name says a file and the input is not one (reference-promote's `items` are item ids).
X_FILE = ("upload", "artifact", "no")
X_REF = ("system",)
#: A text a call gives that the command line also reads as a code file (`path.py:Class`) or a file (`@file`): the API
#: takes its other form only, which the input's `pattern` says.
CODE_OR_FILE = re.compile(r"\.py:|@file")


def names_a_file(name: str) -> bool:
    """Whether an input's name says a file may be behind it."""
    return "path" in name or bool(FILE_WORDS & set(name.split("_")))


def _dotted(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][\w.]*:[A-Za-z_]\w*", value or ""))


def problems(op: Op) -> list[str]:
    """What is wrong with this operation's declaration as a job: empty for a read or an edit, and for a good one."""
    if not op.is_job():
        return []
    out: list[str] = []
    say = out.append
    if op.method != "POST":
        say(f"method {op.method}: a job is started by POST")
    if not op.route.startswith("/") or not op.route.strip("/"):
        say(f"route {op.route!r}: a job needs a resource route")
    if not _dotted(op.run):
        say(f"run {op.run!r}: a dotted module:function, the job's body")
    if op.positional:
        say(f"positional {op.positional}: a job takes named options only")
    if op.locks is None and not op.locks_fn:
        say("locks: not declared (locks=() when the job writes nothing another job writes)")
    if op.locks is not None and op.locks != op_locks.PROJECT and not isinstance(op.locks, tuple):
        say(f"locks {op.locks!r}: a tuple of (template, exclusive), or 'project'")
    for entry in op.locks if isinstance(op.locks, tuple) else ():
        if not (isinstance(entry, tuple) and len(entry) == 2 and isinstance(entry[0], str)):
            say(f"lock {entry!r}: (template, exclusive)")
            continue
        for n in op_locks.fields(entry[0]):
            if n not in op.inputs:
                say(f"lock {entry[0]!r} names {n}, which is not an input")
    if op.locks_fn and not _dotted(op.locks_fn):
        say(f"locks_fn {op.locks_fn!r}: a dotted module:function")
    for dotted in (op.run, op.locks_fn, op.parts_fn):
        if _dotted(dotted):
            try:
                _load(dotted)
            except (ImportError, AttributeError) as exc:
                say(f"{dotted}: cannot be loaded ({type(exc).__name__}: {exc})")
    if op.kind == "decision":
        if op.why:
            if op.why not in op.inputs or op.why not in op.required:
                say(f"why {op.why!r}: a decision's reason is a required input")
        elif op.name not in NO_WHY:
            say("a decision names the required input that is its reason (why=...), or is listed in NO_WHY")
    elif op.why:
        say("why: only a decision has a reason of its own")
    if op.spends and op.kind == "decision" and not op.why:
        say("a decision that spends still names its why")
    if op.parts_fn and not _dotted(op.parts_fn):
        say(f"parts_fn {op.parts_fn!r}: a dotted module:function")
    for part in op.path_params():
        target = op.parts.get(part, part)
        if target not in op.inputs:
            say(f"part {{{part}}} fills {target!r}, which is not an input")
        elif target not in op.required:
            say(f"part {{{part}}} fills {target!r}, which is not required")
    for part in set(op.parts) - set(op.path_params()):
        say(f"parts names {part!r}, which is not in the route")
    for n in op.required:
        if n not in op.inputs:
            say(f"required {n!r}: not an input")
    for n in (*op.tool_hidden, *op.one_of, *(m for g in op.exclusive for m in g)):
        if n not in op.inputs:
            say(f"{n!r}: named but not an input")
    for n in ("by", "for", "json", "inputs_file", "max_cost_usd"):
        if n in op.inputs:
            say(f"input {n!r}: never an input (the call's own)")
    if op.resume and not (len(op.resume) == 2 and all(n in op.inputs for n in op.resume)):
        say(f"resume {op.resume}: (the input naming the run to continue, the input naming the run written)")
    for n, spec in op.inputs.items():
        say_in = lambda msg, n=n: say(f"input {n}: {msg}")  # noqa: E731
        _input_problems(n, spec, op, say_in)
    return out


def _input_problems(name: str, spec: dict[str, Any], op: Op, say: Any) -> None:
    f = spec.get("x-file")
    if f is not None and f not in X_FILE:
        say(f"x-file {f!r}: one of {', '.join(X_FILE)}")
    ref = spec.get("x-ref")
    if ref is not None and ref not in X_REF:
        say(f"x-ref {ref!r}: one of {', '.join(X_REF)}")
    names_one = names_a_file(name) and "enum" not in spec  # a choice among words is no path
    if (names_one or spec.get("format") == "path") and f is None and name not in op.tool_hidden:
        say("names a file or a path: say how a call carries it (x-file: upload or artifact), or tool_hidden")
    if f in ("upload", "artifact") and name in op.tool_hidden:
        say("x-file and tool_hidden: a hidden input is never carried")
    if f in ("upload", "artifact") and not (
        spec.get("type") == "string"
        or (spec.get("type") == "array" and spec.get("items", {}).get("type") == "string")
    ):
        say(
            "x-file: the job is given a path (a list of them), so the input is a string (or an array of strings)"
        )
    if (
        CODE_OR_FILE.search(spec.get("description", ""))
        and "pattern" not in spec
        and name not in op.tool_hidden
    ):
        say("its description offers path.py:Class or @file, and it has no pattern that refuses them")
    if spec.get("type") == "boolean" and spec.get("default") is True:
        say("a boolean flag only turns on: its default is false")
    if "pattern" in spec and spec.get("type") != "string":
        say("pattern: only on a text")
    if spec.get("x-short") and not re.fullmatch(r"-[A-Za-z]", spec["x-short"]):
        say(f"x-short {spec['x-short']!r}: one letter after a dash")
    if spec.get("x-flag") is not None and not re.fullmatch(r"--[a-z][a-z0-9-]*", str(spec["x-flag"])):
        say(f"x-flag {spec['x-flag']!r}: an option, --like-this")
    if spec.get("x-nargs") not in (None, "+"):
        say("x-nargs: '+' or nothing")


def route_overlaps(ops: list[Op]) -> list[str]:
    """Pairs of routes a request could match both of: the same method, the same number of parts, and at each place the
    same word or a placeholder in either (the server runs the first it finds, so the second would never answer)."""
    out: list[str] = []
    seen: list[Op] = []
    for op in ops:
        a = op.route.strip("/").split("/")
        for other in seen:
            b = other.route.strip("/").split("/")
            if op.method != other.method or len(a) != len(b):
                continue
            if all(x == y or x.startswith("{") or y.startswith("{") for x, y in zip(a, b, strict=True)):
                out.append(f"{op.method} {op.route} ({op.name}) overlaps {other.route} ({other.name})")
        seen.append(op)
    return out
