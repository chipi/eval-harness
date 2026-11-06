#!/usr/bin/env python3
"""The kaggle source against Kaggle's API served locally (PLAN_0.8.0 P3).

    python tests/test_kaggle.py

A dataset with a CSV and a sqlite file in its zip: the current version is read and recorded when none is named, a
named version is the one downloaded, Kaggle's licence name maps to its SPDX id (an unmapped one is left out), and a
zip with two tables needs "file". Offline: nothing leaves the machine.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

STATE: dict[str, Any] = {"licence": "CC0: Public Domain", "two": False, "asked": []}


def zipped(version: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Notes.csv", f"Id,Note\n1,first v{version}\n2,second v{version}\n")
        z.writestr("db.sqlite", b"not a table")
        if STATE["two"]:
            z.writestr("More.csv", "Id,Note\n9,other\n")
    return buf.getvalue()


class Api(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json"):
        body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/v1/datasets/view/ada/notes":
            return self._send({"ref": "ada/notes", "title": "Notes", "licenseName": STATE["licence"],
                               "currentVersionNumber": 3, "description": "Two notes."})  # fmt: skip
        if u.path == "/api/v1/datasets/download/ada/notes":
            v = int(parse_qs(u.query)["datasetVersionNumber"][0])
            STATE["asked"].append(v)
            return self._send(zipped(v), "application/zip")
        self.send_response(404)
        self.end_headers()


srv = ThreadingHTTPServer(("127.0.0.1", 0), Api)
threading.Thread(target=srv.serve_forever, daemon=True).start()
proj = Path(tempfile.mkdtemp(prefix="evh-kaggle-"))
env = dict(
    os.environ,
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-kaggle",
    KAGGLE_ENDPOINT=f"http://127.0.0.1:{srv.server_address[1]}",
)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVAL_FETCH_HEADERS"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


def ds(i):
    return json.loads((proj / "data" / "datasets" / f"{i}.json").read_text())


try:
    q = {"ref": "ada/notes", "text": "Note", "id": "Id"}
    r = evh("dataset-create", "--dataset-id", "k_v1", "--source", "kaggle", "--query", json.dumps(q))
    d = ds("k_v1") if r.returncode == 0 else {}
    check(
        "the current version read and recorded; the one readable table chosen; the licence name mapped",
        STATE["asked"] == [3]
        and d.get("source", {}).get("revision") == "3"
        and [it["item_id"] for it in d.get("items") or []] == ["1", "2"]
        and (proj / "data" / "sources" / "k_v1" / "2.txt").read_text() == "second v3"
        and d.get("licence") == "CC0-1.0",
        (r.stdout + r.stderr)[-400:],
    )
    STATE["licence"] = "Other (specified in description)"
    r = evh(
        "dataset-create",
        "--dataset-id",
        "k_v2",
        "--source",
        "kaggle",
        "--query",
        json.dumps({**q, "version": 1}),
    )
    d = ds("k_v2") if r.returncode == 0 else {}
    check(
        "a named version is the one downloaded; a licence name we cannot map is left out",
        STATE["asked"][-1] == 1 and d.get("source", {}).get("revision") == "1" and "licence" not in d
        and (proj / "data" / "sources" / "k_v2" / "1.txt").read_text() == "first v1",
        (r.stdout + r.stderr)[-400:],
    )  # fmt: skip
    STATE["two"] = True
    r = evh("dataset-create", "--dataset-id", "k_v3", "--source", "kaggle", "--query", json.dumps(q))
    check(
        'two tables in the zip need "file", naming them',
        r.returncode == 1 and 'with "file"' in r.stderr and "More.csv" in r.stderr,
        r.stderr[-300:],
    )
finally:
    srv.shutdown()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
