#!/usr/bin/env python3
"""`evh migrate`'s runs steps: runs in the old layout (an outputs/ folder of <item>.txt) to one outputs.jsonl (RFC-024),
and then every run and score into data/runs (RFC-032 step 4).

    python tests/test_run_migrate.py

A project at format 0 with a measured run (its rows checkpoint left behind), a judged copy of it (byte copies of its
outputs), a re-score whose outputs differ, and a judged run whose source is gone: --dry-run changes nothing; the
migration refuses the orphan, writing nothing of the new layout, then the re-score (a score keeps no outputs of its
own); without them the measured run has its file in dataset
order and V5's old signature, the copy is a score of the run and reads the run's outputs, the checkpoint
predictions.jsonl covers is dropped; a second run changes nothing; an output that is not UTF-8 is refused before
anything of its run changes.
"""

import hashlib
import json
import os
import shutil
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
os.environ.pop("EVAL_DATA_DIR", None)
from evaluation_harness import _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

env = dict(os.environ, EVAL_BUILD_REF="test-run-migrate")
ITEMS = ["t03", "t01", "t02"]  # the dataset's order, not sorted
OUT = {"t01": "one\r\nline", "t02": "two ✓", "t03": "three\n"}


sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _cli
import _cli  # noqa: E402


def evh(*args):
    return _cli.run(proj, env, *args, timeout=300)


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
    (data / "systems").mkdir()
    (data / "systems" / "arm_v1.yaml").write_text(
        "system_id: arm_v1\n"
    )  # the last step refuses a run of no system
    m = data / "runs" / "arm_v1_20261101T000000Z"
    adapter = {"fingerprint": {"instrument": {"adapter": {"sha256": "a" * 64}}}}
    old_run(m, OUT, {"run_id": m.name, "dataset_id": "ds1", "config_id": "arm_v1", **adapter}, rows=True)
    judge = {"kind": "judge", "from": m.name, "with": {"scorer_id": "judge1", "judging_set_id": "set1"}}
    j = data / "runs-judged" / "judge1" / m.name
    old_run(j, OUT, {"run_id": m.name, "dataset_id": "ds1", "config_id": "arm_v1", "derived": judge})
    r = data / "runs-rescored" / "s1" / "runs" / m.name
    old_run(
        r,
        {**OUT, "t02": "edited"},
        {
            "run_id": m.name,
            "dataset_id": "ds1",
            "config_id": "arm_v1",
            "derived": {"kind": "rescore", "from": m.name, "with": {"sha256": "b" * 64}},
        },
    )
    o = data / "runs-judged" / "judge1" / "gone_v1_20261101T000000Z"
    old_run(
        o,
        {"t01": "x"},
        {
            "run_id": o.name,
            "dataset_id": "ds1",
            "config_id": "gone_v1",
            "derived": {
                "kind": "judge",
                "from": "gone_v1_20261101T000000Z",
                "with": {"scorer_id": "judge1", "judging_set_id": "set1"},
            },
        },
    )
    before = sorted(str(p.relative_to(data)) for p in data.rglob("*") if p.is_file())

    d = evh("migrate", "--dry-run")
    check(
        "--dry-run: refuses the orphan judged run (its run is not here), names it, changes nothing",
        d.returncode != 0
        and "gone_v1_20261101T000000Z" in d.stderr
        and "a run that is not in" in d.stderr
        and sorted(str(p.relative_to(data)) for p in data.rglob("*") if p.is_file()) == before,
        d.stdout[-400:] + d.stderr[-300:],
    )
    a = evh("migrate")
    check(
        "migrate: the orphan is named by the outputs step and refused by the runs step, which writes nothing",
        a.returncode != 0
        and "its source is not here" in a.stdout
        and "a run that is not in" in a.stderr
        and not (m / "run.json").exists()
        and (m / _outputs.FILE).is_file(),
        a.stdout[-400:] + a.stderr[-300:],
    )
    shutil.rmtree(o.parent / o.name)  # the orphan gone
    d = evh("migrate", "--dry-run")
    check(
        "--dry-run: refuses the re-score whose outputs differ from its run's (a score has none of its own), names it",
        d.returncode != 0 and r.name in d.stderr and "keeps outputs of its own" in d.stderr,
        d.stdout[-400:] + d.stderr[-300:],
    )
    shutil.rmtree(r)  # and that re-score gone: the project can move
    d = evh("migrate", "--dry-run")
    check(
        "--dry-run: says what it would do, changes nothing",
        d.returncode == 0
        and "2 score(s)" in d.stdout
        and "1 run(s) into data/runs" in d.stdout
        and not (m / "run.json").exists(),
        d.stdout[-500:] + d.stderr[-300:],
    )
    a = evh("migrate")
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
        and not (m / "outputs").exists()
        and (model_runs.run(m.name) or {}).get("purpose") == "run",
        a.stdout[-400:] + a.stderr[-300:],
    )
    js = m / "scores" / "judge1@set1"
    check(
        "the judged copy is a score of the run: no outputs of its own, its record names the run's directory, it reads the run's",
        js.is_dir()
        and not (js / "outputs").exists()
        and not (js / _outputs.FILE).exists()
        and ((model_runs.record(js) or {}).get("derived") or {}).get("from_dir") == f"runs/{m.name}"
        and _outputs.outputs(js) == OUT
        and model_runs.label(js) == "judged/judge1",
        model_runs.record(js),
    )
    check(
        "the row checkpoint predictions.jsonl covers is dropped",
        not (m / _outputs.ROWS).exists() and not list(data.rglob(_outputs.ROWS)),
    )
    a2 = evh("migrate")
    (proj / "data" / "project.yaml").unlink()  # the steps again, as after a migration stopped half way
    a2b = evh("migrate")
    check(
        "a second run changes nothing: the format says so, and the steps run again change nothing",
        a2.returncode == 0
        and "nothing to do" in a2.stdout
        and a2b.returncode == 0
        and "already in this format" in a2b.stdout,
        a2.stdout[-200:] + a2b.stdout[-200:],
    )
    v = evh("validate")
    v23 = [ln for ln in v.stdout.splitlines() if "V23" in ln]
    check(
        "validate V23: every run's outputs readable after the migration",
        bool(v23) and v23[0].lstrip().startswith("ok") and "1 run(s)" in v23[0],
        "\n".join(v23) or v.stdout[-400:],
    )
    (
        m / _outputs.FILE
    ).unlink()  # the judged score's run has no outputs: what the score was derived from, gone
    v = evh("validate")
    check(
        "validate V23: a score derived from a run's outputs, the run having none, is named",
        v.returncode != 0 and "derived from its run's outputs, and the run has none" in v.stdout,
        v.stdout[-500:],
    )
    b = data / "runs" / "bin_v1_20261101T000000Z"
    old_run(b, {"t01": b"\xff\xfe not text"}, {"run_id": b.name, "dataset_id": "ds1", "config_id": "bin_v1"})
    (b / "run.json").write_text(json.dumps({"run_id": b.name, "dataset_id": "ds1", "config_id": "bin_v1"}))
    v = evh("validate")
    check(
        "validate V23: a run left in the old layout is named, with the command",
        "evh migrate" in v.stdout,
        v.stdout[-400:],
    )
    (proj / "data" / "project.yaml").unlink()  # a run in the old layout: data at format 0 again
    a3 = evh("migrate")
    check(
        "an output that is not UTF-8 is refused, naming it, before its run changes",
        a3.returncode == 1
        and "not UTF-8" in a3.stderr
        and (b / "outputs" / "t01.txt").is_file()
        and not (b / _outputs.FILE).exists(),
        a3.stderr[-300:],
    )
    # An import made without --scorer-file (0.4.x) has no scorer hash: its score is keyed as `evh import-run` keys it
    # now, by the hash of the scorer's id. A record with neither is still refused.
    shutil.rmtree(proj / "data")
    (proj / "data" / "datasets").mkdir(parents=True)
    (proj / "data" / "datasets" / "ds1.json").write_text(
        json.dumps(
            {
                "dataset_id": "ds1",
                "created_at": "2026-11-01T00:00:00Z",
                "version": 1,
                "items": [{"item_id": "t01", "source_sha256": "0" * 64}],
            }
        )
    )
    (proj / "data" / "systems").mkdir()
    (proj / "data" / "systems" / "arm_v1.yaml").write_text("system_id: arm_v1\nparams: {}\n")
    scorer_id = "podcast_scraper scripts/measure/naming_gate.py"
    adapter_fp = {"fingerprint": {"instrument": {"adapter": {"sha256": "c" * 64}}}}
    imp = proj / "data" / "runs" / "arm_v1_20261102T000000Z"
    bare = proj / "data" / "runs" / "arm_v1_20261103T000000Z"
    old_run(
        imp,
        {"t01": "x"},
        {
            "run_id": imp.name,
            "dataset_id": "ds1",
            "config_id": "elsewhere_v1",
            "created_at": "2026-11-02T00:00:00Z",
            "scores": {"acc": 1.0},
            "n_items": 1,
            "build": {"ref": "abc1234", "dirty": False, "source": "git"},
            "imported": {
                "source": "elsewhere",
                "scorer_id": scorer_id,
                "scorer_sha256": None,
                "scorer_sha256_unrecoverable_at_v4": True,
            },
        },
    )
    old_run(bare, {"t01": "x"}, {"run_id": bare.name, "dataset_id": "ds1", "config_id": "arm_v1"})
    d = evh("migrate", "--dry-run")
    check(
        "a run with no scorer hash and no imported scorer id is refused, naming it",
        d.returncode != 0 and bare.name in d.stderr and "records no scorer" in d.stderr,
        d.stdout[-300:] + d.stderr[-300:],
    )
    shutil.rmtree(bare)
    # 0.8's import-run writes a system_id naming no system file: the imported run's config_id names none either, and
    # it keeps its value; a run that is not imported with an unknown id is still refused.
    stray = proj / "data" / "runs" / "stray_v1_20261104T000000Z"
    old_run(
        stray,
        {"t01": "x"},
        {
            "run_id": stray.name,
            "dataset_id": "ds1",
            "config_id": "stray_v1",
            "created_at": "2026-11-04T00:00:00Z",
            "scores": {"acc": 1.0},
            "n_items": 1,
            "build": {"ref": "abc1234", "dirty": False, "source": "git"},
            **adapter_fp,
        },
    )
    d = evh("migrate", "--dry-run")
    check(
        "a run that is not imported, its config_id no system's, is refused; the imported one is not",
        d.returncode != 0
        and "stray_v1" in d.stderr
        and "not the id of a system" in d.stderr
        and "elsewhere_v1" not in d.stderr,
        d.stdout[-300:] + d.stderr[-400:],
    )
    shutil.rmtree(stray)
    key = hashlib.sha256(f"imported:{scorer_id}".encode()).hexdigest()[:12]
    a4 = evh("migrate")
    check(
        "an imported run with no scorer hash migrates: its score is keyed as import-run keys it",
        a4.returncode == 0 and (imp / "scores" / f"{key}@none").is_dir(),
        a4.stdout[-300:] + a4.stderr[-300:] + str(sorted(p.name for p in (imp / "scores").glob("*"))),
    )
    rec = model_runs.run(imp.name) or {}
    check(
        "the imported run keeps its id as system_id though no system has it",
        rec.get("system_id") == "elsewhere_v1" and "config_id" not in rec,
        rec,
    )
    v = evh("validate")
    check("validate after migrating an imported run: no failure", v.returncode == 0, v.stdout[-900:])
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
