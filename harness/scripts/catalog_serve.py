#!/usr/bin/env python3
"""Serve the catalog and the run inspector: on this machine (127.0.0.1) by default, or --public behind a proxy.

    evh catalog-serve [--port N] [--adapter path/to/file.py:Class]
    make catalog-serve

Builds nothing, and needs nothing built: the catalog's pages are rendered when they are asked for (RFC-040), the same
pages `evh catalog` writes. Static files are the data tree (its "files" links open run folders) and any page a project's
own builder wrote into the catalog's folder. Three JSON endpoints feed the inspector page (and GET /api/health says the
server is up); a local server also answers the API (/api/v1/, RFC-026):

The catalog never goes stale (RFC-032 step 8, RFC-040). A page is rendered from one model of the data, kept until the
data changes: a write through the API, or a job it started that wrote, refreshes what the server has read and the next
page is rendered from the new data; any other change (the command line in another terminal, an editor, git) is noticed
on the next read and does the same. The slowest pages (home, goals) are rendered ahead in the background after a change.
A page that cannot be rendered answers 500 and says why: on GET /api/health (`catalog`: failed) and in the server's log.

  GET /api/compare?runs=<arm|path>,...[&baseline=<arm>][&metric=<name>][&rescore=0]
      [&family=<m>][&threshold=<t>]
      every arm's per-item scores for one metric, each arm tested against the baseline with
      the paired test (stats.py: exact p up to 30 items, Holm across the family)
  GET /api/item?arms=<arm>,...&item=<item_id>[&ref=<reference_id>]
      each arm's output for one item, and the reference's
  GET /api/sheet?dataset=<id>[&runs=<arm>,...][&metric=<m>][&wrong=<label set>][&new=<dataset>]
      [&where=<field>:<value>][&only=<signal>][&format=csv[&item=<id>][&fill=label][&scores_only=1]]
      (the sheet, RFC-023: the local inspector only) one dataset's items, a column per arm: outputs, scores,
      labels, the winner, the signals and a footer per arm, as JSON for the page or as the CSV the page offers to
      download. A read: the server builds the CSV in memory, writes nothing.

Runs on different dataset_ids are never compared: the request is refused, as `run-compare`
refuses.

LOCAL (default): binds 127.0.0.1, serves the built catalog and the data tree beside the API, and
answers only to a 127.0.0.1/localhost Host (DNS rebinding). Item text leaves this machine only
towards this machine.

PUBLIC (--public HOST[,HOST]): the API only, behind a reverse proxy that serves the static
catalog (infra/: nginx for the pages, Caddy in front). It answers only to the named Host(s);
each client (the peer, or the header --client-header names, which only a proxy that sets it
and an origin that only that proxy can reach make trustworthy) gets --rate requests a minute; at most
--max-arms arms per comparison; two comparisons compute at once and the rest wait; every
answer is cached by its exact question; errors say what was wrong with the request, never the
server's internals. --warm DIR computes, in the background, every comparison the built catalog
in DIR links to, so the pages' own links answer from the cache.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import argparse
import errno
import functools
import json
import re
import sys
import threading
import time
import traceback
from collections import OrderedDict, defaultdict
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent

from evaluation_harness import (  # noqa: E402
    _artifact,
    _common,
    _store,
    _visibility,
)
from evaluation_harness._common import (  # noqa: E402
    CODE,
    ROOT,
    die,
)
from evaluation_harness.catalog_adapter import Adapter, load_catalog_adapter, scores_once  # noqa: E402
from evaluation_harness.model import compare as _compare  # noqa: E402
from evaluation_harness.model import view_cache  # noqa: E402
from evaluation_harness.model.compare import (  # noqa: E402, F401 -- compare and goal_clusters_on stay importable here
    STATES,
    _arms_known,
    _conditions,
    _field_list,
    _fields_of,
    _filter,
    _known,
    _scores,
    compare,
    goal_clusters_on,
)
from evaluation_harness.ops import openapi, registry  # noqa: E402
from evaluation_harness.ops.openapi import REFUSAL_STATUS  # noqa: E402

A: Adapter = None  # type: ignore[assignment]  # set by main() or set_adapter()


def set_adapter(adapter: Adapter) -> None:
    """Set the adapter, here and in the comparison, and clear cached scores."""
    global A
    A = adapter
    _compare.set_adapter(adapter)


#: An item id: the name of a file in a run's outputs/ or a reference, never a path.
_ITEM_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@+=-]{0,199}")


def plain_item(item_id: str) -> bool:
    """True for an item id that names a file and nothing else (no "/", no "..")."""
    return bool(_ITEM_ID.fullmatch(item_id or "")) and ".." not in item_id


def item(params: dict) -> dict:
    """Fetch one item's output from multiple arms and the reference."""
    arms = [a for a in params.get("arms", [""])[0].split(",") if a.strip()]
    it = params.get("item", [""])[0]
    refs = _known()[1]
    # No arm chosen, a dataset named (the sheet, RFC-023; the local inspector only): the item, its fields, labels.
    public = _visibility.public()
    alone = params.get("dataset", [""])[0] if not arms and not public else ""
    if alone:
        from evaluation_harness._common import DATASETS  # noqa: PLC0415

        if not plain_item(alone) or not _store.is_file(DATASETS / f"{alone}.json"):
            return {"error": "need dataset=<a dataset id>"}
    if not it or (not arms and not alone) or any(not _arms_known(a) for a in arms):
        return {"error": "need arms=<arm>,... known to the catalog and item=<item_id>"}
    if not plain_item(it):  # an item is a file's name in a run, never a path: ../ would leave it
        return {"error": "not an item id: letters, digits and . _ : @ + = -"}
    # PUBLIC MODE PUBLISHES TEXT ONLY WHEN TOLD (--publish outputs,references). An arm's output
    # can quote its input (an extractive arm returns the article's own sentences) and a reference
    # can be a dataset's licensed text, so a public server serves numbers unless the deployment
    # has decided to publish them. The local inspector shows everything, on this machine.
    published = LIMITS.get("publish") or ()
    dataset = alone or A.describe(A.arms_of(arms[0])[0]).get("dataset", "")
    if not _visibility.text_shown(dataset, public=public):
        # `text: hidden` (RFC-019): nothing that comes from this dataset's text, whatever is published.
        published = ()
    if not public or "outputs" in published:
        from evaluation_harness import _exposure  # noqa: PLC0415

        _exposure.read_by_harness(
            dataset, [it], "the inspector's item view" + (" (served)" if public else "")
        )
    if public and "outputs" not in published:
        withheld = {
            "kind": "none",
            "note": "this deployment does not publish outputs (catalog-serve --publish)",
        }
        out = {"item": it, "views": {a: dict(withheld) for a in arms}}
    else:
        out = {"item": it, "views": {a: A.item_view(a, it) for a in arms}}
        if public:  # an artifact is never public: its directory quotes the items (RFC-038)
            # Nor is the judge's agreement with the gold unless the references are published too: it compares the
            # verdict, which is served, with the reference, which is not, and says which of the two it sides with.
            from evaluation_harness import judge_validation  # noqa: PLC0415

            drop = {"artifact"} | (set() if "references" in published else {judge_validation.MARK})
            out["views"] = {
                a: {
                    **{k: v for k, v in view.items() if k != "artifact"},
                    **(
                        {"info": {k: v for k, v in view["info"].items() if k not in drop}}
                        if "info" in view
                        else {}
                    ),
                }
                for a, view in out["views"].items()
            }
    decl, values = _fields_of(dataset)
    out["fields"] = [
        dict(f, value=values.get(it, {})[f["name"]])
        for f in _field_list(decl)
        if f["name"] in values.get(it, {})
        and (_visibility.text_shown(dataset, public=public) or f["type"] not in ("text", "url"))
    ]
    ref = params.get("ref", [""])[0]
    if ref and ref not in refs:
        return {"error": f"no reference known to the catalog: {ref}"}
    if ref:
        out["reference"] = {
            "id": ref,
            "view": (
                {
                    "kind": "none",
                    "note": "this deployment does not publish references (catalog-serve --publish)",
                }
                if public and "references" not in published
                else A.reference_view(ref, it)
            ),
        }
    # The item itself (the input every arm read), so an output can be checked against it. Only
    # the local inspector shows it: a public deployment never serves a dataset's inputs, which a
    # project may not be free to redistribute.
    src = getattr(A, "item_text", None)
    if callable(src) and not public:
        out["source"] = src(dataset, it)
    # Every label the item has (RFC-023), and which output is production's recorded one: the local inspector only.
    lab = getattr(A, "item_labels", None)
    if callable(lab) and not public:
        out["labels"] = lab(dataset, it)
    out["recorded"] = {a: rec for a in arms if (rec := A.describe(A.arms_of(a)[0]).get("recorded"))}
    # What the judges said of this item and why (RFC-034 §5): the local inspector only, as the reasons describe the
    # outputs they judged.
    if not public:
        out["verdicts"] = _judged(dataset, it)
    return out


def _judged(dataset: str, item_id: str) -> list[dict]:
    """Every judge scorer's primary verdicts on one item of a dataset, in the judging set's order."""
    from evaluation_harness.model import scorer_views  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    out = []
    for s in scorer_views.list_scorers(check_format=False):
        if s.get("dataset") != dataset:
            continue
        try:
            r = scorer_views.verdicts(s["scorer"], item=item_id, order="item", limit=500)
        except Problem:
            continue
        out += [dict(x, scorer=s["scorer"], scale=s.get("scale")) for x in r["rows"]]
    return out


