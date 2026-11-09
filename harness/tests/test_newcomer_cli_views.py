#!/usr/bin/env python3
"""The CLI views a newcomer's first pass found wanting (0.7.1). $0, offline.

    python tests/test_newcomer_cli_views.py

rescore says what the goals read after it; silver-calibrate says what --ref-match and --arm-match take;
family-test --round takes the leader and the arms in play from the round; score-preview with no measured run says
so; the leaderboard fits a terminal and a tie is not "worse"; the conditions table shows a model name whole; the
goal table has no empty column; cost-report names each repeat; overview counts what arm-smoke spent.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
KIT = HERE.parent / "tutorial"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

PY = sys.executable
KEEP = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_") and k != "COLUMNS"}


def evh(proj: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    e = {**KEEP, "EVAL_HOME": str(proj), "EVAL_NO_CACHE": "1", "EVAL_BUILD_REF": "test-views", **env}
    return subprocess.run([PY, str(HERE / "cli.py"), *args], cwd=proj, env=e, capture_output=True, text=True)


def out(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


def write_run(proj: Path, name: str, config: str, scores: dict, extra: dict | None = None) -> None:
    d = proj / "data" / "runs" / name
    d.mkdir(parents=True)
    m = {
        "run_id": name,
        "dataset_id": "dsv",
        "config_id": config,
        "scores": scores,
        "metric_kinds": {
            **dict.fromkeys(scores, "quality"),
            **{k: "cost" for k in scores if "cost" in k},
            **{k: "speed" for k in scores if k.startswith("latency")},
        },
        "primary_metric": "acc",
        "created_at": "2026-11-01T10:00:00Z",
        **(extra or {}),
    }
    (d / "metrics.json").write_text(json.dumps(m))
    _runstore.put_rows_text(
        d,
        "".join(
            json.dumps({"item_id": f"i{i}", "acc": scores["acc"], "cost_usd": 0.001}) + "\n" for i in range(4)
        ),
    )


# ---- synthetic project: cost-report, leaderboard ----
syn = Path(tempfile.mkdtemp(prefix="evh-views-syn-"))
tutorial_proj = Path(tempfile.mkdtemp(prefix="evh-views-tut-"))
try:
    # three repeats of one arm, one run of another, each with a provider bill
    for name, cfg in (
        ("rep_x_r1", "arm_rep_v1"),
        ("rep_x_r2", "arm_rep_v1"),
        ("rep_x_r3", "arm_rep_v1"),
        ("single", "arm_one_v1"),
    ):
        write_run(syn, name, cfg, {"acc": 0.5, "total_cost_usd": 0.004})
        _runstore.put_rows_text(
            syn / "data" / "runs" / name,
            "".join(
                json.dumps(
                    {"item_id": f"i{i}", "acc": 0.5, "cost_usd": 0.001, "_meta": {"usage": {"cost": 0.001}}}
                )
                + "\n"
                for i in range(4)
            ),
        )
    r = evh(syn, "cost-report", "--dataset-id", "dsv")
    rows = [ln.split()[0:2] for ln in r.stdout.splitlines() if ln.strip().startswith("arm_")]
    check(
        "cost-report: each repeat of an arm is named r1, r2, r3; a single run keeps its name",
        sorted(x[1] for x in rows if x[0] == "arm_rep_v1") == ["r1", "r2", "r3"]
        and [x[1] for x in rows if x[0] == "arm_one_v1"] == ["0.0040"],
        out(r),
    )

    # leaderboard: arm_best, arm_tie (same acc, dearer and slower), arm_twin (identical to arm_best), many metrics
    extras = {f"extra_metric_number_{i}": 0.1 * i for i in range(8)}
    base = {"acc": 0.9, "total_cost_usd": 0.001, "latency_ms": 100.0, **extras}
    for name, cfg, over in (
        ("lb_best", "arm_best_v1", {}),
        ("lb_tie", "arm_tie_v1", {"total_cost_usd": 0.002, "latency_ms": 200.0}),
        ("lb_twin", "arm_twin_v1", {}),
        ("lb_worse", "arm_worse_v1", {"acc": 0.5, "total_cost_usd": 0.003, "latency_ms": 300.0}),
    ):
        write_run(syn, name, cfg, {**base, **over})
    lb = evh(syn, "leaderboard", "--dataset-id", "dsv", "--match", "_v1")
    widest = max((len(ln) for ln in lb.stdout.splitlines()), default=0)
    check(
        "leaderboard: the default text fits a normal terminal (<= 100 characters a line)",
        widest <= 100,
        widest,
    )
    check(
        "leaderboard: the columns left out are named, with how to see them",
        "Not shown (" in lb.stdout
        and "--wide, or --json" in lb.stdout
        and "extra_metric_number_7" in lb.stdout,
        lb.stdout[:900],
    )
    check(
        "leaderboard: the ranking metric, cost and speed stay in the table, ahead of the other metrics",
        all(
            k in next(ln for ln in lb.stdout.splitlines() if re.match(r"\s+arm\s+runs\s", ln))
            for k in ("acc", "total_cost_usd", "latency_ms")
        ),
        lb.stdout[:600],
    )
    wide = evh(syn, "leaderboard", "--dataset-id", "dsv", "--match", "_v1", "--wide")
    check(
        "leaderboard --wide: every column, nothing left out",
        "extra_metric_number_7" in wide.stdout.split("IS THE ORDERING")[0] and "Not shown" not in wide.stdout,
    )
    js = evh(syn, "leaderboard", "--dataset-id", "dsv", "--match", "_v1", "--json")
    g = json.loads(js.stdout)["result"]["values"]["groups"][0]
    check(
        "leaderboard --json: every metric of every arm, whatever the text shows",
        all(f"extra_metric_number_{i}" in g["arms"][0]["metrics"] for i in range(8))
        and "extra_metric_number_7" in g["metrics"],
        g["metrics"],
    )
    fr = g["frontier"]
    check(
        "frontier: an arm that ties on quality but costs more and is slower is dominated, by the arm that beats it",
        "arm_tie_v1" in fr["dominated"]
        and fr["dominated_by"]["arm_tie_v1"] in ("arm_best_v1", "arm_twin_v1"),
        fr,
    )
    check(
        "frontier: two arms equal on all three dominate neither",
        {"arm_best_v1", "arm_twin_v1"} <= set(fr["frontier"]) and "arm_worse_v1" in fr["dominated"],
        fr,
    )
    check(
        "frontier text: says what dominated means, not 'worse on all three'",
        "worse on all three" not in lb.stdout
        and "as good on all three and better on at least one" in lb.stdout
        and "arm_tie_v1 (by arm_" in " ".join(lb.stdout.split()),
        lb.stdout[-900:],
    )

    # evh baselines: the mean over the baseline's repeats, as the other views show it
    (syn / "data" / "baselines" / "_dataset" / "dsv").mkdir(parents=True)
    (syn / "data" / "baselines" / "_dataset" / "dsv" / "1.json").write_text(
        json.dumps(
            {
                "version": 1,
                "goal": None,
                "dataset_id": "dsv",
                "promoted_from": "rep_x_r1",
                "build": {"ref": "abc123def456"},
                "reason": "test",
                "scores": {"acc": 0.5, "cost_usd": 0.001},
                "repeats": {
                    "runs": ["rep_x_r1", "rep_x_r2", "rep_x_r3"],
                    "mean_scores": {"acc": 0.6, "cost_usd": 0.002},
                },
            }
        )
    )
    bl = evh(syn, "baselines")
    check(
        "evh baselines: the scores are the mean over the repeats, and the line says it is one",
        re.search(r"scores \(mean of 3 repeats\)\s+acc=0\.6\s+cost_usd=0\.002", bl.stdout) is not None,
        bl.stdout,
    )
    blj = json.loads(evh(syn, "baselines", "--json").stdout)
    row = blj["baselines"][0]
    check(
        "evh baselines --json: the same mean, and the number of repeats beside it",
        row.get("scores", {}).get("acc") == 0.6 and row.get("repeats") == 3,
        blj,
    )

    # rounds --goal: each round's conclusion in the list is whole, not cut at 70 characters
    import yaml

    texts = [
        (yaml.safe_load(f.read_text()).get("conclusion") or {}).get("text", "")
        for f in sorted((HERE.parent / "data" / "rounds" / "triage_orrery").glob("r*.yaml"))
    ]
    rl = evh(HERE.parent, "rounds", "--goal", "triage_orrery")
    flat_rl = " ".join(rl.stdout.split())
    check(
        "rounds --goal triage_orrery: every earlier round's conclusion is in the list whole",
        rl.returncode == 0 and len(texts) > 1 and all(" ".join(t.split()) in flat_rl for t in texts[:-1]),
        [t[:80] for t in texts if " ".join(t.split()) not in flat_rl],
    )

    # ---- units: silver-calibrate, rescore, inspect, overview ----
    from evaluation_harness import catalog_views as cv
    from evaluation_harness import rescore as rs
    from evaluation_harness import silver_calibrate as sc

    h = subprocess.run(
        [PY, str(HERE / "cli.py"), "silver-calibrate", "--help"], capture_output=True, text=True
    ).stdout
    flat = " ".join(h.split())
    check(
        "silver-calibrate --help: what --ref-match and --arm-match each match",
        "substring of config_id: the runs whose outputs are used AS the silver references" in flat
        and "substring of config_id: the runs scored against those references" in flat,
        h,
    )
    saved = sc.runs_on
    try:
        sc.runs_on = lambda ds, **kw: [
            (Path("d"), {"config_id": c}) for c in ("a_v1", "b_v1", "a_v2", "b_v2", "c_v1")
        ]
        msg = sc._sets_message("dsx")
        sc.runs_on = lambda ds, **kw: [(Path("d"), {"config_id": c}) for c in ("a_v1", "b_v1")]
        one = sc._sets_message("dsx")
        sc.runs_on = lambda ds, **kw: [(Path("d"), {"config_id": c}) for c in ("a", "b")]
        none = sc._sets_message("dsx")
    finally:
        sc.runs_on = saved
    check(
        "silver-calibrate: the message names the sets it found and builds an example from them",
        "--ref-match takes a substring of config_id" in msg
        and "--arm-match takes a substring of config_id" in msg
        and "_v1 (3 config(s)), _v2 (2 config(s))" in msg
        and "For example: --ref-match _v1 --arm-match _v2" in msg,
        msg,
    )
    check(
        "silver-calibrate: with one version only, says to run a second; with none, says to name the substrings",
        "only _v1 (2 config(s))" in one and "No config id on dsx ends in a version" in none,
        (one, none),
    )

    line = " ".join((rs.closing_line([("gold/x", "gold/x")]) + "evh goals").split())
    check(
        "rescore: the closing line is a whole sentence ending with the command, for a re-score on the run's reference",
        "in place of its runs when every run of the arm was re-scored against the reference it was measured on."
        in line
        and line.endswith("See it with: evh goals")
        and "Not in place" not in line,
        line,
    )
    line = " ".join((rs.closing_line([("gold/x", "silver/x"), ("gold/x", "silver/x")]) + "evh goals").split())
    check(
        "rescore: a re-score on another reference says it is a table of its own and the old table is unchanged",
        "Not in place: 2 run(s) against silver/x, measured against gold/x." in line
        and "the table scored against the old one stays as it was" in line
        and line.endswith("evh goals"),
        line,
    )
    many: list[tuple[str | None, str]] = [
        (f"gold/set_{i}_with_a_long_name", f"silver/set_{i}_with_a_long_name") for i in range(4)
    ]
    widths = [len(x) for x in rs.closing_line(many).splitlines()]
    check(
        "rescore: the closing lines are wrapped to 100 columns, however many references they name",
        max(widths) <= 100 and len(widths) > 3,
        widths,
    )

    check(
        "inspect conditions: a model name is shown whole, a digest by its first 16 characters",
        cv._condition_value("eval-mistral-small") == "eval-mistral-small"
        and cv._condition_value("a" * 64) == "a" * 16
        and cv._condition_value(None) == "None",
    )

    from evaluation_harness.catalog_adapter import smoke_spend
    from evaluation_harness.catalog_build import SPEND_KINDS

    smoke = {"at": "2026-11-03T10:00:00Z", "report": {"spent_usd": 0.5, "items": [{"cost_usd": 0.1}]}}
    items_only = {
        "at": "2026-11-04T10:00:00Z",
        "report": {"items": [{"cost_usd": 0.1}, {"cost_usd": 0.2}, {}]},
    }
    got = sorted(
        (x["at"], x["usd"], x["kind"], x["dataset"], x["what"])
        for x in smoke_spend([{"record": {"smokes": {"a": smoke, "b": items_only, "c": None}}, "arms": []}])
    )
    check(
        "spend: a smoke's spend is its report's total, else the sum of its items' cost_usd, as its own kind",
        [(d, k, ds, w) for d, _, k, ds, w in got]
        == [("2026-11-03", "smoke", "", "a"), ("2026-11-04", "smoke", "", "b")]
        and abs(got[0][1] - 0.5) < 1e-12
        and abs(got[1][1] - 0.3) < 1e-12
        and ("smoke", "arm smokes") in SPEND_KINDS,
        got,
    )

    # ---- a tutorial project: goals, family-test --round, score-preview, overview, inspect ----
    proj = tutorial_proj
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
    (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    shutil.copy(KIT / "goals" / "tickets_summary.yaml", data / "goals")
    r = evh(proj, "dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh(proj, "dataset-materialize", "--dataset-id", "tickets_v1")
    r = (
        r
        if r.returncode
        else evh(
            proj,
            "label-import",
            str(KIT / "gold"),
            "--dataset-id",
            "tickets_v1",
            "--set",
            "owner_gold",
            "--by",
            "owner",
        )
    )
    r = (
        r
        if r.returncode
        else evh(
            proj,
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
    )
    check("setup: the kit's dataset and gold", r.returncode == 0, out(r)[-300:])
    for cfg in ("lead1", "lead2", "lead2_noisy"):
        text = (KIT / "configs" / f"tickets_{cfg}.yaml").read_text() + "goal: tickets_summary\n"
        (data / "configs" / f"{cfg}.yaml").write_text(text)
        r = evh(proj, "run", "--config", f"data/configs/{cfg}.yaml")
    check("setup: three arms run", r.returncode == 0, out(r)[-400:])
    r = evh(
        proj,
        "round-open",
        "--goal",
        "tickets_summary",
        "--dataset",
        "tickets_v1",
        "--adopt",
        "--hypothesis",
        "lead sentences",
    )
    check("setup: a round adopts the arms", r.returncode == 0, out(r)[-300:])

    # family-test --round
    bare = evh(proj, "family-test", "--dataset-id", "tickets_v1")
    check(
        "family-test: without --round, --a and --against are still required",
        bare.returncode != 0
        and "--a and --against are required (or --round, which defaults them)" in out(bare),
        out(bare),
    )
    ft = evh(proj, "family-test", "--dataset-id", "tickets_v1", "--round", "r1")
    check(
        "family-test --round: the leader is A and every other arm in play is the family, Holm-corrected",
        ft.returncode == 0
        and "round r1: tickets_" in ft.stdout
        and "(its leader) against every other arm in play (2)" in ft.stdout
        and "family size m=2" in ft.stdout
        and "Holm step-down" in ft.stdout,
        out(ft),
    )
    leader = m.group(1) if (m := re.search(r"round r1: (\S+) \(its leader\)", ft.stdout)) else ""
    others = [c for c in ("tickets_lead1_v1", "tickets_lead2_v1", "tickets_lead2_noisy_v1") if c != leader]
    check(
        "family-test --round: the opponents are the arms in play but the leader",
        leader != "" and all(o in ft.stdout for o in others),
        (leader, ft.stdout),
    )
    ex = evh(
        proj,
        "family-test",
        "--dataset-id",
        "tickets_v1",
        "--round",
        "r1",
        "--a",
        "tickets_lead1_v1",
        "--against",
        "tickets_lead2_v1",
    )
    check(
        "family-test --round: an explicit --a and --against are kept",
        ex.returncode == 0
        and "family size m=1" in ex.stdout
        and "tickets_lead2_noisy_v1" not in ex.stdout
        and "(its leader)" not in ex.stdout,
        out(ex),
    )
    exa = evh(
        proj,
        "family-test",
        "--dataset-id",
        "tickets_v1",
        "--a",
        "tickets_lead1_v1",
        "--against",
        "tickets_lead2",
    )
    check(
        "family-test: without --round, as before",
        exa.returncode == 0 and "family size m=2" in exa.stdout,
        out(exa),
    )

    # goals --goal: no empty column
    gl = evh(proj, "goals", "--goal", "tickets_summary")
    head = next(
        (ln for ln in gl.stdout.splitlines() if ln.strip().startswith("arm ") and "vs leader" in ln), ""
    )
    check(
        "goals --goal: no empty 'row' column over measured arms; the leader column is named",
        head != "" and " row " not in head + " " and head.rstrip().endswith("decision"),
        head,
    )

    # inspect conditions: the model name whole
    for cfg, model in (("tickets_lead1_v1", "eval-mistral-small"), ("tickets_lead2_v1", "eval-opus-5")):
        mj = next((data / "runs").glob(f"{cfg}_*/metrics.json"))
        m = json.loads(mj.read_text())
        m.setdefault("fingerprint", {}).setdefault("deployment", {})["model"] = model
        mj.write_text(json.dumps(m))
    ins = evh(proj, "inspect", "--runs", "runs/tickets_v1/tickets_lead1_v1,runs/tickets_v1/tickets_lead2_v1")
    check(
        "inspect: the conditions table shows eval-mistral-small whole",
        "eval-mistral-small" in ins.stdout and "eval-mistral-sma " not in ins.stdout,
        out(ins)[-600:],
    )

    rins = evh(proj, "inspect", "--round", "r1")
    check(
        "inspect --round: the table's head names the baseline as the round's leader when no baseline was promoted",
        re.search(r"· baseline \S+ \(the round's leader\): mean", rins.stdout) is not None,
        out(rins)[:400],
    )
    pins = evh(proj, "inspect", "--round", "r1", "--baseline", "tickets_lead2_v1")
    check(
        "inspect --round --baseline: a baseline given is not called the leader",
        "(the round's leader)" not in pins.stdout and "· baseline " in pins.stdout,
        out(pins)[:400],
    )

    # overview: arm-smoke spend beside the billed figure
    (data / "models").mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rec = (
        "model_id: smoked-model\nsmokes:\n  smoked_arm_v1:\n    status: pass\n    at: '"
        + now
        + "'\n    flags: []\n"
        "    report:\n      items:\n      - {item: a, cost_usd: 0.25, scored: true}\n      - {item: b, cost_usd: 0.5, scored: true}\n"
    )
    (data / "models" / "smoked-model.yaml").write_text(rec)
    ov = evh(proj, "overview")
    billed = next((ln for ln in ov.stdout.splitlines() if ln.strip().startswith("billed")), "")
    check(
        "overview: the billed tile counts the arm smoke (the project's runs here bill nothing)",
        "$0.7500" in billed,
        billed or out(ov)[:800],
    )
    check(
        "overview: and in the USD spend of the period",
        re.search(r"^\s+arm smokes\s+\$0\.7500$", ov.stdout, re.M) is not None,
        ov.stdout[-1500:],
    )

    # rescore: outputs the stored runs ended at max_tokens are named, as evh run names them
    clean = evh(proj, "rescore", "--dataset-id", "tickets_v1", "--out", str(proj / "rs_clean"))
    check(
        "rescore: no cut-off output, no cut-off warning",
        clean.returncode == 0 and "stopped at max_tokens" not in clean.stdout,
        out(clean)[-500:],
    )
    cut_run = next((data / "runs").glob("tickets_lead1_v1_*"))
    preds = _runstore.rows(cut_run)
    preds[0].setdefault("_meta", {})["finish_reason"] = "length"
    preds[1]["tokens_out"] = 99
    cm = json.loads((cut_run / "metrics.json").read_text())
    cm.setdefault("params", {})["max_tokens"] = 99
    (cut_run / "metrics.json").write_text(json.dumps(cm))
    _runstore.put_rows_text(cut_run, "".join(json.dumps(x) + "\n" for x in preds))
    cutr = evh(proj, "rescore", "--dataset-id", "tickets_v1", "--out", str(proj / "rs_cut"))
    flat_cut = " ".join(cutr.stdout.split())
    check(
        "rescore: 2 of the stored outputs stopped at max_tokens: it says so, names them, and the closing line stays last",
        cutr.returncode == 0
        and f"WARNING: {cut_run.name}: 2 of 6 output(s) stopped at max_tokens=99" in flat_cut
        and f"({preds[0]['item_id']}, {preds[1]['item_id']})" in flat_cut
        and "A re-score reads them as they are and scores them as if complete. Raise max_tokens (a new config_id) and run again."
        in flat_cut
        and flat_cut.index("WARNING: tickets_lead1")
        < flat_cut.index("the goals, the rounds and the catalog"),
        out(cutr)[-900:],
    )
    shutil.rmtree(proj / "rs_clean", ignore_errors=True)
    shutil.rmtree(proj / "rs_cut", ignore_errors=True)

    # score-preview with only re-scores
    rsr = evh(proj, "rescore", "--dataset-id", "tickets_v1")
    check(
        "rescore: ends with a whole sentence and the command, for the reference the runs were measured on",
        rsr.returncode == 0
        and "in place of its runs when every run of the arm was re-scored against the reference it was measured on."
        in " ".join(rsr.stdout.split())
        and rsr.stdout.rstrip().endswith(("See it with: evh goals", "See it with: make catalog")),
        rsr.stdout[-500:],
    )
    sp = evh(proj, "score-preview", "--goal", "tickets_summary")
    check(
        "score-preview: with measured runs, as before",
        sp.returncode == 0 and "nothing written" in sp.stdout and "no measured run" not in sp.stdout,
        out(sp)[-500:],
    )
    shutil.rmtree(data / "runs")
    (data / "runs").mkdir()
    sp = evh(proj, "score-preview", "--goal", "tickets_summary")
    check(
        "score-preview: no measured run says so, that the runs are re-scores, and how to check them",
        sp.returncode == 0
        and "no measured run to re-score" in sp.stdout
        and "are themselves re-scores" in sp.stdout
        and "evh rescore --dataset-id tickets_v1 --out" in sp.stdout,
        out(sp),
    )
    check(
        "score-preview: and prints no table of dashes, no 'by ?'",
        "—" not in sp.stdout
        and " by ?" not in sp.stdout
        and "->" not in sp.stdout
        and "after" not in sp.stdout,
        sp.stdout,
    )

    # judge-score through a pipe: its progress line reaches the reader while the run is still going
    jp = Path(tempfile.mkdtemp(prefix="evh-views-judge-"))
    try:
        (jp / "src").mkdir()
        for k, f in enumerate(sorted((KIT / "tickets").glob("*.txt")) * 2):
            shutil.copy(f, jp / "src" / f"{k:02d}_{f.name}")
        for d in ("configs", "scorers"):
            (jp / "data" / d).mkdir(parents=True)
        shutil.copy(KIT / "scorers" / "tickets-judge-v1.yaml", jp / "data" / "scorers")
        (jp / "tutorial").mkdir()
        shutil.copy(KIT / "judge_prompt.txt", jp / "tutorial")
        steps: list[tuple[str, ...]] = [
            ("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "src")
        ]
        steps += [("dataset-materialize", "--dataset-id", "tickets_v1")]
        for cfg in ("lead1", "lead2"):
            (jp / "data" / "configs" / f"{cfg}.yaml").write_text(
                (KIT / "configs" / f"tickets_{cfg}.yaml").read_text()
            )
            steps.append(("run", "--config", f"data/configs/{cfg}.yaml"))
        bad = [out(r)[-300:] for r in (evh(jp, *a) for a in steps) if r.returncode]
        check("setup: a project with 12 items and two arms to judge", not bad, bad)
        # the 25th call prints "25 calls"; the three calls after it are slow, so the process outlives that line
        driver = jp / "slow_judge.py"
        driver.write_text(
            "import sys, time\n"
            f"sys.path.insert(0, {str(HERE.parent)!r})\n"
            "from evaluation_harness import judge_score as js\n"
            "from evaluation_harness.judging import call_judge\n"
            "n = [0]\n"
            "def slow(message, params):\n"
            "    n[0] += 1\n"
            "    time.sleep(0.7 if 25 < n[0] <= 28 else 0)\n"
            "    return call_judge(message, params)\n"
            "js.real_call = slow\n"
            "sys.argv = ['judge_score.py', '--dataset-id', 'tickets_v1', '--scorer', 'tickets-judge-v1', '--unvalidated']\n"
            "sys.exit(js.main())\n"
        )
        started = time.perf_counter()
        pr = subprocess.Popen(
            [PY, str(driver)],
            cwd=jp,
            env={**KEEP, "EVAL_HOME": str(jp), "EVAL_NO_CACHE": "1", "EVAL_BUILD_REF": "test-views"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert pr.stdout is not None
        seen = [(time.perf_counter() - started, ln.rstrip("\n")) for ln in pr.stdout]
        pr.wait()
        ended = time.perf_counter() - started
        prog = [t for t, ln in seen if re.match(r"\s+25 calls, \$", ln)]
        check(
            "judge-score through a pipe: the '25 calls' line arrives while the judging goes on, not when it ends",
            pr.returncode == 0 and bool(prog) and ended - prog[0] > 1.5,
            (pr.returncode, prog, ended, [ln for _, ln in seen][-6:]),
        )
    finally:
        shutil.rmtree(jp, ignore_errors=True)
finally:
    shutil.rmtree(syn, ignore_errors=True)
    shutil.rmtree(tutorial_proj, ignore_errors=True)

# A judged table at 120 columns: each judge's own score stays beside the panel's, ahead of cost and speed (0.7.1
# printed the panel's score, latency and cost, and named the judges "Not shown").
from evaluation_harness import leaderboard as lbm  # noqa: E402

os.environ["COLUMNS"] = "120"
show = [
    "judge_judge_a_unvalidated",
    "judge_judge_b_unvalidated",
    "judge_score_unvalidated",
    "cost_usd",
    "latency_ms",
    "total_cost_usd",
]
kinds = {"cost_usd": "cost", "total_cost_usd": "cost", "latency_ms": "speed"}
judged_rows = [{"config_id": f"tickets_arm{i}_v1", **dict.fromkeys(show, 3.25)} for i in range(4)]
kept = lbm._fit_columns(show, judged_rows, kinds, "judge_score_unvalidated", False)
check(
    "leaderboard: a judged table keeps each judge's score beside the panel's, ahead of cost and speed",
    {"judge_judge_a_unvalidated", "judge_judge_b_unvalidated", "judge_score_unvalidated"} <= set(kept),
    kept,
)

sys.exit(summary())
