"""Which functions of a system's code a replay entered (RFC-030), with the standard library alone.

A `call` event per Python function call (no line tracing: the trace function returns None), on every thread
(`sys.settrace` and `threading.settrace`), kept only for code under one folder: the replay's version copies. A file
counts once a function or its module body ran in it; its functions are then listed from its syntax tree, and those
never entered are named, so a passing gate also says what no item exercised.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import ast
import os
import sys
import threading
from pathlib import Path
from typing import Any

#: At most this many never-entered functions are listed per version; the count is always whole.
LIST_AT_MOST = 200


class Tracer:
    """`with Tracer(root):` records (file, first line) of each function entered under `root`."""

    def __init__(self, root: Path) -> None:
        self.root = str(Path(root).resolve()) + os.sep
        self.entered: set[tuple[str, int]] = set()
        self._prev: Any = None
        self._prev_thread: Any = None

    def _trace(self, frame: Any, event: str, _arg: Any) -> None:
        if event == "call":
            co = frame.f_code
            if co.co_filename.startswith(self.root):
                self.entered.add((co.co_filename, co.co_firstlineno))

    def __enter__(self) -> Tracer:
        self._prev = sys.gettrace()
        self._prev_thread = getattr(threading, "gettrace", lambda: None)()
        threading.settrace(self._trace)
        sys.settrace(self._trace)
        return self

    def __exit__(self, *_exc: Any) -> None:
        sys.settrace(self._prev)
        threading.settrace(self._prev_thread)


def _functions(path: Path) -> list[tuple[str, int]]:
    """(qualified name, first line as the code object counts it: the first decorator's) for each def in a file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, ValueError, OSError):
        return []
    out: list[tuple[str, int]] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                first = min([child.lineno, *(d.lineno for d in child.decorator_list)])
                out.append((prefix + child.name, first))
                walk(child, f"{prefix}{child.name}.<locals>.")
            elif isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            else:
                walk(child, prefix)

    walk(tree, "")
    return out


def report(entered: set[tuple[str, int]], version_of: Any) -> dict[str, Any]:
    """Per version (`version_of(file)` -> a commit, or None to leave out): the files that ran, the functions they
    define, how many were entered, and those never entered (`file:qualname`, at most LIST_AT_MOST)."""
    files: dict[str, set[int]] = {}
    for f, line in entered:
        files.setdefault(f, set()).add(line)
    out: dict[str, Any] = {}
    for f in sorted(files):
        commit, rel = version_of(f)
        if commit is None:
            continue
        v = out.setdefault(commit, {"files": 0, "defined": 0, "entered": 0, "never": [], "never_count": 0})
        v["files"] += 1
        for name, line in _functions(Path(f)):
            v["defined"] += 1
            if line in files[f]:
                v["entered"] += 1
            else:
                v["never_count"] += 1
                if len(v["never"]) < LIST_AT_MOST:
                    v["never"].append(f"{rel}:{name}")
    return out
