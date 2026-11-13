"""Rounds (RFC-032 step 5): a round's arms as it stores them, and its evidence, computed once.

A round (data/rounds/<goal>/<r>.yaml) keeps its arms: each a system read under one label (the arm's id is
`<label prefix>/<dataset>/<system>`, model/runs.arm_id), the runs it is read through, how and when it entered, and its
retirement. `evidence(goal, round)` is what every view of a round reads: `evh rounds`, the goal page, the inspector's
`--round`, pair-test's and family-test's `--round` and the API (owner, 2026-11-13). Its leader is read as a goal
decides: among the gold-scored arms where there are any, never a judged arm, never the arm that wrote the reference it
is scored against."""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import Any

from evaluation_harness import _common, _rounds, _store
from evaluation_harness import catalog_serve as cs
from evaluation_harness._common import load_goals, read_json
from evaluation_harness.model import runs as model_runs
from evaluation_harness.stats import fmt_p

# -- the stored arms -------------------------------------------------------------------------------------------------


def arms(rnd: dict[str, Any]) -> list[dict[str, Any]]:
    """A round's arms as it stores them."""
    return [a for a in rnd.get("arms") or [] if isinstance(a, dict) and a.get("system")]


def in_play(rnd: dict[str, Any]) -> list[dict[str, Any]]:
    """The round's arms not retired."""
    return [a for a in arms(rnd) if not a.get("retired")]


def arm_id(rnd: dict[str, Any], arm: dict[str, Any]) -> str:
    """The arm's id as the catalog and the inspector name it: `<label prefix>/<dataset>/<system>`."""
    return f"{model_runs.arm_prefix(str(arm.get('label') or ''))}/{rnd['dataset_id']}/{arm['system']}"


def arm_ids(rnd: dict[str, Any]) -> list[str]:
    """The ids of the round's arms in play."""
    return [arm_id(rnd, a) for a in sorted(in_play(rnd), key=lambda a: a["system"])]


def retired_ids(rnd: dict[str, Any]) -> list[str]:
    """The ids of the round's retired arms."""
    return [arm_id(rnd, a) for a in arms(rnd) if a.get("retired")]


def find_arm(rnd: dict[str, Any], system: str) -> dict[str, Any] | None:
    """The round's arm of a system, in play first."""
    found = [a for a in arms(rnd) if a["system"] == system]
    return next((a for a in found if not a.get("retired")), found[0] if found else None)


def entered(how: str, who: dict[str, Any] | None = None, frm: str | None = None) -> dict[str, Any]:
    """How an arm entered a round, now."""
    e: dict[str, Any] = {"how": how, "at": _common.now()}
    if frm:
        e["from"] = frm
    if who:
        e["actor"] = who
    return e


def add_run(
    rnd: dict[str, Any], system: str, run_id: str, who: dict[str, Any] | None = None, label: str = ""
) -> dict[str, Any] | None:
    """A run made in the round joins its system's arm read under `label`, the label of the run's own score (a
    re-timing on another machine is read as "linux", not as the plain runs), or adds that arm; returns the arm. A
    retired arm the run joins is back in play: a run made after the retirement brings the system back. None, and
    nothing changed, when the round reads the system under a re-score and the run is not one yet: it is read in the
    round once the round's runs are re-scored (`evh rescore --goal G --round R`)."""
    same = [a for a in arms(rnd) if a["system"] == system and str(a.get("label") or "") == label]
    rescored = [
        a for a in in_play(rnd) if a["system"] == system and str(a.get("label") or "").startswith("rescored ")
    ]
    if not same and rescored and not label:
        return None
    arm = next((a for a in same if not a.get("retired")), same[0] if same else None)
    if arm is None:
        arm = {
            "system": system,
            **({"label": label} if label else {}),
            "runs": [],
            "entered": entered("ran", who),
        }
        rnd.setdefault("arms", []).append(arm)
    if run_id not in arm.setdefault("runs", []):
        arm["runs"].append(run_id)
    arm.pop("retired", None)
    return arm


def carry(
    rnd: dict[str, Any], system: str, label: str, runs: list[str], frm: str | None, who: dict[str, Any] | None
) -> dict[str, Any]:
    """An arm carried (or adopted) into the round unchanged: read under `label` through `runs`."""
    arm: dict[str, Any] = {"system": system, **({"label": label} if label else {}), "runs": sorted(runs)}
    arm["entered"] = entered("carried", who, frm)
    rnd.setdefault("arms", []).append(arm)
    return arm


