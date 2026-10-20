"""`evh <command>`: the harness as an installed tool.

Every command runs the same script `make <target>` runs in a checkout, with the same
arguments, so the two cannot drift: this file only maps names to scripts. The scripts
import each other as top-level modules (`from _common import ...`), which is why this
directory goes on sys.path before one runs.

Where the data lives is the PROJECT's business, not the package's:
  EVAL_HOME       the project root (default: the current directory)
  EVAL_DATA_DIR   the data root, relative to EVAL_HOME (default: data)
  EVAL_RUNS_DIR   runs only, for a throwaway pass (default: <data>/runs)
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: command -> (script, one line of help). Names follow the Makefile targets.
COMMANDS = {
    "env-check": ("env_check.py", "check the Python environment and keys"),
    "dataset-create": ("dataset_create.py", "freeze a dataset: item list + per-item sha256"),
    "dataset-materialize": ("materialize.py", "hash-checked working copy of a dataset"),
    "reference-create": ("reference_create.py", "draft silver references with a config"),
    "experiment-run": ("experiment_run.py", "run one arm over a dataset (--dry-run to cost it)"),
    "sweep": ("sweep.py", "run several arms, then the leaderboard"),
    "runs-list": ("list_runs.py", "list runs (or baselines)"),
    "rescore": ("rescore.py", "re-score stored outputs against references, for $0"),
    "silver-calibrate": ("silver_calibrate.py", "how far silver references drift from gold"),
    "cost-report": ("cost_report.py", "billed cost per arm, with projections"),
    "leaderboard": ("leaderboard.py", "rank arms, with Friedman/Nemenyi before any order"),
    "pair-test": ("pair_test.py", "paired permutation test, two arms"),
    "family-test": ("family_test.py", "one arm against a declared family, Holm-corrected"),
    "bootstrap-test": ("bootstrap_test.py", "bootstrap intervals for corpus-level metrics"),
    "holdout": ("holdout_significance.py", "tune on a dev slice, confirm on the rest"),
    "rank-stability": ("rank_stability.py", "how many items a ranking needs"),
    "import-run": ("import_run.py", "per-item scores from another tool, as a run the tests can read"),
    "run-compare": ("compare_runs.py", "diff two runs, fingerprint first"),
    "run-promote": ("promote_baseline.py", "promote a run to a baseline, with a reason"),
    "validate": ("validate_tree.py", "schema and integrity checks over the data tree"),
    "self-test": ("self_test.py", "the harness's own test suite"),
}


def _usage() -> str:
    from _version import __version__

    width = max(map(len, COMMANDS))
    rows = "\n".join(f"  {name:<{width}}  {help_}" for name, (_, help_) in COMMANDS.items())
    return (f"evaluation-harness {__version__}\n\nusage: evh <command> [args]\n\n{rows}\n\n"
            f"`evh <command> --help` for a command's own options.\n"
            f"Data: EVAL_HOME (project root, default: cwd), EVAL_DATA_DIR (default: data).")


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(HERE))
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0
    if argv[0] in ("-V", "--version", "version"):
        from _version import __version__
        print(__version__)
        return 0
    name, rest = argv[0], argv[1:]
    if name not in COMMANDS:
        print(f"evh: unknown command {name!r}\n\n{_usage()}", file=sys.stderr)
        return 2
    script = HERE / COMMANDS[name][0]
    sys.argv = [str(script), *rest]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        print(code, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
