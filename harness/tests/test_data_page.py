#!/usr/bin/env python3
"""The data page's commands and API (PRD-016, UXS-004, ADR-0027), on both stores.

    python tests/test_data_page.py

In a tutorial project with a dataset, two runs, a goal, kept as files and then moved into its database:

  - evh data-ls: the store, the settings folders with their counts, the data folders; a folder; --find.
  - evh data-show: a setting's text, size, sha256; a run's file says what writes it.
  - evh data-put --check: a YAML error with its line, a schema error, an id that is not the file name; nothing saved.
  - evh data-put: a valid change saved and read back; --new refuses a name taken; a harness-written file, a path
    outside data/ and Python are refused.
  - evh data-put --set / --unset and data-show --fields: one field changed, the file's comments and every other line
    kept; a field the schema requires, unset, is refused and nothing is saved.
  - evh data-rm: --dry-run names what a run takes; a setting, then a run, deleted (its outputs and rows with it);
    a dataset refused.
  - The API on a local catalog-serve answers the same: GET form (schema, values, the project's datasets, the runs
    made with a config), PUT form (problems at their fields and nothing written; a save that keeps comments; an
    unchanged save that writes nothing; a new goal, then --new refusing it again); a write without the X-EVH-Data
    header, or from another origin, is refused; a public server answers no /api/data call, a write least of all.
"""

from __future__ import annotations

import atexit
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
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HARNESS / "tools"))  # _wheel, shared with the deploy
import _wheel  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

#: The package as `pip install` lays it out (built once per process): the commands run from it, as a project runs
#: them, so a file the package leaves out fails here.
_SITE: list[Path] = []


def site() -> Path:
    if not _SITE:
        tmp = Path(tempfile.mkdtemp(prefix="evh-datapage-site-"))
        atexit.register(shutil.rmtree, tmp, True)
        _SITE.append(_wheel.install(tmp / "site-packages"))
    return _SITE[0]


GOOD_GOAL_EDIT = "# the margin a person changed on the page\n"


def setup(store: str) -> tuple[Path, dict]:
    proj = Path(tempfile.mkdtemp(prefix=f"evh-datapage-{store}-"))
    env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-data-page", PYTHONPATH=str(site()))
    for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_STORE", "EVAL_MAX_COST_USD"):
        env.pop(k, None)

    def evh(*args: str) -> None:
        r = subprocess.run([sys.executable, "-m", "evaluation_harness", *args], cwd=proj, env=env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)  # fmt: skip
        if r.returncode:
            raise SystemExit(f"setup: evh {' '.join(args)} failed:\n{r.stdout}{r.stderr}")

    evh("init", "--tutorial")
    shutil.copy(proj / "tutorial/fields/tickets.yaml", proj / "data/fields/")
    evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets", "--fieldset", "tickets",
        "--fields", "tutorial/ticket_fields.csv")  # fmt: skip
    evh("dataset-materialize", "--dataset-id", "tickets_v1")
    for f in (proj / "tutorial/configs").glob("tickets_*.yaml"):
        shutil.copy(f, proj / "data/configs/")
    for arm in ("lead1", "lead2"):
        evh("run", "--config", f"data/configs/tickets_{arm}.yaml")
    shutil.copy(proj / "tutorial/goals/tickets_summary.yaml", proj / "data/goals/")
    if store == "sqlite":
        (proj / "config.yaml").write_text("store: sqlite\nconfigure: true\n")
        env["EVAL_STORE"] = "sqlite"
        evh("data-migrate", "--to", "sqlite")
    evh("catalog")
    return proj, env


def cli(proj: Path, env: dict, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "evaluation_harness", *args], cwd=proj, env=env,
                          capture_output=True, text=True, input=stdin)  # fmt: skip


def serve(proj: Path, env: dict, *extra: str) -> tuple:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    log = proj / "serve.log"
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.Popen([sys.executable, "-m", "evaluation_harness", "catalog-serve", "--port", str(port), *extra],
                             cwd=proj, env=env, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)  # fmt: skip
    for _ in range(150):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)  # nosec B310
            break
        except Exception:  # noqa: BLE001 - not up yet
            if p.poll() is not None:
                raise SystemExit(f"catalog-serve exited:\n{log.read_text()}") from None
            time.sleep(0.1)
    return p, port


