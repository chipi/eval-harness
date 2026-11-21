"""The goal's decision, made once (RFC-032 step 8): model/goal_views.

    python tests/test_goal_views.py

On a stand-in adapter (no project): one rule for which arms a leader may be read from (a goal and a round share it),
the leader against the baseline corrected for the arms it was chosen from, the baseline's gap as one comparison, the
goal's leaderboard (`goal-leaderboard`) and a dataset read without a goal (`evh leaderboard`).
"""

import sys
from pathlib import Path
from typing import Any, cast

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
from evaluation_harness import catalog_build as cb  # noqa: E402
from evaluation_harness import catalog_serve, stats  # noqa: E402
from evaluation_harness._check import check, summary  # noqa: E402
from evaluation_harness.model import goal_views as gv  # noqa: E402
from evaluation_harness.model.entity import Problem  # noqa: E402
from evaluation_harness.ops import registry  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/: the fixture
from _goal_fixture import DS, GOAL, GOLD, SILVER, A, arm  # noqa: E402

AA = cast(Any, A)
gold_arms = [a for a in A.arms() if a.startswith("runs/")]

# -- one list of flags: the page's rows and the leader rule read it -----------------------------------------------
check(
    "flags_of: too few items, a format outside the contract, the arm that wrote its reference, in that order",
    gv.flags_of(GOAL, 20, "json", True)
    == ["n 20 < min_items 40", "format json not in the contract", "wrote the reference it is scored against"],
)
check(
    "flags_of: nothing held against an arm that meets the contract",
    gv.flags_of(GOAL, 40, "text", False) == [],
)
check(
    "flags_of: a goal with no min_items or contract holds only the written reference",
    gv.flags_of({}, 3, "json", False) == [] and gv.flags_of({}, 3, "json", True) != [],
)

by_ds = gv.by_dataset(AA)
rows = {r["arm"]: r for r in by_ds[DS]["arms"]}
check(
    "by_dataset: each arm's mean, items, reference and whether it wrote it, from the adapter; the baseline marked",
    rows[arm("wrote_v1")]["wrote"] is True
    and rows[arm("lead_v1")]["n"] == 40
    and rows[arm("short_v1")]["n"] == 20
    and rows[arm("base_v1")].get("baseline", {}).get("version") == 1
    and {r["id"] for r in by_ds[DS]["refs"]} == {GOLD, SILVER},
)
check("by_dataset: only the datasets asked for", gv.by_dataset(AA, {"elsewhere"}) == {})

answers = gv.goal_answers(GOAL, by_ds)
groups = {g["key"]: g for g in answers[0]["groups"]}
check(
    "goal_answers: gold first, silver next, the judge's group last; an arm without the goal's measure is not in it",
    [g["key"] for g in answers[0]["groups"]] == [GOLD, SILVER, "judge j1"]
    and arm("bare_v1") not in {r["arm"] for g in groups.values() for r in g["rows"]},
    [g["key"] for g in answers[0]["groups"]],
)
check(
    "goal_answers: a row's flags are flags_of's",
    all(
        r["flags"] == gv.flags_of(GOAL, r["n"], r["format"], r["wrote"])
        for g in answers[0]["groups"]
        for r in g["rows"]
    )
    and groups[GOLD]["rows"][-1]["flags"] != [],
)

# -- the leader rule ------------------------------------------------------------------------------------------------
retired = gv.retired_in_of(AA, GOAL)
fit = gv.comparable(AA, GOAL, gold_arms, retired)
check(
    "comparable: an arm the goal flags (too few items, the wrong format, wrote its reference) or retired is no leader",
    sorted(fit) == sorted([arm("base_v1"), arm("lead_v1"), arm("ok2_v1")]),
    fit,
)
for system, why in (
    ("short_v1", "too few items"),
    ("json_v1", "a format outside the contract"),
    ("wrote_v1", "it wrote the reference it is scored against"),
):
    check(
        f"comparable: {why}",
        gv.comparable(AA, GOAL, [arm(system), arm("ok2_v1")], retired) == [arm("ok2_v1")],
    )
check(
    "comparable: an arm a round retired, and one read under another label that only its system names",
    gv.comparable(AA, GOAL, [arm("gone_v1"), arm("ok2_v1")], retired) == [arm("ok2_v1")]
    and gv.comparable(AA, GOAL, [arm("gone_v1"), arm("ok2_v1")]) == [arm("gone_v1"), arm("ok2_v1")],
)
check(
    "retired_in_of: the arms a round of the goal retired, with the round",
    gv.retired_in_of(AA, GOAL) == {arm("gone_v1"): "r2"} and gv.retired_in_of(AA, {"goal_id": "other"}) == {},
)
check(
    "comparable: never a judged arm",
    gv.comparable(AA, GOAL, [arm("j_v1", "judged-j1"), arm("ok2_v1")]) == [arm("ok2_v1")],
)
check(
    "comparable: the gold-scored arms where any arm is gold, the others when none is",
    gv.comparable(AA, GOAL, [arm("lead_v1", "silver"), arm("ok2_v1")]) == [arm("ok2_v1")]
    and gv.comparable(AA, GOAL, [arm("lead_v1", "silver")]) == [arm("lead_v1", "silver")]
    and gv.comparable(AA, GOAL, []) == [],
)
check(
    "comparable: with no goal, only the arm that wrote its reference is left out",
    gv.comparable(AA, None, [arm("short_v1"), arm("wrote_v1"), arm("json_v1")])
    == [arm("short_v1"), arm("json_v1")],
)

