#!/usr/bin/env python3
"""Judges that say why (RFC-034 §5), end to end: $0, offline, on the store EVAL_STORE names (files by default).

    python tests/test_judge_verdicts.py

The tutorial's two fake judges, asked for their reasons, judge three echo arms; `evh judge-verdicts` reads what each
said of each arm and why, the lowest scores first, a page at a time, and the API answers the same; `scorer-new` makes a
scorer that explains unless told otherwise; the local inspector's item view carries the verdicts of that item and a
public server's does not.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
import _serve  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-verdicts-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj))
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)
os.environ.setdefault("EVAL_STORE", "files")
env["EVAL_STORE"] = os.environ["EVAL_STORE"]


import _cli  # noqa: E402


def evh(*args: str) -> subprocess.CompletedProcess:
    return _cli.run(proj, env, *args, timeout=600)


def last(r: subprocess.CompletedProcess) -> dict:
    try:
        return json.loads(r.stdout.splitlines()[-1]).get("result") or {}
    except (IndexError, ValueError):
        return {}


def serve() -> tuple[subprocess.Popen, int]:
    """catalog-serve on a free port, once it answers."""
    p, port, _out = _serve.start(proj, env)
    return p, port


def get(port: int, path: str) -> tuple[int, dict]:
    """One API read with the server's token."""
    token = (proj / ".build" / "api-token").read_text().strip()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1{path}",
        headers={"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}", "X-EVH-Data": "1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def item_view(public: bool) -> dict:
    """The inspector's /api/item for one item and one arm, as the server answers it."""
    code = (
        "import json; from evaluation_harness import catalog_serve as cs; "
        "from evaluation_harness.catalog_adapter import load_catalog_adapter as L; cs.set_adapter(L(None)); "
        + ("cs.LIMITS['hosts'] = ['example.org']; " if public else "")
        + "print(json.dumps(cs.item({'arms': ['runs/tk_v1/echo_s1'], 'item': ['t01_login']})))"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=proj, env=dict(env, PYTHONPATH=str(HARNESS)),
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)  # fmt: skip
    try:
        return json.loads(r.stdout.splitlines()[-1])
    except (IndexError, ValueError):
        return {"error": (r.stdout + r.stderr)[-400:]}


try:
    r = evh("init", "--store", env["EVAL_STORE"], "--tutorial")
    judged = r
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for s in (1, 2, 3):
        _runstore.write_text(
            proj,
            f"systems/echo_s{s}.yaml",
            f"system_id: echo_s{s}\nparams:\n  provider: echo\n  sentences: {s}\n",
        )
    sc = yaml.safe_load((KIT / "scorers" / "tickets-judge-v1.yaml").read_text())
    sc["dataset_id"] = "tk_v1"
    _runstore.write_text(proj, "scorers/tickets-judge-v1.yaml", yaml.safe_dump(sc, sort_keys=False))
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        *(("run", "--system", f"echo_s{s}", "--dataset", "tk_v1") for s in (1, 2, 3)),
        ("judge-score", "--dataset-id", "tk_v1", "--scorer", "tickets-judge-v1", "--unvalidated"),
        ("catalog",),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
        if step[0] == "judge-score":
            judged = r
    check(
        "setup: three arms judged by the tutorial's fake judges, who explain; judge-score names where to read why",
        r.returncode == 0
        and sc.get("explain") is True
        and judged.returncode == 0
        and "evh judge-verdicts tickets-judge-v1" in judged.stdout,
        (r.stdout + r.stderr)[-400:],
    )

    allv = last(evh("judge-verdicts", "tickets-judge-v1", "--limit", "500", "--json"))
    rows = allv.get("rows") or []
    saids = [x["said"] for x in rows]
    check(
        "every arm of every item, by each judge, with its reason: 6 items x 3 arms x 2 judges, the lowest first",
        allv.get("total") == 36 and allv.get("explained") == 36 and len(rows) == 36
        and saids == sorted(saids) and all(isinstance(x["why"], str) and x["why"] for x in rows)
        and {x["arm"] for x in rows} == {"echo_s1", "echo_s2", "echo_s3"} and {x["judge"] for x in rows} == {"judge_a", "judge_b"},
        json.dumps(allv)[:600],
    )  # fmt: skip
    page = last(evh("judge-verdicts", "tickets-judge-v1", "--limit", "5", "--offset", "5", "--json"))
    check(
        "a page: --limit rows from --offset, the total kept",
        page.get("total") == 36 and page.get("offset") == 5 and page.get("rows") == rows[5:10],
        json.dumps(page)[:300],
    )
    one = last(
        evh(
            "judge-verdicts",
            "tickets-judge-v1",
            "--item",
            "t01_login",
            "--arm",
            "echo_s2",
            "--judge",
            "judge_a",
            "--json",
        )
    )
    check(
        "--item, --arm and --judge narrow it to one cell",
        one.get("total") == 1
        and one["rows"][0]["item"] == "t01_login"
        and one["rows"][0]["arm"] == "echo_s2",
        json.dumps(one)[:300],
    )
    pos = last(
        evh(
            "judge-verdicts",
            "tickets-judge-v1",
            "--pass",
            "position",
            "--order",
            "item",
            "--limit",
            "500",
            "--json",
        )
    )
    check(
        "--pass position reads the control's verdicts (half the items, re-asked in another order), in the set's order",
        pos.get("pass") == "position" and pos.get("total") == 18 and pos.get("order") == "item",
        json.dumps(pos)[:300],
    )
    text = evh("judge-verdicts", "tickets-judge-v1", "--limit", "3")
    check(
        "the command says it in words: the page, how many have a reason, and each reason under its score",
        text.returncode == 0 and "rows 1-3 of 36" in text.stdout and "36 with a reason" in text.stdout
        and text.stdout.count("why: ") == 3,
        text.stdout[-500:],
    )  # fmt: skip
    nope = evh("judge-verdicts", "nope-v1")
    check(
        "a scorer that judged nothing is refused, naming the command that judges",
        nope.returncode == 1 and "ERROR (not-found)" in nope.stderr and "evh judge-score" in nope.stderr,
        nope.stderr[-300:],
    )

    made = evh("scorer-new", "made_v1", "--set", "dataset_id=tk_v1", "--set", "judges.0.id=ja",
               "--set", "judges.0.params.provider=fake", "--set", "judges.0.params.model=a", "--set", "judges.0.params.family=f1",
               "--set", "judges.1.id=jb", "--set", "judges.1.params.provider=fake", "--set", "judges.1.params.model=b",
               "--set", "judges.1.params.family=f2", "--set", "prompt.file=judge_prompt.txt",
               *(f"--set=judges.{i}.params.usd_per_mtok_{d}=0" for i in (0, 1) for d in ("in", "out")),
               "--set", "protocol.outputs_per_call=3", "--set", "protocol.position_check_fraction=0.5",
               "--set", "protocol.noise_check_fraction=0.5", "--by", "t")  # fmt: skip
    quiet = evh("scorer-new", "quiet_v1", "--set", "dataset_id=tk_v1", "--set", "explain=false", "--set", "judges.0.id=ja",
                "--set", "judges.0.params.provider=fake", "--set", "judges.0.params.model=a", "--set", "judges.0.params.family=f1",
                "--set", "judges.1.id=jb", "--set", "judges.1.params.provider=fake", "--set", "judges.1.params.model=b",
                "--set", "judges.1.params.family=f2", "--set", "prompt.file=judge_prompt.txt",
               *(f"--set=judges.{i}.params.usd_per_mtok_{d}=0" for i in (0, 1) for d in ("in", "out")),
                "--set", "protocol.outputs_per_call=3", "--set", "protocol.position_check_fraction=0.5",
                "--set", "protocol.noise_check_fraction=0.5", "--by", "t")  # fmt: skip
    rec = last(evh("scorer-show", "made_v1", "--json")).get("record") or {}
    rq = last(evh("scorer-show", "quiet_v1", "--json")).get("record") or {}
    check(
        "scorer-new makes a scorer whose judges explain, unless it is told explain=false",
        made.returncode == 0
        and quiet.returncode == 0
        and rec.get("explain") is True
        and rq.get("explain") is False,
        (made.stderr[-300:], quiet.stderr[-300:], rec, rq),
    )

    vd = evh("validate")
    lines = [ln.strip() for ln in vd.stdout.splitlines()]
    check(
        "validate's V1 (schemas) and V12 (verdicts) pass with the reasons stored: the verdicts' why and the judging "
        "set's explain fit their schemas",
        any(ln.startswith("ok   V1 schemas") for ln in lines)
        and any(ln.startswith("ok   V12 ") for ln in lines),
        [ln for ln in lines if ln.startswith(("FAIL V1 ", "FAIL V12"))][:5],
    )
    local, public = item_view(False), item_view(True)
    lv = local.get("verdicts") or []
    check(
        "the local inspector's item view carries that item's verdicts with their reasons",
        len(lv) == 6
        and all(x["item"] == "t01_login" and x["why"] and x["scorer"] == "tickets-judge-v1" for x in lv),
        json.dumps(local)[:500],
    )
    check(
        "the item view's verdicts name the scale the judges graded on and each arm's position in the judge's list "
        "(the reasons say 'the first answer': 080d inspector #2-3)",
        all(x.get("scale") == [1, 5] or x.get("scale") for x in lv)
        and sorted({x["position"] for x in lv if x["judge"] == lv[0]["judge"]}) == [1, 2, 3],
        json.dumps(lv)[:400],
    )
    check(
        "a public server's item view carries no verdicts: the reasons describe the outputs",
        "verdicts" not in public and "error" not in public,
        json.dumps(public)[:400],
    )

    srv, port = serve()
    try:
        code, body = get(port, "/scorers/tickets-judge-v1/verdicts?limit=7&offset=2")
        cli = last(evh("judge-verdicts", "tickets-judge-v1", "--limit", "7", "--offset", "2", "--json"))
        check(
            "the API's resource gives the command line's answer",
            code == 200 and body.get("result") == cli,
            (code, json.dumps(body)[:300]),
        )
        code404, _ = get(port, "/scorers/nope-v1/verdicts")
        check("the API answers 404 for a scorer that judged nothing", code404 == 404, code404)
    finally:
        _serve.stop(srv, proj)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
