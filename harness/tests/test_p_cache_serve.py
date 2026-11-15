#!/usr/bin/env python3
"""The paired tests' p cache wherever views are computed (RFC-032 step 9): catalog-serve keeps them too.

    python tests/test_p_cache_serve.py

`evh` and the MCP server set EVH_P_CACHE to the project's ignored .cache/evh-p.jsonl unless it is set (an empty value
turns it off); catalog-serve answers the API's views in its own process and did not, so every restart drew the
goals' tests again (~10 s a view). `catalog_serve.main()` is run here in a process of its own, as `python
catalog_serve.py` runs it (the deployment's way: compose starts it so, not through `evh`), with the one thing that
would keep it running, `serve_forever`, replaced; the variable it leaves in its environment is read back.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _common  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-pserve-")).resolve()
(proj / "data").mkdir()
script = proj / "serve_once.py"
script.write_text(
    f"""
import os, sys
sys.path.insert(0, {str(HARNESS)!r})
from http.server import ThreadingHTTPServer
from evaluation_harness import catalog_serve
ThreadingHTTPServer.serve_forever = lambda self, *a, **k: None
sys.argv = ["catalog_serve.py", "--public", "localhost", "--port", "0"]
catalog_serve.main()
print("P_CACHE=" + repr(os.environ.get("EVH_P_CACHE")))
"""
)


def serve_env(**set_: str) -> str:
    """What the server process holds in EVH_P_CACHE once main() has run, given what it was started with."""
    env = {k: v for k, v in os.environ.items() if k not in ("EVH_P_CACHE", "EVAL_DATA_DIR", "EVAL_GOALS_DIR")}
    env.update(EVAL_HOME=str(proj), EVAL_BUILD_REF="test-p-cache-serve", **set_)
    r = subprocess.run(
        [sys.executable, str(script)], cwd=proj, env=env, capture_output=True, text=True, timeout=120,
        stdin=subprocess.DEVNULL,
    )  # fmt: skip
    lines = [x for x in r.stdout.splitlines() if x.startswith("P_CACHE=")]
    return lines[-1].removeprefix("P_CACHE=") if lines else f"NO ANSWER: {(r.stdout + r.stderr)[-300:]}"


want = repr(str(proj / ".cache" / "evh-p.jsonl"))
check("catalog-serve keeps the p's in the project's .cache/ by default", serve_env() == want, serve_env())
check("an EVH_P_CACHE it is started with is kept", serve_env(EVH_P_CACHE="/x/p.jsonl") == "'/x/p.jsonl'")
check("an empty one (no cache) is kept empty", serve_env(EVH_P_CACHE="") == "''")
check(
    "the default is one function's: the MCP server's commands and `evh` name the same file",
    _common.p_cache_path(proj) == str(proj / ".cache" / "evh-p.jsonl"),
)
sys.exit(summary())
