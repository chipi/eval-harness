#!/usr/bin/env python3
"""`evh run-migrate`: runs in the old layout (an outputs/ folder of <item>.txt) to one outputs.jsonl (RFC-024).

    python tests/test_run_migrate.py

A project with a measured run (its rows checkpoint left behind), a judged copy of it (byte copies of its outputs), a
re-score whose outputs differ, and a derived run whose source is gone: --dry-run changes nothing; the migration gives
the measured run its file in dataset order and V5's old signature, drops the copy's outputs (it reads its source's),
keeps the differing and the orphan their own, drops the checkpoint predictions.jsonl covers; a second run changes
nothing; an output that is not UTF-8 is refused before anything of its run changes.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
# the layout before 0.8.0 is files on disk by definition (data-migrate refuses a project that still has it)
os.environ["EVAL_STORE"] = "files"
proj = Path(tempfile.mkdtemp(prefix="evh-run-migrate-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR"):
    os.environ.pop(k, None)
from evaluation_harness import _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

env = dict(os.environ, EVAL_BUILD_REF="test-run-migrate")
ITEMS = ["t03", "t01", "t02"]  # the dataset's order, not sorted
OUT = {"t01": "one\r\nline", "t02": "two ✓", "t03": "three\n"}


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


def old_run(d: Path, outs: dict, metrics: dict, rows: bool = False) -> None:
    (d / "outputs").mkdir(parents=True)
    for i, t in outs.items():
        (d / "outputs" / f"{i}.txt").write_bytes(t.encode() if isinstance(t, str) else t)
    (d / "metrics.json").write_text(json.dumps(metrics))
    (d / "predictions.jsonl").write_text("".join(json.dumps({"item_id": i, "acc": 1.0}) + "\n" for i in outs))
    if rows:
        (d / "outputs" / "_rows.jsonl").write_text("".join(json.dumps({"item_id": i}) + "\n" for i in outs))


def old_sig(outs: dict) -> str:
    h = hashlib.sha256()
    for i in sorted(outs):
        h.update(f"{i}.txt".encode() + b"\0" + outs[i].encode() + b"\x1e")
    return h.hexdigest()


try:
    data = proj / "data"
    (data / "datasets").mkdir(parents=True)
    (data / "datasets" / "ds1.json").write_text(
        json.dumps({"dataset_id": "ds1", "items": [{"item_id": i} for i in ITEMS]})
    )
    m = data / "runs" / "arm_v1_20261101T000000Z"
    old_run(m, OUT, {"run_id": m.name, "dataset_id": "ds1", "config_id": "arm_v1"}, rows=True)
    j = data / "runs-judged" / "judge1" / m.name
    old_run(j, OUT, {"run_id": m.name, "dataset_id": "ds1", "derived": {"kind": "judge", "from": m.name}})
    r = data / "runs-rescored" / "s1" / "runs" / m.name
    old_run(
        r,
        {**OUT, "t02": "edited"},
        {"run_id": m.name, "dataset_id": "ds1", "derived": {"kind": "rescore", "from": m.name}},
    )
    o = data / "runs-judged" / "judge1" / "gone_v1_20261101T000000Z"
    old_run(
        o,
        {"t01": "x"},
        {
            "run_id": o.name,
            "dataset_id": "ds1",
            "derived": {"kind": "judge", "from": "gone_v1_20261101T000000Z"},
        },
    )
    before = sorted(str(p.relative_to(data)) for p in data.rglob("*") if p.is_file())

    d = evh("run-migrate", "--dry-run")
    check(
        "--dry-run: says what it would do, changes nothing",
        d.returncode == 0
        and "4 run(s)" in d.stdout
        and "1 derived read their source's" in d.stdout
        and sorted(str(p.relative_to(data)) for p in data.rglob("*") if p.is_file()) == before,
        d.stdout[-400:] + d.stderr[-300:],
    )
    a = evh("run-migrate")
    rows = (
        [json.loads(x) for x in (m / _outputs.FILE).read_text().splitlines()]
        if (m / _outputs.FILE).is_file()
        else []
    )
    check(
        "the measured run: one file, the dataset's order, each text exactly (\\r\\n kept), V5's old signature",
        a.returncode == 0
        and [x["item_id"] for x in rows] == ITEMS
        and _outputs.outputs(m) == OUT
        and _outputs.signature(m) == old_sig(OUT)
        and not (m / "outputs").exists(),
        a.stdout[-400:] + a.stderr[-300:],
    )
    check(
        "the judged copy keeps no outputs of its own, records its source's directory, and reads its source's",
        not (j / "outputs").exists()
        and not (j / _outputs.FILE).exists()
        and json.loads((j / "metrics.json").read_text())["derived"].get("from_dir") == f"runs/{m.name}"
        and _outputs.outputs(j) == OUT,
        json.loads((j / "metrics.json").read_text()).get("derived"),
    )
    check(
        "a re-score whose outputs differ keeps its own; an orphan too, named",
        _outputs.output(r, "t02") == "edited"
        and _outputs.outputs(o) == {"t01": "x"}
        and "its source is not here" in a.stdout,
        a.stdout[-400:],
    )
    check("the row checkpoint predictions.jsonl covers is dropped", not (m / _outputs.ROWS).exists())
    a2 = evh("run-migrate")
    check(
        "a second run changes nothing",
        a2.returncode == 0 and "already in this format" in a2.stdout,
        a2.stdout[-200:],
    )
    v = evh("validate")
    v23 = [ln for ln in v.stdout.splitlines() if "V23" in ln]
    check(
        "validate V23: every run's outputs readable after the migration",
        bool(v23) and v23[0].lstrip().startswith("ok"),
        "\n".join(v23) or v.stdout[-400:],
    )
    shutil.rmtree(m)  # the judged copy's source, gone
    v = evh("validate")
    check(
        "validate V23: a derived run whose source is gone is named",
        v.returncode != 0 and "its source arm_v1_20261101T000000Z is not here" in v.stdout,
        v.stdout[-500:],
    )
    b = data / "runs" / "bin_v1_20261101T000000Z"
    old_run(b, {"t01": b"\xff\xfe not text"}, {"run_id": b.name, "dataset_id": "ds1", "config_id": "bin_v1"})
    v = evh("validate")
    check(
        "validate V23: a run left in the old layout is named, with the command",
        "evh run-migrate" in v.stdout,
        v.stdout[-400:],
    )
    a3 = evh("run-migrate")
    check(
        "an output that is not UTF-8 is refused, naming it, before its run changes",
        a3.returncode == 1
        and "not UTF-8" in a3.stderr
        and (b / "outputs" / "t01.txt").is_file()
        and not (b / _outputs.FILE).exists(),
        a3.stderr[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
