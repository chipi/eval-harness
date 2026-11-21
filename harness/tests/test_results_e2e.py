#!/usr/bin/env python3
"""Format 7 end to end (RFC-033): a resumed run, and the score sets added to a run later, in both stores.

    python tests/test_results_e2e.py

`evh run` with an adapter whose meta carries the three run settings and a full billing object, in a project of
the tutorial's tickets ($0, no network), once per store:

- a run that dies after three items (a hard exit in the adapter, so the crash checkpoint holds three rows), then
  `--resume`d: its rows and run.json are what the same system gives uninterrupted, but for what a resume records
  (`resumed`, `resumed_from_disk`, the `resume` block, the clock): the settings in `call` when every row held one value,
  in the rows when they did not, usage slimmed; V28 and validate pass. A finished run resumed the same way.
- later score sets of a run with a `call`, whose source rows hold a run setting again (a row from before the
  migration): `evh rescore` (another scorer: the adapter file changed), `evh judge-score` with the fake judge, `evh
  sheet-import` of a judged sheet. Each writes rows without a setting equal to the run's `call`, keeps one that
  differs, usage slimmed; run again, rescore says "already scored" and judge-score writes nothing, sheet-import
  refuses to overwrite and leaves the score as it was; the rows sheet-import writes have no `_meta` and read back so.
"""

import contextlib
import csv
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _runstore  # noqa: E402
from evaluation_harness import _outputs, _store  # noqa: E402
from evaluation_harness import validate_tree as vt  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import results as R  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

KIT = HARNESS / "tutorial"
CRASH_AT = 4  # the adapter's 4th call kills the process: three rows are on disk
GC = {"max_tokens": 300, "temperature": 0}
GC_OTHER = {"max_tokens": 300, "temperature": 0.5}
CALL = {"generation_config": GC, "generation_requested": {"max_tokens": 300}, "encoder_window": 512}
RICH = {
    "completion_tokens": 20,
    "completion_tokens_details": {"reasoning_tokens": 5},
    "cost": 0.0012,
    "cost_details": {"upstream_inference_cost": 0.001},
    "is_byok": False,
    "prompt_tokens": 100,
    "prompt_tokens_details": {"audio_tokens": 0, "cache_write_tokens": 10, "cached_tokens": 40},
    "total_tokens": 120,
}
SLIM = R.slim_usage(RICH)

ADAPTER = """
import json
import os
from types import SimpleNamespace

N = [0]
RICH = json.loads('@RICH@')


def call_system(text, params):
    N[0] += 1
    if N[0] == int(os.environ.get("EVH_E2E_CRASH_AT") or 0):
        os._exit(3)
    gc = {"max_tokens": 300, "temperature": 0}
    if params.get("vary") and sum(map(ord, text)) % 2:
        gc = {"max_tokens": 300, "temperature": 0.5}
    meta = {"generation_config": gc, "generation_requested": {"max_tokens": 300}, "encoder_window": 512,
            "usage": RICH, "provider": "p", "finish_reason": "stop"}
    return SimpleNamespace(output=text[: params.get("keep", 40)], tokens_in=10, tokens_out=5, cost_usd=0.0012,
                           latency_ms=None, extra={}, meta=meta)


def score(output, reference):
    return {"words": float(len(output.split()))@MORE@}


PRIMARY_METRIC = "words"
""".replace("@RICH@", json.dumps(RICH))


def adapter_text(second: bool = False) -> str:
    """The adapter; `second` adds a metric, so the file's hash, and with it the scorer, is another."""
    return ADAPTER.replace("@MORE@", ', "chars": float(len(output))' if second else "")