def _sheet_rows(params: dict) -> tuple[dict, list, list]:
    """The sheet a question asks for: (the model, the rows after --where, the rows shown). A refusal raises
    SystemExit (an arm not on the dataset, no such label set, a field the dataset lacks) with its own words."""
    from evaluation_harness import _sheet  # noqa: PLC0415
    from evaluation_harness._common import DATASETS  # noqa: PLC0415

    ds = params.get("dataset", [""])[0]
    if not ds or not plain_item(ds) or not _store.is_file(DATASETS / f"{ds}.json"):
        die("need dataset=<a dataset id>", "bad-argument")
    runs = [r.strip("/") for r in params.get("runs", [""])[0].split(",") if r.strip()]
    if len(runs) > LIMITS["max_arms"]:
        die(f"{len(runs)} arms asked for; at most {LIMITS['max_arms']}", "bad-argument")
    only = params.get("only", [])
    if bad := [x for x in only if x not in _sheet.SIGNALS]:
        die(f"no signal {bad[0]!r}: one of {', '.join(_sheet.SIGNALS)}", "not-found")
    items = [i for i in params.get("item", []) if plain_item(i)] if "item" in params else None
    model = _sheet.build(
        ds,
        runs,
        _fields_of,
        metric=params.get("metric", [""])[0] or None,
        wrong_against=params.get("wrong", [""])[0] or None,
        new_vs=params.get("new", [""])[0] or None,
        items=items,
    )
    found = _sheet.by_where(model, params.get("where", []))
    return model, found, _sheet.by_signals(found, only)


def _error(exc: SystemExit) -> dict:
    return {"error": re.sub(r"^ERROR( \([a-z-]+\))?: ", "", str(exc)).splitlines()[0]}


def sheet_csv(query: str) -> tuple[int, bytes, str]:
    """The sheet as a download (RFC-023): the CSV `evh sheet-export --csv` writes, built in memory by the same
    code, so the page still writes nothing. The local inspector only: a sheet carries item text and outputs."""
    if _visibility.public():
        return 403, b"the sheet shows item text and outputs: not served publicly", "text/plain; charset=utf-8"
    from evaluation_harness import _sheet  # noqa: PLC0415
    from evaluation_harness._sheets import write_csv  # noqa: PLC0415

    params = parse_qs(query)
    fill = params.get("fill", [""])[0] or None
    if fill not in (None, "label"):
        return (
            400,
            b"fill=label (a blind fill needs its key written beside the sheet: evh sheet-export --csv)",
            "text/plain; charset=utf-8",
        )
    choices = [c.strip() for c in params.get("choices", [""])[0].split(",") if c.strip()] or None
    try:
        model, _, shown = _sheet_rows(params)
    except SystemExit as exc:
        return 400, _error(exc)["error"].encode(), "text/plain; charset=utf-8"
    head, body = _sheet.csv_sheet(
        model, shown, scores_only=bool(params.get("scores_only", [""])[0]), fill=fill, choices=choices
    )
    return 200, write_csv(head, body).encode("utf-8"), "text/csv; charset=utf-8"


def sheet(params: dict) -> dict:
    """The sheet (RFC-023, UXS-002 05): one dataset's items down, a column per arm across (the first stands for
    production): outputs and scores, a column per label set, the winners, the signals, the footer per arm;
    `evh sheet-show D` in the browser. The local inspector only: it carries outputs and labels."""
    if _visibility.public():
        return {"error": "the sheet shows outputs and labels: not served publicly"}
    from evaluation_harness import _picks, _sheet  # noqa: PLC0415
    from evaluation_harness._common import DATASETS  # noqa: PLC0415

    try:
        model, found, shown = _sheet_rows(params)
    except SystemExit as exc:  # a refusal: its own words
        return _error(exc)
    ds = model["dataset_id"]
    state = _picks.state()

    def short(t):
        one = " ".join((t or "").split())
        return one if len(one) <= 160 else one[:159] + "…"

    tokens = [a["token"] for a in model["arms"]]
    from evaluation_harness import _exposure  # noqa: PLC0415

    _exposure.read_by_harness(ds, [r["item"] for r in shown], "the inspector's sheet")
    out_rows = []
    for r in shown:
        p = state.get((ds, r["item"])) or {}
        out_rows.append(
            {
                "item": r["item"],
                "text": short(r["text"]),
                "fields": r["fields"],
                "cells": {
                    t: {
                        "output": None if r["shown"].get(t) is None else short(r["shown"][t]),
                        # the whole output behind a decision (its reason), the cell's tooltip
                        "full": (
                            r["decisions"][t][:600]
                            if r["shown"].get(t) is not None and r["decisions"].get(t) != r["shown"][t]
                            else None
                        ),
                        "scores": r["scores"][t],
                    }
                    for t in tokens
                },
                "labels": {k: short(v) for k, v in r["label_text"].items()},
                "references": {k: short(v) for k, v in r["references"].items()},
                "winners": r["winners"],
                "picked": (p.get("for") or ["no target yet"]) if p.get("action") == "pick" else [],
                "signals": r["signals"],
                "tags": r.get("tags", {}),
            }
        )
    return {
        "dataset": ds,
        "runs": tokens,
        "arms": [
            {"token": a["token"], "system_id": a["system_id"], "scores": a["scores"]} for a in model["arms"]
        ],
        "metric": model["metric"],
        "lower_is_better": model["lower"],
        "goal": model["goal"],
        "metrics": model["metrics"],
        "label_cols": model["label_cols"],
        "ref_cols": model["ref_cols"],
        "winner_cols": [{"key": w["key"], "header": w["header"]} for w in model["winner_cols"]],
        "rows": out_rows,
        "footer": _sheet.footer(model, shown),
        "total": len(found),
        "counts": _sheet.counts(found),
        "sets": [c["key"] for c in model["label_cols"]],
        "datasets": sorted(p.stem for p in _store.glob(DATASETS, "*.json") if p.stem != ds),
        "fields": _field_list(model["decl"]),
        "wrong": params.get("wrong", [""])[0],
        "new": params.get("new", [""])[0],
    }


#: The public mode's limits, set by main(): the comparison's own (model/compare).
LIMITS = _compare.LIMITS
#: Each answer kept as the bytes it is sent as, bounded by their total: a 40-arm comparison is
#: ~1.8 MB, so a count bound (1024) let a hundred distinct questions take a 256 MiB container
#: past its limit (an independent review, 2026-10-29). Least recently used out first.
_CACHE: OrderedDict[str, tuple] = OrderedDict()
_CACHE_MAX = 1024
_CACHE_BYTES = 32 * 1024 * 1024
#: The longest question answered: 40 arms by their ids fit in well under 4 KB.
MAX_QUERY = 4096
_cache_size = [0]
_CACHE_LOCK = threading.Lock()
_COMPUTE = threading.BoundedSemaphore(2)
_HITS: defaultdict[str, list] = defaultdict(list)


def cache_clear() -> None:
    """Forget every answer, and the scores and arms they were made from: when the data changed (`refresh`), after a
    rebuild (the arms are the catalog's) and after a migration, so an answer never outlives what it was made from."""
    with _CACHE_LOCK:
        _CACHE.clear()
        _cache_size[0] = 0
    _scores.cache_clear()
    _known.cache_clear()
    view_cache.clear()


def answer(path: str, query: str) -> tuple:
    """(status, the JSON body as bytes) for one API request; every answer cached by its exact
    question until the data changes or the catalog is rebuilt (`cache_clear`)."""
    if len(query) > MAX_QUERY:
        return 400, json.dumps({"error": f"the question is over {MAX_QUERY} characters"}).encode()
    key = f"{path}?{'&'.join(sorted(query.split('&')))}"
    if (kept := _kept(key)) is not None:
        return kept
    params = parse_qs(query)
    with _COMPUTE:
        try:
            body = (
                compare(params)
                if path == "/api/compare"
                else sheet(params)
                if path == "/api/sheet"
                else item(params)
            )
            code = 400 if "error" in body else 200
        except Exception as exc:  # noqa: BLE001 — report, don't kill the server
            body = {"error": "internal error" if LIMITS["hosts"] else f"{type(exc).__name__}: {exc}"}
            code = 500
    data = json.dumps(body).encode()
    _keep(key, code, data)
    return code, data


def _kept(key: str) -> tuple | None:
    """The answer kept for this question, (status, bytes), or None."""
    with _CACHE_LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    return None


def _keep(key: str, code: int, data: bytes) -> None:
    """Keep an answer, within the cache's bounds. Only answers are kept: a refusal (4xx) costs nothing to repeat, and
    keeping it let distinct junk questions fill the cache by their keys (an independent review, 2026-10-29)."""
    if code == 200 and len(data) <= _CACHE_BYTES // 4:
        with _CACHE_LOCK:
            if key not in _CACHE:
                _CACHE[key] = (code, data)
                _cache_size[0] += len(data)
            while _CACHE and (len(_CACHE) > _CACHE_MAX or _cache_size[0] > _CACHE_BYTES):
                _cache_size[0] -= len(_CACHE.popitem(last=False)[1][1])


def client_key(header: str | None, peer: str) -> str:
    """Whom the rate counts: the named header when it holds an address (an IPv6 one by its /64),
    else the connection's own. A header that is not an address (60 KB of text, a value rotated per
    request) never becomes a key: keys are short and few."""
    import ipaddress  # noqa: PLC0415

    for v in (header, peer):
        try:
            ip = ipaddress.ip_address((v or "").strip()[:64])
        except ValueError:
            continue
        return str(ipaddress.ip_network(f"{ip}/64", strict=False)) if ip.version == 6 else str(ip)
    return peer[:64]


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
    for page in sorted(_store.rglob(build_dir, "*.html")):
        for href in re.findall(
            r'href="(?:\.\./)*inspect\.html\?([^"]+)"', _store.read_text(page, encoding="utf-8")
        ):
            links.add(href.replace("&amp;", "&"))
    done = 0
    for q in sorted(links):
        # Warm only what the cache keeps: past its bound each answer would evict an earlier one,
        # and the work and the memory it peaks at would be for nothing.
        if _cache_size[0] > _CACHE_BYTES * 3 // 4:
            break
        answer("/api/compare", q)
        done += 1
    return done


