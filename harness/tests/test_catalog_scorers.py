#!/usr/bin/env python3
"""The Scorers pages of the catalog (RFC-032 step 8, from step 7), in the suite's store.

    python tests/test_catalog_scorers.py

In a project `evh init` makes, with judge scorers, their judged scores, a judging set with verdicts and a summary, and the
people's checks of the judges: `scorers.html` lists every scorer (a record that does not read is named, not shown) with
its mode, judges, validation and judged scores, how many of them with another version of it; a page per scorer shows its
judges, validation, checks, judging sets, summaries and the arms it judged; the menu and the arms' "judged by" and
"scored against" cells link to them; no page carries a verdict's reply; the adapter reads the scorers, and
`_texts_tracked` a dataset, from its own data directory; a deployment's copy of the data (what `render.sh` builds from)
gives the pages from what it holds. The hidden dataset's case is test_hidden_text's.
"""

from __future__ import annotations

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
sys.path.insert(0, str(Path(__file__).resolve().parent))
proj = Path(tempfile.mkdtemp(prefix="evh-catscorers-"))
os.environ["EVAL_HOME"] = str(proj)
for k in ("EVAL_DATA_DIR", "EVAL_GOALS_DIR"):
    os.environ.pop(k, None)
import _runfix  # noqa: E402
import _runstore  # noqa: E402
import yaml  # noqa: E402
from evaluation_harness import _release, _store  # noqa: E402
from evaluation_harness import catalog_build as cb  # noqa: E402
from evaluation_harness import catalog_scorers as cs  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness._codeid import content_sha256  # noqa: E402
from evaluation_harness.catalog_adapter import HarnessAdapter  # noqa: E402

env = dict(os.environ, EVH_ACTOR="person:tester", EVAL_BUILD_REF="test-catalog-scorers")
FIRST = "[{id: ja, params: {provider: fake, model: fake-a, family: vendor_a, usd_per_mtok_in: 0, usd_per_mtok_out: 0}}, "
JUDGES = (
    FIRST
    + "{id: jb, params: {provider: fake, model: fake-b, family: vendor_b, usd_per_mtok_in: 0, usd_per_mtok_out: 0}}]"
)
NEW = ("--set", "dataset_id=ds", "--set", f"judges={JUDGES}", "--set", "prompt.file=judge_prompt.txt",
       "--set", "protocol.outputs_per_call=2", "--set", "protocol.position_check_fraction=0.5",
       "--set", "protocol.noise_check_fraction=0.5")  # fmt: skip
SHA = "a" * 64
REPLY = "Verdictreplymarker"


def evh(*args: str, home: Path | None = None) -> subprocess.CompletedProcess:
    """`evh <args>` in the test project; in `home`, a deployment's copy, read as files (render.sh's build)."""
    e = {**env, "EVAL_HOME": str(home), "EVAL_STORE": "files"} if home else env
    return subprocess.run(
        [sys.executable, str(HERE / "cli.py"), *args], cwd=home or proj, env=e,
        capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600,
    )  # fmt: skip


def stored(rel: str) -> str:
    return _runstore.read_text(proj, rel) if _runstore.is_file(proj, rel) else ""


def put(rel: str, doc: object) -> None:
    _runstore.write_text(proj, rel, json.dumps(doc, indent=2) + "\n")


def judged(scorer: str, run: str, sha: str, set_id: str = "set1") -> None:
    """A run with a judged score of it, as judge-score writes one."""
    _runfix.put_run(
        proj / "data",
        {"run_id": run, "system_id": f"{run}_arm", "dataset_id": "ds", "scores": {"judge_score": 4.0},
         "derived": {"kind": "judge", "with": {"scorer_id": scorer, "scorer_sha256": sha}}},
        scorer=scorer, reference=set_id, label=f"judged/{scorer}",
    )  # fmt: skip


def sha_of(scorer: str) -> str:
    return content_sha256(yaml.safe_load(stored(f"scorers/{scorer}.yaml")))


