#!/usr/bin/env python3
"""A sentinel in every field that may carry private text, searched for in every public read, page and export (R7).

    python tests/test_public_leak.py        # EVAL_STORE=files (default) or sqlite

A project of two datasets (lk_h marked `text: hidden`, lk_s shown) with a unique sentinel in each field that may carry
private text: the items' inputs, their text and URL fields, the arms' outputs, the gold references, a second label set,
the judges' reasons, a goal, a round, a prompt (text and note), a system's own prompt parameter, a reference's promotion
reason, a capture's records. Then every surface that is public is searched for every sentinel:

- every read the public MCP server offers, in this process (`mcp_server.run_op`, public);
- a public server (`catalog-serve --public`) under each `--publish` (nothing, outputs, references, both): every /api/v1
  read and each read it leaves out, the inspector's /api/compare, /api/item and /api/sheet, the Workbench's files;
- the catalog's export (`evh catalog`), with and without `catalog: {publish: [prompts]}`;
- the deployment's copy of the data (`_release.copy_data`).

A sentinel may appear only where the rules say its field is public (`server_allows`, `catalog_allows`, `copy_allows`:
each cites the doc it comes from). The owner's decision of 2026-11-23 settled the two fields the docs left unsaid, and
their checks start "owner 2026-11-23:": a system's own prompt parameter is a prompt (shown only with `--publish
prompts` / `catalog: {publish: [prompts]}`); a reference's promotion reason and a prompt version's note are project
notes (public). The checks that start "RFC-041 F4:" are F4's: the public env set with no public hosts (the inspector's
item view and the reads a public MCP leaves out serve text), and `_visibility.hidden` failing open. A control for each
sentinel: a person's own reads carry it, or a search that finds nothing proves nothing.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/
proj = Path(tempfile.mkdtemp(prefix="evh-leak-"))
env = dict(os.environ, EVAL_HOME=str(proj), EVAL_BUILD_REF="test-leak", EVH_ACTOR="person:tester")
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR", "EVAL_MAX_COST_USD", "EVH_FOR", "EVH_PUBLIC"):
    env.pop(k, None)
env.setdefault("EVAL_STORE", "files")
# the in-process reads below resolve the project's paths on first use: the environment is the project's before any import
os.environ.clear()
os.environ.update(env)

import _cli  # noqa: E402
import _runstore  # noqa: E402
import _viewer_fixture as fx  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _store  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402

KIT = HARNESS / "tutorial"
SALT = "7f3a"
#: the fields that may carry private text, each with a sentinel per dataset (H: `text: hidden`, S: text shown)
FIELDS = ("ITEM-INPUT", "FIELD-TEXT", "FIELD-URL", "OUTPUT", "REFERENCE", "LABEL", "JUDGE-REASON")
#: the project's own prose and records, one sentinel each
PROJECT = ("NOTE-GOAL", "NOTE-ROUND", "NOTE-PROMPT", "PROMPT-TEXT", "SYSTEM-PROMPT", "NOTE-REFERENCE",
           "CAPTURE-BODY", "CAPTURE-OUTCOME")  # fmt: skip


def s(field: str, ds: str | None = None) -> str:
    return f"SENTINEL-{field}-{ds}-{SALT}" if ds else f"SENTINEL-{field}-{SALT}"


ADAPTER = f"""
from types import SimpleNamespace

def call_system(text, params):
    tag = "H" if "-H-" in text else "S"
    return SimpleNamespace(output="SENTINEL-OUTPUT-" + tag + "-{SALT} a summary", tokens_in=1, tokens_out=1,
                           cost_usd=0.0, latency_ms=1.0, extra={{}}, meta={{}})

def score(output, reference):
    return {{"words": float(len(output.split())), "chars": float(len(output))}}

PRIMARY_METRIC = "words"
"""
FIELDSET = """fieldset_id: notes
description: test fields
fields:
  - {name: note, type: text, label: Note, description: a note, public: true}
  - {name: link, type: url, label: Link, description: a link, public: true}
