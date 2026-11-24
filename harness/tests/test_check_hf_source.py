#!/usr/bin/env python3
"""examples/_shared/check_hf_source.py reads the datasets-server's /rows, and a 502 there is not a difference (S3).

    python tests/test_check_hf_source.py

`rows_api` with a stubbed urlopen and no sleeping: a 5xx or a connection error is retried (each retry on stderr with
its status and attempt) and 502, 502, 200 passes; a 4xx fails at once, with no retry; a 5xx every time ends in one
line, "datasets-server /rows unavailable (502) after N tries: not a difference", and `main` exits 1 without a
traceback. Offline.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import urllib.error
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(HARNESS.parent / "examples" / "_shared"))
import check_hf_source as chk  # noqa: E402


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(chk.ROWS_API, code, "stub", None, None)  # type: ignore[arg-type]


OK = json.dumps({"rows": [{"row_idx": 3, "row": {"text": "x"}}]}).encode()


def run(script):
    """rows_api over a urlopen that plays `script` (a status code, an exception or a body), its sleeps and stderr."""
    calls, sleeps = [], []
    seq = iter(script)

    def urlopen(url, timeout=None):
        calls.append(url)
        step = next(seq)
        if isinstance(step, int):
            raise http(step)
        if isinstance(step, Exception):
            raise step
        return Resp(step)

    real, chk.urllib.request.urlopen = chk.urllib.request.urlopen, urlopen
    err, out, raised = io.StringIO(), None, None
    try:
        with contextlib.redirect_stderr(err):
            try:
                out = chk.rows_api("d", "c", "s", 0, 5, sleep=sleeps.append)
            except chk.RowsUnavailable as e:
                raised = e
    finally:
        chk.urllib.request.urlopen = real
    return out, raised, len(calls), sleeps, err.getvalue()


out, raised, n, sleeps, err = run([502, 502, OK])
check("502, 502, 200: the rows come back", out == [(3, {"text": "x"})] and raised is None, (out, raised))
check("  after 3 calls and 2 sleeps", n == 3 and len(sleeps) == 2, (n, sleeps))
check(
    "  each retry says its status and attempt on stderr",
    err.count("502") == 2 and "1" in err and "2" in err,
    err,
)

out, raised, n, sleeps, err = run([404])
check(
    "404: fails at once, one call, no sleep",
    raised is not None and n == 1 and not sleeps,
    (raised, n, sleeps),
)
check("  the line names the code", raised is not None and "(404)" in str(raised), raised)

out, raised, n, sleeps, err = run(
    [urllib.error.URLError("refused"), TimeoutError(), ConnectionResetError(), OK]
)
check(
    "connection errors and timeouts are retried", out is not None and n == 4 and len(sleeps) == 3, (n, sleeps)
)

out, raised, n, sleeps, err = run([502] * 50)
want = f"datasets-server /rows unavailable (502) after {n} tries: not a difference"
check("502 every time: ends in the one line", raised is not None and str(raised) == want, (raised, want))
check(
    "  more than 4 tries, the backoff bounded near two minutes",
    n > 4 and 90 <= sum(sleeps) <= 150,
    (n, sleeps),
)

with contextlib.redirect_stderr(io.StringIO()) as e2, contextlib.redirect_stdout(io.StringIO()) as o2:
    real_page, real_rows = chk.hf_rows.page, chk.rows_api
    chk.hf_rows.page = lambda *a: []
    chk.rows_api = lambda *a, **k: (_ for _ in ()).throw(chk.RowsUnavailable(want))
    try:
        rc = chk.main()
    finally:
        chk.hf_rows.page, chk.rows_api = real_page, real_rows
check(
    "main: exit 1, the line, no traceback",
    rc == 1 and want in (e2.getvalue() + o2.getvalue()) and "Traceback" not in e2.getvalue(),
    rc,
)

sys.exit(summary())