check(
    "leader: the best mean among the arms a leader may be read from; the lowest where lower is better; none without a score",
    gv.leader(AA, GOAL, gold_arms, "acc", False, retired) == arm("lead_v1")
    and gv.leader(AA, GOAL, gold_arms, "acc", True, retired) == arm("base_v1")
    and gv.leader(AA, GOAL, [arm("bare_v1"), arm("short_v1")], "acc", False, retired) is None
    and gv.leader(AA, GOAL, gold_arms, "nothing", False, retired) is None,
)
decisions = {g["key"]: g["dec"] for g in gv.decided(AA, GOAL, by_ds)[0]["groups"]}
dec = decisions[GOLD]
means = {a: sum(A.scores(a)["acc"]["values"].values()) / 40 for a in fit}
check(
    "decided: the goal's leader is the best of the arms a leader may be read from, as a round reads it",
    dec["leader"] == max(fit, key=lambda a: means[a]) == arm("lead_v1"),
    dec["leader"],
)
check(
    "decided: no flagged or retired arm leads, is a contender or is recommended",
    not {arm(s) for s in ("short_v1", "json_v1", "wrote_v1", "gone_v1")}
    & {dec["leader"], dec["recommended"], *dec["contenders"]},
)
check(
    "decided: a group scored against silver beside gold is shown, not recommended",
    decisions[SILVER]["shown_only"] and decisions[SILVER]["recommended"] is None,
)

# -- the leader against the baseline, corrected for the arms it was chosen from -------------------------------------
check(
    "corrected: p x k, at most 1; significant only while p x k stays under 0.05",
    gv.corrected({"p": 0.02, "verdict": "significant: better", "delta": 1.0}, 6)["p_adjusted"] == 0.12
    and gv.corrected({"p": 0.02, "verdict": "significant: better", "delta": 1.0}, 6)["verdict"]
    == "not significant"
    and gv.corrected({"p": 0.0002, "verdict": "significant: better", "delta": 1.0}, 6)["verdict"]
    == "significant: better"
    and gv.corrected({"p": 0.6, "verdict": "not significant", "delta": 0.1}, 6)["p_adjusted"] == 1.0,
)
check(
    "corrected: one arm to choose from changes nothing; no p is never significant",
    gv.corrected({"p": 0.02, "verdict": "significant: better", "delta": 1.0}, 1)["verdict"]
    == "significant: better"
    and gv.corrected({"p": None, "verdict": "significant: worse", "delta": 1.0}, 3)["verdict"]
    == "not significant",
)
raw = stats.compare(
    {
        arm("lead_v1"): A.scores(arm("lead_v1"))["acc"]["values"],
        arm("base_v1"): A.scores(arm("base_v1"))["acc"]["values"],
    },
    arm("base_v1"),
    higher_is_better=True,
    family=1,
)["rows"][0]
glance = gv.glance(AA, by_ds)[0]
test = glance["test"]
check(
    "glance: the leader against the baseline is Bonferroni over the other arms of its group, as a round's evidence reads it",
    raw["verdict"] == "significant: better"
    and glance["leader"] == arm("lead_v1")
    and test["family"] == len(groups[GOLD]["rows"]) - 1 == 6
    and abs(test["p_adjusted"] - min(1.0, raw["p"] * 6)) < 1e-12
    and test["p"] == raw["p"]
    and test["verdict"] == "not significant",
    (raw, test),
)
check(
    "glance_verdict: says the number of arms and the adjusted p",
    f"Bonferroni over {test['family']} arms: {stats.fmt_p(test['p_adjusted'])}" in cb.glance_verdict(glance),
    cb.glance_verdict(glance),
)

gap_dec = {"recommended": arm("lead_v1"), "axes": [{"direction": "higher"}], "goal": GOAL, "dataset": DS}
gap = gv.baseline_gap(AA, gap_dec, groups[GOLD]["rows"], "acc")
check(
    "baseline_gap: the recommended arm against the baseline, one comparison (family 1), not corrected",
    gap is not None
    and gap["family"] == 1
    and gap["p"] == raw["p"]
    and gap["verdict"] == "significant: better",
    gap,
)
words = cb.baseline_gap(AA, gap_dec, groups[GOLD]["rows"], "acc")
check(
    "baseline_gap: the page's note says it is one comparison, not corrected",
    "one comparison, not corrected" in words
    and words.startswith("Differs from the promoted baseline, base_v1"),
    words,
)
check(
    "baseline_gap: nothing to say when the baseline is the recommended arm",
    gv.baseline_gap(AA, {**gap_dec, "recommended": arm("base_v1")}, groups[GOLD]["rows"], "acc") is None,
)

