#!/usr/bin/env python3
"""One POST of each shape of route, for the commands that became operations (RFC-032 step 9 P3, steps 3 to 5).

    python tests/test_job_routes.py

In a throwaway tutorial project ($0, offline) behind a real `evh catalog-serve`: a route that creates (`POST
/goals/{goal}/rounds`, `POST /datasets/{dataset}`), one that acts on a part (`POST /runs/{run}/promote`, `POST
/datasets/{dataset}/materialize`), one with no part (`POST /baselines/rollback`), one that takes a file the call carries
(an upload: `POST /datasets/{dataset}/label-sets/{set}`) and one that writes a file the job keeps (an artifact: `POST
/datasets/{dataset}/label-sheets`, fetched from `GET /jobs/{id}/files/<name>`). Each answers 202 with a job whose record
names the operation, the merged inputs (the route's parts and the body), the locks its declaration names and who asked;
the job runs and the answer is in the data. Every route of every operation is also called with a body that repeats its
part (400), and each file input of an operation is an upload or an artifact or the command line's only.
"""

import base64
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

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
KIT = HERE.parent / "tutorial"
os.environ.setdefault("EVAL_STORE", "files")
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-routes-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-routes")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVAL_GOALS_DIR"):
    env.pop(k, None)
SERVERS: list[subprocess.Popen] = []


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL,
    )  # fmt: skip


def serve():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port)],
        cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    SERVERS.append(p)
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    return port, (proj / ".build" / "api-token").read_text().strip()


def call(method, path, body=None, data_header=True):
    h = {"Host": f"127.0.0.1:{PORT}", "Authorization": f"Bearer {TOKEN}"}
    if data_header:
        h["X-EVH-Data"] = "1"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 — the test's own server  # nosec B310
            raw = r.read()
            try:
                return r.status, json.loads(raw or b"{}")
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def until(job_id, states=("succeeded", "failed", "cancelled", "lost"), seconds=120):
    end = time.monotonic() + seconds
    j: dict = {}
    while time.monotonic() < end:
        _st, j = call("GET", f"/api/v1/jobs/{job_id}")
        if j.get("state") in states:
            return j
        time.sleep(0.2)
    return j


def rec_of(job_id):
    return json.loads((proj / ".build" / "jobs" / job_id / "job.json").read_text())


def post(path, body, by="person:ana"):
    """POST a route; (status, the job's record on disk or the error, the job when it ran to its end)."""
    st, j = call("POST", f"/api/v1{path}", {**body, "by": by})
    if st != 202:
        return st, j, {}
    return st, rec_of(j["id"]), until(j["id"])


def log_tail(rec, done):
    """What a job printed last, for a failure's message."""
    p = proj / ".build" / "jobs" / rec.get("id", "none") / "log"
    return p.read_text()[-300:] if p.is_file() else ""


def locks_of(rec):
    return [tuple(x) for x in rec["locks"]]


