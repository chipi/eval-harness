#!/usr/bin/env python3
"""Serve the catalog and the run inspector: on this machine (127.0.0.1) by default, or --public behind a proxy.

    evh catalog-serve [--port N] [--adapter path/to/file.py:Class]
    make catalog-serve

Builds nothing: run `evh catalog` first. Static files are the built catalog and the data tree
(its "files" links open run folders). Three JSON endpoints feed the inspector page (and GET /api/health says the
server is up); a local server also answers the API (/api/v1/, RFC-026):

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
import json
import re
import sys
import threading
import time
from collections import Counter, OrderedDict, defaultdict
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent

from evaluation_harness import (  # noqa: E402
    _common,
    _fields,
    _store,
    _visibility,
    stats,
)
from evaluation_harness._common import (  # noqa: E402
    ROOT,
    SPEED_KEYS,
    die,
)
from evaluation_harness.catalog_adapter import Adapter, item_fields, load_catalog_adapter  # noqa: E402

#: Every comparison ends in one of these, so a page can always say what it shows and why.
STATES = ("compared", "average only", "no shared metric", "not scorable")

A: Adapter = None  # type: ignore[assignment]  # set by main() or set_adapter()


def set_adapter(adapter: Adapter) -> None:
    """Set the adapter and clear cached scores."""
    global A
    A = adapter
    _scores.cache_clear()
    _known.cache_clear()


@lru_cache(maxsize=1)
def _known() -> tuple[frozenset, frozenset]:
    """(every arm the catalog lists, every reference id). A request may name an arm or a path
    that selects arms (a run directory), but only arms in this set: an adapter's arms_of may
    accept any path it is handed, and `../../.git` reached the podcast adapter's file reads."""
    listed = set(A.arms())
    arms = listed | {x for a in listed for x in A.arms_of(a)}
    return frozenset(arms), frozenset(str(r.get("id")) for r in A.references())


def _arms_known(path: str) -> list:
    """The arms `path` selects, or [] when it selects none or any the catalog does not list."""
    got = A.arms_of(path)
    return got if got and set(got) <= _known()[0] else []


@lru_cache(maxsize=4096)
def _scores(arm: str, rescore: bool) -> dict:
    # Re-scoring can be the slow part, and a baseline page asks for every arm on its dataset.
    # Forgotten by cache_clear (a data page write, a rebuild); a run another process makes shows after a restart.
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


def _reference_free(metric: str) -> bool:
    """The adapter says (reference_free); else a metric named for the bill or the clock."""
    fn = getattr(A, "reference_free", None)
    return bool(fn(metric)) if callable(fn) else any(k in metric for k in _REFERENCE_FREE)


def _other_reference(series: dict, baseline: str, metric: str, rescore: bool, dataset: str = "") -> list:
    """Arms whose `metric` was scored against another reference than the baseline's, which a
    paired test must not set against it: on one dataset, a silver-scored and a gold-scored run
    both record `overlap_f1`, but not of the same thing. Nothing is set aside when the scores
    were recomputed against one reference (re-scoring, or a metric named `x vs <ref>`), or when
    the metric needs no reference (length, cost, latency, tokens)."""
    if (
        rescore
        or _ref_of(metric)
        or A.is_neutral(metric, dataset or None)
        or metric in A.shape_metrics
        or _reference_free(metric)
    ):
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


def _metric_rows(counts: Counter, per_arm: dict, baseline: str, dataset: str | None = None) -> list:
    return [
        {
            "name": k,
            "arms": n,
            "lower_is_better": A.lower_is_better(k, dataset),
            "neutral": A.is_neutral(k, dataset or None),
            "baseline_has": k in per_arm.get(baseline, {}),
            "format": A.reference_format(_ref_of(k)) if _ref_of(k) else "",
            "archived": bool(_ref_of(k) and A.reference_archived(_ref_of(k))),
        }
        for k, n in counts.most_common()
    ]


