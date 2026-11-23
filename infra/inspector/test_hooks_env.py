#!/usr/bin/env python3
"""Dev and prod observability for both servers' hooks (hooks_env.py): a dev run labels every error, span and log line
with environment=dev and its worktree and reports to the dev project only; prod is as it was; a run that would cross
is refused. Nothing leaves the machine: GlitchTip events are kept by a transport of the test's, log lines go to a
local server, spans are read from the tracer.

    PYTHONPATH=harness/.build/vendor python infra/inspector/test_hooks_env.py
    make budget-check        (vendors the SDKs, then runs this)

Each case runs in a process of its own (the SDKs keep global state): this file, run with the case's name.
"""

from __future__ import annotations

import http.server
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import ClassVar

HERE = Path(__file__).resolve().parent
INFRA = HERE.parent
DEV_DSN, PROD_DSN, MCP_PROD_DSN = (
    "http://k@127.0.0.1:9/40",
    "http://k@127.0.0.1:9/37",
    "http://k@127.0.0.1:9/38",
)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _capture_sentry() -> list:
    """GlitchTip events as the hooks would send them, kept here: the SDK's init given this transport."""
    import sentry_sdk  # noqa: PLC0415
    from sentry_sdk.transport import Transport  # noqa: PLC0415

    events: list = []

    class Keep(Transport):
        def capture_envelope(self, envelope):
            ev = envelope.get_event()
            if ev is not None:
                events.append(ev)

    real = sentry_sdk.init
    sentry_sdk.init = lambda **kw: real(transport=Keep, **kw)
    return events


class _Logs(http.server.BaseHTTPRequestHandler):
    got: ClassVar[list] = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Logs.got.append(
            {
                "path": self.path,
                "type": self.headers["Content-Type"],
                "lines": [json.loads(x) for x in body.splitlines()],
            }
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


def _log_server() -> str:
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Logs)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/insert/jsonline"


def _wait_logs(n: int) -> list:
    for _ in range(80):
        lines = [x for b in _Logs.got for x in b["lines"]]
        if len(lines) >= n:
            return lines
        time.sleep(0.1)
    return [x for b in _Logs.got for x in b["lines"]]


