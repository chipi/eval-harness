#!/usr/bin/env python3
"""An unhandled error in catalog-serve is answered as JSON, with or without --hooks (API 6, owner 2026-11-17).

    python tests/test_serve_error_json.py

Without --hooks a route that raised used to propagate: the connection closed with no answer, and a Workbench page
read a broken response instead of `{error}`. Here the server's own Handler, in this process, on a free port, in a
throwaway project, with a route made to raise: the answer is a 500 whose body is JSON with `error`, and the traceback
is printed on the server's stderr (no hooks to tell).
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
proj = Path(tempfile.mkdtemp(prefix="evh-serve-error-"))
env = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_")}
init = subprocess.run(
    [sys.executable, str(HERE / "cli.py"), "init", "--store", "files"], cwd=proj, env={**env, "EVAL_HOME": str(proj)},
    capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300,
)  # fmt: skip
os.environ["EVAL_HOME"] = str(proj)
os.environ.pop("EVAL_STORE", None)
sys.path.insert(0, str(HERE.parent))
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

check("the throwaway project is made", init.returncode == 0, init.stderr[-300:])


def boom(self):
    raise RuntimeError("a route that fails for the test")


setattr(cs.Handler, "_get", boom)  # noqa: B010 — the route made to fail; mypy refuses assigning a method
server = ThreadingHTTPServer(("127.0.0.1", 0), partial(cs.Handler, directory=str(proj)))
threading.Thread(target=server.serve_forever, daemon=True).start()
port = server.server_address[1]
err = io.StringIO()
status, body = 0, {}
with contextlib.redirect_stderr(err):
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/", headers={"Host": f"127.0.0.1:{port}"})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 — the test's own server  # nosec B310
            status = r.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            body = json.loads(exc.read() or b"{}")
        except ValueError:
            body = {"not json": True}
    except OSError as exc:
        body = {"no answer": str(exc)}
server.shutdown()
check(
    "without --hooks, a route that raises is answered 500 with a JSON {error}, not a closed connection",
    cs.HOOKS is None and status == 500 and isinstance(body.get("error"), str) and body["error"],
    (cs.HOOKS, status, body),
)
check(
    "and the traceback is printed on the server's stderr",
    "RuntimeError: a route that fails for the test" in err.getvalue(),
    err.getvalue()[-300:],
)
sys.exit(summary())