def _default_metric(counts: Counter, per_arm: dict, arms: list, asked: str, dataset: str = "") -> str:
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
            A.is_neutral(k, dataset or None),
            _reference_free(k),  # the bill and the clock: only when nothing is scored
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
    averages: dict = {}
    repeats: dict = {}
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
        w.append(
            f"{_label(ctx['asked'])} has no '{metric}' scores, so "
            f"{_label(ctx['baseline'])} is the baseline instead."
        )
    if ctx["baseline"] and A.describe(ctx["baseline"]).get("wrote_reference"):
        w.append(
            f"{_label(ctx['baseline'])} wrote the reference these arms are scored against: it is graded "
            "against its own outputs, so every other arm reads as worse. Compare the others to each "
            "other with another baseline."
        )
    hashes = {a: A.input_hashes(a) for a in series}
    base_h = hashes.get(ctx["baseline"], {})
    for a, h in hashes.items():
        diff = [e for e in h if e in base_h and h[e] != base_h[e]]
        if diff:
            w.append(
                f"{_label(a)} recorded a different input hash than the baseline on "
                f"{len(diff)} {item}(s): the arms may not have read the same input."
            )
    unknown = [_label(a) for a in ctx["arms"] if not ctx["ds"][a]]
    if unknown:
        w.append(
            f"No dataset_id on record for: {', '.join(unknown)}. The same-dataset rule cannot "
            f"be checked for them; they are paired by {item} id only."
        )
    averages, repeats = ctx["averages"], ctx["repeats"]
    missing = [
        _label(a)
        for a in ctx["arms"]
        if a not in series and a not in averages and a not in repeats and a not in ctx.get("other_ref", ())
    ]
    if missing:
        w.append(f"No '{metric}' on record for: {', '.join(missing)}.")
    if repeats:
        w.append(
            f"{len(repeats)} arm(s) recorded exactly the same '{metric}' as an arm already "
            "shown, so they are not drawn again: "
            + "; ".join(f"{_label(a)} = {_label(t)}" for a, t in repeats.items())
            + "."
        )
    if ctx["aside"]:
        w.append(
            f"Left out, on another dataset than {ctx['dataset']}: "
            + ", ".join(_label(a) for a in ctx["aside"])
            + "."
        )
    if ctx.get("other_ref"):
        want = A.describe(ctx["baseline"]).get("reference", "")
        w.append(
            f"Not tested against the baseline: '{metric}' was scored against another reference "
            f"than the baseline's ({want}) for "
            + ", ".join(f"{_label(a)} ({A.describe(a).get('reference', '')})" for a in ctx["other_ref"])
            + ". Pick a baseline scored against the same reference to compare them."
        )
    if averages:
        w.append(
            f"{len(averages)} arm(s) recorded only an average '{metric}', no per-{item} "
            "scores: shown as averages, not tested."
        )
    drift = []
    for a in series:
        f = A.output_format(a)
        if f["asked"] and f["got"] and f["got"] != f["asked"]:
            drift.append(f"{_label(a)} (asked {f['asked']}, got {f['got']})")
    if drift:
        w.append("Format not followed: " + "; ".join(drift) + ". The score compares what came back.")
    w += [n.rstrip(".") + "." for n in dict.fromkeys(n for a in ctx["arms"] for n in A.notes(a))]
    if ctx.get("wheres"):
        n = len(series.get(ctx["baseline"], {}))
        w.append(
            f"Filtered to the {n} {item}(s) where "
            + " and ".join(x.replace(":", " = ", 1) for x in ctx["wheres"])
            + ": a subset is a smaller sample, so fewer differences can be significant."
        )
    if ctx.get("breakdown"):
        w.append(
            f"Broken down by {ctx['by']}: {ctx['breakdown']['family_size']} tests, Holm-corrected "
            "together, so a group is held to a stricter threshold than it would be alone."
        )
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
    return [
        {
            "name": n,
            "label": f.get("label") or n,
            "type": f["type"],
            "values": f.get("values"),
            "unit": f.get("unit", ""),
            "groupable": f["type"] in _fields.GROUPABLE,
        }
        for n, f in decl.items()
    ]


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


def _disagreeing(series: dict, baseline: str) -> dict:
    """Only the items where the arms decided differently (RFC-023): an item stays when any arm's output is not the
    same decision as the baseline's, by the baseline arm's adapter's `same(a, b)` (else the same text)."""
    fn = getattr(A, "same_output", None)
    same = fn(baseline) if callable(fn) else (lambda a, b: a.strip() == b.strip())

    def out(arm: str, item: str) -> str | None:
        v = A.item_view(arm, item)  # the adapter keeps an item name from leaving its run
        return v.get("text") if v.get("kind") == "text" else None

    keep = set()
    for item in series.get(baseline, {}):
        b = out(baseline, item)
        if b is None:
            continue
        if any(
            item in vals and (o := out(a, item)) is not None and not same(b, o)
            for a, vals in series.items()
            if a != baseline
        ):
            keep.add(item)
    return {a: {i: v for i, v in vals.items() if i in keep} for a, vals in series.items()}


