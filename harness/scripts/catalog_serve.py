#!/usr/bin/env python3
"""Serve the catalog and the run inspector on this machine only (127.0.0.1).

    evh catalog-serve [--port 8765] [--adapter path/to/file.py:Class]
    make catalog-serve

Builds nothing: run `evh catalog` first. Static files are the built catalog and the data tree
(its "files" links open run folders). Two JSON endpoints feed the inspector page:

  GET /api/compare?runs=<arm|path>,...[&baseline=<arm>][&metric=<name>][&rescore=0]
      [&family=<m>][&threshold=<t>]
      every arm's per-item scores for one metric, each arm tested against the baseline with
      the paired test (stats.py: exact p up to 30 items, Holm across the family)
  GET /api/item?arms=<arm>,...&item=<item_id>[&ref=<reference_id>]
      each arm's output for one item, and the reference's

Runs on different dataset_ids are never compared: the request is refused, as `run-compare`
refuses.

LOCAL (default): binds 127.0.0.1, serves the built catalog and the data tree beside the API, and
answers only to a 127.0.0.1/localhost Host (DNS rebinding). Item text leaves this machine only
towards this machine.

PUBLIC (--public HOST[,HOST]): the API only, behind a reverse proxy that serves the static
catalog (infra/: nginx for the pages, Caddy in front). It answers only to the named Host(s);
each client (CF-Connecting-IP, else the peer) gets --rate requests a minute; at most
--max-arms arms per comparison; two comparisons compute at once and the rest wait; every
answer is cached by its exact question; errors say what was wrong with the request, never the
server's internals. --warm DIR computes, in the background, every comparison the built catalog
in DIR links to, so the pages' own links answer from the cache.
"""

from __future__ import annotations

import argparse
import errno
import json
import re
import sys
import threading
import time
from collections import Counter, OrderedDict, defaultdict
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import stats  # noqa: E402
from _common import ROOT  # noqa: E402
import _fields  # noqa: E402
from catalog_adapter import Adapter, item_fields, load_adapter  # noqa: E402

#: Every comparison ends in one of these, so a page can always say what it shows and why.
STATES = ("compared", "average only", "no shared metric", "not scorable")

A: Adapter = None  # type: ignore[assignment]  # set by main() or set_adapter()


def set_adapter(adapter: Adapter) -> None:
    global A
    A = adapter
    _scores.cache_clear()


@lru_cache(maxsize=4096)
def _scores(arm: str, rescore: bool) -> dict:
    # Re-scoring can be the slow part, and a baseline page asks for every arm on its dataset.
    # Restart the server to see new runs.
    return A.scores(arm, rescore=rescore)


def _state(rows: list, averages: dict, swapped: bool) -> str:
    if swapped:
        return "no shared metric"
    if any(r["n"] for r in rows):
        return "compared"
    return "average only" if averages else "no shared metric"


def _label(a: str) -> str:
    return A.describe(a)["label"]


def _ref_of(metric: str) -> str:
    return metric.split(" vs ", 1)[1] if " vs " in metric else ""


#: Measured off the output or the bill, not against a reference: comparable across references.
_REFERENCE_FREE = ("cost", "latency", "tokens")


def _other_reference(series: dict, baseline: str, metric: str, rescore: bool) -> list:
    """Arms whose `metric` was scored against another reference than the baseline's, which a
    paired test must not set against it: on one dataset, a silver-scored and a gold-scored run
    both record `overlap_f1`, but not of the same thing. Nothing is set aside when the scores
    were recomputed against one reference (re-scoring, or a metric named `x vs <ref>`), or when
    the metric needs no reference (length, cost, latency, tokens)."""
    if rescore or _ref_of(metric) or A.is_neutral(metric) or metric in A.shape_metrics \
            or any(k in metric for k in _REFERENCE_FREE):
        return []
    ref = {a: A.describe(a).get("reference", "") for a in series}
    want = ref.get(baseline, "")
    return [a for a in series if a != baseline and want and ref[a] and ref[a] != want]


