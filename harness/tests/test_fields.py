#!/usr/bin/env python3
"""Assertions for item fields and URL items (ADR-0003): create, update, materialize, V15.

    python tests/test_fields.py

In a throwaway project ($0; the URL items come from a server on 127.0.0.1): values are read
from a CSV, typed by the project's field set, and refused when undeclared, mistyped, outside a
choice, for an unknown item, or missing where required; correcting a value changes neither the
run fingerprint's data identity nor created_at, and moves fields_sha256; a manifest pins URL
items by their hash, or fetches and pins them; materialize fetches, caches, and refuses bytes
that are not the pinned ones; V15 fails a hand edit, an undeclared field and a missing field set.
"""

import functools
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
sys.path.insert(0, str(HERE))
from _check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-fields-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-fields")
env.pop("EVAL_DATA_DIR", None)
env.pop("EVAL_RUNS_DIR", None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


def v15():
    r = evh("validate")
    return next((ln for ln in r.stdout.splitlines() if "V15" in ln), ""), out(r)


FIELDSET = """fieldset_id: tickets
description: what a support ticket is about
fields:
  - {name: product, type: choice, values: [billing, login, export], label: Product, public: true}
  - {name: priority, type: integer, label: Priority, required: true}
  - {name: opened, type: date}
  - {name: wait, type: duration, label: Time to first reply}
  - {name: escalated, type: boolean}
  - {name: link, type: url}
  - {name: note, type: text}
"""

srv = None
try:
    import _fields

    # ── the types ──────────────────────────────────────────────────────────────────────
    F = {f["name"]: f for f in __import__("yaml").safe_load(FIELDSET)["fields"]}
    check("parse: a duration as h:mm:ss is seconds", _fields.parse(F["wait"], "1:02:03") == 3723)
    check(
        "parse: a duration as m:ss and as seconds",
        _fields.parse(F["wait"], "2:30") == 150 and _fields.parse(F["wait"], "90") == 90,
    )
    check(
        "parse: yes/no and 1/0 are booleans",
        _fields.parse(F["escalated"], "yes") is True and _fields.parse(F["escalated"], "0") is False,
    )
    for name, raw in (
        ("priority", "1.5"),
        ("priority", "high"),
        ("opened", "22/10/2026"),
        ("product", "shipping"),
        ("link", "ftp://x"),
        ("escalated", "maybe"),
        ("wait", "-3"),
    ):
        try:
            _fields.parse(F[name], raw)
            check(f"parse: {name} = {raw!r} is refused", False, "accepted")
        except ValueError:
            check(f"parse: {name} = {raw!r} is refused", True)
    check(
        "matches: a number range, either end open",
        _fields.matches(F["wait"], 150, "100..")
        and not _fields.matches(F["wait"], 150, "..100")
        and _fields.matches(F["wait"], 150, "100..200"),
    )

    # ── create with fields ────────────────────────────────────────────────────────────
    data = proj / "data"
    src = proj / "tickets"
    src.mkdir(parents=True)
    for i in ("t1", "t2", "t3"):
        (src / f"{i}.txt").write_text(f"Ticket {i}. The user cannot log in. Support replied.\n")
    (data / "fields").mkdir(parents=True)
    (data / "fields" / "tickets.yaml").write_text(FIELDSET)
    good = (
        "item_id,product,priority,opened,wait,escalated\n"
        "t1,login,1,2026-10-01,1:00:00,no\n"
        "t2,billing,2,2026-10-02,300,yes\n"
        "t3,login,3,,,\n"
    )
    (proj / "fields.csv").write_text(good)

    def bad_csv(body, label, expect):
        (proj / "bad.csv").write_text(body)
        r = evh(
            "dataset-create",
            "--dataset-id",
            "bad_v1",
            "--source-dir",
            "tickets",
            "--fieldset",
            "tickets",
            "--fields",
            "bad.csv",
        )
        check(
            f"create: refused — {label}",
            r.returncode != 0 and expect in out(r) and not (data / "datasets" / "bad_v1.json").exists(),
            out(r)[-300:],
        )

    bad_csv(
        "item_id,prodcut,priority\nt1,login,1\nt2,login,2\nt3,login,3\n", "an undeclared column", "prodcut"
    )
    bad_csv(
        "item_id,product,priority\nt1,shipping,1\nt2,login,2\nt3,login,3\n",
        "a value outside the choices",
        "shipping",
    )
    bad_csv("item_id,product,priority\nt1,login,high\nt2,login,2\nt3,login,3\n", "a mistyped value", "high")
    bad_csv(
        "item_id,product,priority\nt1,login,1\nt2,login,2\nt9,login,3\n",
        "an item that is not in the dataset",
        "t9",
    )
    bad_csv(
        "item_id,product,priority\nt1,login,1\nt2,login,2\nt3,login,\n",
        "a required field with no value",
        "priority",
    )
    r = evh("dataset-create", "--dataset-id", "nofs_v1", "--source-dir", "tickets", "--fields", "fields.csv")
    check(
        "create: values without --fieldset are refused",
        r.returncode != 0 and "--fieldset" in out(r),
        out(r)[-200:],
    )
    r = evh("dataset-create", "--dataset-id", "nofs_v1", "--source-dir", "tickets", "--fieldset", "nope")
    check("create: a field set that does not exist is named", r.returncode != 0 and "nope.yaml" in out(r))

    r = evh(
        "dataset-create",
        "--dataset-id",
        "tk_v1",
        "--source-dir",
        "tickets",
        "--fieldset",
        "tickets",
        "--fields",
        "fields.csv",
    )
    check("create: a dataset with typed fields", r.returncode == 0, out(r)[-300:])
    ds = json.loads((data / "datasets" / "tk_v1.json").read_text())
    by = {it["item_id"]: it for it in ds["items"]}
    check(
        "create: values are typed, empty cells absent",
        by["t1"]["fields"]
        == {"product": "login", "priority": 1, "opened": "2026-10-01", "wait": 3600, "escalated": False}
        and by["t3"]["fields"] == {"product": "login", "priority": 3},
        by,
    )
    check(
        "create: the dataset names its field set and the fields' hash",
        ds.get("fieldset") == "tickets" and ds.get("fields_sha256") == _fields.digest(ds["items"]),
    )
    line, _ = v15()
    check("V15: a dataset with declared, typed fields passes", line.strip().startswith("ok"), line)

    # ── fields are not the identity ───────────────────────────────────────────────────
    from _fingerprint import items_digest

    before_id, before_fields, before_at = items_digest(ds), ds["fields_sha256"], ds["created_at"]
    (proj / "fix.csv").write_text("item_id,product,priority\nt3,export,3\n")
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--update-fields", "--fields", "fix.csv")
    ds2 = json.loads((data / "datasets" / "tk_v1.json").read_text())
    check(
        "update-fields: replaces the values",
        r.returncode == 0
        and {i["item_id"]: i.get("fields") for i in ds2["items"]}["t3"]
        == {"product": "export", "priority": 3},
        out(r)[-300:],
    )
    check(
        "update-fields: the data identity a run fingerprint records is unchanged",
        items_digest(ds2) == before_id,
    )
    check(
        "update-fields: created_at kept, fields_sha256 moved",
        ds2["created_at"] == before_at and ds2["fields_sha256"] != before_fields,
    )
    check(
        "update-fields: values not in the file are kept (t1, and t3's other fields)",
        r.returncode == 0
        and ds2["fields_sha256"] != before_fields
        and {i["item_id"]: i.get("fields") for i in ds2["items"]}["t1"] == by["t1"]["fields"],
        out(r)[-200:],
    )

    (proj / "clear.csv").write_text("item_id,opened,priority\nt1,,1\n")
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--update-fields", "--fields", "clear.csv")
    ds3 = json.loads((data / "datasets" / "tk_v1.json").read_text())
    t1 = {i["item_id"]: i.get("fields") for i in ds3["items"]}["t1"]
    check(
        "update-fields: an empty cell clears that value; the item's other values stay",
        r.returncode == 0 and "opened" not in t1 and t1.get("wait") == 3600,
        (out(r)[-200:], t1),
    )
    (proj / "clear_req.csv").write_text("item_id,priority\nt1,\n")
    r = evh("dataset-create", "--dataset-id", "tk_v1", "--update-fields", "--fields", "clear_req.csv")
    check(
        "update-fields: clearing a required field is refused",
        r.returncode != 0 and "priority" in out(r),
        out(r)[-200:],
    )

    # ── V15 ───────────────────────────────────────────────────────────────────────────
    path = data / "datasets" / "tk_v1.json"
    keep = path.read_text()
    edited = json.loads(keep)
    edited["items"][0]["fields"]["priority"] = 9
    path.write_text(json.dumps(edited))
    line, o = v15()
    check("V15: a value edited by hand fails (fields_sha256)", "FAIL" in line and "fields_sha256" in o, line)
    edited = json.loads(keep)
    edited["items"][0]["fields"]["colour"] = "red"
    edited["fields_sha256"] = _fields.digest(edited["items"])
    path.write_text(json.dumps(edited))
    line, o = v15()
    check("V15: an undeclared field fails", "FAIL" in line and "colour" in o, line)
    edited = json.loads(keep)
    edited["fieldset"] = "gone"
    path.write_text(json.dumps(edited))
    line, o = v15()
    check("V15: a field set that does not exist fails", "FAIL" in line and "does not exist" in o, line)
    edited = json.loads(keep)
    del edited["fieldset"], edited["fields_sha256"]
    path.write_text(json.dumps(edited))
    line, o = v15()
    check("V15: fields with no field set fail", "FAIL" in line and "names no fieldset" in o, line)
    path.write_text(keep)

    # ── URL items ─────────────────────────────────────────────────────────────────────
    served = proj / "served"
    served.mkdir()
    (served / "a.mp3").write_bytes(b"ID3 audio a")
    (served / "b.mp3").write_bytes(b"ID3 audio b")
    flaky = {"left": 1}

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/private.mp3":  # refused without the project's header
                if self.headers.get("Authorization") != "Bearer t0k":
                    self.send_error(403)
                    return
                body = b"ID3 private"
            elif self.path == "/away.mp3":  # a redirect to another host name
                self.send_response(302)
                self.send_header("Location", f"http://localhost:{self.server.server_address[1]}/landed.mp3")
                self.end_headers()
                return
            elif self.path == "/landed.mp3":  # records what the other host was sent
                flaky["landed_auth"] = self.headers.get("Authorization")
                body = b"ID3 landed"
            elif self.path == "/flaky.mp3":  # one 503, then the file
                if flaky["left"]:
                    flaky["left"] -= 1
                    self.send_error(503)
                    return
                body = b"ID3 flaky"
            else:
                return super().do_GET()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(served)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    import hashlib

    sha_a = hashlib.sha256(b"ID3 audio a").hexdigest()
    (proj / "manifest.csv").write_text(
        "item_id,source_url,source_sha256,product,priority\n"
        f"ep_a,{base}/a.mp3,{sha_a},login,1\n"
        f"ep_b,{base}/b.mp3,,billing,2\n"
    )
    r = evh(
        "dataset-create", "--dataset-id", "urls_v1", "--manifest", "manifest.csv", "--fieldset", "tickets"
    )
    dsu = json.loads((data / "datasets" / "urls_v1.json").read_text()) if r.returncode == 0 else {}
    u = {i["item_id"]: i for i in dsu.get("items", [])}
    check(
        "manifest: URL items, one pinned by its hash, one fetched and pinned now",
        r.returncode == 0
        and "pinned 1 item(s) now" in out(r)
        and u["ep_b"]["source_sha256"] == hashlib.sha256(b"ID3 audio b").hexdigest()
        and u["ep_a"]["source_path"] == "ep_a.mp3"
        and u["ep_a"]["fields"]["product"] == "login",
        out(r)[-300:],
    )
    r = evh("dataset-materialize", "--dataset-id", "urls_v1")
    mat = data / "materialized" / "urls_v1"
    check(
        "materialize: fetches each URL item and checks its hash",
        r.returncode == 0 and (mat / "ep_a.mp3").read_bytes() == b"ID3 audio a",
        out(r)[-300:],
    )
    check("materialize: the bytes are cached by their hash", (proj / ".cache" / "items" / sha_a).is_file())
    line, o = v15()
    r_val = evh("validate")
    check(
        "validate: V4 checks the URL items' materialized copy",
        "V4 materialized copies match their frozen hashes" in r_val.stdout and r_val.returncode == 0,
        out(r_val)[-300:],
    )
    (served / "b.mp3").write_bytes(b"ID3 audio b, re-encoded")
    for p in (proj / ".cache" / "items").iterdir():
        p.unlink()
    r = evh("dataset-materialize", "--dataset-id", "urls_v1", "--force")
    check(
        "materialize: a changed file at the URL is refused, not cached",
        r.returncode != 0
        and "not the pinned" in out(r)
        and not (proj / ".cache" / "items" / hashlib.sha256(b"ID3 audio b, re-encoded").hexdigest()).exists(),
        out(r)[-300:],
    )
    (proj / "auth_manifest.csv").write_text(f"item_id,source_url\nep_p,{base}/private.mp3\n")
    r = evh("dataset-create", "--dataset-id", "private_v1", "--manifest", "auth_manifest.csv")
    check(
        "fetch: a URL that needs a header is refused without it",
        r.returncode != 0 and "403" in out(r),
        out(r)[-200:],
    )
    env["EVAL_FETCH_HEADERS"] = json.dumps({"127.0.0.1": {"Authorization": "Bearer t0k"}})
    r = evh("dataset-create", "--dataset-id", "private_v1", "--manifest", "auth_manifest.csv")
    stored = (data / "datasets" / "private_v1.json").read_text() if r.returncode == 0 else ""
    check(
        "fetch: EVAL_FETCH_HEADERS sends the project's header to its host",
        r.returncode == 0 and hashlib.sha256(b"ID3 private").hexdigest() in stored,
        out(r)[-200:],
    )
    check("fetch: the header is never written into the dataset", stored and "t0k" not in stored)
    (proj / "away_manifest.csv").write_text(f"item_id,source_url\nep_r,{base}/away.mp3\n")
    r = evh("dataset-create", "--dataset-id", "away_v1", "--manifest", "away_manifest.csv")
    check(
        "fetch: a redirect to another host does not carry the header",
        r.returncode == 0 and "landed_auth" in flaky and flaky["landed_auth"] is None,
        (out(r)[-200:], flaky.get("landed_auth")),
    )
    env.pop("EVAL_FETCH_HEADERS")
    env["EVAL_RETRY_MAX_DELAY"] = "0"
    (proj / "flaky_manifest.csv").write_text(f"item_id,source_url\nep_f,{base}/flaky.mp3\n")
    r = evh("dataset-create", "--dataset-id", "flaky_v1", "--manifest", "flaky_manifest.csv")
    check(
        "fetch: a transient 503 is retried, then the item is pinned",
        r.returncode == 0 and "retry" in out(r) and flaky["left"] == 0,
        out(r)[-300:],
    )
    env.pop("EVAL_RETRY_MAX_DELAY")
    (proj / "bad_manifest.csv").write_text(f"item_id,source_url\nep_x,{base}/missing.mp3\n")
    r = evh("dataset-create", "--dataset-id", "bad_urls_v1", "--manifest", "bad_manifest.csv")
    check(
        "manifest: a URL that cannot be read is refused",
        r.returncode != 0 and "missing.mp3" in out(r),
        out(r)[-200:],
    )
    secret = proj / "local_secret.txt"
    secret.write_bytes(b"not for a dataset")
    (proj / "file_manifest.csv").write_text(f"item_id,source_url\nep_l,{secret.as_uri()}\n")
    r = evh("dataset-create", "--dataset-id", "file_urls_v1", "--manifest", "file_manifest.csv")
    check(
        "manifest: a file:// URL is refused before anything is read",
        r.returncode != 0
        and "http" in out(r)
        and not (proj / ".cache" / "items" / hashlib.sha256(b"not for a dataset").hexdigest()).exists(),
        out(r)[-200:],
    )

    # ── the catalog summary ───────────────────────────────────────────────────────────
    import yaml

    fs = yaml.safe_load(FIELDSET)
    s = {r_["name"]: r_ for r_ in _fields.summary(fs, ds["items"])}
    check(
        "summary: coverage for every field",
        s["priority"]["filled"] == 3 and s["wait"]["filled"] == 2 and s["note"]["filled"] == 0,
    )
    check(
        "summary: a public field's values are summarised",
        s["product"].get("counts") == {"login": 2, "billing": 1},
    )
    check(
        "summary: a field not marked public shows no value",
        not any(k in s["priority"] for k in ("counts", "min", "max", "median", "distinct")),
    )
finally:
    if srv:
        srv.shutdown()
    import shutil

    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
