#!/usr/bin/env python3
"""Assertions for goals (ADR-0002): config -> run -> baseline, validate V14, the goal pages.

    python tests/test_goals.py

In a throwaway project built from the tutorial ($0, offline): a config naming an unknown goal
is refused before it runs; a known one is recorded on the run and carried to the baseline with
its format; V14 fails a dangling goal, a format the goal does not accept, a goal_id that is not
its file name and, once policy.yaml sets required_from, a new run with no goal; the catalog
gets a page per goal that ranks only arms on the goal's datasets.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
KIT = HERE.parent / "tutorial"
import _runstore  # noqa: E402
from evaluation_harness import _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-goals-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-goals")
env.pop("EVAL_DATA_DIR", None)
env.pop("EVAL_RUNS_DIR", None)
GOAL = "goals/tickets_summary.yaml"


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def arm_rows(text):
    """The arm rows of `evh goals --goal` (a name, then the six items): not the wrapped reasons beneath."""
    return [ln for ln in text.splitlines() if re.match(r"^  tickets_\S+.* {2,}6 {2,}", ln)]


def validate():
    r = evh("validate")
    line = next((ln for ln in r.stdout.splitlines() if "V14" in ln and ("ok" in ln or "FAIL" in ln)), "")
    return r, line


try:
    data = proj / "data"
    if not _runstore.sqlite():
        (data / "configs").mkdir(parents=True)
        (data / "goals").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")  # sources live inside the project
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset is created and materialized", r.returncode == 0, r.stderr[-300:])
    r = evh(
        "label-import",
        str(KIT / "gold"),
        "--dataset-id",
        "tickets_v1",
        "--set",
        "owner_gold",
        "--by",
        "owner",
    )
    r = (
        r
        if r.returncode
        else evh(
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
    check("setup: the kit's gold, imported and promoted", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    _runstore.write_text(proj, GOAL, (KIT / "goals" / "tickets_summary.yaml").read_text())

    cfg = (KIT / "configs" / "tickets_lead2.yaml").read_text()
    _runstore.write_text(proj, "configs/bad.yaml", cfg + "goal: no_such_goal\n")
    r = evh("run", "--config", str(data / "configs" / "bad.yaml"))
    check(
        "run: a config naming an unknown goal is refused before it runs",
        r.returncode != 0 and "no_such_goal" in (r.stdout + r.stderr) and not _runstore.exists(proj, "runs"),
        (r.stdout + r.stderr)[-200:],
    )
    _runstore.unlink(proj, "configs/bad.yaml")
    _runstore.write_text(
        proj, "configs/keyed.yaml", cfg.replace("params:\n", "params:\n  api_key: sk-LITERAL-0001\n", 1)
    )
    r = evh("run", "--config", str(data / "configs" / "keyed.yaml"))
    check(
        "run: a config with a key written into its params is refused before it runs, and says how instead",
        r.returncode != 0 and "api_key_env" in (r.stdout + r.stderr) and not _runstore.exists(proj, "runs"),
        (r.stdout + r.stderr)[-300:],
    )
    _runstore.unlink(proj, "configs/keyed.yaml")

    _runstore.write_text(proj, "configs/lead2.yaml", cfg + "goal: tickets_summary\nformat: paragraph\n")
    r = evh("run", "--config", str(data / "configs" / "lead2.yaml"))
    runs = [
        f"runs/{n}/metrics.json"
        for n in _runstore.listdir(proj, "runs")
        if _runstore.is_file(proj, f"runs/{n}/metrics.json")
    ]
    m = _runstore.read_json(proj, runs[0]) if runs else {}
    check(
        "run: the goal and format are recorded on the run",
        m.get("goal") == "tickets_summary" and m.get("format") == "paragraph",
        r.stderr[-200:],
    )
    check(
        "run: neither is in the fingerprint (they change what it answers, not what was measured)",
        "tickets_summary" not in json.dumps(m.get("fingerprint", {})),
    )

    r = evh(
        "run-promote",
        "--run",
        m.get("run_id", "?"),
        "--reason",
        "lead2 answers the triage goal on six tickets",
    )
    rel = "baselines/tickets_summary/tickets_v1/1.json"  # the goal's own baseline line (RFC-027)
    b = _runstore.read_json(proj, rel) if _runstore.is_file(proj, rel) else {}
    check(
        "promote: the baseline carries the goal and the format",
        b.get("goal") == "tickets_summary" and b.get("format") == "paragraph",
        (r.stdout + r.stderr)[-200:],
    )

    r, line = validate()
    check(
        "V14: passes with one goal named by a config, a run and a baseline",
        "ok" in line and "1 goal(s)" in line,
        line,
    )

    _runstore.write_text(proj, "configs/lead2.yaml", cfg + "goal: tickets_summary\nformat: bullets\n")
    r, line = validate()
    check(
        "V14: fails a format the goal's output contract does not accept",
        "FAIL" in line and "bullets" in r.stdout,
        line,
    )
    _runstore.write_text(proj, "configs/lead2.yaml", cfg + "goal: tickets_summray\n")
    r, line = validate()
    check(
        "V14: fails a config naming a goal that does not exist",
        "FAIL" in line and "tickets_summray" in r.stdout,
        line,
    )
    _runstore.write_text(proj, "configs/lead2.yaml", cfg + "goal: tickets_summary\n")

    _runstore.write_text(proj, "goals/renamed.yaml", _runstore.read_text(proj, GOAL))
    r, line = validate()
    check(
        "V14: fails a goal_id that is not its file name", "FAIL" in line and "renamed.yaml" in r.stdout, line
    )
    _runstore.unlink(proj, "goals/renamed.yaml")

    _runstore.write_text(proj, "goals/policy.yaml", "required_from: 2000-01-01\n")
    m.pop("goal", None)
    _runstore.write_text(proj, runs[0], json.dumps(m))
    r, line = validate()
    check(
        "V14: with required_from set, a run created since then that names no goal fails",
        "FAIL" in line and "names no goal" in r.stdout,
        line,
    )
    _runstore.write_text(proj, "goals/policy.yaml", "required_from: 2999-01-01\n")
    r, line = validate()
    check("V14: a run created before required_from is not held to it", "ok" in line, line)
    _runstore.unlink(proj, "goals/policy.yaml")
    m["goal"] = "tickets_summary"
    _runstore.write_text(proj, runs[0], json.dumps(m))

    _runstore.write_text(
        proj,
        GOAL,
        _runstore.read_text(proj, GOAL).rstrip("\n")
        + "\nlinks:\n  - {url: https://findings.example/tickets.html, note: the findings}\n"
        + "  - {url: notes/TRIAGE.md, note: the notes}\n",
    )
    r = evh("catalog")
    page = proj / ".build" / "catalog" / "g" / "tickets_summary.html"
    html = page.read_text() if page.is_file() else ""
    check("catalog: a page per goal", r.returncode == 0 and page.is_file(), r.stderr[-300:])
    check(
        "catalog: the goal page shows its links, a web address as a link and a project path as text",
        '<a href="https://findings.example/tickets.html">the findings</a>' in html
        and "the notes: <code>notes/TRIAGE.md</code>" in html,
    )
    r = evh(
        "catalog",
        "--repo",
        "https://code.example/o/r/blob/main",
        "--out",
        str(proj / ".build" / "catalog-repo"),
    )
    repo_html = (
        (proj / ".build" / "catalog-repo" / "g" / "tickets_summary.html").read_text()
        if r.returncode == 0
        else ""
    )
    check(
        "evh catalog --repo: a project path in a goal's links is a link to the project's file",
        '<a href="https://code.example/o/r/blob/main/notes/TRIAGE.md"><code>notes/TRIAGE.md</code></a>'
        in repo_html,
        r.stderr[-300:],
    )
    r = evh("catalog", "--repo", "file:///etc/", "--out", str(proj / ".build" / "catalog-bad"))
    check(
        "evh catalog --repo: refuses anything but a web address", r.returncode != 0 and "--repo" in r.stderr
    )
    check(
        "catalog: the goal page lists the arm, marked as filed under the goal",
        "tickets_lead2_v1" in html and "filed" in html,
    )
    check(
        "catalog: the goals index links it",
        "g/tickets_summary.html" in (proj / ".build/catalog/goals.html").read_text(),
    )
    answer = html.find("the answer so far")
    check(
        "catalog: the goal page explains what it is for first, then the answer: the promoted baseline and its reason",
        0 <= html.find("what it is for") < answer and "lead2 answers the triage goal on six tickets" in html,
    )
    check(
        "catalog: the goal page groups its arms by what they are scored against (linked, its pill), the baseline tagged",
        'scored against <a class="cell-link" href="../r/gold-tickets_v1.html">gold/tickets_v1</a> '
        '<span class="pill tier-gold">gold</span>'
        in html
        and 'class="tag-base"' in html,
    )
    ds_page = (proj / ".build/catalog/d/tickets_v1.html").read_text()
    check(
        "catalog: the dataset page shows its baseline and reason, and tags the row",
        "lead2 answers the triage goal on six tickets" in ds_page and 'class="tag-base"' in ds_page,
    )

    # Cost, quality and speed (ADR-0006): the goal page decides, the CLI says the same.
    check(
        "catalog: the goal page says what the goal weighs, its strategy and its tie-break",
        "<dt>weighs</dt>" in html
        and "balanced: contenders" in html
        and "<dt>tie-break</dt><dd>cost, speed</dd>" in html,
    )
    check(
        "catalog: each group carries the decision box and the cost and speed columns",
        'class="decision"' in html and "cost per item" in html and "speed per item" in html,
    )
    check("catalog: the dataset page shows cost and speed per arm", "cost per item" in ds_page)
    r = evh("goals", "--goal", "tickets_summary")
    check(
        "evh goals --goal: the strategy, the tie-break and the group's recommendation",
        r.returncode == 0
        and "strategy   balanced" in r.stdout
        and "tie-break  cost, speed" in r.stdout
        and "link       the findings: https://findings.example/tickets.html" in r.stdout
        and ("recommended:" in r.stdout or "no single arm recommended" in r.stdout),
        r.stdout[-600:] + r.stderr[-300:],
    )
    r = evh("overview")
    check(
        "evh overview: the glance has the recommended column", r.returncode == 0 and "recommended" in r.stdout
    )
    goals_page = (proj / ".build/catalog/goals.html").read_text()
    check(
        "catalog: the goals page counts configs, not scorings, and shows each goal's recommendation",
        "configs filed" in goals_page and "arms filed" not in goals_page and ">recommended<" in goals_page,
    )
    r = evh("goals")
    check(
        "evh goals: configs filed and the recommendation",
        "configs filed" in r.stdout and "recommended" in r.stdout,
        r.stdout,
    )
    cost_page = proj / ".build/catalog/m/cost_usd.html"
    cp = cost_page.read_text() if cost_page.is_file() else ""
    check(
        "catalog: cost is its own kind, and the page names the goals that weigh it",
        "cost: what an item cost" in cp and "<dt>weighed by</dt>" in cp and "tickets_summary.html" in cp,
        f"page exists: {cost_page.is_file()}",
    )
    r = evh("metrics", "--metric", "latency_ms")
    check(
        "evh metrics --metric: speed is its own kind, weighed by the goal",
        "speed: how long an item took" in r.stdout and "weighed by   tickets_summary" in r.stdout,
        r.stdout[-400:] + r.stderr[-300:],
    )

    # A goal with many arms (evh goals --goal G --arms/--top): the table can be cut down, never the decision.
    lead1 = (KIT / "configs" / "tickets_lead1.yaml").read_text()
    for i in range(1, 7):
        _runstore.write_text(
            proj,
            f"configs/x{i:02d}.yaml",
            lead1.replace("tickets_lead1_v1", f"tickets_x{i:02d}_v1").replace(
                "sentences: 1", f"sentences: {1 + i % 3}"
            )
            + "goal: tickets_summary\n",
        )
        evh("run", "--config", f"data/configs/x{i:02d}.yaml")
    full = evh("goals", "--goal", "tickets_summary")
    rows_full = arm_rows(full.stdout)
    check(
        "evh goals --goal: every arm listed, a 'vs leader' column with the paired test against the leader",
        len(rows_full) == 7
        and "vs leader (paired test)" in full.stdout
        and ("not significant" in full.stdout or "significant" in full.stdout or "identical" in full.stdout)
        and "left out" not in full.stdout,
        full.stdout[-1500:],
    )
    r = evh("goals", "--goal", "tickets_summary", "--top", "2")
    shown = arm_rows(r.stdout)
    check(
        "evh goals --goal --top 2: at most two arms and what must stay (the baseline), kept, the count left out said",
        r.returncode == 0
        and len(shown) < len(rows_full)
        and any("[baseline]" in ln for ln in shown)
        and f"{len(shown)} of 7 arms shown, {7 - len(shown)} left out by --top 2" in r.stdout,
        r.stdout[-1500:] + r.stderr[-300:],
    )
    r = evh("goals", "--goal", "tickets_summary", "--arms", "x01,x02", "--arms", "tickets_x0[56]*")
    shown = arm_rows(r.stdout)
    check(
        "evh goals --goal --arms: substring and glob, repeatable and comma-separated; the baseline stays",
        r.returncode == 0
        and any("[baseline]" in ln for ln in shown)
        and all(f"x0{n}" in "\n".join(shown) for n in (1, 2, 5, 6))
        and "x03" not in "\n".join(shown)
        and "left out by --arms x01 --arms x02 --arms tickets_x0[56]*" in r.stdout,
        r.stdout[-1500:] + r.stderr[-300:],
    )
    r = evh("goals", "--goal", "tickets_summary", "--arms", "zzz_no_such_arm")
    shown = arm_rows(r.stdout)
    check(
        "evh goals --goal --arms with no match: the baseline is still there, marked",
        # Shown whatever the filter: the baseline, the leader and the recommended arm. Which arm the goal
        # recommends turns on these offline arms' speeds, a few ms that vary run to run, so it is sometimes
        # not the leader: its row is marked [recommended].
        r.returncode == 0
        and shown
        and any("[baseline]" in ln for ln in shown)
        and all("[baseline]" in ln or "leader" in ln or "[recommended]" in ln for ln in shown),
        r.stdout[-900:],
    )
    r = evh("goals", "--goal", "tickets_summary", "--top", "1", "--json")
    v = json.loads(r.stdout)["result"]["values"] if r.returncode == 0 else {}
    g0 = (v.get("groups") or [{}])[0]
    check(
        "evh goals --goal --json: leader, baseline, contenders, recommended and each arm's test against the leader",
        v.get("goal") == "tickets_summary"
        and v.get("baseline", "").endswith("tickets_lead2_v1")
        and v.get("leader")
        and isinstance(v.get("contenders"), list)
        and "recommended" in v
        and len(v.get("vs_leader") or {}) == 7
        and all(set(x) == {"delta", "p", "verdict"} for x in v["vs_leader"].values() if x),
        {k: v.get(k) for k in ("goal", "leader", "baseline", "contenders", "recommended")},
    )
    check(
        "evh goals --goal --top 1 --json: the arms shown with raw numbers, and how many were left out",
        g0.get("arms_total") == 7
        and g0.get("arms_left_out") == 7 - g0.get("arms_shown", 0) > 0
        and g0["filter"] == {"arms": [], "top": 1}
        and all(isinstance(a["mean"], float) and isinstance(a["n"], int) for a in g0["arms"])
        and any(a["baseline"] for a in g0["arms"])
        and any(a["leader"] for a in g0["arms"]),
        {k: g0.get(k) for k in ("arms_total", "arms_shown", "arms_left_out", "filter")},
    )
    r = evh("goals", "--top", "3")
    check(
        "evh goals --top without --goal: refused, saying why",
        r.returncode != 0 and "need --goal" in r.stderr,
        r.stderr[-300:],
    )
    r = evh("goals", "--goal", "tickets_summary", "--top", "0")
    check(
        "evh goals --goal --top 0: refused",
        r.returncode != 0 and "--top must be at least 1" in r.stderr,
        r.stderr[-300:],
    )
    for i in range(1, 7):
        _runstore.unlink(proj, f"configs/x{i:02d}.yaml")
        _runstore.rmtree(
            proj,
            "runs/"
            + next(n for n in _runstore.listdir(proj, "runs") if n.startswith(f"tickets_x{i:02d}_v1_")),
        )

    original = _runstore.read_text(proj, GOAL)
    _runstore.write_text(
        proj,
        GOAL,
        original.replace(
            "  min_items: 6\n",
            "  min_items: 6\n  strategy: frugal\n  tie_break: [speed, cost]\n"
            "  axes: {speed: {limit: 60000}}\n"
            "  guardrails:\n    - {name: no PII, rule: summaries never quote an email address, source: privacy review}\n",
        ),
    )
    r, line = validate()
    check(
        "V14: a goal with axes, a strategy, a tie-break and guardrails is valid",
        line.startswith("  ok"),
        line,
    )
    evh("catalog")
    html = page.read_text()
    check(
        "catalog: the goal page shows its guardrails in words, with their source",
        "<dt>guardrails</dt>" in html and "never quote an email address" in html and "privacy review" in html,
    )
    check(
        "catalog: the chosen strategy, the tie-break order and the limit are shown",
        "frugal: contenders" in html and "speed, cost" in html and "limit ≤ 60,000" in html,
    )
    # A limit an arm breaks: the arms page badges it "over a limit", not "not eligible", and evh arms
    # says the same. No arm in this repository's own data breaks a limit, so this is the proof.
    r = evh("arms", "--quality", "contender")
    check(
        "evh arms --quality contender: the goal's quality leader, and no arm it ranks below",
        r.returncode == 0 and "leader" in r.stdout and "no arm matches" not in r.stdout,
        r.stdout[-500:] + r.stderr[-300:],
    )
    _runstore.write_text(
        proj, GOAL, original.replace("  min_items: 6\n", "  min_items: 6\n  axes: {quality: {limit: 0.99}}\n")
    )
    evh("catalog")
    arms_page = (proj / ".build/catalog/arms.html").read_text()
    r = evh("arms")
    check(
        "catalog: an arm below the goal's quality limit is badged over a limit, on the page and in evh arms",
        '<span class="role">over a limit</span>' in arms_page and "over a limit" in r.stdout,
        r.stdout[-500:] + r.stderr[-300:],
    )
    _runstore.write_text(proj, GOAL, original)
    for bad, why in (
        ("  secondary:\n    - {measure: rouge1, direction: higher}\n", "the old secondary key (now axes)"),
        ("  tie_break: [carbon]\n", "a tie-break naming an axis the goal does not weigh"),
        ("  strategy: cheapest\n", "an unknown strategy"),
        ("  axes: {quality: {measure: x}}\n", "a quality axis given a measure (it is the primary)"),
        ("  axes: {cost: {margin: 0.1}}\n", "a margin on an axis other than quality"),
    ):
        _runstore.write_text(proj, GOAL, original.replace("  min_items: 6\n", "  min_items: 6\n" + bad))
        r, line = validate()
        check(f"V14: fails {why}", "FAIL" in line, line)
    _runstore.write_text(proj, GOAL, original)

    # A dataset the goal never decides on (a pilot slice, a generalization check): its groups keep
    # their leader, never a recommendation, and the home page's glance leaves it out.
    _runstore.write_text(
        proj, GOAL, original.replace("role: validation,", "role: validation, decides: false,")
    )
    r = evh("goals", "--goal", "tickets_summary")
    check(
        "decides: false: the goal page says it does not decide there, and recommends nothing",
        "The goal does not decide on tickets_v1 (validation)" in r.stdout and "recommended:" not in r.stdout,
        r.stdout[-700:],
    )
    r = evh("overview")
    glance = r.stdout.split("goals at a glance", 1)[-1].split("activity", 1)[0]
    check("decides: false: the glance leaves the dataset out", "tickets_v1" not in glance, glance)
    _runstore.write_text(proj, GOAL, original)

    # Gold this checkout does not hold (not redistributed): the group is still gold by its id, so
    # the glance does not call it "no gold".
    with _runstore._InProject(proj) as pdata:
        _store.copy_tree(pdata / "references" / "gold", proj / "gold-aside")
        _store.rmtree(pdata / "references" / "gold")
    r = evh("overview")
    check(
        "evh overview: a gold reference the checkout does not hold is still read as gold",
        r.returncode == 0 and "no gold" not in r.stdout and "tickets_summary" in r.stdout,
        r.stdout[:600] + r.stderr[-300:],
    )
    with _runstore._InProject(proj) as pdata:
        _store.copy_tree(proj / "gold-aside", pdata / "references" / "gold")

    # An engineering goal checked by a gate: no dataset, and a guard, not a ranking direction.
    _runstore.write_text(
        proj,
        "goals/no_drop.yaml",
        "goal_id: no_drop\ntitle: No regression\nstatement: Nothing drops between builds.\n"
        "decision: Block a build.\ndatasets: []\n"
        "success_criteria:\n  primary: {measure: score, direction: non_inferior}\n",
    )
    r, line = validate()
    check(
        "V14: a gate goal with no dataset and a non_inferior criterion is valid",
        line.startswith("  ok"),
        line,
    )
    r = evh("catalog")
    gate = proj / ".build" / "catalog" / "g" / "no_drop.html"
    check(
        "catalog: its page says what non_inferior means, not 'non_inferior is better'",
        gate.is_file()
        and "no significant drop against the baseline" in gate.read_text()
        and "non_inferior is better" not in gate.read_text(),
        r.stderr[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
