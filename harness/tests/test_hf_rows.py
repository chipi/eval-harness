"""examples/_shared/hf_rows.py against a local server that answers the way the datasets-server
does when it is unhappy: 429s, 502s and a 404. No network; sleeps are recorded, not slept."""

from __future__ import annotations

import hashlib
import http.server
import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples" / "_shared"))
import hf_rows
from evaluation_harness._check import check, summary

script: list[int] = []  # status codes to answer with, in order; 200 when empty
seen: list[str] = []


class Server(http.server.BaseHTTPRequestHandler):
    """Answers each request with the next scripted status."""

    def do_GET(self):
        seen.append(self.path)
        code = script.pop(0) if script else 200
        body = json.dumps(
            {"rows": [{"row_idx": 7, "row": {"i": 1}}]} if code == 200 else {"error": code}
        ).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Server)
threading.Thread(target=srv.serve_forever, daemon=True).start()
hf_rows.ROWS_API = f"http://127.0.0.1:{srv.server_address[1]}/rows"
waits: list[float] = []
hf_rows.time.sleep = waits.append  # recorded, not slept

try:
    rows = hf_rows.page("d", "c", "test", 0, 5)
    check("a clean answer is the page's rows", rows == [{"i": 1}], rows)
    check("and it paces the next request", waits == [hf_rows.DEFAULT_DELAY], waits)
    check(
        "the query names dataset, config, split, offset and length",
        all(k in seen[-1] for k in ("dataset=d", "config=c", "split=test", "offset=0", "length=5")),
        seen[-1],
    )

    waits.clear()
    script[:] = [429, 429, 200]
    check("429s are waited out, then the page comes back", hf_rows.page("d", "c", "test", 0, 5) == [{"i": 1}])
    check("on the slow schedule: 5 s, then 15 s", waits[:2] == [5, 15], waits)

    waits.clear()
    script[:] = [502, 200]
    hf_rows.page("d", "c", "test", 0, 5)
    check("a 502 retries on the short ladder (2 s)", waits[:1] == [2], waits)

    waits.clear()
    script[:] = [404]
    before = len(seen)
    try:
        hf_rows.page("d", "c", "test", 0, 5)
        stopped = False
    except SystemExit as exc:
        stopped = "HTTP 404" in str(exc)
    check("a 404 stops at once, with one message naming it", stopped and len(seen) - before == 1)

    waits.clear()
    script[:] = [429] * hf_rows.MAX_ATTEMPTS
    try:
        hf_rows.page("d", "c", "test", 300, 5)
        gave_up = ""
    except SystemExit as exc:
        gave_up = str(exc)
    check("a limit that never lifts ends in one message naming the offset", "offset 300" in gave_up, gave_up)
    check("after the whole 429 schedule", waits == list(hf_rows.RATE_LIMIT_BACKOFF), waits)

    # Where each row came from: its row number, kept beside the row without changing it.
    row = hf_rows.page("d", "c", "test", 0, 1)[0]
    check(
        "a row keeps its row number", row.row_idx == 7 and json.dumps(row) == '{"i": 1}', (row.row_idx, row)
    )
    tmp = Path(tempfile.mkdtemp(prefix="hf-rows-"))
    (tmp / "data" / "sources" / "ds").mkdir(parents=True)
    (tmp / "data" / "sources" / "ds" / "x.txt").write_bytes(b"hello")
    where = hf_rows.Sources("org/set", "c", "test")
    where.record("x", row)
    where.record("gone", row)  # no file written for it: not in the map
    where.write(tmp, "ds")
    doc = json.loads((tmp / "data" / "sources" / "ds.rows.json").read_text())
    check(
        "the rows map names the source and each written item's row and bytes",
        doc["source"]["name"] == "org/set"
        and doc["rows"] == {"x": {"row": 7, "sha256": hashlib.sha256(b"hello").hexdigest()}}
        and doc["item_url"].endswith("/org/set/viewer/c/test?row={row}"),
        doc,
    )
    shutil.rmtree(tmp, ignore_errors=True)
finally:
    srv.shutdown()

sys.exit(summary())
