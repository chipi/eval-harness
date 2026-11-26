#!/usr/bin/env python3
"""Release smoke: does the built release work for a newcomer and for the deployment, in a few minutes, for $0.

    python harness/tools/release_smoke.py                  # or: make release-smoke
    python harness/tools/release_smoke.py --list           # the checks, without running any
    python harness/tools/release_smoke.py --only 1,3       # some of them (3 and 4 build the install of 2 first)
    python harness/tools/release_smoke.py --release        # also render the release and run its container checks

It ends with `RELEASE SMOKE: PASS` (exit 0) or `RELEASE SMOKE: FAIL (n of m)` (exit 1), one `ok` or `FAIL` line
before it for each check, with the command it ran. Offline: the echo provider, servers on 127.0.0.1, no model, no
key, no network (the wheel's dependencies come from this checkout's venv unless --online-deps), so it costs nothing.
What it does not cover is in harness/docs/RELEASING.md, "Quick release smoke".

It calls what exists and does not copy it: the wheel of tools/_wheel.py, the pin check of site/build.py, and
infra/deploy's render.sh, smoke_release.py and headers_check.py. Every server it starts it stops by its PID, on a
failure and on Ctrl-C too.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
REPO = HARNESS.parent
sys.path.insert(0, str(HARNESS / "tools"))
sys.path.insert(0, str(REPO / "infra" / "deploy"))
import _wheel  # noqa: E402  (the wheel pyproject.toml builds, in a temp dir)
import smoke_release  # noqa: E402  (free_port; its container checks run as a script below)

#: number -> (title, what it runs): the one list --help, --list and the tests read.
CHECKS = {
    "1": (
        "version agreement",
        (
            "_version.py, every skill's harness-version, the top CHANGELOG section, UPGRADING's newest 'From X to Y' "
            "and every install pin (site/build.py check_pins) name one version"
        ),
    ),
    "2": (
        "build and install",
        (
            "the wheel (tools/_wheel.py) in a fresh venv: evh --version, the package resolves from the venv, "
            "evh --help shows 'Start here', evh docs, evh docs runbook --print"
        ),
    ),
    "3": (
        "newcomer path, per store",
        (
            "in a fresh project, files then sqlite: evh init --tutorial, dataset-create, dataset-materialize, "
            "data-put, run --dry-run, run, leaderboard, validate (the echo provider)"
        ),
    ),
    "4": (
        "servers from the install",
        (
            "evh catalog-serve (home, /api/v1/goals, /workbench/), evh mcp --http (health, tools/list), "
            "evh mcp --http --no-agent-tools (no tool that is not read-only)"
        ),
    ),
    "5": (
        "the deployment (--release)",
        (
            "infra/deploy/render.sh into a temp dir, then smoke_release.py and headers_check.py on it; needs docker "
            "and the network (pip and the image), so it runs only when asked"
        ),
    ),
}
STARTED: list[subprocess.Popen] = []
RESULTS: list[tuple[bool, str]] = []
TMP: Path | None = None


def shown(cmd: list, tmp: Path | None) -> str:
    """The command as a person would type it, the temp folder written as $T."""
    text = shlex.join(str(c) for c in cmd)
    return text.replace(str(tmp), "$T") if tmp else text


def record(ok: bool, label: str, cmd: str = "", detail: str = "") -> bool:
    """Print one check line and remember it."""
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}" + (f"   [$ {cmd}]" if cmd else ""), flush=True)
    if not ok and detail:
        print("          " + detail.strip().replace("\n", "\n          ")[-1200:], flush=True)
    RESULTS.append((ok, label))
    return ok


def sh(cmd: list, cwd: Path | None = None, env: dict | None = None, timeout: int = 300) -> tuple[int, str]:
    """Run a command to its end, both streams together; (exit code, output)."""
    try:
        r = subprocess.run(
            [str(c) for c in cmd], cwd=cwd, env=env, text=True, timeout=timeout, encoding="utf-8",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        return 124, f"timed out after {timeout}s: {exc.cmd}"
    return r.returncode, r.stdout


def step(
    label: str, cmd: list, tmp: Path | None, cwd: Path | None, env: dict, want: str = ""
) -> tuple[bool, str]:
    """A command that must exit 0 (and print `want`): one check line."""
    code, out = sh(cmd, cwd, env)
    ok = code == 0 and want in out
    record(ok, label, shown(cmd, tmp), f"exit {code}; wanted {want!r}\n{out}" if not ok else "")
    return ok, out


def stop_all() -> None:
    """Stop every process this run started, by its PID (its own process group: the server's children with it)."""
    for p in STARTED:
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)
                p.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                    p.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired):
                    pass
    STARTED.clear()


