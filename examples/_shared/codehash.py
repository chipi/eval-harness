r"""Hash the code that decides a score — functions AND the constants they read.

WHY THIS EXISTS AS A SHARED HELPER

  Every scoring hash in this repo was written as `sha256(inspect.getsource(fn))`, and
  that covers strictly less than it appears to. A parser is its function *plus* the
  module-level regexes the function references; `getsource` returns only the `def`
  block, so editing `_BARE_KEY` or `_PUNCT` changed the score and left the hash
  identical -- the precise failure the hash was added to prevent.

  An external review found this in four places at once (the classification parser, the
  NER parser, the extraction normaliser, the retrieval tokeniser) and found the
  retrieval *parser* covered by no hash at all. One helper, used everywhere, is the
  only way this stays fixed: a scattered idiom drifts again the moment someone adds a
  fifth scorer.

USAGE

    _PUNCT = re.compile(r"[^\w\s]")
    def normalize(s): ...
    def normalizer_sha256() -> str:
        return code_digest(normalize, consts={"_PUNCT": _PUNCT})

  Pass every module-level name the functions actually read. There is no way to discover
  that automatically that is worth trusting -- `__code__.co_names` misses closures and
  includes builtins -- so it is declared, and a missed constant is a real hole. The
  compensating control is that `code_digest` is used in exactly one shape everywhere,
  so a reviewer can check the argument list against the function body in one glance.

DOCUMENTATION IS NOT CODE

  A function is hashed as its syntax tree with its docstrings removed, never as its text:
  rewording a docstring, adding a comment or reformatting changes nothing a score depends
  on, and a hash that moved on it would flag every comparison across the edit.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import textwrap
from collections.abc import Iterable
from typing import Any, Callable


def _stable(value: Any) -> str:
    """A repr that is stable across processes for the kinds of constant used here.

    `repr` of a compiled regex includes its pattern, which is what matters. Sets and
    dicts are sorted, because their repr order is not guaranteed to be stable across
    versions and a hash that changes without the code changing is worse than no hash.
    """
    import re as _re  # noqa: PLC0415

    if isinstance(value, _re.Pattern):
        return f"re({value.pattern!r},{value.flags})"
    if isinstance(value, (set, frozenset)):
        return "{" + ",".join(sorted(_stable(v) for v in value)) + "}"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k!r}:{_stable(v)}" for k, v in sorted(value.items())) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable(v) for v in value) + "]"
    return repr(value)


def _behaviour(fn: Callable) -> str:
    """A function's syntax tree without docstrings, comments or formatting."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return _tree_text(tree)


def _tree_text(node: Any) -> str:
    """The tree as text that is the same on every Python version: empty and None fields are
    left out (`ast.dump` prints them on 3.11 and not on 3.13+). The same rule as the harness's
    `_codeid.tree_text`; examples do not import the harness's private modules."""
    if isinstance(node, ast.AST):
        fields = []
        for name in node._fields:
            value = getattr(node, name, None)
            if value is None or value == []:
                continue
            fields.append(f"{name}={_tree_text(value)}")
        return f"{type(node).__name__}({','.join(fields)})"
    if isinstance(node, list):
        return "[" + ",".join(_tree_text(x) for x in node) + "]"
    return repr(node)


def code_digest(*fns: Callable | Iterable[Callable], consts: dict[str, Any] | None = None) -> str:
    """sha256 over the behaviour of every function plus every declared constant.

    Functions are hashed in the order given and constants by sorted name, so the digest
    depends on the code and not on how the call was written.
    """
    flat: list = []
    for f in fns:
        if callable(f):
            flat.append(f)
        else:
            flat.extend(f)
    h = hashlib.sha256()
    for f in flat:
        h.update(_behaviour(f).encode())
        h.update(b"\x1e")
    for name in sorted(consts or {}):
        h.update(name.encode())
        h.update(b"\x00")
        h.update(_stable((consts or {})[name]).encode())
        h.update(b"\x1e")
    return h.hexdigest()
