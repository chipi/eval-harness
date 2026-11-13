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
        "start a project: data folders, a .gitignore, AGENTS.md; --tutorial adds the GUIDE's kit",
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
    "dataset-card": (
        "dataset_card.py",
        "a dataset's card: what, where from, the datasheet's answers; or it as Croissant 1.1",
    ),
    "licences": ("view_licences.py", "the licences a dataset can name (SPDX ids), a line each"),
    "migrate": (
        "migrate.py",
        "bring the project's data to this release's formats: runs, datasets, records, fingerprints, once (idempotent)",
    ),
    "data-migrate": (
        "data_migrate.py",
        "move the project's data/ into its SQLite database or back (RFC-025)",
    ),
    "data-ls": ("data_ls.py", "list what the project keeps under data/, in either store (UXS-004)"),
    "data-show": ("data_show.py", "show one file of the project's data"),
    "data-put": ("data_put.py", "create or change a setting (system, goal, fieldset, ...), checked first"),
    "data-rm": ("data_rm.py", "delete a setting, or a whole run"),
    "dataset-materialize": ("materialize.py", "hash-checked working copy of a dataset"),
    "dataset-profile": (
        "dataset_profile.py",
        "what is inside a dataset: items, lengths, the gold's shape, a link per item (text only with --with-text)",
    ),
    "dataset-items": (
        "dataset_items.py",
        "a dataset's profile: its shape, then one row per item (--item for one)",
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
    "runs-list": ("list_runs.py", "list runs (the baselines: evh baselines)"),
    "rescore": ("rescore.py", "re-score stored outputs, a round's or a dataset's, for $0"),
    "score-preview": (
        "score_preview.py",
        "what the scorer in this tree would move in a goal's decision; writes nothing",
    ),
    "judge": (
        "judge_panel.py",
        "the judge panel: promote finalists on a cheap metric, judge their stored outputs",
    ),
    "judge-score": (
        "judge_score.py",
        "re-measure frozen outputs with a validated LLM judge (--dry-run first)",
    ),
    "silver-calibrate": ("silver_calibrate.py", "how far silver reference sets drift from gold"),
    "cost-report": ("cost_report.py", "billed cost per arm, with projections"),
    "leaderboard": ("leaderboard.py", "rank arms, with Friedman/Nemenyi before any order"),
    "pair-test": ("pair_test.py", "paired permutation test, two arms"),
    "family-test": ("family_test.py", "one arm against a declared family, Holm-corrected"),
    "bootstrap-test": ("bootstrap_test.py", "bootstrap intervals for corpus-level metrics"),
    "holdout": ("holdout_significance.py", "tune on a pilot slice, confirm on the rest"),
    "rank-stability": ("rank_stability.py", "how many items a ranking needs"),
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
    "captures": ("view_captures.py", "every capture, or one: what was read, when, the datasets made from it"),
    "labels": (
        "view_labels.py",
        "every label set, or a dataset's: source, coverage, guideline, how often two agree",
    ),
    "tags": (
        "view_tags.py",
        "the failure modes tagged on outputs: every tag set, or per arm on a dataset how often each mode was",
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
    "label-coverage": (
        "label_coverage.py",
        "how far an outcome rule set labels a dataset now: labelled, skipped, not yet mature (and when), unmatched",
    ),
    "pick": ("pick.py", "pick production items for the next version of governed datasets, or drop a pick"),
    "exposure-add": (
        "exposure_add.py",
        "record reads of a held-out side's items: each is left out of every later score on it (RFC-031)",
    ),
    "exposure": ("view_exposure.py", "a held-out side's exposure register, in counts (RFC-031)"),
    "label-mutants": (
        "label_mutants.py",
        "mutation-test a labeller: each named change to the rules or the join must move some labels (RFC-031)",
    ),
    "periods": (
        "view_periods.py",
        "a code record's deployed periods, numbered, dated, with their faithfulness (RFC-031)",
    ),
    "period-compare": (
        "period_compare.py",
        "a past period's items: production, the code that ran then, and a candidate, with the paired test (RFC-031)",
    ),
    "exposure-check": (
        "exposure_check.py",
        "search the project's public repos for a held-out side's item ids: leaks the register lacks (RFC-031)",
    ),
    "sealed-counts": (
        "sealed_counts.py",
        "counts over a held-out side by the fields it was sealed with: for safety, never to judge effect (RFC-031)",
    ),
    "dataset-seal-counts": (
        "dataset_seal_counts.py",
        "allow one more field in a held-out side's counts: a person's decision, recorded (RFC-031)",
    ),
    "picks": (
        "view_picks.py",
        "the picks waiting: per target, where each came from, its labels, tags and note",
    ),
    "dataset-extend": (
        "dataset_extend.py",
        "the next version of a dataset: its items and the picks you choose",
    ),
    "deploy-sheet": (
        "deploy_sheet.py",
        "what production must match to run a promoted arm, and whether a capture says it did",
    ),
    "arm-from-capture": (
        "arm_from_capture.py",
        "production's recorded decisions as an arm, scored like any (no call)",
    ),
    "dataset-from-capture": (
        "dataset_from_capture.py",
        "make a dataset version from a capture: choose records, freeze their bodies as items",
    ),
    "run-compare": ("compare_runs.py", "diff two runs, fingerprint first"),
    "baselines": (
        "view_baselines.py",
        "the baselines: each goal's on each dataset, and each dataset's own, with evidence and history (--json: the export)",
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
    "rounds": ("round_status.py", "a goal's rounds, and what the evidence suggests next"),
    "studies": (
        "view_studies.py",
        "every study, by goal: its status, trials, what it kept and spent; --study one, trial by trial (RFC-029)",
    ),
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
    "looks": (
        "view_looks.py",
        "the looks each test set allows: its looks so far, the next one's level, its limit",
    ),
    "faithfulness": (
        "faithfulness.py",
        "replay a system at the commits production ran and compare it with production's arm, item by item",
    ),
    "faithfulness-name": (
        "faithfulness_name.py",
        "name a replay's disagreement whose cause is outside the system (a person's decision)",
    ),
    "faithfulness-show": (
        "faithfulness_show.py",
        "a faithfulness record: counts, disagreements and who named which, coverage",
    ),
    "prompts": (
        "view_prompts.py",
        "prompt versions: every name, or one's versions, lineage and the runs that used each",
    ),
    "prompt-diff": (
        "prompt_diff.py",
        "two prompt versions compared: their text as a diff, and the runs of each",
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
    "overview": (
        "view_overview.py",
        "the catalog's home page: goals at a glance, activity, spend, coverage, what was recorded",
    ),
    "datasets": ("view_datasets.py", "every dataset, or one: its versions, reference sets and arms"),
    "arms": ("view_arms.py", "every arm, or one: its metrics, runs, system, conditions and rounds"),
    "models": (
        "view_models.py",
        "every model record, or one: its deployments, onboarding, settings history and arms",
    ),
    "references": (
        "view_references.py",
        "every reference set, or one: who wrote it, what is scored against it",
    ),
    "metrics": ("view_metrics.py", "what each metric measures, or one in full with the arms recording it"),
    "goals": ("view_goals.py", "every goal, or one: its arms on each of its datasets"),
    "activity": (
        "view_activity.py",
        "the activity page: runs, spend and tokens by dataset, arm and kind, in a period",
    ),
    "search": ("view_search.py", "the catalog's search: datasets, arms, reference sets, metrics, goals"),
    "inspect": (
        "view_inspect.py",
        "the inspector in the terminal: verdicts, conditions, a breakdown, one item, the charts, the sheet of a dataset",
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
    from evaluation_harness._common import project_root, stray_home  # noqa: PLC0415

    if note := stray_home():
        print(note, file=sys.stderr)
    # Every estimated p kept in the project's ignored .cache/, as `evh mcp` keeps them: each command is a new
    # process, and without it `goals` right after `catalog` drew every test again (PLAN_0.8.0 S1, 142 s at 1,000
    # items). EVH_P_CACHE names another file; an empty value turns it off.
    os.environ.setdefault("EVH_P_CACHE", str(project_root() / ".cache" / "evh-p.jsonl"))
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
