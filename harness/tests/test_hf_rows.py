#!/usr/bin/env python3
"""The examples' shared Hub reader (examples/_shared/hf_rows.py) through the harness's huggingface source (P4).

    python tests/test_hf_rows.py

Against a Hub served locally (HF_ENDPOINT), with a split in two parquet files: `page` returns the rows of any
[offset, offset + length) across the two files with their split row numbers, [] past the end; the conversion's
commit is resolved once a process and every page reads at it; `Sources` writes the rows map with the sha256 of each
written file and the commit as the source's revision; a dataset the Hub has not converted ends in one message
naming it. Offline.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

REF, REV = "acme/rows", "b" * 40


def part(lo: int, hi: int) -> bytes:
    buf = io.BytesIO()
    pq.write_table(
        pa.table({"text": [f"row {n}" for n in range(lo, hi)], "label": [n % 3 for n in range(lo, hi)]}), buf
    )
    return buf.getvalue()


FILES = {"default/test/0000.parquet": part(0, 4), "default/test/0001.parquet": part(4, 7)}
STATE = {"refs": 0, "converts": True}


class Hub(BaseHTTPRequestHandler):
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
        if self.path == f"/api/datasets/{REF}/refs":
            STATE["refs"] += 1
            conv = [{"name": "parquet", "targetCommit": REV}] if STATE["converts"] else []
            return self._send({"converts": conv})
        if self.path == f"/api/datasets/{REF}/tree/{REV}/default/test":
            return self._send(
                [{"path": p, "lfs": {"oid": hashlib.sha256(b).hexdigest()}} for p, b in FILES.items()]
            )
        for p, b in FILES.items():
            if self.path == f"/datasets/{REF}/resolve/{REV}/{p}":
                return self._send(b, "application/octet-stream")
        self.send_response(404)
        self.end_headers()


srv = ThreadingHTTPServer(("127.0.0.1", 0), Hub)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["HF_ENDPOINT"] = f"http://127.0.0.1:{srv.server_address[1]}"
os.environ["EVAL_HOME"] = tempfile.mkdtemp(prefix="evh-hf-rows-")  # the item cache lives under it
sys.path.insert(0, str(HARNESS.parent / "examples" / "_shared"))
import hf_rows  # noqa: E402

try:
    rows = hf_rows.page(REF, "default", "test", 2, 4)
    check(
        "a page across the two files: its rows and their split row numbers",
        [(r.row_idx, r["text"]) for r in rows] == [(2, "row 2"), (3, "row 3"), (4, "row 4"), (5, "row 5")],
        [(r.row_idx, dict(r)) for r in rows],
    )
    check("past the end: []", hf_rows.page(REF, "default", "test", 7, 5) == [])
    hf_rows.page(REF, "default", "test", 0, 1)
    check("the conversion's commit is resolved once a process", STATE["refs"] == 1, STATE)
    root = Path(tempfile.mkdtemp(prefix="evh-hf-rows-out-"))
    (root / "data" / "sources" / "ds").mkdir(parents=True)
    (root / "data" / "sources" / "ds" / "x.txt").write_bytes(b"hello")
    where = hf_rows.Sources(REF, "default", "test")
    where.record("x", rows[0])
    where.record("gone", rows[1])  # no file written for it: not in the map
    where.write(root, "ds")
    doc = json.loads((root / "data" / "sources" / "ds.rows.json").read_text())
    check(
        "the rows map: each written item's row and bytes, the commit as the source's revision",
        doc["rows"] == {"x": {"row": 2, "sha256": hashlib.sha256(b"hello").hexdigest()}}
        and doc["source"]["revision"] == REV
        and doc["source"]["provider"] == "huggingface"
        and doc["item_url"].endswith("/acme/rows/viewer/default/test?row={row}"),
        doc,
    )
    STATE["converts"] = False
    hf_rows._REVISIONS.clear()  # a new process starts with none
    try:
        hf_rows.page(REF, "default", "test", 0, 1)
        said = ""
    except SystemExit as e:
        said = str(e)
    check(
        "a dataset without a parquet conversion ends in one message naming it",
        "no parquet conversion" in said,
        said,
    )
finally:
    srv.shutdown()
sys.exit(summary())