def start_server(
    cmd: list, cwd: Path, env: dict, log: Path, port: int, ready: str
) -> tuple[subprocess.Popen, str]:
    """Start a server in its own process group; wait for `ready` to answer 200; (process, why not or '')."""
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            [str(c) for c in cmd], cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", start_new_session=True,
        )  # fmt: skip
    STARTED.append(proc)
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return (
                proc,
                f"exited {proc.returncode} before it answered\n{log.read_text(encoding='utf-8')[-800:]}",
            )
        if fetch(port, ready)[0] == 200:
            return proc, ""
        time.sleep(0.3)
    return proc, f"never answered {ready}\n{log.read_text(encoding='utf-8')[-800:]}"


def fetch(
    port: int, path: str, body: dict | None = None, headers: dict | None = None
) -> tuple[int, str, dict]:
    """GET (or POST a JSON body) on 127.0.0.1; (status, text, response headers); 0 when nothing answers."""
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Accept": "application/json, text/event-stream", **(headers or {})}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310  # nosec B310 - our own server, loopback
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), dict(exc.headers)
    except OSError:
        return 0, "", {}


def rpc(port: int, method: str, params: dict, rid: int, session: str = "") -> dict:
    """One JSON-RPC call to the MCP endpoint (a JSON or an event-stream answer); its parsed message."""
    hdrs = {"mcp-session-id": session} if session else {}
    code, text, _ = fetch(
        port, "/mcp", {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}, hdrs
    )
    for line in text.splitlines():
        if line.startswith("data:"):
            text = line[5:].strip()
    try:
        return json.loads(text)
    except ValueError:
        return {"error": f"HTTP {code}: {text[:300]}"}


def tool_list(port: int) -> list[dict]:
    """tools/list of a server on `port`, after the handshake; the tools, or [] when it did not answer."""
    init = {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "release-smoke", "version": "0"},
    }
    code, _text, hdrs = fetch(
        port, "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": init}
    )
    session = next((v for k, v in hdrs.items() if k.lower() == "mcp-session-id"), "")
    if code == 200:
        fetch(port, "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"},
              {"mcp-session-id": session} if session else None)  # fmt: skip
    return list(rpc(port, "tools/list", {}, 2, session).get("result", {}).get("tools", []))


# ── 1: the version, said once everywhere ─────────────────────────────────────────────────────────────────────────


def first(pattern: str, text: str) -> str:
    """The first group of a pattern, or ''."""
    m = re.search(pattern, text, re.M)
    return m.group(1) if m else ""


def check_versions(expect: str | None, env: dict) -> str:
    """Group 1; the version every source agrees on (the expected one when it was given)."""
    version = first(r'__version__ = "([^"]+)"', (HARNESS / "scripts/_version.py").read_text(encoding="utf-8"))
    want = expect or version
    where = "harness/scripts/_version.py"
    record(version == want, f"1 _version.py is {want}", f"read {where}", f"it says {version!r}")
    skills = sorted((HARNESS / "skills").glob("*/SKILL.md"))
    named = {
        s.parent.name: first(r'harness-version:\s*"?([^"\s]+)', s.read_text(encoding="utf-8")) for s in skills
    }
    record(
        bool(named) and all(v == want for v in named.values()),
        f"1 the {len(named)} skills' harness-version is {want}",
        "read harness/skills/*/SKILL.md",
        str({k: v for k, v in named.items() if v != want}),
    )
    top = first(r"^## (\d+\.\d+\.\d+\S*) ", (HARNESS / "CHANGELOG.md").read_text(encoding="utf-8"))
    record(
        top == want, f"1 the top CHANGELOG section is {want}", "read harness/CHANGELOG.md", f"it says {top!r}"
    )
    heading = first(r"^## From \S+ to (\S+)", (HARNESS / "docs/UPGRADING.md").read_text(encoding="utf-8"))
    record(
        heading == want,
        f"1 UPGRADING's newest 'From X to Y' heading ends at {want}",
        "read harness/docs/UPGRADING.md",
        f"it says {heading!r}",
    )
    snippet = (
        "import json, sys; sys.path.insert(0, 'site'); import build, releases; "
        "from evaluation_harness import _store; "
        "latest = next(r['version'] for r in releases.releases(_store.read_text(releases.CHANGELOG)) if r['date']); "
        "print(json.dumps({'latest': latest, 'problems': build.check_pins()}))"
    )
    cmd = [sys.executable, "-c", snippet]
    code, out = sh(cmd, REPO, env)
    try:
        got = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        got = {"latest": "", "problems": [out[-600:]]}
    record(
        code == 0 and not got["problems"] and got["latest"] == want.split(".dev")[0],
        f"1 every install pin names v{want} (the latest dated release is v{got['latest']})",
        "python -c 'import build; build.check_pins()'  (site/build.py, run from the repository root)",
        "\n".join(got["problems"]) or f"latest dated release v{got['latest']}, expected v{want}",
    )
    return want


