"""`evh <command>`: the harness as an installed tool.

Every command runs the same script `make <target>` runs in a checkout, with the same
arguments, so the two cannot drift: this file only maps names to scripts. The scripts
import each other as the package (`from evaluation_harness._common import ...`), so
nothing of theirs goes on sys.path and a project's own `stats.py` stays the project's.

Where the data lives is the PROJECT's business, not the package's:
  EVAL_HOME       the project root (default: the nearest directory up from here with data/)
  EVAL_DATA_DIR   the data root, relative to EVAL_HOME (default: data)
  EVAL_RUNS_DIR   runs only, for a throwaway pass (default: <data>/runs)
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

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
    "dataset-profile": (
        "dataset_profile.py",
        "what is inside a dataset: items, lengths, the gold's shape, a link per item (text only with --with-text)",
    ),
    "dataset-items": (
        "dataset_items.py",
        "a dataset's profile: its shape, then one row per item (--item for one)",
    ),
    "reference-create": ("reference_create.py", "make references from a run (--from-run) or with a config"),
    "reference-manifest": (
        "reference_manifest.py",
        "the checksummed manifest of a reference a fetch script built",
    ),
    "experiment-run": ("experiment_run.py", "run one arm over a dataset (--dry-run to cost it)"),
    "arm-smoke": ("arm_smoke.py", "smoke an arm on a few items before its full run: checks, projection, flags"),
    "model-onboard": ("model_onboard.py", "onboard a model once: probe a build, write what was found into its record"),
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
    "importer-check": (
        "importer_check.py",
        "check an importer: its records are well-formed, ids unique, two reads the same",
    ),
    "capture": ("capture.py", "keep a production system's records as a capture (data/captures/)"),
    "reference-from-outcomes": (
        "reference_from_outcomes.py",
        "a reference from what production recorded afterwards, by recorded rules",
    ),
    "dataset-split": (
        "dataset_split.py",
        "split a dataset into <id>_dev and <id>_heldout, stable across versions",
    ),
    "capture-scrub": (
        "capture_scrub.py",
        "run the project's own scrubber over a capture's records, and record it",
    ),
    "captures": ("view_captures.py", "every capture, or one: what was read, when, the datasets made from it"),
    "dataset-from-capture": (
        "dataset_from_capture.py",
        "make a dataset version from a capture: choose records, freeze their bodies as items",
    ),
    "run-compare": ("compare_runs.py", "diff two runs, fingerprint first"),
    "run-promote": ("promote_baseline.py", "promote a run to a baseline, with a reason"),
    "round-open": (
        "round_open.py",
        "open a round of a goal (optional): its hypothesis, changes, arms kept or dropped",
    ),
    "round-retire": ("round_retire.py", "drop an arm from the open round, with the reason"),
    "round-close": ("round_close.py", "close a round with its conclusion, promoting the run it chose"),
    "rounds": ("round_status.py", "a goal's rounds, and what the evidence suggests next"),
    "overview": (
        "view_overview.py",
        "the catalog's home page: goals at a glance, activity, spend, coverage, what was recorded",
    ),
    "datasets": ("view_datasets.py", "every dataset, or one: its versions, references and arms"),
    "arms": ("view_arms.py", "every arm, or one: its metrics, runs, config, conditions and rounds"),
    "references": ("view_references.py", "every reference, or one: who wrote it, what is scored against it"),
    "metrics": ("view_metrics.py", "what each metric measures, or one in full with the arms recording it"),
    "goals": ("view_goals.py", "every goal, or one: its arms on each of its datasets"),
    "activity": (
        "view_activity.py",
        "the activity page: runs, spend and tokens by dataset, arm and kind, in a period",
    ),
    "search": ("view_search.py", "the catalog's search: datasets, arms, references, metrics, goals"),
    "inspect": (
        "view_inspect.py",
        "the inspector in the terminal: verdicts, conditions, a breakdown, one item, the per-item table, the charts",
    ),
    "catalog": ("catalog_build.py", "build the catalog: static pages over the runs, by dataset"),
    "catalog-serve": ("catalog_serve.py", "serve the catalog and the run inspector on 127.0.0.1"),
    "mcp": (
        "mcp_server.py",
        "the project's read commands as MCP tools for an agent (stdio, or --http for a team; none writes the project or spends)",
    ),
    "validate": ("validate_tree.py", "schema and integrity checks over the data tree"),
    "self-test": (
        "self_check.py",
        "does the installed harness work here? (in a checkout: the full test suite)",
    ),
}


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
