#!/usr/bin/env python3
"""An adapter that declares CALL_ONCE is called once per item (RFC-038 section 1, owner 2026-11-20).

    python tests/test_call_once.py

In a throwaway project with the tutorial's six tickets: an adapter with `CALL_ONCE = True` (or `call_once(params)`) is
called once per item, a failure of any kind, a transient one included, is a failed item and not exit 75, and the failed
item keeps the `meta` and cost its exception carried; the same adapter without the constant retries as before. A warm-up
is retried either way. `--resume` calls an item with no row and no start mark, and never one with an output, a failed
row or a start mark (a kill during its call); `--recall-failed` calls exactly those, records them (`recalled`), and is
refused on a run that is not call-once. The start mark is read from both stores. `arm-smoke` calls item 1 once, `--dry-run`
and the first line say so, and `evh env-check` names the knob the adapter does not use.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
from evaluation_harness import _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import _format  # noqa: E402
from evaluation_harness.model import runs as _R  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-once-"))
LOG = proj / "calls.log"
env = dict(
    os.environ,
    EVAL_HOME=str(proj),
    EVAL_BUILD_REF="test-call-once",
    EVAL_MAX_RETRIES="3",
    EVAL_RETRY_MAX_DELAY="0",
    CALL_LOG=str(LOG),
    TICKETS=str(proj / "tutorial" / "tickets"),
)
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "FAIL_ON", "FAIL_KIND", "KILL_ON"):
    env.pop(k, None)


def evh(*args, **extra):
    e = {**env, **{k: v for k, v in extra.items() if v is not None}}
    for k, v in extra.items():
        if v is None:
            e.pop(k, None)
    return _cli.run(proj, e, *args, timeout=300)


BODY = """
import os
import signal
from pathlib import Path

from evaluation_harness import _common
from evaluation_harness.adapter import Result, score  # noqa: F401

IDS = None


class WithMeta(Exception):
    meta = {"trial": "T1"}
    cost_usd = 0.02


def _item(text):
    global IDS
    if IDS is None:
        IDS = {p.read_text(): p.stem for p in Path(os.environ["TICKETS"]).glob("*.txt")}
    return IDS[text]


def warmup(params):
    mark = Path(os.environ["CALL_LOG"]).with_name("warm.log")
    seen = mark.read_text() if mark.exists() else ""
    mark.write_text(seen + "w\\n")
    if params.get("warm_fails") and not seen:
        raise RuntimeError("503 Service Unavailable")


def call_system(text, params):
    item = _item(text)
    with open(os.environ["CALL_LOG"], "a") as fh:
        fh.write(item + "\\n")
    if item in os.environ.get("KILL_ON", "").split(","):
        os.kill(os.getpid(), signal.SIGKILL)
    if item in os.environ.get("FAIL_ON", "").split(","):
        kind = os.environ.get("FAIL_KIND", "timeout")
        if kind == "meta":
            raise WithMeta("the trial ended badly")
        if kind == "cap":
            raise _common.CostCapExceeded("the cap")
        raise TimeoutError("timed out")
    return Result(output=text[:80], cost_usd=0.0)
