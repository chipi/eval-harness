#!/usr/bin/env python3
"""The API's OpenAPI 3.1 description, made from the operations (RFC-032 step 9).

    python tests/test_openapi.py

The document on its own: every operation is a path and a method with its operationId, its route's parts as path
parameters (each declared, each in the path), a read's inputs as query parameters and an edit's or a decision's as a
JSON body with `by` and the data header, the refusals as 4xx with the error envelope, a declared result schema as the
200's; the job routes are there; the structure is OpenAPI 3.1's (required keys, references that resolve, security
schemes that exist) and every schema is valid JSON Schema 2020-12 (jsonschema's Draft202012Validator). The checker
itself is shown to refuse a document with a part taken out. Then a real `evh catalog-serve` in a throwaway project
($0, offline): `GET /api/v1/openapi.json` answers the document `evh openapi` prints, only with the token, to this
machine's Host and Origin; a read route the document names answers, and the routes RFC-032 removed (`/api/v1/read/*`,
`/api/v1/commands`) answer 404; a --public server answers none of it.
"""

import copy
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
import jsonschema  # noqa: E402
from evaluation_harness import _common, _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.ops import openapi  # noqa: E402
from evaluation_harness.ops.registry import OPS  # noqa: E402

METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
PREFIX = "/api/v1"


def schemas_of(doc: dict):
    """Every JSON Schema in the document: its components', and each parameter's, body's and response's."""
    yield from doc.get("components", {}).get("schemas", {}).values()
    for item in doc.get("paths", {}).values():
        for op in item.values():
            for p in op.get("parameters", []):
                if "schema" in p:
                    yield p["schema"]
            for c in (op.get("requestBody") or {}).get("content", {}).values():
                yield c["schema"]
            for r in op.get("responses", {}).values():
                for c in (r.get("content") or {}).values():
                    yield c["schema"]
    for r in doc.get("components", {}).get("responses", {}).values():
        for c in (r.get("content") or {}).values():
            yield c["schema"]


def resolves(doc: dict, ref: str) -> bool:
    here: object = doc
    for part in ref.removeprefix("#/").split("/"):
        if not isinstance(here, dict) or part not in here:
            return False
        here = here[part]
    return True


def refs_in(node: object):
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            yield node["$ref"]
        for v in node.values():
            yield from refs_in(v)
    elif isinstance(node, list):
        for v in node:
            yield from refs_in(v)


