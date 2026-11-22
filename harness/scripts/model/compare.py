"""The comparison of arms (RFC-032 step 8): the paired test of every arm against a baseline on one metric, the
yardstick chosen, what could not be compared said in words. The inspector's `/api/compare`, `evh comparison-show`, a round's
evidence (model/rounds) and the API's comparison all read it; catalog_serve answers the route by calling it.

It reads one adapter, set by `set_adapter` (the server's, or the one a view builds): the arms, their scores and what
the project says of them. `LIMITS` are the public mode's limits, set by the server."""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

from evaluation_harness import _fields, stats
from evaluation_harness._common import SPEED_KEYS
from evaluation_harness.catalog_adapter import Adapter, item_fields

#: Every comparison ends in one of these, so a page can always say what it shows and why.
STATES = ("compared", "average only", "no shared metric", "not scorable")

A: Adapter = None  # type: ignore[assignment]  # set by set_adapter()
#: Set by the server's main(): the public mode's limits. max_arms applies locally too (a URL is not a query).
LIMITS: dict = {"max_arms": 40, "rate": 0, "hosts": (), "proxy_hosts": ()}


def public() -> bool:
    """Whether this comparison is a public server's: the inspector's --public, or an MCP call made for a public server."""
    from evaluation_harness import _visibility  # noqa: PLC0415

    return bool(LIMITS["hosts"]) or _visibility.public_env()


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

    # The compared arms' own primary metric before any count, among the metrics every compared arm scores: with no
    # primary in the key, two metrics every arm records tied and the name decided (fleet, 2026-11-18: `actionable`
    # shown before the arms' `oracle_pass`); preferred whatever its count, a primary only one arm scores won over a
    # metric all share, and left nothing to test (review, 2026-11-19).
    primaries = Counter(p for a in arms if (p := (A.describe(a) or {}).get("primary")))
    everyone = len(per_arm)

    return min(
        pool,
        key=lambda k: (
            k in A.shape_metrics,
            A.is_neutral(k, dataset or None),
            _reference_free(k),  # the bill and the clock: only when nothing is scored
            k not in mine,
            mismatch(k),
            -(primaries[k.split(" vs ")[0]] if counts[k] == everyone else 0),
            -counts[k],
            -recorded[k],
            next((i for i, p in enumerate(preferred) if k.split(" vs ")[0] == p), 99),
            k,
        ),
    )


def _primary_not_read(arms: list, metric: str, per_arm: dict) -> str | None:
    """When no metric was named and the compared arms' primary metric is not scored per item for every one of them as
    they are read, the default is another metric: said, with the arms that lack it, where another reading of the same
    runs scores it (`--label`, when the adapter says what its readings are: `read_as`), and the arms it is scored for
    nowhere (fleet, 2026-11-18: bugfix arms read as plain runs carry `oracle_pass` only in their `silver` reading, and
    were compared on `actionable` in silence). A metric is its name before " vs " (`oracle_pass vs gold`)."""
    primaries = Counter(p for a in arms if (p := (A.describe(a) or {}).get("primary")))
    if not primaries:
        return None
    primary = primaries.most_common(1)[0][0]

    def base(k: str) -> str:
        return k.split(" vs ")[0]

    if base(metric) == primary:
        return None
    lacking = [a for a in arms if not any(base(k) == primary for k in per_arm.get(a, {}))]
    if not lacking:
        return None
    read_as = getattr(A, "read_as", None)
    where: dict[str, list[str]] = {}
    nowhere = []
    for a in lacking:
        found = []
        if callable(
            read_as
        ):  # an arm id is `<reading>/<dataset>/<system>`; the reading's label is what --label takes
            rest = a.split("/", 1)[-1]
            found = [
                read_as(b) or b.split("/", 1)[0]
                for b in A.arms()
                if b != a and b.split("/", 1)[-1] == rest and any(base(k) == primary for k in A.scores(b))
            ]
        for lb in found:
            where.setdefault(lb, []).append(_label(a))
        if not found:
            nowhere.append(_label(a))
    said = (
        f"The arms' primary metric, {primary}, has no score per {A.item_word} for "
        f"{', '.join(_label(a) for a in lacking)} as read, so it cannot be tested across them; "
        + (f"compared on {metric} instead." if metric else "there is no other metric to compare them on.")
    )
    said += "".join(f" It is scored for {', '.join(xs)} under --label {lb}." for lb, xs in where.items())
    if nowhere and callable(read_as):
        said += (
            f" It is not scored for {', '.join(nowhere)} in any reading: no reference scores it (evh rescore "
            "scores the runs against one that does)."
        )
    return said


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
    if public():
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
            return None, f"no field {name!r} to filter by" + (" here" if public() else "")
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

    # The adapter's goals, so the data directory it reads is the one asked (a deployment's copy of the project's).
    fn = getattr(A, "goals", None)
    goals = fn() if callable(fn) else list(load_goals().values())
    named = {goal_cluster(g, dataset) for g in goals} - {None}
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
        else:
            instead = _primary_not_read(arms, metric, per_arm)
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
