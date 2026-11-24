"""Where a goal stands, decided once (RFC-032 step 8): the arms on each of its datasets that record its measure, grouped
by what they are scored against, each group's leader, contenders and recommended arm (axes.decide), the promoted
baseline's facts, and the leader against the baseline. The goal pages, `evh goal-list`, the overview, the arms page,
`evh leaderboard` and `GET /goals/{goal}/leaderboard` all read these functions; the catalog only renders them.

Everything here reads the adapter it is given (the catalog's), never a global: `by_dataset(A)` is what the arms, the
references and the baselines say, and the decision is made from that."""

from __future__ import annotations

import copy
import statistics
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from evaluation_harness import _runs
from evaluation_harness.axes import strategy_of
from evaluation_harness.catalog_adapter import item_fields

# -- what every goal view reads ------------------------------------------------------------------------------------


def by_dataset(A, datasets: set[str] | None = None) -> dict:
    """{dataset: {"arms": [row], "refs": [ref], "items": 0, "baselines": [baseline]}}: every arm the adapter lists with
    its headline, its mean on each metric (and the items behind it), what it is scored against and whether it wrote
    that; the references; and the promoted baselines (the catalog adds what only its pages need: versions, tags, sizes); `datasets`: only these."""
    by_ds: dict = {}
    runs_of = getattr(A, "arm_runs", None)
    read_as = getattr(A, "read_as", None)
    for arm in A.arms():
        d = A.describe(arm)
        if datasets is not None and d["dataset"] not in datasets:
            continue
        sc = A.scores(arm)
        runs = runs_of(arm) if callable(runs_of) else []
        head = d.get("primary") or d.get("task") or ""
        values = (sc.get(head) or {}).get("values") or {}
        by_ds.setdefault(d["dataset"], {"arms": [], "refs": [], "items": 0})["arms"].append(
            {
                "arm": arm,
                "label": d["label"],
                "read_as": read_as(arm) if callable(read_as) else "",
                "runs": d.get("runs", 1),
                "metric": head,
                "mean": statistics.fmean(values.values()) if values else None,
                "n": len(values) or max((len(v["values"]) for v in sc.values()), default=0),
                "lower": A.lower_is_better(head, d["dataset"]) if head else False,
                "reference": d.get("reference", ""),
                "judge": d.get("judge", ""),
                "wrote": bool(d.get("wrote_reference")),
                "failed_every_item": bool(d.get("failed_every_item")),
                "labels_source": d.get("labels_source", ""),
                "recorded": d.get("recorded", ""),
                "replay": d.get("replay"),
                "machine": _machine(A, arm),
                "goal": d.get("goal", ""),
                "format": d.get("format", ""),
                "run_list": runs,
                "last": max((r.get("created_at") or "" for r in runs), default=""),
                # every metric's mean and item count, for the goal pages (numbers only)
                "means": {
                    k: (statistics.fmean(v["values"].values()), len(v["values"]))
                    for k, v in sc.items()
                    if v["values"]
                },
            }
        )
    for r in A.references():
        if datasets is not None and r["dataset"] not in datasets:
            continue
        by_ds.setdefault(r["dataset"], {"arms": [], "refs": [], "items": 0})["refs"].append(r)
    _mark_superseded(by_ds)
    bl = getattr(A, "baselines", None)
    for b in bl() if callable(bl) else []:
        v = by_ds.get(b["dataset"])
        if v is None:
            continue
        v.setdefault("baselines", []).append(b)
        for a in v["arms"]:
            if a["arm"] == b["arm"]:
                a["baseline"] = b
        # A baseline whose arm is read from its re-score is the re-score's (RFC-022): the goal reads that one.
        for a in v["arms"]:
            if a.get("baseline") and a.get("superseded_by"):
                for t in v["arms"]:
                    if t["arm"] == a["superseded_by"]:
                        t["baseline"] = a["baseline"]
    return by_ds


def _mark_superseded(by_ds: dict) -> None:
    """An arm every run of which was re-scored (`evh rescore`) against the same reference gets
    "superseded_by": the arm holding the latest re-score. A scorer that changes after runs were measured
    leaves their scores stale, and the re-score is the same outputs read by the current scorer; showing
    both ranks one arm twice (and an old score may lack the goal's measure entirely). The goal pages read
    the re-score; the measured arm keeps its page as the record of what was first scored."""
    for v in by_ds.values():
        latest: dict = {}
        for a in v["arms"]:
            for r in a["run_list"]:
                if r.get("derived") == "rescore" and r.get("from"):
                    key = (a["reference"], r["from"])
                    if key not in latest or (r["created_at"], a["arm"]) > latest[key][0]:
                        latest[key] = ((r["created_at"], a["arm"]), a["arm"])
        for a in v["arms"]:
            ids = [r["run_id"] for r in a["run_list"]]
            by = {latest.get((a["reference"], i), (None, None))[1] for i in ids}
            if ids and len(by) == 1 and None not in by and a["arm"] not in by:
                a["superseded_by"] = by.pop()