class Project:
    """A throwaway project in the store under test, and the commands and reads the checks use."""

    def __init__(self, store: str) -> None:
        self.store = store
        self.dir = Path(tempfile.mkdtemp(prefix="evh-results-e2e-"))
        self.env = dict(os.environ, EVAL_HOME=str(self.dir), EVAL_STORE=store, EVAL_BUILD_REF="test-results-e2e",
                        EVAL_MAX_RETRIES="0", EVH_ACTOR="person:tester")  # fmt: skip
        for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVH_E2E_CRASH_AT"):
            self.env.pop(k, None)
        os.environ["EVAL_HOME"] = str(self.dir)
        os.environ["EVAL_STORE"] = store
        for k in ("EVAL_DATA_DIR",):
            os.environ.pop(k, None)
        _outputs.reset()
        r = self.evh("init", "--store", store)
        (self.dir / "res_adapter.py").write_text(adapter_text())
        shutil.copytree(KIT / "tickets", self.dir / "tutorial" / "tickets")
        shutil.copy(KIT / "judge_prompt.txt", self.dir / "judge_prompt.txt")
        r = (
            r
            if r.returncode
            else self.evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
        )
        r = r if r.returncode else self.evh("dataset-materialize", "--dataset-id", "tickets_v1")
        check(
            f"{store}: setup: a project with the tutorial's tickets frozen and materialized",
            r.returncode == 0,
            tail(r),
        )

    def close(self) -> None:
        _outputs.reset()
        shutil.rmtree(self.dir, ignore_errors=True)

    def evh(self, *args, **more):
        return subprocess.run(
            [sys.executable, str(HERE / "cli.py"), *args], cwd=self.dir, env={**self.env, **more}, capture_output=True,
            text=True, stdin=subprocess.DEVNULL, timeout=600,
        )  # fmt: skip

    def system(self, name, **params):
        body = "".join(f"  {k}: {json.dumps(v)}\n" for k, v in params.items())
        _runstore.write_text(
            self.dir,
            f"systems/{name}_v1.yaml",
            f"system_id: {name}_v1\nadapter: res_adapter.py\nparams:\n{body}",
        )
        return ["--system", f"{name}_v1", "--dataset", "tickets_v1"]

    def run_dir(self, run_id):
        return self.dir / "data" / "runs" / run_id

    def run_json(self, run_id):
        with _runstore._InProject(self.dir):
            return model_runs.run(self.run_dir(run_id)) or {}

    def first_score(self, run_id):
        with _runstore._InProject(self.dir):
            return model_runs.first_score(self.run_dir(run_id))

    def first_rows(self, run_id):
        with _runstore._InProject(self.dir):
            sd = model_runs.first_score(self.run_dir(run_id))
            return _runstore.rows(sd) if sd else []

    def scores(self, run_id):
        with _runstore._InProject(self.dir):
            return list(model_runs.scores_of(self.run_dir(run_id)))

    def rows_of(self, score_dir):
        with _runstore._InProject(self.dir):
            return _runstore.rows(score_dir)

    def text_of(self, score_dir):
        with _runstore._InProject(self.dir):
            return _outputs.rows_text(score_dir)

    def record_text(self, score_dir):
        with _runstore._InProject(self.dir):
            return json.dumps(model_runs.record(score_dir), sort_keys=True)

    def watch(self):
        """The sqlite store has no file time to read: the test's own copy of the database counts every row inserted."""
        if self.store == "sqlite":
            with contextlib.closing(sqlite3.connect(self.dir / "data" / _store.DB)) as db:
                db.execute("CREATE TABLE IF NOT EXISTS _inserted (run TEXT)")
                db.execute(
                    "CREATE TRIGGER IF NOT EXISTS _count AFTER INSERT ON score_rows BEGIN INSERT INTO _inserted VALUES (NEW.item_id); END"
                )
                db.commit()

    def stamp(self, score_dir):
        """When the rows of a score were last written (files), or how many rows were inserted since `watch` (sqlite):
        equal before and after a command that is to write nothing."""
        if self.store == "files":
            f = score_dir / _outputs.PREDICTIONS
            return f.stat().st_mtime_ns if f.exists() else None
        with contextlib.closing(sqlite3.connect(self.dir / "data" / _store.DB)) as db:
            return db.execute("SELECT count(*) FROM _inserted").fetchone()[0]

    def put_first_rows(self, run_id, rows):
        with _runstore._InProject(self.dir):
            sd = model_runs.first_score(self.run_dir(run_id))
            assert sd is not None
            _runstore.put_rows(sd, rows)

    def v28(self):
        vt.problems.clear()
        with contextlib.redirect_stdout(io.StringIO()) as out, _runstore._InProject(self.dir):
            vt.v28_rows_in_format_7()
        return [p for p in vt.problems if "V28" in p], out.getvalue()

    def validate(self):
        return self.evh("validate")


