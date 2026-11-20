#!/usr/bin/env python3
"""What `evh arm-smoke` and `evh run` tell about money, time and replies (0.7.1 newcomer findings).

    python tests/test_arm_smoke_report.py

In a throwaway project ($0, offline, stand-in adapters): arm-smoke says what it spent and on what basis (the
provider's bill or the system's price table), in its text and its --json values, counting the determinism
re-call; it prints each reply (an excerpt, all with --replies); a call's time is the call's real time for an
adapter that does not time itself; `evh run` says whether "spent" is the bill or the price table, and prints a
warm-up only when something was warmed; the dry run counts the system's prompt, or says it counts the item text only.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"  # the core modules (this file is in tests/)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
KIT = HERE.parent / "tutorial"
import yaml  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from _model_records import deployment, put  # noqa: E402
from evaluation_harness import _format  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-smoke-report-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-smoke-report", EVAL_MAX_RETRIES="0")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

# A stand-in for a project's adapter that calls a hosted model through the bundled provider: it does not time
# itself (latency_ms None), and it reports a bill (meta usage.cost) or only a cost it computed from a price table.
ADAPTER = """
import time
from types import SimpleNamespace

def call_system(text, params):
    time.sleep(float(params.get("sleep", 0)))
    meta = {"finish_reason": "stop"}
    if params.get("billed"):
        meta["usage"] = {"cost": 0.002}
    if params.get("source"):
        meta["cost_source"] = params["source"]
    return SimpleNamespace(output="A" * 350 + "END", tokens_in=10, tokens_out=5, cost_usd=0.002,
                           latency_ms=None, extra={}, meta=meta)

def warmup(params):
    time.sleep(float(params.get("warm", 0)))

def score(output, reference):
    return {"words": float(len(output.split()))}

