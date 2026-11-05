#!/usr/bin/env python3
"""A dataset's card: the datasheet questions in Croissant RAI's words (PLAN_0.8.0 E4).

    python tests/test_card.py

`dataset-describe --card-template` prints every question as YAML to fill; `--card FILE` records the answered ones
(an empty answer left out), leaves the items and version as they were, and refuses a key that is not a card key;
`validate` V22 refuses one a hand edit put there.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
from evaluation_harness._card import QUESTIONS  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-card-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-card")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )


def ds(i):
    return json.loads((proj / "data" / "datasets" / f"{i}.json").read_text())


try:
    r = evh("dataset-describe", "--card-template")
    check(
        "--card-template: every card key with its question, needing no dataset",
        r.returncode == 0
        and all(f"\n{k}: " in "\n" + r.stdout for k in QUESTIONS)
        and r.stdout.count("# ") == 20,
        r.stdout[:300],
    )
    (proj / "src").mkdir()
    for n in "ab":
        (proj / "src" / f"{n}.txt").write_text(f"item {n}\n")
    r = evh("dataset-create", "--dataset-id", "c_v1", "--source-dir", "src")
    before = ds("c_v1")
    (proj / "card.yaml").write_text(
        "dataUseCases: Testing the card.\ndataBiases: ''\ndataLimitations: Two items only.\n"
    )
    r = evh("dataset-describe", "--dataset-id", "c_v1", "--card", "card.yaml")
    after = ds("c_v1")
    check(
        "--card records the answered questions, leaves out an empty one, keeps the items and version",
        r.returncode == 0
        and after.get("card") == {"dataUseCases": "Testing the card.", "dataLimitations": "Two items only."}
        and after["items"] == before["items"]
        and after["version"] == before["version"],
        (r.stdout + r.stderr)[-300:] + json.dumps(after.get("card")),
    )
    (proj / "bad.yaml").write_text("motivation: not a Croissant key\n")
    r = evh("dataset-describe", "--dataset-id", "c_v1", "--card", "bad.yaml")
    check(
        "a key that is not a card key is refused, and nothing is written",
        r.returncode != 0
        and "card.motivation is not a card key" in r.stderr
        and ds("c_v1")["card"] == after["card"],
        r.stderr[-300:],
    )
    doc = ds("c_v1")
    doc["card"]["purpose"] = "x"
    (proj / "data" / "datasets" / "c_v1.json").write_text(json.dumps(doc, indent=1))
    r = evh("validate")
    check(
        "validate V22 refuses a card key a hand edit put there",
        r.returncode != 0 and "card.purpose" in r.stdout,
        r.stdout[-400:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