# ── 2: the wheel, installed ──────────────────────────────────────────────────────────────────────────────────────


def project_env(tmp: Path, venv: Path) -> dict:
    """The environment a newcomer's shell has: the venv's bin first, none of this checkout's settings."""
    env = {
        k: v for k, v in os.environ.items() if not k.startswith(("EVAL_", "EVH_", "PYTHON", "VIRTUAL_ENV"))
    }
    env.update(
        PATH=f"{venv / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}", PYTHONDONTWRITEBYTECODE="1",
        EVH_ACTOR="person:reader", GIT_AUTHOR_NAME="smoke", GIT_AUTHOR_EMAIL="smoke@example.invalid",
        GIT_COMMITTER_NAME="smoke", GIT_COMMITTER_EMAIL="smoke@example.invalid",
    )  # fmt: skip
    return env


def check_install(tmp: Path, want: str, online: bool) -> tuple[Path, dict] | None:
    """Group 2; (the venv, the environment) when it can go on, else None."""
    try:
        whl = _wheel.wheel()
    except SystemExit as exc:
        record(False, "2 the wheel builds", "python harness/tools/_wheel.py (pip wheel --no-deps)", str(exc))
        return None
    record(whl.is_file(), f"2 the wheel builds: {whl.name}", "tools/_wheel.py wheel()")
    venv = tmp / "venv"
    env = project_env(tmp, venv)
    ok, _ = step("2 a fresh venv", [sys.executable, "-m", "venv", venv], tmp, None, env)
    if not ok:
        return None
    pip = [venv / "bin/pip", "install", "-q"]
    if online:
        ok, _ = step("2 pip install of the wheel, dependencies from the index", [*pip, whl], tmp, None, env)
    else:
        # No network: the wheel alone goes in; its dependencies are this checkout's venv's, put behind it on the path.
        ok, _ = step(
            "2 pip install --no-deps --no-index of the wheel",
            [*pip, "--no-deps", "--no-index", whl],
            tmp,
            None,
            env,
        )
        site = next((Path(sys.prefix) / "lib").glob("python*/site-packages"), None)
        if ok and site:
            pth = next((venv / "lib").glob("python*/site-packages")) / "zz_deps.pth"
            pth.write_text(f"{site}\n", encoding="utf-8")
    if not ok:
        return None
    evh = venv / "bin/evh"
    work = tmp / "scratch"
    work.mkdir()
    _, out = step(f"2 evh --version prints {want}", [evh, "--version"], tmp, work, env, want)
    record(
        out.strip().endswith(want), f"2 evh --version is exactly {want}", shown([evh, "--version"], tmp), out
    )
    code, out = sh(
        [venv / "bin/python", "-c", "import evaluation_harness as m; print(m.__file__)"], work, env
    )
    where = out.strip()
    record(
        code == 0 and where.startswith(str(venv)) and not where.startswith(str(REPO)),
        "2 evh resolves the installed package, not this checkout",
        "python -c 'import evaluation_harness; print(__file__)'  (in the venv)",
        where,
    )
    step("2 evh --help shows 'Start here'", [evh, "--help"], tmp, work, env, "Start here")
    ok, out = step("2 evh docs lists the shipped docs", [evh, "docs"], tmp, work, env, "runbook")
    paths = re.findall(r"^\s+(?:upgrading|runbook|integration)\s+(\S+)", out, re.M)
    record(
        len(paths) == 3 and all(Path(p).is_file() for p in paths),
        "2 the three docs evh docs names exist in the install",
        shown([evh, "docs"], tmp),
        out,
    )
    ok, out = step(
        "2 evh docs runbook --print prints text", [evh, "docs", "runbook", "--print"], tmp, work, env
    )
    record(
        len(out) > 2000 and "#" in out, "2 the runbook it prints is a document", "", f"{len(out)} characters"
    )
    return venv, env


# ── 3: a newcomer's project, per store ───────────────────────────────────────────────────────────────────────────

SYSTEMS = ("tickets_lead1_v1", "tickets_lead2_v1")


