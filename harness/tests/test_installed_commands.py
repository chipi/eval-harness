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
import _wheel  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.cli import COMMANDS  # noqa: E402


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="evh-commands-"))
    try:
        site = _wheel.install(tmp / "site-packages")
        proj = tmp / "proj"
        proj.mkdir()
        env = {
            **os.environ,
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
        for f in (proj / "tutorial/configs").glob("tickets_*.yaml"):
            shutil.copy(f, proj / "data/configs/")
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
        fetched = proj / "data/references/gold/tickets_pilot_v1"
        fetched.mkdir(parents=True)
        for f in sorted((proj / "tutorial/gold").glob("*.txt"))[:2]:
            shutil.copy(f, fetched / f.name)
        for arm in ("lead1", "lead2", "lead2_noisy", "author"):
            setup("run", "--config", f"data/configs/tickets_{arm}.yaml", "--repeat", "2")
        shutil.copytree(proj / "tutorial/scorers", proj / "data/scorers")
        run_id = sorted(p.name for p in (proj / "data/runs").glob("tickets_lead2_v1_*"))[0]
        base_id = sorted(p.name for p in (proj / "data/runs").glob("tickets_lead1_v1_*"))[0]
        (proj / "imported.jsonl").write_text(
            "".join(
                json.dumps({"item_id": i, "acc": 1.0}) + "\n"
                for i in (
                    it["item_id"]
                    for it in json.loads((proj / "data/datasets/tickets_v1.json").read_text())["items"]
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
            ("run", ["--config", "data/configs/tickets_lead1.yaml", "--dry-run"], "ok"),
            (
                "sweep",
                [
                    "--configs",
                    "data/configs/tickets_lead1.yaml",
                    "data/configs/tickets_lead2.yaml",
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
                    "--config-id",
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
            ("captures", ["--capture", "c1"], "ok:c1:"),
            ("dataset-from-capture", ["c1", "--dataset-id", "captured_v1"], "ok:records kept"),
            ("capture-restore", ["--capture", "c1"], "ok:records restored"),
            # Labels (RFC-023): installed and reading their arguments; the flow is tests/test_label_sets.py.
            ("labels", [], "ok:tickets_v1/installed_from_run: model"),
            ("tags", [], "ok:No tag sets yet"),
            ("licences", ["--search", "share"], "ok:CC-BY-SA-4.0"),
            ("run-migrate", ["--dry-run"], "ok:run(s)"),
            ("data-migrate", ["--to", "files", "--dry-run"], "ok:would move into the files store"),
            ("dataset-publish", ["--dataset-id", "tickets_v1", "--to", "folder"], "cannot publish"),
            (
                "fieldset-propose",
                ["--source", "folder", "--query", '{"path": "tutorial/tickets"}', "--fieldset-id", "x"],
                "describes no features",
            ),
            ("dataset-card", ["--dataset-id", "tickets_v1", "--format", "croissant"], "ok:croissant/1.1"),
            ("dataset-migrate", ["--dry-run"], "ok:dataset(s)"),
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
            ("deploy-sheet", ["--config", "no_such_v1"], "no run of that config"),
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
            ("arms", ["--by", "config", "--period", "30d"], "ok:config tickets_lead2_v1"),
            ("arms", ["--configs"], "ok:rank on each goal"),
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
            # Model records (RFC-020, optional): installed, each answers in words; the flows are
            # test_model_onboard.py, test_arm_smoke.py and test_catalog_models.py.
            ("models", [], "ok:no model records"),
            ("model-onboard", ["no_such_model"], "no model record 'no_such_model'"),
            ("arm-smoke", ["--config", "no_such.yaml"], "no config at no_such.yaml"),
            ("fingerprint-migrate", ["--dry-run"], "ok:after:"),
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
        cfg1 = str(proj / "data/configs/tickets_lead1.yaml")
        r = subprocess.run(
            [sys.executable, "-m", "evaluation_harness", "run", "--config", cfg1, "--run-id", "ids_probe"],
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
                "--config",
                cfg1,
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
        shutil.rmtree(proj / "data" / "runs-smoke-ids", ignore_errors=True)

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