def served(build_dir: Path, data_dir: Path, also: tuple = ()) -> tuple:
    """The URL prefixes readable over HTTP: the built catalog, the data tree, any directory
    the adapter names in `served_dirs` (a project whose pages link its reports) and `artifacts/`
    (where an adapter writes what an item leaves for a person to open, RFC-038: served whether or not it exists yet),
    all under the project root (the server's document root)."""
    out = []
    for p in (build_dir, data_dir, *also, ROOT / _artifact.DIR):
        try:
            prefix = "/" + p.resolve().relative_to(ROOT.resolve()).as_posix().strip("/") + "/"
            if prefix not in out:
                out.append(prefix)
        except ValueError:
            # The server's document root is the project: it serves the catalog and the data
            # tree from inside it, and nothing outside, so a directory elsewhere has no URL.
            die(
                f"{p} is not inside the project ({ROOT}): the inspector serves the catalog "
                "and the data tree from inside the project only. Build the catalog there "
                "(the default, .build/catalog), or run from the project that holds it.",
                "not-allowed",
            )
    return tuple(out)


def query_inputs(schema: dict, query: dict) -> dict:
    """A read operation's inputs from the query string, each as its schema types it (a query holds only strings): an
    integer, a number, a boolean (true or false, 1 or 0), a string as it is, an array as the key repeated
    (`?x=a&x=b`; a comma is part of a value, never a separator), its items typed by `items`. ValueError names the
    input that is not what the schema says."""

    def one(name: str, value: str, kind: str | None):
        try:
            if kind == "integer":
                return int(value)
            if kind == "number":
                return float(value)
        except ValueError:
            raise ValueError(
                f"{name}: {value!r} is not {'an integer' if kind == 'integer' else 'a number'}"
            ) from None
        if kind == "boolean":
            if value.lower() not in ("true", "false", "1", "0"):
                raise ValueError(f"{name}: {value!r} is not true or false")
            return value.lower() in ("true", "1")
        return value

    out: dict = {}
    for name, values in query.items():
        spec = schema.get(name)
        if spec is None:
            continue
        kind = spec.get("type")
        out[name] = (
            [one(name, v, (spec.get("items") or {}).get("type")) for v in values]
            if kind == "array"
            else one(name, values[0], kind)
        )
    return out


#: The API's endpoints. Anything else under /api/ is 404: it is not a way into the files.
API_ROUTES = ("/api/health", "/api/compare", "/api/item", "/api/sheet")
#: The header every API call that is not a read must carry: a page from another origin cannot send it without a CORS
#: preflight, which this server never grants (ADR-0027).
DATA_HEADER = "X-EVH-Data"
#: The API's token (RFC-026), made when a local server starts; empty: the API answers nothing.
API_TOKEN: list[str] = []
API_COOKIE = "evh_token"
API_MAX_BODY = 64 * 1024
#: The Workbench's files (PRD-017): beside the package's code when installed, harness/workbench in a checkout.
WORKBENCH = next(
    (p for p in (CODE / "workbench", CODE.parent / "workbench") if _store.is_dir(p)),
    CODE.parent / "workbench",
)
#: The live Workbench's files: what /workbench/ serves, from the package or a checkout (whose mockup.html and its data,
#: mock.js, a frozen design reference, are never served; D7).
WORKBENCH_FILES = frozenset({"index.html", "workbench.css", "workbench.js", "help.js", "live.js"})
WORKBENCH_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}
#: The catalog's rendered pages and its assets are the same four kinds (RFC-040).
SITE_TYPES = WORKBENCH_TYPES
#: What a public server (a viewer's, RFC-039) says to a call that writes, spends or runs.
VIEWER_REFUSES = (
    "this is a read-only view of a published project: nothing here writes, spends or runs a model"
)
API_MAX_JOB_BODY = 70 * 1024 * 1024  # 50 MB of files, base64 (RFC-026: owner, 2026-11-08)


def api_estimate(body: dict) -> tuple[int, dict]:
    """POST /api/v1/estimate, `{operation, inputs}`: a job operation's own dry run, run now as a read (it calls nothing
    and writes nothing). Its inputs are checked as a job's are, the operation run as a short child that reads them from
    a file, and what it printed and answered: what the job would do and, for one that spends, its cost (RFC-026 step 5)."""
    import json as _json  # noqa: PLC0415

    from evaluation_harness import _api, _cmdline, _jobs  # noqa: PLC0415
    from evaluation_harness._version import __version__  # noqa: PLC0415

    extra = sorted(set(body) - {"operation", "inputs"})
    try:
        if extra:
            raise _api.Refused(f"an estimate is {{operation, inputs}}, not {', '.join(extra)}")
        op = _api.job_operation(str(body.get("operation") or ""))
        if "dry_run" not in op.inputs:
            raise _api.Refused(
                f"{op.name} has no dry run: there is nothing to estimate (a spending job shows its cap)", 404
            )
        checked = _api.operation_inputs(op, {**(body.get("inputs") or {}), "dry_run": True}, _jobs.new_id())
    except _api.Refused as exc:
        return exc.status, {"error": str(exc)}
    code, out, err = _cmdline.run_operation(ROOT, op.name, checked)
    try:
        result = _json.loads(out).get("result") if out.strip() else None
    except ValueError:
        result = None
    return (200 if code == 0 else 400), {
        "operation": op.name,
        "version": __version__,
        "exit": code,
        "text": err,
        "result": result,
    }


