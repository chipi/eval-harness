"""The catalog's views as resources (RFC-032 step 8): `evh overview-show`, `arm-list`, `dataset-arm-list`, `arm-show`,
`metric-list`, `metric-show`, `activity-show`, `comparison-show` and `label-coverage-show`, and the resources under
/api/v1/overview, /arms, /datasets/{dataset}/arms, /metrics, /activity, /compare and /datasets/{dataset}/label-coverage.
Each reads what the command of the same name reads (model/overview_views, arm_views, metric_views, activity_views,
compare, label_coverage.coverage) and says it in the words the command prints: the API gives `evh <op> --json`. `evh
overview`, `arms`, `metrics`, `activity`, `inspect` and `label-coverage` stay as they are; they are the same views read
by a process (RFC-026) until step 9.

A read's inputs reach the server as the query's strings, so every input here is a string: a flag is `1`, a period one of
`catalog_periods.PERIODS`."""

from __future__ import annotations

import contextlib
import io
import re
from pathlib import Path
from typing import Any

from evaluation_harness.catalog_periods import DEFAULT, PERIODS
from evaluation_harness.ops import legacy
from evaluation_harness.ops.registry import Op

_V = "evaluation_harness.ops.views"
_PERIOD: dict[str, Any] = {
    "type": "string",
    "enum": [k for k, *_ in PERIODS],
    "description": "counted from today: " + ", ".join(f"{k} ({label})" for k, label, _ in PERIODS),
}
_DATASET = {"type": "string", "description": "only this dataset's"}
_ARMS = {
    "where": {
        "type": "string",
        "enum": ["local", "hosted"],
        "description": "only arms run locally, or only hosted ones",
    },
    "tier": {"type": "string", "description": "only arms of this price tier (free, small, mid, large, ...)"},
    "weights": {
        "type": "string",
        "enum": ["open", "proprietary"],
        "description": "only arms whose model's weights are open, or proprietary (the model records)",
    },
    "quality": {
        "type": "string",
        "enum": ["contender", "below"],
        "description": "only arms a goal counts as contenders beside its quality leader, or only those it ranks below the leader",
    },
    "systems": {
        "type": "string",
        "enum": ["1"],
        "description": "1: also one row per system across the datasets it ran on, with its rank on each goal",
    },
    "period": {**_PERIOD, "description": "add each arm's numbers in a period, " + _PERIOD["description"]},
}
_COMPARE = {
    "runs": {
        "type": "string",
        "description": "the arms compared, comma-separated: arm ids, or system ids (looked up under label)",
    },
    "round": {
        "type": "string",
        "description": "instead of runs: the arms in play in this round of a goal (rN; ADR-0004)",
    },
    "goal": {"type": "string", "description": "the goal the round belongs to, when several goals have one"},
    "label": {
        "type": "string",
        "description": 'the label system ids are looked up under: "", silver, repeats, "rescored cd35dc1f", judged/<scorer> (default: the plain arm); `evh runs-list` shows what is there',
    },
    "baseline": {
        "type": "string",
        "description": "the arm the others are tested against (default: a round's leader, else the first)",
    },
    "metric": {"type": "string", "description": "the metric compared (default: the arms' primary metric)"},
    "where": {
        "type": "array",
        "items": {"type": "string"},
        "description": "FIELD:VALUE or FIELD:LO..HI, keep only matching items",
    },
    "disagree": {
        "type": "string",
        "enum": ["1"],
        "description": "1: only the items where the arms decided differently from the baseline",
    },
    "by": {"type": "string", "description": "break the comparison down by a choice or yes/no field"},
    "rescore": {
        "type": "string",
        "enum": ["0", "1"],
        "description": "0: read only what is on record, as the inspector's re-score box unticked",
    },
    "family": {
        "type": "string",
        "description": "the number of comparisons Holm corrects across (default: the arms compared)",
    },
    "threshold": {"type": "string", "description": "the level the paired test is held to (default: 0.05)"},
    "cluster": {
        "type": "string",
        "description": "a field whose equal values count as one item in every test",
    },
    "analysis": {
        "type": "boolean",
        "description": "also the analysis charts as numbers: the spread per arm, the difference from the baseline, and with x each arm's mean on a second metric",
    },
    "x": {"type": "string", "description": "with analysis: each arm's mean on this metric too (the scatter)"},
    "series": {
        "type": "boolean",
        "description": "also each arm's score on every item and the other metrics' per item (what the inspector draws its charts from): large, a megabyte for thirty arms",
    },
}
_COVERAGE = {
    "items": {
        "type": "boolean",
        "description": "the command also prints every item with its class (and maturing date): the answer always carries them",
    },
    "capture": {"type": "string", "description": "the capture whose records hold the outcomes"},
    "map": {
        "type": "string",
        "description": "the rules: a YAML file inside the project, the mapping label-from-capture reads",
    },
    "from_set": {
        "type": "string",
        "description": "also say what a relabel of this earlier label set would add and change today",
    },
    "outcomes": legacy.OUTCOMES,
}

