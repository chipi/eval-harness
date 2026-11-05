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
from evaluation_harness import _outputs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402


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
    """A copy of a run under a new id, changed by `edit(run_dir, metrics)`."""
    src, dst = proj / "data/runs" / run_id, proj / "data/runs" / name
    shutil.copytree(src, dst)
    m = json.loads((dst / "metrics.json").read_text())
    m["run_id"] = name
    edit(dst, m)
    if (dst / "metrics.json").is_file():
        (dst / "metrics.json").write_text(json.dumps(m))
    return name


LABELS = proj / "data/labels/tickets_v1"

try:
    data = proj / "data"
    (data / "configs").mkdir(parents=True)
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
        shutil.copy(KIT / "configs" / f"tickets_{arm}.yaml", data / "configs")
        r = evh("run", "--config", f"data/configs/tickets_{arm}.yaml")
        check(f"setup: the {arm} arm runs", r.returncode == 0, out(r)[-300:])
    author = next(p.name for p in (data / "runs").glob("tickets_author_v1_*"))

    def unfinished(d, m):
        (d / "metrics.json").unlink()

    def derived(d, m):
        m["derived"] = {"kind": "rescore", "from": author}

    def dirty(d, m):
        m["build"] = {"ref": "abc", "dirty": True}

    def empty(d, m):
        _set_output(d, "t03_export", "   \n")

    def cut_off(d, m):
        m["params"]["max_tokens"] = 40
        rows = [json.loads(x) for x in (d / "predictions.jsonl").read_text().splitlines() if x.strip()]
        for row in rows[:2]:
            row["tokens_out"] = 40
        (d / "predictions.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))

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
            refused(r, text) and not (LABELS / f"s_{name}").exists(),
            out(r)[-300:],
        )
        if name == "cut_off":
            r = evh("label-from-run", "--run", run, "--set", "s_cut_ok", "--allow-cut-off")
            check("--allow-cut-off keeps outputs that end at the cap", r.returncode == 0, out(r)[-300:])
        shutil.rmtree(data / "runs" / run)

    r = evh("label-from-run", "--run", author, "--set", "author_v1")
    doc = json.loads((LABELS / "author_v1" / "labels.json").read_text()) if r.returncode == 0 else {}
    src_run = data / "runs" / author
    run_m = json.loads((src_run / "metrics.json").read_text())
    same = all(
        (LABELS / "author_v1" / f"{k}.txt").read_text() == v.strip() + "\n"
        for k, v in _outputs.outputs(src_run).items()
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
        "--out",
        "data/runs-silver",
    )
    board = evh("leaderboard", "--dataset-id", "tickets_v1", extra={"EVAL_RUNS_DIR": "data/runs-silver"})
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
    nr = LABELS / "author_nr"
    doc = json.loads((nr / "labels.json").read_text()) if (nr / "labels.json").is_file() else {}
    rebuild = doc.get("rebuild", "")
    check(
        "--not-redistributed: a .gitignore for the texts; labels.json says so and records how to rebuild them",
        r.returncode == 0
        and (nr / ".gitignore").read_text().strip().endswith("*.txt")
        and doc.get("redistributed") is False
        and rebuild == f"evh label-from-run --run {author} --set author_nr --not-redistributed",
        out(r)[-300:],
    )
    texts = {f.name: f.read_bytes() for f in nr.glob("*.txt")}
    before = (nr / "labels.json").read_bytes()
    for f in nr.glob("*.txt"):
        f.unlink()
    r = evh("validate")
    check(
        "validate (V19): a set kept out of git with its texts not here passes",
        "FAIL V19" not in out(r),
        out(r)[-500:],
    )
    r = evh(*rebuild.split()[1:])
    check(
        "the recorded command rebuilds the texts byte for byte, labels.json as it was",
        r.returncode == 0
        and {f.name: f.read_bytes() for f in nr.glob("*.txt")} == texts
        and (nr / "labels.json").read_bytes() == before,
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
    ref = data / "references/silver/tickets_v1_nr"
    m = json.loads((ref / "manifest.json").read_text()) if (ref / "manifest.json").is_file() else {}
    check(
        "a reference promoted from it is kept out too: the manifest says so and how to rebuild it",
        r.returncode == 0
        and m.get("redistributed") is False
        and (ref / ".gitignore").is_file()
        and rebuild in m.get("source", "")
        and "evh reference-promote --dataset-id tickets_v1 --labels tickets_v1/author_nr"
        in m.get("source", ""),
        out(r)[-300:] + json.dumps(m)[:300],
    )
    ref_texts = {f.name: f.read_bytes() for f in ref.glob("*.txt")}
    for f in ref.glob("*.txt"):
        f.unlink()
    r = evh(*r.args[2:])
    check(
        "the same promotion on a reference whose texts are not here rebuilds them from the set, checked",
        r.returncode == 0 and {f.name: f.read_bytes() for f in ref.glob("*.txt")} == ref_texts,
        out(r)[-300:],
    )
    promote = r.args[2:]
    for f in ref.glob("*.txt"):
        f.unlink()
    one = sorted(nr.glob("*.txt"))[0]
    was = one.read_bytes()
    one.write_text("a label edited after the reference was promoted\n")
    r = evh(*promote)
    check(
        "a reference rebuild from a set whose text changed since is refused, and writes nothing",
        refused(r, "do not match") and not list(ref.glob("*.txt")),
        out(r)[-300:],
    )
    one.write_bytes(was)
    for f in nr.glob("*.txt"):
        f.unlink()
    first = sorted(k for k in _outputs.outputs(src_run) if k.startswith("t"))[0]
    kept = _outputs.output(src_run, first)
    _set_output(src_run, first, "an output that changed after the set was made")
    r = evh(*rebuild.split()[1:])
    check(
        "a rebuild from a run that changed since is refused, and writes nothing",
        refused(r, "do not match") and not list(nr.glob("*.txt")),
        out(r)[-300:],
    )
    _set_output(src_run, first, kept)
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
