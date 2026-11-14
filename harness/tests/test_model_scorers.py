#!/usr/bin/env python3
"""Judge scorers through both surfaces (RFC-032 step 7), in the suite's store.

    python tests/test_model_scorers.py

In a project `evh init` makes: `scorer-new` makes a scorer's file, `scorer-list` and `scorer-show` give its mode, its
judges with their fingerprints, whether it is validated, the judging sets it judged with their verdicts counted, the runs
it judged, how many judged scores it made and how many of them with another version of it, and the people's checks of its
judges (the report and the records of each source, counted); a scorer that has made judged scores is not changed or
deleted, by `scorer-set`, `data-put` or `data-rm` (a comment is not a change), and a new version is a new scorer with
`supersedes`; validate (V13) names a judged score whose scorer is not the one it was made with, and one whose scorer is
gone; the checks' records and reports match their schemas; the API's resources give the command line's answers.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-scorers-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runfix  # noqa: E402
import _runstore  # noqa: E402
import jsonschema  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness._codeid import content_sha256  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-model-scorers")
FIRST = "[{id: ja, params: {provider: fake, model: fake-a, family: vendor_a, usd_per_mtok_in: 0, usd_per_mtok_out: 0}}, "
JUDGES = (
    FIRST
    + "{id: jb, params: {provider: fake, model: fake-b, family: vendor_b, usd_per_mtok_in: 0, usd_per_mtok_out: 0}}]"
)
NEW = ("--set", "dataset_id=ds", "--set", f"judges={JUDGES}", "--set", "prompt.file=judge_prompt.txt",
       "--set", "protocol.outputs_per_call=2", "--set", "protocol.position_check_fraction=0.5",
       "--set", "protocol.noise_check_fraction=0.5")  # fmt: skip
SHA = "a" * 64


def evh(*args: str) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project."""
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def result(r: subprocess.CompletedProcess) -> dict:
    """A --json command's result."""
    return json.loads(r.stdout)["result"]


def stored(rel: str) -> str:
    """A file of the project's data, "" when it is not there."""
    return _runstore.read_text(proj, rel) if _runstore.is_file(proj, rel) else ""


def put(rel: str, doc: object) -> None:
    _runstore.write_text(proj, rel, json.dumps(doc, indent=2) + "\n")


def judged(scorer: str, run: str, sha: str, set_id: str = "set1") -> None:
    """A run with a judged score of it, as judge-score writes one."""
    _runfix.put_run(
        proj / "data",
        {"run_id": run, "config_id": f"{run}_arm", "dataset_id": "ds", "scores": {"judge_score": 4.0},
         "derived": {"kind": "judge", "with": {"scorer_id": scorer, "scorer_sha256": sha}}},
        scorer=scorer, reference=set_id, label=f"judged/{scorer}",
    )  # fmt: skip


def sha_of(scorer: str) -> str:
    """The content hash of the scorer's file, worked out here."""
    return content_sha256(yaml.safe_load(stored(f"scorers/{scorer}.yaml")))


def serve() -> tuple[subprocess.Popen, int]:
    """catalog-serve on a free port, once it answers."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)], cwd=proj, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return p, port
        except OSError:
            time.sleep(0.1)
    p.kill()
    raise RuntimeError(f"the server did not start: {(p.communicate()[0] or '')[-500:]}")


def call(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """One API call with the server's token."""
    token = (proj / ".build" / "api-token").read_text().strip()
    h = {"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}", "X-EVH-Data": "1"}
    raw = json.dumps(body).encode() if body is not None else None
    if raw is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1{path}", data=raw, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b"{}"
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"text": raw.decode(errors="replace")[-500:]}


