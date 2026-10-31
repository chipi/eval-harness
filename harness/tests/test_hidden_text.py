#!/usr/bin/env python3
"""`text: hidden` (RFC-019 §4): no text from a hidden dataset on any public surface.

In a throwaway git project built from the tutorial ($0, offline), two datasets of the same tickets:
tickets_s (shown) and tickets_h (hidden). Each has its own marker word in every ticket, its gold
texts, and a text and a URL field. Two echo arms run on each, so their outputs quote the marker.
Then every public surface is searched for the hidden marker, and for the shown one beside it: a
surface where the shown marker does not appear proves nothing, so that is a failure too.

Surfaces: the catalog's pages, the inspector's item answer (public, publishing outputs and
references), `evh dataset-items` as a public MCP server runs it, and the deployment's copy of the
data (_release.py). Judge verdicts are not exercised here (no judge runs offline).

    python tests/test_hidden_text.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "scripts"
KIT = HERE.parent / "tutorial"
proj = Path(tempfile.mkdtemp(prefix="evh-hidden-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-hidden")
env.pop("EVAL_DATA_DIR", None)
env.pop("EVAL_RUNS_DIR", None)
env.pop("EVH_PUBLIC", None)
# The in-process surfaces below resolve the project's paths on first read: set before any import.
os.environ.clear()
os.environ.update(env)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

MARK = {"s": "Shownmarkerword", "h": "Hiddenmarkerword"}
FIELDSET = """fieldset_id: notes
description: test fields
fields:
  - {name: note, type: text, label: Note, description: a note, public: true}
  - {name: link, type: url, label: Link, description: a link, public: true}
