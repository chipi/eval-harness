#!/usr/bin/env python3
"""The zenodo and openml sources against their APIs served locally (PLAN_0.8.0 P2).

    python tests/test_zenodo_openml.py

Zenodo: a record with one CSV becomes items (its record id as revision, the concept as ref, the licence from
Zenodo's id); a file whose bytes are not the md5 Zenodo lists is refused; a record with two readable files needs
"file". OpenML: a dataset's parquet copy becomes items (its version as revision, its features with their types);
fieldset-propose reads those features. Offline: nothing leaves the machine.
"""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

CSV = b"comment,label\ngood,pos\nbad,neg\nfine,pos\n"
buf = io.BytesIO()
pq.write_table(
    pa.table({"class": ["setosa", "versicolor", "virginica"], "sepallength": [5.1, 7.0, 6.3]}), buf
)
PQ = buf.getvalue()
STATE = {"md5": hashlib.md5(CSV, usedforsecurity=False).hexdigest(), "two": False}


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
        base = f"http://127.0.0.1:{self.server.server_address[1]}"
        if self.path == "/api/records/42":
            files = [
                {
                    "key": "comments.csv",
                    "checksum": f"md5:{STATE['md5']}",
                    "links": {"self": f"{base}/files/comments.csv"},
                }
            ]
            if STATE["two"]:
                files.append(
                    {"key": "more.csv", "checksum": "md5:0", "links": {"self": f"{base}/files/more.csv"}}
                )
            return self._send({"id": 42, "conceptrecid": "40", "doi_url": "https://doi.org/10.5281/zenodo.42",
                               "metadata": {"title": "Comments", "description": "<p>Three comments.</p>",
                                            "license": {"id": "cc-by-4.0"}}, "files": files})  # fmt: skip
        if self.path == "/files/comments.csv":
            return self._send(CSV, "text/csv")
        if self.path == "/api/v1/json/data/61":
            return self._send({"data_set_description": {"id": "61", "name": "iris", "version": "1", "licence": "Public",
                                                        "description": "Iris.", "parquet_url": f"{base}/pq/61.pq"}})  # fmt: skip
        if self.path == "/api/v1/json/data/features/61":
            return self._send({"data_features": {"feature": [{"name": "sepallength", "data_type": "numeric"},
                                                             {"name": "class", "data_type": "nominal"}]}})  # fmt: skip
        if self.path == "/pq/61.pq":
            return self._send(PQ, "application/octet-stream")
        self.send_response(404)
        self.end_headers()


srv = ThreadingHTTPServer(("127.0.0.1", 0), Api)
threading.Thread(target=srv.serve_forever, daemon=True).start()
api = f"http://127.0.0.1:{srv.server_address[1]}"
proj = Path(tempfile.mkdtemp(prefix="evh-zo-"))
env = dict(
    os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-zo", ZENODO_ENDPOINT=api, OPENML_ENDPOINT=api
)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVAL_FETCH_HEADERS"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


def ds(i):
    return _runstore.read_json(proj, f"datasets/{i}.json")


try:
    (proj / "data" / "fields").mkdir(parents=True)
    _runstore.write_text(
        proj,
        "fields/c.yaml",
        "fieldset_id: c\nfields:\n  - {name: label, type: choice, values: [pos, neg]}\n",
    )
    r = evh("dataset-create", "--dataset-id", "z_v1", "--source", "zenodo", "--fieldset", "c",
            "--query", json.dumps({"record": 42, "text": "comment", "fields": ["label"]}))  # fmt: skip
    d = ds("z_v1") if r.returncode == 0 else {}
    check(
        "zenodo: the record's one CSV as items; revision the record id, ref its concept, the licence from Zenodo's id",
        [(it["item_id"], it.get("fields")) for it in d.get("items") or []]
        == [("row_0", {"label": "pos"}), ("row_1", {"label": "neg"}), ("row_2", {"label": "pos"})]
        and d["source"]["revision"] == "42"
        and d["source"]["ref"] == "40"
        and d.get("licence") == "CC-BY-4.0"
        and d.get("description") == "Comments",
        (r.stdout + r.stderr)[-400:],
    )
    STATE["md5"] = "0" * 32
    r = evh(
        "dataset-create",
        "--dataset-id",
        "z_v2",
        "--source",
        "zenodo",
        "--query",
        json.dumps({"record": 42, "text": "comment"}),
    )
    check(
        "zenodo: bytes that are not the md5 it lists are refused",
        r.returncode == 1 and "not the md5" in r.stderr,
        r.stderr[-300:],
    )
    STATE["two"] = True
    r = evh(
        "dataset-create",
        "--dataset-id",
        "z_v3",
        "--source",
        "zenodo",
        "--query",
        json.dumps({"record": 42, "text": "comment"}),
    )
    check(
        'zenodo: two readable files need "file"',
        r.returncode == 1 and 'name one with "file"' in r.stderr,
        r.stderr[-300:],
    )
    r = evh(
        "dataset-create",
        "--dataset-id",
        "o_v1",
        "--source",
        "openml",
        "--query",
        json.dumps({"dataset": 61, "text": "class", "limit": 2}),
    )
    d = ds("o_v1") if r.returncode == 0 else {}
    check(
        "openml: the parquet copy's rows as items; its version as revision, its page, no licence it cannot name",
        [it["item_id"] for it in d.get("items") or []] == ["row_0", "row_1"]
        and _runstore.read_text(proj, "sources/o_v1/row_1.txt") == "versicolor"
        and d["source"]["revision"] == "1"
        and d["source"]["url"] == f"{api}/d/61"
        and "licence" not in d,
        (r.stdout + r.stderr)[-400:],
    )
    r = evh(
        "fieldset-propose",
        "--source",
        "openml",
        "--query",
        json.dumps({"dataset": 61, "text": "class"}),
        "--fieldset-id",
        "iris",
    )
    check(
        "fieldset-propose reads OpenML's features: a numeric one is a number",
        r.returncode == 0 and "name: sepallength\n  type: number" in r.stdout,
        (r.stdout + r.stderr)[-300:],
    )
finally:
    srv.shutdown()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
