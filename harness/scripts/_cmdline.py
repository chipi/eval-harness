"""An operation run as its own process, for what must not run its body in a server's (RFC-032 P3): the agent sampler's
two MCP tools (`study-ask`, `study-tell`, work operations) and the API's estimate (an operation's `dry_run`, run now). Its
inputs in a file under the project's .build/calls (read through the store, which serves the project's paths), `evh
<operation> --json --inputs-file F` in the project, in its own process group with a timeout that kills the group."""

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
TIMEOUT_S = 300
#: A tool argument's bounds: no input takes a longer value (an id, a period, a search's words).
MAX_VALUE = 512
MAX_VALUES = 64
#: The environment variables that name a path from where a command stands (EVAL_DATA_DIR is relative to
#: the project root, _common._paths, so it stays as it is).
PATH_VARS = ("EVAL_HOME", "EVH_P_CACHE")


def public_error(text: str, project: Path) -> str:
    """A command's refusal as a public caller is told it: its own message, with no server path and
    no traceback (a crash is "internal error"; the log and the error tracker have the rest)."""
    if "Traceback (most recent call last)" in text:
        return "internal error: the command failed; it is reported to the server's maintainers"
    lines = [ln for ln in text.splitlines() if ln.strip()]
    msg = next((ln for ln in reversed(lines) if ln.startswith("ERROR")), lines[-1] if lines else "")
    for root in sorted({str(project), str(project.resolve()), str(HERE.parent)}, key=len, reverse=True):
        msg = msg.replace(root + "/", "").replace(root, ".")
    return re.sub(r"/(?:[\w.-]+/)+", "", msg)[:2000]


def run_operation(
    project: Path,
    operation: str,
    inputs: dict[str, Any],
    timeout: float = TIMEOUT_S,
    started: list[subprocess.Popen] | None = None,
) -> tuple[int, str, str]:
    """`evh <operation> --json --inputs-file F` in the project, its inputs written to F under .build/calls and the file
    removed after; stdin closed, in its own process group, with a timeout that kills the group. `started` receives the
    process, for a caller that may have to stop it (a cancelled call, kill_group)."""
    import uuid  # noqa: PLC0415

    from evaluation_harness import _common  # noqa: PLC0415

    calls = Path(project) / ".build" / "calls"
    calls.mkdir(parents=True, exist_ok=True)
    path = calls / f"{uuid.uuid4().hex}.json"
    _common.write_text_atomic(path, json.dumps(inputs))
    try:
        return _run(project, [operation, "--json", "--inputs-file", str(path)], timeout, started)
    finally:
        path.unlink(missing_ok=True)


def _run(
    project: Path, argv: list[str], timeout: float, started: list[subprocess.Popen] | None
) -> tuple[int, str, str]:
    cmd = [sys.executable, str(HERE / "cli.py"), *argv]
    # The goals' tests are the slow part of a view (~50 s for this repository's runs); each call is a
    # fresh process, so they are kept on disk (stats.EVH_P_CACHE), in the project's ignored .cache/
    # unless the deployment names its own precomputed file.
    env = dict(os.environ)
    # The command runs in the project, so a relative path the caller set is made absolute from where the
    # caller stands: render.sh ran `EVAL_HOME=_release/inspector`, the commands resolved it inside the project
    # and read an empty one, and every answer written ahead for 0.6.2 to 0.7.1 said there were no goals.
    for k in PATH_VARS:
        if env.get(k) and not os.path.isabs(env[k]):
            env[k] = os.path.abspath(env[k])
    from evaluation_harness._common import p_cache_path  # noqa: PLC0415

    env.setdefault("EVH_P_CACHE", p_cache_path(project))
    env.pop("EVH_PUBLIC", None)
    p = subprocess.Popen(
        cmd,
        cwd=project,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    if started is not None:
        started.append(p)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        kill_group(p)
        out, err = p.communicate()
        return 124, out, err + f"\n(stopped after {timeout:g} s)"
    return p.returncode, out, err


def kill_group(p: subprocess.Popen) -> None:
    """Stop a command and everything it started (its own process group); one already gone is fine."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(p.pid, signal.SIGKILL)