def tail(r):
    return (r.stdout + r.stderr)[-500:]


def bare(row):
    """A row as a resume leaves it, less what a resume records and what is measured."""
    row = json.loads(json.dumps(row))
    for k in ("resumed", "latency_ms", "_commit"):
        row.pop(k, None)
    row.get("_meta", {}).pop("resumed_from_disk", None)
    return row


# ── a resumed run ───────────────────────────────────────────────────────────────────────────────────────────────────
def resumed(store: str) -> None:
    p = Project(store)
    try:
        # One system per case, and a different output for the one that varies: validate (V5) refuses two systems
        # whose scores are byte-identical.
        cases = {
            "const": (p.system("res_const", provider="echo"), CALL, ()),
            "vary": (
                p.system("res_vary", provider="echo", vary=True, keep=30),
                {k: v for k, v in CALL.items() if k != "generation_config"},
                ("generation_config",),
            ),
        }
        for label, (args, want_call, kept) in cases.items():
            u, c, n = f"{label}_r1", f"{label}_crash", f"{label}_r2"
            ru = p.evh("run", *args, "--run-id", u)
            rc = p.evh("run", *args, "--run-id", c, EVH_E2E_CRASH_AT=str(CRASH_AT))
            with _runstore._InProject(p.dir):
                part = _runstore.rows(p.run_dir(c), partial=True)
            check(
                f"{store}: {label}: the adapter's death leaves {CRASH_AT - 1} checkpoint rows, usage slimmed, the "
                "settings kept, no score, and a run.json without a `call`",
                ru.returncode == 0
                and rc.returncode == 3
                and len(part) == CRASH_AT - 1
                and all(x["_meta"]["usage"] == SLIM and "generation_config" in x["_meta"] for x in part)
                and not p.scores(c)
                and "call" not in p.run_json(c),
                (tail(rc), len(part), p.scores(c)),
            )
            rr = p.evh("run", *args, "--resume", c, "--run-id", n)
            ur, nr = p.first_rows(u), p.first_rows(n)
            check(
                f"{store}: {label}: --resume replays the {CRASH_AT - 1} done items and calls the other three",
                rr.returncode == 0
                and (p.run_json(n).get("resume") or {}).get("replayed_items") == CRASH_AT - 1
                and len(nr) == len(ur) == 6
                and [x["resumed"] for x in nr] == [1.0] * (CRASH_AT - 1) + [0.0] * (6 - CRASH_AT + 1),
                (tail(rr), [x.get("resumed") for x in nr]),
            )
            check(
                f"{store}: {label}: the resumed run's run.json `call` is the uninterrupted run's: "
                + ("all three settings" if not kept else "the settings that took one value"),
                p.run_json(n).get("call") == p.run_json(u).get("call") == want_call,
                (p.run_json(n).get("call"), p.run_json(u).get("call")),
            )
            check(
                f"{store}: {label}: every row of the resumed run equals the uninterrupted run's but for what a resume records",
                [bare(x) for x in nr] == [bare(x) for x in ur],
                [(a, b) for a, b in zip(map(bare, nr), map(bare, ur), strict=True) if a != b][:1],
            )
            check(
                f"{store}: {label}: usage slimmed on every row; a setting in the rows only where `call` does not hold it",
                all(x["_meta"]["usage"] == SLIM for x in nr)
                and all((k in x["_meta"]) == (k in kept) for x in nr for k in R.RUN_SETTINGS),
                nr[0]["_meta"],
            )
            if kept:
                check(
                    f"{store}: {label}: the adapter did vary the setting over the rows (else the case proves nothing)",
                    len({json.dumps(x["_meta"]["generation_config"], sort_keys=True) for x in nr}) == 2,
                )
            # A run that finished is resumed the same way: its first score holds the rows with the settings taken off,
            # and `call` is on its run.json.
            f = f"{label}_r3"
            rf = p.evh("run", *args, "--resume", u, "--run-id", f)
            fr = p.first_rows(f)
            check(
                f"{store}: {label}: a finished run resumed (all six replayed) gives the same `call` and rows",
                rf.returncode == 0
                and (p.run_json(f).get("resume") or {}).get("replayed_items") == 6
                and p.run_json(f).get("call") == want_call
                and [bare(x) for x in fr] == [bare(x) for x in ur],
                (tail(rf), p.run_json(f).get("call"), fr[:1]),
            )
            v3 = p.validate()
            check(
                f"{store}: {label}: the crashed run names its build (V3 holds with it in the project)",
                ((p.run_json(c).get("build") or {}).get("ref") or "unknown") != "unknown"
                and "ok   V3 every run identifies its build" in v3.stdout,
                (p.run_json(c).get("build"), [x for x in v3.stdout.splitlines() if "V3" in x]),
            )
            d = p.evh("data-rm", "--path", f"runs/{c}")
            check(f"{store}: {label}: the crashed run, resumed, is discarded", d.returncode == 0, tail(d))
        bad, out = p.v28()
        v = p.validate()
        check(
            f"{store}: V28 and validate pass with the resumed runs in the project",
            not bad and "ok   V28" in out and v.returncode == 0,
            (bad, v.stdout[-1500:]),
        )
    finally:
        p.close()