# -- the goal's leaderboard (goal-leaderboard) ----------------------------------------------------------------------
lb = gv.leaderboard(AA, "g")
gold = lb["datasets"][0]["groups"][0]
silver = lb["datasets"][0]["groups"][1]
by_arm = {x["arm"]: x for x in gold["arms"]}
check(
    "leaderboard: per dataset and reference, every arm's row with its flags, and the leader and the baseline named",
    lb["goal"] == "g"
    and lb["measure"] == "acc"
    and lb["datasets"][0]["dataset"] == DS
    and (gold["scored_against"], silver["scored_against"]) == (GOLD, SILVER)
    and gold["leader"] == arm("lead_v1")
    and gold["baseline"] == arm("base_v1")
    and by_arm[arm("lead_v1")]["leader"] is True
    and by_arm[arm("short_v1")]["flags"][0] == "n 20 < min_items 40"
    and by_arm[arm("gone_v1")]["retired_in"] == "r2"
    and lb["datasets"][0]["baseline"]["arm"] == arm("base_v1"),
    gold["arms"][:2],
)
check(
    "leaderboard: the tests the page shows (against the leader, the contender test) and the leader against the baseline",
    by_arm[arm("ok2_v1")]["vs_leader"] is not None
    and gold["leader_vs_baseline"]["family"] == 6
    and gold["leader_vs_baseline"]["verdict"] == "not significant"
    and silver["leader_vs_baseline"] is None,
    gold["leader_vs_baseline"],
)
try:
    gv.leaderboard(AA, "nope")
    refused = None
except Problem as exc:
    refused = exc.kind
check("leaderboard: a goal that does not exist is refused as not found", refused == "not-found", refused)

op = registry.get("goal-leaderboard")
check(
    "goal-leaderboard: a read operation at GET /goals/{goal}/leaderboard",
    op is not None and (op.kind, op.method, op.route) == ("read", "GET", "/goals/{goal}/leaderboard"),
)
serve: Any = catalog_serve
was = serve.A
try:
    serve.A = AA  # the adapter the server serves
    answer = op.call(goal="g") if op else {}
    said = op.say(answer) if op else ""
finally:
    serve.A = was
check(
    "goal-leaderboard: answers with the adapter the server serves, and says it in words",
    answer.get("datasets", [{}])[0].get("groups", [{}])[0].get("leader") == arm("lead_v1")
    and "leader against the baseline: not significant" in said
    and "Bonferroni over 6 arms" in said,
    said[:600],
)

# -- a dataset read without a goal (evh leaderboard) ----------------------------------------------------------------
free = gv.dataset_groups(AA, by_ds, DS, None)
free_rows = {r["arm"] for g in free for r in g["rows"]}
check(
    "dataset_groups: with no goal every arm is read on its own headline, in its reference's group, with no decision",
    arm("bare_v1") in free_rows
    and arm("short_v1") in free_rows
    and all("dec" not in g for g in free)
    and next(r for g in free for r in g["rows"] if r["arm"] == arm("short_v1"))["flags"] == [],
    sorted(free_rows),
)
read = gv.dataset_groups(AA, by_ds, DS, GOAL)
check(
    "dataset_groups: with the goal, its groups and decisions; an arm without its measure is not in them",
    [g["key"] for g in read] == [GOLD, SILVER, "judge j1"]
    and read[0]["dec"]["leader"] == arm("lead_v1")
    and arm("bare_v1") not in {r["arm"] for g in read for r in g["rows"]},
)


class _Rounds:
    """r2 retired two arms; r4 carries one of them back in (ADR-0006, RFC-004: a retirement is a round's decision)."""

    def rounds(self) -> list[dict]:
        a, b = arm("gone_v1"), arm("also_gone_v1")
        # a re-score of the same system is retired with it (`rounds.retired_arms`), and comes back with it
        return [
            {"goal": "g", "round_id": "r2", "retired_arms": [a, b, arm("gone_v1", "rescored-x")], "arms": []},
            {"goal": "g", "round_id": "r3", "retired_arms": [], "arms": []},
            {"goal": "g", "round_id": "r4", "retired_arms": [], "arms": [a]},
        ]


check(
    "retired_in_of: an arm a later round carries in is in play there; its re-scored sibling too; the one nobody carried stays retired in r2",
    gv.retired_in_of(_Rounds(), GOAL) == {arm("also_gone_v1"): "r2"},
    gv.retired_in_of(_Rounds(), GOAL),
)

sys.exit(summary())
