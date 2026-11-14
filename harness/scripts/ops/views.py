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
import os
import re
from pathlib import Path
from typing import Any

from evaluation_harness.catalog_periods import DEFAULT, PERIODS
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
    "runs": {"type": "string", "description": "the arms compared, comma-separated arm ids"},
    "baseline": {
        "type": "string",
        "description": "the arm the others are tested against (default: a promoted baseline, else the first)",
    },
    "metric": {"type": "string", "description": "the metric compared (default: the arms' primary metric)"},
    "where": {"type": "string", "description": "FIELD:VALUE or FIELD:LO..HI, keep only matching items"},
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
}
_COVERAGE = {
    "capture": {"type": "string", "description": "the capture whose records hold the outcomes"},
    "map": {
        "type": "string",
        "description": "the rules: a YAML file inside the project, the mapping label-from-capture reads",
    },
    "from_set": {
        "type": "string",
        "description": "also say what a relabel of this earlier label set would add and change today",
    },
    "outcomes": {
        "type": "string",
        "description": "another capture holding the outcome (an outside system's records); needs join",
    },
    "outcomes_as": {
        "type": "string",
        "description": "the name the rules read the other capture's fields under (default: its id)",
    },
    "join": {
        "type": "string",
        "description": "ITEM_FIELD=RECORD_FIELD: what ties a decision to the other capture's record",
    },
    "within": {
        "type": "string",
        "description": "a window after the item's time, -1m,+15m: only records made in it match",
    },
    "identity": {
        "type": "string",
        "description": "ITEM_FIELD=RECORD_FIELD that must also agree: a reused id is gone, not another's outcome",
    },
    "gone_if_missing": {
        "type": "string",
        "enum": ["1"],
        "description": "1: an item whose key no record of the other capture carries is gone from the source",
    },
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
       "GET", "/compare", f"{_V}:comparison", f"{_V}:say_comparison", inputs=_COMPARE, required=("runs",)),
    Op("label-coverage-show", "read", "how far an outcome rule set labels a dataset now: each item labelled, skipped, not yet mature (and when), unmatched or not in the capture; per rule, what it takes now and when mature",
       "GET", "/datasets/{dataset}/label-coverage", f"{_V}:label_coverage", f"{_V}:say_label_coverage",
       inputs=_COVERAGE, required=("capture", "map")),
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
    from evaluation_harness.catalog_adapter import load_catalog_adapter, scores_once  # noqa: PLC0415

    return getattr(catalog_serve, "A", None) or scores_once(load_catalog_adapter(None))


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
    """overview-show's answer as text: what `evh overview` prints."""
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
    """arm-list's answer as text: what `evh arms` prints, the arms grouped by dataset as the arms page groups them."""
    return _say("print_arms", r)


def show_arm(label: str, dataset: str, system: str) -> dict[str, Any]:
    """The arm `<label>/<dataset>/<system>` in full."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import arm_views  # noqa: PLC0415

    A, by_ds = _view()
    return _jsonout.plain(arm_views.arm(A, by_ds, f"{label}/{dataset}/{system}"))


def say_arm(r: dict[str, Any]) -> str:
    """arm-show's answer as text: what `evh arms --arm` prints."""
    return _say("print_arm", r)


def list_metrics(dataset: str | None = None, period: str | None = None) -> dict[str, Any]:
    """Every metric recorded (on the dataset, when given)."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import metric_views  # noqa: PLC0415

    A, by_ds = _view()
    return _jsonout.plain(metric_views.metrics(A, by_ds, dataset or None, _period(period)))


def say_metrics(r: dict[str, Any]) -> str:
    """metric-list's answer as text: what `evh metrics` prints."""
    return _say("print_metrics", r)


def show_metric(metric: str, dataset: str | None = None) -> dict[str, Any]:
    """One metric in full, its arms on the dataset when one is given."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import metric_views  # noqa: PLC0415

    A, by_ds = _view()
    return _jsonout.plain(metric_views.metric(A, by_ds, metric, dataset or None))


def say_metric(r: dict[str, Any]) -> str:
    """metric-show's answer as text: what `evh metrics --metric` prints."""
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
    """activity-show's answer as text: what `evh activity` prints."""
    return _say("print_activity", r)


