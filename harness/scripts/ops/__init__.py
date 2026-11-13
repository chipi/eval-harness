"""The model's operations (RFC-032): each declared once, with its inputs as JSON Schema, what kind it is (read, edit,
decision, work), its resource route and its command, and every surface made from it: `evh <command>`
(`ops.cli`), the API's resource (`catalog_serve`), the MCP tool of a read.

Importing this package imports no project code: `evh` reads the commands from it before the project's .env is loaded.
"""

from __future__ import annotations

from evaluation_harness.ops.registry import OPS, Op, get, of_kind

__all__ = ["OPS", "Op", "get", "of_kind"]
