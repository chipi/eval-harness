#!/usr/bin/env python3
"""A held-out side's exposure register and its counts-only report (RFC-031 H1, H2).

    python tests/test_exposure.py

In a throwaway git project ($0, offline): the tutorial's tickets with an `opened` date, a `kind` and an `alert` id,
split at a time boundary with the test side sealed and its counts allowed by `kind`. `sealed-counts` counts by the
allowed fields only (an agent cannot widen them; a person can, recorded). `exposure-add` records a read (an unknown id
refused); `exposure` counts it (`--ids` refused to an agent). After an unseal, every paired score on the side leaves the
read items out and says how many, `--include-exposed` shows the full number beside it, marked; `inspect --item` on a
held-out item records the read itself. `exposure-check` finds an item's alert id in a later commit of a public
checkout (not an earlier one), exits 6 and writes the rows `exposure-add --from` records; then it passes.
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

proj = Path(tempfile.mkdtemp(prefix="evh-exposure-"))
env = dict(os.environ, EVH_ACTOR="person:ana", EVAL_HOME=str(proj))
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVAL_BUILD_REF", "EVH_FOR"):
    env.pop(k, None)
AGENT = dict(env, EVH_ACTOR="agent:probe", EVH_FOR="person:ana")
HYP = {"against": "base_x_v1", "measure": "overlap_f1", "direction": "better", "statement": "two sentences"}


def evh(*args, e=None):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=e or env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def git(*args, cwd=None, e=None):
    return subprocess.run(
        ["git", *args], cwd=cwd or proj, capture_output=True, text=True, env=e
    ).stdout.strip()


def commit(msg, cwd=None, when=None):
    e = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when) if when else None
    git("add", "-A", cwd=cwd, e=e)
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", msg, cwd=cwd, e=e)


def refused(r, *said):
    return r.returncode != 0 and "Traceback" not in out(r) and all(s in out(r) for s in said)


def config(config_id, sentences, hypothesis=None):
    text = f"config_id: {config_id}\ndataset_id: tk_v1_test\nparams:\n  provider: echo\n  sentences: {sentences}\n"
    if hypothesis:
        text += "hypothesis:\n" + "".join(f"  {k}: {json.dumps(v)}\n" for k, v in hypothesis.items())
    _runstore.write_text(proj, f"configs/{config_id}.yaml", text)


def register():
    rel = "exposure/tk_v1_test.jsonl"
    text = _runstore.read_text(proj, rel) if _runstore.is_file(proj, rel) else ""
    return [json.loads(x) for x in text.splitlines() if x.strip()]


try:
    git("init", "-q")
    (proj / "data" / "configs").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tickets")
    _runstore.write_text(
        proj,
        "fields/t.yaml",
        "fieldset_id: t\nfields:\n  - name: opened\n    type: date\n    required: true\n"
        "  - name: kind\n    type: choice\n    values: [bug, question]\n"
        "  - name: alert\n    type: text\n",
    )
    dates = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-08", "2026-11-09", "2026-11-10"]
    kinds = ["bug", "question", "bug", "bug", "question", "bug"]
    names = sorted(p.stem for p in (proj / "tickets").glob("*.txt"))
    (proj / "f.csv").write_text(
        "item_id,opened,kind,alert\n"
        + "".join(f"{n},{d},{k},ALERT-{i}\n" for i, (n, d, k) in enumerate(zip(names, dates, kinds)))
    )
    r = evh(
        "dataset-create",
        "--dataset-id",
        "tk_v1",
        "--source-dir",
        "tickets",
        "--fieldset",
        "t",
        "--fields",
        "f.csv",
    )
    check("setup: a dataset whose items carry opened, kind and alert", r.returncode == 0, out(r)[-300:])
    r = evh(
        "dataset-split", "tk_v1", "--split-by", "time", "--key", "opened", "--at", "2026-11-02T00:00:00Z",
        "--seal", "--count-by", "kind,nope",
    )  # fmt: skip
    check("--count-by: a field no item has is refused", refused(r, "nope"), out(r)[-300:])
    r = evh(
        "dataset-split", "tk_v1", "--split-by", "time", "--key", "opened", "--at", "2026-11-02T00:00:00Z",
        "--seal", "--count-by", "kind",
    )  # fmt: skip
    sealed = (
        (_runstore.read_json(proj, "datasets/tk_v1_test.json").get("sealed") or {})
        if r.returncode == 0
        else {}
    )
    check(
        "dataset-split --seal --count-by: the allowed fields on the seal",
        sealed.get("count_by") == ["kind"],
        out(r)[-300:],
    )
    held = names[1:]
    r = evh("dataset-materialize", "--dataset-id", "tk_v1_test")
    check("setup: the sealed side materialized (reading it is not refused)", r.returncode == 0, out(r)[-300:])

    # H2: counts only, by the allowed fields
    r = evh("sealed-counts", "--dataset-id", "tk_v1_test", "--no-day", "--json")
    counts = (
        (json.loads(r.stdout)["result"]["values"]["counts"]["held-out items"]["all"])
        if r.returncode == 0
        else {}
    )
    check(
        "sealed-counts: counts by kind, no id printed, said to be for safety only",
        counts == {"n": 5, "kind=bug": 3, "kind=question": 2}
        and "for safety only, never to judge effect" in r.stderr
        and not any(n in out(r) for n in held),
        out(r)[-500:],
    )
    r = evh("sealed-counts", "--dataset-id", "tk_v1_test", "--by", "alert")
    check(
        "sealed-counts: a field the seal does not allow is refused",
        refused(r, "not a field this held-out side may be counted by"),
        out(r)[-300:],
    )
    r = evh("dataset-seal-counts", "--dataset-id", "tk_v1_test", "--add", "alert", "--reason", "x", e=AGENT)
    check("dataset-seal-counts: an agent is refused", refused(r, "an agent is refused"), out(r)[-300:])
    r = evh(
        "dataset-seal-counts", "--dataset-id", "tk_v1_test", "--add", "opened", "--reason", "per opening day"
    )
    added = _runstore.read_json(proj, "datasets/tk_v1_test.json")["sealed"].get("count_by_added") or []
    check(
        "dataset-seal-counts: a person adds a field, with who and why on the record",
        r.returncode == 0 and added and added[0]["field"] == "opened" and added[0]["actor"]["name"] == "ana",
        out(r)[-300:],
    )

    # H1: the register
    r = evh("exposure-add", "--dataset-id", "tk_v1_test", "--item", "no_such_item", "--what", "x")
    check(
        "exposure-add: an id not in the side is refused, the id not printed",
        refused(r, "1 id(s) are not items"),
        out(r)[-300:],
    )
    r = evh("exposure-add", "--dataset-id", "tk_v1_validation", "--item", names[0], "--what", "x")
    check(
        "exposure-add: a side never sealed has no register", refused(r, "not a held-out side"), out(r)[-300:]
    )
    r = evh(
        "exposure-add", "--dataset-id", "tk_v1_test", "--item", held[0], "--what", "decision and reason",
        "--read-by", "agent:homelab", "--at", "2026-11-11T09:00:00Z", e=AGENT,
    )  # fmt: skip
    reg = register()
    check(
        "exposure-add: an agent records a read; the row names the reader and who recorded it",
        r.returncode == 0
        and len(reg) == 1
        and reg[0]["by"] == "agent:homelab"
        and reg[0]["recorded_by"] == "agent:probe for person:ana"
        and "1 of 5 item(s) now exposed" in out(r),
        out(r)[-300:] + json.dumps(reg),
    )
    r = evh("exposure", "--dataset-id", "tk_v1_test")
    check(
        "exposure: counts, no id",
        "1 of 5 item(s) exposed (4 unread)" in r.stdout and held[0] not in r.stdout,
        out(r)[-300:],
    )
    r = evh("exposure", "--dataset-id", "tk_v1_test", "--ids", e=AGENT)
    check("exposure --ids: an agent is refused", refused(r, "a person's command"), out(r)[-300:])
    r = evh("exposure", "--dataset-id", "tk_v1_test", "--ids")
    check("exposure --ids: a person sees the ids", held[0] in r.stdout, out(r)[-300:])

    # scores leave the read item out, after an unseal
    config("base_x_v1", 1)
    config("cand_x_v1", 2, HYP)
    commit("the candidate and its hypothesis")
    r = evh(
        "dataset-unseal",
        "tk_v1_test",
        "--config",
        "cand_x_v1",
        "--reason",
        "the two-sentence candidate, frozen before the side is read",
    )
    check("setup: unsealed for the candidate", r.returncode == 0, out(r)[-900:])
    (proj / "gold_test").mkdir()
    for f in (KIT / "gold").iterdir():
        if f.stem in held:
            shutil.copy(f, proj / "gold_test" / f.name)
    r = evh("label-import", "gold_test", "--dataset-id", "tk_v1_test", "--set", "g", "--by", "o")
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote",
            "--dataset-id",
            "tk_v1_test",
            "--labels",
            "g",
            "--tier",
            "gold",
            "--reason",
            "the kit's summaries, for the held-out side",
            "--by",
            "o",
        )
    )
    ra = evh("run", "--config", "data/configs/cand_x_v1.yaml")
    rb = evh("run", "--config", "data/configs/base_x_v1.yaml")
    check(
        "setup: both arms ran on the side",
        r.returncode == ra.returncode == rb.returncode == 0,
        out(r)[-400:] + out(ra)[-200:] + out(rb)[-200:],
    )
    r = evh(
        "pair-test", "--dataset-id", "tk_v1_test", "--a", "cand_x_v1", "--b", "base_x_v1", "--metric", "overlap_f1",
        "--json",
    )  # fmt: skip
    vals = json.loads(r.stdout)["result"]["values"] if r.returncode == 0 else {}
    check(
        "pair-test: the read item is left out (n 4 of 5), said, and in the JSON",
        vals.get("n") == 4
        and vals.get("left_out_exposed") == {"tk_v1_test": 1}
        and "1 item(s) left out (exposed" in out(r),
        out(r)[-600:],
    )
    r = evh(
        "pair-test", "--dataset-id", "tk_v1_test", "--a", "cand_x_v1", "--b", "base_x_v1", "--metric", "overlap_f1",
        "--include-exposed",
    )  # fmt: skip
    check(
        "pair-test --include-exposed: the full number beside it, marked as not the one that counts",
        r.returncode == 0 and "NOT the number that counts): n 5 (+1)" in r.stdout,
        out(r)[-600:],
    )
    r = evh("inspect", "--runs", "cand_x_v1", "--item", held[1])
    reg = register()
    check(
        "inspect --item on a held-out item records the read itself (by this process's actor)",
        any(x["item_id"] == held[1] and x["source"] == "harness" and x["by"] == "person:ana" for x in reg),
        out(r)[-400:] + json.dumps(reg)[-400:],
    )

    # H1: the leak check
    pub = proj.parent / (proj.name + "-public")
    pub.mkdir()
    git("init", "-q", cwd=pub)
    (pub / "notes.md").write_text("ALERT-5 was looked at before it was held out\n")
    commit("an old note", cwd=pub, when="2026-11-01T00:00:00Z")
    cfg = proj / "config.yaml"  # config.yaml is the project's, never in the store
    cfg.write_text(
        (cfg.read_text() if cfg.is_file() else "") + f"exposure:\n  public_repos: [{pub}]\n  ids: [alert]\n"
    )
    r = evh("exposure-check", "--dataset-id", "tk_v1_test")
    check(
        "exposure-check: a commit before the item's time does not count",
        r.returncode == 0 and "0 not in the register" in r.stdout,
        out(r)[-400:],
    )
    (pub / "phase-2-plan.md").write_text("we read ALERT-5 and ALERT-4 again\n")
    commit("a plan that names held-out alerts", cwd=pub)
    r = evh("exposure-check", "--dataset-id", "tk_v1_test", "--out", "leaks.tsv")
    tsv = (proj / "leaks.tsv").read_text() if (proj / "leaks.tsv").is_file() else ""
    check(
        "exposure-check: a later commit naming an unrecorded item exits 6, ids only in the --out file, misses said",
        r.returncode == 6
        and "2 not in the register" in r.stdout
        and "not caught: a paraphrase" in r.stdout
        and held[3] in tsv
        and held[4] in tsv
        and held[3] not in r.stdout,
        out(r)[-500:] + tsv,
    )
    r = evh("exposure-add", "--dataset-id", "tk_v1_test", "--from", "leaks.tsv")
    r2 = evh("exposure-check", "--dataset-id", "tk_v1_test")
    check(
        "exposure-add --from the leaks; then exposure-check passes",
        r.returncode == 0 and r2.returncode == 0,
        out(r)[-300:] + out(r2)[-300:],
    )
    r = evh("catalog")
    page = proj / ".build" / "catalog" / "d" / "tk_v1_test.html"
    html = page.read_text() if page.is_file() else ""
    check(
        "the catalog: the held-out dataset page says how many items were read, and that scores leave them out",
        r.returncode == 0
        and "item(s) read (the exposure register); every score here leaves them out" in html,
        out(r)[-300:],
    )
    r = evh("validate")
    check(
        "validate: a sealed side with count_by and its additions is valid", r.returncode == 0, r.stdout[-600:]
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(proj.parent / (proj.name + "-public"), ignore_errors=True)
sys.exit(summary())