"""


def evh(*args: str) -> subprocess.CompletedProcess:
    return _cli.run(proj, env, *args, timeout=600)


def need(*args: str) -> None:
    r = evh(*args)
    assert r.returncode == 0, f"evh {' '.join(args)}: {(r.stdout + r.stderr)[-500:]}"


def git(*args: str) -> None:
    subprocess.run(["git", "-C", str(proj), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   capture_output=True, check=True, env=env)  # fmt: skip


def build() -> None:
    need("init", "--store", store_under_test(), "--tutorial")
    _runstore.write_text(proj, "fields/notes.yaml", FIELDSET)
    (proj / "leak_adapter.py").write_text(ADAPTER)
    for tag in "HS":
        ds = f"lk_{tag.lower()}"
        src, gold, lab = proj / f"src_{tag}", proj / f"gold_{tag}", proj / f"lab_{tag}"
        for d, kit, word in (
            (src, "tickets", "ITEM-INPUT"),
            (gold, "gold", "REFERENCE"),
            (lab, "gold", "LABEL"),
        ):
            shutil.copytree(KIT / kit, d)
            for f in d.glob("*.txt"):
                f.write_text(f"{s(word, tag)} " + f.read_text())
        rows = ["item_id,note,link"] + [
            f"{f.stem},{s('FIELD-TEXT', tag)},https://example.org/{s('FIELD-URL', tag)}/{f.stem}"
            for f in sorted(src.glob("*.txt"))
        ]
        (proj / f"{ds}_fields.csv").write_text("\n".join(rows) + "\n")
        need("dataset-create", "--dataset-id", ds, "--source-dir", f"src_{tag}", "--fieldset", "notes",
             "--fields", f"{ds}_fields.csv")  # fmt: skip
        need("dataset-materialize", "--dataset-id", ds)
        need(
            "label-import",
            "--sheet",
            f"gold_{tag}",
            "--dataset-id",
            ds,
            "--set",
            "owner_gold",
            "--by",
            "person:owner",
        )
        need("reference-promote", "--dataset-id", ds, "--labels", "owner_gold", "--tier", "gold", "--reason",
             f"The hand-written answers decide. {s('NOTE-REFERENCE')}", "--by", "person:owner")  # fmt: skip
        need(
            "label-import",
            "--sheet",
            f"lab_{tag}",
            "--dataset-id",
            ds,
            "--set",
            "triage",
            "--by",
            "person:owner",
        )
    for sid in ("lk_a_v1", "lk_b_v1"):
        _runstore.write_text(
            proj, f"systems/{sid}.yaml",
            f"system_id: {sid}\nadapter: leak_adapter.py\nparams:\n  prompt: {s('SYSTEM-PROMPT')}\n",
        )  # fmt: skip
    need("prompt-version", "--name", "lkg/prompt", "--text", s("PROMPT-TEXT"), "--note", s("NOTE-PROMPT"),
         "--by", "person:owner")  # fmt: skip
    need("prompt-version", "--name", "lkg/prompt", "--text", s("PROMPT-TEXT") + " second", "--note", "again",
         "--by", "person:owner")  # fmt: skip
    need("goal-new", "lkg", "--set", "title=Leak goal", "--set", f"statement=A goal. {s('NOTE-GOAL')}",
         "--set", "decision=Which system.", "--set", "success_criteria.primary.measure=words",
         "--set", "success_criteria.primary.direction=higher", "--set", "datasets.0.dataset_id=lk_s",
         "--set", "datasets.0.role=validation", "--set", "datasets.1.dataset_id=lk_h",
         "--set", "datasets.1.role=validation", "--by", "person:owner")  # fmt: skip
    for tag in "SH":
        for sid in ("lk_a_v1", "lk_b_v1"):
            need("run", "--system", sid, "--dataset", f"lk_{tag.lower()}", "--goal", "lkg")
    need("round-open", "--goal", "lkg", "--dataset", "lk_s", "--adopt", "--hypothesis", s("NOTE-ROUND"),
         "--by", "person:owner")  # fmt: skip
    # a judge on each dataset (the tutorial's fake one: $0, offline); its reasons are then rewritten to carry a sentinel
    for tag in "HS":
        sc = yaml.safe_load((KIT / "scorers" / "tickets-judge-v1.yaml").read_text())
        sc.update(scorer_id=f"lk-judge-{tag.lower()}-v1", dataset_id=f"lk_{tag.lower()}")
        _runstore.write_text(
            proj, f"scorers/lk-judge-{tag.lower()}-v1.yaml", yaml.safe_dump(sc, sort_keys=False)
        )
        need(
            "judge-score",
            "--dataset-id",
            f"lk_{tag.lower()}",
            "--scorer",
            f"lk-judge-{tag.lower()}-v1",
            "--unvalidated",
        )
    for tag in "HS":  # the fake judge's reasons are fixed words: a sentinel in their place
        for f in _store.glob(proj / "data" / "judge-verdicts" / f"lk-judge-{tag.lower()}-v1", "*/*/*.json"):
            v = json.loads(_store.read_text(f, encoding="utf-8"))
            v["why"] = json.loads(json.dumps(v["why"]).replace("the fake judge", s("JUDGE-REASON", tag)))
            _store.write_text(f, json.dumps(v, indent=2, sort_keys=True) + "\n")
    # a production capture: a body and an outcome
    records = [{"id": f"c{i}", "body": f"{s('CAPTURE-BODY')} {i}", "created_at": "2026-10-01T10:00:00Z",
             "outcome": {"resolution": s("CAPTURE-OUTCOME")}} for i in range(3)]  # fmt: skip
    (proj / "prod.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    need(
        "capture", "--importer", "jsonl", "--query", json.dumps({"path": "prod.jsonl"}), "--capture", "lk_cap"
    )
    git("init", "-q")
    git("add", "-A")
    git("commit", "-qm", "project")
    for tag in "HS":
        need("dataset-profile", "--dataset-id", f"lk_{tag.lower()}", "--with-text")
    doc = _runstore.read_json(proj, "datasets/lk_h.json")
    _runstore.write_text(proj, "datasets/lk_h.json", json.dumps({**doc, "text": "hidden"}, indent=2) + "\n")
    git("add", "-A")
    git("commit", "-qm", "profiles, one hidden", "--allow-empty")


# ── what is asked ───────────────────────────────────────────────────────────────────────────────────────────────────
ALL = {s(f, t): (f, t) for f in FIELDS for t in "HS"} | {s(p): (p, "") for p in PROJECT}
DS = {"H": "lk_h", "S": "lk_s"}
SETTINGS = (
    (),
    ("outputs",),
    ("references",),
    ("outputs", "references"),
    ("prompts",),
)  # `catalog-serve --publish`
ARMS = {t: f"runs/{DS[t]}/lk_a_v1,runs/{DS[t]}/lk_b_v1" for t in "HS"}
#: What a path part is in the fixture; each of a list is asked for in turn.
PART: dict[str, list] = {
    "dataset": ["lk_s", "lk_h"], "set": ["owner_gold", "triage"], "scorer": ["lk-judge-s-v1", "lk-judge-h-v1"],
    "goal": ["lkg"], "round": ["r1"], "system": ["lk_a_v1"], "capture": ["lk_cap"], "label": ["runs"],
    "fieldset": ["notes"], "failure_modes": ["none"], "kind": ["intervals"], "metric": ["words"], "model": ["gem"],
    "deployment": ["mac"], "study": ["s1"],
}  # fmt: skip
#: The reads that need an input to answer at all, or that answer differently for one: their arguments in full.
CALLS: dict[str, list[dict]] = {
    "reference-show": [{"tier": "gold", "name": d} for d in ("lk_s", "lk_h")],
    "arm-show": [{"label": "runs", "dataset": d, "system": "lk_a_v1"} for d in ("lk_s", "lk_h")],
    "comparison-crosstab": [{"runs": ARMS[t], "crosstab": "words,chars"} for t in "SH"],
    "comparison-show": [{"runs": ARMS[t]} for t in "SH"] + [{"goal": "lkg", "round": "r1"}],
    "search": [{"text": "ticket"}, {"text": "SENTINEL"}],
    "period-compare": [{"system": "lk_a_v1", "dataset": d, "candidate": "lk_b_v1"} for d in ("lk_s", "lk_h")],
    "run-compare": [{"baseline": ARMS["S"].split(",")[0], "candidate": ARMS["S"].split(",")[1]}],
    "chart": [{"kind": "intervals", "goal": "lkg"}, {"kind": "intervals", "dataset": "lk_s"}, {"kind": "intervals", "dataset": "lk_h"}],
    "arm-list": [{}, {"dataset": "lk_s"}, {"dataset": "lk_h"}],
    "metric-show": [{"metric": "words", "dataset": d} for d in ("lk_s", "lk_h")],
    "metric-list": [{}, {"dataset": "lk_h"}],
    "looks": [{}, {"dataset": "lk_h"}],
    "baselines": [{}, {"dataset": "lk_h"}],
    "deploy-sheet": [{"system": "lk_a_v1", "capture": "lk_cap"}],
    "pair-test": [{"dataset": d, "a": "lk_a_v1", "b": "lk_b_v1"} for d in ("lk_s", "lk_h")],
    "family-test": [{"dataset": d, "a": "lk_a_v1"} for d in ("lk_s", "lk_h")],
    "comparison-item": [{"runs": ARMS[t].split(",")[0], "item": "t01_login"} for t in "SH"],
    "comparison-items": [{"runs": ARMS[t]} for t in "SH"],
    "sheet-show": [{"dataset": DS[t], "runs": ARMS[t]} for t in "SH"],
    "label-coverage-show": [{"dataset": DS[t], "capture": "lk_cap", "map": "tutorial/production/outcomes.yaml"} for t in "SH"],
    "label-mutants": [{"dataset": DS[t], "capture": "lk_cap", "map": "tutorial/production/outcomes.yaml"} for t in "SH"],
    "exposure": [{}, {"dataset": "lk_h"}],
    "sealed-counts": [{"dataset": "lk_h"}, {"dataset": "lk_s"}],
    "data-ls": [{}, {"path": "data"}],
    "data-show": [{"path": f"data/profiles/{d}.json", "text": True} for d in ("lk_h", "lk_s")]
    + [{"path": "data/datasets/lk_h.json"}],
    "periods": [{"model": "gem"}],
    "faithfulness-show": [{"model": "gem"}],
}  # fmt: skip


def calls(op, public: bool) -> list[dict]:
    """The arguments a read is asked with: its path parts from the fixture (each dataset, label set and judge in turn),
    or the set written out for it above; only the inputs a public read takes when it is a public call."""
    if op.name == "prompt-show":
        return (
            [{"name": "lkg/prompt", "text": True}, {"name": "lkg/prompt"}]
            if not public
            else [{"name": "lkg/prompt"}]
        )
    if op.name == "prompt-diff":
        ids = prompt_ids()
        return [{"a": ids[0], "b": ids[-1]}]
    found: list[dict]
    if op.name in CALLS:
        found = CALLS[op.name]
    else:
        found = [{}]
        for p in op.path_params():
            found = [{**a, p: v} for a in found for v in PART.get(p, ["x"])]
    return (
        found
        if not public
        else [{k: v for k, v in a.items() if k in op.path_params() or k in public_props(op)} for a in found]
    )


def public_props(op) -> set:
    return set(op.schema(public=True)["properties"])


def prompt_ids() -> list[str]:
    r = evh("prompt-show", "--name", "lkg/prompt", "--json")
    return [v["id"] for v in json.loads(r.stdout)["result"]["versions"]]


def path_of(op, a: dict) -> str:
    parts = [
        urllib.parse.quote(str(a[x[1:-1]]), safe="") if x.startswith("{") else x for x in op.route.split("/")
    ]
    q = "&".join(
        f"{k}={urllib.parse.quote('true' if v is True else str(v))}"
        for k, v in a.items()
        if k not in op.path_params()
    )
    return "/api/v1" + "/".join(parts) + (f"?{q}" if q else "")


def http(port: int, path: str) -> tuple[int, str]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": f"127.0.0.1:{port}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - the test's own server  # nosec B310
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


# ── what is found ───────────────────────────────────────────────────────────────────────────────────────────────────
def note(seen: dict, label: str, text: str) -> None:
    for k in ALL:
        if k in text:
            seen.setdefault(k, []).append(label)


def in_process(reads: list, public: bool, seen: dict, got: dict) -> None:
    """Each read, in this process, as the MCP server runs it (`run_op`: the tool's schema, then the call): its answer, or
    the words of its refusal, searched for every sentinel."""
    for op in reads:
        for a in calls(op, public):
            label = f"{op.name} {json.dumps(a, sort_keys=True)}"
            try:
                mcp_server.check_arguments(op, a, public)
                body = json.dumps(mcp_server.run_op(op, a, public))
                got.setdefault(op.name, []).append("ok")
            except BaseException as exc:  # noqa: BLE001 - a refusal's words are searched too
                body = f"{type(exc).__name__}: {exc}"
                got.setdefault(op.name, []).append("refused")
            note(seen, label, body)


def over_http(publish: tuple) -> tuple[dict, dict]:
    """Every route a public server answers, asked over HTTP, with `--publish <publish>`: the API's reads, the reads it
    leaves out, the inspector's three, the health route, the Workbench's files and the pages a catalog has."""
    seen: dict = {}
    got: dict = {}
    srv, port, _lines = fx.serve_public(proj, env, *(("--publish", ",".join(publish)) if publish else ()))
    try:
        for op in mcp_server.read_ops(True):
            for a in calls(op, True):
                st, b = http(port, path_of(op, a))
                got.setdefault(op.name, []).append(st)
                note(seen, f"GET {path_of(op, a)}", b)
        for op in [o for o in ops.of_kind("read") if o.public_dropped]:
            for a in calls(op, False):
                st, b = http(port, path_of(op, a))
                got.setdefault(op.name, []).append(st)
                note(seen, f"GET {path_of(op, a)}", b)
        for t in "SH":
            q = urllib.parse.quote
            for path in (
                f"/api/compare?arms={q(ARMS[t])}", f"/api/compare?arms={q(ARMS[t])}&item=t01_login",
                f"/api/item?arms={q(ARMS[t])}&item=t01_login&ref=gold/{DS[t]}",
                f"/api/item?arms={q(ARMS[t].split(',')[0])}&item=t01_login",
                f"/api/item?dataset={DS[t]}&item=t01_login", f"/api/sheet?dataset={DS[t]}&runs={q(ARMS[t])}",
                f"/api/sheet?dataset={DS[t]}&runs={q(ARMS[t])}&format=csv",
            ):  # fmt: skip
                st, b = http(port, path)
                got.setdefault(path.split("?")[0], []).append(st)
                note(seen, f"GET {path}", b)
        for path in (
            "/api/health", "/api/v1/openapi.json", "/workbench/", "/workbench/workbench.js", "/workbench/live.js",
            "/workbench/help.js", "/workbench/workbench.css", "/", "/index.html", "/catalog/", "/d/lk_h.html",
        ):  # fmt: skip
            st, b = http(port, path)
            got.setdefault(path, []).append(st)
            note(seen, f"GET {path}", b)
    finally:
        srv.terminate()
        srv.wait(timeout=10)
    return seen, got


def in_files(root: Path, label: str) -> dict:
    seen: dict = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            data = p.read_bytes()
            for k in ALL:
                if k.encode() in data:
                    seen.setdefault(k, []).append(f"{label}:{p.relative_to(root)}")
    return seen


# ── what the docs say may be there ──────────────────────────────────────────────────────────────────────────────────
def server_allows(k: str, publish: tuple) -> bool:
    """A sentinel on a public server's answer (RFC-039, RFC-019, `catalog-serve --publish`): a hidden dataset's text
    never; a shown dataset's field values yes, its outputs only with `outputs`, its references only with `references`,
    its items' inputs, labels and judge reasons never (an item's input is a non-goal; the labels and reasons are
    `public_dropped` or not taken); a goal's, a round's and a prompt's own words yes (RFC-039, open question 1: a
    prompt is the project's, served); owner, 2026-11-23: a system's own prompt parameter only with `prompts`, a
    reference's promotion reason always; a capture's records are not shown."""
    field, tag = ALL[k]
    if tag == "H":
        return False
    if tag == "S":
        return (
            field in ("FIELD-TEXT", "FIELD-URL")
            or (field == "OUTPUT" and "outputs" in publish)
            or (field == "REFERENCE" and "references" in publish)
        )
    return field in ("NOTE-GOAL", "NOTE-ROUND", "NOTE-PROMPT", "NOTE-REFERENCE") or (
        field in ("SYSTEM-PROMPT", "PROMPT-TEXT") and "prompts" in publish
    )


def catalog_allows(k: str, prompts: bool) -> bool:
    """A sentinel on a page of the export (`evh catalog`, always public: catalog_build's docstring, RFC-019 §4, ADR-0002):
    counts and means only; an item's text only where the project publishes it (a profile written `--with-text`, shown
    datasets only); outputs and references only through the inspector's server; a prompt's text only with
    `catalog: {publish: [prompts]}`, and so a system's own prompt parameter (owner, 2026-11-23); a goal's and a round's
    own words, a prompt version's note and a reference's promotion reason yes; the rest as above, not shown."""
    field, tag = ALL[k]
    if tag == "H":
        return False
    if tag == "S":
        return field in ("ITEM-INPUT", "FIELD-TEXT", "FIELD-URL")
    return field in ("NOTE-GOAL", "NOTE-ROUND", "NOTE-PROMPT", "NOTE-REFERENCE") or (
        prompts and field in ("PROMPT-TEXT", "SYSTEM-PROMPT")
    )


def copy_allows(k: str) -> bool:
    """A sentinel in the deployment's copy of the data (`_release.py`, test_hidden_text): nothing of a hidden dataset's
    text, no capture's records; a shown dataset's data is copied (its outputs, references, verdicts), so only what the
    docs forbid for any dataset is asserted."""
    field, tag = ALL[k]
    if tag == "H":
        return False
    return field not in ("CAPTURE-BODY", "CAPTURE-OUTCOME")


#: The fields the owner decided on 2026-11-23, the docs having been silent: a system's own prompt parameter (a prompt),
#: a reference's promotion reason and a prompt version's note (project notes).
DECIDED = ("SYSTEM-PROMPT", "PROMPT-TEXT", "NOTE-REFERENCE", "NOTE-PROMPT")


def judge(surface: str, seen: dict, allows, must: tuple = (), f4: tuple = ()) -> None:
    """One check a sentinel for the surface: found only where `allows`. `must`: sentinels the surface has to carry (the
    control that the search can find one); `f4`: sentinels whose failure is RFC-041 F4's."""
    for k in ALL:
        ok = bool(allows(k)) or k not in seen
        prefix = "RFC-041 F4: " if k in f4 else "owner 2026-11-23: " if ALL[k][0] in DECIDED else ""
        check(
            f"{prefix}{surface}: {k} is {'allowed here' if allows(k) else 'not shown'}",
            ok,
            f"in {len(seen[k])} answer(s), the first: {seen[k][0][:220]}" if k in seen else "",
        )
    for k in must:
        check(f"{surface}: the control carries {k}", k in seen, "not found: the search proves nothing for it")


