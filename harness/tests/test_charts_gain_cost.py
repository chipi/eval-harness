"""The gain-cost chart on stub data (RFC-034 §3; the review of 2026-11-19): what each point is, where it is drawn, and
what it may be called.

- an arm that shares no item with the base is a row that says so, never a point (it crashed the chart);
- a measure where lower is better is flipped, so up is better, and the axis says so;
- a study is drawn on its own measure, in that measure's direction (on the goal's primary, a trial better on the study's
  measure was plotted down and called worse);
- a significant difference is a filled mark, any other a hollow one;
- with no cost recorded the cost axis is tokens.

    python tests/test_charts_gain_cost.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation_harness import _study, charts
from evaluation_harness._check import check, summary
from evaluation_harness.model import compare as mc
from evaluation_harness.model import rounds as mr
from evaluation_harness.model import studies as ms
from evaluation_harness.model.entity import Problem
from evaluation_harness.ops import rounds as orr

N = 40
ITEMS = [f"i{k:02d}" for k in range(N)]


def scores(base: float, step: float, cost: float | None = None, tokens: float | None = None) -> dict:
    """Per-item values: base + step on every item (+ a small wobble so the paired test has a spread)."""
    out = {"m": {"values": {i: base + step + (k % 5) * 0.01 for k, i in enumerate(ITEMS)}}}
    if cost is not None:
        out["cost_usd"] = {"values": dict.fromkeys(ITEMS, cost)}
    if tokens is not None:
        out["tokens_in"] = {"values": dict.fromkeys(ITEMS, tokens)}
        out["tokens_out"] = {"values": dict.fromkeys(ITEMS, 0.0)}
    return out


class Stub:
    item_word = "item"

    def __init__(self, goal_direction: str, arms: dict):
        self.goal_direction, self.data = goal_direction, arms

    def goals(self):
        return [
            {
                "goal_id": "g",
                "success_criteria": {"primary": {"measure": "m", "direction": self.goal_direction}},
            }
        ]

    def direction(self, metric, dataset=None):
        return self.goal_direction

    def lower_is_better(self, metric, dataset=None):
        return self.direction(metric, dataset) == "lower"

    def arms(self):
        return list(self.data)

    def scores(self, arm):
        return self.data[arm]

    def describe(self, arm):
        return {"label": arm.rsplit("/", 1)[-1]}


def no_clusters(dataset: str) -> tuple[dict | None, str | None]:
    return None, None


def the_round(goal: str, round: str) -> dict:
    return {"dataset_id": "d"}


mc.goal_clusters_on = no_clusters
orr._round = the_round


def round_chart(direction: str, arms: dict) -> dict:
    names = list(arms)
    mr.evidence = lambda goal, rnd, A=None, data=None: {
        "arms": names,
        "baseline_arm": names[0],
        "leader": names[0],
    }
    with charts.using(Stub(direction, arms)):
        return charts.gain_cost("g", round="r1")


def circles(svg: str) -> dict[str, str]:
    """Each point's name (its title's first word) and whether it is drawn filled or hollow."""
    out = {}
    for paint, tip in re.findall(r'<circle [^>]*?(fill="[^"]+")[^>]*><title>([^<]+)</title>', svg):
        out[tip.split(":")[0]] = "hollow" if 'fill="none"' in paint else "filled"
    return out


# an arm with no items: a row that says so, no point, named in the caption; the others drawn
c = round_chart(
    "higher",
    {
        "runs/d/base": scores(0.5, 0.0, cost=0.01),
        "runs/d/better": scores(0.5, 0.2, cost=0.02),
        "runs/d/empty": {"m": {"values": {}}, "cost_usd": {"values": {}}},
    },
)
rows = {r["arm"]: r for r in c["rows"]}
check(
    "an arm sharing no item with the base: a row 'not compared', no point, named in the caption; the others drawn",
    rows["empty"]["claim"] == "not compared: no shared item"
    and rows["empty"]["quality_delta"] is None
    and "empty" not in circles(c["svg"])
    and "better" in circles(c["svg"])
    and "sharing no item with the baseline: empty" in c["caption"],
    (rows, c["caption"][-200:]),
)
check(
    "significant: a filled mark named by its quadrant (better, costs more)",
    circles(c["svg"]).get("better") == "filled" and rows["better"]["claim"] == "better, costs more",
    (circles(c["svg"]), rows["better"]["claim"]),
)

# no difference: hollow, not named by a quadrant
c = round_chart(
    "higher", {"runs/d/base": scores(0.5, 0.0, cost=0.01), "runs/d/same": scores(0.5, 0.0, cost=0.01)}
)
check(
    "not separated: a hollow mark, called 'not separated', never a quadrant",
    circles(c["svg"]).get("same") == "hollow" and c["rows"][0]["claim"] == "not separated",
    (circles(c["svg"]), c["rows"]),
)

# lower is better: an arm lower on m is better, plotted up, and the axis says the flip
c = round_chart(
    "lower", {"runs/d/base": scores(0.5, 0.0, cost=0.01), "runs/d/lower": scores(0.5, -0.2, cost=0.01)}
)
r = c["rows"][0]
check(
    "a measure where lower is better: the lower arm is up (positive), its interval too, and the axis says it is flipped",
    r["quality_delta"] > 0
    and r["low"] > 0
    and r["high"] >= r["low"]
    and "flipped (lower is better)" in c["svg"]
    and "lower is better: flipped" in c["caption"],
    (r, c["caption"][:200]),
)

# no cost recorded: tokens are the cost axis, and the quadrant is named on tokens
c = round_chart(
    "higher",
    {"runs/d/base": scores(0.5, 0.0, tokens=100.0), "runs/d/terse": scores(0.5, 0.2, tokens=60.0)},
)
r = c["rows"][0]
check(
    "no cost recorded: the cost axis is tokens per item, and a significant gain with fewer tokens is 'better and "
    "cheaper'",
    "difference in tokens per item" in c["svg"]
    and r["tokens_delta_per_item"] == -40.0
    and r["claim"] == "better and cheaper"
    and "in tokens" in c["caption"],
    (r, c["caption"][:240]),
)

# no cost difference at all (review, 2026-11-19: two arms costing the same were called "better and cheaper"), and no
# cost recorded on the items both share
c = round_chart(
    "higher", {"runs/d/base": scores(0.5, 0.0, cost=0.01), "runs/d/same_cost": scores(0.5, 0.2, cost=0.01)}
)
check(
    "a significant gain at the same cost is 'better at the same cost', never 'cheaper'",
    c["rows"][0]["claim"] == "better at the same cost",
    c["rows"][0]["claim"],
)
# RFC-041 F3: no arm with a known cost is no cost axis; an unknown cost is not drawn at 0, the chart refuses
try:
    round_chart("higher", {"runs/d/base": scores(0.5, 0.0), "runs/d/no_cost": scores(0.5, 0.2)})
    refusal = None
except Problem as exc:
    refusal = (exc.kind, str(exc))
check(
    "RFC-041 F3: no arm has a known cost: the chart refuses (not-enough), saying so, and draws nothing at 0",
    refusal is not None and refusal[0] == "not-enough" and "no arm has a known cost" in refusal[1],
    refusal,
)

# an arm whose cost is unknown is not a free arm (RFC-041 F3, RUNBOOK 886-887): it is left off the cost axis and named in
# the caption; an arm that recorded $0 is drawn at its difference from the base's
u = round_chart(
    "higher",
    {
        "runs/d/base": scores(0.5, 0.0, cost=0.01),
        "runs/d/priced": scores(0.5, 0.2, cost=0.02),
        "runs/d/free": scores(0.5, 0.2, cost=0.0),
        "runs/d/unpriced": scores(0.5, 0.2),
    },
)
urows = {r["arm"]: r for r in u["rows"]}
check(
    "an arm with no recorded cost is not drawn on the cost axis and the caption names it; a recorded $0 is drawn",
    set(circles(u["svg"])) == {"priced", "free"}
    and "its cost unknown: unpriced" in u["caption"]
    and urows["unpriced"]["claim"] == "better, its cost not compared"
    and urows["unpriced"]["cost_delta_per_item"] is None
    and urows["free"]["cost_delta_per_item"] == -0.01,
    (circles(u["svg"]), u["caption"][-240:], urows["unpriced"]),
)
t = round_chart(
    "higher",
    {
        "runs/d/base": scores(0.5, 0.0, tokens=100.0),
        "runs/d/terse": scores(0.5, 0.2, tokens=60.0),
        "runs/d/uncounted": scores(0.5, 0.2),
    },
)
# No cost recorded, the same tokens on both arms (the workbench's echo round, 2026-11-24): the token difference 0 is known,
# so the chart is drawn on tokens; it refused, reading "no token difference" as "no tokens".
z = round_chart(
    "higher", {"runs/d/base": scores(0.5, 0.0, tokens=50.0), "runs/d/same": scores(0.5, 0.2, tokens=50.0)}
)
check(
    "no cost recorded and the same tokens on both arms: drawn on the tokens axis at a difference of 0, not refused",
    set(circles(z["svg"])) == {"same"}
    and {r["arm"]: r for r in z["rows"]}["same"]["tokens_delta_per_item"] == 0.0,
    (circles(z["svg"]), z["caption"][-200:]),
)
check(
    "on the tokens axis an arm with no tokens recorded is left off and named, the same",
    set(circles(t["svg"])) == {"terse"} and "its tokens unknown: uncounted" in t["caption"],
    (circles(t["svg"]), t["caption"][-200:]),
)
check(
    "a gain that is not separated, with no cost known on either side, is 'not separated': an unknown cost is not 'costs more'",
    charts._claim(False, 0.1, None) == "not separated" and charts._claim(False, 0.1, 0.0) == "not separated",
    (charts._claim(False, 0.1, None), charts._claim(False, 0.1, 0.0)),
)

# a study decided on a measure other than the goal's primary is drawn in the study's direction
arms = {"runs/d/base_v1": scores(0.5, 0.0, cost=0.01), "runs/d/t1_v1": scores(0.5, 0.2, cost=0.01)}
ms.state = lambda goal, sid, data=None: {
    "baseline": "base_v1",
    "trials": [
        {
            "k": 1,
            "system_id": "t1_v1",
            "change": "more",
            "outcome": "kept",
            "vs_baseline": {"verdict": "significant: better", "p": 0.001},
        }
    ],
}
ms.spec = lambda goal, sid, data=None: {"dataset": "d", "measure": "m2"}
for a in arms.values():
    a["m2"] = a.pop("m")
_study.lower_is_better = lambda goal, metric, dataset=None: (
    metric == "m"
)  # the goal's primary m is lower; the study's m2 is not
with charts.using(Stub("lower", arms)):
    c = charts.gain_cost("g", study="s1")
r = c["rows"][0]
check(
    "a study on a measure other than the goal's primary: its better trial is up and called better, on the study's "
    "measure, in its direction",
    r["quality_delta"] > 0
    and r["claim"].startswith("better")
    and "up is better on m2" in c["caption"]
    and "flipped" not in c["caption"],
    (r, c["caption"][:200]),
)

# every reader counts a score as `_number` says: NaN, inf and None are a failed item's 0, a boolean or text is no score
odd = Stub(
    "higher", {"runs/d/x": {"m": {"values": {"a": 0.5, "b": float("nan"), "c": None, "d": True, "e": "t"}}}}
)
with charts.using(odd):
    got = charts._values(odd, "runs/d/x", "m")
    dropped = charts._values_dropped(odd, "runs/d/x", "m")
check(
    "charts._values: NaN and None count as 0 (a failed item), a boolean and text are left out and counted",
    got == {"a": 0.5, "b": 0.0, "c": 0.0} and dropped == 2,
    (got, dropped),
)

sys.exit(summary())