def _goal_cluster_on(dataset: str) -> str | None:
    """The one field every goal that names `cluster:` for this dataset names, so the inspector tests
    as the goal pages do (ADR-0002); None when no goal does, or goals disagree (then only `cluster=` does)."""
    from evaluation_harness._common import goal_cluster, load_goals  # noqa: PLC0415

    named = {goal_cluster(g, dataset) for g in load_goals().values()} - {None}
    return next(iter(named)) if len(named) == 1 else None


def goal_clusters_on(dataset: str) -> tuple[dict | None, str | None]:
    """({item: cluster key}, field) for the goals' cluster field on `dataset` (_goal_cluster_on), else (None, None)."""
    field = _goal_cluster_on(dataset) if dataset else None
    if not field:
        return None, None
    every = (item_fields(A, dataset) or {}).get("values") or {}
    return {i: v[field] for i, v in every.items() if v.get(field) not in (None, "")}, field


def compare(params: dict) -> dict:
    """Compare arms: parse query params, get scores, run paired tests, return result."""
    runs = [r.strip("/") for r in params.get("runs", [""])[0].split(",") if r.strip()]
    if len(runs) > LIMITS["max_arms"]:
        return {"error": f"{len(runs)} arms asked for; at most {LIMITS['max_arms']} in one comparison"}
    by_run = {r: _arms_known(r) for r in runs}
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
    notes = [n.rstrip(".") + "." for n in dict.fromkeys(n for a in arms for n in A.notes(a))]
    metric = params.get("metric", [""])[0]
    instead = None
    if metric not in counts:
        # A metric asked for by name that no arm scores per item (a run-level one, score_run()'s, or one these runs
        # do not record) cannot be the one compared: said, with the values the arms record for it, never swapped
        # in silence.
        if metric:
            had = {a: v for a in arms if (v := A.recorded_means(a).get(metric)) is not None}
            instead = f"{metric} has no score per {A.item_word} for these runs, so it cannot be tested" + (
                ": recorded per run as " + ", ".join(f"{_label(a)} {v:.4g}" for a, v in had.items())
                if had
                else ": no arm records it"
            )
        metric = _default_metric(counts, per_arm, arms, asked, dataset) if counts else ""
        if instead:
            instead += f". Compared on {metric} instead."
    if not counts or (metric in A.shape_metrics and not params.get("metric", [""])[0]):
        return {
            "state": "not scorable",
            "can_rescore": A.can_rescore,
            "arms": [A.describe(a) for a in arms],
            "metrics": _metric_rows(counts, per_arm, asked, dataset),
            "warnings": [
                *notes,
                f"No score per {A.item_word} on record for these runs"
                + (", only output length or latency: pick one of those to compare them." if counts else ".")
                + (" Re-scoring may produce one." if A.can_rescore and not rescore else ""),
            ],
        }
    series = {a: s[metric]["values"] for a, s in per_arm.items() if metric in s}
    # With no baseline named, a promoted baseline is the natural reference point.
    # The arm of a promoted baseline when one is selected, else the first.
    bfn = getattr(A, "baselines", None)
    current_bl = [b for b in (bfn() if callable(bfn) else []) if b.get("arm")]
    # The dataset's own baseline first (arms that answer no goal), then any goal's (RFC-027).
    own = {b["arm"] for b in current_bl if not b.get("goal")}
    promoted = {b["arm"] for b in current_bl}
    fallback = next(
        (a for a in series if a in own),
        next((a for a in series if a in promoted or a.startswith("baselines/")), next(iter(series))),
    )
    baseline = asked if asked in series else fallback
    other_ref = _other_reference(series, baseline, metric, rescore, dataset)
    for a in other_ref:
        series.pop(a)
    decl, fvalues = _fields_of(dataset)
    wheres = [w for w in params.get("where", []) if w]
    series, error = _filter(series, decl, fvalues, wheres)
    if error:
        return {"error": error}
    disagree = params.get("disagree", [""])[0] == "1"
    if disagree:
        series = _disagreeing(series, baseline)
    # Items that share a value of the cluster field count as one in every test (stats.clustered). Asked for by
    # name it must be a field this deployment shows; a goal's own field is used as the goal pages use it.
    cluster = params.get("cluster", [""])[0]
    if cluster and cluster not in decl:
        return {"error": f"cluster by a field of {dataset}, not {cluster!r}"}
    clusters: dict | None
    if cluster:
        every = (item_fields(A, dataset) or {}).get("values") or {}
        clusters = {i: v[cluster] for i, v in every.items() if v.get(cluster) not in (None, "")}
    else:
        clusters, cluster = goal_clusters_on(dataset)
    higher, neutral = not A.lower_is_better(metric, dataset), A.is_neutral(metric, dataset or None)
    # A family and a threshold come from the URL, so they are checked, not trusted: a family
    # smaller than the arms tested here, or a threshold above alpha (or below what the family
    # allows), would turn "not significant" into "significant" by editing a link.
    family = _number(params, "family", int) or None
    threshold = _number(params, "threshold", float)
    tested = max(len(series) - 1, 1)
    if family is not None and family < tested:
        return {"error": f"family={family} is smaller than the {tested} arm(s) tested here"}
    if threshold is not None and not (
        0 < threshold <= stats.ALPHA and threshold >= stats.ALPHA / (family or tested)
    ):
        return {
            "error": f"threshold={threshold} is not a Holm threshold for this family (alpha {stats.ALPHA})"
        }
    result = stats.compare(
        series,
        baseline,
        higher_is_better=higher,
        neutral=neutral,
        family=family,
        threshold=threshold,
        clusters=clusters,
    )
    by, breakdown, ungrouped = params.get("by", [""])[0], None, 0
    if by:
        if by not in decl or decl[by]["type"] not in _fields.GROUPABLE:
            return {"error": f"break a comparison down by a choice or yes/no field, not {by!r}"}
        groups, ungrouped = _groups(decl[by], by, fvalues, series.get(baseline, {}))
        breakdown = stats.compare_by(
            series, baseline, groups, higher_is_better=higher, neutral=neutral, clusters=clusters
        )
    averages, repeats = _averages(arms, series, metric)
    swapped = bool(asked) and asked != baseline
    ctx = {
        "metric": metric,
        "series": series,
        "arms": arms,
        "ds": ds,
        "asked": asked,
        "baseline": baseline,
        "swapped": swapped,
        "averages": averages,
        "repeats": repeats,
        "aside": aside,
        "dataset": dataset,
        "other_ref": other_ref,
        "wheres": wheres,
        "by": by,
        "breakdown": breakdown,
        "ungrouped": ungrouped,
    }
    return {
        "metric": metric,
        "higher_is_better": higher,
        "neutral": neutral,
        "baseline": baseline,
        "can_rescore": A.can_rescore,
        "metrics": _metric_rows(counts, per_arm, baseline, dataset),
        "arms": [dict(A.describe(a), source=per_arm[a].get(metric, {}).get("source", "")) for a in arms],
        "series": series,
        # every arm's shape metrics, for the scatter's x axis, whatever metric is chosen
        "shape": _shape(per_arm),
        "items": result["items"],
        "rows": result["rows"],
        "family_size": result["family_size"],
        "dataset": dataset,
        "averages": averages,
        "repeats": repeats,
        "state": _state(result["rows"], averages, swapped),
        "warnings": [
            *(
                [
                    (
                        f"Tested by {cluster}: {A.item_word}s that share a {cluster} count as one in every test "
                        f"({max((r.get('clusters') or 0 for r in result['rows']), default=0)} clusters)."
                    )
                ]
                if clusters is not None
                else []
            ),
            *([instead] if instead else []),
            *_warnings(ctx),
        ],
        "cluster": cluster or None,
        "fields": _field_list(decl),
        "where": wheres,
        "disagree": disagree,
        "by": by,
        "breakdown": breakdown,
        "conditions": _conditions(list(series), metric),
    }


