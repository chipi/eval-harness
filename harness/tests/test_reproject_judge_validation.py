#!/usr/bin/env python3
"""tools/reproject_judge_validation.py is rerunnable: a capture and a system that exist with the same content are kept.

    python tests/test_reproject_judge_validation.py

In a scratch project (EVAL_HOME, never this checkout's data), a judge's two stored records for the Goyal source, a rated
dataset of the same two articles and a scorer: the tool makes the capture, the system and a run; run again, it says
"kept" for the capture and the system, makes a second run and no capture error; a capture whose records changed, or a
system whose params did, is refused and nothing is run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HARNESS / "tests"))
proj = Path(tempfile.mkdtemp(prefix="evh-reproject-"))
os.environ.update(EVAL_HOME=str(proj), EVAL_BUILD_REF="test-reproject", EVH_ACTOR="person:tester")
os.environ.setdefault("EVAL_STORE", "files")
ENV = dict(os.environ)

import _cli  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _store  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import runs as model_runs  # noqa: E402

TOOL = HARNESS / "tools" / "reproject_judge_validation.py"
DIMS = ("coherence", "consistency", "fluency", "relevance")
ARTICLES = {"a1": [1, 2, 3], "a2": [3, 1, 2]}
SOURCE_PY = f"""
import json

ARTICLES = {ARTICLES!r}
DIMS = {DIMS!r}


class Source:
    def __init__(self, options):
        pass

    def describe(self, query):
        return {{"source": {{"provider": "test"}}}}

    def items(self, query):
        for aid, ranks in ARTICLES.items():
            r = {{d: [float(x) for x in ranks] for d in DIMS}}
            yield {{"item_id": aid, "text": json.dumps({{"source": "article " + aid, "outputs": ["one", "two", "three"]}}),
                   "answer": json.dumps({{"ratings": r, "raters": [r, r]}})}}
"""


def evh(*args: str) -> subprocess.CompletedProcess[str]:
    return _cli.run(proj, ENV, *args)


def tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), "--scorers", "t-v1", "--sources", "goyal", *args],
        cwd=proj, env=ENV, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600, check=False, encoding="utf-8",
    )  # fmt: skip


def write_records(shift: int = 0) -> None:
    root = proj / "data" / "judge-validation" / "t-v1" / "goyal2022-cnn" / "ja"
    _store.mkdir(root, parents=True, exist_ok=True)
    for i, (aid, ranks) in enumerate(ARTICLES.items()):
        order = ["t0", "gpt3", "brio"]
        reply = {d: [ranks[2] + shift, ranks[0], ranks[1]] for d in DIMS}
        rec = {"article_id": aid, "order": order, "output": json.dumps(reply)}
        _store.write_text(root / f"{i}.json", json.dumps(rec))


def out(r: subprocess.CompletedProcess[str]) -> str:
    return r.stdout + r.stderr


def runs() -> list[str]:
    return [r for r in model_runs.run_ids() if r.startswith("t-v1__ja__validation_goyal_")]


try:
    r = evh("init", "--store", os.environ["EVAL_STORE"])
    _store.mkdir(proj / "data" / "scorers", parents=True, exist_ok=True)
    _store.write_text(
        proj / "data" / "scorers" / "t-v1.yaml",
        yaml.safe_dump(
            {"scorer_id": "t-v1", "kind": "judge", "judges": [{"id": "ja", "params": {"model": "m"}}]}
        ),
    )
    (proj / "src.py").write_text(SOURCE_PY, encoding="utf-8")
    write_records()
    r = r if r.returncode else evh("dataset-create", "--dataset-id", "goyal2022_cnn_v1", "--source", "src.py:Source", "--query", '{"answer": "answer"}')  # fmt: skip
    r = r if r.returncode else evh("dataset-materialize", "--dataset-id", "goyal2022_cnn_v1")
    r = r if r.returncode else evh("reference-promote", "--dataset-id", "goyal2022_cnn_v1", "--labels", "answers", "--tier", "gold", "--reason", "the fixture's ranks decide", "--by", "tester")  # fmt: skip
    check(
        "setup: a scratch project with a rated dataset, a scorer and a judge's stored records",
        r.returncode == 0,
        out(r)[-400:],
    )

    first = tool()
    check(
        "first run: the capture and the system are made and a run is written",
        first.returncode == 0 and len(runs()) == 1 and "kept" not in out(first),
        out(first)[-500:],
    )
    second = tool()
    check(
        "second run: the capture and the system are kept, a second run is made and there is no capture error",
        second.returncode == 0
        and len(runs()) == 2
        and out(second).count("kept") == 2
        and "would-overwrite" not in out(second),
        out(second)[-600:],
    )
    write_records(shift=1)  # the stored records changed since the capture was made
    changed = tool()
    check(
        "a capture whose records differ is refused, naming it, and nothing is run",
        changed.returncode != 0 and "differs" in out(changed) and len(runs()) == 2,
        out(changed)[-500:],
    )
    write_records()
    spec = proj / "data" / "systems" / "t-v1__ja__validation_goyal.yaml"
    _store.write_text(spec, _store.read_text(spec).replace("mode: grade", "mode: pick"))
    sys_changed = tool()
    check(
        "a system whose params differ is refused, naming it, and nothing is run",
        sys_changed.returncode != 0 and "differs" in out(sys_changed) and len(runs()) == 2,
        out(sys_changed)[-500:],
    )
finally:
    import shutil

    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
