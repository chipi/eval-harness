#!/usr/bin/env python3
"""Two projects on one machine share nothing (ADR-0024): each serves its catalog and its MCP endpoint on a port of
its own, the same every time; each catalog names its project; a shell whose EVAL_HOME points at one project says
so when used in the other; model records are locked by their own path.

    python tests/test_parallel_projects.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _common, _models  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

top = Path(tempfile.mkdtemp(prefix="evh-parallel-"))
env = {k: v for k, v in os.environ.items() if not k.startswith("EVAL_")}


def evh(proj: Path, *args: str, extra: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        # Each project is its own: run from a checkout, the harness would take the checkout as the project.
        env={**env, "EVAL_HOME": str(proj), **(extra or {})},
        capture_output=True,
        text=True,
        timeout=600,
    )


projects = {}
for name in ("alpha", "beta"):
    p = top / name
    p.mkdir()
    r = evh(p, "init", "--tutorial")
    check(f"init {name}", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    r = evh(p, "catalog")
    check(f"catalog {name}", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    projects[name] = p


def serve(proj: Path, *args: str) -> tuple[subprocess.Popen, str]:
    """Start a server in its project and return it with the first address it prints."""
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env={**env, "EVAL_HOME": str(proj)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline, url = time.time() + 60, ""
    while time.time() < deadline and not url:
        line = p.stdout.readline() if p.stdout else ""
        m = re.search(r"http://127\.0\.0\.1:(\d+)\S*", line)
        url = m.group(0) if m else ""
        if not line and p.poll() is not None:
            break
    return p, url


def stop(p: subprocess.Popen) -> None:
    p.terminate()
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        p.kill()


def port(url: str) -> int:
    m = re.search(r":(\d+)", url)
    return int(m.group(1)) if m else 0


# ── catalog-serve: a port each, both at once, each its own catalog ───────────────────────────────
a, url_a = serve(projects["alpha"], "catalog-serve")
b, url_b = serve(projects["beta"], "catalog-serve")
try:
    check(
        "catalog-serve: each project on its own port, in the catalog range",
        url_a
        and url_b
        and port(url_a) != port(url_b)
        and all(18000 <= port(u) < 19000 for u in (url_a, url_b)),
        f"{url_a} {url_b}",
    )
    pages = {}
    for name, url in (("alpha", url_a), ("beta", url_b)):
        try:
            with urllib.request.urlopen(url + "index.html", timeout=10) as resp:  # noqa: S310 — the test's own server on 127.0.0.1  # nosec B310
                pages[name] = resp.read().decode()
        except OSError as exc:
            pages[name] = f"unreachable: {exc}"
    check(
        "each serves its own catalog, naming its project in the title and the header",
        "· alpha</title>" in pages["alpha"]
        and "· beta</title>" in pages["beta"]
        and 'class="proj"> · alpha' in pages["alpha"],
        pages["alpha"][:300] + " | " + pages["beta"][:300],
    )
finally:
    stop(a)
    stop(b)
again, url_a2 = serve(projects["alpha"], "catalog-serve")
stop(again)
check("catalog-serve: the same port every time", port(url_a2) == port(url_a), f"{url_a} then {url_a2}")
held, url_h = serve(projects["alpha"], "catalog-serve")
other, url_o = serve(projects["alpha"], "catalog-serve")
stop(held)
stop(other)
check(
    "catalog-serve: when its port is held, the next free one",
    port(url_h) == port(url_a) and port(url_o) not in (0, port(url_a)),
    f"{url_h} {url_o}",
)

# ── mcp --http: the project's own port, in its range ───────────────────────────────────────────
m, url_m = serve(projects["alpha"], "mcp", "--http")
stop(m)
check(
    "mcp --http: the project's own port, at the same offset as its catalog's",
    port(url_m) - 19000 == port(url_a) - 18000,
    f"{url_m} beside {url_a}",
)

# ── EVAL_HOME pointing at another project ─────────────────────────────────────────────────────
r = evh(projects["beta"], "datasets", extra={"EVAL_HOME": str(projects["alpha"])})
check(
    "a shell's EVAL_HOME at another project is named",
    "note: EVAL_HOME is" in r.stderr and "alpha" in r.stderr and "beta" in r.stderr,
    r.stderr[-300:],
)
r = evh(projects["alpha"], "datasets", extra={"EVAL_HOME": str(projects["alpha"])})
check("no note when EVAL_HOME is the project you are in", "EVAL_HOME" not in r.stderr, r.stderr[-300:])

# ── model records: locked by their own path ───────────────────────────────────────────────────
la = _models.lock_path(projects["alpha"] / "data" / "models" / "m.yaml")
lb = _models.lock_path(projects["beta"] / "data" / "models" / "m.yaml")
check("a model of one name in two projects: two locks", la != lb, f"{la} {lb}")
check(
    "port_offset: two projects, two offsets (fixed paths, so it is never luck)",
    _common.port_offset(Path("/srv/p/alpha")) != _common.port_offset(Path("/srv/p/beta"))
    and _common.port_offset(Path("/srv/p/alpha")) == _common.port_offset(Path("/srv/p/alpha")),
)
check(
    "project_port: the same root, the same port",
    _common.project_port("catalog", projects["beta"]) == _common.project_port("catalog", projects["beta"]),
)

shutil.rmtree(top, ignore_errors=True)
sys.exit(summary())
