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
    "dataset-create": ("dataset_create.py", "freeze a dataset: item list + per-item sha256"),
    "dataset-describe": (
        "dataset_describe.py",
        "change a dataset's licence or description, never its items or version",
    ),
    "fieldset-propose": (
        "fieldset_propose.py",
        "a field set proposed from a dataset source's features, for a person to accept (--write)",
    ),
    "dataset-publish": (
        "dataset_publish.py",
        "publish a dataset to a new repo (Hugging Face), private first, read back and checked by sha256",
    ),
    "migrate": (
        "migrate.py",
        "bring the project's data to this release's formats: runs, datasets, records, fingerprints, once (idempotent)",
    ),
    "data-migrate": (
        "data_migrate.py",
        "move the project's data/ into its SQLite database or back (RFC-025)",
    ),
    "data-put": ("data_put.py", "create or change a setting (system, goal, fieldset, ...), checked first"),
    "data-rm": ("data_rm.py", "delete a setting, or a whole run"),
    "dataset-materialize": ("materialize.py", "hash-checked working copy of a dataset"),
    "dataset-profile": (
        "dataset_profile.py",
        "what is inside a dataset: items, lengths, the gold's shape, a link per item (text only with --with-text)",
    ),
    "reference-promote": (
        "reference_promote.py",
        "promote a label set's labels to a reference set, at a tier, with a reason",
    ),
    "reference-manifest": (
        "reference_manifest.py",
        "the checksummed manifest of a reference set a fetch script built",
    ),
    "run": ("run.py", "run one arm over a dataset (--dry-run to cost it)"),
    "arm-smoke": (
        "arm_smoke.py",
        "smoke an arm on a few items before its full run: checks, projection, flags",
    ),
    "model-onboard": (
        "model_onboard.py",
        "onboard a model once: probe a deployment, write what was found into its record",
    ),
    "sweep": ("sweep.py", "run several arms, then the leaderboard"),
    "rescore": ("rescore.py", "re-score stored outputs, a round's or a dataset's, for $0"),
    "score-preview": (
        "score_preview.py",
        "what the scorer in this tree would move in a goal's decision; writes nothing",
    ),
    "judge-score": (
        "judge_score.py",
        "re-measure frozen outputs with a validated LLM judge (--dry-run first)",
    ),
    "silver-calibrate": ("silver_calibrate.py", "how far silver reference sets drift from gold"),
    "cost-report": ("cost_report.py", "billed cost per arm, and what judging cost"),
    "bootstrap-test": ("bootstrap_test.py", "bootstrap intervals for corpus-level metrics"),
    "holdout": ("holdout_significance.py", "tune on a pilot slice, confirm on the rest"),
    "import-run": ("import_run.py", "per-item scores from another tool, as a run the tests can read"),
    "importer-check": (
        "importer_check.py",
        "check an importer: its records are well-formed, ids unique, two reads the same",
    ),
    "capture": ("capture.py", "keep a production system's records as a capture (data/captures/)"),
    "dataset-split": (
        "dataset_split.py",
        "split a dataset into <id>_validation and <id>_test, stable across versions",
    ),
    "dataset-unseal": (
        "dataset_unseal.py",
        "open a sealed test side to one candidate system whose hypothesis is committed (one look)",
    ),
    "capture-restore": (
        "capture_restore.py",
        "read a capture's records again from its source, and the items of the datasets made from it, every hash checked",
    ),
    "capture-scrub": (
        "capture_scrub.py",
        "run the project's own scrubber over a capture's records, and record it",
    ),
    "sheet-export": (
        "sheet_export.py",
        "a dataset's sheet written as a CSV to fill in: what each run wrote and scored beside every item, the columns to fill (--fill label|pick|scores|tags)",
    ),
    "label-sheet": (
        "label_sheet.py",
        "a sheet of a dataset's items to label, with what production or an arm decided",
    ),
    "label-import": ("label_import.py", "a filled label sheet as a person's label set"),
    "sheet-import": (
        "sheet_import.py",
        "a sheet filled elsewhere, read back: labels as a label set, picks or scores as judged runs",
    ),
    "label-from-run": (
        "label_from_run.py",
        "a finished run's outputs as a model's label set (calls nothing)",
    ),
    "label-from-capture": (
        "label_from_capture.py",
        "rules over a capture's recorded outcomes as a rule label set",
    ),
    "pick": ("pick.py", "pick production items for the next version of governed datasets, or drop a pick"),
    "exposure-add": (
        "exposure_add.py",
        "record reads of a held-out side's items: each is left out of every later score on it (RFC-031)",
    ),
    "exposure-check": (
        "exposure_check.py",
        "search the project's public repos for a held-out side's item ids: leaks the register lacks (RFC-031)",
    ),
    "dataset-seal-counts": (
        "dataset_seal_counts.py",
        "allow one more field in a held-out side's counts: a person's decision, recorded (RFC-031)",
    ),
    "dataset-extend": (
        "dataset_extend.py",
        "the next version of a dataset: its items and the picks you choose",
    ),
    "arm-from-capture": (
        "arm_from_capture.py",
        "production's recorded decisions as an arm, scored like any (no call)",
    ),
    "dataset-from-capture": (
        "dataset_from_capture.py",
        "make a dataset version from a capture: choose records, freeze their bodies as items",
    ),
    "baseline-rollback": (
        "baseline_rollback.py",
        "roll a baseline back to an earlier version, as a new version with its own evidence",
    ),
    "run-promote": ("promote_baseline.py", "promote a run to a baseline, with a reason"),
    "round-open": (
        "round_open.py",
        "open a round of a goal (optional): its hypothesis, changes, arms kept or dropped",
    ),
    "round-carry": ("round_carry.py", "carry an arm of an earlier round into the open round, unchanged"),
    "round-retire": ("round_retire.py", "drop an arm from the open round, with the reason"),
    "round-close": ("round_close.py", "close a round with its conclusion, promoting the run it chose"),
    "study-run": (
        "study_run.py",
        "open a study and run its loop on validation items: research, never evidence",
    ),
    "study-ask": ("study_ask.py", "a study's state for the agent sampler, with an ask id"),
    "study-tell": ("study_tell.py", "the agent sampler's proposal, run as the study's next trial"),
    "study-stop": ("study_stop.py", "stop a study after its current trial"),
    "study-confirm": (
        "study_confirm.py",
        "a study's best trial against its baseline on a test set: one look, the evidence",
    ),
    "study-import": ("study_import.py", "a past loop's results.tsv as a closed study (not confirmable)"),
    "faithfulness": (
        "faithfulness.py",
        "replay a system at the commits production ran and compare it with production's arm, item by item",
    ),
    "faithfulness-name": (
        "faithfulness_name.py",
        "name a replay's disagreement whose cause is outside the system (a person's decision)",
    ),
    "prompt-version": (
        "prompt_version.py",
        "record a prompt version from a file or text, with its parent and a note",
    ),
    "prompt-export": ("prompt_export.py", "write a prompt version out, for a person to commit"),
    "jobs-start": (
        "jobs_start.py",
        "start a command as a job: detached, with its locks, log and state (RFC-026)",
    ),
    "jobs-status": ("jobs_status.py", "the jobs, or one job: its state, what it waits for, how it ended"),
    "jobs-logs": ("jobs_logs.py", "a job's log, from a byte on, or followed until it ends"),
    "jobs-stop": ("jobs_stop.py", "stop a job: its process group, cancelled"),
    "jobs-resume": ("jobs_resume.py", "resume a stopped or lost run job, as a new job"),
    "openapi": ("openapi_doc.py", "the API's OpenAPI 3.1 description, made from the operations, as JSON"),
    "catalog": ("catalog_build.py", "build the catalog: static pages over the runs, by dataset"),
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
