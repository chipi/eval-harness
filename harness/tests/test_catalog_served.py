#!/usr/bin/env python3
"""What a catalog server serves is the export of one state of the data (RFC-040 tests 2 and 4).

    python tests/test_catalog_served.py

In a throwaway tutorial project with production's recorded arm ($0, offline), in either store (the store matrix runs it
in both):

  - over HTTP (test 2): every page of the project fetched from a real `evh catalog-serve` process, the p-value cache
    off and on, is the export's, but for the footer's time (another process's clock);
  - across a change (test 4): six readers fetch every page again and again over HTTP while the goal's title is edited
    four times. After each edit the project is exported; every page a reader got is the export of one state, whole
    (never a mix of two), and every page the export badges "recorded" carries the badge, in every state.

The same equality on this repository's own runs is in tests/test_catalog_render_real.py.
"""

import json
import os
import random
import re
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

proj = Path(tempfile.mkdtemp(prefix="evh-served-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-served")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    env.pop(k, None)
    os.environ.pop(k, None)
os.environ.update(env)

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/
import _cli  # noqa: E402
import _render_proj  # noqa: E402
import _runstore  # noqa: E402
import _serve  # noqa: E402
from evaluation_harness import _store  # noqa: E402
from evaluation_harness import catalog_build as cb  # noqa: E402
from evaluation_harness import catalog_serve as cs  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402
from evaluation_harness.catalog_adapter import load_catalog_adapter  # noqa: E402

KIT = HARNESS / "tutorial"
GOAL = "tickets_summary"
SETS = [
    "title=Ticket summaries", "statement=A one-line summary of a support ticket for the person triaging it.",
    "decision=Which system writes the summary.", "success_criteria.primary.measure=overlap_f1",
    "success_criteria.primary.direction=higher", "datasets.0.dataset_id=tk_v1", "datasets.0.role=test",
]  # fmt: skip
BUILT = "2026-11-23 12:00 UTC"
TOKEN = "test-token"


def evh(*args):
    return _cli.run(proj, env, *args)


def get(port: int, path: str) -> tuple[int, str]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": f"127.0.0.1:{port}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def export() -> dict[str, str]:
    """{path: page} of the project as it is now, exported with the fixed time, assets left out."""
    out = proj / ".build" / "served-export"
    shutil.rmtree(out, ignore_errors=True)
    cb.prepare(load_catalog_adapter(None), built=BUILT).export(out)
    return {
        p.relative_to(out).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.relative_to(out).parts[0] != "assets"
    }


try:
    r = evh("init", "--store", store_under_test(), "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("label-import", "--sheet", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold", "--reason", "the kit's summaries, for the served test", "--by", "t"),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    for cid, n in (("one_v1", 1), ("two_v1", 2)):
        _runstore.write_text(
            proj, f"systems/{cid}.yaml", f"system_id: {cid}\nparams:\n  provider: echo\n  sentences: {n}\n"
        )
    for cid in ("one_v1", "two_v1"):
        r = r if r.returncode else evh("run", "--system", cid, "--dataset", "tk_v1")
    r = r if r.returncode else evh("goal-new", GOAL, *(x for s in SETS for x in ("--set", s)))
    r = r if r.returncode else _render_proj.add_recorded_arm(evh, proj)
    check(
        "setup: a project with a goal, two runs and production's recorded arm",
        r.returncode == 0,
        (r.stdout + r.stderr)[-400:],
    )

    _render_proj.p_cache("")
    state0 = export()
    badged = sorted(p for p, html in state0.items() if 'class="badge recorded"' in html)
    check(
        f"setup: the export has {len(state0)} pages, {len(badged)} of them badge a recorded arm",
        len(state0) > 20 and len(badged) > 1,
        (len(state0), badged),
    )

    # ── over HTTP, from a real process, the cache off and on ────────────────────────────────────────────────────────
    for what, path in (("off", ""), ("on", str(proj / ".cache" / "served-p.jsonl"))):
        proc, port, lines = _serve.start(proj, {**env, "EVH_P_CACHE": path})
        try:
            prefix = next(
                (
                    m.group(1)
                    for ln in lines
                    if (m := re.search(r"catalog: http://127\.0\.0\.1:\d+(\S*)", ln))
                ),
                "/",
            )
            got = {p: get(port, prefix + p) for p in sorted(state0)}
            differ = [
                p
                for p, (st, body) in got.items()
                if st != 200 or _render_proj.mask_built(body) != _render_proj.mask_built(state0[p])
            ]
            check(
                f"over HTTP from a real server, the p-value cache {what}: all {len(got)} pages are the export's",
                not differ,
                [(p, got[p][0]) for p in differ[:5]],
            )
        finally:
            _serve.stop(proc)

    # ── across a change: a server in this process, readers during four edits ────────────────────────────────────────
    cb._now = lambda: BUILT  # the server's model says the time the exports say
    cs.say = lambda line, err=False: None
    cs.FRESH_EVERY_S = 0.0
    cs.set_adapter(load_catalog_adapter(None))
    cs.Handler.prefixes = cs.served(proj / ".build" / "catalog", cs.A.data_dir)
    cs.API_TOKEN[:] = [TOKEN]
    cs.start_fresh()
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(cs.Handler, directory=str(cs.ROOT)), bind_and_activate=False
    )
    server.server_bind()
    server.server_activate()
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    prefix = cs.Handler.prefixes[0]

    def patch_title(title: str) -> int:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/goals/{GOAL}",
            data=json.dumps({"set": {"title": title}, "by": "person:t"}).encode(),
            method="PATCH",
            headers={
                "Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {TOKEN}", "X-EVH-Data": "1",
                "Content-Type": "application/json",
            },
        )  # fmt: skip
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status

    check(
        "setup: the server in this process serves the first state",
        all(get(port, prefix + p) == (200, state0[p]) for p in ("goals.html", "index.html", "arms.html")),
    )
    states = [state0]
    answers: list[tuple[str, int, str]] = []
    stop = threading.Event()
    names = sorted(state0)

    def reader(seed: int) -> None:
        mine = list(names)
        random.Random(seed).shuffle(mine)
        while not stop.is_set():
            for p in mine:
                if stop.is_set():
                    return
                st, body = get(port, prefix + p)
                answers.append((p, st, body))

    readers = [threading.Thread(target=reader, args=(k,)) for k in range(6)]
    for t in readers:
        t.start()
    codes = []
    for edit in range(1, 5):
        codes.append(patch_title(f"Served {edit}"))
        states.append(
            export()
        )  # the writes are one at a time: this is state k, whatever the readers meet meanwhile
        time.sleep(0.3)
    time.sleep(1.0)
    stop.set()
    for t in readers:
        t.join(timeout=180)
    server.shutdown()
    server.server_close()
    cs.FRESH["on"] = False
    check("four edits accepted", codes == [200] * 4, codes)
    check(
        "the states differ where the title is shown, and only there",
        {p for p in names if len({s[p] for s in states}) > 1}
        >= {"goals.html", "index.html", cb.goal_page(GOAL)}
        and any(len({s[p] for s in states}) == 1 for p in names),
        sorted(p for p in names if len({s[p] for s in states}) > 1),
    )
    bad = [(p, st) for p, st, _b in answers if st != 200]
    mixed = [p for p, st, body in answers if st == 200 and not any(body == s[p] for s in states)]
    check(
        f"{len(answers)} pages fetched while the data changed four times: each is the export of one state, whole",
        len(answers) > len(names) and not bad and not mixed,
        (bad[:3], sorted(set(mixed))[:5]),
    )
    seen_states = {
        i
        for p, st, body in answers
        for i, s in enumerate(states)
        if body == s[p] and len({x[p] for x in states}) > 1
    }
    check(
        "readers met more than one state of a page that changes (the check ran across a change)",
        len(seen_states) > 1,
        sorted(seen_states),
    )
    missing = [p for p, st, body in answers if p in badged and 'class="badge recorded"' not in body]
    check(
        f"the recorded badge is on every page that has it, in every state ({sum(p in badged for p, *_ in answers)} fetched)",
        not missing and any(p in badged for p, *_ in answers),
        sorted(set(missing))[:5],
    )
finally:
    _store.close()
    time.sleep(0.5)
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
