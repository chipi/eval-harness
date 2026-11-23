#!/usr/bin/env python3
"""F1 (PLAN_0.8.1): where the judge and the gold disagree, on the inspector (UXS-002 04 and 05).

    .venv/bin/python tests/test_judge_gold.py

A judge validated against people's ratings is a run whose per-item score is the figure's own term: `judge_validation.score`
(tau, top1 against top1_chance, pair_agreement against 0.5). The item disagrees with the gold when that term is under its
chance level (`judge_validation.agreement`). Checked here:

- the definition, per mode, and that an item it cannot read has none;
- the item view says, for a validation run, whether the judge agreed (the same words in the terminal's `comparison-item`);
- the sheet has a signal `judge` (flag `--judge-disagrees`, `only=judge`): exactly the disagreeing items, counted;
- a public server shows the marker only where the deployment publishes the outputs and the references (the marker is a
  comparison of the verdict with the reference, and a public reader must not learn the reference from it).

The project is built by `_judge_gold.build` (free: the judge is the seeded random one).
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
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _judge_gold as gold  # noqa: E402
from evaluation_harness import judge_validation as jva  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

MARK = "judge vs gold"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(proj: Path, env: dict, log: Path, *args: str) -> tuple:
    port = free_port()
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.Popen(
            [sys.executable, "-m", "evaluation_harness", "catalog-serve", "--port", str(port), *args],
            cwd=proj,
            env=env,
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    for _ in range(150):
        if "catalog:" in log.read_text(encoding="utf-8") or "inspector API on" in log.read_text(
            encoding="utf-8"
        ):
            return p, port
        if p.poll() is not None:
            raise SystemExit(f"catalog-serve exited:\n{log.read_text(encoding='utf-8')}")
        time.sleep(0.1)
    raise SystemExit(f"catalog-serve did not start:\n{log.read_text(encoding='utf-8')}")


def get(port: int, path: str, host: str | None = None) -> tuple:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def agrees(term: dict) -> bool | None:
    """The item's verdict, None when it has none."""
    a = jva.agreement(term)
    return None if a is None else a["agrees"]


# ── the definition ────────────────────────────────────────────────────────────────────────────────────────────────────
check(
    "agreement, grade: tau against 0 (a tau under 0 disagrees, 0 and over does not)",
    agrees({"tau": -0.2, "parsed": 1.0}) is False
    and agrees({"tau": 0.0, "parsed": 1.0}) is True
    and agrees({"tau": 0.4, "parsed": 1.0}) is True,
)
check(
    "agreement, pick: top1 against the item's own top1_chance",
    agrees({"top1": 0.0, "top1_chance": 0.25}) is False
    and agrees({"top1": 0.5, "top1_chance": 0.25}) is True
    and agrees({"top1": 1.0, "top1_chance": 1.0}) is True,
)
check(
    "agreement, pairwise: pair_agreement against 0.5 (a tie counts half: all ties agree)",
    agrees({"pair_agreement": 0.25, "n_pairs": 4.0}) is False
    and agrees({"pair_agreement": 0.5, "n_pairs": 4.0}) is True,
)
check(
    "agreement: an unreadable verdict, or a score of another kind, has none",
    jva.agreement({"parsed": 0.0}) is None and jva.agreement({"acc": 0.3}) is None,
)
a = jva.agreement({"top1": 0.0, "top1_chance": 0.25}) or {}
check(
    "agreement: names the figure's metric, its value and its chance level",
    (a.get("metric"), a.get("value"), a.get("chance")) == ("top1", 0.0, 0.25),
    a,
)