def problems(doc: dict) -> list[str]:
    """What is wrong with the document, by OpenAPI 3.1's structure and JSON Schema 2020-12."""
    out: list[str] = []
    if not str(doc.get("openapi", "")).startswith("3.1."):
        out.append(f"openapi: {doc.get('openapi')!r} is not 3.1.x")
    for key in ("info", "paths"):
        if not isinstance(doc.get(key), dict) or not doc[key]:
            out.append(f"{key}: missing or empty")
    info = doc.get("info") or {}
    for key in ("title", "version"):
        if not isinstance(info.get(key), str) or not info[key]:
            out.append(f"info.{key}: missing")
    schemes = (doc.get("components") or {}).get("securitySchemes", {})
    for req in doc.get("security", []):
        for name in req:
            if name not in schemes:
                out.append(f"security: {name} is not a security scheme")
    ids: list[str] = []
    for path, item in (doc.get("paths") or {}).items():
        if not path.startswith("/"):
            out.append(f"{path}: a path starts with /")
        in_path = re.findall(r"\{([^}]+)\}", path)
        for method, op in item.items():
            where = f"{method.upper()} {path}"
            if method not in METHODS:
                out.append(f"{where}: not an HTTP method")
                continue
            if not op.get("responses"):
                out.append(f"{where}: no responses")
            for code, r in op.get("responses", {}).items():
                if not re.fullmatch(r"[1-5][0-9X]{2}|default", code):
                    out.append(f"{where}: response {code!r} is not a status")
                if "$ref" not in r and "description" not in r:
                    out.append(f"{where}: response {code} has no description")
            if "operationId" in op:
                ids.append(op["operationId"])
            params = op.get("parameters", [])
            seen = [(p["name"], p["in"]) for p in params]
            if len(seen) != len(set(seen)):
                out.append(f"{where}: a parameter declared twice")
            for p in params:
                if p.get("in") not in ("path", "query", "header", "cookie"):
                    out.append(f"{where}: parameter {p.get('name')!r} is in {p.get('in')!r}")
                if "schema" not in p and "content" not in p:
                    out.append(f"{where}: parameter {p.get('name')!r} has no schema")
                if p.get("in") == "path" and p.get("required") is not True:
                    out.append(f"{where}: path parameter {p['name']!r} is not required")
            declared = {p["name"] for p in params if p.get("in") == "path"}
            for name in in_path:
                if name not in declared:
                    out.append(f"{where}: path part {{{name}}} is not declared")
            for name in declared - set(in_path):
                out.append(f"{where}: path parameter {name!r} is not in the path")
            for name in op.get("security", []) and [n for req in op["security"] for n in req]:
                if name not in schemes:
                    out.append(f"{where}: security {name} is not a scheme")
            if method in ("get", "head") and "requestBody" in op:
                out.append(f"{where}: a body on a method that has none")
    for dup in {i for i in ids if ids.count(i) > 1}:
        out.append(f"operationId {dup!r} is used twice")
    for ref in refs_in(doc):
        if not resolves(doc, ref):
            out.append(f"{ref}: does not resolve")
    for i, s in enumerate(schemas_of(doc)):
        try:
            jsonschema.Draft202012Validator.check_schema(s)
        except jsonschema.SchemaError as exc:
            out.append(f"schema #{i}: {exc.message}")
    return out


doc = openapi.document()
paths = doc["paths"]
check(
    "the document is OpenAPI 3.1 by structure, every schema valid JSON Schema 2020-12",
    not problems(doc),
    problems(doc)[:5],
)
check(
    "the document is what `json` can carry and is the same every time",
    json.loads(json.dumps(doc)) == doc and openapi.document() == doc,
)
check(
    "the schema dialect is 2020-12, which the operations' inputs are written in",
    doc.get("jsonSchemaDialect") == "https://json-schema.org/draft/2020-12/schema",
)

missing = [
    op.name
    for op in OPS.values()
    if (paths.get(f"{PREFIX}{op.route}", {}).get(op.method.lower()) or {}).get("operationId") != op.name
]
check("every operation is a path and a method with its name as operationId", not missing, missing)
check(
    "the paths hold the operations' and nothing else but the job routes and the API's own",
    {(m.upper(), p) for p, item in paths.items() for m in item}
    - {(op.method, f"{PREFIX}{op.route}") for op in OPS.values()}
    == {
        ("GET", f"{PREFIX}/jobs"),
        ("POST", f"{PREFIX}/jobs"),
        ("GET", f"{PREFIX}/jobs/{{id}}"),
        ("GET", f"{PREFIX}/jobs/{{id}}/log"),
        ("GET", f"{PREFIX}/jobs/{{id}}/files/{{name}}"),
        ("POST", f"{PREFIX}/jobs/{{id}}/stop"),
        ("POST", f"{PREFIX}/jobs/{{id}}/resume"),
        ("POST", f"{PREFIX}/estimate"),
        ("GET", f"{PREFIX}/openapi.json"),
        ("GET", f"{PREFIX}/session"),
    },
)


def op_of(op) -> dict:
    return paths[f"{PREFIX}{op.route}"][op.method.lower()]


