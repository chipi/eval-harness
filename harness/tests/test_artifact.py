#!/usr/bin/env python3
"""An artifact link per item (RFC-038 section 2, owner 2026-11-20).

    python tests/test_artifact.py

Four layers, offline and at $0:

  the rules      `_artifact.normalise` / `link`: a path inside the project is kept as a relative POSIX path; a `..`, an
                 absolute path outside, a symlink out, a non-string and the project itself are refused with a reason;
                 a stored path is checked again when read (a hand-edited row).
  a run          `evh run` normalises `meta["artifact"]` at write: the row keeps the clean path, or drops it with
                 `artifact_refused` and says so once; the item is not failed. `evh comparison-item` prints the path
                 beside the arm and `--json` carries it (`views[arm].artifact`, `artifacts`); `evh arm-smoke` does too.
  the server     the static handler serves `artifacts/` and every `served_dirs` directory with `nosniff` and
                 `Content-Security-Policy: sandbox`, never the catalog's own pages with it, and answers 404 for a path
                 that reaches outside its prefix through a symlink; `/api/item` of a public server carries no link.
  a release      a hidden dataset's rows drop `artifact`; a hidden run whose artifact lies under data/runs/ (it would be
                 copied) is refused.
"""

import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parents[1]
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/
import _catalog_fixture as fx  # noqa: E402
import _cli  # noqa: E402
import _runstore  # noqa: E402
import _serve  # noqa: E402
from evaluation_harness import _artifact, _common, _format, _visibility  # noqa: E402
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.catalog_adapter import HarnessAdapter  # noqa: E402
from evaluation_harness.model import runs as R  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-artifact-"))
outside = Path(tempfile.mkdtemp(prefix="evh-artifact-out-"))
dest = Path(tempfile.mkdtemp(prefix="evh-artifact-copy-"))
(outside / "secret.txt").write_text("not for the browser\n")
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-artifact", PROJ=str(proj))
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_ACTOR"):
    env.pop(k, None)


def evh(*args):
    return _cli.run(proj, env, *args, timeout=300)


ADAPTER = """
import os
from pathlib import Path

from evaluation_harness.adapter import Result, score  # noqa: F401


class Failed(ValueError):
    meta = {"artifact": "artifacts/h1/failed"}


def call_system(text, params):
    proj = Path(os.environ["PROJ"])
    meta = {}
    if params.get("fail") and params["fail"] in text.lower():
        (proj / "artifacts" / "h1" / "failed").mkdir(parents=True, exist_ok=True)
        raise Failed("400: this input is refused")
    if "artifact" in params:
        value = params["artifact"]
        meta["artifact"] = value.replace("{proj}", str(proj)) if isinstance(value, str) else value
    if params.get("make"):
        d = proj / params["make"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "result.txt").write_text("ok\\n")
    return Result(output=text[:80], cost_usd=0.0, meta=meta)
"""

SYSTEMS = {
    "dir_v1": "{artifact: artifacts/h1/trial_a, make: artifacts/h1/trial_a}",
    "abs_v1": "{artifact: '{proj}/artifacts/h1/trial_b', make: artifacts/h1/trial_b}",
    "unclean_v1": "{artifact: 'artifacts/h1/../h1/trial_a', make: artifacts/h1/trial_a}",
    "up_v1": "{artifact: ../outside}",
    "etc_v1": "{artifact: /etc}",
    "link_v1": "{artifact: artifacts/link}",
    "num_v1": "{artifact: 123}",
    "report_v1": "{artifact: reports/x, make: reports/x}",
    "gone_v1": "{artifact: artifacts/none}",
    "none_v1": "{}",
    "fail_v1": "{fail: invoice}",
}


def meta_of(rid):
    with _runstore._InProject(proj):
        return [(r.get("_meta") or {}, r) for r in _runstore.rows(R.first_score(rid))]


def value_of(r, name):
    return (json.loads(r.stdout).get("result") or {}).get("values", {}).get(name)


