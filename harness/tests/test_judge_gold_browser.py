#!/usr/bin/env python3
"""F1 in a real browser: where the judge and the gold disagree, on the inspector's sheet and item view (UXS-002 04, 05).

    .venv/bin/python tests/test_judge_gold_browser.py

A judge validated on twelve rated items agrees with the people's ratings on some and not on others
(`_judge_gold.build`). The sheet marks the items it disagrees on, counts them, and its filter "only where the judge
disagrees with the gold" keeps exactly those; opening an item says, in the item view, which it is.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _judge_gold as gold  # noqa: E402
import _slow  # noqa: E402
from evaluation_harness import judge_validation as jva  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


def serve(proj: Path, env: dict, log: Path) -> tuple:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.Popen(
            [sys.executable, "-m", "evaluation_harness", "catalog-serve", "--port", str(port)],
            cwd=proj,
            env=env,
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    for _ in range(150):
        if "catalog:" in log.read_text(encoding="utf-8"):
            return p, f"http://127.0.0.1:{port}"
        if p.poll() is not None:
            raise SystemExit(f"catalog-serve exited:\n{log.read_text(encoding='utf-8')}")
        time.sleep(0.1)
    raise SystemExit("catalog-serve did not start")


def api(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=60) as r:  # noqa: S310 - the test's own server  # nosec B310
        return json.loads(r.read())


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print("  FAIL Playwright is not installed: `make browser-install` (requirements-browser.txt)")
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="evh-judge-gold-b-"))
    server = None
    try:
        env = {
            **os.environ,
            "PYTHONPATH": str(HARNESS),
            "EVAL_BUILD_REF": "judge-gold-b",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        for k in ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_STORE"):
            env.pop(k, None)
        info = gold.build(tmp, env)
        arm, ds, items = info["arm"], info["dataset"], info["items"]
        r = gold.evh(tmp, env, "catalog")
        if r.returncode:
            raise SystemExit(f"catalog: {r.stdout}{r.stderr}")
        server, base = serve(tmp, env, tmp / "serve.log")
        ref = urllib.parse.quote("gold/" + ds)
        # the expected: each item's own term of the figure, from the stored verdict and the people's ratings
        want = set()
        for i in items:
            v = api(base, f"/api/item?arms={urllib.parse.quote(arm)}&item={i}&ref={ref}")
            got = jva.agreement(jva.score(v["views"][arm]["text"], v["reference"]["view"]["text"]))
            if got is not None and not got["agrees"]:
                want.add(i)
        check(
            "fixture: the judge agrees on some items and disagrees on others",
            0 < len(want) < len(items),
            len(want),
        )

        with sync_playwright() as pw:
            browser = _slow.launch(pw)
            page = browser.new_page()
            errors: list = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(
                f"{base}/.build/catalog/inspect.html?dataset={ds}&sheet=1&runs={urllib.parse.quote(arm)}&show=all"
            )
            page.wait_for_selector("#sheettable tbody tr", timeout=20000)
            page.get_by_text("show all", exact=False).first.click() if page.locator(
                "text=show all"
            ).count() else None
            rows = page.locator("#sheettable tbody tr")
            marked = set(
                page.locator("#sheettable tbody tr:has(.sig-judge)").evaluate_all(
                    "els => els.map(e => e.dataset.ep)"
                )
            )
            check(
                "sheet: a row the judge disagrees on carries the marker `judge ≠ gold`, and only those",
                marked == want and rows.count() <= len(items),
                (sorted(marked), sorted(want), rows.count()),
            )
            counts = page.locator("#scounts").inner_text()
            check(
                "sheet: the counts say how many the judge disagrees on",
                f"{len(want)} judge ≠ gold" in counts,
                counts,
            )
            box = page.locator('input.sonly[value="judge"]')
            label = box.locator("xpath=..").inner_text()
            check(
                "sheet: a filter says in words what it keeps: only where the judge disagrees with the gold",
                "the judge disagrees with the gold" in label,
                label,
            )
            box.check()
            page.wait_for_function("new URLSearchParams(location.search).getAll('only').includes('judge')")
            page.wait_for_selector("#sheettable tbody tr", timeout=20000)
            if page.locator("text=show all").count():
                page.get_by_text("show all", exact=False).first.click()
            shown = set(
                page.locator("#sheettable tbody tr").evaluate_all("els => els.map(e => e.dataset.ep)")
            )
            check(
                "sheet: the filter shows exactly the items the judge disagrees on (the address says only=judge)",
                shown == want and "only=judge" in page.url,
                (sorted(shown), sorted(want), page.url),
            )
            # the item view: one that disagrees, one that agrees
            agree_item = next(i for i in items if i not in want)
            disagree_item = sorted(want)[0]
            for it, word in ((disagree_item, "disagrees"), (agree_item, "agrees")):
                page.goto(
                    f"{base}/.build/catalog/inspect.html?dataset={ds}&sheet=1&runs={urllib.parse.quote(arm)}&item={it}"
                )
                page.wait_for_selector("#drill, .outtext", timeout=20000)
                page.wait_for_function("document.body.innerText.includes('judge vs gold')", timeout=20000)
                text = page.locator("body").inner_text()
                line = next((ln for ln in text.splitlines() if "judge vs gold" in ln), "")
                check(
                    f"item view: {it} says the judge {word} with the gold, with the figure's number and its chance",
                    f"judge vs gold {word}" in line and "chance" in line and "top1" in line,
                    line,
                )
            check("no page error", not errors, errors[:3])
            browser.close()
    finally:
        if server is not None:
            os.killpg(server.pid, signal.SIGTERM)
            server.wait(timeout=10)
        shutil.rmtree(tmp, ignore_errors=True)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
