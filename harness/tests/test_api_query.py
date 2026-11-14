#!/usr/bin/env python3
"""A read resource's inputs through the API's query string and path (RFC-032 step 8).

    python tests/test_api_query.py

A query holds only strings: catalog-serve types each input as the operation's schema says (an integer, a number, a
boolean as true or false or 1 or 0, an array as the key repeated, its items typed too) and refuses, as a 400 naming
the input, one that is not; a part of the path is URL-decoded, so an id with a space or a slash (a metric called
`a b/c`) reaches the operation as it is. In a throwaway project with a run that records such a metric, and an
operation registered for the run that echoes what it is given.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-apiquery-"))
os.environ.update(EVAL_HOME=str(proj), EVAL_BUILD_REF="test-api-query", EVH_ACTOR="person:tester")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVH_PUBLIC"):
    os.environ.pop(k, None)

import _catalog_fixture as fx  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format, _store  # noqa: E402
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.catalog_adapter import load_catalog_adapter  # noqa: E402
from evaluation_harness.ops import registry  # noqa: E402
from evaluation_harness.ops.registry import Op  # noqa: E402

TOKEN = "test-token"


def echo(name: str, **given) -> dict:
    """The operation the test registers: what it was given, with the type of each."""
    return {"name": name, "given": given, "types": {k: type(v).__name__ for k, v in given.items()}}


def say(r: dict) -> str:
    """Its answer as text."""
    return json.dumps(r)


registry.OPS["echo-show"] = Op(
    "echo-show", "read", "echoes its inputs", "GET", "/echo/{name}", "__main__:echo", "__main__:say",
    inputs={
        "n": {"type": "integer"}, "f": {"type": "number"}, "on": {"type": "boolean"}, "s": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "ids": {"type": "array", "items": {"type": "integer"}},
    },
)  # fmt: skip


def get(port: int, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {TOKEN}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


try:
    (proj / "data" / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    rows = "".join(json.dumps({"item_id": f"i{i:02d}", "a b/c": 0.5}) + "\n" for i in range(12))
    fx.put(
        proj / "data",
        "r1",
        {
            "run_id": "r1", "dataset_id": "ds", "config_id": "sys_a", "primary_metric": "a b/c",
            "metric_kinds": {"a b/c": "quality"}, "fingerprint": {"data": {"reference_id": "gold/ds"}},
            "created_at": "2026-11-14T10:00:00Z",
        },
        rows,
    )  # fmt: skip
    cs.set_adapter(load_catalog_adapter(None))
    cs.Handler.prefixes = cs.served(proj / ".build" / "catalog", cs.A.data_dir)
    cs.API_TOKEN[:] = [TOKEN]
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(cs.Handler, directory=str(cs.ROOT)), bind_and_activate=False
    )
    server.server_bind()
    server.server_activate()
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    st, body = get(port, "/api/v1/echo/a%20b%2Fc?n=5&f=1.5&on=true&s=hi+there&tags=x&tags=y,z&ids=1&ids=2")
    got = body.get("result", {})
    check(
        "a path part is URL-decoded: an id with a space and a slash arrives as it is",
        st == 200 and got.get("name") == "a b/c",
        (st, body),
    )
    check(
        "each input is typed by its schema: integer, number, boolean, string; an array is the key repeated, items typed",
        got.get("given") == {"n": 5, "f": 1.5, "on": True, "s": "hi there", "tags": ["x", "y,z"], "ids": [1, 2]}
        and got.get("types") == {"n": "int", "f": "float", "on": "bool", "s": "str", "tags": "list", "ids": "list"},
        got,
    )  # fmt: skip
    st, body = get(port, "/api/v1/echo/x?on=0&ids=3")
    check(
        "a boolean is 0 as well as false, a single array value is a list of one",
        st == 200 and body["result"]["given"] == {"on": False, "ids": [3]},
        (st, body),
    )
    refused = {q: get(port, f"/api/v1/echo/x?{q}") for q in ("n=abc", "f=x", "on=maybe", "ids=1&ids=two")}
    check(
        "an input that is not what the schema says is a 400 naming it",
        all(st == 400 and "echo-show:" in b.get("error", "") for st, b in refused.values())
        and "n: 'abc' is not an integer" in refused["n=abc"][1]["error"]
        and "on: 'maybe' is not true or false" in refused["on=maybe"][1]["error"],
        refused,
    )  # fmt: skip
    st, body = get(port, "/api/v1/echo/x?unknown=1&n=2")
    check(
        "an input the operation does not have is left out",
        st == 200 and body["result"]["given"] == {"n": 2},
        (st, body),
    )
    st, body = get(port, "/api/v1/metrics/a%20b%2Fc")
    check(
        "metric-show with a metric called `a b/c` answers 200 and names it",
        st == 200 and "a b/c" in json.dumps(body),
        (st, str(body)[:300]),
    )
    server.shutdown()
    server.server_close()
finally:
    _store.close()

sys.exit(summary())
