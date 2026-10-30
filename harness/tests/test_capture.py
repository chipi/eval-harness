#!/usr/bin/env python3
"""The capture lane's first steps (RFC-019): importers, `evh importer-check`, `evh capture`.

In a throwaway project, offline: the jsonl importer's mapping, filter and window; the contract
check going red on each kind of bad record; a capture's files and hashes; no overwrite without
--force; --since-capture continuing from an earlier capture.

    python tests/test_capture.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _importers  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-capture-"))
(proj / "data").mkdir()
env = dict(os.environ, EVAL_HOME=str(proj))
env.pop("EVAL_DATA_DIR", None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True
    )


def out(r):
    return r.stdout + r.stderr


rows = [
    {
        "id": "a1",
        "body": "first",
        "kind": "x",
        "created_at": "2026-10-01T10:00:00Z",
        "outcome": {"verdict": "fixed"},
    },
    {"id": "a2", "body": "second", "kind": "", "created_at": "2026-10-05T10:00:00Z", "outcome": None},
    {
        "id": "a3",
        "body": {"signal": "s", "probes": {"p": 1}},
        "kind": "y",
        "created_at": "2026-10-09T10:00:00Z",
    },
    {"id": "a4", "body": "untimed", "kind": "x"},
]
(proj / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def ids(query):
    recs, _ = _importers.read("jsonl", {"path": str(proj / "rows.jsonl"), **query})
    return [r["id"] for r in recs]


# ── the jsonl importer ──────────────────────────────────────────────────────────────────────
check("jsonl: every row a record", ids({}) == ["a1", "a2", "a3", "a4"], ids({}))
check("jsonl: where on a value", ids({"where": {"kind": "x"}}) == ["a1", "a4"])
check(
    'jsonl: where on an empty cell matches ""',
    ids({"where": {"kind": ""}}) == ["a2"],
    ids({"where": {"kind": ""}}),
)
check(
    "jsonl: the window is [since, until), untimed rows left out",
    ids({"since": "2026-10-02", "until": "2026-10-09T10:00:00Z"}) == ["a2"],
    ids({"since": "2026-10-02", "until": "2026-10-09T10:00:00Z"}),
)
recs, _ = _importers.read("jsonl", {"path": str(proj / "rows.jsonl")})
r1 = _importers.normalise(next(recs))
check(
    "jsonl: id, body, fields, created_at and outcome mapped",
    r1["body"] == "first"
    and r1["fields"] == {"kind": "x"}
    and r1["created_at"] == "2026-10-01T10:00:00Z"
    and r1["outcome"] == {"verdict": "fixed"},
    r1,
)

# ── hashes ──────────────────────────────────────────────────────────────────────────────────
edited = dict(r1, outcome={"verdict": "noise"})
check(
    "record_sha256 moves when only the outcome changes; body_sha256 does not",
    _importers.record_sha256(edited) != _importers.record_sha256(r1)
    and _importers.body_sha256(edited) == _importers.body_sha256(r1),
)

# ── importer-check ──────────────────────────────────────────────────────────────────────────
r = evh("importer-check", "jsonl", "--query", json.dumps({"path": "rows.jsonl"}))
check("importer-check: a good file passes", r.returncode == 0 and out(r).rstrip().endswith("PASS"), out(r))


def bad_file(name, lines):
    (proj / name).write_text("".join(json.dumps(x) + "\n" for x in lines))
    return evh("importer-check", "jsonl", "--query", json.dumps({"path": name}))


for label, lines, says in (
    ("a repeated id", [{"id": "d", "body": "1"}, {"id": "d", "body": "2"}], "no id repeats"),
    ("an id with a slash", [{"id": "../x", "body": "1"}], "every record is well-formed"),
    ("an id over 200 characters", [{"id": "a" * 201, "body": "1"}], "every record is well-formed"),
    ("a bad time", [{"id": "t", "body": "1", "created_at": "not a time"}], "every record is well-formed"),
    ("no body and no fields", [{"id": "e", "body": None}], "every record is well-formed"),
):
    r = bad_file("bad.jsonl", lines)
    check(f"importer-check: red on {label}", r.returncode == 1 and f"FAIL {says}" in out(r), out(r)[-300:])

(proj / "flaky.py").write_text(
    "import random\n"
    "class Importer:\n"
    "    def __init__(self, options): pass\n"
    "    def records(self, query):\n"
    "        yield {'id': 'f', 'body': str(random.random())}\n"
)
r = evh("importer-check", "flaky.py:Importer", "--query", "{}")
check(
    "importer-check: red when two reads differ",
    r.returncode == 1 and "FAIL two reads" in out(r),
    out(r)[-300:],
)
r = evh("importer-check", "../escape", "--query", "{}")
check(
    "importer-check: a name that would leave data/ is refused",
    r.returncode != 0 and "lowercase" in out(r),
    out(r)[-200:],
)

# ── capture ─────────────────────────────────────────────────────────────────────────────────
q = json.dumps({"path": "rows.jsonl", "until": "2026-10-06"})
r = evh("capture", "--importer", "jsonl", "--query", q, "--capture", "c1")
cap = proj / "data" / "captures" / "c1"
doc = json.loads((cap / "capture.json").read_text()) if (cap / "capture.json").is_file() else {}
check(
    "capture: the records in the window, each a file, each hashed",
    r.returncode == 0
    and doc.get("n_records") == 2
    and sorted(p.name for p in (cap / "records").iterdir()) == ["a1.json", "a2.json"],
    out(r),
)
rec = json.loads((cap / "records" / "a1.json").read_text()) if doc else {}
check(
    "capture: capture.json holds the importer, its code hash, the query and the window",
    doc.get("importer") == "jsonl"
    and len(doc.get("importer_sha256", "")) == 64
    and doc.get("query") == json.loads(q)
    and doc.get("window") == {"until": "2026-10-06"},
    doc,
)
check(
    "capture: each record's sha256 is the record on disk",
    doc and {x["id"]: x["sha256"] for x in doc["records"]}["a1"] == _importers.record_sha256(rec),
)
r = evh("capture", "--importer", "jsonl", "--query", q, "--capture", "c1")
check("capture: never overwritten without --force", r.returncode != 0 and "--force" in out(r), out(r))
r = evh(
    "capture",
    "--importer",
    "jsonl",
    "--query",
    json.dumps({"path": "rows.jsonl"}),
    "--capture",
    "c2",
    "--since-capture",
    "c1",
)
doc2 = (
    json.loads((proj / "data" / "captures" / "c2" / "capture.json").read_text()) if r.returncode == 0 else {}
)
check(
    "capture --since-capture: starts where the earlier one ended, skips what it holds",
    doc2.get("query", {}).get("since") == "2026-10-06"
    and [x["id"] for x in doc2.get("records", [])] == ["a3"]
    and doc2.get("continues") == "c1",
    out(r) + json.dumps(doc2)[:300],
)
r = evh("capture", "--importer", "jsonl", "--query", json.dumps({"path": "bad.jsonl"}), "--capture", "c3")
check(
    "capture: malformed records write nothing",
    r.returncode != 0 and not (proj / "data" / "captures" / "c3").exists(),
    out(r)[-200:],
)

# ── dataset-from-capture ────────────────────────────────────────────────────────────────────
more = [{"id": f"m{i}", "body": f"Same  text {i % 3}", "kind": "abc"[i % 3]} for i in range(12)]
more.append({"id": "m_dup", "body": "same text 0", "kind": "a"})
(proj / "more.jsonl").write_text("".join(json.dumps(x) + "\n" for x in more))
evh("capture", "--importer", "jsonl", "--query", json.dumps({"path": "more.jsonl"}), "--capture", "m")
(proj / "data" / "fields").mkdir(exist_ok=True)
(proj / "data" / "fields" / "kinds.yaml").write_text(
    "fieldset_id: kinds\ndescription: test\nfields:\n"
    "  - {name: kind, type: choice, values: [a, b, c, x, y, ''], label: Kind, description: a kind, public: true}\n"
)
ds_dir = proj / "data" / "datasets"


def ds(name):
    return json.loads((ds_dir / f"{name}.json").read_text())


r = evh("dataset-from-capture", "c1", "--dataset-id", "cap_v1")
d = ds("cap_v1") if r.returncode == 0 else {}
src = proj / "data" / "sources" / "cap_v1"
cap1 = json.loads((proj / "data" / "captures" / "c1" / "capture.json").read_text())
check(
    "from-capture: every record's body is an item, its hash the capture's body_sha256",
    sorted(it["item_id"] for it in d.get("items", [])) == ["a1", "a2"]
    and {it["item_id"]: it["source_sha256"] for it in d.get("items", [])}
    == {x["id"]: x["body_sha256"] for x in cap1["records"]},
    out(r)[-300:],
)
check(
    "from-capture: only the body: the outcome is nowhere in the item's bytes",
    src.is_dir() and all("fixed" not in p.read_text() for p in src.iterdir()),
)
check(
    "from-capture: made_from records the capture, its hash and the rules",
    d.get("made_from", {}).get("capture") == "c1"
    and len(d["made_from"].get("capture_sha256", "")) == 64
    and d["made_from"].get("records") == 2,
    d.get("made_from"),
)
r = evh("dataset-materialize", "--dataset-id", "cap_v1")
check("from-capture: the dataset materializes, hashes checked", r.returncode == 0, out(r)[-300:])
r = evh("validate")
check("from-capture: validate passes (V1 schema, V2, V4)", r.returncode == 0, out(r)[-400:])

r = evh("dataset-from-capture", "m", "--dataset-id", "m_where", "--where", "kind:b")
check(
    "from-capture --where on a field",
    r.returncode == 0 and {it["item_id"] for it in ds("m_where")["items"]} == {"m1", "m4", "m7", "m10"},
    out(r)[-200:],
)
r = evh("dataset-from-capture", "m", "--dataset-id", "m_text", "--dedup", "text")
check(
    "from-capture --dedup text: case and whitespace folded, the first kept",
    r.returncode == 0
    and len(ds("m_text")["items"]) == 3
    and "m_dup" not in {it["item_id"] for it in ds("m_text")["items"]},
    out(r)[-200:],
)
r = evh("dataset-from-capture", "m", "--dataset-id", "m_exact", "--dedup", "exact")
check(
    "from-capture --dedup exact: only identical bodies",
    r.returncode == 0 and len(ds("m_exact")["items"]) == 4,
)
r1 = evh("dataset-from-capture", "m", "--dataset-id", "m_s1", "--sample", "6", "--by", "kind", "--seed", "7")
r2 = evh("dataset-from-capture", "m", "--dataset-id", "m_s2", "--sample", "6", "--by", "kind", "--seed", "7")
s1 = [it["item_id"] for it in ds("m_s1")["items"]] if r1.returncode == 0 else []
kinds = [next(x["kind"] for x in more if x["id"] == i) for i in s1]
check(
    "from-capture --sample --by --seed: 6 items, 2 per kind, the same draw again",
    len(s1) == 6
    and sorted(kinds) == ["a", "a", "b", "b", "c", "c"]
    and s1 == [it["item_id"] for it in ds("m_s2")["items"]],
    out(r1)[-200:] + str(kinds),
)
r = evh("dataset-from-capture", "m", "--dataset-id", "m_nos", "--sample", "3")
check("from-capture --sample without --seed is refused", r.returncode != 0 and "--seed" in out(r))
r = evh(
    "dataset-from-capture",
    "m",
    "--dataset-id",
    "m_f",
    "--fieldset",
    "kinds",
    "--field",
    "kind",
    "--where",
    "kind:a",
)
check(
    "from-capture --fieldset --field: record fields become typed item fields",
    r.returncode == 0 and all(it.get("fields") == {"kind": "a"} for it in ds("m_f")["items"]),
    out(r)[-300:],
)
r = evh("dataset-from-capture", "c2", "--dataset-id", "cap_v2", "--from", "cap_v1")
lin = ds("cap_v2").get("derived_from", {}) if r.returncode == 0 else {}
check(
    "from-capture --from: the earlier version's items stay, the new are added, lineage recorded",
    sorted(it["item_id"] for it in ds("cap_v2")["items"]) == ["a1", "a2", "a3"]
    and lin.get("dataset_id") == "cap_v1"
    and lin.get("added") == ["a3"]
    and lin.get("removed") == [],
    out(r)[-300:],
)
r = evh("dataset-from-capture", "c1", "--dataset-id", "cap_v1")
check(
    "from-capture: a dataset is never overwritten without --force", r.returncode != 0 and "frozen" in out(r)
)
rec_file = proj / "data" / "captures" / "c1" / "records" / "a1.json"
rec_doc = json.loads(rec_file.read_text())
rec_doc["outcome"] = {"verdict": "noise"}
rec_file.write_text(json.dumps(rec_doc))
r = evh("dataset-from-capture", "c1", "--dataset-id", "cap_tampered")
check(
    "from-capture: a record edited since the capture is refused",
    r.returncode != 0 and "does not match the hash" in out(r),
    out(r)[-300:],
)

sys.exit(summary())
