#!/usr/bin/env python3
"""Build the catalog: static pages over a project's runs, plus the run inspector's shell.

    evh catalog [--out .build/catalog] [--adapter path/to/file.py:Class]
    make catalog

Pages: the catalog's home (every dataset, with its arms and references), one page per dataset
(every arm on it, with its headline number, and an "inspect" link per arm and for all of
them), and the inspector shell, which `evh catalog-serve` fills from the adapter.

The output embeds counts and means only, never an item's text (but what the repository already
publishes: a profile written --with-text, refused unless git has committed every item's file):
outputs and references leave the data tree only through the inspector server (ADR-0002). The page shell (`page`,
`hero`, `block`, `table`) and the assets are the parts a project's own builder reuses.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent
if __name__ == "__main__":
    # Run as a command (evh catalog runs this file as __main__), this module IS
    # evaluation_harness.catalog_build: the renderers that import it by name (catalog_arms) must
    # see the options main() sets (--brand, --link, --head, --api, --about), not a second copy
    # with the defaults. arms.html was built by such a copy, as "eval catalog" with no switcher.
    _sys.modules["evaluation_harness.catalog_build"] = _sys.modules[__name__]
    if "evaluation_harness" in _sys.modules:  # imported already: its attribute names this module too
        vars(_sys.modules["evaluation_harness"])["catalog_build"] = _sys.modules[__name__]

import argparse
import html
import json
import re
import shutil
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent

from evaluation_harness import _common, _fields  # noqa: E402
from evaluation_harness._common import ROOT  # noqa: E402
from evaluation_harness.axes import (  # noqa: E402
    STRATEGIES,
    axes_of,
    axis_title,
    builtin_axes,
    cell_of,
    cell_text,
    strategy_of,
    tie_break_of,
)
from evaluation_harness.catalog_adapter import Adapter, item_fields, load_catalog_adapter  # noqa: E402
from evaluation_harness.stats import fmt_p  # noqa: E402

#: The front-end files every page loads: installed beside the package, or in a checkout.
ASSET_DIR = next(p for p in (HERE / "catalog_assets", HERE.parent / "catalog_assets") if p.is_dir())
# forest.js draws a baseline's answers chart; no page of the harness's own uses it, a project's
# builder does (podcast_scraper's baseline pages), so it ships with the assets.
ASSETS = (
    "style.css",
    "catalog.css",
    "catalog.js",
    "inspect.js",
    "forest.js",
    "period.js",
    "overview.js",
    "arms.js",
    "group.js",
    "icon.svg",
)
#: Links that would put more arms than this in one inspector URL go to the picker instead.
INSPECT_MAX = 40

#: The theme is applied before first paint by assets/head.js, a file rather than an inline
#: script, so the pages need no 'unsafe-inline' in a Content-Security-Policy.
HEAD_JS_SRC = """(function(){var t;try{t=localStorage.getItem('theme');}catch(e){}
if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;
document.documentElement.classList.add('js');})();
"""

# The bar's icons, drawn the same as on the eval-harness site and its docs: a glyph like ☰ or ◐
# renders differently per font.
_SVG = (
    '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round">'
)
ICON = {
    "menu": _SVG + '<path d="M4 7h16M4 12h16M4 17h16"/></svg>',
    "search": _SVG + '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/></svg>',
    "theme": _SVG
    + '<circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor"/></svg>',
}

#: The catalog's menu, by the home tiles' subjects. An entry is (key, page, label), or a group
#: (key, [entries], label) that opens a short list; on a phone the ☰ menu lists every page.
NAV = [
    ("home", "index.html", "Overview"),
    ("goals", "goals.html", "Goals"),
    (
        "data",
        [("datasets", "datasets.html", "Datasets"), ("references", "references.html", "References")],
        "Data",
    ),
    (
        "experiments",
        [
            ("arms", "arms.html", "Arms"),
            ("configs", "arms.html#configs", "Configs"),
            ("metrics", "metrics.html", "Metrics"),
        ],
        "Experiments",
    ),
    ("activity", "activity.html", "Activity"),
    ("inspect", "inspect.html", "Inspector"),
]

#: What the harness's own metrics measure; a project describes its own with METRIC_DESCRIPTIONS.
BUILTIN_METRICS = {
    "cost_usd": "What one item cost, in USD: the provider's bill when the response carries one, "
    "else the tokens times the config's prices.",
    "total_cost_usd": "What the whole run cost, in USD: the sum of cost_usd.",
    "tokens_in": "Prompt tokens per item, as the provider counted them.",
    "tokens_out": "Completion tokens per item, as the provider counted them.",
    "total_tokens_in": "Prompt tokens over the whole run.",
    "total_tokens_out": "Completion tokens over the whole run.",
    "latency_ms": "Wall-clock time of one call, in milliseconds.",
    "latency_s": "Wall-clock time of one call, in seconds.",
    "judge_score": "The judges' mean score for the output on the scorer's scale, over its "
    "dimensions and judges (evh judge-score). The judges were validated against human ratings.",
    "judge_score_unvalidated": "The judges' mean score for the output on the scorer's scale, over "
    "its dimensions and judges (evh judge-score). The judges were not validated against human "
    "ratings: a trial, not a measurement.",
    "overlap_f1": "Token-overlap F1 against the reference: the bundled adapter's placeholder, "
    "enough to run the loop, not to defend a decision.",
    "output_words": "How many words the output has: a description of the output, not a quality.",
    "resumed": "1 when the item was replayed from a stopped run's stored output (--resume), "
    "else 0: bookkeeping, not a score.",
    "reasoning_tokens": "Tokens a reasoning model spent thinking before it answered, as the provider "
    "reported them: a description of the call, not a quality.",
}

#: How the harness's own metrics are computed and read: each metric page's longer text. A
#: project gives its own with METRIC_DESCRIPTIONS = {"metric": {"summary": ..., "details": ...}}.
BUILTIN_DETAILS = {
    "cost_usd": "Recorded for every item. When the provider's response carries what it billed "
    "(OpenRouter always, a LiteLLM proxy that passes usage.cost through, any OpenAI-compatible "
    "endpoint that returns it), that bill is the cost. Otherwise it is tokens_in × usd_per_mtok_in "
    "plus tokens_out × usd_per_mtok_out from the arm's config, per million tokens. With neither the "
    "cost is unknown and left empty, never 0. Lower is better, and it needs no reference, so arms "
    "scored against different references can still be compared on it. evh cost-report shows how "
    "far the bills and the price tables differ.",
    "total_cost_usd": "The run's cost: the sum of cost_usd over its items, not a mean. An arm's "
    "repeats are separate runs, each with its own total.",
    "tokens_in": "Counted by the provider, not the harness: an adapter that reports none leaves it "
    "empty. Together with the config's prices it is the fallback cost when no bill comes back.",
    "tokens_out": "Counted by the provider, not the harness. Most providers bill a reasoning "
    "model's thinking as completion tokens; reasoning_tokens says how many of them it was.",
    "latency_ms": "The wall-clock time of one call. When an adapter reports none, the core times "
    "the call itself; a model's first call, which loads it (the warm-up), is excluded. It depends "
    "on the machine, the provider's load and the network: compare it between arms measured under "
    "the same conditions, which the inspector's conditions line checks. Lower is better, and it "
    "needs no reference.",
    "judge_score": "evh judge-score shows each item and the outputs of several arms to two or more "
    "judges from different vendor families, blinded and in a seeded order, in blocks. Each judge "
    "scores every output on each of the scorer's dimensions; an arm's judge_score for an item is "
    "the mean over the dimensions and the judges. The scorer's validation names the committed runs "
    "and the agreement with people they reached; the pass also re-asks a fraction of items in "
    "another order (position) and again (noise), and reports how much the scores moved.",
    "judge_score_unvalidated": "Computed as judge_score is, by judges that were never compared "
    "with human ratings for this use. It ranks arms by what the judges prefer, which may not be "
    "what people prefer: read it as a trial. A validated scorer turns it into judge_score.",
    "overlap_f1": "The bundled adapter's score: the output and the reference as sets of lowercased "
    "words, precision is the share of the output's words in the reference, recall the share of the "
    "reference's words in the output, and F1 their harmonic mean. Word order, synonyms and "
    "repetition do not count. Replace score() with what your task rewards.",
    "output_words": "The number of whitespace-separated words in the output. It says how long the "
    "output was, never whether it was good: ranking by it rewards verbosity, and the leaderboard "
    "says so when a table is sorted by it.",
    "reasoning_tokens": "Read from the provider's usage (completion_tokens_details.reasoning_tokens "
    "or its equivalent). Empty when the provider does not report it, never 0. Billed with the "
    "completion tokens, so cost_usd already includes it.",
    "resumed": "A run stopped by a cost cap or a crash prints its --resume command; the resumed "
    "run replays the items already done from their stored outputs instead of paying for them "
    "again. The mean of resumed is the share of the run that was replayed.",
}


def _summary(value) -> str:
    """A METRIC_DESCRIPTIONS value's one-line summary: the string, or its "summary"."""
    return value.get("summary", "") if isinstance(value, dict) else str(value or "")


def metric_details(metric: str, project: dict) -> str:
    """How a metric is computed and read, for its page: the project's details, else the harness's."""
    own = project.get(metric)
    if isinstance(own, dict) and own.get("details"):
        return own["details"]
    return BUILTIN_DETAILS.get(metric, "")


def describe_metric(metric: str, project: dict) -> str:
    """What a metric measures: the project's own words, else the harness's, else ""."""
    if _summary(project.get(metric)):
        return _summary(project[metric])
    if metric in BUILTIN_METRICS:
        return BUILTIN_METRICS[metric]
    m = re.fullmatch(r"judge_(.+?)(_unvalidated)?", metric)
    if m and not metric.startswith("judge_score"):
        return f"Judge {m.group(1)}'s mean score for the output, on the scorer's scale" + (
            ", not validated against human ratings." if m.group(2) else "."
        )
    m = re.fullmatch(r"self_family_(.+)", metric)
    if m:
        return (
            f"1 when judge {m.group(1)} is from the arm's own vendor family, else 0: context for its score."
        )
    return ""


def metric_page(metric: str) -> str:
    """The metric's page, relative to the catalog root."""
    return f"m/{slug(metric)}.html"


def metric_link(metric: str, up: str = "") -> str:
    """A metric's name, linked to its page."""
    if not metric:
        return "—"
    return f'<a class="cell-link" href="{up}{metric_page(metric)}">{e(metric)}</a>'


def reference_page(ref: str) -> str:
    """The reference's page, relative to the catalog root."""
    return f"r/{slug(ref)}.html"


def reference_link(ref: str, up: str = "") -> str:
    """A reference's id, linked to its page."""
    return f'<a class="cell-link" href="{up}{reference_page(ref)}">{e(ref)}</a>' if ref else "—"


def arm_page(arm: str) -> str:
    """The arm's page, relative to the catalog root: one per arm id (runs dir, dataset, config)."""
    return f"a/{slug(arm)}.html"


def _label_of(by_ds: dict, ds: str, arm: str) -> str:
    """An arm's label on its dataset, or its id when the catalog does not list it."""
    return next((a["label"] for a in (by_ds.get(ds) or {}).get("arms", []) if a["arm"] == arm), arm)


def arm_link(arm: str, label: str, up: str = "") -> str:
    """An arm's label, linked to its page."""
    return f'<a class="cell-link" href="{up}{arm_page(arm)}">{e(label)}</a>'


def dataset_page(ds: str) -> str:
    """The dataset's page, relative to the catalog root."""
    return f"d/{slug(ds or 'none')}.html"


def dataset_link(ds: str, up: str = "") -> str:
    """A dataset's id, linked to its page."""
    return f'<a class="cell-link" href="{up}{dataset_page(ds)}">{e(ds or "(no dataset_id)")}</a>'


def goal_page(goal_id: str) -> str:
    """The goal's page, relative to the catalog root."""
    return f"g/{slug(goal_id)}.html"


def goal_link(g: dict, up: str = "") -> str:
    """A goal's title, linked to its page."""
    return (
        f'<a class="cell-link" href="{up}{goal_page(g["goal_id"])}">{e(g.get("title") or g["goal_id"])}</a>'
    )


def row_kind(a: dict, tiers: dict) -> str:
    """The class of an arm's row: what its scores are measured against, when that is not gold."""
    if a.get("wrote"):
        return "t-author"
    if a.get("judge"):
        return "t-judged"
    tier = tiers.get(a.get("reference", "")) or (a.get("reference") or "").split("/", 1)[0]
    return "t-silver" if tier == "silver" else ""


def scored_against(a: dict, up: str) -> str:
    """The table cell that says what an arm was scored against: a judge, or a reference, linked."""
    if a.get("judge"):
        return f'judge <code class="small">{e(a["judge"])}</code>'
    ref = a.get("reference")
    if not ref:
        return "—"
    return f'<a class="cell-link" href="{up}{reference_page(ref)}">{e(ref)}</a>'


ROW_KEY = (
    '<p class="rowkey small muted"><span class="key t-silver">scored against silver</span>'
    '<span class="key t-judged">scored by a judge</span>'
    '<span class="key t-author">wrote the reference it is scored against</span>'
    "<span>unmarked rows are scored against gold</span></p>"
)


def e(s) -> str:
    """HTML-escape a string."""
    return html.escape(str(s), quote=True)


def slug(s: str) -> str:
    """Convert a string to a URL-friendly slug."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "x"


def page(
    title: str,
    body: str,
    depth: int = 0,
    here: str = "",
    scripts: tuple = (),
    *,
    nav: list = NAV,
    brand: str = "",
    item: str = "item",
    serve: str = "evh catalog-serve",
    footer: str = "",
    elsewhere: tuple = (),
) -> str:
    """Build a complete HTML page with header, nav, body, and footer. `elsewhere`: the read
    commands that answer what the page shows, ((command, {option: value}), ...), named in the
    footer as the terminal command and, with --mcp, as the MCP tool."""
    up = "../" * depth
    brand = brand or BRAND

    def link(key, href, label, *rest) -> str:
        return (
            f'<a href="{href if "://" in href else up + href}"{" aria-current=page" if key == here else ""}'
            f"{f' class={rest[0]}' if rest else ''}>{label}</a>"
        )

    def group(key, items, label) -> str:
        cur = any(k == here for k, *_ in items)
        return (
            f'<details class="navgroup" data-group="{e(key)}"><summary{" aria-current=page" if cur else ""}>'
            f'{label}</summary><div class="navlist">{"".join(link(*x) for x in items)}</div></details>'
        )

    links = "".join(group(*x) if isinstance(x[1], list) else link(*x) for x in nav)
    # the phone's ☰ menu: every page, a group's under its name
    flat = "".join(
        (
            f'<span class="menu-group">{x[2]}</span><span class="menu-sub">'
            + "".join(link(*y) for y in x[1])
            + "</span>"
        )
        if isinstance(x[1], list)
        else link(*x)
        for x in nav
    )
    # A part of the publication the bar hides on phones (an MCP section, catalog.css) goes in the menu.
    flat += "".join(
        f'<a class="menu-mcp" href="{e(href)}">Ask it from your agent (MCP)</a>'
        for _label, href in SECTIONS
        if href.endswith("#mcp")
    )
    # The parts of the publication (--link), this catalog marked: the logo opens the first.
    here_href = f"{up}index.html"
    parts = [(label, here_href if href == "." else href, href == ".") for label, href in SECTIONS]
    sections = (
        '<nav class="sections" aria-label="Sections">'
        + "".join(
            f'<a href="{e(h)}"{" aria-current=page" if cur else ""}>{e(lb)}</a>' for lb, h, cur in parts
        )
        + "</nav>"
        if parts
        else ""
    )
    logo_href = e(parts[0][1]) if parts else here_href
    brand_text = f"<span>{e(brand)}</span>"
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    foot = footer or (
        f"Built {built} by <code>evh catalog</code>. The pages carry counts and means only, "
        f"and an {e(item)}'s text only where the project publishes it; the inspector shows the rest "
        f"where its server allows."
    )
    # noindex, deliberately: the catalog is a working view over runs, not a page to be found by a
    # search engine; the findings site is what is indexed.
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{e(title)} · {e(brand)}</title>
{share_card(title, brand, body)}
<meta name="color-scheme" content="dark light">
<script src="{up}assets/head.js"></script>
<link rel="stylesheet" href="{up}assets/style.css">
<link rel="stylesheet" href="{up}assets/catalog.css">
<link rel="icon" href="{up}assets/icon.svg" type="image/svg+xml">
{HEAD}</head>
<body data-up="{up}" data-item="{e(item)}" data-serve="{e(serve)}" data-api="{e(API)}">
<header class="bar"><div class="wrap">
  <a class="brand" href="{logo_href}" aria-label="{e(parts[0][0] if parts else brand)}"><img class="mark"
    src="{up}assets/icon.svg" alt="" width="28" height="28">{brand_text}</a>{sections}
  <div class="search"><input id="q" type="search" placeholder="Search  ( / )"
    autocomplete="off" aria-label="Search the catalog"><div id="hits" hidden></div></div>
  <nav class="nav">{links}</nav>
  <details class="menu"><summary class="hbtn" aria-label="Menu">{ICON["menu"]}</summary><nav class="menu-links">{flat}</nav></details>
  <button class="hbtn search-btn" type="button" aria-label="Search" aria-expanded="false" aria-controls="q">{ICON["search"]}</button>
  <button id="theme" class="theme hbtn" aria-label="Toggle light and dark">{ICON["theme"]}</button>
</div></header>
<main>
{body}
</main>
<footer><div class="wrap"><p>{foot}</p>{elsewhere_line(elsewhere)}</div></footer>
<script src="{up}search.js"></script>
<script src="{up}assets/catalog.js"></script>
{"".join(f'<script src="{up}{x}"></script>' for x in scripts)}
</body>
</html>
"""


def hero(kicker: str, title: str, dek: str = "", extra: str = "") -> str:
    """Build a hero section with kicker, title, and optional dek."""
    d = f'<p class="dek">{dek}</p>' if dek else ""
    return (
        f'<section class="hero slim"><div class="wrap"><p class="kicker">{kicker}</p>'
        f"<h1>{title}</h1>{d}{extra}</div></section>"
    )