OPS = (
    Op("overview-show", "read", "the catalog's home page: the period's tiles with trends, each goal's decision at a glance, runs per day, spend, what each dataset has, what was recorded",
       "GET", "/overview", f"{_V}:overview", f"{_V}:say_overview", inputs={"period": _PERIOD}),
    Op("arm-list", "read", "every arm: how it was measured, its model and provider, its roles under the goals, its cost and speed; with systems, one row per system across the datasets it ran on",
       "GET", "/arms", f"{_V}:list_arms", f"{_V}:say_arms", inputs={"dataset": _DATASET, **_ARMS}),
    Op("dataset-arm-list", "read", "a dataset's arms, as arm-list gives them", "GET", "/datasets/{dataset}/arms",
       f"{_V}:list_dataset_arms", f"{_V}:say_arms", inputs=_ARMS),
    Op("arm-show", "read", "one arm in full: where it ran, what it was scored against, its headline, cost and speed, metrics, runs, config and conditions, the same system scored other ways, its rounds and notes",
       "GET", "/arms/{label}/{dataset}/{system}", f"{_V}:show_arm", f"{_V}:say_arm"),
    Op("metric-list", "read", "what each metric measures: which way is better, where it is recorded, the goals that decide on it or weigh it",
       "GET", "/metrics", f"{_V}:list_metrics", f"{_V}:say_metrics", inputs={"dataset": _DATASET, "period": _PERIOD}),
    Op("metric-show", "read", "one metric in full: how it is computed, its kind, and the arms recording it on each dataset, best first",
       "GET", "/metrics/{metric}", f"{_V}:show_metric", f"{_V}:say_metric", inputs={"dataset": _DATASET}),
    Op("activity-show", "read", "runs, spend and tokens in a period by dataset, by arm and by kind, against the period before",
       "GET", "/activity", f"{_V}:activity", f"{_V}:say_activity",
       inputs={"period": _PERIOD, "arms": {"type": "string", "description": "how many arms to list, what moved most first (default 20)"}}),
    Op("comparison-show", "read", "arms compared on one metric: each tested against the baseline with the paired test, Holm across them, the conditions that differ and, with by, a breakdown; the inspector's /api/compare",
       "GET", "/compare", f"{_V}:comparison", f"{_V}:say_comparison", printer=f"{_V}:print_comparison", inputs=_COMPARE),
    Op("label-coverage-show", "read", "how far an outcome rule set labels a dataset now: each item labelled, skipped, not yet mature (and when), unmatched or not in the capture; per rule, what it takes now and when mature",
       "GET", "/datasets/{dataset}/label-coverage", f"{_V}:label_coverage", f"{_V}:say_label_coverage", printer=f"{_V}:print_label_coverage",
       inputs=_COVERAGE, required=("capture", "map"),
       public_dropped="it reads a rules file by path and the captures, which are this machine's"),
)  # fmt: skip


