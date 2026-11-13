#!/usr/bin/env python3
"""`label-from-run`: a run's outputs become a model's label set, then a reference only when promoted (RFC-023).

    python tests/test_label_from_run.py

In a throwaway project built from the tutorial ($0, offline): a finished, clean run becomes a `model` set with no
calls, its source the run, config, fingerprint and build; the refusals (an unfinished run, a derived run, a dirty
build, an empty output, outputs cut off at max_tokens) leave no set behind; promoted to silver, the leaderboard marks
the arm that wrote it. --not-redistributed keeps the texts out of git, records the command that rebuilds them,
rebuilds them byte for byte (and refuses a run that changed since); the reference promoted from it is kept out too,
and its texts are rebuilt from the set.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
KIT = HERE.parent / "tutorial"
from evaluation_harness import (  # noqa: E402
    _format,
    _outputs,
    _store,
)
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
import _runview  # noqa: E402
from evaluation_harness.model import runs as _R  # noqa: E402


def _set_output(d, item, text):
    """Change one output of a run in place (None removes it), as a hand edit of its outputs.jsonl would."""
    texts = _outputs.outputs(d)
    texts.pop(item, None)
    if text is not None:
        texts[item] = text
    _outputs.write_all(d, texts, list(texts))


proj = Path(tempfile.mkdtemp(prefix="evh-labelrun-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-labelrun")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args, extra=None):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env={**env, **(extra or {})},
        capture_output=True,
        text=True,
    )


def out(r):
    return r.stdout + r.stderr


def refused(r, text):
    return r.returncode != 0 and "Traceback" not in out(r) and text in out(r)


def clone(run_id, name, edit):
    """A copy of a run (its first score too) under a new id, changed by `edit(run_dir, score_dir, record)`; the record
    is the score's, written back unless the edit removed the score."""
    with _runstore._InProject(proj) as data:
        src, dst = data / "runs" / run_id, data / "runs" / name
        _runstore.copy_run(src, dst)
        first = _R.first_score(src)
        _runstore.copy_run(first, dst / "scores" / first.name)
        sd, meta = dst / "scores" / first.name, _R.meta(first)
        m = _R.record(sd)
        m["run_id"] = name
        edit(dst, sd, m)
        if _store.is_dir(dst / "scores"):
            _R.write_run(name, {**(_R.run(dst) or {}), **_R.run_part(m)})
            _R.write_score(name, meta["scorer"], meta["reference"], m, label_as=meta["label"], first=True)
    return name


def txts(rel):
    """The .txt files of a directory under data/, by name: their bytes."""
    return {
        n: _runstore.read_bytes(proj, f"{rel}/{n}")
        for n in _runstore.listdir(proj, rel)
        if n.endswith(".txt")
    }


def drop_txts(rel):
    for n in txts(rel):
        _runstore.unlink(proj, f"{rel}/{n}")


LABELS = "labels/tickets_v1"  # under data/

