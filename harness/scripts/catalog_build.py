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
    ("inspect", "inspect.html", "Inspector"),
]


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
        f'<a href="{href if "://" in href else up + href}"{" aria-current=page" if key == here else ""}>{label}</a>'
        for key, href, label in nav
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
    """Build an HTML table with optional search filter."""
    th = "".join(f"<th>{h}</th>" for h in heads)
    f = ""
    if filt:
        f = (
            f'<div class="filter"><input type="search" data-filter="{tid}" placeholder="{e(filt)}" '
            f'aria-label="{e(filt)}"><span class="muted small"><span data-count="{tid}">{len(rows)}</span>'
            f" shown</span></div>"
        )
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
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
    # The dataset's own size, from the ADAPTER: the harness's DATASETS path is not where a
    # project with its own layout keeps them. An adapter that cannot say falls back to the
    # most items any arm scored.
    size = getattr(A, "dataset_items", None)
    for ds, v in by_ds.items():
        n = size(ds) if callable(size) else None
        v["items"] = n if n is not None else max((a["n"] for a in v["arms"]), default=0)
    return by_ds


def render_home(A: Adapter, by_ds: dict, out: Path, nav: list) -> None:
    """Render the catalog home page with all datasets."""
    rows = []
    for ds in sorted(by_ds, key=lambda d: (-len(by_ds[d]["arms"]), d)):
        v = by_ds[ds]
        rows.append(
            [
                f'<a href="d/{slug(ds or "none")}.html">{e(ds or "(no dataset_id)")}</a>',
                f'<span data-v="{v["items"]}">{v["items"]}</span>',
                f'<span data-v="{len(v["arms"])}">{len(v["arms"])}</span>',
                e(", ".join(r["id"] for r in v["refs"]) or "—"),
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
    rows = [
        [
            e(a["label"]),
            e(a["metric"] or "—"),
            (
                f'<span data-v="{a["mean"] if a["mean"] is not None else ""}">{fmt(a["mean"])}'
                f"{' ↓' if a['lower'] else ''}</span>"
            ),
            f'<span data-v="{a["n"]}">{a["n"]}</span>',
            str(a["runs"]),
            e(a["reference"] or "—"),
            f'<a class="btn small" href="{inspect_url([a["arm"]], "../")}">inspect</a>',
        ]
        for a in arms
    ]
    # One button per group of arms that can be tested together: the same headline metric,
    # scored against the same reference. A silver-scored and a gold-scored run both record
    # the metric but measure different things, and the inspector sets such arms aside.
    groups: dict = {}
    for a in arms:
        groups.setdefault((a["metric"] or "", a["reference"] or ""), []).append(a["arm"])
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
    refs = "".join(f"<li><code>{e(r['id'])}</code> · {e(r['tier'])}</li>" for r in v["refs"])
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
        table(
            "arms",
            ["arm", "metric", "mean", f"{e(A.item_word)}s", "runs", "reference", ""],
            rows,
            "filter arms",
        ),
    )
    n = 1
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


def goal_answers(goal: dict, by_ds: dict) -> list:
    """[(dataset, role, rows, leader)] for one goal: on each of its datasets, every arm that
    records the goal's primary measure, best first. Only arms on the same dataset are ever
    ranked together; an arm filed under the goal is marked, and so is one whose format the
    goal does not accept or whose items are fewer than its min_items."""
    crit = goal.get("success_criteria") or {}
    measure = (crit.get("primary") or {}).get("measure", "")
    lower = (crit.get("primary") or {}).get("direction") == "lower"
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
            rows.append(dict(a, mean=mean, n=n, filed=a["goal"] == goal["goal_id"], flags=flags))
        rows.sort(key=lambda r: (bool(r["flags"]), r["mean"] if lower else -r["mean"], r["label"]))
        leader = next((r for r in rows if not r["flags"]), None)
        out.append((ds, d.get("role", ""), rows, leader))
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


def render_goal(A: Adapter, g: dict, by_ds: dict, out: Path, nav: list) -> None:
    """Render a page for one goal showing which arms satisfy its criteria."""
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
    body += block("01", "what it is for", f'<dl class="kv">{dl}</dl>')
    n = 2
    for ds, role, rows, leader in goal_answers(g, by_ds):
        if not rows:
            inner = f'<p class="muted">No arm on this dataset records <code>{e(measure)}</code>.</p>'
        else:
            trs = []
            for r in rows:
                link = (
                    (
                        f'<a class="btn small" href="{inspect_url([r["arm"], leader["arm"]], "../", baseline=leader["arm"], metric=measure)}">'
                        "test vs leader</a>"
                    )
                    if leader and r["arm"] != leader["arm"]
                    else ("leader" if leader and r is leader else "")
                )
                trs.append(
                    [
                        e(r["label"]) + (" <small>filed</small>" if r["filed"] else ""),
                        f'<span data-v="{r["mean"]}">{fmt(r["mean"])}</span>',
                        f'<span data-v="{r["n"]}">{r["n"]}</span>',
                        e("; ".join(r["flags"]) or "—"),
                        link,
                    ]
                )
            arms = [r["arm"] for r in rows][:INSPECT_MAX]
            all_link = (
                (
                    f'<p><a class="btn" href="{inspect_url(arms, "../", baseline=leader["arm"], metric=measure)}">'
                    "Test every arm against the leader</a></p>"
                )
                if leader and len(arms) > 1
                else ""
            )
            inner = (
                f'<p class="small muted">Mean {e(measure)} over each arm\'s {e(A.item_word)}s; a mean is not a '
                "verdict: the inspector tests each arm against the leader (Holm across them). "
                "Flagged arms are never the leader.</p>"
                + all_link
                + table(f"ans{n}", ["arm", f"mean {e(measure)}", f"{e(A.item_word)}s", "flags", ""], trs)
            )
        body += block(f"{n:02d}", f"{ds}{' · ' + role if role else ''}", inner)
        n += 1
    write(
        out,
        f"g/{slug(g['goal_id'])}.html",
        page(g.get("title") or g["goal_id"], body, 1, "goals", nav=nav, item=A.item_word),
    )


def render_inspect(A: Adapter, out: Path, page_fn=page, **page_kw) -> None:
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
        '<p class="muted">Loading… (this page needs <code>evh catalog-serve</code>; opened '
        "from disk it cannot read runs.)</p></div></section>"
    )
    write(
        out,
        "inspect.html",
        page_fn("Inspector", body, 0, "inspect", ("runs.js", "assets/inspect.js"), item=item, **page_kw),
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
        render_dataset(A, ds, v, out, nav)
    n_goals = render_goals(A, by_ds, out, nav)
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