def _machine(A, arm: str) -> str:
    """Where an arm's time was spent, in one form: "served on <machine>" when its deployment names the machine
    that served the model, else "run on [<label> · ]<platform>, <n> CPUs" for the runner (the label is
    EVAL_HOST_LABEL, when set). Four forms in one table ("mac-dev", "Darwin/x86_64 · 12 CPUs", "x3") read as four
    kinds of thing; a runner without a label is never guessed to be a labelled one."""
    fn = getattr(A, "conditions", None)
    c = fn(arm) if callable(fn) else {}
    if c.get("deployment.machine"):
        return f"served on {c['deployment.machine']}"
    hw = ", ".join(
        b
        for b in (c.get("machine.platform"), c.get("machine.cpu_count") and f"{c['machine.cpu_count']} CPUs")
        if b
    )
    name = " · ".join(b for b in (c.get("machine.label"), hw) if b)
    return f"run on {name}" if name else ""


# -- the leader rule -----------------------------------------------------------------------------------------------


def flags_of(goal: dict, n: int, fmt: str, wrote: bool) -> list[str]:
    """What the goal holds against an arm that records its measure on `n` items in `fmt`: too few items, a format
    its output contract does not list, or having written the reference it is scored against. A flagged arm is shown,
    never the leader and never recommended."""
    crit = goal.get("success_criteria") or {}
    need = crit.get("min_items")
    formats = {c.get("format") for c in goal.get("output_contract") or [] if c.get("format")}
    flags = []
    if need and n < need:
        flags.append(f"n {n} < min_items {need}")
    if fmt and formats and fmt not in formats:
        flags.append(f"format {fmt} not in the contract")
    if wrote:
        flags.append("wrote the reference it is scored against")
    return flags


def comparable(A, goal: dict | None, arms: list[str], retired_in: dict | None = None) -> list[str]:
    """The arms a leader is read from, one rule for a goal and for a round: never a judged arm, never an arm the goal
    flags (`flags_of`, which includes the arm that wrote its reference: it scores 1.0 on its own outputs) or has
    retired (`retired_in`, `retired_in_of`; a round passes none: the arms it reads are its own, in play), and the
    gold-scored arms where any arm is."""
    if not arms:
        return []
    g = goal or {}
    measure = ((g.get("success_criteria") or {}).get("primary") or {}).get("measure", "")
    ref = {a: str(A.describe(a).get("reference") or "") for a in arms}

    def held(a: str) -> bool:
        d = A.describe(a)
        n = len(((A.scores(a).get(measure) or {}).get("values")) or {})
        return bool(flags_of(g, n, d.get("format", ""), bool(d.get("wrote_reference")))) or bool(
            retired_in and retired_round(retired_in, a)
        )

    keep = [a for a in arms if not a.split("/", 1)[0].startswith("judged-") and not held(a)]
    gold = [a for a in keep if ref[a].startswith("gold/")]
    return gold or keep


def leader(
    A, goal: dict | None, arms: list[str], metric: str, lower: bool, retired_in: dict | None = None
) -> str | None:
    """The leader of these arms: the best mean on `metric` among the arms a leader is read from (`comparable`), None
    when none records it. A round's leader and a goal's are this one."""
    means = {}
    for a in comparable(A, goal, arms, retired_in):
        vals = (A.scores(a).get(metric) or {}).get("values") or {}
        if vals:
            means[a] = statistics.fmean(vals.values())
    if not means:
        return None
    return (min if lower else max)(means, key=lambda a: means[a])


def corrected(row: dict, k: int) -> dict:
    """A paired test's row corrected for the arm having been chosen from `k` others (a selection effect): Bonferroni,
    significant only when p x k <= 0.05. Conservative, and it needs no more than the one paired test."""
    k = max(1, k)
    p_adj = min(1.0, row["p"] * k) if row.get("p") is not None else None
    verdict = row["verdict"]
    if verdict.startswith("significant") and (p_adj is None or p_adj > 0.05):
        verdict = "not significant"
    return {**row, "verdict": verdict, "p_adjusted": p_adj, "family": k}


# -- the answer on each dataset ------------------------------------------------------------------------------------


def _group_key(a: dict) -> str:
    """What an arm's numbers are measured against: a judge, a reference, or nothing."""
    return f"judge {a['judge']}" if a.get("judge") else (a.get("reference") or "no reference")


def lower_on(A, goal: dict, measure: str, ds: str) -> bool:
    """Whether `measure` is better lower on `ds`, for a goal's block: what every reader says (`_runs.direction`: the goal
    that declares it, the runs, the name table), never the goal's `direction` alone, which a goal may leave out. Without
    an adapter (a block read from rows alone), the goal and the name table."""
    if A is not None:
        return bool(A.lower_is_better(measure, ds))
    return _runs.direction(measure, dataset=ds, goals={str(goal.get("goal_id", "")): goal}) == "lower"


