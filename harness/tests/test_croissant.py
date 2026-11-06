#!/usr/bin/env python3
"""A dataset as Croissant 1.1, and its card as text (PLAN_0.8.0 E6).

    python tests/test_croissant.py

A dataset with a licence, a card and fields, made from a parent: `dataset-card --format croissant` gives the 1.1
document (conformsTo, the licence's SPDX page, the card as rai: properties, the parent as prov:wasDerivedFrom, the record file
with its real sha256, a record set whose fields carry the field set's types); without --creator it names creator as
missing on stderr and invents none; the text card lists the answered questions.
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
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-croissant-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-croissant")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


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


try:
    (proj / "data" / "fields").mkdir(parents=True)
    (proj / "data" / "fields" / "notes.yaml").write_text(
        "fieldset_id: notes\nfields:\n  - {name: words, type: integer}\n  - {name: channel, type: choice, values: [email, chat]}\n"
    )
    (proj / "src").mkdir()
    for n in "abc":
        (proj / "src" / f"{n}.txt").write_text(f"item {n}\n")
    (proj / "f.csv").write_text("item_id,words,channel\na,2,email\nb,2,chat\nc,2,email\n")
    r = evh("dataset-create", "--dataset-id", "n_v1", "--source-dir", "src", "--licence", "CC-BY-4.0")
    (proj / "src" / "d.txt").write_text("item d\n")
    r = (
        r
        if r.returncode
        else evh(
            "dataset-create",
            "--dataset-id",
            "n_v2",
            "--source-dir",
            "src",
            "--from",
            "n_v1",
            "--fieldset",
            "notes",
            "--fields",
            "f.csv",
            "--licence",
            "CC-BY-4.0",
        )
    )
    (proj / "card.yaml").write_text("dataUseCases: Testing the export.\ndataBiases: Four short notes.\n")
    r = r if r.returncode else evh("dataset-describe", "--dataset-id", "n_v2", "--card", "card.yaml")
    check(
        "setup: a dataset with a licence, a card, fields and a parent",
        r.returncode == 0,
        (r.stdout + r.stderr)[-300:],
    )
    r = evh("dataset-card", "--dataset-id", "n_v2", "--format", "croissant")
    doc = json.loads(r.stdout) if r.returncode == 0 else {}
    rec = proj / "data" / "datasets" / "n_v2.json"
    check(
        "Croissant 1.1: conformsTo, the licence's SPDX page, the version, the parent, the card as rai:",
        doc.get("conformsTo") == "http://mlcommons.org/croissant/1.1"
        and doc.get("@type") == "sc:Dataset"
        and doc.get("license") == "https://spdx.org/licenses/CC-BY-4.0.html"
        and doc.get("version") == "1.1"
        and doc.get("prov:wasDerivedFrom") == {"@id": "n_v1"}
        and doc["@context"].get("prov") == "http://www.w3.org/ns/prov#"
        and doc.get("rai:dataUseCases") == "Testing the export."
        and doc.get("rai:dataBiases") == "Four short notes.",
        (r.stdout + r.stderr)[:600],
    )
    dist = {d["@id"]: d for d in doc.get("distribution") or []}
    check(
        "the record file is a FileObject with its real sha256; the items a FileSet",
        dist.get("n_v2.json", {}).get("sha256") == hashlib.sha256(rec.read_bytes()).hexdigest()
        and dist.get("items-files", {}).get("@type") == "cr:FileSet",
        json.dumps(list(dist.values()))[:400],
    )
    fields = {f["name"]: f for f in (doc.get("recordSet") or [{}])[0].get("field") or []}
    check(
        "the record set: id, text, and each declared field with its type",
        set(fields) >= {"item_id", "text", "field_words", "field_channel"}
        and fields["field_words"]["dataType"] == "sc:Integer"
        and fields["field_channel"]["dataType"] == "sc:Text"
        and fields["field_words"]["source"]["extract"]["jsonPath"] == "$.items[*].fields.words",
        json.dumps(fields)[:500],
    )
    check(
        "no creator given: none invented, and it is named as missing",
        "creator" not in doc and "creator" in r.stderr,
        r.stderr[-300:],
    )
    r = evh(
        "dataset-card",
        "--dataset-id",
        "n_v2",
        "--format",
        "croissant",
        "--creator",
        "Ada L.",
        "--out",
        "n.json",
    )
    out = json.loads((proj / "n.json").read_text()) if r.returncode == 0 else {}
    check(
        "--creator and --out: written, the creator named; a folder dataset has no url, and that alone is named",
        out.get("creator", {}).get("name") == "Ada L."
        and "asks for url, which" in r.stderr
        and "creator" not in r.stderr,
        r.stderr[-300:],
    )
    r = evh("dataset-card", "--dataset-id", "n_v2")
    check(
        "the text card: version, licence, and each answered question",
        r.returncode == 0
        and "version 1.1" in r.stdout
        and "licence: CC-BY-4.0" in r.stdout
        and "What is it for" in r.stdout
        and "2 of 20 questions answered" in r.stdout,
        r.stdout[-500:],
    )
    r = evh("dataset-card", "--dataset-id", "n_v2", "--format", "hf-readme")
    head = r.stdout.split("---")[1] if r.stdout.startswith("---") else ""
    check(
        "the Hugging Face README: the Hub's licence key, the card's answers under the Hub template's headings",
        r.returncode == 0
        and "license: cc-by-4.0" in head
        and "## Uses" in r.stdout
        and "Testing the export." in r.stdout
        and "## Bias, Risks, and Limitations" in r.stdout
        and "## Annotations" not in r.stdout,
        r.stdout[:600],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