def check_project(tmp: Path, venv: Path, env: dict, store: str) -> Path | None:
    """Group 3 for one store: the GUIDE's loop on the echo provider in a fresh project; the project, or None."""
    proj = tmp / f"proj-{store}"
    proj.mkdir()
    evh = venv / "bin/evh"
    tag = f"3 [{store}]"

    def go(label: str, *args: object, want: str = "", prog: object = evh) -> bool:
        return step(f"{tag} {label}", [prog, *args], tmp, proj, env, want)[0]

    steps = [
        go("evh init --tutorial", "init", "--store", store, "--tutorial"),
        go("git init", "init", "-q", prog="git"),
        go("git add", "add", "-A", prog="git"),
        go("git commit (a clean tree, as the GUIDE has it)", "commit", "-qm", "the tutorial kit", prog="git"),
        go(
            "dataset-create",
            "dataset-create",
            "--dataset-id",
            "tickets_v1",
            "--source-dir",
            "tutorial/tickets",
        ),
        go(
            "dataset-materialize",
            "dataset-materialize",
            "--dataset-id",
            "tickets_v1",
            want="all hashes verified",
        ),
    ]
    for s in SYSTEMS:
        steps.append(
            go(
                f"data-put {s}",
                "data-put",
                "--path",
                f"systems/{s}.yaml",
                "--file",
                f"tutorial/systems/{s}.yaml",
            )
        )
    steps.append(go("git commit the systems", "commit", "-qam", "systems", "--allow-empty", prog="git"))
    if not all(steps):
        return None
    for s in SYSTEMS:
        go(f"run --dry-run {s}", "run", "--system", s, "--dataset", "tickets_v1", "--dry-run")
        go(f"run {s}", "run", "--system", s, "--dataset", "tickets_v1")
    go("leaderboard", "leaderboard", "tickets_v1", want=SYSTEMS[-1])
    go("validate", "validate", want="VALIDATION PASSED")
    return proj


# ── 4: the servers, started from the install ─────────────────────────────────────────────────────────────────────


def check_servers(tmp: Path, venv: Path, env: dict, proj: Path) -> None:
    """Group 4: the catalog and the MCP server (twice) on free loopback ports, each stopped by its PID."""
    evh = venv / "bin/evh"
    port = smoke_release.free_port()
    cmd = [evh, "catalog-serve", "--port", port]
    proc, why = start_server(cmd, proj, env, tmp / "catalog.log", port, "/")
    record(not why, f"4 evh catalog-serve answers on 127.0.0.1:{port}", shown(cmd, tmp), why)
    if not why:
        for path, text in (("/", "<"), ("/api/v1/goals", '"result"'), ("/workbench/", "<header")):
            tokenfile = proj / ".build/api-token"
            token = (
                tokenfile.read_text(encoding="utf-8").strip()
                if path.startswith("/api/") and tokenfile.is_file()
                else ""
            )
            code, body, _ = fetch(port, path, headers={"Authorization": f"Bearer {token}"} if token else None)
            record(
                code == 200 and text in body,
                f"4 catalog GET {path} is 200 with {text!r}",
                f"curl{' -H Authorization:Bearer' if token else ''} 127.0.0.1:{port}{path}",
                f"{code} {body[:200]!r}",
            )
    stop_all()
    record(proc.poll() is not None, f"4 catalog-serve (pid {proc.pid}) stopped", f"kill {proc.pid}")

    for flags in ((), ("--no-agent-tools",)):
        port = smoke_release.free_port()
        cmd = [evh, "mcp", "--http", "--port", port, *flags]
        proc, why = start_server(cmd, proj, env, tmp / f"mcp{len(flags)}.log", port, "/mcp/health")
        name = " ".join(["evh mcp --http", *flags])
        record(not why, f"4 {name} answers on 127.0.0.1:{port}", shown(cmd, tmp), why)
        if not why:
            code, body, _ = fetch(port, "/mcp/health")
            record(
                code == 200 and '"ok"' in body,
                f"4 {name}: /mcp/health is ok",
                f"curl 127.0.0.1:{port}/mcp/health",
                body,
            )
            tools = tool_list(port)
            record(
                bool(tools),
                f"4 {name}: tools/list answers ({len(tools)} tools)",
                "POST /mcp tools/list (JSON-RPC)",
            )
            if not flags:
                n = len([t for t in tools if (t.get("annotations") or {}).get("readOnlyHint") is not True])
                record(
                    n > 0,
                    f"4 the default server has the agent tools ({n} not read-only): the next check can fail",
                    "POST /mcp tools/list",
                )
            if flags:
                writers = [
                    t["name"] for t in tools if (t.get("annotations") or {}).get("readOnlyHint") is not True
                ]
                record(
                    bool(tools) and not writers,
                    "4 --no-agent-tools: every tool is read-only (readOnlyHint true)",
                    "POST /mcp tools/list",
                    str(writers),
                )
        stop_all()
        record(proc.poll() is not None, f"4 {name} (pid {proc.pid}) stopped", f"kill {proc.pid}")