def goal_answers(goal: dict, by_ds: dict, A=None) -> list:
    """[{"dataset", "role", "notes", "groups": [{"key", "rows", "leader"}]}] for one goal: on each
    of its datasets, every arm that records the goal's primary measure, grouped by what it is
    scored against (gold first, then silver, then judges), best first within a group. Arms are
    ranked only against arms on the same dataset scored against the same thing, and a group's
    leader is never a flagged arm: fewer items than min_items, a format the goal does not accept,
    or the arm that wrote the reference it is scored against. Each row ranks by its own measure's direction on its
    dataset (`lower_on`: a judge's group reads on the judge's score)."""
    out = []
    for ds, role, notes, rows in _goal_rows(goal, by_ds):
        lowers = {m: lower_on(A, goal, m, ds) for m in {r["measure"] for r in rows}}

        def sign(r: dict, lowers: dict = lowers) -> float:
            return r["mean"] if lowers[r["measure"]] else -r["mean"]

        groups: dict = {}
        for r in rows:
            groups.setdefault(_group_key(r), []).append(r)
        ordered = sorted(
            groups.items(), key=lambda kv: (kv[0].startswith("judge "), not kv[0].startswith("gold/"), kv[0])
        )
        out.append(
            {
                "dataset": ds,
                "role": role,
                "notes": notes,
                "groups": [
                    {
                        "key": k,
                        "rows": sorted(
                            g,
                            key=lambda r: (bool(r["flags"]), sign(r), r["label"]),
                        ),
                        "leader": next(
                            (r for r in sorted(g, key=sign) if not r["flags"]),
                            None,
                        ),
                    }
                    for k, g in ordered
                ],
            }
        )
    return out


def unrecorded(goal: dict, by_ds: dict, ds: str) -> list[str] | None:
    """What the arms on `ds` are read on (their own headlines, sorted), when `goal` names a primary measure that no arm
    there records: V14 warns about it, and the goal decides nothing on `ds` (`_goal_rows` has no row). None when the
    goal has no measure, the dataset no arm, or an arm records it."""
    measure = ((goal.get("success_criteria") or {}).get("primary") or {}).get("measure", "")
    arms = [a for a in (by_ds.get(ds) or {}).get("arms", []) if not a.get("superseded_by")]
    if not measure or not arms:
        return None
    if any(measure in a["means"] or (a.get("judge") and a["metric"] in a["means"]) for a in arms):
        return None
    return sorted({a["metric"] for a in arms if a.get("metric")} or {k for a in arms for k in a["means"]})


def _goal_rows(goal: dict, by_ds: dict) -> list:
    """[(dataset, role, notes, rows)]: the arms on each of the goal's datasets that record its
    measure, each with its mean, items, whether it names the goal, and its flags. A goal with no measure (a dataset
    read without a goal, `evh leaderboard`) reads each arm on its own headline."""
    crit = goal.get("success_criteria") or {}
    measure = (crit.get("primary") or {}).get("measure", "")
    out = []
    for d in goal.get("datasets") or []:
        ds = d.get("dataset_id", "")
        rows = []
        arms = (by_ds.get(ds) or {}).get("arms", [])
        # the measured arms read through a re-score (an older re-score superseded by a newer one is not another)
        moved = [
            a for a in arms if a.get("superseded_by") and not any(r.get("derived") for r in a["run_list"])
        ]
        # The baseline is the goal's own (RFC-041 F6): the arm `baseline_read` gives for this goal, not any arm another goal
        # on the dataset promoted (`by_dataset` flags an arm for every goal, for the arm's own page).
        bl, base = baseline_read(by_ds.get(ds) or {}, goal["goal_id"])
        notes = d.get("notes", "")
        if moved:
            notes = (notes.rstrip(". ") + ". " if notes else "") + (
                f"{len(moved)} arm(s) are read from their re-score with the current scorer, not their first "
                "score (the measured run keeps its own page)."
            )
        for a in arms:
            if a.get("superseded_by"):
                continue
            # A judged arm records its judge's score, not the goal's measure: it is shown in its
            # judge's group, read on that score (never ranked with the reference-scored groups).
            if measure:
                use = measure if measure in a["means"] else (a["metric"] if a.get("judge") else None)
                if not use or use not in a["means"]:
                    continue
            else:  # no goal: every arm, on its headline (or its first metric; a run-level one has no mean)
                use = a["metric"] if a["metric"] in a["means"] else next(iter(sorted(a["means"])), "")
            mean, n = a["means"].get(use, (0.0, a["n"]))
            flags = flags_of(goal, n, a["format"], a["wrote"])
            mine = bl[-1] if bl and a["arm"] == base else None
            rows.append(
                dict(
                    a,
                    mean=mean,
                    n=n,
                    measure=use,
                    filed=a["goal"] == goal["goal_id"],
                    flags=flags,
                    baseline=mine,
                )
            )
        seen = unrecorded(goal, by_ds, ds)
        if seen is not None:
            notes = (notes.rstrip(". ") + ". " if notes else "") + (
                f"No arm records {measure!r}, which this goal reads; the arms record {', '.join(seen)}. "
                "`evh validate` warns about it (V14); the goal needs a measure the runs record."
            )
        out.append((ds, d.get("role", ""), notes, rows))
    return out


