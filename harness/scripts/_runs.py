"""Reading runs: which runs are on a dataset, and what each scored per item.

Every command that reads runs used to walk the runs directory itself, about fifteen times,
with different filters and orderings: some sorted and some not, some fell back to the
directory name for a missing system_id, one crashed on a malformed line where another
skipped it, one counted a boolean as 1.0 where another dropped it. The inspector's p
agreed with pair-test's because the committed data is clean, not because the code was
shared. It is now: every reader goes through these functions.

    runs = runs_on("ag_news_200", match="_v2")            # [(score dir, its record)], by run id
    M = matrix(runs, "accuracy")                           # system_id -> item_id -> mean
    lower = lower_is_better_on(runs, "wer")                # the direction the runs declare
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import contextvars
import math
import re
import statistics
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, Literal, overload

from evaluation_harness import _common, _outputs
from evaluation_harness._common import is_descriptive, lower_is_better
from evaluation_harness.axes import BUILTIN, axes_of
from evaluation_harness.model import runs as _model_runs

Run = tuple[Path, dict]


def read_metrics(score_dir: Path) -> dict | None:
    """A score's record (the run's facts with the score's over them: model/runs), or None when it is missing or
    unreadable."""
    return _model_runs.record(score_dir)


def runs_on(
    dataset_id: str | None = None,
    *,
    label: str | None = "",
    match: str | None = None,
    system_id: str | None = None,
) -> list[Run]:
    """Every score read under `label` ("": a plain run's own score, the arm a goal reads; None: any) with its
    record, by run id; optionally only one dataset, system_ids containing `match`, or exactly `system_id`."""
    return _model_runs.read_arms(
        _model_runs.scored(dataset_id, label_is=label, system_id=system_id, match=match)
    )[0]


def left_out(
    dataset_id: str | None = None,
    *,
    label: str | None = "",
    match: str | None = None,
    system_id: str | None = None,
) -> list[str]:
    """What `runs_on` leaves out, one line a arm, named: an arm's runs scored against another reference than its latest
    run's are never averaged in (`model.runs.runs_of_arm`). [] when no arm has any."""
    scores = _model_runs.scored(dataset_id, label_is=label, system_id=system_id, match=match)
    groups: dict[str, list[Run]] = {}
    for d, m in scores:
        groups.setdefault(_model_runs.arm_of(d, m), []).append((d, m))
    lines = []
    for arm, found in sorted(groups.items()):
        kept, left = _model_runs.runs_of_arm(found)
        if left:
            ref = _model_runs.reference_of(kept[0][1])
            was = sorted({_model_runs.reference_of(m) or "no reference" for _d, m in left})
            lines.append(
                f"{arm}: {', '.join(sorted(m['run_id'] for _d, m in left))} scored against {', '.join(was)}, left out: "
                f"the arm is read against {ref or 'no reference'}, the reference of its latest run"
            )
    return lines


def by_arm(runs: Iterable[Run]) -> dict[str, list[Run]]:
    """system_id -> its runs (repeats, or anything else sharing the id), in sorted order."""
    out: dict[str, list[Run]] = {}
    for d, m in runs:
        out.setdefault(m["system_id"], []).append((d, m))
    return dict(sorted(out.items()))


def item_rows(run_dir: Path, strict: bool = True, meta: bool = True) -> Iterator[dict]:
    """The rows of a run (its predictions.jsonl, or the sqlite store's) that name an item. A malformed line raises
    (naming the run and line) unless `strict` is False, when it is skipped: a statistical
    test must not quietly drop an item, a page that shows a run may. `meta=False`: the caller reads the item and the
    numbers, and not a row's `_meta` or `_extra`, which the sqlite store then does not decode (and may leave out of the
    row). The rows are the store's own, shared: a caller that changes one copies it first."""
    for row in _outputs.rows(run_dir, errors="strict" if strict else "replace", meta=meta) or ():
        if "item_id" in row:
            yield row


def score_of(row: dict, metric: str) -> float | None:
    """The row's value for `metric` when it is a number; a boolean is not a score, nor is a NaN or an infinity (a run
    recorded before RFC-041 F7 can hold one: the item is read as not scored, as one the arm has no row for)."""
    v = row.get(metric)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


# The call's, not the process's (the MCP server answers calls at once, in threads): `not_scorable()`, `confound()`.
#: Items each arm's runs left unscored in this call: its action differed from production's, under which their labels
#: hold (RFC-031 L3). {system_id: item ids}; the command says it (`_jsonout`).
_NOT_SCORABLE: contextvars.ContextVar[dict[str, set[str]] | None] = contextvars.ContextVar(
    "evh_not_scorable", default=None
)
#: A replay arm's history confound (RFC-031 P1): {system_id: {items, of}}, said by the command.
_CONFOUND: contextvars.ContextVar[dict[str, dict[str, int]] | None] = contextvars.ContextVar(
    "evh_confound", default=None
)


def _own(var: contextvars.ContextVar) -> dict:
    d = var.get()
    if d is None:
        d = {}
        var.set(d)
    return d


def not_scorable() -> dict[str, set[str]]:
    """The items this call's scores left unscored, per arm (RFC-031 L3)."""
    return _own(_NOT_SCORABLE)


def confound() -> dict[str, dict[str, int]]:
    """This call's replay arms' history confounds (RFC-031 P1)."""
    return _own(_CONFOUND)


def per_item(
    runs: Iterable[Run],
    metric: str,
    *,
    keep: set[str] | None = None,
    raw: list[float] | None = None,
    strict: bool = True,
    reduce: str = "mean",
    data: Path | None = None,
) -> dict[str, float]:
    """item_id -> `metric` over the given runs (an arm's repeats), combined by `reduce` (stats.reduce_repeats: the
    mean by default). `keep` restricts the items; `raw` collects every value as stored, before averaging (the
    leaderboard measures stored precision on it); `data`: the data directory the runs are of (its exposure register
    says which items a held-out side leaves out), the project's when none."""
    from evaluation_harness import _exposure  # noqa: PLC0415

    acc: dict[str, list[float]] = {}
    datasets: set[str] = set()
    for d, m in runs:
        datasets.add(str((m or {}).get("dataset_id") or ""))
        if (m or {}).get("not_scorable"):  # RFC-031 L3: said by the command (_jsonout)
            not_scorable().setdefault(str(m.get("system_id")), set()).update(m["not_scorable"])
        # RFC-031 P1, said by the command: counted over the items this command reads (a period's, under `keep`), not
        # the whole run's (the fleet's beta: "5 of 287" beside a comparison of 52).
        confounded = ((m or {}).get("history_confound") or {}).get("items")
        hit: set[str] = set()
        seen: set[str] = set()
        for row in item_rows(d, strict=strict, meta=False):
            if keep is not None and row["item_id"] not in keep:
                continue
            seen.add(row["item_id"])
            if row.get("history_confound") == 1.0:
                hit.add(row["item_id"])
            v = score_of(row, metric)
            if v is None:
                continue
            acc.setdefault(row["item_id"], []).append(v)
            if raw is not None:
                raw.append(v)
        if confounded and hit:
            confound()[str(m.get("system_id"))] = {"items": len(hit), "of": len(seen)}
    # A held-out side's read items count in no score on it (RFC-031 H1): left out here, where every paired command's
    # scores come from, and counted for the command to say.
    for ds in datasets:
        kept = _exposure.keep(ds, acc, data)
        if kept is not None:
            acc = {i: v for i, v in acc.items() if i in kept}
    if reduce not in ("", "mean"):
        from evaluation_harness.stats import reduce_repeats  # noqa: PLC0415

        return {i: reduce_repeats(v, reduce) for i, v in acc.items() if v}
    return {i: statistics.fmean(v) for i, v in acc.items() if v}


def refuse_run_level(runs: Iterable[Run], metric: str | None, command: str) -> None:
    """Refuse a per-item test of a run-level metric (the adapter's score_run(): one number per run), by name,
    instead of finding no items and saying "nothing to test"."""
    from evaluation_harness._record import run_level_names  # noqa: PLC0415

    if metric and any(metric in run_level_names(m) for _d, m in runs):
        _common.die(
            f"{metric} is a run-level metric (the adapter's score_run(): one number for each run, no per-item "
            f"values), so {command} cannot test it item by item. The leaderboard shows it per arm, with its spread "
            "over the arm's runs; name a per-item metric with --metric to test.",
            "bad-argument",
        )


def repeat_agreement(runs: Iterable[Run], metric: str, items: Iterable[str] | None = None) -> dict | None:
    """How far an arm's runs (its repeats) agree, item by item (the fleet's feedback 33: three runs of a
    temperature-0 model gave 23 gate firings on 9 distinct items). {"runs", "items", "same", "item_runs"}: the
    items scored in two runs or more, how many of them got the same score in every run, and the item-runs
    behind them. None below two runs, or when no item was scored twice."""
    runs = list(runs)
    if len(runs) < 2:
        return None
    keep = set(items) if items is not None else None
    acc: dict[str, list[float]] = {}
    for d, _m in runs:
        for row in item_rows(d, strict=False, meta=False):
            v = score_of(row, metric)
            if v is not None and (keep is None or row["item_id"] in keep):
                acc.setdefault(row["item_id"], []).append(v)
    twice = {i: v for i, v in acc.items() if len(v) > 1}
    if not twice:
        return None
    return {
        "runs": len(runs),
        "items": len(twice),
        "same": sum(1 for v in twice.values() if len(set(v)) == 1),
        "item_runs": sum(len(v) for v in twice.values()),
    }


def say_agreement(label: str, ag: dict) -> str:
    """One arm's repeat agreement in words, with the unit it implies."""
    near = ag["same"] >= 0.9 * ag["items"]
    return f"{label}: {ag['runs']} runs, the same score on {ag['same']} of {ag['items']} items" + (
        " (near-copies, not independent samples)" if near else ""
    )


def matrix(
    runs: Iterable[Run], metric: str, *, keep: set[str] | None = None, raw: list[float] | None = None
) -> dict[str, dict[str, float]]:
    """system_id -> item_id -> mean `metric`; arms with no value for it are left out."""
    out = {cid: per_item(rs, metric, keep=keep, raw=raw) for cid, rs in by_arm(runs).items()}
    return {cid: items for cid, items in out.items() if items}


def recorded_direction(runs: Iterable[Run], metric: str) -> str | None:
    """ "lower" / "higher" as the runs record it for `metric` (`metric_directions`: the
    adapter's METRIC_DIRECTIONS, or `import-run --asc`). None when no run says."""
    said: dict[str, str] = {}
    for d, m in runs:
        declared = (m.get("metric_directions") or {}).get(metric)
        if declared in ("lower", "higher"):
            said.setdefault(str(declared), str(m.get("run_id") or d))
    if len(said) > 1:
        # Two runs, two answers: name them rather than take whichever was listed first.
        print(
            f"  NOTE: runs disagree on which way {metric} is better ("
            + ", ".join(f"{v}: {k}" for k, v in said.items())
            + "); using the first. Pass --asc or --desc to decide.",
            file=sys.stderr,
        )
    return next(iter(said), None)


def _declared_by(goal: dict, metric: str) -> str | None:
    """ "lower" / "higher" where `goal` itself says which way `metric` goes: as its primary measure, or as an axis that
    carries a direction of its own. A primary `direction` that is neither (`non_inferior`: a decision rule) says
    nothing, and an axis with none, or a built-in axis left at its default, is no declaration either."""
    crit = goal.get("success_criteria") or {}
    prim = crit.get("primary") or {}
    if prim.get("measure") == metric and prim.get("direction") in ("lower", "higher"):
        return str(prim["direction"])
    own = crit.get("axes") or {}
    for ax in axes_of(goal, lambda _m: "undeclared"):
        if ax["name"] == "quality" or ax["measure"] != metric or ax["role"] == "ignore":
            continue
        if ax["direction"] in ("lower", "higher") and (
            ax["name"] not in BUILTIN or (own.get(ax["name"]) or {}).get("direction")
        ):
            return str(ax["direction"])
    return None


def goal_declarations(goal: dict) -> dict[str, str]:
    """{measure: "lower" | "higher"} for each measure `goal` declares a direction for (V14 reads it)."""
    crit = goal.get("success_criteria") or {}
    measures = {(crit.get("primary") or {}).get("measure"), *(a["measure"] for a in axes_of(goal))}
    said = {m: _declared_by(goal, str(m)) for m in measures if m}
    return {m: d for m, d in said.items() if d}


def goal_datasets(goal: dict) -> list[str]:
    """The datasets a goal lists ([] when it lists none: it applies to any)."""
    return [
        str(d["dataset_id"])
        for d in goal.get("datasets") or []
        if isinstance(d, dict) and d.get("dataset_id")
    ]


#: What `direction_source` names for a measure nothing speaks for: no goal, no run, no name in the name table. It is read
#: as higher-is-better (a result never moves for it) and `assumed_note` says so wherever a ranking rests on it.
ASSUMED = "the default (nothing declares it)"


def assumed_note(metric: str, source: str) -> str | None:
    """The one line that says a direction is the bare default (`direction_source` named `ASSUMED`), None for any other
    source: declare the measure in a goal (`direction:`) or the adapter (`METRIC_DIRECTIONS`) to settle it."""
    if source != ASSUMED:
        return None
    return f"{metric}: no goal or adapter says which way is better; read as higher-is-better (declare it)"


def note_assumed(metric: str, **ask: Any) -> None:
    """Print `assumed_note` for `metric` as a reader's NOTE line when `direction(metric, **ask)` is the bare default.
    `ask` is what the reader asked `direction` with, so the line is true of the direction it used."""
    if line := assumed_note(metric, direction_source(metric, **ask)[1]):
        print(f"  NOTE: {line}")


def direction_source(
    metric: str,
    *,
    dataset: str | None = None,
    runs: Iterable[Run] = (),
    goals: dict | None = None,
    kinds: dict[str, str] | None = None,
) -> tuple[str, str]:
    """`direction`, and what decided it: "goal <id>", "the runs' directions", "the runs' kinds", "the name table" (a name
    it knows: cost, speed, tokens, an error rate, a descriptive key) or `ASSUMED` (higher, for a measure nothing says)."""
    runs = list(runs)
    if dataset is None:
        shared = {str(m["dataset_id"]) for _d, m in runs if m.get("dataset_id")}
        dataset = next(iter(shared)) if len(shared) == 1 else None
    goals = _common.load_goals() if goals is None else goals
    named = {str(m["goal"]) for _d, m in runs if m.get("goal")}
    listing = {g for g, doc in goals.items() if dataset and dataset in goal_datasets(doc or {})}
    # A question about a dataset is answered by the goals that list it and the goals the runs name: a goal on another
    # dataset says nothing about this one. Any goal answers only a question with no dataset.
    tiers = (sorted(listing), sorted(named & goals.keys() - listing)) + (
        (sorted(goals),) if dataset is None else ()
    )
    for tier in tiers:
        for gid in tier:
            said = _declared_by(goals[gid] or {}, metric)
            if said:
                return said, f"goal {gid}"
    said = recorded_direction(runs, metric)
    if said:
        return said, "the runs' directions"
    seen = [k for _d, m in runs if (k := (m.get("metric_kinds") or {}).get(metric))]
    kind = (kinds or {}).get(metric) or ("descriptive" if "descriptive" in seen else next(iter(seen), None))
    if kind == "descriptive" or (kind is None and is_descriptive(metric)):
        return "neutral", "the runs' kinds" if kind else "the name table"
    if lower_is_better(metric):
        return "lower", "the name table"
    return "higher", ASSUMED


def direction(
    metric: str,
    *,
    dataset: str | None = None,
    runs: Iterable[Run] = (),
    goals: dict | None = None,
    kinds: dict[str, str] | None = None,
) -> str:
    """Which way is better for `metric`: "lower", "higher" or "neutral". The one answer every reader gives (RFC-041):

      1. a goal that declares it, as its primary measure or as an axis with a direction: for a question about
         `dataset`, a goal listing it first, then the goals the runs name (a goal on another dataset says nothing
         about this one); for a question with no dataset, then any goal (V14 fails two that disagree on one dataset).
         The listing goal wins over a goal the runs name because a goal that names the dataset speaks for it, while a
         run's `goal` only says what the run was made for, and the run may be on a dataset that goal does not decide;
      2. what the runs record: the adapter's directions (`metric_directions`, `import-run --asc`), then the kinds
         they declare (`metric_kinds`; `kinds` overrides them, for the adapter's declaration as it is today): a
         descriptive kind is neutral;
      3. the name table (`_common`): cost, speed, tokens and error rates are lower, the descriptive keys neutral; the
         rest, which nothing declares, is higher (`ASSUMED`, which the readers that rank on it say, `assumed_note`).

    A declared direction beats neutral: a project that says which way a count goes has said it is not neutral.
    `dataset` is the dataset asked about; left out, it is the one the runs share. `goals` is {goal_id: goal}, read
    from the project when None.
    """
    return direction_source(metric, dataset=dataset, runs=runs, goals=goals, kinds=kinds)[0]


def combine(per: dict[str, str] | Iterable[str]) -> str:
    """One measure's directions on several datasets ({dataset: direction}) as one: the direction they all give, or
    "mixed" when they differ (a declaration on one dataset decides nothing for another)."""
    said = set(per.values() if isinstance(per, dict) else per)
    return said.pop() if len(said) == 1 else "mixed" if said else "higher"


#: The words every page prints for a direction.
BETTER_WORDS = {"lower": "lower", "higher": "higher", "neutral": "neutral: a description"}


def better_word(which: str, per: dict[str, str] | None = None) -> str:
    """The word that says which way is better, for a `direction` ("neutral: a description" for a count). For "mixed",
    the per-dataset answers: "lower on asr_v1; higher on dev_v1"."""
    if which != "mixed":
        return BETTER_WORDS[which]
    by: dict[str, list[str]] = {}
    for ds, d in sorted((per or {}).items()):
        by.setdefault(d, []).append(ds)
    return "; ".join(f"{d} on {', '.join(v)}" for d, v in by.items())


def lower_is_better_on(runs: Iterable[Run], metric: str, goals: dict | None = None) -> bool:
    """Whether a decrease in `metric` is an improvement on these runs: `direction` says "lower"."""
    return direction(metric, runs=runs, goals=goals) == "lower"


def ranks_direction(runs: Iterable[Run], metric: str, asc: bool = False, desc: bool = False) -> str:
    """ "lower", "higher" or "neutral" for `metric` on these runs: `asc` / `desc` when the caller passed one, else
    `direction`. What a ranking prints beside its heading: a count that is only a description is neutral, not higher."""
    if asc and desc:
        from evaluation_harness._common import die  # noqa: PLC0415

        die("--asc and --desc contradict each other", "bad-argument")
    if asc or desc:
        return "lower" if asc else "higher"
    return direction(metric, runs=runs)


def ranks_lower(runs: Iterable[Run], metric: str, asc: bool = False, desc: bool = False) -> bool:
    """True when lower is better for `metric` on these runs: `asc` / `desc` when the caller
    passed one, else `lower_is_better_on`. Every command that counts wins or ranks arms asks
    this, so "A wins 180/200" on latency means A was faster without anyone remembering --asc."""
    return ranks_direction(runs, metric, asc, desc) == "lower"


def mixed_versions(system_ids: Iterable[str]) -> dict[str, list[str]]:
    """{arm: its `_vN` endings} for each arm present at more than one version: v1 and v2 of one
    arm are two measurements side by side. Different arms at different versions (opus_v2 beside
    mistral_v1) are not a mix."""
    seen: dict[str, set[str]] = {}
    for c in system_ids:
        m = re.search(r"_v\d+$", c)
        if m:
            seen.setdefault(c[: m.start()], set()).add(m.group(0))
    return {base: sorted(v) for base, v in sorted(seen.items()) if len(v) > 1}


#: What to do about runs averaged into one row that nothing tells apart: said with the commands that do it (the 0.8.0
#: newcomer run was told to edit run.json by hand). A second plain run of a system is refused (evh run); these are
#: runs made before that, or copied in.
AMBIGUOUS_HOW = (
    "           They are averaged together below, and validate fails V8 once they are committed. Keep one measurement:\n"
    "           delete the others (evh data-rm --path runs/<run_id>), or allow the pair in validate.json's duplicate_ok\n"
    "           when they are one on purpose. To measure an arm again, repeat its run as it was run:\n"
    "           evh run ... --purpose repeat --of <run_id> joins the arm when nothing it measures differs; a repeat that\n"
    "           differs in its data, deployment, settings or adapter is read under `repeats`, as another measurement."
)


class AmbiguousRuns(Exception):
    """Two runs claim the same system_id and nothing says which one to read."""


@overload
def deciding_metric(
    dataset_id: str,
    *,
    match: str | None = ...,
    label: str | None = ...,
    runs: Iterable[Run] | None = ...,
    goals: dict | None = ...,
    refuse: Literal[True] = ...,
) -> str:
    """The deciding metric; a refusal when nothing decides (the overload that does not return None)."""


@overload
def deciding_metric(
    dataset_id: str,
    *,
    match: str | None = ...,
    label: str | None = ...,
    runs: Iterable[Run] | None = ...,
    goals: dict | None = ...,
    refuse: bool,
) -> str | None:
    """The deciding metric, None when nothing decides and `refuse` is False."""


def deciding_metric(
    dataset_id: str,
    *,
    match: str | None = None,
    label: str | None = "",
    runs: Iterable[Run] | None = None,
    goals: dict | None = None,
    refuse: bool = True,
) -> str | None:
    """The metric that decides on a dataset: what every command reads when none is named (RFC-041).

      1. the goal that lists the dataset (the first by id; else a goal the runs name) and whose primary measure a run
         records: its measure. A goal whose measure no run records (V14 warns) decides nothing;
      2. else the primary metric the runs record (the most common one: the adapter's PRIMARY_METRIC);
      3. else a refusal that names what is recorded and the measures a goal reads that nothing records (`refuse`; None
         when False).

    `runs` is what is read (the dataset's under `label` and `match` by default); `goals` {goal_id: goal} the project's.
    It used to be `default_metric`, the runs' primary alone: `pair-test` refused where `leaderboard` read the goal."""
    from collections import Counter  # noqa: PLC0415

    runs = list(runs_on(dataset_id, label=label, match=match) if runs is None else runs)
    goals = _common.load_goals() if goals is None else goals
    recorded: set[str] = set()
    primary: Counter = Counter()
    for _d, m in runs:
        recorded |= set((m.get("scores") or {}).keys())
        if m.get("primary_metric"):
            primary[m["primary_metric"]] += 1
    named = {str(m["goal"]) for _d, m in runs if m.get("goal")}
    listing = [g for g in sorted(goals) if dataset_id in goal_datasets(goals[g] or {})]
    unread: list[str] = []
    for gid in [*listing, *sorted((named & goals.keys()) - set(listing))]:
        measure = str(
            (((goals[gid] or {}).get("success_criteria") or {}).get("primary") or {}).get("measure") or ""
        )
        if measure in recorded:
            return measure
        if measure:
            unread.append(f"goal {gid} reads {measure!r}")
    if primary:
        if len(primary) > 1:
            print(
                f"  NOTE: runs on {dataset_id} declare different primary metrics ({dict(primary)}); "
                f"using the most common. Pass --metric to choose.",
                file=sys.stderr,
            )
        return str(primary.most_common(1)[0][0])
    if not refuse:
        return None
    from evaluation_harness._common import die  # noqa: PLC0415

    die(
        f"no run on {dataset_id} records a primary metric"
        + (f", and no goal reads a measure a run records ({'; '.join(unread)})" if unread else "")
        + ": pass --metric"
        + (f" (recorded: {', '.join(sorted(recorded))})" if recorded else ""),
        "not-found",
    )


def runs_by_arm(label: str, dataset_id: str, prefix: str = "", strip: str = "") -> dict[str, list[Path]]:
    """system_id -> the score directories read under `label` that produced it, by run id.

    WHY THIS EXISTS RATHER THAN A GLOB AT EACH CALL SITE.

    Five places in `check_report_claims.py` globbed for a run and took whichever came
    back -- three took the last hit, two the first, and one of them had a different
    exclusion rule from the others. That is fine while every system_id is unique. Three
    SciFact arms were re-run, so three were not, and the checker's answer then depended
    on the order the filesystem returned directories in: green on APFS, red on ext4.
    `make ci` was reported green for a week on the only machine anyone had run it on.

    REPEATS ARE NOT AMBIGUITY. `--repeat 3` writes three runs, all one measurement of
    one arm, and so does a repeat of a run made with the same fingerprint (`--purpose
    repeat --of`); averaging them is the point. Those come back together
    (`model.runs.set_of`). Anything ELSE sharing a system_id is two different
    measurement occasions wearing one name,
    and this raises rather than picking one, because there is no correct pick.
    """
    groups: dict[str, list[Run]] = {}
    for d, m in runs_on(dataset_id, label=label):
        cid = m["system_id"]
        if prefix and not cid.startswith(prefix):
            continue
        key = cid[len(prefix) :] if prefix else cid
        if strip and key.endswith(strip):
            key = key[: -len(strip)]
        groups.setdefault(key, []).append((d, m))

    for key, found in groups.items():
        if len(found) < 2:
            continue
        if _model_runs.is_set(found):
            continue
        raise AmbiguousRuns(
            f"{len(found)} runs read as {label or 'runs'} claim system_id {key!r} on "
            f"{dataset_id}: {sorted(m['run_id'] for _d, m in found)}.\n"
            f"  These are different measurement occasions sharing one name, so any "
            f"tool reading them picks one by run id.\n"
            f"  A run that is not the record is a re-run: its run.json's purpose says which "
            f"(repeat, retime, pair), as the SciFact re-runs' do."
        )
    return {k: [d for d, _m in sorted(v, key=lambda x: x[1]["run_id"])] for k, v in sorted(groups.items())}


def warn_on_ambiguous_runs(read_as: str = "", dataset_id: str | None = None, label: str = "") -> int:
    """Say loudly when two runs share a system_id for reasons other than --repeat.

    Every loader in this repo groups runs by `system_id` and then averages or picks --
    `leaderboard` printed `sf_llama_l_n200_v1 runs=2 0.683350`, the mean of 0.7281 and
    0.6386, a number in no run and no report; `pair_test`, `family_test`,
    `rank_stability` and `holdout_significance` averaged per item across both; the
    report scripts silently took whichever the filesystem returned last. None of it
    said anything. Found by external review.

    `runs_by_arm` RAISES on this, which is right for a checker and wrong for a
    leaderboard someone is reading interactively. This warns instead and returns the
    count, so the number on screen is still explained.

    A repeat set (`--repeat N`, and repeats joined to the run they repeat) is one arm
    measured N times and is not ambiguous; averaging those is the point.
    """
    groups: dict[str, list[Run]] = {}
    for d, m in runs_on(dataset_id or None, label=read_as):
        groups.setdefault(m["system_id"], []).append((d, m))
    bad = []
    for cid, found in sorted(groups.items()):
        if len(found) < 2:
            continue
        if _model_runs.is_set(found):
            continue
        bad.append((cid, sorted(m["run_id"] for _d, m in found)))
    for cid, names in bad:
        print(
            f"  WARNING: {len(names)} runs claim system_id {cid!r}"
            f"{' in ' + label if label else ''} — {', '.join(names)}."
        )
        print(AMBIGUOUS_HOW)
    for line in left_out(dataset_id or None, label=read_as):
        print(f"  WARNING: {line}.")
    return len(bad)
