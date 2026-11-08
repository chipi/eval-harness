#!/usr/bin/env python3
"""A dataset read from a Croissant description (PLAN_0.8.0 E7).

    python tests/test_croissant_in.py

A local Croissant 1.1 file over a CSV: `dataset-create --source croissant` freezes the record set's rows (text, id,
row, a kept field), records the source block (the publisher's version as revision), the licence from its SPDX URL
and the rai: properties as the card; `limit` holds; a parquet FileObject gives the same items; a CSV whose bytes are
not the sha256 the description gives, a FileSet and a field that is not in the record set are refused.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-croissant-in-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-croissant-in")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)
CSV = "id,text,label\nn1,first note,a\nn2,second note,b\nn3,third note,a\n"


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


def description(sha: str, fmt: str = "text/csv") -> dict:
    col = lambda c: {"fileObject": {"@id": "notes.csv"}, "extract": {"column": c}}  # noqa: E731
    return {
        "@context": {
            "@vocab": "http://schema.org/",
            "cr": "http://mlcommons.org/croissant/",
            "rai": "http://mlcommons.org/croissant/RAI/",
        },
        "@type": "sc:Dataset",
        "conformsTo": "http://mlcommons.org/croissant/1.1",
        "name": "acme-notes",
        "description": "Three notes.",
        "url": "https://acme.example/notes",
        "version": "2.1.0",
        "license": "https://spdx.org/licenses/CC-BY-4.0.html",
        "rai:dataBiases": "Only three notes.",
        "distribution": [
            {
                "@type": "cr:FileObject",
                "@id": "notes.csv",
                "contentUrl": "notes.csv",
                "encodingFormat": fmt,
                "sha256": sha,
            }
        ],
        "recordSet": [
            {
                "@type": "cr:RecordSet",
                "@id": "default",
                "name": "default",
                "field": [
                    {
                        "@type": "cr:Field",
                        "@id": "default/id",
                        "name": "id",
                        "dataType": "sc:Text",
                        "source": col("id"),
                    },
                    {
                        "@type": "cr:Field",
                        "@id": "default/text",
                        "name": "text",
                        "dataType": "sc:Text",
                        "source": col("text"),
                    },
                    {
                        "@type": "cr:Field",
                        "@id": "default/label",
                        "name": "label",
                        "dataType": "sc:Text",
                        "source": col("label"),
                    },
                ],
            }
        ],
    }


def ds(i):
    return _runstore.read_json(proj, f"datasets/{i}.json")


try:
    (proj / "notes.csv").write_text(CSV)
    sha = hashlib.sha256(CSV.encode()).hexdigest()
    (proj / "croissant.json").write_text(json.dumps(description(sha)))
    (proj / "data" / "fields").mkdir(parents=True)
    _runstore.write_text(
        proj,
        "fields/notes.yaml",
        "fieldset_id: notes\nfields:\n  - {name: label, type: choice, values: [a, b]}\n",
    )
    q = {"path": "croissant.json", "text": "text", "id": "id", "fields": ["label"]}
    r = evh(
        "dataset-create",
        "--dataset-id",
        "c_v1",
        "--source",
        "croissant",
        "--query",
        json.dumps(q),
        "--fieldset",
        "notes",
    )
    d = ds("c_v1") if r.returncode == 0 else {}
    check(
        "the record set's rows become items: id, row, a kept field; their text in the items folder",
        [(it["item_id"], it.get("source_row"), it.get("fields")) for it in d.get("items") or []]
        == [("n1", 0, {"label": "a"}), ("n2", 1, {"label": "b"}), ("n3", 2, {"label": "a"})]
        and _runstore.read_text(proj, "sources/c_v1/n2.txt") == "second note",
        (r.stdout + r.stderr)[-400:],
    )
    check(
        "the source block, the licence from its SPDX URL, the rai: properties as the card",
        d.get("source", {}).get("provider") == "croissant"
        and d["source"]["ref"] == "acme-notes"
        and d["source"]["revision"] == "2.1.0"
        and d["source"]["url"] == "https://acme.example/notes"
        and d.get("licence") == "CC-BY-4.0"
        and d.get("card") == {"dataBiases": "Only three notes."}
        and d.get("description") == "Three notes.",
        json.dumps({k: d.get(k) for k in ("source", "licence", "card", "description")}),
    )
    r = evh(
        "dataset-create",
        "--dataset-id",
        "c_v2",
        "--source",
        "croissant",
        "--query",
        json.dumps({**q, "limit": 2, "fields": []}),
    )
    check("limit holds", r.returncode == 0 and len(ds("c_v2")["items"]) == 2, (r.stdout + r.stderr)[-300:])
    (proj / "croissant.json").write_text(json.dumps(description("0" * 64)))
    r = evh(
        "dataset-create",
        "--dataset-id",
        "c_v3",
        "--source",
        "croissant",
        "--query",
        json.dumps({**q, "fields": []}),
    )
    check(
        "a file whose bytes are not the description's sha256 is refused",
        r.returncode == 1 and "not the sha256" in r.stderr,
        r.stderr[-300:],
    )
    import pyarrow as pa
    import pyarrow.parquet as pq

    pq.write_table(
        pa.table(
            {
                "id": ["n1", "n2", "n3"],
                "text": ["first note", "second note", "third note"],
                "label": ["a", "b", "a"],
            }
        ),
        proj / "notes.parquet",
    )
    psha = hashlib.sha256((proj / "notes.parquet").read_bytes()).hexdigest()
    pdoc = description(psha, "application/x-parquet")
    pdoc["distribution"][0]["contentUrl"] = "notes.parquet"
    (proj / "croissant.json").write_text(json.dumps(pdoc))
    r = evh(
        "dataset-create",
        "--dataset-id",
        "c_v4",
        "--source",
        "croissant",
        "--query",
        json.dumps({**q, "fields": []}),
    )
    check(
        "a parquet FileObject is read: the same items as the CSV",
        r.returncode == 0
        and [it["item_id"] for it in ds("c_v4")["items"]] == ["n1", "n2", "n3"]
        and _runstore.read_text(proj, "sources/c_v4/n3.txt") == "third note",
        (r.stdout + r.stderr)[-300:],
    )
    fsdoc = description(sha)
    fsdoc["distribution"].append(
        {
            "@type": "cr:FileSet",
            "@id": "parts",
            "encodingFormat": "application/x-parquet",
            "includes": "*.parquet",
        }
    )
    for f in fsdoc["recordSet"][0]["field"]:
        f["source"] = {"fileSet": {"@id": "parts"}, "extract": {"column": f["name"]}}
    (proj / "croissant.json").write_text(json.dumps(fsdoc))
    r = evh(
        "dataset-create",
        "--dataset-id",
        "c_v6",
        "--source",
        "croissant",
        "--query",
        json.dumps({**q, "fields": []}),
    )
    check(
        "a FileSet (many files, which the host lists) is refused, naming its format",
        r.returncode == 1 and "FileSet of application/x-parquet" in r.stderr,
        r.stderr[-300:],
    )
    (proj / "croissant.json").write_text(json.dumps(description(sha)))
    r = evh(
        "dataset-create",
        "--dataset-id",
        "c_v5",
        "--source",
        "croissant",
        "--query",
        json.dumps({**q, "text": "body", "fields": []}),
    )
    check(
        "a field the record set does not have is refused, naming the ones it has",
        r.returncode == 1 and "no field body" in r.stderr and "label" in r.stderr,
        r.stderr[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