def decided(A, g: dict, by_ds: dict) -> list:
    """`goal_answers`, each group with its `measure` (a judge's group reads on the judge's score) and its decision `dec`
    (`group_decision`; a group scored against silver beside a gold one is shown, not recommended)."""
    retired_in = retired_in_of(A, g)
    measure = ((g.get("success_criteria") or {}).get("primary") or {}).get("measure", "")
    answers = goal_answers(g, by_ds, A)
    for ans in answers:
        tiers = {r["id"]: r["tier"] for r in (by_ds.get(ans["dataset"]) or {}).get("refs", [])}
        for grp in ans["groups"]:
            gm = (grp["rows"][0].get("measure") if grp["rows"] else None) or measure
            grp["measure"] = gm
            grp["dec"] = group_decision(
                A,
                g,
                ans["dataset"],
                grp["rows"],
                gm,
                retired_in,
                gold_beside(tiers, ans["groups"], grp["key"]),
            )
    return answers


def systems_filed(by_ds: dict, g: dict) -> int:
    """How many systems were run for this goal, each counted once however many
    ways it was scored (gold, silver, a judge)."""
    return len(
        {a["arm"].rsplit("/", 1)[-1] for v in by_ds.values() for a in v["arms"] if a["goal"] == g["goal_id"]}
    )


def retired_in_of(A, g: dict) -> dict:
    """{arm id: round_id} for every arm a round of this goal retired (its `retired_arms`) and no later round has back in
    play: a retirement is a round's decision (ADR-0006, RFC-004), so an arm carried into a later round is in play."""
    rfn = getattr(A, "rounds", None)
    out: dict = {}
    for r in rfn() if callable(rfn) else []:
        if r.get("goal") != g["goal_id"]:
            continue
        for k in r.get("arms") or []:
            # with its re-scored siblings (the same dataset and system under another label), retired with it
            tail = k.split("/", 1)[-1]
            for gone in [x for x in out if x.split("/", 1)[-1] == tail]:
                del out[gone]
        for k in r.get("retired_arms") or []:
            out[k] = r["round_id"]
    return out


def retired_round(retired_in: dict, arm: str) -> str | None:
    """The round that retired this arm: by its arm id, else by its system id. A retirement names runs, and every arm
    a retired run is scored in (its re-scores, RFC-022, the goal's reading of it) is retired with it: otherwise an
    arm a round retired stayed among the goal's contenders whenever it had been re-scored (found 2026-11-01: 25 of
    the triage goal's 76 contenders were round 3's retirements)."""
    return retired_in.get(arm) or retired_in.get(arm.rsplit("/", 1)[-1])


def retired_arms(r: dict) -> set:
    """The arm ids a round retired."""
    return set(r.get("retired_arms") or [])


def ratio_text(r: float) -> str:
    """A ratio for a person: whole from 10 up ("209×"), two significant digits to 0.01 ("2.5×", "0.35×"), "<0.01×"
    under a hundredth (a rule-based arm's speed against a model's), "0×" for none; never scientific notation."""
    if r == 0:
        return "0×"
    if r >= 10:
        return f"{r:,.0f}×"
    if r < 0.01:
        return "<0.01×"
    return f"{r:.2g}×"


def axis_ratios(dec: dict, arm: str, base: str) -> list[str]:
    """The arm against the baseline on each axis beside quality, as ratios ("cost 0.1×"). An axis
    either has no number for is left out; two zeros read "same"."""
    out: list[str] = []
    if arm == base or arm not in dec["rows"] or base not in dec["rows"]:
        return out
    for ax in shown_axes(dec):
        a, b = dec["rows"][arm][ax["name"]]["value"], dec["rows"][base][ax["name"]]["value"]
        stat = "" if ax["stat"] == "mean" else f" {ax['stat']}"
        if a is None or b is None:
            continue
        if b == 0:
            out.append(f"{ax['name']}{stat} same" if a == 0 else f"{ax['name']}{stat} from 0")
        else:
            r = a / b
            out.append(f"{ax['name']}{stat} {ratio_text(r)}")
    return out


def goal_clusters(A, g: dict, ds: str) -> tuple[dict | None, str | None]:
    """({item: cluster key}, field) when the goal's entry for `ds` names `cluster: FIELD`, else (None, None).
    Items with no value for the field are clusters of their own (stats.clustered)."""
    field = next((d.get("cluster") for d in g.get("datasets") or [] if d.get("dataset_id") == ds), None)
    if not field:
        return None, None
    values = item_fields(A, ds).get("values") or {}
    return {i: v[field] for i, v in values.items() if v.get(field) not in (None, "")}, field


