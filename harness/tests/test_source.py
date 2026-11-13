#!/usr/bin/env python3
"""Where a dataset's items came from: the `source` block (PLAN_0.8.0 E1, E9).

    python tests/test_source.py

In a throwaway project: a fetcher's rows file beside the items becomes the record's source block and each item's
`source_row`, but only for items whose bytes are the ones the fetcher wrote; the profile links each item from the
block; `validate` V22 refuses a key outside the block and rows with no template to fill; `evh migrate` brings a
record made before 0.8.0 to the block from its committed profile, nothing unrecorded guessed, and is idempotent.
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
from evaluation_harness import _source  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402

proj = Path(tempfile.mkdtemp(prefix="evh-source-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-source")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)
TEMPLATE = "https://example.org/d/viewer/default/test?row={row}"


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


def ds(i):
    return _runstore.read_json(proj, f"datasets/{i}.json")


def sha(p: Path) -> str:

    return hashlib.sha256(p.read_bytes()).hexdigest()


try:
    src = proj / "data" / "sources" / "s_v1"
    src.mkdir(parents=True)
    for n in "abc":
        (src / f"{n}.txt").write_text(f"item {n}\n")
    rows = {"a": {"row": 4, "sha256": sha(src / "a.txt")}, "b": {"row": 9, "sha256": "0" * 64}}
    (proj / "data" / "sources" / "s_v1.rows.json").write_text(
        json.dumps(
            {
                "source": {
                    "provider": "example",
                    "ref": "org/d",
                    "url": "https://example.org/d",
                    "split": "test",
                },
                "item_url": TEMPLATE,
                "rows": rows,
            }
        )
    )
    _runstore.migrate_in(proj)
    r = evh("dataset-create", "--dataset-id", "s_v1", "--source-dir", "data/sources/s_v1")
    d = ds("s_v1") if r.returncode == 0 else {}
    by = {it["item_id"]: it for it in d.get("items") or []}
    check(
        "a fetcher's rows file becomes the source block, every key present, unrecorded ones null",
        (d.get("source") or {}).get("ref") == "org/d"
        and set(d["source"]) == set(_source.KEYS)
        and d["source"]["revision"] is None
        and d["source"]["item_url"] == TEMPLATE,
        (r.stdout + r.stderr)[-300:] + json.dumps(d.get("source")),
    )
    check(
        "a row only for an item whose bytes are the fetcher's (b's sha256 differs, c has none)",
        by.get("a", {}).get("source_row") == 4
        and "source_row" not in by.get("b", {})
        and "source_row" not in by.get("c", {}),
        json.dumps(list(by.values()))[:400],
    )
    r = evh("dataset-materialize", "--dataset-id", "s_v1")
    r = r if r.returncode else evh("dataset-profile", "--dataset-id", "s_v1")
    prof = _runstore.read_json(proj, "profiles/s_v1.json") if r.returncode == 0 else {}
    links = {row["item_id"]: row.get("source_url") for row in prof.get("rows") or []}
    check(
        "the profile links an item from the block's template and its row; no row, no link",
        links.get("a") == TEMPLATE.replace("{row}", "4")
        and links.get("c") is None
        and prof.get("source") == d["source"],
        (r.stdout + r.stderr)[-300:] + json.dumps(links),
    )
    r = evh("validate")
    v22 = [ln for ln in r.stdout.splitlines() if "V22" in ln]
    check(
        "validate V22 passes the block",
        bool(v22) and v22[0].lstrip().startswith("ok"),
        "\n".join(v22) or r.stdout[-400:],
    )
    bad = dict(d)
    bad["source"] = {**d["source"], "hf_repo": "org/d", "item_url": "https://example.org/d"}
    _runstore.write_text(proj, "datasets/s_v1.json", json.dumps(bad, indent=1))
    r = evh("validate")
    check(
        "validate V22 refuses a key outside the block, and rows with no {row} to fill",
        r.returncode != 0 and "source.hf_repo is not a key" in r.stdout and "no {row}" in r.stdout,
        r.stdout[-600:],
    )
    _runstore.write_text(proj, "datasets/s_v1.json", json.dumps(d, indent=1))
    # A record made before 0.8.0: no source, its profile carries the old shape and a page per item.
    old = {k: v for k, v in d.items() if k != "source"}
    old["dataset_id"] = "old_v1"
    old["items"] = [{k: v for k, v in it.items() if k != "source_row"} for it in d["items"]]
    _runstore.write_text(proj, "datasets/old_v1.json", json.dumps(old, indent=1))
    legacy = {
        **prof,
        "dataset_id": "old_v1",
        "source": {
            "name": "org/d",
            "url": "https://huggingface.co/datasets/org/d",
            "config": "default",
            "split": "test",
        },
        "rows": [
            {
                "item_id": it["item_id"],
                "words": 2,
                "reference": {},
                "source_url": f"https://huggingface.co/datasets/org/d/viewer/default/test?row={n}",
            }
            for n, it in enumerate(old["items"])
        ],
    }
    _runstore.write_text(proj, "profiles/old_v1.json", json.dumps(legacy, indent=1))
    r = evh("migrate")
    m = ds("old_v1")
    mp = _runstore.read_json(proj, "profiles/old_v1.json")
    check(
        "migrate: the block and each row from the old profile; the provider from its address; nothing guessed",
        r.returncode == 0
        and m.get("source", {}).get("provider") == "huggingface"
        and m["source"]["ref"] == "org/d"
        and m["source"]["revision"] is None
        and m["source"]["gated"] is None
        and [it.get("source_row") for it in m["items"]] == [0, 1, 2]
        and mp["source"] == m["source"],
        r.stdout[-400:] + json.dumps(m.get("source")),
    )
    _runstore.unlink(proj, "project.yaml")  # the steps again (the stamp would say "nothing to do")
    r = evh("migrate")
    check(
        "a second run changes nothing",
        r.returncode == 0 and "dataset(s), 0 changed" in r.stdout,
        r.stdout[-200:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