try:
    data = proj / "data"
    (data / "systems").mkdir(parents=True)
    (data / "goals").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    _runstore.write_text(
        proj, "goals/tickets_summary.yaml", (KIT / "goals" / "tickets_summary.yaml").read_text()
    )
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    r = (
        r
        if r.returncode
        else evh(
            "label-import",
            "--sheet",
            str(KIT / "gold"),
            "--dataset-id",
            "tickets_v1",
            "--set",
            "g",
            "--by",
            "o",
        )
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote", "--dataset-id", "tickets_v1", "--labels", "g", "--tier", "gold",
            "--reason", "The kit's hand-written summaries decide.", "--by", "owner",
        )
    )  # fmt: skip
    for arm in ("lead1", "lead2"):
        _runstore.write_text(
            proj, f"systems/tickets_{arm}_v1.yaml", (KIT / "systems" / f"tickets_{arm}_v1.yaml").read_text()
        )
        r = r if r.returncode else evh("run", "--system", f"tickets_{arm}_v1", "--dataset", "tickets_v1")
    r = r if r.returncode else evh("catalog")
    check(
        "setup: the tutorial dataset, gold, two arms run, the catalog",
        r.returncode == 0,
        (r.stdout + r.stderr)[-300:],
    )
    lead2 = sorted(n for n in _runstore.listdir(proj, "runs") if n.startswith("tickets_lead2_v1_"))[-1]
    PORT, TOKEN = serve()

    # ── steps 3: rounds and baselines ─────────────────────────────────────────────────────────────────────────────
    st, rec, done = post(
        "/goals/tickets_summary/rounds",
        {
            "dataset": "tickets_v1",
            "keep": "tickets_lead1_v1,tickets_lead2_v1",
            "hypothesis": "which summariser",
        },
    )
    doc = (
        yaml.safe_load(_runstore.read_text(proj, "rounds/tickets_summary/r1.yaml"))
        if done.get("state") == "succeeded"
        else {}
    )
    check(
        "create: POST /goals/{goal}/rounds opens a round (round-open): 202, the goal's lock, the round written",
        st == 202
        and rec["operation"] == "round-open"
        and rec["inputs"]["goal"] == "tickets_summary"
        and rec["inputs"]["hypothesis"] == "which summariser"
        and rec["inputs"]["scoring"] == ""
        and locks_of(rec) == [("goal:tickets_summary", True), ("project", False)]
        and doc.get("status") == "open",
        (st, rec, done.get("state"), done.get("refusal")),
    )
    st, rec, done = post(
        "/goals/tickets_summary/rounds/r1/retire",
        {"arm": "tickets_lead1_v1", "reason": "one sentence is too few"},
    )
    doc = yaml.safe_load(_runstore.read_text(proj, "rounds/tickets_summary/r1.yaml"))
    gone: dict = next((a for a in doc.get("arms", []) if a["system"] == "tickets_lead1_v1"), {})
    check(
        "action on a round: POST .../retire (round-retire) retires the arm with the reason, as the person who asked",
        st == 202
        and done.get("state") == "succeeded"
        and (gone.get("retired") or {}).get("reason") == "one sentence is too few"
        and gone["retired"]["actor"]["name"] == "ana",
        (st, rec, done.get("state"), done.get("refusal")),
    )
    st, rec, done = post("/goals/tickets_summary/rounds/r1/carry", {"arm": "tickets_lead1_v1"})
    check(
        "POST .../carry (round-carry): a decision with no reason of its own; r1 is the goal's first round, so the job "
        "is refused by the harness (no earlier round has the arm: not-found), never by the route",
        st == 202
        and rec["operation"] == "round-carry"
        and done.get("state") == "failed"
        and done.get("refusal") == "not-found",
        (st, done.get("state"), done.get("refusal")),
    )
    st, rec, done = post(
        f"/runs/{lead2}/promote",
        {"reason": "the test's own baseline for the route", "goal": "tickets_summary"},
    )
    check(
        "action on a part: POST /runs/{run}/promote (run-promote): the baseline's lock from the run's own goal and "
        "dataset, the baseline written, the part in the record",
        st == 202
        and rec["inputs"]["run"] == lead2
        and locks_of(rec) == [("baselines:tickets_summary/tickets_v1", True), ("project", False)]
        and done.get("state") == "succeeded"
        and bool(_runstore.listdir(proj, "baselines")),
        (st, rec, done.get("state"), done.get("refusal")),
    )
    st, rec, done = post(
        "/baselines/rollback",
        {"goal": "tickets_summary", "dataset": "tickets_v1", "to": 1, "reason": "back to the first version"},
    )
    check(
        "no part: POST /baselines/rollback (baseline-rollback) takes every input from the body; the job is refused by "
        "the harness (version 1 is the current one), saying so",
        st == 202
        and rec["operation"] == "baseline-rollback"
        and rec["inputs"]["to"] == 1
        and locks_of(rec) == [("baselines:tickets_summary/tickets_v1", True), ("project", False)]
        and done.get("state") == "failed"
        and done.get("refusal") in ("not-allowed", "bad-argument"),
        (st, rec, done.get("state"), done.get("refusal")),
    )
    st, e = call(
        "POST", f"/api/v1/runs/{lead2}/promote", {"run": "x", "reason": "a b c d", "by": "person:ana"}
    )
    check("a body that repeats a part is refused (400)", st == 400 and "run" in e["error"], (st, e))
    st, e = call("POST", f"/api/v1/runs/{lead2}/promote", {"reason": "a b c d"})
    check("a decision with no `by` is refused (400)", st == 400, (st, e))

    # A spending operation's own route (run, step 6): its cap, the system it names, the run id the job gives it.
    st, e = call(
        "POST", "/api/v1/systems/tickets_lead1_v1/runs", {"dataset": "tickets_v1", "by": "person:ana"}
    )
    check(
        "POST /systems/{system}/runs without max_cost_usd is refused before a job exists (400)",
        st == 400 and "max_cost_usd" in e.get("error", ""),
        (st, e),
    )
    st, e = call(
        "POST",
        "/api/v1/systems/no_such_v1/runs",
        {"dataset": "tickets_v1", "by": "person:ana", "max_cost_usd": 1},
    )
    check("a run of a system that does not exist is refused (404)", st == 404, (st, e))
    st, rec, done = post("/systems/tickets_lead1_v1/runs", {"dataset": "tickets_v1", "max_cost_usd": 1})
    check(
        "POST /systems/{system}/runs starts a run job: the system from the path, the run id the job's own, "
        "the cap in its environment, and the run ends succeeded ($0, an offline arm)",
        st == 202
        and rec.get("operation") == "run"
        and rec.get("inputs", {}).get("system") == "tickets_lead1_v1"
        and str(rec.get("run_id", "")).startswith("tickets_lead1_v1_")
        and rec.get("env", {}).get("EVAL_MAX_COST_USD") == "1"
        and done.get("state") == "succeeded",
        (st, rec, done.get("state"), done.get("refusal"), log_tail(rec, done)),
    )

    # ── step 4: datasets ───────────────────────────────────────────────────────────────────────────────────────────
    for n in range(1, 13):
        _runstore.write_text(proj, f"sources/item_{n}.txt", f"item {n} of the route test\n")
    st, rec, done = post("/datasets/routes_v1", {"description": "made through its route"})
    made = _runstore.read_json(proj, "datasets/routes_v1.json") if done.get("state") == "succeeded" else {}
    check(
        "create: POST /datasets/{dataset} freezes the items of the project's data/sources (dataset-create): the part is "
        "the dataset's id, the folder is the project's own (a job names none), the dataset's lock is held",
        st == 202
        and rec["operation"] == "dataset-create"
        and rec["inputs"]
        == {"dataset_id": "routes_v1", "description": "made through its route", "glob": "*", "query": "{}"}
        and locks_of(rec) == [("dataset:routes_v1", True), ("project", False)]
        and made.get("description") == "made through its route"
        and len(made.get("items", [])) >= 12,
        (st, rec, done.get("state"), done.get("refusal"), log_tail(rec, done)),
    )
    st, e = call("POST", "/api/v1/datasets/routes_v1", {"source_dir": "/etc", "by": "person:ana"})
    check(
        "a folder of the server's is never taken: source_dir is the command line's alone (400)",
        st == 400 and "source_dir" in e["error"],
        (st, e),
    )
    st, e = call("POST", "/api/v1/datasets/routes_v2", {"source": "sources/x.py:Source", "by": "person:ana"})
    check(
        "a code file for a source is refused by the input's pattern (400)",
        st == 400 and "does not match" in e["error"],
        (st, e),
    )
    st, rec, done = post("/datasets/routes_v1/materialize", {})
    check(
        "action: POST /datasets/{dataset}/materialize: the hash-checked copy built, the dataset's lock held",
        st == 202
        and rec["inputs"] == {"dataset_id": "routes_v1"}
        and locks_of(rec) == [("dataset:routes_v1", True), ("project", False)]
        and done.get("state") == "succeeded"
        and _runstore.exists(proj, "materialized/routes_v1"),
        (st, rec, done.get("state"), done.get("refusal")),
    )
    st, rec, done = post("/datasets/routes_v1/profile", {})
    pj = (done or {}).get("result") or {}
    check(
        "POST .../profile: the profile written, and the answer is the profile (result.values.profile)",
        st == 202
        and done.get("state") == "succeeded"
        and ((pj.get("result") or {}).get("values") or {}).get("profile", {}).get("dataset_id")
        == "routes_v1",
        (st, done.get("state"), done.get("refusal")),
    )
    st, rec, done = post("/datasets/routes_v1/split", {"test": 0.4, "seed": 1})
    check(
        "POST .../split: the two datasets beside it, all three locked (the function adds the sides)",
        st == 202
        and locks_of(rec)
        == [
            ("dataset:routes_v1", True),
            ("dataset:routes_v1_test", True),
            ("dataset:routes_v1_validation", True),
            ("project", False),
        ]
        and rec["inputs"]["split_by"] == "hash"
        and rec["inputs"]["seed"] == 1
        and done.get("state") == "succeeded"
        and _runstore.exists(proj, "datasets/routes_v1_test.json"),
        (st, rec, done.get("state"), done.get("refusal")),
    )
    st, rec, done = post("/dataset-descriptions", {"dataset_id": "routes_v1", "licence": "MIT"})
    check(
        "no part: POST /dataset-descriptions (dataset-describe; its dataset is optional for --card-template, so the route "
        "has no part): licence written",
        st == 202
        and rec["inputs"]["dataset_id"] == "routes_v1"
        and done.get("state") == "succeeded"
        and _runstore.read_json(proj, "datasets/routes_v1.json").get("licence") == "MIT",
        (st, rec, done.get("state"), done.get("refusal")),
    )
    card = "dataUseCases: to test the route\n"
    up = {"name": "card.yaml", "content_base64": base64.b64encode(card.encode()).decode()}
    st, rec, done = post("/dataset-descriptions", {"dataset_id": "routes_v1", "card": up})
    kept = proj / rec["inputs"]["card"] if st == 202 else None
    check(
        "upload: a card carried in the call is kept under .build/uploads/<sha256>/ and the job is given its path; the card "
        "is on the dataset",
        st == 202
        and rec["inputs"]["card"].startswith(".build/uploads/")
        and kept is not None
        and kept.read_text() == card
        and done.get("state") == "succeeded"
        and _runstore.read_json(proj, "datasets/routes_v1.json").get("card")
        == {"dataUseCases": "to test the route"},
        (st, rec, done.get("state"), done.get("refusal")),
    )
    st, e = call(
        "POST",
        "/api/v1/dataset-descriptions",
        {"dataset_id": "routes_v1", "card": "data/card.yaml", "by": "person:ana"},
    )
    check("a card named by a path is refused: a file is an upload (400)", st == 400, (st, e))
    st, rec, done = post("/fieldset-proposals", {"source": "folder", "fieldset_id": "routes_f"})
    check(
        "no part: POST /fieldset-proposals (fieldset-propose; /fieldsets/propose would be swallowed by POST /fieldsets/"
        "{fieldset}): 202, nothing to lock beyond the project",
        st == 202 and locks_of(rec) == [("project", False)] and rec["inputs"]["sample"] == 200,
        (st, rec, done.get("state"), done.get("refusal")),
    )
    st, rec, done = post(
        "/datasets/routes_v1/picks",
        {"item": [made["items"][0]["item_id"]], "targets": ["routes_v1"], "note": "a pick"},
    )
    check(
        "POST /datasets/{dataset}/picks (pick): the pick list's lock; the item is waiting, by the person who asked",
        st == 202
        and locks_of(rec) == [("picks", True), ("project", False)]
        and done.get("state") == "succeeded"
        and "a pick" in _runstore.read_text(proj, "picks.jsonl"),
        (st, rec, done.get("state"), done.get("refusal")),
    )
    st, rec, done = post(
        "/datasets/routes_v1_test/sealed-counts/allow", {"add": "x", "reason": "the counts need it"}
    )
    check(
        "a decision on a part: POST .../sealed-counts/allow (dataset-seal-counts) is a job that the harness refuses (not a "
        "sealed side), never the route; the reason is an input",
        st == 202
        and rec["operation"] == "dataset-seal-counts"
        and done.get("state") == "failed"
        and rec["inputs"]["reason"],
        (st, done.get("state"), done.get("refusal")),
    )

    # ── step 5: labels, references, captures ───────────────────────────────────────────────────────────────────────
    rows = [
        {"id": f"r{i}", "body": f"row {i}", "kind": "x", "created_at": f"2026-10-0{i}T10:00:00Z"}
        for i in range(1, 7)
    ]
    (proj / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    st, rec, done = post("/captures/rc1", {"importer": "jsonl", "query": json.dumps({"path": "rows.jsonl"})})
    check(
        "create: POST /captures/{capture} keeps a production system's records (capture): the captures' lock, exclusive",
        st == 202
        and rec["operation"] == "capture"
        and locks_of(rec) == [("captures", True), ("project", False)]
        and done.get("state") == "succeeded"
        and _runstore.exists(proj, "captures/rc1/capture.json"),
        (st, rec, done.get("state"), done.get("refusal"), log_tail(rec, done)),
    )
    st, e = call(
        "POST", "/api/v1/captures/rc2", {"importer": "x.py:Importer", "query": "{}", "by": "person:ana"}
    )
    check(
        "a code file for an importer is refused by the pattern (400)",
        st == 400 and "does not match" in e["error"],
        (st, e),
    )
    st, e = call(
        "POST", "/api/v1/captures/rc2", {"importer": "jsonl", "query": "@/etc/hostname", "by": "person:ana"}
    )
    check(
        "a query that names a file (@file) is refused by the pattern (400)",
        st == 400 and "does not match" in e["error"],
        (st, e),
    )
    st, rec, done = post("/importers/jsonl/check", {"query": json.dumps({"path": "rows.jsonl"})})
    check(
        "POST /importers/{importer}/check (importer-check): nothing to lock beyond the project, the importer read twice",
        st == 202 and locks_of(rec) == [("project", False)] and done.get("state") == "succeeded",
        (st, rec, done.get("state"), done.get("refusal"), log_tail(rec, done)),
    )
    st, rec, done = post("/captures/rc1/datasets", {"dataset_id": "rcap_v1"})
    check(
        "action on a capture: POST /captures/{capture}/datasets (dataset-from-capture) freezes its records as a dataset: "
        "the captures read-locked, the new dataset's lock exclusive",
        st == 202
        and locks_of(rec) == [("captures", False), ("dataset:rcap_v1", True), ("project", False)]
        and done.get("state") == "succeeded"
        and len(_runstore.read_json(proj, "datasets/rcap_v1.json").get("items", [])) == 6,
        (st, rec, done.get("state"), done.get("refusal"), log_tail(rec, done)),
    )
    st, rec, done = post("/captures/rc1/restore", {})
    check(
        "POST /captures/{capture}/restore (capture-restore): the records read again from the source, every hash checked",
        st == 202 and done.get("state") == "succeeded",
        (st, done.get("state"), done.get("refusal"), log_tail(rec, done)),
    )
    # an artifact: the sheet is written in the job's folder and fetched from there
    st, rec, done = post("/datasets/routes_v1/label-sheets", {"out": "sheet.csv", "items": "all"})
    stf, sheet = call("GET", f"/api/v1/jobs/{rec['id']}/files/sheet.csv") if st == 202 else (0, b"")
    check(
        "artifact: POST /datasets/{dataset}/label-sheets (label-sheet) writes the sheet in the job's own folder (the input "
        "is the name given, kept as a path there) and GET /jobs/{id}/files/sheet.csv fetches it",
        st == 202
        and rec["inputs"]["out"] == f".build/jobs/{rec['id']}/sheet.csv"
        and done.get("state") == "succeeded"
        and stf == 200
        and isinstance(sheet, bytes)
        and b"item_id" in sheet,
        (st, rec, done.get("state"), done.get("refusal"), stf),
    )
    st, e = call("POST", "/api/v1/datasets/routes_v1/label-sheets", {"out": "/etc/x.csv", "by": "person:ana"})
    check(
        "an artifact named with a path is only its file name, in the job's folder (the job is made, the folder is its own)",
        st == 202 and e["inputs"]["out"].endswith("/x.csv") and e["inputs"]["out"].startswith(".build/jobs/"),
        (st, e),
    )
    # an upload: the filled sheet read back as a person's label set
    import csv
    import io

    reader = list(csv.reader(io.StringIO(sheet.decode())))
    head, body_rows = reader[0], reader[1:]
    col = head.index("label")
    for row in body_rows:
        row[col] = "good"
    filled = io.StringIO()
    csv.writer(filled).writerows([head, *body_rows])
    up = {"name": "filled.csv", "content_base64": base64.b64encode(filled.getvalue().encode()).decode()}
    st, rec, done = post("/datasets/routes_v1/label-sets/rs1", {"sheet": up})
    check(
        "upload: POST /datasets/{dataset}/label-sets/{set} (label-import) is given the sheet the call carries, kept under "
        ".build/uploads; the label set is written as the person who asked (both parts are in the inputs)",
        st == 202
        and rec["inputs"]["sheet"].startswith(".build/uploads/")
        and rec["inputs"]["dataset_id"] == "routes_v1"
        and rec["inputs"]["set"] == "rs1"
        and done.get("state") == "succeeded"
        and _runstore.read_json(proj, "labels/routes_v1/rs1/labels.json").get("source", {}).get("by")
        == "person:ana",
        (st, rec, done.get("state"), done.get("refusal"), log_tail(rec, done)),
    )
    st, e = call(
        "POST", "/api/v1/datasets/routes_v1/label-sets/rs2", {"sheet": "filled.csv", "by": "person:ana"}
    )
    check("a sheet named by a path is refused: a file is an upload (400)", st == 400, (st, e))
    st, rec, done = post(
        "/datasets/routes_v1/references",
        {"labels": "rs1", "tier": "gold", "reason": "the test's labels decide"},
    )
    check(
        "a decision with a part: POST /datasets/{dataset}/references (reference-promote): the labels promoted, the reason "
        "an input, the dataset's lock",
        st == 202
        and rec["operation"] == "reference-promote"
        and locks_of(rec) == [("dataset:routes_v1", True), ("project", False)]
        and done.get("state") == "succeeded"
        and bool(_runstore.listdir(proj, "references/gold")),
        (st, rec, done.get("state"), done.get("refusal"), log_tail(rec, done)),
    )
    st, rec, done = post(f"/runs/{lead2}/label-sets", {"set": "from_run_1"})
    check(
        "POST /runs/{run}/label-sets (label-from-run): the lock is the run's own dataset, read from the run",
        st == 202
        and locks_of(rec) == [("dataset:tickets_v1", True), ("project", False)]
        and done.get("state") == "succeeded",
        (st, rec, done.get("state"), done.get("refusal"), log_tail(rec, done)),
    )
    ids = sorted(p.stem for p in (proj / "tutorial" / "tickets").glob("*.txt"))
    scores = "".join(json.dumps({"item_id": i, "acc": 1.0}) + "\n" for i in ids)

    def carried(name, text):
        return {"name": name, "content_base64": base64.b64encode(text.encode()).decode()}

    st, rec, done = post(
        "/datasets/tickets_v1/runs/import",
        {
            "system_id": "imported_v1", "primary_metric": "acc", "source": "a route test", "scorer_id": "test",
            "build_ref": "test", "scores": carried("scores.jsonl", scores),
            "scorer_file": [carried("scorer.py", '"""a scorer"""\n\n\ndef score(x):\n    return 1.0\n')],
        },
    )  # fmt: skip
    check(
        "uploads: POST /datasets/{dataset}/runs/import (import-run) is given a scores file and a list of scoring files, "
        "each kept under .build/uploads; the run is written",
        st == 202
        and rec["inputs"]["scores"].startswith(".build/uploads/")
        and [x.startswith(".build/uploads/") for x in rec["inputs"]["scorer_file"]] == [True]
        and done.get("state") == "succeeded",
        (st, rec, done.get("state"), done.get("refusal"), log_tail(rec, done)),
    )
    st, e = call(
        "POST", "/api/v1/datasets/tickets_v1/runs/import",
        {"system_id": "x", "primary_metric": "acc", "source": "s", "scorer_id": "t", "build_ref": "b", "scores": "scores.jsonl", "by": "person:ana"},
    )  # fmt: skip
    check("scores named by a path are refused: a file is an upload (400)", st == 400, (st, e))
finally:
    for p in SERVERS:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