#: The decisions kept while a catalog Site renders one state of the data (RFC-040): the home page's glance, the goals
#: page and a goal's own page decide the same groups, 96 decisions on this repository's catalog, 5 of its 30 s.
_KEPT = threading.local()


@contextmanager
def decisions_kept(memo: dict) -> Iterator[None]:
    """Within the block, on this thread, a group's decision is made once and kept in `memo`: for one state of the data
    only (a new state needs a new memo). Each caller gets its own copy, as it would get its own decision."""
    prev = getattr(_KEPT, "memo", None)
    _KEPT.memo = memo
    try:
        yield
    finally:
        _KEPT.memo = prev


def group_decision(
    A,
    g: dict,
    ds: str,
    rows: list,
    gm: str,
    retired_in: dict,
    gold: str | None = None,
) -> dict:
    """`_group_decision`, kept within `decisions_kept`: keyed on everything it is given; what it reads from the adapter
    (the scores, the goal's clusters, a measure's direction) one state of the data fixes."""
    memo = getattr(_KEPT, "memo", None)
    if memo is None:
        return _group_decision(A, g, ds, rows, gm, retired_in, gold)
    key = (
        repr(g),
        ds,
        tuple(
            (r["arm"], r["label"], tuple(r["flags"]), r.get("machine", ""), bool(r.get("baseline")))
            for r in rows
        ),
        gm,
        repr(sorted(retired_in.items())),
        gold,
    )
    if key not in memo:
        memo[key] = _group_decision(A, g, ds, rows, gm, retired_in, gold)
    return copy.deepcopy(memo[key])


def _group_decision(
    A,
    g: dict,
    ds: str,
    rows: list,
    gm: str,
    retired_in: dict,
    gold: str | None = None,
) -> dict:
    """The goal's decision over one group of arms on one dataset (axes.decide): its axes, limits,
    the quality leader, the contenders and the tie-break. A judge's group decides on the judge's score;
    an arm a round retired is shown, never recommended. `gold`: this group is scored against
    silver and that gold reference's group is on the same dataset, so gold decides and this group
    only shows its leader; so does a group measured by unvalidated judges."""
    from evaluation_harness import axes  # noqa: PLC0415

    crit = g.get("success_criteria") or {}
    goal = g
    if gm != (crit.get("primary") or {}).get("measure"):
        own = {k: v for k, v in (crit.get("axes") or {}).items() if k != "quality"}
        goal = {
            **g,
            "success_criteria": {**crit, "primary": {"measure": gm}, "axes": own},
        }
    arms = {
        r["arm"]: {
            "label": r["label"],
            "flags": list(r["flags"]) + (["retired"] if retired_round(retired_in, r["arm"]) else []),
            "scores": A.scores(r["arm"]),
        }
        for r in rows
    }
    machines = {r["arm"]: r.get("machine", "") for r in rows}
    baseline = next((r["arm"] for r in rows if r.get("baseline")), None)
    clusters, cluster_by = goal_clusters(A, g, ds)
    dec = axes.decide(
        goal,
        arms,
        lambda m: "lower" if A.lower_is_better(m, ds) else None,
        machines,
        baseline=baseline,
        clusters=clusters,
        cluster_by=cluster_by,
    ) | {"goal": goal, "dataset": ds}
    if not decides_on(g, ds):
        # The goal never decides here (a pilot slice, a generalization check): the leader stands, the
        # recommendation does not.
        role = next((d.get("role") for d in g.get("datasets") or [] if d.get("dataset_id") == ds), "") or ""
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still undecided"))],
            f"The goal does not decide on {ds}"
            + (f" ({role})" if role else "")
            + ": shown, not recommended.",
        ]
    elif gold:
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still undecided"))],
            (
                f"Scored against silver, beside {gold}: gold decides on {ds}; this group is shown, not "
                "recommended. Silver is not what the goal decides on: a model's opinion (its author's "
                "family ranks higher on it) or what production recorded afterwards; its caveat says which."
            ),
        ]
    elif gm != (crit.get("primary") or {}).get("measure") and not gm.endswith("_unvalidated"):
        # A re-measurement (a judge's grade, pick or pairwise, or a scorer's other metric): the goal recommends from
        # the group it decides on, its own measure; this one shows its leader beside it (owner, 2026-11-03).
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still undecided"))],
            (
                f"Read on {gm}: the goal decides on {(crit.get('primary') or {}).get('measure')}; this group is "
                "shown, not recommended."
            ),
        ]
    elif gm.endswith("_unvalidated"):
        dec["recommended"] = None
        dec["shown_only"] = True
        dec["why"] = [
            *[w for w in dec["why"] if not w.startswith(("Recommended:", "Still undecided"))],
            (
                f"{gm}: judges never compared with people for this use, a trial rather than a "
                "measurement; this group is shown, not recommended."
            ),
        ]
    return dec


