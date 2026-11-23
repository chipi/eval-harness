#!/usr/bin/env python3
"""The catalog's one renderer, two drivers (RFC-040): the export writes what the server renders on request.

    python tests/test_catalog_render.py

In a throwaway tutorial project ($0, offline), in either store (the store matrix runs it in both):

  - coverage: the addresses the model names are the files the export writes, each owned by the group that wrote it;
  - equality: every page rendered on its own, from a fresh model, is the exported file byte for byte;
  - one page at a time: asking for one page renders its group only, not the site;
  - threads: pages rendered concurrently from one model are the exported files (no global read half-filled);
  - the footer's time is the model's, not the clock's, so the two drivers agree.

The same checks on this repository's own runs (a goal page per goal, redirects, a dataset's item pages) are in
tests/test_catalog_render_real.py.
"""

import os
import random
import shutil
import sys
import tempfile
import threading
from pathlib import Path

proj = Path(tempfile.mkdtemp(prefix="evh-render-"))
env = dict(os.environ, EVH_ACTOR="person:test", EVAL_HOME=str(proj), EVAL_BUILD_REF="test-render")
for k in ("EVAL_DATA_DIR", "EVAL_MAX_COST_USD", "EVAL_GOALS_DIR"):
    env.pop(k, None)
    os.environ.pop(k, None)
os.environ.update(env)

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/
import _cli  # noqa: E402
import _runstore  # noqa: E402
from evaluation_harness import catalog_build as cb  # noqa: E402
from evaluation_harness._check import check, store_under_test, summary  # noqa: E402
from evaluation_harness.catalog_adapter import load_catalog_adapter  # noqa: E402

KIT = HARNESS / "tutorial"
GOAL = "tickets_summary"
SETS = [
    "title=Ticket summaries", "statement=A one-line summary of a support ticket for the person triaging it.",
    "decision=Which system writes the summary.", "success_criteria.primary.measure=overlap_f1",
    "success_criteria.primary.direction=higher", "datasets.0.dataset_id=tk_v1", "datasets.0.role=test",
]  # fmt: skip
BUILT = "2026-11-23 12:00 UTC"


def evh(*args):
    return _cli.run(proj, env, *args)


def files_under(out: Path) -> dict[str, str]:
    """{relative path: text} of every page the export wrote, the assets left out (they are copied, not rendered)."""
    return {
        p.relative_to(out).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.relative_to(out).parts[0] != "assets"
    }


try:
    r = evh("init", "--store", store_under_test(), "--tutorial")
    shutil.copytree(KIT / "tickets", proj / "tickets")
    for step in (
        ("dataset-create", "--dataset-id", "tk_v1", "--source-dir", "tickets"),
        ("dataset-materialize", "--dataset-id", "tk_v1"),
        ("label-import", "--sheet", str(KIT / "gold"), "--dataset-id", "tk_v1", "--set", "g", "--by", "t"),
        ("reference-promote", "--dataset-id", "tk_v1", "--labels", "g", "--tier", "gold", "--reason", "the kit's summaries, for the render test", "--by", "t"),
    ):  # fmt: skip
        r = r if r.returncode else evh(*step)
    for cid, n in (("one_v1", 1), ("two_v1", 2)):
        _runstore.write_text(
            proj, f"systems/{cid}.yaml", f"system_id: {cid}\nparams:\n  provider: echo\n  sentences: {n}\n"
        )
    for cid in ("one_v1", "two_v1"):
        r = r if r.returncode else evh("run", "--system", cid, "--dataset", "tk_v1")
    r = r if r.returncode else evh("goal-new", GOAL, *(x for s in SETS for x in ("--set", s)))
    check("setup: a project with a goal and two runs", r.returncode == 0, (r.stdout + r.stderr)[-400:])

    out = proj / ".build" / "render-export"
    A = load_catalog_adapter(None)
    site = cb.prepare(A, built=BUILT)
    wrote = site.export(out)
    exported = files_under(out)

    # ── coverage ────────────────────────────────────────────────────────────────────────────────────────────────────
    pages = {p: g for p, g in site.addresses.items() if not p.startswith("assets/")}
    check(
        "coverage: the export wrote exactly the addresses the model names",
        set(exported) == set(pages),
        (sorted(set(exported) - set(pages))[:5], sorted(set(pages) - set(exported))[:5]),
    )
    check(
        "coverage: each address is owned by the group that wrote it",
        wrote == pages,
        sorted(
            (p, wrote.get(p), pages.get(p)) for p in set(wrote) | set(pages) if wrote.get(p) != pages.get(p)
        )[:5],
    )
    check(
        "coverage: the site has a home, a goal page, a dataset page and an arm page",
        {"index.html", cb.goal_page(GOAL), cb.dataset_page("tk_v1")} <= set(pages)
        and any(p.startswith("a/") for p in pages),
        sorted(pages)[:20],
    )
    check(
        "coverage: the assets are served from the model's addresses too",
        {f"assets/{a}" for a in cb.ASSETS} | {"assets/head.js"} <= set(site.addresses),
        sorted(p for p in site.addresses if p.startswith("assets/")),
    )
    check(
        "the footer carries the model's time, not the clock's",
        f"Built {BUILT}" in exported["index.html"],
        exported["index.html"][-600:],
    )

    # ── equality, one page at a time, from a fresh model ────────────────────────────────────────────────────────────
    fresh = cb.prepare(load_catalog_adapter(None), built=BUILT)
    rendered: list[str] = []
    real_render = fresh.render

    def counting(group: str, keep: bool = True) -> dict[str, str]:
        rendered.append(group)
        return real_render(group, keep)

    fresh.render = counting  # type: ignore[method-assign]
    goal_html = fresh.page(cb.goal_page(GOAL))
    check(
        "one page at a time: the goal page renders its own group and nothing else",
        rendered == [pages[cb.goal_page(GOAL)]],
        rendered,
    )
    check("the goal page rendered on request is the exported file", goal_html == exported[cb.goal_page(GOAL)])
    again = fresh.page(cb.goal_page(GOAL))
    check("asked again, it is kept, not rendered again", again == goal_html and len(rendered) == 1, rendered)
    differ = [p for p in sorted(pages) if fresh.page(p) != exported[p]]
    check(
        f"equality: every page ({len(pages)}) rendered on request is the exported file, byte for byte",
        not differ,
        differ[:5],
    )
    check("an address the model does not name is no page", fresh.page("a/no-such-arm.html") is None)
    check(
        "an asset is served as the export copies it",
        fresh.page("assets/head.js") == (out / "assets" / "head.js").read_text(encoding="utf-8"),
    )

    # ── threads ─────────────────────────────────────────────────────────────────────────────────────────────────────
    shared = cb.prepare(load_catalog_adapter(None), built=BUILT)
    order = sorted(pages) * 3
    random.Random(7).shuffle(order)
    wrong: list[str] = []
    errors: list[str] = []

    def worker(paths: list[str]) -> None:
        for p in paths:
            try:
                if shared.page(p) != exported[p]:
                    wrong.append(p)
            except Exception as exc:  # noqa: BLE001 - reported by the check below
                errors.append(f"{p}: {exc!r}")

    threads = [threading.Thread(target=worker, args=(order[i::8],)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=600)
    check(
        "threads: eight threads asking for every page three times get the exported files, and no error",
        not wrong and not errors and not any(t.is_alive() for t in threads),
        (sorted(set(wrong))[:5], errors[:3]),
    )
finally:
    shutil.rmtree(proj, ignore_errors=True)
sys.exit(summary())