def allowed(path: str, host: str, port: int, prefixes: tuple) -> int:
    """0 if the request may be served, else the HTTP status to refuse it with.

    Binding to 127.0.0.1 does not stop a web page from reaching the server through DNS
    rebinding, so the Host header must name this machine. Only the API's endpoints and the
    served trees are readable, and no dot-folder inside them (.git and the like) ever is.
    `..` is refused first, for every path: /api/../.env once skipped the checks and was served
    from the project root, keys included.
    """
    local = (f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost")
    if host not in (LIMITS["hosts"] or (*local, *LIMITS.get("proxy_hosts", ()))):
        return 403
    p = unquote(urlparse(path).path)
    if ".." in p.split("/"):
        return 404
    if p.startswith("/api/v1/"):
        # RFC-026: this machine's, with its token; never behind a proxy. A public server serves its reads to a viewer,
        # with no token (RFC-039, owner, 2026-11-23): `_viewer` refuses the rest.
        return 0 if LIMITS["hosts"] else 404 if LIMITS.get("proxy_hosts") or not API_TOKEN else 0
    if p.startswith("/api/"):
        return 0 if p in API_ROUTES else 404
    if p == "/workbench" or p.startswith("/workbench/"):  # as the API's
        return 0 if LIMITS["hosts"] else 404 if LIMITS.get("proxy_hosts") or not API_TOKEN else 0
    prefix = next((x for x in prefixes if p.startswith(x)), None)
    if prefix is None:
        return 404
    if any(seg.startswith(".") for seg in p[len(prefix) :].split("/")):
        return 404
    # The file server follows a symlink, and an agent's trial directory may hold one to /etc: a path that lands outside
    # its prefix's own directory, once the links are followed, is not served (RFC-038).
    base = (ROOT / prefix.strip("/")).resolve()
    if not (ROOT / p.lstrip("/")).resolve().is_relative_to(base):
        return 404
    return 0


#: Whether a migration holds the whole project (RFC-026 step 4): every call is answered 503 until it ends.
MIGRATING: list[bool] = [False]
MIGRATION_POLL_S = 0.5
_MIGRATION_SEEN: list = []  # the migration mark last acted on (unset until the first look)
_MIGRATION_LOCK = threading.Lock()


def migration_check() -> bool:
    """Whether a migration holds the project now. A migration that began (or ended) since the last look closes this
    server's hold on the store and makes it read the store again: `data-migrate` finds the database free, and an answer
    after the move reads the new store. Asked before every call and every half second (watch_migrations)."""
    from evaluation_harness import _jobs, _outputs  # noqa: PLC0415

    with _MIGRATION_LOCK:
        now, mark = _jobs.migrating(), _jobs.migration_mark()
        if not _MIGRATION_SEEN:
            _MIGRATION_SEEN.append(mark)
        # A short move can begin and end between two looks: the mark says one did.
        if now != MIGRATING[0] or mark != _MIGRATION_SEEN[0]:
            MIGRATING[0], _MIGRATION_SEEN[0] = now, mark
            _outputs.reset()
            cache_clear()
        return now


def watch_migrations() -> None:
    """migration_check every half second, so a server nobody asks anything still lets go of the database."""
    while True:
        migration_check()
        time.sleep(MIGRATION_POLL_S)


# ── the catalog never goes stale ────────────────────────────────────────────────────────────────────────────────────

#: Least seconds between two looks at the data's state: a page and the assets a browser asks for with it are one look.
FRESH_EVERY_S = 0.25
#: How often a job (a rebuild, or one of the server's writes) is looked at while it runs.
FRESH_POLL_S = 0.2
_ENDED = ("succeeded", "failed", "cancelled", "lost")
#: What the server knows of the data under its pages. `on` only for a server that has pages of its own (not --public:
#: its pages and data are a deployment's copy, which the deploy rebuilds); `seen` is the data's state last looked at.
FRESH: dict[str, Any] = {"on": False, "seen": None, "looked": 0.0}
_FRESH_LOCK = threading.Lock()
#: The catalog's pages, rendered when asked for from one model of the data (RFC-040, catalog_build.Site). `gen` counts
#: the changes the server has seen; `site` is the newest model and `site_gen` the change it was prepared after, so a
#: request is answered by a model prepared from the data as it was when the request came, or later: a write is on the
#: next page, and the requests that wait for one model get that one, not one each. `day`: the day it was prepared (a
#: model's "stale" mark is against today); `prepared` how many were; `failed` the last failure, until a page renders.
SITE: dict[str, Any] = {"site": None, "site_gen": -1, "gen": 0, "day": "", "prepared": 0, "failed": None}
_SITE_LOCK = threading.Lock()  # SITE's fields
_PREPARE_LOCK = threading.Lock()  # one model prepared at a time
_WARM = threading.Event()
#: After a change, the pages are rendered ahead once the data has been still this long: a run in another terminal
#: writes for minutes, and rendering ahead for each of its writes renders pages nobody reads.
WARM_QUIET_S = 1.0
#: The requests waiting for a page: rendering ahead starts no page while one waits. The renders' lock is not fair, and
#: under load the thread rendering ahead took it again before the request (7 goal pages ahead of it, in the test).
_ASKING = {"n": 0}
_ASKING_CV = threading.Condition()


def data_state(first: bool = False) -> tuple[tuple, int]:
    """(a fingerprint of the data the catalog reads, when it last changed in ns; the latter only when `first`): the
    adapter's data directory and, when they are elsewhere, its goals (`_store.fingerprint`: ~25 ms for this repository's
    14,500 entries in the files store, 0.02 ms in the sqlite store)."""
    root = Path(A.data_dir)
    roots = [root]
    goals = getattr(A, "goals_dir", None)
    if goals and not Path(goals).resolve().is_relative_to(root.resolve()):
        roots.append(Path(goals))
    got = [_store.fingerprint(r, newest=first) for r in roots]
    return tuple(g[:2] for g in got), max(g[2] for g in got)


def say(line: str, err: bool = False) -> None:
    """A line of the server's log."""
    print(line, file=sys.stderr if err else sys.stdout, flush=True)


def refresh() -> None:
    """The server forgets what it read of the data: the adapter's own caches (its index of runs, its listings), the
    comparisons and every answer made from them. The p's of the tests are kept by what they were computed from (the
    paired differences), so none can be out of date; the files' and the database's readers check their own stamps."""
    fn = getattr(A, "refresh", None)
    if callable(fn):
        fn()
    cache_clear()


def catalog_status() -> dict:
    """What GET /api/health says of the pages: rendered on request; `state` failed (the last model or page could not be
    made, `failed` says why) or idle; when the model the pages are rendered from was made, and how many have been."""
    with _SITE_LOCK:
        site = SITE["site"]
        return {
            "mode": "on request",
            "state": "failed" if SITE["failed"] else "idle",
            "built_at": site.built if site is not None else None,
            "prepared": SITE["prepared"],
            "failed": SITE["failed"],
        }


def _wait_job(job_id: str) -> dict:
    """The job as it was when it ended (a job nobody can read any more is `lost`)."""
    from evaluation_harness import _jobs  # noqa: PLC0415

    while True:
        try:
            j = _jobs.read(job_id)
        except (FileNotFoundError, ValueError, OSError):
            return {"id": job_id, "state": "lost"}
        if j["state"] in _ENDED:
            return j
        time.sleep(FRESH_POLL_S)


def current_site():
    """A model of the data at least as new as it was when this was called: the one kept, the one another request was
    preparing meanwhile, or one prepared now (one at a time). Raises what preparing it raised."""
    from evaluation_harness import catalog_build  # noqa: PLC0415

    day = _common.today().isoformat()

    def kept(asked: int):
        s = SITE["site"]
        return s if s is not None and SITE["site_gen"] >= asked and SITE["day"] == day else None

    with _SITE_LOCK:
        asked = SITE["gen"]
        if (got := kept(asked)) is not None:
            return got
    with _PREPARE_LOCK:
        with _SITE_LOCK:
            if (got := kept(asked)) is not None:
                return got
            gen = SITE["gen"]
        site = catalog_build.prepare(A, once=False)  # the server's adapter holds its scores itself
        with _SITE_LOCK:
            SITE["prepared"] += 1
            if gen >= SITE["site_gen"]:
                SITE.update(site=site, site_gen=gen, day=day)
        return site


def site_page(rel: str) -> tuple[Any, str | None]:
    """(the model, the catalog's page at `rel` rendered from it, None for none). A failure is said, in the log and on
    health, and raised."""
    with _ASKING_CV:
        _ASKING["n"] += 1
    try:
        site = current_site()
        got = site.page(rel)
    except Exception as exc:
        why = f"{type(exc).__name__}: {exc}"
        with _SITE_LOCK:
            SITE["failed"] = {"at": _common.now(), "why": why}
        say(f"catalog: {rel} could not be rendered: {why}", err=True)
        raise
    finally:
        with _ASKING_CV:
            _ASKING["n"] -= 1
            _ASKING_CV.notify_all()
    if got is not None:
        with _SITE_LOCK:
            SITE["failed"] = None
    return site, got


def renew(why: str) -> None:
    """The data changed: the next page is rendered from it, and the slowest pages again in the background."""
    with _SITE_LOCK:
        SITE["gen"] += 1
    say(f"catalog: {why}: the pages are rendered from the data as it is now")
    _WARM.set()


def _pages_warmer() -> None:
    """Prepare the model and render the pages that take longest (the home page, the goals and each goal's page, 0.3-2 s
    each) once the data is still, so the first person to open one does not wait; a request that comes first renders it
    itself. A change while it runs starts it again. It starts no page while a request waits for one."""
    from evaluation_harness import catalog_build  # noqa: PLC0415

    def render_ahead(site, path: str) -> None:
        while True:
            with _ASKING_CV:
                _ASKING_CV.wait_for(lambda: _ASKING["n"] == 0)
            with catalog_build._RENDER_LOCK:
                if _ASKING["n"] == 0:  # looked at under the lock: a request that came meanwhile goes first
                    site.page(path)
                    return

    while True:
        _WARM.wait()
        while True:
            _WARM.clear()
            if not _WARM.wait(WARM_QUIET_S):
                break
        try:
            site = current_site()
            for path in ("index.html", "goals.html", *(catalog_build.goal_page(g) for g in site.goals)):
                if _WARM.is_set():
                    break
                render_ahead(site, path)
        except Exception as exc:  # noqa: BLE001 -- said; a request renders what it asks for and says the same
            say(f"catalog: the pages could not be rendered ahead: {type(exc).__name__}: {exc}", err=True)


def fresh_check(force: bool = False, why: str = "") -> bool:
    """Look at the data's state and, when it is not the one last seen, refresh what the server read and render the pages
    from it. Called before every request, at most every FRESH_EVERY_S; `force`: now, whatever the last look. True when
    the data had changed."""
    if not FRESH["on"] or not _FRESH_LOCK.acquire(blocking=force):
        return False
    try:
        now = time.monotonic()
        if not force and now - FRESH["looked"] < FRESH_EVERY_S:
            return False
        FRESH["looked"] = now
        state, _newest = data_state()
        if state == FRESH["seen"]:
            return False
        FRESH["seen"] = state
        refresh()
        renew(why or "the data changed")
        return True
    finally:
        _FRESH_LOCK.release()


def data_changed(why: str) -> None:
    """A write this server made (an edit of the model through the API): its answer is read from fresh data at once, and
    so is the next page."""
    if not FRESH["on"]:
        return
    with _FRESH_LOCK:
        FRESH["seen"] = data_state()[0]  # after the write: a later change differs from it
        refresh()
        renew(why)


def watch_write_job(job: dict) -> None:
    """A job this server started: when it ends, look at the data at once (the looks before requests see its writes as
    they come; this one does not wait for the next request)."""

    name = job["operation"]
    if not FRESH["on"]:
        return

    def end() -> None:
        _wait_job(job["id"])
        try:
            fresh_check(force=True, why=f"job {job['id']} ({name}) ended")
        except Exception as exc:  # noqa: BLE001 -- the look failed; the next read looks again
            say(
                f"catalog: could not look at the data after job {job['id']}: {type(exc).__name__}: {exc}",
                err=True,
            )

    threading.Thread(target=end, daemon=True).start()


def _look() -> None:
    """The look before a request: never fails it."""
    try:
        fresh_check()
    except Exception as exc:  # noqa: BLE001
        say(f"catalog: could not look at the data: {type(exc).__name__}: {exc}", err=True)


def start_fresh() -> None:
    """Begin keeping the pages current (a server with pages of its own, RFC-040): they are rendered when asked for from
    the data as it is, so nothing waits for a build, not even the first. The slowest are rendered ahead."""
    FRESH.update(on=True, looked=time.monotonic())
    FRESH["seen"] = data_state(first=True)[0]
    threading.Thread(target=_pages_warmer, daemon=True).start()
    _WARM.set()


#: A deployment's hooks (--hooks), or None. The harness calls them and knows nothing of what they
#: do: error reporting, tracing and metrics belong to the deployment, not to the harness.
HOOKS = None


def load_hooks(spec: str):
    """The hooks --hooks names: `path/to/file.py`, `path/to/file.py:NAME`, `module` or
    `module:NAME`. Without NAME the module itself is the hooks. Each part is optional:

        start(info)          once, before serving: {"bind", "port", "public", "version"}
        request(info)        after each request: {"method", "path", "route", "status", "ms"}
        error(exc, info)     a request raised: it is then answered 500 (info as for request)
        routes               {path: fn(query) -> (status, content_type, body bytes)}, extra GET
                             paths answered before the host check: serve on them only what
                             anyone who can reach the port may read (a deployment's /metrics)

    A hook that raises is reported on stderr and never breaks the request."""
    import importlib  # noqa: PLC0415

    target, _, name = spec.partition(":")
    if target.endswith(".py"):
        path = Path(target).resolve()
        if not _store.is_file(path):
            die(f"--hooks: no file {target}", "not-found")
        from evaluation_harness._common import ModuleNotLoadable, load_module  # noqa: PLC0415

        try:
            mod = load_module(path, f"evh_hooks_{path.stem}")
        except ModuleNotLoadable:
            die(f"--hooks: cannot load {target}", "failed")
    else:
        try:
            mod = importlib.import_module(target)
        except ImportError as exc:
            die(f"--hooks: cannot import {target}: {exc}", "failed")
    obj = getattr(mod, name) if name else mod
    return obj() if isinstance(obj, type) else obj


def _hook(name: str, *args) -> None:
    fn = getattr(HOOKS, name, None) if HOOKS is not None else None
    if callable(fn):
        try:
            fn(*args)
        except Exception as exc:  # noqa: BLE001 -- a hook never breaks the request it observes
            print(f"hooks.{name} failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)


def _hook_routes() -> dict:
    r = getattr(HOOKS, "routes", None) if HOOKS is not None else None
    r = r() if callable(r) else r
    return r if isinstance(r, dict) else {}


#: The /api/v1 routes that are no operation's: the jobs', the estimate, the description and the session.
V1_FIXED = (
    "/jobs", "/jobs/{id}", "/jobs/{id}/log", "/jobs/{id}/files/{name}", "/jobs/{id}/stop", "/jobs/{id}/resume",
    "/estimate", "/openapi.json", "/session",
)  # fmt: skip


@functools.cache
def _v1_templates() -> tuple[tuple[str, ...], ...]:
    """Every /api/v1 route as its segments, the most literal first (a path two templates fit is the literal one's)."""
    from evaluation_harness import ops  # noqa: PLC0415

    found = {op.route for op in ops.OPS.values()} | set(V1_FIXED)
    split = [tuple(r.strip("/").split("/")) for r in found]
    return tuple(sorted(split, key=lambda t: (-sum(not x.startswith("{") for x in t), t)))


def _v1_route(path: str) -> str:
    """An /api/v1 path as its route's template (`/api/v1/goals/{goal}/rounds/{round}`), never its ids: a route is a
    metric series and a trace's name, and the ids are many. One no route fits is `/api/v1/other`."""
    parts = tuple(path[len("/api/v1") :].strip("/").split("/"))
    for t in _v1_templates():
        if len(t) == len(parts) and all(w.startswith("{") or w == p for w, p in zip(t, parts, strict=True)):
            return "/api/v1/" + "/".join(t)
    return "/api/v1/other"


def _route(path: str) -> str:
    """A request's route for the hooks: the API endpoint, an /api/v1 path's route template, a hook's own path,
    "/api/other" for any other /api/ path (one name, however many paths are asked: a route is a metric series), or
    "static"."""
    if path in API_ROUTES or path in _hook_routes():
        return path
    if path == "/api/v1" or path.startswith("/api/v1/"):
        return _v1_route(path)
    return "/api/other" if path.startswith("/api/") else "static"


def _data_url_prefix() -> str | None:
    """The URL path the project's data tree is served under (/data/), None when it is outside the project."""
    try:
        return "/" + _common.DATA.resolve().relative_to(ROOT.resolve()).as_posix().strip("/") + "/"
    except ValueError:  # a data directory outside the project has no URL (served() says so at start)
        return None


class Handler(SimpleHTTPRequestHandler):
    """HTTP request handler for catalog serving and API endpoints."""

    prefixes: tuple = ()

    def send_response(self, code, message=None):
        """Send the status line, remembering the status for the hooks."""
        self._status = code
        super().send_response(code, message)

    def _observed(self, serve) -> None:
        """Serve the request, then tell the hooks how it went; on an unhandled error answer a JSON 500 (`{error}`) when
        nothing was sent yet, and tell the hooks, or print the traceback on the server's stderr without them: a page
        always reads an answer (before 0.8.0, without --hooks the error propagated and the browser got a broken
        response)."""
        t0, self._status = time.monotonic(), 0
        path = urlparse(self.path).path
        try:
            if migration_check():
                self.send_response(503)
                self.send_header("Retry-After", "5")
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                body = json.dumps({"error": "a migration holds the project; try again when it ends"}).encode()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            _look()
            serve()
        except Exception as exc:  # noqa: BLE001 — the request's last resort: printed or told to the hooks, answered 500
            if HOOKS is None:
                traceback.print_exc(file=sys.stderr)
            else:
                _hook(
                    "error",
                    exc,
                    {"method": self.command, "path": path, "route": _route(path), "status": 500, "ms": 0.0},
                )
            if not self._status:
                try:
                    self._json(500, {"error": "the server failed on this request"})
                except OSError:
                    pass
        finally:
            if HOOKS is not None:
                _hook(
                    "request",
                    {
                        "method": self.command,
                        "path": path,
                        "route": _route(path),
                        "status": self._status or 500,
                        "ms": round((time.monotonic() - t0) * 1000, 2),
                    },
                )

    def _refuse(self) -> bool:
        # The server's root, and the catalog's address without its slash, open the catalog.
        if self.prefixes and urlparse(self.path).path in ("", "/", self.prefixes[0].rstrip("/")):
            self.send_response(302)
            self.send_header("Location", self.prefixes[0])
            self.end_headers()
            return True
        port = int(self.server.server_address[1])  # type: ignore[index]  # an AF_INET (host, port)
        code = allowed(self.path, self.headers.get("Host", ""), port, self.prefixes)
        if code:
            self.send_error(code)
            return True
        return False

    def do_POST(self):
        """The API's calls (RFC-026), observed by the hooks; nothing else is written to."""
        if urlparse(self.path).path.startswith("/api/v1/"):
            self._observed(lambda: self._api("POST"))
            return
        self._observed(self._no_write)

    def _api_authorized(self) -> bool:
        """The token, from `Authorization: Bearer` or the cookie the session route sets (RFC-026)."""
        import hmac  # noqa: PLC0415

        auth = self.headers.get("Authorization") or ""
        given = auth[len("Bearer ") :].strip() if auth.startswith("Bearer ") else None
        if given is None:
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == API_COOKIE:
                    given = v
        return bool(given and API_TOKEN and hmac.compare_digest(given, API_TOKEN[0]))

    def _api(self, method: str) -> None:
        """/api/v1/: the token on every call, this machine's Host (`_refuse`), no foreign Origin, and the data header on
        every call that is not a read (RFC-026, Who may call)."""

        url = urlparse(self.path)
        if self._refuse():
            return
        port = int(self.server.server_address[1])  # type: ignore[index]  # an AF_INET (host, port)
        origin = self.headers.get("Origin")
        own: tuple[str, ...] = (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
        if LIMITS["hosts"]:  # a viewer's page is on the site's own origin
            own = tuple(f"{scheme}://{h}" for h in LIMITS["hosts"] for scheme in ("https", "http"))
        if origin is not None and origin not in own:
            return self._json(403, {"error": "a call from another origin is refused"}, cache=False)
        if LIMITS["hosts"]:
            return self._viewer(method, url)
        if method == "GET" and url.path == "/api/v1/session":
            # The Workbench's first load trades the token in its address for a cookie (HttpOnly, SameSite=Strict).
            import hmac  # noqa: PLC0415

            tok = (parse_qs(url.query).get("token") or [""])[0]
            if not (tok and API_TOKEN and hmac.compare_digest(tok, API_TOKEN[0])):
                return self._json(401, {"error": "no valid token"}, cache=False)
            nxt = (parse_qs(url.query).get("next") or [""])[0]
            local_page = nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt
            self.send_response(303 if local_page else 204)
            # The printed Configure link: the cookie, then the page itself (this server's only).
            if local_page:
                self.send_header("Location", nxt)
            self.send_header("Set-Cookie", f"{API_COOKIE}={tok}; HttpOnly; SameSite=Strict; Path=/api/")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if not self._api_authorized():
            return self._json(
                401, {"error": "the API needs the server's token (.build/api-token)"}, cache=False
            )
        if method == "GET" and url.path == "/api/v1/openapi.json":
            return self._json(200, openapi.document(), cache=False)
        if url.path == "/api/v1/jobs" or url.path.startswith("/api/v1/jobs/"):
            return self._jobs_route(method, url)
        if method == "POST" and url.path == "/api/v1/estimate":
            n = int(self.headers.get("Content-Length") or 0)
            if n > API_MAX_BODY:
                return self._json(
                    413, {"error": f"an estimate is at most {API_MAX_BODY:,} bytes"}, cache=False
                )
            try:
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            except ValueError:
                return self._json(
                    400,
                    {"error": 'the body is a JSON object: {"operation": ..., "inputs": {...}}'},
                    cache=False,
                )
            if not isinstance(body, dict):
                return self._json(400, {"error": "the body is a JSON object"}, cache=False)
            code, answer_body = api_estimate(body)
            return self._json(code, answer_body, cache=False)
        if self._model_route(method, url):
            return None
        if method != "GET" and self.headers.get(DATA_HEADER) != "1":
            return self._json(
                403, {"error": f"a call that is not a read needs the {DATA_HEADER}: 1 header"}, cache=False
            )
        return self._json(404, {"error": f"no API route {method} {url.path}"}, cache=False)

    def _viewer(self, method: str, url) -> None:
        """/api/v1/ on a public server (RFC-039): no token, nothing written. Counted by the rate limit as the inspector's
        reads are. Only a GET is answered; the jobs' routes, the estimate (it starts a child process) and the session (there
        is no token to trade) are refused, and `_model_route` answers a read operation a public server offers and refuses
        every other. The page's viewer mode is a courtesy: this is what holds."""
        hdr = LIMITS.get("client_header")
        if over_rate(client_key(self.headers.get(hdr) if hdr else None, self.client_address[0])):
            return self._json(429, {"error": f"more than {LIMITS['rate']} requests a minute; wait a moment"})
        if len(url.query) > MAX_QUERY:
            return self._json(400, {"error": f"the question is over {MAX_QUERY} characters"})
        fixed = url.path in ("/api/v1/session", "/api/v1/estimate", "/api/v1/jobs") or url.path.startswith(
            "/api/v1/jobs/"
        )
        if method != "GET" or fixed:
            return self._json(403, {"error": VIEWER_REFUSES, "kind": "not-public"}, cache=False)
        if url.path == "/api/v1/openapi.json":
            key = f"v1:{url.path}"
            code, data = _kept(key) or (200, json.dumps(openapi.document()).encode())
            _keep(key, code, data)
            return self._json(code, data, cache=False)
        if self._model_route(method, url):
            return None
        return self._json(404, {"error": f"no API route {method} {url.path}"}, cache=False)

    def _model_route(self, method: str, url) -> bool:
        """The model's resources (RFC-032): the operation whose method and route match the path, run in this process.
        A read takes its inputs from the query; a write needs the data header, its inputs as a JSON object and `by`
        (who acted, RFC-027; an agent names `for`, the person it acts for). None when no operation's route matches.
        On a public server (a viewer's) only a read the public MCP server offers is run, as a public call, with only the
        inputs it takes there, its answers kept and at most two computed at once; anything else is refused."""
        import jsonschema  # noqa: PLC0415
        from evaluation_harness import _jsonout, mcp_server, ops  # noqa: PLC0415
        from evaluation_harness._version import __version__  # noqa: PLC0415
        from evaluation_harness.model.entity import Problem  # noqa: PLC0415

        public = _visibility.public()

        def say(code: int, body: dict | bytes) -> bool:
            self._json(code, body, cache=False)
            return True

        def words(text: str) -> str:
            """What a refusal says: on a public server with no path of this machine in it."""
            from evaluation_harness import _cmdline  # noqa: PLC0415

            return (
                _cmdline.public_error("ERROR: " + " ".join(text.split()), ROOT)[len("ERROR: ") :]
                if public
                else text
            )

        parts = url.path[len("/api/v1") :].strip("/").split("/")
        for op in ops.OPS.values():
            want = op.route.strip("/").split("/")
            if op.method != method or len(want) != len(parts):
                continue
            if any(w != p for w, p in zip(want, parts, strict=True) if not w.startswith("{")):
                continue
            params = {w[1:-1]: unquote(p) for w, p in zip(want, parts, strict=True) if w.startswith("{")}
            from evaluation_harness import _api  # noqa: PLC0415

            bad = next(((k, v) for k, v in params.items() if _api.id_problem(v)), None)
            if bad:
                return say(400, {"error": f"{op.name}: {bad[0]} {bad[1]!r}: {_api.id_problem(bad[1])}"})
            key = ""
            if public:
                if op.kind != "read" or op.public_dropped:
                    return say(
                        404,
                        {
                            "error": f"{op.name} is not served publicly: {op.public_dropped or 'it is not a read'}",
                            "kind": "not-public",
                        },
                    )
                key = f"v1:{url.path}?{'&'.join(sorted(url.query.split('&')))}"
                if (kept := _kept(key)) is not None:
                    return say(*kept)
            if op.is_job():
                self._job_route(op, params)
                return True
            inputs: dict = {}
            optional = False
            if op.kind == "read":
                q = parse_qs(url.query)
                # `optional=1`: the caller shows the answer only when there is one (a Workbench chart, a file a project
                # may not have), so a read with nothing to show is answered 200 with why (`empty`), as the command
                # says it, not as an error (a browser logs every 4xx in its console).
                optional = q.pop("optional", ["0"])[-1] == "1"
                # An input a public server does not take is refused, not ignored: a caller who asked for an item's text
                # or a rendered file is told, and never answered as if the input had been given.
                refused = sorted(k for k in q if k in op.inputs and k not in op.schema(public)["properties"])
                if public and refused:
                    return say(
                        400,
                        {
                            "error": f"{op.name}: {', '.join(refused)} not taken on a public server",
                            "kind": "not-public",
                        },
                    )
                try:
                    inputs = query_inputs(op.inputs, q)
                except ValueError as exc:
                    return say(400, {"error": f"{op.name}: {exc}"})
            else:
                if self.headers.get(DATA_HEADER) != "1":
                    return say(403, {"error": f"a write needs the {DATA_HEADER}: 1 header"})
                n = int(self.headers.get("Content-Length") or 0)
                if n > API_MAX_BODY:
                    return say(413, {"error": f"a write is at most {API_MAX_BODY:,} bytes"})
                try:
                    body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                except ValueError:
                    body = None
                if not isinstance(body, dict):
                    return say(400, {"error": "the body is a JSON object"})
                by, for_ = body.pop("by", None), body.pop("for", None)
                if not isinstance(by, str) or not by.strip().startswith(("person:", "agent:")):
                    return say(400, {"error": "by: who acted, person:NAME or agent:NAME (RFC-027)"})
                if by.startswith("agent:") and not (isinstance(for_, str) and for_.strip()):
                    return say(
                        400, {"error": f"{by} is an agent: name the person it acts for (for: person:NAME)"}
                    )
                inputs = body
                inputs["by"] = by.strip() + (f" for {for_.strip()}" if by.startswith("agent:") else "")
            try:
                if public:  # as the public MCP server checks a call: the tool's own schema, and the sizes
                    mcp_server.check_arguments(op, {**params, **inputs}, public=True)
                else:
                    jsonschema.validate({k: v for k, v in inputs.items() if k != "by"}, op.schema())
            except jsonschema.ValidationError as exc:
                return say(400, {"error": f"{op.name}: {registry.input_problem(exc)}"})
            except ValueError as exc:
                return say(400, {"error": f"{op.name}: {exc}"})

            def nothing(kind: str, why: str, optional: bool = optional, name: str = op.name) -> bool | None:
                """A read asked as optional with nothing to show, answered 200 with why; None for any other refusal."""
                if not (optional and kind in ("not-enough", "not-found")):
                    return None
                return say(
                    200, {"command": name, "version": __version__, "result": None, "empty": why, "kind": kind}
                )

            def call(op=op, params=params, inputs=inputs):
                if not public:
                    return op.call(**params, **inputs)
                with (
                    _COMPUTE,
                    _visibility.public_call(True),
                ):  # two at once; what it reads, it reads as a public call
                    return op.call(**params, **inputs)

            try:
                result = call()
            except Problem as exc:
                return nothing(exc.kind, words(str(exc))) or say(
                    REFUSAL_STATUS.get(exc.kind, 400),
                    {"error": words(str(exc)), "kind": exc.kind, "problems": [] if public else exc.problems},
                )
            except (
                SystemExit
            ) as exc:  # a body that refuses as a command does (die): ended the thread, no answer
                m = re.match(r"ERROR \(([a-z-]+)\): (.*)", str(exc), re.S)
                kind = m.group(1) if m else "failed"
                why = words((m.group(2) if m else str(exc)).strip())
                return nothing(kind, why) or say(REFUSAL_STATUS.get(kind, 400), {"error": why, "kind": kind})
            if op.kind != "read":
                data_changed(f"{op.name} through the API")
            if (
                public
            ):  # as the MCP server answers: a NaN or an infinity is null, which a browser's JSON.parse reads
                data = json.dumps(
                    _jsonout.plain({"command": op.name, "version": __version__, "result": result})
                ).encode()
                _keep(key, 200, data)
                return say(200, data)
            return say(200, {"command": op.name, "version": __version__, "result": result})
        return False

    def _job_route(self, op, params: dict) -> None:
        """A decision or a work operation (RFC-032 step 9 P3): POST of its resource starts a job and answers 202 with
        it. The body is the inputs the route's parts do not fill, with `by`, `for` and, for an operation that spends,
        `max_cost_usd`; the parts and the body make the job's inputs, the same a call of POST /api/v1/jobs gives."""
        if self.headers.get(DATA_HEADER) != "1":
            return self._json(
                403, {"error": f"a call that is not a read needs the {DATA_HEADER}: 1 header"}, cache=False
            )
        n = int(self.headers.get("Content-Length") or 0)
        if n > API_MAX_JOB_BODY:
            return self._json(413, {"error": "a job call carries at most 50 MB of files"}, cache=False)
        try:
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self._json(400, {"error": "the body is a JSON object"}, cache=False)
        by, for_, cap = body.pop("by", None), body.pop("for", None), body.pop("max_cost_usd", None)
        try:
            mapped = op.route_inputs(params)
        except ValueError as exc:
            return self._json(400, {"error": f"{op.name}: {exc}"}, cache=False)
        clash = sorted(k for k in body if k in params or k in mapped)
        if clash:
            return self._json(
                400,
                {"error": f"{op.name}: {', '.join(clash)} is in the route: not also in the body"},
                cache=False,
            )
        return self._start_job_reply(op.name, {**body, **mapped}, by, for_, cap)

    def _start_job_reply(self, name: str, inputs: Any, by: Any, for_: Any, cap: Any) -> None:
        """Start a job of an operation and answer 202 with it (what POST /api/v1/jobs and the operation's own route
        share): refused before a job exists when it cannot run."""
        from evaluation_harness import _api  # noqa: PLC0415

        try:
            j = _api.start_operation(_api.job_operation(name), inputs, by, cap, for_)
        except _api.Refused as exc:
            return self._json(exc.status, {"error": str(exc)}, cache=False)
        watch_write_job(j)
        return self._json(202, j, cache=False)

    def _start_operation_reply(self, body: dict) -> None:
        """POST /api/v1/jobs: `{operation, inputs, by, for, max_cost_usd}` and nothing else."""
        from evaluation_harness import _api  # noqa: PLC0415

        extra = sorted(set(body) - {"operation", "inputs", "by", "for", "max_cost_usd"})
        if extra or "operation" not in body:
            raise _api.Refused(
                "a job is {operation, inputs, by, for, max_cost_usd}"
                + (f", not {', '.join(extra)}" if extra else ": name the operation")
                + ("; a decision's reason is one of its inputs" if "reason" in extra else "")
            )
        return self._start_job_reply(
            str(body["operation"]),
            body.get("inputs", {}),
            body.get("by"),
            body.get("for"),
            body.get("max_cost_usd"),
        )

    def _jobs_route(self, method: str, url) -> None:
        """The jobs (RFC-026 step 3): list, read, follow the log, fetch an artifact (GET); start, stop, resume (POST,
        with the data header)."""
        from evaluation_harness import _api, _jobs  # noqa: PLC0415

        parts = url.path[len("/api/v1/jobs") :].strip("/").split("/") if url.path != "/api/v1/jobs" else []
        q = parse_qs(url.query)
        try:
            if method == "GET":
                if not parts:
                    try:
                        found = _jobs.list_jobs(
                            q.get("state"), (q.get("operation") or [None])[0], (q.get("goal") or [None])[0]
                        )
                        offset = int((q.get("offset") or ["0"])[0])
                        limit = int((q.get("limit") or ["0"])[0])
                        if offset < 0 or limit < 0:
                            raise ValueError("offset and limit are 0 or more")
                    except ValueError as exc:
                        return self._json(400, {"error": f"jobs: {exc}"}, cache=False)
                    shown = found[offset : offset + limit] if limit else found[offset:]
                    return self._json(200, {"jobs": shown, "total": len(found)}, cache=False)
                job_id = parts[0]
                if len(parts) == 1:
                    return self._json(200, _jobs.read(job_id), cache=False)
                if parts[1:] == ["log"]:
                    data, nxt = _jobs.log_from(job_id, int((q.get("from") or ["0"])[0]))
                    return self._json(200, {"log": data.decode("utf-8", "replace"), "next": nxt}, cache=False)
                if len(parts) == 3 and parts[1] == "files":
                    f = _jobs.job_dir(job_id) / _api._safe_name(parts[2])
                    from evaluation_harness._sheet import KEY_SUFFIX  # noqa: PLC0415

                    if f.name.endswith(KEY_SUFFIX):
                        return self._json(
                            403,
                            {
                                "error": f"{f.name} is a blind sheet's key: it stays with the job, so the sheet stays "
                                f"blind; sheet-import reads it there (export_job: {job_id})"
                            },
                            cache=False,
                        )
                    if parts[2] in (
                        "job.json",
                        "state.json",
                        "supervisor.lock",
                        "supervisor.pid",
                    ) or not _store.is_file(f):
                        return self._json(
                            404, {"error": f"no file {parts[2]!r} in job {job_id}"}, cache=False
                        )
                    body = _store.read_bytes(f)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Disposition", f'attachment; filename="{f.name}"')
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                    return None
                return self._json(404, {"error": f"no API route GET {url.path}"}, cache=False)
            if self.headers.get(DATA_HEADER) != "1":
                return self._json(
                    403,
                    {"error": f"a call that is not a read needs the {DATA_HEADER}: 1 header"},
                    cache=False,
                )
            if not parts:
                n = int(self.headers.get("Content-Length") or 0)
                if n > API_MAX_JOB_BODY:
                    return self._json(
                        413, {"error": "a job call carries at most 50 MB of files"}, cache=False
                    )
                try:
                    body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                except ValueError:
                    return self._json(400, {"error": "the body is a JSON object"}, cache=False)
                if not isinstance(body, dict):
                    return self._json(400, {"error": "the body is a JSON object"}, cache=False)
                return self._start_operation_reply(body)
            if len(parts) == 2 and parts[1] == "stop":
                return self._json(200, _jobs.stop(parts[0]), cache=False)
            if len(parts) == 2 and parts[1] == "resume":
                resumed = _api.resume_job(parts[0])
                watch_write_job(resumed)
                return self._json(202, resumed, cache=False)
            return self._json(404, {"error": f"no API route POST {url.path}"}, cache=False)
        except _api.Refused as exc:
            return self._json(exc.status, {"error": str(exc)}, cache=False)
        except (FileNotFoundError, ValueError) as exc:
            return self._json(404, {"error": f"no such job: {exc}"}, cache=False)

    def do_PATCH(self):
        """An edit of the model's records (RFC-032), through the API; nothing else."""
        if urlparse(self.path).path.startswith("/api/v1/"):
            self._observed(lambda: self._api("PATCH"))
            return
        self._observed(self._no_write)

    def do_PUT(self):
        """Nothing is written by PUT (the Configure page's save is retired, PRD-017)."""
        self._observed(self._no_write)

    def do_DELETE(self):
        """Nothing is deleted by DELETE (the Configure page's delete is retired, PRD-017; `evh data-rm` deletes)."""
        self._observed(self._no_write)

    def _no_write(self) -> None:
        if not self._refuse():
            self.send_error(404)

    def do_HEAD(self):
        """Handle HEAD requests with access checks. A public server has no file to serve (its pages are nginx's)."""
        if LIMITS["hosts"]:
            self.send_error(404)
        elif not self._refuse() and not self._from_site(urlparse(self.path).path, head=True):
            super().do_HEAD()

    def do_GET(self):
        """Handle GET requests for static files and API endpoints (observed by the hooks)."""
        self._observed(self._get)

    def _get(self):
        url = urlparse(self.path)
        if url.path.startswith("/api/v1/"):
            return self._api("GET")
        hook_route = _hook_routes().get(url.path)
        if hook_route is not None:
            code, ctype, data = hook_route(url.query)
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if self._refuse():
            return
        if url.path == "/api/health":
            if FRESH["on"]:
                return self._json(200, {"ok": True, "catalog": catalog_status()}, cache=False)
            return self._json(200, {"ok": True})
        if url.path == "/workbench" or url.path.startswith("/workbench/"):
            return self._workbench(url.path)
        if url.path == "/api/sheet" and parse_qs(url.query).get("format") == ["csv"]:
            code, data, ctype = sheet_csv(url.query)
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if code == 200:
                ds = parse_qs(url.query).get("dataset", ["sheet"])[0]
                self.send_header("Content-Disposition", f'attachment; filename="sheet-{ds}.csv"')
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if url.path in ("/api/compare", "/api/item", "/api/sheet"):
            # A client-supplied header is trusted only when named (--client-header): behind a
            # proxy that sets it, with the origin reachable only through that proxy. Otherwise
            # anyone can send a new value per request and never hit the limit.
            hdr = LIMITS.get("client_header")
            client = self.headers.get(hdr) if (LIMITS["hosts"] and hdr) else None
            if over_rate(client_key(client, self.client_address[0])):
                return self._json(
                    429, {"error": f"more than {LIMITS['rate']} requests a minute; wait a moment"}
                )
            code, body = answer(url.path, url.query)
            return self._json(code, body)
        if not self.prefixes:  # public mode: the API only, never a file
            self.send_error(404)
            return
        if self._from_site(url.path):
            return
        if self._from_store(url.path):
            return
        super().do_GET()

    def _workbench(self, url_path: str) -> None:
        """A file of the Workbench (PRD-017), from the package: a name in its folder, never a path; it reads the
        project through the API, with the cookie the session route set."""
        if url_path == "/workbench":
            self.send_response(301)
            self.send_header("Location", "/workbench/")
            self.end_headers()
            return
        name = url_path[len("/workbench/") :] or "index.html"
        kind = WORKBENCH_TYPES.get(Path(name).suffix)
        f = WORKBENCH / name
        if name not in WORKBENCH_FILES or kind is None or not _store.is_file(f):
            self.send_error(404)
            return
        data = _store.read_bytes(f)
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _from_site(self, url_path: str, head: bool = False) -> bool:
        """A page of the catalog, rendered from the data as it is (RFC-040): under the catalog's address, on a server
        that has pages of its own; `head`: its headers only. A page the catalog's own (Site.claims) that the data does
        not have is 404, whatever an older export left on disk. False for anything else: a page a project's builder wrote
        beside them is then read from the folder, as it always was."""
        prefix = self.prefixes[0] if self.prefixes else ""
        if not FRESH["on"] or not prefix or not url_path.startswith(prefix):
            return False
        rel = unquote(url_path[len(prefix) :])
        if rel == "" or rel.endswith("/"):
            rel += "index.html"
        if ".." in Path(rel).parts or rel.startswith("/"):
            return False
        kind = SITE_TYPES.get(Path(rel).suffix)
        if kind is None:
            return False
        try:
            site, text = site_page(rel)
        except Exception as exc:  # noqa: BLE001 -- said in the log and on health (site_page); the next request tries again
            self._json(
                500, {"error": f"the page could not be rendered: {type(exc).__name__}: {exc}"}, cache=False
            )
            return True
        if text is None:
            if not site.claims(rel):
                return False
            self.send_error(404)
            return True
        data = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if not head:
            self.wfile.write(data)
        return True

    def _from_store(self, url_path: str) -> bool:
        """With the sqlite store (RFC-025) a file of the data tree is a row of the project's database: served from
        it, through the same prefix and path checks as a file on disk. False for anything else."""
        if _common.store() != "sqlite":
            return False
        data = _common.DATA
        data_prefix = _data_url_prefix()
        if not data_prefix or not url_path.startswith(data_prefix):
            return False
        rel = Path(unquote(url_path[len(data_prefix) :]))
        if ".." in rel.parts or rel.is_absolute():
            self.send_error(404)
            return True
        f = data / rel
        if not _store.is_file(f):
            self.send_error(404)
            return True
        body = _store.read_bytes(f)
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(str(f)))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def end_headers(self) -> None:
        """A file of the project's data is shown, never run as one of this server's pages: an .html or .svg under
        data/ (a fetched source page, a capture record) could otherwise call the Configure page's write API from this
        origin (advisor review, 2026-11-06). sandbox gives it an origin of its own; nosniff keeps its type. The same for
        every served prefix but the catalog's own pages (their scripts must run): `served_dirs` and `artifacts/` hold files
        a project or an agent wrote, an agent's trial directory among them (RFC-038)."""
        path = urlparse(self.path).path
        shown = (*self.prefixes[1:], _data_url_prefix())  # the first prefix is the catalog's pages
        if any(x and path.startswith(x) for x in shown):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "sandbox")
        super().end_headers()

    def _json(self, code: int, body, cache: bool = True) -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if code >= 400 or not cache else "public, max-age=300")
        if LIMITS["hosts"] and urlparse(self.path).path.startswith("/api/v1/"):
            # How the Workbench's page knows it is a viewer (RFC-039): the server says so with every answer, so the page
            # needs no sign-in call and no setting of its own. It is a courtesy: the refusals are the server's.
            self.send_header("X-EVH-Viewer", "1")
            # Where the catalog is: the deployment serves it under a path of its own, the local server at its root.
            self.send_header("X-EVH-Catalog", LIMITS.get("catalog_at") or "/")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        """Log API requests only; suppress static file serving noise. A token in a request line (the session route's
        `?token=`) is masked: the log is kept where the token must not be (fleet, 2026-11-18)."""
        if args and "/api/" in str(args[0]):
            super().log_message(fmt, *(re.sub(r"token=[^&\s\"]+", "token=<masked>", str(a)) for a in args))