def ref_tier(tiers: dict, key: str) -> str:
    """A group's reference tier: as the references listing says, else from its id (gold/<dataset>,
    silver/<dataset>), for a reference this checkout does not hold (gold not redistributed)."""
    return tiers.get(key) or (key.split("/", 1)[0] if key.startswith(("gold/", "silver/")) else "")


def gold_beside(tiers: dict, groups: list, key: str) -> str | None:
    """The gold reference a silver-scored group sits beside on its dataset, or None: a silver group
    with a gold one next to it never recommends (group_decision's `gold`)."""
    if ref_tier(tiers, key) != "silver":
        return None
    return next((x["key"] for x in groups if ref_tier(tiers, x["key"]) == "gold"), None)


def decides_on(g: dict, ds: str) -> bool:
    """Whether the goal decides on this dataset (`decides: false` on a goal dataset: never)."""
    return next((d.get("decides", True) for d in g.get("datasets") or [] if d.get("dataset_id") == ds), True)


def shown_axes(dec: dict) -> list:
    """The axes beside quality that some arm in the group records (cost counts its tokens too)."""
    return [
        ax
        for ax in dec["axes"][1:]
        if any(
            row[ax["name"]]["n"] or (row[ax["name"]].get("tokens") or {}).get("n")
            for row in dec["rows"].values()
        )
    ]


# -- the baseline --------------------------------------------------------------------------------------------------


def baseline_read(v: dict, goal_id: str) -> tuple[list, str | None]:
    """A dataset's baselines for a goal, and the arm the goal reads for the latest one: its latest re-score when
    it was re-scored (RFC-022), as the goal page reads it, else the promoted arm itself."""
    bl = [x for x in v.get("baselines", []) if x.get("goal") == goal_id]
    base = bl[-1]["arm"] if bl and bl[-1].get("arm") else None
    moved = next((a.get("superseded_by") for a in v.get("arms", []) if base and a["arm"] == base), None)
    return bl, moved or base


def baseline_gap(A, dec: dict, rows: list, gm: str) -> dict | None:
    """When the rule recommends another arm than the promoted baseline in this group: the recommended arm against the
    baseline on quality, one paired test (family 1, not corrected: the strategy picked the arm, not the best mean), as
    {"recommended", "baseline", "measure", "delta", "p", "verdict", "family"}; None when it recommends the baseline,
    there is none, or the arms share nothing to test."""
    from evaluation_harness import stats  # noqa: PLC0415

    rec = dec["recommended"]
    base = next((r for r in rows if r.get("baseline")), None)
    if not rec or base is None or base["arm"] == rec:
        return None
    higher = dec["axes"][0]["direction"] == "higher"
    series = {a: (A.scores(a).get(gm) or {}).get("values") or {} for a in (rec, base["arm"])}
    clusters = goal_clusters(A, dec.get("goal") or {}, dec.get("dataset") or "")[0]
    row = (
        stats.compare(series, base["arm"], higher_is_better=higher, family=1, clusters=clusters).get("rows")
        or [None]
    )[0]
    if not row or row.get("p") is None:
        return None
    return {
        "recommended": rec,
        "baseline": base["arm"],
        "measure": gm,
        "delta": row["delta"],
        "p": row["p"],
        "verdict": row.get("verdict", ""),
        "family": 1,
    }


def leader_vs_baseline(
    A, g: dict, ds: str, rows: list, dec: dict | None, base: str | None, measure: str
) -> dict | None:
    """The group's leader (the decision's: never a flagged or retired arm) against the baseline: the paired test,
    corrected for the arms the leader was chosen from (every other arm of the group), as a round's evidence reads its
    leader against the baseline it started from; None without a leader, a baseline, or a test."""
    from evaluation_harness import stats  # noqa: PLC0415

    leader = next((r for r in rows if dec and r["arm"] == dec["leader"]), None)
    if not (leader and base and leader["arm"] != base):
        return None
    lower = lower_on(A, g, measure, ds)
    cmp = stats.compare(
        {
            leader["arm"]: (A.scores(leader["arm"]).get(measure) or {}).get("values") or {},
            base: (A.scores(base).get(measure) or {}).get("values") or {},
        },
        base,
        higher_is_better=not lower,
        family=1,
        clusters=goal_clusters(A, g, ds)[0],
    )
    row = (cmp.get("rows") or [None])[0]
    return corrected(row, len([r for r in rows if r["arm"] != base])) if row else None


# -- the goals at a glance -----------------------------------------------------------------------------------------


