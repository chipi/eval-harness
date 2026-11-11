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
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent

from evaluation_harness import _common, _fields, _jsonout, _looks, _store, _visibility  # noqa: E402
from evaluation_harness._common import ROOT, die  # noqa: E402
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
from evaluation_harness.catalog_adapter import Adapter, item_fields, load_catalog_adapter, scores_once  # noqa: E402
from evaluation_harness.stats import fmt_p  # noqa: E402

#: The front-end files every page loads: installed beside the package, or in a checkout.
ASSET_DIR = next(p for p in (HERE / "catalog_assets", HERE.parent / "catalog_assets") if _store.is_dir(p))
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
    "data_form.js",
    "data.js",
    "icon.svg",
)
#: Links that would put more arms than this in one inspector URL go to the picker instead.
INSPECT_MAX = 40
#: A dataset page's items, at most this many a page: the rest on pages of their own beside it. One page held them all,
#: 13.8 MB at 10,000 items (S1), each row with an inspect link naming the arms.
ITEMS_PER_PAGE = 200

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

#: A home tile's label, where it is not the tile's key (catalog_periods.TILES).
TILE_LABEL = {"references": "reference sets"}

#: The catalog's menu, by the home tiles' subjects. An entry is (key, page, label), or a group
#: (key, [entries], label) that opens a short list; on a phone the ☰ menu lists every page.
NAV = [
    ("home", "index.html", "Overview"),
    ("goals", "goals.html", "Goals"),
    (
        "data",
        [
            ("datasets", "datasets.html", "Datasets"),
            ("captures", "captures.html", "Captures"),
            ("labels", "labels.html", "Labels"),
            ("references", "references.html", "Reference sets"),
        ],
        "Data",
    ),
    (
        "arms",
        [
            ("arms", "arms.html", "Arms"),
            ("configs", "arms.html#configs", "Configs"),
            ("models", "models.html", "Models"),
            ("prompts", "prompts.html", "Prompts"),
            ("metrics", "metrics.html", "Metrics"),
        ],
        "Arms",
    ),
    ("activity", "activity.html", "Activity"),
    ("inspect", "inspect.html", "Inspector"),
]
#: The Configure pages (UXS-004): a menu of their own, built only for a project that deploys them (`configure: true`,
#: SQLite only); even then shown only by a local catalog-serve, which catalog.js asks.
CONFIGURE_NAV = ("configure", "data.html", "Configure", "local-only")
#: The Configure pages' own scripts, copied only when they are built.
CONFIGURE_ASSETS = ("data_form.js", "data.js")

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
    "judge_won": "The share of the item the arm won, by judges who picked the best output (1, or 1/k when k "
    "share the best) or compared outputs two at a time (the share of its pairs won): evh judge-score, "
    "mode pick or pairwise. The judges were validated in that mode against human preferences.",
    "judge_won_unvalidated": "Computed as judge_won is, by judges not validated against human preferences "
    "in this mode (or filled in a sheet elsewhere): a trial, not a measurement.",
    "overlap_f1": "Token-overlap F1 against the reference: the bundled adapter's placeholder, "
    "enough to run the loop, not to defend a decision.",
    "output_words": "How many words the output has: a description of the output, not a quality.",
    "failed": "1 when the item's call failed (not transiently) and it was scored as an empty answer; the run "
    "listed it in failed_items and went on. Its mean is the share of the run that failed.",
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
    "judge_won": "evh judge-score in pick mode shows every arm's output for an item at once, blind and "
    "shuffled, and each judge names the best; in pairwise mode it shows two at a time and the judge says "
    "which is better, for every pair. An arm's judge_won for an item is its share of that item (1 alone "
    "best, 1/k shared; its share of the pairs won), the mean over judges. Its mean over items is the arm's "
    "win rate; the summary adds Bradley-Terry strengths with intervals, and the position and noise checks.",
    "judge_won_unvalidated": "Computed as judge_won is, by judges never compared with human preferences in "
    "this mode, or filled in a sheet outside the harness (evh sheet-import): it ranks arms by what the "
    "judges prefer, which may not be what people prefer.",
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
    if m and not metric.startswith(("judge_score", "judge_won")):
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


#: {arm: capture}: production's recorded arms (RFC-023), filled by collect(); arm_link badges them.
RECORDED: dict[str, str] = {}


def breakable(text: str) -> str:
    """An id, escaped, that may break after each underscore: `triage_local_dgx_vllm_qwen3_30b_a3b_nvfp4_v1` has no
    other place to break, so a column holding it could not be narrower than all of it. Copying it copies the id."""
    return e(text).replace("_", "_<wbr>")


def arm_link(arm: str, label: str, up: str = "", wrap: bool = False) -> str:
    """An arm's label, linked to its page; a recorded arm (production's decisions) carries its badge. `wrap`: the
    label may break after an underscore (breakable), for a table that would otherwise run past its edge."""
    badge = (
        f' <span class="badge recorded" title="production\'s decisions, from the capture {e(RECORDED[arm])}">recorded</span>'
        if arm in RECORDED
        else ""
    )
    text = breakable(label) if wrap else e(label)
    return f'<a class="cell-link" href="{up}{arm_page(arm)}">{text}</a>{badge}'


def tier_pill(tier: str) -> str:
    """A reference's tier as a pill in its own colour (UXS-001): gold on gold, silver on silver."""
    if tier not in ("gold", "silver"):
        return e(tier) if tier else ""
    return f'<span class="pill tier-{tier}">{tier}</span>'


def source_chip(kind: str) -> str:
    """A label set's source as a chip (person, model, rule), never a tier's colours (UXS-001)."""
    k = kind if kind in ("person", "model", "rule") else "unknown"
    return f'<span class="src src-{k}">{e(kind or "unknown")}</span>'


def labels_page_anchor(set_id: str) -> str:
    """A label set's row on the labels page, relative to the catalog root."""
    return f"labels.html#set-{slug(set_id)}"


def label_set_html(set_id: str, kind: str, up: str = "") -> str:
    """A label set: its source chip, then its name linked to its row on the labels page."""
    name = set_id.rsplit("/", 1)[-1]
    return f'{source_chip(kind)} <a class="cell-link" href="{up}{labels_page_anchor(set_id)}"><code>{e(name)}</code></a>'


def promoted_from_html(r: dict, up: str = "", arm: str = "") -> str:
    """Where a reference was promoted from: the label set with its source chip (and the arm a model set came from),
    else the source a reference made before labels existed names. `arm`: that arm already linked, named in its
    place (the references list named it twice, as code and again as the author's link)."""
    pf = r.get("promoted_from") or {}
    src = pf.get("source") or {}
    kind = str(src.get("kind") or "")
    if pf.get("labels"):
        out = label_set_html(f"{pf.get('dataset_id')}/{pf['labels']}", kind, up)
    elif kind:
        # A model's run is named once, below, as the arm.
        who = src.get("by") or ("" if kind == "model" else src.get("config_id")) or ""
        out = source_chip(kind) + (f" <small>{e(who)}</small>" if who else "")
    else:
        return "—"
    if kind == "model" and src.get("config_id"):
        named = arm or f"<code>{e(src['config_id'])}</code>"
        out += f" <small>the arm: {named}</small>"
    return out


def dataset_page(ds: str) -> str:
    """The dataset's page, relative to the catalog root."""
    return f"d/{slug(ds or 'none')}.html"


def dataset_link(ds: str, up: str = "", wrap: bool = False) -> str:
    """A dataset's id, linked to its page; `wrap`: it may break after an underscore (breakable)."""
    text = breakable(ds) if wrap and ds else e(ds or "(no dataset_id)")
    return f'<a class="cell-link" href="{up}{dataset_page(ds)}">{text}</a>'


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
    if (a.get("reference") or "").startswith("labels/"):
        return "t-labels"
    tier = tiers.get(a.get("reference", "")) or (a.get("reference") or "").split("/", 1)[0]
    return "t-silver" if tier == "silver" else ""


def scored_against(a: dict, up: str) -> str:
    """The table cell that says what an arm was scored against: a judge, a reference with its tier pill, or a label
    set with its source chip (RFC-023), linked."""
    if a.get("judge"):
        return f'judge <code class="small">{e(a["judge"])}</code>'
    ref = a.get("reference")
    if not ref:
        return "—"
    if ref.startswith("labels/"):
        return label_set_html(ref.removeprefix("labels/"), a.get("labels_source") or "", up)
    tier = ref.split("/", 1)[0]
    return f'<a class="cell-link" href="{up}{reference_page(ref)}">{e(ref)}</a> {tier_pill(tier)}'.rstrip()


