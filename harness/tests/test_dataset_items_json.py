#!/usr/bin/env python3
"""Assertions for dataset-create over JSON items: --fields-from-item, field `from`/`reduce`, and --exclude.

    python tests/test_dataset_items_json.py

In a throwaway project ($0): a folder of JSON scenario items (one object per file, beside an export manifest.json)
freezes with the field values read out of the items, and the record is byte-equal to the one a --fields file of
the same values gives; a field's `from` (a JSON pointer, RFC 6901) reaches into the item and `reduce: count` takes a
list's length; a non-scalar value, an item that is no object, and a field set that says `reduce` wrongly are refused
naming them; --exclude takes files out of what --glob matched, and changes nothing when absent.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # harness/: the evaluation_harness package
sys.path.insert(0, str(Path(__file__).resolve().parent))  # its siblings in tests/
import _cli
import _runstore
from evaluation_harness._check import check, summary

proj = Path(tempfile.mkdtemp(prefix="evh-items-json-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-items-json")
env.pop("EVAL_DATA_DIR", None)


def evh(*args):
    return _cli.run(proj, env, *args)


def out(r):
    return r.stdout + r.stderr


def put(rel, text):
    p = proj / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def fieldset(fid, body):
    put(f"data/fields/{fid}.yaml", f"fieldset_id: {fid}\nfields:\n{body}")
    _runstore.migrate_in(proj)


def record(ds):
    return _runstore.read_bytes(proj, f"datasets/{ds}.json")


def exists(ds):
    return _runstore.exists(proj, f"datasets/{ds}.json")


def ids(ds):
    return [i["item_id"] for i in json.loads(record(ds))["items"]]


def create(ds, *more, src="avoid"):
    return evh("dataset-create", "--dataset-id", ds, "--source-dir", src, *more)


def refused(label, ds, expect, *more, src="avoid"):
    r = create(ds, *more, src=src)
    check(
        f"refused: {label}",
        r.returncode != 0 and all(e in out(r) for e in expect) and not exists(ds),
        out(r)[-400:],
    )


ITEMS = {
    "a-s1": {
        "scene": "corridor_3",
        "seed": 7,
        "speed": 1.5,
        "start": {"x": 1.5, "y": 2},
        "obstacles": [{"r": 1}, {"r": 2}],
    },
    "a-s2": {"scene": "atrium", "seed": 8, "start": {"x": 0, "y": 0}, "obstacles": [], "extra": "ignored"},
}
for name, doc in ITEMS.items():
    put(f"avoid/{name}.json", json.dumps(doc))
put("avoid/manifest.json", json.dumps({"exported": "2026-11-26", "items": 2}))
put("avoid/README.md", "notes\n")
(proj / "data").mkdir(exist_ok=True)
_runstore.migrate_in(proj)
SEL = ("--glob", "*-s*.json")

# ── --fields-from-item: the record is the one a --fields file gives ──────────────────────────────────────────
fieldset(
    "flat",
    "  - {name: scene, type: text}\n  - {name: seed, type: integer}\n  - {name: speed, type: number}\n",
)
r = create("avoid_v1", *SEL, "--fieldset", "flat", "--fields-from-item")
check("from-item: a dataset from the items' own keys", r.returncode == 0, out(r)[-300:])
by = {it["item_id"]: it for it in json.loads(record("avoid_v1"))["items"]} if r.returncode == 0 else {}
check(
    "from-item: declared fields only, a missing one absent",
    by.get("a-s1", {}).get("fields") == {"scene": "corridor_3", "seed": 7, "speed": 1.5}
    and by.get("a-s2", {}).get("fields") == {"scene": "atrium", "seed": 8},
    by,
)
put(
    "fields.jsonl",
    '{"item_id": "a-s1", "scene": "corridor_3", "seed": 7, "speed": 1.5}\n'
    '{"item_id": "a-s2", "scene": "atrium", "seed": 8}\n',
)
mine = record("avoid_v1") if exists("avoid_v1") else b""
r = create("avoid_v1", *SEL, "--fieldset", "flat", "--fields", "fields.jsonl", "--force")
check(
    "from-item: byte-equal to the record of the equivalent --fields file",
    r.returncode == 0 and bool(mine) and record("avoid_v1") == mine,
    out(r)[-300:],
)

refused(
    "with --fields too, naming both",
    "x_v1",
    ["--fields-from-item", "--fields", "bad-argument"],
    *SEL, "--fieldset", "flat", "--fields-from-item", "--fields", "fields.jsonl",
)  # fmt: skip
refused("without --fieldset", "x_v1", ["--fields-from-item", "--fieldset"], *SEL, "--fields-from-item")
fieldset("flatlist", "  - {name: scene, type: text}\n  - {name: obstacles, type: text}\n")
refused(
    "a list for a scalar field, naming item and field",
    "x_v1",
    ["a-s1", "obstacles"],
    *SEL, "--fieldset", "flatlist", "--fields-from-item",
)  # fmt: skip
put("bad/ok.json", json.dumps({"scene": "x", "seed": 1}))
put("bad/list.json", "[1, 2]")
refused(
    "an item that is no object, naming it",
    "x_v1",
    ["list"],
    "--fieldset",
    "flat",
    "--fields-from-item",
    src="bad",
)
(proj / "bad" / "list.json").unlink()
put("bad/broken.json", "{not json")
refused(
    "an item that is not JSON, naming it",
    "x_v1",
    ["broken"],
    "--fieldset",
    "flat",
    "--fields-from-item",
    src="bad",
)
(proj / "bad" / "broken.json").unlink()
put("bad/ok.json", json.dumps({"scene": "x", "seed": "high"}))
refused(
    "a mistyped value, as --fields refuses it",
    "x_v1",
    ["seed", "high"],
    "--fieldset", "flat", "--fields-from-item",
    src="bad",
)  # fmt: skip
r = create("x_v1", "--manifest", "m.csv", "--fieldset", "flat", "--fields-from-item")
check(
    "refused: --fields-from-item with --manifest",
    r.returncode != 0 and "--source-dir" in out(r),
    out(r)[-300:],
)

# ── a field's `from` and `reduce: count` ─────────────────────────────────────────────────────────────────────
fieldset(
    "nested",
    "  - {name: start_x, type: number, from: /start/x}\n"
    "  - {name: obstacles, type: integer, from: /obstacles, reduce: count}\n"
    "  - {name: scene, type: text}\n",
)
r = create("nested_v1", *SEL, "--fieldset", "nested", "--fields-from-item")
by = {it["item_id"]: it for it in json.loads(record("nested_v1"))["items"]} if r.returncode == 0 else {}
check(
    "from: a pointer reaches in, reduce: count is a list's length, no `from` is the field's own name",
    r.returncode == 0
    and by["a-s1"]["fields"] == {"start_x": 1.5, "obstacles": 2, "scene": "corridor_3"}
    and by["a-s2"]["fields"] == {"start_x": 0, "obstacles": 0, "scene": "atrium"},
    out(r)[-300:] or by,
)
put("esc/e1.json", json.dumps({"a/b": 1, "m~n": 2, "xs": [{"k": "v0"}, {"k": "v1"}], "o": {"p": 1}}))
fieldset(
    "esc",
    '  - {name: slash, type: integer, from: "/a~1b"}\n  - {name: tilde, type: integer, from: "/m~0n"}\n'
    "  - {name: second, type: text, from: /xs/1/k}\n  - {name: gone, type: text, from: /no/such}\n"
    "  - {name: keys, type: integer, from: /o, reduce: count}\n",
)
r = create("esc_v1", "--fieldset", "esc", "--fields-from-item", src="esc")
got = json.loads(record("esc_v1"))["items"][0].get("fields") if r.returncode == 0 else out(r)
check(
    "from: ~1 and ~0 escapes, a list index, an object counted, an unresolved pointer is a missing value",
    got == {"slash": 1, "tilde": 2, "second": "v1", "keys": 1},
    got,
)
fieldset("obj", "  - {name: start, type: text, from: /start}\n")
refused(
    "an object without reduce, naming item, field and pointer",
    "x_v1",
    ["a-s1", "start", "/start"],
    *SEL, "--fieldset", "obj", "--fields-from-item",
)  # fmt: skip
fieldset("cnt", "  - {name: n, type: integer, from: /seed, reduce: count}\n")
refused(
    "reduce: count on a scalar, naming item, field and pointer",
    "x_v1",
    ["a-s1", "n", "/seed"],
    *SEL, "--fieldset", "cnt", "--fields-from-item",
)  # fmt: skip
LOAD_CASES = (
    (
        "reduce: count on a field that is not an integer",
        "{name: n, type: number, from: /o, reduce: count}",
        ["'n'", "integer"],
    ),
    ("a reduce other than count", "{name: n, type: integer, from: /o, reduce: sum}", ["'n'", "reduce"]),
    ("an empty pointer", '{name: n, type: integer, from: ""}', ["'n'", "from"]),
    ("a pointer with no leading slash", "{name: n, type: integer, from: o/p}", ["'n'", "from"]),
    ("a pointer with a bad escape", '{name: n, type: integer, from: "/o~2p"}', ["'n'", "from"]),
)
for n, (label, spec, expect) in enumerate(LOAD_CASES):
    sid = f"badset{n}"  # a field set already in the database is never rewritten, so one each
    fieldset(sid, f"  - {spec}\n")
    refused(f"a field set with {label}, at load", "x_v1", [f"{sid}.yaml", *expect], *SEL, "--fieldset", sid)

from evaluation_harness import _fields  # noqa: E402

committed = __import__("yaml").safe_load(
    (Path(__file__).resolve().parents[1] / "data" / "fields" / "triage.yaml").read_text(encoding="utf-8")
)
check(
    "a committed field set with no from/reduce loads clean and its fields keep their keys",
    _fields.fieldset_problems("triage", committed) == []
    and not any({"from", "reduce"} & set(f) for f in committed["fields"]),
)

# ── --exclude ────────────────────────────────────────────────────────────────────────────────────────────────
r = create("all_v1", "--glob", "*.json")
check(
    "exclude: absent, a manifest.json is an item as before (no reserved names)",
    r.returncode == 0 and ids("all_v1") == ["a-s1", "a-s2", "manifest"],
    out(r)[-300:],
)
r = create("ex_v1", "--glob", "*.json", "--exclude", "manifest.json")
ex = json.loads(record("ex_v1")) if r.returncode == 0 else {}
check(
    "exclude: the file is not an item, and the record names no exclude",
    [i["item_id"] for i in ex.get("items", [])] == ["a-s1", "a-s2"]
    and "exclude" not in ex
    and "glob" not in ex,
    out(r)[-300:],
)
r = create("ex_v2", "--glob", "*.json", "--exclude", "manifest.json", "--exclude", "a-s2.json")
check("exclude: repeatable", r.returncode == 0 and ids("ex_v2") == ["a-s1"], out(r)[-300:])
put("tree/top.json", "{}")
put("tree/sub/one.json", "{}")
put("tree/sub/two.json", "{}")
put("tree/other/three.json", "{}")
r = create("ex_v3", "--glob", "*.json", "--recursive", "--exclude", "sub/*.json", src="tree")
check(
    "exclude: matched against the path under --source-dir, as --glob is",
    r.returncode == 0 and ids("ex_v3") == ["other/three", "top"],
    out(r)[-300:],
)
r = create("ex_v4", "--glob", "*.json", "--exclude", "*.json")
check(
    'exclude: every file excluded is the "no items" refusal',
    r.returncode != 0 and "no items matched" in out(r) and not exists("ex_v4"),
    out(r)[-300:],
)
r = create("ex_v5", "--manifest", "m.csv", "--exclude", "x")
check("exclude: with --manifest is refused", r.returncode != 0 and "--exclude" in out(r), out(r)[-300:])

sys.exit(summary())
