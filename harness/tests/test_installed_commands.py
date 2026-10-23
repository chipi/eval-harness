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
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
REPO = HERE.parent.parent  # the checkout (infra/ is not part of the package)
sys.path.insert(0, str(HERE))
import _wheel  # noqa: E402
from _check import check, summary  # noqa: E402
from cli import COMMANDS  # noqa: E402


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

        def evh(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, "-m", "evaluation_harness", *args],
                cwd=proj,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        # Importing the package's modules, as INTEGRATION.md documents: `evaluation_harness.judging`
        # did not import at all, and catalog_adapter + judging loaded `_common` twice.
        import_probe = (
            "import sys, evaluation_harness.judging, evaluation_harness.catalog_adapter\n"
            "print(sorted(m for m in sys.modules if m.rsplit('.', 1)[-1] == '_common'))\n"
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
            r.returncode == 0 and r.stdout.strip() == "['_common']",
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
            "tickets_dev_v1",
            "--source-dir",
            "tutorial/tickets",
            "--limit",
            "2",
        )
        setup("dataset-materialize", "--dataset-id", "tickets_v1")
        for f in (proj / "tutorial/configs").glob("tickets_*.yaml"):
            shutil.copy(f, proj / "data/configs/")
        shutil.copytree(proj / "tutorial/gold", proj / "data/references/gold/tickets_v1")
        for arm in ("lead1", "lead2", "lead2_noisy", "author"):
            setup("experiment-run", "--config", f"data/configs/tickets_{arm}.yaml", "--repeat", "2")
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
            ("env-check", [], "ok"),
            (
                "dataset-create",
                ["--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets"],
                "already exists",
            ),
            ("dataset-materialize", ["--dataset-id", "tickets_v1"], "ok"),
            (
                "reference-create",
                ["--dataset-id", "tickets_v1", "--config", "data/configs/tickets_author.yaml"],
                "ok",
            ),
            ("experiment-run", ["--config", "data/configs/tickets_lead1.yaml", "--dry-run"], "ok"),
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
            ("holdout", ["--dataset-id", "tickets_v1", "--exclude-dataset", "tickets_dev_v1"], "ok"),
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
            ("run-compare", ["--baseline", base_id, "--candidate", run_id], "ok"),
            (
                "run-promote",
                ["--run", run_id, "--reason", "the tutorial's working baseline, for this test"],
                "ok",
            ),
            ("catalog", [], "ok"),
            ("catalog-serve", [], "ok"),  # started, its address read, stopped
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
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
