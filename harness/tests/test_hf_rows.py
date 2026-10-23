"""examples/_shared/hf_rows.py against a local server that answers the way the datasets-server
does when it is unhappy: 429s, 502s and a 404. No network; sleeps are recorded, not slept."""

from __future__ import annotations

import http.server
import json
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples" / "_shared"))
import hf_rows
from _check import check, summary

script: list[int] = []  # status codes to answer with, in order; 200 when empty
seen: list[str] = []


class Server(http.server.BaseHTTPRequestHandler):
    """Answers each request with the next scripted status."""

    def do_GET(self):
        seen.append(self.path)
        code = script.pop(0) if script else 200
        body = json.dumps({"rows": [{"row": {"i": 1}}]} if code == 200 else {"error": code}).encode()
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
finally:
    srv.shutdown()

sys.exit(summary())