def comparison(
    runs: str,
    baseline: str | None = None,
    metric: str | None = None,
    where: str | None = None,
    disagree: str | None = None,
    by: str | None = None,
    rescore: str | None = None,
    family: str | None = None,
    threshold: str | None = None,
    cluster: str | None = None,
) -> dict[str, Any]:
    """The arms compared, as the inspector's /api/compare answers (the paired test of each against the baseline)."""
    from evaluation_harness import _jsonout  # noqa: PLC0415
    from evaluation_harness.model import compare  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    A = _adapter()
    if compare.A is not A:
        compare.set_adapter(A)
    if os.environ.get("EVH_PUBLIC"):  # a public MCP server's process: the inspector's public rules
        compare.LIMITS["hosts"] = ("public",)
    given = {
        "runs": runs,
        "baseline": baseline,
        "metric": metric,
        "where": where,
        "disagree": _choice("disagree", disagree, ("1",)),
        "by": by,
        "rescore": _choice("rescore", rescore, ("0", "1")),
        "family": family,
        "threshold": threshold,
        "cluster": cluster,
    }
    got = compare.compare({k: [v] for k, v in given.items() if v not in (None, "")})
    if got.get("error"):
        raise Problem(str(got["error"]), "bad-argument")
    return _jsonout.plain({**got, "item_word": A.item_word})


def say_comparison(r: dict[str, Any]) -> str:
    """comparison-show's answer as text: what `evh inspect --runs` prints."""
    return _say("print_compared", r)


def _project_file(path: str) -> Path:
    """A file inside the project: a read over the API names no file of the machine's beyond it."""
    from evaluation_harness import _common  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    root = _common.project_root().resolve()
    p = (root / path).resolve()
    if not p.is_relative_to(root):
        raise Problem(f"map: {path!r} is outside the project; name a file inside it", "bad-argument")
    return p


def label_coverage(
    dataset: str,
    capture: str,
    map: str,
    from_set: str | None = None,
    outcomes: str | None = None,
    outcomes_as: str | None = None,
    join: str | None = None,
    within: str | None = None,
    identity: str | None = None,
    gone_if_missing: str | None = None,
) -> dict[str, Any]:
    """The dataset's labels against the capture under the rules (`evh label-coverage`, nothing written); with
    `outcomes` the outcome read from another capture, joined to each decision."""
    from evaluation_harness import _jsonout, _outcome_join  # noqa: PLC0415
    from evaluation_harness._outcome_rules import load_rules  # noqa: PLC0415
    from evaluation_harness.label_coverage import coverage  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    if os.environ.get(
        "EVH_PUBLIC"
    ):  # a public MCP server's process: the captures and the rules are this machine's
        raise Problem(
            "label coverage reads a rules file and the captures, which are this machine's", "not-allowed"
        )
    if not outcomes and any((outcomes_as, join, within, identity, gone_if_missing)):
        raise Problem(
            "outcomes_as, join, within, identity and gone_if_missing belong to outcomes", "bad-argument"
        )
    path = _project_file(map)
    with _refusing():
        joins = (
            _outcome_join.Joins(
                [
                    _outcome_join.Join(
                        outcomes,
                        join or None,
                        within or None,
                        identity or None,
                        _flag("gone_if_missing", gone_if_missing),
                        outcomes_as or None,
                    )
                ]
            )
            if outcomes
            else None
        )
        cov = coverage(dataset, capture, load_rules(path), joins, from_set or None)
    return _jsonout.plain({**cov, "map": map})


def say_label_coverage(r: dict[str, Any]) -> str:
    """label-coverage-show's answer as text: what `evh label-coverage` prints, without the item list."""
    from evaluation_harness import label_coverage  # noqa: PLC0415

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        label_coverage.show(r, r["map"])
    return buf.getvalue().rstrip("\n")
