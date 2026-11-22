"""The API's OpenAPI 3.1 description (RFC-032), made from the operations: `GET /api/v1/openapi.json` and `evh openapi`
print the same document. Every operation is a path and a method; its route's parts are path parameters, a read's inputs
query parameters, an edit's inputs a JSON body, with `by` (RFC-027) and the data header. A decision or a work operation
is a job (P3): its POST answers 202 with the job, its body the inputs the route's parts do not fill with `by`, `for` and
`max_cost_usd`. The job routes and the few routes that are not an operation are described here, by what `catalog_serve`
does with them.

OpenAPI 3.1 takes JSON Schema 2020-12 as is, which is what the operations' inputs are written in."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from evaluation_harness.ops.registry import OPS, Op

#: A refusal of the model's, as an HTTP status (the kinds are `_common.REFUSALS`).
REFUSAL_STATUS = {
    "not-found": 404,
    "bad-argument": 400,
    "invalid-file": 422,
    "would-overwrite": 409,
    "not-allowed": 409,
    "old-format": 409,
    "mismatch": 409,
}
DIALECT = "https://json-schema.org/draft/2020-12/schema"
PREFIX = "/api/v1"

_ERROR = "#/components/schemas/Error"
_JOB = "#/components/schemas/Job"


def _kinds(status: int) -> str:
    return ", ".join(k for k, s in REFUSAL_STATUS.items() if s == status)


def _responses() -> dict[str, Any]:
    def err(description: str) -> dict[str, Any]:
        return {
            "description": description,
            "content": {"application/json": {"schema": {"$ref": _ERROR}}},
        }

    return {
        "BadRequest": err(f"an input that is not what the schema says, or a refusal of kind {_kinds(400)}"),
        "Unauthorized": err("no token, or a wrong one"),
        "Forbidden": err("another Host or a foreign Origin; a call that is not a read without X-EVH-Data: 1"),
        "NotFound": err(f"no such route, or a refusal of kind {_kinds(404)}"),
        "Conflict": err(f"a refusal of kind {_kinds(409)}"),
        "TooLarge": err("a body over the most the route takes"),
        "Invalid": err(
            f"a refusal of kind {_kinds(422)}: the record does not check, each problem with its field"
        ),
        "Migrating": err("a migration holds the project; try again when it ends (Retry-After)"),
    }


def _ref(name: str) -> dict[str, Any]:
    return {"$ref": f"#/components/responses/{name}"}


def _errors(*names: str) -> dict[str, Any]:
    codes = {
        "BadRequest": "400",
        "Unauthorized": "401",
        "Forbidden": "403",
        "NotFound": "404",
        "Conflict": "409",
        "TooLarge": "413",
        "Invalid": "422",
        "Migrating": "503",
    }
    return {codes[n]: _ref(n) for n in names}


def _json_body(schema: dict[str, Any], required: bool = True) -> dict[str, Any]:
    return {"required": required, "content": {"application/json": {"schema": schema}}}


def _data_header() -> dict[str, Any]:
    return {
        "name": "X-EVH-Data",
        "in": "header",
        "required": True,
        "description": "a call that is not a read carries it (a page of another origin cannot send it, ADR-0027)",
        "schema": {"type": "string", "const": "1"},
    }


def _path(path: str) -> list[dict[str, Any]]:
    return [
        {
            "name": p[1:-1],
            "in": "path",
            "required": True,
            "description": f"the {p[1:-1].replace('_', ' ')}'s id",
            "schema": {"type": "string"},
        }
        for p in path.split("/")
        if p.startswith("{") and p.endswith("}")
    ]


def _write_body(op: Op) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            **op.inputs,
            "by": {
                "type": "string",
                "pattern": "^(person|agent):",
                "description": "who acted, person:NAME or agent:NAME (RFC-027)",
            },
            "for": {
                "type": "string",
                "description": "the person an agent acts for, person:NAME: needed when by is an agent",
            },
        },
        "required": [*op.required, "by"],
        "additionalProperties": False,
    }


def _job_body(op: Op) -> dict[str, Any]:
    """A job operation's request body: the inputs its route's parts do not fill, and who asked, for whom and the cap."""
    own = op.schema()
    return {
        "type": "object",
        "properties": {
            **own["properties"],
            "by": {
                "type": "string",
                "pattern": "^(person|agent):",
                "description": "who asked, person:NAME or agent:NAME (RFC-027); the job's actor",
            },
            "for": {
                "type": "string",
                "description": "the person an agent acts for, person:NAME: needed when by is an agent",
            },
            "max_cost_usd": {
                "type": "number",
                "exclusiveMinimum": 0,
                "description": "the most the job may spend"
                + ("; required" if op.spends else ": this operation does not spend, so it takes none"),
            },
        },
        "required": [*own["required"], "by", *(["max_cost_usd"] if op.spends else [])],
        "additionalProperties": False,
        **({"anyOf": own["anyOf"]} if "anyOf" in own else {}),
        **({"allOf": own["allOf"]} if "allOf" in own else {}),
    }


def _locks_doc(op: Op) -> Any:
    """What the job holds, as the description says it: `project` (a migration holds the whole project), the templates
    of its locks, and the function that adds the others."""
    if op.locks == "project":
        return "project"
    return {
        "templates": [{"key": k, "exclusive": bool(ex)} for k, ex in op.locks or ()],
        **({"function": op.locks_fn} if op.locks_fn else {}),
    }


def _job_operation(op: Op) -> dict[str, Any]:
    out: dict[str, Any] = {
        "operationId": op.name,
        "summary": op.about,
        "tags": [op.route.strip("/").split("/")[0]],
        "x-evh-kind": op.kind,
        "x-evh-locks": _locks_doc(op),
        "x-evh-spends": op.spends,
        "parameters": [*_path(op.route), _data_header()],
        "requestBody": _json_body(_job_body(op)),
        "responses": {
            "202": {
                "description": "the job, queued or started: follow it at GET /jobs/{id}",
                "content": {"application/json": {"schema": {"$ref": _JOB}}},
            },
            **_errors(
                "BadRequest",
                "Unauthorized",
                "Forbidden",
                "NotFound",
                "Conflict",
                "TooLarge",
                "Invalid",
                "Migrating",
            ),
        },
    }
    return out


def _operation(op: Op) -> dict[str, Any]:
    if op.is_job():
        return _job_operation(op)
    result = op.output or {"type": "object"}
    envelope = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "const": op.name},
            "version": {"type": "string", "description": "the harness's version"},
            "result": result,
        },
        "required": ["command", "version", "result"],
    }
    out: dict[str, Any] = {
        "operationId": op.name,
        "summary": op.about,
        "tags": [op.route.strip("/").split("/")[0]],
        "x-evh-kind": op.kind,
        "parameters": _path(op.route),
    }
    if op.kind == "read":
        out["parameters"] += [
            {
                "name": name,
                "in": "query",
                "required": name in op.required,
                "description": spec.get("description", ""),
                "schema": spec,
            }
            for name, spec in op.inputs.items()
        ]
        names: tuple[str, ...] = (
            "BadRequest",
            "Unauthorized",
            "Forbidden",
            "NotFound",
            "Conflict",
            "Invalid",
            "Migrating",
        )
    else:
        out["parameters"].append(_data_header())
        out["requestBody"] = _json_body(_write_body(op))
        names = (
            "BadRequest", "Unauthorized", "Forbidden", "NotFound", "Conflict", "TooLarge", "Invalid", "Migrating",
        )  # fmt: skip
    out["responses"] = {
        "200": {
            "description": "the operation's answer",
            "content": {"application/json": {"schema": envelope}},
        },
        **_errors(*names),
    }
    return out


def _job_paths() -> dict[str, Any]:
    job_id = {
        "name": "id",
        "in": "path",
        "required": True,
        "description": "the job's id",
        "schema": {"type": "string"},
    }
    job = {"application/json": {"schema": {"$ref": _JOB}}}
    read = ("Unauthorized", "Forbidden", "NotFound", "Migrating")
    write = ("BadRequest", "Unauthorized", "Forbidden", "NotFound", "Conflict", "Migrating")
    return {
        f"{PREFIX}/jobs": {
            "get": {
                "operationId": "jobs-list",
                "summary": "the jobs, newest first",
                "tags": ["jobs"],
                "parameters": [
                    {
                        "name": "state",
                        "in": "query",
                        "required": False,
                        "description": "only the jobs in these states: repeated, or comma-separated "
                        "(`queued,running,running (unsupervised)`); 400 for a state a job is never in",
                        "schema": {"type": "array", "items": {"type": "string"}},
                        "style": "form",
                        "explode": True,
                    },
                    {
                        "name": "operation",
                        "in": "query",
                        "required": False,
                        "description": "only the jobs of this operation",
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "goal",
                        "in": "query",
                        "required": False,
                        "description": "only the jobs whose inputs name this goal",
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "offset",
                        "in": "query",
                        "required": False,
                        "description": "skip this many of the jobs found",
                        "schema": {"type": "integer", "minimum": 0, "default": 0},
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "description": "at most this many (0: every one)",
                        "schema": {"type": "integer", "minimum": 0, "default": 0},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "the jobs",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "jobs": {"type": "array", "items": {"$ref": _JOB}},
                                        "total": {
                                            "type": "integer",
                                            "description": "the jobs found, before offset and limit",
                                        },
                                    },
                                    "required": ["jobs", "total"],
                                }
                            }
                        },
                    },
                    **_errors(*read),
                },
            },
            "post": {
                "operationId": "jobs-start",
                "summary": "start a job: an operation and its inputs; checked, written, started; refused before a job "
                "exists when it cannot run",
                "tags": ["jobs"],
                "parameters": [_data_header()],
                "requestBody": _json_body(
                    {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": sorted(op.name for op in OPS.values() if op.is_job()),
                                "description": "the operation to run (a decision or a work operation); its resource "
                                "route starts the same job",
                            },
                            "inputs": {
                                "type": "object",
                                "description": "the operation's inputs by name, the route's parts too; a file as "
                                "base64 where the operation takes an upload",
                                "additionalProperties": True,
                            },
                            "by": {
                                "type": "string",
                                "description": "who started it, person:NAME or agent:NAME",
                            },
                            "for": {"type": "string", "description": "the person an agent acts for"},
                            "max_cost_usd": {
                                "type": "number",
                                "exclusiveMinimum": 0,
                                "description": "the most a spending job may spend; required for one",
                            },
                        },
                        "required": ["operation"],
                        "additionalProperties": False,
                    }
                ),
                "responses": {
                    "202": {"description": "the job, started", "content": job},
                    **_errors("BadRequest", "Unauthorized", "Forbidden", "NotFound", "TooLarge", "Migrating"),
                },
            },
        },
        f"{PREFIX}/jobs/{{id}}": {
            "get": {
                "operationId": "jobs-show",
                "summary": "one job: its state, what it waits for, how it ended",
                "tags": ["jobs"],
                "parameters": [job_id],
                "responses": {"200": {"description": "the job", "content": job}, **_errors(*read)},
            }
        },
        f"{PREFIX}/jobs/{{id}}/log": {
            "get": {
                "operationId": "jobs-log",
                "summary": "a job's log from a byte on",
                "tags": ["jobs"],
                "parameters": [
                    job_id,
                    {
                        "name": "from",
                        "in": "query",
                        "required": False,
                        "description": "the byte to start at (default 0)",
                        "schema": {"type": "integer", "minimum": 0},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "the log text and the byte to ask from next",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"log": {"type": "string"}, "next": {"type": "integer"}},
                                    "required": ["log", "next"],
                                }
                            }
                        },
                    },
                    **_errors(*read),
                },
            }
        },
        f"{PREFIX}/jobs/{{id}}/files/{{name}}": {
            "get": {
                "operationId": "jobs-file",
                "summary": "a file the job wrote in its folder (not its own state files)",
                "tags": ["jobs"],
                "parameters": [
                    job_id,
                    {
                        "name": "name",
                        "in": "path",
                        "required": True,
                        "description": "the file's name",
                        "schema": {"type": "string"},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "the file",
                        "content": {
                            "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
                        },
                    },
                    **_errors(*read),
                },
            }
        },
        f"{PREFIX}/jobs/{{id}}/stop": {
            "post": {
                "operationId": "jobs-stop",
                "summary": "stop a job: its process group, cancelled",
                "tags": ["jobs"],
                "parameters": [job_id, _data_header()],
                "responses": {"200": {"description": "the job, stopped", "content": job}, **_errors(*write)},
            }
        },
        f"{PREFIX}/jobs/{{id}}/resume": {
            "post": {
                "operationId": "jobs-resume",
                "summary": "resume a stopped or lost run, as a new job with what the first left of its cap",
                "tags": ["jobs"],
                "parameters": [job_id, _data_header()],
                "responses": {
                    "202": {"description": "the new job, started", "content": job},
                    **_errors(*write),
                },
            }
        },
    }


def _other_paths() -> dict[str, Any]:
    plain = {"application/json": {"schema": {"type": "object"}}}
    return {
        f"{PREFIX}/openapi.json": {
            "get": {
                "operationId": "openapi-show",
                "summary": "this description (`evh openapi` prints the same)",
                "tags": ["api"],
                "responses": {
                    "200": {"description": "an OpenAPI 3.1 document", "content": plain},
                    **_errors("Unauthorized", "Forbidden", "Migrating"),
                },
            }
        },
        f"{PREFIX}/estimate": {
            "post": {
                "operationId": "jobs-estimate",
                "summary": "a job operation's own dry run, run now (it calls nothing and writes nothing): what the "
                "job would do and, for an operation that spends, its cost",
                "tags": ["jobs"],
                "parameters": [_data_header()],
                "requestBody": _json_body(
                    {
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": sorted(
                                    op.name for op in OPS.values() if op.is_job() and "dry_run" in op.inputs
                                ),
                                "description": "the operation (one with a dry_run input)",
                            },
                            "inputs": {"type": "object", "additionalProperties": True},
                        },
                        "required": ["operation"],
                        "additionalProperties": False,
                    }
                ),
                "responses": {
                    "200": {
                        "description": "what the dry run printed",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "operation": {"type": "string"},
                                        "version": {"type": "string"},
                                        "exit": {"type": "integer"},
                                        "text": {"type": "string", "description": "what the dry run printed"},
                                        "result": {
                                            "type": ["object", "null"],
                                            "description": "its answer as data (the operation's --json result)",
                                        },
                                    },
                                    "required": ["operation", "version", "exit", "text", "result"],
                                }
                            }
                        },
                    },
                    **_errors("BadRequest", "Unauthorized", "Forbidden", "NotFound", "TooLarge", "Migrating"),
                },
            }
        },
        f"{PREFIX}/session": {
            "get": {
                "operationId": "session-open",
                "summary": "trade the token for the cookie (HttpOnly, SameSite=Strict); with next, a redirect to a "
                "page of this server",
                "tags": ["api"],
                "security": [],
                "parameters": [
                    {
                        "name": "token",
                        "in": "query",
                        "required": True,
                        "description": "the server's token",
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "next",
                        "in": "query",
                        "required": False,
                        "description": "a path of this server to go on to",
                        "schema": {"type": "string", "pattern": "^/"},
                    },
                ],
                "responses": {
                    "204": {"description": "the cookie is set"},
                    "303": {"description": "the cookie is set; on to next"},
                    **_errors("Unauthorized", "Forbidden"),
                },
            }
        },
    }


def document() -> dict[str, Any]:
    """The OpenAPI 3.1 document of the API, made from the operations."""
    from evaluation_harness._version import __version__  # noqa: PLC0415

    paths: dict[str, Any] = {}
    for op in OPS.values():
        item = paths.setdefault(f"{PREFIX}{op.route}", {})
        if op.method.lower() in item:
            raise ValueError(f"{op.method} {op.route} is declared twice")
        item[op.method.lower()] = _operation(op)
    for path, item in {**_job_paths(), **_other_paths()}.items():
        paths.setdefault(path, {}).update(item)
    return {
        "openapi": "3.1.0",
        "jsonSchemaDialect": DIALECT,
        "info": {
            "title": "Eval harness API",
            "version": __version__,
            "description": "The model's entities as resources and its operations as actions, on this machine only. "
            "Every call carries the server's token (.build/api-token) as a bearer or as the cookie "
            "GET /api/v1/session sets, to a 127.0.0.1 or localhost Host and no foreign Origin; a call "
            "that is not a read carries X-EVH-Data: 1. A server started --public or behind a proxy "
            "answers none of it.",
        },
        "security": [{"bearerAuth": []}, {"cookieAuth": []}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Authorization: Bearer <token>",
                },
                "cookieAuth": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "evh_token",
                    "description": "the cookie GET /api/v1/session sets",
                },
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "kind": {"type": "string", "enum": [*REFUSAL_STATUS]},
                        "problems": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "for a record that does not check, each problem with the field it is at",
                        },
                    },
                    "required": ["error"],
                },
                "Job": {
                    "type": "object",
                    "description": "a job (RFC-026): its id, the operation and its inputs, state, who started it, its "
                    "locks and how it ended",
                    "properties": {
                        "id": {"type": "string"},
                        "operation": {"type": "string"},
                        "inputs": {"type": "object"},
                        "state": {"type": "string"},
                        "state_label": {
                            "type": "string",
                            "description": 'the state a person reads: `state`, but "checked, flagged" for a job that '
                            "ended failed with exit 6 (its checks ran and flagged something)",
                        },
                        "progress": {
                            "type": ["object", "null"],
                            "description": "how far it has got, as its operation last said (run: items, sweep: arms, "
                            "judge-score: verdict tasks, rescore: runs); null for one that says nothing",
                            "properties": {
                                "done": {"type": "integer"},
                                "total": {"type": ["integer", "null"]},
                                "at": {"type": "string"},
                            },
                        },
                        "spent_usd": {"type": "number", "description": "what it has spent so far"},
                    },
                    "required": ["id", "operation", "inputs", "state"],
                    "additionalProperties": True,
                },
            },
            "responses": _responses(),
        },
    }


def main(argv: list[str] | None = None) -> int:
    """evh openapi: the document, as JSON."""
    from evaluation_harness._common import evh_prog  # noqa: PLC0415

    argparse.ArgumentParser(
        prog=evh_prog(), description="the API's OpenAPI 3.1 description, made from the operations, as JSON"
    ).parse_args(argv)
    print(json.dumps(document(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
