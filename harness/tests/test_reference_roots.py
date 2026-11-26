#!/usr/bin/env python3
"""A project may declare where it keeps references besides data/references: `references: {roots: [...]}` (0.8.2).

    python tests/test_reference_roots.py

In a throwaway project ($0, offline), in whichever store the suite runs in: with no roots declared, `import-run
--reference-id` records an id that names nothing and says so (V16's note), as 0.8.1 did. With a root declared, an id
found in it is accepted without the note and validate's V16 checks that folder against its manifest (a drifted text
fails); an id found nowhere is refused, naming the roots searched, and nothing is written; `rescore --reference-id`
looks in the roots too; a `references:` key that is not a list of paths is refused.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _format
from evaluation_harness._check import check, summary

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _cli
import _cli
import _runstore

proj = Path(tempfile.mkdtemp(prefix="evh-ref-roots-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-reference-roots")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVH_ACTOR"):
    env.pop(k, None)
STORE = os.environ.get("EVAL_STORE") or "files"


def evh(*args):
    return _cli.run(proj, env, *args)


def config(extra=""):
    (proj / "config.yaml").write_text(f"store: {STORE}\n{extra}", encoding="utf-8")


def runs():
    return sorted(_runstore.listdir(proj, "runs")) if _runstore.exists(proj, "runs") else []


def v16(out):
    return next(
        (ln for ln in out.splitlines() if " V16 " in ln and ln.lstrip().startswith(("ok", "FAIL", "--"))), ""
    )


def imp(system, ref):
    return evh(
        "import-run", "--dataset-id", "toy_v1", "--system-id", system, "--scores", "scores.jsonl",
        "--primary-metric", "wer", "--asc", "--build-ref", "t", "--source", "test", "--scorer-id", "wer",
        "--reference-id", ref,
    )  # fmt: skip


try:
    (proj / "data").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    config()
    for n, t in (("a", "billing"), ("b", "shipping")):
        _runstore.write_text(proj, f"sources/toy/{n}.txt", t)
    r = evh("dataset-create", "--dataset-id", "toy_v1", "--source-dir", "data/sources/toy")
    check("setup: a dataset", r.returncode == 0, r.stdout + r.stderr)
    (proj / "scores.jsonl").write_text(
        "".join(json.dumps({"item_id": i, "wer": 0.1 * k}) + "\n" for k, i in enumerate("ab")),
        encoding="utf-8",
    )

    r = imp("arm_none", "gold/toy_v1")
    check(
        "no roots declared: an id that names nothing is recorded, with V16's note (as 0.8.1)",
        r.returncode == 0 and "V16" in r.stderr and len(runs()) == 1,
        r.stdout + r.stderr,
    )

    # A reference kept outside data/: built with the harness, then moved out of data/references.
    for n, t in (("a", "billing"), ("b", "shipping")):
        _runstore.write_text(proj, f"references/gold/toy_v1/{n}.txt", t)
    r = evh(
        "reference-manifest", "--reference-id", "gold/toy_v1", "--source", "fetch.py", "--labelled-by", "the authors",
        "--reason", "the dataset's own labels decide", "--by", "owner",
    )  # fmt: skip
    check("setup: a reference with a manifest", r.returncode == 0, r.stdout + r.stderr)
    out = proj / "records" / "references" / "gold" / "toy_v1"
    out.mkdir(parents=True)
    for n in _runstore.listdir(proj, "references/gold/toy_v1"):
        (out / n).write_bytes(_runstore.read_bytes(proj, f"references/gold/toy_v1/{n}"))
    _runstore.rmtree(proj, "references/gold")

    config("references:\n  roots:\n    - records/references\n")
    before = len(runs())
    r = imp("arm_root", "gold/toy_v1")
    check(
        "a declared root holding the id: accepted, without the V16 note",
        r.returncode == 0 and "V16" not in r.stderr and len(runs()) == before + 1,
        r.stdout + r.stderr,
    )
    line = v16(evh("validate").stdout)
    check(
        "V16 reads the declared root and checks it against its manifest",
        line.lstrip().startswith("ok") and "1 checked" in line,
        line,
    )
    (out / "b.txt").write_text("billing", encoding="utf-8")
    line = v16(evh("validate").stdout)
    check(
        "V16 fails a text in the root that drifted from its manifest", line.lstrip().startswith("FAIL"), line
    )
    (out / "b.txt").write_text("shipping", encoding="utf-8")

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from evaluation_harness._common import ROOT, DATA; from evaluation_harness._fingerprint import "
                "references_digest as d; print(d(ROOT, 'gold/toy_v1', DATA) or 'NONE')"
            ),
        ],
        cwd=proj,
        env=dict(env, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True,
        text=True,
    )
    check(
        "a reference in a declared root has a content hash, not 'scored against nothing'",
        probe.returncode == 0 and len(probe.stdout.strip()) == 64,
        probe.stdout + probe.stderr,
    )

    before = len(runs())
    r = imp("arm_nowhere", "gold/nowhere_v1")
    check(
        "a root declared and the id found nowhere: refused, naming the roots searched, nothing written",
        r.returncode != 0
        and "records/references" in r.stderr
        and "gold/nowhere_v1" in r.stderr
        and len(runs()) == before,
        r.stdout + r.stderr,
    )
    r = evh("rescore", "--dataset-id", "toy_v1", "--reference-id", "gold/nowhere_v1")
    check(
        "rescore --reference-id names the roots it searched",
        r.returncode != 0 and "records/references" in r.stderr,
        r.stdout + r.stderr,
    )

    config("references:\n  roots: 5\n")
    r = imp("arm_bad", "gold/toy_v1")
    check(
        "a references.roots that is not a list of paths is refused, naming the key",
        r.returncode != 0 and "references.roots" in r.stderr,
        r.stdout + r.stderr,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
summary()