def pages(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*.html"))}


def in_page(text: str, *needles: str) -> bool:
    return all(n in text for n in needles)


try:
    r = evh("init")
    shutil.copy(HARNESS / "tutorial" / "judge_prompt.txt", proj / "judge_prompt.txt")
    r = r if r.returncode else evh("scorer-new", "s_v1", *NEW)
    check("setup: a project and a scorer", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    judged("s_v1", "run_a", sha_of("s_v1"))
    judged("s_v1", "run_b", SHA)  # made with another version of the scorer
    put("judging-sets/set1.json", {"judging_set_id": "set1", "dataset_id": "ds", "arms": [{"config_id": "a"}, {"config_id": "b"}],
                                   "items": [{"item_id": "i1", "outputs": {"a": REPLY}}]})  # fmt: skip
    for j in ("ja", "jb"):
        _runstore.write_text(
            proj, f"judge-verdicts/s_v1/set1/{j}/i1.primary.b0.json", json.dumps({"reply": REPLY}) + "\n"
        )
    put("judge-summaries/s_v1@set1.json", {"scorer_id": "s_v1", "scorer_sha256": sha_of("s_v1"), "label": "unvalidated judge",
                                           "validated": False, "partial": False, "items_scored": 1})  # fmt: skip
    base = "judge-validation/s_v1"
    report = {"source": "Someone et al. 2022", "scorer": "s_v1", "articles": 2, "human_baseline": {},
              "inputs": {"scorer_sha256": sha_of("s_v1")},
              "judges": {j: {"billed_usd": 0.01, "unparsed": 0, "records_sha256": SHA} for j in ("ja", "jb")}}  # fmt: skip
    put(f"{base}/goyal/report.json", report)
    for j in ("ja", "jb"):
        put(f"{base}/goyal/{j}/a.json", {"article_id": "1", "output": REPLY, "judge_fp": "0" * 16})
    r = evh(
        "scorer-new",
        "s_v2",
        *NEW,
        "--set",
        "supersedes=s_v1",
        "--set",
        "why=the rubric asked for the wrong thing",
    )
    check("setup: a new version, which supersedes s_v1", r.returncode == 0, (r.stdout + r.stderr)[-300:])
    # A validated scorer: its validation runs are in the project's runs, which the catalog's reading must find.
    want = hashlib.sha256((proj / "judge_prompt.txt").read_text().strip().encode()).hexdigest()
    vj = {"provider": "litellm", "temperature": 0.0, "family": "x"}
    val_runs = []
    for j in ("ja", "jb"):
        _runfix.put_run(
            proj / "data",
            {"run_id": f"val_{j}", "system_id": f"val_{j}_arm", "dataset_id": "valds", "scores": {"tau": 0.5},
             "params": {**vj, "model": f"m-{j}", "prompt_file": "judge_prompt.txt"},
             "fingerprint": {"settings": {"declared": {"prompt_sha256": want}}}},
        )  # fmt: skip
        val_runs.append({"judge": j, "run": f"val_{j}", "value": 0.5})
    _runstore.write_text(
        proj, "scorers/s_val.yaml",
        yaml.safe_dump({
            "scorer_id": "s_val", "kind": "judge", "dataset_id": "ds", "prompt": {"file": "judge_prompt.txt", "sha256_at_16": want},
            "protocol": {"outputs_per_call": 2, "position_check_fraction": 0.5, "noise_check_fraction": 0.5},
            "judges": [{"id": j, "params": {**vj, "model": f"m-{j}", "family": fam}} for j, fam in (("ja", "vendor_a"), ("jb", "vendor_b"))],
            "validation": {"dataset_id": "valds", "metric": "tau", "what": "a check against people", "runs": val_runs},
        }),
    )  # fmt: skip
    _runstore.write_text(proj, "scorers/s_bad.yaml", "scorer_id: s_bad\nkind: [oops\n")
    r = evh("catalog")
    check(
        "setup: the catalog builds with a scorer that does not read",
        r.returncode == 0,
        (r.stdout + r.stderr)[-500:],
    )
    cat = proj / ".build" / "catalog"
    allp = pages(cat)

    # ── the list ───────────────────────────────────────────────────────────────────────────────────────────────────
    lst = allp.get("scorers.html", "")
    check(
        "scorers.html: every scorer, linked to its page; the record that does not read is named, not linked",
        in_page(lst, 'href="scorers/s_v1.html"', 'href="scorers/s_v2.html"', "<b>s_bad</b>", "does not read")
        and 'href="scorers/s_bad.html"' not in lst and "scorers/s_bad.html" not in allp,
        lst[:300] if lst else "no scorers.html",
    )  # fmt: skip
    row = next((x for x in lst.split("<tr") if "scorers/s_v1.html" in x), "")
    check(
        "the list row: mode, each judge with its model, not validated, 2 judged scores and 1 with another version",
        in_page(row, "grade", "<code>ja</code> fake-a", "<code>jb</code> fake-b", ">no<", 'data-v="2"', "1 with another version"),
        row,
    )  # fmt: skip
    check(
        "the list's tables scroll sideways on a phone (the catalog's scroll-x wrapper), and every page has the viewport",
        lst.count('class="scroll-x"') == lst.count("<table") == 1 and 'name="viewport"' in lst,
    )

    pv = allp.get("scorers/s_val.html", "")
    check(
        "a validated scorer: the list and its page say so (the validation runs are found in the adapter's data directory)",
        in_page(pv, "<dt>validated</dt><dd>yes</dd>", "a check against people") and "judge_score" not in pv
        and next(x for x in HarnessAdapter().scorers() if x["scorer"] == "s_val")["validated"] is True
        and next((x for x in lst.split("<tr") if "scorers/s_val.html" in x), "").count(">yes<") == 1,
        pv[pv.find("02") :][:500],
    )  # fmt: skip

    # ── the menu, the arms ─────────────────────────────────────────────────────────────────────────────────────────
    check(
        "the menu names Scorers on every page, the way each page reaches it",
        all(">Scorers</a>" in t and "scorers.html" in t for t in allp.values()),
        [n for n, t in allp.items() if ">Scorers</a>" not in t][:5],
    )
    arms = allp.get("arms.html", "")
    ds_page = allp.get("d/ds.html", "")
    check(
        "the arms page says judged by <scorer> and the dataset page judge <scorer>, each linked to the scorer's page",
        'judged by <a class="cell-link" href="scorers/s_v1.html">s_v1</a>' in arms
        and 'judge <a class="cell-link" href="../scorers/s_v1.html"><code class="small">s_v1</code></a>' in ds_page,
        (arms.count("judged by"), ds_page.count("judge <")),
    )  # fmt: skip

    # ── a scorer's page ────────────────────────────────────────────────────────────────────────────────────────────
    p1 = allp.get("scorers/s_v1.html", "")
    check(
        "a scorer's page: its judges with their models and vendor families, and why it is not validated",
        in_page(p1, "<code>ja</code>", "fake-a", "vendor_a", "<code>jb</code>", "fake-b", "vendor_b", "stand-in"),
        p1[:300] if p1 else "no page",
    )  # fmt: skip
    check(
        "the people's checks: a source with its citation, articles, judges, records; the report is of this version",
        in_page(p1, "<code>goyal</code>", "Someone et al. 2022", "<code>ja</code>, <code>jb</code>", 'data-v="2"'),
        p1[p1.find("the people") :][:600],
    )  # fmt: skip
    sets = p1[p1.find('id="judgingsets"') :]
    check(
        "the judging set: its dataset, arms, items, verdicts and judged scores, counted; the summary beside it, of this version",
        in_page(sets, "<code>set1</code>", 'data-v="2"', 'data-v="1"', "unvalidated judge", "this version"),
        sets[:800],
    )  # fmt: skip
    judged_arms = p1[p1.find("arms it judged") :]
    check(
        "the arms it judged, linked, with the judged score made with another version said",
        judged_arms.count('class="cell-link" href="../a/') == 2 and "1 with another version" in judged_arms and "../d/ds.html" in judged_arms,
        judged_arms[:900],
    )  # fmt: skip
    p2 = allp.get("scorers/s_v2.html", "")
    check(
        "a scorer that judged nothing: its page says so and links the scorer it supersedes",
        in_page(p2, "supersedes", 'href="../scorers/s_v1.html"', "judged by this scorer yet", "judged no judging set"),
        p2[:300] if p2 else "no page",
    )  # fmt: skip
    check(
        "no page carries a verdict's reply, a judging set's outputs or a check's record",
        not [n for n, t in allp.items() if REPLY in t] and not [p for p in cat.rglob("*") if p.is_file() and REPLY in p.read_text(errors="replace")],
        [n for n, t in allp.items() if REPLY in t],
    )  # fmt: skip

    # ── the adapter's data directory ──────────────────────────────────────────────────────────────────────────────
    other = proj / "other_data"
    other.mkdir()
    (other / "scorers").mkdir()
    (other / "datasets").mkdir()
    (other / "sources").mkdir()
    (other / "scorers" / "s_copy.yaml").write_text(
        stored("scorers/s_v1.yaml").replace("scorer_id: s_v1", "scorer_id: s_copy")
    )
    (other / "datasets" / "ds2.json").write_text(
        json.dumps({"dataset_id": "ds2", "items": [{"item_id": "a"}]})
    )
    (other / "sources" / "a").write_text("an item")
    A = HarnessAdapter(other)
    check(
        "the adapter reads the scorers of its own data directory: the copy's, not the project's",
        [s["scorer"] for s in A.scorers()] == ["s_copy"] and [s["scorer"] for s in HarnessAdapter().scorers()][:1] == ["s_bad"]
        and A.scorer("s_copy")["judged_scores"] == 0 and A.scorers() is A.scorers(),
        ([s["scorer"] for s in A.scorers()], [s["scorer"] for s in HarnessAdapter().scorers()]),
    )  # fmt: skip
    outdir = proj / "copy-pages"
    cs.render_scorers(A, {}, outdir, cb.NAV)
    check(
        "and renders its pages from it",
        (outdir / "scorers.html").is_file() and (outdir / "scorers" / "s_copy.html").is_file()
        and not (outdir / "scorers" / "s_v1.html").exists(),
        sorted(str(p.relative_to(outdir)) for p in outdir.rglob("*.html")),
    )  # fmt: skip
    git = ["git", "-C", str(proj), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "other_data"], check=True)
    subprocess.run([*git, "commit", "-qm", "the copy"], check=True)
    check(
        "_texts_tracked reads the dataset from the adapter's data directory (the project has none of that name)",
        cb._texts_tracked(A, "ds2") is True and cb._texts_tracked(HarnessAdapter(), "ds2") is False and cb._texts_tracked(A, "nope") is False,
        (cb._texts_tracked(A, "ds2"), cb._texts_tracked(HarnessAdapter(), "ds2")),
    )  # fmt: skip

    # ── a deployment's copy of the data, as render.sh builds from it ──────────────────────────────────────────────
    rel = proj / "release"
    (rel / "data").mkdir(parents=True)
    counts = _release.copy_data(proj / "data", rel / "data")
    shutil.copy(proj / "judge_prompt.txt", rel / "judge_prompt.txt")
    r = evh("catalog", "--out", str(rel / "catalog"), home=rel)
    rp = pages(rel / "catalog")
    check(
        "the catalog builds from the copy",
        r.returncode == 0 and "scorers/s_v1.html" in rp,
        (r.stdout + r.stderr)[-400:],
    )
    rp1 = rp.get("scorers/s_v1.html", "")
    check(
        "from the copy: the scorer's page has its judges, judging set and verdict count; the people's checks, which a copy does not carry, are said to be absent",
        in_page(rp1, "<code>ja</code>", "<code>set1</code>", 'data-v="2"', "a deployment's copy of the data does not carry them")
        and "goyal" not in rp1,
        rp1[rp1.find("the people") :][:500],
    )  # fmt: skip
    check(
        "nor does any page of the copy carry a reply",
        not [n for n, t in rp.items() if REPLY in t] and bool(counts),
    )
finally:
    _store.close()
    shutil.rmtree(proj, ignore_errors=True)

sys.exit(summary())
