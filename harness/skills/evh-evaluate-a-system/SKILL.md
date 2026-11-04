---
name: evh-evaluate-a-system
description: Measure a system with eval-harness (evh) from nothing to a recorded decision — freeze a dataset (from files or from production records), make a reference, run each version of the system as an arm, compare them with paired tests, and promote the winner with a reason. Use when asked to "evaluate", "measure", "benchmark", "compare versions of" or "improve" a system with evh, or when starting evh in a project.
metadata:
  harness-version: "0.6.2"
---

# Evaluate a system with evh

The loop: **dataset → reference → arms → runs → comparison → decision.** Each step writes files
under `data/` that are frozen once written; a change is a new id. The project's `AGENTS.md`
(written by `evh init`) holds the rules; read it first. This skill is the procedure.

The blocks below run as written on the tutorial kit (`evh init --tutorial`: six support tickets,
offline arms); use your own names in a real project. Every command takes `--help`.

## 0. Before anything

- **What is the goal?** One measure decides (accuracy, a cost, a combined score), and which way is
  better. If your operator has not said what decides, ask: a comparison on the wrong measure is
  worse than none.
- **Who asked, and the budget.** You run arms and promote a baseline only when your operator asked
  for that task. Set the cap before any paid call: `export EVAL_MAX_COST_USD=2` (with none, a run
  has no cap).

## 1. A dataset

From files (one item per file):

```evh
evh dataset-create --dataset-id tickets_v1 --source-dir tutorial/tickets
evh dataset-materialize --dataset-id tickets_v1
```

From production records (a JSON-lines export; also `tsv`, `github`, `langfuse` importers):

```evh
evh capture --importer jsonl --query '{"path": "tutorial/production/desk_export.jsonl"}' --capture desk_c1
evh dataset-from-capture desk_c1 --dataset-id tickets_desk_v1
evh dataset-materialize --dataset-id tickets_desk_v1
```

`evh dataset-create --limit 10` keeps a first pass cheap. Ten items is a smoke test, not evidence.

## 2. Arms, committed

An arm is one version of the system: a YAML config in `data/configs/` naming the provider (or your
`adapter.py`), the model, the prompt and the settings, and a unique `config_id`. One change, one new
`config_id`; never edit a config that has runs.

```evh
cp tutorial/configs/tickets_*.yaml data/configs/
git add -A && git commit -qm "tickets_v1: dataset and arms"
```

Commit before every run: a run records the commit it ran from, and one from a dirty tree is refused
later.

## 3. A reference

What each item is scored against. In order of strength:

- **gold**: a person's labels (`evh label-sheet` for them to fill, `evh label-import` to read it).
  Never import labels you made as a person's.
- **production's outcomes**: `evh label-from-capture --dataset-id D --capture C --map rules.yaml --set S`.
- **silver**: the best system's outputs, as a model's labels: good for ranking the rest, not for
  claiming correctness.

```evh
RUN=$(evh run --config data/configs/tickets_author.yaml --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["values"]["runs"][0]["run_id"])')
evh label-from-run --run "$RUN" --set author_v1
evh reference-promote --dataset-id tickets_v1 --labels author_v1 --tier silver --reason "the author arm ranks the others until a person writes gold" --by agent
git add -A && git commit -qm "silver/tickets_v1"
```

## 4. Run each arm

Cost first (`--dry-run`), a few items next (`evh arm-smoke --config C`, and read the replies), then
the full run. `--repeat 3` measures an arm's own noise.

```evh
evh run --config data/configs/tickets_lead1.yaml --dry-run
evh run --config data/configs/tickets_lead1.yaml --repeat 3
evh run --config data/configs/tickets_lead2.yaml --repeat 3
git add -A && git commit -qm "tickets_v1: runs"
```

## 5. Compare, then decide

Use the skill `evh-compare-and-read`: the leaderboard says whether any order is real; `pair-test`
answers one comparison named in advance; `family-test` one arm against several, corrected.

```evh
evh leaderboard --dataset-id tickets_v1 --json
evh pair-test --dataset-id tickets_v1 --a tickets_lead2_v1 --b tickets_lead1_v1 --json
```

Then `evh-promote-with-evidence` to record the choice, and `evh validate` before you report.

## When to stop and ask

- The goal or the deciding measure is not stated.
- A run would exceed the cap, or no cap is set and the model is paid.
- A host is shared (a GPU another job uses), or data would leave the machine (a hosted model on
  private records) and nobody said it may.
- The evidence does not separate the arms: report "not significantly different", never a winner.
