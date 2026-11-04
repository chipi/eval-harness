---
name: evh-evaluate-a-system
description: Measure a system with eval-harness (evh) from nothing to a recorded decision — freeze a dataset (from files or from production records), make a reference, run each version of the system as an arm, compare them with paired tests, and promote the winner with a reason. Use when asked to "evaluate", "measure", "benchmark", "compare versions of" or "improve" a system with evh, or when starting evh in a project.
metadata:
  harness-version: "0.7.0"
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

An arm that is a change you expect to matter carries its prediction: a `hypothesis:` block in its
config (`against` the config it is compared with, the `measure`, the `direction` better, worse or
no-worse, and a `statement`), written before the run and committed with it. The run records it and
whether it was committed first, and `pair-test` then reports "named in advance: yes". `evh validate`
and `evh run` refuse a block that names no such config or measure.

If your system's code lives outside this tree, pin its commit in the arm's params
(`system_commit: <sha>`): the run records only this project's commit, and params are part of what
was measured.

```evh
cp tutorial/configs/tickets_*.yaml data/configs/
cat >> data/configs/tickets_lead2.yaml <<'EOF'
hypothesis:
  against: tickets_lead1_v1
  measure: overlap_f1
  direction: better
  statement: "two leading sentences recover more of a ticket's gold summary than one"
EOF
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

Cost first (`--dry-run`: one call per item, not an upper bound), a few items next (`evh arm-smoke --config C`,
and read the replies; the dry run then shows its `MEASURED` cost, the number to cap from), then
the full run. `--repeat 3` measures an arm's own noise.

Working in rounds (one line of investigation each: `evh round-open --goal G --dataset D --hypothesis
"..."`)? Open the round **before** its arms run: a new arm names it in its config (`round: rN`,
beside `goal:`); an arm already run joins only when a round is opened with `--keep CONFIG_ID`.

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

`values.hypothesis` says whether the pair was named in advance (the `hypothesis:` of step 2, committed
before the run) and whether the result agrees with its direction; without one, the test is valid only
for a pair you chose before reading the table.

**Read the items before you trust a difference.** A significant mean can come from a handful of items,
or from evidence that gave the answer away. List the items the two arms decided differently, then open
a few:

```evh
evh inspect --runs tickets_lead1_v1,tickets_lead2_v1 --disagree --json
evh inspect --runs tickets_lead1_v1,tickets_lead2_v1 --item t01_login
```

Check that the frozen evidence holds only what the system could see when it decided. Evidence
rebuilt afterwards that states the present instead of the past (a status as it is today, a count
that includes what happened later) is hindsight: it makes the arm look good for a reason it did
not have in production. Stop and say so; the dataset needs rebuilding as `_v2`.

Then `evh-promote-with-evidence` to record the choice, and `evh validate` before you report.

## Measure one change against an existing baseline

The project already has a baseline and you changed one thing. Read the baseline and its config, copy
the config under a new `config_id` with the change and a hypothesis, commit, then measure it the way
the baseline was measured (the same dataset, reference and repeats) and test it against the baseline.

1. `evh goals --goal G --json`: `values.baseline` is the baseline arm; `evh arms --arm <that arm> --json`
   gives its config and how many repeats it has.
2. Copy that config, give it a new `config_id`, make the one change, and add the `hypothesis:` block
   (`against` the baseline's `config_id`). Commit.
3. `evh run --config C --dry-run`, then `evh arm-smoke --config C` and read the replies, then
   `evh run --config C --repeat N` with the baseline's number of repeats.
4. `evh pair-test --dataset-id D --a NEW --b BASELINE --json`, and read the items (step 5).

The same on the tutorial kit, with `tickets_lead1_v1` standing as the baseline:

```evh
cp tutorial/goals/tickets_summary.yaml data/goals/
evh goals --goal tickets_summary --json
sed -e 's/tickets_lead1_v1/tickets_lead3_v1/' -e 's/sentences: 1/sentences: 3/' data/configs/tickets_lead1.yaml > data/configs/tickets_lead3.yaml
cat >> data/configs/tickets_lead3.yaml <<'EOF'
hypothesis:
  against: tickets_lead1_v1
  measure: overlap_f1
  direction: better
  statement: "three leading sentences recover more of the gold summary than one"
EOF
git add -A && git commit -qm "tickets_lead3_v1: one change against lead1, its hypothesis"
evh run --config data/configs/tickets_lead3.yaml --dry-run
evh arm-smoke --config data/configs/tickets_lead3.yaml
evh run --config data/configs/tickets_lead3.yaml --repeat 3
git add -A && git commit -qm "tickets_lead3_v1: runs"
evh pair-test --dataset-id tickets_v1 --a tickets_lead3_v1 --b tickets_lead1_v1 --json
```

## When to stop and ask

- The goal or the deciding measure is not stated.
- A run would exceed the cap, or no cap is set and the model is paid.
- A host is shared (a GPU another job uses), or data would leave the machine (a hosted model on
  private records) and nobody said it may.
- The evidence does not separate the arms: report "not significantly different", never a winner.
- The change is outside what the adapter replays (a step, a tool or a data source the adapter does
  not run): evh cannot measure it here; say so rather than measuring something else.
