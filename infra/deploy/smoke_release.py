#!/usr/bin/env python3
"""Start a rendered release's inspector and MCP server as compose.yml starts them on the box, and ask each what a
visitor asks: the release must answer before it is uploaded.

    python3 infra/deploy/smoke_release.py <release-dir>

The image, user, environment, working directory and command come from the release's own compose.yml; the release is
mounted read-only where the box mounts it. CI and the tests run the harness in a venv with every dependency installed,
so a module the box's PYTHONPATH does not carry fails only here: 0.8.1's public /api/v1 imported jsonschema, which the
inspector's vendored SDKs never held, and every read of the Workbench was a 500 in prod (EVALS-INSPECTOR-3,
2026-11-24). Needs docker; the hooks find no settings file and stay off, as they say they do.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import yaml

HOST = "evals.humancopilot.eu"
MOUNT = "/srv/evals/current"
#: What each service must answer, as a visitor asks it through Caddy (the Host the server accepts): path, the text the
#: answer contains. /api/v1/goals and /api/v1/models are the Workbench's first reads (the public read API, RFC-039).
ASKS = {
    "inspector": (
        ("/api/health", '"ok"'),
        ("/api/v1/goals", '"result"'),
        ("/api/v1/models", '"result"'),
        ("/workbench/", "<header"),
    ),
    "mcp": (("/mcp/health", '"ok"'),),
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def get(port: int, path: str) -> tuple[int, str]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": HOST})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310  # nosec B310 - the container just started
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def start(release: Path, name: str) -> tuple[int, str, str]:
    """The release's service `name`, started as its compose.yml says: (port, container, why it never answered or '')."""
    svc = yaml.safe_load((release / "compose.yml").read_text(encoding="utf-8"))["services"][name]
    port = free_port()
    cname = f"evals-smoke-{name}-{uuid.uuid4().hex[:8]}"
    env = [x for k, v in (svc.get("environment") or {}).items() for x in ("-e", f"{k}={v}")]
    cmd = [
        "docker", "run", "-d", "--rm", "--name", cname,
        "--user", str(svc["user"]), "--read-only", "--tmpfs", "/tmp",  # noqa: S108  # nosec B108 - the container's own tmpfs, as compose.yml mounts it
        "-v", f"{release.resolve()}:{MOUNT}:ro", "-w", svc["working_dir"],
        "-p", f"127.0.0.1:{port}:8080", *env, svc["image"], *[str(c) for c in svc["command"]],
    ]  # fmt: skip
    subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
    deadline = time.monotonic() + 120
    while True:
        try:
            code, _ = get(port, ASKS[name][0][0])
        except (urllib.error.URLError, ConnectionError, OSError):
            code = 0
        if code == 200:
            return port, cname, ""
        alive = subprocess.run(["docker", "inspect", cname], capture_output=True).returncode == 0
        if not alive or time.monotonic() > deadline:
            return (
                port,
                cname,
                f"{name}: never answered {ASKS[name][0][0]} (container {'up' if alive else 'gone'})",
            )
        time.sleep(1)


def stop(cname: str) -> None:
    subprocess.run(["docker", "stop", "-t", "2", cname], capture_output=True)


def run(release: Path, name: str) -> list[str]:
    """The service started from the release, each of its ASKS put to it; what failed, or nothing."""
    port, cname, why = start(release, name)
    failed: list[str] = [why] if why else []
    try:
        for path, text in () if why else ASKS[name]:
            code, body = get(port, path)
            ok = code == 200 and text in body
            print(f"  {'ok' if ok else 'FAIL'}  {name} GET {path}: {code}")
            if not ok:
                failed.append(f"{name} GET {path}: {code} {body[:200]!r}")
    finally:
        if failed:
            logs = subprocess.run(
                ["docker", "logs", "--tail", "40", cname], capture_output=True, text=True, encoding="utf-8"
            )
            print(logs.stdout + logs.stderr)
        stop(cname)
    return failed


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.splitlines()[2].strip())
        return 2
    release = Path(sys.argv[1])
    if not shutil.which("docker"):
        print("SMOKE: FAIL - docker is not on PATH")
        return 1
    failed = [f for name in ASKS for f in run(release, name)]
    for f in failed:
        print(f"::error::{f}")
    print(f"SMOKE: {'FAIL' if failed else 'PASS'} ({json.dumps(sorted(ASKS))})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