def retire(
    rnd: dict[str, Any], system: str, reason: str, who: dict[str, Any] | None, label: str | None = None
) -> dict[str, Any] | None:
    """Retire the system's arm in play (the one read under `label`, when given); the arm, or None when it has none in
    play."""
    arm = next(
        (
            a
            for a in in_play(rnd)
            if a["system"] == system and (label is None or str(a.get("label") or "") == label)
        ),
        None,
    )
    if arm is not None:
        arm["retired"] = {"at": _common.now(), "reason": reason, **({"actor": who} if who else {})}
    return arm


# -- the evidence ----------------------------------------------------------------------------------------------------


def _authors(A, ds: str) -> dict[str, str]:
    """{arm: the silver reference it wrote} on this dataset."""
    return {a: rid for rid, a in _silver_authors(A, ds)}


def comparable(A, arms_: list[str]) -> list[str]:
    """The arms a leader is read from, as a goal decides: on gold where any arm is, never a judged arm, never the
    arm that wrote the reference it is scored against (it scores 1.0 on its own outputs)."""
    if not arms_:
        return []
    ds = arms_[0].split("/")[-2]
    wrote = _authors(A, ds)
    ref = {a: str(A.describe(a).get("reference") or "") for a in arms_}
    keep = [
        a
        for a in arms_
        if not a.split("/", 1)[0].startswith("judged-") and not (a in wrote and wrote[a] == ref[a])
    ]
    gold = [a for a in keep if ref[a].startswith("gold/")]
    return gold or keep


def _best(A, arms: list[str], metric: str, lower: bool) -> str | None:
    """The leader: the best mean on the metric among the arms a leader is read from (`comparable`)."""
    means = {}
    for a in comparable(A, arms):
        vals = (A.scores(a).get(metric) or {}).get("values") or {}
        if vals:
            means[a] = statistics.fmean(vals.values())
    if not means:
        return None
    return (min if lower else max)(means, key=lambda a: means[a])


def _arm(A, dataset: str, config_id: str) -> str:
    """The adapter's arm id for a system (arm_of), else the harness's layout."""
    fn = getattr(A, "arm_of", None)
    return fn(dataset, config_id) if callable(fn) else f"runs/{dataset}/{config_id}"


def _dirs(A, arm: str) -> list:
    """The run directories behind an arm, where the adapter can say (HarnessAdapter)."""
    fn = getattr(A, "_dirs", None)
    return list(fn(arm)) if callable(fn) else []


def _cost_per_item(A, arm: str) -> float | None:
    vals = (A.scores(arm).get("cost_usd") or {}).get("values") or {}
    return statistics.fmean(vals.values()) if vals else None


def _silver_authors(A, ds: str) -> list[tuple[str, str]]:
    """(reference id, arm) for each silver reference of this dataset whose author is a run here:
    the frontier arm whose outputs became the reference, read from its manifest."""
    out = []
    root = _common.REFERENCES / "silver"
    known = set(A.arms())
    for mf in sorted(_store.glob(root, "*/manifest.json")) if _store.is_dir(root) else []:
        m = read_json(mf)
        cid = _common.system_now((m.get("from_run") or {}).get("config_id") or m.get("authored_by"))
        if m.get("dataset_id") == ds and cid and _arm(A, ds, cid) in known:
            out.append((f"silver/{mf.parent.name}", _arm(A, ds, cid)))
    return out


def _against(A, label: str, other: str, leader: str, metric: str) -> dict | None:
    d = cs.compare({"runs": [f"{other},{leader}"], "baseline": [other], "metric": [metric]})
    row = next(iter(d.get("rows") or []), None)
    if not row:
        return None
    return {"label": label, "other": other, "verdict": row["verdict"], "p": row["p"], "delta": row["delta"]}


