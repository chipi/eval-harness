#!/usr/bin/env python3
"""Run docs/GUIDE.md in a fresh project and check every output it quotes.

    python scripts/check_guide.py            # PASS / FAIL, exits non-zero on a mismatch
    python scripts/check_guide.py --print    # also print what each command printed

The GUIDE is the onboarding path: a new project, the harness installed, the tutorial kit
copied in, then every step with `evh`. A quoted output that no longer matches what the
command prints is a GUIDE that lies to its first reader, so this runs each ```bash block in
order in a scratch project, the way a reader would, and checks that every line of the
```text block after it appears in what was printed (spaces collapsed; a line with "..." is
an elision and is not checked).

The package is laid out as pip lays it out, beside the project, and `evh` is a shim on PATH
that runs it: no network, no install. A one-line HTML comment before a block steers the
check, and does not show on the page:

  <!-- guide-check: skip -->        not run (installing the package: done here instead)
  <!-- guide-check: varies -->      run, its output not compared
  <!-- guide-check: varies A B -->  run, its lines that mention A or B not compared (the unseeded
                                    noisy arm, and what its numbers move)
  <!-- guide-check: background -->  started, its first output compared, then stopped

`<a NAME run_id>` and `<the NAME run_id>` are replaced by the id of a run of NAME. A background
block whose output names 127.0.0.1:8765 runs on a free port instead when another program on the
machine holds that one.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
GUIDE = HARNESS.parent / "docs" / "GUIDE.md"
FENCE = re.compile(r"^```(\w*)\s*$")
MARK = re.compile(r"^<!--\s*guide-check:\s*(\w+)((?:\s+[\w.-]+)*)\s*-->\s*$")
PLACEHOLDER = re.compile(r"<(?:a|the) ([A-Za-z0-9_]+) run_id>")


def blocks(text: str) -> list:
    """[(kind, body, (mark, words), line)] for every fenced block, with the comment mark
    before it ("" and () when there is none)."""
    none = ("", ())
    out, lines, i, mark = [], text.splitlines(), 0, none
    while i < len(lines):
        m = MARK.match(lines[i].strip())
        if m:
            mark = (m.group(1), tuple(m.group(2).split()))
            i += 1
            continue
        f = FENCE.match(lines[i])
        if f:
            start, body = i + 1, []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            out.append((f.group(1), "\n".join(body), mark, start))
            mark = none
        elif lines[i].strip():
            mark = none
        i += 1
    return out


def norm(s: str) -> str:
    return " ".join(s.split())


def expected_lines(text: str) -> list:
    return [norm(x) for x in text.splitlines() if x.strip() and "..." not in x and "…" not in x]


def setup(tmp: Path) -> tuple:
    """The package as pip lays it out, an `evh` shim on PATH, and an empty project."""
    site = tmp / "site-packages"
    pkg = site / "evaluation_harness"
    shutil.copytree(HERE, pkg, ignore=shutil.ignore_patterns("__pycache__", "test_*.py", "self_test.py"))
    for sub in ("schemas", "catalog_assets", "tutorial"):
        shutil.copytree(HARNESS / sub, pkg / sub, ignore=shutil.ignore_patterns("__pycache__"))
    bindir = tmp / "bin"
    bindir.mkdir()
    shim = bindir / "evh"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m evaluation_harness "$@"\n')
    shim.chmod(0o755)
    proj = tmp / "my-evals"
    proj.mkdir()
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}",
           "PYTHONPATH": str(site), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
           "GIT_AUTHOR_NAME": "guide", "GIT_AUTHOR_EMAIL": "guide@example.invalid",
           "GIT_COMMITTER_NAME": "guide", "GIT_COMMITTER_EMAIL": "guide@example.invalid"}
    for k in ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_RUNS_DIR", "OPENROUTER_API_KEY", "LITELLM_BASE_URL",
              "EVAL_MAX_COST_USD"):
        env.pop(k, None)
    return proj, env


def fill(cmd: str, proj: Path) -> str:
    def run_id(m):
        runs = sorted(p.name for p in (proj / "data" / "runs").glob(f"{m.group(1)}_2*"))
        return runs[0] if runs else m.group(0)
    return PLACEHOLDER.sub(run_id, cmd)


PORT = 8765  # catalog-serve's default


def port_free(port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run(cmd: str, proj: Path, env: dict, background: bool) -> tuple:
    if not background:
        r = subprocess.run(["bash", "-c", cmd], cwd=proj, env=env, capture_output=True, text=True, timeout=900)
        return r.returncode, r.stdout + r.stderr
    log = proj.parent / "background.log"
    with open(log, "w") as fh:
        p = subprocess.Popen(["bash", "-c", f"exec {cmd}"], cwd=proj, env=env, stdout=fh,
                             stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(80):
        if log.read_text().strip():
            break
        time.sleep(0.25)
    time.sleep(0.5)
    os.killpg(p.pid, signal.SIGTERM)
    p.wait(timeout=10)
    return 0, log.read_text()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--print", action="store_true", help="print what each command printed")
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="guide-check-"))
    problems, ran = [], 0
    try:
        proj, env = setup(tmp)
        bs = blocks(GUIDE.read_text(encoding="utf-8"))
        for n, (kind, body, (mark, _), line) in enumerate(bs):
            if kind != "bash" or mark == "skip":
                continue
            cmd = fill(body, proj)
            nxt = bs[n + 1] if n + 1 < len(bs) else None
            want = nxt[1] if nxt and nxt[0] == "text" and nxt[3] - line <= len(body.splitlines()) + 3 else None
            if mark == "background" and want and f"127.0.0.1:{PORT}" in want and not port_free(PORT):
                # Another program on this machine holds the default port: not the GUIDE's to take.
                free = free_port()
                cmd, want = f"{cmd.strip()} --port {free}", want.replace(f"127.0.0.1:{PORT}", f"127.0.0.1:{free}")
            code, out = run(cmd, proj, env, mark == "background")
            ran += 1
            if args.print:
                print(f"\n=== GUIDE line {line} (exit {code}):\n{cmd}\n--- printed:\n{out.rstrip()}")
            if want is None:
                if code != 0:
                    problems.append(f"line {line}: exited {code}, and the GUIDE quotes no output for it\n"
                                    f"    {out.strip()[-300:]}")
                continue
            vmark, vwords = nxt[2]
            if vmark == "varies" and not vwords:
                continue
            got = norm(out)
            lines_ = [x for x in expected_lines(want)
                      if not (vmark == "varies" and any(w in x for w in vwords))]
            missing = [x for x in lines_ if x not in got]
            if missing:
                problems.append(f"line {line}: {len(missing)} quoted line(s) not printed, e.g. {missing[0]!r}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for p in problems:
        print(f"  FAIL {p}")
    print(f"GUIDE: {ran} command block(s) run in a fresh project, "
          + ("every quoted output matches" if not problems else f"{len(problems)} problem(s)"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