def _one_dataset(by_run: dict, baseline: str):
    """Comparisons always use one dataset_id: pairing by item id alone would line up runs on
    different datasets that happen to share ids.

    A selected path can yield arms on several datasets; its arm on the comparison's dataset
    (the baseline's, else the first one's) is kept and the rest set aside.
    Returns (arms, {arm: dataset}, set_aside, dataset, error).
    """
    arms = [a for xs in by_run.values() for a in xs]
    ds = {a: A.describe(a)["dataset"] for a in arms}
    want = ds.get(baseline) or next((ds[a] for a in arms if ds[a]), "")
    aside = []
    for xs in by_run.values():
        on = [a for a in xs if ds[a] in (want, "")]
        if len(xs) > 1 and on and len(on) < len(xs):
            aside += [a for a in xs if a not in on]
    arms = [a for a in arms if a not in aside]
    known = sorted({ds[a] for a in arms} - {""})
    if len(known) > 1:
        by = "; ".join(f"{d}: {', '.join(_label(a) for a in arms if ds[a] == d)}" for d in known)
        return arms, ds, aside, want, f"these runs are on different datasets ({by}). Compare within one."
    return arms, ds, aside, (known[0] if known else ""), None


def _metric_rows(counts: Counter, per_arm: dict, baseline: str) -> list:
    return [
        {
            "name": k,
            "arms": n,
            "lower_is_better": A.lower_is_better(k),
            "neutral": A.is_neutral(k),
            "baseline_has": k in per_arm.get(baseline, {}),
            "format": A.reference_format(_ref_of(k)) if _ref_of(k) else "",
            "archived": bool(_ref_of(k) and A.reference_archived(_ref_of(k))),
        }
        for k, n in counts.most_common()
    ]


def _default_metric(counts: Counter, per_arm: dict, arms: list, asked: str) -> str:
    """The yardstick shown first.

    Order: never a shape metric (length, latency); scores before neutral counts and before
    cost, latency and tokens; what the
    baseline recorded; a reference in the baseline's output format; the most arms; what most
    arms recorded (per item or as an average); the adapter's preferred names.
    """
    pool = [k for k in counts if k in per_arm.get(asked, {})] or list(counts)
    preferred = tuple(getattr(A, "preferred_metrics", ()) or ())

    def own(a):
        keys = {k for k, v in per_arm.get(a, {}).items() if not v["source"].startswith("re-scored")}
        return keys | set(A.recorded_means(a))

    recorded = Counter(k for a in arms for k in own(a))
    mine = own(asked) if asked else set()
    want = A.output_format(asked)["asked"] if asked else ""

    def mismatch(k):
        f = A.reference_format(_ref_of(k)) if _ref_of(k) else ""
        return bool(want and f and f != want)

    return min(
        pool,
        key=lambda k: (
            k in A.shape_metrics,
            A.is_neutral(k),
            any(x in k for x in _REFERENCE_FREE),  # the bill and the clock: only when nothing is scored
            k not in mine,
            mismatch(k),
            -counts[k],
            -recorded[k],
            next((i for i, p in enumerate(preferred) if k.split(" vs ")[0] == p), 99),
            k,
        ),
    )


def _averages(arms: list, series: dict, metric: str):
    """Arms with only a run-level average for this metric: shown beside the comparison, never
    tested. The same value as an arm already shown is the same result filed twice: reported,
    not drawn again."""
    averages, repeats = {}, {}
    tested = {a: A.recorded_means(a).get(metric) for a in series}
    for a in arms:
        if a in series or metric not in A.recorded_means(a):
            continue
        v = A.recorded_means(a)[metric]
        same = next((t for t, tv in tested.items() if tv is not None and abs(tv - v) < 1e-12), None)
        same = same or next((t for t, tv in averages.items() if abs(tv - v) < 1e-12), None)
        if same:
            repeats[a] = same
        else:
            averages[a] = v
    return averages, repeats


