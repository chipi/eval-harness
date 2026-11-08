#!/usr/bin/env python3
"""The huggingface source against a Hub served locally (PLAN_0.8.0 P1).

    python tests/test_hf_source.py

A small Hub on 127.0.0.1 (HF_ENDPOINT) answers the dataset's info, refs and tree with a real parquet file:
`--source huggingface` records the block pinned to the parquet conversion's commit (gated, the viewer page per row),
the card's licence and metadata, and reads rows by offset and limit; a file whose bytes are not the sha256 the Hub
lists is refused; so is a split without a conversion. Offline: nothing leaves the machine.
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

REF, REV = "acme/notes", "c0ffee" * 6 + "abcd"
buf = io.BytesIO()
pq.write_table(pa.table({"text": [f"note {n}" for n in range(6)], "label": [n % 2 for n in range(6)]}), buf)
PARQUET = buf.getvalue()
STATE = {"oid": hashlib.sha256(PARQUET).hexdigest(), "converts": True}
INFO = {
    "id": REF,
    "sha": "f" * 40,
    "gated": "manual",
    "description": "Six notes.",
    "cardData": {
        "license": "cc-by-sa-4.0",
        "pretty_name": "Acme notes",
        "task_categories": ["text-classification"],
        "annotations_creators": ["expert-generated"],
        "dataset_info": {
            "features": [{"name": "text", "dtype": "string"}, {"name": "label", "dtype": "int64"}]
        },
    },
}


class Hub(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path
        if p == f"/api/datasets/{REF}":
            return self._send(json.dumps(INFO).encode())
        if p == f"/api/datasets/{REF}/refs":
            conv = (
                [{"name": "parquet", "ref": "refs/convert/parquet", "targetCommit": REV}]
                if STATE["converts"]
                else []
            )
            return self._send(json.dumps({"branches": [], "converts": conv}).encode())
        if p == f"/api/datasets/{REF}/tree/{REV}/default/test":
            return self._send(
                json.dumps(
                    [{"type": "file", "path": "default/test/0000.parquet", "lfs": {"oid": STATE["oid"]}}]
                ).encode()
            )
        if p == f"/datasets/{REF}/resolve/{REV}/default/test/0000.parquet":
            return self._send(PARQUET, "application/octet-stream")
        self.send_response(404)
        self.end_headers()


srv = ThreadingHTTPServer(("127.0.0.1", 0), Hub)
threading.Thread(target=srv.serve_forever, daemon=True).start()
hub = f"http://127.0.0.1:{srv.server_address[1]}"
proj = Path(tempfile.mkdtemp(prefix="evh-hf-source-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-hf-source", HF_ENDPOINT=hub)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD", "EVAL_FETCH_HEADERS"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )


try:
    (proj / "data" / "fields").mkdir(parents=True)
    (proj / "data" / "fields" / "notes.yaml").write_text(
        "fieldset_id: notes\nfields:\n  - {name: label, type: integer}\n"
    )
    _runstore.migrate_in(proj)
    q = {"ref": REF, "split": "test", "text": "text", "fields": ["label"], "offset": 1, "limit": 3}
    r = evh(
        "dataset-create",
        "--dataset-id",
        "n_v1",
        "--source",
        "huggingface",
        "--query",
        json.dumps(q),
        "--fieldset",
        "notes",
    )
    d = _runstore.read_json(proj, "datasets/n_v1.json") if r.returncode == 0 else {}
    src = d.get("source") or {}
    check(
        "the block pinned to the parquet conversion's commit, gated, the viewer page per row",
        src.get("provider") == "huggingface"
        and src.get("revision") == REV
        and src.get("gated") is True
        and src.get("item_url") == f"{hub}/datasets/{REF}/viewer/default/test?row={{row}}"
        and src.get("description_sha256") == hashlib.sha256(b"Six notes.").hexdigest(),
        (r.stdout + r.stderr)[-400:] + json.dumps(src),
    )
    check(
        "the card's licence, its metadata in the card's words",
        d.get("licence") == "CC-BY-SA-4.0"
        and d.get("card", {}).get("dataUseCases", "").startswith("tasks: text-classification")
        and "expert-generated" in d.get("card", {}).get("dataAnnotationProtocol", ""),
        json.dumps({k: d.get(k) for k in ("licence", "card")}),
    )
    check(
        "rows by offset and limit, each with its row and kept field",
        [(it["item_id"], it.get("source_row"), it.get("fields")) for it in d.get("items") or []]
        == [("row_1", 1, {"label": 1}), ("row_2", 2, {"label": 0}), ("row_3", 3, {"label": 1})]
        and _runstore.read_text(proj, "sources/n_v1/row_2.txt") == "note 2",
        json.dumps(d.get("items"))[:400],
    )
    STATE["oid"] = "0" * 64
    if _runstore.exists(proj, "sources/n_v2"):
        _runstore.rmtree(proj, "sources/n_v2")
    r = evh(
        "dataset-create",
        "--dataset-id",
        "n_v2",
        "--source",
        "huggingface",
        "--query",
        json.dumps({**q, "fields": []}),
    )
    check(
        "a file whose bytes are not the Hub's sha256 is refused",
        r.returncode == 1 and "n_v2" not in str(_runstore.listdir(proj, "datasets")),
        r.stderr[-300:],
    )
    STATE["converts"] = False
    r = evh(
        "dataset-create",
        "--dataset-id",
        "n_v3",
        "--source",
        "huggingface",
        "--query",
        json.dumps({**q, "fields": []}),
    )
    check(
        "a dataset the Hub has not converted to parquet is refused, naming it",
        r.returncode == 1 and "no parquet conversion" in r.stderr,
        r.stderr[-300:],
    )
finally:
    srv.shutdown()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