def http(
    port: int,
    method: str,
    route: str,
    body: str | None = None,
    headers: dict | None = None,
    host: str | None = None,
):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{route}", data=body.encode() if body is not None else None,
                                 method=method, headers=headers or {})  # fmt: skip
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - the test's own server  # nosec B310
            raw = r.read()
            return r.status, json.loads(raw) if raw[:1] in (b"{", b"[") else raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


W = {"X-EVH-Data": "1", "Content-Type": "application/json; charset=utf-8"}


def run_case(store: str) -> None:
    proj, env = setup(store)
    try:
        data = proj / "data"
        goal = "goals/tickets_summary.yaml"
        r = cli(proj, env, "data-ls")
        check(
            f"{store}: data-ls names the store, the settings folders and the data folders",
            r.returncode == 0
            and f"store: {store}" in r.stdout
            and "configs" in r.stdout
            and "runs" in r.stdout,
            (r.stdout + r.stderr)[-400:],
        )
        r = cli(proj, env, "data-ls", "configs", "--json")
        names = (
            [e["name"] for e in json.loads(r.stdout)["result"]["values"]["listing"]["entries"]]
            if r.returncode == 0
            else []
        )
        check(f"{store}: data-ls configs lists the arm configs", "tickets_lead1.yaml" in names, names)
        r = cli(proj, env, "data-ls", "scorers", "--json")
        ls = json.loads(r.stdout)["result"]["values"]["listing"] if r.returncode == 0 else {}
        check(
            f"{store}: a settings folder not made yet lists empty, ready for its first file",
            ls.get("entries") == [] and ls.get("settings_folder") == "scorers",
            (r.stdout + r.stderr)[-300:],
        )
        r = cli(proj, env, "data-ls", "nothing-here")
        check(f"{store}: any other missing folder is refused", r.returncode != 0, r.stdout[-200:])
        r = cli(proj, env, "data-ls", "--find", "summary")
        check(f"{store}: data-ls --find finds the goal by name", goal in r.stdout, r.stdout[-300:])
        r = cli(proj, env, "data-show", goal, "--json")
        f = json.loads(r.stdout)["result"]["values"]["file"] if r.returncode == 0 else {}
        before = f.get("text") or ""
        check(f"{store}: data-show: a goal's text, editable, its sha256", "goal_id: tickets_summary" in before
              and f.get("editable") is True and len(f.get("sha256", "")) == 64, f)  # fmt: skip
        run = next(
            e["path"]
            for e in json.loads(cli(proj, env, "data-ls", "runs", "--json").stdout)["result"]["values"][
                "listing"
            ]["entries"]
            if e["type"] == "run"
        )
        r = cli(proj, env, "data-show", f"{run}/metrics.json")
        check(f"{store}: a run's file says it is written by evh run and is not edited here",
              r.returncode == 0 and "written by evh run" in r.stdout, r.stdout[-200:])  # fmt: skip

        # Checks: nothing saved on a problem.
        r = cli(
            proj, env, "data-put", goal, "-", "--check", stdin="goal_id: tickets_summary\ntitle: [unclosed\n"
        )
        check(
            f"{store}: --check: a YAML error with its line",
            r.returncode == 1 and "not YAML (line" in r.stdout,
            r.stdout,
        )
        r = cli(
            proj,
            env,
            "data-put",
            goal,
            "-",
            "--check",
            stdin=before.replace("goal_id: tickets_summary", "goal_id: other"),
        )
        check(
            f"{store}: --check: an id that is not the file name",
            r.returncode == 1 and "must be the file name" in r.stdout,
            r.stdout,
        )
        cfg = cli(proj, env, "data-show", "configs/tickets_lead1.yaml", "--text").stdout
        r = cli(proj, env, "data-put", "configs/tickets_lead1.yaml", "-", "--check", stdin=cfg)
        check(f"{store}: --check: an arm config's config_id need not be its file name (the tutorial's is not)",
              r.returncode == 0 and "passes the check: it parses, matches config.schema.json" in r.stdout, r.stdout)  # fmt: skip
        r = cli(proj, env, "data-put", goal, "-", "--check", stdin="goal_id: tickets_summary\n")
        check(
            f"{store}: --check: the schema's missing keys",
            r.returncode == 1 and "title: required" in r.stdout,
            r.stdout[-300:],
        )
        r = cli(proj, env, "data-put", goal, "-", stdin="goal_id: tickets_summary\n")
        same = cli(proj, env, "data-show", goal, "--text").stdout
        check(f"{store}: a failing put is refused and saves nothing", r.returncode != 0 and "ERROR (invalid-file)" in r.stderr
              and same == before, r.stderr[-300:])  # fmt: skip
        # A valid change, saved and read back.
        r = cli(proj, env, "data-put", goal, "-", stdin=GOOD_GOAL_EDIT + before)
        check(f"{store}: a valid change is saved and reads back", r.returncode == 0 and "saved goals/tickets_summary.yaml" in r.stdout
              and cli(proj, env, "data-show", goal, "--text").stdout == GOOD_GOAL_EDIT + before, (r.stdout + r.stderr)[-300:])  # fmt: skip
        r = cli(proj, env, "goals")
        check(
            f"{store}: evh goals reads the changed goal",
            r.returncode == 0 and "tickets_summary" in r.stdout,
            r.stderr[-300:],
        )
        r = cli(proj, env, "data-put", goal, "-", "--new", stdin=before)
        check(
            f"{store}: --new refuses a name already taken",
            "ERROR (would-overwrite)" in r.stderr,
            r.stderr[-200:],
        )
        new_cfg = cli(proj, env, "data-show", "configs/tickets_lead1.yaml", "--text").stdout.replace(
            "config_id: tickets_lead1_v1", "config_id: tickets_lead3"
        )
        r = cli(proj, env, "data-put", "configs/tickets_lead3.yaml", "-", "--new", stdin=new_cfg)
        check(f"{store}: a new arm config is created", r.returncode == 0, (r.stdout + r.stderr)[-300:])
        # One field at a time, as the form saves: the comments and every other line kept.
        lead1 = "configs/tickets_lead1.yaml"
        cfg_before = cli(proj, env, "data-show", lead1, "--text").stdout
        r = cli(proj, env, "data-put", lead1, "--set", "params.sentences=2")
        cfg_after = cli(proj, env, "data-show", lead1, "--text").stdout
        changed = [(a, b) for a, b in zip(cfg_before.splitlines(), cfg_after.splitlines()) if a != b]
        check(f"{store}: data-put --set changes one line, the comments kept",
              r.returncode == 0 and changed == [("  sentences: 1", "  sentences: 2")]
              and len(cfg_before.splitlines()) == len(cfg_after.splitlines()) and cfg_after.startswith("# Arm"),
              (changed, (r.stdout + r.stderr)[-300:]))  # fmt: skip
        r = cli(proj, env, "data-show", lead1, "--fields")
        check(f"{store}: data-show --fields prints the dotted keys --set takes",
              r.returncode == 0 and "params.sentences: 2" in r.stdout and "config_id: tickets_lead1_v1" in r.stdout, r.stdout[-300:])  # fmt: skip
        r = cli(proj, env, "data-put", lead1, "--unset", "dataset_id")
        check(f"{store}: --unset of a required field is refused at its field; nothing saved",
              r.returncode == 1 and "dataset_id: required" in r.stdout
              and cli(proj, env, "data-show", lead1, "--text").stdout == cfg_after, r.stdout[-300:])  # fmt: skip
        r = cli(proj, env, "data-put", lead1, "--set", "params.sentences=2")
        check(
            f"{store}: a --set that changes nothing writes nothing",
            r.returncode == 0 and "nothing changed" in r.stdout,
            r.stdout,
        )
        r = cli(proj, env, "data-put", lead1, "--set", "goal=no_such_goal")
        check(f"{store}: a change the schema allows but evh validate refuses is put back, and says why",
              r.returncode != 0 and "V14" in r.stderr and "no_such_goal" in r.stderr
              and cli(proj, env, "data-show", lead1, "--text").stdout == cfg_after, r.stderr[-400:])  # fmt: skip
        for target, why in ((f"{run}/metrics.json", "written by evh run"), ("datasets/tickets_v1.json", "written by the dataset-* commands"),
                            ("../config.yaml", "outside the project's data"), ("configs/x.py", "code")):  # fmt: skip
            r = cli(proj, env, "data-put", target, "-", stdin="x: 1\n")
            check(
                f"{store}: data-put refuses {target}",
                r.returncode != 0 and "ERROR (not-allowed)" in r.stderr and why in r.stderr,
                r.stderr[-200:],
            )

        if store == "files":
            # No Configure part in a files project: not built, not served, refused when asked for.
            p, port = serve(proj, env)
            try:
                code, _b = http(port, "GET", "/api/data/store")
                code2, _b = http(port, "PUT", "/api/data/form?path=" + goal, "{}", W)
                check(f"{store}: a files project's server answers no /api/data call, a write least of all",
                      code == 404 and code2 == 404, (code, code2))  # fmt: skip
            finally:
                os.killpg(p.pid, 15)
                p.wait(timeout=30)
            check(f"{store}: its catalog has no Configure page or scripts",
                  not (proj / ".build/catalog/data.html").exists() and not (proj / ".build/catalog/assets/data.js").exists()
                  and ">Configure<" not in (proj / ".build/catalog/index.html").read_text())  # fmt: skip
            on = dict(env, EVAL_CONFIGURE="1")
            r = subprocess.run([sys.executable, "-m", "evaluation_harness", "catalog"], cwd=proj, env=on,
                               capture_output=True, text=True, check=False)  # fmt: skip
            check(f"{store}: EVAL_CONFIGURE=1 is refused: the Configure pages need store: sqlite",
                  r.returncode != 0 and "ERROR (not-allowed)" in r.stderr and "need store: sqlite" in r.stderr, r.stderr[-300:])  # fmt: skip
            r = subprocess.run([sys.executable, "-m", "evaluation_harness", "validate"], cwd=proj, env=on,
                               capture_output=True, text=True, check=False)  # fmt: skip
            check(
                f"{store}: evh validate (V23) names it",
                r.returncode != 0 and "need store: sqlite" in r.stdout,
                r.stdout[-400:],
            )
        else:
            # The API on a local server, then a public one.
            p, port = serve(proj, env)
            try:
                code, body = http(port, "GET", "/api/data/store")
                check(
                    f"{store}: GET /api/data/store answers locally",
                    code == 200 and body.get("store") == store,
                    (code, body),
                )
                code, body = http(port, "GET", "/api/data/file?path=" + goal)
                check(
                    f"{store}: GET /api/data/file reads the changed goal",
                    code == 200 and body["text"].startswith(GOOD_GOAL_EDIT),
                    code,
                )
                code, form = http(port, "GET", "/api/data/form?path=" + goal)
                check(f"{store}: GET form: the goal's schema, its values, the project's datasets",
                      code == 200 and form["schema"]["properties"]["goal_id"] and form["values"]["goal_id"] == "tickets_summary"
                      and "tickets_v1" in form["options"]["datasets"] and form["refs"]["datasets.*.dataset_id"] == "datasets",
                      (code, str(form)[:300]))  # fmt: skip
                code, cform = http(port, "GET", "/api/data/form?path=configs/tickets_lead1.yaml")
                check(f"{store}: GET form of an arm config counts the runs made with its config_id",
                      code == 200 and cform.get("runs_made") == 1, (code, cform.get("runs_made")))  # fmt: skip
                values = form["values"]
                changed = json.loads(json.dumps(values))
                changed["title"] = "Ticket summaries, edited on the form"
                code, body = http(
                    port,
                    "PUT",
                    "/api/data/form?path=" + goal,
                    json.dumps(changed),
                    {"Content-Type": "application/json"},
                )
                check(
                    f"{store}: a write without the X-EVH-Data header is refused",
                    code == 403 and "X-EVH-Data" in body.get("error", ""),
                    (code, body),
                )
                code, body = http(
                    port,
                    "PUT",
                    "/api/data/form?path=" + goal,
                    json.dumps(changed),
                    {**W, "Origin": "http://evil.example"},
                )
                check(f"{store}: a write from another origin is refused", code == 403, (code, body))
                bad = json.loads(json.dumps(values))
                del bad["decision"]
                bad["datasets"][0]["notes"] = 3
                code, body = http(port, "PUT", "/api/data/form?path=" + goal, json.dumps(bad), W)
                where = sorted(".".join(map(str, p["path"])) for p in body.get("problems", []))
                check(f"{store}: PUT form with problems: each at its field, nothing written",
                      code == 200 and body.get("saved") is False and where == ["datasets.0.notes", "decision"]
                      and http(port, "GET", "/api/data/file?path=" + goal)[1]["text"].startswith(GOOD_GOAL_EDIT), (code, body))  # fmt: skip
                code, body = http(port, "PUT", "/api/data/form?path=" + goal, json.dumps(changed), W)
                text = http(port, "GET", "/api/data/file?path=" + goal)[1]["text"]
                check(f"{store}: PUT form saves the value and keeps the file's comment",
                      code == 200 and body.get("saved") and text.startswith(GOOD_GOAL_EDIT)
                      and "title: Ticket summaries, edited on the form" in text, (code, str(body)[:300]))  # fmt: skip
                sha = body.get("sha256")
                code, body = http(port, "PUT", "/api/data/form?path=" + goal, json.dumps(changed), W)
                check(
                    f"{store}: an unchanged save writes nothing",
                    code == 200 and body.get("unchanged") and body.get("sha256") == sha,
                    (code, body),
                )
                code, nform = http(port, "GET", "/api/data/form?new=goals")
                draft = nform["values"] if code == 200 else {}
                draft.update(
                    goal_id="draft_goal",
                    title="A draft",
                    statement="Drafts for people so that they decide.",
                    decision="Which draft.",
                )
                draft["success_criteria"]["primary"]["measure"] = "overlap_f1"
                draft["datasets"][0]["dataset_id"] = "tickets_v1"
                code, body = http(
                    port, "PUT", "/api/data/form?path=goals/draft_goal.yaml&new=1", json.dumps(draft), W
                )
                check(
                    f"{store}: a new goal from GET form?new=goals is created",
                    code == 200 and body.get("saved"),
                    (code, body),
                )
                code, body = http(
                    port, "PUT", "/api/data/form?path=goals/draft_goal.yaml&new=1", json.dumps(draft), W
                )
                check(f"{store}: new=1 refuses a name already taken", code == 409, (code, body))
                code, body = http(port, "DELETE", "/api/data/file?path=goals/draft_goal.yaml", None, W)
                check(f"{store}: the new goal is deleted", code == 200, (code, body))
                bad_cfg = json.loads(json.dumps(cform["values"]))
                bad_cfg["goal"] = "no_such_goal"
                cfg_text = http(port, "GET", "/api/data/file?path=configs/tickets_lead1.yaml")[1]["text"]
                code, body = http(
                    port, "PUT", "/api/data/form?path=configs/tickets_lead1.yaml", json.dumps(bad_cfg), W
                )
                msgs = " | ".join(p["message"] for p in body.get("problems", []))
                check(f"{store}: PUT form: what evh validate refuses comes back as problems, the file put back",
                      code == 200 and body.get("saved") is False and "V14" in msgs and "no_such_goal" in msgs
                      and http(port, "GET", "/api/data/file?path=configs/tickets_lead1.yaml")[1]["text"] == cfg_text, (code, body))  # fmt: skip
                code, gp = http(port, "GET", "/api/data/form?new=goals/policy.yaml")
                code2, body = http(
                    port,
                    "PUT",
                    "/api/data/form?path=goals/policy.yaml&new=1",
                    json.dumps({"required_from": "2099-01-01"}),
                    W,
                )
                code3, shown = http(port, "GET", "/api/data/file?path=goals/policy.yaml")
                check(f"{store}: the goal policy is a setting of its own: its form, created, read back",
                      code == 200 and gp.get("kind") == "goal policy" and code2 == 200 and body.get("saved") and code3 == 200
                      and "2099-01-01" in shown.get("text", "") and shown.get("setting_kind") == "goal policy",
                      (gp.get("kind"), body, shown.get("text")))  # fmt: skip
                http(port, "DELETE", "/api/data/file?path=goals/policy.yaml", None, W)
                code, body = http(port, "PUT", "/api/data/form?path=datasets/tickets_v1.json", "{}", W)
                check(
                    f"{store}: PUT form refuses a harness-written file",
                    code == 403 and body.get("kind") == "not-allowed",
                    (code, body),
                )
                code, body = http(port, "GET", "/api/data/list?path=..%2F")
                check(f"{store}: a path outside data/ is refused", code in (403, 404), (code, body))
                code, body = http(port, "GET", "/api/data/store", host="evil.example")
                check(f"{store}: another Host is refused (DNS rebinding)", code == 403, code)
                code, body = http(port, "GET", "/api/data/run?path=" + run)
                n_out = body.get("outputs") if code == 200 else None
                check(
                    f"{store}: GET run names what a delete takes",
                    code == 200 and n_out and body.get("rows"),
                    (code, body),
                )
                code, body = http(port, "DELETE", "/api/data/file?path=" + run, None, W)
                check(
                    f"{store}: DELETE deletes a whole run with its outputs and rows",
                    code == 200 and body.get("outputs") == n_out,
                    (code, body),
                )
                code, body = http(port, "GET", "/api/data/file?path=" + f"{run}/metrics.json")
                check(f"{store}: the deleted run is gone", code == 404, code)
                code, body = http(port, "DELETE", "/api/data/file?path=datasets/tickets_v1.json", None, W)
                check(f"{store}: DELETE refuses a dataset", code == 403, (code, body))
                # The page asks in parallel, and the server answers on threads sharing one database connection: an
                # unlocked connection killed the server (2026-11-06). Every answer, and the server still up.
                from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

                routes = ["/api/data/store", "/api/data/list?path=configs", "/api/data/file?path=" + goal,
                          "/api/data/find?q=tickets", "/api/data/list?path=runs"] * 16  # fmt: skip
                with ThreadPoolExecutor(max_workers=16) as pool:
                    codes = list(pool.map(lambda rt: http(port, "GET", rt)[0], routes))
                alive = http(port, "GET", "/api/health")[0]
                check(f"{store}: 80 requests at once all answered, the server still up",
                      codes == [200] * len(routes) and alive == 200, sorted(set(codes)))  # fmt: skip
            finally:
                os.killpg(p.pid, 15)
                p.wait(timeout=30)
        if store == "sqlite":
            check(f"{store}: everything above stayed in the database (nothing under data/ on disk)",
                  sorted(x.name for x in data.iterdir()) == ["project.sqlite"] or all(x.name.startswith("project.sqlite") for x in data.iterdir()),
                  sorted(x.name for x in data.iterdir()))  # fmt: skip
        # The commands' deletes.
        r = cli(proj, env, "data-rm", "configs/tickets_lead3.yaml", "--dry-run")
        check(f"{store}: data-rm --dry-run deletes nothing", r.returncode == 0 and "would delete" in r.stdout
              and cli(proj, env, "data-show", "configs/tickets_lead3.yaml").returncode == 0, r.stdout)  # fmt: skip
        r = cli(proj, env, "data-rm", "configs/tickets_lead3.yaml")
        check(
            f"{store}: data-rm deletes a setting",
            r.returncode == 0 and cli(proj, env, "data-show", "configs/tickets_lead3.yaml").returncode != 0,
            r.stderr[-200:],
        )
        r = cli(proj, env, "data-rm", "datasets/tickets_v1.json", "--dry-run")
        check(
            f"{store}: data-rm --dry-run refuses a dataset as data-rm would",
            "ERROR (not-allowed)" in r.stderr,
            r.stderr[-200:],
        )
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def public_case() -> None:
    """A public server answers no /api/data call, a write least of all: even for a project that deploys Configure."""
    proj, env = setup("sqlite")
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        log = proj / "public.log"
        with open(log, "w", encoding="utf-8") as fh:
            p = subprocess.Popen([sys.executable, "-m", "evaluation_harness", "catalog-serve", "--port", str(port),
                                  "--public", f"127.0.0.1:{port}"], cwd=proj, env=env, stdout=fh,
                                 stderr=subprocess.STDOUT, start_new_session=True)  # fmt: skip
        try:
            for _ in range(150):
                try:
                    code, _b = http(port, "GET", "/api/health", host=f"127.0.0.1:{port}")
                    if code == 200:
                        break
                except urllib.error.URLError:
                    pass  # not up yet
                if p.poll() is not None:
                    raise SystemExit(f"catalog-serve --public exited:\n{log.read_text()}")
                time.sleep(0.1)
            code, _b = http(port, "GET", "/api/data/store")
            check("public: GET /api/data/store is 404", code == 404, code)
            code, _b = http(port, "PUT", "/api/data/form?path=goals/tickets_summary.yaml", "{}", W)
            check("public: PUT form is 404", code == 404, code)
            code, _b = http(port, "DELETE", "/api/data/file?path=goals/tickets_summary.yaml", None, W)
            r = subprocess.run([sys.executable, "-m", "evaluation_harness", "data-show", "goals/tickets_summary.yaml"],
                               cwd=proj, env=env, capture_output=True, text=True, check=False)  # fmt: skip
            check("public: DELETE is 404, the goal untouched", code == 404 and r.returncode == 0, code)
        finally:
            os.killpg(p.pid, 15)
            p.wait(timeout=30)
    finally:
        shutil.rmtree(proj, ignore_errors=True)


if __name__ == "__main__":
    for store in ("files", "sqlite"):
        run_case(store)
    public_case()
    sys.exit(summary())
