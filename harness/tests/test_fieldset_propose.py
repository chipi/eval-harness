#!/usr/bin/env python3
"""A field set proposed from a source's features (PLAN_0.8.0 E8).

    python tests/test_fieldset_propose.py

From a Croissant description with an id, a text, a label of two values and a word count: `fieldset-propose` prints
label as a choice of its sampled values and words as an integer, leaving the text and the id out; nothing is written
until --write, which refuses to overwrite; the accepted field set freezes a dataset with those fields as it is.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HARNESS = Path(__file__).resolve().parents[1]
HERE = HARNESS / "scripts"
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-propose-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-fieldset-propose")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)
CSV = "id,text,label,words\nn1,first note,a,2\nn2,second note,b,2\nn3,third note,a,2\nn4,fourth note,b,2\n"


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )


def col(c):
    return {"fileObject": {"@id": "notes.csv"}, "extract": {"column": c}}


try:
    (proj / "notes.csv").write_text(CSV)
    desc = {
        "@type": "sc:Dataset",
        "name": "notes",
        "distribution": [
            {"@type": "cr:FileObject", "@id": "notes.csv", "contentUrl": "notes.csv", "encodingFormat": "text/csv",
             "sha256": hashlib.sha256(CSV.encode()).hexdigest()}
        ],
        "recordSet": [
            {"@type": "cr:RecordSet", "name": "default", "field": [
                {"name": "default/id", "dataType": "sc:Text", "source": col("id")},
                {"name": "default/text", "dataType": "sc:Text", "source": col("text")},
                {"name": "default/label", "dataType": "sc:Text", "source": col("label")},
                {"name": "default/words", "dataType": "sc:Integer", "source": col("words")},
            ]}
        ],
    }  # fmt: skip
    (proj / "croissant.json").write_text(json.dumps(desc))
    q = json.dumps({"path": "croissant.json", "text": "text", "id": "id"})
    r = evh("fieldset-propose", "--source", "croissant", "--query", q, "--fieldset-id", "notes")
    doc = yaml.safe_load(r.stdout) if r.returncode == 0 else {}
    by = {f["name"]: f for f in doc.get("fields") or []}
    check(
        "label proposed as a choice of its sampled values, words as an integer; text and id left out",
        set(by) == {"label", "words"}
        and by["label"]["type"] == "choice"
        and by["label"]["values"] == ["a", "b"]
        and by["words"]["type"] == "integer",
        (r.stdout + r.stderr)[-500:],
    )
    check("nothing written without --write", not _runstore.exists(proj, "fields/notes.yaml"))
    r = evh("fieldset-propose", "--source", "croissant", "--query", q, "--fieldset-id", "notes", "--write")
    r2 = evh("fieldset-propose", "--source", "croissant", "--query", q, "--fieldset-id", "notes", "--write")
    check(
        "--write writes it; a second --write is refused",
        r.returncode == 0
        and _runstore.is_file(proj, "fields/notes.yaml")
        and r2.returncode == 1
        and "would-overwrite" in r2.stderr,
        r.stdout[-200:] + r2.stderr[-200:],
    )
    q2 = json.dumps({"path": "croissant.json", "text": "text", "id": "id", "fields": ["label", "words"]})
    r = evh(
        "dataset-create",
        "--dataset-id",
        "n_v1",
        "--source",
        "croissant",
        "--query",
        q2,
        "--fieldset",
        "notes",
    )
    items = _runstore.read_json(proj, "datasets/n_v1.json")["items"] if r.returncode == 0 else []
    check(
        "the accepted field set freezes a dataset with those fields, as it is",
        [it.get("fields") for it in items][:2] == [{"label": "a", "words": 2}, {"label": "b", "words": 2}],
        (r.stdout + r.stderr)[-400:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