try:
    # --- the rules ---------------------------------------------------------------------------------------------
    root = Path(tempfile.mkdtemp(prefix="evh-artifact-rules-"))
    (root / "artifacts" / "d").mkdir(parents=True)
    (root / "artifacts" / "f.txt").write_text("x")
    (root / "artifacts" / "out").symlink_to(outside)
    (root / "artifacts" / "in").symlink_to(root / "artifacts" / "d")
    n = lambda v: _artifact.normalise(v, root)  # noqa: E731
    check(
        "rules: a relative path inside is kept as it is",
        n("artifacts/d") == ("artifacts/d", None),
        n("artifacts/d"),
    )
    check(
        "rules: an absolute path inside becomes relative",
        n(str(root / "artifacts" / "f.txt")) == ("artifacts/f.txt", None),
    )
    check(
        "rules: a `..` that stays inside is cleaned",
        n("artifacts/x/../d") == ("artifacts/d", None),
        n("artifacts/x/../d"),
    )
    check(
        "rules: a symlink that stays inside is followed: the stored path is where it lands",
        n("artifacts/in") == ("artifacts/d", None),
        n("artifacts/in"),
    )
    for what, value in (
        ("a `..` out", "../x"),
        ("an absolute path outside", "/etc"),
        ("a symlink out", "artifacts/out"),
        ("a symlink out and a file beyond it", "artifacts/out/secret.txt"),
    ):
        norm = n(value)
        check(f"rules: {what} is refused, outside the project", norm == (None, "outside the project"), norm)
    check(
        "rules: the project itself is refused",
        n(".")[0] is None and n(str(root))[0] is None,
        (n("."), n(str(root))),
    )
    odd: tuple[tuple[str, Any], ...] = (
        ("a number", 7),
        ("an empty string", ""),
        ("a list", ["a"]),
        ("None", None),
    )
    for what, value in odd:
        check(
            f"rules: {what} is refused, not a path",
            n(value)[0] is None and "path" in (n(value)[1] or ""),
            n(value),
        )

    served = ("/data/", "/docs/", "/artifacts/")
    lk = lambda v: _artifact.link(v, served, root)  # noqa: E731
    check(
        "link: a directory under a served prefix has a url with a trailing slash",
        lk("artifacts/d") == {"path": "artifacts/d", "kind": "dir", "url": "/artifacts/d/"},
        lk("artifacts/d"),
    )
    check(
        "link: a file",
        lk("artifacts/f.txt") == {"path": "artifacts/f.txt", "kind": "file", "url": "/artifacts/f.txt"},
        lk("artifacts/f.txt"),
    )
    check(
        "link: a missing path is `missing`, and keeps its url",
        lk("artifacts/none") == {"path": "artifacts/none", "kind": "missing", "url": "/artifacts/none"},
        lk("artifacts/none"),
    )
    (root / "reports").mkdir()
    (root / "reports" / "r.html").write_text("<p>")
    check(
        "link: a path under no served prefix has no url",
        lk("reports/r.html") == {"path": "reports/r.html", "kind": "file"},
        lk("reports/r.html"),
    )
    check(
        "link: a stored path with a space or markup is percent-encoded in its url, never raw",
        (_artifact.link("artifacts/a b<x>", served, root) or {}).get("url") == "/artifacts/a%20b%3Cx%3E",
        _artifact.link("artifacts/a b<x>", served, root),
    )
    stored: tuple[tuple[str, Any], ...] = (
        ("a `..`", "../x"),
        ("an absolute path outside", "/etc/passwd"),
        ("a symlink out", "artifacts/out"),
        ("a number", 5),
    )
    for what, value in stored:
        shown = lk(value)
        check(
            f"link: a stored value that is {what} is `refused`: no url, whatever was stored",
            shown is not None and shown["kind"] == "refused" and "url" not in shown,
            shown,
        )
    check("link: nothing stored, no link", lk(None) is None, lk(None))
    prefixes = _artifact.served_prefixes(root / "data", (root / "docs", root.parent / "elsewhere"), root)
    check(
        "served prefixes: artifacts/, the data tree and the served_dirs inside the project, never one outside",
        prefixes == ("/artifacts/", "/data/", "/docs/"),
        prefixes,
    )
    shutil.rmtree(root, ignore_errors=True)

    # --- a run: write-time normalisation, comparison-item, the smoke ----------------------------------------------
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
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
            "owner",
        )
    )
    r = r if r.returncode else evh(
        "reference-promote", "--dataset-id", "tickets_v1", "--labels", "g", "--tier", "gold",
        "--reason", "The kit's hand-written summaries decide.", "--by", "owner",
    )  # fmt: skip
    check("setup: the tutorial dataset and its gold", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    (proj / "art.py").write_text(ADAPTER)
    for sid, params in SYSTEMS.items():
        _runstore.write_text(
            proj, f"systems/{sid}.yaml", f"system_id: {sid}\nadapter: art.py\nparams: {params}\n"
        )
    (proj / "artifacts").mkdir()
    (proj / "artifacts" / "link").symlink_to("/etc")

    runs = {
        sid: evh("run", "--system", sid, "--dataset", "tickets_v1", "--run-id", f"r_{sid}") for sid in SYSTEMS
    }
    check(
        "every run finishes (a refused artifact does not fail an item)",
        all(r.returncode == 0 for r in runs.values()),
        {k: r.returncode for k, r in runs.items() if r.returncode},
    )
    for sid, want in (
        ("dir_v1", "artifacts/h1/trial_a"),
        ("abs_v1", "artifacts/h1/trial_b"),
        ("unclean_v1", "artifacts/h1/trial_a"),
        ("report_v1", "reports/x"),
        ("gone_v1", "artifacts/none"),
    ):
        paths = {m.get("artifact") for m, _row in meta_of(f"r_{sid}")}
        check(f"write: {sid} stores the clean relative path {want}", paths == {want}, paths)
    for sid, why in (
        ("up_v1", "outside the project"),
        ("etc_v1", "outside the project"),
        ("link_v1", "outside the project"),
        ("num_v1", "not a path"),
    ):
        got = meta_of(f"r_{sid}")
        out = runs[sid].stdout + runs[sid].stderr
        check(
            f"write: {sid}: no artifact stored, artifact_refused says why, no item failed",
            all(
                "artifact" not in m and why in str(m.get("artifact_refused")) and row.get("failed") == 0.0
                for m, row in got
            ),
            got[:1],
        )
        check(
            f"write: {sid}: the run says so once",
            out.count("artifact dropped") == 1 and why in out,
            out[-400:],
        )
    check(
        "write: an adapter with no artifact stores none and says nothing",
        all("artifact" not in m for m, _ in meta_of("r_none_v1"))
        and "artifact dropped" not in runs["none_v1"].stdout,
    )

    r = evh("comparison-item", "--runs", "dir_v1", "--item", "t01_login")
    check(
        "comparison-item prints the path beside the arm: (run R · artifact artifacts/h1/trial_a)",
        r.returncode == 0 and "artifact artifacts/h1/trial_a)" in r.stdout and "(run r_dir_v1" in r.stdout,
        r.stdout[-500:],
    )
    r = evh("comparison-item", "--runs", "dir_v1", "--item", "t01_login", "--json")
    views = (value_of(r, "item") or {}).get("views") or {}
    art = next((v.get("artifact") for v in views.values()), None)
    check(
        "comparison-item --json: views[arm].artifact carries path, kind and url",
        art == {"path": "artifacts/h1/trial_a", "kind": "dir", "url": "/artifacts/h1/trial_a/"},
        art,
    )
    got = value_of(r, "artifacts")
    check(
        "comparison-item --json: `artifacts` lists {arm, path, kind, url} for the Workbench",
        isinstance(got, list)
        and len(got) == 1
        and got[0].get("path") == "artifacts/h1/trial_a"
        and got[0].get("arm"),
        got,
    )
    r = evh("comparison-item", "--runs", "report_v1", "--item", "t01_login", "--json")
    art = next((v.get("artifact") for v in ((value_of(r, "item") or {}).get("views") or {}).values()), None)
    check("a path under no served prefix: its kind, no url", art == {"path": "reports/x", "kind": "dir"}, art)
    r = evh("comparison-item", "--runs", "gone_v1", "--item", "t01_login", "--json")
    art = next((v.get("artifact") for v in ((value_of(r, "item") or {}).get("views") or {}).values()), None)
    check("a path that is not there: kind missing", art is not None and art["kind"] == "missing", art)
    r = evh("comparison-item", "--runs", "none_v1", "--item", "t01_login", "--json")
    art = list(((value_of(r, "item") or {}).get("views") or {}).values())
    check(
        "an arm with no artifact: no key, and `artifacts` is empty",
        art and "artifact" not in art[0] and value_of(r, "artifacts") == [],
        (art, value_of(r, "artifacts")),
    )

    r = evh("comparison-item", "--runs", "fail_v1", "--item", "t02_invoice", "--json")
    view: dict[str, Any] = next(iter(((value_of(r, "item") or {}).get("views") or {}).values()), {})
    check(
        "a failed item has no output but keeps the artifact its exception named: the view says it failed and links the directory",
        view.get("kind") == "none"
        and "failed" in view.get("note", "")
        and (view.get("artifact") or {}).get("path") == "artifacts/h1/failed",
        view,
    )

    # a row edited by hand: the read checks again
    with _runstore._InProject(proj):
        sd = R.first_score("r_dir_v1")
        assert sd is not None
        rows = _runstore.rows(sd)
        for x in rows:
            x["_meta"] = {**(x.get("_meta") or {}), "artifact": "../../etc"}
        _runstore.put_rows(sd, rows)
    r = evh("comparison-item", "--runs", "dir_v1", "--item", "t01_login", "--json")
    art = next((v.get("artifact") for v in ((value_of(r, "item") or {}).get("views") or {}).values()), None)
    check(
        "a hand-edited row with `../../etc`: the read refuses it, no url",
        art is not None and art["kind"] == "refused" and "url" not in art,
        art,
    )
    check(
        "... and the printed line says refused, not the path as a link",
        "refused" in evh("comparison-item", "--runs", "dir_v1", "--item", "t01_login").stdout,
    )

    r = evh("arm-smoke", "--system", "dir_v1", "--dataset", "tickets_v1", "--items", "1", "--json")
    items = (json.loads(r.stdout).get("result", {}).get("values", {}) or {}).get("items") or []
    check(
        "arm-smoke --json: each item carries its artifact (path, kind, url)",
        items
        and items[0].get("artifact")
        == {"path": "artifacts/h1/trial_a", "kind": "dir", "url": "/artifacts/h1/trial_a/"},
        items[:1],
    )
    r = evh("arm-smoke", "--system", "dir_v1", "--dataset", "tickets_v1", "--items", "1")
    check(
        "arm-smoke prints the artifact's path", "artifact artifacts/h1/trial_a" in r.stdout, r.stdout[-400:]
    )
    r = evh("arm-smoke", "--system", "up_v1", "--dataset", "tickets_v1", "--items", "1", "--json")
    items = (json.loads(r.stdout).get("result", {}).get("values", {}) or {}).get("items") or []
    check(
        "arm-smoke: an artifact outside the project is dropped, as a run drops it",
        items and "artifact" not in items[0],
        items[:1],
    )
    r = evh("validate")
    check(
        "validate tolerates an artifacts/ directory (with a symlink out) at the project root",
        r.returncode in (0, 6)
        and "artifacts" not in (r.stdout + r.stderr).lower().replace("artifact_refused", ""),
        (r.stdout + r.stderr)[-400:],
    )

    # --- a live `catalog-serve`, local and --public ----------------------------------------------------------------------
    r = evh("catalog")
    arm_id = "runs/tickets_v1/abs_v1"

    def api_item(port: int, host: str) -> tuple[int, str]:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        c.request("GET", f"/api/item?arms={arm_id}&item=t01_login", headers={"Host": host})
        resp = c.getresponse()
        body = resp.read().decode(errors="replace")
        c.close()
        return resp.status, body

    srv_p, srv_port, _lines = _serve.start(proj, env)
    try:
        st, body = api_item(srv_port, f"127.0.0.1:{srv_port}")
    finally:
        _serve.stop(srv_p, proj)
    check(
        "a live local server's /api/item carries the artifact (the control for the public one)",
        st == 200 and "artifacts/h1/trial_b" in body,
        (st, body[:200]),
    )
    srv_p, srv_port, _lines = _serve.start(proj, env, "--public", "example.org", "--publish", "outputs")
    try:
        st, body = api_item(srv_port, "example.org")
    finally:
        _serve.stop(srv_p, proj)
    check(
        "a live `catalog-serve --public … --publish outputs` serves the output and no artifact: no path, no url, no key",
        st == 200 and '"kind": "text"' in body.replace('":"', '": "') and "artifact" not in body,
        (st, body[:300]),
    )

    # --- the item view and the public server, in this process --------------------------------------------------------
    tmp = Path(tempfile.mkdtemp(prefix="evh-artifact-srv-"))
    data = tmp / "data"
    (tmp / "artifacts" / "h1" / "trial_a" / "sub").mkdir(parents=True)
    (tmp / "artifacts" / "h1" / "trial_a" / "sub" / "notes.txt").write_text("n\n")
    (tmp / "artifacts" / "h1" / "trial_a" / "result.txt").write_text("ok\n")
    (tmp / "artifacts" / "h1" / "trial_a" / "index.html").write_text("<script>fetch('/api/v1/jobs')</script>")
    (tmp / "artifacts" / "h1" / "trial_a" / "inside.txt").symlink_to(
        tmp / "artifacts" / "h1" / "trial_a" / "result.txt"
    )
    (tmp / "artifacts" / "h1" / "trial_a" / "escape").symlink_to(outside)
    (tmp / "artifacts" / "h1" / "leak.txt").symlink_to(outside / "secret.txt")
    (tmp / "docs").mkdir()
    (tmp / "docs" / "report.html").write_text("<p>report</p>")
    (tmp / "docs" / "leak").symlink_to(outside)
    (tmp / ".build" / "catalog").mkdir(parents=True)
    (tmp / ".build" / "catalog" / "index.html").write_text("<script src=x.js></script>")
    rows = [
        {"item_id": "i00", "acc": 0.5, "_meta": {"artifact": "artifacts/h1/trial_a"}},
        {"item_id": "i01", "acc": 0.5, "_meta": {"artifact": "artifacts/h1/gone"}},
    ]
    fx.put(data, "a_1", {"run_id": "a_1", "dataset_id": "ds1", "system_id": "arm_a", "primary_metric": "acc",
                         "metric_kinds": {"acc": "quality"}, "fingerprint": {"data": {"reference_id": "gold/ds1"}}},
           "\n".join(json.dumps(x) for x in rows) + "\n", outputs={"i00": "an output", "i01": "another"})  # fmt: skip
    # A public server serves a dataset's text only when its record can be read; this fixture's data is not the project's.
    (data / "datasets").mkdir()
    (data / "datasets" / "ds1.json").write_text(json.dumps({"dataset_id": "ds1", "items": []}))
    real_record_file = _visibility.record_file
    _visibility.record_file = lambda ds, data_dir=None: data / "datasets" / f"{ds}.json"  # type: ignore[assignment]
    old_root = _common.ROOT
    _common.ROOT = tmp
    cs.ROOT = tmp
    try:
        A = HarnessAdapter(data)
        A.served_dirs = (tmp / "docs",)  # type: ignore[attr-defined]  # the optional attribute an adapter may set
        cs.set_adapter(A)
        arm = sorted(A.arms())[0]
        gone = A.item_view(arm, "i01")["artifact"]
        check(
            "a missing artifact in the project's own data says nothing of a deployment",
            gone["kind"] == "missing" and "why" not in gone,
            gone,
        )
        (data / "release.json").write_text('{"released": true}\n')
        gone = A.item_view(arm, "i01")["artifact"]
        check(
            "in a release's copy (data/release.json, which copy_data writes) a missing artifact is 'not in this deployment'",
            gone["kind"] == "missing" and gone.get("why") == "not in this deployment",
            gone,
        )
        check(
            "... and an artifact the copy does hold is still linked",
            A.item_view(arm, "i00")["artifact"]["kind"] == "dir",
        )
        (data / "release.json").unlink()
        v = A.item_view(arm, "i00")
        check(
            "item view: `artifact` is {path, kind, url}, and info carries the path as text",
            v.get("artifact")
            == {"path": "artifacts/h1/trial_a", "kind": "dir", "url": "/artifacts/h1/trial_a/"}
            and v["info"].get("artifact") == "artifacts/h1/trial_a",
            (v.get("artifact"), v.get("info")),
        )
        local = cs.item({"arms": [arm], "item": ["i00"]})
        check(
            "the inspector's item route (local) carries the link",
            (local["views"][arm].get("artifact") or {}).get("url") == "/artifacts/h1/trial_a/",
            local["views"][arm].get("artifact"),
        )
        saved = dict(cs.LIMITS)
        cs.LIMITS["hosts"], cs.LIMITS["publish"] = ("example.org",), ("outputs",)
        try:
            got = cs.item({"arms": [arm], "item": ["i00"]})
        finally:
            cs.LIMITS.clear()
            cs.LIMITS.update(saved)
        pub = got["views"][arm]
        check(
            "a public server that publishes outputs serves the output and no artifact, in the view or in info",
            pub.get("kind") == "text" and "artifact" not in pub and "artifact" not in (pub.get("info") or {}),
            pub,
        )

        out = tmp / ".build" / "catalog"
        prefixes = cs.served(out, data, (tmp / "docs",))
        check(
            "served: artifacts/ is a served prefix by default, once",
            prefixes == ("/.build/catalog/", "/data/", "/docs/", "/artifacts/"),
            prefixes,
        )
        check(
            "served: named twice (served_dirs has it), still once",
            cs.served(out, data, (tmp / "artifacts",)).count("/artifacts/") == 1,
            cs.served(out, data, (tmp / "artifacts",)),
        )
        cs.Handler.prefixes = prefixes
        srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(cs.Handler, directory=str(tmp)))
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        def get(path):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            c.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
            r = c.getresponse()
            body = r.read().decode(errors="replace")
            hdr = {k.lower(): v for k, v in r.getheaders()}
            c.close()
            return r.status, hdr, body

        def hardened(h):
            return (
                h.get("x-content-type-options") == "nosniff" and h.get("content-security-policy") == "sandbox"
            )

        st, h, body = get("/artifacts/h1/trial_a/sub/")
        check(
            "http: a served directory answers a listing, with nosniff and sandbox",
            st == 200 and "notes.txt" in body and hardened(h),
            (st, h, body[:200]),
        )
        st, h, body = get("/artifacts/h1/trial_a/result.txt")
        check(
            "http: a file in it, with nosniff and sandbox",
            st == 200 and body == "ok\n" and hardened(h),
            (st, h),
        )
        st, h, body = get("/artifacts/h1/trial_a/index.html")
        check(
            "http: an HTML file in it is sandboxed (it cannot call the write API from this origin)",
            st == 200 and hardened(h),
            (st, h),
        )
        st, h, body = get("/docs/report.html")
        check(
            "http: a served_dirs directory is hardened too, not only the data tree",
            st == 200 and hardened(h),
            (st, h),
        )
        st, h, body = get("/.build/catalog/index.html")
        check(
            "http: the catalog's own pages are not sandboxed (their scripts must run)",
            st == 200 and "content-security-policy" not in h,
            (st, h),
        )
        st, h, body = get("/data/runs/a_1/run.json")
        check("http: the data tree stays hardened", st == 200 and hardened(h), (st, h))
        check(
            "http: a symlink inside the prefix to a file inside it is served",
            get("/artifacts/h1/trial_a/inside.txt")[0] == 200,
        )
        st, _, body = get("/artifacts/h1/leak.txt")
        check(
            "http: a symlinked file that leads outside the prefix is 404, its content not served",
            st == 404 and "not for the browser" not in body,
            (st, body[:80]),
        )
        st, _, body = get("/artifacts/h1/trial_a/escape/secret.txt")
        check(
            "http: a file through a symlinked directory outside is 404",
            st == 404 and "not for the browser" not in body,
            (st, body[:80]),
        )
        check(
            "http: the symlinked directory's own listing is 404",
            get("/artifacts/h1/trial_a/escape/")[0] == 404 and get("/artifacts/h1/trial_a/escape")[0] == 404,
        )
        check("http: the same in a served_dirs directory", get("/docs/leak/secret.txt")[0] == 404)
        check(
            "http: nothing else under the project is served",
            get("/art.py")[0] == 404 and get("/artifacts/../data/runs/a_1/run.json")[0] == 404,
        )
        srv.shutdown()
    finally:
        del _common.ROOT  # the project's own again, resolved lazily as before
        _visibility.record_file = real_record_file
        cs.ROOT = old_root
        cs.Handler.prefixes = ()
        shutil.rmtree(tmp, ignore_errors=True)

    # --- a release ---------------------------------------------------------------------------------------------------
    rel = Path(tempfile.mkdtemp(prefix="evh-artifact-rel-"))
    renv = dict(os.environ, EVAL_HOME=str(rel), EVAL_BUILD_REF="test-artifact-release")
    for k in ("EVAL_DATA_DIR", "EVH_ACTOR"):
        renv.pop(k, None)
    subprocess.run(["git", "init", "-q"], cwd=rel, check=True)
    (rel / "data").mkdir()
    _runstore.write_text(rel, _format.NAME, f"format: {_format.FORMAT}\n")
    for ds, extra in (("held_h", {"text": "hidden"}), ("open_v1", {})):
        _runstore.write_text(
            rel, f"datasets/{ds}.json", json.dumps({"dataset_id": ds, "version": "", "items": [], **extra})
        )
    rec = {"dataset_id": "held_h", "system_id": "arm_h", "primary_metric": "acc", "metric_kinds": {"acc": "quality"},
           "fingerprint": {"data": {"reference_id": "gold/held_h"}}}  # fmt: skip
    with _runstore._InProject(rel):
        for rid, art in (("h_ok", "artifacts/t1"), ("h_bad", "data/runs/h_bad/trial")):
            fx.put(rel / "data", rid, {**rec, "run_id": rid},
                   json.dumps({"item_id": "i00", "acc": 1.0, "_meta": {"artifact": art, "provider": "p"}}) + "\n", outputs={"i00": "secret text"})  # fmt: skip
        from evaluation_harness import _release

        bad_all = _release.plan_problems(rel / "data")
    check(
        "release: a hidden run whose artifact lies under data/runs/ is refused (it would be copied), and only that one",
        any("h_bad" in b and "artifact" in b for b in bad_all) and not any("h_ok" in b for b in bad_all),
        bad_all,
    )
    _runstore.rmtree(rel, "runs/h_bad")
    copy = dest / "data"
    r = subprocess.run(
        [sys.executable, str(HARNESS / "scripts" / "_release.py"), "copy-data", str(rel / "data"), str(copy), "--store", "files"],
        cwd=rel, env=renv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    ok_rows = [
        json.loads(x)
        for p in (copy / "runs" / "h_ok").rglob("predictions.jsonl")
        for x in p.read_text().splitlines()
    ]
    check(
        "release: copy_data marks its copy (data/release.json), which is what 'not in this deployment' reads",
        (copy / "release.json").is_file(),
        sorted(x.name for x in copy.iterdir()),
    )
    check(
        "release: a hidden dataset's copied rows keep the call's facts and drop the artifact",
        r.returncode == 0
        and ok_rows
        and all(
            "artifact" not in (x.get("_meta") or {}) and (x.get("_meta") or {}).get("provider") == "p"
            for x in ok_rows
        ),
        (r.stdout + r.stderr)[-300:] + str(ok_rows[:1]),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(outside, ignore_errors=True)
    shutil.rmtree(dest, ignore_errors=True)
sys.exit(summary())
