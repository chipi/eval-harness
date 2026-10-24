#!/usr/bin/env python3
"""Assertions for `reference-create --from-run`: a run's outputs become the reference.

    python tests/test_reference_from_run.py

In a throwaway project built from the tutorial ($0, offline): a finished, clean run becomes
silver with no calls and a manifest that names the run; the refusals (gold, an unfinished run,
another dataset, a derived run, a dirty build, an empty output, outputs cut off at max_tokens,
in both --from-run and --config) leave no reference behind; the leaderboard marks the arm that
wrote the reference it is scored against.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
KIT = HERE.parent / "tutorial"
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-refrun-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-refrun")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def refused(r, text):
    out = r.stdout + r.stderr
    return r.returncode != 0 and "Traceback" not in out and text in out


def clone(run_id, name, edit):
    """A copy of a run under a new id, changed by `edit(run_dir, metrics)`."""
    src, dst = proj / "data/runs" / run_id, proj / "data/runs" / name
    shutil.copytree(src, dst)
    m = json.loads((dst / "metrics.json").read_text())
    m["run_id"] = name
    edit(dst, m)
    if (dst / "metrics.json").is_file():
        (dst / "metrics.json").write_text(json.dumps(m))
    return name


SILVER = proj / "data/references/silver/tickets_v1"

try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset is created and materialized", r.returncode == 0, r.stderr[-300:])
    shutil.copytree(KIT / "gold", data / "references" / "gold" / "tickets_v1")
    for arm in ("lead1", "author"):
        shutil.copy(KIT / "configs" / f"tickets_{arm}.yaml", data / "configs")
        r = evh("experiment-run", "--config", f"data/configs/tickets_{arm}.yaml")
        check(f"setup: the {arm} arm runs", r.returncode == 0, r.stderr[-300:])
    author = next(p.name for p in (data / "runs").glob("tickets_author_v1_*"))

    r = evh("reference-create", "--dataset-id", "tickets_v1", "--from-run", author, "--tier", "gold")
    check(
        "gold from a run is refused: gold is a person's", refused(r, "gold is what a person"), r.stderr[-300:]
    )

    def unfinished(d, m):
        (d / "metrics.json").unlink()

    def other_dataset(d, m):
        m["dataset_id"] = "tickets_v2"

    def derived(d, m):
        m["derived"] = {"kind": "rescore", "from": author}

    def dirty(d, m):
        m["build"] = {"ref": "abc", "dirty": True}

    def empty(d, m):
        (d / "outputs" / "t03_export.txt").write_text("   \n")

    def cut_off(d, m):
        m["params"]["max_tokens"] = 40
        rows = [json.loads(x) for x in (d / "predictions.jsonl").read_text().splitlines() if x.strip()]
        for row in rows[:2]:
            row["tokens_out"] = 40
        (d / "predictions.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))

    for name, edit, text in (
        ("unfinished", unfinished, "did not finish"),
        ("other_dataset", other_dataset, "not 'tickets_v1'"),
        ("derived", derived, "rescored from"),
        ("dirty", dirty, "dirty tree"),
        ("empty", empty, "empty output"),
        ("cut_off", cut_off, "stopped at max_tokens=40"),
    ):
        run = clone(author, f"tickets_author_v1_{name}", edit)
        r = evh("reference-create", "--dataset-id", "tickets_v1", "--from-run", run)
        check(
            f"--from-run refuses {name.replace('_', ' ')}, and leaves no reference",
            refused(r, text) and not SILVER.exists() and not SILVER.with_name("tickets_v1.partial").exists(),
            (r.stdout + r.stderr)[-300:],
        )
        if name == "cut_off":
            r = evh("reference-create", "--dataset-id", "tickets_v1", "--from-run", run, "--allow-cut-off")
            check("--allow-cut-off freezes outputs that end at the cap", r.returncode == 0, r.stderr[-300:])
            shutil.rmtree(SILVER)
        shutil.rmtree(data / "runs" / run)

    r = evh("reference-create", "--dataset-id", "tickets_v1", "--from-run", author)
    out = r.stdout + r.stderr
    m = json.loads((SILVER / "manifest.json").read_text()) if (SILVER / "manifest.json").is_file() else {}
    src = data / "runs" / author
    same = all(
        (SILVER / f.name).read_bytes() == f.read_bytes()
        for f in (src / "outputs").glob("*.txt")
        if f.name[0] != "_"
    )
    check(
        "--from-run: the run's outputs, byte for byte, with no calls",
        r.returncode == 0 and "no calls" in out and same and m.get("cost_usd") == 0.0,
        out[-300:],
    )
    run_m = json.loads((src / "metrics.json").read_text())
    check(
        "--from-run: the manifest names the run, its config, fingerprint and build",
        m.get("authored_by") == "tickets_author_v1"
        and m.get("from_run", {}).get("run_id") == author
        and m["from_run"].get("fingerprint_hash") == run_m["fingerprint"]["hash"]
        and m["from_run"].get("build") == run_m["build"],
        m,
    )
    check(
        "--from-run: with gold present it says new runs keep scoring against gold, and how to rescore",
        "outranks silver" in out and "--reference-id silver/tickets_v1" in out and "Commit it" in out,
        out[-400:],
    )

    r = evh(
        "rescore",
        "--dataset-id",
        "tickets_v1",
        "--reference-id",
        "silver/tickets_v1",
        "--out",
        "data/runs-silver",
    )
    board = subprocess.run(
        [sys.executable, str(HERE / "cli.py"), "leaderboard", "--dataset-id", "tickets_v1"],
        cwd=proj,
        env=dict(env, EVAL_RUNS_DIR="data/runs-silver"),
        capture_output=True,
        text=True,
    )
    check(
        "leaderboard: the arm that wrote the reference is marked, and the note says why",
        r.returncode == 0
        and "tickets_author_v1 *" in board.stdout
        and "wrote the reference silver/tickets_v1" in board.stdout
        and "tickets_lead1_v1 *" not in board.stdout,
        board.stdout[-600:] + board.stderr[-300:],
    )

    # --config: the same refusals apply after authoring, and nothing is frozen.
    shutil.rmtree(SILVER)
    (proj / "capped.py").write_text(
        "from types import SimpleNamespace\n"
        "def call_system(text, params):\n"
        "    return SimpleNamespace(output=text.split('.')[0], tokens_out=int(params['max_tokens']),\n"
        "                           tokens_in=None, cost_usd=None, latency_ms=None, extra={}, meta={})\n"
        "def score(output, reference):\n"
        "    return {}\n"
    )
    (data / "configs" / "capped.yaml").write_text(
        "config_id: capped_v1\ndataset_id: tickets_v1\nadapter: capped.py\nparams: {max_tokens: 12}\n"
    )
    r = evh("reference-create", "--dataset-id", "tickets_v1", "--config", "data/configs/capped.yaml")
    check(
        "--config: outputs cut off at max_tokens are refused, nothing frozen",
        refused(r, "stopped at max_tokens=12") and not SILVER.exists(),
        (r.stdout + r.stderr)[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
