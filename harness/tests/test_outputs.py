#!/usr/bin/env python3
"""A run's outputs in one file, read through one function (RFC-024), in either runs store (RFC-025).

    python tests/test_outputs.py

The module: appended lines are read back, a torn last line is not an output, finish() writes dataset order and drops
the row checkpoint, a derived run reads its source's outputs (followed along a chain), V5's signature is the value the
per-item files gave. Through the commands: a run writes outputs.jsonl and no outputs/ folder; a run stopped mid-pass
resumes, the done items not called again and the finished file whole; no module but _outputs builds an outputs/ path.
All of it runs twice: the files store, then the sqlite store (data/runs.sqlite).
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
KIT = HARNESS / "tutorial"
sys.path.insert(0, str(HARNESS))
proj = Path(tempfile.mkdtemp(prefix="evh-outputs-"))
os.environ["EVAL_HOME"] = str(proj)
os.environ.pop("EVAL_RUNS_STORE", None)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR"):
    os.environ.pop(k, None)
from evaluation_harness import _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

env = dict(os.environ, EVAL_BUILD_REF="test-outputs")
env.pop("EVAL_MAX_COST_USD", None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


def body(store: str) -> None:
    os.environ["EVAL_RUNS_STORE"] = env["EVAL_RUNS_STORE"] = store
    _outputs.reset()
    sq = store == "sqlite"
    try:
        runs = proj / "data" / "runs"
        a = runs / "arm_a_v1_x"
        w = _outputs.writer(a)
        w.add("i2", "second")
        w.add("i1", "first é")
        if not sq:
            with (a / _outputs.FILE).open("a", encoding="utf-8") as fh:
                fh.write('{"item_id": "i3", "text": "torn')
        check(
            f"{store}: appended outputs read back" + ("" if sq else "; a torn last line is not an output"),
            _outputs.outputs(a) == {"i2": "second", "i1": "first é"} and _outputs.output(a, "i3") is None,
            _outputs.outputs(a),
        )
        _outputs.append_partial(a, {"item_id": "i1"})
        _outputs.finish(a, {"i1": "first é", "i2": "second", "i9": "not in the dataset"}, ["i1", "i2", "i3"])
        rows = _outputs.lines(a)
        check(
            f"{store}: finish(): dataset order, only the dataset's items, each line's sha256, the row checkpoint gone",
            [r["item_id"] for r in rows] == ["i1", "i2"]
            and rows[0]["sha256"] == hashlib.sha256("first é".encode()).hexdigest()
            and _outputs.rows_text(a, partial=True) is None,
            rows,
        )
        (a / "metrics.json").write_text(json.dumps({"run_id": a.name}))
        j = proj / "data" / "runs-judged" / "judge1" / a.name
        j.mkdir(parents=True)
        (j / "metrics.json").write_text(json.dumps({"derived": {"kind": "judge", "from": a.name}}))
        r = proj / "data" / "runs-rescored" / "s1" / "runs-judged" / a.name
        r.mkdir(parents=True)
        (r / "metrics.json").write_text(json.dumps({"derived": {"kind": "rescore", "from": a.name}}))
        check(
            f"{store}: a derived run reads its source's outputs; one of a derived run too",
            _outputs.output(j, "i2") == "second"
            and _outputs.outputs(r) == _outputs.outputs(a)
            and _outputs.source(r) == a,
            (_outputs.source(j), _outputs.source(r)),
        )
        old = hashlib.sha256()
        for item, text in sorted({"i1": "first é", "i2": "second"}.items()):
            old.update(f"{item}.txt".encode() + b"\0" + text.encode() + b"\x1e")
        check(
            f"{store}: V5's signature is the value the per-item files gave",
            _outputs.signature(a) == old.hexdigest(),
        )
        check(
            f"{store}: a run with no outputs signs as one",
            _outputs.signature(proj / "nothing") == "<no-outputs>",
        )
        check(
            f"{store}: the outputs are in the store, and only there",
            (a / _outputs.FILE).exists() != sq and (proj / "data" / _outputs.DB).exists() == sq,
        )

        _outputs.reset()
        shutil.rmtree(proj / "data")
        (proj / "data" / "configs").mkdir(parents=True)
        shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
        r1 = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
        r1 = r1 if r1.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
        cfg = proj / "data" / "configs" / "lead1.yaml"
        cfg.write_text((KIT / "configs" / "tickets_lead1.yaml").read_text())
        r1 = r1 if r1.returncode else evh("run", "--config", str(cfg))
        run = next((proj / "data" / "runs").glob("tickets_lead1_v1_*"), proj / "missing")
        check(
            f"{store}: a run writes its outputs, every item, and no outputs/ folder or row checkpoint",
            r1.returncode == 0
            and run is not None
            and _outputs.count(run) == 6
            and (run / _outputs.FILE).exists() != sq
            and not (run / "outputs").exists()
            and _outputs.rows_text(run, partial=True) is None,
            (r1.stdout + r1.stderr)[-300:],
        )
        # A run stopped after two items: its outputs file and run.json, no metrics.json; resume it.
        stopped = proj / "data" / "runs" / "tickets_lead1_v1_stopped"
        stopped.mkdir()
        done = _outputs.lines(run)
        if sq:
            w = _outputs.writer(stopped)
            for row in done[:2]:
                w.add(row["item_id"], row["text"])
        else:
            lines = [json.dumps(r, ensure_ascii=False) for r in done]
            (stopped / _outputs.FILE).write_text("\n".join(lines[:2]) + "\n" + lines[2][:20])
        (stopped / "run.json").write_text(
            json.dumps({"config_id": "tickets_lead1_v1", "dataset_id": "tickets_v1"})
        )
        r2 = evh("run", "--config", str(cfg), "--resume", "tickets_lead1_v1_stopped")
        new = sorted((proj / "data" / "runs").glob("tickets_lead1_v1_2*"))[-1]
        check(
            f"{store}: --resume: the two done items replayed, the third called again; the new run's outputs whole",
            r2.returncode == 0
            and json.loads((new / "metrics.json").read_text()).get("resume", {}).get("replayed_items") == 2
            and _outputs.outputs(new) == _outputs.outputs(run),
            (r2.stdout + r2.stderr)[-400:],
        )
    finally:
        _outputs.reset()
        shutil.rmtree(proj / "data", ignore_errors=True)
        shutil.rmtree(proj / "tutorial", ignore_errors=True)


try:
    for store in ("files", "sqlite"):
        body(store)
finally:
    shutil.rmtree(proj, ignore_errors=True)

# No module but _outputs builds an outputs/ path (RFC-024: one reader); run_migrate reads the old one to move it.
pat = re.compile(r'"outputs"\s*\)|/ "outputs"|"outputs/')
stray = [
    f"{p.name}:{n}"
    for p in sorted(HERE.glob("*.py"))
    if p.name not in ("_outputs.py", "run_migrate.py")  # the migration reads the old layout, by design
    for n, line in enumerate(p.read_text().splitlines(), 1)
    if pat.search(line) and not line.lstrip().startswith("#")
]
check("no module but _outputs.py (and the migration) builds an outputs/ path", not stray, stray)
sys.exit(summary())