def _warnings(ctx: dict) -> list:
    """Everything a reader needs to know about what the comparison could not do."""
    w, metric, series, item = [], ctx["metric"], ctx["series"], A.item_word
    if ctx["swapped"]:
        w.append(f"{_label(ctx['asked'])} has no '{metric}' scores, so "
                 f"{_label(ctx['baseline'])} is the baseline instead.")
    hashes = {a: A.input_hashes(a) for a in series}
    base_h = hashes.get(ctx["baseline"], {})
    for a, h in hashes.items():
        diff = [e for e in h if e in base_h and h[e] != base_h[e]]
        if diff:
            w.append(f"{_label(a)} recorded a different input hash than the baseline on "
                     f"{len(diff)} {item}(s): the arms may not have read the same input.")
    unknown = [_label(a) for a in ctx["arms"] if not ctx["ds"][a]]
    if unknown:
        w.append(f"No dataset_id on record for: {', '.join(unknown)}. The same-dataset rule cannot "
                 f"be checked for them; they are paired by {item} id only.")
    averages, repeats = ctx["averages"], ctx["repeats"]
    missing = [_label(a) for a in ctx["arms"] if a not in series and a not in averages and a not in repeats
               and a not in ctx.get("other_ref", ())]
    if missing:
        w.append(f"No '{metric}' on record for: {', '.join(missing)}.")
    if repeats:
        w.append(f"{len(repeats)} arm(s) recorded exactly the same '{metric}' as an arm already "
                 "shown, so they are not drawn again: "
                 + "; ".join(f"{_label(a)} = {_label(t)}" for a, t in repeats.items()) + ".")
    if ctx["aside"]:
        w.append(f"Left out, on another dataset than {ctx['dataset']}: "
                 + ", ".join(_label(a) for a in ctx["aside"]) + ".")
    if ctx.get("other_ref"):
        want = A.describe(ctx["baseline"]).get("reference", "")
        w.append(f"Not tested against the baseline: '{metric}' was scored against another reference "
                 f"than the baseline's ({want}) for "
                 + ", ".join(f"{_label(a)} ({A.describe(a).get('reference', '')})" for a in ctx["other_ref"])
                 + ". Pick a baseline scored against the same reference to compare them.")
    if averages:
        w.append(f"{len(averages)} arm(s) recorded only an average '{metric}', no per-{item} "
                 "scores: shown as averages, not tested.")
    drift = []
    for a in series:
        f = A.output_format(a)
        if f["asked"] and f["got"] and f["got"] != f["asked"]:
            drift.append(f"{_label(a)} (asked {f['asked']}, got {f['got']})")
    if drift:
        w.append("Format not followed: " + "; ".join(drift) + ". The score compares what came back.")
    w += [f"Re-scoring: {n}." for n in dict.fromkeys(n for a in ctx["arms"] for n in A.notes(a))]
    if ctx.get("wheres"):
        n = len(series.get(ctx["baseline"], {}))
        w.append(f"Filtered to the {n} {item}(s) where " + " and ".join(x.replace(":", " = ", 1) for x in ctx["wheres"])
                 + ": a subset is a smaller sample, so less can be separated.")
    if ctx.get("breakdown"):
        w.append(f"Broken down by {ctx['by']}: {ctx['breakdown']['family_size']} tests, Holm-corrected "
                 "together, so a group is held to a stricter threshold than it would be alone.")
        if ctx.get("ungrouped"):
            w.append(f"{ctx['ungrouped']} {item}(s) have no {ctx['by']} and are in no group.")
    return w


def _fields_of(dataset: str) -> tuple:
    """({name: field}, {item_id: {name: value}}) for the dataset's declared fields (ADR-0003).
    A public deployment (--public) sees only the fields marked public: what the static pages may
    show, the public API may show, and a filter on a hidden field would leak it through counts."""
    fl = item_fields(A, dataset) if dataset else {"fieldset": None, "values": {}}
    decl = {f["name"]: f for f in (fl["fieldset"] or {}).get("fields") or []}
    if LIMITS["hosts"]:
        decl = {n: f for n, f in decl.items() if f.get("public")}
    values = {i: {n: v for n, v in vs.items() if n in decl} for i, vs in fl["values"].items()}
    return decl, values


def _field_list(decl: dict) -> list:
    return [{"name": n, "label": f.get("label") or n, "type": f["type"], "values": f.get("values"),
             "unit": f.get("unit", ""), "groupable": f["type"] in _fields.GROUPABLE} for n, f in decl.items()]


def _filter(series: dict, decl: dict, values: dict, wheres: list):
    """series restricted to the items whose fields pass every `name:value` filter; or an error."""
    for w in wheres:
        name, _, want = w.partition(":")
        if name not in decl:
            return None, f"no field {name!r} to filter by" + (" here" if LIMITS["hosts"] else "")
        try:
            keep = {i for i, vs in values.items() if _fields.matches(decl[name], vs.get(name), want)}
        except ValueError as exc:
            return None, f"filter {w}: {exc}"
        series = {a: {i: x for i, x in s.items() if i in keep} for a, s in series.items()}
    return series, ""


