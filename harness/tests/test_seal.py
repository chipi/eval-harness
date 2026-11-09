#!/usr/bin/env python3
"""A sealed side of a split (the fleet's feedback 29).

    python tests/test_seal.py

In a throwaway git project ($0, offline): the tutorial's tickets with an `opened` date, split at a time boundary
(`dataset-split --by time --at`) with the test side sealed. Every run, label and reference written onto the sealed
side is refused; `dataset-unseal` refuses a config with no hypothesis or an uncommitted one, then opens the side to
the candidate and the config its hypothesis is against (one look, recorded). Another config is still refused.
validate holds the seal: the open side changed after sealing fails it.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-seal-"))
env = dict(os.environ, EVAL_HOME=str(proj))
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVAL_BUILD_REF"):
    env.pop(k, None)

HYP = {
    "against": "base_test_v1",
    "measure": "overlap_f1",
    "direction": "better",
    "statement": "two sentences summarise a ticket better than one",
}


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def git(*args):
    return subprocess.run(["git", *args], cwd=proj, capture_output=True, text=True).stdout.strip()


def commit(msg):
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", msg)


def config(config_id, sentences, hypothesis=None):
    text = (
        f"config_id: {config_id}\ndataset_id: tk_v1_test\n"
        f"params:\n  provider: echo\n  sentences: {sentences}\n"
    )
    if hypothesis:
        text += "hypothesis:\n" + "".join(f"  {k}: {json.dumps(v)}\n" for k, v in hypothesis.items())
    _runstore.write_text(proj, f"configs/{config_id}.yaml", text)


def refused(r, *said):
    return r.returncode != 0 and "Traceback" not in out(r) and all(s in out(r) for s in said)


try:
    git("init", "-q")
    (proj / "data" / "configs").mkdir(parents=True)
    (proj / "data" / "fields").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tickets")
    _runstore.write_text(
        proj,
        "fields/t.yaml",
        "fieldset_id: t\nfields:\n  - name: opened\n    type: date\n    required: true\n",
    )
    dates = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-08", "2026-11-09", "2026-11-10"]
    names = sorted(p.stem for p in (proj / "tickets").glob("*.txt"))
    (proj / "opened.csv").write_text("item_id,opened\n" + "".join(f"{n},{d}\n" for n, d in zip(names, dates)))
    r = evh(
        "dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets", "--fieldset", "t",
        "--fields", "opened.csv",
    )  # fmt: skip
    check("setup: a dataset whose items carry an opened date", r.returncode == 0, out(r)[-300:])

    r = evh(
        "dataset-split", "tk_v1", "--test", "0.5", "--by", "time", "--key", "opened", "--at", "2026-11-07"
    )
    check("dataset-split: --test and --at together are refused", refused(r, "one of --test"), out(r)[-300:])
    r = evh("dataset-split", "tk_v1", "--at", "2026-11-07")
    check("dataset-split: --at needs --by time", refused(r, "--at is a time boundary"), out(r)[-300:])
    r = evh(
        "dataset-split", "tk_v1", "--by", "time", "--key", "opened", "--at", "2026-11-07T00:00:00Z", "--seal"
    )
    test = _runstore.read_json(proj, "datasets/tk_v1_test.json") if r.returncode == 0 else {}
    val = _runstore.read_json(proj, "datasets/tk_v1_validation.json") if r.returncode == 0 else {}
    check(
        "dataset-split --by time --at --seal: items at or after the boundary are the sealed test side",
        sorted(it["item_id"] for it in test.get("items") or []) == names[3:]
        and sorted(it["item_id"] for it in val.get("items") or []) == names[:3]
        and (test.get("sealed") or {}).get("open_side") == "tk_v1_validation"
        and not val.get("sealed")
        and test["split"].get("at") == "2026-11-07T00:00:00Z"
        and "SEALED" in r.stdout,
        out(r)[-400:],
    )
    r = evh("dataset-materialize", "--dataset-id", "tk_v1_test")
    check("setup: the sealed side materialized (reading it is not refused)", r.returncode == 0, out(r)[-300:])

    r = evh("label-import", str(KIT / "gold"), "--dataset-id", "tk_v1_test", "--set", "g", "--by", "o")
    check(
        "sealed: a label set onto it is refused",
        refused(r, "tk_v1_test is sealed", "a label set"),
        out(r)[-300:],
    )
    r = evh("label-sheet", "--dataset-id", "tk_v1_test", "--out", "sheet.csv")
    check("sealed: a label sheet of it is refused", refused(r, "a label sheet"), out(r)[-300:])
    config("base_test_v1", 1)
    config("cand_test_v1", 2, HYP)
    config("other_test_v1", 3)
    r = evh("run", "--config", "data/configs/cand_test_v1.yaml")
    check(
        "sealed: a run on it is refused before anything is called, with how to name the candidate",
        refused(
            r, "tk_v1_test is sealed", "a run is refused for cand_test_v1", "evh dataset-unseal tk_v1_test"
        ),
        out(r)[-400:],
    )

    r = evh(
        "dataset-unseal", "tk_v1_test", "--config", "base_test_v1", "--reason", "the baseline, to look at it"
    )
    check(
        "dataset-unseal: a config with no hypothesis is refused",
        refused(r, "names no hypothesis"),
        out(r)[-300:],
    )
    # The files store's configs are in git: an uncommitted hypothesis is refused. The database's are not (RFC-025):
    # there the unseal itself is the naming in advance, recorded as such.
    if not _runstore.sqlite():
        r = evh(
            "dataset-unseal",
            "tk_v1_test",
            "--config",
            "cand_test_v1",
            "--reason",
            "the two-sentence candidate",
        )
        check(
            "dataset-unseal: a hypothesis not yet committed is refused",
            refused(r, "is not committed"),
            out(r)[-300:],
        )
    commit("the candidate and its hypothesis, before the held-out side is read")
    r = evh(
        "dataset-unseal",
        "tk_v1_test",
        "--config",
        "cand_test_v1",
        "--reason",
        "the two-sentence candidate, frozen",
    )
    looks = (
        (_runstore.read_json(proj, "datasets/tk_v1_test.json").get("unsealed") or [])
        if r.returncode == 0
        else []
    )
    check(
        "dataset-unseal: opened to the candidate and what its hypothesis is against; the look recorded",
        len(looks) == 1
        and looks[0]["config_id"] == "cand_test_v1"
        and looks[0]["hypothesis"]["against"] == "base_test_v1"
        and (looks[0]["commit"] == "not determinable" if _runstore.sqlite() else len(looks[0]["commit"]) >= 7)
        and "look 1" in r.stdout,
        out(r)[-400:],
    )
    (proj / "gold_test").mkdir()
    for f in (KIT / "gold").iterdir():
        if f.stem in names[3:]:
            shutil.copy(f, proj / "gold_test" / f.name)
    r = evh("label-import", "gold_test", "--dataset-id", "tk_v1_test", "--set", "g", "--by", "o")
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote", "--dataset-id", "tk_v1_test", "--labels", "g", "--tier", "gold",
            "--reason", "the kit's summaries, for the held-out side", "--by", "o",
        )
    )  # fmt: skip
    check("unsealed: labels and a reference onto it are written", r.returncode == 0, out(r)[-300:])
    ra = evh("run", "--config", "data/configs/cand_test_v1.yaml")
    rb = evh("run", "--config", "data/configs/base_test_v1.yaml")
    check(
        "unsealed: the candidate and the config it is against run on it",
        ra.returncode == 0 and rb.returncode == 0,
        out(ra)[-300:] + out(rb)[-300:],
    )
    r = evh("run", "--config", "data/configs/other_test_v1.yaml")
    check(
        "unsealed for a candidate: any other config is still refused, naming the ones it is open to",
        refused(r, "it is open to base_test_v1, cand_test_v1 only"),
        out(r)[-300:],
    )
    r = evh("validate")
    v22 = [ln for ln in r.stdout.splitlines() if "V22" in ln]
    check(
        "validate V22: the seal holds (1 sealed side held)",
        bool(v22) and v22[0].lstrip().startswith("ok") and "1 sealed side(s) held" in v22[0],
        "\n".join(v22) or r.stdout[-600:],
    )
    doc = _runstore.read_json(proj, "datasets/tk_v1_validation.json")
    doc["items"] = doc["items"][:2]
    _runstore.write_text(proj, "datasets/tk_v1_validation.json", json.dumps(doc))
    r = evh("validate")
    check(
        "validate V22: the open side changed after sealing fails it",
        r.returncode != 0 and "items have changed since" in r.stdout,
        r.stdout[-800:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
