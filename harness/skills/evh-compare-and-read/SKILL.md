---
name: evh-compare-and-read
description: Read eval-harness (evh) results as data and say what they support — which arm leads, whether the lead is real, where two arms differ item by item, and what a goal recommends — with the paired tests behind each claim. Use when asked "which is better", "did the change help", "is it significant", "what does the goal recommend", or before reporting any evh result.
metadata:
  harness-version: "0.6.2"
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

## Reporting

- Say what the test says: "A is significantly better than B on M (p = 0.01, n = 200)", or "A and
  B are not significantly different at n = 6". A higher mean without a test is not a finding.
- Name the reference the scores are against: a silver reference ranks; only gold supports
  "correct".
- Name what was not covered: items not run, arms not compared, a measure not checked.