wrong_params, wrong_inputs, wrong_body = [], [], []
for op in OPS.values():
    o = op_of(op)
    by_in = {k: {p["name"]: p for p in o["parameters"] if p["in"] == k} for k in ("path", "query", "header")}
    if list(by_in["path"]) != op.path_params():
        wrong_params.append(op.name)
    if op.kind == "read":
        if {n: p["required"] for n, p in by_in["query"].items()} != {n: n in op.required for n in op.inputs}:
            wrong_inputs.append(op.name)
        if any(p["schema"] != op.inputs[n] for n, p in by_in["query"].items()) or "requestBody" in o:
            wrong_inputs.append(op.name)
    else:
        body = o["requestBody"]["content"]["application/json"]["schema"]
        if (
            by_in["query"]
            or by_in["header"].get("X-EVH-Data", {}).get("required") is not True
            or not set(op.inputs) < set(body["properties"])
            or body["required"] != [*op.required, "by"]
            or body["additionalProperties"] is not False
        ):
            wrong_body.append(op.name)
check("every path parameter of a route is declared, in the route's order", not wrong_params, wrong_params)
check(
    "a read's inputs are query parameters (required as the operation says, the schema as it is)",
    not wrong_inputs,
    wrong_inputs,
)
check(
    "an edit's or a decision's inputs are a JSON body with by, and the data header is required",
    not wrong_body,
    wrong_body,
)
check(
    "the operations of each kind are all there",
    {op.kind for op in OPS.values()} >= {"read", "edit", "decision"}
    and all(op_of(op)["x-evh-kind"] == op.kind for op in OPS.values()),
)

errors = {
    s: {k for k, v in openapi.REFUSAL_STATUS.items() if v == s} for s in set(openapi.REFUSAL_STATUS.values())
}
check(
    "every refusal kind has a status, the model's own kinds",
    set(openapi.REFUSAL_STATUS) <= set(_common.REFUSALS),
    set(openapi.REFUSAL_STATUS) - set(_common.REFUSALS),
)
shape_wrong = []
for op in OPS.values():
    rs = op_of(op)["responses"]
    want = {"200", "400", "401", "403", "404", "409", "422", "503"} | (
        {"413"} if op.kind != "read" else set()
    )
    if set(rs) != want:
        shape_wrong.append((op.name, sorted(set(rs) ^ want)))
    for code, r in rs.items():
        if code != "200" and r != {"$ref": f"#/components/responses/{r['$ref'].rsplit('/', 1)[-1]}"}:
            shape_wrong.append((op.name, code))
check(
    "every operation answers 200 and the refusals as 4xx (413 too for a write), 503 while a migration holds the project",
    not shape_wrong,
    shape_wrong[:3],
)
err_codes = {
    "400": "BadRequest",
    "401": "Unauthorized",
    "403": "Forbidden",
    "404": "NotFound",
    "409": "Conflict",
    "413": "TooLarge",
    "422": "Invalid",
    "503": "Migrating",
}
comp = doc["components"]["responses"]
check(
    "each refusal is the error envelope: the message, and for the model's refusals their kind and problems",
    all(
        comp[name]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/Error"}
        for name in err_codes.values()
    )
    and doc["components"]["schemas"]["Error"]["required"] == ["error"]
    and set(doc["components"]["schemas"]["Error"]["properties"]) == {"error", "kind", "problems"}
    and all(
        str(s) in err_codes and any(k in comp[err_codes[str(s)]]["description"] for k in kinds)
        for s, kinds in errors.items()
    ),
)

sec = doc["components"]["securitySchemes"]
check(
    "the token is a bearer or the cookie the session route sets",
    sec["bearerAuth"] == {"type": "http", "scheme": "bearer", "description": "Authorization: Bearer <token>"}
    and sec["cookieAuth"]["in"] == "cookie"
    and sec["cookieAuth"]["name"] == "evh_token"
    and doc["security"] == [{"bearerAuth": []}, {"cookieAuth": []}]
    and paths[f"{PREFIX}/session"]["get"]["security"] == [],
)

