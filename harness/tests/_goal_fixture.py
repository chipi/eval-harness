"""A stand-in adapter for the goal view (model/goal_views): one dataset, arms with per-item scores, a gold and a silver
reference, a promoted baseline, a round that retired an arm, and a goal. Not a project: nothing is written."""

from __future__ import annotations

from typing import Any

DS = "ds_v1"
ITEMS = [f"i{k:02d}" for k in range(40)]
GOLD, SILVER = f"gold/{DS}", f"silver/{DS}"


def arm(system: str, label: str = "runs") -> str:
    """The arm id of a system read under a label."""
    return f"{label}/{DS}/{system}"


def values(up: int, n: int = 40) -> dict[str, float]:
    """The base's 0.5 on every item, plus 0.1 on the first `up` items and -0.05 on the next four: a paired gain over
    the base that is significant alone (up 9 and over) and not once the arm is one of several."""
    return {i: 0.5 + (0.1 if k < up else (-0.05 if k < up + 4 else 0.0)) for k, i in enumerate(ITEMS[:n])}


class Stand:
    """An adapter with what the goal view reads: arms with their per-item scores, a gold and a silver reference, a
    promoted baseline and a round that retired an arm."""

    def __init__(self, arms: dict[str, dict[str, Any]]) -> None:
        self.table = arms

    def arms(self) -> list[str]:
        """Every arm."""
        return list(self.table)

    def describe(self, a: str) -> dict[str, Any]:
        """An arm's facts: its reference, format, judge and whether it wrote its reference."""
        t = self.table[a]
        return {
            "id": a,
            "label": a.rsplit("/", 1)[-1],
            "dataset": DS,
            "primary": "acc",
            "task": "acc",
            "runs": 1,
            "goal": "g",
            "format": t.get("format", "text"),
            "reference": t.get("reference", GOLD),
            "judge": t.get("judge", ""),
            "wrote_reference": t.get("wrote", False),
        }

    def scores(self, a: str, rescore: bool = False) -> dict[str, dict]:
        """An arm's per-item scores on `acc`."""
        return {"acc": {"values": self.table[a]["acc"]}} if self.table[a]["acc"] else {}

    def lower_is_better(self, metric: str, dataset: str | None = None) -> bool:
        """Higher is better for every metric."""
        return False

    def references(self) -> list[dict]:
        """The dataset's gold and silver references."""
        return [{"id": GOLD, "dataset": DS, "tier": "gold"}, {"id": SILVER, "dataset": DS, "tier": "silver"}]

    def baselines(self) -> list[dict]:
        """The goal's promoted baseline."""
        return [
            {
                "version": 1,
                "dataset": DS,
                "run": "base_run",
                "arm": arm("base_v1"),
                "reason": "the one in use",
                "promoted_at": "2026-11-01T00:00:00Z",
                "tier": "gold",
                "goal": "g",
            }
        ]

    def rounds(self) -> list[dict]:
        """Two rounds: the second retired an arm."""
        return [
            {"goal": "g", "round_id": "r1", "retired_arms": []},
            {"goal": "g", "round_id": "r2", "retired_arms": [arm("gone_v1")]},
        ]

    def goals(self) -> list[dict]:
        """The one goal."""
        return [GOAL]


GOAL: dict[str, Any] = {
    "goal_id": "g",
    "success_criteria": {"primary": {"measure": "acc", "direction": "higher"}, "min_items": 40},
    "output_contract": [{"format": "text"}],
    "datasets": [{"dataset_id": DS, "role": "test"}],
}
A = Stand(
    {
        arm("base_v1"): {"acc": values(0)},
        arm("lead_v1"): {"acc": values(10)},
        arm("ok2_v1"): {"acc": dict.fromkeys(ITEMS, 0.51)},
        arm("short_v1"): {"acc": dict.fromkeys(ITEMS[:20], 0.9)},
        arm("json_v1"): {"acc": dict.fromkeys(ITEMS, 0.8), "format": "json"},
        arm("wrote_v1"): {"acc": dict.fromkeys(ITEMS, 1.0), "wrote": True},
        arm("gone_v1"): {"acc": dict.fromkeys(ITEMS, 0.7)},
        arm("lead_v1", "silver"): {"acc": dict.fromkeys(ITEMS, 0.99), "reference": SILVER},
        arm("j_v1", "judged-j1"): {"acc": dict.fromkeys(ITEMS, 0.95), "judge": "j1"},
        arm("bare_v1"): {"acc": {}},
    }
)