def glance(A, by_ds: dict) -> list[dict]:
    """Per goal and dataset: the deciding measure, the promoted baseline, the leader of the gold
    group, the paired test of the leader against the baseline (corrected for the arms it was chosen from), and what
    the goal's strategy recommends with its cost and speed against the baseline."""
    rows = []
    for g in A.goals():
        prim = (g.get("success_criteria") or {}).get("primary") or {}
        measure = prim.get("measure", "")
        retired_in = retired_in_of(A, g)
        for ans in goal_answers(g, by_ds, A):
            ds = ans["dataset"]
            lower = lower_on(A, g, measure, ds)
            if not decides_on(g, ds):
                continue  # a pilot slice or a generalization check: on the goal page, not the glance
            v = by_ds.get(ds) or {}
            bl, base = baseline_read(v, g["goal_id"])
            # The gold group decides; without one, the first group scored against a reference,
            # named in the row so it is never read as gold.
            tiers = {r["id"]: r["tier"] for r in v.get("refs", [])}

            plain = [x for x in ans["groups"] if not x["key"].startswith("judge ")]
            grp = next((x for x in plain if ref_tier(tiers, x["key"]) == "gold"), plain[0] if plain else None)
            dec = (
                group_decision(
                    A,
                    g,
                    ds,
                    grp["rows"],
                    measure,
                    retired_in,
                )
                if grp
                else None
            )
            # The decision's leader: the best arm it may recommend, so never a retired or flagged one.
            leader = (
                next((r for r in grp["rows"] if dec and r["arm"] == dec["leader"]), None) if grp else None
            )
            label = {x["arm"]: x["label"] for x in v.get("arms", [])}
            test = leader_vs_baseline(A, g, ds, grp["rows"], dec, base, measure) if grp else None
            rec = dec["recommended"] if dec else None
            rows.append(
                {
                    "goal": g,
                    "dataset": ds,
                    "measure": measure,
                    "lower": lower,
                    "baseline": base,
                    "baseline_label": label.get(base, base) if base else "",
                    "baseline_reason": bl[-1].get("reason", "") if bl else "",
                    "baseline_mean": _mean(v, base, measure) if base else None,
                    "leader": leader["arm"] if leader else None,
                    "leader_label": leader["label"] if leader else "",
                    "leader_mean": leader["mean"] if leader else None,
                    "test": test,
                    "group": grp["key"] if grp else "",
                    "gold": grp is not None and ref_tier(tiers, grp["key"]) == "gold",
                    "recommended": rec,
                    "recommended_label": label.get(rec, rec) if rec else "",
                    "strategy": strategy_of(dec["goal"]) if dec else strategy_of(g),
                    # The recommendation against the baseline on cost, speed and the goal's own axes.
                    "vs_baseline": axis_ratios(dec, rec, base) if dec and rec and base else [],
                    # The decision's reasons, as the goal page lists them.
                    "why": list(dec["why"]) if dec else [],
                    # The decision itself (the arms page reads its eligible arms and draws its trade-off).
                    "dec": dec,
                    "retired": retired_in,
                }
            )
    return rows


def _mean(v: dict, arm: str, measure: str):
    a = next((x for x in v.get("arms", []) if x["arm"] == arm), None)
    return a["means"][measure][0] if a and measure in a["means"] else None


# -- one dataset, as the goal reads it ------------------------------------------------------------------------------


def dataset_groups(A, by_ds: dict, ds: str, goal: dict | None = None) -> list[dict]:
    """The groups of one dataset as the goal reads them (`decided`: each with its decision), or, with no goal, every arm
    on its own headline grouped by what it is scored against (no decision): the tables of `evh leaderboard`."""
    if goal is None:
        answers = goal_answers({"goal_id": "", "datasets": [{"dataset_id": ds}]}, by_ds, A)
    else:
        answers = decided(
            A,
            {**goal, "datasets": [d for d in goal.get("datasets") or [] if d.get("dataset_id") == ds]},
            by_ds,
        )
    return answers[0]["groups"] if answers else []


# -- the goal's leaderboard ----------------------------------------------------------------------------------------


