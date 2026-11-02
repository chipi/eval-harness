#!/usr/bin/env python3
"""The deploy sheet (RFC-023 step 7, PRD-005 FR3): what production must match, and whether a capture says it did.

    python tests/test_deploy_sheet.py

In a throwaway project ($0, offline): a project adapter that reports its model and prompt hash per item and says,
from a capture's record, what production ran; a model record with an alias, a deployment and a setting the arm does
not send; one arm promoted, one not. The sheet names the promoted run, the record and deployment, what was sent (and
the bookkeeping that was not), the record's setting left out, what the items reported, the adapter; the capture
check counts matches (the model by its record id or alias), what differs and what is not recorded, and exits 1
unless every record matches. Nothing is written.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-deploy-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-deploy", PYTHONPATH=str(HERE))
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def refused(r, text):
    return r.returncode != 0 and "Traceback" not in out(r) and text in out(r)


def snapshot():
    return {str(p.relative_to(proj)): p.stat().st_mtime_ns for p in proj.rglob("*") if p.is_file()}


try:
    data = proj / "data"
    for d in ("configs", "models"):
        (data / d).mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: a dataset", r.returncode == 0, out(r)[-300:])
    (proj / "adapter.py").write_text(
        "from evaluation_harness.adapter import Result, score  # noqa: F401\n"
        "def call_system(text, params):\n"
        '    return Result(output=text.split(".")[0] + ".", cost_usd=0.0,\n'
        '                  meta={"model": params.get("model"), "prompt_sha": "p1", "gates": text[:12]})\n'
        "def production_ran(record):\n"
        '    f = record.get("fields") or {}\n'
        '    return {"model": f.get("model"), "prompt_sha": f.get("prompt_sha")}\n'
    )
    (proj / "plain.py").write_text(
        "from evaluation_harness.adapter import Result, score  # noqa: F401\n"
        "def call_system(text, params):\n"
        '    return Result(output=text.split(".")[0] + ".", cost_usd=0.0)\n'
    )
    (data / "models" / "m-one.yaml").write_text(
        "model_id: m-one\nkind: llm\nname: Model one\naliases: [m-one-alias]\n"
        "deployments:\n- id: hosted\n  where: a gateway\n  tag: m-one-alias\n"
        "settings:\n  temperature: 0\n"
    )
    for cid, adapter in (("own_v1", "adapter.py"), ("own2_v1", "adapter.py"), ("plain_v1", "plain.py")):
        (data / "configs" / f"{cid}.yaml").write_text(
            f"config_id: {cid}\ndataset_id: tickets_v1\nadapter: {adapter}\n"
            "params:\n  provider: echo\n  model: m-one-alias\n  usd_per_mtok_in: 1.0\n"
        )
        r = evh("experiment-run", "--config", f"data/configs/{cid}.yaml", "--run-id", cid.replace("_v1", ""))
        check(f"setup: {cid} runs", r.returncode == 0, out(r)[-300:])
    r = evh("run-promote", "--run", "own", "--reason", "The arm we deploy, for the deploy sheet's test.")
    check("setup: own_v1 is promoted", r.returncode == 0, out(r)[-300:])
    rows = [
        {"id": "d1", "body": "x", "created_at": "2026-11-01T00:00:00Z", "model": "m-one", "prompt_sha": "p1"},
        {
            "id": "d2",
            "body": "y",
            "created_at": "2026-11-01T01:00:00Z",
            "model": "m-one-alias",
            "prompt_sha": "p1",
        },
        {"id": "d3", "body": "z", "created_at": "2026-11-01T02:00:00Z", "model": "m-two", "prompt_sha": "p2"},
        {"id": "d4", "body": "w", "created_at": "2026-11-01T03:00:00Z", "model": "m-one"},
    ]
    (proj / "prod.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
    r = evh(
        "capture", "--importer", "jsonl", "--query", json.dumps({"path": "prod.jsonl"}), "--capture", "prod"
    )
    check("setup: a capture of what production ran", r.returncode == 0, out(r)[-300:])
    (proj / "good.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows[:2]))
    r = evh(
        "capture", "--importer", "jsonl", "--query", json.dumps({"path": "good.jsonl"}), "--capture", "good"
    )
    check("setup: a capture where production ran the promoted arm", r.returncode == 0, out(r)[-300:])
    (proj / "partial.jsonl").write_text("".join(json.dumps(x) + "\n" for x in (rows[0], rows[3])))
    r = evh(
        "capture",
        "--importer",
        "jsonl",
        "--query",
        json.dumps({"path": "partial.jsonl"}),
        "--capture",
        "partial",
    )
    check(
        "setup: a capture that matches where it says, and does not say the prompt once",
        r.returncode == 0,
        out(r)[-300:],
    )
    before = snapshot()

    # ── the sheet ────────────────────────────────────────────────────────────────────────────
    r = evh("deploy-sheet", "--config", "own_v1")
    check(
        "the sheet: the promoted run, the model record and its deployment, the dataset and reference",
        r.returncode == 0
        and "measured by   own on tickets_v1, against no reference" in r.stdout
        and "None" not in r.stdout
        and "promoted      as tickets_v1_baseline on tickets_v1" in r.stdout
        and "record        m-one" in r.stdout
        and "tag           m-one-alias" in r.stdout,
        out(r)[-900:],
    )
    check(
        "what was sent, the bookkeeping that was not, and a record setting the arm left out",
        "model                  m-one-alias" in r.stdout
        and "(bookkeeping, not sent: usd_per_mtok_in)" in r.stdout
        and "NOTE: the record sets temperature: 0; this arm did not send it" in r.stdout,
        out(r)[-900:],
    )
    check(
        "what the items reported (a key with few values; a per-item account is left out), the adapter",
        "prompt_sha             p1" in r.stdout
        and "gates" not in r.stdout
        and "adapter         adapter.py" in r.stdout,
        out(r)[-900:],
    )
    r = evh("deploy-sheet", "--config", "own2_v1")
    check(
        "an arm not promoted: its latest run, said so",
        r.returncode == 0 and "promoted      no: this is the arm's latest run" in r.stdout,
        out(r)[-400:],
    )
    r = evh("deploy-sheet", "--config", "own_v1", "--json")
    j = json.loads(r.stdout) if r.returncode == 0 else {}
    check(
        "--json: the same sheet as data",
        j.get("run_id") == "own"
        and j["model"]["record"] == "m-one"
        and j["record_settings_not_sent"] == {"temperature": 0}
        and "usd_per_mtok_in" not in j["sent"]
        and j["sent"].get("model") == "m-one-alias"
        and j["reported"].get("prompt_sha") == ["p1"],
        out(r)[-400:],
    )

    # ── the capture check ────────────────────────────────────────────────────────────────────
    r = evh("deploy-sheet", "--config", "own_v1", "--capture", "prod")
    check(
        "--capture: the model matched by record id or alias, what differs and what is not recorded; exit 1",
        r.returncode == 1
        and "model        3 match; differ: m-two (1)" in r.stdout
        and "prompt_sha   2 match; differ: p2 (1); not recorded: 1" in r.stdout
        and "NOT every captured decision was made by the promoted model and prompt" in r.stdout,
        out(r)[-600:],
    )
    r = evh("deploy-sheet", "--config", "own_v1", "--capture", "prod", "--json")
    j = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    check(
        "--capture --json: the check as data, exit 1 when it differs",
        r.returncode == 1
        and j["capture_check"]["ok"] is False
        and j["capture_check"]["keys"]["model"]["differ"] == {"m-two": 1},
        out(r)[-400:],
    )
    r = evh("deploy-sheet", "--config", "own_v1", "--capture", "partial")
    check(
        "--capture: a record that does not say is not a match (all that say match, still exit 1)",
        r.returncode == 1
        and "prompt_sha   1 match; not recorded: 1" in r.stdout
        and "NOT every captured decision" in r.stdout,
        out(r)[-400:],
    )
    r = evh("deploy-sheet", "--config", "own_v1", "--capture", "good", "--json")
    j = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    check(
        "--capture where every record matches: said so, exit 0",
        r.returncode == 0
        and j.get("capture_check", {}).get("ok") is True
        and "every captured decision was made by the promoted model and prompt"
        in evh("deploy-sheet", "--config", "own_v1", "--capture", "good").stdout,
        out(r)[-400:],
    )
    check("the sheet writes nothing", snapshot() == before, "files changed")

    # ── refusals ─────────────────────────────────────────────────────────────────────────────
    r = evh("deploy-sheet", "--config", "no_such_v1")
    check("refused: a config with no run", refused(r, "no run of that config"), out(r)[-200:])
    r = evh("deploy-sheet", "--config", "plain_v1", "--capture", "prod")
    check(
        "refused: --capture with an adapter that cannot say what production ran",
        refused(r, "has no production_ran(record)"),
        out(r)[-200:],
    )
    r = evh("deploy-sheet", "--config", "own_v1", "--capture", "no_such")
    check("refused: an unknown capture", refused(r, "no capture"), out(r)[-200:])
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