# A declared result schema is the 200's; none declares one yet, so it is object.
first = next(iter(OPS.values()))
check(
    "the 200 is the envelope with an object result when the operation declares none",
    op_of(first)["responses"]["200"]["content"]["application/json"]["schema"]["properties"]["result"]
    == {"type": "object"},
)
real = openapi.OPS
try:
    from dataclasses import replace

    declared = {"type": "object", "properties": {"goals": {"type": "array"}}, "required": ["goals"]}
    openapi.OPS = {**real, first.name: replace(first, output=declared)}
    got = openapi.document()["paths"][f"{PREFIX}{first.route}"][first.method.lower()]
    check(
        "a declared result schema is the 200's result",
        got["responses"]["200"]["content"]["application/json"]["schema"]["properties"]["result"] == declared,
    )
finally:
    openapi.OPS = real

# The checker has to refuse what is wrong, or "valid" means nothing.
goal_show = f"{PREFIX}/goals/{{goal}}"


def mutated(change) -> list[str]:
    d = copy.deepcopy(doc)
    change(d)
    return problems(d)


refused = {
    "a path part not declared": mutated(lambda d: d["paths"][goal_show]["get"].__setitem__("parameters", [])),
    "a path parameter not in the path": mutated(
        lambda d: d["paths"][f"{PREFIX}/goals"]["get"]["parameters"].append(
            {"name": "x", "in": "path", "required": True, "schema": {"type": "string"}}
        )
    ),
    "a path parameter not required": mutated(
        lambda d: d["paths"][goal_show]["get"]["parameters"][0].__setitem__("required", False)
    ),
    "a schema that is not JSON Schema": mutated(
        lambda d: d["components"]["schemas"]["Error"]["properties"].__setitem__("error", {"type": "nope"})
    ),
    "a reference that does not resolve": mutated(
        lambda d: d["paths"][f"{PREFIX}/goals"]["get"]["responses"].__setitem__(
            "404", {"$ref": "#/components/responses/Nowhere"}
        )
    ),
    "not 3.1": mutated(lambda d: d.__setitem__("openapi", "3.0.3")),
    "no responses": mutated(lambda d: d["paths"][f"{PREFIX}/goals"]["get"].__setitem__("responses", {})),
    "an operationId twice": mutated(
        lambda d: d["paths"][f"{PREFIX}/goals"]["get"].__setitem__("operationId", "goal-show")
    ),
    "a security scheme that does not exist": mutated(lambda d: d.__setitem__("security", [{"nope": []}])),
}
check(
    "the checker refuses a document with each part broken",
    all(refused.values()),
    [k for k, v in refused.items() if not v],
)

# ── a real server ────────────────────────────────────────────────────────────────────────────────────────────────────
proj = Path(tempfile.mkdtemp(prefix="evh-openapi-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-openapi", EVH_ACTOR="person:test")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)
#: Every server this test started, stopped in the end whatever happened.
SERVERS: list[subprocess.Popen] = []


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj, env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip


def serve(*extra):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "catalog-serve", "--port", str(port), *extra],
        cwd=proj, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    SERVERS.append(p)
    for _ in range(200):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return port
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("the server did not start")


def call(port, method, path, headers=None, host=None, body=None):
    h = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 — the test's own server  # nosec B310
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), dict(exc.headers)