def block(num: str, eyebrow: str, inner: str, anchor: str = "") -> str:
    """Build a block section with a number, eyebrow text, and inner HTML."""
    aid = f' id="{anchor}"' if anchor else ""
    return (
        f'<section class="block tight"{aid}><div class="wrap"><p class="eyebrow">'
        f'<span class="num">{num}</span>{e(eyebrow)}</p>{inner}</div></section>'
    )


PROSE = re.compile(r"[A-Za-z]{2,}(?=\s)")


def table(tid: str, heads: list, rows: list, filt: str = "", period: bool = False, noun: str = "") -> str:
    """Build an HTML table with optional search filter. A row is a list of cells, or
    {"cells": [...], "cls": "...", "id": "...", "key": "...", "made": "...", "data": {...}} for a
    row with a class, an anchor, a place in the period (`period`: catalog_assets/period.js reads
    the row's key and the day it was made, and fills its `data-flow` cells), or attributes
    group.js groups and filters on (`data`; `noun` names a row in a group's heading)."""
    th = "".join(f"<th>{h}</th>" for h in heads)
    f = ""
    if filt:
        f = (
            f'<div class="filter"><input type="search" data-filter="{tid}" placeholder="{e(filt)}" '
            f'aria-label="{e(filt)}"><span class="muted small"><span data-count="{tid}">{len(rows)}</span>'
            f" shown</span></div>"
        )

    def tr(r) -> str:
        cells, attrs = (r["cells"], r) if isinstance(r, dict) else (r, {})
        a = (
            (f' class="{attrs["cls"]}"' if attrs.get("cls") else "")
            + (f' id="{attrs["id"]}"' if attrs.get("id") else "")
            + (f' data-key="{e(attrs["key"])}"' if attrs.get("key") else "")
            + (f' data-made="{e(attrs["made"])}"' if attrs.get("made") else "")
            + "".join(f' data-{k}="{e(v)}"' for k, v in (attrs.get("data") or {}).items())
        )
        return f"<tr{a}>" + "".join(td(c) for c in cells) + "</tr>"

    def td(c) -> str:
        # Running text gets a readable minimum width on phones; identifiers keep their own width.
        return f'<td class="prose">{c}</td>' if len(PROSE.findall(plain(str(c)))) >= 6 else f"<td>{c}</td>"

    body = "".join(tr(r) for r in rows)
    return (
        f'{f}<div class="scroll-x"><table id="{tid}" class="data sortable"{" data-period-rows" if period else ""}'
        f"{f' data-noun={chr(34)}{e(noun)}{chr(34)}' if noun else ''}><thead><tr>{th}</tr>"
        f"</thead><tbody>{body}</tbody></table></div>"
    )


def group_chips(tid: str, groups: tuple) -> str:
    """The "group by" chips over table `tid` (catalog_assets/group.js): (row attribute, name) pairs,
    the first ("", "no grouping") pressed."""
    chips = "".join(
        f'<button type="button" class="chip" data-group-by="{k}" data-label="{e(n)}" '
        f'aria-pressed="{str(not k).lower()}">{e(n)}</button>'
        for k, n in groups
    )
    return (
        f'<p class="row-chips group-chips" data-for="{tid}" role="group" aria-label="group by">'
        f'<span class="muted small">group by</span>{chips}</p>'
    )


def write(out: Path, rel: str, content: str) -> None:
    """Write content to a relative path within output directory."""
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def write_periods(A: Adapter, by_ds: dict, out: Path) -> None:
    """periods.js: the periods every page's chips offer, and the first day anything happened."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    w = window(A, by_ds)
    write(
        out,
        "periods.js",
        "window.PERIOD="
        + json.dumps(
            {"periods": cp.PERIODS, "default": cp.DEFAULT, "first": w["first"]}, separators=(",", ":")
        )
        + ";\n",
    )


def write_period_rows(out: Path, name: str, rows: dict) -> None:
    """<name>-rows.js: each row's dated runs ([[day, arm number]]) and spend ([[day, usd]])."""
    write(out, f"{name}-rows.js", "window.PERIOD_ROWS=" + json.dumps(rows, separators=(",", ":")) + ";\n")


def PERIOD_SCRIPTS(name: str = "") -> tuple:  # noqa: N802
    """What a page with the period loads after the catalog's own script, in order."""
    return ("periods.js", *((f"{name}-rows.js",) if name else ()), "assets/period.js")


# -- each page's rows in the period: one builder, read by the page (period.js) and by evh ----------
# A row is {"runs": [[day, arm number]], "usd": [[day, usd]], "tokens": [[day, n]],
# "events": [[day, html]], "made": day}, keyed as the page's table keys its rows.


def period_datasets(A: Adapter, by_ds: dict) -> dict:
    """{dataset: row}: its measured runs and what was billed on it; new from `created_at` or its
    first run."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    w, idx, made = window(A, by_ds), cp.arm_index(by_ds), cp.first_dates(A, by_ds)["datasets"]
    return {
        ds: {
            "runs": cp.runs_of(v["arms"], idx),
            "usd": cp.spend_of(w["spend"], lambda x, ds=ds: x.get("dataset") == ds),
            "made": made.get(ds, ""),
        }
        for ds, v in by_ds.items()
    }


def period_goals(A: Adapter, by_ds: dict) -> dict:
    """{goal id: row}: runs and spend on its datasets, and what happened to it (a baseline
    promoted, a round opened or closed), said short; new from its first round or the first day of
    its datasets."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    w, idx, ds_made = window(A, by_ds), cp.arm_index(by_ds), cp.first_dates(A, by_ds)["datasets"]
    fn = getattr(A, "rounds", None)
    rounds = fn() if callable(fn) else []
    out = {}
    for g in A.goals():
        on = [d.get("dataset_id", "") for d in g.get("datasets") or [] if isinstance(d, dict)]
        opened = [(r.get("opened_at") or "")[:10] for r in rounds if r.get("goal") == g["goal_id"]]
        out[g["goal_id"]] = {
            "runs": cp.runs_of([a for d in on if d in by_ds for a in by_ds[d]["arms"]], idx),
            "usd": cp.spend_of(w["spend"], lambda x, on=on: x.get("dataset") in on),
            "events": [
                [bl["promoted_at"][:10], "baseline " + arm_link(bl["arm"], _label_of(by_ds, d, bl["arm"]))]
                for d in on
                for bl in (by_ds.get(d) or {}).get("baselines") or []
                if bl.get("promoted_at") and bl.get("arm")
            ]
            + [
                [r[stamp][:10], f"round {e(r['round_id'])} {verb}"]
                for r in rounds
                if r.get("goal") == g["goal_id"]
                for stamp, verb in (("opened_at", "opened"), ("closed_at", "closed"))
                if r.get(stamp)
            ],
            "made": min([x for x in opened + [ds_made.get(d, "") for d in on] if x], default=""),
        }
    return out


def period_references(A: Adapter, by_ds: dict) -> dict:
    """{reference id: row}: the measured runs of the arms scored against it; new from its
    `created_at`."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    idx = cp.arm_index(by_ds)
    return {
        r["id"]: {
            "runs": cp.runs_of([a for a in v["arms"] if a["reference"] == r["id"] and not a["judge"]], idx),
            "made": (r.get("created_at") or "")[:10],
        }
        for v in by_ds.values()
        for r in v["refs"]
    }


def period_metrics(A: Adapter, by_ds: dict) -> dict:
    """{metric: row}: the measured runs of the arms recording it; new from the first of them."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    idx = cp.arm_index(by_ds)
    out = {}
    for m in metric_index(A, by_ds):
        runs = cp.runs_of([a for v in by_ds.values() for a in v["arms"] if m in a["means"]], idx)
        out[m] = {"runs": runs, "made": min((r[0] for r in runs), default="")}
    return out


def period_activity(A: Adapter, by_ds: dict) -> dict:
    """{"d:<dataset>" | "a:<arm>" | "k:<kind>": row}: runs, spend and tokens by dataset, by arm,
    and by kind of call billed (systems under test, judges)."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    w, idx = window(A, by_ds), cp.arm_index(by_ds)

    def tok(keep) -> list:
        return sorted(
            [(x.get("at") or "")[:10], int(x["tokens"])]
            for x in w["spend"]
            if x.get("at") and isinstance(x.get("tokens"), (int, float)) and keep(x)
        )

    out: dict = {}
    for ds, v in by_ds.items():
        mine = lambda x, ds=ds: x.get("dataset") == ds  # noqa: E731
        out[f"d:{ds}"] = {
            "runs": cp.runs_of(v["arms"], idx),
            "usd": cp.spend_of(w["spend"], mine),
            "tokens": tok(mine),
        }
        for a in v["arms"]:
            runs = cp.runs_of([a], idx)
            mine = lambda x, arm=a["arm"]: x["kind"] == "arm" and x.get("arm") == arm  # noqa: E731
            out[f"a:{a['arm']}"] = {
                "runs": runs,
                "usd": cp.spend_of(w["spend"], mine),
                "tokens": tok(mine),
                "made": min((r[0] for r in runs), default=""),
            }
    for kind, _name in SPEND_KINDS:
        mine = lambda x, kind=kind: x["kind"] == kind  # noqa: E731
        out[f"k:{kind}"] = {"usd": cp.spend_of(w["spend"], mine), "tokens": tok(mine)}
    return out


def inspect_url(arms: list, up: str = "", **params) -> str:
    """Build a URL for the inspector with arms and optional query parameters."""
    q = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items() if v)
    return f"{up}inspect.html?runs=" + quote(",".join(arms), safe=",/") + (f"&{q}" if q else "")


def copy_assets(out: Path) -> None:
    """Copy CSS, JS, and SVG assets to output directory."""
    (out / "assets").mkdir(parents=True, exist_ok=True)
    for a in ASSETS:
        shutil.copy(ASSET_DIR / a, out / "assets" / a)
    (out / "assets" / "head.js").write_text(HEAD_JS_SRC, encoding="utf-8")


def fmt(v) -> str:
    """Format a number for display, or return — for None."""
    if v is None:
        return "—"
    return f"{v:.1f}" if abs(v) >= 10 else f"{v:.3f}"


# -- the harness's own pages -------------------------------------------------------------------
def collect(A: Adapter) -> dict:
    """{dataset: {"arms": [row], "refs": [ref], "items": n}}: what every page needs, read once."""
    by_ds: dict = {}
    runs_of = getattr(A, "arm_runs", None)
    for arm in A.arms():
        d = A.describe(arm)
        sc = A.scores(arm)
        runs = runs_of(arm) if callable(runs_of) else []
        head = d.get("primary") or d.get("task") or ""
        values = (sc.get(head) or {}).get("values") or {}
        by_ds.setdefault(d["dataset"], {"arms": [], "refs": [], "items": 0})["arms"].append(
            {
                "arm": arm,
                "label": d["label"],
                "runs": d.get("runs", 1),
                "metric": head,
                "mean": statistics.fmean(values.values()) if values else None,
                "n": len(values) or max((len(v["values"]) for v in sc.values()), default=0),
                "lower": A.lower_is_better(head, d["dataset"]) if head else False,
                "reference": d.get("reference", ""),
                "judge": d.get("judge", ""),
                "wrote": bool(d.get("wrote_reference")),
                "machine": _machine(A, arm),
                "goal": d.get("goal", ""),
                "format": d.get("format", ""),
                "run_list": runs,
                "last": max((r.get("created_at") or "" for r in runs), default=""),
                # every metric's mean and item count, for the goal pages (numbers only)
                "means": {
                    k: (statistics.fmean(v["values"].values()), len(v["values"]))
                    for k, v in sc.items()
                    if v["values"]
                },
            }
        )
    for r in A.references():
        by_ds.setdefault(r["dataset"], {"arms": [], "refs": [], "items": 0})["refs"].append(r)
    bl = getattr(A, "baselines", None)
    for b in bl() if callable(bl) else []:
        v = by_ds.get(b["dataset"])
        if v is None:
            continue
        v.setdefault("baselines", []).append(b)
        for a in v["arms"]:
            if a["arm"] == b["arm"]:
                a["baseline"] = b
    _versions(A, by_ds)
    # The dataset's own size, from the ADAPTER: the harness's DATASETS path is not where a
    # project with its own layout keeps them. An adapter that cannot say falls back to the
    # most items any arm scored.
    size = getattr(A, "dataset_items", None)
    for ds, v in by_ds.items():
        n = size(ds) if callable(size) else None
        v["items"] = n if n is not None else max((a["n"] for a in v["arms"]), default=0)
    return by_ds


def _machine(A: Adapter, arm: str) -> str:
    """The machine an arm ran on, in a few words (EVAL_HOST_LABEL when set), from its conditions."""
    fn = getattr(A, "conditions", None)
    c = fn(arm) if callable(fn) else {}
    if c.get("machine.label"):
        return c["machine.label"]
    bits = [c.get("machine.platform"), c.get("machine.cpu_count") and f"{c['machine.cpu_count']} CPUs"]
    return " · ".join(b for b in bits if b)


def _versions(A: Adapter, by_ds: dict) -> None:
    """Each dataset's "parent" (the lineage it was made from) and "children" (the versions made
    from it). A version no arm has run on yet still gets a page when it is linked to one that
    has, so the chain has no dead link; unlinked, unrun datasets stay off the pages."""
    lin_of = getattr(A, "dataset_lineage", None)
    if not callable(lin_of):
        return
    every = getattr(A, "datasets", None)
    known = set(every() if callable(every) else []) | set(by_ds)
    lineage = {ds: lin_of(ds) for ds in known}
    linked = True
    while linked:  # pull in each unrun version linked to a shown one, until nothing changes
        linked = False
        for ds, lin in lineage.items():
            parent = (lin or {}).get("dataset_id")
            if parent and (ds in by_ds) != (parent in by_ds) and parent in known:
                by_ds.setdefault(ds, {"arms": [], "refs": [], "items": 0})
                by_ds.setdefault(parent, {"arms": [], "refs": [], "items": 0})
                linked = True
    for ds, v in by_ds.items():
        v["parent"] = lineage.get(ds)
        v["children"] = sorted(
            c for c, lin in lineage.items() if c in by_ds and (lin or {}).get("dataset_id") == ds
        )


def _version_links(by_ds: dict, ds: str, up: str) -> str:
    """The dataset's place in its version chain, as links: made from, and made into."""
    v = by_ds[ds]
    parts = []
    lin = v.get("parent")
    if lin:
        n = {k: len(lin.get(k) or []) for k in ("added", "removed", "changed")}
        parts.append(
            f'<p>Made from <a class="cell-link" href="{up}d/{slug(lin["dataset_id"])}.html">'
            f"{e(lin['dataset_id'])}</a>: {n['added']} added, {n['removed']} removed, {n['changed']} changed."
            + "".join(
                f'<br><span class="small muted">{k}: {e(", ".join(lin[k][:12]))}'
                f"{' …' if len(lin[k]) > 12 else ''}</span>"
                for k in ("added", "removed", "changed")
                if lin.get(k)
            )
            + "</p>"
        )
    for c in v.get("children") or []:
        cl = by_ds[c]["parent"] or {}
        n = {k: len(cl.get(k) or []) for k in ("added", "removed", "changed")}
        parts.append(
            f'<p>Made into <a class="cell-link" href="{up}d/{slug(c)}.html">{e(c)}</a>: '
            f"{n['added']} added, {n['removed']} removed, {n['changed']} changed.</p>"
        )
    if parts:
        parts.append(
            '<p class="small muted">Runs on different versions measure different items, so they are '
            "never tested against each other; compare each version's arms on its own page.</p>"
        )
    return "".join(parts)


def _goals_of(A: Adapter) -> dict:
    """{dataset: [goal]} for every goal naming the dataset."""
    out: dict = {}
    for g in A.goals():
        for d in g.get("datasets") or []:
            out.setdefault(d.get("dataset_id", ""), []).append(g)
    return out


