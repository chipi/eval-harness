#!/usr/bin/env python3
"""What `evh run` tells before and while it runs: the dry run's wording and a run's progress lines.

    python tests/test_run_progress.py

In a throwaway project ($0, offline): the dry run says what it counts and never calls an estimate an
upper bound; an adapter that declares CALLS_PER_ITEM is counted so; a measured cost from an arm-smoke
(the model record) is shown, projected over the items and repeats and named, and without one the dry
run says so and names the command; a run whose stdout is a pipe prints one `[n/N]` line per item, in
order, while it runs (not when it ends), and under --json they go to stderr.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
KIT = HERE.parent / "tutorial"
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.run import progress_every, progress_line  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-progress-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-progress", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

ADAPTER = """
import time
from types import SimpleNamespace

CALLS_PER_ITEM = 4

def call_system(text, params):
    time.sleep(float(params.get("sleep", 0)))
    return SimpleNamespace(output=text[:40], tokens_in=10, tokens_out=5, cost_usd=None,
                           latency_ms=None, extra={}, meta={})

def score(output, reference):
    return {"words": float(len(output.split()))}

PRIMARY_METRIC = "words"
"""


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def config(name, adapter=None, record=None, **params):
    p = proj / "data" / "configs" / f"{name}.yaml"
    body = "".join(f"  {k}: {json.dumps(v)}\n" for k, v in params.items())
    head = f"config_id: {name}_v1\ndataset_id: tickets_v1\n"
    head += f"adapter: {adapter}\n" if adapter else ""
    head += f"model_record: {record}\n" if record else ""
    p.write_text(head + "params:\n" + body)
    return f"data/configs/{name}.yaml"


try:
    (proj / "data" / "configs").mkdir(parents=True)
    (proj / "data" / "models").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    (proj / "calls_adapter.py").write_text(ADAPTER)
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset is frozen and materialized", r.returncode == 0, r.stderr[-300:])

    # the dry run: a one-call adapter
    priced = {"provider": "echo", "usd_per_mtok_in": 1.0, "usd_per_mtok_out": 2.0, "max_tokens": 100}
    r = evh("run", "--config", config("one", **priced), "--repeat", "3", "--dry-run", "--json")
    dry = (json.loads(r.stdout).get("result", {}).get("values", {}) if r.returncode == 0 else {}).get(
        "dry_run", {}
    )
    text = r.stderr
    check(
        "dry run: says what it counts, and that more calls per item or a growing conversation cost more",
        "one per item" in text
        and "NOT an upper bound" in text
        and "a conversation that grows" in text
        and "(upper bound: assumes" not in text,
        text[-700:],
    )
    check(
        "dry run --json: the old fields stay, and the estimate says it is not an upper bound",
        dry.get("api_calls") == 18
        and dry.get("items") == 6
        and dry.get("estimate_usd")
        and dry.get("estimate_is_upper_bound") is False
        and dry.get("calls_per_item") == 1
        and dry.get("calls_per_item_declared") is False
        and "cap_usd" in dry
        and "output_tokens_per_pass_max" in dry,
        dry,
    )
    check(
        "dry run: no arm-smoke of the config, so it says so and names the command to run before a cap",
        "MEASURED    none for one_v1" in text
        and "evh arm-smoke --config data/configs/one.yaml" in text
        and dry.get("measured_usd_per_item") is None,
        text[-700:],
    )

    # the dry run: an adapter that declares its calls
    r = evh(
        "run",
        "--config",
        config("multi", adapter="calls_adapter.py", **priced),
        "--repeat",
        "2",
        "--dry-run",
        "--json",
    )
    multi = (json.loads(r.stdout).get("result", {}).get("values", {}) if r.returncode == 0 else {}).get(
        "dry_run", {}
    )
    check(
        "dry run: an adapter's CALLS_PER_ITEM multiplies the calls and the estimate, and is named",
        multi.get("api_calls") == 6 * 2 * 4
        and multi.get("calls_per_item") == 4
        and multi.get("calls_per_item_declared") is True
        and abs(multi["estimate_usd"] - 4 * dry["estimate_usd"] * 2 / 3) < 1e-9
        and "4 per item, declared by the adapter" in r.stderr,
        (multi, r.stderr[-500:]),
    )

    # the dry run: a measured cost from an arm-smoke, read from the model record
    (proj / "data" / "models" / "mrec.yaml").write_text(
        "model_id: mrec\nkind: llm\naliases: [mrec:1b]\nsmokes:\n  measured_v1:\n    status: pass\n"
        "    at: '2026-11-03T10:00:00Z'\n    flags: []\n    report:\n      items:\n"
        "      - {item: a, s: 1.0, cost_usd: 0.004}\n      - {item: b, s: 1.0, cost_usd: 0.008}\n"
        "      projection: {items: 6, usd: 0.036}\n"
    )
    r = evh(
        "run", "--config", config("measured", record="mrec", **priced), "--repeat", "3", "--dry-run", "--json"
    )
    meas = (json.loads(r.stdout).get("result", {}).get("values", {}) if r.returncode == 0 else {}).get(
        "dry_run", {}
    )
    check(
        "dry run: the measured cost per item, projected over the items and repeats, and where it came from",
        abs(meas.get("measured_usd_per_item", 0) - 0.006) < 1e-12
        and abs(meas.get("measured_projected_usd", 0) - 0.006 * 6 * 3) < 1e-9
        and meas["measured_from"]["arm_smoke_at"] == "2026-11-03T10:00:00Z"
        and "MEASURED    $0.00600/item = $0.0360 per pass of 6 items, $0.1080 at 3 repeat(s)" in r.stderr
        and "from the arm-smoke of 2 item(s) at 2026-11-03T10:00:00Z (model record mrec)" in r.stderr,
        (meas, r.stderr[-700:], r.stdout[-300:]),
    )

    # progress lines
    check(
        "progress: a line for every item up to 2000 items, about 200 lines above",
        progress_every(6) == 1 and progress_every(2000) == 1 and progress_every(2001) == 11,
        (progress_every(2000), progress_every(2001)),
    )
    check(
        "progress: the line is [n/N] item outcome seconds, with the cost once there is one",
        progress_line(2, 6, "t2", "words=31", 1.234, 0.0) == "  [2/6] t2 words=31 1.2s"
        and progress_line(2, 6, "t2", "ok", 1.0, 0.0123).endswith("1.0s  $0.0123 so far"),
    )

    cfg = config("slow", adapter="calls_adapter.py", provider="echo", sleep=0.5)
    started = time.perf_counter()
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "run", "--config", cfg],
        cwd=proj,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines: list[tuple[float, str]] = []
    assert p.stdout is not None
    for line in p.stdout:
        lines.append((time.perf_counter() - started, line.rstrip("\n")))
    p.wait()
    ended = time.perf_counter() - started
    prog = [(t, ln) for t, ln in lines if ln.lstrip().startswith("[")]
    numbered = [ln.split()[0] for _, ln in prog]
    check(
        "progress: one [n/N] line per item, in order, outcome and seconds on each",
        p.returncode == 0
        and numbered == [f"[{k}/6]" for k in range(1, 7)]
        and all(ln.split()[2].startswith("words=") and ln.endswith("s") for _, ln in prog),
        [ln for _, ln in lines][-12:],
    )
    check(
        "progress: the first line reaches a pipe while the run is still going, not when it ends",
        bool(prog) and ended - prog[0][0] > 1.5,
        (prog[0][0] if prog else None, ended),
    )

    r = evh("run", "--config", cfg, "--json", "--run-id", "slow_json")
    done = [ln.split()[0] for ln in r.stderr.splitlines() if ln.lstrip().startswith("[")]
    check(
        "progress under --json: the lines are on stderr, and stdout is one JSON object",
        r.returncode == 0
        and done == [f"[{k}/6]" for k in range(1, 7)]
        and len(r.stdout.splitlines()) == 1
        and json.loads(r.stdout)["command"] == "run",
        r.stderr[-400:],
    )

    # 2026-11-04 (final review pass): a run's id is its config and its start to the second, and two runs started in
    # the same second shared one directory: the second wrote over the first, a committed run included. The
    # directories of the next few seconds are made first, each with a marker; the run must land in a new one.
    cid = "one_v1"
    runs = proj / "data" / "runs"
    marked = []
    t0 = time.time()
    for s in range(4):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(t0 + s))
        (runs / f"{cid}_{stamp}").mkdir(parents=True, exist_ok=True)
        (runs / f"{cid}_{stamp}" / "MARKER").write_text("an earlier run\n")
        marked.append(runs / f"{cid}_{stamp}")
    r = evh("run", "--config", "data/configs/one.yaml", "--json")
    made = json.loads(r.stdout)["result"]["values"]["runs"][0]["run_id"] if r.returncode == 0 else ""
    check(
        "run: an id already taken (a run started in the same second) is never written into: the run takes a new one",
        r.returncode == 0
        and made
        and all(m.name != made for m in marked)
        and all(sorted(p.name for p in m.iterdir()) == ["MARKER"] for m in marked),
        (r.stderr[-300:], made),
    )
    r = evh("run", "--config", "data/configs/one.yaml", "--run-id", marked[0].name)
    check(
        "run: --run-id naming a directory that exists is refused, and nothing is written into it",
        r.returncode != 0
        and "never written into another" in (r.stdout + r.stderr)
        and sorted(p.name for p in marked[0].iterdir()) == ["MARKER"],
        (r.stdout + r.stderr)[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