@contextlib.contextmanager
def _refusing():
    """What the commands' helpers refuse with `die` (an exit that names the kind), as the model's own refusal: the
    server answers it, the command prints it as it always did."""
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    try:
        yield
    except SystemExit as exc:
        m = re.fullmatch(r"ERROR \(([a-z-]+)\): (.*)", str(exc.code or ""), re.S)
        if m is None:
            raise
        raise Problem(m.group(2), m.group(1)) from None


def _choice(name: str, value: str | None, allowed: tuple[str, ...]) -> str | None:
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    if value in (None, "") or value in allowed:
        return value or None
    raise Problem(f"{name}: one of {', '.join(allowed)}; got {value!r}", "bad-argument")


def _flag(name: str, value: str | None) -> bool:
    return _choice(name, value, ("1",)) == "1"


def _period(value: str | None) -> str | None:
    return _choice("period", value, tuple(k for k, *_ in PERIODS))


def _adapter() -> Any:
    """The adapter the server serves when one is set (its scores read once), else the project's catalog adapter."""
    from evaluation_harness import catalog_serve  # noqa: PLC0415
    from evaluation_harness.catalog_adapter import shared_adapter  # noqa: PLC0415

    return getattr(catalog_serve, "A", None) or shared_adapter()


def _view() -> tuple[Any, dict]:
    """The adapter and what the catalog collects from it: the arms by dataset."""
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415

    A = _adapter()
    return A, cb.collect(A)


def _say(printer: str, r: dict[str, Any]) -> str:
    from evaluation_harness import catalog_views  # noqa: PLC0415

    return catalog_views.say(getattr(catalog_views, printer), r)


def overview(period: str | None = None) -> dict[str, Any]:
    """The home page for the period (default the last 14 days)."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import overview_views  # noqa: PLC0415

    A, by_ds = _view()
    return _jsonout.plain(overview_views.overview(A, by_ds, (_period(period) or DEFAULT)))


def say_overview(r: dict[str, Any]) -> str:
    """overview-show's answer as text: what `evh overview-show` prints."""
    return _say("print_overview", r)


def _arms(dataset, where, tier, weights, quality, systems, period, known: bool = False) -> dict[str, Any]:
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import arm_views  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    A, by_ds = _view()
    fn = getattr(A, "datasets", None)
    if known and dataset not in {*by_ds, *(fn() if callable(fn) else [])}:
        raise Problem(f"no dataset {dataset!r} in this project", "not-found")
    return _jsonout.plain(
        arm_views.arms(
            A,
            by_ds,
            dataset or None,
            _choice("where", where, ("local", "hosted")),
            tier or None,
            _choice("weights", weights, ("open", "proprietary")),
            _choice("quality", quality, ("contender", "below")),
            _flag("systems", systems),
            _period(period),
        )
    )