def _common_prog() -> str | None:
    """`evh <command>` for --help (see _common.evh_prog)."""
    from evaluation_harness._common import evh_prog  # noqa: PLC0415

    return evh_prog()


def main() -> int:
    """Start the catalog server on localhost or in public mode."""
    ap = argparse.ArgumentParser(prog=_common_prog(), description=__doc__.splitlines()[0])
    ap.add_argument(
        "--port",
        type=int,
        help="the port (default: the project's own, the same every time; 8765 with --public)",
    )
    ap.add_argument(
        "--adapter",
        help="path/to/file.py:Class (default: config.yaml catalog.adapter, else the harness's own layout)",
    )
    ap.add_argument("--build-dir", type=Path, default=ROOT / ".build" / "catalog")
    ap.add_argument(
        "--public",
        metavar="HOST[,HOST]",
        help="serve the API only, to these Host names, behind a reverse proxy",
    )
    ap.add_argument(
        "--behind-proxy",
        metavar="HOST[,HOST]",
        help="the whole local inspector (pages, items, outputs, references) for these Host names too, behind a "
        "private proxy (a tailnet's Caddy); with --bind 0.0.0.0 in a container. No rate limit and nothing withheld, "
        "unlike --public; the write API (/api/v1) and the Workbench stay this machine's own, never served to these Host names",
    )
    ap.add_argument(
        "--bind",
        default="127.0.0.1",
        help="address to listen on (0.0.0.0 inside a container whose port is published on loopback)",
    )
    ap.add_argument("--rate", type=int, default=30, help="public mode: API requests per client per minute")
    ap.add_argument(
        "--publish",
        default="",
        metavar="WHAT",
        help="public mode: text to serve besides the numbers, comma-separated: outputs, references "
        "(default: none; the item itself is never served publicly)",
    )
    ap.add_argument(
        "--client-header",
        metavar="NAME",
        help="public mode: the header that names the client (e.g. CF-Connecting-IP), only behind a proxy "
        "that sets it and an origin no one else can reach; default: the TCP peer",
    )
    ap.add_argument(
        "--catalog-at",
        default="/",
        metavar="PATH",
        help="public mode: where the deployment serves the built catalog (e.g. /catalog/), for the Workbench's links "
        "to it; default /",
    )
    ap.add_argument("--max-arms", type=int, default=40, help="most arms in one comparison")
    ap.add_argument(
        "--hooks",
        metavar="FILE.py[:NAME]|MODULE[:NAME]",
        help="a deployment's hooks: start, request, error, routes (load_hooks says what each is); default none",
    )
    ap.add_argument(
        "--warm",
        type=Path,
        metavar="CATALOG_DIR",
        help="answer every comparison this built catalog links to, in the background",
    )
    # The pages' own options, as `evh catalog` takes them (RFC-040): the server renders the pages it would write.
    pages = ap.add_argument_group("the pages (as evh catalog takes them)")
    pages.add_argument("--brand", default="eval catalog", help="the name beside the logo")
    pages.add_argument(
        "--api", default="/api/", help="where the inspector's API answers, for pages served under a path"
    )
    pages.add_argument("--head", metavar="FILE", help="HTML added to every page's <head> (none by default)")
    pages.add_argument("--about", metavar="FILE", help="HTML shown on the overview, under its description")
    pages.add_argument(
        "--repo", metavar="URL", help="where the project's files can be read: a project path links there"
    )
    pages.add_argument(
        "--mcp", metavar="URL", help="the deployment's MCP server, named in every page's footer"
    )
    pages.add_argument("--mcp-howto", metavar="URL", help="--mcp: where to read how to connect an agent")
    pages.add_argument("--card", metavar="URL", help="the image a shared link's card shows (1200x630)")
    pages.add_argument(
        "--link",
        action="append",
        default=[],
        metavar="LABEL=URL",
        help="a part of the publication, for the header",
    )
    args = ap.parse_args()
    if args.public and args.behind_proxy:
        die("--public and --behind-proxy are two deployments: one at a time", "bad-argument")
    from evaluation_harness import catalog_build  # noqa: PLC0415

    catalog_build.SECTIONS = catalog_build.configure(args)
    if args.port is None:
        from evaluation_harness._common import project_port  # noqa: PLC0415

        args.port = 8765 if args.public else project_port("catalog")
    global HOOKS
    HOOKS = load_hooks(args.hooks) if args.hooks else None
    _common.use_p_cache()  # the API's views draw the goals' tests in this process; keep them as `evh` does
    # The API's views read every arm's scores: kept (and dropped when the data changes: refresh -> cache_clear), not
    # read again for each request.
    set_adapter(scores_once(load_catalog_adapter(args.adapter), held=True))
    LIMITS["max_arms"] = args.max_arms
    if args.public:
        LIMITS["hosts"] = tuple(h.strip() for h in args.public.split(",") if h.strip())
        LIMITS["rate"] = args.rate
        LIMITS["client_header"] = args.client_header
        LIMITS["publish"] = tuple(x.strip() for x in args.publish.split(",") if x.strip())
        bad = set(LIMITS["publish"]) - {"outputs", "references"}
        if bad:
            die(f"--publish takes outputs and/or references, not {', '.join(sorted(bad))}", "bad-argument")
        if not (args.catalog_at.startswith("/") and args.catalog_at.endswith("/")):
            die(
                f"--catalog-at is a path that starts and ends with /, not {args.catalog_at!r}", "bad-argument"
            )
        LIMITS["catalog_at"] = args.catalog_at
        Handler.prefixes = ()
    else:
        if args.behind_proxy:
            # The homelab fleet's private catalog (2026-11-05): Caddy on the tailnet in front, no published port.
            LIMITS["proxy_hosts"] = tuple(h.strip() for h in args.behind_proxy.split(",") if h.strip())
            if not LIMITS["proxy_hosts"]:
                die("--behind-proxy needs at least one Host name", "bad-argument")
        elif args.bind != "127.0.0.1":
            die(
                "--bind other than 127.0.0.1 needs --public or --behind-proxy (and a proxy in front)",
                "not-allowed",
            )
        # No catalog needs building first: its pages are rendered when asked for (RFC-040). The folder is still where
        # its address points, and where a page a project's own builder adds beside them is read from.
        Handler.prefixes = served(args.build_dir, A.data_dir, tuple(getattr(A, "served_dirs", ())))
        start_fresh()
    migration_check()
    threading.Thread(target=watch_migrations, daemon=True).start()
    if args.warm:
        threading.Thread(
            target=lambda: print(f"warm: {warm(args.warm)} comparison(s) cached", flush=True), daemon=True
        ).start()
    # Bound, then the token written, then listening: a client that waits for the port to open and reads
    # .build/api-token then reads this server's token. Listening first left a moment in which it read the previous
    # server's (a 401; test_jobs met it under load). A port that cannot be bound leaves a running server's token as is.
    server = ThreadingHTTPServer(
        (args.bind, args.port), partial(Handler, directory=str(ROOT)), bind_and_activate=False
    )
    try:
        server.server_bind()
        # --port 0: the system chose one; every line below names it (they printed :0, which opens nothing)
        args.port = int(server.server_address[1])  # an AF_INET (host, port)
        local = not args.public and not LIMITS.get("proxy_hosts")
        if local:
            from evaluation_harness import _api  # noqa: PLC0415

            API_TOKEN[:] = [_api.new_token()]
        server.server_activate()
    except OSError as exc:
        server.server_close()
        why = (
            f"port {args.port} is in use. Stop what holds it, or pass --port N."
            if exc.errno == errno.EADDRINUSE
            else f"{exc.strerror}. Pass --port N, or check --bind."
        )
        die(f"cannot listen on {args.bind}:{args.port}: {why}", "failed")
    from evaluation_harness._version import __version__  # noqa: PLC0415

    _hook(
        "start", {"bind": args.bind, "port": args.port, "public": bool(args.public), "version": __version__}
    )
    if args.public:
        print(
            f"inspector API on {args.bind}:{args.port} for {', '.join(LIMITS['hosts'])} "
            f"({LIMITS['rate']}/min per client, {LIMITS['max_arms']} arms max)",
            flush=True,
        )
    elif LIMITS.get("proxy_hosts"):
        print(
            f"catalog on {args.bind}:{args.port} for {', '.join(LIMITS['proxy_hosts'])} (behind a proxy) and this "
            f"machine, at {Handler.prefixes[0]}; the data page's writes are not served",
            flush=True,
        )
    else:
        from evaluation_harness import _api  # noqa: PLC0415

        print(f"catalog: http://127.0.0.1:{args.port}{Handler.prefixes[0]}   (Ctrl-C to stop)", flush=True)
        print(
            f"  API: http://127.0.0.1:{args.port}/api/v1/  (token in {_api.token_path()}: "
            f"Authorization: Bearer <token>, or GET /api/v1/session?token=<token> for a cookie)",
            flush=True,
        )
        # The link that signs in carries the token: printed whole only to a terminal, so a log that captures this
        # output to a file or a pipe (a background job's log, CI's) never holds a working token (fleet, 2026-11-18).
        # A terminal recorder (script, asciinema, tmux's pipe-pane) runs in a terminal and does keep it.
        tok = (API_TOKEN or [""])[0] if sys.stdout.isatty() else f"<the token in {_api.token_path()}>"
        print(
            f"  Workbench: http://127.0.0.1:{args.port}/api/v1/session?token={tok}&next=/workbench/  (signs in once)",
            flush=True,
        )
        print(f"  the project {ROOT}, on a port of its own", flush=True)
        print(
            "  each page is rendered when it is asked for, from the data as it is then: a write shows on the next read",
            flush=True,
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