ROW_KEY = (
    '<p class="rowkey small muted"><span class="key t-silver">scored against silver</span>'
    '<span class="key t-judged">scored by a judge</span>'
    '<span class="key t-author">wrote the reference it is scored against</span>'
    '<span class="key t-labels">scored against a label set, not a reference set</span>'
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
    # A catalog under the default name and in no publication (no --link) is a project's own, read locally: it names
    # its project, so two open side by side are never confused (ADR-0024). A deployment names itself and is not
    # changed.
    local = brand == "eval catalog" and not parts
    brand_text = (
        f'<span>{e(brand)}<small class="proj"> · {e(ROOT.name)}</small></span>'
        if local
        else f"<span>{e(brand)}</span>"
    )
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
<title>{e(title)} · {e(brand)}{f" · {e(ROOT.name)}" if local else ""}</title>
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
    autocomplete="off" aria-label="Search the catalog"><div id="hits" class="hits" hidden></div></div>
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
    _store.mkdir(p.parent, parents=True, exist_ok=True)
    _store.write_text(p, content, encoding="utf-8")


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
                if bl.get("promoted_at") and bl.get("arm") and bl.get("goal") == g["goal_id"]
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


def copy_assets(out: Path, configure: bool = False) -> None:
    """Copy CSS, JS, and SVG assets to output directory (the Configure pages' scripts only when they are built)."""
    _store.mkdir(out / "assets", parents=True, exist_ok=True)
    for a in ASSETS:
        if a in CONFIGURE_ASSETS and not configure:
            continue
        _store.copy_file(ASSET_DIR / a, out / "assets" / a)
    _store.write_text(out / "assets" / "head.js", HEAD_JS_SRC, encoding="utf-8")


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
    RECORDED.clear()
    for arm in A.arms():
        d = A.describe(arm)
        if d.get("recorded"):
            RECORDED[arm] = d["recorded"]
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
                "labels_source": d.get("labels_source", ""),
                "recorded": d.get("recorded", ""),
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
    _mark_superseded(by_ds)
    bl = getattr(A, "baselines", None)
    for b in bl() if callable(bl) else []:
        v = by_ds.get(b["dataset"])
        if v is None:
            continue
        v.setdefault("baselines", []).append(b)
        for a in v["arms"]:
            if a["arm"] == b["arm"]:
                a["baseline"] = b
        # A baseline whose arm is read from its re-score is the re-score's (RFC-022): the goal reads that one.
        for a in v["arms"]:
            if a.get("baseline") and a.get("superseded_by"):
                for t in v["arms"]:
                    if t["arm"] == a["superseded_by"]:
                        t["baseline"] = a["baseline"]
    _versions(A, by_ds)
    # The dataset's own size, from the ADAPTER: the harness's DATASETS path is not where a
    # project with its own layout keeps them. An adapter that cannot say falls back to the
    # most items any arm scored.
    size = getattr(A, "dataset_items", None)
    meta = getattr(A, "dataset_meta", None)
    for ds, v in by_ds.items():
        n = size(ds) if callable(size) else None
        v["items"] = n if n is not None else max((a["n"] for a in v["arms"]), default=0)
        m = (meta(ds) if callable(meta) else None) or {}
        v["tags"], v["origin"], v["capture"] = (
            m.get("tags") or {},
            m.get("origin") or "",
            m.get("capture") or "",
        )
    return by_ds


def _mark_superseded(by_ds: dict) -> None:
    """An arm every run of which was re-scored (`evh rescore`) against the same reference gets
    "superseded_by": the arm holding the latest re-score. A scorer that changes after runs were measured
    leaves their scores stale, and the re-score is the same outputs read by the current scorer; showing
    both ranks one arm twice (and an old score may lack the goal's measure entirely). The goal pages read
    the re-score; the measured arm keeps its page as the record of what was first scored."""
    for v in by_ds.values():
        latest: dict = {}
        for a in v["arms"]:
            for r in a["run_list"]:
                if r.get("derived") == "rescore" and r.get("from"):
                    key = (a["reference"], r["from"])
                    if key not in latest or (r["created_at"], a["arm"]) > latest[key][0]:
                        latest[key] = ((r["created_at"], a["arm"]), a["arm"])
        for a in v["arms"]:
            ids = [r["run_id"] for r in a["run_list"]]
            by = {latest.get((a["reference"], i), (None, None))[1] for i in ids}
            if ids and len(by) == 1 and None not in by and a["arm"] not in by:
                a["superseded_by"] = by.pop()


def _machine(A: Adapter, arm: str) -> str:
    """Where an arm's time was spent, in one form: "served on <machine>" when its deployment names the machine
    that served the model, else "run on [<label> · ]<platform>, <n> CPUs" for the runner (the label is
    EVAL_HOST_LABEL, when set). Four forms in one table ("mac-dev", "Darwin/x86_64 · 12 CPUs", "x3") read as four
    kinds of thing; a runner without a label is never guessed to be a labelled one."""
    fn = getattr(A, "conditions", None)
    c = fn(arm) if callable(fn) else {}
    if c.get("deployment.machine"):
        return f"served on {c['deployment.machine']}"
    hw = ", ".join(
        b
        for b in (c.get("machine.platform"), c.get("machine.cpu_count") and f"{c['machine.cpu_count']} CPUs")
        if b
    )
    name = " · ".join(b for b in (c.get("machine.label"), hw) if b)
    return f"run on {name}" if name else ""


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
    # every tag key some dataset carries: each is a "group by" chip (RFC-019: tags group and filter)
    tag_keys = sorted({k for v in by_ds.values() for k in (v.get("tags") or {})})
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
        tags = v.get("tags") or {}
        rows.append(
            {
                "key": ds,
                "made": period_rows[ds]["made"],
                "data": {"goal": its_goals, **{f"tag-{k}": tags.get(k) or f"no {k}" for k in tag_keys}},
                "cells": [
                    dataset_link(ds, wrap=True)
                    + (f"<br><small>from {dataset_link(parent, wrap=True)}</small>" if parent else "")
                    + (f"<br><small>{origin_html(v)}</small>" if v.get("origin") and not parent else ""),
                    # A chip per tag: run together as text, five tags and a Hugging Face pin made one tall
                    # unreadable cell (owner, 2026-10-31).
                    "".join(
                        f'<span class="tag" title="{e(k)}: {e(t)}"><b>{e(k)}</b> {e(t)}</span>'
                        for k, t in sorted(tags.items())
                    )
                    or "—",
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
        group_chips("datasets", (("", "no grouping"), ("goal", "goal"), *((f"tag-{k}", k) for k in tag_keys)))
        + cp.row_chips("datasets", "datasets")
        + table(
            "datasets",
            [
                "dataset",
                "tags",
                f"{e(A.item_word)}s",
                "arms",
                "runs in period",
                "runs per day",
                "spend in period",
                "reference sets",
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
                if day and day >= since and (not r.get("derived") or r.get("in_place")):
                    counts.setdefault(ds, {}).setdefault(day, 0)
                    counts[ds][day] += 1
    return counts


#: The spend chart's series: what kind of call was billed, and its name on the page.
SPEND_KINDS = (("arm", "systems under test"), ("judge", "judges"), ("smoke", "arm smokes"))


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


def baseline_read(v: dict, goal_id: str) -> tuple[list, str | None]:
    """A dataset's baselines for a goal, and the arm the goal reads for the latest one: its latest re-score when
    it was re-scored (RFC-022), as the goal page reads it, else the promoted arm itself."""
    bl = [x for x in v.get("baselines", []) if x.get("goal") == goal_id]
    base = bl[-1]["arm"] if bl and bl[-1].get("arm") else None
    moved = next((a.get("superseded_by") for a in v.get("arms", []) if base and a["arm"] == base), None)
    return bl, moved or base


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
                continue  # a pilot slice or a generalization check: on the goal page, not the glance
            v = by_ds.get(ds) or {}
            bl, base = baseline_read(v, g["goal_id"])
            # The gold group decides; without one, the first group scored against a reference,
            # named in the row so it is never read as gold.
            tiers = {r["id"]: r["tier"] for r in v.get("refs", [])}

            plain = [x for x in ans["groups"] if not x["key"].startswith("judge ")]
            grp = next((x for x in plain if ref_tier(tiers, x["key"]) == "gold"), plain[0] if plain else None)
            dec = (
                group_decision(
                    A,
                    g,
                    ds,
                    grp["rows"],
                    measure,
                    retired_in,
                )
                if grp
                else None
            )
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
                    clusters=goal_clusters(A, g, ds)[0],
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
        kinds = {"gold": 0, "silver": 0, "labels": 0, "judged": 0, "none": 0}
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
                        if not m.startswith(("self_family_", "resumed", "failed", "total_"))
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
                # The answer beside the question: last, at 1400 px it was the column cut at the edge.
                (
                    arm_link(r["recommended"], brief(r["recommended_label"]), wrap=True)
                    + (
                        f"<br><small>{e(' · '.join(r['vs_baseline']))} vs baseline</small>"
                        if r["vs_baseline"]
                        else ""
                    )
                )
                if r["recommended"]
                else '<span class="muted">none yet</span>',
                (
                    arm_link(r["baseline"], brief(r["baseline_label"]), wrap=True)
                    + f" <small>{fmt(r['baseline_mean'])}</small>"
                )
                if r["baseline"]
                else '<span class="muted">none promoted</span>',
                (
                    arm_link(r["leader"], brief(r["leader_label"]), wrap=True)
                    + f" <small>{fmt(r['leader_mean'])}</small>"
                )
                if r["leader"]
                else "—",
                verdict,
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
            ["goal", "dataset", "decides", "recommended", "baseline", "leader", "leader vs baseline"],
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
            "reference sets",
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
    from evaluation_harness.catalog_models import entries  # noqa: PLC0415
    from evaluation_harness.catalog_periods import TILES  # noqa: PLC0415

    billed = sum(float(x["usd"]) for x in spend if isinstance(x.get("usd"), (int, float)))
    tokens = int(sum(x["tokens"] for x in spend if isinstance(x.get("tokens"), (int, float))))
    n = {
        "goals": len(A.goals()),
        "datasets": len(by_ds),
        "configs": _n_configs(by_ds),
        "arms": sum(len(v["arms"]) for v in by_ds.values()),
        "models": len(entries(A)),
        "references": sum(len(v["refs"]) for v in by_ds.values()),
        "metrics": len(metric_index(A, by_ds)),
        "measured runs": sum(
            1
            for v in by_ds.values()
            for a in v["arms"]
            for r in a["run_list"]
            if not r.get("derived") or r.get("in_place")
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


#: The home page's ways in: (key in home_counts, page, title, subject colour, one line).
ENTRIES = (
    (
        "goals",
        "goals.html",
        "Goals",
        "goals",
        "What each evaluation decides, its leader and what it recommends.",
    ),
    (
        "datasets",
        "datasets.html",
        "Datasets",
        "data",
        "Every run by dataset, with its references and coverage.",
    ),
    ("arms", "arms.html", "Arms", "arms", "Every config on every dataset, scored each way it was."),
    ("models", "models.html", "Models", "arms", "Each model: where it is deployed, onboarded and vetted."),
    (None, "inspect.html", "Inspector", "work", "Any arms against a baseline, item by item."),
)


def _entries(counts: list[tuple]) -> str:
    """The home page's entry tiles: each subject's page, its count and one line on what is there."""
    n = {k: v for k, v, _ in counts}
    return (
        '<nav class="entries" aria-label="The catalog">'
        + "".join(
            f'<a class="entry" href="{href}" data-group="{g}"><span class="n">{"→" if k is None else tile_value(n[k])}</span>'
            f"<b>{e(title)}</b><small>{e(line)}</small></a>"
            for k, href, title, g, line in ENTRIES
        )
        + "</nav>"
    )


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
            f'<a class="tile" href="{href}" data-tile="{i}" data-group="{cp.TILES[i][3]}"{" data-period-link" if ".html" in href else ""} title="{e(n)} {e(TILE_LABEL.get(k, k))}"><b>{tile_value(n)}</b>'
            f'<span>{e(TILE_LABEL.get(k, k))}</span><small class="trend"></small></a>'
            for i, (k, n, href) in enumerate(home_counts(A, by_ds, w["spend"]))
        )
        + "</div>"
        + '<p class="legend groups">'
        + "".join(
            f'<span data-group="{g}"><i></i>{e(name)}</span>'
            for g, name in (
                ("goals", "goals"),
                ("data", "data"),
                ("arms", "arms"),
                ("work", "work and spend"),
            )
        )
        + "</p>"
    )
    switch = cp.bar(first, until)
    body = (
        '<section class="hero slim home"><div class="wrap"><p class="kicker">catalog</p>'
        "<h1>The eval catalog</h1>"
        '<p class="dek">Every goal, dataset, arm and model in this project\'s committed runs.</p>'
        + (f'<div class="about">{ABOUT}</div>' if ABOUT else "")
        + '<div class="search home-search"><input id="home-q" type="search" autocomplete="off" '
        'placeholder="Search goals, datasets, arms…" aria-label="Search the catalog">'
        '<div class="hits" hidden></div></div>'
        + _entries(home_counts(A, by_ds, w["spend"]))
        + "</div></section>"
    )
    body += block("01", "at a glance", switch + tile_html, "period")
    body += block("02", "goals at a glance", _glance(A, by_ds), "glance")
    activity = _activity_chart(by_ds, first, until) if first else '<p class="muted">No runs yet.</p>'
    spending = (
        _spend_panel(w["spend"], first, until)
        if first and w["spend"]
        else '<p class="muted">Nothing spent is recorded.</p>'
    )
    body += block(
        "03",
        "activity and spend",
        f'<div class="duo"><div id="activity"><h3 class="sub">activity</h3><div data-chart="activity">{activity}</div></div>'
        f'<div id="spend"><h3 class="sub">spend</h3><div data-chart="spend">{spending}</div></div></div>'
        '<p><a class="btn small" href="activity.html" data-period-link>every dataset, arm and kind of spend in the period</a></p>',
    )
    body += block("04", "coverage", _coverage(A, by_ds), "coverage")
    body += block(
        "05",
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
    # The measure a goal decides on first: by name, triage's 19 false_dismiss arms came before its 317 on
    # triage_cost, and SummEval's pair_agreement arms before the τ field.
    deciding = [
        ((g.get("success_criteria") or {}).get("primary") or {}).get("measure")
        for g in _goals_of(A).get(ds, [])
    ]
    arms = sorted(
        v["arms"],
        key=lambda a: (
            scored_by_rank(a, tiers),
            a.get("reference") or "",
            a["metric"] not in deciding,
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
                + (f"<br><small>{e(a['machine'])}</small>" if len(machines) > 1 and a.get("machine") else ""),
                metric_link(a["metric"], "../"),
                (
                    f'<span data-v="{a["mean"] if a["mean"] is not None else ""}">{fmt(a["mean"])}'
                    f"{' ↓' if a['lower'] else ''}</span>"
                ),
                f'<span data-v="{a["n"]}">{a["n"]}</span>',
                *(NO_CALL if a.get("recorded") else axis_cell(ax, c) for ax, c in zip(bax, cells[a["arm"]])),
                str(a["runs"]),
                scored_against(a, "../"),
                f'<a class="btn small" href="{inspect_url([a["arm"]], "../")}">inspect</a>',
            ],
        }
        for a in arms
    ]
    # One button per group of arms that can be tested together: the same headline metric,
    # scored against the same reference. A silver-scored and a gold-scored run both record
    # the metric but measure different things, and the inspector sets such arms aside. So do two judges' scores:
    # one button per judging pass, never judge-summ-v1 and v2 as one comparison of 58.
    groups: dict = {}
    for a in arms:
        groups.setdefault(
            (a["metric"] or "", ("judge", a["judge"]) if a["judge"] else ("ref", a["reference"] or "")), []
        ).append(a["arm"])
    btns = []
    for (metric, (kind, by)), members in sorted(
        groups.items(), key=lambda kv: (kv[0][0] not in deciding, -len(kv[1]), kv[0])
    ):
        if len(members) < 2:
            continue
        more = (
            f" (the first {INSPECT_MAX} of {len(members)}; add others in the inspector)"
            if len(members) > INSPECT_MAX
            else ""
        )
        whose = f"judged by {e(by)}" if kind == "judge" else f"scored against {e(by)}" if by else ""
        what = ", ".join(x for x in ((f"on {e(metric)}" if metric else ""), whose) if x)
        btns.append(
            f'<a class="btn" href="{inspect_url(members[:INSPECT_MAX], "../", metric=metric)}">'
            f"Inspect the {len(members)} arms {what}</a>"
            + (f'<span class="muted small">{more}</span>' if more else "")
        )
    # The sheet (RFC-023): its items one per row, production's recorded arm first when there is one.
    rec = [a["arm"] for a in arms if a.get("recorded")]
    q = f"dataset={quote(ds, safe='')}&sheet=1" + (f"&runs={quote(','.join(rec), safe=',/')}" if rec else "")
    btns.append(f'<a class="btn" href="../inspect.html?{q}">Open its sheet</a>')
    btn = f'<p class="btns">{"".join(btns)}</p>' if btns else ""
    for b in v.get("baselines", []):
        label = next((a["label"] for a in arms if a["arm"] == b.get("arm")), b["run"])
        who = arm_link(b["arm"], label, "../") if b.get("arm") else e(label)
        of = f"{b['goal']}'s baseline" if b.get("goal") else "the dataset's own baseline"
        btn = (
            f'<div class="answer"><p class="small muted">{e(of)}, version {e(b.get("version"))}, promoted '
            f"{e((b['promoted_at'] or '')[:10])}</p>"
            f'<p class="lead"><b>{who}</b></p><p>{e(b["reason"])}</p></div>'
        ) + btn
    goals = _goals_of(A).get(ds, [])
    if goals:
        btn += '<p class="small">goals: ' + ", ".join(goal_link(g, "../") for g in goals) + "</p>"
    refs = "".join(
        f"<li>{reference_link(r['id'], '../')} {tier_pill(r['tier'])}"
        + (f" · promoted from {promoted_from_html(r, '../')}" if r.get("promoted_from") else "")
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
    inside, item_pages = render_inside(A, ds, biggest[1][:INSPECT_MAX], biggest[0])
    body += block("02", "what's inside", inside, "inside")
    for rel, items_body in item_pages:  # the rest of the items, a page each, beside the dataset's page
        write(
            out,
            rel,
            page(
                f"{ds}: {A.item_word}s",
                block("02", "what's inside", items_body, "inside"),
                1,
                "",
                nav=nav,
                item=A.item_word,
            ),
        )
    if v.get("versions"):
        n += 1
        body += block(f"{n:02d}", "versions", v["versions"], "versions")
    if refs:
        n += 1
        body += block(f"{n:02d}", "reference sets", f"<ul>{refs}</ul>")
    labels_html = render_labels_of(A, ds, v)
    if labels_html:
        n += 1
        body += block(f"{n:02d}", "labels", labels_html, "labels")
    picks_html = render_picks_waiting(A, ds)
    if picks_html:
        n += 1
        body += block(f"{n:02d}", "picks waiting", picks_html, "picks")
    added_html = render_added(A, ds)
    if added_html:
        n += 1
        body += block(f"{n:02d}", "added from production", added_html, "added")
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


def _made_line(source: dict, created_at) -> str:
    """Who or which run made a label set, and when."""
    from evaluation_harness._label_sets import source_line  # noqa: PLC0415

    when = (created_at or "")[:10]
    return e(source_line(source)) + (f" <small>{e(when)}</small>" if when else "")


def _promoted_as(A: Adapter, set_id: str) -> str:
    """The reference set promoted from a label set, with its pill, or "not promoted"."""
    ds, _, name = set_id.partition("/")
    hit = [
        r
        for r in A.references()
        if (r.get("promoted_from") or {}).get("labels") == name
        and (r.get("promoted_from") or {}).get("dataset_id") == ds
    ]
    return (
        ", ".join(f"{reference_link(r['id'], '../')} {tier_pill(r['tier'])}" for r in hit)
        if hit
        else '<span class="muted">not promoted</span>'
    )


def render_labels_of(A: Adapter, ds: str, v: dict) -> str:
    """A dataset's label sets (RFC-023): those covering its items, matched by hash, and how often two agree."""
    fn = getattr(A, "label_coverage", None)
    if not callable(fn):
        return ""
    cov = fn(ds)
    n = v.get("items") or 0
    if not cov["sets"]:
        return (
            '<p class="muted">No labels yet. A sheet to fill: <code>evh label-sheet --dataset-id '
            f"{e(ds)} --out sheet.csv</code>; a run's outputs as a model set: <code>evh label-from-run --run R "
            "--set S</code>.</p>"
        )
    rows = [
        {
            "cells": [
                label_set_html(x["id"], (x.get("source") or {}).get("kind", ""), "../"),
                dataset_link(x["dataset"], "../")
                if x["dataset"] != ds
                else '<span class="muted">this one</span>',
                f'<span data-v="{len(x["covers"])}">{len(x["covers"])} of {n}</span>',
                e((x.get("guideline") or {}).get("path") or "none"),
                _made_line(x.get("source") or {}, x.get("created_at")),
                _promoted_as(A, x["id"]),
            ]
        }
        for x in cov["sets"]
    ]
    html_ = table(f"labels-{slug(ds)}", ["set", "made on", "coverage", "guideline", "made", "promoted"], rows)
    if cov["agreement"]:
        html_ += (
            '<h3 class="sub">how often two sets agree <small>on the items both label: the same answers, sharing '
            "one, and chance-corrected (Cohen's κ, Krippendorff's α)</small></h3>"
            # "α −0.25 MASI" was a number and a word with nothing to read them by.
            '<p class="small muted">κ and α are 1 when two sets always agree, 0 when they agree only as often as '
            "chance would, and below 0 when they agree less often than that. <b>MASI</b>: where a label may name "
            "several answers, α counts a partial overlap as partial agreement (Passonneau's MASI distance), not as "
            "a miss.</p>"
            + table(
                f"agree-{slug(ds)}",
                # In <small>: a header is uppercased, and Κ and Α read as K and A.
                [
                    "set",
                    "set",
                    "both label",
                    "same answers",
                    "share an answer",
                    "<small>κ</small>",
                    "<small>α</small>",
                ],
                [
                    {"cells": [f"<code>{e(a['a'])}</code>", f"<code>{e(a['b'])}</code>", *agreement_cells(a)]}
                    for a in cov["agreement"]
                ],
            )
            # A hidden dataset's labels are per-item text (RFC-019 §4): its confusion matrices, which name them, stay off
            # the pages; the counts and coefficients above are numbers.
            + ("" if _visibility.hidden(ds) else "".join(confusion_html(a) for a in cov["agreement"]))
        )
    return html_


def agreement_cells(a: dict) -> list[str]:
    """One pair of label sets compared (`_label_sets.compare`): the items, the same answers, a shared one, κ, α."""
    both = a["both"]
    if a.get("kind") != "categories":
        free = '<span class="muted">free text: not compared as text</span>'
        return [str(both), free, "", "", ""]

    def share(k: str) -> str:
        return f"{a[k]} ({a[k] / both:.0%})" if both else "0"

    def coef(k: str) -> str:
        return "—" if a.get(k) is None else f"{a[k]:.2f}"

    alpha = coef("alpha") + (
        ' <small title="a partial overlap of answers counts as partial agreement (MASI distance)">MASI</small>'
        if a.get("alpha_distance") == "MASI" and a.get("alpha") is not None
        else ""
    )
    return [str(both), share("same"), share("share"), coef("kappa"), alpha]


def confusion_html(a: dict) -> str:
    """One pair's confusion matrix, folded: a's labels down, b's across."""
    conf = a.get("confusion") or {}
    if not conf:
        return ""
    cols = sorted({c for row in conf.values() for c in row})
    rows = [
        {
            "cells": [
                e(r),
                *[str(conf[r].get(c, 0)) if conf[r].get(c) else '<span class="muted">0</span>' for c in cols],
            ]
        }
        for r in sorted(conf)
    ]
    head = [f"{e(a['a'])} ↓ · {e(a['b'])} →", *[e(c) for c in cols]]
    return (
        f"<details><summary>where <code>{e(a['a'])}</code> and <code>{e(a['b'])}</code> differ</summary>"
        + table(f"confusion-{slug(a['a'])}-{slug(a['b'])}", head, rows)
        + "</details>"
    )


def _label_sets_of(A: Adapter) -> list:
    """The adapter's label sets (optional: an adapter without them has none)."""
    fn = getattr(A, "label_sets", None)
    return fn() if callable(fn) else []


def _labels_of_sha(A: Adapter, sha: str) -> str:
    """The source chips of every label set holding an item with these bytes (labels follow the item)."""
    sets = [
        ls
        for ls in _label_sets_of(A)
        if any((row or {}).get("item_sha256") == sha for row in ls["items"].values())
    ]
    return (
        " ".join(label_set_html(ls["id"], (ls.get("source") or {}).get("kind", ""), "../") for ls in sets)
        if sets
        else '<span class="muted">none yet</span>'
    )


def cmdpick(prefix: str, flag: str, empty: str, inner: str) -> str:
    """A selection that gives a command (RFC-023): the boxes ticked in `inner` (input.cmdsel, their value the
    argument) become `prefix flag v flag v …`, shown to copy; catalog.js keeps it current. The page writes nothing."""
    return (
        f'<div class="cmdpick" data-prefix="{e(prefix)}" data-flag="{e(flag)}" data-empty="{e(empty)}">{inner}'
        f'<p class="cmdbox"><code class="cmd">{e(empty)}</code> '
        '<button type="button" class="btn small copy" data-copy="" hidden>copy</button></p></div>'
    )


def render_picks_waiting(A: Adapter, ds: str) -> str:
    """The picks waiting for this dataset (ADR-0023), a box per row; the rows ticked give dataset-extend."""
    fn = getattr(A, "picks_waiting", None)
    picks = fn(ds) if callable(fn) else []
    if not picks:
        return ""
    rows = [
        {
            "cells": [
                (
                    f'<input type="checkbox" class="cmdsel" value="{e(p.get("from"))}:{e(p.get("item"))}" '
                    f'aria-label="pick {e(p.get("item"))}">'
                ),
                (
                    f'<a class="cell-link" href="../inspect.html?dataset={quote(str(p.get("from")), safe="")}'
                    f'&sheet=1&item={quote(str(p.get("item")), safe="")}"><code>{e(p.get("item"))}</code></a>'
                ),
                dataset_link(str(p.get("from")), "../")
                + (f" <small>capture {e(p['capture'])}</small>" if p.get("capture") else ""),
                _labels_of_sha(A, str(p.get("sha256") or "")),
                e(", ".join(f"{k}={v_}" for k, v_ in (p.get("tags") or {}).items())) or "—",
                e(p.get("note") or "") or "—",
                e(" ".join(x for x in (str(p.get("by") or ""), str(p.get("at") or "")[:10]) if x)) or "—",
            ]
        }
        for p in picks
    ]
    tbl = table(
        f"picks-{slug(ds)}",
        [
            '<input type="checkbox" class="cmdall" aria-label="select all shown">',
            "item",
            "from",
            "labels",
            "tags",
            "note",
            "picked",
        ],
        rows,
    )
    return cmdpick(
        f"evh dataset-extend {ds} --dataset-id <next>",
        "--pick",
        "tick the picks to add: the command to make the next version shows here",
        f'<p class="small muted">{len(picks)} pick(s) name this dataset as a target. The page writes nothing: '
        "it gives the command for the rows you tick.</p>" + tbl,
    )


def render_added(A: Adapter, ds: str) -> str:
    """A version made by dataset-extend: each item it added, where it came from, the note, the labels it carried."""
    meta = getattr(A, "dataset_meta", None)
    ext = ((meta(ds) if callable(meta) else None) or {}).get("extended_from")
    if not ext:
        return ""
    sha = {}
    got = getattr(A, "data_dir", None)
    if got is not None:
        doc = json.loads(_store.read_text(Path(got) / "datasets" / f"{ds}.json", encoding="utf-8"))
        sha = {it["item_id"]: it.get("source_sha256") for it in doc.get("items") or []}
    rows = [
        {
            "cells": [
                f"<code>{e(p.get('item_id'))}</code>",
                dataset_link(str(p.get("from")), "../")
                + (f" <small>capture {e(p['capture'])}</small>" if p.get("capture") else ""),
                e(p.get("note") or "") or "—",
                _labels_of_sha(A, str(sha.get(p.get("item_id")) or "")),
            ]
        }
        for p in ext.get("picks") or []
    ]
    return (
        f'<p class="small">Made from {dataset_link(str(ext.get("dataset")), "../")} and {len(rows)} pick(s).</p>'
        + table(f"added-{slug(ds)}", ["item", "from", "note", "labels it carried"], rows)
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


def render_inside(
    A: Adapter, ds: str, inspect_arms: list[str], metric: str
) -> tuple[str, list[tuple[str, str]]]:
    """What is inside the dataset (data/profiles/<ds>.json): how many items and how long, the gold's
    shape, then one row per item with its length, its gold and where it can be read at its source.
    No item text unless the profile carries it, which `evh dataset-profile --with-text` allows only
    for text git already tracks. More than ITEMS_PER_PAGE items: the first on the dataset's page, the rest on
    pages of their own, returned as (path under the catalog, the body) for the caller to write."""
    from evaluation_harness import catalog_charts as ch  # noqa: PLC0415

    fn = getattr(A, "dataset_profile", None)
    p = fn(ds) if callable(fn) else None
    if not p:
        return (
            f'<p class="muted">No profile yet. Where the dataset is materialized, '
            f"<code>evh dataset-profile --dataset-id {e(ds)}</code> writes one: its {e(A.item_word)}s, how long "
            f"they are, the gold's shape and where each can be read.</p>"
        ), []
    hide = _visibility.hidden(ds)
    if hide:
        p = _visibility.public_profile(p)
    elif any(r.get("text") for r in p.get("rows") or []) and not _texts_tracked(ds):
        # A profile written --with-text is checked again here: text whose source git no longer
        # tracks is not shown, whatever the profile carries.
        p = {**p, "rows": [{k: v for k, v in r.items() if k != "text"} for r in p["rows"]]}
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
        name = e(src.get("ref") or src.get("provider") or "the source")
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
    if hide:
        lines.append(
            f"This dataset's text is kept off public pages (<code>text: hidden</code>): its {e(A.item_word)}s, "
            "their labels and links are not shown, only their number and length."
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
    foot = (
        '<p class="small muted">Each row is the profile <code>evh dataset-items --dataset-id '
        f"{e(ds)}</code> prints; <b>inspect</b> opens the {e(A.item_word)} in the inspector with the dataset's "
        "largest group of comparable arms, and its text where the inspector runs on a machine that has it.</p>"
    )
    per = ITEMS_PER_PAGE
    chunks = [rows[i : i + per] for i in range(0, len(rows), per)] or [[]]
    names = [f"{slug(ds or 'none')}.html"] + [
        f"{slug(ds or 'none')}~items-{k}.html" for k in range(2, len(chunks) + 1)
    ]

    def pager(k: int) -> str:
        if len(chunks) == 1:
            return ""
        lo, hi = (k - 1) * per + 1, min(k * per, len(rows))
        links = " ".join(
            f"<b>{j}</b>" if j == k else f'<a href="{names[j - 1]}#inside">{j}</a>'
            for j in range(1, len(chunks) + 1)
        )
        return (
            f'<p class="small">{e(A.item_word)}s {lo}–{hi} of {len(rows)}, {per} a page: {links}. The filter reads '
            f"this page's {e(A.item_word)}s; <code>evh dataset-items --dataset-id {e(ds)}</code> lists them all.</p>"
        )

    first = (
        head
        + chart
        + (f'<p class="eyebrow small">the gold</p>{golds}' if golds else "")
        + pager(1)
        + table("inside-items", heads, chunks[0], f"filter {A.item_word}s")
        + foot
    )
    more = [
        (
            f"d/{names[k - 1]}",
            pager(k) + table("inside-items", heads, chunks[k - 1], f"filter {A.item_word}s") + foot,
        )
        for k in range(2, len(chunks) + 1)
    ]
    return first, more


def _texts_tracked(ds: str) -> bool:
    """Whether git still tracks every item's source file (what --with-text required when written)."""
    from evaluation_harness import dataset_profile  # noqa: PLC0415

    try:
        d = _common.load_dataset(ds)
    except SystemExit:
        return False
    src = ROOT / d.get("source_dir", "data/sources")
    if _common.store() == "sqlite":  # RFC-025: the database is the record, as git is for files
        return all(
            _store.is_file(src / (it.get("source_path") or it["item_id"])) for it in d.get("items") or []
        )
    return not dataset_profile.tracked(
        [src / (it.get("source_path") or it["item_id"]) for it in d.get("items") or []]
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
        arms = (by_ds.get(ds) or {}).get("arms", [])
        # the measured arms read through a re-score (an older re-score superseded by a newer one is not another)
        moved = [
            a for a in arms if a.get("superseded_by") and not any(r.get("derived") for r in a["run_list"])
        ]
        notes = d.get("notes", "")
        if moved:
            notes = (notes.rstrip(". ") + ". " if notes else "") + (
                f"{len(moved)} arm(s) are read from their re-score with the current scorer, not their first "
                "score (the measured run keeps its own page)."
            )
        for a in arms:
            if a.get("superseded_by"):
                continue
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
        out.append((ds, d.get("role", ""), notes, rows))
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
            (dataset_link(r["dataset"], wrap=True) + ": " if len(g.get("datasets") or []) > 1 else "")
            + arm_link(r["recommended"], brief(r["recommended_label"]), wrap=True)
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
                    rec or '<span class="muted">none yet</span>',
                    "<br>".join(
                        dataset_link(d.get("dataset_id", ""), wrap=True) for d in g.get("datasets") or []
                    )
                    or "—",
                    f'<span data-v="{filed}">{filed}</span>',
                    f'<span data-flow="runs" data-line>{len(period_rows[g["goal_id"]]["runs"])}</span>',
                    '<span data-flow="usd">—</span>',
                    f'<span data-flow="events">{len(period_rows[g["goal_id"]]["events"])}</span>',
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
                "recommended",
                "datasets",
                "configs filed",
                "runs in period",
                "spend in period",
                "changes in period",
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


def _sheet_fold(A: Adapter, b: dict) -> str:
    """The baseline's deploy sheet, folded, with what the captures say production ran (UXS-001)."""
    fn = getattr(A, "deploy_sheet", None)
    sh = fn(b["arm"]) if b.get("arm") and callable(fn) else None
    if not sh:
        return ""
    v = deploy_verdicts(sh).replace("{up}", "../")
    return (
        (f'<ul class="small">{v}</ul>' if v else "")
        + '<details class="inline small"><summary>deploy sheet: what production must match</summary>'
        + deploy_sheet_html(sh, "../")
        + "</details>"
    )


def _answer(A: Adapter, g: dict, by_ds: dict, measure: str) -> str:
    """The goal's answer so far: on each of its datasets, the promoted baseline and why, or that
    nothing has been decided, with the command that decides it."""
    parts = []
    # A round closed after the baseline was promoted says what is known now, so it leads; the promotion's reason
    # is why that run was kept, and can name a plan a later round replaced (the triage gold "grows to 93").
    fn = getattr(A, "rounds", None)
    closed = sorted(
        (
            r
            for r in (fn() if callable(fn) else [])
            if r.get("goal") == g["goal_id"]
            and r.get("status") == "closed"
            and (r.get("conclusion") or {}).get("text")
        ),
        key=lambda r: str(r.get("closed_at") or ""),
    )
    latest = closed[-1] if closed else None
    for d in g.get("datasets") or []:
        ds = d.get("dataset_id", "")
        v = by_ds.get(ds) or {}
        bl = [b for b in v.get("baselines", []) if b.get("goal") == g["goal_id"]]
        label = {a["arm"]: a["label"] for a in v.get("arms", [])}
        head = dataset_link(ds, "../")
        if bl and latest and str(latest.get("closed_at") or "") > str(bl[-1].get("promoted_at") or ""):
            b = bl[-1]
            arm = label.get(b.get("arm") or "", b["run"])
            who = arm_link(b["arm"], arm, "../") if b.get("arm") else e(arm)
            parts.append(
                f'<div class="answer"><p class="small muted">{head} · round {e(latest["round_id"])} concluded '
                f"{e(_when(str(latest.get('closed_at') or '')))}</p>"
                f"<p>{e(latest['conclusion']['text'])}</p>"
                f'<p class="small">baseline: <b>{who}</b>, promoted {e(_when(b["promoted_at"]))}'
                + (f" · scored against {tier_pill(b['tier'])}" if b.get("tier") else "")
                + f'</p><details class="inline small"><summary>why it was promoted</summary>{e(b["reason"])}</details>'
                + _baseline_facts(A, b)
                + _sheet_fold(A, b)
                + (
                    f'<p><a class="btn small" href="{inspect_url([b["arm"]], "../", metric=measure)}">inspect it</a></p>'
                    if b.get("arm")
                    else ""
                )
                + "</div>"
            )
        elif bl:
            b = bl[-1]
            arm = label.get(b.get("arm") or "", b["run"])
            who = arm_link(b["arm"], arm, "../") if b.get("arm") else e(arm)
            parts.append(
                f'<div class="answer"><p class="small muted">{head} · baseline promoted {e(_when(b["promoted_at"]))}'
                + (f" · scored against {tier_pill(b['tier'])}" if b.get("tier") else "")
                + f'</p><p class="lead"><b>{who}</b></p><p>{e(b["reason"])}</p>'
                + _baseline_facts(A, b)
                + _sheet_fold(A, b)
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


def _baseline_facts(A: Adapter, b: dict) -> str:
    """What a baseline version says beyond its run (RFC-027): its number, who promoted it, the evidence frozen in
    at promotion, and the line's history, folded."""
    who = b.get("actor") or {}
    by = (e(who.get("name") or "") + (f" for {e(who['for'])}" if who.get("for") else "")) if who else ""
    ev = b.get("evidence") or {}
    vd = ev.get("verdict")
    if b.get("migrated"):
        said = "promoted before 0.8.0: its evidence was not recorded"
    elif ev.get("compared_to") is None:
        said = "the first version: nothing to compare with"
    elif vd:
        said = (
            f"against version {e(ev['compared_to'])}: {e(vd.get('outcome'))}, Δ {vd.get('delta', 0):+.4f}, "
            f"p {fmt_p(vd.get('p'))} on {e(ev.get('measure'))} (n={e(ev.get('n'))})"
        )
    else:
        said = f"against version {e(ev['compared_to'])}: no test ({e('; '.join(ev.get('not_comparable') or []))})"
    fn = getattr(A, "baseline_versions", None)
    older = [
        v
        for v in (fn(b.get("goal"), b["dataset"]) if callable(fn) else [])
        if v.get("version") != b.get("version")
    ]
    hist = "".join(
        f"<li>v{e(v['version'])} · {e(str(v.get('promoted_at') or '')[:10])} · <code>{e(v.get('promoted_from'))}</code>"
        + (f" (restores {e(v['restores'])})" if v.get("restores") else "")
        + f": {e(v.get('reason') or '')}</li>"
        for v in reversed(older)
    )
    return (
        f'<p class="small">version {e(b.get("version"))}'
        + (f", promoted by {by}" if by else "")
        + f" · {said}</p>"
        + (
            f'<details class="inline small"><summary>history ({len(older)})</summary><ul>{hist}</ul></details>'
            if older
            else ""
        )
    )


def _fold(text: str, at: int = 200) -> str:
    """A suggestion as one line: past `at` characters (45 arms named one by one), its opening words up to
    the list, with the whole text folded under them."""
    if len(text) <= at:
        return e(text)
    head = text[: text.find(" (")] if " (" in text[:at] else text[:80] + "…"
    return f'<details class="inline"><summary>{e(head)}</summary><small>{e(text)}</small></details>'


def _rounds_block(
    A: Adapter, g: dict, measure: str, lower: bool, by_ds: dict | None = None, above: str = ""
) -> str:
    """A goal's rounds (ADR-0004), newest first: what each set out to learn, what changed, its arms
    in play and those retired (with why), its best arm and how it compares with the previous
    round's best, its conclusion; for the open round, what the evidence suggests next, each as the
    command that does it. Empty when the goal has no rounds (they are optional). `above`: the page's answer
    so far; a conclusion it already prints is folded here, not printed twice."""
    fn = getattr(A, "rounds", None)
    rounds = [r for r in (fn() if callable(fn) else []) if r.get("goal") == g["goal_id"]]
    if not rounds:
        return ""
    by_id = {r["round_id"]: r for r in rounds}
    # As the goal reads them (RFC-022): an arm every run of which was re-scored is read from its latest re-score.
    instead = {
        a["arm"]: a["superseded_by"]
        for v in (by_ds if by_ds is not None else collect(A)).values()
        for a in v["arms"]
        if a.get("superseded_by")
    }
    for r in rounds:
        r["arms"] = [instead.get(a, a) for a in r.get("arms") or []]

    info = {a["arm"]: a for v in (by_ds if by_ds is not None else collect(A)).values() for a in v["arms"]}

    def comparable(r) -> list:
        """The round's arms its best is read from: as the goal decides, on gold where the dataset has a gold
        group, never a judged copy, never the arm that wrote the reference it is scored against (it scores 1.0)."""
        arms = [
            a
            for a in r.get("arms") or []
            if not (info.get(a) or {}).get("judge") and not (info.get(a) or {}).get("wrote")
        ]
        gold = [a for a in arms if str((info.get(a) or {}).get("reference") or "").startswith("gold/")]
        return gold or arms

    def best(r):
        means = {}
        for a in comparable(r):
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
        n_cfg = len({a.rsplit("/", 1)[-1] for a in r.get("arms") or []})
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
                    f"<b>{e(r['round_id'])}</b> <small>{e(r.get('status', ''))}</small>"
                    + (f"<br><small>from {e(r['from'])}</small>" if r.get("from") else ""),
                    # The conclusion leads, with room to be read: last, in a narrow column, a round's answer ran
                    # thirty lines down the page (owner, 2026-10-31).
                    '<div class="concl">'
                    + (
                        f"<details><summary>the answer so far, above</summary>{e(concl)}</details>"
                        if concl and e(concl) in above
                        else e(concl) or ("<i>open</i>" if r.get("status") == "open" else "—")
                    )
                    + "</div>",
                    '<div class="hyp">' + e(r.get("hypothesis", "") or "—") + "</div>",
                    # Arms, best and the comparison in one narrow cell: three columns of mostly "—" took the width
                    # the conclusion needs (owner, 2026-10-31).
                    # Counted by config, as `evh rounds` counts: a re-score of a run (runs-rescored/...) is that arm.
                    f'<div class="armsbest"><span data-v="{n_cfg}">{n_cfg} arms</span>'
                    + (f" <small>({len(r.get('retired') or [])} retired)</small>" if r.get("retired") else "")
                    # The round's arms in the inspector, against its leader: `evh inspect --round`.
                    + (
                        f' <a class="btn small" title="evh inspect --round {e(r["round_id"])} --goal {e(g["goal_id"])}" '
                        f'href="{inspect_url((r.get("arms") or [])[:INSPECT_MAX], "../", baseline=arm, metric=measure)}">inspect</a>'
                        if arm and len(r.get("arms") or []) > 1
                        else ""
                    )
                    + (
                        f"<br><small>best</small> {arm_link(arm, label, '../')} <small>{fmt(mean)}</small>"
                        if arm
                        else ""
                    )
                    + (f"<br>{vs}" if vs != "—" else "")
                    + "</div>",
                ],
            }
        )
        # An opened round, one heading per part: a single list mixing changes, arms, scoring and evidence read as
        # data tossed in (owner, 2026-10-31).
        changed = [f"<li>{e(c)}</li>" for c in r.get("changes") or []]
        by_reason: dict = {}
        for x in r.get("retired") or []:
            by_reason.setdefault(x["reason"], []).append(x["config_id"])
        carried = r.get("carried") or []
        arms_li = [
            f"<li><b>retired {len(cs)}</b>: {e(why)}<br><small>{', '.join(_config_link(A, r, c) for c in cs)}</small></li>"
            for why, cs in by_reason.items()
        ] + (
            [
                (
                    f'<li><details class="inline"><summary><b>carried in unchanged {len(carried)}</b></summary>'
                    f"<small>{', '.join(_config_link(A, r, c) for c in carried)}</small></details></li>"
                )
            ]
            if carried
            else []
        )
        # The scorer it is judged by, and each change of it (RFC-022): `evh rounds` prints the same lines.
        scoring_li = ([f"<li>judged by <code>{e(r['scorer'])}</code></li>"] if r.get("scorer") else []) + [
            f"<li>{e(str(sc.get('at', ''))[:10])}: {e(sc.get('why', ''))} (<code>{e(sc.get('scorer', ''))}</code>, "
            f"{int(sc.get('runs') or 0)} run(s) re-scored into {e(', '.join(sc.get('written') or []) or '—')})</li>"
            for sc in r.get("scoring") or []
        ]
        evidence_li: list = []
        sugg, notes = "", ""
        if r.get("status") == "open" and getattr(A, "data_dir", None) == _common.DATA:
            try:
                from evaluation_harness.rounds import evidence  # noqa: PLC0415

                ev = evidence(g["goal_id"], r)
                evidence_li = [
                    f"<li>the leader against {e(v['label'])} (<code>{e(v['other'].rsplit('/', 1)[-1])}</code>): "
                    f"{e(v['verdict'])}, Δ {v['delta']:+.4f}, p {fmt_p(v['p'])}</li>"
                    for v in ev["against"]
                ]
                sugg = "".join(
                    f"<li>{_fold(what)}"
                    + (
                        f'<br><code class="cmd">{e(cmd)}</code> <button type="button" class="btn small copy" data-copy="{e(cmd)}">copy</button>'
                        if cmd
                        else ""
                    )
                    + "</li>"
                    for what, cmd in ev["suggest"]
                )
                notes = "".join(f"<li>{e(n)}</li>" for n in ev["notes"])
            except SystemExit:
                sugg = notes = ""
        # One section per round: its header is the row the rounds table had, its body the detail that sat in a
        # second list below the table; one place per round, folded until opened (owner, 2026-10-31).
        cells = rows[-1]["cells"]
        counts = " · ".join(
            x
            for x in (
                f"{len(r.get('changes') or [])} change(s)" if r.get("changes") else "",
                f"{len(r.get('retired') or [])} retired" if r.get("retired") else "",
                f"{len(carried)} carried" if carried else "",
                f"judged by {e(str(r['scorer'])[:12])}" if r.get("scorer") else "",
                "suggested next" if sugg else "",
            )
            if x
        )

        def part(title: str, items: list | str, note: str = "", cls: str = "") -> str:
            inner = "".join(items) if isinstance(items, list) else items
            if not inner:
                return ""
            return (
                f'<h4 class="rc-h">{title}</h4>'
                + (f'<p class="small muted">{note}</p>' if note else "")
                + f"<ul{f' class={chr(34)}{cls}{chr(34)}' if cls else ''}>{inner}</ul>"
            )

        body = (
            part("what changed", changed)
            + part("arms", arms_li)
            + part("scoring", scoring_li)
            + part("evidence", evidence_li)
            + part(
                "suggested next",
                sugg,
                "each as the command that does it; the catalog only reads",
                "suggest",
            )
            + part("notes", notes, cls="muted")
        )
        details.append(
            f'<details class="roundcard {rows[-1]["cls"]}" id="round-{e(r["round_id"])}">'
            f'<summary><div class="rc-round">{cells[0]}</div><div class="rc-concl">{cells[1]}</div>'
            f'<div class="rc-hyp">{cells[2]}</div><div class="rc-arms">{cells[3]}'
            + (f'<br><small class="muted">{counts}</small>' if counts else "")
            + "</div></summary>"
            + (f'<div class="rc-body">{body}</div>' if body else "")
            + "</details>"
        )
    return (
        '<p class="small muted">Rounds are optional: each one sets out to learn something, changes a few '
        "arms, drops what lost and says why, and ends in a conclusion. Decisions are made with "
        "<code>evh round-open</code>, <code>round-retire</code> and <code>round-close</code>; "
        "<code>evh rounds</code> says the same as this page. Open a round for what changed, what was "
        "retired and why, and what to do next.</p>"
        '<div class="roundcards"><div class="rc-head" aria-hidden="true"><div>round</div>'
        f"<div>concluded</div><div>set out to learn</div><div>arms · best on {e(measure)}</div></div>"
        + "".join(details)
        + "</div>"
    )


def _studies_block(g: dict) -> str:
    """A goal's studies (RFC-029): each one's trials as a table (the change, the hypothesis, kept or dropped and why,
    the delta against the best so far, the cost), its stop reason, and its confirmations with their looks."""
    from evaluation_harness import _study  # noqa: PLC0415

    parts = []
    for s in _study.of_goal(g["goal_id"]):
        rows = [
            [
                f"t{r['k']}",
                e(r["change"]),
                e(r["hypothesis"]),
                f'<b>{e(str(r["outcome"]))}</b><br><small class="muted">{e(r["reason"])}</small>',
                f"{r['delta']:+.4g}" if isinstance(r["delta"], (int, float)) else "—",
                f"${r['cost_usd']:.4f}" if isinstance(r["cost_usd"], (int, float)) else "—",
            ]
            for r in s["rows"]
        ]
        conf = "".join(
            f"<li>confirmed on {e(str(c.get('test')))}: <b>{e(str(c.get('outcome')))}</b> ({e(str(c.get('rule')))}, look "
            f"{(c.get('look') or {}).get('number')} at {float((c.get('look') or {}).get('level') or 0):.4%}; delta "
            f"{c.get('delta')} on the test items, {c.get('validation_delta')} on validation)</li>"
            for c in s["confirms"]
        )
        parts.append(
            f'<h3 id="study-{e(s["study"])}">{e(s["study"])}</h3>'
            f'<p class="small muted">{e(s["status"])}, from {e(str(s["baseline"]))}, round {e(str(s["round"]))}, '
            f"${s['spent_usd']:.4f} spent" + (f"; ended: {e(str(s['end']))}" if s["end"] else "") + ". Research: its "
            "p values are nominal; only a confirmation on a test set is evidence.</p>"
            + (table(f"study-{s['study']}", ["trial", "change", "hypothesis", "outcome", "vs best", "cost"], rows) if rows else "")
            + (f"<ul>{conf}</ul>" if conf else "")
        )  # fmt: skip
    return "".join(parts)


def render_goal(A: Adapter, g: dict, by_ds: dict, out: Path, nav: list) -> None:
    """One goal: what it is for, its answer so far (the promoted baselines), how it got there (its rounds), then on
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
    # What the goal is for, then the answer so far, then how it was reached (its rounds): the page explains the
    # goal before it concludes (owner, 2026-10-31).
    body += block("01", "what it is for", f'<dl class="kv">{dl}</dl>')
    answer = _answer(A, g, by_ds, measure)
    body += block("02", "the answer so far", answer)
    n = 3
    rounds_html = _rounds_block(A, g, measure, prim.get("direction") == "lower", by_ds, answer)
    if rounds_html:
        body += block(f"{n:02d}", "how we got here: rounds", rounds_html, "rounds")
        n += 1
    studies_html = _studies_block(g)
    if studies_html:
        body += block(f"{n:02d}", "studies: research, then one confirmation", studies_html, "studies")
        n += 1
    retired_in = retired_in_of(A, g)
    explained = (
        False  # how to read the groups, said once on the page, not under each dataset (CNN: three times)
    )
    said: set = set()  # the strategy paragraphs the page's decisions have printed
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
            + (f'<p class="small">{e(looks_line)}</p>' if (looks_line := _looks.said(ds)) else "")
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
                if not explained
                else ""
            )
            explained = True
            for gi, grp in enumerate(ans["groups"]):
                rows = grp["rows"]
                gm = rows[0].get("measure", measure) if rows else measure  # a judge's group: its score
                dec = group_decision(
                    A,
                    g,
                    ds,
                    rows,
                    gm,
                    retired_in,
                    gold_beside(tiers, ans["groups"], grp["key"]),
                )
                # The decision's leader, as the glance has it: never a retired or flagged arm, so the
                # table, its "test vs leader" links and the decision box name the same arm.
                leader = next((r for r in rows if r["arm"] == dec["leader"]), None)
                shown = shown_axes(dec)
                trs = []
                named, _scorer = shown_labels({r["arm"]: r["label"] for r in rows})
                renamed = sorted(((r["label"], named[r["arm"]]) for r in rows), key=lambda x: -len(x[0]))

                def as_named(text: str, renamed: list = renamed) -> str:
                    for lb, nm in renamed:
                        text = text.replace(lb, nm)
                    return text

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
                                arm_link(r["arm"], named[r["arm"]], "../", wrap=True) + tag,
                                f'<span data-v="{r["mean"]}">{fmt(r["mean"])}</span>',
                                f'<span data-v="{r["n"]}">{r["n"]}</span>',
                                *(
                                    NO_CALL
                                    if r.get("recorded") and ax["name"] in ("cost", "speed")
                                    else axis_cell(ax, dec["rows"][r["arm"]][ax["name"]])
                                    for ax in shown
                                ),
                                e(as_named("; ".join(r["flags"] + dec["out"].get(r["arm"], []))) or "—"),
                                link,
                            ],
                        }
                    )
                # Retired arms stay in the table (history) but are not tested again: the link names the leader's
                # live rivals, and says how many it leaves out.
                live = [r["arm"] for r in rows if not retired_round(retired_in, r["arm"]) or r is leader]
                arms = live[:INSPECT_MAX]
                left_out = len(rows) - len(live)
                what = grp["key"]
                need = (g.get("success_criteria") or {}).get("min_items")
                short = (
                    f' <small class="retired" title="the goal asks for at least {need} {e(A.item_word)}s per arm '
                    f"before an arm may lead\">below the goal's min_items ({need}): shown, never recommended</small>"
                    if need and rows and all(any("min_items" in f for f in r["flags"]) for r in rows)
                    else ""
                )
                inner += f'<h3 class="sub">{group_heading(what, rows)}{short}</h3>'
                if leader and len(arms) > 1:
                    inner += (
                        f'<p><a class="btn" href="{inspect_url(arms, "../", baseline=leader["arm"], metric=gm)}">'
                        "Test every arm in this group against its leader</a>"
                        + (
                            f' <small class="muted">({left_out} retired arm{"s" if left_out != 1 else ""} left out)</small>'
                            if left_out
                            else ""
                        )
                        + "</p>"
                    )
                inner += decision_html(
                    dec, {r["arm"]: r["label"] for r in rows}, g, "../", baseline_gap(A, dec, rows, gm), said
                )
                inner += table(
                    f"ans{n}_{gi}",
                    [
                        "arm",
                        f"mean {e(gm)}",
                        f"{e(A.item_word)}s",
                        *(axis_head(ax) for ax in shown),
                        "flags",
                        "",
                    ],
                    trs,
                )
                inner += tradeoff_charts(dec, named, gm)
        inner += _failure_modes_html(A, ds, v.get("arms") or [])
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


def _failure_modes_html(A: Adapter, ds: str, rows: list) -> str:
    """How the dataset's arms fail, from the tags on their outputs (PLAN_0.8.0 D1): per tagged arm the outputs read, how
    many had a failure and each mode's count. A tag needs no measure, so every arm of the dataset is listed, not only
    those of a group. Empty when none was tagged (or the adapter has no tags)."""
    fn = getattr(A, "tag_counts", None)
    got = [(r, fn(ds, r["arm"])) for r in rows] if callable(fn) else []
    got = [(r, c) for r, c in got if c]
    if not got:
        return ""
    named, _scorer = shown_labels({r["arm"]: r["label"] for r, _ in got})
    lis = "".join(
        f"<li>{arm_link(r['arm'], named[r['arm']], '../')}: {c['tagged']} of {c['outputs']} output(s) read have a failure"
        + (": " + ", ".join(f"{e(m)} {n}" for m, n in c["modes"].items()) if c["modes"] else "")
        + "</li>"
        for r, c in got
    )
    return (
        '<p class="small"><b>failure modes</b> <small class="muted">(tagged by hand on outputs read; '
        f'<code>evh tags --dataset-id {e(ds)}</code>)</small></p><ul class="small">{lis}</ul>'
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
    """The round that retired this arm: by its arm id, else by its config id. An arm read through its re-score
    (`runs-rescored/<scorer>/<arm>`, RFC-022, the goal's reading of it) is the arm it re-scored: without this, an
    arm a round retired stayed among the goal's contenders whenever it had been re-scored (found 2026-11-01: 25 of
    the triage goal's 76 contenders were round 3's retirements)."""
    if arm.startswith("runs-rescored/") and arm.count("/") >= 3:
        arm = arm.split("/", 2)[2]
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


def goal_clusters(A: Adapter, g: dict, ds: str) -> tuple[dict | None, str | None]:
    """({item: cluster key}, field) when the goal's entry for `ds` names `cluster: FIELD`, else (None, None).
    Items with no value for the field are clusters of their own (stats.clustered)."""
    field = next((d.get("cluster") for d in g.get("datasets") or [] if d.get("dataset_id") == ds), None)
    if not field:
        return None, None
    values = item_fields(A, ds).get("values") or {}
    return {i: v[field] for i, v in values.items() if v.get(field) not in (None, "")}, field


def group_decision(
    A: Adapter,
    g: dict,
    ds: str,
    rows: list,
    gm: str,
    retired_in: dict,
    gold: str | None = None,
) -> dict:
    """The goal's decision over one group of arms on one dataset (axes.decide): its axes, limits,
    the quality leader, the contenders and the tie-break. A judge's group decides on the judge's score;
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
    baseline = next((r["arm"] for r in rows if r.get("baseline")), None)
    clusters, cluster_by = goal_clusters(A, g, ds)
    dec = axes.decide(
        goal,
        arms,
        lambda m: "lower" if A.lower_is_better(m, ds) else None,
        machines,
        baseline=baseline,
        clusters=clusters,
        cluster_by=cluster_by,
    ) | {"goal": goal, "dataset": ds}
    if not decides_on(g, ds):
        # The goal never decides here (a pilot slice, a generalization check): the leader stands, the
        # recommendation does not.
        role = next((d.get("role") for d in g.get("datasets") or [] if d.get("dataset_id") == ds), "") or ""
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still undecided"))],
            f"The goal does not decide on {ds}"
            + (f" ({role})" if role else "")
            + ": shown, not recommended.",
        ]
    elif gold:
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still undecided"))],
            (
                f"Scored against silver, beside {gold}: gold decides on {ds}; this group is shown, not "
                "recommended. Silver is not what the goal decides on: a model's opinion (its author's "
                "family ranks higher on it) or what production recorded afterwards; its caveat says which."
            ),
        ]
    elif gm != (crit.get("primary") or {}).get("measure") and not gm.endswith("_unvalidated"):
        # A re-measurement (a judge's grade, pick or pairwise, or a scorer's other metric): the goal recommends from
        # the group it decides on, its own measure; this one shows its leader beside it (owner, 2026-11-03).
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still undecided"))],
            (
                f"Read on {gm}: the goal decides on {(crit.get('primary') or {}).get('measure')}; this group is "
                "shown, not recommended."
            ),
        ]
    elif gm.endswith("_unvalidated"):
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still undecided"))],
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
    the recommended arm differs on quality, and whether the paired test finds the difference significant. Both can
    be right: the rule follows the strategy, the baseline is a person's decision."""
    from evaluation_harness import stats  # noqa: PLC0415

    rec = dec["recommended"]
    base = next((r for r in rows if r.get("baseline")), None)
    if not rec or base is None or base["arm"] == rec:
        return ""
    # as the page's other reasons name them: the scorer most arms are read through is named once, not after each
    labels = shown_labels({r["arm"]: r["label"] for r in rows})[0]
    higher = dec["axes"][0]["direction"] == "higher"
    series = {a: (A.scores(a).get(gm) or {}).get("values") or {} for a in (rec, base["arm"])}
    clusters = goal_clusters(A, dec.get("goal") or {}, dec.get("dataset") or "")[0]
    row = (
        stats.compare(series, base["arm"], higher_is_better=higher, family=1, clusters=clusters).get("rows")
        or [None]
    )[0]
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
    from evaluation_harness import _goal_view  # noqa: PLC0415

    v = cell.get("value")
    over = cell.get("within") is False
    vs = (cell.get("vs_leader") or {}).get("verdict")
    ni = cell.get("noninferior")
    title = (
        (f"vs the quality leader: {vs}" if vs else "")
        + (f"; contender test: {_goal_view.ni_text(ni)}" if ni else "")
        + ("; past the limit" if over else "")
    )
    attrs = f'data-v="{v if v is not None else ""}"' + (' class="over"' if over else "")
    attrs += f' title="{e(title)}"' if title else ""
    return f"<span {attrs}>{e(cell_text(ax, cell))}</span>"


LONG_LIST = 8
RESCORED = re.compile(r" · rescored ([0-9a-f]{8})")


def brief(label: str) -> str:
    """An arm's label in a summary table (goals at a glance, the goals page): without the re-score's scorer, which
    the goal page names. "x · rescored 5f2c057c, repeats ×3" reads "x · repeats ×3"."""
    m = RESCORED.search(label)
    if not m:
        return label
    rest = label[m.end() :]
    return label[: m.start()] + (" · " + rest[2:] if rest.startswith(", ") else rest)


def shown_labels(labels: dict) -> tuple[dict, str]:
    """({arm: label as a page shows it}, the scorer): when most of a group's arms are read through one re-score
    (RFC-022), the page names that scorer once and its arms without it. "x · rescored 5f2c057c, repeats ×3" reads
    "x · repeats ×3"; an arm through another scorer keeps its suffix."""
    hashes = [m.group(1) for lb in labels.values() if (m := RESCORED.search(lb))]
    common = max(set(hashes), key=hashes.count) if hashes else ""
    if not common or hashes.count(common) * 2 <= len(labels):
        return dict(labels), ""
    drop = f" · rescored {common}"
    return {a: lb.replace(f"{drop}, ", " · ").replace(drop, "") for a, lb in labels.items()}, common


def why_lines(dec: dict, labels: dict) -> list[str]:
    """The decision's reasons as HTML, for a page: the scorer every arm is read through named once, not after each
    arm, and a list of more than LONG_LIST arms (the triage goal's 50 contenders, then the same 50 undecided) given
    as a count with the names folded under it. `evh goals` prints them whole."""
    shown, common = shown_labels({a: labels[a] for a in dec["rows"] if a in labels})
    drop = bool(common)
    # Label by label, longest first, so a list's commas are never touched.
    short = {
        labels[a]: shown[a] for a in sorted(shown, key=lambda a: -len(labels[a])) if shown[a] != labels[a]
    }

    def bare(s: str) -> str:
        for lb, sh in short.items():
            s = s.replace(lb, sh)
        return s

    def listed(arms: list) -> str:
        return ", ".join(labels[x] for x in arms)

    def folded(arms: list) -> str:
        return f"{len(arms)} arms<details><summary>which</summary>{e(bare(listed(arms)))}</details>"

    close = [x for x in dec.get("contenders") or [] if x != dec.get("leader")]
    left = dec.get("undecided") or []
    out = []
    for w in dec["why"]:
        if w.startswith("Strategy ") and len(close) > LONG_LIST and f": {listed(close)}." in w:
            head, _, rest = w.partition(f": {listed(close)}.")
            out.append(f"{e(bare(head))}: {folded(close)}{e(bare(rest))}")
        elif w.startswith("Still undecided") and left and set(left) == set(dec.get("contenders") or []):
            out.append(e(f"Still undecided after the tie-break: all {len(left)} contenders."))
        elif w.startswith("Still undecided") and len(left) > LONG_LIST:
            out.append(f"Still undecided after the tie-break: {folded(left)}")
        else:
            out.append(e(bare(w)))
    if drop:
        out.insert(0, e(f"Every arm here is read through its re-score by scorer {common} (RFC-022)."))
    return out


def axis_head(ax: dict) -> str:
    """An axis as a column head: its name on the first line, its limit small on the second, the whole in the
    title. On one line, "false_alarm · no worse than the baseline (paired test)" ran past the table's edge."""
    full = axis_title(ax)
    name, _, limit = full.partition(" · ")
    return f'<span title="{e(full)}">{e(name)}</span>' + (f"<br><small>{e(limit)}</small>" if limit else "")


def decision_html(dec: dict, labels: dict, g: dict, up: str, gap: str = "", said: set | None = None) -> str:
    """What the goal's rule concludes for this group, and why, in the goal's own terms; `gap`
    says how it differs from the promoted baseline (baseline_gap). `said`: the page's strategy paragraphs so far;
    one already printed is not printed again (the CNN goal page printed the same one six times)."""

    if not dec["rows"]:
        return ""
    rec = dec["recommended"]
    head = (
        f"Recommended: <b>{arm_link(rec, shown_labels(labels)[0][rec], up)}</b>"
        if rec
        else "Shown, not recommended"
        if dec.get("shown_only")
        else "No single arm recommended" + (" yet" if dec["leader"] else ": no arm is eligible")
    )
    weighs = "; ".join(axis_title(a) for a in dec["axes"])
    why = "".join(f"<li>{w}</li>" for w in why_lines(dec, labels))
    if gap:
        why += f'<li class="gap"><b>{e(gap)}</b></li>'
    rule = (
        f'<p class="small muted">Strategy <b>{e(strategy_of(dec["goal"]))}</b> '
        f"({e(STRATEGIES[strategy_of(dec['goal'])])}). Weighs {e(weighs)}. Among the contenders on quality, "
        f"the tie-break is {e(', '.join(tie_break_of(dec['goal'])))}. The rule recommends; promoting "
        "is <code>evh run-promote</code>; the goal chooses its strategy (<code>strategy:</code>).</p>"
    )
    # The strategy and tie-break are the goal's: once per page. A judged group's own quality measure is in its
    # reasons ("Read on judge_score: the goal decides on coverage").
    key = (strategy_of(dec["goal"]), tuple(tie_break_of(dec["goal"])))
    if said is not None and key in said:
        rule = ""
    elif said is not None:
        said.add(key)
    return f'<div class="decision"><p class="lead">{head}</p><ul class="small">{why}</ul>{rule}</div>'


def tradeoff_charts(dec: dict, labels: dict, quality_name: str) -> str:
    """Quality against each other axis, for the eligible arms, the frontier drawn: the trade-off at
    a glance. Two to a row."""
    from evaluation_harness import catalog_charts as ch  # noqa: PLC0415

    q = dec["axes"][0]
    # The arms the rule could recommend: not over a limit, not flagged (the reference's author,
    # too few items, a format the goal does not take), not retired.
    eligible = dec["eligible"]
    charts: list[str] = []
    notes: list[str] = []
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
        if len(pts) > 1 and len({p[0] for p in pts}) == 1:
            # Every arm the same on this axis (all free): no trade-off to draw, and the drawn one had a "$-1" axis.
            usd = ax["name"] == "cost" and ax["measure"] == "cost_usd"
            same = f"${pts[0][0]:.6f}".rstrip("0").rstrip(".") if usd else fmt(pts[0][0])
            notes.append(f"{ax['name']}: {same} for every arm, so no trade-off to draw")
            continue
        svg = ch.scatter(
            pts,
            f"{ax['name']}{stat}{unit}",
            quality_name,
            lower_x=ax["direction"] == "lower",
            higher_y=q["direction"] == "higher",
            # a number draws its line; the baseline limit is a paired test, not a line
            x_limit=ax.get("limit") if isinstance(ax.get("limit"), (int, float)) else None,
            y_limit=q.get("limit") if isinstance(q.get("limit"), (int, float)) else None,
            fmt_x=(lambda v: f"${v:.4f}") if ax["name"] == "cost" and ax["measure"] == "cost_usd" else None,
            width=HALF,
        )
        if svg:
            charts.append(f"<div>{svg}</div>")
    note = f'<p class="small muted">{e("; ".join(notes))}.</p>' if notes else ""
    return (f'<div class="duo">{"".join(charts)}</div>' if charts else "") + note


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
    for m in sorted(idx, key=lambda k: (k.startswith(("total_", "self_family_", "resumed", "failed")), k)):
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
    "gold": "Promoted as gold: the yardstick a decision rests on.",
    "silver": "Promoted as silver: consistent, not a claim that any arm is right; good for ranking arms against "
    "each other.",
}


def render_references(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """One page per reference set: what it is, who wrote it, and every arm scored against it."""
    for ds, v in by_ds.items():
        tiers = {r["id"]: r["tier"] for r in v["refs"]}
        for r in v["refs"]:
            scored = [a for a in v["arms"] if a["reference"] == r["id"] and not a["judge"]]
            pf = r.get("promoted_from") or {}
            facts = [
                ("tier", tier_pill(r["tier"])),
                ("dataset", f'<a class="cell-link" href="../d/{slug(ds or "none")}.html">{e(ds)}</a>'),
                ("promoted from", promoted_from_html(r, "../") if pf else ""),
                ("promoted by", e(r.get("promoted_by") or "")),
                ("why", e(r.get("reason") or "")),
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
            dek = e(TIER_WORDS.get(r["tier"], ""))
            if pf:
                when = (r.get("created_at") or "")[:10]
                by = f", by {e(r['promoted_by'])}" if r.get("promoted_by") else ""
                dek += (
                    f"<br>Promoted from {promoted_from_html(r, '../')}"
                    + (f", {e(when)}" if when else "")
                    + by
                    + (f": {e(r['reason'])}" if r.get("reason") else "")
                )
                if ((pf.get("source") or {}).get("kind")) == "model":
                    dek += "<br>The arm whose outputs these are is graded against its own outputs."
            body = hero("reference", f"<code>{e(r['id'])}</code> {tier_pill(r['tier'])}", dek)
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


NO_CALL = '<span class="muted">recorded, no call</span>'


def group_heading(key: str, rows: list) -> str:
    """A goal's group of arms, headed by what they are scored against: a judge, a label set by its source chip, a
    reference with its tier pill (UXS-001)."""
    if key.startswith("judge "):
        return "scored by " + e(key)
    if key.startswith("labels/"):
        kind = next((r.get("labels_source") for r in rows if r.get("labels_source")), "")
        return "scored against " + label_set_html(key.removeprefix("labels/"), kind, "../")
    return f"scored against {reference_link(key, '../')} {tier_pill(key.split('/', 1)[0])}".rstrip()


def deploy_verdicts(sh: dict) -> str:
    """Per capture whose records say what production ran: "matches", or what differs on how many records."""
    out = []
    for c in sh.get("captures") or []:
        cap = f'capture <a class="cell-link" href="{{up}}captures.html#capture-{e(c["capture"])}">{e(c["capture"])}</a>'
        if c.get("ok"):
            out.append(
                f"{cap}: every one of its {c['records']} decisions was made by the promoted model and prompt"
            )
            continue
        bits = []
        for k, row in c["keys"].items():
            if row["missing"] == c["records"] and not row["match"] and not row["differ"]:
                # "0 match; not recorded: 233" read as a failure: nothing was compared.
                bits.append(f"<code>{e(k)}</code>: production recorded none, so it cannot be checked")
                continue
            b = f"<code>{e(k)}</code> {row['match']} match"
            if row["differ"]:
                b += "; differ: " + ", ".join(f"{e(v)} ({n})" for v, n in list(row["differ"].items())[:5])
            if row["missing"]:
                b += f"; not recorded: {row['missing']}"
            bits.append(b)
        out.append(f"{cap}, {c['records']} decisions: " + " · ".join(bits))
    return "".join(f"<li>{x}</li>" for x in out)


def deploy_sheet_html(sh: dict, up: str) -> str:
    """The deploy sheet (PRD-005 FR3): what production must match to run what was measured, then what each capture
    says production ran."""
    m = sh.get("model") or {}
    dep = m.get("deployment") or {}
    facts = [
        ("measured by", f"<code>{e(sh['run_id'])}</code> on {dataset_link(sh.get('dataset_id') or '', up)}"),
        ("against", e((sh.get("reference") or {}).get("id") or "")),
        ("model sent", f"<code>{e(m.get('sent') or '')}</code>"),
        (
            "model record",
            f"<code>{e(m.get('record'))}</code>" if m.get("record") else "no model record names it",
        ),
        ("deployment", e(" · ".join(str(dep[k]) for k in ("id", "where", "tag") if dep.get(k)))),
        ("server", e(str(m.get("server") or "not recorded"))),
        ("build", e(str(m.get("build") or "none recorded (a hosted model has no digest)"))),
        (
            "settings sent",
            "<br>".join(
                f"<code>{e(k)}: {e(json.dumps(v) if not isinstance(v, str) else v)}</code>"
                for k, v in (sh.get("sent") or {}).items()
            ),
        ),
        (
            "not sent",
            "<br>".join(
                [f"bookkeeping: <code>{e(', '.join(sh.get('not_sent') or []))}</code>"]
                * bool(sh.get("not_sent"))
                + [
                    f"<b>the record sets <code>{e(k)}: {e(json.dumps(v) if not isinstance(v, str) else v)}</code>; this arm did not send it</b>"
                    for k, v in (sh.get("record_settings_not_sent") or {}).items()
                ]
            ),
        ),
        (
            "declared",
            "<br>".join(
                f"<code>{e(part)}.{e(k)}: {e(v)}</code>"
                for part, kv in (sh.get("declared") or {}).items()
                for k, v in kv.items()
            ),
        ),
        (
            "reported per item",
            "<br>".join(
                f"<code>{e(k)}: {e(', '.join(vs))}</code>" for k, vs in (sh.get("reported") or {}).items()
            ),
        ),
        (
            "adapter",
            f"<code>{e((sh.get('adapter') or {}).get('id') or '')}</code> <small>{e((sh.get('adapter') or {}).get('sha256') or '')[:12]}</small>",
        ),
        ("harness", e(" ".join(str(x) for x in (sh.get("harness") or {}).values() if x))),
    ]
    dl = "".join(f"<dt>{e(k)}</dt><dd>{v}</dd>" for k, v in facts if v)
    v = deploy_verdicts(sh).replace("{up}", up)
    caps = (
        f'<p class="small">What production ran, as its captures say:</p><ul class="small">{v}</ul>'
        if v
        else '<p class="small muted">No capture here says what production ran (the adapter\'s production_ran).</p>'
    )
    return (
        f'<dl class="kv">{dl}</dl>{caps}<p class="small">Command: <code>evh deploy-sheet --config '
        f"{e(sh['config_id'])} [--capture C]</code></p>"
    )


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
    if a.get("superseded_by"):
        facts.append(
            (
                "re-scored",
                f"the goals read its re-score, {arm_link(a['superseded_by'], a['superseded_by'], '../')}",
            )
        )
    dl = "".join(f"<dt>{e(k)}</dt><dd>{x}</dd>" for k, x in facts if x)
    # The baseline of the arm's own goal (RFC-027), else the dataset's own.
    base = next(
        (b for b in reversed(v.get("baselines") or []) if b.get("goal") == (a.get("goal") or None)), None
    )
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
        e(a["label"])
        + (' <span class="tag-base">baseline</span>' if a.get("baseline") else "")
        + (' <span class="badge recorded">recorded</span>' if a.get("recorded") else ""),
        (
            f"Production's decisions, from the capture "
            f'<a class="cell-link" href="../captures.html#capture-{e(a["recorded"])}">{e(a["recorded"])}</a>; '
            f"no model was called. Scored like any arm on {dataset_link(ds, '../')}."
        )
        if a.get("recorded")
        else f"One config on {dataset_link(ds, '../')}, scored one way; its repeats averaged per {e(A.item_word)}.",
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
    if a.get("recorded"):
        body += block(
            f"{n:02d}",
            "cost and speed",
            f'<p class="small">{NO_CALL}: its outputs are what production decided, read from the capture.</p>',
        )
        n += 1
    elif any(c["n"] or (c.get("tokens") or {}).get("n") for _, c in cs):
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
    if a.get("recorded"):
        kv = "".join(
            f"<dt>{e(k)}</dt><dd>{v_}</dd>"
            for k, v_ in (
                (
                    "capture",
                    f'<a class="cell-link" href="../captures.html#capture-{e(a["recorded"])}">{e(a["recorded"])}</a>',
                ),
                ("recorded arm", f"<code>{e(cfg.get('config_id', ''))}</code>"),
                ("outputs read by", e(cfg.get("recorded_by") or "")),
                ("adapter", f"<code>{e(cfg.get('adapter') or '')}</code>"),
            )
            if v_
        )
        body += block(f"{n:02d}", "config", f'<dl class="kv">{kv}</dl>')
        n += 1
    elif cfg.get("params"):
        kv = "".join(
            f"<dt>{e(k)}</dt><dd><code>{e(json.dumps(x) if not isinstance(x, str) else x)}</code></dd>"
            for k, x in sorted(cfg["params"].items())
        )
        extra = (
            f'<p class="small muted">config <code>{e(cfg.get("config_id", ""))}</code>'
            + (f" · adapter <code>{e(cfg['adapter'])}</code>" if cfg.get("adapter") else "")
            + (f" · deployment <code>{e(cfg['deployment'])}</code>" if cfg.get("deployment") else "")
            + " · credentials are never shown</p>"
        )
        body += block(f"{n:02d}", "config", extra + f'<dl class="kv">{kv}</dl>')
        n += 1
    sheet_fn = getattr(A, "deploy_sheet", None)
    sheet = sheet_fn(a["arm"]) if a.get("baseline") and callable(sheet_fn) else None
    if sheet:
        body += block(f"{n:02d}", "deploy sheet", deploy_sheet_html(sheet, "../"), "deploy-sheet")
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
        # A sentence, not "r1 of … · in play · closed": what the round was and what it did with this arm.
        lis = "".join(
            f"<li>Round <b>{e(r['round_id'])}</b> of "
            f"{goal_link(goals[r['goal']], '../') if r.get('goal') in goals else e(r.get('goal', ''))}"
            + (f", {e(r['status'])}" if r.get("status") else "")
            + (": <b>retired</b> in it" if {a["arm"], cid} & _retired_arms(r) else ": one of its arms")
            + ".</li>"
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
        # The arm that wrote a reference scores 1.0 against it: on the strip it ran the silver scale to 1.0 and
        # squashed every other arm. It stays in the table, marked; the strip says it is left out.
        authors = [a["label"] for a in arms if a.get("wrote")]
        for a in arms:
            if a.get("wrote"):
                continue
            key = f"judge {a['judge']}" if a["judge"] else (a.get("reference") or "no reference")
            groups.setdefault(key, []).append((a["means"][m][0], a["label"]))
        chart = (
            ch.strip(groups, f"{m} per arm on {ds}, by what each is scored against", lower=lower)
            + (
                f'<p class="small muted">Not drawn: {e(", ".join(authors))}, scored against the reference it '
                "wrote (its row is in the table).</p>"
                if authors
                else ""
            )
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
                        tier_pill(r["tier"]),
                        dataset_link(ds),
                        f'<span data-v="{r.get("items") or ""}">{r.get("items") if r.get("items") is not None else "—"}</span>',
                        (
                            promoted_from_html(r, arm=_author_link(r, v, ""))
                            if r.get("author")
                            and ((r.get("promoted_from") or {}).get("source") or {}).get("config_id")
                            == r["author"]
                            else promoted_from_html(r)
                            + (f" <small>{_author_link(r, v, '')}</small>" if r.get("author") else "")
                        ),
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
        "Reference sets",
        "What arms are scored against: labels promoted on purpose, at the tier chosen then. Gold is the "
        "yardstick a decision rests on; silver is consistent, good for ranking arms against each other, not a "
        "claim that any arm is right.",
        cp.bar(w["first"], w["until"]),
    )
    body += block(
        "01",
        "reference sets",
        cp.row_chips("references", "reference sets")
        + table(
            "references",
            [
                "reference set",
                "tier",
                "dataset",
                f"{e(A.item_word)}s",
                "promoted from",
                "created",
                "arms scored",
                "arms scored in period",
                "runs in period",
            ],
            rows,
            "filter reference sets",
            period=True,
        )
        if rows
        else '<p class="muted">No reference sets yet: a reference set is a label set promoted on purpose, '
        '<code>evh reference-promote --dataset-id D --labels SET --tier gold|silver --reason "…" --by WHO</code>; '
        'the label sets are on the <a class="cell-link" href="labels.html">labels page</a>.</p>',
    )
    write(
        out,
        "references.html",
        page(
            "Reference sets",
            body,
            0,
            "references",
            PERIOD_SCRIPTS("references"),
            nav=nav,
            item=A.item_word,
            elsewhere=(("references", {}),),
        ),
    )


def origin_html(v: dict, up: str = "") -> str:
    """A dataset's origin in a few words, its capture linked to the Captures page."""
    cap = v.get("capture") or ""
    text = e(v.get("origin") or "")
    if not cap:
        return text
    return text.replace(
        e(f"capture {cap}"), f'capture <a href="{up}captures.html#capture-{e(cap)}">{e(cap)}</a>', 1
    )


def render_captures(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """captures.html: what a production system did, kept as records (RFC-019), and the datasets frozen from each
    capture; an adapter without captures shows how to make one."""
    fn = getattr(A, "captures", None)
    caps = fn() if callable(fn) else []
    rows = []
    for c in caps:
        imp = str(c.get("importer") or "").rsplit("/", 1)[-1]
        when = (
            f"{_when(str(c.get('first') or ''))} – {_when(str(c.get('last') or ''))}"
            if c.get("first")
            else "—"
        )
        rows.append(
            [
                f'<b id="capture-{e(c["capture"])}">{e(c["capture"])}</b>'
                + (
                    f'<br><small class="muted">continues {e(c["continues"])}</small>'
                    if c.get("continues")
                    else ""
                ),
                f'<span data-v="{int(c.get("records") or 0)}">{int(c.get("records") or 0)}</span>'
                + (
                    f'<br><small class="muted">a sample: rate {e(str(c["sample"]["rate"]))}, '
                    f"of {int(c['sample'].get('read') or 0)} read</small>"
                    if isinstance(c.get("sample"), dict)
                    else ""
                ),
                f"<code>{e(imp)}</code>"
                + (' <small class="muted">scrubbed</small>' if c.get("scrubbed") else ""),
                f'<span data-v="{e(str(c.get("captured_at") or ""))}">{e(_when(str(c.get("captured_at") or "")))}</span>',
                e(when),
                ", ".join(
                    (dataset_link(d) if d in by_ds else f'{e(d)} <small class="muted">no runs yet</small>')
                    + _sets_on(A, d)
                    for d in c.get("datasets") or []
                )
                or "—",
                *(
                    [
                        ", ".join(
                            arm_link(a, a.rsplit("/", 1)[-1])
                            for a, cap in sorted(RECORDED.items())
                            if cap == c["capture"]
                        )
                        or "—"
                    ]
                    if RECORDED
                    else []
                ),
            ]
        )
    body = hero(
        "captures",
        "Captures",
        "What a system did in production, kept as records, each hashed: the source of the datasets frozen from them. "
        "What happened next becomes labels through rules you can read (<code>evh label-from-capture</code>): a "
        "<code>rule</code> label set, promoted like any.",
    )
    body += block(
        "01",
        "captures",
        table(
            "captures",
            [
                "capture",
                "records",
                "importer",
                "captured",
                "records from – to",
                "datasets made from it",
                # Only when a capture has one: a column of "—" on every row says nothing.
                *(["recorded arm"] if RECORDED else []),
            ],
            rows,
            "filter captures",
        )
        if rows
        else '<p class="muted">No captures yet: <code>evh capture --importer jsonl --query \'{"path": "…"}\' '
        "--capture &lt;id&gt;</code> keeps what a system did, then <code>evh dataset-from-capture</code> freezes a "
        "dataset from it.</p>",
    )
    write(
        out,
        "captures.html",
        page("Captures", body, 0, "captures", nav=nav, item=A.item_word, elsewhere=(("captures", {}),)),
    )


def render_prompts(A: Adapter, out: Path, nav: list) -> None:
    """prompts.html (RFC-028): every prompt name with its versions (lineage, notes, who made each) and the runs that
    used each, with their score. The text and the diffs only when the project publishes them
    (`catalog: {publish: [prompts]}`); otherwise hashes and sizes, and `evh prompt-diff` shows the text."""
    import difflib  # noqa: PLC0415

    from evaluation_harness import _prompt_cmd, _prompts  # noqa: PLC0415

    show = _prompts.published()
    used = _prompt_cmd._runs_of()
    names = _prompts.names()
    rows, sections = [], []
    for name in names:
        vs = _prompts.versions(name)
        n_runs = sum(len(used.get((name, v["sha256"]), [])) for v in vs)
        anchor = "prompt-" + re.sub(r"[^A-Za-z0-9_-]", "-", name)
        rows.append([f'<a class="cell-link" href="#{e(anchor)}">{e(name)}</a>', str(len(vs)), str(n_runs)])
        items, prev = [], None
        for v in vs:
            runs = used.get((name, v["sha256"]), [])
            who = (v.get("actor") or {}).get("name") or "?"
            text = ""
            if show:
                try:
                    cur = _prompts.text_of(v["id"]).decode("utf-8", "replace")
                except FileNotFoundError:
                    cur = ""
                if prev is None:
                    text = f"<details><summary>text</summary><pre>{e(cur)}</pre></details>"
                else:
                    diff = "".join(
                        difflib.unified_diff(prev.splitlines(True), cur.splitlines(True), "before", "after")
                    )
                    text = f"<details><summary>the change from v{v['n'] - 1}</summary><pre>{e(diff)}</pre></details>"
                prev = cur
            run_list = ", ".join(
                f"{arm_link('runs/' + r['dataset_id'] + '/' + r['config_id'], r['config_id']) if r.get('dataset_id') else e(r['run_id'])}"
                + (
                    f' <small class="muted">{e(str(r["metric"]))} {e(str(r["score"]))}</small>'
                    if r.get("score") is not None
                    else ""
                )
                for r in runs
            )
            items.append(
                f'<li><b>v{v["n"]}</b> <code>{e(v["id"])}</code> <small class="muted">{e(str(v.get("created_at")))} by '
                f"{e(who)}, {int(v.get('bytes') or 0)} bytes"
                + (f", from <code>{e(str(v['parent']))}</code>" if v.get("parent") else "")
                + f"</small><br>{e(str(v.get('note') or ''))}"
                + (f"<br><small>runs: {run_list}</small>" if run_list else "")
                + text
                + "</li>"
            )
        sections.append(f'<h3 id="{e(anchor)}">{e(name)}</h3><ul class="plain">{"".join(items)}</ul>')
    body = hero(
        "prompts",
        "Prompts",
        "The prompt files the arms declare, each version kept by its content, with who made it, from which, and the runs "
        "that used it. "
        + ("" if show else "The text is not published here: <code>evh prompt-diff</code> shows it, and "
           "<code>catalog: {publish: [prompts]}</code> in config.yaml puts it on these pages."),
    )  # fmt: skip
    body += block(
        "01",
        "prompts",
        (table("prompts", ["prompt", "versions", "runs"], rows, "filter prompts") + "".join(sections))
        if rows
        else '<p class="muted">No prompt versions yet: declare <code>prompts:</code> in an arm config and its next run '
        "records them (<code>evh prompts</code>).</p>",
    )
    write(
        out,
        "prompts.html",
        page("Prompts", body, 0, "prompts", nav=nav, item=A.item_word, elsewhere=(("prompts", {}),)),
    )


def _sets_on(A: Adapter, ds: str) -> str:
    """The label sets made on a dataset, as source chips with their names, under it."""
    sets = [x for x in _label_sets_of(A) if x["dataset"] == ds]
    if not sets:
        return ""
    return (
        "<br><small>"
        + " ".join(label_set_html(x["id"], (x.get("source") or {}).get("kind", "")) for x in sets)
        + "</small>"
    )


def render_labels(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """labels.html (RFC-023): every label set, its source, what it covers, who made it, whether it was promoted."""
    fn = getattr(A, "label_sets", None)
    sets = fn() if callable(fn) else []
    size = getattr(A, "dataset_items", None)
    rows = []
    for x in sets:
        n = (
            (size(x["dataset"]) if callable(size) else None)
            or (by_ds.get(x["dataset"]) or {}).get("items")
            or 0
        )
        kind = (x.get("source") or {}).get("kind", "")
        rows.append(
            {
                "key": x["id"],
                "cells": [
                    f'<span id="set-{slug(x["id"])}">{label_set_html(x["id"], kind)}</span>',
                    dataset_link(x["dataset"])
                    if x["dataset"] in by_ds
                    else f"<code>{e(x['dataset'])}</code>",
                    f'<span data-v="{x["n_items"]}">{x["n_items"]} of {n or "?"}</span>',
                    e((x.get("guideline") or {}).get("path") or "none"),
                    _made_line(x.get("source") or {}, x.get("created_at")),
                    _promoted_as(A, x["id"]).replace('href="../', 'href="'),
                ],
            }
        )
    body = hero(
        "labels",
        "Labels",
        "A label is what is right for one item, and who said it: a person, a model or a rule. A label set is never "
        "edited, and its labels follow an item by its bytes into any dataset holding it. A reference is labels "
        "promoted on purpose, at the tier chosen then.",
    )
    body += block(
        "01",
        "label sets",
        table(
            "labelsets",
            ["set", "dataset", "coverage", "guideline", "made", "promoted"],
            rows,
            "filter label sets",
        )
        if rows
        else '<p class="muted">No labels yet: <code>evh label-sheet --dataset-id D --out sheet.csv</code>, filled '
        "and read back with <code>evh label-import sheet.csv --dataset-id D --set S --by WHO</code>; a run's outputs "
        "with <code>evh label-from-run --run R --set S</code>.</p>",
    )
    write(
        out,
        "labels.html",
        page("Labels", body, 0, "labels", nav=nav, item=A.item_word, elsewhere=(("labels", {}),)),
    )


def write_pick(A: Adapter, by_ds: dict, out: Path, rows: list[dict]) -> None:
    """What the inspector's picker chooses from (assets/inspect.js): each goal with its datasets,
    each dataset with its arm count and goals, and each arm as the arms page describes it
    (catalog_arms.arm_rows): config, model, model record, hosted or local, how it was scored,
    what against, its roles and its value on the deciding measure. Without this file the
    picker is a plain list of arm names."""
    goals = [
        {
            "id": g["goal_id"],
            "t": g.get("title") or g["goal_id"],
            "ds": [d["dataset_id"] for d in g.get("datasets") or [] if d.get("dataset_id") in by_ds],
        }
        for g in A.goals()
    ]
    datasets = {
        ds: {"n": len(v["arms"]), "g": [g["id"] for g in goals if ds in g["ds"]]}
        for ds, v in sorted(by_ds.items())
    }
    arms = {
        r["arm"]: {
            "d": r["dataset"],
            "c": r["config"],
            "m": r["model"],
            "r": r["record"],
            "w": "local" if r["local"] else "hosted",
            "h": r["how"],
            "s": r["scored"],
            "ro": r["roles"],
            "v": r["value"],
            "ms": r["measure"],
        }
        for r in rows
    }
    write(
        out,
        "pick.js",
        "window.PICK="
        + json.dumps(
            {"goals": goals, "datasets": datasets, "arms": arms, "max": INSPECT_MAX}, separators=(",", ":")
        )
        + ";\n",
    )


def render_data(A: Adapter, out: Path, page_fn=page, serve: str = "evh catalog-serve", **page_kw) -> None:
    """The Configure page (UXS-004), built only for a project that deploys it; assets/data.js fills it from the local
    server's /api/data/. The one page
    that writes, and only through a server on this machine (ADR-0027)."""
    body = (
        '<section class="hero slim"><div class="wrap"><p class="kicker">configure</p>'
        "<h1>Project data</h1><p class=dek>What this project keeps under data/: its settings, which you can "
        "create, change and delete here, and the data the harness wrote, shown read-only.</p>"
        '<p class="dm-store small" id="store"></p></div></section>'
        '<section class="block tight"><div class="wrap" id="app">'
        f'<p class="muted">Loading… (this page needs <code>{e(serve)}</code> on this machine; opened from disk it '
        "cannot read the project's data.)</p></div></section>"
    )
    write(
        out,
        "data.html",
        page_fn(
            "Project data",
            body,
            0,
            "configure",
            ("assets/data_form.js", "assets/data.js"),
            item=A.item_word,
            serve=serve,
            elsewhere=(("data-ls", {}),),
            **page_kw,
        ),
    )


def render_inspect(
    A: Adapter,
    out: Path,
    page_fn=page,
    serve: str = "evh catalog-serve",
    *,
    pages: bool = False,
    pick: bool = False,
    **page_kw,
) -> None:
    """The inspector shell; assets/inspect.js fills it from the local server's /api/. `pages`: the
    catalog beside it has a page per arm and per metric (the harness's own build), so the
    inspector links to them; a project's own builder without them leaves it False. `pick`: the
    build wrote pick.js (write_pick), so the picker chooses by goal, dataset and facets."""
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
            ("runs.js", *(("pick.js",) if pick else ()), "assets/inspect.js"),
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
    configure = _common.configure()
    nav = [*NAV, CONFIGURE_NAV] if configure else NAV
    if _store.exists(out):
        _store.rmtree(out)
    copy_assets(out, configure)
    A = scores_once(A)  # one build: each arm's scores read once, not for every page that asks
    by_ds = collect(A)
    write_periods(A, by_ds, out)
    render_home(A, by_ds, out, nav)
    render_activity(A, by_ds, out, nav)
    from evaluation_harness.catalog_arms import arm_rows, render_arms  # noqa: PLC0415
    from evaluation_harness.catalog_models import render_models  # noqa: PLC0415

    arms_rows = arm_rows(A, by_ds)
    render_arms(A, by_ds, out, nav, arms_rows)
    render_models(A, by_ds, out, nav, arms_rows)
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
    render_captures(A, by_ds, out, nav)
    render_prompts(A, out, nav)
    render_labels(A, by_ds, out, nav)
    render_reference_index(A, by_ds, out, nav)
    write_search(A, by_ds, out)
    write_pick(A, by_ds, out, arms_rows)
    render_inspect(A, out, nav=nav, pages=True, pick=True)
    if configure:
        render_data(A, out, nav=nav)
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


def _exchange(a: Path, b: Path) -> bool:
    """Swap two directories in one system call, so no reader ever finds `b` absent: Linux's renameat2 with
    RENAME_EXCHANGE, macOS's renamex_np with RENAME_SWAP (both through ctypes, the standard library). False where
    neither exists or the call fails (an older kernel, another filesystem): the caller then renames twice."""
    import ctypes  # noqa: PLC0415
    import ctypes.util  # noqa: PLC0415
    import sys as _s  # noqa: PLC0415

    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        if _s.platform.startswith("linux") and hasattr(libc, "renameat2"):
            at_fdcwd, rename_exchange = -100, 2
            return libc.renameat2(at_fdcwd, bytes(a), at_fdcwd, bytes(b), rename_exchange) == 0
        if _s.platform == "darwin" and hasattr(libc, "renamex_np"):
            rename_swap = 0x2
            return libc.renamex_np(bytes(a), bytes(b), rename_swap) == 0
    except (OSError, AttributeError, TypeError):
        return False
    return False


def build_beside(A: Adapter, out: Path, sections: tuple = ()) -> dict:
    """`build` into a folder beside `out`, then swapped in (RFC-026 step 4): a server serving `out` keeps serving the
    old pages until the new ones are whole, a failed build leaves them as they were, and two builds at once never
    empty each other's folder (each has its own). The swap is one system call where the platform has one (Linux,
    macOS), so `out` is never absent; elsewhere it is two renames, absent for the time between them."""
    import os  # noqa: PLC0415

    tag = f"{os.getpid()}"
    nxt, old = out.with_name(f"{out.name}.next-{tag}"), out.with_name(f"{out.name}.old-{tag}")
    try:
        counts = build(A, nxt, sections)
    except BaseException:
        _store.rmtree(nxt, ignore_errors=True)
        raise
    if _store.exists(out) and _exchange(nxt, out):
        _store.rmtree(nxt, ignore_errors=True)  # the old pages, swapped out
        return counts
    if _store.exists(out):
        _store.replace(out, old)
    _store.replace(nxt, out)
    _store.rmtree(old, ignore_errors=True)
    return counts


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
    ap.add_argument(
        "--json",
        action="store_true",
        help="one JSON object on stdout when done (the text goes to stderr as it is printed): the envelope every --json command gives (result.blocks, result.values)",
    )
    args = ap.parse_args()
    with _jsonout.collect("catalog", args.json, live=sys.stderr):
        for flag, url in (("--mcp", args.mcp), ("--mcp-howto", args.mcp_howto), ("--card", args.card)):
            if url and not url.startswith(("https://", "http://")):
                die(f"{flag} {url!r}: expected https://...", "bad-argument")
        MCP = args.mcp or ""
        CARD = args.card or ""
        MCP_HOWTO = args.mcp_howto or MCP_HOWTO
        if not args.api.startswith("/") or not args.api.endswith("/"):
            die(
                f"--api {args.api!r}: expected a path that starts and ends with /, e.g. /catalog/api/",
                "bad-argument",
            )
        API = args.api
        BRAND = args.brand
        if args.head:
            if not _store.is_file(args.head):
                die(f"--head {args.head}: no such file", "not-found")
            HEAD = _store.read_text(args.head, encoding="utf-8").strip() + "\n"
        if args.repo:
            if not args.repo.startswith(("https://", "http://")):
                die(
                    f"--repo {args.repo!r}: expected https://..., where the project's files can be read",
                    "bad-argument",
                )
            REPO = args.repo if args.repo.endswith("/") else args.repo + "/"
        if args.about:
            if not _store.is_file(args.about):
                die(f"--about {args.about}: no such file", "not-found")
            ABOUT = _store.read_text(args.about, encoding="utf-8").strip()
        sections = []
        for spec in args.link:
            label, _, url = spec.partition("=")
            if not label or not (url == "." or url.startswith(("https://", "http://"))):
                die(f"--link {spec!r}: expected LABEL=https://... or LABEL=. for the catalog", "bad-argument")
            sections.append((label, url))
        if sections and not any(u == "." for _, u in sections):
            sections.insert(0, ("Catalog", "."))
        counts = build_beside(load_catalog_adapter(args.adapter), args.out, tuple(sections))
        print(f"catalog: {args.out} — " + ", ".join(f"{v} {k}" for k, v in counts.items()))
        _jsonout.values({"out": str(args.out), "counts": counts})
        print("inspect: evh catalog-serve, then open the address it prints")
        return 0


if __name__ == "__main__":
    sys.exit(main())
