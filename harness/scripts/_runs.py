"""Reading runs: which runs are on a dataset, and what each scored per item.

Every command that reads runs used to walk the runs directory itself, about fifteen times,
with different filters and orderings: some sorted and some not, some fell back to the
directory name for a missing config_id, one crashed on a malformed line where another
skipped it, one counted a boolean as 1.0 where another dropped it. The inspector's p
agreed with pair-test's because the committed data is clean, not because the code was
shared. It is now: every reader goes through these functions.

    runs = runs_on("ag_news_200", match="_v2")            # [(run dir, metrics.json)], sorted
    M = matrix(runs, "accuracy")                           # config_id -> item_id -> mean
    lower = lower_is_better_on(runs, "wer")                # the direction the runs declare
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

if not __package__:  # run as a file (a checkout's python scripts/x.py, or an installed copy by path)
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))  # the package's parent

import json
import re
import statistics
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

from evaluation_harness import _common
from evaluation_harness._common import lower_is_better

Run = tuple[Path, dict]


def read_metrics(run_dir: Path) -> dict | None:
    """A run's metrics.json, or None when it is missing, unreadable or not an object."""
    mj = run_dir / "metrics.json"
    try:
        m = json.loads(mj.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return m if isinstance(m, dict) else None


def runs_on(
    dataset_id: str | None = None,
    *,
    runs_dir: Path | None = None,
    match: str | None = None,
    config_id: str | None = None,
) -> list[Run]:
    """Every run in `runs_dir` (default: the runs directory) with a readable metrics.json and
    a config_id, in directory-name order; optionally only one dataset, config_ids containing
    `match`, or exactly `config_id`."""
    base = runs_dir or _common.RUNS
    out: list[Run] = []
    for d in sorted(base.iterdir()) if base.is_dir() else []:
        m = read_metrics(d) if d.is_dir() else None
        if m is None or not m.get("config_id"):
            continue
        if dataset_id is not None and m.get("dataset_id") != dataset_id:
            continue
        if match and match not in m["config_id"]:
            continue
        if config_id is not None and m["config_id"] != config_id:
            continue
        out.append((d, m))
    return out


def by_arm(runs: Iterable[Run]) -> dict[str, list[Run]]:
    """config_id -> its runs (repeats, or anything else sharing the id), in sorted order."""
    out: dict[str, list[Run]] = {}
    for d, m in runs:
        out.setdefault(m["config_id"], []).append((d, m))
    return dict(sorted(out.items()))


def item_rows(run_dir: Path, strict: bool = True) -> Iterator[dict]:
    """The rows of a run's predictions.jsonl that name an item. A malformed line raises
    (naming the file and line) unless `strict` is False, when it is skipped: a statistical
    test must not quietly drop an item, a page that shows a run may."""
    pj = run_dir / "predictions.jsonl"
    if not pj.is_file():
        return
    for n, line in enumerate(
        pj.read_text(encoding="utf-8", errors="strict" if strict else "replace").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            if strict:
                raise ValueError(f"{pj}:{n}: not JSON ({exc})") from exc
            continue
        if isinstance(row, dict) and "item_id" in row:
            yield row


def score_of(row: dict, metric: str) -> float | None:
    """The row's value for `metric` when it is a number; a boolean is not a score."""
    v = row.get(metric)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


def per_item(
    runs: Iterable[Run],
    metric: str,
    *,
    keep: set[str] | None = None,
    raw: list[float] | None = None,
    strict: bool = True,
) -> dict[str, float]:
    """item_id -> the mean of `metric` over the given runs (an arm's repeats). `keep`
    restricts the items; `raw` collects every value as stored, before averaging (the
    leaderboard measures stored precision on it)."""
    acc: dict[str, list[float]] = {}
    for d, _m in runs:
        for row in item_rows(d, strict=strict):
            v = score_of(row, metric)
            if v is None or (keep is not None and row["item_id"] not in keep):
                continue
            acc.setdefault(row["item_id"], []).append(v)
            if raw is not None:
                raw.append(v)
    return {i: statistics.fmean(v) for i, v in acc.items() if v}


def matrix(
    runs: Iterable[Run], metric: str, *, keep: set[str] | None = None, raw: list[float] | None = None
) -> dict[str, dict[str, float]]:
    """config_id -> item_id -> mean `metric`; arms with no value for it are left out."""
    out = {cid: per_item(rs, metric, keep=keep, raw=raw) for cid, rs in by_arm(runs).items()}
    return {cid: items for cid, items in out.items() if items}


def recorded_direction(runs: Iterable[Run], metric: str) -> str | None:
    """ "lower" / "higher" as the runs record it for `metric` (`metric_directions`: the
    adapter's METRIC_DIRECTIONS, or `import-run --asc`). None when no run says."""
    said: dict[str, str] = {}
    for d, m in runs:
        declared = (m.get("metric_directions") or {}).get(metric)
        if declared in ("lower", "higher"):
            said.setdefault(str(declared), d.name)
    if len(said) > 1:
        # Two runs, two answers: name them rather than take whichever was listed first.
        print(
            f"  NOTE: runs disagree on which way {metric} is better ("
            + ", ".join(f"{v}: {k}" for k, v in said.items())
            + "); using the first. Pass --asc or --desc to decide.",
            file=sys.stderr,
        )
    return next(iter(said), None)


def goal_direction(runs: Iterable[Run], metric: str, goals: dict | None = None) -> str | None:
    """ "lower" / "higher" from a goal these runs name whose primary measure is `metric`."""
    from evaluation_harness._common import load_goals  # noqa: PLC0415

    named = {str(m["goal"]) for _d, m in runs if m.get("goal")}
    if not named:
        return None
    goals = load_goals() if goals is None else goals
    for gid in sorted(named):
        primary = ((goals.get(gid) or {}).get("success_criteria") or {}).get("primary") or {}
        if primary.get("measure") == metric and primary.get("direction") in ("lower", "higher"):
            return str(primary["direction"])
    return None


def lower_is_better_on(runs: Iterable[Run], metric: str, goals: dict | None = None) -> bool:
    """Whether a decrease in `metric` is an improvement on these runs, by one precedence: the
    goal they name, then what the adapter declared (recorded on the run), then the name table
    (a cost, speed or token count). A goal and the runs could disagree, so the goal page
    ranked lowest first while the inspector one click away counted the leader as losing; V14
    now fails a goal that contradicts its runs."""
    runs = list(runs)
    said = goal_direction(runs, metric, goals) or recorded_direction(runs, metric)
    return said == "lower" if said else lower_is_better(metric)


def direction(runs: Iterable[Run], metric: str, asc: bool = False, desc: bool = False) -> bool:
    """True when lower is better for `metric` on these runs: `asc` / `desc` when the caller
    passed one, else `lower_is_better_on`. Every command that counts wins or ranks arms asks
    this, so "A wins 180/200" on latency means A was faster without anyone remembering --asc."""
    if asc and desc:
        raise SystemExit("ERROR: --asc and --desc contradict each other")
    if asc or desc:
        return asc
    return lower_is_better_on(runs, metric)


#: `--repeat N` writes `<id>_r1 .. <id>_rN`: one arm measured N times, not N arms.
_REPEAT = re.compile(r"_r\d+$")


def mixed_versions(config_ids: Iterable[str]) -> dict[str, list[str]]:
    """{arm: its `_vN` endings} for each arm present at more than one version: v1 and v2 of one
    arm are two measurements side by side. Different arms at different versions (opus_v2 beside
    mistral_v1) are not a mix."""
    seen: dict[str, set[str]] = {}
    for c in config_ids:
        m = re.search(r"_v\d+$", c)
        if m:
            seen.setdefault(c[: m.start()], set()).add(m.group(0))
    return {base: sorted(v) for base, v in sorted(seen.items()) if len(v) > 1}


def repeat_stem(run_name: str) -> str:
    """The run name without its `_rN` repeat suffix."""
    return _REPEAT.sub("", run_name)


def is_repeat_set(run_names: list[str]) -> bool:
    """Whether these runs are one `--repeat` set: every name `<stem>_rN` off one stem."""
    return len({repeat_stem(n) for n in run_names}) == 1 and all(_REPEAT.search(n) for n in run_names)


class AmbiguousRuns(Exception):
    """Two runs claim the same config_id and nothing says which one to read."""


def default_metric(dataset_id: str, match: str | None = None, runs_dir: Path | None = None) -> str:
    """The metric a command reads when none is named: the primary metric the matching runs
    on this dataset recorded, the most common one. It used to be `coverage`, the
    summarisation example's metric, hard-coded: every other project got "no arms" or a
    crash unless it passed --metric."""
    from collections import Counter  # noqa: PLC0415

    primary: Counter = Counter()
    seen: set = set()
    for _d, m in runs_on(dataset_id, runs_dir=runs_dir, match=match):
        if m.get("primary_metric"):
            primary[m["primary_metric"]] += 1
        seen |= set((m.get("scores") or {}).keys())
    if primary:
        if len(primary) > 1:
            print(
                f"  NOTE: runs on {dataset_id} declare different primary metrics ({dict(primary)}); "
                f"using the most common. Pass --metric to choose.",
                file=sys.stderr,
            )
        return primary.most_common(1)[0][0]
    raise SystemExit(
        f"ERROR: no run on {dataset_id} records a primary metric: pass --metric"
        + (f" (recorded: {', '.join(sorted(seen))})" if seen else "")
    )


def runs_by_arm(base: Path, dataset_id: str, prefix: str = "", strip: str = "") -> dict[str, list[Path]]:
    """config_id -> the run directories that produced it, deterministically ordered.

    WHY THIS EXISTS RATHER THAN A GLOB AT EACH CALL SITE.

    Five places in `check_report_claims.py` globbed for a run and took whichever came
    back -- three took the last hit, two the first, and one of them had a different
    exclusion rule from the others. That is fine while every config_id is unique. Three
    SciFact arms were re-run, so three were not, and the checker's answer then depended
    on the order the filesystem returned directories in: green on APFS, red on ext4.
    `make ci` was reported green for a week on the only machine anyone had run it on.

    REPEATS ARE NOT AMBIGUITY. `--repeat 3` writes `<id>_r1.._r3`, all one measurement
    of one arm, and averaging them is the point. Those come back together. Anything
    ELSE sharing a config_id is two different measurement occasions wearing one name,
    and this raises rather than picking one, because there is no correct pick.
    """
    groups: dict[str, list[Path]] = {}
    for d, m in runs_on(dataset_id, runs_dir=base):
        cid = m["config_id"]
        if prefix and not cid.startswith(prefix):
            continue
        key = cid[len(prefix) :] if prefix else cid
        if strip and key.endswith(strip):
            key = key[: -len(strip)]
        groups.setdefault(key, []).append(d)

    for key, dirs in groups.items():
        if len(dirs) < 2:
            continue
        if is_repeat_set([d.name for d in dirs]):
            continue
        raise AmbiguousRuns(
            f"{len(dirs)} runs under {base.name}/ claim config_id {key!r} on "
            f"{dataset_id}: {sorted(d.name for d in dirs)}.\n"
            f"  These are different measurement occasions sharing one name, so any "
            f"tool reading them picks one by filesystem order.\n"
            f"  Move the ones that are not the record out of this directory "
            f"(data/runs-repeats/ is where the SciFact re-runs live)."
        )
    return {k: sorted(v) for k, v in sorted(groups.items())}


def warn_on_ambiguous_runs(base: Path, dataset_id: str | None = None, label: str = "") -> int:
    """Say loudly when two runs share a config_id for reasons other than --repeat.

    Every loader in this repo groups runs by `config_id` and then averages or picks --
    `leaderboard` printed `sf_llama_l_n200_v1 runs=2 0.683350`, the mean of 0.7281 and
    0.6386, a number in no run and no report; `pair_test`, `family_test`,
    `rank_stability` and `holdout_significance` averaged per item across both; the
    report scripts silently took whichever the filesystem returned last. None of it
    said anything. Found by external review.

    `runs_by_arm` RAISES on this, which is right for a checker and wrong for a
    leaderboard someone is reading interactively. This warns instead and returns the
    count, so the number on screen is still explained.

    A `--repeat N` set (`<id>_r1.._rN`) is one arm measured N times and is not
    ambiguous; averaging those is the point.
    """
    groups: dict[str, list[str]] = {}
    for d, m in runs_on(dataset_id or None, runs_dir=base):
        groups.setdefault(m["config_id"], []).append(d.name)
    bad = []
    for cid, names in sorted(groups.items()):
        if len(names) < 2:
            continue
        if is_repeat_set(names):
            continue
        bad.append((cid, sorted(names)))
    for cid, names in bad:
        print(
            f"  WARNING: {len(names)} runs claim config_id {cid!r}"
            f"{' in ' + label if label else ''} — {', '.join(names)}."
        )
        print(
            f"           They are averaged together below. If they are different "
            f"measurement occasions, move all but one out of {base.name}/."
        )
    return len(bad)
