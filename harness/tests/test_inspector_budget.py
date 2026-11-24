#!/usr/bin/env python3
"""The inspector's budgets on this repository's own runs: memory under --warm, and how long an
answer takes, cached and cold.

    python tests/test_inspector_budget.py [--catalog DIR] [--hooks FILE.py]
    make budget-check

Starts `catalog-serve` with the arguments infra/compose.yml gives the inspector (--public, --rate,
--catalog-at, --publish, --client-header, --warm <catalog>; the bind, the port and the catalog's path
are this machine's), samples its resident memory every half second from the start of the warm-up to the
end of the reads, and asks comparisons the catalog links to and, as the read-only Workbench does
(RFC-039), the /api/v1 reads its screens make. Fails when

  - the peak passes the container's mem_limit, read from compose.yml so the two cannot drift (the
    0.4.0 inspector peaked at 259 MB on this warm-up and was OOM-killed every ~5 minutes under the
    256 MiB it had then, 2026-10-26/27);
  - the median cached answer (a link asked a second time) passes CACHED_MS, or the slowest cold one COLD_S (a cold answer
    computes a paired test per arm; the limits leave room for a slow CI runner).

--hooks adds a deployment's hooks (infra/inspector/hooks.py with its SDKs on PYTHONPATH) to
measure what they cost. Without --catalog it builds the catalog first (in .build/budget-catalog).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

# It measures this repository's own runs, its committed data, which is files.
os.environ["EVAL_STORE"] = "files"

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

COMPOSE = HARNESS.parent / "infra" / "compose.yml"
CACHED_MS = 50
COLD_S = 15.0
WARM_TIMEOUT_S = 900


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def rss_mb(pid: int) -> float:
    for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return 0.0


def deployed() -> tuple:
    """(the inspector's `catalog_serve.py` arguments, its mem_limit in MiB) as infra/compose.yml has them."""
    svc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["inspector"]
    cmd = [str(x) for x in svc["command"]]
    limit = str(svc["mem_limit"]).lower()
    units = {"k": 1 / 1024, "m": 1, "g": 1024}
    mem = float(limit[:-1]) * units[limit[-1]] if limit[-1] in units else float(limit) / 2**20
    return cmd[next(i for i, x in enumerate(cmd) if x.endswith("catalog_serve.py")) + 1 :], mem


class Client:
    """The requests a deployment's visitors make: its Host, and a client address per 40 requests, so --rate (the
    deployment's own, 60 a minute per client) is in force and a run of many reads is not one client's."""

    def __init__(self, port: int, host: str) -> None:
        self.port, self.host, self.n = port, host, 0
        self.lock = threading.Lock()

    def get(self, path: str, timeout: float = 120) -> tuple:
        """(status, seconds, body, headers) of GET path; an error status is an answer, not an exception."""
        with self.lock:
            self.n += 1
            ip = f"10.1.{self.n // 40 // 250}.{self.n // 40 % 250 + 1}"
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", headers={"Host": self.host, "X-Real-IP": ip}
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — http to 127.0.0.1 only  # nosec B310
                body = r.read()
                return r.status, time.perf_counter() - t0, body, r.headers
        except urllib.error.HTTPError as exc:
            return exc.code, time.perf_counter() - t0, exc.read(), exc.headers

    def ask(self, query: str) -> tuple:
        code, secs, _, _ = self.get(f"/api/compare?{query}")
        return code, secs


def viewer_reads(c: Client) -> list:
    """What the read-only Workbench asks (workbench/live.js `load`): each list, then each goal's, dataset's, model's,
    system's and scorer's own reads, found from the answers as the screens find them. [(path, status, seconds, bytes)]"""
    done: list = []

    def read(path: str) -> dict:
        code, secs, body, _ = c.get("/api/v1" + path)
        done.append((path, code, secs, len(body)))
        try:
            return json.loads(body).get("result") or {}
        except ValueError:
            return {}

    lists = {p: read(p) for p in (
        "/goals", "/models", "/systems", "/datasets", "/arms", "/scorers", "/prompts", "/references", "/captures",
        "/failure-modes", "/metrics",
    )}  # fmt: skip
    for g in (x["goal"] for x in lists["/goals"].get("goals", [])):
        read(f"/goals/{g}")
        read(f"/goals/{g}/status")
        read(f"/baselines?goal={g}")
        for st in read(f"/goals/{g}/studies").get("studies", []):
            read(f"/goals/{g}/studies/{st.get('study_id') or st.get('study')}")
        for r in (x["round_id"] for x in read(f"/goals/{g}/rounds").get("rounds", [])):
            read(f"/goals/{g}/rounds/{r}")
            read(f"/goals/{g}/rounds/{r}/evidence")
    by_ds: dict = {}  # a dataset's systems with a run of their own on it: what the screens pair and rank
    for a in lists["/arms"].get("arms", []):
        if a["arm"].startswith("runs/"):
            by_ds.setdefault(a["dataset"], []).append(a["system"])
    for d in (x["dataset"] for x in lists["/datasets"].get("datasets", [])):
        read(f"/datasets/{d}")
        read(f"/datasets/{d}/arms")
        read(f"/datasets/{d}/label-sets")
        if by_ds.get(d):  # the leaderboard of a dataset with no run answers 404, and the screens do not ask
            read(f"/datasets/{d}/leaderboard")
        if len(by_ds.get(d, [])) > 1:
            read(f"/datasets/{d}/pair-test?a={by_ds[d][0]}&b={by_ds[d][1]}&include_exposed=true")
    for m in (x["model"] for x in lists["/models"].get("models", [])):
        read(f"/models/{m}")
    for sy in (x["system"] for x in lists["/systems"].get("systems", [])):
        read(f"/systems/{sy}")
    for sc in (x["scorer"] for x in lists["/scorers"].get("scorers", [])):
        read(f"/scorers/{sc}")
    return done


class Sampler(threading.Thread):
    """The process's resident memory, every half second, and its highest."""

    def __init__(self, pid: int) -> None:
        super().__init__(daemon=True)
        self.pid, self.peak, self.stop_ = pid, 0.0, threading.Event()

    def run(self) -> None:
        while not self.stop_.is_set():
            self.peak = max(self.peak, rss_mb(self.pid))
            self.stop_.wait(0.5)


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
            [sys.executable, str(HARNESS / "scripts" / "cli.py"), "catalog", "--out", str(cat)],
            check=True,
            capture_output=True,
        )
        print(f"  catalog built in {time.monotonic() - t0:.0f} s")
    links = set()
    for page in cat.rglob("*.html"):
        for href in re.findall(r'href="(?:\.\./)*inspect\.html\?([^"]+)"', page.read_text(encoding="utf-8")):
            links.add(href.replace("&amp;", "&"))

    served, budget_mb = deployed()
    host = served[served.index("--public") + 1]

    def start(warm: bool) -> tuple:
        # compose.yml's arguments, but for where it listens, what it warms and its hooks (SDKs this machine lacks)
        port = free_port()
        kept, i = [], 0
        while i < len(served):
            if served[i] in ("--bind", "--port", "--warm", "--hooks"):
                i += 2
                continue
            kept.append(served[i])
            i += 1
        cmd = [
            sys.executable,
            str(HARNESS / "scripts" / "catalog_serve.py"),
            *kept,
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            *(["--warm", str(cat)] if warm else []),
            *(["--hooks", args.hooks] if args.hooks else []),
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy(),
            encoding="utf-8",
        )
        lines: list = []
        threading.Thread(target=lambda: lines.extend(proc.stdout or ()), daemon=True).start()
        return proc, Client(port, host), lines

    def stop(proc) -> None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    # Cold: a fresh server, nothing cached, the largest comparisons the catalog links to.
    largest = sorted(links, key=lambda q: -q.count(","))[:5]
    proc, client, lines = start(warm=False)
    try:
        for _ in range(300):
            try:
                if client.get("/api/health", timeout=2)[0] == 200:
                    break
            except OSError:
                time.sleep(0.2)
        cold = [client.ask(q) for q in largest]
    finally:
        stop(proc)
    worst = max((s for _, s in cold), default=0.0)
    check(
        f"a cold answer: the slowest of the {len(cold)} largest comparisons ({max(q.count(',') + 1 for q in largest)} arms) "
        f"took {worst:.2f} s on a fresh server, under {COLD_S:.0f} s",
        cold and all(c == 200 for c, _ in cold) and worst < COLD_S,
    )

    # Warm: as the deployment runs it, then asked what its visitors ask: the inspector's comparisons and the Workbench's reads.
    proc, client, lines = start(warm=True)
    sampler = Sampler(proc.pid)
    sampler.start()
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < WARM_TIMEOUT_S and proc.poll() is None:
            if any(x.startswith("warm:") for x in lines):
                break
            time.sleep(0.5)
        warm_s = time.monotonic() - t0
        settled = rss_mb(proc.pid) if proc.poll() is None else 0.0
        done = any(x.startswith("warm:") for x in lines)
        peak_warm = sampler.peak
        check(
            f"warm-up finishes ({len(links)} comparisons the catalog links to, {warm_s:.0f} s)",
            done,
            "".join(lines[-5:]),
        )
        check(
            f"memory under --warm: peak {peak_warm:.0f} MB, settled {settled:.0f} MB, under {budget_mb:.0f} MB "
            f"(the container's mem_limit in {COMPOSE.relative_to(HARNESS.parent)})",
            0 < peak_warm < budget_mb,
        )
        # The warm-up stops at 3/4 of the cache's bytes (a 40-arm answer is ~2 MB), so most links are not in it:
        # each sampled link is asked once, then timed. Timing the first ask measured a recompute (26-53 ms by the
        # runner's speed, 2026-11-11) under this check's name; an answer the cache does not hold is COLD_S's.
        said = next((x for x in lines if x.startswith("warm:")), "")
        print(f"  note: {said.strip() or 'warm: ?'} of the {len(links)} the catalog links to")
        sample = sorted(links)[:: max(1, len(links) // 40)][:40]
        first = [client.ask(q) for q in sample]
        cached = [client.ask(q) for q in sample]
        med_ms = statistics.median(s for _, s in cached) * 1000 if cached else 0
        check(
            f"a cached answer: median {med_ms:.1f} ms over {len(cached)} of the catalog's links (each asked once "
            f"before; the first asks' median {statistics.median(s for _, s in first) * 1000:.1f} ms), under {CACHED_MS} ms",
            cached and all(c == 200 for c, _ in first + cached) and med_ms < CACHED_MS,
        )
        # The viewer (RFC-039): the same process answers the Workbench's reads, and they are the same budget. Twice, so
        # the second pass shows what the answer cache and the allocator add; the inspector's comparisons are asked again after.
        code, _, _, hdrs = client.get("/api/v1/goals")
        check(
            "the Workbench is served as the deployment serves it: /api/v1/goals answers 200 with no token, as a viewer, "
            "naming the catalog's path",
            code == 200 and hdrs.get("X-EVH-Viewer") == "1" and hdrs.get("X-EVH-Catalog") == "/catalog/",
            (code, hdrs.get("X-EVH-Viewer"), hdrs.get("X-EVH-Catalog")),
        )
        reads = viewer_reads(client)
        reads += viewer_reads(client)
        # a pair of systems that share no items (two captures) is refused "not-enough", 400, and the screen says so
        bad = [(p, c) for p, c, _, _ in reads if c != 200 and not (c == 400 and "/pair-test?" in p)]
        slow = max(reads, key=lambda r: r[2])
        big = max(reads, key=lambda r: r[3])
        check(
            f"the Workbench's reads: {len(reads)} asked ({len({p for p, *_ in reads})} distinct), every one answered 200 (a pair with no shared item, 400) "
            f"(slowest {slow[0]} {slow[2]:.2f} s, largest {big[0]} {big[3] / 1024:.0f} KB)",
            len({p for p, *_ in reads}) >= 100 and not bad,
            bad[:5],
        )
        more = [client.ask(q) for q in sample]
        alive = proc.poll() is None
        peak = max(sampler.peak, rss_mb(proc.pid) if alive else 0.0)
        check(
            f"memory with the viewer's reads: peak {peak:.0f} MB (warm-up {peak_warm:.0f} MB), settled "
            f"{rss_mb(proc.pid) if alive else 0:.0f} MB, under the container's {budget_mb:.0f} MB",
            alive and 0 < peak < budget_mb and all(c == 200 for c, _ in more),
        )
    finally:
        sampler.stop_.set()
        stop(proc)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