# ── 5: the deployment ────────────────────────────────────────────────────────────────────────────────────────────


def check_release(tmp: Path, env: dict) -> None:
    """Group 5: the release rendered as the deploy renders it, then the container and header checks on it."""
    if not shutil.which("docker"):
        print("  skip  5 the deployment: skipped: no docker")
        return
    rel = tmp / "release"
    sha = sh(["git", "rev-parse", "--short=12", "HEAD"], REPO, env)[1].strip() or "0" * 12
    renv = {**os.environ, "EVALS_STORE": "sqlite"}
    ok, _ = step("5 render.sh", ["bash", REPO / "infra/deploy/render.sh", rel, sha], tmp, REPO, renv)
    if not ok:
        return
    py = sys.executable
    step(
        "5 smoke_release.py: the release's containers answer",
        [py, REPO / "infra/deploy/smoke_release.py", rel],
        tmp,
        REPO,
        env,
        "SMOKE: PASS",
    )
    step(
        "5 headers_check.py: one header across the publication",
        [py, REPO / "infra/deploy/headers_check.py", rel],
        tmp,
        REPO,
        env,
        "HEADERS: PASS",
    )


def main() -> int:
    """Run the chosen checks; 0 when every line was ok."""
    global TMP
    ap = argparse.ArgumentParser(
        description=__doc__,
        epilog="checks:\n" + "\n".join(f"  {n}  {t}: {d}" for n, (t, d) in CHECKS.items()),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--list", action="store_true", help="print the checks and stop")
    ap.add_argument("--only", help="comma-separated check numbers (default: 1 to 4, and 5 with --release)")
    ap.add_argument("--expect-version", help="the version every source must name (default: _version.py's)")
    ap.add_argument(
        "--release",
        action="store_true",
        help="also check 5: render the release and run its container checks (docker, network)",
    )
    ap.add_argument(
        "--online-deps",
        action="store_true",
        help="install the wheel's dependencies from the package index, as pip does",
    )
    ap.add_argument("--keep", action="store_true", help="keep the temp folder and print it")
    args = ap.parse_args()
    if args.list:
        for n, (title, what) in CHECKS.items():
            print(f"{n}  {title}: {what}")
        return 0
    chosen = (
        set(args.only.split(",")) if args.only else {"1", "2", "3", "4"} | ({"5"} if args.release else set())
    )
    if unknown := chosen - set(CHECKS):
        ap.error(f"unknown check {sorted(unknown)}; they are {sorted(CHECKS)}")
    if chosen & {"3", "4"}:
        chosen.add("2")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    signal.signal(signal.SIGINT, signal.default_int_handler)  # a background job starts with it ignored
    TMP = tmp = Path(tempfile.mkdtemp(prefix="evh-release-smoke-"))
    base = {k: v for k, v in os.environ.items() if not k.startswith(("EVAL_", "EVH_"))}
    started = time.monotonic()
    try:
        own = first(r'__version__ = "([^"]+)"', (HARNESS / "scripts/_version.py").read_text(encoding="utf-8"))
        want = check_versions(args.expect_version, base) if "1" in chosen else args.expect_version or own
        installed = check_install(tmp, want, args.online_deps) if "2" in chosen else None
        if "2" in chosen and installed is None:
            record(False, "3, 4 cannot run: no install to run them on")
        elif installed:
            venv, env = installed
            if "3" in chosen or "4" in chosen:
                projects = {s: check_project(tmp, venv, env, s) for s in ("files", "sqlite")}
                if "4" in chosen:
                    if projects["files"]:
                        check_servers(tmp, venv, env, projects["files"])
                    else:
                        record(False, "4 cannot run: the files project was not made")
        if "5" in chosen:
            check_release(tmp, base)
        elif not args.only:
            print("  skip  5 the deployment: skipped: --release not given (it needs docker and the network)")
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        stop_all()
        print("RELEASE SMOKE: FAIL (interrupted)")
        return 130
    finally:
        stop_all()
        if args.keep:
            print(f"kept: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)
    bad = sum(1 for ok, _ in RESULTS if not ok)
    print(f"{len(RESULTS)} checks in {time.monotonic() - started:.0f}s")
    print("RELEASE SMOKE: PASS" if not bad else f"RELEASE SMOKE: FAIL ({bad} of {len(RESULTS)})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
