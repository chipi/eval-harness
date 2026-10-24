"""`evh <command>`: the harness as an installed tool.

Every command runs the same script `make <target>` runs in a checkout, with the same
arguments, so the two cannot drift: this file only maps names to scripts. The scripts
import each other as top-level modules (`from _common import ...`), which is why this
directory goes on sys.path before one runs.

Where the data lives is the PROJECT's business, not the package's:
  EVAL_HOME       the project root (default: the nearest directory up from here with data/)
  EVAL_DATA_DIR   the data root, relative to EVAL_HOME (default: data)
  EVAL_RUNS_DIR   runs only, for a throwaway pass (default: <data>/runs)
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: command -> (script, one line of help). Names follow the Makefile targets.
COMMANDS = {
    "init": (
        "init_project.py",
        "start a project: data folders, a .gitignore; --tutorial adds the GUIDE's kit",
    ),
    "env-check": ("env_check.py", "check the Python environment and keys"),
    "dataset-create": ("dataset_create.py", "freeze a dataset: item list + per-item sha256"),
    "dataset-materialize": ("materialize.py", "hash-checked working copy of a dataset"),
    "reference-create": ("reference_create.py", "make references from a run (--from-run) or with a config"),
    "experiment-run": ("experiment_run.py", "run one arm over a dataset (--dry-run to cost it)"),
    "sweep": ("sweep.py", "run several arms, then the leaderboard"),
    "runs-list": ("list_runs.py", "list runs (or baselines)"),
    "rescore": ("rescore.py", "re-score stored outputs against references, for $0"),
    "judge": (
        "judge_panel.py",
        "the judge panel: promote finalists on a cheap metric, judge their stored outputs",
    ),
    "judge-score": (
        "judge_score.py",
        "re-measure frozen outputs with a validated LLM judge (--dry-run first)",
    ),
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
    "round-open": (
        "round_open.py",
        "open a round of a goal (optional): its hypothesis, changes, arms kept or dropped",
    ),
    "round-retire": ("round_retire.py", "drop an arm from the open round, with the reason"),
    "round-close": ("round_close.py", "close a round with its conclusion, promoting the run it chose"),
    "rounds": ("round_status.py", "a goal's rounds, and what the evidence suggests next"),
    "datasets": ("view_datasets.py", "every dataset, or one: its versions, references and arms"),
    "references": ("view_references.py", "every reference, or one: who wrote it, what is scored against it"),
    "metrics": ("view_metrics.py", "what each metric measures, which way is better, where it is recorded"),
    "goals": ("view_goals.py", "every goal, or one: its arms on each of its datasets"),
    "search": ("view_search.py", "the catalog's search: datasets, arms, references, metrics, goals"),
    "inspect": (
        "view_inspect.py",
        "the inspector in the terminal: verdicts, conditions, a breakdown, one item, the per-item table, the charts",
    ),
    "catalog": ("catalog_build.py", "build the catalog: static pages over the runs, by dataset"),
    "catalog-serve": ("catalog_serve.py", "serve the catalog and the run inspector on 127.0.0.1"),
    "validate": ("validate_tree.py", "schema and integrity checks over the data tree"),
    "self-test": (
        "self_check.py",
        "does the installed harness work here? (in a checkout: the full test suite)",
    ),
}


def _usage() -> str:
    from _version import __version__  # noqa: PLC0415

    width = max(map(len, COMMANDS))
    rows = "\n".join(f"  {name:<{width}}  {help_}" for name, (_, help_) in COMMANDS.items())
    return (
        f"evaluation-harness {__version__}\n\nusage: evh <command> [args]\n\n{rows}\n\n"
        f"`evh <command> --help` for a command's own options.\n"
        f"Data: EVAL_HOME (project root, default: the nearest directory up with data/), EVAL_DATA_DIR (default: data), EVAL_GOALS_DIR (default: <data>/goals)."
    )


def main(argv: list[str] | None = None) -> int:
    """Dispatch evh commands to their scripts."""
    sys.path.insert(0, str(HERE))
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0
    if argv[0] in ("-V", "--version", "version"):
        from _version import __version__  # noqa: PLC0415

        print(__version__)
        return 0
    name, rest = argv[0], argv[1:]
    if name not in COMMANDS:
        print(f"evh: unknown command {name!r}\n\n{_usage()}", file=sys.stderr)
        return 2
    script = HERE / COMMANDS[name][0]
    sys.argv = [str(script), *rest]
    # The scripts' "next, run this" hints read it: `evh …` here, `make …` in a checkout.
    os.environ["EVAL_VIA_EVH"] = "1"
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
