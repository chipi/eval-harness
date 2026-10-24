#!/usr/bin/env python3
"""Build the catalog: static pages over a project's runs, plus the run inspector's shell.

    evh catalog [--out .build/catalog] [--adapter path/to/file.py:Class]
    make catalog

Pages: the catalog's home (every dataset, with its arms and references), one page per dataset
(every arm on it, with its headline number, and an "inspect" link per arm and for all of
them), and the inspector shell, which `evh catalog-serve` fills from the adapter.

The output embeds counts and means only, never an item's text: outputs and references leave
the data tree only through the local inspector server (ADR-0002). The page shell (`page`,
`hero`, `block`, `table`) and the assets are the parts a project's own builder reuses.
"""

from __future__ import annotations

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

import _fields  # noqa: E402
from _common import ROOT  # noqa: E402
from catalog_adapter import Adapter, item_fields, load_catalog_adapter  # noqa: E402

#: The front-end files every page loads: installed beside the package, or in a checkout.
ASSET_DIR = next(p for p in (HERE / "catalog_assets", HERE.parent / "catalog_assets") if p.is_dir())
ASSETS = ("style.css", "catalog.css", "catalog.js", "inspect.js", "forest.js", "icon.svg")
#: Links that would put more arms than this in one inspector URL go to the picker instead.
INSPECT_MAX = 40

#: The theme is applied before first paint by assets/head.js, a file rather than an inline
#: script, so the pages need no 'unsafe-inline' in a Content-Security-Policy.
HEAD_JS_SRC = """(function(){var t;try{t=localStorage.getItem('theme');}catch(e){}
if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;
document.documentElement.classList.add('js');})();
"""

NAV = [
    ("home", "index.html", "Catalog"),
    ("goals", "goals.html", "Goals"),
    ("metrics", "metrics.html", "Metrics"),
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
}


def describe_metric(metric: str, project: dict) -> str:
    """What a metric measures: the project's own words, else the harness's, else ""."""
    if project.get(metric):
        return project[metric]
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


def metric_link(metric: str, up: str = "") -> str:
    """A metric's name, linked to its row on the metrics page."""
    if not metric:
        return "—"
    return f'<a class="cell-link" href="{up}metrics.html#m-{slug(metric)}">{e(metric)}</a>'


