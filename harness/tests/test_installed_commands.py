#!/usr/bin/env python3
"""Every `evh` command, run the way a project that pins the package runs it.

    python tests/test_installed_commands.py

The package is installed from its wheel (_wheel.py) beside a fresh project with the tutorial
dataset, gold references and three arms. Each command in cli.COMMANDS has one case here: it
must finish without a traceback, and either succeed or refuse with the message named. A
command with no case fails the test, so a new command cannot ship untried.

Why: every bug of this kind found so far (rescore and silver-calibrate looking for
`scripts/adapter.py`, rank-stability defaulting to another project's metric, self-test
checking this repository's own reports) passed in a checkout and broke in a pinned project.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
REPO = HERE.parent.parent  # the checkout (infra/ is not part of the package)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))  # _wheel, shared with the deploy
import _runstore  # noqa: E402

STORE = "sqlite" if _runstore.sqlite() else "files"
import _wheel  # noqa: E402
from evaluation_harness import _common, _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.cli import COMMANDS  # noqa: E402


def put(proj: Path, rel: str, content: bytes) -> None:
    """A fixture file in the project's data/ (rel as under data/), in its store, its folder made where one exists."""
    _common.project_root.cache_clear()  # this process resolved its own project on import; _runstore aims by EVAL_HOME
    with _runstore._InProject(proj) as data:
        _store.mkdir((data / rel).parent, parents=True, exist_ok=True)
        _store.write_bytes(data / rel, content)


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="evh-commands-"))
    try:
        site = _wheel.install(tmp / "site-packages")
        proj = tmp / "proj"
        proj.mkdir()
        env = {
            **os.environ,
            "EVH_ACTOR": "person:test",
            "PYTHONPATH": str(site),
            "PYTHONDONTWRITEBYTECODE": "1",
            "EVAL_BUILD_REF": "test-commands",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }
        for k in ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
            env.pop(k, None)

        def evh(*args: str, timeout: int = 600, cwd: Path | None = None) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, "-m", "evaluation_harness", *args],
                cwd=cwd or proj,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        # Importing the package's modules, as INTEGRATION.md documents: `evaluation_harness.judging`
        # did not import at all, and catalog_adapter + judging loaded `_common` twice.
        import_probe = (
            "import sys, evaluation_harness.judging, evaluation_harness.catalog_adapter\n"
            # The harness's own: a bare `_common` or one under evaluation_harness. Python 3.14's stdlib
            # has its own compression._common, which is not the harness's and was counted as a second.
            "print(sorted(m for m in sys.modules if m == '_common' or m.startswith('evaluation_harness.') and m.endswith('._common')))\n"
        )
        r = subprocess.run(
            [sys.executable, "-c", import_probe],
            cwd=proj,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        check(
            "import evaluation_harness.judging and .catalog_adapter: one _common",
            r.returncode == 0 and r.stdout.strip() == "['evaluation_harness._common']",
            (r.stdout + r.stderr).strip()[-300:],
        )

        def setup(*args: str) -> None:
            r = evh(*args)
            if r.returncode:
                raise SystemExit(f"setup: evh {' '.join(args)}\n{r.stdout}{r.stderr}")

        setup("init", "--tutorial")
        setup("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
        setup(
            "dataset-create",
            "--dataset-id",
            "tickets_pilot_v1",
            "--source-dir",
            "tutorial/tickets",
            "--limit",
            "2",
        )
        setup("dataset-materialize", "--dataset-id", "tickets_v1")
        for f in sorted((proj / "tutorial/systems").glob("tickets_*.yaml")):
            put(proj, f"systems/{f.name}", f.read_bytes())
        setup(
            "label-import",
            "tutorial/gold",
            "--dataset-id",
            "tickets_v1",
            "--set",
            "owner_gold",
            "--by",
            "owner",
        )
        setup(
            "reference-promote",
            "--dataset-id",
            "tickets_v1",
            "--labels",
            "owner_gold",
            "--tier",
            "gold",
            "--reason",
            "The kit's hand-written summaries decide.",
            "--by",
            "owner",
        )
        # gold a script builds, for reference-manifest below: the texts where a fetch script would put them
        for f in sorted((proj / "tutorial/gold").glob("*.txt"))[:2]:
            put(proj, f"references/gold/tickets_pilot_v1/{f.name}", f.read_bytes())
        for arm in ("lead1", "lead2", "lead2_noisy", "author"):
            setup("run", "--system", f"tickets_{arm}_v1", "--dataset", "tickets_v1", "--repeat", "2")
        for f in sorted((proj / "tutorial/scorers").rglob("*")):
            if f.is_file():
                put(proj, f"scorers/{f.relative_to(proj / 'tutorial/scorers').as_posix()}", f.read_bytes())
        run_names = _runstore.listdir(proj, "runs")
        run_id = sorted(n for n in run_names if n.startswith("tickets_lead2_v1_"))[0]
        base_id = sorted(n for n in run_names if n.startswith("tickets_lead1_v1_"))[0]
        (proj / "imported.jsonl").write_text(
            "".join(
                json.dumps({"item_id": i, "acc": 1.0}) + "\n"
                for i in (
                    it["item_id"] for it in _runstore.read_json(proj, "datasets/tickets_v1.json")["items"]
                )
            )
        )
        subprocess.run(["git", "init", "-q"], cwd=proj, env=env)
        subprocess.run(["git", "add", "-A"], cwd=proj, env=env)
        subprocess.run(["git", "commit", "-qm", "start"], cwd=proj, env=env)

        # (command, args, expect): "ok" = exit 0; "ok:TEXT" = exit 0 and TEXT printed; any other
        # string = a refusal (non-zero exit) whose output contains it.
        cases: list[tuple[str, list, str]] = [
            ("init", ["--help"], "ok"),
            ("skills-install", ["--target", "installed-skills"], "ok:evh-evaluate-a-system"),
            ("env-check", [], "ok"),
            (
                "dataset-create",
                ["--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets"],
                "already exists",
            ),
            ("dataset-materialize", ["--dataset-id", "tickets_v1"], "ok"),
            ("dataset-profile", ["--dataset-id", "tickets_v1"], "ok:tickets_v1: 6 items"),
            ("dataset-items", ["--dataset-id", "tickets_v1"], "ok:6 items"),
            ("label-from-run", ["--run", run_id, "--set", "installed_from_run"], "ok:label(s), source model"),
            (
                "reference-manifest",
                [
                    "--reference-id",
                    "gold/tickets_pilot_v1",
                    "--source",
                    "tutorial/gold",
                    "--labelled-by",
                    "the kit's author",
                    "--reason",
                    "the kit's own answers decide",
                    "--by",
                    "owner",
                ],
                "ok:2 item(s), gold, promoted from person",
            ),
            ("run", ["--system", "tickets_lead1_v1", "--dataset", "tickets_v1", "--dry-run"], "ok"),
            (
                "sweep",
                [
                    "--systems",
                    "tickets_lead1_v1",
                    "tickets_lead2_v1",
                    "--dataset",
                    "tickets_v1",
                    "--dry-run",
                ],
                "ok",
            ),
            ("runs-list", [], "ok"),
            (
                "rescore",
                [
                    "--dataset-id",
                    "tickets_v1",
                    "--reference-id",
                    "gold/tickets_v1",
                    "--out",
                    "data/runs-gold",
                ],
                "ok",
            ),
            (
                "judge-score",
                ["--dataset-id", "tickets_v1", "--scorer", "tickets-judge-v1", "--unvalidated", "--dry-run"],
                "ok",
            ),
            ("silver-calibrate", ["--dataset-id", "tickets_v1"], "ok"),
            ("cost-report", ["--dataset-id", "tickets_v1"], "ok"),
            ("leaderboard", ["--dataset-id", "tickets_v1"], "ok"),
            ("judge", ["--config", "tutorial/judge_panel.yaml", "--use-fake-judge"], "ok:Report written"),
            # No --metric: the default is the runs' recorded primary metric, not another project's.
            (
                "pair-test",
                ["--dataset-id", "tickets_v1", "--a", "tickets_lead2_v1", "--b", "tickets_lead1_v1"],
                "ok:overlap_f1",
            ),
            (
                "family-test",
                ["--dataset-id", "tickets_v1", "--a", "tickets_lead2_v1", "--against", "tickets_"],
                "ok:overlap_f1",
            ),
            (
                "bootstrap-test",
                ["--dataset-id", "tickets_v1", "--a", "tickets_lead2_v1", "--against", "tickets_"],
                "for classification",
            ),
            ("holdout", ["--dataset-id", "tickets_v1", "--exclude-dataset", "tickets_pilot_v1"], "ok"),
            ("rank-stability", ["--dataset-id", "tickets_v1"], "too few"),
            (
                "import-run",
                [
                    "--dataset-id",
                    "tickets_v1",
                    "--system-id",
                    "imported_v1",
                    "--scores",
                    "imported.jsonl",
                    "--primary-metric",
                    "acc",
                    "--build-ref",
                    "tool-1.0",
                    "--source",
                    "another tool",
                    "--scorer-id",
                    "acc-v1",
                ],
                "ok",
            ),
            # The capture lane (RFC-019), on the same scores file read as records.
            (
                "importer-check",
                ["jsonl", "--query", '{"path": "imported.jsonl", "id": "item_id"}'],
                "ok:PASS",
            ),
            (
                "capture",
                [
                    "--importer",
                    "jsonl",
                    "--query",
                    '{"path": "imported.jsonl", "id": "item_id"}',
                    "--capture",
                    "c1",
                ],
                "ok:record(s) from jsonl",
            ),
            ("capture-scrub", ["c1", "--command", "true {records}"], "ok:0 of"),
            ("dataset-split", ["tickets_v1", "--test", "0.5", "--seed", "3"], "ok:tickets_v1_test"),
            (
                "dataset-unseal",
                ["tickets_v1_test", "--system", "nope_v1", "--reason", "only to read the arguments"],
                "is not sealed",
            ),
            ("baselines", [], "ok:no baselines yet"),
            (
                "baseline-rollback",
                [
                    "--goal",
                    "nope",
                    "--dataset",
                    "tickets_v1",
                    "--to",
                    "1",
                    "--reason",
                    "only to read the arguments",
                ],
                "no versions",
            ),
            ("captures", ["--capture", "c1"], "ok:c1:"),
            ("dataset-from-capture", ["c1", "--dataset-id", "captured_v1"], "ok:records kept"),
            ("capture-restore", ["--capture", "c1"], "ok:records restored"),
            # Labels (RFC-023): installed and reading their arguments; the flow is tests/test_label_sets.py.
            ("labels", [], "ok:tickets_v1/installed_from_run: model"),
            ("tags", [], "ok:No tag sets yet"),
            ("licences", ["--search", "share"], "ok:CC-BY-SA-4.0"),
            ("migrate", ["--dry-run"], "ok:this release reads"),
            # the project's own store: data-migrate moves into the store the setting names, and data-ls says it
            ("data-migrate", ["--to", STORE, "--dry-run"], f"ok:would move into the {STORE} store"),
            ("data-ls", [], f"ok:store: {STORE}"),
            ("data-show", ["datasets/tickets_v1.json"], "ok:written by the dataset-* commands"),
            (
                "data-put",
                ["datasets/tickets_v1.json", "--set", "x=1"],
                "is written by the dataset-* commands",
            ),
            ("data-rm", ["datasets/tickets_v1.json", "--dry-run"], "is written by the dataset-* commands"),
            ("dataset-publish", ["--dataset-id", "tickets_v1", "--to", "folder"], "cannot publish"),
            (
                "fieldset-propose",
                ["--source", "folder", "--query", '{"path": "tutorial/tickets"}', "--fieldset-id", "x"],
                "describes no features",
            ),
            ("dataset-card", ["--dataset-id", "tickets_v1", "--format", "croissant"], "ok:croissant/1.1"),
            (
                "dataset-create",
                [
                    "--dataset-id",
                    "installed_src",
                    "--source",
                    "folder",
                    "--query",
                    '{"path": "tutorial/tickets"}',
                ],
                "ok:item(s) from folder",
            ),
            ("dataset-describe", ["--dataset-id", "tickets_v1", "--licence", "nope"], "not on the list"),
            (
                "label-sheet",
                ["--dataset-id", "tickets_v1", "--items", "all", "--out", "installed_sheet.csv"],
                "ok:to label",
            ),
            (
                "label-import",
                ["installed_sheet.csv", "--dataset-id", "tickets_v1", "--set", "installed_v1", "--by", "t"],
                "no labels",
            ),
            (
                "sheet-import",
                ["installed_sheet.csv", "--dataset-id", "tickets_v1", "--by", "t", "--set", "installed_v2"],
                "nothing filled",
            ),
            ("label-from-run", ["--run", "no_such_run", "--set", "installed_v1"], "no finished run"),
            ("picks", [], "ok:No picks waiting"),
            ("deploy-sheet", ["--system", "no_such_v1"], "no run of that system"),
            ("pick", ["--dataset-id", "tickets_v1", "--item", "no_such_item"], "not in tickets_v1"),
            ("dataset-extend", ["tickets_v1", "--dataset-id", "tickets_v9", "--picks"], "no pick is waiting"),
            (
                "arm-from-capture",
                ["--dataset-id", "captured_v1", "--capture", "no_such_capture", "--as", "installed_rec_v1"],
                "no capture no_such_capture",
            ),
            (
                "reference-promote",
                [
                    "--dataset-id",
                    "tickets_v1",
                    "--labels",
                    "no_such_set",
                    "--tier",
                    "silver",
                    "--name",
                    "installed_x",
                    "--by",
                    "t",
                    "--reason",
                    "only to read the arguments",
                ],
                "no labels of tickets_v1/no_such_set",
            ),
            (
                "label-from-capture",
                [
                    "--dataset-id",
                    "captured_v1",
                    "--capture",
                    "c1",
                    "--map",
                    "no_such_map.yaml",
                    "--set",
                    "o1",
                ],
                "--map: no file",
            ),
            (
                "label-coverage",
                ["--dataset-id", "captured_v1", "--capture", "c1", "--map", "no_such_map.yaml"],
                "--map: no file",
            ),
            ("run-compare", ["--baseline", base_id, "--candidate", run_id], "ok"),
            (
                "run-promote",
                ["--run", run_id, "--reason", "the tutorial's working baseline, for this test"],
                "ok",
            ),
            # The pages in the terminal: the same answers as the catalog and the inspector.
            ("datasets", [], "ok:tickets_v1"),
            ("datasets", ["--dataset-id", "tickets_v1"], "ok:runs/tickets_v1/tickets_lead2_v1"),
            ("references", ["--reference-id", "gold/tickets_v1"], "ok:scored against it"),
            ("metrics", [], "ok:overlap_f1"),
            ("metrics", ["--metric", "overlap_f1"], "ok:on tickets_v1:"),
            ("overview", [], "ok:goals at a glance"),
            ("overview", ["--period", "all"], "ok:all time"),
            ("activity", ["--period", "all"], "ok:by dataset:"),
            ("datasets", ["--period", "30d"], "ok:runs in period"),
            ("arms", ["--by", "system", "--period", "30d"], "ok:system tickets_lead2_v1"),
            ("arms", ["--systems"], "ok:rank on each goal"),
            ("arms", ["--quality", "contender"], "ok:no arm matches: only arms a goal's decision weighs"),
            (
                "arms",
                ["--weights", "open"],
                "ok:no arm matches: an arm's weights come from the model records (data/models/",
            ),
            ("arms", [], "ok:runs/tickets_v1/tickets_lead2_v1"),
            ("arms", ["--arm", "runs/tickets_v1/tickets_lead2_v1"], "ok:metrics:"),
            ("arms", ["--arm", "tickets_lead2_v1"], "ok:scored against"),
            ("arms", ["--arm", "runs/tickets_v1/no_such_v1"], "no arm"),
            ("goals", [], "ok"),
            # The goal through the model (RFC-032 step 1): the flow is test_model_goals.py.
            ("goal-list", [], "ok"),
            # The system through the model (RFC-032 step 3): installed, each answers in words.
            ("prompt-list", [], "ok:no prompt versions yet"),
            ("prompt-show", ["--name", "no/such"], "no prompt 'no/such'"),
            ("system-list", [], "ok:tickets_lead1_v1"),
            ("system-show", ["tickets_lead1_v1"], "ok:tickets_lead1_v1"),
            ("system-show", ["no_such_v1"], "no system 'no_such_v1'"),
            ("system-new", ["tickets_lead1_v1"], "system 'tickets_lead1_v1' exists"),
            ("system-set", ["no_such_v1", "--set", "params.a=1"], "no system 'no_such_v1'"),
            ("goal-show", ["no_such_goal"], "no goal 'no_such_goal'"),
            ("goal-status", ["no_such_goal"], "no goal 'no_such_goal'"),
            ("goal-history", ["no_such_goal"], "no goal 'no_such_goal'"),
            ("goal-new", ["no_such_goal"], "goals/no_such_goal.yaml not saved"),
            ("goal-set", ["no_such_goal", "--set", "title=x"], "no goal 'no_such_goal'"),
            # Models and deployments through the model (RFC-032 step 2): the flow is test_model_ops.py.
            ("model-list", [], "ok:no model records yet"),
            ("model-show", ["no_such_model"], "no model 'no_such_model'"),
            ("model-new", ["no_such_model", "--set", "kind=llm"], "models/no_such_model.yaml not saved"),
            ("model-set", ["no_such_model", "--set", "kind=llm"], "no model 'no_such_model'"),
            ("deployment-show", ["no_such_model", "x"], "no deployment 'no_such_model/x'"),
            ("deployment-history", ["no_such_model", "x"], "no deployment 'no_such_model/x'"),
            (
                "deployment-new",
                ["no_such_model", "x", "--set", "where=x"],
                "no model 'no_such_model' in this project",
            ),
            ("deployment-set", ["no_such_model", "x", "--set", "where=x"], "no deployment 'no_such_model/x'"),
            (
                "deployment-accept",
                ["no_such_model", "x", "--flag", "where it ran", "--why", "a gateway has no build"],
                "no deployment 'no_such_model/x'",
            ),
            # Model records (RFC-020, optional): installed, each answers in words; the flows are
            # test_model_onboard.py, test_arm_smoke.py and test_catalog_models.py.
            ("models", [], "ok:no model records"),
            ("model-onboard", ["no_such_model"], "no model record 'no_such_model'"),
            ("arm-smoke", ["--system", "no_such_v1", "--dataset", "tickets_v1"], "no system 'no_such_v1'"),
            # Scoring that evolves (RFC-022): the flow is test_scoring_evolves.py.
            ("score-preview", ["--goal", "no_such_goal"], "no goal 'no_such_goal'"),
            ("search", ["lead2"], "ok:evh inspect --runs runs/tickets_v1/tickets_lead2_v1"),
            ("search", ["no_such_thing"], "No match."),
            # lead2 against lead1 on gold: the p of tutorial 3 step 4 (3/32 = 0.09375, printed 0.0938; exact over 2^6)
            ("inspect", ["--runs", "tickets_lead1_v1,tickets_lead2_v1"], "ok:0.0938"),
            ("inspect", ["--runs", "tickets_lead1_v1,no_such_v1"], "no arm with that id"),
            (
                "inspect",
                ["--sheet", "--dataset-id", "tickets_v1", "--runs", "tickets_lead1_v1,tickets_lead2_v1"],
                "ok:tickets_v1: 6 of 6",
            ),
            (
                "inspect",
                ["--runs", "tickets_lead1_v1,tickets_lead2_v1", "--item", "t01_login"],
                "ok:(baseline)",
            ),
            # Rounds (optional; the flow is test_rounds.py): installed, each answers in words.
            ("rounds", ["--goal", "no_such_goal"], "no goal 'no_such_goal'"),
            ("round-open", ["--goal", "no_such_goal", "--dataset", "tickets_v1"], "no goal 'no_such_goal'"),
            ("round-retire", ["--goal", "g", "--round", "r1", "--arm", "a", "--reason", "x y z"], "no round"),
            ("round-close", ["--goal", "g", "--round", "r1", "--conclusion", "x y z"], "no round"),
            # The terminal's jobs (RFC-026): installed, each answers in words; the flow is test_jobs.py.
            # Prompt versions (RFC-028): installed, each answers in words; the flow is test_prompts.py.
            ("prompts", [], "ok:no prompt versions yet"),
            ("looks", ["--dataset", "no_such_v1"], "not a test set"),
            # Studies (RFC-029): installed, each answers in words; the flow is test_study.py.
            ("studies", [], "ok:no studies"),
            ("studies", ["--study", "g/no_such"], "no study"),
            ("periods", ["--model", "no_such"], "no model record 'no_such'"),
            (
                "period-compare",
                ["--system", "no_v1", "--dataset", "tickets_v1", "--candidate", "x", "--period", "1"],
                "no system 'no_v1'",
            ),
            (
                "label-mutants",
                ["--dataset-id", "tickets_v1", "--capture", "no_such", "--map", "no.yaml"],
                "--map: no file no.yaml",
            ),
            # Held-out discipline (RFC-031): installed, each answers in words; the flow is test_exposure.py.
            ("exposure", [], "ok:No held-out sides"),
            (
                "exposure-add",
                ["--dataset-id", "tickets_v1", "--item", "x", "--what", "a read"],
                "not a held-out side",
            ),
            ("exposure-check", ["--dataset-id", "tickets_v1"], "not a held-out side"),
            ("sealed-counts", ["--dataset-id", "tickets_v1"], "not a held-out side"),
            (
                "dataset-seal-counts",
                ["--dataset-id", "tickets_v1", "--add", "x", "--reason", "only to read the arguments"],
                "not a held-out side",
            ),
            ("study-run", ["g/no_such"], "no spec at"),
            ("study-ask", ["g/no_such"], "no study"),
            ("study-tell", ["g/no_such", "--ask", "x", "--proposal-json", "{}"], "no study"),
            ("study-stop", ["g/no_such"], "no study"),
            (
                "study-confirm",
                ["g/no_such", "--test", "x", "--rule", "superiority", "--by", "person:t"],
                "no study",
            ),
            ("study-import", ["no_such.tsv", "--goal", "no_such_goal", "--study", "s"], "no goal"),
            ("prompt-diff", ["a/0123456789abcdef", "b/0123456789abcdef"], "no prompt version"),
            ("prompt-version", ["bad name!", "--text", "x", "--note", "n"], "prompt name"),
            ("prompt-export", ["a/0123456789abcdef", "--to", "x.txt"], "no prompt version"),
            # Replay and faithfulness (RFC-030): installed, each answers in words; the flow is test_replay.py.
            (
                "faithfulness",
                ["--system", "no_such_v1", "--dataset", "tickets_v1", "--production", "x"],
                "no system 'no_such_v1'",
            ),
            (
                "faithfulness-name",
                ["--model", "no_such", "--item", "x", "--cause", "c"],
                "no model record 'no_such'",
            ),
            ("faithfulness-show", ["--model", "no_such"], "no model record 'no_such'"),
            ("jobs-status", [], "ok:no jobs"),
            ("jobs-start", ["datasets"], "not a job"),
            ("jobs-logs", ["20990101T000000-abcdef"], "no job"),
            ("jobs-stop", ["20990101T000000-abcdef"], "no job"),
            ("jobs-resume", ["20990101T000000-abcdef"], "no job"),
            ("catalog", [], "ok"),
            ("catalog-serve", [], "ok"),  # started, its address read, stopped
            # A stdio server: --help here; tests/test_mcp_server.py talks to it through the SDK.
            ("mcp", ["--help"], "ok:the project's read commands as MCP tools"),
            ("validate", [], "ok"),
            ("self-test", [], "ok"),
        ]
        covered = {c for c, _, _ in cases}
        check(
            "every evh command has a case here",
            covered == set(COMMANDS),
            f"no case: {sorted(set(COMMANDS) - covered)}; unknown: {sorted(covered - set(COMMANDS))}",
        )

        for cmd, args, expect in cases:
            if cmd == "catalog-serve":
                with socket.socket() as s:
                    s.bind(("127.0.0.1", 0))
                    port = s.getsockname()[1]
                log = tmp / "serve.log"
                with open(log, "w") as fh:
                    p = subprocess.Popen(
                        [sys.executable, "-m", "evaluation_harness", "catalog-serve", "--port", str(port)],
                        cwd=proj,
                        env=env,
                        stdout=fh,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                for _ in range(100):
                    if "catalog:" in log.read_text() or p.poll() is not None:
                        break
                    time.sleep(0.1)
                out = log.read_text()
                alive = p.poll() is None
                # The deploy's second health probe (infra/deploy/probe_link.sh, deploy.sh): the
                # first group link on the dataset pages, answered with verdict rows, no error.
                probe = REPO / "infra" / "deploy" / "probe_link.sh"
                if alive and probe.is_file():
                    q = subprocess.run(
                        ["bash", str(probe), str(proj / ".build/catalog/d")], capture_output=True, text=True
                    ).stdout.strip()
                    body = ""
                    if q:
                        import urllib.request  # noqa: PLC0415

                        with urllib.request.urlopen(  # the test's own server on 127.0.0.1  # nosec B310
                            f"http://127.0.0.1:{port}/api/compare?{q}", timeout=120
                        ) as resp:
                            body = resp.read().decode()
                    check(
                        "deploy probe: finds a group link, and the inspector tests it",
                        "," in q and "metric=" in q and '"rows": [{' in body and '"error"' not in body,
                        (q, body[:200]),
                    )
                    q1 = subprocess.run(
                        ["bash", str(probe), str(proj / ".build/catalog/d"), "one"],
                        capture_output=True,
                        text=True,
                    ).stdout.strip()
                    body1 = ""
                    if q1:
                        import urllib.request  # noqa: PLC0415

                        with urllib.request.urlopen(  # the test's own server on 127.0.0.1  # nosec B310
                            f"http://127.0.0.1:{port}/api/compare?{q1}", timeout=120
                        ) as resp:
                            body1 = resp.read().decode()
                    check(
                        "deploy probe: finds a single-arm link, and the inspector answers it",
                        q1.startswith("runs=") and "," not in q1 and '"rows"' in body1,
                        (q1, body1[:200]),
                    )
                if alive:
                    os.killpg(p.pid, signal.SIGTERM)
                    p.wait(timeout=10)
                check(
                    "catalog-serve: serves, and says where", alive and f"127.0.0.1:{port}" in out, out[-300:]
                )
                continue
            r = evh(cmd, *args)
            out = r.stdout + r.stderr
            clean = "Traceback" not in out
            if expect.startswith("ok"):
                want = expect.partition(":")[2]
                check(
                    f"{cmd}: runs" + (f", on {want}" if want else ""),
                    r.returncode == 0 and clean and want in out,
                    out.strip()[-300:],
                )
            else:
                check(
                    f"{cmd}: refuses, saying {expect!r}",
                    r.returncode != 0 and clean and expect in out,
                    f"exit {r.returncode}: {out.strip()[-300:]}",
                )

        # --json on the commands an agent reads the ranking and the tests with: one envelope on stdout,
        # the key results by name under result.values (the numbers are pinned in test_stat_commands.py).
        def as_json(*args: str) -> tuple[subprocess.CompletedProcess, dict]:
            r = evh(*args, "--json")
            ok = r.returncode == 0 and r.stdout.count("\n") == 1
            return r, (json.loads(r.stdout) if ok else {})

        def values_of(env_: dict) -> dict:
            return (env_.get("result") or {}).get("values") or {}

        r, e = as_json(
            "pair-test", "--dataset-id", "tickets_v1", "--a", "tickets_lead2_v1", "--b", "tickets_lead1_v1"
        )
        v = values_of(e)
        check(
            "pair-test --json: lead2 against lead1, the tutorial's p = 3/32, exact over 6 items",
            (v.get("a"), v.get("b"), v.get("metric"), v.get("n"), v.get("method"))
            == ("tickets_lead2_v1", "tickets_lead1_v1", "overlap_f1", 6, "exact")
            and abs(v.get("p", 0) - 3 / 32) < 1e-9,
            r.stdout[-300:] + r.stderr[-300:],
        )
        r, e = as_json(
            "family-test", "--dataset-id", "tickets_v1", "--a", "tickets_lead2_v1", "--against", "tickets_"
        )
        rows: list = next(
            (b["rows"] for b in e.get("result", {}).get("blocks", []) if "opponent" in b.get("columns", [])),
            [],
        )
        check(
            "family-test --json: the family, and a Holm-adjusted p per opponent",
            values_of(e).get("family_size") == len(rows) >= 2 and all("p_holm" in x for x in rows),
            r.stdout[-300:] + r.stderr[-300:],
        )
        r, e = as_json("leaderboard", "--dataset-id", "tickets_v1")
        groups = values_of(e).get("groups") or [{}]
        check(
            "leaderboard --json: a ranking with a row per arm, and the ordering test",
            {"tickets_lead1_v1", "tickets_lead2_v1"} <= {a["config_id"] for a in groups[0].get("arms", [])}
            and (groups[0].get("ordering") or {}).get("global_p") is not None,
            r.stdout[-300:] + r.stderr[-300:],
        )
        r, e = as_json("run-compare", "--baseline", base_id, "--candidate", run_id)
        check(
            "run-compare --json: the fingerprint result, and the metrics as rows",
            values_of(e).get("fingerprint", {}).get("comparable") is True
            and any(
                "overlap_f1" in [x.get("metric") for x in b.get("rows", [])] for b in e["result"]["blocks"]
            ),
            r.stdout[-300:] + r.stderr[-300:],
        )
        r, e = as_json("runs-list")
        listed = [x["run_id"] for b in e.get("result", {}).get("blocks", []) for x in b.get("rows", [])]
        check(
            "runs-list --json: a row per run",
            values_of(e).get("count") == len(listed) and run_id in listed and base_id in listed,
            r.stdout[-300:] + r.stderr[-300:],
        )
        for cmd, args, said in (
            ("rank-stability", ["--dataset-id", "tickets_v1"], "too few"),
            ("rounds", ["--goal", "no_such_goal"], "no goal 'no_such_goal'"),
        ):
            r = evh(cmd, *args, "--json")
            check(
                f"{cmd} --json: a refusal is on stderr, nothing on stdout",
                r.returncode != 0 and r.stdout == "" and said in r.stderr,
                (r.stdout, r.stderr[-300:]),
            )
        # `evh run` names the runs it wrote, and with --json says so as data, its progress on stderr.
        env_ids = {**env, "EVAL_RUNS_DIR": str(proj / "data" / "runs-smoke-ids")}
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "evaluation_harness",
                "run",
                "--system",
                "tickets_lead1_v1",
                "--dataset",
                "tickets_v1",
                "--run-id",
                "ids_probe",
            ],
            cwd=proj,
            env=env_ids,
            capture_output=True,
            text=True,
        )
        lines = r.stdout.splitlines()
        check(
            "run: prints '  run <id>' for each run it wrote, after the 'wrote N run(s)' line",
            r.returncode == 0
            and any(
                a.startswith("wrote 1 run(s) to") and b == "  run ids_probe"
                for a, b in zip(lines, lines[1:], strict=False)
            ),
            r.stdout[-300:] + r.stderr[-300:],
        )
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "evaluation_harness",
                "run",
                "--system",
                "tickets_lead1_v1",
                "--dataset",
                "tickets_v1",
                "--run-id",
                "ids_json",
                "--json",
            ],
            cwd=proj,
            env=env_ids,
            capture_output=True,
            text=True,
        )
        made = json.loads(r.stdout)["result"]["values"]["runs"] if r.returncode == 0 else []
        check(
            "run --json: the run as data on stdout (one object), the progress on stderr",
            r.stdout.count("\n") == 1
            and len(made) == 1
            and (made[0]["run_id"], made[0]["config_id"], made[0]["n_items"])
            == ("ids_json", "tickets_lead1_v1", 6)
            and "fingerprint" in r.stderr,
            r.stdout[-300:] + r.stderr[-300:],
        )
        if _runstore.exists(proj, "runs-smoke-ids"):
            _runstore.rmtree(proj, "runs-smoke-ids")

        # From a subfolder of the project, a command finds the project (the nearest directory
        # up with data/): from the current directory it read an empty project.
        at_root, below = evh("runs-list"), evh("runs-list", cwd=proj / "tutorial")
        check(
            "a command run from a subfolder finds the project",
            below.returncode == 0 and "tickets_" in below.stdout and below.stdout == at_root.stdout,
            below.stdout[-300:] + below.stderr[-300:],
        )

        # The project's .env, read by the installed `evh` (pip's entry script in the venv's bin/, not
        # `python -m`, whose argv[0] is inside the package): cli imported _common before it pointed
        # argv[0] at the command's script, so .env was never loaded (the 0.6.0 newcomer scenario, B1).
        launcher = tmp / "bin" / "evh"
        launcher.parent.mkdir()
        launcher.write_text("import sys\nfrom evaluation_harness.cli import main\nsys.exit(main())\n")
        dotenv = proj / ".env"
        kept = dotenv.read_text() if dotenv.is_file() else None
        dotenv.write_text("EVAL_MAX_COST_USD=0.37\n")
        try:
            r = subprocess.run(
                [sys.executable, str(launcher), "env-check"],
                cwd=proj,
                env=env,
                capture_output=True,
                text=True,
            )
        finally:
            dotenv.unlink()
            if kept is not None:
                dotenv.write_text(kept)
        check(
            "the installed evh reads the project's .env (a cost cap set only there is in force)",
            "loaded 1 var(s)" in r.stdout and "0.37" in r.stdout,
            (r.stdout + r.stderr)[-400:],
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
