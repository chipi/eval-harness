"""Where Python code reads or writes text, or decodes a child's output, without naming an encoding.

    from _encoding_sites import find_sites
    for line, col, what in find_sites(source_text): ...

Python's default is the locale's encoding: UTF-8 on this repository's machines, cp1252 on a Windows
console, ASCII under LC_ALL=C. A file this repository wrote in one reads back as an error or as
other characters in another. ruff's PLW1514 sees only a receiver it can prove is a `Path`
and no subprocess call, so this walks the syntax tree and flags by the call's shape.
"""

from __future__ import annotations

import ast

#: Methods whose name alone says "text file": a call without `encoding=` is a site.
_TEXT_METHODS = {"read_text", "write_text"}
#: Callables that open a file and take the mode as the second positional argument or `mode=`.
_OPENERS = {"open", "open_file", "fdopen", "NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"}
#: Receivers whose `.open` is not a text-file open, or is not the filesystem's.
_NOT_FILES = {"webbrowser", "Image", "zipfile", "ZipFile", "tarfile", "tf", "zf", "zip_file", "os", "Dataset"}
#: Default mode of each opener: text for `open`/`fdopen`, binary for the tempfile ones.
_BINARY_DEFAULT = {"NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"}
#: The harness's own store helpers: their `read_text`/`write_text` default to UTF-8.
_STORE_RECEIVERS = {"_store", "_runstore"}
#: The position of `encoding` among a method's positional arguments, where one may pass it there.
_ENCODING_AT = {"read_text": 1, "write_text": 2}
_SUBPROCESS = {"run", "Popen", "check_output", "check_call", "call", "run_child"}
_HANDLERS = {"FileHandler", "RotatingFileHandler", "TimedRotatingFileHandler", "WatchedFileHandler"}


def _kw(call: ast.Call, name: str) -> ast.keyword | None:
    """The keyword argument of that name, if the call passes one."""
    return next((k for k in call.keywords if k.arg == name), None)


def _name(func: ast.expr) -> tuple[str, str]:
    """(receiver's last name, callable's name) of a call's function, '' where it has none."""
    if isinstance(func, ast.Name):
        return "", func.id
    if isinstance(func, ast.Attribute):
        owner = func.value
        recv = (
            owner.id
            if isinstance(owner, ast.Name)
            else owner.attr
            if isinstance(owner, ast.Attribute)
            else ""
        )
        return recv, func.attr
    return "", ""


def _mode(call: ast.Call, default: str, first: bool) -> str | None:
    """The mode a file-opening call asks for; None when it is not a literal. `first`: the mode is the first
    positional argument (`Path.open(mode)`, `NamedTemporaryFile(mode)`), not the second (`open(path, mode)`)."""
    at = 0 if first else 1
    node = call.args[at] if len(call.args) > at else None
    kw = _kw(call, "mode")
    if kw is not None:
        node = kw.value
    if node is None:
        return default
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _text_flag(call: ast.Call, name: str) -> bool:
    """Whether the call asks for text from a child process: `text=True` anywhere, or a flag that is not a
    literal on a subprocess call (a variable might be True)."""
    for flag in ("text", "universal_newlines"):
        kw = _kw(call, flag)
        if kw is None:
            continue
        if isinstance(kw.value, ast.Constant):
            if kw.value.value is True:
                return True
        elif name in _SUBPROCESS:
            return True
    return False


def classify(call: ast.Call) -> str:
    """What this call is, if it is a text site with no encoding; '' if it is fine or not one."""
    if _kw(call, "encoding") is not None:
        return ""
    recv, name = _name(call.func)
    if any(k.arg is None for k in call.keywords) and not _text_flag(
        call, name
    ):  # **kw: it may carry the encoding
        return ""
    if len(call.args) >= _ENCODING_AT.get(name, 99):  # the encoding given positionally
        return ""
    if name in _TEXT_METHODS:
        # a bare read_text() is a helper's own, not Path's; the store's helpers default to UTF-8
        return "" if recv in _STORE_RECEIVERS or isinstance(call.func, ast.Name) else name
    if _text_flag(call, name):
        return f"{name}(text=)"
    if name in _HANDLERS:
        return name
    if name == "TextIOWrapper":
        return name
    if name in _OPENERS or (name == "open" and recv):
        if name == "open" and recv in _NOT_FILES:
            return ""
        if len(call.args) >= 4 and name in {"open", "open_file", "fdopen"}:  # encoding given positionally
            return ""
        first = name in _BINARY_DEFAULT or (
            bool(recv) and name == "open" and bool(call.args) and isinstance(call.args[0], ast.Constant)
        )
        mode = _mode(call, "w+b" if name in _BINARY_DEFAULT else "r", first)
        if mode is None:
            return f"{name}(mode not literal)"
        if "b" in mode and "t" not in mode:
            return ""
        return f"{name}({mode!r})"
    return ""


def find_sites(source: str) -> list[tuple[int, int, str]]:
    """(line, column, what) of every text-mode call in the source that names no encoding."""
    return [
        (n.lineno, n.col_offset, what)
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Call) and (what := classify(n))
    ]