def list_arms(
    dataset: str | None = None,
    where: str | None = None,
    tier: str | None = None,
    weights: str | None = None,
    quality: str | None = None,
    systems: str | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    """Every arm that fits the filters, and with `systems` one row per system."""
    return _arms(dataset, where, tier, weights, quality, systems, period)


def list_dataset_arms(
    dataset: str,
    where: str | None = None,
    tier: str | None = None,
    weights: str | None = None,
    quality: str | None = None,
    systems: str | None = None,
    period: str | None = None,
) -> dict[str, Any]:
    """The dataset's arms: arm-list for one dataset, which has to exist (a dataset frozen or with an arm)."""
    return _arms(dataset, where, tier, weights, quality, systems, period, known=True)


def say_arms(r: dict[str, Any]) -> str:
    """arm-list's answer as text: what `evh arm-list` prints, the arms grouped by dataset as the arms page groups them."""
    return _say("print_arms", r)


def show_arm(label: str, dataset: str, system: str) -> dict[str, Any]:
    """The arm `<label>/<dataset>/<system>` in full."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import arm_views  # noqa: PLC0415

    A, by_ds = _view()
    return _jsonout.plain(arm_views.arm(A, by_ds, f"{label}/{dataset}/{system}"))


def say_arm(r: dict[str, Any]) -> str:
    """arm-show's answer as text: what `evh arm-show` prints."""
    return _say("print_arm", r)


def list_metrics(dataset: str | None = None, period: str | None = None) -> dict[str, Any]:
    """Every metric recorded (on the dataset, when given)."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import metric_views  # noqa: PLC0415

    A, by_ds = _view()
    return _jsonout.plain(metric_views.metrics(A, by_ds, dataset or None, _period(period)))


def say_metrics(r: dict[str, Any]) -> str:
    """metric-list's answer as text: what `evh metric-list` prints."""
    return _say("print_metrics", r)


def show_metric(metric: str, dataset: str | None = None) -> dict[str, Any]:
    """One metric in full, its arms on the dataset when one is given."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import metric_views  # noqa: PLC0415

    A, by_ds = _view()
    return _jsonout.plain(metric_views.metric(A, by_ds, metric, dataset or None))


def say_metric(r: dict[str, Any]) -> str:
    """metric-show's answer as text: what `evh metric-list --metric` prints."""
    return _say("print_metric", r)


def activity(period: str | None = None, arms: str | None = None) -> dict[str, Any]:
    """The period's runs, spend and tokens (default the last 14 days), the `arms` that moved most (default 20)."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import activity_views  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    if arms not in (None, "") and not str(arms).isdigit():
        raise Problem(f"arms: a number; got {arms!r}", "bad-argument")
    A, by_ds = _view()
    return _jsonout.plain(
        activity_views.activity(A, by_ds, (_period(period) or DEFAULT), int(arms) if arms else 20)
    )


def say_activity(r: dict[str, Any]) -> str:
    """activity-show's answer as text: what `evh activity-show` prints."""
    return _say("print_activity", r)


def comparison(series: bool = False, **inputs: Any) -> dict[str, Any]:
    """The arms compared, as the inspector's /api/compare answers (the paired test of each against the baseline), without
    the score of every arm on every item unless `series` asks for them (see `compared`)."""
    out = compared(**inputs)
    if not series:
        import statistics  # noqa: PLC0415

        base = list((out.get("series") or {}).get(out.get("baseline"), {}).values())
        out["baseline_mean"] = (
            statistics.fmean(base) if base else None
        )  # what the text says beside the verdicts
        for k in ("series", "shape"):
            out.pop(k, None)
    return out


def compared(
    runs: str | None = None,
    round: str | None = None,
    goal: str | None = None,
    label: str | None = None,
    baseline: str | None = None,
    metric: str | None = None,
    where: list[str] | None = None,
    disagree: str | None = None,
    by: str | None = None,
    rescore: str | None = None,
    family: str | None = None,
    threshold: str | None = None,
    cluster: str | None = None,
    analysis: bool = False,
    x: str | None = None,
) -> dict[str, Any]:
    """The arms compared, whole: the arms named by `runs` (arm ids, or system ids read under `label`) or those in play in a
    `round`, whose leader is the baseline unless one is named; with `analysis`, the charts as numbers."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import arm_views, compare  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    A = _adapter()
    if compare.A is not A:
        compare.set_adapter(A)
    label = label or ""
    if bool(runs) == bool(round):
        raise Problem("one of runs or round names the arms compared", "bad-argument")
    notes: list[str] = []
    round_leader = None
    if round:
        from evaluation_harness._rounds import resolve  # noqa: PLC0415
        from evaluation_harness.model import rounds as model_rounds  # noqa: PLC0415
        from evaluation_harness.rounds import _goal  # noqa: PLC0415

        with _refusing():
            rnd = resolve(round, goal)
            known = set(A.arms())
            tokens = [a for a in model_rounds.arm_ids(rnd) if a in known]
            if not tokens:
                raise Problem(f"round {round} has no arms in play yet", "not-enough")
            # A round is read on its goal's measure, against its leader: defaulting to the first arm made an arm with no
            # score the baseline and fell back to cost_usd.
            prim = (_goal(rnd["goal"]).get("success_criteria") or {}).get("primary") or {}
            if not metric and prim.get("measure"):
                metric = prim["measure"]
            unscored = [a for a in tokens if not (A.scores(a).get(metric) or {}).get("values")]
            if unscored:
                notes.append(
                    f"no {metric} recorded for {', '.join(a.rsplit('/', 1)[-1] for a in unscored)}: left out of the comparison"
                )
                tokens = [t for t in tokens if t not in unscored]
                if not tokens:
                    raise Problem(f"no arm of round {round} records {metric} yet", "not-enough")
            round_leader = model_rounds.evidence(rnd["goal"], rnd, A).get("leader")
    else:
        tokens = [t.strip() for t in (runs or "").split(",") if t.strip()]
    arms = arm_views.arm_ids(A, tokens, label)
    base = (
        arm_views.arm_ids(A, [baseline], label)[0]
        if baseline
        else (round_leader if round_leader and round_leader in arms else arms[0])
    )
    given = {
        "runs": ",".join(arms),
        "baseline": base,
        "metric": metric,
        "disagree": _choice("disagree", disagree, ("1",)),
        "by": by,
        "rescore": _choice("rescore", rescore, ("0", "1")),
        "family": family,
        "threshold": threshold,
        "cluster": cluster,
    }
    params = {k: [v] for k, v in given.items() if v not in (None, "")}
    if where:
        params["where"] = list(where)
    got = compare.compare(params)
    if got.get("error"):
        raise Problem(str(got["error"]), "bad-argument")
    names = {a["id"]: a["label"] for a in got.get("arms") or []} | {a: A.describe(a)["label"] for a in arms}
    leader_is_baseline = False
    if round_leader and not baseline and got["baseline"] == round_leader:
        from evaluation_harness.model import runs as model_runs  # noqa: PLC0415
        from evaluation_harness.rounds import _dirs  # noqa: PLC0415

        # The round's leader stands in as the baseline unless the round started from a promoted one.
        leader_is_baseline = not any(
            model_runs.run_of(d).name == rnd.get("baseline") for d in _dirs(A, round_leader)
        )
    out = {
        **got,
        "item_word": A.item_word,
        "labels": names,
        "notes": notes,
        "round": {"id": round, "leader": round_leader, "baseline_is_leader": leader_is_baseline}
        if round
        else None,
        "by": by or "",
    }
    if analysis:
        out["analysis"] = compare_analysis(got, names, x)
    return _jsonout.plain(out)


def compare_analysis(d: dict[str, Any], names: dict[str, str], x: str | None) -> dict[str, Any]:
    """The inspector's analysis charts as numbers: each arm's spread over the items, each arm's per-item difference from the
    baseline, and each arm's mean on a second metric (`x`, else the first other metric the arms record per item)."""
    import statistics  # noqa: PLC0415

    def spread(vals: list[float]) -> dict[str, float]:
        v = sorted(vals)
        q = statistics.quantiles(v, n=4, method="inclusive") if len(v) > 1 else [v[0]] * 3
        return {"min": v[0], "p25": q[0], "median": q[1], "p75": q[2], "max": v[-1]}

    series = d.get("series") or {}
    base = series.get(d["baseline"], {})
    diffs = {a: [s[i] - base[i] for i in s if i in base] for a, s in series.items() if a != d["baseline"]}
    shape = d.get("shape") or {}
    xm = x or next(iter(shape), None)
    scatter = []
    if xm and xm in shape:
        for a, ys in series.items():
            pts = [(shape[xm].get(a, {})[i], y) for i, y in ys.items() if i in shape[xm].get(a, {})]
            if pts:
                scatter.append(
                    {
                        "arm": a,
                        "label": names.get(a, a),
                        "y": statistics.fmean(y for _, y in pts),
                        "x": statistics.fmean(v for v, _ in pts),
                        "n": len(pts),
                    }
                )
    return {
        "metric": d["metric"],
        "spread": [
            {
                "arm": a,
                "label": names.get(a, a),
                "mean": statistics.fmean(s.values()),
                **spread(list(s.values())),
            }
            for a, s in series.items()
            if s
        ],
        "difference": [
            {"arm": a, "label": names.get(a, a), "mean": statistics.fmean(v), **spread(v)}
            for a, v in diffs.items()
            if v
        ],
        "x": xm,
        "x_recorded": list(shape),
        "scatter": scatter,
    }


def say_comparison(r: dict[str, Any]) -> str:
    """comparison-show's answer as text: what `evh comparison-show` prints (the verdicts, the arms with only an average,
    the conditions that differ, with `by` the breakdown, with `analysis` the charts as numbers)."""
    from evaluation_harness import catalog_views  # noqa: PLC0415

    def show(d: dict[str, Any]) -> None:
        for w in [*(d.get("notes") or []), *(d.get("warnings") or [])]:
            print(f"NOTE: {w}")
        if d.get("state") == "not scorable":
            return
        what = " (the round's leader)" if (d.get("round") or {}).get("baseline_is_leader") else ""
        catalog_views.print_comparison(
            d,
            d["labels"],
            d["item_word"],
            what,
            d.get("by") or "",
            bool(d.get("analysis")),
            (d.get("analysis") or {}).get("x"),
        )

    return catalog_views.say(show, r)


def _project_file(path: str) -> Path:
    """A file inside the project: a read over the API names no file of the machine's beyond it."""
    from evaluation_harness import _common, _store  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    root = _common.project_root().resolve()
    p = (root / path).resolve()
    if not p.is_relative_to(root):
        raise Problem(f"map: {path!r} is outside the project; name a file inside it", "bad-argument")
    if not _store.is_file(p):
        raise Problem(f"map: no file {path}", "not-found")
    return p


def label_coverage(
    dataset: str,
    capture: str,
    map: str,
    from_set: str | None = None,
    items: bool = False,
    outcomes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The dataset's labels against the capture under the rules (`evh label-coverage-show`, nothing written); with
    `outcomes` the outcome read from other captures, joined to each decision."""
    from evaluation_harness import _jsonout, _outcome_join, _visibility  # noqa: PLC0415
    from evaluation_harness._outcome_rules import load_rules  # noqa: PLC0415
    from evaluation_harness.label_coverage import coverage  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    if _visibility.public_env():  # a public MCP server's call: the captures and the rules are this machine's
        raise Problem(
            "label coverage reads a rules file and the captures, which are this machine's", "not-allowed"
        )
    path = _project_file(map)
    with _refusing():
        cov = coverage(dataset, capture, load_rules(path), _outcome_join.joins_of(outcomes), from_set or None)
    return _jsonout.plain({**cov, "map": map})


def say_label_coverage(r: dict[str, Any]) -> str:
    """label-coverage-show's answer as text: what `evh label-coverage-show` prints, without the item list."""
    from evaluation_harness import _jsonout, label_coverage  # noqa: PLC0415

    buf = io.StringIO()
    with _jsonout.printing_to(buf):
        label_coverage.show(r, r["map"])
    return buf.getvalue().rstrip("\n")


def print_label_coverage(dataset: str, capture: str, map: str, items: bool = False, **rest: Any) -> None:
    """`evh label-coverage-show` on the terminal: the answer as `say_label_coverage` gives it, and with `items` every item
    with its class (and maturing date)."""
    from evaluation_harness import label_coverage as coverage_module  # noqa: PLC0415

    cov = label_coverage(dataset, capture, map, **rest)
    coverage_module.show(cov, cov["map"], items)


def print_comparison(**inputs: Any) -> None:
    """`evh comparison-show` on the terminal: the comparison whole (the analysis charts need each item's score), said as
    `say_comparison` says it."""
    inputs.pop("series", None)
    print(say_comparison(compared(**inputs)))