# ── a validated judge, on the server ──────────────────────────────────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp(prefix="evh-judge-gold-"))
procs: list = []
try:
    env = {
        **os.environ,
        "PYTHONPATH": str(HARNESS),
        "EVAL_BUILD_REF": "judge-gold",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for k in ("EVAL_HOME", "EVAL_DATA_DIR", "EVAL_STORE"):
        env.pop(k, None)
    info = gold.build(tmp, env)
    arm, ds, items = info["arm"], info["dataset"], info["items"]
    r = gold.evh(tmp, env, "catalog")
    check(
        "setup: the catalog builds over the validated judge", r.returncode == 0, (r.stdout + r.stderr)[-300:]
    )
    p, port = serve(tmp, env, tmp / "local.log")
    procs.append(p)

    ref = "gold/" + ds
    views = {i: get(port, f"/api/item?arms={arm}&item={i}&ref={urllib.parse.quote(ref)}")[1] for i in items}
    # what the figure says of each item, from the stored verdict and the people's ratings, by the adapter's own score()
    said = {i: jva.score(v["views"][arm]["text"], v["reference"]["view"]["text"]) for i, v in views.items()}
    want = {i for i, s in said.items() if (jva.agreement(s) or {}).get("agrees") is False}
    check(
        "fixture: the judge agrees with the gold on some items and disagrees on others",
        0 < len(want) < len(items),
        (len(want), len(items)),
    )

    marks = {i: (v["views"][arm].get("info") or {}).get(MARK, "") for i, v in views.items()}
    check(
        "item view: a validation run's item says whether the judge agreed with the gold, on every item, rightly",
        all(marks[i].startswith("disagrees") if i in want else marks[i].startswith("agrees") for i in items),
        marks,
    )
    check(
        "item view: the mark names the figure's own number and its chance level",
        all("top1" in m and "chance" in m for m in marks.values()),
        next(iter(marks.values())),
    )

    st, sheet = get(port, f"/api/sheet?dataset={ds}&runs={urllib.parse.quote(arm)}")
    flagged = {r["item"] for r in sheet.get("rows", []) if "judge" in r["signals"]}
    check(
        "sheet: the signal `judge` is on exactly the items the judge disagrees on, and counted",
        st == 200 and flagged == want and sheet["counts"].get("judge") == len(want),
        (sorted(flagged), sorted(want), sheet.get("counts")),
    )
    st, only = get(port, f"/api/sheet?dataset={ds}&runs={urllib.parse.quote(arm)}&only=judge")
    check(
        "sheet: only=judge keeps exactly the disagreeing items",
        st == 200 and {r["item"] for r in only["rows"]} == want and only["total"] == len(items),
        (st, sorted(r["item"] for r in only.get("rows", []))),
    )

    r = gold.evh(tmp, env, "sheet-show", ds, "--runs", arm, "--judge-disagrees", "--json")
    blocks = json.loads(r.stdout)["result"]["blocks"] if r.returncode == 0 else []
    got = {x["item_id"] for b in blocks for x in b.get("rows", []) if "item_id" in x} or {r.stderr[-200:]}
    check(
        "terminal: `evh sheet-show --judge-disagrees` keeps the same items",
        got == want,
        (sorted(got), sorted(want)),
    )
    r = gold.evh(tmp, env, "comparison-item", "--runs", arm, "--item", sorted(want)[0])
    check(
        "terminal: `evh comparison-item` prints the mark",
        r.returncode == 0 and f"{MARK} disagrees" in r.stdout,
        (r.stdout + r.stderr)[-300:],
    )

    # public: the marker compares the verdict with the reference, so it is shown only where both are published
    q = f"/api/item?arms={arm}&item={sorted(want)[0]}&ref={urllib.parse.quote(ref)}"
    for publish, shown in (
        ("", False),
        ("outputs", False),
        ("references", False),
        ("outputs,references", True),
    ):
        args = ["--public", "127.0.0.1", "--rate", "100000"] + (["--publish", publish] if publish else [])
        pp, pport = serve(tmp, env, tmp / f"pub-{publish or 'none'}.log", *args)
        procs.append(pp)
        st, body = get(pport, q, host="127.0.0.1")
        mark = ((body.get("views") or {}).get(arm, {}).get("info") or {}).get(MARK)
        check(
            f"public, --publish {publish or '(nothing)'}: the mark is "
            + ("shown" if shown else "withheld, with no trace of it in the answer"),
            st == 200 and (bool(mark) if shown else (MARK not in json.dumps(body))),
            (st, mark),
        )
        os.killpg(pp.pid, signal.SIGTERM)
        pp.wait(timeout=10)
        procs.remove(pp)
finally:
    for p in procs:
        os.killpg(p.pid, signal.SIGTERM)
        p.wait(timeout=10)
    shutil.rmtree(tmp, ignore_errors=True)

sys.exit(summary())