def _groups(field: dict, name: str, values: dict, items) -> tuple:
    """({group: set of items}, items with no value): a choice field's groups in declared order,
    a boolean's as yes then no."""
    order = field.get("values") or ["true", "false"]
    groups: dict = {g: set() for g in order}
    none = 0
    for i in items:
        v = values.get(i, {}).get(name)
        if v is None:
            none += 1
            continue
        groups.setdefault(str(v).lower() if isinstance(v, bool) else str(v), set()).add(i)
    return {g: m for g, m in groups.items() if m}, none


def _number(params: dict, key: str, kind):
    try:
        return kind(params[key][0]) if params.get(key) and params[key][0] else None
    except ValueError:
        return None


def compare(params: dict) -> dict:
    runs = [r.strip("/") for r in params.get("runs", [""])[0].split(",") if r.strip()]
    if len(runs) > LIMITS["max_arms"]:
        return {"error": f"{len(runs)} arms asked for; at most {LIMITS['max_arms']} in one comparison"}
    by_run = {r: A.arms_of(r) for r in runs}
    bad = [r for r, xs in by_run.items() if not xs]
    if bad:
        return {"error": f"no arm known to the catalog: {', '.join(bad)}"}
    # Re-scoring is on unless asked off, where the adapter can do it.
    rescore = A.can_rescore and params.get("rescore", ["1"])[0] != "0"
    asked = params.get("baseline", [""])[0]
    arms, ds, aside, dataset, error = _one_dataset(by_run, asked)
    if error:
        return {"error": error}
    per_arm = {a: _scores(a, rescore) for a in arms}
    counts = Counter(k for s in per_arm.values() for k in s)
    notes = [f"Re-scoring: {n}." for n in dict.fromkeys(n for a in arms for n in A.notes(a))]
    metric = params.get("metric", [""])[0]
    if metric not in counts:
        metric = _default_metric(counts, per_arm, arms, asked) if counts else ""
    if not counts or metric in A.shape_metrics and not params.get("metric", [""])[0]:
        return {
            "state": "not scorable",
            "can_rescore": A.can_rescore,
            "arms": [A.describe(a) for a in arms],
            "metrics": _metric_rows(counts, per_arm, asked),
            "warnings": notes + [
                f"No score per {A.item_word} on record for these runs"
                + (", only output length or latency: pick one of those to compare them." if counts else ".")
                + (" Re-scoring may produce one." if A.can_rescore and not rescore else "")
            ],
        }
    series = {a: s[metric]["values"] for a, s in per_arm.items() if metric in s}
    # With no baseline named, a promoted baseline is the natural reference point.
    fallback = next((a for a in series if a.startswith("baselines/")), next(iter(series)))
    baseline = asked if asked in series else fallback
    other_ref = _other_reference(series, baseline, metric, rescore)
    for a in other_ref:
        series.pop(a)
    decl, fvalues = _fields_of(dataset)
    wheres = [w for w in params.get("where", []) if w]
    series, error = _filter(series, decl, fvalues, wheres)
    if error:
        return {"error": error}
    higher, neutral = not A.lower_is_better(metric), A.is_neutral(metric)
    result = stats.compare(series, baseline, higher_is_better=higher, neutral=neutral,
                           family=_number(params, "family", int) or None,
                           threshold=_number(params, "threshold", float))
    by, breakdown, ungrouped = params.get("by", [""])[0], None, 0
    if by:
        if by not in decl or decl[by]["type"] not in _fields.GROUPABLE:
            return {"error": f"break a comparison down by a choice or yes/no field, not {by!r}"}
        groups, ungrouped = _groups(decl[by], by, fvalues, series.get(baseline, {}))
        breakdown = stats.compare_by(series, baseline, groups, higher_is_better=higher, neutral=neutral)
    averages, repeats = _averages(arms, series, metric)
    swapped = bool(asked) and asked != baseline
    ctx = dict(metric=metric, series=series, arms=arms, ds=ds, asked=asked, baseline=baseline,
               swapped=swapped, averages=averages, repeats=repeats, aside=aside, dataset=dataset,
               other_ref=other_ref, wheres=wheres, by=by, breakdown=breakdown, ungrouped=ungrouped)
    return {
        "metric": metric,
        "higher_is_better": higher,
        "neutral": neutral,
        "baseline": baseline,
        "can_rescore": A.can_rescore,
        "metrics": _metric_rows(counts, per_arm, baseline),
        "arms": [dict(A.describe(a), source=per_arm[a].get(metric, {}).get("source", "")) for a in arms],
        "series": series,
        # every arm's shape metrics, for the scatter's x axis, whatever metric is chosen
        "shape": {k: {a: s[k]["values"] for a, s in per_arm.items() if k in s}
                  for k in A.shape_metrics if any(k in s for s in per_arm.values())},
        "items": result["items"],
        "rows": result["rows"],
        "family_size": result["family_size"],
        "dataset": dataset,
        "averages": averages,
        "repeats": repeats,
        "state": _state(result["rows"], averages, swapped),
        "warnings": _warnings(ctx),
        "fields": _field_list(decl),
        "where": wheres,
        "by": by,
        "breakdown": breakdown,
    }


