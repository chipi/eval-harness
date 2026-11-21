"""The statistics reads as operations (RFC-032 step 9): `evh leaderboard`, `pair-test`, `family-test` and `rank-stability`,
each over the runs of one dataset. Their answer is what `--json` always gave, the printed lines and tables in order and
the command's named results (`result.values`: the ranking and ordering test per reference, the test's p and verdict);
the command line prints them as it always printed them, a table fitted to the terminal."""

from __future__ import annotations

from typing import Any

from evaluation_harness.ops import legacy
from evaluation_harness.ops.registry import Op

_S = "evaluation_harness.ops.stats"
_STR = {"type": "string"}
_ASC = {"type": "boolean", "description": "lower is better (default: inferred from the metric and the runs)"}
_DESC = {"type": "boolean", "description": "higher is better, whatever the runs declare"}
_LABEL = {
    "type": "string",
    "description": 'the arm label the runs are read under (default: "", the plain runs; `evh runs-list` shows the labels present, e.g. "repeats" or a re-score\'s)',
}
_ROUND = {"type": "string", "description": "a round of a goal (rN; ADR-0004)"}
_GOAL = {"type": "string", "description": "the goal the round belongs to, when several goals have one"}
_EXCLUDE = {"type": "string", "description": "drop items this dataset also contains"}
_ITEMS = {
    "type": "string",
    "description": "file of item_ids (one per line); restrict the test to exactly these",
}
_CLUSTER = {
    "type": "string",
    "description": "an item field whose items are not independent (one thread's comments): flip one sign per value of it, so related items count once (with round: default the goal's `cluster:`)",
}
_REDUCE = {
    "type": "string",
    "description": "how an arm's repeats make one score per item: mean (the default), majority or at_least_K, for 0/1 scores (with round: default the goal's primary.reduce)",
}
_SEED = {"type": "integer", "description": "the permutations' seed (default 20260926)"}

