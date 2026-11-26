#!/usr/bin/env python3
"""A manifest row may bring a local source_url when its source_sha256 pins it (0.8.2), and validate names what it notes.

    python tests/test_local_sources.py

In a throwaway project ($0, offline), in whichever store the suite runs in: `dataset-create --manifest` with a row
{item_id, source_url: <relative path>, source_sha256} writes a record `evh validate` accepts (V1); a local source_url
with no hash is refused at create time naming its row, and a refused create writes no record; a local url that leaves
the project is refused; V4 fails a local file whose bytes hash differently and only notes a missing one;
`dataset-materialize` copies the pinned local file and refuses a changed one; an http(s) url is accepted as before.
validate's "name no actor" note names the records.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness import _format
from evaluation_harness._check import check, summary

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore, _cli
import _cli
import _runstore

proj = Path(tempfile.mkdtemp(prefix="evh-local-src-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-local-sources")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVH_ACTOR"):
    env.pop(k, None)


def evh(*args):
    return _cli.run(proj, env, *args)


def line(out, tag):
    """The result line of one validate check."""
    return next(
        (ln for ln in out.splitlines() if f" {tag} " in ln and ln.lstrip().startswith(("ok", "FAIL", "--"))),
        "",
    )


try:
    (proj / "data").mkdir()
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    (proj / "config.yaml").write_text(f"store: {os.environ.get('EVAL_STORE') or 'files'}\n", encoding="utf-8")
    src = proj / "records" / "sources" / "x"
    src.mkdir(parents=True)
    (src / "p01_e01.txt").write_text("hello", encoding="utf-8")
    sha = hashlib.sha256(b"hello").hexdigest()
    rel = "records/sources/x/p01_e01.txt"

    def manifest(name, *rows):
        lines = ["item_id,source_url,source_sha256"] + [",".join(r) for r in rows]
        (proj / name).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return name

    r = evh(
        "dataset-create", "--dataset-id", "loc_v1", "--manifest", manifest("m1.csv", ("p01_e01", rel, sha))
    )
    check("a local source_url pinned by a hash: the create succeeds", r.returncode == 0, r.stdout + r.stderr)
    v = evh("validate").stdout
    check(
        "V1 accepts the record dataset-create wrote for it",
        line(v, "V1").lstrip().startswith("ok"),
        line(v, "V1"),
    )
    check("V4 notes a dataset with no materialized copy, without failing", "FAIL V4" not in v, line(v, "V4"))

    # A local url without a hash is refused, naming the row, and writes nothing.
    r = evh(
        "dataset-create", "--dataset-id", "nohash_v1", "--manifest", manifest("m2.csv", ("p01_e01", rel, ""))
    )
    check(
        "a local source_url with no hash is refused naming its row",
        r.returncode != 0 and "row 1" in r.stderr and "p01_e01" in r.stderr and "source_sha256" in r.stderr,
        r.stdout + r.stderr,
    )
    check(
        "a refused create leaves no record behind",
        not _runstore.is_file(proj, "datasets/nohash_v1.json"),
        str(_runstore.listdir(proj, "datasets")),
    )
    r = evh(
        "dataset-create",
        "--dataset-id",
        "esc_v1",
        "--manifest",
        manifest("m3.csv", ("p01_e01", "../x.txt", sha)),
    )
    check(
        "a local source_url that leaves the project is refused",
        r.returncode != 0 and "row 1" in r.stderr and not _runstore.is_file(proj, "datasets/esc_v1.json"),
        r.stdout + r.stderr,
    )
    r = evh(
        "dataset-create",
        "--dataset-id",
        "web_v1",
        "--manifest",
        manifest("m4.csv", ("w1", "https://example.invalid/w1.txt", sha)),
    )
    check("an http(s) url with a hash is accepted as before", r.returncode == 0, r.stdout + r.stderr)

    # materialize reads the local file and verifies the pin.
    r = evh("dataset-materialize", "--dataset-id", "loc_v1")
    check(
        "dataset-materialize copies the pinned local file",
        r.returncode == 0 and _runstore.read_text(proj, "materialized/loc_v1/p01_e01.txt") == "hello",
        r.stdout + r.stderr,
    )

    # V4's local check: a changed file fails, a missing one is a note.
    (src / "p01_e01.txt").write_text("changed", encoding="utf-8")
    v = evh("validate").stdout
    check(
        "V4 fails a local source whose bytes no longer hash to the pin, and says which",
        line(v, "V4").lstrip().startswith("FAIL") and rel in v,
        line(v, "V4"),
    )
    r = evh("dataset-materialize", "--dataset-id", "loc_v1", "--force")
    check("dataset-materialize refuses the changed local file", r.returncode != 0, r.stdout + r.stderr)
    (src / "p01_e01.txt").unlink()
    v = evh("validate").stdout
    check(
        "a missing local source is a note, not a failure",
        "FAIL V4" not in v and "FAIL V1" not in v and "no file" in v and "not checked" in v and rel in v,
        line(v, "V4"),
    )

    # The note about records that name no actor says which ones.
    for n in ("old_a", "old_b", "old_c", "old_d", "old_e"):
        _runstore.write_text(
            proj,
            f"datasets/{n}.json",
            json.dumps(
                {
                    "dataset_id": n,
                    "version": "1.0",
                    "description": n,
                    "created_at": "2026-11-10T00:00:00Z",
                    "items": [{"item_id": "a", "source_path": "a.txt", "source_sha256": sha}],
                }
            ),
        )
    v = evh("validate").stdout
    note = next((ln for ln in v.splitlines() if "name no actor" in ln), "")
    check(
        "the no-actor note names the records, a few, then 'and N more'",
        "old_a.json" in note
        and "old_b.json" in note
        and "old_c.json" in note
        and "and 2 more" in note
        and "old_e.json" not in note,
        note,
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
summary()
