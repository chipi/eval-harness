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
import _model_records  # noqa: E402
import _runfix  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.run import price_drift, progress_every, progress_line  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-progress-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-progress", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
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


import _cli  # noqa: E402


def evh(*args):
    return _cli.run(proj, env, *args)


def system(name, adapter=None, record=None, **params):
    body = "".join(f"  {k}: {json.dumps(v)}\n" for k, v in params.items())
    head = f"system_id: {name}_v1\n"
    head += f"adapter: {adapter}\n" if adapter else ""
    head += f"model_record: {record}\n" if record else ""
    _runstore.write_text(proj, f"systems/{name}_v1.yaml", head + "params:\n" + body)
    return ["--system", f"{name}_v1", "--dataset", "tickets_v1"]


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
        (proj / "data" / "models").mkdir()
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    (proj / "calls_adapter.py").write_text(ADAPTER, encoding="utf-8")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset is frozen and materialized", r.returncode == 0, r.stderr[-300:])

    # the dry run: a one-call adapter
    priced = {"provider": "echo", "usd_per_mtok_in": 1.0, "usd_per_mtok_out": 2.0, "max_tokens": 100}
    r = evh("run", *system("one", **priced), "--repeat", "3", "--dry-run", "--json")
    dry = (json.loads(r.stdout).get("result", {}).get("values", {}) if r.returncode == 0 else {}).get(
        "dry_run", {}
    )
    text = r.stderr
    check(
        "dry run: says what it counts, and that more calls per item or a growing conversation cost more",
        "one per item" in text and "a conversation that grows" in text and "NOT an upper bound" not in text,
        text[-700:],
    )
    check(
        "dry run: the estimate is an upper bound and says so: at most, if every reply used max_tokens (080d N3)",
        "ESTIMATE    at most ~$" in text
        and "if every reply used max_tokens 100" in text
        and "a model that answers in a sentence usually costs less" in text,
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
        and "evh arm-smoke --system one_v1 --dataset tickets_v1" in text
        and dry.get("measured_usd_per_item") is None,
        text[-700:],
    )
    # The dry run's notes: no reference set is what will happen to the scoring, after the dry-run header, and
    # the advice fits the adapter and the runs there are (a dataset with no run has none to label from).
    check(
        "dry run: no reference set is a note after the dry-run header, in words of what will happen, not an error",
        r.returncode == 0
        and 0 <= text.find("DRY RUN") < text.find("no reference set for tickets_v1")
        and "quality cannot be scored" not in text
        and "output_words only" in text
        and "is not refused" in text,
        text[:900],
    )
    check(
        "dry run: with no run to label from, the advice offers a person's labels (label-sheet), not label-from-run",
        "evh label-sheet --dataset-id tickets_v1" in text and "label-from-run" not in text,
        text[:900],
    )
    r_custom = evh("run", *system("custom", adapter="calls_adapter.py", **priced), "--dry-run")
    check(
        "dry run: an adapter of the project's own is told its score(output, None) is what runs without a reference, "
        "and that the labels only add scoring against answers",
        r_custom.returncode == 0
        and "score(output, None)" in r_custom.stdout
        and "own checks" in r_custom.stdout
        and "output_words only" not in r_custom.stdout
        and "quality cannot be scored" not in r_custom.stdout
        and r_custom.stdout.find("DRY RUN") < r_custom.stdout.find("no reference set"),
        r_custom.stdout[:900],
    )
    check(
        "dry run --json: says whether the run scores without a reference",
        dry.get("scored_without_reference") is True and dry.get("typical_estimate_usd") is None,
        dry,
    )
    # A cap of 0 is a cap ("spend nothing", _spend.reached); the dry run printed it as NONE and asked for one.
    r = _cli.run(
        proj, dict(env, EVAL_MAX_COST_USD="0"), "run", *system("one", **priced), "--dry-run", "--json"
    )
    zero = (json.loads(r.stdout).get("result", {}).get("values", {}) if r.returncode == 0 else {}).get(
        "dry_run", {}
    )
    cap_line = next((ln for ln in r.stderr.splitlines() if ln.strip().startswith("cap ")), "")
    check(
        "dry run: a cap of 0 is shown as $0.00 that spends nothing, never as NONE",
        "$0.00" in cap_line
        and "spend nothing" in cap_line
        and "NONE" not in cap_line
        and zero.get("cap_usd") == 0,
        f"{cap_line!r} cap_usd={zero.get('cap_usd')!r}",
    )

    # the dry run: an adapter that declares its calls
    r = evh(
        "run",
        *system("multi", adapter="calls_adapter.py", **priced),
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
    _model_records.put(
        proj,
        {
            "model_id": "mrec",
            "kind": "llm",
            "aliases": ["mrec:1b"],
            "deployments": [{"id": "here", "where": "here"}],
            "smokes": {
                "measured_v1": {
                    "status": "pass",
                    "at": "2026-11-03T10:00:00Z",
                    "flags": [],
                    "report": {
                        "items": [
                            {"item": "a", "s": 1.0, "cost_usd": 0.004},
                            {"item": "b", "s": 1.0, "cost_usd": 0.008},
                        ],
                        "projection": {"items": 6, "usd": 0.036},
                    },
                }
            },
        },
    )
    r = evh("run", *system("measured", record="mrec", **priced), "--repeat", "3", "--dry-run", "--json")
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
    check(
        "progress: the time left at the pass's pace once it is 30 s or more (the 0.8.0 newcomer run's CPU model said "
        "nothing of its 5.7 minutes); a fast pass's line as before",
        progress_line(2, 20, "b2", "ok", 16.0, 0.0, 33.0) == "  [2/20] b2 ok 16.0s  about 5 min left"
        and progress_line(18, 20, "b18", "ok", 16.0, 0.0, 297.0).endswith("about 33 s left")
        and progress_line(2, 6, "t2", "ok", 0.1, 0.0, 0.2) == "  [2/6] t2 ok 0.1s",
        (
            progress_line(2, 20, "b2", "ok", 16.0, 0.0, 33.0),
            progress_line(18, 20, "b18", "ok", 16.0, 0.0, 297.0),
        ),
    )
    # A bill far from the system's declared prices is named (the 0.8.0 newcomer run's mistral-small row: 77 tokens in,
    # 37 out, billed $0.000013175 where its prices give $0.0000188, 0.70x); one at its prices, or a system that
    # declares none, says nothing.
    row = {"_meta": {"usage": {"cost": 1.3175e-05}}, "tokens_in": 77.0, "tokens_out": 37.0}
    priced = {"usd_per_mtok_in": 0.1, "usd_per_mtok_out": 0.3}
    at_prices = {"_meta": {"usage": {"cost": 1.88e-05}}, "tokens_in": 77.0, "tokens_out": 37.0}
    note = price_drift([row], priced) or ""
    check(
        "run: a bill far from the system's declared prices is named with the ratio; one at them, or no prices, is not",
        "the provider billed $0.000013, 0.70x" in note
        and price_drift([at_prices], priced) is None
        and price_drift([row], {}) is None,
        note,
    )

    cfg = system("slow", adapter="calls_adapter.py", provider="echo", sleep=0.5)
    started = time.perf_counter()
    p = subprocess.Popen(
        [sys.executable, str(HERE / "cli.py"), "run", *cfg],
        cwd=proj,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
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

    r = evh("run", *cfg, "--json", "--run-id", "slow_json")
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
    marked = []
    t0 = time.time()
    for s in range(4):
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(t0 + s))
        if not _runstore.sqlite():
            (proj / "data" / "runs" / f"{cid}_{stamp}").mkdir(parents=True, exist_ok=True)
        _runstore.write_text(proj, f"runs/{cid}_{stamp}/MARKER", "an earlier run\n")
        marked.append(f"{cid}_{stamp}")
    r = evh("run", "--system", "one_v1", "--dataset", "tickets_v1", "--json")
    made = json.loads(r.stdout)["result"]["values"]["runs"][0]["run_id"] if r.returncode == 0 else ""
    check(
        "run: an id already taken (a run started in the same second) is never written into: the run takes a new one",
        r.returncode == 0
        and made
        and all(m != made for m in marked)
        and all(_runstore.listdir(proj, f"runs/{m}") == ["MARKER"] for m in marked),
        (r.stderr[-300:], made),
    )
    r = evh("run", "--system", "one_v1", "--dataset", "tickets_v1", "--run-id", marked[0])
    check(
        "run: --run-id naming a directory that exists is refused, and nothing is written into it",
        r.returncode != 0
        and "never written into another" in (r.stdout + r.stderr)
        and _runstore.listdir(proj, f"runs/{marked[0]}") == ["MARKER"],
        (r.stdout + r.stderr)[-300:],
    )

    dry_priced = {"provider": "echo", "usd_per_mtok_in": 1.0, "usd_per_mtok_out": 2.0, "max_tokens": 100}
    # A dataset with a run has one to label from; the note then offers label-from-run too, and a real run prints the
    # same note where it always did (not as a failure).
    r = evh("run", *system("one", **dry_priced), "--dry-run")
    check(
        "dry run: once the dataset has a run, the advice offers label-from-run as well",
        "evh label-from-run --run" in r.stdout and "evh label-sheet" in r.stdout,
        r.stdout[:900],
    )
    r = evh("run", "--system", "one_v1", "--dataset", "tickets_v1")
    check(
        "run: no reference set is a note of what happens (scored without one), not 'cannot be scored'",
        r.returncode == 0
        and "no reference set for tickets_v1" in r.stdout
        and "quality cannot be scored" not in r.stdout,
        r.stdout[:700],
    )

    # The estimate says what it is: at most, if every reply used max_tokens; a typical one is shown where earlier runs
    # of the system recorded their output tokens, from their mean, and the recorded numbers are not touched.
    r = evh("run", "--system", "one_v1", "--dataset", "tickets_v1", "--dry-run")
    check(
        "dry run: the estimate line says 'at most' and 'if every reply used max_tokens 100', and that calls it does "
        "not count cost more",
        "ESTIMATE    at most ~$" in r.stdout
        and "if every reply used max_tokens 100" in r.stdout
        and "a conversation that grows" in r.stdout,
        r.stdout[:1200],
    )
    system("typ", **dry_priced)
    for n, out_tok in ((1, 10), (2, 30)):
        _runfix.put_run(
            proj / "data",
            {"run_id": f"typ_v1_{n}", "system_id": "typ_v1", "dataset_id": "tickets_v1", "scores": {"words": 1.0},
             "primary_metric": "words", "created_at": f"2026-11-2{n}T10:00:00Z"},
            [{"item_id": f"i{k}", "words": 1.0, "tokens_in": 50.0, "tokens_out": float(out_tok)} for k in range(4)],
        )  # fmt: skip
    r = evh("run", "--system", "typ_v1", "--dataset", "tickets_v1", "--dry-run", "--json")
    typ = json.loads(r.stdout)["result"]["values"]["dry_run"] if r.returncode == 0 else {}
    # 20 output tokens a call on average over the 8 rows of the 2 runs; 6 items
    want = typ.get("input_tokens_per_pass", 0) / 1e6 * 1.0 + 20 * 6 / 1e6 * 2.0
    check(
        "dry run: where earlier runs of the system recorded output tokens, a typical estimate from their mean, beside "
        "the at-most one (which is unchanged)",
        abs(typ.get("typical_estimate_usd", 0) - want) < 1e-12
        and typ.get("typical_output_tokens_per_item") == 20
        and typ.get("typical_from_runs") == 2
        and typ.get("estimate_usd", 0) > typ.get("typical_estimate_usd", 1)
        and "TYPICAL" in r.stderr
        and "mean of 20 tokens out" in r.stderr,
        (typ, r.stderr[:1200]),
    )
    check(
        "dry run: the at-most estimate is what it was (input at the usual rate, max_tokens out)",
        abs(
            typ.get("estimate_usd", 0)
            - (typ.get("input_tokens_per_pass", 0) / 1e6 * 1.0 + 100 * 6 / 1e6 * 2.0)
        )
        < 1e-12,
        typ,
    )

    # No model record: said once for a model, where a sweep dry-runs several systems of it.
    system("sw1", model="m1", **dry_priced)
    system("sw2", model="m1", **dry_priced)
    r = evh("sweep", "--systems", "sw1_v1", "sw2_v1", "--dataset", "tickets_v1", "--dry-run")
    out = r.stdout
    check(
        "sweep --dry-run: the 'no model record' explanation is given once for a model, each system still named",
        r.returncode == 0
        and out.count("a smoke is kept on a model's record") == 1
        and "MEASURED    none for sw1_v1" in out
        and "MEASURED    none for sw2_v1" in out
        and "as for sw1_v1 above" in out,
        out[-1800:],
    )
    r = evh("run", "--system", "sw1_v1", "--dataset", "tickets_v1", "--dry-run")
    check(
        "dry run: a single system's 'no model record' says what it means and what to do",
        "it names no model record" in r.stdout
        and "not kept" in r.stdout
        and "model_record:" in r.stdout
        and "evh arm-smoke --system sw1_v1 --dataset tickets_v1" in r.stdout,
        r.stdout[-900:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
