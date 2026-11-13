#!/usr/bin/env python3
"""Dataset sources: one interface for every place items come from (PLAN_0.8.0 E5).

    python tests/test_sources.py

In a throwaway project: `--source folder` freezes the same items as `--source-dir`; a project's own source
(data/dataset_sources/<name>.py) gives text items, their rows, a source block, a licence and a card, and the record
carries them all and materializes; `--source manifest` records pinned addresses; a name that is no source, an item
id that would leave the folder, and a second fetch into the same folder are refused.
"""

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

proj = Path(tempfile.mkdtemp(prefix="evh-sources-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-sources")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)

MINE = """
class Source:
    def __init__(self, options):
        self.options = options

    def describe(self, query):
        return {
            "source": {"provider": "acme", "ref": "acme/notes", "revision": "r42",
                       "item_url": "https://acme.example/notes?row={row}"},
            "licence": "cc-by-4.0",
            "card": {"dataUseCases": "Testing sources."},
            "features": {"text": "string"},
        }

    def items(self, query):
        for n in range(int(query.get("n", 3))):
            yield {"item_id": f"note_{n}", "text": f"note number {n}", "row": n}
"""


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


def own_source(name, text):
    """The --source naming a project's own source. In the sqlite store a project's code is never under data/ and is
    named by path (RFC-025); in the files store it is data/dataset_sources/NAME.py, named by NAME."""
    if _runstore.sqlite():
        (proj / "own_sources").mkdir(exist_ok=True)
        (proj / "own_sources" / f"{name}.py").write_text(text)
        return f"own_sources/{name}.py:Source"
    (proj / "data" / "dataset_sources").mkdir(parents=True, exist_ok=True)
    (proj / "data" / "dataset_sources" / f"{name}.py").write_text(text)
    return name


def ident(d):
    return [(it["item_id"], it["source_sha256"]) for it in d["items"]]


try:
    raw = proj / "raw"
    raw.mkdir()
    for n in "abc":
        (raw / f"{n}.txt").write_text(f"item {n}\n")
    (raw / "README.md").write_text("not an item\n")
    r1 = evh("dataset-create", "--dataset-id", "dir_v1", "--source-dir", "raw")
    r2 = evh(
        "dataset-create",
        "--dataset-id",
        "fold_v1",
        "--source",
        "folder",
        "--query",
        json.dumps({"path": "raw"}),
    )
    check(
        "--source folder freezes the same items as --source-dir (README skipped)",
        r1.returncode == 0
        and r2.returncode == 0
        and ident(ds("dir_v1")) == ident(ds("fold_v1"))
        and len(ident(ds("fold_v1"))) == 3,
        (r2.stdout + r2.stderr)[-300:],
    )
    mine = own_source("mine", MINE)
    r = evh("dataset-create", "--dataset-id", "mine_v1", "--source", mine, "--query", '{"n": 3}')
    d = ds("mine_v1") if r.returncode == 0 else {}
    check(
        "a project's own source: its block, rows, licence and card on the record",
        d.get("source", {}).get("revision") == "r42"
        and d["source"]["provider"] == "acme"
        and [it.get("source_row") for it in d["items"]] == [0, 1, 2]
        and d.get("licence") == "CC-BY-4.0"
        and d.get("card") == {"dataUseCases": "Testing sources."},
        (r.stdout + r.stderr)[-300:] + json.dumps({k: d.get(k) for k in ("source", "licence", "card")}),
    )
    r = evh("dataset-materialize", "--dataset-id", "mine_v1")
    check("its items materialize, their hashes checked", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    (proj / "data" / "sources" / "x_v1").mkdir(parents=True)
    _runstore.write_text(proj, "sources/x_v1/old.txt", "someone's\n")
    r = evh("dataset-create", "--dataset-id", "x_v1", "--source", mine)
    check(
        "a fetch into an items folder that has files is refused without --force; nothing overwritten",
        r.returncode == 1
        and "would-overwrite" in r.stderr
        and _runstore.read_text(proj, "sources/x_v1/old.txt") == "someone's\n",
        r.stderr[-200:],
    )
    (proj / "m.csv").write_text(
        "item_id,source_url,source_sha256,row\nu1,https://example.org/u1.txt," + "a" * 64 + ",5\n"
    )
    r = evh(
        "dataset-create", "--dataset-id", "man_v1", "--source", "manifest", "--query", '{"path": "m.csv"}'
    )
    m = ds("man_v1") if r.returncode == 0 else {}
    check(
        "--source manifest records each pinned address and its row",
        m.get("items", [{}])[0].get("source_url") == "https://example.org/u1.txt"
        and m["items"][0]["source_sha256"] == "a" * 64
        and m["items"][0].get("source_row") == "5"
        and m["source"]["provider"] == "url",
        (r.stdout + r.stderr)[-300:],
    )
    r = evh("dataset-create", "--dataset-id", "n_v1", "--source", "nosuch")
    check(
        "a name that is no source is refused, naming the built-in ones",
        r.returncode == 1
        and "not a built-in source (" in r.stderr
        and "folder" in r.stderr
        and "manifest" in r.stderr,
        r.stderr[-300:],
    )
    escape = own_source("escape", MINE.replace('f"note_{n}"', '"../../etc/x"'))
    r = evh("dataset-create", "--dataset-id", "e_v1", "--source", escape)
    check(
        "an item id that would leave the items folder is refused, and nothing is frozen",
        r.returncode == 1
        and "a path out of the folder" in r.stderr
        and not _runstore.exists(proj, "datasets/e_v1.json"),
        r.stderr[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