def _against_family(A, label: str, other: str, leader: str, arms: list[str], metric: str) -> dict | None:
    """The leader against `other`, corrected for having been chosen from the round's arms. The leader
    is the best mean of the round, so testing it alone, uncorrected, would count the luck of the choice
    as evidence (a selection effect). Bonferroni over the round's arms (every one could have been the
    leader): significant only when p x K <= 0.05. Conservative, and it needs no more than the one
    paired test, read as the inspector reads it (re-scored where the arms are)."""
    row = _against(A, label, other, leader, metric)
    if not row:
        return None
    k = max(1, len([a for a in arms if a != other]))
    p_adj = min(1.0, row["p"] * k) if row.get("p") is not None else None
    verdict = row["verdict"]
    if verdict.startswith("significant") and (p_adj is None or p_adj > 0.05):
        verdict = "not significant"
    return {**row, "verdict": verdict, "p_adjusted": p_adj, "family": k}


def _promote_hold(
    against: list[dict], prev_id: str | None, tied: Sequence[str] = (), scorers_differ: bool = False
) -> str:
    """Why a round's leader is not to be promoted, from its `against` rows, or "" to promote it: it
    must be significantly better than the baseline the round started from (corrected for the round's
    arms, as it was chosen from them), not significantly worse than the previous round's best, and
    separated from the other arms of the round. A mean that leads by chance is no reason to promote,
    and neither is a test the round's own notes say not to read."""
    row_of = {r["label"]: r for r in against}
    vs_base = row_of.get("the baseline it started from")
    vs_prev = next((r for k, r in row_of.items() if k.endswith("'s best")), None)

    def said(r: dict) -> str:
        fam = (
            f", Bonferroni over {r['family']} arms: {fmt_p(r['p_adjusted'])}"
            if r.get("family", 1) > 1 and r.get("p_adjusted") is not None
            else ""
        )
        return f"{r['verdict']}, Δ {r['delta']:+.4f}, p {fmt_p(r['p'])}{fam}"

    if scorers_differ:
        return "measured by different scorers: re-score the arms before reading the test"
    if vs_base is not None and vs_base["verdict"] != "significant: better":
        return f"not ahead of the baseline it started from ({said(vs_base)})"
    if prev_id and vs_prev is not None and vs_prev["verdict"] == "significant: worse":
        return f"behind {prev_id}'s best ({said(vs_prev)})"
    if tied:
        shown = ", ".join(tied[:5]) + (f" and {len(tied) - 5} more" if len(tied) > 5 else "")
        return (
            f"not separated from {shown} (not significantly different after Holm): the goal's tie-break picks among "
            "them, and `evh goals --goal` names the arm it recommends"
        )
    return ""


