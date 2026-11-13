#!/usr/bin/env python3
"""Baselines per goal, in versions written once, with the evidence frozen in (RFC-027 D2-D4).

    python tests/test_baselines.py

In a throwaway project ($0, offline), the tutorial's tickets and gold under two goals on one dataset: promoting
writes version n + 1 and never touches n; each goal keeps its own line; a run with no goal goes to the dataset's
own and no goal reads it; the evidence is what `pair-test` answers for the two arms at promotion, and stays when
new runs arrive; another run of the same arm records no test; a rollback restores an earlier version as a new one;
version 10 comes after 9; a version taken by another writer first is written as the next; `evh baselines --json`
is the same bytes twice; validate holds the chain.
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
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-baselines-"))
env = dict(os.environ, EVH_ACTOR="person:ana", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-baselines")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def out(r):
    return r.stdout + r.stderr


def version(goal, n, ds="tk_v1"):
    rel = f"baselines/{goal}/{ds}/{n}.json"
    return _runstore.read_json(proj, rel) if _runstore.is_file(proj, rel) else {}


def run_of(cid):
    return next((n for n in sorted(_runstore.listdir(proj, "runs")) if n.startswith(cid + "_")), "")


try:
    (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (proj / "data" / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tickets")
    goal = (KIT / "goals" / "tickets_summary.yaml").read_text().replace("tickets_v1", "tk_v1")
    _runstore.write_text(proj, "goals/g_one.yaml", goal.replace("goal_id: tickets_summary", "goal_id: g_one"))
    _runstore.write_text(proj, "goals/g_two.yaml", goal.replace("goal_id: tickets_summary", "goal_id: g_two"))
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tk_v1")
    r = (
        r
        if r.returncode
        else evh("label-import", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "ana")
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold",
            "--reason", "the kit's hand-written summaries", "--by", "ana",
        )
    )  # fmt: skip
    check("setup: a dataset with gold, under two goals", r.returncode == 0, out(r)[-300:])
    for cid, n, g in (("one_v1", 1, "g_one"), ("two_v1", 2, "g_one"), ("free_v1", 3, None)):
        _runstore.write_text(
            proj,
            f"systems/{cid}.yaml",
            f"system_id: {cid}\nparams:\n  provider: echo\n  sentences: {n}\n",
        )
        r = evh("run", "--system", cid, "--dataset", "tk_v1", *(["--goal", g] if g else []))
        check(f"setup: {cid} runs", r.returncode == 0, out(r)[-300:])

    r = evh("run-promote", "--run", run_of("one_v1"), "--reason", "the first arm, to start the line")
    v1 = version("g_one", 1)
    check(
        "the first promotion is version 1 of the goal's line, with no comparison",
        r.returncode == 0
        and v1.get("goal") == "g_one"
        and v1.get("replaces") is None
        and v1.get("evidence") == {"compared_to": None}
        and v1.get("actor", {}).get("name") == "ana",
        out(r)[-400:],
    )
    before = _runstore.read_text(proj, "baselines/g_one/tk_v1/1.json")
    r = evh("run-promote", "--run", run_of("two_v1"), "--reason", "two sentences, against one")
    v2 = version("g_one", 2)
    pt = evh(
        "pair-test", "--dataset-id", "tk_v1", "--a", "two_v1", "--b", "one_v1", "--metric", "overlap_f1", "--desc", "--json"
    )  # fmt: skip
    want = (json.loads(pt.stdout).get("result") or {}).get("values") or {} if pt.returncode == 0 else {}
    ev = v2.get("evidence") or {}
    check(
        "version 2 replaces 1 and never touches it",
        r.returncode == 0
        and v2.get("replaces") == 1
        and _runstore.read_text(proj, "baselines/g_one/tk_v1/1.json") == before,
        out(r)[-400:],
    )
    check(
        "its evidence is pair-test's answer for the two arms, with what it was computed on",
        ev.get("compared_to") == 1
        and ev.get("measure") == "overlap_f1"
        and (ev.get("verdict") or {}).get("p") == want.get("p")
        and (ev.get("verdict") or {}).get("delta") == want.get("delta")
        and ev.get("n") == want.get("n")
        and ev.get("items_sha256") == want.get("items_sha256")
        and (ev.get("computed_with") or {}).get("runs_a") == want.get("run_ids_a"),
        (ev, {k: want.get(k) for k in ("p", "delta", "n")}),
    )
    r = evh(
        "run-promote",
        "--run",
        run_of("one_v1"),
        "--reason",
        "the first arm, for the second goal",
        "--goal",
        "g_two",
    )
    check(
        "two goals on one dataset keep their own lines",
        r.returncode == 0
        and version("g_two", 1).get("goal") == "g_two"
        and version("g_one", 2).get("version") == 2,
        out(r)[-300:],
    )
    r = evh("run-promote", "--run", run_of("free_v1"), "--reason", "an ad-hoc experiment with no goal")
    own = version("_dataset", 1)
    check(
        "a run with no goal goes to the dataset's own baselines, goal null",
        r.returncode == 0 and own.get("goal") is None and own.get("promoted_from") == run_of("free_v1"),
        out(r)[-300:],
    )
    evh("catalog")
    page = (
        (proj / ".build/catalog/g/g_one.html").read_text()
        if (proj / ".build/catalog/g/g_one.html").exists()
        else ""
    )
    check(
        "a goal's page reads its own baseline, never the dataset's own",
        "two_v1" in page and run_of("free_v1") not in page,
        page[:300],
    )
    check(
        "the goal page: the version, who promoted it, the evidence frozen in, the history folded",
        "version 2, promoted by ana" in page and "against version 1:" in page and "history (1)" in page,
        page[page.find("version 2") - 200 :][:800] if "version 2" in page else page[-500:],
    )
    r = evh(
        "baseline-rollback",
        "--goal",
        "g_one",
        "--dataset",
        "tk_v1",
        "--to",
        "1",
        "--reason",
        "two sentences ran long",
    )
    v3 = version("g_one", 3)
    check(
        "a rollback is version 3, restoring 1, with its own evidence against 2",
        r.returncode == 0
        and v3.get("restores") == 1
        and v3.get("replaces") == 2
        and v3.get("promoted_from") == run_of("one_v1")
        and (v3.get("evidence") or {}).get("compared_to") == 2,
        out(r)[-400:],
    )
    r = evh(
        "baseline-rollback",
        "--goal",
        "g_one",
        "--dataset",
        "tk_v1",
        "--to",
        "3",
        "--reason",
        "it is already current",
    )
    check(
        "rolling back to the current version is refused",
        r.returncode != 0 and "current one" in out(r),
        out(r)[-300:],
    )
    r = evh("run-promote", "--run", run_of("one_v1"), "--reason", "the same arm again, another of its runs")
    v4 = version("g_one", 4)
    check(
        "the same arm promoted again records no test, and why",
        r.returncode == 0
        and (v4.get("evidence") or {}).get("not_comparable") == ["the same arm (another run of it)"],
        (out(r)[-300:], v4.get("evidence")),
    )
    a = evh("baselines", "--json").stdout
    b = evh("baselines", "--json").stdout
    doc = json.loads(a) if a.strip() else {}
    lines = {(x["goal"], x["dataset"]): x for x in doc.get("baselines") or []}
    check(
        "evh baselines --json: the same bytes twice; one entry per line with its current version and history",
        a == b
        and set(lines) == {("g_one", "tk_v1"), ("g_two", "tk_v1"), (None, "tk_v1")}
        and lines[("g_one", "tk_v1")]["current"] == 4
        and len(lines[("g_one", "tk_v1")]["history"]) == 3
        and lines[("g_one", "tk_v1")]["reproduce"]["run_id"] == run_of("one_v1"),
        a[:600],
    )
    r = evh("baselines", "--goal", "g_one")
    check(
        "evh baselines: the line, who promoted it and why, the evidence, the history",
        "g_one's baseline on tk_v1: version 4" in r.stdout
        and "by ana" in r.stdout
        and "restores 1" in r.stdout,
        r.stdout[-800:],
    )
    r = evh("validate")
    v6 = [ln for ln in r.stdout.splitlines() if "V6" in ln]
    check(
        "validate V6: the chain holds",
        bool(v6) and v6[0].lstrip().startswith("ok"),
        "\n".join(v6) or r.stdout[-400:],
    )

    # Numbers, not names: version 10 comes after 9.
    sys.path.insert(0, str(HERE.parent))
    with _runstore._InProject(proj):
        from evaluation_harness import _baselines

        for n in range(5, 11):
            src = _runstore.read_text(proj, "baselines/g_one/tk_v1/4.json")
            d = json.loads(src) | {"replaces": n - 1}
            _runstore.write_text(
                proj, f"baselines/g_one/tk_v1/{n}.json", json.dumps(d, indent=2, sort_keys=True) + "\n"
            )
        cur = _baselines.current("g_one", "tk_v1")
        check(
            "the current version is the highest number (10 after 9, not 9 after 10)",
            cur and cur["version"] == 10,
        )

        # Two writers: one takes n first; the other is built again against it and lands as n + 1.
        seen: list = []

        def make(c, n):
            seen.append((c["version"] if c else None, n))
            if len(seen) == 1:
                _runstore.write_text(
                    proj, f"baselines/g_one/tk_v1/{n}.json", json.dumps({"version": n}) + "\n"
                )
            return {"promoted_from": "x"}

        doc = _baselines.write_next("g_one", "tk_v1", make)
        check(
            "a version another writer took first is written as the next, built against theirs",
            doc["version"] == 12 and seen == [(10, 11), (11, 12)],
            seen,
        )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
