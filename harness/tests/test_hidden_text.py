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
env.pop("EVH_PUBLIC", None)
# The in-process surfaces below resolve the project's paths on first read: set before any import.
os.environ.clear()
os.environ.update(env)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation_harness._check import check, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: _runstore
import _runstore  # noqa: E402
from evaluation_harness import _format, _store  # noqa: E402

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
    for d in ("systems", "goals", "fields"):
        (data / d).mkdir(parents=True)
    _runstore.write_text(proj, _format.NAME, f"format: {_format.FORMAT}\n")
    _runstore.write_text(proj, "fields/notes.yaml", FIELDSET)
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
        answers = proj / f"{ds}_gold"
        shutil.copytree(KIT / "gold", answers)
        for f in answers.glob("*.txt"):
            f.write_text(f"{word} gold. " + f.read_text())
        r = evh("label-import", f"{ds}_gold", "--dataset-id", ds, "--set", "owner_gold", "--by", "owner")
        r = (
            r
            if r.returncode
            else evh(
                "reference-promote",
                "--dataset-id",
                ds,
                "--labels",
                "owner_gold",
                "--tier",
                "gold",
                "--reason",
                "The kit's hand-written summaries decide.",
                "--by",
                "owner",
            )
        )
        check(f"setup: {ds}'s gold, imported and promoted", r.returncode == 0, said(r)[-300:])
        for c in ("tickets_lead1", "tickets_lead2"):
            text = (KIT / "systems" / f"{c}_v1.yaml").read_text()
            _runstore.write_text(
                proj,
                f"systems/{c}_{k}_v1.yaml",
                text.replace(f"system_id: {c}_v1", f"system_id: {c}_{k}_v1"),
            )
            r = evh("run", "--system", f"{c}_{k}_v1", "--dataset", ds)
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
        and MARK["h"] in _runstore.read_text(proj, "profiles/tickets_h.json"),
        said(r)[-300:] + said(r2)[-300:],
    )
    _runstore.write_text(
        proj,
        "datasets/tickets_h.json",
        json.dumps({**_runstore.read_json(proj, "datasets/tickets_h.json"), "text": "hidden"}, indent=2)
        + "\n",
    )
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

    # ── label agreement: two sets whose labels are short text (a category by its shape, RFC-023) ──────────
    # On a hidden dataset its label values are per-item labels (§4): a reference's text if a set is promoted.
    for k in MARK:
        ds = f"tickets_{k}"
        ids = sorted(x["item_id"] for x in _runstore.read_json(proj, f"datasets/{ds}.json")["items"])
        for name, extra in (("short_a", ""), ("short_b", " two")):
            folder = proj / f"{ds}_{name}"
            folder.mkdir()
            for n, i in enumerate(ids):
                (folder / f"{i}.txt").write_text(f"{MARK[k]}{extra if n % 2 else ''}\n")
            r = evh("label-import", str(folder), "--dataset-id", ds, "--set", name, "--by", "owner")
            check(f"setup: {ds}'s short label set {name}", r.returncode == 0, said(r)[-300:])
    cat2 = proj / "cat2"
    r = evh("catalog", "--out", str(cat2))
    page_s = (cat2 / "d" / "tickets_s.html").read_text() if r.returncode == 0 else ""
    page_h = (cat2 / "d" / "tickets_h.html").read_text() if r.returncode == 0 else ""
    check(
        "catalog: the shown dataset's label agreement names its labels (the surface shows them)",
        "how often two sets agree" in page_s and MARK["s"] in page_s,
        said(r)[-300:],
    )
    check(
        "catalog: the hidden dataset's label agreement is there, its labels' text never",
        "how often two sets agree" in page_h and MARK["h"] not in page_h,
        [ln for ln in page_h.splitlines() if MARK["h"] in ln][:2],
    )
    rc, out, err = run_command(proj, "labels", ["--dataset-id", "tickets_s", "--confusion"], public=True)
    check(
        "MCP public: labels --confusion names the shown dataset's labels",
        rc == 0 and MARK["s"] in out,
        out[-300:],
    )
    rc, out, err = run_command(proj, "labels", ["--dataset-id", "tickets_h", "--confusion"], public=True)
    check(
        "MCP public: labels --confusion on the hidden dataset answers, with none of its labels' text",
        rc == 0 and "tickets_h" in out and MARK["h"] not in out + err,
        (out + err)[-400:],
    )

    # ── the deployment's copy of the data ──────────────────────────────────────────────────
    from evaluation_harness._release import copy_data

    # A label set on the hidden dataset (RFC-023): its record is copied, its label text never.
    lab = "labels/tickets_h/l1"
    _store.mkdir(data / lab, parents=True)
    _runstore.write_text(proj, f"{lab}/{item}.txt", f"a label quoting {MARK['h']}\n")
    # Its record carries a person's notes from the sheet (free text: RFC-019 §4's adjudication notes).
    _runstore.write_text(
        proj,
        f"{lab}/labels.json",
        json.dumps(
            {
                "dataset_id": "tickets_h",
                "set": "l1",
                "n_items": 1,
                "notes": {item: f"a note quoting {MARK['h']}"},
            }
        ),
    )
    # A tag set on the hidden dataset (PLAN_0.8.0 D1): its modes are counted, a person's note on an output is its text.
    tag = "tags/tickets_h/t1"
    _store.mkdir(data / tag, parents=True)
    _runstore.write_text(
        proj,
        f"{tag}/tags.json",
        json.dumps(
            {
                "kind": "tag-set",
                "dataset_id": "tickets_h",
                "set": "t1",
                "failure_modes": "m",
                "n_tagged": 1,
                "runs": {"r1": {item: {"modes": ["too-long"], "note": f"it repeats {MARK['h']}"}}},
            }
        ),
    )
    rc, out, err = run_command(proj, "tags", ["--dataset-id", "tickets_h", "--json"], public=True)
    check(
        "MCP public: tags counts the hidden dataset's modes, never a note",
        rc == 0 and "too-long" in out and MARK["h"] not in out + err,
        (out + err)[-300:],
    )
    rc, out, err = run_command(proj, "labels", [], public=False)
    check("labels, local: a hidden set's notes are listed on this machine", MARK["h"] in out, out[-300:])
    rc, out, err = run_command(proj, "labels", [], public=True)
    check(
        "MCP public: labels lists the hidden dataset's sets, never their notes",
        rc == 0 and "tickets_h" in out and MARK["h"] not in out + err,
        (out + err)[-300:],
    )
    # A study run on each dataset (RFC-029, RFC-032 step 7): the agent's hypotheses, rationales and instructions may quote
    # the items it was shown; the goal's page and the release copy show a hidden dataset's study without them.
    _runstore.write_text(
        proj,
        "goals/studies_g.yaml",
        "goal_id: studies_g\ntitle: t\nstatement: s\ndecision: d\n"
        "success_criteria: {primary: {measure: overlap_f1, direction: higher}}\n"
        "datasets:\n  - {dataset_id: tickets_s, role: validation}\n  - {dataset_id: tickets_h, role: validation}\n",
    )
    for k, word in MARK.items():
        _runstore.write_text(
            proj,
            f"studies/studies_g/study_{k}.yaml",
            f"dataset: tickets_{k}\nbaseline: {{system: tickets_lead1_{k}_v1}}\nmeasure: overlap_f1\nsampler: agent\n"
            f"accept: {{point: {{min_gain: 0}}}}\nstop: {{trials: 3}}\ndirections: look at what {word} wrote\n",
        )
        events = [
            {"event": "start", "round": "r1", "baseline": f"tickets_lead1_{k}_v1", "instruction": f"read {word} first"},
            {"event": "trial", "k": 1, "config_id": f"study_{k}-t1", "outcome": "kept", "reason": "beat the best so far",
             "hypothesis": f"{word} items are long", "rationale": f"{word} said so", "change": {"params": {"sentences": 2}, "prompts": []},
             "vs_best": {"delta": 0.2}, "cost_usd": 0, "shown": [{"item_id": item, "sha256": "a" * 64}]},
            {"event": "end", "reason": "3 trial(s)", "summary": "1 trial(s), 1 kept"},
        ]  # fmt: skip
        _runstore.write_text(
            proj,
            f"studies/studies_g/study_{k}.events.jsonl",
            "".join(json.dumps(e) + "\n" for e in events),
        )
        _runstore.write_text(
            proj,
            f"studies/studies_g/study_{k}/study_{k}-t1.yaml",
            f"system_id: study_{k}-t1\nparams: {{provider: echo, sentences: 2}}\n",
        )
    # A faithfulness record of a replay on each dataset: what production and the replay answered quote the item.
    for k, word in MARK.items():
        rec = {"n": 1, "model_id": f"fleet_{k}", "config_id": "replay_v1", "dataset_id": f"tickets_{k}", "items_sha256": "a" * 64,
               "versions_sha256": "a" * 64, "adapter_sha256": None, "commits": {"c" * 40: 1}, "production_run": "prod",
               "counts": {"items": 1, "agree": 0, "differ": 1, "replay_errors": 0, "production_missing": 0}, "coverage": {},
               "disagreements": [{"item_id": item, "kind": "differ", "commit": "c" * 40, "production": f"{word} p", "replay": f"{word} r", "error": f"{word} e"}],
               "at": "2026-11-14T00:00:00Z", "actor": {"type": "person", "name": "t"}}  # fmt: skip
        _runstore.write_text(proj, f"faithfulness/fleet_{k}/1.json", json.dumps(rec))
        _runstore.write_text(
            proj,
            f"faithfulness/fleet_{k}/1.exceptions.jsonl",
            json.dumps(
                {
                    "item_id": item,
                    "cause": f"{word} cause",
                    "actor": {"type": "person", "name": "t"},
                    "at": "x",
                }
            )
            + "\n",
        )
    cat3 = proj / "cat3"
    r = evh("catalog", "--out", str(cat3))
    goal_page = next(iter(cat3.rglob("studies_g.html")), None)
    text = goal_page.read_text() if goal_page else ""
    check(
        "catalog: a study on the shown dataset is on its goal page with its hypothesis; one on the hidden dataset is there, "
        "its hypothesis never",
        r.returncode == 0
        and "study_s" in text
        and "study_h" in text
        and f"{MARK['s']} items are long" in text
        and not found(cat3, MARK["h"])
        and "kept" in text,
        (said(r)[-300:], found(cat3, MARK["h"])),
    )
    # A judging of a hidden run is another score of it (runs/<run>/scores/<judge>@<set>) and its rows carry the source
    # row's `_meta`, which can quote the item: the release cuts them to the call too.
    hrun = next(
        d
        for d in _runstore.listdir(proj, "runs")
        if _runstore.is_file(proj, f"runs/{d}/run.json")
        and _runstore.read_json(proj, f"runs/{d}/run.json").get("dataset_id") == "tickets_h"
    )
    jrel = f"runs/{hrun}/scores/j1@judging-set"
    jdir = data / jrel
    _store.mkdir(jdir, parents=True)
    _runstore.write_text(
        proj,
        f"{jrel}/score.json",
        json.dumps({"scorer": "j1", "reference": "judging-set", "label": "judged/j1"}),
    )
    _runstore.write_text(
        proj, f"{jrel}/metrics.json", json.dumps({"derived": {"kind": "judge", "from": hrun}})
    )
    _runstore.put_rows_text(
        jdir,
        json.dumps(
            {"item_id": item, "judge_x": 1.0, "_meta": {"usage": {"t": 1}, "prompt": f"quoting {MARK['h']}"}}
        )
        + "\n",
    )
    rel = proj / ".release"
    counts = copy_data(data, rel)
    check(
        "release: a label set's record is copied, its label text never",
        (rel / "labels" / "tickets_h" / "l1" / "labels.json").is_file()
        and not list((rel / "labels").rglob("*.txt")),
        str(sorted(str(p.relative_to(rel)) for p in (rel / "labels").rglob("*")))
        if (rel / "labels").exists()
        else "no labels/",
    )
    t1 = rel / "tags" / "tickets_h" / "t1" / "tags.json"
    check(
        "release: a hidden dataset's tag set is copied with its modes, without its notes",
        t1.is_file() and '"too-long"' in t1.read_text() and MARK["h"] not in t1.read_text(),
        t1.read_text()[:300] if t1.is_file() else "no tags.json",
    )
    check("release: the shown dataset's outputs and gold texts are copied", bool(found(rel, MARK["s"])))
    check("release: nothing of the hidden dataset's text", not found(rel, MARK["h"]), found(rel, MARK["h"]))
    sl, sh = rel / "studies" / "studies_g", rel / "faithfulness"
    check(
        "release: a study on the shown dataset is copied whole; one on the hidden dataset keeps its outcomes, reasons and "
        "counts, its hypotheses, rationales and instructions a mark",
        MARK["s"] in (sl / "study_s.events.jsonl").read_text()
        and MARK["s"] in (sl / "study_s.yaml").read_text()
        and counts["hidden_studies"] == 1
        and "beat the best so far" in (sl / "study_h.events.jsonl").read_text()
        and "(not published" in (sl / "study_h.events.jsonl").read_text()
        and "(not published" in (sl / "study_h.yaml").read_text()
        and (sl / "study_h" / "study_h-t1.yaml").is_file()
        and '"vs_best"' in (sl / "study_h.events.jsonl").read_text(),
        (counts, (sl / "study_h.events.jsonl").read_text()[:400]),
    )
    fh, fs = (sh / "fleet_h" / "1.json").read_text(), (sh / "fleet_s" / "1.json").read_text()
    check(
        "release: a faithfulness record of a replay on the shown dataset is copied whole; on the hidden dataset it keeps "
        "the item, its kind and who named it, never what was answered or the cause",
        MARK["s"] in fs
        and MARK["s"] in (sh / "fleet_s" / "1.exceptions.jsonl").read_text()
        and counts["hidden_faithfulness"] == 1
        and '"item_id"' in fh
        and '"differ"' in fh
        and json.loads(fh)["disagreements"][0]["production"] is None
        and "(not published" in fh
        and "(not published" in (sh / "fleet_h" / "1.exceptions.jsonl").read_text()
        and '"person"' in (sh / "fleet_h" / "1.exceptions.jsonl").read_text(),
        (counts, fh[:400]),
    )
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
    if not _runstore.sqlite():
        _runstore.write_text(proj, "references/gold/tickets_s/t99_extra.txt", "untracked")
        try:
            copy_data(data, proj / ".release2")
            refused = ""
        except SystemExit as exc:
            refused = str(exc)
        check("release: a reference text git does not track is refused", "t99_extra.txt" in refused, refused)
    else:
        # In the database there is no git to say what is published: a reference whose manifest says its texts are
        # not redistributed (their licence) is what a release must refuse, as git refuses them when ignored.
        man = "references/gold/tickets_s/manifest.json"
        doc = _runstore.read_json(proj, man)
        doc["redistributed"] = False
        _runstore.write_text(proj, man, json.dumps(doc, indent=1))
        try:
            copy_data(data, proj / ".release2")
            refused = ""
        except SystemExit as exc:
            refused = str(exc)
        check(
            "release: the texts of a reference not redistributed (its manifest) are refused, in the database too",
            "not redistributed" in refused and "references/gold/tickets_s/" in refused,
            refused,
        )
        for text, says in (
            (json.dumps({**doc, "redistributed": "false"}), "'false', not true or false"),
            ("{", "cannot be read"),
        ):
            _runstore.write_text(proj, man, text)
            try:
                copy_data(data, proj / ".release3")
                refused = ""
            except SystemExit as exc:
                refused = str(exc)
            check(
                f"release: a manifest that cannot say ({says}): its texts refused, never published",
                says in refused,
                refused,
            )
finally:
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