OPS = (
    Op("leaderboard", "read", "rank every arm that ran on one dataset, quality, cost and speed together, with Friedman/Nemenyi before any order",
       "GET", "/datasets/{dataset}/leaderboard", f"{_S}:leaderboard", f"{_S}:say_blocks", output=legacy.BLOCKS,
       printer=f"{_S}:print_leaderboard", inputs={
           "sort": {"type": "string", "description": "metric to rank by (default: the first quality metric)"},
           "asc": _ASC,
           "desc": _DESC,
           "match": {"type": "string", "description": "only arms whose system_id contains this substring"},
           "label": {"type": "string", "description": 'only the arms read under this label: "" the runs\' own scores; "silver", "repeats", "linux", "judged/<scorer>", "rescored <scorer>" ... (evh runs-list names those present); default: every arm'},
           "round": {"type": "string", "description": "only the arms this round of a goal compared, under their labels (rN; ADR-0004)"},
           "goal": {"type": "string", "description": "the goal that reads the dataset (default: the one that names it; with round, the round's goal)"},
           "wide": {"type": "boolean", "description": "print every metric column, however wide (default: as many as fit the terminal, the ranking metric first)"},
       }),
    Op("pair-test", "read", "one pre-registered pair, tested on its own: sign-flip permutation on paired deltas",
       "GET", "/datasets/{dataset}/pair-test", f"{_S}:pair_test", f"{_S}:say_blocks", output=legacy.BLOCKS,
       printer=f"{_S}:print_pair_test", inputs={
           "a": {"type": "string", "description": "system_id of the arm under test (with round: default its leader)"},
           "b": {"type": "string", "description": "system_id it is compared against (with round: default the baseline it started from)"},
           "b_dataset": {"type": "string", "description": "a second version of the dataset: B's runs are read on it, A's on the first, paired by item id. Refused unless the items, the reference they are scored against and the metric agree"},
           "round": {"type": "string", "description": "test within this round of a goal (rN): arms must be in play in it"},
           "goal": _GOAL,
           "metric": {"type": "string", "description": "default: the round's goal measure with round, else the primary metric the runs recorded"},
           "label": _LABEL,
           "exclude_dataset": _EXCLUDE,
           "include_exposed": {"type": "boolean", "description": "on a held-out side, also show the mean difference with its read (exposed) items kept, marked: the number without them is the one that counts (RFC-031)"},
           "items": _ITEMS,
           "cluster": _CLUSTER,
           "reduce": _REDUCE,
           "margin": {"type": "number", "description": "also test whether A is no worse than B by more than this, in the metric's units: the contender test goals use (one-sided non-inferiority; ADR-0026), for this one pair, uncorrected"},
           "look_level": {"type": "number", "description": "decide one-sided at this level, as a look at a test set does (RFC-029): A better than B; with margin, non-inferiority at the level too. Reports the smallest p these items can reach"},
           "permutations": {"type": "integer", "minimum": 1, "description": "how many sign flips (default 20000)"},
           "family": {"type": "integer", "minimum": 1, "description": "how many pairs were tested together (Bonferroni: alpha/family); default 1, or with round when A was chosen as the round's leader, the arms in play minus 1"},
           "seed": _SEED,
           "asc": _ASC,
           "desc": _DESC,
       }, tool_hidden=("items",), public_hidden=("permutations",)),
    Op("family-test", "read", "one arm against a declared family of opponents, Holm step-down over the whole family",
       "GET", "/datasets/{dataset}/family-test", f"{_S}:family_test", f"{_S}:say_blocks", output=legacy.BLOCKS,
       printer="evaluation_harness.family_test:text", inputs={
           "a": {"type": "string", "description": "system_id of the arm under test (with round: default its leader)"},
           "against": {"type": "string", "description": "the opponent family, declared in advance: a substring of their system ids, or a comma-separated list of system ids (with round: default every other arm in play in it)"},
           "metric": {"type": "string", "description": "default: the primary metric the runs recorded"},
           "label": _LABEL,
           "exclude_dataset": _EXCLUDE,
           "items": _ITEMS,
           "reduce": _REDUCE,
           "cluster": _CLUSTER,
           "permutations": {"type": "integer", "minimum": 1, "description": "how many sign flips per opponent (default 20000)"},
           "alpha": {"type": "number", "description": "the family-wise level (default 0.05)"},
           "asc": _ASC,
           "desc": _DESC,
           "seed": _SEED,
           "round": {"type": "string", "description": "only opponents in play in this round of a goal (rN; ADR-0004)"},
           "goal": _GOAL,
       }, tool_hidden=("items",), public_hidden=("permutations",)),
    Op("rank-stability", "read", "how many items a ranking needs: how many items before a leaderboard stops moving, measured, not assumed",
       "GET", "/datasets/{dataset}/rank-stability", f"{_S}:rank_stability", f"{_S}:say_blocks", output=legacy.BLOCKS,
       printer=f"{_S}:print_rank_stability", inputs={
           "metric": {"type": "string", "description": "default: the primary metric the runs recorded"},
           "match": {"type": "string", "description": "only arms whose system_id contains this substring"},
           "draws": {"type": "integer", "minimum": 1, "description": "random halves drawn per size (default 400)"},
           "seed": _SEED,
           "asc": {"type": "boolean", "description": "lower is better (default: inferred)"},
           "desc": _DESC,
       }, public_hidden=("draws",)),
)  # fmt: skip

leaderboard, print_leaderboard = legacy.of("evaluation_harness.leaderboard")
pair_test, print_pair_test = legacy.of("evaluation_harness.pair_test")
_family_run, _ = legacy.of("evaluation_harness.family_test")


def family_test(dataset: str, **given: Any) -> dict[str, Any]:
    """The family test's answer, replayed from the project's cache when the exact same test has run (it is ~18 s of seeded
    permutations for a family of 29, and an agent asks the same question again)."""
    from evaluation_harness import family_test as module  # noqa: PLC0415

    return module.replayed(dataset, given, lambda: _family_run(dataset=dataset, **given))


rank_stability, print_rank_stability = legacy.of("evaluation_harness.rank_stability", as_json="as_json")
say_blocks = legacy.say_blocks