"""


def evh(*args, extra_env=None):
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args],
        cwd=proj,
        env={**env, **(extra_env or {})},
        capture_output=True,
        text=True,
    )


def said(r):
    return r.stdout + r.stderr


def git(*args):
    return subprocess.run(["git", "-C", str(proj), *args], capture_output=True, text=True)


def found(root: Path, word: str) -> list[str]:
    """The files under `root` holding `word`."""
    return [
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and word in p.read_text(errors="replace")
    ]


try:
    data = proj / "data"
    for d in ("configs", "goals", "fields"):
        (data / d).mkdir(parents=True)
    (data / "fields" / "notes.yaml").write_text(FIELDSET)
    for k, word in MARK.items():
        ds = f"tickets_{k}"
        src = proj / "tutorial" / ds
        shutil.copytree(KIT / "tickets", src)
        for f in src.glob("*.txt"):
            f.write_text(f"{word} reported this. " + f.read_text())
        rows = ["item_id,note,link"] + [
            f"{f.stem},{word} note,https://example.org/{word}/{f.stem}" for f in sorted(src.glob("*.txt"))
        ]
        (proj / f"{ds}_fields.csv").write_text("\n".join(rows) + "\n")
        r = evh(
            "dataset-create",
            "--dataset-id",
            ds,
            "--source-dir",
            f"tutorial/{ds}",
            "--fieldset",
            "notes",
            "--fields",
            f"{ds}_fields.csv",
        )
        check(f"setup: {ds} created", r.returncode == 0, said(r)[-300:])
        evh("dataset-materialize", "--dataset-id", ds)
        gold = data / "references" / "gold" / ds
        shutil.copytree(KIT / "gold", gold)
        for f in gold.glob("*.txt"):
            f.write_text(f"{word} gold. " + f.read_text())
        for c in ("tickets_lead1", "tickets_lead2"):
            cfg = data / "configs" / f"{c}_{k}.yaml"
            text = (KIT / "configs" / f"{c}.yaml").read_text()
            cfg.write_text(
                text.replace("tickets_v1", ds).replace(f"config_id: {c}_v1", f"config_id: {c}_{k}_v1")
            )
            r = evh("experiment-run", "--config", str(cfg))
            check(f"setup: {c} runs on {ds}", r.returncode == 0, said(r)[-300:])
    git("init", "-q")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "project")
    # Both profiles carry their text: tickets_h's was written before it was marked hidden, the way
    # a dataset made public first and hidden later has one. Hiding it must hide that text too.
    r = evh("dataset-profile", "--dataset-id", "tickets_s", "--with-text")
    r2 = evh("dataset-profile", "--dataset-id", "tickets_h", "--with-text")
    check(
        "setup: both profiles are written with their text",
        r.returncode == 0
        and r2.returncode == 0
        and MARK["h"] in (data / "profiles" / "tickets_h.json").read_text(),
        said(r)[-300:] + said(r2)[-300:],
    )
    f = data / "datasets" / "tickets_h.json"
    f.write_text(json.dumps({**json.loads(f.read_text()), "text": "hidden"}, indent=2) + "\n")
    r = evh("dataset-profile", "--dataset-id", "tickets_h", "--with-text")
    check(
        "dataset-profile --with-text is refused on a hidden dataset",
        r.returncode != 0 and "hidden" in said(r),
    )
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "profiles")

    # ── the catalog ────────────────────────────────────────────────────────────────────────
    r = evh("catalog")
    cat = proj / ".build" / "catalog"
    check("setup: the catalog builds", r.returncode == 0, said(r)[-400:])
    check(
        "catalog: the shown dataset's text is on its pages (the search can find a marker)",
        bool(found(cat, MARK["s"])),
    )
    check(
        "catalog: no page carries the hidden dataset's text", not found(cat, MARK["h"]), found(cat, MARK["h"])
    )
    page = cat / "d" / "tickets_h.html"
    check(
        "catalog: the hidden dataset's page says why its text is not shown",
        page.is_file() and "text: hidden" in page.read_text(),
        str(sorted(p.name for p in (cat / "d").glob("*")) if (cat / "d").is_dir() else "no d/"),
    )

    # ── the inspector's item answer, in process ────────────────────────────────────────────
    from evaluation_harness import catalog_serve as cs
    from evaluation_harness.catalog_views import load_catalog_adapter

    cs.set_adapter(load_catalog_adapter(None))
    item = "t01_login"

    on = {k: [a for a in cs.A.arms() if cs.A.describe(a).get("dataset") == f"tickets_{k}"] for k in MARK}
    check(
        "setup: the catalog lists two arms on each dataset",
        all(len(v) == 2 for v in on.values()),
        str(cs.A.arms()),
    )

    def answer(k: str) -> str:
        a = cs.item({"arms": [",".join(on[k])], "item": [item], "ref": [f"gold/tickets_{k}"]})
        return json.dumps(a)

    cs.LIMITS.update(hosts=(), publish=())
    check(
        "inspector, local: the hidden dataset's text is shown on this machine",
        MARK["h"] in answer("h"),
        answer("h")[:400],
    )
    cs.LIMITS.update(hosts=("public",), publish=("outputs", "references"))
    check(
        "inspector, public: outputs, reference and fields of the shown dataset served",
        MARK["s"] in answer("s"),
        answer("s")[:400],
    )
    check(
        "inspector, public: nothing of the hidden dataset's text, whatever is published",
        MARK["h"] not in answer("h"),
        answer("h")[:600],
    )
    cs.LIMITS.update(hosts=(), publish=())

    # ── a public MCP server's command ──────────────────────────────────────────────────────
    from evaluation_harness.mcp_server import run_command

    rc, out, err = run_command(proj, "dataset-items", ["--dataset-id", "tickets_s"], public=True)
    check(
        "MCP public: dataset-items shows the shown dataset's text",
        rc == 0 and MARK["s"] in out,
        (out + err)[-300:],
    )
    rc, out, err = run_command(proj, "dataset-items", ["--dataset-id", "tickets_h"], public=True)
    check(
        "MCP public: dataset-items answers on the hidden dataset",
        rc == 0 and "t01_login" in out,
        (out + err)[-300:],
    )
    check("MCP public: with none of its text", MARK["h"] not in out + err, out[-300:])
    rc, out, err = run_command(
        proj, "dataset-items", ["--dataset-id", "tickets_h", "--item", item], public=True
    )
    check(
        "MCP public: dataset-items --item on the hidden dataset is refused",
        rc != 0 and MARK["h"] not in out + err,
    )

    # ── the deployment's copy of the data ──────────────────────────────────────────────────
    from evaluation_harness._release import copy_data

    rel = proj / ".release"
    counts = copy_data(data, rel)
    check("release: the shown dataset's outputs and gold texts are copied", bool(found(rel, MARK["s"])))
    check("release: nothing of the hidden dataset's text", not found(rel, MARK["h"]), found(rel, MARK["h"]))
    check(
        "release: the hidden dataset's runs, reference (manifest only) and profile are there, numbers only",
        counts["hidden_runs"] == 2
        and counts["hidden_refs"] == 1
        and (rel / "references" / "gold" / "tickets_h").is_dir()
        and not [
            p for p in (rel / "references" / "gold" / "tickets_h").iterdir() if p.name != "manifest.json"
        ]
        and (rel / "profiles" / "tickets_h.json").is_file()
        and not (rel / "materialized").exists(),
        json.dumps(counts)
        + " "
        + str(sorted(str(p.relative_to(rel)) for p in rel.rglob("*") if "runs" not in str(p))),
    )
    (data / "references" / "gold" / "tickets_s" / "t99_extra.txt").write_text("untracked")
    try:
        copy_data(data, proj / ".release2")
        refused = ""
    except SystemExit as exc:
        refused = str(exc)
    check("release: a reference text git does not track is refused", "t99_extra.txt" in refused, refused)
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