def case(name: str) -> dict:
    """One case, in this process; what it saw, as JSON for the parent to check."""
    out: dict = {}
    if name == "env-unit":
        env = _load(HERE / "hooks_env.py", "evals_hooks_env")
        modes = {}
        for v in (None, "dev", "PROD", "staging"):
            os.environ.pop("EVALS_ENV", None)
            if v is not None:
                os.environ["EVALS_ENV"] = v
            modes[str(v)] = env.mode()
        out["modes"] = modes
        out["refused"] = {
            f"{m}:{d.rsplit('/', 1)[1]}": env.dsn_refused(d, m)
            for m in ("dev", "prod")
            for d in (DEV_DSN, PROD_DSN, MCP_PROD_DSN, "http://k@127.0.0.1:9/1")
        }
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "dsn.env").write_text(f"SENTRY_DSN={DEV_DSN}\n", encoding="utf-8")
            (Path(td) / "dev.env").write_text(
                f"SENTRY_DSN_FILE={td}/dsn.env\nEVALS_LOGS_URL=http://x/insert/jsonline\n", encoding="utf-8"
            )
            os.environ["EVALS_OBS_ENV"] = f"{td}/dev.env"
            out["settings"] = env.settings("dev", ("EVALS_LOGS_URL",))
            os.environ["EVALS_LOGS_URL"] = "http://override/insert/jsonline"
            out["override"] = env.settings("dev", ("EVALS_LOGS_URL",))["EVALS_LOGS_URL"]
        os.environ["EVALS_WORKTREE"] = "feature/x"
        out["worktree_set"] = env.worktree()
        del os.environ["EVALS_WORKTREE"]
        out["worktree_git"] = env.worktree()
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "RELEASE").write_text("0123456789abcdef\n", encoding="utf-8")
            out["release_file"] = env.release(Path(td) / "RELEASE", "prod")
        out["release_dev"] = env.release(Path("/nonexistent"), "dev")
        out["release_prod"] = env.release(Path("/nonexistent"), "prod")
        return out
    if name == "exit-flush":
        env = _load(HERE / "hooks_env.py", "evals_hooks_env")
        push = env.LogPush(
            os.environ["TEST_LOGS_URL"], {"service": "s", "environment": "dev", "worktree": "w"}
        )
        for i in range(3):
            push.log(f"line {i}")
        return {"queued": 3}  # and the process ends at once, well inside the worker's two seconds
    events = _capture_sentry()
    logs_url = _log_server()
    os.environ["EVALS_LOGS_URL"] = logs_url
    os.environ["EVALS_OBS_ENV"] = "/nonexistent"
    os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = "http://127.0.0.1:9/v1/traces"
    os.environ["EVALS_WORKTREE"] = "branch-under-test"
    service, mode, dsn_key, dsn = name.split(":", 3)
    if mode == "dev":
        os.environ["EVALS_ENV"] = "dev"
    os.environ[dsn_key] = dsn
    if service == "inspector":
        hooks = _load(HERE / "hooks.py", "hooks")
        hooks.start({})
        hooks.request({"route": "/api/compare", "status": 200, "ms": 12.5, "method": "GET"})
        hooks.error(RuntimeError("boom"), {"route": "/api/compare"})
        from opentelemetry import trace  # noqa: PLC0415

        provider = trace.get_tracer_provider()
        out["resource"] = (
            dict(getattr(provider, "resource", None).attributes) if hasattr(provider, "resource") else {}
        )
    else:
        # The deployed layout: mcp_hooks.py beside hooks_env.py and mcp_umami.json (render.sh), Umami's URL set.
        d = Path(tempfile.mkdtemp())
        shutil.copy(INFRA / "mcp" / "hooks.py", d / "mcp_hooks.py")
        shutil.copy(HERE / "hooks_env.py", d / "hooks_env.py")
        (d / "mcp_umami.json").write_text('{"website_id": "w"}', encoding="utf-8")
        os.environ["UMAMI_SEND_URL"] = "https://127.0.0.1:9/api/send"
        hooks = _load(d / "mcp_hooks.py", "mcp_hooks")
        hooks.start({"tools": ["goal-list"]})
        hooks.request({"tool": "goal-list", "exit": 0, "ms": 40, "args": ["goal"]})
        hooks.error(RuntimeError("boom"), {"tool": "goal-list"})
        out["umami"] = hooks._state["umami"] is not None
        tracer = hooks._state["tracer"]
        out["resource"] = dict(tracer.resource.attributes) if tracer is not None else {}
    import sentry_sdk  # noqa: PLC0415

    sentry_sdk.flush(5)
    out["sentry"] = hooks._state["sentry"]
    out["events"] = [{"environment": e.get("environment"), "tags": e.get("tags") or {}} for e in events]
    out["logs"] = hooks._state["logs"] is not None
    out["lines"] = _wait_logs(3) if out["logs"] else []
    out["log_requests"] = [{"path": b["path"], "type": b["type"]} for b in _Logs.got]
    return out


def run(name: str, extra: dict | None = None) -> dict:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("EVALS_", "SENTRY_", "MCP_SENTRY", "OTEL_", "UMAMI"))
    }
    r = subprocess.run(
        [sys.executable, __file__, name],
        capture_output=True,
        text=True,
        env={**env, **(extra or {})},
        timeout=120,
        encoding="utf-8",
    )
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"failed": r.stdout[-800:] + r.stderr[-1500:]}