try:
    r = evh("init")
    r = r if r.returncode else evh("catalog")
    shutil.copy(HARNESS / "tutorial" / "judge_prompt.txt", proj / "judge_prompt.txt")
    check("setup: a project", r.returncode == 0, (r.stdout + r.stderr)[-300:])

    empty = evh("scorer-list")
    check(
        "scorer-list of a project with none says how to make one",
        empty.returncode == 0 and "no judge scorers yet" in empty.stdout and result(evh("scorer-list", "--json")) == {"scorers": []},
        empty.stdout[-200:],
    )  # fmt: skip
    nope = evh("scorer-show", "nope_v1")
    check(
        "scorer-show of a scorer that does not exist is refused, saying there are none",
        nope.returncode == 1
        and "ERROR (not-found): no scorer 'nope_v1': there are no scorers" in nope.stderr,
        nope.stderr[-200:],
    )

    # -- making and refusing
    made = evh("scorer-new", "s_v1", *NEW)
    doc = yaml.safe_load(stored("scorers/s_v1.yaml") or "{}")
    check(
        "scorer-new makes the scorer's own file, named by its id, a judge scorer",
        made.returncode == 0 and doc.get("scorer_id") == "s_v1" and doc.get("kind") == "judge"
        and [j["id"] for j in doc["judges"]] == ["ja", "jb"],
        (made.stdout + made.stderr)[-300:],
    )  # fmt: skip
    again = evh("scorer-new", "s_v1", *NEW)
    bad = evh("scorer-new", "s_bad", "--set", "dataset_id=ds")
    ghost = evh(
        "scorer-new",
        "s_ghost",
        *NEW,
        "--set",
        "supersedes=nope_v1",
        "--set",
        "why=a reason that is long enough",
    )
    check(
        "scorer-new refuses an id that is taken, a record that does not check, and a scorer to supersede that is not there",
        again.returncode == 1 and "ERROR (would-overwrite)" in again.stderr
        and bad.returncode == 1 and "ERROR (invalid-file)" in bad.stderr and "judges" in bad.stderr
        and ghost.returncode == 1 and "no scorer 'nope_v1'" in ghost.stderr
        and not stored("scorers/s_bad.yaml") and not stored("scorers/s_ghost.yaml"),
        (again.stderr[-100:], bad.stderr[-200:], ghost.stderr[-200:]),
    )  # fmt: skip

    # -- the views
    rows = result(evh("scorer-list", "--json"))["scorers"]
    row = rows[0] if rows else {}
    check(
        "scorer-list: the scorer with its mode (grade when it says none), judges, no validation, no judged score",
        [x["scorer"] for x in rows] == ["s_v1"] and row["mode"] == "grade" and not row["validated"]
        and [j["judge"] for j in row["judges"]] == ["ja", "jb"] and row["judges"][0]["model"] == "fake-a"
        and row["judges"][1]["family"] == "vendor_b"
        and row["judged_scores"] == 0 and row["other_version"] == 0 and row["file"] == "data/scorers/s_v1.yaml",
        row,
    )  # fmt: skip
    show = result(evh("scorer-show", "s_v1", "--json"))
    from evaluation_harness import judge_score as js

    with _runstore._InProject(proj) as data:
        fps = [js.judge_fingerprint(j) for j in js.load_scorer(data / "scorers" / "s_v1.yaml")["judges"]]
    check(
        "scorer-show: the record, its hash (the parsed YAML's), each judge's fingerprint, why it is not validated",
        show["record"]["scorer_id"] == "s_v1" and show["sha256"] == sha_of("s_v1")
        and [j["fingerprint"] for j in show["judges"]] == fps
        and show["validation"]["validated"] is False and show["validation"]["block"] is None
        and any("stand-in" in p for p in show["validation"]["problems"])
        and show["judging_sets"] == [] and show["runs"] == [] and show["checks"] == [],
        show,
    )  # fmt: skip
    text = evh("scorer-list").stdout
    words = evh("scorer-show", "s_v1").stdout
    check(
        "scorer-list and scorer-show in words: a line a scorer, the judges, the hash, the validation, what it made",
        "s_v1" in text and "unvalidated" in text and "ja (fake-a)" in text and "0 judged score(s)" in text
        and "judge        ja  fake-a  vendor_a  fp " in words and f"sha256       {sha_of('s_v1')}" in words
        and "not validated" in words and "made         0 judged score(s)" in words,
        (text, words),
    )  # fmt: skip

    # -- a scorer that has judged is not changed
    judged("s_v1", "run_a", sha_of("s_v1"))
    judged("s_v1", "run_b", sha_of("s_v1"))
    put(
        "judging-sets/set1.json",
        {
            "judging_set_id": "set1",
            "dataset_id": "ds",
            "arms": [{"config_id": "a"}, {"config_id": "b"}],
            "items": [{"item_id": "i1"}],
        },
    )
    _runstore.write_text(proj, "judge-verdicts/s_v1/set1/ja/i1.primary.b0.json", "{}\n")
    _runstore.write_text(proj, "judge-verdicts/s_v1/set1/jb/i1.primary.b0.json", "{}\n")
    put(
        "judge-summaries/s_v1@set1.json",
        {
            "scorer_id": "s_v1",
            "scorer_sha256": sha_of("s_v1"),
            "label": "unvalidated judge",
            "validated": False,
            "partial": False,
            "items_scored": 1,
        },
    )
    row = result(evh("scorer-list", "--json"))["scorers"][0]
    show = result(evh("scorer-show", "s_v1", "--json"))
    sets = show["judging_sets"]
    check(
        "scorer-list and scorer-show count the judged scores, the judging set's arms, items and verdicts, its summary, the runs",
        row["judged_scores"] == 2 and row["other_version"] == 0 and show["judged_scores"] == 2
        and [(s["set"], s["dataset"], s["arms"], s["items"], s["verdicts"], s["judged_scores"]) for s in sets]
        == [("set1", "ds", 2, 1, 2, 2)]
        and sets[0]["summary"]["current"] is True and sets[0]["summary"]["items_scored"] == 1
        and sorted((x["run"], x["system"], x["set"], x["current"]) for x in show["runs"])
        == [("run_a", "run_a_arm", "set1", True), ("run_b", "run_b_arm", "set1", True)],
        (row, sets, show["runs"]),
    )  # fmt: skip
    before = stored("scorers/s_v1.yaml")
    refused = [
        evh("scorer-set", "s_v1", "--set", "cost_cap_usd=5"),
        evh("scorer-set", "s_v1", "--set", "protocol.order_seed=3"),
        evh("data-put", "scorers/s_v1.yaml", "--set", "cost_cap_usd=5"),
        evh("data-rm", "scorers/s_v1.yaml"),
        evh("data-rm", "scorers/s_v1.yaml", "--dry-run"),
    ]
    check(
        "a scorer that made judged scores is not changed or deleted: scorer-set, data-put and data-rm refuse, nothing written",
        all(x.returncode == 1 and "ERROR (not-allowed)" in x.stderr and "2 judged score(s)" in x.stderr and "`supersedes: s_v1`" in x.stderr
            for x in refused[:2])
        and all(x.returncode == 1 and "ERROR (not-allowed)" in x.stderr and "judged score(s)" in x.stderr for x in refused)
        and stored("scorers/s_v1.yaml") == before and "s_v1.yaml" in "".join(_runstore.listdir(proj, "scorers")),
        [x.stderr[-160:] for x in refused],
    )  # fmt: skip
    whole = proj / "whole.yaml"
    whole.write_text(before + "cost_cap_usd: 9\n")
    changed = evh("data-put", "scorers/s_v1.yaml", str(whole))
    checked = evh("data-put", "scorers/s_v1.yaml", str(whole), "--check")
    whole.write_text("# only a comment changes\n" + before)
    comment = evh("data-put", "scorers/s_v1.yaml", str(whole), "--check")
    check(
        "data-put of a whole file: a changed one is refused (saving or checking), one whose content is the same passes",
        changed.returncode == 1 and "not-allowed" in changed.stderr and checked.returncode == 1 and "not-allowed" in checked.stderr
        and comment.returncode == 0 and "passes the check" in comment.stdout and stored("scorers/s_v1.yaml") == before,
        (changed.stderr[-160:], checked.stderr[-160:], comment.stdout[-160:] + comment.stderr[-160:]),
    )  # fmt: skip

    # -- a new version is a new scorer
    two = evh(
        "scorer-new",
        "s_v2",
        *NEW,
        "--set",
        "supersedes=s_v1",
        "--set",
        "why=the rubric asked for the wrong thing",
    )
    rec2 = yaml.safe_load(stored("scorers/s_v2.yaml") or "{}")
    check(
        "scorer-new makes a new version of one that judged, naming what it supersedes and why",
        two.returncode == 0 and rec2.get("supersedes") == "s_v1" and "wrong thing" in rec2.get("why", ""),
        (two.stdout + two.stderr)[-300:],
    )
    changed2 = evh("scorer-set", "s_v2", "--set", "cost_cap_usd=3")
    put2 = evh("data-put", "scorers/s_v2.yaml", "--set", "cost_cap_usd=4")
    same = evh("scorer-set", "s_v2", "--set", "cost_cap_usd=4")
    check(
        "a scorer with no judged score is changed: scorer-set and data-put save, the same value saves nothing",
        changed2.returncode == 0 and put2.returncode == 0 and yaml.safe_load(stored("scorers/s_v2.yaml"))["cost_cap_usd"] == 4
        and same.returncode == 0 and "unchanged" in same.stdout,
        (changed2.stderr[-160:], put2.stderr[-160:], same.stdout[-100:]),
    )  # fmt: skip
    rm2 = evh("data-rm", "scorers/s_v2.yaml")
    check(
        "a scorer with no judged score is deleted",
        rm2.returncode == 0 and not stored("scorers/s_v2.yaml"),
        rm2.stderr[-200:],
    )

    # -- validate names a judged score whose scorer is not the one it was made with
    from evaluation_harness import validate_tree as vt

    with _runstore._InProject(proj) as data:
        clean = vt.judged_score_problems(data / "scorers")
    _runstore.write_text(proj, "scorers/s_v1.yaml", before + "cost_cap_usd: 7\n")
    judged("ghost_v1", "run_g", SHA)
    with _runstore._InProject(proj) as data:
        found = vt.judged_score_problems(data / "scorers")
    row = result(evh("scorer-list", "--json"))["scorers"][0]
    show = result(evh("scorer-show", "s_v1", "--json"))
    check(
        "V13: no judged score is named while each was made with its scorer as it is",
        clean == [],
        clean,
    )
    check(
        "V13: a judged score whose scorer changed since is named with both hashes, and one whose scorer is gone",
        len(found) == 3
        and sum(1 for p in found if "made with s_v1" in p and sha_of("s_v1")[:12] in p and SHA[:12] not in p) == 2
        and sum(1 for p in found if "scorer ghost_v1, which is not in data/scorers" in p) == 1
        and all(p.startswith("data/runs/") for p in found),
        found,
    )  # fmt: skip
    check(
        "scorer-list and scorer-show count the judged scores made with another version of the scorer",
        row["judged_scores"] == 2
        and row["other_version"] == 2
        and show["other_version"] == 2
        and not any(x["current"] for x in show["runs"]),
        (row, show["runs"]),
    )
    _runstore.write_text(proj, "scorers/s_v1.yaml", before)
    with _runstore._InProject(proj) as data:
        found = vt.judged_score_problems(data / "scorers")
    check(
        "V13: the scorer put back, only the one with no scorer is named",
        len(found) == 1 and "ghost_v1" in found[0],
        found,
    )

    # -- the people's checks of the judges
    base = "judge-validation/s_v1"
    report = {"source": "Someone et al. 2022", "scorer": "s_v1", "articles": 2, "human_baseline": {},
              "inputs": {"scorer_sha256": sha_of("s_v1")},
              "judges": {j: {"billed_usd": 0.01, "unparsed": 0, "records_sha256": SHA} for j in ("ja", "jb")}}  # fmt: skip
    goyal = {"article_id": "1", "order": ["x", "y"], "output": '{"a": [1, 2]}', "scores": [4.0, 3.0], "cost_usd": 0.0,
             "latency_ms": 10.0, "judge_fp": "0" * 16, "prompt_sha": SHA}  # fmt: skip
    zhang = {"article_id": "9", "block": 0, "order": ["x"], "output": None, "output_sha256": SHA, "output_withheld": True,
             "withheld_reason": "quotes the article", "dims": None, "cost_usd": 0.0, "cost_known": True,
             "latency_ms": 10.0, "judge_fp": "0" * 16, "prompt_sha": SHA}  # fmt: skip
    put(f"{base}/goyal/report.json", report)
    put(f"{base}/zhang/report.json", {**report, "source": "Another et al. 2024", "articles": 1})
    for jid in ("ja", "jb"):
        put(f"{base}/goyal/{jid}/a.json", goyal)
        put(f"{base}/goyal/{jid}/b.json", {**goyal, "article_id": "2"})
    put(f"{base}/zhang/ja/c.json", zhang)
    put(f"{base}/loose/jb/d.json", goyal)
    checks_ = result(evh("scorer-show", "s_v1", "--json"))["checks"]
    by = {c["source"]: c for c in checks_}
    check(
        "scorer-show: the people's checks, a source each with its report, the judges' records counted, never the records",
        sorted(by) == ["goyal", "loose", "zhang"]
        and (by["goyal"]["citation"], by["goyal"]["articles"], by["goyal"]["records"], by["goyal"]["report"], by["goyal"]["current"])
        == ("Someone et al. 2022", 2, 4, True, True)
        and [(j["judge"], j["records"], j["billed_usd"]) for j in by["goyal"]["judges"]] == [("ja", 2, 0.01), ("jb", 2, 0.01)]
        and by["zhang"]["records"] == 1 and by["loose"]["report"] is False and by["loose"]["current"] is False
        and not any("output" in str(c) for c in checks_),
        checks_,
    )  # fmt: skip
    words = evh("scorer-show", "s_v1").stdout
    check(
        "scorer-show in words: a line a source, its articles, records and judges; no report, and a report of another version, said",
        "checked by   goyal: 2 articles, 4 records (ja 2, jb 2)" in words
        and "loose: ? articles, 1 records (jb 1); no report" in words,
        words,
    )
    _runstore.write_text(proj, "scorers/s_v1.yaml", before + "# a comment only\n")
    same = {c["source"]: c for c in result(evh("scorer-show", "s_v1", "--json"))["checks"]}["goyal"][
        "current"
    ]
    _runstore.write_text(
        proj, "scorers/s_v1.yaml", before.replace("noise_check_fraction: 0.5", "noise_check_fraction: 0.25")
    )
    other = {c["source"]: c for c in result(evh("scorer-show", "s_v1", "--json"))["checks"]}["goyal"][
        "current"
    ]
    _runstore.write_text(proj, "scorers/s_v1.yaml", before)
    check(
        "a report is of the scorer as it is: a comment keeps it current, a changed protocol does not",
        same is True and other is False,
        (same, other),
    )
    rec_v = jsonschema.Draft202012Validator(
        json.loads((HARNESS / "schemas" / "judge-validation-record.schema.json").read_text())
    )
    rep_v = jsonschema.Draft202012Validator(
        json.loads((HARNESS / "schemas" / "judge-validation-report.schema.json").read_text())
    )
    nofp = {k: v for k, v in goyal.items() if k != "judge_fp"}
    both = {**goyal, "block": 0}
    check(
        "the records' schema: both shapes of a source pass; a record with no judge_fp, one of both shapes, an unknown key do not",
        rec_v.is_valid(goyal) and rec_v.is_valid(zhang) and not rec_v.is_valid(nofp) and not rec_v.is_valid(both)
        and not rec_v.is_valid({**goyal, "extra": 1}) and not rec_v.is_valid({**goyal, "judge_fp": "abc"}),
    )  # fmt: skip
    no_inputs = {k: v for k, v in report.items() if k != "inputs"}
    check(
        "the report's schema: a report passes; one with no inputs, or a judge with no cost, does not",
        rep_v.is_valid(report) and not rep_v.is_valid(no_inputs)
        and not rep_v.is_valid({**report, "judges": {"ja": {"unparsed": 0, "records_sha256": SHA}}}),
    )  # fmt: skip

    # -- the tools that write the checks write to the project's data
    sys.path.insert(1, str(HARNESS / "tools"))
    import validate_judge_goyal as vg
    import validate_judge_zhang as vz

    check(
        "the tools that write a judge's checks (validate_judge_goyal, validate_judge_zhang) work in the project's data",
        vg.DATA.resolve() == (proj / "data").resolve() and vz.DATA.resolve() == (proj / "data").resolve()
        and vg.EXT.parent.parent.resolve() == vg.DATA.resolve() and vz.EXT.parent.parent.resolve() == vz.DATA.resolve(),
        (vg.DATA, vz.DATA),
    )  # fmt: skip

    # -- the API gives what the command line gives
    srv, port = serve()
    try:
        pairs = {"scorer-list": ("/scorers", ()), "scorer-show": ("/scorers/s_v1", ("s_v1",))}
        differ = [
            name
            for name, (route, args) in pairs.items()
            if call(port, "GET", route)[1].get("result") != result(evh(name, *args, "--json"))
        ]
        check("the API's resources give the command line's answer, for both reads", not differ, differ)
        check(
            "the API answers 404 for a scorer that does not exist",
            call(port, "GET", "/scorers/nope_v1")[0] == 404,
        )
        code, body = call(port, "PATCH", "/scorers/s_v1", {"set": {"cost_cap_usd": 5}, "by": "person:api"})
        check(
            "the API refuses the edit of a scorer that judged, naming why; nothing written",
            code == 409 and "judged score" in json.dumps(body) and stored("scorers/s_v1.yaml") == before,
            (code, body),
        )
        code, body = call(
            port,
            "POST",
            "/scorers/s_v3",
            {
                "set": json.loads(json.dumps(yaml.safe_load(before))) | {"scorer_id": "s_v3"},
                "by": "person:api",
            },
        )
        history = [json.loads(x) for x in stored("history/scorers/s_v3.jsonl").splitlines() if x.strip()]
        check(
            "the API makes a scorer through the model, recorded as who sent it",
            code == 200 and body["result"]["changed"] and history and history[-1]["by"] == "person:api",
            (code, body, history[-1:]),
        )
    finally:
        srv.terminate()
        srv.wait(timeout=20)
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