try:
    (proj / "data").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    built = evh("catalog")
    check("setup: an empty project and its catalog", built.returncode == 0, built.stderr[-300:])
    cli = evh("openapi")
    check(
        "evh openapi prints the document, offline",
        cli.returncode == 0 and json.loads(cli.stdout) == doc,
        cli.stderr[-300:],
    )

    port = serve()
    token = (proj / ".build" / "api-token").read_text().strip()
    bearer = {"Authorization": f"Bearer {token}"}
    url = f"{PREFIX}/openapi.json"
    st, body, hd = call(port, "GET", url, bearer)
    check(
        "GET /api/v1/openapi.json answers the document `evh openapi` prints",
        st == 200 and json.loads(body) == json.loads(cli.stdout) and "json" in hd.get("Content-Type", ""),
        (st, body[:200]),
    )
    st1, _b, _h = call(port, "GET", url)
    st2, _b, _h = call(port, "GET", url, {"Authorization": "Bearer nope"})
    st3, _b, _h = call(port, "GET", url, bearer, host="evil.example")
    st4, _b, _h = call(port, "GET", url, {**bearer, "Origin": "http://evil.example"})
    check(
        "only with the token, to this machine's Host and Origin: no token (401), a wrong one (401), another Host (403), a foreign Origin (403)",
        (st1, st2, st3, st4) == (401, 401, 403, 403),
        (st1, st2, st3, st4),
    )
    st, _b, hd = call(port, "GET", f"{PREFIX}/session?token={token}")
    st2, body2, _h = call(port, "GET", url, {"Cookie": (hd.get("Set-Cookie") or "").split(";")[0]})
    check(
        "the cookie the session route sets opens it too",
        st == 204 and st2 == 200 and json.loads(body2) == doc,
        (st, st2),
    )

    # What the document names is served: each read route without a part or a required input answers with a status
    # the document gives for it, and the two lists answer 200.
    unserved = []
    for op in OPS.values():
        if op.kind == "read" and not op.path_params() and not op.required:
            st, _b, _h = call(port, "GET", f"{PREFIX}{op.route}", bearer)
            if str(st) not in op_of(op)["responses"]:
                unserved.append((op.name, st))
    check(
        "every read route of the document that needs no id answers a status the document names",
        not unserved,
        unserved,
    )
    st, body, _h = call(port, "GET", f"{PREFIX}/goals", bearer)
    st2, body2, _h = call(port, "GET", f"{PREFIX}/datasets", bearer)
    check(
        "the answer of a read is the envelope the document describes",
        st == 200
        and st2 == 200
        and set(json.loads(body)) == {"command", "version", "result"}
        and json.loads(body)["command"] == "goal-list"
        and json.loads(body2)["command"] == "dataset-list",
        (st, st2),
    )
    st, body, _h = call(port, "GET", f"{PREFIX}/goals/nope", bearer)
    err = json.loads(body)
    check(
        "a refusal is the error envelope the document describes, at the status its kind has",
        st == 404
        and set(err) <= {"error", "kind", "problems"}
        and err.get("kind") == "not-found"
        and "404" in op_of(OPS["goal-show"])["responses"],
        (st, body[:200]),
    )

    data = {"X-EVH-Data": "1"}
    gone = {
        "GET /api/v1/commands": call(port, "GET", f"{PREFIX}/commands", bearer)[0],
        "GET /api/v1/commands (the data header)": call(port, "GET", f"{PREFIX}/commands", {**bearer, **data})[
            0
        ],
        "POST /api/v1/read/datasets": call(
            port, "POST", f"{PREFIX}/read/datasets", {**bearer, **data}, body={"args": {}}
        )[0],
        "GET /api/v1/read/datasets": call(port, "GET", f"{PREFIX}/read/datasets", bearer)[0],
    }
    check(
        "the removed routes answer 404: /api/v1/commands and /api/v1/read/<command>",
        set(gone.values()) == {404},
        gone,
    )
    SERVERS[0].terminate()
    SERVERS[0].wait(timeout=10)

    for mode in (("--public", "a.example"), ("--behind-proxy", "evals.example")):
        port = serve(*mode, *(("--bind", "0.0.0.0") if mode[0] == "--behind-proxy" else ()))  # noqa: S104 - a mode under test  # nosec B104
        st, _b, _h = call(port, "GET", url, {"Authorization": "Bearer x"}, host=mode[1])
        check(f"a server started {mode[0]} answers no /api/v1/openapi.json", st == 404, st)
finally:
    for p in SERVERS:
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
