---
name: evh-compare-and-read
description: Read eval-harness (evh) results as data and say what they support — which arm leads, whether the lead is real, where two arms differ item by item, and what a goal recommends — with the paired tests behind each claim. Use when asked "which is better", "did the change help", "is it significant", "what does the goal recommend", or before reporting any evh result.
metadata:
  harness-version: "0.8.0.dev0"
---

# Compare arms and read the results

Every answer here is a command; add `--json` and stdout is one object,
`{"command", "version", "result": {"blocks": [...], "values": {...}}}`: tables as columns and
rows with their raw numbers, the key results as named values. You do not need the catalog or
`evh mcp`: they show the same numbers from the same code.

The blocks run as written on the tutorial kit after `evh-evaluate-a-system`.

## Which arm leads, and is the order real

```evh
evh leaderboard --dataset-id tickets_v1 --json
```

The ranking alone is not a finding. The leaderboard's own test (Friedman, then Nemenyi's critical
difference) says which pairs are distinguishable; with few items, often none are.

## One comparison you named in advance

```evh
evh pair-test --dataset-id tickets_v1 --a tickets_lead2_v1 --b tickets_lead1_v1 --json
```

A paired test on the same items: the difference, its p, and the verdict at 0.05. Valid only for a
pair chosen before you read the table; for one arm against all the others, correct for the family:

```evh
evh family-test --dataset-id tickets_v1 --a tickets_lead2_v1 --against tickets_ --json
```

## A goal's answer

With a goal (`data/goals/<goal_id>.yaml`), one command gives the leader, the baseline, their paired
test and what the goal's strategy recommends once its limits are applied:

```evh
evh goals --json
```

## Where two arms differ

`evh inspect --runs A,B --json` tests each arm against the first (Holm across them) and lists the
items; `--item ID` shows one item's outputs beside the reference; `--disagree` keeps only the items
the arms decided differently; `--by FIELD` breaks it down by an item's field.

```evh
evh inspect --runs tickets_lead1_v1,tickets_lead2_v1 --json
```

## Why the items flipped: the outputs together

`evh inspect --item ID` shows one item. For many, `--items-out` gives per item each arm's decision,
whole output, per-item scores and the facts the adapter recorded (`_meta`), beside the reference and
the labels; `--disagree` keeps the items the arms decided differently from the first, `--where F:V`
narrows by an item's field. In `--json` the texts are whole (`result.values.items_out.items`); in
text an output is cut at `--max-chars` (default 300). The sheet (`--sheet`) has the decisions and
labels too, but cut to a cell.

```evh
evh inspect --runs tickets_lead1_v1,tickets_lead2_v1 --items-out --disagree --json
```

## How two scores relate, by a recorded fact

`--crosstab M1,M2` counts a run's items by their value of two per-item scores (`M1` down, `M2`
across), with totals, and names the items off the diagonal. `--group FIELD` does it per value of a
field of the run's prediction rows (a dotted path such as `_meta.gates`; a part of a packed string
with `--group-match REGEX`, the first `(...)` of it). That answers "how many gate downgrades saved a
false dismissal, and how many cost a false alarm": cross the model's own score with the final one
(`model_false_dismiss,false_dismiss`; `model_false_alarm,false_alarm`) per gate, and read the cell
counts and ids. Items with no value count as `none`. Run both crosses before reporting a net effect:
a save and a cost are different items.

```evh
evh inspect --runs tickets_lead2_v1 --crosstab overlap_f1,overlap_f1 --json
```

## A result with and without a set of items

`evh pair-test --dataset-id D --a A --b B --items FILE` tests only the item ids in FILE (one per
line); give the rest as a second file, or drop a dataset's items with `--exclude-dataset D2`. The
inspector filters by an item's field, so a set marked by a field is `evh inspect --runs A,B --where
FIELD:VALUE` (and the other half with the other value). Report both halves and the whole, and say
how the set was chosen: a set picked after reading results is a finding to confirm, not a test.

## What a new version of a dataset changed

`evh pair-test --dataset-id D1 --a ARM_v1 --b ARM_v2 --b-dataset D2` tests one arm's runs on D1
against its runs on D2, paired by item id. It refuses unless the items are in both versions and the
reference gives the same text for each, and says it is a cross-version comparison: the difference is
the dataset change plus the arm's run-to-run noise, so one run each cannot separate them. Repeats are
averaged per item. `run-compare` still refuses across datasets.

## Reporting

- Say what the test says: "A is significantly better than B on M (p = 0.01, n = 200)", or "A and
  B are not significantly different at n = 6". A higher mean without a test is not a finding.
- Name the reference the scores are against: a silver reference ranks; only gold supports
  "correct".
- Name what was not covered: items not run, arms not compared, a measure not checked.
