"""`evh <command>`: the harness as an installed tool.

Every command runs the same script `make <target>` runs in a checkout, with the same
arguments, so the two cannot drift: this file only maps names to scripts. The scripts
import each other as the package (`from evaluation_harness._common import ...`), so
nothing of theirs goes on sys.path and a project's own `stats.py` stays the project's.

Where the data lives is the PROJECT's business, not the package's:
  EVAL_HOME       the project root (default: the nearest directory up from here with data/)
  EVAL_DATA_DIR   the data root, relative to EVAL_HOME (default: data)
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import os
import runpy
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: command -> (script, one line of help). Names follow the Makefile targets.
COMMANDS = {
    "init": (
        "init_project.py",
        "start a project: --store files|sqlite (required), data folders, a .gitignore, AGENTS.md; --tutorial adds the GUIDE's kit",
    ),
    "skills-install": (
        "skills_install.py",
        "copy the agent skills (evaluate, compare, promote) into .claude/skills/ or --target",
    ),
    "env-check": ("env_check.py", "check the Python environment and keys"),
    "capture-scrub": (
        "capture_scrub.py",
        "run the project's own scrubber over a capture's records, and record it",
    ),
    "jobs-start": (
        "jobs_start.py",
        "start an operation as a job: detached, with its locks, log and state (RFC-026)",
    ),
    "jobs-status": ("jobs_status.py", "the jobs, or one job: its state, what it waits for, how it ended"),
    "jobs-logs": ("jobs_logs.py", "a job's log, from a byte on, or followed until it ends"),
    "jobs-stop": ("jobs_stop.py", "stop a job: its process group, cancelled"),
    "jobs-resume": ("jobs_resume.py", "resume a stopped or lost run job, as a new job"),
    "openapi": ("openapi_doc.py", "the API's OpenAPI 3.1 description, made from the operations, as JSON"),
    "catalog-serve": ("catalog_serve.py", "serve the catalog and the run inspector on 127.0.0.1"),
    "mcp": (
        "mcp_server.py",
        "the project's read commands as MCP tools for an agent (stdio, or --http for a team; none writes the project or spends)",
    ),
    "self-test": (
        "self_check.py",
        "does the installed harness work here? (in a checkout: the full test suite)",
    ),
}
# The commands made from the model's operations (RFC-032): one script runs each, told which by EVH_COMMAND. The ops
# package imports no project code, so reading it here loads no .env early.
from evaluation_harness import ops as _ops  # noqa: E402

COMMANDS.update({name: ("op_command.py", op.about) for name, op in _ops.OPS.items()})


def _usage() -> str:
    from evaluation_harness._version import __version__  # noqa: PLC0415

    width = max(map(len, COMMANDS))
    rows = "\n".join(f"  {name:<{width}}  {help_}" for name, (_, help_) in COMMANDS.items())
    return (
        f"evaluation-harness {__version__}\n\nusage: evh <command> [args]\n\n{rows}\n\n"
        f"`evh <command> --help` for a command's own options.\n"
        f"Data: EVAL_HOME (project root, default: the nearest directory up with data/), EVAL_DATA_DIR (default: data), EVAL_GOALS_DIR (default: <data>/goals)."
    )


def main(argv: list[str] | None = None) -> int:
    """Dispatch evh commands to their scripts."""
    # No script directory on sys.path: the scripts import the package (evaluation_harness.*), and a
    # bare `stats` or `adapter` in a project is the project's own.
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0
    if argv[0] in ("-V", "--version", "version"):
        from evaluation_harness._version import __version__  # noqa: PLC0415

        print(__version__)
        return 0
    name, rest = argv[0], argv[1:]
    if name not in COMMANDS:
        print(f"evh: unknown command {name!r}\n\n{_usage()}", file=sys.stderr)
        return 2
    script = HERE / COMMANDS[name][0]
    # Before anything imports _common: it loads the project's .env at import, only for a harness
    # command, which it tells by argv[0]. Imported first, under the venv's bin/evh, it loaded none.
    sys.argv = [str(script), *rest]
    # The scripts' "next, run this" hints read it: `evh …` here, `make …` in a checkout.
    os.environ["EVAL_VIA_EVH"] = "1"
    os.environ["EVH_COMMAND"] = name  # which operation op_command.py runs
    from evaluation_harness._common import stray_home, use_p_cache  # noqa: PLC0415

    if note := stray_home():
        print(note, file=sys.stderr)
    # Every estimated p kept in the project's ignored .cache/, as `evh mcp` keeps them: each command is a new
    # process, and without it `goals` right after `catalog` drew every test again (PLAN_0.8.0 S1, 142 s at 1,000
    # items). EVH_P_CACHE names another file; an empty value turns it off.
    use_p_cache()
    from evaluation_harness._common import EXIT_INTERNAL, EXIT_INTERRUPTED, EXIT_REFUSED  # noqa: PLC0415

    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return EXIT_REFUSED
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception:  # noqa: BLE001 -- anything uncaught, told apart from a refusal (1) by its number
        traceback.print_exc()
        print(
            f"evh {name}: stopped by an error nothing caught (exit {EXIT_INTERNAL}); the traceback above says "
            "where: the harness, or the project's own code (an adapter, a scorer)",
            file=sys.stderr,
        )
        return EXIT_INTERNAL
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