"""

ADAPTERS = {
    "once": "CALL_ONCE = True\n" + BODY,
    "plain": BODY,
    "percall": "CALL_ONCE = False\n\n\ndef call_once(params):\n    return bool(params.get('once'))\n" + BODY,
}


def calls(item=None):
    got = LOG.read_text(encoding="utf-8").split() if LOG.exists() else []
    return got.count(item) if item else got


def reset():
    LOG.unlink(missing_ok=True)


def record(rid):
    with _runstore._InProject(proj):
        first = _R.first_score(rid)
        return (_R.record(first) if first else None) or {}


def run_json(rid):
    try:
        return _runstore.read_json(proj, f"runs/{rid}/run.json")
    except (OSError, ValueError):
        return {}


def rows_of(rid):
    with _runstore._InProject(proj):
        first = _R.first_score(rid)
        return _runstore.rows(first) if first else []


def checkpoint_of(rid):
    with _runstore._InProject(proj):
        return _outputs.rows(_R.run_dir(rid), partial=True) or []


try:
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    if not _runstore.sqlite():
        (proj / "data" / "systems").mkdir(parents=True)
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    r = (
        r
        if r.returncode
        else evh(
            "label-import",
            "--sheet",
            str(KIT / "gold"),
            "--dataset-id",
            "tickets_v1",
            "--set",
            "g",
            "--by",
            "owner",
        )
    )
    r = r if r.returncode else evh(
        "reference-promote", "--dataset-id", "tickets_v1", "--labels", "g", "--tier", "gold",
        "--reason", "The kit's hand-written summaries decide.", "--by", "owner",
    )  # fmt: skip
    check("setup: the tutorial dataset and its gold", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    for name, text in ADAPTERS.items():
        (proj / f"{name}.py").write_text(text, encoding="utf-8")
    for sid, adapter, params in (
        ("once_v1", "once", "{}"),
        ("plain_v1", "plain", "{}"),
        ("on_v1", "percall", "{once: true}"),
        ("off_v1", "percall", "{once: false}"),
        ("warm_v1", "once", "{warm_fails: true}"),
        ("rep_v1", "once", "{}"),
        ("smoke_once_v1", "once", "{}"),
        ("smoke_plain_v1", "plain", "{}"),
    ):
        _runstore.write_text(
            proj, f"systems/{sid}.yaml", f"system_id: {sid}\nadapter: {adapter}.py\nparams: {params}\n"
        )

    # --- the adapter says it: one call, a failure is a failed item, whatever the failure ---
    reset()
    r = evh("run", "--system", "once_v1", "--dataset", "tickets_v1", "--run-id", "A1", FAIL_ON="t02_invoice")
    out = r.stdout + r.stderr
    m = record("A1")
    check(
        "CALL_ONCE: a transient failure ('timed out') is called once, and is a failed item (exit 0, not 75)",
        r.returncode == 0 and calls("t02_invoice") == 1 and len(m.get("failed_items") or []) == 1,
        out[-500:],
    )
    check(
        "... the run says at its start that it calls each item once",
        "calls each item once" in out,
        out[:600],
    )
    check(
        "... the run record says call_once, in run.json and in the score's record",
        run_json("A1").get("call_once") is True and m.get("call_once") is True,
        (run_json("A1").get("call_once"), m.get("call_once")),
    )
    check(
        "... every other item is called once",
        sorted(calls())
        == sorted(["t01_login", "t02_invoice", "t03_export", "t04_api", "t05_delete", "t06_mobile"]),
        calls(),
    )

    reset()
    r = evh("run", "--system", "plain_v1", "--dataset", "tickets_v1", "--run-id", "P1", FAIL_ON="t02_invoice")
    check(
        "without the constant, the same adapter is retried EVAL_MAX_RETRIES times, then stops with 75 (unchanged)",
        r.returncode == 75 and calls("t02_invoice") == 3,
        (calls("t02_invoice"), (r.stdout + r.stderr)[-300:]),
    )
    check(
        "... and a run that is not call-once does not say so, nor record it",
        "calls each item once" not in (r.stdout + r.stderr) and "call_once" not in run_json("P1"),
        run_json("P1"),
    )

    reset()
    r = evh("run", "--system", "on_v1", "--dataset", "tickets_v1", "--run-id", "C1", FAIL_ON="t02_invoice")
    check(
        "call_once(params) true for this system: called once, exit 0",
        r.returncode == 0 and calls("t02_invoice") == 1,
        (calls("t02_invoice"), (r.stdout + r.stderr)[-300:]),
    )
    reset()
    r = evh("run", "--system", "off_v1", "--dataset", "tickets_v1", "--run-id", "C2", FAIL_ON="t02_invoice")
    check(
        "call_once(params) false wins over CALL_ONCE = False's absence: this system retries",
        r.returncode == 75 and calls("t02_invoice") == 3,
        (calls("t02_invoice"), (r.stdout + r.stderr)[-300:]),
    )

    # --- a failed item keeps what its exception carried ---
    reset()
    r = evh(
        "run",
        "--system",
        "once_v1",
        "--dataset",
        "tickets_v1",
        "--run-id",
        "M1",
        FAIL_ON="t02_invoice",
        FAIL_KIND="meta",
    )
    bad: dict = next((x for x in rows_of("M1") if x.get("failed") == 1.0), {})
    check(
        "a failed item keeps the meta and the cost its exception carried (exc.meta, exc.cost_usd)",
        r.returncode == 0
        and (bad.get("_meta") or {}).get("trial") == "T1"
        and bad.get("cost_usd") == 0.02
        and "WithMeta" in ((bad.get("_meta") or {}).get("call_error") or ""),
        bad,
    )
    check(
        "... and the cost is in the run's total",
        abs(float(record("M1").get("scores", {}).get("total_cost_usd", 0)) - 0.02) < 1e-9,
        record("M1").get("scores"),
    )

    # --- the warm-up is retried ---
    reset()
    (proj / "warm.log").unlink(missing_ok=True)
    r = evh("run", "--system", "warm_v1", "--dataset", "tickets_v1", "--run-id", "W1")
    check(
        "the warm-up of a call-once adapter is retried (a transient failure there does not end the run)",
        r.returncode == 0 and (proj / "warm.log").read_text(encoding="utf-8").count("w") == 2,
        (
            (proj / "warm.log").read_text(encoding="utf-8") if (proj / "warm.log").exists() else None,
            (r.stdout + r.stderr)[-300:],
        ),
    )

    # --- resume: never again what may have happened ---
    reset()
    r1 = evh("run", "--system", "once_v1", "--dataset", "tickets_v1", "--run-id", "R1", FAIL_ON="t02_invoice")
    reset()
    r2 = evh("run", "--system", "once_v1", "--dataset", "tickets_v1", "--run-id", "R2", "--resume", "R1")
    out = r2.stdout + r2.stderr
    check(
        "--resume of a call-once run: the failed item is not called again, and nothing else is",
        r2.returncode == 0 and calls() == [],
        (calls(), out[-500:]),
    )
    check(
        "... the run lists it by id with its error and names the flag",
        "1 item(s) were called once already and not again" in out
        and "t02_invoice" in out
        and "timed out" in out
        and "--recall-failed" in out
        and "repeats their side effects" in out,
        out[-700:],
    )
    m2 = record("R2")
    check(
        "... it stays a failed item of the new run, its error kept, and nothing is recalled",
        [f["item_id"] for f in m2.get("failed_items") or []] == ["t02_invoice"]
        and "timed out" in (m2.get("failed_items") or [{}])[0].get("error", "")
        and not m2.get("recalled"),
        m2.get("failed_items"),
    )
    reset()
    r3 = evh(
        "run",
        "--system",
        "once_v1",
        "--dataset",
        "tickets_v1",
        "--run-id",
        "R3",
        "--resume",
        "R2",
        "--recall-failed",
    )
    m3 = record("R3")
    check(
        "--resume --recall-failed calls exactly the failed item, once, and records it (recalled)",
        r3.returncode == 0
        and calls() == ["t02_invoice"]
        and m3.get("recalled") == ["t02_invoice"]
        and not m3.get("failed_items")
        and run_json("R3").get("recalled") == ["t02_invoice"],
        (calls(), m3.get("recalled"), (r3.stdout + r3.stderr)[-400:]),
    )
    check(
        "... the recalled item now has an output, so one more resume calls nothing and recalls nothing",
        evh(
            "run", "--system", "once_v1", "--dataset", "tickets_v1", "--run-id", "R3b", "--resume", "R3"
        ).returncode
        == 0
        and calls() == ["t02_invoice"]
        and not record("R3b").get("recalled"),
        calls(),
    )

    # --- the dry run of a resume says what it would call ---
    reset()
    d1 = evh("run", "--system", "once_v1", "--dataset", "tickets_v1", "--resume", "R2", "--dry-run")
    d2 = evh(
        "run",
        "--system",
        "once_v1",
        "--dataset",
        "tickets_v1",
        "--resume",
        "R2",
        "--recall-failed",
        "--dry-run",
    )
    check(
        "the dry run of a resume prices only what it would call: nothing without --recall-failed, the one held item with it, and nothing is called",
        d1.returncode == 0
        and "0 call(s) in all" in d1.stdout
        and "not called; --recall-failed would call them" in d1.stdout
        and d2.returncode == 0
        and "1 call(s) in all" in d2.stdout
        and "CALLED AGAIN" in d2.stdout
        and "API calls   1" in d2.stdout
        and calls() == [],
        (d1.stdout[-500:], d2.stdout[-500:]),
    )

    # --- a kill during a call: the start mark ---
    reset()
    r = evh("run", "--system", "once_v1", "--dataset", "tickets_v1", "--run-id", "K1", KILL_ON="t03_export")
    marks = [x.get("_started") for x in checkpoint_of("K1") if "_started" in x]
    done = [x.get("item_id") for x in checkpoint_of("K1") if x.get("item_id")]
    check(
        "a kill (SIGKILL) during item 3's call leaves its start mark in the checkpoint, beside the rows of items 1 and 2",
        r.returncode != 0
        and marks == ["t01_login", "t02_invoice", "t03_export"]
        and done == ["t01_login", "t02_invoice"],
        (r.returncode, marks, done),
    )
    reset()
    r = evh("run", "--system", "once_v1", "--dataset", "tickets_v1", "--run-id", "K2", "--resume", "K1")
    out = r.stdout + r.stderr
    check(
        "--resume: the in-doubt item (a start mark, no row) is not called; the items never started are",
        r.returncode == 0 and sorted(calls()) == ["t04_api", "t05_delete", "t06_mobile"],
        (calls(), out[-500:]),
    )
    check(
        "... and listed as in doubt, with the flag",
        "t03_export" in out and "in doubt" in out and "--recall-failed" in out,
        out[-600:],
    )
    k2 = record("K2")
    check(
        "... it is a failed item of the new run, so one more resume still does not call it",
        [f["item_id"] for f in k2.get("failed_items") or []] == ["t03_export"]
        and (
            evh(
                "run", "--system", "once_v1", "--dataset", "tickets_v1", "--run-id", "K2b", "--resume", "K2"
            ).returncode
            == 0
        )
        and "t03_export" not in calls(),
        k2.get("failed_items"),
    )
    reset()
    r = evh(
        "run",
        "--system",
        "once_v1",
        "--dataset",
        "tickets_v1",
        "--run-id",
        "K3",
        "--resume",
        "K2",
        "--recall-failed",
    )
    check(
        "--recall-failed calls the in-doubt item once and records it",
        r.returncode == 0 and calls() == ["t03_export"] and record("K3").get("recalled") == ["t03_export"],
        (calls(), (r.stdout + r.stderr)[-300:]),
    )

    # --- the cost cap inside a call of a call-once item ---
    reset()
    r = evh(
        "run",
        "--system",
        "once_v1",
        "--dataset",
        "tickets_v1",
        "--run-id",
        "X1",
        FAIL_ON="t03_export",
        FAIL_KIND="cap",
    )
    reset()
    r2 = evh("run", "--system", "once_v1", "--dataset", "tickets_v1", "--run-id", "X2", "--resume", "X1")
    check(
        "the provider's cap raised inside a call-once item stops the run (exit 4) and the item is not called by --resume",
        r.returncode == 4 and "t03_export" not in calls() and "t03_export" in (r2.stdout + r2.stderr),
        (r.returncode, calls(), (r2.stdout + r2.stderr)[-300:]),
    )

    # --- refusals ---
    r = evh(
        "run",
        "--system",
        "plain_v1",
        "--dataset",
        "tickets_v1",
        "--run-id",
        "Z1",
        "--resume",
        "P1",
        "--recall-failed",
    )
    check(
        "--recall-failed on a run that is not call-once: ERROR (bad-argument)",
        r.returncode != 0 and "ERROR (bad-argument)" in r.stderr,
        (r.stdout + r.stderr)[-300:],
    )
    r = evh("run", "--system", "once_v1", "--dataset", "tickets_v1", "--run-id", "Z2", "--recall-failed")
    check(
        "--recall-failed without --resume: ERROR (bad-argument)",
        r.returncode != 0 and "ERROR (bad-argument)" in r.stderr,
        (r.stdout + r.stderr)[-300:],
    )

    # --- repeats, the dry run, the smoke, env-check ---
    reset()
    r = evh("run", "--system", "rep_v1", "--dataset", "tickets_v1", "--repeat", "2")
    check(
        "--repeat 2 is allowed on a call-once arm: 12 real calls",
        r.returncode == 0 and len(calls()) == 12,
        (len(calls()), (r.stdout + r.stderr)[-300:]),
    )
    reset()
    r = evh("run", "--system", "once_v1", "--dataset", "tickets_v1", "--dry-run")
    check(
        "--dry-run says the arm calls each item once, and calls nothing",
        r.returncode == 0 and "calls each item once" in r.stdout and calls() == [],
        r.stdout[-500:],
    )
    reset()
    r = evh("arm-smoke", "--system", "smoke_once_v1", "--dataset", "tickets_v1", "--items", "2")
    check(
        "arm-smoke of a call-once arm: one call per item, item 1 not called twice, and it says so",
        calls() == ["t01_login", "t02_invoice"]
        and "call once: item 1 not called twice, determinism not checked" in r.stdout
        and "2 real call" in r.stdout,
        (calls(), r.stdout[-600:]),
    )
    reset()
    r = evh("arm-smoke", "--system", "smoke_plain_v1", "--dataset", "tickets_v1", "--items", "2")
    check(
        "arm-smoke of an arm that is not: item 1 is called twice, as before",
        calls() == ["t01_login", "t01_login", "t02_invoice"] and "call once" not in r.stdout,
        (calls(), r.stdout[-300:]),
    )
    r = evh("env-check")
    check(
        "env-check says EVAL_MAX_RETRIES is not used by an adapter that declares CALL_ONCE",
        "CALL_ONCE" in r.stdout and "EVAL_MAX_RETRIES" in r.stdout,
        r.stdout[-800:],
    )
    r = evh("validate")
    out = r.stdout + r.stderr
    check(
        "validate reads the records of call-once runs, `call_once` and `recalled` among them, with no schema complaint",
        "call_once" not in out
        and "recalled" not in out
        and "additional" not in out.lower()
        and "Traceback" not in out,
        out[-600:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