try:
    data = proj / "data"
    if not _runstore.sqlite():
        (data / "systems").mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    shutil.copytree(KIT / "tickets", proj / "tutorial" / "tickets")
    r = evh("dataset-create", "--dataset-id", "tickets_v1", "--source-dir", "tutorial/tickets")
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "tickets_v1")
    check("setup: the tutorial dataset is created and materialized", r.returncode == 0, out(r)[-300:])
    r = evh(
        "label-import",
        str(KIT / "gold"),
        "--dataset-id",
        "tickets_v1",
        "--set",
        "owner_gold",
        "--by",
        "owner",
    )
    r = (
        r
        if r.returncode
        else evh(
            "reference-promote",
            "--dataset-id",
            "tickets_v1",
            "--labels",
            "owner_gold",
            "--tier",
            "gold",
            "--reason",
            "The kit's hand-written summaries decide.",
            "--by",
            "owner",
        )
    )
    check("setup: the kit's gold, imported and promoted", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    for arm in ("lead1", "author"):
        _runstore.write_text(
            proj, f"systems/tickets_{arm}_v1.yaml", (KIT / "systems" / f"tickets_{arm}_v1.yaml").read_text()
        )
        r = evh("run", "--system", f"tickets_{arm}_v1", "--dataset", "tickets_v1")
        check(f"setup: the {arm} arm runs", r.returncode == 0, out(r)[-300:])
    author = next(n for n in _runstore.listdir(proj, "runs") if n.startswith("tickets_author_v1_"))

    def unfinished(d, sd, m):
        _store.rmtree(d / "scores")

    def derived(d, sd, m):
        m["derived"] = {"kind": "rescore", "from": author}

    def dirty(d, sd, m):
        m["build"] = {"ref": "abc", "dirty": True}

    def empty(d, sd, m):
        _set_output(d, "t03_export", "   \n")

    def cut_off(d, sd, m):
        m["params"]["max_tokens"] = 40
        rows = _runstore.rows(sd)
        for row in rows[:2]:
            row["tokens_out"] = 40
        _runstore.put_rows_text(sd, "".join(json.dumps(x) + "\n" for x in rows))

    for name, edit, text in (
        ("unfinished", unfinished, "no finished run"),
        ("derived", derived, "rescored from"),
        ("dirty", dirty, "dirty tree"),
        ("empty", empty, "empty output"),
        ("cut_off", cut_off, "stopped at max_tokens=40"),
    ):
        run = clone(author, f"tickets_author_v1_{name}", edit)
        r = evh("label-from-run", "--run", run, "--set", f"s_{name}")
        check(
            f"label-from-run refuses {name.replace('_', ' ')}, and leaves no set",
            refused(r, text) and not _runstore.exists(proj, f"{LABELS}/s_{name}"),
            out(r)[-300:],
        )
        if name == "cut_off":
            r = evh("label-from-run", "--run", run, "--set", "s_cut_ok", "--allow-cut-off")
            check("--allow-cut-off keeps outputs that end at the cap", r.returncode == 0, out(r)[-300:])
        _runstore.rmtree(proj, f"runs/{run}")

    r = evh("label-from-run", "--run", author, "--set", "author_v1")
    doc = _runstore.read_json(proj, f"{LABELS}/author_v1/labels.json") if r.returncode == 0 else {}
    run_m = _runview.record_of(proj, author)[1]
    with _runstore._InProject(proj) as data:
        src_run_outputs = _outputs.outputs(data / "runs" / author)
    same = all(
        _runstore.read_text(proj, f"{LABELS}/author_v1/{k}.txt") == v.strip() + "\n"
        for k, v in src_run_outputs.items()
        if k.startswith("t")
    )
    check(
        "label-from-run: the run's outputs as labels (each stripped, one newline), no calls",
        r.returncode == 0 and same and doc.get("n_items") == 6,
        out(r)[-300:],
    )
    s = doc.get("source") or {}
    check(
        "the set's source names the run, its config, fingerprint and build",
        s.get("kind") == "model"
        and s.get("run_id") == author
        and s.get("config_id") == "tickets_author_v1"
        and s.get("fingerprint_hash") == run_m["fingerprint"]["hash"]
        and s.get("build") == run_m["build"],
        json.dumps(s),
    )
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "author_v1",
        "--tier",
        "silver",
        "--reason",
        "The author's summaries rank the others.",
        "--by",
        "owner",
    )
    r2 = evh(
        "rescore",
        "--dataset-id",
        "tickets_v1",
        "--reference-id",
        "silver/tickets_v1",
    )
    board = evh("leaderboard", "--dataset-id", "tickets_v1", "--label", "silver")
    check(
        "promoted: the leaderboard marks the arm that wrote the reference, and says why",
        r.returncode == 0
        and r2.returncode == 0
        and "tickets_author_v1 *" in board.stdout
        and "wrote the reference silver/tickets_v1" in board.stdout
        and "tickets_lead1_v1 *" not in board.stdout,
        board.stdout[-600:] + out(r)[-200:],
    )

    # ── not redistributed: the texts kept out of git, rebuilt from the run ──────────────────────
    r = evh("label-from-run", "--run", author, "--set", "author_nr", "--not-redistributed")
    nr = f"{LABELS}/author_nr"
    doc = (
        _runstore.read_json(proj, f"{nr}/labels.json") if _runstore.is_file(proj, f"{nr}/labels.json") else {}
    )
    rebuild = doc.get("rebuild", "")
    check(
        "--not-redistributed: a .gitignore for the texts; labels.json says so and records how to rebuild them",
        r.returncode == 0
        and _runstore.read_text(proj, f"{nr}/.gitignore").strip().endswith("*.txt")
        and doc.get("redistributed") is False
        and rebuild == f"evh label-from-run --run {author} --set author_nr --not-redistributed",
        out(r)[-300:],
    )
    texts = txts(nr)
    before = _runstore.read_bytes(proj, f"{nr}/labels.json")
    drop_txts(nr)
    r = evh("validate")
    check(
        "validate (V19): a set kept out of git with its texts not here passes",
        "FAIL V19" not in out(r),
        out(r)[-500:],
    )
    r = evh(*rebuild.split()[1:])
    check(
        "the recorded command rebuilds the texts byte for byte, labels.json as it was",
        r.returncode == 0 and txts(nr) == texts and _runstore.read_bytes(proj, f"{nr}/labels.json") == before,
        out(r)[-300:],
    )
    r = evh(*rebuild.split()[1:])
    check(
        "with its texts here, the same command is refused: a set is never edited",
        refused(r, "never edited"),
        out(r)[-200:],
    )
    r = evh(
        "reference-promote",
        "--dataset-id",
        "tickets_v1",
        "--labels",
        "author_nr",
        "--tier",
        "silver",
        "--name",
        "tickets_v1_nr",
        "--reason",
        "The same answers, kept out of git.",
        "--by",
        "owner",
    )
    ref = "references/silver/tickets_v1_nr"
    m = (
        _runstore.read_json(proj, f"{ref}/manifest.json")
        if _runstore.is_file(proj, f"{ref}/manifest.json")
        else {}
    )
    check(
        "a reference promoted from it is kept out too: the manifest says so and how to rebuild it",
        r.returncode == 0
        and m.get("redistributed") is False
        and _runstore.is_file(proj, f"{ref}/.gitignore")
        and rebuild in m.get("source", "")
        and "evh reference-promote --dataset-id tickets_v1 --labels tickets_v1/author_nr"
        in m.get("source", ""),
        out(r)[-300:] + json.dumps(m)[:300],
    )
    ref_texts = txts(ref)
    drop_txts(ref)
    r = evh(*r.args[2:])
    check(
        "the same promotion on a reference whose texts are not here rebuilds them from the set, checked",
        r.returncode == 0 and txts(ref) == ref_texts,
        out(r)[-300:],
    )
    promote = r.args[2:]
    drop_txts(ref)
    one = f"{nr}/" + sorted(txts(nr))[0]
    was = _runstore.read_bytes(proj, one)
    _runstore.write_text(proj, one, "a label edited after the reference was promoted\n")
    r = evh(*promote)
    check(
        "a reference rebuild from a set whose text changed since is refused, and writes nothing",
        refused(r, "do not match") and not txts(ref),
        out(r)[-300:],
    )
    _runstore.write_bytes(proj, one, was)
    drop_txts(nr)
    with _runstore._InProject(proj) as data:
        src_run = data / "runs" / author
        first = sorted(k for k in _outputs.outputs(src_run) if k.startswith("t"))[0]
        kept = _outputs.output(src_run, first)
        _set_output(src_run, first, "an output that changed after the set was made")
    r = evh(*rebuild.split()[1:])
    check(
        "a rebuild from a run that changed since is refused, and writes nothing",
        refused(r, "do not match") and not txts(nr),
        out(r)[-300:],
    )
    with _runstore._InProject(proj) as data:
        _set_output(data / "runs" / author, first, kept)
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