def reference_page(ref: str) -> str:
    """The reference's page, relative to the catalog root."""
    return f"r/{slug(ref)}.html"


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
    brand: str = "eval catalog",
    item: str = "item",
    serve: str = "evh catalog-serve",
    footer: str = "",
) -> str:
    """Build a complete HTML page with header, nav, body, and footer."""
    up = "../" * depth
    links = "".join(
        f'<a href="{href if "://" in href else up + href}"{" aria-current=page" if key == here else ""}'
        f"{f' class={rest[0]}' if rest else ''}>{label}</a>"
        for key, href, label, *rest in nav
    )
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    foot = footer or (
        f"Built {built} by <code>evh catalog</code>. The pages carry counts and means "
        f"only; {e(item)} text is fetched from the inspector when you open an {e(item)}."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{e(title)} · {e(brand)}</title>
<meta name="color-scheme" content="dark light">
<script src="{up}assets/head.js"></script>
<link rel="stylesheet" href="{up}assets/style.css">
<link rel="stylesheet" href="{up}assets/catalog.css">
<link rel="icon" href="{up}assets/icon.svg" type="image/svg+xml">
</head>
<body data-up="{up}" data-item="{e(item)}" data-serve="{e(serve)}">
<header class="bar"><div class="wrap">
  <a class="brand" href="{up}index.html"><img class="mark" src="{up}assets/icon.svg"
    alt="" width="28" height="28"><span>{e(brand)}</span></a>
  <div class="search"><input id="q" type="search" placeholder="Search everything  ( / )"
    autocomplete="off" aria-label="Search the catalog"><div id="hits" hidden></div></div>
  <nav class="nav">{links}</nav>
  <button id="theme" class="theme" aria-label="Toggle light and dark">◐</button>
</div></header>
<main>
{body}
</main>
<footer><div class="wrap"><p>{foot}</p></div></footer>
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


def table(tid: str, heads: list, rows: list, filt: str = "") -> str:
    """Build an HTML table with optional search filter. A row is a list of cells, or
    {"cells": [...], "cls": "...", "id": "..."} for a row with a class or an anchor."""
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
        a = (f' class="{attrs["cls"]}"' if attrs.get("cls") else "") + (
            f' id="{attrs["id"]}"' if attrs.get("id") else ""
        )
        return f"<tr{a}>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

    body = "".join(tr(r) for r in rows)
    return (
        f'{f}<div class="scroll-x"><table id="{tid}" class="data sortable"><thead><tr>{th}</tr>'
        f"</thead><tbody>{body}</tbody></table></div>"
    )


def write(out: Path, rel: str, content: str) -> None:
    """Write content to a relative path within output directory."""
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


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
    for arm in A.arms():
        d = A.describe(arm)
        sc = A.scores(arm)
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


def render_home(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """Render the catalog home page with all datasets."""
    rows = []
    for ds in sorted(by_ds, key=lambda d: (-len(by_ds[d]["arms"]), d)):
        v = by_ds[ds]
        parent = (v.get("parent") or {}).get("dataset_id")
        rows.append(
            [
                f'<a href="d/{slug(ds or "none")}.html">{e(ds or "(no dataset_id)")}</a>'
                + (
                    f'<br><small>from <a class="cell-link" href="d/{slug(parent)}.html">{e(parent)}</a></small>'
                    if parent
                    else ""
                ),
                f'<span data-v="{v["items"]}">{v["items"]}</span>',
                f'<span data-v="{len(v["arms"])}">{len(v["arms"])}</span>',
                ", ".join(
                    f'<a class="cell-link" href="{reference_page(r["id"])}">{e(r["id"])}</a>'
                    for r in v["refs"]
                )
                or "—",
            ]
        )
    n_arms = sum(len(v["arms"]) for v in by_ds.values())
    body = hero(
        "catalog",
        "Every run, by dataset",
        f"{n_arms} arms on {len(by_ds)} datasets. An arm is one config on one dataset, its "
        f"repeats averaged per {e(A.item_word)}, exactly as <code>pair-test</code> reads it. "
        "Open a dataset to compare its arms in the inspector.",
    )
    body += block(
        "01",
        "datasets",
        table("datasets", ["dataset", f"{e(A.item_word)}s", "arms", "references"], rows, "filter datasets"),
    )
    write(out, "index.html", page("Catalog", body, 0, "home", nav=nav, item=A.item_word))


def render_dataset(A: Adapter, ds: str, v: dict, out: Path, nav: list) -> None:
    """Render a page for one dataset with all its arms."""
    arms = sorted(
        v["arms"],
        key=lambda a: (
            a["metric"],
            (a["mean"] if a["mean"] is not None else -1e18) * (1 if a["lower"] else -1),
            a["label"],
        ),
    )
    tiers = {r["id"]: r["tier"] for r in v["refs"]}
    # The machine is named only when the arms ran on more than one: then latency and cost per
    # second differ by machine, and the inspector's conditions say how.
    machines = {a["machine"] for a in arms if a.get("machine")}
    rows = [
        {
            "cls": row_kind(a, tiers),
            "cells": [
                e(a["label"])
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
        btn = (
            f'<div class="answer"><p class="small muted">baseline, promoted {e((b["promoted_at"] or "")[:10])}</p>'
            f'<p class="lead"><b>{e(label)}</b></p><p>{e(b["reason"])}</p></div>'
        ) + btn
    refs = "".join(
        f'<li><a class="cell-link" href="../{reference_page(r["id"])}"><code>{e(r["id"])}</code></a> · {e(r["tier"])}'
        + (f" · written by <code>{e(r['author'])}</code>" if r.get("author") else "")
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
            ["arm", "metric", "mean", f"{e(A.item_word)}s", "runs", "scored against", ""],
            rows,
            "filter arms",
        ),
    )
    n = 1
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
    write(out, f"d/{slug(ds or 'none')}.html", page(ds or "dataset", body, 1, "", nav=nav, item=A.item_word))


def _show(v, field: dict) -> str:
    if field.get("type") == "duration" and isinstance(v, (int, float)):
        secs = round(v)
        return f"{secs // 3600}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
    s = fmt(v) if isinstance(v, float) else str(v)
    return s + (f" {field['unit']}" if field.get("unit") else "")


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
            if measure not in a["means"]:
                continue
            mean, n = a["means"][measure]
            flags = []
            if need and n < need:
                flags.append(f"n {n} < min_items {need}")
            if a["format"] and formats and a["format"] not in formats:
                flags.append(f"format {a['format']} not in the contract")
            if a["wrote"]:
                flags.append("wrote the reference it is scored against")
            rows.append(dict(a, mean=mean, n=n, filed=a["goal"] == goal["goal_id"], flags=flags))
        out.append((ds, d.get("role", ""), d.get("notes", ""), rows))
    return out


def render_goals(A: Adapter, by_ds: dict, out: Path, nav: list) -> int:
    """Render the goals page and one page per goal; return the number rendered."""
    goals = A.goals()
    rows = []
    for g in goals:
        prim = (g.get("success_criteria") or {}).get("primary") or {}
        filed = sum(1 for v in by_ds.values() for a in v["arms"] if a["goal"] == g["goal_id"])
        rows.append(
            [
                f'<a href="g/{slug(g["goal_id"])}.html">{e(g.get("title") or g["goal_id"])}</a>',
                e(g.get("statement", "")),
                e(f"{prim.get('measure', '')} ({prim.get('direction', '')})"),
                e(", ".join(d.get("dataset_id", "") for d in g.get("datasets") or [])),
                f'<span data-v="{filed}">{filed}</span>',
            ]
        )
        render_goal(A, g, by_ds, out, nav)
    dek = (
        "What each evaluation is for: who uses the output, the decision it informs, and the "
        "measure that decides. Runs name their goal in their config (<code>goal:</code>)."
    )
    body = hero("goals", "Goals", dek)
    body += block(
        "01",
        "goals",
        table("goals", ["goal", "statement", "decides", "datasets", "arms filed"], rows)
        if rows
        else '<p class="muted">No goals yet: add <code>data/goals/&lt;goal_id&gt;.yaml</code> '
        "(schema: <code>goal.schema.json</code>).</p>",
    )
    write(out, "goals.html", page("Goals", body, 0, "goals", nav=nav, item=A.item_word))
    return len(goals)


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
        head = f'<a class="cell-link" href="../d/{slug(ds or "none")}.html">{e(ds)}</a>'
        if bl:
            b = bl[-1]
            arm = label.get(b.get("arm") or "", b["run"])
            parts.append(
                f'<div class="answer"><p class="small muted">{head} · baseline promoted {e(_when(b["promoted_at"]))}'
                + (f" · scored against {e(b['tier'])}" if b.get("tier") else "")
                + f'</p><p class="lead"><b>{e(arm)}</b></p><p>{e(b["reason"])}</p>'
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
    body = hero("goal", e(g.get("title") or g["goal_id"]), e(g.get("statement", "")))
    body += block("01", "the answer so far", _answer(A, g, by_ds, measure))
    body += block("02", "what it is for", f'<dl class="kv">{dl}</dl>')
    n = 3
    for ans in goal_answers(g, by_ds):
        ds, v = ans["dataset"], by_ds.get(ans["dataset"]) or {}
        tiers = {r["id"]: r["tier"] for r in v.get("refs", [])}
        lin = (v.get("parent") or {}).get("dataset_id")
        about = (
            f'<p><a class="cell-link" href="../d/{slug(ds or "none")}.html">{e(ds)}</a>: '
            f"{v.get('items', 0)} {e(A.item_word)}s"
            + (f" · {e(ans['role'])}" if ans["role"] else "")
            + (f' · made from <a class="cell-link" href="../d/{slug(lin)}.html">{e(lin)}</a>' if lin else "")
            + "</p>"
            + (f'<p class="small muted">{e(ans["notes"])}</p>' if ans["notes"] else "")
            + (
                '<p class="small">references: '
                + ", ".join(
                    f'<a class="cell-link" href="../{reference_page(r["id"])}">{e(r["id"])}</a>'
                    + (f" (written by {e(r['author'])})" if r.get("author") else "")
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
                "Flagged arms are never the leader.</p>"
            )
            for gi, grp in enumerate(ans["groups"]):
                leader, rows = grp["leader"], grp["rows"]
                trs = []
                for r in rows:
                    link = (
                        f'<a class="btn small" href="{inspect_url([r["arm"], leader["arm"]], "../", baseline=leader["arm"], metric=measure)}">test vs leader</a>'
                        if leader and r["arm"] != leader["arm"]
                        else ("leader" if leader and r is leader else "")
                    )
                    tag = (
                        ' <small title="its config names this goal">filed</small>' if r["filed"] else ""
                    ) + (' <span class="tag-base">baseline</span>' if r.get("baseline") else "")
                    trs.append(
                        {
                            "cls": row_kind(r, tiers),
                            "cells": [
                                e(r["label"]) + tag,
                                f'<span data-v="{r["mean"]}">{fmt(r["mean"])}</span>',
                                f'<span data-v="{r["n"]}">{r["n"]}</span>',
                                e("; ".join(r["flags"]) or "—"),
                                link,
                            ],
                        }
                    )
                arms = [r["arm"] for r in rows][:INSPECT_MAX]
                what = grp["key"]
                inner += f'<h3 class="sub">{"scored by " + e(what) if what.startswith("judge ") else "scored against " + e(what)}</h3>'
                if leader and len(arms) > 1:
                    inner += (
                        f'<p><a class="btn" href="{inspect_url(arms, "../", baseline=leader["arm"], metric=measure)}">'
                        "Test every arm in this group against its leader</a></p>"
                    )
                inner += table(
                    f"ans{n}_{gi}",
                    ["arm", f"mean {e(measure)}", f"{e(A.item_word)}s", "flags", ""],
                    trs,
                )
        body += block(f"{n:02d}", f"{ds}{' · ' + ans['role'] if ans['role'] else ''}", inner)
        n += 1
    write(
        out,
        f"g/{slug(g['goal_id'])}.html",
        page(g.get("title") or g["goal_id"], body, 1, "goals", nav=nav, item=A.item_word),
    )


def metric_index(A: Adapter, by_ds: dict) -> dict:
    """{metric: {"datasets": {dataset: arms recording it}, "goals": [goal ids deciding on it]}}."""
    out: dict = {}
    for ds, v in by_ds.items():
        for a in v["arms"]:
            for m in a["means"]:
                out.setdefault(m, {"datasets": {}, "goals": []})["datasets"].setdefault(ds, 0)
                out[m]["datasets"][ds] += 1
    for g in A.goals():
        m = ((g.get("success_criteria") or {}).get("primary") or {}).get("measure")
        if m:
            out.setdefault(m, {"datasets": {}, "goals": []})["goals"].append(g)
    return out


def render_metrics(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """One page, one row per metric: what it measures, which way is better, where it is recorded,
    and which goals decide on it. A row's anchor is #m-<metric>, which every metric link uses."""
    fn = getattr(A, "metric_descriptions", None)
    project = fn() if callable(fn) else {}
    idx = metric_index(A, by_ds)
    rows = []
    for m in sorted(idx, key=lambda k: (k.startswith(("total_", "self_family_", "resumed")), k)):
        where = idx[m]
        lower = any(A.lower_is_better(m, ds) for ds in where["datasets"]) if where["datasets"] else False
        # Direction first: cost, tokens and latency are "neutral" to the tests but lower is better.
        better = "lower" if lower else ("neutral: a description" if A.is_neutral(m) else "higher")
        text = describe_metric(m, project)
        rows.append(
            {
                "id": f"m-{slug(m)}",
                "cells": [
                    f'<code class="nowrap">{e(m)}</code>',
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
                    or "—",
                ],
            }
        )
    body = hero(
        "metrics",
        "Metrics",
        "What each number on these pages measures, which way is better, where it is recorded, and "
        "which goals decide on it. A project describes its own metrics with "
        "<code>METRIC_DESCRIPTIONS</code> in its adapter; the harness describes its own.",
    )
    body += block(
        "01",
        "metrics",
        table(
            "metrics",
            ["metric", "what it measures", "better", "recorded on", "decides"],
            rows,
            "filter metrics",
        ),
    )
    write(out, "metrics.html", page("Metrics", body, 0, "metrics", nav=nav, item=A.item_word))


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
                ("written by", f"<code>{e(r['author'])}</code>" if r.get("author") else ""),
                ("from the run", f"<code>{e(r['from_run'])}</code>" if r.get("from_run") else ""),
                ("model", e(r.get("model") or "")),
                ("created", e(r.get("created_at") or "")),
            ]
            dl = "".join(f"<dt>{e(k)}</dt><dd>{v_}</dd>" for k, v_ in facts if v_)
            rows = [
                {
                    "cls": row_kind(a, tiers),
                    "cells": [
                        e(a["label"]),
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
                page(r["id"], body, 1, "", nav=nav, item=A.item_word),
            )


def render_inspect(A: Adapter, out: Path, page_fn=page, serve: str = "evh catalog-serve", **page_kw) -> None:
    """The inspector shell; assets/inspect.js fills it from the local server's /api/."""
    arms = {a: A.describe(a)["dataset"] for a in sorted(A.arms())}
    write(out, "runs.js", "window.RUNS=" + json.dumps(arms) + ";\n")
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
            **page_kw,
        ),
    )


def write_search(A: Adapter, by_ds: dict, out: Path) -> None:
    """Write the search index as a JavaScript file."""
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
                    "u": inspect_url([a["arm"]]),
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
        idx.append({"k": "metric", "t": m, "d": "metric", "u": f"metrics.html#m-{slug(m)}", "s": m.lower()})
    for g in A.goals():
        idx.append(
            {
                "k": "goal",
                "t": g.get("title") or g["goal_id"],
                "d": g.get("statement", "")[:120],
                "u": f"g/{slug(g['goal_id'])}.html",
                "s": f"{g['goal_id']} {g.get('title', '')} {g.get('statement', '')}".lower(),
            }
        )
    write(out, "search.js", "window.CATALOG=" + json.dumps(idx, separators=(",", ":")) + ";\n")


def build(A: Adapter, out: Path, links: tuple = ()) -> dict:
    """Build all catalog pages and return statistics. `links` are extra nav entries,
    (key, url, label) each."""
    nav = NAV + list(links)
    if out.exists():
        shutil.rmtree(out)
    copy_assets(out)
    by_ds = collect(A)
    render_home(A, by_ds, out, nav)
    for ds, v in by_ds.items():
        v["versions"] = _version_links(by_ds, ds, "../")
        render_dataset(A, ds, v, out, nav)
    n_goals = render_goals(A, by_ds, out, nav)
    render_metrics(A, by_ds, out, nav)
    render_references(A, by_ds, out, nav)
    write_search(A, by_ds, out)
    render_inspect(A, out, nav=nav)
    return {
        "goals": n_goals,
        "datasets": len(by_ds),
        "arms": sum(len(v["arms"]) for v in by_ds.values()),
        "references": sum(len(v["refs"]) for v in by_ds.values()),
    }


def main() -> int:
    """Build the catalog and write static pages to output directory."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
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
        help="add a link to the nav, e.g. Findings=https://evals.example.org/ (repeatable)",
    )
    args = ap.parse_args()
    links = []
    for spec in args.link:
        label, _, url = spec.partition("=")
        if not url.startswith(("https://", "http://")):
            raise SystemExit(f"--link {spec!r}: expected LABEL=https://...")
        links.append((label.lower(), url, label))
    counts = build(load_catalog_adapter(args.adapter), args.out, tuple(links))
    print(f"catalog: {args.out} — " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    print("inspect: evh catalog-serve, then open the address it prints")
    return 0


if __name__ == "__main__":
    sys.exit(main())