def covered(surface: str, got: dict, names: tuple, good) -> None:
    missing = [n for n in names if not any(good(x) for x in got.get(n, []))]
    check(
        f"{surface}: the reads that need the fixture answer ({len(names) - len(missing)} of {len(names)})",
        not missing,
        missing,
    )


MUST_ANSWER = (
    "goal-list", "goal-show", "goal-status", "goal-leaderboard", "round-list", "round-show", "dataset-list",
    "dataset-show", "dataset-items", "dataset-card", "leaderboard", "system-list", "system-show", "runs-list", "arm-list",
    "arm-show", "prompt-list", "prompt-show", "prompt-diff", "reference-list", "reference-show", "fieldset-list",
    "overview-show", "comparison-show", "chart", "metric-list", "label-set-list", "label-set-show", "baselines",
    "scorer-list", "scorer-show", "capture-list", "capture-show", "pair-test", "comparison-crosstab",
)  # fmt: skip


try:
    build()
    from evaluation_harness import _visibility, mcp_server, ops
    from evaluation_harness import catalog_serve as cs
    from evaluation_harness.catalog_adapter import load_catalog_adapter

    reads = list(ops.of_kind("read"))
    served = mcp_server.read_ops(public=True)
    cs.set_adapter(load_catalog_adapter(None))

    # ── the control: a person's own reads show everything the fixture holds ────────────────────────────────────────
    local: dict = {}
    got_local: dict = {}
    in_process(reads, False, local, got_local)
    view = cs.item({"arms": [ARMS["S"].split(",")[0]], "item": ["t01_login"], "ref": ["gold/lk_s"]})
    note(local, "the local inspector's item view of lk_s", json.dumps(view))
    view = cs.item({"arms": [ARMS["H"].split(",")[0]], "item": ["t01_login"], "ref": ["gold/lk_h"]})
    note(local, "the local inspector's item view of lk_h", json.dumps(view))
    covered("local reads", got_local, MUST_ANSWER, lambda x: x == "ok")
    for k in ALL:
        check(
            f"control: a person's own reads carry {k}",
            k in local or ALL[k][0] in ("SYSTEM-PROMPT", "NOTE-REFERENCE", "CAPTURE-BODY", "CAPTURE-OUTCOME"),
            "no local read carries it: the search for it on a public surface proves nothing",
        )
    print(
        "  local control carries:",
        len(local),
        "of",
        len(ALL),
        "sentinels; not:",
        sorted(set(ALL) - set(local)),
    )

    # ── the public MCP server's reads ─────────────────────────────────────────────────────────────────────────────
    seen: dict = {}
    got: dict = {}
    in_process(served, True, seen, got)
    covered("public MCP", got, MUST_ANSWER, lambda x: x == "ok")
    judge("public MCP read", seen, lambda k: server_allows(k, ()), must=(s("NOTE-GOAL"),))

    # ── a public server, for each --publish ───────────────────────────────────────────────────────────────────────
    for publish in SETTINGS:
        name = f"public server --publish {','.join(publish) or 'nothing'}"
        seen, got = over_http(publish)
        covered(name, got, MUST_ANSWER, lambda x: x == 200)
        must = [s("NOTE-GOAL"), s("FIELD-TEXT", "S"), s("NOTE-REFERENCE")]
        must += [s("SYSTEM-PROMPT"), s("PROMPT-TEXT")] if "prompts" in publish else []
        must += [s("OUTPUT", "S")] if "outputs" in publish else []
        must += [s("REFERENCE", "S")] if "references" in publish else []
        judge(name, seen, lambda k, p=publish: server_allows(k, p), must=tuple(must))

    # ── RFC-041 F4: in this process, the public env set and no public hosts ──────────────────────────────────────
    os.environ["EVH_PUBLIC"] = "1"
    try:
        cs.LIMITS["hosts"] = ()
        cs.LIMITS["publish"] = ()
        seen, got = {}, {}
        in_process(served, False, seen, got)
        judge("public env, no hosts, the reads a public MCP offers", seen, lambda k: server_allows(k, ()))
        cs.LIMITS["publish"] = ("prompts",)
        seen, got = {}, {}
        in_process(served, False, seen, got)
        judge("public env, no hosts, prompts published, the reads a public MCP offers", seen,
              lambda k: server_allows(k, ("prompts",)), must=(s("SYSTEM-PROMPT"), s("PROMPT-TEXT")))  # fmt: skip
        cs.LIMITS["publish"] = ()
        seen, got = {}, {}
        in_process([o for o in reads if o.public_dropped], False, seen, got)
        judge(
            "public env, no hosts, the reads a public MCP leaves out",
            seen,
            lambda k: server_allows(k, ()),
            f4=tuple(ALL),
        )
        seen = {}
        for t in "SH":
            note(seen, f"the inspector's item view of lk_{t.lower()}",
                 json.dumps(cs.item({"arms": [ARMS[t].split(",")[0]], "item": ["t01_login"], "ref": [f"gold/lk_{t.lower()}"]})))  # fmt: skip
        judge(
            "public env, no hosts, the inspector's item view",
            seen,
            lambda k: server_allows(k, ()),
            f4=tuple(ALL),
        )
        # a dataset whose record cannot be read is not shown on a public server
        _runstore.write_text(proj, "datasets/lk_broken.json", "{not json")
        check(
            "RFC-041 F4: public env: a dataset whose record is unreadable is hidden (`hidden` fails closed)",
            not _visibility.text_shown("lk_broken", public=True),
        )
        check(
            "RFC-041 F4: public env: a dataset with no record is hidden",
            not _visibility.text_shown("lk_nothing_here", public=True),
        )
        check(
            "public env: a dataset marked hidden is hidden", not _visibility.text_shown("lk_h", public=True)
        )
        check("public env: a shown dataset is shown", _visibility.text_shown("lk_s", public=True))
    finally:
        os.environ.pop("EVH_PUBLIC", None)

    # ── the export: the catalog's pages, with and without `catalog: {publish: [prompts]}` ────────────────────────
    cfg = proj / "config.yaml"
    plain = cfg.read_text(encoding="utf-8")
    assert "catalog:" not in plain, plain
    for prompts in (False, True):
        out = proj / f".build/leak-catalog-{int(prompts)}"
        cfg.write_text(plain + ("\ncatalog:\n  publish: [prompts]\n" if prompts else ""), encoding="utf-8")
        r = evh("catalog", "--out", str(out))
        check(
            f"setup: the catalog builds (publish prompts: {prompts})",
            r.returncode == 0,
            (r.stdout + r.stderr)[-400:],
        )
        seen = in_files(out, "catalog")
        judge(f"catalog export (publish prompts: {prompts})", seen, lambda k, p=prompts: catalog_allows(k, p),
              must=(s("NOTE-GOAL"), s("ITEM-INPUT", "S"), s("NOTE-REFERENCE"), s("NOTE-PROMPT"))
              + ((s("SYSTEM-PROMPT"), s("PROMPT-TEXT")) if prompts else ()))  # fmt: skip
    cfg.write_text(plain, encoding="utf-8")

    # ── the export: the deployment's copy of the data ────────────────────────────────────────────────────────────
    from evaluation_harness._release import copy_data

    dst = proj / ".build" / "leak-release"
    try:
        copy_data(proj / "data", dst)
        judge("deployment's copy of the data", in_files(dst, "release"), copy_allows)
    except SystemExit as exc:
        check("the deployment's copy of the data is made", False, str(exc)[:400])
finally:
    if os.environ.get("LEAK_KEEP"):
        print("PROJECT", proj)
    else:
        shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
