#!/usr/bin/env python3
"""The inspector's budgets on this repository's own runs: memory under --warm, and how long an
answer takes, cached and cold.

    python tests/test_inspector_budget.py [--catalog DIR] [--hooks FILE.py]
    make budget-check

Starts `catalog-serve --public localhost --warm <catalog>` as the deployment does (prod runs it in
a 256 MiB container), samples its resident memory every half second until the warm-up says it is
done, then asks comparisons the catalog links to. Fails when

  - the peak passes MEMORY_MB (prod's limit is 256 MiB; the 0.4.0 inspector peaked at 259 MB on
    this warm-up and was OOM-killed every ~5 minutes, 2026-10-26/27);
  - the median cached answer passes CACHED_MS, or the slowest cold one COLD_S (a cold answer
    computes a paired test per arm; the limits leave room for a slow CI runner).

--hooks adds a deployment's hooks (infra/inspector/hooks.py with its SDKs on PYTHONPATH) to
measure what they cost. Without --catalog it builds the catalog first (in .build/budget-catalog).
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

MEMORY_MB = 200
CACHED_MS = 50
COLD_S = 15.0
WARM_TIMEOUT_S = 900


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def rss_mb(pid: int) -> float:
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return 0.0


def ask(port: int, query: str) -> tuple:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/compare?{query}", headers={"Host": "localhost"}
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 -- http to 127.0.0.1 only
        r.read()
        return r.status, time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalog", type=Path, help="a built catalog (default: build one)")
    ap.add_argument("--hooks", help="a deployment's hooks, to measure their cost")
    args = ap.parse_args()
    cat = args.catalog
    if cat is None:
        cat = HARNESS / ".build" / "budget-catalog"
        t0 = time.monotonic()
        subprocess.run(
            [sys.executable, str(HARNESS / "scripts" / "catalog_build.py"), "--out", str(cat)],
            check=True,
            capture_output=True,
        )
        print(f"  catalog built in {time.monotonic() - t0:.0f} s")
    links = set()
    for page in cat.rglob("*.html"):
        for href in re.findall(r'href="(?:\.\./)*inspect\.html\?([^"]+)"', page.read_text(encoding="utf-8")):
            links.add(href.replace("&amp;", "&"))

    def start(warm: bool) -> tuple:
        port = free_port()
        cmd = [
            sys.executable,
            str(HARNESS / "scripts" / "catalog_serve.py"),
            "--public",
            "localhost",
            "--port",
            str(port),
            "--rate",
            "100000",
            *(["--warm", str(cat)] if warm else []),
            *(["--hooks", args.hooks] if args.hooks else []),
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=os.environ.copy()
        )
        lines: list = []
        threading.Thread(target=lambda: lines.extend(proc.stdout), daemon=True).start()
        return proc, port, lines

    def stop(proc) -> None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    # Cold: a fresh server, nothing cached, the largest comparisons the catalog links to.
    largest = sorted(links, key=lambda q: -q.count(","))[:5]
    proc, port, lines = start(warm=False)
    try:
        for _ in range(300):
            try:
                urllib.request.urlopen(
                    urllib.request.Request(
                        f"http://127.0.0.1:{port}/api/health", headers={"Host": "localhost"}
                    ),
                    timeout=2,
                )
                break
            except OSError:
                time.sleep(0.2)
        cold = [ask(port, q) for q in largest]
    finally:
        stop(proc)
    worst = max((s for _, s in cold), default=0.0)
    check(
        f"a cold answer: the slowest of the {len(cold)} largest comparisons ({max(q.count(',') + 1 for q in largest)} arms) "
        f"took {worst:.2f} s on a fresh server, under {COLD_S:.0f} s",
        cold and all(c == 200 for c, _ in cold) and worst < COLD_S,
    )

    # Warm: as the deployment runs it.
    proc, port, lines = start(warm=True)
    peak, t0 = 0.0, time.monotonic()
    try:
        while time.monotonic() - t0 < WARM_TIMEOUT_S and proc.poll() is None:
            peak = max(peak, rss_mb(proc.pid))
            if any(x.startswith("warm:") for x in lines):
                break
            time.sleep(0.5)
        warm_s = time.monotonic() - t0
        settled = rss_mb(proc.pid) if proc.poll() is None else 0.0
        done = any(x.startswith("warm:") for x in lines)
        check(
            f"warm-up finishes ({len(links)} comparisons the catalog links to, {warm_s:.0f} s)",
            done,
            "".join(lines[-5:]),
        )
        check(
            f"memory under --warm: peak {peak:.0f} MB, settled {settled:.0f} MB, under {MEMORY_MB} MB "
            "(prod's container limit is 256 MiB)",
            0 < peak < MEMORY_MB,
        )
        sample = sorted(links)[:: max(1, len(links) // 40)][:40]
        cached = [ask(port, q) for q in sample]
        med_ms = statistics.median(s for _, s in cached) * 1000 if cached else 0
        check(
            f"a cached answer: median {med_ms:.1f} ms over {len(cached)} of the catalog's links, under {CACHED_MS} ms",
            cached and all(c == 200 for c, _ in cached) and med_ms < CACHED_MS,
        )
    finally:
        stop(proc)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