def evidence(goal: str, rnd: dict, A: Any = None) -> dict:
    """What the evidence says about a round, read as the inspector reads it: its arms against its
    leader; its leader against the previous round's best, the baseline it started from and the arm
    that wrote a silver reference of the dataset (`against`); spend and cost per item; and the
    decisions that follow, each with its command."""
    g = load_goals().get(goal) or {}
    prim = (g.get("success_criteria") or {}).get("primary") or {}
    metric, lower = prim.get("measure", ""), prim.get("direction") == "lower"
    # The project's own catalog adapter (--adapter, else config.yaml), as the pages read it.
    if A is None:
        from evaluation_harness.catalog_adapter import load_catalog_adapter  # noqa: PLC0415

        A = load_catalog_adapter(None)
    cs.set_adapter(A)
    ds = rnd["dataset_id"]
    stored = arm_ids(rnd)
    rescored = [a for a in stored if a.startswith("rescored-")]
    moved = sorted({a.split("/")[0].removeprefix("rescored-") for a in rescored})
    known = set(A.arms())
    arms = [a for a in stored if a in known]
    out: dict[str, Any] = {
        "metric": metric,
        "arms": arms,
        "rows": [],
        "against": [],
        "suggest": [],
        "notes": (
            [f"{len(rescored)} arm(s) read from their re-score by {', '.join(moved)}"] if moved else []
        ),
    }
    # ONE INSTRUMENT PER ROUND (the fleet's feedback 17): harness code taken mid-round measures some arms with
    # other code than the rest. Named, never refused: the change may not touch what was measured.
    split = _rounds.off_harness(rnd)
    if split:
        had = (rnd.get("harness") or {}).get("version")
        out["notes"].append(
            f"{len(split)} run(s) ran on other harness code than the round opened on ({had}, code "
            f"{str(rnd['harness']['code_sha256'])[:12]}): "
            + ", ".join(
                f"{rid} ({h.get('version')}, code {str(h.get('code_sha256'))[:12]})" for rid, h in split
            )
            + f"; to compare like with like, {_rounds.how_to_run_on(rnd)}"
        )
    # ONE REFERENCE PER ROUND: a silver mean beside a gold mean is not a comparison. The round is
    # read against the reference most of its arms are scored against (gold before silver on a
    # tie); an arm on another one is named and left out, never silently.
    ref_of = {a: A.describe(a).get("reference") or "" for a in arms}
    if len(set(ref_of.values())) > 1:
        from collections import Counter  # noqa: PLC0415

        count = Counter(ref_of.values())
        rank = {"gold": 0, "silver": 1}
        ref = min(count, key=lambda r: (-count[r], rank.get(r.split("/")[0], 2), r))
        off = [a for a in arms if ref_of[a] != ref]
        out["notes"].append(
            f"read against {ref or 'no reference'}; not compared: "
            + ", ".join(f"{a.rsplit('/', 1)[-1]} (scored against {ref_of[a] or 'no reference'})" for a in off)
            + " — run them again to score them against it"
        )
        arms = [a for a in arms if ref_of[a] == ref]
        out["arms"] = arms
        out["reference"] = ref
    round_ref = out.get("reference") or next(iter(set(ref_of.values())), "")
    spent = sum((m.get("scores") or {}).get("total_cost_usd") or 0 for _, m in _rounds.runs_of(rnd))
    out["spent"] = spent
    if rnd.get("budget_usd") is not None:
        line = f"spent ${spent:.4f} of ${rnd['budget_usd']:.2f}"
        if rnd.get("status") != "closed":
            # What a spending command would be given now (RFC-026 step 5): running commands' reservations and a
            # stopped run's paid items counted, as the commands count them.
            from evaluation_harness import _spend  # noqa: PLC0415

            left = _spend.round_left(rnd)
            out["left"] = None if left is None else round(left, 8)
            if left is not None and abs(rnd["budget_usd"] - spent - left) > 1e-9:
                line += f"; ${max(left, 0):.4f} left, counting what running or stopped commands hold"
        out["notes"].append(line + (" — over budget" if spent > rnd["budget_usd"] else ""))
    leader = _best(A, arms, metric, lower)
    out["leader"] = leader
    if not leader:
        out["notes"].append(
            f"no arm in {rnd['round_id']} records {metric} yet: run them (evh run --system <id> --dataset <id> --goal {rnd['goal']} --round {rnd['round_id']})"
        )
        return out
    # The arm the round started from: the goal's promoted baseline, never suggested for retirement.
    base_run = rnd.get("baseline")
    barm = (
        next(
            (
                a
                for a in known
                if a.startswith(_arm(A, ds, ""))
                and any(model_runs.run_of(d).name == base_run for d in _dirs(A, a))
            ),
            None,
        )
        if base_run
        else None
    )
    # Read the baseline as the round reads its arms: its latest re-score where it has one. Its original
    # arm is scored differently from the re-scored arms beside it, so the paired test had no rows and the
    # rule "a leader must beat the baseline" never ran.
    if barm:
        held = find_arm(rnd, barm.rsplit("/", 1)[-1])
        barm = arm_id(rnd, held) if held is not None else barm
    level: list[str] = []  # the arms the leader is not separated from, after Holm
    if len(arms) > 1:
        from evaluation_harness import stats  # noqa: PLC0415

        if len(arms) <= cs.LIMITS["max_arms"]:
            d = cs.compare({"runs": [",".join(arms)], "baseline": [leader], "metric": [metric]})
        else:
            # More arms than the inspector compares in one request: the same paired test, Holm across them,
            # read from the scores directly. The request's refusal used to leave the rows empty, without a word.
            series = {a: (A.scores(a).get(metric) or {}).get("values") or {} for a in arms}
            d = stats.compare(series, leader, higher_is_better=not lower, clusters=cs.goal_clusters_on(ds)[0])
        if d.get("error"):
            out["notes"].append(f"no comparison: {d['error']}")
        out["rows"] = d.get("rows") or []
        out["notes"] += [
            w
            for w in [*(d.get("warnings") or []), *((d.get("conditions") or {}).get("warnings") or [])]
            if w not in out["notes"]
        ]
        # Scored against its own silver, the arm that wrote it is the yardstick, not a contender:
        # losing to the leader there is the finding, not a reason to drop it. Against gold it is an
        # arm like any other. The baseline the round started from is the goal's, not the round's to
        # retire: promoting the leader on close replaces it.
        authors = {a for rid, a in _silver_authors(A, ds) if rid == round_ref}
        for r in out["rows"]:
            cid = r["arm"].rsplit("/", 1)[-1]
            if r["verdict"] == "significant: worse" and r["arm"] not in authors and r["arm"] != barm:
                reason = f"significantly worse than {leader.rsplit('/', 1)[-1]} on {metric} after Holm (p {fmt_p(r['p'])})"
                out["suggest"].append(
                    (
                        f"retire {cid}",
                        f'evh round-retire --goal {goal} --round {rnd["round_id"]} --arm {cid} --reason "{reason}"',
                    )
                )
        level = [r["arm"].rsplit("/", 1)[-1] for r in out["rows"] if r["verdict"] == "not significant"]
        if level:
            out["suggest"].append(
                (
                    f"{len(level)} arm(s) not significantly different from the leader ({', '.join(level)}): more items may tell them apart",
                    f"evh rank-stability --dataset-id {ds}",
                )
            )
    prev = _rounds.find(goal, rnd["from"]) if rnd.get("from") else None
    if prev:
        pbest = _best(A, [a for a in arm_ids(prev) if a in known], metric, lower)
        if pbest and pbest != leader and prev["dataset_id"] == ds:
            row = _against(A, f"{prev['round_id']}'s best", pbest, leader, metric)
            if row:
                out["against"].append(row)
                if row["verdict"] != "significant: better":
                    how = (
                        "is significantly worse than"
                        if row["verdict"] == "significant: worse"
                        else "is not significantly different from"
                    )
                    out["suggest"].append(
                        (
                            f"{rnd['round_id']}'s best {how} {prev['round_id']}'s ({pbest.rsplit('/', 1)[-1]}): change course, or close",
                            "",
                        )
                    )
    if barm and barm != leader:
        row = _against_family(A, "the baseline it started from", barm, leader, arms, metric)
        if row:
            out["against"].append(row)
    # The frontier arm whose outputs became a silver reference: how close the leader comes to it,
    # scored on the same references as the round, and at what cost per item.
    for ref_id, author in _silver_authors(A, ds):
        if author != leader:
            row = _against(A, f"the arm that wrote {ref_id}", author, leader, metric)
            if row:
                out["against"].append(row)
    costs = {a: _cost_per_item(A, a) for a in [leader, *(r["other"] for r in out["against"])]}
    priced = {a: c for a, c in costs.items() if c is not None}
    if priced:
        out["cost_per_item"] = priced
        out["notes"].append(
            "cost per item: " + ", ".join(f"{a.rsplit('/', 1)[-1]} ${c:.6f}" for a, c in priced.items())
        )
    lead_run = (
        sorted(model_runs.run_of(d).name for d in _dirs(A, leader))[0] if _dirs(A, leader) else "<run_id>"
    )
    # Promote only what is not already the baseline: the leader may be the run the round began from.
    already = lead_run == rnd.get("baseline") or any(
        model_runs.run_of(d).name == rnd.get("baseline") for d in _dirs(A, leader)
    )
    # And only a leader the evidence puts ahead: significantly better than the baseline it started from,
    # and not behind the previous round's best. A mean that leads by chance is no reason to promote.
    scorers_differ = any("different scorers" in n for n in out["notes"])
    hold = _promote_hold(out["against"], prev["round_id"] if prev else None, level, scorers_differ)
    promote = not already and not hold
    out["suggest"].append(
        (
            "close the round with what it showed"
            + (f" ({leader.rsplit('/', 1)[-1]} is already the baseline)" if already else "")
            + (f", promoting nothing: {leader.rsplit('/', 1)[-1]} is {hold}" if hold and not already else ""),
            f'evh round-close --goal {goal} --round {rnd["round_id"]} --conclusion "..."'
            + (f" --promote {lead_run}" if promote else ""),
        )
    )
    return out
