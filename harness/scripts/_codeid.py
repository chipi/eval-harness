"""The identity of code: what it does, never how it is documented.

A hash that moves when a docstring, a comment, a blank line or a metric's description changes
says the scorer changed when it did not, and every comparison across that edit is flagged. So
code is hashed as its syntax tree, with documentation removed: docstrings (module, class,
function), comments and formatting (the tree has none), and `METRIC_DESCRIPTIONS`, the adapter's
one-sentence explanations of its metrics. Anything else that changes, changes the hash.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import ast
import hashlib
import json
from pathlib import Path

#: Module-level names that hold documentation, not behaviour: dropped before hashing.
DOC_NAMES = frozenset({"METRIC_DESCRIPTIONS"})


def _strip(tree: ast.AST) -> ast.AST:
    """Remove docstrings and documentation assignments from a parsed module, in place."""
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    if isinstance(tree, ast.Module):
        tree.body = [n for n in tree.body if not _is_doc_assignment(n)] or [ast.Pass()]
        # Importing a documentation name is documentation too: an adapter that takes its
        # METRIC_DESCRIPTIONS from a shared module hashes as it did before it did so.
        for n in tree.body:
            if isinstance(n, ast.ImportFrom):
                n.names = [a for a in n.names if a.name not in DOC_NAMES]
        emptied = [n for n in tree.body if isinstance(n, ast.ImportFrom) and not n.names]
        tree.body = [n for n in tree.body if n not in emptied] or [ast.Pass()]
    return tree


def _is_doc_assignment(node: ast.stmt) -> bool:
    targets = (
        node.targets
        if isinstance(node, ast.Assign)
        else [node.target]
        if isinstance(node, ast.AnnAssign)
        else []
    )
    return any(isinstance(t, ast.Name) and t.id in DOC_NAMES for t in targets)


def source_sha256(text: str) -> str:
    """sha256 of Python source's behaviour: its syntax tree without docstrings, comments,
    formatting or `METRIC_DESCRIPTIONS`. Source that does not parse is hashed as its bytes."""
    try:
        tree = _strip(ast.parse(text))
    except SyntaxError:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return hashlib.sha256(tree_text(tree).encode("utf-8")).hexdigest()


def tree_text(node: object) -> str:
    """A syntax tree as text that is the same on every Python version.

    Not `ast.dump`: 3.13 stopped printing empty fields and 3.12 added `type_params`, so the
    same file dumped to different text under 3.11 and 3.14 and looked like a different
    scorer. Empty and None fields are left out here, whatever the version prints."""
    if isinstance(node, ast.AST):
        fields = []
        for name in node._fields:
            value = getattr(node, name, None)
            if value is None or value == []:
                continue
            fields.append(f"{name}={tree_text(value)}")
        return f"{type(node).__name__}({','.join(fields)})"
    if isinstance(node, list):
        return "[" + ",".join(tree_text(x) for x in node) + "]"
    return repr(node)


def _str_keys(obj: object) -> object:
    if isinstance(obj, dict):
        return {str(k): _str_keys(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_str_keys(v) for v in obj]
    return obj


def content_sha256(obj: object) -> str:
    """sha256 of a parsed document (YAML or JSON) by its content: comments and layout are gone
    once parsed. Keys are compared as strings, since YAML can mix them (`on:` is a bool)."""
    return hashlib.sha256(json.dumps(_str_keys(obj), sort_keys=True, default=str).encode("utf-8")).hexdigest()


def file_sha256(path: Path | None) -> str | None:
    """`source_sha256` of a .py file; any other file, or one that cannot be read, by its bytes
    (None when unreadable)."""
    if path is None:
        return None
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if Path(path).suffix != ".py":
        return hashlib.sha256(data).hexdigest()
    return source_sha256(data.decode("utf-8", errors="replace"))