def item(params: dict) -> dict:
    arms = [a for a in params.get("arms", [""])[0].split(",") if a.strip()]
    it = params.get("item", [""])[0]
    if not it or not arms or any(not A.arms_of(a) for a in arms):
        return {"error": "need arms=<arm>,... known to the catalog and item=<item_id>"}
    out = {"item": it, "views": {a: A.item_view(a, it) for a in arms}}
    decl, values = _fields_of(A.describe(A.arms_of(arms[0])[0]).get("dataset", ""))
    out["fields"] = [dict(f, value=values.get(it, {})[f["name"]]) for f in _field_list(decl)
                     if f["name"] in values.get(it, {})]
    ref = params.get("ref", [""])[0]
    if ref:
        out["reference"] = {"id": ref, "view": A.reference_view(ref, it)}
    return out


#: Set by main(): the public mode's limits. max_arms applies locally too (a URL is not a query).
LIMITS = {"max_arms": 40, "rate": 0, "hosts": ()}
_CACHE: "OrderedDict[str, tuple]" = OrderedDict()
_CACHE_MAX = 1024
_CACHE_LOCK = threading.Lock()
_COMPUTE = threading.BoundedSemaphore(2)
_HITS: "defaultdict[str, list]" = defaultdict(list)


def answer(path: str, query: str) -> tuple:
    """(status, body) for one API request; every answer cached by its exact question (the data
    under a running server does not change: restart it to see new runs)."""
    key = f"{path}?{'&'.join(sorted(query.split('&')))}"
    with _CACHE_LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    params = parse_qs(query)
    with _COMPUTE:
        try:
            body = compare(params) if path == "/api/compare" else item(params)
            code = 400 if "error" in body else 200
        except Exception as exc:  # report, don't kill the server
            body = {"error": "internal error" if LIMITS["hosts"] else f"{type(exc).__name__}: {exc}"}
            code = 500
    if code != 500:
        with _CACHE_LOCK:
            _CACHE[key] = (code, body)
            while len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
    return code, body


def over_rate(client: str) -> bool:
    """True when this client has made LIMITS["rate"] API requests in the last minute."""
    if not LIMITS["rate"]:
        return False
    now = time.monotonic()
    with _CACHE_LOCK:
        hits = [t for t in _HITS[client] if now - t < 60]
        hits.append(now)
        _HITS[client] = hits
        if len(_HITS) > 10000:  # forget idle clients
            for k in [k for k, v in _HITS.items() if now - v[-1] > 60]:
                del _HITS[k]
    return len(hits) > LIMITS["rate"]


def warm(build_dir: Path) -> int:
    """Answer, once, every comparison the built catalog links to: the pages' own links then
    come from the cache. Returns how many."""
    links = set()
    for page in sorted(build_dir.rglob("*.html")):
        for href in re.findall(r'href="(?:\.\./)*inspect\.html\?([^"]+)"', page.read_text(encoding="utf-8")):
            links.add(href.replace("&amp;", "&"))
    for q in sorted(links):
        answer("/api/compare", q)
    return len(links)


def served(build_dir: Path, data_dir: Path) -> tuple:
    """The URL prefixes readable over HTTP: the built catalog and the data tree, both under
    the project root (the server's document root)."""
    return tuple("/" + p.resolve().relative_to(ROOT.resolve()).as_posix().strip("/") + "/"
                 for p in (build_dir, data_dir))