def main() -> int:
    sys.path.insert(0, str(INFRA.parent / "harness"))
    from evaluation_harness._check import check, summary  # noqa: PLC0415

    u = run("env-unit")
    check(
        "EVALS_ENV: unset is prod, dev is dev (any case), anything else is off",
        u.get("modes") == {"None": "prod", "dev": "dev", "PROD": "prod", "staging": "off"},
        u,
    )
    r = u.get("refused", {})
    check(
        "a dev run reports to the dev project only, a prod run never to it",
        r.get("dev:40") == "" and "evals-inspector" in r.get("dev:37", "") and "evals-mcp" in r.get("dev:38", "")
        and r.get("dev:1") and "dev project" in r.get("prod:40", "") and r.get("prod:37") == "" and r.get("prod:1") == "",
        r,
    )  # fmt: skip
    check(
        "dev settings: the DSN read from the file SENTRY_DSN_FILE names; the environment over the file",
        u.get("settings", {}).get("SENTRY_DSN") == DEV_DSN
        and u.get("override") == "http://override/insert/jsonline",
        u.get("settings"),
    )
    branch = subprocess.run(
        ["git", "-C", str(HERE), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    check(
        "the release: sha-<7> from the release's file; with none, dev-<7> of this commit in dev, unknown in prod",
        u.get("release_file") == "sha-0123456"
        and u.get("release_dev")
        == "dev-"
        + subprocess.run(
            ["git", "-C", str(HERE), "rev-parse", "--short=7", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        and u.get("release_prod") == "unknown",
        (u.get("release_file"), u.get("release_dev"), u.get("release_prod")),
    )
    url = _log_server()
    run("exit-flush", {"TEST_LOGS_URL": url})
    got = _wait_logs(3)
    check(
        "log lines queued when the process ends are sent then, not lost with the worker's batch",
        [x.get("_msg") for x in got] == ["line 0", "line 1", "line 2"],
        got,
    )
    _Logs.got.clear()
    check(
        "the worktree label: EVALS_WORKTREE when set, else this checkout's git branch",
        u.get("worktree_set") == "feature/x" and u.get("worktree_git") == branch,
        (u.get("worktree_set"), u.get("worktree_git"), branch),
    )

    for service, dsn_key, prod_dsn in (
        ("inspector", "SENTRY_DSN", PROD_DSN),
        ("mcp", "MCP_SENTRY_DSN", MCP_PROD_DSN),
    ):
        dev = run(f"{service}:dev:SENTRY_DSN:{DEV_DSN}")
        ev = (dev.get("events") or [{}])[0]
        check(
            f"{service} in dev: its error reaches GlitchTip as environment dev, tagged with the worktree and the service",
            dev.get("sentry") and ev.get("environment") == "dev"
            and ev.get("tags", {}).get("worktree") == "branch-under-test"
            and ev.get("tags", {}).get("service") == f"evals-{service}",
            dev,
        )  # fmt: skip
        check(
            f"{service} in dev: its spans' resource says deployment.environment dev and the worktree",
            dev.get("resource", {}).get("deployment.environment") == "dev"
            and dev.get("resource", {}).get("worktree") == "branch-under-test",
            dev.get("resource"),
        )
        lines = dev.get("lines") or []
        check(
            f"{service} in dev: log lines (the start, the call, the error) reach VictoriaLogs' jsonline endpoint with "
            "the stream fields and the content type it keeps, each labelled",
            len(lines) >= 3
            and all(x.get("environment") == "dev" and x.get("worktree") == "branch-under-test"
                    and x.get("service") == f"evals-{service}" for x in lines)
            and any(x.get("level") == "error" for x in lines)
            and all(q["type"] == "application/stream+json"
                    and q["path"].endswith("_stream_fields=service,environment,worktree") for q in dev["log_requests"]),
            (lines, dev.get("log_requests")),
        )  # fmt: skip
        if service == "mcp":
            check(
                "mcp in dev: no Umami event, even with Umami's URL set (a dev run is not a visit)",
                dev.get("umami") is False,
                dev,
            )
        crossed = run(f"{service}:dev:SENTRY_DSN:{prod_dsn}")
        check(
            f"{service} in dev with a prod GlitchTip project: refused, nothing sent there",
            crossed.get("sentry") is False and crossed.get("events") == [],
            crossed,
        )
        prod = run(f"{service}:prod:{dsn_key}:{prod_dsn}")
        pev = (prod.get("events") or [{}])[0]
        check(
            f"{service} in prod: as before, environment prod, no worktree, no log push (the box's collector reads stdout)",
            prod.get("sentry") and pev.get("environment") == "prod" and "worktree" not in pev.get("tags", {})
            and prod.get("resource", {}).get("deployment.environment") == "prod"
            and "worktree" not in prod.get("resource", {}) and prod.get("logs") is False,
            prod,
        )  # fmt: skip
        if service == "mcp":
            check("mcp in prod: Umami on, as before", prod.get("umami") is True, prod)
        into_dev = run(f"{service}:prod:{dsn_key}:{DEV_DSN}")
        check(
            f"{service} in prod with the dev project's DSN: refused",
            into_dev.get("sentry") is False and into_dev.get("events") == [],
            into_dev,
        )
    return summary()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(json.dumps(case(sys.argv[1]), default=str))
        sys.exit(0)
    sys.exit(main())