# ── score sets added to a run later ─────────────────────────────────────────────────────────────────────────────────
def later(store: str) -> None:
    p = Project(store)
    try:
        a_args = p.system("arm_a", provider="echo")
        b_args = p.system("arm_b", provider="echo", vary=True, keep=30)
        ra = p.evh("run", *a_args, "--run-id", "arm_a_run")
        rb = p.evh("run", *b_args, "--run-id", "arm_b_run")
        check(
            f"{store}: later: two arms run; the first has a `call`",
            ra.returncode == 0 and rb.returncode == 0 and p.run_json("arm_a_run").get("call") == CALL,
            (tail(ra), tail(rb)),
        )
        bad, out = p.v28()
        check(
            f"{store}: later: V28 passes on the runs as they were written", not bad and "ok   V28" in out, out
        )

        # The first score of arm_a gets what an older version wrote: item 1 holds two settings equal to the run's `call`
        # and a billing object whole, item 2 a setting that differs from it.
        rows = p.first_rows("arm_a_run")
        ids = [x["item_id"] for x in rows]
        rows[0]["_meta"].update(generation_config=GC, encoder_window=512, usage=RICH)
        rows[1]["_meta"].update(generation_config=GC_OTHER)
        p.put_first_rows("arm_a_run", rows)
        first_sd = p.first_score("arm_a_run")
        planted = p.text_of(first_sd)
        p.watch()

        def later_scores():
            return [s for s in p.scores("arm_a_run") if s != first_sd]

        def shaped(sd, what):
            """A later score of arm_a: the planted rows' settings taken off, the differing one and the usage kept right."""
            got = p.rows_of(sd)
            m = {x["item_id"]: x.get("_meta", {}) for x in got}
            return (
                [x["item_id"] for x in got] == ids
                and "generation_config" not in m[ids[0]]
                and "encoder_window" not in m[ids[0]]
                and m[ids[0]]["usage"] == SLIM
                and m[ids[1]]["generation_config"] == GC_OTHER
                and "encoder_window" not in m[ids[1]]
                and all("generation_config" not in m[i] and "encoder_window" not in m[i] for i in ids[2:])
                and all(x["usage"] == SLIM for x in m.values() if "usage" in x)
            ), (what, m[ids[0]], m[ids[1]])

        # (a) rescore: the adapter file changed, so the scorer is another and the score a new one
        (p.dir / "res_adapter.py").write_text(adapter_text(second=True))
        r = p.evh("rescore", "--dataset-id", "tickets_v1", "--match", "arm_a")
        new = later_scores()
        ok, why = shaped(new[0], "rescore") if len(new) == 1 else (False, [str(s) for s in new])
        check(
            f"{store}: rescore: a new score set whose rows hold no setting equal to the run's `call`, the differing "
            "one, and usage slimmed",
            r.returncode == 0 and ok,
            (tail(r), why),
        )
        if len(new) == 1:
            sd = new[0]
            before = (p.text_of(sd), p.record_text(sd), p.stamp(sd))
            r2 = p.evh("rescore", "--dataset-id", "tickets_v1", "--match", "arm_a")
            after = (p.text_of(sd), p.record_text(sd), p.stamp(sd))
            check(
                f"{store}: rescore: again, it is 'already scored': not refused, not rewritten, no other score set",
                r2.returncode == 0
                and "already scored" in r2.stdout
                and before == after
                and later_scores() == [sd],
                (tail(r2), before[2], after[2]),
            )
            check(
                f"{store}: rescore: the first score is as planted, untouched", p.text_of(first_sd) == planted
            )

        # (b) judge-score with the fake judge
        fake = "provider: fake, usd_per_mtok_in: 0, usd_per_mtok_out: 0"
        judges = f"[{{id: ja, params: {{{fake}, model: fake-a, family: vendor_a}}}}, {{id: jb, params: {{{fake}, model: fake-b, family: vendor_b}}}}]"
        made = p.evh(
            "scorer-new", "judge_v1", "--set", "dataset_id=tickets_v1", "--set", f"judges={judges}",
            "--set", "prompt.file=judge_prompt.txt", "--set", "protocol.outputs_per_call=2",
            # the kit's task, which its prompt asks for (judge-score refuses a prompt that does not name the task's
            # dimensions; with no task the scorer read SummEval's, which this prompt never names)
            "--set", "task.source_label=TICKET", "--set", "task.output_label=SUMMARIES",
            "--set", "task.dimensions=[accuracy, usefulness]", "--set", "task.scale=[1, 5]",
            "--set", "protocol.position_check_fraction=0.5", "--set", "protocol.noise_check_fraction=0.5", "--set", "cost_cap_usd=1",
        )  # fmt: skip
        jr = p.evh("judge-score", "--dataset-id", "tickets_v1", "--scorer", "judge_v1", "--unvalidated")

        def judged(run_id):
            return [s for s in p.scores(run_id) if s.name.startswith("judge_v1@")]

        ja, jb = judged("arm_a_run"), judged("arm_b_run")
        check(
            f"{store}: judge-score: the fake judge scores both arms",
            made.returncode == 0 and jr.returncode == 0 and len(ja) == 1 and len(jb) == 1,
            (tail(made), tail(jr)),
        )
        if len(ja) == 1 and len(jb) == 1:
            ok, why = shaped(ja[0], "judge-score")
            check(
                f"{store}: judge-score: its rows hold no setting equal to the run's `call`, keep the differing one, "
                "usage slimmed",
                ok,
                why,
            )
            brows = p.rows_of(jb[0])
            check(
                f"{store}: judge-score: an arm whose setting varied keeps it on every row, the settings `call` holds "
                "on none",
                all(x["_meta"]["generation_config"] and "encoder_window" not in x["_meta"] for x in brows)
                and all(x["_meta"]["usage"] == SLIM for x in brows),
                brows[0]["_meta"],
            )
            judged_before = [(p.text_of(s), p.record_text(s), p.stamp(s)) for s in (ja[0], jb[0])]
            jr2 = p.evh("judge-score", "--dataset-id", "tickets_v1", "--scorer", "judge_v1", "--unvalidated")
            judged_after = [(p.text_of(s), p.record_text(s), p.stamp(s)) for s in (ja[0], jb[0])]
            check(
                f"{store}: judge-score: again, no new calls and nothing rewritten, no other score set",
                jr2.returncode == 0
                and "calls 0," in jr2.stdout
                and judged_before == judged_after
                and judged("arm_a_run") == ja
                and judged("arm_b_run") == jb,
                (tail(jr2), judged_before[0][2], judged_after[0][2]),
            )

        # what the planted first score held is put right: the project validates with the rescored and judged sets in it
        p.put_first_rows("arm_a_run", [R.prepare(x, CALL) for x in rows])
        bad, out = p.v28()
        v = p.validate()
        check(
            f"{store}: later: V28 and validate pass with the rescored and judged score sets in the project",
            not bad and "ok   V28" in out and v.returncode == 0,
            (bad, v.stdout[-1500:]),
        )

        # (c) sheet-import of a judged sheet
        (p.dir / "rubric.md").write_text("Score the summary for what a person triaging needs to know.\n")
        runs = ",".join(["arm_a_v1", "arm_b_v1"])
        sh = p.evh("sheet-export", "--dataset-id", "tickets_v1", "--runs", runs, "--csv", "sc.csv",
                   "--fill", "scores", "--scale", "1..10", "--rubric", "rubric.md", "--seed", "3")  # fmt: skip
        key = json.loads((p.dir / "sc.key.json").read_text())
        raw = (p.dir / "sc.csv").read_bytes().decode("utf-8-sig")
        sheet = list(csv.DictReader(io.StringIO(raw, newline="")))
        head = next(csv.reader(io.StringIO(raw)))
        value = {"arm_a_v1": "9", "arm_b_v1": "4"}
        out_rows = []
        for r_ in sheet:
            if not r_["item_id"].startswith("#"):
                for letter, info in key["rows"][r_["item_id"]].items():
                    r_[f"score: {letter}"] = value[key["arms"][info["arm"]]["arm"]]
            out_rows.append(r_)
        with (p.dir / "sc_f.csv").open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(head)
            w.writerows([[x.get(h, "") for h in head] for x in out_rows])
        shutil.copy(p.dir / "sc.key.json", p.dir / "sc_f.key.json")
        si = p.evh(
            "sheet-import",
            "--sheet",
            "sc_f.csv",
            "--dataset-id",
            "tickets_v1",
            "--by",
            "owner",
            "--scorer",
            "sheet_v1",
        )

        def sheeted(run_id):
            return [s for s in p.scores(run_id) if s.name.startswith("sheet_v1@")]

        sa, sb = sheeted("arm_a_run"), sheeted("arm_b_run")
        check(
            f"{store}: sheet-import: a judged sheet gives a score set under each arm's run",
            sh.returncode == 0 and si.returncode == 0 and len(sa) == 1 and len(sb) == 1,
            (tail(sh), tail(si)),
        )
        if len(sa) == 1 and len(sb) == 1:
            got = p.rows_of(sa[0])
            check(
                f"{store}: sheet-import: its rows have no `_meta`, in the stored text and read back",
                len(got) == 6
                and all("_meta" not in x for x in got)
                and '"_meta"' not in (p.text_of(sa[0]) or ""),
                got[:1],
            )
            sheet_before = [(p.text_of(s), p.record_text(s), p.stamp(s)) for s in (sa[0], sb[0])]
            si2 = p.evh(
                "sheet-import",
                "--sheet",
                "sc_f.csv",
                "--dataset-id",
                "tickets_v1",
                "--by",
                "owner",
                "--scorer",
                "sheet_v1",
            )
            sheet_after = [(p.text_of(s), p.record_text(s), p.stamp(s)) for s in (sa[0], sb[0])]
            check(
                f"{store}: sheet-import: again, it is refused (a judged score is never overwritten) and the score set "
                "is as it was",
                si2.returncode != 0
                and "never overwritten" in tail(si2)
                and sheet_before == sheet_after
                and sheeted("arm_a_run") == sa,
                (tail(si2), sheet_before[0][2], sheet_after[0][2]),
            )

        # sheet-import's scores are a person's judgements: no scorer file names them, and V13 does not ask for one
        bad, out = p.v28()
        v = p.validate()
        check(
            f"{store}: later: V28 and validate (V13 included) pass with every later score set in the project",
            not bad and "ok   V28" in out and v.returncode == 0 and "FAIL V13" not in v.stdout,
            (bad, [x for x in v.stdout.splitlines() if "FAIL" in x][:5]),
        )
    finally:
        p.close()


for store_ in ("files", "sqlite"):
    resumed(store_)
    later(store_)

sys.exit(summary())