def allowed(path: str, host: str, port: int, prefixes: tuple) -> int:
    """0 if the request may be served, else the HTTP status to refuse it with.

    Binding to 127.0.0.1 does not stop a web page from reaching the server through DNS
    rebinding, so the Host header must name this machine. Only the served trees are readable,
    and no dot-folder inside them (.git and the like) ever is.
    """
    local = (f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost")
    if host not in (LIMITS["hosts"] or local):
        return 403
    p = unquote(urlparse(path).path)
    if p.startswith("/api/"):
        return 0
    if ".." in p.split("/"):
        return 404
    prefix = next((x for x in prefixes if p.startswith(x)), None)
    if prefix is None:
        return 404
    if any(seg.startswith(".") for seg in p[len(prefix):].split("/")):
        return 404
    return 0


class Handler(SimpleHTTPRequestHandler):
    prefixes: tuple = ()

    def _refuse(self) -> bool:
        if urlparse(self.path).path in ("", "/") and self.prefixes:
            self.send_response(302)
            self.send_header("Location", self.prefixes[0])
            self.end_headers()
            return True
        code = allowed(self.path, self.headers.get("Host", ""), self.server.server_address[1], self.prefixes)
        if code:
            self.send_error(code)
            return True
        return False

    def do_HEAD(self):  # noqa: N802
        if not self._refuse():
            super().do_HEAD()

    def do_GET(self):  # noqa: N802 (http.server's naming)
        if self._refuse():
            return
        url = urlparse(self.path)
        if url.path == "/api/health":
            return self._json(200, {"ok": True})
        if url.path in ("/api/compare", "/api/item"):
            client = self.headers.get("CF-Connecting-IP") if LIMITS["hosts"] else None
            if over_rate(client or self.client_address[0]):
                return self._json(429, {"error": f"more than {LIMITS['rate']} requests a minute; wait a moment"})
            code, body = answer(url.path, url.query)
            return self._json(code, body)
        super().do_GET()

    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if code >= 400 else "public, max-age=300")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        if args and "/api/" in str(args[0]):
            super().log_message(fmt, *args)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--adapter", help="path/to/file.py:Class (default: config.yaml catalog.adapter, "
                                      "else the harness's own layout)")
    ap.add_argument("--build-dir", type=Path, default=ROOT / ".build" / "catalog")
    ap.add_argument("--public", metavar="HOST[,HOST]",
                    help="serve the API only, to these Host names, behind a reverse proxy")
    ap.add_argument("--bind", default="127.0.0.1",
                    help="address to listen on (0.0.0.0 inside a container whose port is published on loopback)")
    ap.add_argument("--rate", type=int, default=30, help="public mode: API requests per client per minute")
    ap.add_argument("--max-arms", type=int, default=40, help="most arms in one comparison")
    ap.add_argument("--warm", type=Path, metavar="CATALOG_DIR",
                    help="answer every comparison this built catalog links to, in the background")
    args = ap.parse_args()
    set_adapter(load_adapter(args.adapter))
    LIMITS["max_arms"] = args.max_arms
    if args.public:
        LIMITS["hosts"] = tuple(h.strip() for h in args.public.split(",") if h.strip())
        LIMITS["rate"] = args.rate
        Handler.prefixes = ()
    else:
        if args.bind != "127.0.0.1":
            raise SystemExit("--bind other than 127.0.0.1 needs --public (and a proxy in front)")
        if not (args.build_dir / "index.html").is_file():
            raise SystemExit(f"no catalog at {args.build_dir}: run `evh catalog` first")
        Handler.prefixes = served(args.build_dir, A.data_dir)
    if args.warm:
        threading.Thread(target=lambda: print(f"warm: {warm(args.warm)} comparison(s) cached", flush=True),
                         daemon=True).start()
    try:
        server = ThreadingHTTPServer((args.bind, args.port), partial(Handler, directory=str(ROOT)))
    except OSError as exc:
        why = (f"port {args.port} is in use. Stop what holds it, or pass --port N."
               if exc.errno == errno.EADDRINUSE else f"{exc.strerror}. Pass --port N, or check --bind.")
        raise SystemExit(f"cannot listen on {args.bind}:{args.port}: {why}")
    if args.public:
        print(f"inspector API on {args.bind}:{args.port} for {', '.join(LIMITS['hosts'])} "
              f"({LIMITS['rate']}/min per client, {LIMITS['max_arms']} arms max)", flush=True)
    else:
        print(f"catalog: http://127.0.0.1:{args.port}{Handler.prefixes[0]}   (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
