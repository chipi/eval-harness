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
sys.path.insert(0, str(HERE))

from _common import DATASETS, ROOT  # noqa: E402
from catalog_adapter import Adapter, load_adapter  # noqa: E402

#: The front-end files every page loads: installed beside the package, or in a checkout.
ASSET_DIR = next(p for p in (HERE / "catalog_assets", HERE.parent / "catalog_assets") if p.is_dir())
ASSETS = ("style.css", "catalog.css", "catalog.js", "inspect.js", "forest.js", "icon.svg")
#: Links that would put more arms than this in one inspector URL go to the picker instead.
INSPECT_MAX = 40

HEAD_JS = """<script>
(function(){var t;try{t=localStorage.getItem('theme');}catch(e){}
if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;
document.documentElement.classList.add('js');})();
</script>"""

NAV = [("home", "index.html", "Catalog"), ("inspect", "inspect.html", "Inspector")]


def e(s) -> str:
    return html.escape(str(s), quote=True)


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-") or "x"


def page(title: str, body: str, depth: int = 0, here: str = "", scripts: tuple = (), *,
         nav: list = NAV, brand: str = "eval catalog", item: str = "item",
         serve: str = "evh catalog-serve", footer: str = "") -> str:
    up = "../" * depth
    links = "".join(f'<a href="{up}{href}"{" aria-current=page" if key == here else ""}>{label}</a>'
                    for key, href, label in nav)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    foot = footer or (f"Built {built} by <code>evh catalog</code>. Counts and means only: no "
                      f"{e(item)} text is embedded; the inspector reads it from this machine.")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{e(title)} · {e(brand)}</title>
<meta name="color-scheme" content="dark light">
{HEAD_JS}
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
    d = f'<p class="dek">{dek}</p>' if dek else ""
    return (f'<section class="hero slim"><div class="wrap"><p class="kicker">{kicker}</p>'
            f"<h1>{title}</h1>{d}{extra}</div></section>")


def block(num: str, eyebrow: str, inner: str, anchor: str = "") -> str:
    aid = f' id="{anchor}"' if anchor else ""
    return (f'<section class="block tight"{aid}><div class="wrap"><p class="eyebrow">'
            f'<span class="num">{num}</span>{e(eyebrow)}</p>{inner}</div></section>')


def table(tid: str, heads: list, rows: list, filt: str = "") -> str:
    th = "".join(f"<th>{h}</th>" for h in heads)
    f = ""
    if filt:
        f = (f'<div class="filter"><input type="search" data-filter="{tid}" placeholder="{e(filt)}" '
             f'aria-label="{e(filt)}"><span class="muted small"><span data-count="{tid}">{len(rows)}</span>'
             f" shown</span></div>")
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return (f'{f}<div class="scroll-x"><table id="{tid}" class="data sortable"><thead><tr>{th}</tr>'
            f"</thead><tbody>{body}</tbody></table></div>")


def write(out: Path, rel: str, content: str) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def inspect_url(arms: list, up: str = "", **params) -> str:
    q = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items() if v)
    return f"{up}inspect.html?runs=" + quote(",".join(arms), safe=",/") + (f"&{q}" if q else "")


def copy_assets(out: Path) -> None:
    (out / "assets").mkdir(parents=True, exist_ok=True)
    for a in ASSETS:
        shutil.copy(ASSET_DIR / a, out / "assets" / a)


def fmt(v) -> str:
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
        by_ds.setdefault(d["dataset"], {"arms": [], "refs": [], "items": 0})["arms"].append({
            "arm": arm, "label": d["label"], "runs": d.get("runs", 1), "metric": head,
            "mean": statistics.fmean(values.values()) if values else None,
            "n": len(values) or max((len(v["values"]) for v in sc.values()), default=0),
            "lower": A.lower_is_better(head) if head else False,
            "reference": d.get("reference", ""),
        })
    for r in A.references():
        by_ds.setdefault(r["dataset"], {"arms": [], "refs": [], "items": 0})["refs"].append(r)
    for ds, v in by_ds.items():
        meta = DATASETS / f"{ds}.json"
        try:
            v["items"] = len(json.loads(meta.read_text(encoding="utf-8")).get("items") or [])
        except (OSError, ValueError):
            v["items"] = max((a["n"] for a in v["arms"]), default=0)
    return by_ds


def render_home(A: Adapter, by_ds: dict, out: Path) -> None:
    rows = []
    for ds in sorted(by_ds, key=lambda d: (-len(by_ds[d]["arms"]), d)):
        v = by_ds[ds]
        rows.append([f'<a href="d/{slug(ds or "none")}.html">{e(ds or "(no dataset_id)")}</a>',
                     f'<span data-v="{v["items"]}">{v["items"]}</span>',
                     f'<span data-v="{len(v["arms"])}">{len(v["arms"])}</span>',
                     e(", ".join(r["id"] for r in v["refs"]) or "—")])
    n_arms = sum(len(v["arms"]) for v in by_ds.values())
    body = hero("catalog", "Every run, by dataset",
                f"{n_arms} arms on {len(by_ds)} datasets. An arm is one config on one dataset, its "
                f"repeats averaged per {e(A.item_word)}, exactly as <code>pair-test</code> reads it. "
                "Open a dataset to compare its arms in the inspector.")
    body += block("01", "datasets", table("datasets", ["dataset", f"{e(A.item_word)}s", "arms", "references"],
                                          rows, "filter datasets"))
    write(out, "index.html", page("Catalog", body, 0, "home", item=A.item_word))


