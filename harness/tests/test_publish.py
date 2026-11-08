#!/usr/bin/env python3
"""Publishing a dataset to the Hugging Face Hub, offline (PLAN_0.8.0 P1).

    python tests/test_publish.py

The huggingface source's publish() against a fake Hub API: it writes the items as parquet, the record and the README
in one commit to a new private repo, reads each file back at that commit and checks every sha256, and refuses a repo
that exists and a read-back that is not the bytes written. Through the command: a hidden dataset and items not
materialized here are refused, and a publish is recorded on the dataset without a new version. Nothing leaves the
machine; the live check (a private repo created, read back and deleted) is separate.
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
from evaluation_harness import _common  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.sources.huggingface import Source  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402


class Commit:
    def __init__(self, oid):
        self.oid = oid


class FakeHub:
    """The four HfApi calls publish() makes, kept in memory."""

    def __init__(self, exists=False, tamper=None):
        self.exists, self.tamper, self.files, self.repos = exists, tamper, {}, []
        self.dir = Path(tempfile.mkdtemp(prefix="evh-fakehub-"))

    def repo_exists(self, repo, repo_type=None):
        return self.exists

    def create_repo(self, repo, repo_type=None, private=None, **_kw):
        self.repos.append((repo, repo_type, private))

    def create_commit(self, repo, ops, **_kw):
        for op in ops:
            self.files[op.path_in_repo] = op.path_or_fileobj
        return Commit("a" * 40)

    def hf_hub_download(self, repo, path, repo_type=None, revision=None):
        data = self.files[path]
        if self.tamper == path:
            data = data + b" "
        out = self.dir / path.replace("/", "_")
        out.write_bytes(data)
        return str(out)


items = [
    (
        {
            "item_id": f"n{n}",
            "source_sha256": hashlib.sha256(f"note {n}".encode()).hexdigest(),
            "fields": {"label": n % 2},
        },
        f"note {n}".encode(),
    )
    for n in range(3)
]
record = {
    "dataset_id": "n_v1",
    "version": "1.0",
    "description": "Three notes.",
    "licence": "CC-BY-4.0",
    "items": [it for it, _ in items],
}

hub = FakeHub()
got = Source({"api": hub}).publish(record, items, {"repo": "ada/notes"})
check(
    "publish: a new private repo, one commit of the parquet, the record and the README, every file's sha256 kept",
    hub.repos == [("ada/notes", "dataset", True)]
    and set(hub.files) == {"data/test.parquet", "evh/n_v1.json", "README.md"}
    and got["revision"] == "a" * 40
    and got["private"] is True
    and got["files"]["README.md"] == hashlib.sha256(hub.files["README.md"]).hexdigest()
    and b"license: cc-by-4.0" in hub.files["README.md"],
    json.dumps(got)[:400],
)
for kwargs, why in (
    ({"exists": True}, "exists on the Hub"),
    ({"tamper": "evh/n_v1.json"}, "not the bytes written"),
):
    try:
        Source({"api": FakeHub(**kwargs)}).publish(record, items, {"repo": "ada/notes"})
        refused = ""
    except ValueError as e:
        refused = str(e)
    check(f"publish refuses: {why}", why in refused, refused)
got = Source({"api": FakeHub()}).publish(record, items, {"repo": "ada/notes", "public": True})
check('"public": true makes it public', got["private"] is False)

proj = Path(tempfile.mkdtemp(prefix="evh-publish-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-publish")
for k in ("EVAL_DATA_DIR", "EVAL_RUNS_DIR", "EVAL_MAX_COST_USD"):
    env.pop(k, None)


def evh(*args):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=proj, env=env, capture_output=True, text=True,
        stdin=subprocess.DEVNULL, timeout=300,
    )  # fmt: skip


try:
    (proj / "src").mkdir()
    for n in "ab":
        (proj / "src" / f"{n}.txt").write_text(f"item {n}\n")
    evh("dataset-create", "--dataset-id", "p_v1", "--source-dir", "src")
    r = evh("dataset-publish", "--dataset-id", "p_v1", "--to", "huggingface", "--query", '{"repo": "ada/x"}')
    check(
        "items not materialized here are refused, naming the fix",
        r.returncode == 1 and "not-materialized" in r.stderr and "dataset-materialize" in r.stderr,
        r.stderr[-300:],
    )
    # The Hub source above resolved this process's project; _runstore aims at the test project by EVAL_HOME.
    _common.project_root.cache_clear()
    doc = _runstore.read_json(proj, "datasets/p_v1.json")
    _runstore.write_text(proj, "datasets/p_v1.json", json.dumps({**doc, "text": "hidden"}, indent=1))
    r = evh("dataset-publish", "--dataset-id", "p_v1", "--to", "huggingface", "--query", '{"repo": "ada/x"}')
    check(
        "a hidden dataset is never published", r.returncode == 1 and "not-public" in r.stderr, r.stderr[-300:]
    )
    _runstore.write_text(proj, "datasets/p_v1.json", json.dumps(doc, indent=1))
    r = evh("dataset-publish", "--dataset-id", "p_v1", "--to", "folder", "--query", "{}")
    check(
        "a source that cannot publish is refused",
        r.returncode == 1 and "cannot publish" in r.stderr,
        r.stderr[-300:],
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