def render_datasets(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """The datasets page: every dataset, its versions, arms, references, goals and baseline."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    goals = _goals_of(A)
    w = window(A, by_ds)
    period_rows = period_datasets(A, by_ds)
    rows = []
    for ds in sorted(by_ds, key=lambda d: (-len(by_ds[d]["arms"]), d)):
        v = by_ds[ds]
        parent = (v.get("parent") or {}).get("dataset_id")
        bl = (v.get("baselines") or [None])[-1]
        label = {a["arm"]: a["label"] for a in v["arms"]}
        last = max((a["last"] for a in v["arms"]), default="")
        runs, usd = period_rows[ds]["runs"], period_rows[ds]["usd"]
        # A dataset under several goals is a group of its own, named after all of them.
        its_goals = " · ".join(g.get("title") or g["goal_id"] for g in goals.get(ds, [])) or "no goal"
        rows.append(
            {
                "key": ds,
                "made": period_rows[ds]["made"],
                "data": {"goal": its_goals},
                "cells": [
                    dataset_link(ds) + (f"<br><small>from {dataset_link(parent)}</small>" if parent else ""),
                    f'<span data-v="{v["items"]}">{v["items"]}</span>',
                    f'<span data-v="{len(v["arms"])}">{len(v["arms"])}</span>',
                    f'<span data-flow="runs">{len(runs)}</span>',
                    '<span data-flow="line"></span>',
                    f'<span data-flow="usd">{e(fmt_amount(sum(x[1] for x in usd), "usd")) if usd else "—"}</span>',
                    ", ".join(reference_link(r["id"]) for r in v["refs"]) or "—",
                    "<br>".join(goal_link(g) for g in goals.get(ds, [])) or "—",
                    arm_link(bl["arm"], label.get(bl["arm"], bl["run"])) if bl and bl.get("arm") else "—",
                    f'<span data-v="{e(last)}">{e(last[:10]) or "—"}</span>',
                ],
            }
        )
    write_period_rows(out, "datasets", period_rows)
    n_arms = sum(len(v["arms"]) for v in by_ds.values())
    body = hero(
        "datasets",
        "Every run, by dataset",
        f"{n_arms} arms on {len(by_ds)} datasets, from {_n_configs(by_ds)} configs. An arm is one config on one "
        f"dataset scored one way, its repeats averaged per {e(A.item_word)}, exactly as <code>pair-test</code> reads "
        "it: a config rescored against silver or by a judge is an arm of its own. "
        "Open a dataset to compare its arms in the inspector.",
        cp.bar(w["first"], w["until"]),
    )
    body += block(
        "01",
        "datasets",
        group_chips("datasets", (("", "no grouping"), ("goal", "goal")))
        + cp.row_chips("datasets", "datasets")
        + table(
            "datasets",
            [
                "dataset",
                f"{e(A.item_word)}s",
                "arms",
                "runs in period",
                "runs per day",
                "spend in period",
                "references",
                "goals",
                "baseline",
                "last run",
            ],
            rows,
            "filter datasets",
            period=True,
            noun="dataset",
        ),
    )
    write(
        out,
        "datasets.html",
        page(
            "Datasets",
            body,
            0,
            "datasets",
            (*PERIOD_SCRIPTS("datasets"), "assets/group.js"),
            nav=nav,
            item=A.item_word,
            elsewhere=(("datasets", {}),),
        ),
    )


def plain(fragment: str) -> str:
    """An HTML fragment as text, for the terminal: tags dropped, entities read."""
    return html.unescape(re.sub(r"<[^>]+>", "", fragment))


def events(A: Adapter, by_ds: dict) -> list[dict]:
    """Everything the project recorded, newest first: {"at", "kind", "dataset", "html"}. Runs are
    one event per arm and day, so three repeats read as one."""
    out = []
    for ds, v in by_ds.items():
        for a in v["arms"]:
            days: dict = {}
            for r in a["run_list"]:
                if r.get("created_at"):
                    days.setdefault(r["created_at"][:10], []).append(r)
            for rs in days.values():
                how = rs[0].get("derived") or "run"
                verb = {"run": "ran", "rescore": "rescored", "judge": "judged", "reparse": "re-parsed"}.get(
                    how, how
                )
                out.append(
                    {
                        "at": max(r["created_at"] for r in rs),
                        "kind": how,
                        "dataset": ds,
                        "html": f"{verb} {arm_link(a['arm'], a['label'])}"
                        + (f" ({len(rs)} runs)" if len(rs) > 1 and "×" not in a["label"] else "")
                        + f" on {dataset_link(ds)}",
                    }
                )
        for r in v["refs"]:
            if r.get("created_at"):
                out.append(
                    {
                        "at": r["created_at"],
                        "kind": "reference",
                        "dataset": ds,
                        "html": f"{e(r['tier'])} reference {reference_link(r['id'])}"
                        + (f" written by {_author_link(r, v, '')}" if r.get("author") else ""),
                    }
                )
        label = {x["arm"]: x["label"] for x in v["arms"]}
        for bl in v.get("baselines") or []:
            if bl.get("promoted_at"):
                who = (
                    arm_link(bl["arm"], label.get(bl["arm"], bl["run"]))
                    if bl.get("arm")
                    else f"<code>{e(bl['run'])}</code>"
                )
                out.append(
                    {
                        "at": bl["promoted_at"],
                        "kind": "baseline",
                        "dataset": ds,
                        "html": f"promoted {who} as the baseline on {dataset_link(ds)}",
                    }
                )
    goals = {g["goal_id"]: g for g in A.goals()}
    fn = getattr(A, "rounds", None)
    for r in fn() if callable(fn) else []:
        g = goals.get(r.get("goal", ""))
        where = goal_link(g) if g else f"<code>{e(r.get('goal', ''))}</code>"
        for stamp, verb in (("opened_at", "opened"), ("closed_at", "closed")):
            if r.get(stamp):
                out.append(
                    {
                        "at": r[stamp],
                        "kind": "round",
                        "dataset": r.get("dataset_id", ""),
                        "html": f"{verb} round {e(r['round_id'])} of {where}",
                    }
                )
    return sorted(out, key=lambda x: x["at"], reverse=True)


def window(A: Adapter, by_ds: dict) -> dict:
    """Everything recorded and spent, and the days it spans: {"events", "spend", "first", "until"}.
    The page without a script shows all of it; the period switch is the browser's
    (catalog_periods.py)."""
    ev = events(A, by_ds)
    fn = getattr(A, "spend", None)
    sp = fn() if callable(fn) else []
    stamps = [x["at"][:10] for x in ev if x["at"]] + [(x.get("at") or "")[:10] for x in sp if x.get("at")]
    return {"events": ev, "spend": sp, "first": min(stamps, default=""), "until": max(stamps, default="")}


def activity_counts(by_ds: dict, since: str) -> dict:
    """{dataset: {day: measured runs}} from `since` on; repeats count one by one."""
    counts: dict = {}
    for ds, v in by_ds.items():
        for a in v["arms"]:
            for r in a["run_list"]:
                day = (r.get("created_at") or "")[:10]
                if day and day >= since and not r.get("derived"):
                    counts.setdefault(ds, {}).setdefault(day, 0)
                    counts[ds][day] += 1
    return counts


#: The spend chart's series: what kind of call was billed, and its name on the page.
SPEND_KINDS = (("arm", "systems under test"), ("judge", "judges"))


#: What spend is counted in: money, or tokens (what a free local model still uses).
SPEND_UNITS = ("usd", "tokens")


def spend_by_day(spend: list[dict], since: str, unit: str = "usd") -> dict:
    """{series name: {day: amount}} from `since` on, in USD or in tokens; an event with no amount
    in that unit (a local model's USD, an unreported token count) adds nothing."""
    out: dict = {}
    for kind, name in SPEND_KINDS:
        for x in spend:
            day = (x.get("at") or "")[:10]
            amount = x.get(unit)
            if x["kind"] == kind and day >= since and isinstance(amount, (int, float)):
                out.setdefault(name, {}).setdefault(day, 0.0)
                out[name][day] += float(amount)
    return out


def fmt_amount(v: float, unit: str) -> str:
    """An amount of spend: dollars to four decimals under one, tokens whole with separators."""
    if unit == "tokens":
        return f"{round(v):,} tokens"
    return f"${v:.4f}" if v < 1 else f"${v:.2f}"


def ref_tier(tiers: dict, key: str) -> str:
    """A group's reference tier: as the references listing says, else from its id (gold/<dataset>,
    silver/<dataset>), for a reference this checkout does not hold (gold not redistributed)."""
    return tiers.get(key) or (key.split("/", 1)[0] if key.startswith(("gold/", "silver/")) else "")


def glance(A: Adapter, by_ds: dict) -> list[dict]:
    """Per goal and dataset: the deciding measure, the promoted baseline, the leader of the gold
    group, the paired test of the leader against the baseline (one test, threshold 0.05), and what
    the goal's strategy recommends with its cost and speed against the baseline."""
    from evaluation_harness import stats  # noqa: PLC0415

    rows = []
    for g in A.goals():
        prim = (g.get("success_criteria") or {}).get("primary") or {}
        measure = prim.get("measure", "")
        lower = prim.get("direction") == "lower"
        retired_in = retired_in_of(A, g)
        for ans in goal_answers(g, by_ds):
            ds = ans["dataset"]
            if not decides_on(g, ds):
                continue  # a dev slice or a generalization check: on the goal page, not the glance
            v = by_ds.get(ds) or {}
            bl = [x for x in v.get("baselines", []) if not x.get("goal") or x.get("goal") == g["goal_id"]]
            base = bl[-1]["arm"] if bl and bl[-1].get("arm") else None
            # The gold group decides; without one, the first group scored against a reference,
            # named in the row so it is never read as gold.
            tiers = {r["id"]: r["tier"] for r in v.get("refs", [])}

            plain = [x for x in ans["groups"] if not x["key"].startswith("judge ")]
            grp = next((x for x in plain if ref_tier(tiers, x["key"]) == "gold"), plain[0] if plain else None)
            dec = group_decision(A, g, ds, grp["rows"], measure, retired_in) if grp else None
            # The decision's leader: the best arm it may recommend, so never a retired or flagged one.
            leader = (
                next((r for r in grp["rows"] if dec and r["arm"] == dec["leader"]), None) if grp else None
            )
            label = {x["arm"]: x["label"] for x in v.get("arms", [])}
            test = None
            if leader and base and leader["arm"] != base:
                cmp = stats.compare(
                    {
                        leader["arm"]: (A.scores(leader["arm"]).get(measure) or {}).get("values") or {},
                        base: (A.scores(base).get(measure) or {}).get("values") or {},
                    },
                    base,
                    higher_is_better=not lower,
                    family=1,
                )
                test = (cmp.get("rows") or [None])[0]
            rec = dec["recommended"] if dec else None
            rows.append(
                {
                    "goal": g,
                    "dataset": ds,
                    "measure": measure,
                    "lower": lower,
                    "baseline": base,
                    "baseline_label": label.get(base, base) if base else "",
                    "baseline_reason": bl[-1].get("reason", "") if bl else "",
                    "baseline_mean": _mean(v, base, measure) if base else None,
                    "leader": leader["arm"] if leader else None,
                    "leader_label": leader["label"] if leader else "",
                    "leader_mean": leader["mean"] if leader else None,
                    "test": test,
                    "group": grp["key"] if grp else "",
                    "gold": grp is not None and ref_tier(tiers, grp["key"]) == "gold",
                    "recommended": rec,
                    "recommended_label": label.get(rec, rec) if rec else "",
                    "strategy": strategy_of(dec["goal"]) if dec else strategy_of(g),
                    # The recommendation against the baseline on cost, speed and the goal's own axes.
                    "vs_baseline": axis_ratios(dec, rec, base) if dec and rec and base else [],
                    # The decision's reasons, as the goal page lists them.
                    "why": list(dec["why"]) if dec else [],
                    # The decision itself (the arms page reads its eligible arms and draws its trade-off).
                    "dec": dec,
                    "retired": retired_in,
                }
            )
    return rows


def _mean(v: dict, arm: str, measure: str):
    a = next((x for x in v.get("arms", []) if x["arm"] == arm), None)
    return a["means"][measure][0] if a and measure in a["means"] else None


def glance_verdict(r: dict) -> str:
    """A glance row's verdict in words: the test, or why there is none."""
    t = r["test"]
    if t and t.get("p") is not None:
        return f"{t.get('verdict', '')} · Δ {t['delta']:+.3f} · p {fmt_p(t['p'])}"
    if r["leader"] and r["baseline"] and r["leader"] == r["baseline"]:
        return "the baseline leads"
    if not r["baseline"]:
        return "no baseline promoted"
    return "—"


def coverage(A: Adapter, by_ds: dict) -> list[dict]:
    """Per dataset: its arms by what they are scored against, its references, the metrics its arms
    record, the goals that use it and its last run."""
    goals = _goals_of(A)
    rows = []
    for ds in sorted(by_ds, key=lambda d: (-len(by_ds[d]["arms"]), d)):
        v = by_ds[ds]
        tiers = {r["id"]: r["tier"] for r in v["refs"]}
        kinds = {"gold": 0, "silver": 0, "judged": 0, "none": 0}
        for a in v["arms"]:
            k = (
                "judged"
                if a["judge"]
                else (
                    tiers.get(a["reference"])
                    or ("none" if not a["reference"] else a["reference"].split("/", 1)[0])
                )
            )
            kinds[k if k in kinds else "none"] += 1
        rows.append(
            {
                "dataset": ds,
                "parent": (v.get("parent") or {}).get("dataset_id", ""),
                "items": v["items"],
                "scored": {k: n for k, n in kinds.items() if n},
                "references": [r["id"] for r in v["refs"]],
                "metrics": sorted(
                    {
                        m
                        for a in v["arms"]
                        for m in a["means"]
                        if not m.startswith(("self_family_", "resumed", "total_"))
                    }
                ),
                "goals": goals.get(ds, []),
                "last": max((a["last"] for a in v["arms"]), default=""),
            }
        )
    return rows


def _activity_chart(by_ds: dict, since: str, until: str) -> str:
    from evaluation_harness import catalog_charts as ch  # noqa: PLC0415

    counts = activity_counts(by_ds, since)
    if not counts:
        return '<p class="muted">No measured run in this period.</p>'
    days = ch.day_range(since, until)
    series = {ds: [counts[ds].get(d, 0) for d in days] for ds in sorted(counts)}
    total = sum(sum(x) for x in series.values())
    return (
        f'<p class="small muted">{total} measured runs (repeats counted one by one), by day and dataset.</p>'
        + ch.stacked_bars(days, series, "measured runs per day, by dataset", " runs", width=HALF)
    )


#: The width of a chart that shares its row with another (catalog_charts draws at this scale).
HALF = 560


def _spend_chart(spend: list[dict], since: str, until: str, unit: str = "usd") -> str:
    from evaluation_harness import catalog_charts as ch  # noqa: PLC0415

    per = spend_by_day(spend, since, unit)
    if not per:
        return (
            f'<p class="muted">No {"cost" if unit == "usd" else "token count"} recorded in this period.</p>'
        )
    days = ch.day_range(since, until)
    series = {n: [d.get(x, 0.0) for x in days] for n, d in per.items()}
    tot = {n: sum(v) for n, v in series.items()}
    line = " · ".join(f"{e(n)} <b>{e(fmt_amount(t, unit))}</b>" for n, t in tot.items())
    label = "cumulative spend in USD" if unit == "usd" else "cumulative tokens (in plus out)"
    return (
        f'<p class="small">{line} · total <b>{e(fmt_amount(sum(tot.values()), unit))}</b></p>'
        + ch.cumulative(
            days, series, label, fmt=lambda v: fmt_amount(v, unit).replace(" tokens", ""), width=HALF
        )
    )


def _spend_panel(spend: list[dict], since: str, until: str) -> str:
    """The spend chart in both units; the panel's own switch picks one (USD first)."""
    return (
        '<p class="unit-switch" role="group" aria-label="unit">'
        '<button type="button" class="btn small" data-unit-show="usd" aria-pressed="true">USD</button>'
        '<button type="button" class="btn small" data-unit-show="tokens" aria-pressed="false">tokens</button></p>'
        + "".join(
            f'<div data-unit="{u}"{"" if u == "usd" else " hidden"}>{_spend_chart(spend, since, until, u)}</div>'
            for u in SPEND_UNITS
        )
    )


def _glance(A: Adapter, by_ds: dict) -> str:
    rows = []
    for r in glance(A, by_ds):
        verdict = e(glance_verdict(r))
        if r["test"] and r["test"].get("p") is not None:
            verdict += f' <a class="btn small" href="{inspect_url([r["leader"], r["baseline"]], baseline=r["baseline"], metric=r["measure"])}">inspect</a>'
        rows.append(
            [
                goal_link(r["goal"]),
                dataset_link(r["dataset"]),
                metric_link(r["measure"])
                + (" ↓" if r["lower"] else "")
                + (
                    f'<br><small class="muted">no gold: scored against {e(r["group"])}</small>'
                    if r["group"] and not r["gold"]
                    else ""
                ),
                (arm_link(r["baseline"], r["baseline_label"]) + f" <small>{fmt(r['baseline_mean'])}</small>")
                if r["baseline"]
                else '<span class="muted">none promoted</span>',
                (arm_link(r["leader"], r["leader_label"]) + f" <small>{fmt(r['leader_mean'])}</small>")
                if r["leader"]
                else "—",
                verdict,
                (
                    arm_link(r["recommended"], r["recommended_label"])
                    + (
                        f"<br><small>{e(' · '.join(r['vs_baseline']))} vs baseline</small>"
                        if r["vs_baseline"]
                        else ""
                    )
                )
                if r["recommended"]
                else '<span class="muted">none yet</span>',
            ]
        )
    if not rows:
        return '<p class="muted">No goals yet: a goal says what an evaluation is for (<code>data/goals/</code>).</p>'
    return (
        '<p class="small muted">The leader is the best arm the goal may recommend (not flagged, over a limit or retired), scored against the gold group\'s '
        "reference; the test is the leader against the baseline alone (threshold 0.05). The goal "
        "page tests every arm, Holm across them. <b>recommended</b> is what the goal's strategy picks "
        "once limits and the tie-break on cost and speed are applied; its ratios are against the "
        "baseline (0.5× costs half).</p>"
        + table(
            "glance",
            ["goal", "dataset", "decides", "baseline", "leader", "leader vs baseline", "recommended"],
            rows,
        )
    )


def _coverage(A: Adapter, by_ds: dict) -> str:
    rows = [
        [
            dataset_link(c["dataset"])
            + (f"<br><small>from {dataset_link(c['parent'])}</small>" if c["parent"] else ""),
            f'<span data-v="{c["items"]}">{c["items"]}</span>',
            " · ".join(f"{k} <b>{n}</b>" for k, n in c["scored"].items()) or "—",
            ", ".join(reference_link(r) for r in c["references"]) or "—",
            f'<details class="inline"><summary>{len(c["metrics"])}</summary>{", ".join(metric_link(m) for m in c["metrics"])}</details>'
            if c["metrics"]
            else "—",
            "<br>".join(goal_link(g) for g in c["goals"]) or "—",
            e(c["last"][:10]) or "—",
        ]
        for c in coverage(A, by_ds)
    ]
    return table(
        "coverage",
        [
            "dataset",
            f"{e(A.item_word)}s",
            "arms scored against",
            "references",
            "metrics",
            "goals",
            "last run",
        ],
        rows,
    )


def _feed(ev: list[dict], since: str) -> str:
    ev = [x for x in ev if x["at"][:10] >= since]
    if not ev:
        return '<p class="muted">Nothing recorded in this period.</p>'
    return table(
        f"feed{'r' if since else 'a'}",
        ["when", "what", "kind"],
        [
            [
                f'<span data-v="{e(x["at"])}">{e(x["at"][:16].replace("T", " "))}</span>',
                x["html"],
                e(x["kind"]),
            ]
            for x in ev
        ],
    )


def home_counts(A: Adapter, by_ds: dict, spend: list[dict]) -> list[tuple]:
    """The home page's tiles, in catalog_periods.TILES' order: (what, how many, page)."""
    from evaluation_harness.catalog_periods import TILES  # noqa: PLC0415

    billed = sum(float(x["usd"]) for x in spend if isinstance(x.get("usd"), (int, float)))
    tokens = int(sum(x["tokens"] for x in spend if isinstance(x.get("tokens"), (int, float))))
    n = {
        "goals": len(A.goals()),
        "datasets": len(by_ds),
        "configs": _n_configs(by_ds),
        "arms": sum(len(v["arms"]) for v in by_ds.values()),
        "references": sum(len(v["refs"]) for v in by_ds.values()),
        "metrics": len(metric_index(A, by_ds)),
        "measured runs": sum(
            1 for v in by_ds.values() for a in v["arms"] for r in a["run_list"] if not r.get("derived")
        ),
        "billed": fmt_amount(billed, "usd"),
        "tokens": f"{tokens:,}",
    }
    return [(what, n[what], href) for what, href, *_ in TILES]


def tile_value(n) -> str:
    """A tile's number. A count over 7 characters also carries a short form (19.5M), which a
    phone's narrow tile shows instead; the tile's title keeps the exact count."""
    s = str(n)
    digits = s.replace(",", "")
    if len(s) <= 7 or not digits.isdigit():
        return e(s)
    v = int(digits)
    short = next(
        f"{v / d:.1f}".rstrip("0").rstrip(".") + u for d, u in ((1e9, "B"), (1e6, "M"), (1e3, "k")) if v >= d
    )
    return f'<span class="full">{e(s)}</span><span class="short">{short}</span>'


def render_home(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """The home page: the whole catalog at a glance. Counts with their trends, then what each goal
    concludes, when work happened and what it cost, what each dataset covers, and everything
    recorded, for the period picked (from today, in the browser; `evh overview --period` prints
    the same)."""

    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    w = window(A, by_ds)
    first, until = w["first"], w["until"]
    rounds_fn = getattr(A, "rounds", None)
    data = cp.home_data(A, by_ds, w["spend"], A.goals(), rounds_fn() if callable(rounds_fn) else [])
    write(
        out,
        "home.js",
        "window.HOME="
        + json.dumps(
            {
                **data,
                "periods": cp.PERIODS,
                "default": cp.DEFAULT,
                "tiles": cp.TILES,
                "units": list(SPEND_UNITS),
            },
            separators=(",", ":"),
        )
        + ";\n",
    )
    # Without a script the page shows all time; with one, the period picked below (from today).
    tile_html = (
        '<div class="tiles">'
        + "".join(
            f'<a class="tile" href="{href}" data-tile="{i}" data-group="{cp.TILES[i][3]}"{" data-period-link" if ".html" in href else ""} title="{e(n)} {e(k)}"><b>{tile_value(n)}</b>'
            f'<span>{e(k)}</span><small class="trend"></small></a>'
            for i, (k, n, href) in enumerate(home_counts(A, by_ds, w["spend"]))
        )
        + "</div>"
        + '<p class="legend groups">'
        + "".join(
            f'<span data-group="{g}"><i></i>{e(name)}</span>'
            for g, name in (
                ("goals", "goals"),
                ("data", "data"),
                ("experiments", "experiments"),
                ("work", "work and spend"),
            )
        )
        + "</p>"
    )
    switch = cp.bar(first, until)
    body = hero(
        "catalog",
        "Every evaluation, at a glance",
        "Pages the harness builds from this project's committed runs: what each goal concludes so far, "
        "when the work happened and what it cost, what each dataset covers, and everything recorded. "
        "Every name is a link: goals, datasets, arms, references and metrics each have a page, and the "
        "inspector tests any arms against a baseline, item by item.",
        (f'<div class="about">{ABOUT}</div>' if ABOUT else "") + switch + tile_html,
    )
    body += block("01", "goals at a glance", _glance(A, by_ds), "glance")
    activity = _activity_chart(by_ds, first, until) if first else '<p class="muted">No runs yet.</p>'
    spending = (
        _spend_panel(w["spend"], first, until)
        if first and w["spend"]
        else '<p class="muted">Nothing spent is recorded.</p>'
    )
    body += block(
        "02",
        "activity and spend",
        f'<div class="duo"><div id="activity"><h3 class="sub">activity</h3><div data-chart="activity">{activity}</div></div>'
        f'<div id="spend"><h3 class="sub">spend</h3><div data-chart="spend">{spending}</div></div></div>'
        '<p><a class="btn small" href="activity.html" data-period-link>every dataset, arm and kind of spend in the period →</a></p>',
    )
    body += block("03", "coverage", _coverage(A, by_ds), "coverage")
    body += block(
        "04",
        "recorded",
        f'<p class="muted" data-feed-empty hidden>Nothing recorded in this period.</p>{_feed(w["events"], "")}'
        if w["events"]
        else '<p class="muted">Nothing recorded yet.</p>',
        "recorded",
    )
    write(
        out,
        "index.html",
        page(
            "Overview",
            body,
            0,
            "home",
            (*PERIOD_SCRIPTS(), "home.js", "assets/overview.js"),
            nav=nav,
            item=A.item_word,
            elsewhere=(("overview", {}),),
        ),
    )


def render_activity(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """The activity page: the home page's two charts at full width, then the period's runs and
    spend by dataset, by arm and by kind, each against the period before, what moved most first
    (then the busiest; for all time, which has no period before, the busiest).
    The measured runs, billed and tokens tiles open it. home.js feeds the charts."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    w = window(A, by_ds)
    first, until = w["first"], w["until"]
    rows = period_activity(A, by_ds)
    ds_rows, arm_rows, kind_rows = [], [], []
    for ds, v in sorted(by_ds.items()):
        key = f"d:{ds}"
        ds_rows.append(
            {
                "key": key,
                "cells": [
                    dataset_link(ds),
                    f'<span data-flow="runs">{len(rows[key]["runs"])}</span>',
                    '<span data-flow="line"></span>',
                    '<span data-flow="usd">—</span>',
                    '<span data-flow="tokens">—</span>',
                ],
            }
        )
        for a in v["arms"]:
            key = f"a:{a['arm']}"
            arm_rows.append(
                {
                    "key": key,
                    "made": rows[key]["made"],
                    "cells": [
                        arm_link(a["arm"], a["label"]),
                        dataset_link(ds),
                        f'<span data-flow="runs" data-line>{len(rows[key]["runs"])}</span>',
                        '<span data-flow="usd">—</span>',
                        '<span data-flow="tokens">—</span>',
                    ],
                }
            )
    for kind, name in SPEND_KINDS:
        key = f"k:{kind}"
        kind_rows.append(
            {
                "key": key,
                "cells": [e(name), '<span data-flow="usd">—</span>', '<span data-flow="tokens">—</span>'],
            }
        )
    write_period_rows(out, "activity", rows)
    activity = _activity_chart(by_ds, first, until) if first else '<p class="muted">No runs yet.</p>'
    spending = (
        _spend_panel(w["spend"], first, until)
        if first and w["spend"]
        else '<p class="muted">Nothing spent is recorded.</p>'
    )
    body = hero(
        "activity",
        "Activity and spend",
        "When the work happened and what it cost, in the period: measured runs (repeats counted one by "
        "one), and what was billed, in USD and in tokens, to the systems under test and the judges. "
        "Each number is against the period before, and what moved most comes first, up or down.",
        cp.bar(first, until),
    )
    body += block(
        "01",
        "activity",
        f'<div id="activity"><div data-chart="activity" data-width="1100">{activity}</div></div>',
    )
    body += block(
        "02", "spend", f'<div id="spend"><div data-chart="spend" data-width="1100">{spending}</div></div>'
    )
    heads_flow = ["runs in period", "runs per day", "spend in period", "tokens in period"]
    body += block(
        "03",
        "by dataset",
        table("actds", ["dataset", *heads_flow], ds_rows, period=True).replace(
            "data-period-rows", 'data-period-rows data-period-sort="runs"', 1
        ),
    )
    body += block(
        "04",
        "by arm",
        cp.row_chips("actarms", "arms")
        + table(
            "actarms",
            ["arm", "dataset", "runs in period", "spend in period", "tokens in period"],
            arm_rows,
            "filter arms",
            period=True,
        ).replace("data-period-rows", 'data-period-rows data-period-sort="runs"', 1),
    )
    body += block(
        "05",
        "by kind",
        table("actkinds", ["what was billed", "spend in period", "tokens in period"], kind_rows, period=True),
    )
    write(
        out,
        "activity.html",
        page(
            "Activity",
            body,
            0,
            "activity",
            (*PERIOD_SCRIPTS("activity"), "home.js", "assets/overview.js"),
            nav=nav,
            item=A.item_word,
            elsewhere=(("activity", {}),),
        ),
    )


def scored_by_rank(a: dict, tiers: dict) -> int:
    """Where an arm sorts by what it is scored against: gold, silver, a judge, nothing. A silver
    and a gold mean of the same metric are different numbers, so they never interleave."""
    if a.get("judge"):
        return 2
    return {"gold": 0, "silver": 1}.get(tiers.get(a.get("reference") or "") or "", 3)


def _n_configs(by_ds: dict) -> int:
    """How many configs are behind the arms: an arm id ends in <dataset>/<config_id>."""
    return len({tuple(a["arm"].rsplit("/", 2)[-2:]) for v in by_ds.values() for a in v["arms"]})


def render_dataset(A: Adapter, ds: str, v: dict, out: Path, nav: list) -> None:
    """Render a page for one dataset with all its arms."""
    tiers = {r["id"]: r["tier"] for r in v["refs"]}
    arms = sorted(
        v["arms"],
        key=lambda a: (
            scored_by_rank(a, tiers),
            a.get("reference") or "",
            a["metric"],
            (a["mean"] if a["mean"] is not None else -1e18) * (1 if a["lower"] else -1),
            a["label"],
        ),
    )
    # The machine is named only when the arms ran on more than one: then latency and cost per
    # second differ by machine, and the inspector's conditions say how.
    machines = {a["machine"] for a in arms if a.get("machine")}
    # Cost and speed per arm: the same numbers the goal pages decide with.
    bax = builtin_axes()
    cells = {a["arm"]: [cell_of(ax, A.scores(a["arm"])) for ax in bax] for a in arms}
    rows = [
        {
            "cls": row_kind(a, tiers),
            "cells": [
                arm_link(a["arm"], a["label"], "../")
                + (' <span class="tag-base">baseline</span>' if a.get("baseline") else "")
                + (
                    f"<br><small>on {e(a['machine'])}</small>"
                    if len(machines) > 1 and a.get("machine")
                    else ""
                ),
                metric_link(a["metric"], "../"),
                (
                    f'<span data-v="{a["mean"] if a["mean"] is not None else ""}">{fmt(a["mean"])}'
                    f"{' ↓' if a['lower'] else ''}</span>"
                ),
                f'<span data-v="{a["n"]}">{a["n"]}</span>',
                *(axis_cell(ax, c) for ax, c in zip(bax, cells[a["arm"]])),
                str(a["runs"]),
                scored_against(a, "../"),
                f'<a class="btn small" href="{inspect_url([a["arm"]], "../")}">inspect</a>',
            ],
        }
        for a in arms
    ]
    # One button per group of arms that can be tested together: the same headline metric,
    # scored against the same reference. A silver-scored and a gold-scored run both record
    # the metric but measure different things, and the inspector sets such arms aside.
    groups: dict = {}
    for a in arms:
        groups.setdefault((a["metric"] or "", "" if a["judge"] else a["reference"] or ""), []).append(
            a["arm"]
        )
    btns = []
    for (metric, ref), members in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if len(members) < 2:
            continue
        more = (
            f" (the first {INSPECT_MAX} of {len(members)}; add others in the inspector)"
            if len(members) > INSPECT_MAX
            else ""
        )
        what = ", ".join(
            x
            for x in ((f"on {e(metric)}" if metric else ""), (f"scored against {e(ref)}" if ref else ""))
            if x
        )
        btns.append(
            f'<a class="btn" href="{inspect_url(members[:INSPECT_MAX], "../", metric=metric)}">'
            f"Inspect the {len(members)} arms {what}</a>"
            + (f'<span class="muted small">{more}</span>' if more else "")
        )
    btn = f'<p class="btns">{"".join(btns)}</p>' if btns else ""
    for b in v.get("baselines", [])[-1:]:
        label = next((a["label"] for a in arms if a["arm"] == b.get("arm")), b["run"])
        who = arm_link(b["arm"], label, "../") if b.get("arm") else e(label)
        btn = (
            f'<div class="answer"><p class="small muted">baseline, promoted {e((b["promoted_at"] or "")[:10])}</p>'
            f'<p class="lead"><b>{who}</b></p><p>{e(b["reason"])}</p></div>'
        ) + btn
    goals = _goals_of(A).get(ds, [])
    if goals:
        btn += '<p class="small">goals: ' + ", ".join(goal_link(g, "../") for g in goals) + "</p>"
    refs = "".join(
        f"<li>{reference_link(r['id'], '../')} · {e(r['tier'])}"
        + (f" · written by {_author_link(r, v, '../')}" if r.get("author") else "")
        + "</li>"
        for r in v["refs"]
    )
    body = hero(
        "dataset",
        e(ds or "(no dataset_id)"),
        f"{v['items']} {e(A.item_word)}s · {len(arms)} arms. Headline: each arm's own "
        "primary metric, mean over its items; arms with different primary metrics are "
        "not ranked against each other.",
        btn,
    )
    body += block(
        "01",
        "arms",
        ROW_KEY
        + table(
            "arms",
            [
                "arm",
                "metric",
                "mean",
                f"{e(A.item_word)}s",
                *(e(axis_title(ax)) for ax in bax),
                "runs",
                "scored against",
                "",
            ],
            rows,
            "filter arms",
        ),
    )
    n = 2
    biggest: tuple[str, list[str]] = max(
        ((m, members) for (m, _ref), members in groups.items() if len(members) >= 2),
        key=lambda x: len(x[1]),
        default=("", []),
    )
    body += block("02", "what's inside", render_inside(A, ds, biggest[1][:INSPECT_MAX], biggest[0]), "inside")
    if v.get("versions"):
        n += 1
        body += block(f"{n:02d}", "versions", v["versions"], "versions")
    if refs:
        n += 1
        body += block(f"{n:02d}", "references", f"<ul>{refs}</ul>")
    fields_html = render_fields(A, ds)
    if fields_html:
        n += 1
        body += block(f"{n:02d}", f"{A.item_word} fields", fields_html, "item-fields")
    prof = getattr(A, "dataset_profile", None)
    write(
        out,
        f"d/{slug(ds or 'none')}.html",
        page(
            ds or "dataset",
            body,
            1,
            "",
            nav=nav,
            item=A.item_word,
            # dataset-items answers only once the dataset has a profile; it refuses otherwise
            elsewhere=(
                (("datasets", {"dataset-id": ds}),)
                + ((("dataset-items", {"dataset-id": ds}),) if callable(prof) and prof(ds) else ())
                if ds
                else ()
            ),
        ),
    )


def _show(v, field: dict) -> str:
    if field.get("type") == "duration" and isinstance(v, (int, float)):
        secs = round(v)
        return f"{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
    s = fmt(v) if isinstance(v, float) else str(v)
    return s + (f" {field['unit']}" if field.get("unit") else "")


def _gold_line(r: dict) -> str:
    """One gold reference's shape, in words."""
    if r["shape"] == "labels":
        n = sum(r["labels"].values()) or 1
        cells = "".join(
            f"<tr><td>{e(k)}</td><td>{v}</td><td>{v / n:.0%}</td></tr>"
            for k, v in sorted(r["labels"].items(), key=lambda kv: (-kv[1], kv[0]))
        )
        return (
            f"<p>{reference_link(r['id'], '../')}: {len(r['labels'])} labels</p>"
            f'<div class="scroll-x"><table class="data"><thead><tr><th>label</th><th>items</th><th>share</th></tr>'
            f"</thead><tbody>{cells}</tbody></table></div>"
        )
    if r["shape"] == "lists":
        x = r["entries"]
        what = f"a list per item, {x['min']}–{x['max']} entries, median {x['median']}"
    elif r["shape"] == "record":
        what = "a record per item: " + ", ".join(f"<code>{e(k)}</code>" for k in r["keys"])
    elif r["shape"] == "text":
        x = r["words"]
        what = f"text, {x['min']}–{x['max']} words, median {x['median']}"
    else:
        what = e(r.get("note") or "not on the machine that wrote the profile")
    return f"<p>{reference_link(r['id'], '../')}: {what}</p>"


def _web(url) -> bool:
    """An http(s) URL: a profile is project data, and a `javascript:` href would run on click."""
    return isinstance(url, str) and url.lower().startswith(("https://", "http://"))


def render_inside(A: Adapter, ds: str, inspect_arms: list[str], metric: str) -> str:
    """What is inside the dataset (data/profiles/<ds>.json): how many items and how long, the gold's
    shape, then one row per item with its length, its gold and where it can be read at its source.
    No item text unless the profile carries it, which `evh dataset-profile --with-text` allows only
    for text git already tracks."""
    from evaluation_harness import catalog_charts as ch  # noqa: PLC0415

    fn = getattr(A, "dataset_profile", None)
    p = fn(ds) if callable(fn) else None
    if not p:
        return (
            f'<p class="muted">No profile yet. Where the dataset is materialized, '
            f"<code>evh dataset-profile --dataset-id {e(ds)}</code> writes one: its {e(A.item_word)}s, how long "
            f"they are, the gold's shape and where each can be read.</p>"
        )
    it, w = p["items"], p["items"].get("words") or {}
    src = p.get("source")
    lines = [
        (
            f"{e(str(it['n']))} {e(A.item_word)}s, {e(it.get('kind', 'text'))}, "
            f"{e(str(w.get('min', 0)))}–{e(str(w.get('max', 0)))} words (median {e(str(w.get('median', 0)))}, "
            f"middle half {e(str(w.get('p25', 0)))}–{e(str(w.get('p75', 0)))})."
        )
    ]
    if src:
        name = e(src.get("name") or "the source")
        lines.append(
            (
                f'Source: <a href="{e(src["url"])}" rel="noopener">{name}</a>'
                if _web(src.get("url"))
                else f"Source: {name}"
            )
            + (f" ({e(src['split'])} split)" if src.get("split") else "")
            + (
                f". The text stays there; each {e(A.item_word)} below links to its row."
                if any(_web(r.get("source_url")) for r in p["rows"])
                else "."
            )
        )
    if p.get("stale"):
        lines.append(
            f'<span class="note">The items changed since this profile was written: run '
            f"<code>evh dataset-profile --dataset-id {e(ds)}</code> again.</span>"
        )
    head = "".join(f"<p>{x}</p>" for x in lines)
    chart = (
        ch.histogram(w["histogram"], f"{ds}: words per {A.item_word}", "words") if w.get("histogram") else ""
    )
    golds = "".join(_gold_line(r) for r in p.get("references") or [])
    gold_ids = [r["id"] for r in p.get("references") or [] if r.get("shape") not in (None, "absent")]
    has_text = any(r.get("text") for r in p["rows"])
    rows = []
    for r in p["rows"]:
        k = r["item_id"]
        links = [
            f'<a href="{e(r["source_url"])}" rel="noopener">source ↗</a>'
            if _web(r.get("source_url"))
            else "",
            f'<a href="{inspect_url(inspect_arms, "../", metric=metric, item=k)}">inspect</a>'
            if len(inspect_arms) >= 2
            else "",
        ]
        cells = [
            f'<code class="small" title="{e(k)}">{e(k[:12])}</code>',
            e(str(r["words"])),
            "; ".join(e(r["reference"].get(g, "")) for g in gold_ids) or "—",
            " · ".join(x for x in links if x) or "—",
        ]
        if has_text:
            t = r.get("text") or ""
            cells.insert(
                1, f'<details><summary class="small">{e(t[:80])}…</summary>{e(t)}</details>' if t else "—"
            )
        rows.append(cells)
    heads = [f"{e(A.item_word)}", *(["text"] if has_text else []), "words", "gold", "open"]
    return (
        head
        + chart
        + (f'<p class="eyebrow small">the gold</p>{golds}' if golds else "")
        + table("inside-items", heads, rows, f"filter {A.item_word}s")
        + '<p class="small muted">Each row is the profile <code>evh dataset-items --dataset-id '
        + f"{e(ds)}</code> prints; <b>inspect</b> opens the {e(A.item_word)} in the inspector with the dataset's "
        + "largest group of comparable arms, and its text where the inspector runs on a machine that has it.</p>"
    )


def render_fields(A: Adapter, ds: str) -> str:
    """The dataset's declared fields (ADR-0003): name, type, how many items fill each, and for a
    field marked public a summary of its values. A field not marked public shows none: the
    static pages carry no item content unless the project says so."""
    fl = item_fields(A, ds)
    fs = fl["fieldset"]
    if not fs:
        return ""
    decl = {f["name"]: f for f in fs.get("fields") or []}
    items = [{"item_id": i, "fields": f} for i, f in fl["values"].items()]
    rows = []
    for s in _fields.summary(fs, items):
        f = decl[s["name"]]
        if not s["public"]:
            vals = '<span class="muted small">not public</span>'
        elif "counts" in s:
            vals = " · ".join(
                f"{e(k)} <b>{c}</b>" for k, c in sorted(s["counts"].items(), key=lambda kv: -kv[1])
            )
        elif "median" in s:
            vals = f"{e(_show(s['min'], f))} – {e(_show(s['max'], f))}, median {e(_show(s['median'], f))}"
        elif "min" in s:
            vals = f"{e(s['min'])} – {e(s['max'])}"
        elif "distinct" in s:
            vals = f"{s['distinct']} distinct"
        else:
            vals = "—"
        rows.append(
            [
                f'{e(s["label"])}<br><code class="small">{e(s["name"])}</code>',
                e(s["type"] + (f" ({s['unit']})" if s["unit"] else "")),
                f'<span data-v="{s["filled"]}">{s["filled"]} of {s["of"]}</span>',
                e(s["description"]),
                vals,
            ]
        )
    intro = (
        f'<p class="muted small">Declared in the field set <code>{e(fs.get("fieldset_id", ""))}</code>. '
        f"Values are summarised only for fields marked public; the inspector shows each "
        f"{e(A.item_word)}'s, filters a comparison by them, and breaks it down by a choice or "
        "yes/no field.</p>"
    )
    return intro + table("fields", ["field", "type", "filled", "description", "values"], rows)


def _group_key(a: dict) -> str:
    """What an arm's numbers are measured against: a judge, a reference, or nothing."""
    return f"judge {a['judge']}" if a.get("judge") else (a.get("reference") or "no reference")


def goal_answers(goal: dict, by_ds: dict) -> list:
    """[{"dataset", "role", "notes", "groups": [{"key", "rows", "leader"}]}] for one goal: on each
    of its datasets, every arm that records the goal's primary measure, grouped by what it is
    scored against (gold first, then silver, then judges), best first within a group. Arms are
    ranked only against arms on the same dataset scored against the same thing, and a group's
    leader is never a flagged arm: fewer items than min_items, a format the goal does not accept,
    or the arm that wrote the reference it is scored against."""
    crit = goal.get("success_criteria") or {}
    lower = (crit.get("primary") or {}).get("direction") == "lower"
    out = []
    for ds, role, notes, rows in _goal_rows(goal, by_ds):
        groups: dict = {}
        for r in rows:
            groups.setdefault(_group_key(r), []).append(r)
        ordered = sorted(
            groups.items(), key=lambda kv: (kv[0].startswith("judge "), not kv[0].startswith("gold/"), kv[0])
        )
        out.append(
            {
                "dataset": ds,
                "role": role,
                "notes": notes,
                "groups": [
                    {
                        "key": k,
                        "rows": sorted(
                            g,
                            key=lambda r: (bool(r["flags"]), r["mean"] if lower else -r["mean"], r["label"]),
                        ),
                        "leader": next(
                            (
                                r
                                for r in sorted(g, key=lambda r: r["mean"] if lower else -r["mean"])
                                if not r["flags"]
                            ),
                            None,
                        ),
                    }
                    for k, g in ordered
                ],
            }
        )
    return out


def _goal_rows(goal: dict, by_ds: dict) -> list:
    """[(dataset, role, notes, rows)]: the arms on each of the goal's datasets that record its
    measure, each with its mean, items, whether it names the goal, and its flags."""
    crit = goal.get("success_criteria") or {}
    measure = (crit.get("primary") or {}).get("measure", "")
    need = crit.get("min_items")
    formats = {c.get("format") for c in goal.get("output_contract") or [] if c.get("format")}
    out = []
    for d in goal.get("datasets") or []:
        ds = d.get("dataset_id", "")
        rows = []
        for a in (by_ds.get(ds) or {}).get("arms", []):
            # A judged arm records its judge's score, not the goal's measure: it is shown in its
            # judge's group, read on that score (never ranked with the reference-scored groups).
            use = measure if measure in a["means"] else (a["metric"] if a.get("judge") else None)
            if not use or use not in a["means"]:
                continue
            mean, n = a["means"][use]
            flags = []
            if need and n < need:
                flags.append(f"n {n} < min_items {need}")
            if a["format"] and formats and a["format"] not in formats:
                flags.append(f"format {a['format']} not in the contract")
            if a["wrote"]:
                flags.append("wrote the reference it is scored against")
            rows.append(dict(a, mean=mean, n=n, measure=use, filed=a["goal"] == goal["goal_id"], flags=flags))
        out.append((ds, d.get("role", ""), d.get("notes", ""), rows))
    return out


def render_goals(A: Adapter, by_ds: dict, out: Path, nav: list) -> int:
    """Render the goals page and one page per goal; return the number rendered."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    goals = A.goals()
    seen = glance(A, by_ds)
    w = window(A, by_ds)
    period_rows = period_goals(A, by_ds)
    rows = []
    for g in goals:
        made = period_rows[g["goal_id"]]["made"]
        prim = (g.get("success_criteria") or {}).get("primary") or {}
        filed = configs_filed(by_ds, g)
        rec = "<br>".join(
            (dataset_link(r["dataset"]) + ": " if len(g.get("datasets") or []) > 1 else "")
            + arm_link(r["recommended"], r["recommended_label"])
            + (
                f"<br><small>{e(' · '.join(r['vs_baseline']))} vs baseline</small>"
                if r["vs_baseline"]
                else ""
            )
            for r in seen
            if r["goal"]["goal_id"] == g["goal_id"] and r["recommended"]
        )
        rows.append(
            {
                "key": g["goal_id"],
                "made": made,
                "cells": [
                    goal_link(g),
                    e(g.get("statement", "")),
                    metric_link(prim.get("measure", ""))
                    + (f" ({e(prim['direction'])})" if prim.get("direction") else ""),
                    "<br>".join(dataset_link(d.get("dataset_id", "")) for d in g.get("datasets") or [])
                    or "—",
                    f'<span data-v="{filed}">{filed}</span>',
                    f'<span data-flow="runs" data-line>{len(period_rows[g["goal_id"]]["runs"])}</span>',
                    '<span data-flow="usd">—</span>',
                    f'<span data-flow="events">{len(period_rows[g["goal_id"]]["events"])}</span>',
                    rec or '<span class="muted">none yet</span>',
                ],
            }
        )
        render_goal(A, g, by_ds, out, nav)
    write_period_rows(out, "goals", period_rows)
    # What happened, one row per change; the period keeps the rows of its own days.
    feed = sorted(
        ([day, g, html_] for g in goals for day, html_ in period_rows[g["goal_id"]]["events"]),
        key=lambda x: x[0],
        reverse=True,
    )
    dek = (
        "What each evaluation is for: who uses the output, the decision it informs, and the "
        "measure that decides. Runs name their goal in their config (<code>goal:</code>)."
    )
    body = hero("goals", "Goals", dek, cp.bar(w["first"], w["until"]))
    body += block(
        "01",
        "goals",
        cp.row_chips("goals", "goals")
        + table(
            "goals",
            [
                "goal",
                "statement",
                "decides",
                "datasets",
                "configs filed",
                "runs in period",
                "spend in period",
                "changes in period",
                "recommended",
            ],
            rows,
            period=True,
        )
        if rows
        else '<p class="muted">No goals yet: add <code>data/goals/&lt;goal_id&gt;.yaml</code> '
        "(schema: <code>goal.schema.json</code>).</p>",
    )
    if feed:
        body += block(
            "02",
            "what happened in the period",
            '<p class="muted pempty" data-feed-empty="goalfeed" hidden>Nothing happened to a goal in this period.</p>'
            + table(
                "goalfeed",
                ["when", "goal", "what"],
                [
                    {"made": day, "cells": [f'<span data-v="{e(day)}">{e(day)}</span>', goal_link(g), h]}
                    for day, g, h in feed
                ],
            ).replace('class="data sortable"', 'class="data sortable" data-period-feed', 1),
        )
    write(
        out,
        "goals.html",
        page(
            "Goals",
            body,
            0,
            "goals",
            PERIOD_SCRIPTS("goals"),
            nav=nav,
            item=A.item_word,
            elsewhere=(("goals", {}),),
        ),
    )
    return len(goals)


def configs_filed(by_ds: dict, g: dict) -> int:
    """How many configs name this goal: the systems run for it, each counted once however many
    ways it was scored (gold, silver, a judge)."""
    return len(
        {a["arm"].rsplit("/", 1)[-1] for v in by_ds.values() for a in v["arms"] if a["goal"] == g["goal_id"]}
    )


def _when(stamp: str) -> str:
    return (stamp or "")[:10]


def _answer(A: Adapter, g: dict, by_ds: dict, measure: str) -> str:
    """The goal's answer so far: on each of its datasets, the promoted baseline and why, or that
    nothing has been decided, with the command that decides it."""
    parts = []
    for d in g.get("datasets") or []:
        ds = d.get("dataset_id", "")
        v = by_ds.get(ds) or {}
        bl = [b for b in v.get("baselines", []) if not b.get("goal") or b.get("goal") == g["goal_id"]]
        label = {a["arm"]: a["label"] for a in v.get("arms", [])}
        head = dataset_link(ds, "../")
        if bl:
            b = bl[-1]
            arm = label.get(b.get("arm") or "", b["run"])
            who = arm_link(b["arm"], arm, "../") if b.get("arm") else e(arm)
            parts.append(
                f'<div class="answer"><p class="small muted">{head} · baseline promoted {e(_when(b["promoted_at"]))}'
                + (f" · scored against {e(b['tier'])}" if b.get("tier") else "")
                + f'</p><p class="lead"><b>{who}</b></p><p>{e(b["reason"])}</p>'
                + (
                    f'<p><a class="btn small" href="{inspect_url([b["arm"]], "../", metric=measure)}">inspect it</a></p>'
                    if b.get("arm")
                    else ""
                )
                + "</div>"
            )
        else:
            parts.append(
                f'<div class="answer"><p class="small muted">{head}</p><p>No decision yet. When the tests '
                "separate an arm worth keeping, promote its run with the reason they give: "
                '<code>evh run-promote --run &lt;run_id&gt; --reason "…"</code></p></div>'
            )
    return "".join(parts) or '<p class="muted">The goal names no dataset.</p>'


def _rounds_block(A: Adapter, g: dict, measure: str, lower: bool) -> str:
    """A goal's rounds (ADR-0004), newest first: what each set out to learn, what changed, its arms
    in play and those retired (with why), its best arm and how it compares with the previous
    round's best, its conclusion; for the open round, what the evidence suggests next, each as the
    command that does it. Empty when the goal has no rounds (they are optional)."""
    fn = getattr(A, "rounds", None)
    rounds = [r for r in (fn() if callable(fn) else []) if r.get("goal") == g["goal_id"]]
    if not rounds:
        return ""
    by_id = {r["round_id"]: r for r in rounds}

    def best(r):
        means = {}
        for a in r.get("arms") or []:
            vals = (A.scores(a).get(measure) or {}).get("values") or {}
            if vals:
                means[a] = statistics.fmean(vals.values())
        if not means:
            return None, None
        a = (min if lower else max)(means, key=lambda x: means[x])
        return a, means[a]

    rows, details = [], []
    for r in sorted(rounds, key=lambda r: -int(r["round_id"][1:] or 0)):
        arm, mean = best(r)
        prev = by_id.get(r.get("from") or "")
        prev_best, _ = best(prev) if prev else (None, None)
        vs = (
            f'<a class="btn small" href="{inspect_url([prev_best, arm], "../", baseline=prev_best, metric=measure)}">vs {e((prev or {}).get("round_id", ""))}\'s best</a>'
            if arm and prev_best and prev_best != arm
            else "—"
        )
        label = arm.rsplit("/", 1)[-1] if arm else "—"
        concl = (r.get("conclusion") or {}).get("text", "")
        rows.append(
            {
                "cls": "" if r.get("status") == "closed" else "t-open",
                "cells": [
                    f"<b>{e(r['round_id'])}</b>"
                    + (f" <small>from {e(r['from'])}</small>" if r.get("from") else ""),
                    e(r.get("status", "")),
                    e(r.get("hypothesis", "") or "—"),
                    f'<span data-v="{len(r.get("arms") or [])}">{len(r.get("arms") or [])}</span>'
                    + (f" <small>({len(r.get('retired') or [])} retired)</small>" if r.get("retired") else "")
                    # The round's arms in the inspector, against its leader: `evh inspect --round`.
                    + (
                        f' <a class="btn small" title="evh inspect --round {e(r["round_id"])} --goal {e(g["goal_id"])}" '
                        f'href="{inspect_url((r.get("arms") or [])[:INSPECT_MAX], "../", baseline=arm, metric=measure)}">inspect</a>'
                        if arm and len(r.get("arms") or []) > 1
                        else ""
                    ),
                    (f"{arm_link(arm, label, '../')} <small>{fmt(mean)}</small>" if arm else "—"),
                    vs,
                    e(concl) or ("<i>open</i>" if r.get("status") == "open" else "—"),
                ],
            }
        )
        lines = [f"<li>changed: {e(c)}</li>" for c in r.get("changes") or []]
        lines += [
            f"<li>retired {_config_link(A, r, x['config_id'])}: {e(x['reason'])}</li>"
            for x in r.get("retired") or []
        ]
        lines += [f"<li>carried in unchanged: {_config_link(A, r, c)}</li>" for c in r.get("carried") or []]
        sugg = ""
        if r.get("status") == "open" and getattr(A, "data_dir", None) == _common.DATA:
            try:
                from evaluation_harness.rounds import evidence  # noqa: PLC0415

                ev = evidence(g["goal_id"], r)
                lines += [
                    f"<li>against {e(v['label'])} (<code>{e(v['other'].rsplit('/', 1)[-1])}</code>): "
                    f"{e(v['verdict'])}, Δ {v['delta']:+.4f}, p {fmt_p(v['p'])}</li>"
                    for v in ev["against"]
                ]
                sugg = "".join(
                    f"<li>{e(what)}"
                    + (
                        f'<br><code class="cmd">{e(cmd)}</code> <button type="button" class="btn small copy" data-copy="{e(cmd)}">copy</button>'
                        if cmd
                        else ""
                    )
                    + "</li>"
                    for what, cmd in ev["suggest"]
                ) + "".join(f'<li class="muted">{e(n)}</li>' for n in ev["notes"])
            except SystemExit:
                sugg = ""
        if lines or sugg:
            details.append(
                f'<details class="rounddetail"{" open" if r.get("status") == "open" else ""}><summary>{e(r["round_id"])}'
                f" · {e(r.get('status', ''))}</summary><ul>{''.join(lines)}</ul>"
                + (
                    f'<p class="small"><b>suggested next</b>, each as the command that does it (the catalog only reads):</p><ul class="suggest">{sugg}</ul>'
                    if sugg
                    else ""
                )
                + "</details>"
            )
    return (
        '<p class="small muted">Rounds are optional: each one sets out to learn something, changes a few '
        "arms, drops what lost and says why, and ends in a conclusion. Decisions are made with "
        "<code>evh round-open</code>, <code>round-retire</code> and <code>round-close</code>; "
        "<code>evh rounds</code> says the same as this page.</p>"
        + table(
            "rounds",
            [
                "round",
                "status",
                "set out to learn",
                "arms in play",
                f"best on {e(measure)}",
                "against the previous round",
                "concluded",
            ],
            rows,
        )
        + "".join(details)
    )


def render_goal(A: Adapter, g: dict, by_ds: dict, out: Path, nav: list) -> None:
    """One goal: its answer so far (the promoted baselines) first, then what it is for, then on
    each of its datasets the arms that record its measure, grouped by what they are scored
    against, a leader chosen within each group."""
    crit = g.get("success_criteria") or {}
    prim = crit.get("primary") or {}
    measure = prim.get("measure", "")
    facts = [
        ("decision", g.get("decision", "")),
        ("audience", (g.get("context") or {}).get("audience", "")),
        (
            "decides",
            (
                f"{measure}, {prim['direction']} is better"
                if prim.get("direction") in ("higher", "lower")
                else f"{measure}, no significant drop against the baseline"
            )
            + (f"; threshold {prim['threshold']}" if prim.get("threshold") is not None else ""),
        ),
        ("min items", crit.get("min_items", "")),
        ("weighs", "; ".join(axis_title(x) for x in axes_of(g) if x["role"] != "ignore")),
        ("strategy", f"{strategy_of(g)}: {STRATEGIES[strategy_of(g)]}"),
        ("tie-break", ", ".join(tie_break_of(g))),
        (
            "output contract",
            "; ".join(
                " · ".join(str(c.get(k)) for k in ("format", "length", "language") if c.get(k))
                for c in g.get("output_contract") or []
            ),
        ),
        ("status", g.get("status", "")),
    ]
    dl = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in facts if v not in ("", None))

    # Rules in words no number checks: shown, never computed.
    def source(s: str) -> str:
        m = _PATH_HEAD.match(s)
        return project_path(m.group(1)) + e(m.group(2)) if m else e(s)

    guard = "".join(
        f"<li><b>{e(x['name'])}</b>: {e(x['rule'])}"
        + (f' <small class="muted">({source(x["source"])})</small>' if x.get("source") else "")
        + "</li>"
        for x in crit.get("guardrails") or []
    )
    if guard:
        dl += f'<dt>guardrails</dt><dd><ul class="small">{guard}</ul></dd>'
    # The goal's own links (its report, a deployment's findings page): a web address opens; a path
    # in the project links to --repo when given, else it is named.
    see = "".join(
        "<li>"
        + (
            f'<a href="{e(x["url"])}">{e(x.get("note") or x["url"])}</a>'
            if str(x.get("url", "")).startswith(("https://", "http://"))
            else f"{e(x.get('note') or '')}{': ' if x.get('note') else ''}{project_path(str(x.get('url', '')))}"
        )
        + "</li>"
        for x in g.get("links") or []
        if x.get("url")
    )
    if see:
        dl += f'<dt>links</dt><dd><ul class="small">{see}</ul></dd>'
    body = hero("goal", e(g.get("title") or g["goal_id"]), e(g.get("statement", "")))
    body += block("01", "the answer so far", _answer(A, g, by_ds, measure))
    n = 2
    rounds_html = _rounds_block(A, g, measure, prim.get("direction") == "lower")
    if rounds_html:
        body += block(f"{n:02d}", "rounds", rounds_html, "rounds")
        n += 1
    body += block(f"{n:02d}", "what it is for", f'<dl class="kv">{dl}</dl>')
    n += 1
    retired_in = retired_in_of(A, g)
    for ans in goal_answers(g, by_ds):
        ds, v = ans["dataset"], by_ds.get(ans["dataset"]) or {}
        tiers = {r["id"]: r["tier"] for r in v.get("refs", [])}
        lin = (v.get("parent") or {}).get("dataset_id")
        about = (
            f"<p>{dataset_link(ds, '../')}: "
            f"{v.get('items', 0)} {e(A.item_word)}s"
            + (f" · {e(ans['role'])}" if ans["role"] else "")
            + (f" · made from {dataset_link(lin, '../')}" if lin else "")
            + "</p>"
            + (f'<p class="small muted">{e(ans["notes"])}</p>' if ans["notes"] else "")
            + (
                '<p class="small">references: '
                + ", ".join(
                    reference_link(r["id"], "../")
                    + (f" (written by {_author_link(r, v, '../')})" if r.get("author") else "")
                    for r in v.get("refs", [])
                )
                + "</p>"
                if v.get("refs")
                else ""
            )
        )
        if not ans["groups"]:
            inner = about + f'<p class="muted">No arm on this dataset records <code>{e(measure)}</code>.</p>'
        else:
            inner = about + (
                f'<p class="small muted">Mean {metric_link(measure, "../")} over each arm\'s {e(A.item_word)}s, '
                "in groups by what each arm is scored against: numbers from different references, or "
                "from a judge, are different measurements and are never ranked together. A mean is not a "
                "verdict: the inspector tests each arm against its group's leader (Holm across them). "
                "Flagged arms are never the leader. <b>filed</b>: the arm's config names this goal "
                "(<code>goal:</code>); an arm without it is listed because it records the measure.</p>"
            )
            for gi, grp in enumerate(ans["groups"]):
                rows = grp["rows"]
                gm = rows[0].get("measure", measure) if rows else measure  # a judge's group: its score
                dec = group_decision(
                    A, g, ds, rows, gm, retired_in, gold_beside(tiers, ans["groups"], grp["key"])
                )
                # The decision's leader, as the glance has it: never a retired or flagged arm, so the
                # table, its "test vs leader" links and the decision box name the same arm.
                leader = next((r for r in rows if r["arm"] == dec["leader"]), None)
                shown = shown_axes(dec)
                trs = []
                for r in rows:
                    link = (
                        # One pair picked from a group of many: held to the group's family (every
                        # arm in it against the leader), never tested as if it were the only one.
                        f'<a class="btn small" href="{inspect_url([r["arm"], leader["arm"]], "../", baseline=leader["arm"], metric=gm, family=max(len(dec["eligible"]) - 1, 1))}">test vs leader</a>'
                        if leader and r["arm"] != leader["arm"]
                        else ("leader" if leader and r is leader else "")
                    )
                    tag = (
                        ' <small class="filed" title="its config names this goal (goal: in the config)">filed</small>'
                        if r["filed"]
                        else ""
                    ) + (' <span class="tag-base">baseline</span>' if r.get("baseline") else "")
                    if dec["recommended"] == r["arm"]:
                        tag += ' <span class="tag-rec">recommended</span>'
                    gone = retired_round(retired_in, r["arm"])
                    if gone:
                        tag += f' <small class="retired" title="dropped in that round, with its reason">retired in {e(gone)}</small>'
                    trs.append(
                        {
                            # A retired arm stays listed (its numbers are history) but reads as out of play.
                            "cls": (row_kind(r, tiers) + (" t-retired" if gone else "")).strip(),
                            "cells": [
                                arm_link(r["arm"], r["label"], "../") + tag,
                                f'<span data-v="{r["mean"]}">{fmt(r["mean"])}</span>',
                                f'<span data-v="{r["n"]}">{r["n"]}</span>',
                                *(axis_cell(ax, dec["rows"][r["arm"]][ax["name"]]) for ax in shown),
                                e("; ".join(r["flags"] + dec["out"].get(r["arm"], [])) or "—"),
                                link,
                            ],
                        }
                    )
                arms = [r["arm"] for r in rows][:INSPECT_MAX]
                what = grp["key"]
                inner += f'<h3 class="sub">{"scored by " + e(what) if what.startswith("judge ") else "scored against " + e(what)}</h3>'
                if leader and len(arms) > 1:
                    inner += (
                        f'<p><a class="btn" href="{inspect_url(arms, "../", baseline=leader["arm"], metric=gm)}">'
                        "Test every arm in this group against its leader</a></p>"
                    )
                inner += decision_html(
                    dec, {r["arm"]: r["label"] for r in rows}, g, "../", baseline_gap(A, dec, rows, gm)
                )
                inner += table(
                    f"ans{n}_{gi}",
                    [
                        "arm",
                        f"mean {e(gm)}",
                        f"{e(A.item_word)}s",
                        *(e(axis_title(ax)) for ax in shown),
                        "flags",
                        "",
                    ],
                    trs,
                )
                inner += tradeoff_charts(dec, {r["arm"]: r["label"] for r in rows}, gm)
        body += block(f"{n:02d}", f"{ds}{' · ' + ans['role'] if ans['role'] else ''}", inner)
        n += 1
    write(
        out,
        f"g/{slug(g['goal_id'])}.html",
        page(
            g.get("title") or g["goal_id"],
            body,
            1,
            "goals",
            nav=nav,
            item=A.item_word,
            elsewhere=(("goals", {"goal": g["goal_id"]}),),
        ),
    )


def retired_in_of(A: Adapter, g: dict) -> dict:
    """{arm id: round_id} for every arm a round of this goal retired. An adapter that gives no
    arm ids (`retired_arms`) retires by config id: the key is then the config id."""
    rfn = getattr(A, "rounds", None)
    out: dict = {}
    for r in rfn() if callable(rfn) else []:
        if r.get("goal") != g["goal_id"]:
            continue
        keys = r.get("retired_arms")
        for k in keys if keys is not None else [x.get("config_id") for x in r.get("retired") or []]:
            out[k] = r["round_id"]
    return out


def retired_round(retired_in: dict, arm: str) -> str | None:
    """The round that retired this arm: by its arm id, else by its config id."""
    return retired_in.get(arm) or retired_in.get(arm.rsplit("/", 1)[-1])


def _retired_arms(r: dict) -> set:
    """The arm ids (or, from an adapter without them, config ids) a round retired."""
    keys = r.get("retired_arms")
    return set(keys if keys is not None else [x.get("config_id") for x in r.get("retired") or []])


def axis_ratios(dec: dict, arm: str, base: str) -> list[str]:
    """The arm against the baseline on each axis beside quality, as ratios ("cost 0.1×"). An axis
    either has no number for is left out; two zeros read "same"."""
    out: list[str] = []
    if arm == base or arm not in dec["rows"] or base not in dec["rows"]:
        return out
    for ax in shown_axes(dec):
        a, b = dec["rows"][arm][ax["name"]]["value"], dec["rows"][base][ax["name"]]["value"]
        stat = "" if ax["stat"] == "mean" else f" {ax['stat']}"
        if a is None or b is None:
            continue
        if b == 0:
            out.append(f"{ax['name']}{stat} same" if a == 0 else f"{ax['name']}{stat} from 0")
        else:
            r = a / b
            out.append(f"{ax['name']}{stat} {r:,.0f}×" if r >= 10 else f"{ax['name']}{stat} {r:.2g}×")
    return out


def group_decision(
    A: Adapter, g: dict, ds: str, rows: list, gm: str, retired_in: dict, gold: str | None = None
) -> dict:
    """The goal's decision over one group of arms on one dataset (axes.decide): its axes, limits,
    the quality leader, the tie and the tie-break. A judge's group decides on the judge's score;
    an arm a round retired is shown, never recommended. `gold`: this group is scored against
    silver and that gold reference's group is on the same dataset, so gold decides and this group
    only shows its leader; so does a group measured by unvalidated judges."""
    from evaluation_harness import axes  # noqa: PLC0415

    crit = g.get("success_criteria") or {}
    goal = g
    if gm != (crit.get("primary") or {}).get("measure"):
        own = {k: v for k, v in (crit.get("axes") or {}).items() if k != "quality"}
        goal = {
            **g,
            "success_criteria": {**crit, "primary": {"measure": gm, "direction": "higher"}, "axes": own},
        }
    arms = {
        r["arm"]: {
            "label": r["label"],
            "flags": list(r["flags"]) + (["retired"] if retired_round(retired_in, r["arm"]) else []),
            "scores": A.scores(r["arm"]),
        }
        for r in rows
    }
    machines = {r["arm"]: r.get("machine", "") for r in rows}
    dec = axes.decide(goal, arms, lambda m: "lower" if A.lower_is_better(m, ds) else None, machines) | {
        "goal": goal
    }
    if not decides_on(g, ds):
        # The goal never decides here (a dev slice, a generalization check): the leader stands, the
        # recommendation does not.
        role = next((d.get("role") for d in g.get("datasets") or [] if d.get("dataset_id") == ds), "") or ""
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still tied"))],
            f"The goal does not decide on {ds}"
            + (f" ({role})" if role else "")
            + ": shown, not recommended.",
        ]
    elif gold:
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still tied"))],
            (
                f"Scored against silver, beside {gold}: gold decides on {ds}; this group is shown, not "
                "recommended. Silver is not what the goal decides on: a model's opinion (its author's "
                "family ranks higher on it) or what production recorded afterwards; its caveat says which."
            ),
        ]
    elif gm.endswith("_unvalidated"):
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still tied"))],
            (
                f"{gm}: judges never compared with people for this use, a trial rather than a "
                "measurement; this group is shown, not recommended."
            ),
        ]
    return dec


def gold_beside(tiers: dict, groups: list, key: str) -> str | None:
    """The gold reference a silver-scored group sits beside on its dataset, or None: a silver group
    with a gold one next to it never recommends (group_decision's `gold`)."""
    if ref_tier(tiers, key) != "silver":
        return None
    return next((x["key"] for x in groups if ref_tier(tiers, x["key"]) == "gold"), None)


def decides_on(g: dict, ds: str) -> bool:
    """Whether the goal decides on this dataset (`decides: false` on a goal dataset: never)."""
    return next((d.get("decides", True) for d in g.get("datasets") or [] if d.get("dataset_id") == ds), True)


def baseline_gap(A: Adapter, dec: dict, rows: list, gm: str) -> str:
    """When the rule recommends another arm than the promoted baseline in this group: by how much
    the recommended arm differs on quality, and whether the paired test separates them. Both can
    be right: the rule follows the strategy, the baseline is a person's decision."""
    from evaluation_harness import stats  # noqa: PLC0415

    rec = dec["recommended"]
    base = next((r for r in rows if r.get("baseline")), None)
    if not rec or base is None or base["arm"] == rec:
        return ""
    labels = {r["arm"]: r["label"] for r in rows}
    higher = dec["axes"][0]["direction"] == "higher"
    series = {a: (A.scores(a).get(gm) or {}).get("values") or {} for a in (rec, base["arm"])}
    row = (stats.compare(series, base["arm"], higher_is_better=higher, family=1).get("rows") or [None])[0]
    if not row or row.get("p") is None:
        return ""
    return (
        f"Differs from the promoted baseline, {labels[base['arm']]}: {labels[rec]} is "
        f"{row['delta']:+.3f} on {gm} against it, {row.get('verdict', '')} (p {fmt_p(row['p'])}). "
        "The rule recommends by the goal's strategy; the baseline is a person's decision "
        "(evh run-promote)."
    )


def shown_axes(dec: dict) -> list:
    """The axes beside quality that some arm in the group records (cost counts its tokens too)."""
    return [
        ax
        for ax in dec["axes"][1:]
        if any(
            row[ax["name"]]["n"] or (row[ax["name"]].get("tokens") or {}).get("n")
            for row in dec["rows"].values()
        )
    ]


def axis_cell(ax: dict, cell: dict) -> str:
    """A table cell for one arm on one axis, sortable by its value, marked when past the limit."""
    v = cell.get("value")
    over = cell.get("within") is False
    vs = (cell.get("vs_leader") or {}).get("verdict")
    title = (f"vs the quality leader: {vs}" if vs else "") + ("; past the limit" if over else "")
    attrs = f'data-v="{v if v is not None else ""}"' + (' class="over"' if over else "")
    attrs += f' title="{e(title)}"' if title else ""
    return f"<span {attrs}>{e(cell_text(ax, cell))}</span>"


def decision_html(dec: dict, labels: dict, g: dict, up: str, gap: str = "") -> str:
    """What the goal's rule concludes for this group, and why, in the goal's own terms; `gap`
    says how it differs from the promoted baseline (baseline_gap)."""

    if not dec["rows"]:
        return ""
    rec = dec["recommended"]
    head = (
        f"Recommended: <b>{arm_link(rec, labels[rec], up)}</b>"
        if rec
        else "Shown, not recommended"
        if dec.get("shown_only")
        else "No single arm recommended" + (" yet" if dec["leader"] else ": no arm is eligible")
    )
    weighs = "; ".join(axis_title(a) for a in dec["axes"])
    why = "".join(f"<li>{e(w)}</li>" for w in dec["why"])
    if gap:
        why += f'<li class="gap"><b>{e(gap)}</b></li>'
    return (
        f'<div class="decision"><p class="lead">{head}</p><ul class="small">{why}</ul>'
        f'<p class="small muted">Strategy <b>{e(strategy_of(dec["goal"]))}</b> '
        f"({e(STRATEGIES[strategy_of(dec['goal'])])}). Weighs {e(weighs)}. Among arms tied on quality, "
        f"the tie-break is {e(', '.join(tie_break_of(dec['goal'])))}. The rule recommends; promoting "
        "is <code>evh run-promote</code>; the goal chooses its strategy (<code>strategy:</code>).</p></div>"
    )


def tradeoff_charts(dec: dict, labels: dict, quality_name: str) -> str:
    """Quality against each other axis, for the eligible arms, the frontier drawn: the trade-off at
    a glance. Two to a row."""
    from evaluation_harness import catalog_charts as ch  # noqa: PLC0415

    q = dec["axes"][0]
    # The arms the rule could recommend: not over a limit, not flagged (the reference's author,
    # too few items, a format the goal does not take), not retired.
    eligible = dec["eligible"]
    charts = []
    for ax in shown_axes(dec):
        pts = [
            (
                dec["rows"][a][ax["name"]]["value"],
                dec["rows"][a]["quality"]["value"],
                labels[a],
                (
                    f"{labels[a]}: {quality_name} {fmt(dec['rows'][a]['quality']['value'])}, {ax['name']} "
                    f"{fmt(dec['rows'][a][ax['name']]['value'])}"
                ),
            )
            for a in eligible
            if dec["rows"][a][ax["name"]]["value"] is not None
            and dec["rows"][a]["quality"]["value"] is not None
        ]
        stat = "" if ax["stat"] == "mean" else f" {ax['stat']}"
        unit = f" ({ax['unit']})" if ax.get("unit") else ""
        svg = ch.scatter(
            pts,
            f"{ax['name']}{stat}{unit}",
            quality_name,
            lower_x=ax["direction"] == "lower",
            higher_y=q["direction"] == "higher",
            x_limit=ax.get("limit"),
            y_limit=q.get("limit"),
            fmt_x=(lambda v: f"${v:.4f}") if ax["name"] == "cost" and ax["measure"] == "cost_usd" else None,
            width=HALF,
        )
        if svg:
            charts.append(f"<div>{svg}</div>")
    return f'<div class="duo">{"".join(charts)}</div>' if charts else ""


def metric_index(A: Adapter, by_ds: dict) -> dict:
    """{metric: {"datasets": {dataset: arms recording it}, "goals": [goals deciding on it],
    "weighs": [goals weighing it as an axis: cost, speed or their own (ADR-0006)]}}."""
    out: dict = {}

    def entry(m: str) -> dict:
        return out.setdefault(m, {"datasets": {}, "goals": [], "weighs": []})

    for ds, v in by_ds.items():
        for a in v["arms"]:
            for m in a["means"]:
                entry(m)["datasets"].setdefault(ds, 0)
                out[m]["datasets"][ds] += 1
    for g in A.goals():
        m = ((g.get("success_criteria") or {}).get("primary") or {}).get("measure")
        if m:
            entry(m)["goals"].append(g)
        for ax in axes_of(g)[1:]:
            if ax["role"] != "ignore" and ax["measure"] in out:
                out[ax["measure"]]["weighs"].append(g)
    return out


def render_metrics(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """One page, one row per metric: what it measures, which way is better, where it is recorded,
    and which goals decide on it. A row's anchor is #m-<metric>, which every metric link uses."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    fn = getattr(A, "metric_descriptions", None)
    project = fn() if callable(fn) else {}
    idx = metric_index(A, by_ds)
    w = window(A, by_ds)
    rows, period_rows = [], period_metrics(A, by_ds)
    for m in sorted(idx, key=lambda k: (k.startswith(("total_", "self_family_", "resumed")), k)):
        where = idx[m]
        lower = any(A.lower_is_better(m, ds) for ds in where["datasets"]) if where["datasets"] else False
        # Direction first: cost, tokens and latency are "neutral" to the tests but lower is better.
        better = "lower" if lower else ("neutral: a description" if A.is_neutral(m) else "higher")
        text = describe_metric(m, project)
        runs = period_rows[m]["runs"]
        # What the metric is for: a goal decides on it, weighs it as an axis, or nobody uses it to
        # choose and it describes (the table sorts and filters on this word).
        role = "decides" if where["goals"] else "weighs" if where["weighs"] else "describes"
        rows.append(
            {
                "id": f"m-{slug(m)}",
                "key": m,
                "made": period_rows[m]["made"],
                "data": {"role": role},
                "cells": [
                    f'<a class="cell-link nowrap" href="{metric_page(m)}"><code>{e(m)}</code></a>',
                    e(role),
                    e(text)
                    if text
                    else '<span class="muted">not described: add it to the adapter\'s '
                    "<code>METRIC_DESCRIPTIONS</code></span>",
                    e(better),
                    "<br>".join(
                        f'<span class="nowrap"><a class="cell-link" href="d/{slug(ds or "none")}.html">'
                        f'{e(ds or "(none)")}</a> <span class="muted small">{n} arm{"s" if n != 1 else ""}</span></span>'
                        for ds, n in sorted(where["datasets"].items())
                    )
                    or "—",
                    "<br>".join(
                        f'<a class="cell-link" href="g/{slug(g["goal_id"])}.html">{e(g.get("title") or g["goal_id"])}</a>'
                        for g in where["goals"]
                    )
                    + (
                        ("<br>" if where["goals"] else "")
                        + '<span class="muted small">weighed by</span> '
                        + ", ".join(
                            f'<a class="cell-link" href="g/{slug(g["goal_id"])}.html">{e(g.get("title") or g["goal_id"])}</a>'
                            for g in where["weighs"]
                        )
                        if where["weighs"]
                        else ""
                    )
                    or "—",
                    f'<span data-flow="arms" data-line>{len({x[1] for x in runs})}</span>',
                ],
            }
        )
    write_period_rows(out, "metrics", period_rows)
    body = hero(
        "metrics",
        "Metrics",
        "What each number on these pages measures, which way is better, where it is recorded, and "
        "which goals decide on it. A project describes its own metrics with "
        "<code>METRIC_DESCRIPTIONS</code> in its adapter; the harness describes its own.",
        cp.bar(w["first"], w["until"]),
    )
    body += block(
        "01",
        "metrics",
        group_chips("metrics", (("", "no grouping"), ("role", "role")))
        + cp.row_chips("metrics", "metrics")
        + table(
            "metrics",
            [
                "metric",
                "role",
                "what it measures",
                "better",
                "recorded on",
                "decides · weighs",
                "arms recording it in period",
            ],
            rows,
            "filter metrics (decides, weighs, describes…)",
            period=True,
            noun="metric",
        ),
    )
    write(
        out,
        "metrics.html",
        page(
            "Metrics",
            body,
            0,
            "metrics",
            (*PERIOD_SCRIPTS("metrics"), "assets/group.js"),
            nav=nav,
            item=A.item_word,
            elsewhere=(("metrics", {}),),
        ),
    )


TIER_WORDS = {
    "gold": "Gold: written or checked by a person. Every arm scored against it is measured against "
    "what a person signed.",
    "silver": "Silver: written by a model. Consistent, not correct: good for ranking arms against "
    "each other, never a claim that any of them is right. The arm that wrote it is graded against "
    "its own outputs.",
}


def render_references(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """One page per reference: what it is, who wrote it, and every arm scored against it."""
    for ds, v in by_ds.items():
        tiers = {r["id"]: r["tier"] for r in v["refs"]}
        for r in v["refs"]:
            scored = [a for a in v["arms"] if a["reference"] == r["id"] and not a["judge"]]
            facts = [
                ("tier", r["tier"]),
                ("dataset", f'<a class="cell-link" href="../d/{slug(ds or "none")}.html">{e(ds)}</a>'),
                (f"{A.item_word}s", e(r.get("items", "")) if r.get("items") is not None else ""),
                ("written by", _author_link(r, v, "../") if r.get("author") else ""),
                ("from the run", f"<code>{e(r['from_run'])}</code>" if r.get("from_run") else ""),
                ("model", e(r.get("model") or "")),
                ("created", e(r.get("created_at") or "")),
            ]
            dl = "".join(f"<dt>{e(k)}</dt><dd>{v_}</dd>" for k, v_ in facts if v_)
            rows = [
                {
                    "cls": row_kind(a, tiers),
                    "cells": [
                        arm_link(a["arm"], a["label"], "../"),
                        metric_link(a["metric"], "../"),
                        f'<span data-v="{a["mean"] if a["mean"] is not None else ""}">{fmt(a["mean"])}</span>',
                        f'<span data-v="{a["n"]}">{a["n"]}</span>',
                        f'<a class="btn small" href="{inspect_url([a["arm"]], "../")}">inspect</a>',
                    ],
                }
                for a in sorted(scored, key=lambda a: (a["metric"], -(a["mean"] or 0)))
            ]
            body = hero("reference", f"<code>{e(r['id'])}</code>", e(TIER_WORDS.get(r["tier"], "")))
            body += block("01", "what it is", f'<dl class="kv">{dl}</dl>')
            body += block(
                "02",
                f"scored against it · {len(rows)}",
                (ROW_KEY + table("scored", ["arm", "metric", "mean", f"{e(A.item_word)}s", ""], rows))
                if rows
                else '<p class="muted">No arm is scored against it yet.</p>',
            )
            write(
                out,
                reference_page(r["id"]),
                page(
                    r["id"],
                    body,
                    1,
                    "",
                    nav=nav,
                    item=A.item_word,
                    elsewhere=(("references", {"reference-id": r["id"]}),),
                ),
            )


def _author_link(r: dict, v: dict, up: str) -> str:
    """The config that wrote a reference, linked to its arm on the reference's dataset when the
    catalog has one (its measured run, not a rescored copy)."""
    author = r.get("author") or ""
    arms = [a for a in v.get("arms", []) if a["arm"].rsplit("/", 1)[-1] == author]
    arms.sort(key=lambda a: (bool(a["judge"]), a["arm"].split("/", 1)[0] != "runs"))
    return arm_link(arms[0]["arm"], author, up) if arms else f"<code>{e(author)}</code>"


def _config_link(A: Adapter, r: dict, config_id: str) -> str:
    """A config named in a round, linked to its arm on the round's dataset when it has one."""
    fn = getattr(A, "arm_of", None)
    arm = (
        fn(r.get("dataset_id", ""), config_id)
        if callable(fn)
        else f"runs/{r.get('dataset_id', '')}/{config_id}"
    )
    return arm_link(arm, config_id, "../") if arm in set(A.arms()) else f"<code>{e(config_id)}</code>"


def _siblings(by_ds: dict, a: dict, ds: str) -> list:
    """The same config on the same dataset, scored other ways (gold, silver, a judge)."""
    cid = a["arm"].rsplit("/", 1)[-1]
    return [x for x in by_ds[ds]["arms"] if x["arm"] != a["arm"] and x["arm"].rsplit("/", 1)[-1] == cid]


def render_arm(A: Adapter, a: dict, ds: str, by_ds: dict, out: Path, nav: list) -> None:
    """One arm: what it is scored against and for which goal, every metric it records, its runs,
    its config, the conditions it ran under, and the same config scored other ways."""
    v = by_ds[ds]
    tiers = {r["id"]: r["tier"] for r in v["refs"]}
    goals = {g["goal_id"]: g for g in A.goals()}
    facts = [
        ("dataset", dataset_link(ds, "../")),
        ("scored against", scored_against(a, "../")),
        ("goal", goal_link(goals[a["goal"]], "../") if a.get("goal") in goals else e(a.get("goal") or "")),
        ("runs", str(a["runs"])),
        (
            "headline",
            metric_link(a["metric"], "../") + (f" {fmt(a['mean'])}" if a["mean"] is not None else ""),
        ),
        ("last run", e(a["last"][:16].replace("T", " "))),
    ]
    if a.get("wrote"):
        facts.append(
            ("note", "wrote the reference it is scored against: its row measures agreement with itself")
        )
    dl = "".join(f"<dt>{e(k)}</dt><dd>{x}</dd>" for k, x in facts if x)
    base = (v.get("baselines") or [None])[-1]
    btns = [f'<a class="btn" href="{inspect_url([a["arm"]], "../")}">Inspect it</a>']
    group = [
        x["arm"]
        for x in v["arms"]
        if x["metric"] == a["metric"]
        and bool(x["judge"]) == bool(a["judge"])
        and (x["judge"] or x["reference"]) == (a["judge"] or a["reference"])
    ]
    if base and base.get("arm") and base["arm"] != a["arm"] and base["arm"] in group:
        btns.append(
            f'<a class="btn" href="{inspect_url([a["arm"], base["arm"]], "../", baseline=base["arm"], metric=a["metric"])}">Against the baseline</a>'
        )
    if len(group) > 1:
        btns.append(
            f'<a class="btn" href="{inspect_url(group[:INSPECT_MAX], "../", metric=a["metric"])}">With the {len(group)} arms scored the same way</a>'
        )
    body = hero(
        "arm",
        e(a["label"]) + (' <span class="tag-base">baseline</span>' if a.get("baseline") else ""),
        f"One config on {dataset_link(ds, '../')}, scored one way; its repeats averaged per {e(A.item_word)}.",
        f'<dl class="kv">{dl}</dl><p class="btns">{"".join(btns)}</p>',
    )
    n = 1
    rows = [
        [
            metric_link(m, "../"),
            f'<span data-v="{mean}">{metric_value(A, m, mean)}</span>',
            f'<span data-v="{k}">{k}</span>',
            "lower" if A.lower_is_better(m, ds) else ("neutral" if A.is_neutral(m, ds) else "higher"),
        ]
        for m, (mean, k) in sorted(a["means"].items(), key=lambda kv: (kv[0] != a["metric"], kv[0]))
    ]
    body += block(
        f"{n:02d}", "metrics", table("armmetrics", ["metric", "mean", f"{e(A.item_word)}s", "better"], rows)
    )
    n += 1
    sc = A.scores(a["arm"])
    cs = [(ax, cell_of(ax, sc)) for ax in builtin_axes()]
    if any(c["n"] or (c.get("tokens") or {}).get("n") for _, c in cs):
        kv = "".join(f"<dt>{e(axis_title(ax))}</dt><dd>{e(cell_text(ax, c))}</dd>" for ax, c in cs)
        body += block(
            f"{n:02d}",
            "cost and speed",
            f'<dl class="kv">{kv}</dl><p class="small muted">Per {e(A.item_word)}, over its '
            f"{e(A.item_word)}s: cost as dollars and tokens (a local model is free but still uses "
            "tokens), speed as the median and the slow tail (p95). A goal that names this arm weighs "
            "them in its decision.</p>",
        )
        n += 1
    if a["run_list"]:
        rrows = [
            [
                f"<code>{e(r['run_id'])}</code>",
                f'<span data-v="{e(r.get("created_at") or "")}">{e((r.get("created_at") or "")[:16].replace("T", " "))}</span>',
                f'<span data-v="{r.get("items") or ""}">{r.get("items") if r.get("items") is not None else "—"}</span>',
                f'<span data-v="{r.get("cost_usd") if r.get("cost_usd") is not None else ""}">'
                + (f"${r['cost_usd']:.6f}" if isinstance(r.get("cost_usd"), (int, float)) else "—")
                + "</span>",
                e(r.get("derived") or "measured"),
            ]
            for r in a["run_list"]
        ]
        body += block(
            f"{n:02d}", "runs", table("armruns", ["run", "made", f"{e(A.item_word)}s", "cost", "how"], rrows)
        )
        n += 1
    cfg_fn = getattr(A, "arm_config", None)
    cfg = cfg_fn(a["arm"]) if callable(cfg_fn) else {}
    if cfg.get("params"):
        kv = "".join(
            f"<dt>{e(k)}</dt><dd><code>{e(json.dumps(x) if not isinstance(x, str) else x)}</code></dd>"
            for k, x in sorted(cfg["params"].items())
        )
        extra = (
            f'<p class="small muted">config <code>{e(cfg.get("config_id", ""))}</code>'
            + (f" · adapter <code>{e(cfg['adapter'])}</code>" if cfg.get("adapter") else "")
            + " · credentials are never shown</p>"
        )
        body += block(f"{n:02d}", "config", extra + f'<dl class="kv">{kv}</dl>')
        n += 1
    cond_fn = getattr(A, "conditions", None)
    cond = cond_fn(a["arm"]) if callable(cond_fn) else {}
    if cond:
        kv = "".join(f"<dt>{e(k)}</dt><dd><code>{e(x)}</code></dd>" for k, x in sorted(cond.items()))
        body += block(f"{n:02d}", "conditions", f'<dl class="kv">{kv}</dl>')
        n += 1
    sib = _siblings(by_ds, a, ds)
    if sib:
        srows = [
            {
                "cls": row_kind(x, tiers),
                "cells": [
                    arm_link(x["arm"], x["label"], "../"),
                    scored_against(x, "../"),
                    metric_link(x["metric"], "../"),
                    fmt(x["mean"]),
                ],
            }
            for x in sib
        ]
        body += block(
            f"{n:02d}",
            "the same config, scored other ways",
            ROW_KEY + table("siblings", ["arm", "scored against", "headline", "mean"], srows),
        )
        n += 1
    rfn = getattr(A, "rounds", None)
    cid = a["arm"].rsplit("/", 1)[-1]
    rnds = [
        r
        for r in (rfn() if callable(rfn) else [])
        if a["arm"] in (r.get("arms") or []) or {a["arm"], cid} & _retired_arms(r)
    ]
    if rnds:
        lis = "".join(
            f"<li>{e(r['round_id'])} of {goal_link(goals[r['goal']], '../') if r.get('goal') in goals else e(r.get('goal', ''))}"
            + (" · <b>retired</b>" if {a["arm"], cid} & _retired_arms(r) else " · in play")
            + f" · {e(r.get('status', ''))}</li>"
            for r in rnds
        )
        body += block(f"{n:02d}", "rounds", f"<ul>{lis}</ul>")
        n += 1
    notes = A.notes(a["arm"]) if callable(getattr(A, "notes", None)) else []
    if notes:
        body += block(f"{n:02d}", "notes", "<ul>" + "".join(f"<li>{e(x)}</li>" for x in notes) + "</ul>")
    write(
        out,
        arm_page(a["arm"]),
        page(
            a["label"],
            body,
            1,
            "datasets",
            nav=nav,
            item=A.item_word,
            elsewhere=(("arms", {"arm": a["arm"]}),),
        ),
    )


def cost_or_speed(A: Adapter, m: str) -> str | None:
    """ "cost" or "speed" for a metric measured off the bill or the clock, else None. The
    harness's own names first (cost_usd, latency_ms, tokens), then what the adapter says."""
    from evaluation_harness._common import classify_metrics  # noqa: PLC0415

    known = classify_metrics().get(m)
    if known in ("cost", "speed"):
        return known
    fn = getattr(A, "reference_free", None)
    if callable(fn) and fn(m):
        return "speed" if any(k in m for k in ("latency", "time", "_ms", "_s")) else "cost"
    return None


def metric_value(A: Adapter, m: str, v) -> str:
    """A metric's mean for a table: dollars to six places (a cheap model's $0.000012 is not
    0.000), everything else as fmt."""
    if v is not None and cost_or_speed(A, m) == "cost" and "usd" in m:
        return f"${v:.6f}"
    return fmt(v)


def _kind_of(A: Adapter, m: str, datasets=()) -> str:
    """cost, speed, descriptive or quality, as the harness classifies it. Cost and speed first:
    the tests treat them as neutral (no quality verdict), yet lower is better. A metric that is
    a quality on some datasets and descriptive on others names the others."""
    cs = cost_or_speed(A, m)
    if cs == "cost":
        return "cost: what an item cost, from the bill or the tokens; needs no reference"
    if cs == "speed":
        return "speed: how long an item took, by the clock; needs no reference"
    if A.is_neutral(m):
        return "descriptive: says what the output was, never whether it was good"
    aside = sorted(ds for ds in datasets if A.is_neutral(m, ds))
    return "quality: measured against a reference or by a judge" + (
        f" (descriptive on {', '.join(aside)})" if aside else ""
    )


def render_metric(A: Adapter, m: str, where: dict, by_ds: dict, project: dict, out: Path, nav: list) -> None:
    """One metric: what it measures and how, which way is better, the goals that decide on it,
    and on every dataset the arms that record it, best first, with their spread."""
    from evaluation_harness import catalog_charts as ch  # noqa: PLC0415

    lower = any(A.lower_is_better(m, ds) for ds in where["datasets"]) if where["datasets"] else False
    better = "lower" if lower else ("neutral: a description" if A.is_neutral(m) else "higher")
    summary = describe_metric(m, project)
    details = metric_details(m, project)
    facts = [
        ("better", e(better)),
        ("kind", e(_kind_of(A, m, where["datasets"]))),
        ("decides", ", ".join(goal_link(g, "../") for g in where["goals"]) or "no goal"),
        ("weighed by", ", ".join(goal_link(g, "../") for g in where["weighs"]) or "no goal"),
        ("recorded on", ", ".join(dataset_link(ds, "../") for ds in sorted(where["datasets"])) or "—"),
    ]
    dl = "".join(f"<dt>{e(k)}</dt><dd>{x}</dd>" for k, x in facts)
    about = (
        f'<p class="lead">{e(summary)}</p>'
        if summary
        else '<p class="muted">Not described: add it to the adapter\'s <code>METRIC_DESCRIPTIONS</code>.</p>'
    )
    if details:
        about += f"<p>{e(details)}</p>"
    elif summary and m not in BUILTIN_DETAILS:
        about += (
            '<p class="small muted">A project explains its own metric at length with '
            '<code>METRIC_DESCRIPTIONS = {"' + e(m) + '": {"summary": "…", "details": "…"}}</code>.</p>'
        )
    body = hero("metric", f"<code>{e(m)}</code>", "", f'<dl class="kv">{dl}</dl>')
    body += block("01", "what it measures, and how", about)
    n = 2
    for ds in sorted(where["datasets"]):
        v = by_ds[ds]
        tiers = {r["id"]: r["tier"] for r in v["refs"]}
        arms = [a for a in v["arms"] if m in a["means"]]
        arms.sort(
            key=lambda a: (
                scored_by_rank(a, tiers),
                a.get("reference") or "",
                a["means"][m][0] * (1 if lower else -1),
            )
        )
        rows = [
            {
                "cls": row_kind(a, tiers),
                "cells": [
                    arm_link(a["arm"], a["label"], "../"),
                    f'<span data-v="{a["means"][m][0]}">{metric_value(A, m, a["means"][m][0])}</span>',
                    f'<span data-v="{a["means"][m][1]}">{a["means"][m][1]}</span>',
                    scored_against(a, "../"),
                ],
            }
            for a in arms
        ]
        groups: dict = {}
        for a in arms:
            key = f"judge {a['judge']}" if a["judge"] else (a.get("reference") or "no reference")
            groups.setdefault(key, []).append((a["means"][m][0], a["label"]))
        chart = (
            ch.strip(groups, f"{m} per arm on {ds}, by what each is scored against", lower=lower)
            if len(arms) > 1
            else ""
        )
        body += block(
            f"{n:02d}",
            f"on {ds}",
            chart
            + ROW_KEY
            + table(f"on{n}", ["arm", f"mean {e(m)}", f"{e(A.item_word)}s", "scored against"], rows),
        )
        n += 1
    write(
        out,
        metric_page(m),
        page(m, body, 1, "metrics", nav=nav, item=A.item_word, elsewhere=(("metrics", {"metric": m}),)),
    )


def render_reference_index(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """Every reference: its tier, dataset, author, when it was made, how many arms it scores, and
    how many it scored in the period."""
    from evaluation_harness import catalog_periods as cp  # noqa: PLC0415

    w = window(A, by_ds)
    rows, period_rows = [], period_references(A, by_ds)
    for ds, v in sorted(by_ds.items()):
        for r in v["refs"]:
            scored = [a for a in v["arms"] if a["reference"] == r["id"] and not a["judge"]]
            rows.append(
                {
                    "cls": "t-silver" if r["tier"] == "silver" else "",
                    "key": r["id"],
                    "made": (r.get("created_at") or "")[:10],
                    "cells": [
                        reference_link(r["id"]),
                        e(r["tier"]),
                        dataset_link(ds),
                        f'<span data-v="{r.get("items") or ""}">{r.get("items") if r.get("items") is not None else "—"}</span>',
                        _author_link(r, v, "") if r.get("author") else "—",
                        e((r.get("created_at") or "")[:10]) or "—",
                        f'<span data-v="{len(scored)}">{len(scored)}</span>',
                        f'<span data-flow="arms">{len({x[1] for x in period_rows[r["id"]]["runs"]})}</span>',
                        f'<span data-flow="runs" data-line>{len(period_rows[r["id"]]["runs"])}</span>',
                    ],
                }
            )
    write_period_rows(out, "references", period_rows)
    body = hero(
        "references",
        "References",
        "What arms are scored against. Gold is written or checked by a person; silver is written by "
        "a model, consistent rather than correct, and its author is graded against its own outputs.",
        cp.bar(w["first"], w["until"]),
    )
    body += block(
        "01",
        "references",
        cp.row_chips("references", "references")
        + table(
            "references",
            [
                "reference",
                "tier",
                "dataset",
                f"{e(A.item_word)}s",
                "written by",
                "created",
                "arms scored",
                "arms scored in period",
                "runs in period",
            ],
            rows,
            "filter references",
            period=True,
        )
        if rows
        else '<p class="muted">No references yet: gold goes in <code>data/references/gold/&lt;dataset&gt;/</code>, '
        "or make one from a run with <code>evh reference-create --from-run</code>.</p>",
    )
    write(
        out,
        "references.html",
        page(
            "References",
            body,
            0,
            "references",
            PERIOD_SCRIPTS("references"),
            nav=nav,
            item=A.item_word,
            elsewhere=(("references", {}),),
        ),
    )


def render_inspect(
    A: Adapter, out: Path, page_fn=page, serve: str = "evh catalog-serve", *, pages: bool = False, **page_kw
) -> None:
    """The inspector shell; assets/inspect.js fills it from the local server's /api/. `pages`: the
    catalog beside it has a page per arm and per metric (the harness's own build), so the
    inspector links to them; a project's own builder without them leaves it False."""
    arms = {a: A.describe(a)["dataset"] for a in sorted(A.arms())}
    write(
        out,
        "runs.js",
        "window.RUNS=" + json.dumps(arms) + ";\n" + ("window.CATALOG_PAGES=true;\n" if pages else ""),
    )
    item = A.item_word
    body = (
        '<section class="hero slim"><div class="wrap"><p class="kicker">inspector</p>'
        f"<h1>Run inspector</h1><p class=dek>Per-{e(item)} scores for the selected arms, each "
        f"tested against a baseline with the harness's paired test (exact p up to 30 {e(item)}s, "
        "Holm across the family). Click a row to see what each arm produced.</p>"
        '<div id="pick" class="pick"></div></div></section>'
        '<section class="block tight"><div class="wrap" id="app">'
        f'<p class="muted">Loading… (this page needs <code>{e(serve)}</code>; opened '
        "from disk it cannot read runs.)</p></div></section>"
    )
    write(
        out,
        "inspect.html",
        page_fn(
            "Inspector",
            body,
            0,
            "inspect",
            ("runs.js", "assets/inspect.js"),
            item=item,
            serve=serve,
            elsewhere=(("inspect", {}),),
            **page_kw,
        ),
    )


def share_card(title: str, brand: str, body: str) -> str:
    """What a shared link shows (the page stays noindex: a card is for a person pasting a link, not
    for search): the page's title, its dek as the description, and, with --card URL, an image."""
    m = re.search(r"<p class=\"?dek\"?>(.*?)</p>", body, re.S)
    desc = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
    desc = " ".join(desc.split()) or f"{title}: from the project's committed runs, every number recomputed."
    desc = desc if len(desc) <= 200 else desc[:197].rsplit(" ", 1)[0] + "…"
    tags = [
        f'<meta name="description" content="{e(desc)}">',
        f'<meta property="og:title" content="{e(title)} · {e(brand)}">',
        f'<meta property="og:description" content="{e(desc)}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{e(brand)}">',
        f'<meta name="twitter:card" content="{"summary_large_image" if CARD else "summary"}">',
    ]
    if CARD:
        tags.append(f'<meta property="og:image" content="{e(CARD)}">')
    return "\n".join(tags)


def elsewhere_line(cmds: tuple) -> str:
    """The footer's "this page elsewhere": each command in the terminal and, when the deployment
    names its MCP server (--mcp), the same as a tool call. The inspector's line is filled in by
    inspect.js from the arms picked (an empty argument set here)."""
    if not cmds:
        return ""

    def term(cmd: str, args: dict) -> str:
        return " ".join(["evh", cmd, *(f"--{k} {v}" for k, v in args.items())])

    terms = " · ".join(f"<code>{e(term(c, a))}</code>" for c, a in cmds)
    line = f"This page in the terminal: <span data-elsewhere=term>{terms}</span>"
    if MCP:
        calls = " · ".join(
            f"<code>{e(c)}</code>" + (f" with <code>{e(json.dumps(a))}</code>" if a else "") for c, a in cmds
        )
        line += (
            f". From an agent: the tool <span data-elsewhere=mcp>{calls}</span> at <code>{e(MCP)}</code> "
            f'(<a href="{e(MCP_HOWTO)}" rel="noopener">how to connect</a>)'
        )
    return f'<p class="small elsewhere" id="elsewhere" data-mcp="{e(MCP)}">{line}.</p>'


def write_search(A: Adapter, by_ds: dict, out: Path) -> None:
    """Write the search index as a JavaScript file."""
    write(
        out,
        "search.js",
        "window.CATALOG=" + json.dumps(search_index(A, by_ds), separators=(",", ":")) + ";\n",
    )


def search_index(A: Adapter, by_ds: dict) -> list[dict]:
    """What the search box searches: datasets, arms, references, metrics and goals, each with
    a kind (k), a title (t), a description (d), a page (u) and the text matched (s)."""
    idx = []
    for ds, v in by_ds.items():
        idx.append(
            {
                "k": "dataset",
                "t": ds,
                "d": f"{len(v['arms'])} arms",
                "u": f"d/{slug(ds or 'none')}.html",
                "s": f"{ds} {' '.join(a['label'] for a in v['arms'])}".lower(),
            }
        )
        for a in v["arms"]:
            idx.append(
                {
                    "k": "arm",
                    "t": a["label"],
                    "d": f"{ds} · {a['metric']}",
                    "u": arm_page(a["arm"]),
                    "id": a["arm"],
                    "s": f"{a['label']} {ds} {a['metric']}".lower(),
                }
            )
        for r in v["refs"]:
            idx.append(
                {
                    "k": "reference",
                    "t": r["id"],
                    "d": f"{r['tier']} · {ds}",
                    "u": reference_page(r["id"]),
                    "s": f"{r['id']} {r['tier']} {ds} {r.get('author') or ''}".lower(),
                }
            )
    for m in metric_index(A, by_ds):
        idx.append({"k": "metric", "t": m, "d": "metric", "u": metric_page(m), "s": m.lower()})
    for g in A.goals():
        idx.append(
            {
                "k": "goal",
                "t": g.get("title") or g["goal_id"],
                "d": g.get("statement", "")[:120],
                "u": f"g/{slug(g['goal_id'])}.html",
                "s": f"{g['goal_id']} {g.get('title', '')} {g.get('statement', '')}".lower(),
                "id": g["goal_id"],
            }
        )
    return idx


def build(A: Adapter, out: Path, sections: tuple = ()) -> dict:
    """Build all catalog pages and return statistics. `sections` are the parts of the publication
    the catalog belongs to, (label, url) each, "." for the catalog itself: the header's switcher."""
    global SECTIONS
    SECTIONS = tuple(sections)
    nav = NAV
    if out.exists():
        shutil.rmtree(out)
    copy_assets(out)
    by_ds = collect(A)
    write_periods(A, by_ds, out)
    render_home(A, by_ds, out, nav)
    render_activity(A, by_ds, out, nav)
    from evaluation_harness.catalog_arms import render_arms  # noqa: PLC0415

    render_arms(A, by_ds, out, nav)
    render_datasets(A, by_ds, out, nav)
    for ds, v in by_ds.items():
        v["versions"] = _version_links(by_ds, ds, "../")
        render_dataset(A, ds, v, out, nav)
        for a in v["arms"]:
            render_arm(A, a, ds, by_ds, out, nav)
    n_goals = render_goals(A, by_ds, out, nav)
    render_metrics(A, by_ds, out, nav)
    fn = getattr(A, "metric_descriptions", None)
    project = fn() if callable(fn) else {}
    for m, where in metric_index(A, by_ds).items():
        render_metric(A, m, where, by_ds, project, out, nav)
    render_references(A, by_ds, out, nav)
    render_reference_index(A, by_ds, out, nav)
    write_search(A, by_ds, out)
    render_inspect(A, out, nav=nav, pages=True)
    return {
        "goals": n_goals,
        "datasets": len(by_ds),
        "arms": sum(len(v["arms"]) for v in by_ds.values()),
        "configs": _n_configs(by_ds),
        "references": sum(len(v["refs"]) for v in by_ds.values()),
    }


#: Where the run inspector's API answers, written into every page (data-api) for its scripts:
#: /api/ under `evh catalog-serve`; a deployment that serves the catalog under a path says so
#: with --api (this repository's: /catalog/api/ on evals.humancopilot.eu).
API = "/api/"
#: HTML a deployment adds to every page's <head> (--head FILE): its analytics, a verification
#: tag. The harness adds none of its own.
HEAD = ""
#: HTML a deployment puts on the overview, under its description (--about FILE): which project
#: this catalog shows and where its findings are. None by default.
ABOUT = ""
#: The parts of the publication this catalog belongs to (--link), (label, url) each, "." for the
#: catalog itself: one switcher heads every page, the catalog marked. None by default.
SECTIONS: tuple = ()
#: The product's name beside the logo (--brand): the deployment's own, else "eval catalog".
BRAND = "eval catalog"
#: Where the project's files can be read (--repo), ending in "/": a project path in a goal's links
#: or at the start of a guardrail's source becomes a link to it. None by default, and then a path
#: is named as text, since the static pages cannot know where the project is hosted.
REPO = ""
#: The deployment's MCP server (--mcp URL): every page's footer then names its tool call beside its
#: terminal command, and how to connect. None by default: a page names only its command.
MCP = ""
#: The image a shared link's card shows (--card URL, 1200x630): a deployment's own. None by default,
#: and then the card is title and description only.
CARD = ""
#: How to connect an agent to it: the harness's own guide (the package's docs, not a deployment's).
MCP_HOWTO = "https://github.com/chipi/eval-harness/blob/main/harness/docs/INTEGRATION.md#for-an-agent-evh-mcp"
#: A project path at the start of a guardrail's source ("research/REPORT.md, §3.4").
_PATH_HEAD = re.compile(r"^((?:[\w.-]+/)+[\w.-]+\.\w+|[\w.-]+\.(?:md|json|yaml|yml|csv|txt))(.*)$", re.S)


def project_path(text: str) -> str:
    """A project path as a link when --repo says where the project is, else as code."""
    return f'<a href="{e(REPO + text)}"><code>{e(text)}</code></a>' if REPO else f"<code>{e(text)}</code>"


def _common_prog() -> str | None:
    """`evh <command>` for --help (see _common.evh_prog)."""
    from evaluation_harness._common import evh_prog  # noqa: PLC0415

    return evh_prog()


def main() -> int:
    """Build the catalog and write static pages to output directory."""
    global API, HEAD, BRAND, ABOUT, REPO, MCP, MCP_HOWTO, CARD
    ap = argparse.ArgumentParser(prog=_common_prog(), description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / ".build" / "catalog")
    ap.add_argument(
        "--adapter",
        help="path/to/file.py:Class (default: config.yaml catalog.adapter, else the harness's own layout)",
    )
    ap.add_argument(
        "--link",
        action="append",
        default=[],
        metavar="LABEL=URL",
        help="a part of the publication the catalog belongs to, for the header's switcher, in order "
        "(repeatable); URL . is the catalog itself, else it comes first as Catalog. "
        "E.g. --link Site=https://evals.example.org/ --link Catalog=. --link Docs=https://evals.example.org/docs/",
    )
    ap.add_argument("--brand", default=BRAND, help='the name beside the logo (default: "eval catalog")')
    ap.add_argument(
        "--api",
        default=API,
        help="where the inspector's API answers, for pages served under a path (default: /api/)",
    )
    ap.add_argument(
        "--head",
        type=Path,
        metavar="FILE",
        help="HTML added to every page's <head>, for a deployment's own analytics or tags (none by default)",
    )
    ap.add_argument(
        "--about",
        type=Path,
        metavar="FILE",
        help="HTML shown on the overview, under its description: which project this catalog shows, "
        "and where its findings are (none by default)",
    )
    ap.add_argument(
        "--repo",
        metavar="URL",
        help="where the project's files can be read, e.g. https://github.com/o/r/blob/main/: a project "
        "path in a goal's links or a guardrail's source links there (named as text by default)",
    )
    ap.add_argument(
        "--mcp",
        metavar="URL",
        help="the deployment's MCP server (evh mcp --http): every page's footer names its tool call beside "
        "its terminal command (only the command by default)",
    )
    ap.add_argument(
        "--card",
        metavar="URL",
        help="the image a shared link's card shows (https://..., 1200x630; none by default): the pages stay "
        "noindex, a card is for a person pasting a link",
    )
    ap.add_argument(
        "--mcp-howto",
        metavar="URL",
        help="--mcp: where to read how to connect an agent (default: the harness's INTEGRATION guide)",
    )
    args = ap.parse_args()
    for flag, url in (("--mcp", args.mcp), ("--mcp-howto", args.mcp_howto), ("--card", args.card)):
        if url and not url.startswith(("https://", "http://")):
            raise SystemExit(f"{flag} {url!r}: expected https://...")
    MCP = args.mcp or ""
    CARD = args.card or ""
    MCP_HOWTO = args.mcp_howto or MCP_HOWTO
    if not args.api.startswith("/") or not args.api.endswith("/"):
        raise SystemExit(
            f"--api {args.api!r}: expected a path that starts and ends with /, e.g. /catalog/api/"
        )
    API = args.api
    BRAND = args.brand
    if args.head:
        if not args.head.is_file():
            raise SystemExit(f"--head {args.head}: no such file")
        HEAD = args.head.read_text(encoding="utf-8").strip() + "\n"
    if args.repo:
        if not args.repo.startswith(("https://", "http://")):
            raise SystemExit(
                f"--repo {args.repo!r}: expected https://..., where the project's files can be read"
            )
        REPO = args.repo if args.repo.endswith("/") else args.repo + "/"
    if args.about:
        if not args.about.is_file():
            raise SystemExit(f"--about {args.about}: no such file")
        ABOUT = args.about.read_text(encoding="utf-8").strip()
    sections = []
    for spec in args.link:
        label, _, url = spec.partition("=")
        if not label or not (url == "." or url.startswith(("https://", "http://"))):
            raise SystemExit(f"--link {spec!r}: expected LABEL=https://... or LABEL=. for the catalog")
        sections.append((label, url))
    if sections and not any(u == "." for _, u in sections):
        sections.insert(0, ("Catalog", "."))
    counts = build(load_catalog_adapter(args.adapter), args.out, tuple(sections))
    print(f"catalog: {args.out} — " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    print("inspect: evh catalog-serve, then open the address it prints")
    return 0


if __name__ == "__main__":
    sys.exit(main())