def render_dataset(A: Adapter, ds: str, v: dict, out: Path) -> None:
    arms = sorted(v["arms"], key=lambda a: (a["metric"], (a["mean"] if a["mean"] is not None else -1e18)
                                            * (1 if a["lower"] else -1), a["label"]))
    rows = [[e(a["label"]), e(a["metric"] or "—"),
             f'<span data-v="{a["mean"] if a["mean"] is not None else ""}">{fmt(a["mean"])}'
             f'{" ↓" if a["lower"] else ""}</span>',
             f'<span data-v="{a["n"]}">{a["n"]}</span>', str(a["runs"]), e(a["reference"] or "—"),
             f'<a class="btn small" href="{inspect_url([a["arm"]], "../")}">inspect</a>'] for a in arms]
    all_arms = [a["arm"] for a in arms][:INSPECT_MAX]
    more = (f" (the first {INSPECT_MAX} of {len(arms)}; add others in the inspector)"
            if len(arms) > INSPECT_MAX else "")
    btn = (f'<p><a class="btn" href="{inspect_url(all_arms, "../")}">Inspect these arms together</a>'
           f'<span class="muted small">{more}</span></p>') if len(all_arms) > 1 else ""
    refs = "".join(f"<li><code>{e(r['id'])}</code> · {e(r['tier'])}</li>" for r in v["refs"])
    body = hero("dataset", e(ds or "(no dataset_id)"),
                f"{v['items']} {e(A.item_word)}s · {len(arms)} arms. Headline: each arm's own "
                "primary metric, mean over its items; arms with different primary metrics are "
                "not ranked against each other.", btn)
    body += block("01", "arms", table("arms", ["arm", "metric", "mean", f"{e(A.item_word)}s", "runs",
                                               "reference", ""], rows, "filter arms"))
    if refs:
        body += block("02", "references", f"<ul>{refs}</ul>")
    write(out, f"d/{slug(ds or 'none')}.html", page(ds or "dataset", body, 1, "", item=A.item_word))


def render_inspect(A: Adapter, out: Path, page_fn=page, **page_kw) -> None:
    """The inspector shell; assets/inspect.js fills it from the local server's /api/."""
    arms = {a: A.describe(a)["dataset"] for a in sorted(A.arms())}
    write(out, "runs.js", "window.RUNS=" + json.dumps(arms) + ";\n")
    item = A.item_word
    body = ('<section class="hero slim"><div class="wrap"><p class="kicker">inspector</p>'
            f"<h1>Run inspector</h1><p class=dek>Per-{e(item)} scores for the selected arms, each "
            f"tested against a baseline with the harness's paired test (exact p up to 30 {e(item)}s, "
            "Holm across the family). Click a row to see what each arm produced.</p>"
            '<div id="pick" class="pick"></div></div></section>'
            '<section class="block tight"><div class="wrap" id="app">'
            "<p class=\"muted\">Loading… (this page needs <code>evh catalog-serve</code>; opened "
            "from disk it cannot read runs.)</p></div></section>")
    write(out, "inspect.html", page_fn("Inspector", body, 0, "inspect", ("runs.js", "assets/inspect.js"),
                                       item=item, **page_kw))


def write_search(A: Adapter, by_ds: dict, out: Path) -> None:
    idx = []
    for ds, v in by_ds.items():
        idx.append({"k": "dataset", "t": ds, "d": f"{len(v['arms'])} arms", "u": f"d/{slug(ds or 'none')}.html",
                    "s": f"{ds} {' '.join(a['label'] for a in v['arms'])}".lower()})
        for a in v["arms"]:
            idx.append({"k": "arm", "t": a["label"], "d": f"{ds} · {a['metric']}",
                        "u": inspect_url([a["arm"]]), "s": f"{a['label']} {ds} {a['metric']}".lower()})
    write(out, "search.js", "window.CATALOG=" + json.dumps(idx, separators=(",", ":")) + ";\n")


def build(A: Adapter, out: Path) -> dict:
    if out.exists():
        shutil.rmtree(out)
    copy_assets(out)
    by_ds = collect(A)
    render_home(A, by_ds, out)
    for ds, v in by_ds.items():
        render_dataset(A, ds, v, out)
    write_search(A, by_ds, out)
    render_inspect(A, out)
    return {"datasets": len(by_ds), "arms": sum(len(v["arms"]) for v in by_ds.values()),
            "references": sum(len(v["refs"]) for v in by_ds.values())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / ".build" / "catalog")
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: config.yaml catalog.adapter, "
                                      "else the harness's own layout)")
    args = ap.parse_args()
    counts = build(load_adapter(args.adapter), args.out)
    print(f"catalog: {args.out} — " + ", ".join(f"{v} {k}" for k, v in counts.items()))
    print("inspect: evh catalog-serve, then open the address it prints")
    return 0


if __name__ == "__main__":
    sys.exit(main())
