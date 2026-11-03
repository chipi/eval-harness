#!/usr/bin/env python3
"""The catalog of this repository's own runs in a real browser: hundreds of arms, not a tutorial's
three. test_inspector_browser.py proves each control on a small project; this proves the pages hold
at the size the deployment serves.

    python tests/test_catalog_real_browser.py --catalog .build/budget-catalog
    make browser-real-check            (builds the catalog first when it is missing)

With the inspector on a free port, over a built catalog:

  - every page a reader reaches from the menu, and a goal, a dataset, an arm and a metric page,
    loads with no console error and no sideways scroll at phone width;
  - the arms page lists as many arms as it says, groups them into as many configs as it says,
    and its open-weights, proprietary and ties-the-leader filters each keep some arms and only
    arms of that kind;
  - the datasets page groups by goal (one heading per goal at least) and the metrics page by role
    (decides, weighs, describes);
  - the activity page lists what moved most against the period before first;
  - "what changed" on the arms page is shorter than one line per arm (a day's rescores are one);
  - the inspector answers the largest comparison the catalog links to, and every arm in it is
    compared or named in a note saying why not (no score on the metric, scored against another
    reference, a repeat).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness._check import check, summary  # noqa: E402

PAGES = (
    "index.html",
    "goals.html",
    "datasets.html",
    "references.html",
    "metrics.html",
    "arms.html",
    "activity.html",
)


def serve(cat: Path, log: Path) -> tuple:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with open(log, "w", encoding="utf-8") as fh:
        p = subprocess.Popen(
            [
                sys.executable,
                str(HARNESS / "scripts" / "catalog_serve.py"),
                "--port",
                str(port),
                "--build-dir",
                str(cat),
            ],
            cwd=HARNESS,
            stdout=fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    for _ in range(300):
        if "catalog:" in log.read_text():
            break
        if p.poll() is not None:
            raise SystemExit(f"catalog-serve exited:\n{log.read_text()}")
        time.sleep(0.1)
    return p, f"http://127.0.0.1:{port}/{cat.resolve().relative_to(HARNESS).as_posix()}/"


def visible_rows(page, tid: str) -> int:
    return page.evaluate(
        f"""[...document.querySelectorAll('table#{tid} tbody tr')].filter(r=>!r.classList.contains('grouphead')
        &&!r.hidden&&!r.classList.contains('fout')&&!r.classList.contains('pout')).length"""
    )


def drive(cat: Path, base: str) -> None:
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    sub = [
        next(iter(sorted((cat / "g").glob("*.html")))).relative_to(cat).as_posix(),
        next(iter(sorted((cat / "d").glob("*.html")))).relative_to(cat).as_posix(),
        next(iter(sorted((cat / "a").glob("*.html")))).relative_to(cat).as_posix(),
        next(iter(sorted((cat / "m").glob("*.html")))).relative_to(cat).as_posix(),
    ]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        errors: list = []
        phone = browser.new_page(viewport={"width": 390, "height": 844})
        phone.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        phone.on("pageerror", lambda e: errors.append(str(e)))
        for path in (*PAGES, *sub):
            phone.goto(base + path)
            phone.wait_for_selector("main", timeout=30000)
            wide = phone.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(f"phone width: no sideways scroll on {path}", wide <= 1, f"{wide}px too wide")

        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # The label tables at desktop width: long set ids wrap, so the columns that say something (promoted, the
        # agreement counts) are on screen, not behind a sideways scroll.
        labelled = [p.relative_to(cat).as_posix() for p in sorted((cat / "d").glob("*.html"))]
        labelled = [p for p in labelled if 'id="agree-' in (cat / p).read_text(encoding="utf-8")][:3]
        for path in ("labels.html", *labelled):
            page.goto(base + path)
            page.wait_for_selector("main", timeout=30000)
            over = page.evaluate(
                """[...document.querySelectorAll('table#labelsets, table[id^="agree-"], table[id^="labels-"]')]
                .map(t => [t.id, t.scrollWidth - t.closest('.scroll-x').clientWidth]).filter(x => x[1] > 1)"""
            )
            check(
                f"desktop width: the label tables on {path} fit, nothing behind a sideways scroll",
                not over,
                str(over),
            )

        # The arms page at full size: all time, every row shown.
        page.goto(base + "arms.html#pall")
        page.wait_for_selector("table#arms")
        hero = page.locator(".hero").first.inner_text()
        m = re.search(r"(\d+) arms from (\d+) configs", hero)
        n_arms, n_cfg = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        check(
            f"arms page: the table lists the {n_arms} arms it says",
            n_arms > 100 and page.locator("table#arms tbody tr").count() == n_arms,
            f"hero {hero[:80]!r}, rows {page.locator('table#arms tbody tr').count()}",
        )
        page.click('.group-chips[data-for="arms"] [data-group-by="config"]')
        heads = page.locator("table#arms tr.grouphead").count()
        check(
            f"arms page: grouped by config, one heading per config ({n_cfg})",
            heads == n_cfg,
            f"{heads} headings",
        )
        page.click('.group-chips[data-for="arms"] [data-group-by=""]')
        for facet, value, attr in (
            ("weights", "open", "weights"),
            ("weights", "proprietary", "weights"),
            ("quality", "a contender", "quality"),
        ):
            chip = page.locator(f'.facet-chips[data-for="arms"] [data-facet="{facet}"][data-value="{value}"]')
            chip.click()
            kept = page.evaluate(
                """([a])=>[...document.querySelectorAll('table#arms tbody tr')].filter(r=>!r.classList.contains('grouphead')
                &&!r.classList.contains('fout')).map(r=>r.dataset[a])""",
                [attr],
            )
            check(
                f"arms page: the {value} filter keeps some arms, all of them {value}",
                bool(kept) and len(kept) < n_arms and all(k == value for k in kept),
                f"{len(kept)} kept, {sorted(set(kept))}",
            )
            chip.click()
        feed = page.locator("table#armfeed tbody tr").count()
        check(
            f"arms page: what changed is shorter than one line per arm ({feed} lines, {n_arms} arms)",
            0 < feed < n_arms,
        )

        page.goto(base + "datasets.html#pall")
        page.click('.group-chips[data-for="datasets"] [data-group-by="goal"]')
        n_goals = len(list((cat / "g").glob("*.html")))
        goal_heads = page.locator("table#datasets tr.grouphead").all_inner_texts()
        check(
            f"datasets page: grouped by goal, a heading for each of the {n_goals} goals",
            len(goal_heads) >= n_goals,
            " | ".join(goal_heads),
        )
        page.goto(base + "metrics.html#pall")
        page.click('.group-chips[data-for="metrics"] [data-group-by="role"]')
        roles = {t.split()[1] for t in page.locator("table#metrics tr.grouphead").all_inner_texts()}
        check(
            "metrics page: grouped by role, decides and describes among them",
            {"decides", "describes"} <= roles <= {"decides", "weighs", "describes"},
            str(roles),
        )

        page.goto(base + "activity.html#p90d")
        page.wait_for_selector("table#actarms")
        moved = page.evaluate(
            """[...document.querySelectorAll('table#actarms tbody tr [data-flow="runs"]')].slice(0,10)
            .map(c=>c.dataset.prev===undefined?null:Math.abs(+c.dataset.v-(+c.dataset.prev)))"""
        )
        nums = [x for x in moved if x is not None]
        check(
            "activity page: what moved most against the period before comes first",
            len(nums) >= 2 and nums == sorted(nums, reverse=True),
            str(moved),
        )

        links = set()
        for f in cat.rglob("*.html"):
            for href in re.findall(r'href="(?:\.\./)*inspect\.html\?([^"]+)"', f.read_text(encoding="utf-8")):
                links.add(href.replace("&amp;", "&"))
        # The largest comparison, the same one every run (several tie on size).
        largest = max(sorted(links), key=lambda q: q.count(","), default="")
        page.goto(base + "inspect.html?" + largest)
        page.wait_for_selector("span.chip.v-better, span.chip.v-worse, span.chip.v-none", timeout=120000)
        page.wait_for_load_state("networkidle")
        ids = [r.rsplit("/", 1)[-1] for r in largest.split("runs=", 1)[-1].split("&", 1)[0].split(",")]
        text = page.locator("main").inner_text()
        unnamed = [i for i in ids if i not in text]
        rows = page.locator("table.data").first.locator("tbody tr").count()
        check(
            f"inspector: the largest comparison the catalog links to ({len(ids)} arms) answers; every arm is "
            f"compared ({rows} verdict rows) or named in a note saying why not",
            rows > 0 and not unnamed,
            f"not named: {unnamed[:5]}",
        )
        # Every config on the arms page has the day it was first run, as the home page's configs tile counts them:
        # an undated row (a config whose runs were all re-parsed) never counts as new there.
        ct = (cat / "arms.html").read_text(encoding="utf-8")
        ct = ct[ct.index('<table id="configs"') :]
        ct = ct[: ct.index("</table>")]
        undated = re.findall(r'<tr data-key="(c:[^"]+)"(?![^>]*data-made)', ct)
        check(
            "arms page: every config row is dated (its first run, any kind)",
            not undated,
            ", ".join(undated[:5]),
        )

        # Runs re-scored or re-parsed in place (Few-NERD's, SciFact's) are the runs that were measured: their runs and
        # spend count in every period figure, dated when they were measured, once each. A copy (judged, re-scored,
        # silver, adjudicated) keeps the run's id too and is never counted: counting them tripled the spend.
        rows_js = (cat / "datasets-rows.js").read_text(encoding="utf-8")
        per = json.loads(rows_js[rows_js.index("{") : rows_js.rindex("}") + 1])
        counted = {
            d: (
                len(per.get(d, {}).get("runs") or []),
                round(sum(x[1] for x in per.get(d, {}).get("usd") or []), 2),
            )
            for d in ("few_nerd_280", "scifact_200", "ag_news_200")
        }
        check(
            "datasets: runs re-scored in place count once in the period figures, copies never (the run records' "
            "28 runs $2.61, 26 runs $2.97, 33 runs $0.58)",
            counted == {"few_nerd_280": (28, 2.61), "scifact_200": (26, 2.97), "ag_news_200": (33, 0.58)},
            str(counted),
        )

        # One recommendation per goal and dataset, from the goal's own measure (judged groups are shown, never
        # recommend), and a round's best read as the goal decides: on gold, never the arm that wrote silver.
        cnn = (cat / "g" / "news_summary_cnn.html").read_text(encoding="utf-8")
        recs = sorted(set(re.findall(r"Recommended: <b><a [^>]*>([^<]+)</a>", cnn)))
        best = re.findall(r"best</small> <a class=\"cell-link\"[^>]*>([a-z0-9_]+)</a>", cnn)
        check(
            "CNN goal page: one recommendation (gold's), and round r1's best is gold's leader, not silver's author",
            recs == ["cnn_bart_l_n200_v1"] and best[:1] == ["cnn_bart_l_n200_v1"],
            f"recommended {recs}; best {best[:3]}",
        )

        # The triage goal page names its scorer once, not after each of 80 arms, gives its 51 contenders as a count
        # (the same list again as "still undecided" was a screen at phone width), and prints the r3 conclusion once.
        page.goto(base + "g/triage_orrery.html")
        seen = page.locator("main").inner_text()
        concl = "Onboarding was the fix round 1 needed"
        check(
            "triage goal page: the scorer named once, the contenders counted, round r3's conclusion shown once",
            "rescored 5f2c057c" not in seen
            and "re-score by scorer 5f2c057c" in seen
            and "Still undecided after the tie-break: all " in seen
            and seen.count(concl) == 1,
            f"per-arm hashes {seen.count('rescored 5f2c057c')}, conclusion shown {seen.count(concl)}×",
        )

        # A dataset page opens on the measure its goal decides on, and never inspects two judges' scores as one.
        firsts = {}
        for d in ("orrery_triage_v1_labelled", "summeval_100"):
            dp = (cat / "d" / f"{d}.html").read_text(encoding="utf-8")
            firsts[d] = (
                re.search(r'href="\.\./m/([a-z_0-9]+)\.html"', dp[dp.index("<tbody") :]) or [None, ""]
            )[1]
        cnn_d = (cat / "d" / "cnn_dailymail_200.html").read_text(encoding="utf-8")
        check(
            "dataset pages: the deciding measure's arms first; one inspect button per judging pass",
            firsts == {"orrery_triage_v1_labelled": "triage_cost", "summeval_100": "tau"}
            and "Inspect the 58 arms" not in cnn_d
            and "judged by judge-summ-v1" in cnn_d
            and "judged by judge-summ-v2" in cnn_d,
            f"first rows {firsts}",
        )

        # Where an arm's time went, in one form on every dataset page: "served on <machine>" or "run on ...".
        odd = sorted(
            {
                m
                for f in (cat / "d").glob("*.html")
                for m in re.findall(
                    r"<br><small>((?:on|run on|served on) [^<]+)</small>", f.read_text(encoding="utf-8")
                )
                if m.startswith("on ")
            }
        )
        check("dataset pages: the machine in one form (served on / run on)", not odd, ", ".join(odd[:5]))

        # A config's place in a goal's field is counted as the site counts it: one place per config, no arm a round
        # retired (a re-timing on Linux, a paired side run).
        def place(cfg: str) -> str:
            row = ct[ct.index(f'data-key="c:{cfg}"') :]
            return ",".join(re.findall(r"#(\d+ of \d+)", row[: row.index("</tr>")])) or "none"

        places = {
            c: place(c)
            for c in ("ag_anthropic_l_n200_v1", "se_openai_l_n100_v1", "se_gemma_l_pubtext_n100_v1")
        }
        check(
            "arms page: AG News anthropic_l is 5th of 30 and SummEval openai_l 1st of 33, as on the site; a paired "
            "side run has no place",
            places
            == {
                "ag_anthropic_l_n200_v1": "5 of 30",
                "se_openai_l_n100_v1": "1 of 33",
                "se_gemma_l_pubtext_n100_v1": "none",
            },
            str(places),
        )

        # A reference set is never younger than the first run scored against its bytes: the 0.4.0 migration dated
        # every gold set by the migration, so the references page listed sets a month old as new. A run that recorded
        # other bytes of a set whose texts are committed was scored against an earlier version of it (a set promoted
        # again under its id), which dates that version, not this one.
        from evaluation_harness._fingerprint import references_digest  # noqa: PLC0415
        from evaluation_harness.catalog_adapter import HarnessAdapter  # noqa: PLC0415

        A = HarnessAdapter()
        A.arms()
        now_sha: dict = {}
        first: dict = {}
        for _ds, _d, rec, _arm in A._every:
            data = (rec.get("fingerprint") or {}).get("data") or {}
            ref, made = data.get("reference_id"), rec.get("created_at")
            if not ref or not made:
                continue
            if ref not in now_sha:
                committed = any((HARNESS / "data" / "references" / ref).glob("*.txt"))
                now_sha[ref] = references_digest(HARNESS, ref, HARNESS / "data") if committed else None
            if now_sha[ref] and data.get("references_sha256") not in (None, now_sha[ref]):
                continue
            first[ref] = min(first.get(ref, "~"), made)
        young = [
            f"{r['id']} {r['created_at'][:10]} > {first[r['id']][:10]}"
            for r in A.references()
            if r["id"] in first and (r.get("created_at") or "") > first[r["id"]]
        ]
        check(
            "references: each dated no later than the first run scored against it",
            not young,
            "; ".join(young[:4]),
        )

        # A goal page's rounds count their arms as `evh rounds` does: a re-scored run is the same arm.
        differ = []
        for gp in sorted((cat / "g").glob("*.html")):
            shown = dict(
                re.findall(r"<b>(r\d+)</b>.*?<span data-v=\"(\d+)\">\d+ arms</span>", gp.read_text(), re.S)
            )
            if not shown:
                continue
            cli = subprocess.run(
                [sys.executable, str(HARNESS / "scripts" / "cli.py"), "rounds", "--goal", gp.stem],
                cwd=HARNESS,
                capture_output=True,
                text=True,
            ).stdout
            said = dict(re.findall(r"^\s+(r\d+)\s+\S+\s+\S+\s+(\d+) arm\(s\)", cli, re.M))
            differ += [
                f"{gp.stem} {rid}: page {n}, evh rounds {said.get(rid)}"
                for rid, n in shown.items()
                if said.get(rid) != n
            ]
        check(
            "goal pages: each round's arms counted as evh rounds counts them",
            not differ,
            "; ".join(differ[:4]),
        )

        # The sheet of a judging pass's arms, as a dataset page names them (runs-judged/<scorer>/<dataset>/<config>).
        judged = sorted(q for q in links if "runs=runs-judged/" in q)
        if judged:
            q = max(judged, key=lambda x: x.count(","))
            ds = q.split("runs=runs-judged/", 1)[1].split("/")[1]
            arms = q.split("runs=", 1)[1].split("&", 1)[0].split(",")[:3]
            page.goto(f"{base}inspect.html?dataset={ds}&sheet=1&runs={','.join(arms)}")
            page.wait_for_selector("#sheettable, .callout, p.err", timeout=60000)
            over = page.evaluate(
                """[...document.querySelectorAll('#sheettable thead th')]
                .filter(h => h.scrollWidth > h.clientWidth + 1).map(h => h.innerText.slice(0, 60))"""
            )
            check(
                f"sheet: a judging pass's arms as the dataset page names them ({len(arms)} on {ds}) open, and no "
                "column header runs over the next",
                page.locator("#sheettable").count() == 1 and not over,
                f"headers over their cells: {over[:3]}" if over else page.locator("main").inner_text()[-300:],
            )
        check("no console errors", not errors, " | ".join(errors[:5]))
        browser.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--catalog", type=Path, default=HARNESS / ".build" / "budget-catalog")
    args = ap.parse_args()
    try:
        import playwright  # noqa: F401, PLC0415
    except ImportError:
        print("  FAIL Playwright is not installed: `make browser-install` (requirements-browser.txt)")
        return 1
    cat = args.catalog.resolve()
    if not (cat / "index.html").is_file():
        print(f"  FAIL no catalog at {cat}: `make browser-real-check` builds one")
        return 1
    log = HARNESS / ".build" / "real-browser-serve.log"
    server, base = serve(cat, log)
    try:
        drive(cat, base)
    finally:
        os.killpg(server.pid, signal.SIGTERM)
        server.wait(timeout=10)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