PRIMARY_METRIC = "words"
"""


import _cli  # noqa: E402


def evh(*args):
    return _cli.run(proj, env, *args)


def system(name, record=None, **params):
    body = "".join(f"  {k}: {json.dumps(v)}\n" for k, v in params.items())
    head = f"system_id: {name}_v1\nadapter: smoke_adapter.py\n"
    head += f"model_record: {record}\n" if record else ""
    _runstore.write_text(proj, f"systems/{name}_v1.yaml", head + "params:\n" + body)
    return f"{name}_v1"


try:
    for d in () if _runstore.sqlite() else ("systems", "models"):
        (proj / "data" / d).mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    (proj / "smoke_adapter.py").write_text(ADAPTER)
    MREC = {
        "model_id": "mrec",
        "kind": "llm",
        "aliases": ["mrec:1b"],
        "deployments": [{"id": "here", "where": "here"}],
    }
    put(proj, MREC)
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset is frozen and materialized", r.returncode == 0, r.stderr[-300:])

    # arm-smoke: spend. 3 items + the determinism re-call of item 1 = 4 calls of $0.002.
    r = evh(
        "arm-smoke",
        "--system",
        system("priced", record="mrec", sleep=0.2, usd_per_mtok_in=0.5, usd_per_mtok_out=1.5),
        "--dataset",
        "tickets_v1",
        "--no-record",
    )
    out = r.stdout
    check(
        "arm-smoke: says what it spent, and that it is the system's price table when no bill came",
        re.search(r"spent \$0\.008000 on 4 call\(s\) \(the system's price table", out) is not None,
        out[-900:],
    )
    r = evh(
        "arm-smoke",
        "--system",
        system("billed", record="mrec", sleep=0.2, billed=True),
        "--dataset",
        "tickets_v1",
        "--no-record",
    )
    check(
        "arm-smoke: says it is the provider's bill when the calls carry one",
        "spent $0.008000 on 4 call(s) (the provider's bill)" in r.stdout,
        r.stdout[-900:],
    )
    r = evh(
        "arm-smoke",
        "--system",
        system("billed2", record="mrec", sleep=0.2, billed=True),
        "--dataset",
        "tickets_v1",
        "--json",
    )
    j = json.loads(r.stdout)["result"]["values"] if r.stdout.strip().startswith("{") else {}
    check(
        "arm-smoke --json: spent_usd, calls, cost_basis, status and the items",
        abs(j.get("spent_usd", -1) - 0.008) < 1e-12
        and j.get("calls") == 4
        and j.get("cost_basis") == "bill"
        and j.get("status") in ("pass", "check")
        and len(j.get("items", [])) == 3,
        (r.stdout[:500], r.stderr[-300:]),
    )
    checks = deployment(proj, "mrec", "here").get("checks") or []
    check(
        "arm-smoke: the smoke is a check of the model's only deployment, carrying the total spent, the "
        "determinism call included",
        [(c.get("kind"), c.get("system")) for c in checks] == [("smoke", "billed2_v1")]
        and (checks[0].get("report") or {}).get("spent_usd") == 0.008
        and "smokes" not in yaml.safe_load(_runstore.read_text(proj, "models/mrec.yaml")),
        checks,
    )
    put(proj, {**MREC, "deployments": [{"id": "here", "where": "here"}, {"id": "there", "where": "there"}]})
    r = evh("arm-smoke", "--system", system("twodeps", record="mrec"), "--dataset", "tickets_v1")
    check(
        "arm-smoke: with two deployments and a config naming none, the smoke is not recorded, and it says why",
        "not recorded: mrec has 2 deployment(s) and the system names none" in r.stdout
        and not deployment(proj, "mrec", "here").get("checks")
        and not deployment(proj, "mrec", "there").get("checks"),
        r.stdout[-600:],
    )
    _runstore.write_text(
        proj,
        "systems/named_v1.yaml",
        "system_id: named_v1\nadapter: smoke_adapter.py\nmodel_record: mrec\ndeployment: there\nparams: {}\n",
    )
    r = evh("arm-smoke", "--system", "named_v1", "--dataset", "tickets_v1")
    check(
        "arm-smoke: a config naming a deployment records the smoke on that deployment only",
        [c.get("system") for c in deployment(proj, "mrec", "there").get("checks") or []] == ["named_v1"]
        and not deployment(proj, "mrec", "here").get("checks")
        and "written into data/deployments/mrec/there.yaml" in r.stdout,
        r.stdout[-600:],
    )

    # arm-smoke: replies
    r = evh("arm-smoke", "--system", system("rep", sleep=0.0), "--dataset", "tickets_v1", "--no-record")
    check(
        "arm-smoke: prints each item's reply, an excerpt of 300 characters, and says how to see all",
        r.stdout.count("reply:") == 3
        and "A" * 300 in r.stdout
        and "A" * 301 not in r.stdout
        and "END" not in r.stdout
        and "--replies" in r.stdout,
        r.stdout[-1200:],
    )
    r = evh("arm-smoke", "--system", "rep_v1", "--dataset", "tickets_v1", "--no-record", "--replies")
    check("arm-smoke --replies: the whole reply", "A" * 350 + "END" in r.stdout, r.stdout[-1200:])

    # arm-smoke: the call's own time. The item took >= 0.4 s; the call line must not say 0.0
    r = evh("arm-smoke", "--system", system("slow", sleep=0.4), "--dataset", "tickets_v1", "--no-record")
    calls = re.findall(r"call\s+(\d+\.\d+) s", r.stdout)
    check(
        "arm-smoke: a call line shows the call's real time for an adapter that does not time itself",
        len(calls) == 3 and all(float(c) >= 0.35 for c in calls),
        r.stdout[-1200:],
    )

    # evh run: spent says its basis; warm-up only when something was warmed
    r = evh(
        "run",
        "--system",
        system("run_priced", sleep=0.0, usd_per_mtok_in=0.5, usd_per_mtok_out=1.5),
        "--dataset",
        "tickets_v1",
    )
    check(
        "run: 'spent' says the system's price table when no bill came and the system declares prices",
        re.search(r"spent \$0\.012000 \(the system's price table", r.stdout) is not None,
        r.stdout[-500:],
    )
    # G1 (fleet, 2026-11-18): a system with no prices whose adapter reports its own cost was labelled the
    # price table's
    r = evh("run", "--system", system("run_own", sleep=0.0), "--dataset", "tickets_v1")
    check(
        "run: 'spent' says the adapter's own figure when the system declares no prices and no bill came",
        "spent $0.012000 (the adapter's own figure, the provider sent no bill)" in r.stdout
        and "price table" not in r.stdout,
        r.stdout[-500:],
    )
    r = evh("run", "--system", system("run_gateway", sleep=0.0, source="gateway"), "--dataset", "tickets_v1")
    check(
        "run: 'spent' names the cost_source the adapter's rows carry",
        "spent $0.012000 (the adapter's own figure, cost_source gateway, the provider sent no bill)"
        in r.stdout,
        r.stdout[-500:],
    )
    # review, 2026-11-19: a system declaring prices (for the dry run's estimate) whose adapter names its cost_source
    # was still called the price table's
    r = evh(
        "run",
        "--system",
        system("run_gw_priced", sleep=0.0, source="gateway", usd_per_mtok_in=0.5, usd_per_mtok_out=1.5),
        "--dataset",
        "tickets_v1",
    )
    check(
        "run: the adapter's cost_source wins over the system's prices",
        "(the adapter's own figure, cost_source gateway, the provider sent no bill)" in r.stdout
        and "price table" not in r.stdout,
        r.stdout[-500:],
    )
    r = evh(
        "arm-smoke",
        "--system",
        system("smoke_gateway", sleep=0.0, source="gateway"),
        "--dataset",
        "tickets_v1",
        "--no-record",
    )
    check(
        "arm-smoke: names the adapter's cost_source, not the price table",
        "(the adapter's own figure, cost_source gateway, the provider sent no bill)" in r.stdout,
        r.stdout[-900:],
    )
    r = evh("run", "--system", system("run_billed", sleep=0.0, billed=True), "--dataset", "tickets_v1")
    check(
        "run: 'spent' says the provider's bill when the items carry one",
        "spent $0.012000 (the provider's bill)" in r.stdout,
        r.stdout[-500:],
    )
    check(
        "run: a warm-up that did nothing is not printed as 'warmed up in 0ms'",
        "warmed up in" not in r.stdout and "warm-up: nothing to load" in r.stdout,
        r.stdout[-900:],
    )
    r = evh("run", "--system", system("run_warm", sleep=0.0, warm=0.2), "--dataset", "tickets_v1")
    check(
        "run: a warm-up that took time is printed with its time",
        (w := re.search(r"warmed up in (\d+)ms", r.stdout)) is not None and int(w.group(1)) >= 150,
        r.stdout[-900:],
    )

    # the dry run: the prompt the config gives is counted, else the line says it counts the item text only
    r0 = evh("run", "--system", system("dry_plain"), "--dataset", "tickets_v1", "--dry-run", "--json")
    r1 = evh(
        "run",
        "--system",
        system("dry_prompt", prompt="P" * 398),
        "--dataset",
        "tickets_v1",
        "--dry-run",
        "--json",
    )
    d0 = json.loads(r0.stdout)["result"]["values"]["dry_run"]
    d1 = json.loads(r1.stdout)["result"]["values"]["dry_run"]
    check(
        "dry run: the system's prompt (plus the blank line after it) is counted in the input tokens, per item",
        abs((d1["input_tokens_per_pass"] - d0["input_tokens_per_pass"]) - 6 * 400 / 4) < 1e-9,
        (d0["input_tokens_per_pass"], d1["input_tokens_per_pass"]),
    )
    check(
        "dry run: the line says what it counts",
        "item text only" in r0.stderr and "item text + the system's prompt" in r1.stderr,
        (r0.stderr[-600:], r1.stderr[-600:]),
    )

    # G2 (fleet, 2026-11-18): with no metric named, comparison-show compared bugfix arms on `actionable`, the
    # project's most common primary metric (triage's), not on the compared arms' own `oracle_pass`. Here `words` is
    # every other arm's primary and the two compared arms' is `zeta`.
    (proj / "two_adapter.py").write_text(
        ADAPTER.replace(
            'return {"words": float(len(output.split()))}',
            'return {"words": float(len(output.split())), "zeta": 1.0}',
        ).replace('PRIMARY_METRIC = "words"', 'PRIMARY_METRIC = "zeta"')
    )
    for name in ("two_a", "two_b"):
        _runstore.write_text(
            proj,
            f"systems/{name}_v1.yaml",
            f"system_id: {name}_v1\nadapter: two_adapter.py\nparams:\n  sleep: 0\n",
        )
        r = evh("run", "--system", f"{name}_v1", "--dataset", "tickets_v1")
        check(f"setup: {name} ran", r.returncode == 0, r.stderr[-400:])
    r = evh("comparison-show", "--runs", "two_a_v1,two_b_v1", "--json")
    got = json.loads(r.stdout or "{}").get("result") or {}
    check(
        "comparison-show: with no metric named, the compared arms' own primary metric, not the project's most common",
        got.get("metric") == "zeta",
        (got.get("metric"), r.stderr[-400:]),
    )

    # G2, as the fleet re-checked it (2026-11-18): the arms' primary (`oracle_pass`) had no score per item where
    # their plain runs are read, only in another reading of one of them (`silver`), and the comparison moved to
    # another metric in silence. Here the primary `late` is scored only against a reference.
    shutil.copytree(KIT / "gold", proj / "tutorial" / "gold")
    r = evh(
        "label-import", "--sheet", "tutorial/gold", "--dataset-id", "tickets_v1", "--set", "g", "--by", "t"
    )
    check("setup: a label set to score against", r.returncode == 0, r.stderr[-400:])
    (proj / "late_adapter.py").write_text(
        ADAPTER.replace(
            'return {"words": float(len(output.split()))}',
            'return {"words": float(len(output.split()))} | ({"late": 1.0} if reference else {})',
        ).replace('PRIMARY_METRIC = "words"', 'PRIMARY_METRIC = "late"')
    )
    for name in ("late_a", "late_b"):
        _runstore.write_text(
            proj,
            f"systems/{name}_v1.yaml",
            f"system_id: {name}_v1\nadapter: late_adapter.py\nparams:\n  sleep: 0\n",
        )
        r = evh("run", "--system", f"{name}_v1", "--dataset", "tickets_v1")
        check(f"setup: {name} ran", r.returncode == 0, r.stderr[-400:])

    def said() -> str:
        c = evh("comparison-show", "--runs", "late_a_v1,late_b_v1", "--json")
        return (
            " ".join((json.loads(c.stdout or "{}").get("result") or {}).get("warnings") or [])
            + c.stderr[-300:]
        )

    note = said()
    check(
        "comparison-show: when the arms' primary has no score per item as read, it says so and names the metric used",
        "primary metric, late, has no score per item" in note
        and "compared on words instead" in note
        and "not scored for late_a_v1, late_b_v1 in any reading" in note,
        note,
    )
    r = evh("rescore", "--dataset-id", "tickets_v1", "--labels", "g", "--match", "late_a", "--by", "t")
    note = said()
    check(
        "comparison-show: and where another reading scores it (--label), and which arm has it nowhere",
        r.returncode == 0
        and "It is scored for late_a_v1 under --label labels-tickets_v1-g." in note
        and "not scored for late_b_v1 in any reading" in note,
        (r.stderr[-300:], note),
    )
    c = evh("comparison-show", "--runs", "late_a_v1", "--label", "labels-tickets_v1-g", "--json")
    got = json.loads(c.stdout or "{}").get("result") or {}
    check(
        "comparison-show: the label the note names reads the primary when passed back",
        got.get("metric") == "late",
        (got.get("metric"), c.stderr[-300:]),
    )
    from evaluation_harness.run import spend_basis

    # The scenario's mistral run: recorded total_cost_usd is rounded to 8 places, the bill is not, so the
    # remainder was 1.1e-9: printed "$0.000000 the system's price table" beside a bill that was the whole spend.
    check(
        "spend line: a remainder that prints as $0.000000 is rounding, so the short form is used",
        spend_basis(0.0010764089, 1.1e-9, True) == "the provider's bill",
        spend_basis(0.0010764089, 1.1e-9, True),
    )
    check(
        "spend line: a remainder that shows at the printed precision keeps the two figures",
        spend_basis(0.001, 0.0005, True).startswith(
            "$0.001000 the provider's bill, $0.000500 the system's price"
        ),
        spend_basis(0.001, 0.0005, True),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
