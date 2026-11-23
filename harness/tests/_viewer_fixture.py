"""The project the viewer's tests read (RFC-039): a goal, a round, two arms and a baseline over one dataset marked
`text: hidden`, every text of which carries a marker word: the items' sources, a text field, the gold references, and
(because the echo arms copy the first sentences of an item) every arm's outputs.

A hidden dataset's marker must reach no answer of a public server. `positive control`: the same marker is in the local
answers (`MARK` is the word the tests search for), or a search that finds nothing would prove nothing.

    import _viewer_fixture as fx
    fx.build(proj, env)        # raises AssertionError, with the command's output, when a step fails
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import _cli
import _runstore
import _serve
from evaluation_harness._check import store_under_test

KIT = Path(__file__).resolve().parents[1] / "tutorial"
MARK = "Hiddenmarkerword"
DS = "tk_h"
GOAL = "hg"
SYSTEMS = ("h_lead1_v1", "h_lead2_v1")
FIELDSET = """fieldset_id: notes
description: test fields
fields:
  - {name: note, type: text, label: Note, description: a note, public: true}
  - {name: link, type: url, label: Link, description: a link, public: true}
"""


def build(proj: Path, env: dict) -> None:
    """The project at `proj`, offline and free: made by the commands a person runs."""

    def evh(*args: str) -> None:
        r = _cli.run(proj, env, *args)
        assert r.returncode == 0, f"evh {' '.join(args)}: {(r.stdout + r.stderr)[-600:]}"

    evh("init", "--store", store_under_test(), "--tutorial")
    cfg = (proj / "config.yaml").read_text(encoding="utf-8")
    assert f"store: {store_under_test()}" in cfg, f"the project is not on the store under test: {cfg[:300]}"
    src, gold = proj / "src_h", proj / "gold_h"
    shutil.copytree(KIT / "tickets", src)
    shutil.copytree(KIT / "gold", gold)
    for f in src.glob("*.txt"):
        f.write_text(f"{MARK} reported this. " + f.read_text())
    for f in gold.glob("*.txt"):
        f.write_text(f"{MARK} gold. " + f.read_text())
    _runstore.write_text(proj, "fields/notes.yaml", FIELDSET)
    rows = ["item_id,note,link"] + [
        f"{f.stem},{MARK} note,https://example.org/{MARK}/{f.stem}" for f in sorted(src.glob("*.txt"))
    ]
    (proj / "h_fields.csv").write_text("\n".join(rows) + "\n")
    for step in (
        ("dataset-create", "--dataset-id", DS, "--source-dir", "src_h", "--fieldset", "notes", "--fields", "h_fields.csv"),
        ("dataset-materialize", "--dataset-id", DS),
        ("label-import", "--sheet", "gold_h", "--dataset-id", DS, "--set", "owner_gold", "--by", "person:owner"),
        ("reference-promote", "--dataset-id", DS, "--labels", "owner_gold", "--tier", "gold", "--reason",
         "the kit's hand-written summaries decide", "--by", "person:owner"),
    ):  # fmt: skip
        evh(*step)
    for sid, n in zip(SYSTEMS, (1, 2), strict=True):
        _runstore.write_text(
            proj, f"systems/{sid}.yaml", f"system_id: {sid}\nparams:\n  provider: echo\n  sentences: {n}\n"
        )
    evh(
        "goal-new", GOAL, "--set", "title=Hidden ticket summaries", "--set", "statement=A one-line summary of a ticket.",
        "--set", "decision=Which system writes it.", "--set", "success_criteria.primary.measure=overlap_f1",
        "--set", "success_criteria.primary.direction=higher", "--set", f"datasets.0.dataset_id={DS}",
        "--set", "datasets.0.role=validation", "--by", "person:owner",
    )  # fmt: skip
    evh("model-new", "gem", "--set", "name=Gem model", "--set", "kind=llm", "--set", "weights=open",
        "--set", "licence=Apache-2.0", "--set", 'aliases=["gem:1b"]', "--by", "person:owner")  # fmt: skip
    evh(
        "deployment-new",
        "gem",
        "mac",
        "--set",
        "where=the office Mac",
        "--set",
        "tag=gem:1b",
        "--by",
        "person:owner",
    )
    evh("prompt-version", "--name", f"{GOAL}/prompt", "--text", "Keep what support needs.", "--note", "the first wording",
        "--by", "person:owner")  # fmt: skip
    for sid in SYSTEMS:
        evh("run", "--system", sid, "--dataset", DS, "--goal", GOAL)
    evh(
        "round-open",
        "--goal",
        GOAL,
        "--dataset",
        DS,
        "--adopt",
        "--hypothesis",
        "two sentences beat one",
        "--by",
        "person:owner",
    )

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(proj), "-c", "user.name=t", "-c", "user.email=t@t", *args],
            capture_output=True,
            check=True,
            env=env,
        )

    # A held-out side, sealed, that the goal names: the screens of a held-out test read its counts and its register.
    evh("dataset-split", "--dataset-id", DS, "--test", "0.5", "--seal", "--by", "person:owner")
    evh(
        "goal-set",
        GOAL,
        "--set",
        f"datasets.1.dataset_id={DS}_test",
        "--set",
        "datasets.1.role=test",
        "--by",
        "person:owner",
    )
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "project")
    # A profile with the items' text (it needs the text in git), then the dataset is hidden: a dataset made public first
    # and hidden later holds text a public surface must not show.
    evh("dataset-profile", "--dataset-id", DS, "--with-text")
    for ds in (DS, f"{DS}_validation", f"{DS}_test"):
        doc = _runstore.read_json(proj, f"datasets/{ds}.json")
        _runstore.write_text(
            proj, f"datasets/{ds}.json", json.dumps({**doc, "text": "hidden"}, indent=2) + "\n"
        )
    evh("catalog")
    git("add", "-A")
    git(
        "commit", "-qm", "profile, hidden", "--allow-empty"
    )  # on SQLite the datasets are in the store, not the tree


def serve_public(proj: Path, env: dict, *extra: str) -> tuple[subprocess.Popen, int, list[str]]:
    """`evh catalog-serve --public` for the project on a free port, once it answers: (the process, the port, its
    output as it comes). Its Host names are this machine's address and name with that port, so a browser reaches it
    as `http://127.0.0.1:<port>/workbench/`; its rate limit is off unless `extra` sets one (a screen's reads are many)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen(
        [sys.executable, str(_cli.CLI), "catalog-serve", "--port", str(port), "--public",
         f"127.0.0.1:{port},localhost:{port}", "--rate", "0", *extra],
        cwd=proj, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    lines = _serve.drain(p, [])
    for _ in range(300):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return p, port, lines
        except OSError:
            if p.poll() is not None:
                break
            time.sleep(0.1)
    p.kill()
    raise AssertionError("the public server did not answer: " + "\n".join(lines[-20:]))