def leaderboard(
    A, goal_id: str, by_ds: dict | None = None, arms: list[str] | None = None, top: int | None = None
) -> dict:
    """Where each arm of the goal stands, as the goal page shows it: per dataset, per reference scored against, every arm's
    row (`_goal_view.group_values`: its mean and items, flags, the paired test against the group's leader, the contender
    test, its means on the goal's axes), the leader, the contenders, the recommended arm, the promoted baseline, the
    recommended arm against it (`baseline_gap`) and the leader against it, corrected (`leader_vs_baseline`, in the group the baseline is in).

    `arms` (patterns: an arm or system id that contains one, or fits it as a glob) and `top` (the first N arms in the goal's
    own order) choose the rows shown: the decision above them was made over every arm, and the baseline, the leader and the
    recommended arm are always shown."""
    from evaluation_harness import _exposure, _goal_view, _looks  # noqa: PLC0415
    from evaluation_harness import catalog_build as cb  # noqa: PLC0415
    from evaluation_harness.axes import STRATEGIES, tie_break_of  # noqa: PLC0415
    from evaluation_harness.model import arm_views  # noqa: PLC0415
    from evaluation_harness.model.entity import Problem  # noqa: PLC0415

    pats = _goal_view.patterns(arms)
    if top is not None and top < 1:
        raise Problem(f"top must be at least 1, not {top}", "bad-argument")

    goals = A.goals()
    g = next((x for x in goals if x["goal_id"] == goal_id), None)
    if g is None:
        raise Problem(
            f"no goal {goal_id!r}: one of {', '.join(x['goal_id'] for x in goals) or '(none)'}", "not-found"
        )
    by_ds = by_dataset(A) if by_ds is None else by_ds
    retired_in = retired_in_of(A, g)
    prim = (g.get("success_criteria") or {}).get("primary") or {}
    datasets = []
    for ans in decided(A, g, by_ds):
        ds = ans["dataset"]
        bl, base = baseline_read(by_ds.get(ds) or {}, goal_id)
        tiers = {r["id"]: r["tier"] for r in (by_ds.get(ds) or {}).get("refs", [])}
        groups = []
        for grp in ans["groups"]:
            rows, dec, gm = grp["rows"], grp["dec"], grp["measure"]
            base_arm = next((r["arm"] for r in rows if r.get("baseline")), None)
            on_show = _goal_view.select(
                rows, pats, top, {x for x in (base_arm, dec["leader"], dec["recommended"]) if x}
            )
            hyps = {r["arm"]: _goal_view.hypothesis_of(A, r["arm"]) for r in on_show}
            groups.append(
                _goal_view.group_values(
                    dataset=ds,
                    scored_against=grp["key"],
                    measure=gm,
                    dec=dec,
                    rows=rows,
                    shown=on_show,
                    axes=shown_axes(dec),
                    baseline=base_arm,
                    hypotheses={a: h for a, h in hyps.items() if h},
                    retired={r["arm"]: retired_round(retired_in, r["arm"]) for r in on_show},
                    arms_filter=pats,
                    top=top,
                )
                | {
                    "axes_shown": shown_axes(dec),
                    "row_kinds": {r["arm"]: arm_views.kind(r, tiers) for r in on_show},
                    "why": list(dec["why"]),
                    "baseline_gap_text": cb.baseline_gap(A, dec, rows, gm),
                    "baseline_gap": baseline_gap(A, dec, rows, gm),
                    "leader_vs_baseline": leader_vs_baseline(A, g, ds, rows, dec, base, gm)
                    if any(r["arm"] == base for r in rows)
                    else None,
                }
            )
        datasets.append(
            {
                "dataset": ds,
                "role": ans["role"],
                "decides": decides_on(g, ds),
                "notes": ans["notes"],
                "looks": _looks.said(ds, getattr(A, "data_dir", None)),
                "exposure": _exposure.line(ds, getattr(A, "data_dir", None)),
                "baseline": (
                    {k: bl[-1].get(k) for k in ("version", "run", "reason", "promoted_at", "tier")}
                    | {"arm": base}
                    if bl
                    else None
                ),
                "groups": groups,
            }
        )
    studies = getattr(A, "studies", None)
    rounds_of = getattr(A, "rounds", None)
    answer = []
    for d in g.get("datasets") or []:
        b, read = baseline_read(by_ds.get(d.get("dataset_id", "")) or {}, goal_id)
        answer.append(
            {
                "dataset": d.get("dataset_id", ""),
                "baseline": {k: b[-1].get(k) for k in ("run", "promoted_at", "reason")} | {"arm": read}
                if b
                else None,
            }
        )
    per_ds = {
        str(d["dataset_id"]): "lower"
        if lower_on(A, g, str(prim.get("measure", "")), str(d["dataset_id"]))
        else "higher"
        for d in g.get("datasets") or []
        if d.get("dataset_id")
    }
    return {
        "goal": goal_id,
        "item_word": getattr(A, "item_word", "item"),
        "title": g.get("title") or goal_id,
        "statement": g.get("statement", ""),
        "decision": g.get("decision", ""),
        "guardrails": list((g.get("success_criteria") or {}).get("guardrails") or []),
        "links": [x for x in g.get("links") or [] if x.get("url")],
        "studies": (studies(goal_id) if callable(studies) else []) or [],
        "rounds": [
            {
                "round": r["round_id"],
                "status": r.get("status", ""),
                "arms": len(r.get("arms") or []),
                "retired": sum(1 for x in r.get("arm_records") or [] if x.get("retired")),
                "conclusion": (r.get("conclusion") or {}).get("text", ""),
            }
            for r in (rounds_of() if callable(rounds_of) else [])
            if r.get("goal") == goal_id
        ],
        "answer": answer,
        "measure": prim.get("measure", ""),
        "direction": _runs.combine(per_ds),
        "direction_on": per_ds,
        "strategy": strategy_of(g),
        "strategy_about": STRATEGIES[strategy_of(g)],
        "tie_break": list(tie_break_of(g)),
        "datasets": datasets,
    }
