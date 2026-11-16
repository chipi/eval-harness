"""An operation read in this process through a chosen catalog adapter, as the text its command prints (the way the
tests of the views ran the old view commands with their loader replaced). The adapter's data directory is the data the
model reads while the block runs, marked with the current format when it has no mark. The fixtures of the catalog tests
are plain files outside the project's own data, so the block reads them as the files store does, whatever store the suite
runs on."""

import contextlib
import io
import json
import os
from pathlib import Path
from typing import Any

from evaluation_harness import _common, _format, catalog_serve, mcp_server
from evaluation_harness.model.entity import Problem
from evaluation_harness.ops import OPS, registry


@contextlib.contextmanager
def served(A: Any):
    """`A` is the adapter the views read, and its data directory the data root, while the block runs."""
    real = getattr(catalog_serve, "A", None)
    env = os.environ.get("EVAL_DATA_DIR")
    store = os.environ.get("EVAL_STORE")
    data = getattr(A, "data_dir", None)
    if A is not None:
        catalog_serve.A = A
    if data is not None:
        mark = data / _format.NAME
        if not mark.exists() and data.is_dir():
            mark.write_text(f"format: {_format.FORMAT}\n")
        os.environ["EVAL_DATA_DIR"] = str(data)
        os.environ["EVAL_STORE"] = "files"
        _common._paths.cache_clear()
    try:
        yield
    finally:
        catalog_serve.A = real  # type: ignore[assignment]  # None: no adapter was set before
        if data is not None:
            for k, v in (("EVAL_DATA_DIR", env), ("EVAL_STORE", store)):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            _common._paths.cache_clear()


def result(name: str, A: Any = None, **kwargs: Any) -> dict[str, Any]:
    """The operation's answer as data, read through `A` and never from the view cache."""
    with served(A):
        return registry._load(OPS[name].run)(**kwargs)


def view(name: str, A: Any = None, **kwargs: Any) -> str:
    """What `evh <name>` prints for these inputs, read through `A`; a refusal raises `Problem`."""
    op = OPS[name]
    with served(A):
        if op.printer:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                op.print_text(**kwargs)
            return buf.getvalue()
        return op.say(registry._load(op.run)(**kwargs))


def mcp(
    project: Any, tool: str, arguments: dict[str, Any] | None = None, public: bool = True
) -> tuple[int, str, str]:
    """A tool call as the MCP server answers it in its own process: (exit code, the envelope as JSON, the refusal). The
    process is the project's while it runs and is as it was after."""
    cwd, home, via = os.getcwd(), os.environ.get("EVAL_HOME"), os.environ.get("EVAL_VIA_EVH")
    args = dict(arguments or {})
    try:
        mcp_server.use_project(Path(project))
        op = OPS[tool]
        mcp_server.check_arguments(op, args, public)
        return 0, json.dumps(mcp_server.run_op(op, args, public)), ""
    except (Problem, ValueError, RuntimeError) as exc:
        return 1, "", str(exc)
    finally:
        os.chdir(cwd)
        for k, v in (("EVAL_HOME", home), ("EVAL_VIA_EVH", via)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _common.project_root.cache_clear()
        _common._paths.cache_clear()