def _shape(per_arm: dict) -> dict:
    """{x metric: {arm: {item: value}}} for the scatter: the adapter's shape metrics (latency, the
    output's size), then cost in dollars and in tokens (in + out), the goal pages' cost axis."""
    from evaluation_harness.axes import tokens_per_item  # noqa: PLC0415

    out = {
        k: {a: s[k]["values"] for a, s in per_arm.items() if k in s}
        for k in (*A.shape_metrics, "cost_usd")
        if any(k in s for s in per_arm.values())
    }
    tok = {a: tokens_per_item(s) for a, s in per_arm.items()}
    if any(tok.values()):
        out["tokens"] = {a: t for a, t in tok.items() if t}
    return out


def _conditions(arms: list, metric: str) -> dict | None:
    """What the compared arms were measured under, where it differs (A.conditions, from each
    run's fingerprint). A different scorer or different reference bytes makes the scores
    different measurements; a different machine makes latency one. None when the adapter
    cannot say."""
    fn = getattr(A, "conditions", None)
    if not callable(fn) or not arms:
        return None
    got = {a: fn(a) or {} for a in arms}
    keys = sorted({k for c in got.values() for k in c})
    differ = [
        {"name": k, "values": {a: got[a].get(k) for a in arms}}
        for k in keys
        if len({got[a].get(k) for a in arms}) > 1
        or any(str(got[a].get(k, "")).startswith("varies:") for a in arms)
    ]
    names = {d["name"] for d in differ}
    warnings = []
    if names & {"scorer.id", "scorer.sha256"}:
        warnings.append(
            "Scored by different scorers (adapter code): these numbers are different measurements. "
            "Re-score them with one adapter (evh rescore) before reading the test."
        )
    if "reference.sha256" in names:
        warnings.append(
            "Scored against different reference bytes: re-score against one reference before comparing."
        )
    if "data.items_sha256" in names:
        warnings.append("Measured on different item bytes.")
    if metric in SPEED_KEYS or "latency" in metric:
        if any(n.startswith("deployment.") for n in names):
            warnings.append(
                f"{metric} compared across deployments (where the model ran): the difference may be the "
                "machine's or the server's, not the arm's."
            )
        elif any(n.startswith("machine.") for n in names):
            warnings.append(
                f"{metric} measured from different runners: a model called over the network includes each "
                "runner's network time, and one run in process includes its machine."
            )
    return {"fields": len(keys), "differ": differ, "warnings": warnings}


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
    alone = params.get("dataset", [""])[0] if not arms and not LIMITS["hosts"] else ""
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
    public = bool(LIMITS["hosts"])
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
    if callable(src) and not LIMITS["hosts"]:
        out["source"] = src(dataset, it)
    # Every label the item has (RFC-023), and which output is production's recorded one: the local inspector only.
    lab = getattr(A, "item_labels", None)
    if callable(lab) and not LIMITS["hosts"]:
        out["labels"] = lab(dataset, it)
    out["recorded"] = {a: rec for a in arms if (rec := A.describe(A.arms_of(a)[0]).get("recorded"))}
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
    """The sheet as a download (RFC-023): the CSV `evh inspect --sheet --csv` writes, built in memory by the same
    code, so the page still writes nothing. The local inspector only: a sheet carries item text and outputs."""
    if LIMITS["hosts"]:
        return 403, b"the sheet shows item text and outputs: not served publicly", "text/plain; charset=utf-8"
    from evaluation_harness import _sheet  # noqa: PLC0415
    from evaluation_harness._sheets import write_csv  # noqa: PLC0415

    params = parse_qs(query)
    fill = params.get("fill", [""])[0] or None
    if fill not in (None, "label"):
        return (
            400,
            b"fill=label (a blind fill needs its key written beside the sheet: evh inspect --sheet --csv)",
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
    `evh inspect --sheet --dataset-id D` in the browser. The local inspector only: it carries outputs and labels."""
    if LIMITS["hosts"]:
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
            {"token": a["token"], "config_id": a["config_id"], "scores": a["scores"]} for a in model["arms"]
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


#: Set by main(): the public mode's limits. max_arms applies locally too (a URL is not a query).
LIMITS: dict = {"max_arms": 40, "rate": 0, "hosts": (), "proxy_hosts": ()}
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
    """Forget every answer, and the scores and arms they were made from: after the data page writes or deletes, and
    after a rebuild (the arms are the catalog's), so an answer never outlives what it was made from."""
    with _CACHE_LOCK:
        _CACHE.clear()
        _cache_size[0] = 0
    _scores.cache_clear()
    _known.cache_clear()


def answer(path: str, query: str) -> tuple:
    """(status, the JSON body as bytes) for one API request; every answer cached by its exact
    question until the data page changes the data or the catalog is rebuilt (`cache_clear`); a run made by another
    process shows after a restart."""
    if len(query) > MAX_QUERY:
        return 400, json.dumps({"error": f"the question is over {MAX_QUERY} characters"}).encode()
    key = f"{path}?{'&'.join(sorted(query.split('&')))}"
    with _CACHE_LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
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
    # Only answers are kept: a refusal (4xx) costs nothing to repeat, and keeping it let distinct
    # junk questions fill the cache by their keys (an independent review, 2026-10-29).
    if code == 200 and len(data) <= _CACHE_BYTES // 4:
        with _CACHE_LOCK:
            if key not in _CACHE:
                _CACHE[key] = (code, data)
                _cache_size[0] += len(data)
            while _CACHE and (len(_CACHE) > _CACHE_MAX or _cache_size[0] > _CACHE_BYTES):
                _cache_size[0] -= len(_CACHE.popitem(last=False)[1][1])
    return code, data


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
    """The URL prefixes readable over HTTP: the built catalog, the data tree and any directory
    the adapter names in `served_dirs` (a project whose pages link its reports), all under the
    project root (the server's document root)."""
    out = []
    for p in (build_dir, data_dir, *also):
        try:
            out.append("/" + p.resolve().relative_to(ROOT.resolve()).as_posix().strip("/") + "/")
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


#: The API's endpoints. Anything else under /api/ is 404: it is not a way into the files.
API_ROUTES = ("/api/health", "/api/compare", "/api/item", "/api/sheet")
#: The header every API call that is not a read must carry: a page from another origin cannot send it without a CORS
#: preflight, which this server never grants (ADR-0027).
DATA_HEADER = "X-EVH-Data"
#: The API's token (RFC-026), made when a local server starts; empty: the API answers nothing.
API_TOKEN: list[str] = []
API_COOKIE = "evh_token"
API_MAX_BODY = 64 * 1024
#: A refusal of the model's, as an HTTP status.
MODEL_STATUS = {
    "not-found": 404,
    "bad-argument": 400,
    "invalid-file": 422,
    "would-overwrite": 409,
    "not-allowed": 409,
    "old-format": 409,
    "mismatch": 409,
}
API_MAX_JOB_BODY = 70 * 1024 * 1024  # 50 MB of files, base64 (RFC-026: owner, 2026-11-08)


def api_read(command: str, arguments: Any) -> tuple[int, dict]:
    """POST /api/v1/read/<command>: the read command run as the MCP server runs a tool call, its envelope back (or
    its text, for the read commands with no --json yet)."""
    from evaluation_harness import _api  # noqa: PLC0415
    from evaluation_harness import mcp_server as ms  # noqa: PLC0415

    try:
        reg = _api.registry().get(command)
        if reg is None or reg["served"] != "read":
            raise _api.Refused(
                f"{command}: not a read command the API serves (a job: POST /api/v1/jobs)", 404
            )
        checked = _api.checked_args(command, arguments)
        argv = ms.argv_of(ms.parser_of(command), checked)
    except _api.Refused as exc:
        return exc.status, {"error": str(exc)}
    except ValueError as exc:
        return 400, {"error": str(exc)}
    code, out, err = ms.run_command(ROOT, command, argv)
    if code != 0:
        lines = [ln for ln in (err or out).splitlines() if ln.strip()]
        msg = next((ln for ln in reversed(lines) if ln.startswith("ERROR")), lines[-1] if lines else "")
        return (400 if code in (1, 2) else 500), {"error": msg, "exit": code}
    if command in ms.JSON:
        try:
            return 200, json.loads(out)
        except ValueError:
            return 500, {"error": f"{command} --json printed no JSON"}
    from evaluation_harness._version import __version__  # noqa: PLC0415

    return 200, {"command": command, "version": __version__, "text": out}


def api_estimate(command: str, arguments: Any) -> tuple[int, dict]:
    """POST /api/v1/estimate: a job command's own --dry-run, run now as a read (it calls nothing and writes nothing),
    and what it printed: what the job would do and, for a command that spends, cost (RFC-026 step 5)."""
    from evaluation_harness import _api  # noqa: PLC0415
    from evaluation_harness import mcp_server as ms  # noqa: PLC0415

    try:
        reg = _api.registry().get(command)
        if reg is None or reg["served"] != "job":
            raise _api.Refused(f"{command}: not a job command the API serves", 404)
        parser = ms.parser_of(command)
        if not any("--dry-run" in a.option_strings for a in parser._actions):
            raise _api.Refused(
                f"{command} has no --dry-run: there is nothing to estimate (a spending job shows its cap)",
                404,
            )
        checked = _api.checked_args(command, {k: v for k, v in (arguments or {}).items() if k != "dry-run"})
        argv = [*ms.argv_of(parser, checked), "--dry-run"]
    except _api.Refused as exc:
        return exc.status, {"error": str(exc)}
    except (ValueError, AttributeError) as exc:
        return 400, {"error": str(exc)}
    code, out, err = ms.run_command(ROOT, command, argv)
    from evaluation_harness._version import __version__  # noqa: PLC0415

    return (200 if code == 0 else 400), {
        "command": command,
        "version": __version__,
        "exit": code,
        "text": out + err,
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
    if p.startswith(
        "/api/v1/"
    ):  # RFC-026: this machine's only, never behind a proxy or public (owner, 2026-11-09)
        return 404 if LIMITS["hosts"] or LIMITS.get("proxy_hosts") or not API_TOKEN else 0
    if p.startswith("/api/"):
        return 0 if p in API_ROUTES else 404
    prefix = next((x for x in prefixes if p.startswith(x)), None)
    if prefix is None:
        return 404
    if any(seg.startswith(".") for seg in p[len(prefix) :].split("/")):
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


def _route(path: str) -> str:
    """A request's route for the hooks: the API endpoint, a hook's own path, "/api/other" for any
    other /api/ path (one name, however many paths are asked: a route is a metric series), or
    "static"."""
    if path in API_ROUTES or path in _hook_routes():
        return path
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
        """Serve the request, then tell the hooks how it went; on an unhandled error answer 500
        and tell them that too (without hooks the error propagates as before)."""
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
            serve()
        except Exception as exc:
            if HOOKS is None:
                raise
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
        if urlparse(self.path).path in ("", "/") and self.prefixes:
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
        from evaluation_harness import _api  # noqa: PLC0415

        url = urlparse(self.path)
        if self._refuse():
            return
        port = int(self.server.server_address[1])  # type: ignore[index]  # an AF_INET (host, port)
        origin = self.headers.get("Origin")
        if origin is not None and origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            return self._json(403, {"error": "a call from another origin is refused"}, cache=False)
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
        if method == "GET" and url.path == "/api/v1/commands":
            return self._json(200, {"commands": _api.registry()}, cache=False)
        if method == "POST" and url.path.startswith("/api/v1/read/"):
            n = int(self.headers.get("Content-Length") or 0)
            if n > API_MAX_BODY:
                return self._json(
                    413, {"error": f"a read call is at most {API_MAX_BODY:,} bytes"}, cache=False
                )
            try:
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            except ValueError:
                return self._json(400, {"error": 'the body is a JSON object: {"args": {...}}'}, cache=False)
            args = body.get("args", {}) if isinstance(body, dict) else None
            code, answer_body = api_read(url.path[len("/api/v1/read/") :], args)
            return self._json(code, answer_body, cache=False)
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
                    400, {"error": 'the body is a JSON object: {"command": ..., "args": {...}}'}, cache=False
                )
            if not isinstance(body, dict):
                return self._json(400, {"error": "the body is a JSON object"}, cache=False)
            code, answer_body = api_estimate(str(body.get("command") or ""), body.get("args", {}))
            return self._json(code, answer_body, cache=False)
        if self._model_route(method, url):
            return None
        if self.headers.get(DATA_HEADER) != "1":
            return self._json(
                403, {"error": f"a call that is not a read needs the {DATA_HEADER}: 1 header"}, cache=False
            )
        return self._json(404, {"error": f"no API route {method} {url.path}"}, cache=False)

    def _model_route(self, method: str, url) -> bool:
        """The model's resources (RFC-032): the operation whose method and route match the path, run in this process.
        A read takes its inputs from the query; a write needs the data header, its inputs as a JSON object and `by`
        (who acted, RFC-027; an agent names `for`, the person it acts for). None when no operation's route matches."""
        import jsonschema  # noqa: PLC0415
        from evaluation_harness import ops  # noqa: PLC0415
        from evaluation_harness._version import __version__  # noqa: PLC0415
        from evaluation_harness.model.entity import Problem  # noqa: PLC0415

        def say(code: int, body: dict) -> bool:
            self._json(code, body, cache=False)
            return True

        parts = url.path[len("/api/v1") :].strip("/").split("/")
        for op in ops.OPS.values():
            want = op.route.strip("/").split("/")
            if op.method != method or len(want) != len(parts):
                continue
            if any(w != p for w, p in zip(want, parts, strict=True) if not w.startswith("{")):
                continue
            params = {w[1:-1]: p for w, p in zip(want, parts, strict=True) if w.startswith("{")}
            inputs: dict = {}
            if op.kind == "read":
                q = parse_qs(url.query)
                inputs = {k: v[0] for k, v in q.items() if k in op.inputs}
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
                jsonschema.validate({k: v for k, v in inputs.items() if k != "by"}, op.schema())
            except jsonschema.ValidationError as exc:
                return say(400, {"error": f"{op.name}: {exc.message}"})
            try:
                result = op.call(**params, **inputs)
            except Problem as exc:
                return say(
                    MODEL_STATUS.get(exc.kind, 400),
                    {"error": str(exc), "kind": exc.kind, "problems": exc.problems},
                )
            return say(200, {"command": op.name, "version": __version__, "result": result})
        return False

    def _jobs_route(self, method: str, url) -> None:
        """The jobs (RFC-026 step 3): list, read, follow the log, fetch an artifact (GET); start, stop, resume (POST,
        with the data header)."""
        from evaluation_harness import _api, _jobs  # noqa: PLC0415

        parts = url.path[len("/api/v1/jobs") :].strip("/").split("/") if url.path != "/api/v1/jobs" else []
        q = parse_qs(url.query)
        try:
            if method == "GET":
                if not parts:
                    state = (q.get("state") or [None])[0]
                    return self._json(200, {"jobs": _jobs.list_jobs(state)}, cache=False)
                job_id = parts[0]
                if len(parts) == 1:
                    return self._json(200, _jobs.read(job_id), cache=False)
                if parts[1:] == ["log"]:
                    data, nxt = _jobs.log_from(job_id, int((q.get("from") or ["0"])[0]))
                    return self._json(200, {"log": data.decode("utf-8", "replace"), "next": nxt}, cache=False)
                if len(parts) == 3 and parts[1] == "files":
                    f = _jobs.job_dir(job_id) / _api._safe_name(parts[2])
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
                j = _api.start_job(
                    str(body.get("command") or ""), body.get("args", {}), body.get("by"), body.get("reason"),
                    body.get("max_cost_usd"), body.get("for"),
                )  # fmt: skip
                return self._json(202, j, cache=False)
            if len(parts) == 2 and parts[1] == "stop":
                return self._json(200, _jobs.stop(parts[0]), cache=False)
            if len(parts) == 2 and parts[1] == "resume":
                return self._json(202, _api.resume_job(parts[0]), cache=False)
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
        """Handle HEAD requests with access checks."""
        if not self._refuse():
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
            return self._json(200, {"ok": True})
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
        if self._from_store(url.path):
            return
        super().do_GET()

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
        origin (advisor review, 2026-11-06). sandbox gives it an origin of its own; nosniff keeps its type."""
        prefix = _data_url_prefix()
        if prefix and urlparse(self.path).path.startswith(prefix):
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "sandbox")
        super().end_headers()

    def _json(self, code: int, body, cache: bool = True) -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if code >= 400 or not cache else "public, max-age=300")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        """Log API requests only; suppress static file serving noise."""
        if args and "/api/" in str(args[0]):
            super().log_message(fmt, *args)


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
        "unlike --public; the data page's writes stay this machine's own",
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
    args = ap.parse_args()
    if args.public and args.behind_proxy:
        die("--public and --behind-proxy are two deployments: one at a time", "bad-argument")
    if args.port is None:
        from evaluation_harness._common import project_port  # noqa: PLC0415

        args.port = 8765 if args.public else project_port("catalog")
    global HOOKS
    HOOKS = load_hooks(args.hooks) if args.hooks else None
    set_adapter(load_catalog_adapter(args.adapter))
    LIMITS["max_arms"] = args.max_arms
    if args.public:
        LIMITS["hosts"] = tuple(h.strip() for h in args.public.split(",") if h.strip())
        LIMITS["rate"] = args.rate
        LIMITS["client_header"] = args.client_header
        LIMITS["publish"] = tuple(x.strip() for x in args.publish.split(",") if x.strip())
        bad = set(LIMITS["publish"]) - {"outputs", "references"}
        if bad:
            die(f"--publish takes outputs and/or references, not {', '.join(sorted(bad))}", "bad-argument")
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
        if not _store.is_file(args.build_dir / "index.html"):
            die(f"no catalog at {args.build_dir}: run `evh catalog` first", "not-found")
        Handler.prefixes = served(args.build_dir, A.data_dir, tuple(getattr(A, "served_dirs", ())))
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
        print(f"  the project {ROOT}, on a port of its own", flush=True)
        print("  it reads the runs once: restart it to see runs made after it started", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
