---
name: evh-evaluate-a-system
description: Measure a system with eval-harness (evh) from nothing to a recorded decision — freeze a dataset (from files or from production records), make a reference, run each version of the system as an arm, compare them with paired tests, and promote the winner with a reason. Use when asked to "evaluate", "measure", "benchmark", "compare versions of" or "improve" a system with evh, or when starting evh in a project.
metadata:
  harness-version: "0.8.0.dev0"
---

# Evaluate a system with evh

The loop: **dataset → reference → systems → runs → comparison → decision.** Each step writes files
under `data/` that are frozen once written; a change is a new id. The project's `AGENTS.md`
(written by `evh init`) holds the rules; read it first. This skill is the procedure.

A project keeps `data/` as files, or in one database (`store: sqlite`, RFC-025). Put a setting in
with `evh data-put <path under data/> <file>` and read one with `evh data-show --text <path>`, never
with `cp` or `cat` on `data/`: those work in both stores, and they check a setting before it is
kept. Edit a copy outside `data/` (here in a fresh temporary folder, `$D`), then put it in.

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

## 2. Systems, committed

A system is one version of what you evaluate: a YAML file in `data/systems/`, named by its unique
`system_id`, naming the provider (or your `adapter.py`), the model, the prompt and the settings. It
names no dataset: a run puts it on one (`evh run --system ID --dataset D`). One change, one new
`system_id`; never edit a system that has runs.

A system that is a change you expect to matter carries its prediction: a `hypothesis:` block in it
(`against` the system it is compared with, the `measure`, the `direction` better, worse or no-worse,
and a `statement`), written before the run and committed with it. The run records it and whether it
was committed first, and `pair-test` then reports "named in advance: yes". `evh validate` and
`evh run` refuse a block that names no such system or measure. "Named in advance" is told from
git, so it needs a project that keeps its data as files in git: in the database store a setting is
not in git, and the run records it as not determinable.

If your system's code lives outside this tree, pin its commit in the system's params
(`system_commit: <sha>`): the run records only this project's commit, and params are part of what
was measured.

```evh
D=$(mktemp -d) && cp tutorial/systems/tickets_*.yaml "$D"/
cat >> "$D"/tickets_lead2_v1.yaml <<'EOF'
hypothesis:
  against: tickets_lead1_v1
  measure: overlap_f1
  direction: better
  statement: "two leading sentences recover more of a ticket's gold summary than one"
EOF
for f in "$D"/tickets_*.yaml; do evh data-put "systems/$(basename "$f")" "$f"; done
rm -r "$D"
git add -A && git commit -qm "tickets_v1: dataset and systems" --allow-empty
```

Commit before every run: a run records the commit it ran from, and one from a dirty tree is refused
later. (In the database store the commit holds the project's code, not its data: `--allow-empty`
keeps the step the same there.)

## 3. A reference

What each item is scored against. In order of strength:

- **gold**: a person's labels (`evh label-sheet` for them to fill, `evh label-import` to read it).
  Never import labels you made as a person's.
- **production's outcomes**: `evh label-from-capture --dataset-id D --capture C --map rules.yaml --set S`.
- **silver**: the best system's outputs, as a model's labels: good for ranking the rest, not for
  claiming correctness.

```evh
RUN=$(evh run --system tickets_author_v1 --dataset tickets_v1 --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["result"]["values"]["runs"][0]["run_id"])')
evh label-from-run --run "$RUN" --set author_v1
evh reference-promote --dataset-id tickets_v1 --labels author_v1 --tier silver --reason "the author arm ranks the others until a person writes gold" --by agent
git add -A && git commit -qm "silver/tickets_v1" --allow-empty
```

## 4. Run each system

Cost first (`--dry-run`: one call per item, not an upper bound), a few items next (`evh arm-smoke
--system S --dataset D`, and read the replies; the dry run then shows its `MEASURED` cost, the number
to cap from), then the full run. `--repeat 3` measures a system's own noise. A run names the goal it
is for with `--goal G`.

Working in rounds (one line of investigation each: `evh round-open --goal G --dataset D --hypothesis
"..."`)? Open the round **before** its systems run: a new one runs in it (`--goal G --round rN`); one
already run joins only when a round is opened with `--keep SYSTEM_ID`.

```evh
evh run --system tickets_lead1_v1 --dataset tickets_v1 --dry-run
evh run --system tickets_lead1_v1 --dataset tickets_v1 --repeat 3
evh run --system tickets_lead2_v1 --dataset tickets_v1 --repeat 3
git add -A && git commit -qm "tickets_v1: runs" --allow-empty
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

The project already has a baseline and you changed one thing. Read the baseline and its system, copy
the system under a new `system_id` with the change and a hypothesis, commit, then measure it the way
the baseline was measured (the same dataset, reference and repeats) and test it against the baseline.

1. `evh goals --goal G --json`: `values.baseline` is the baseline arm; `evh arms --arm <that arm> --json`
   gives its system and how many repeats it has.
2. Copy that system (`evh data-show --text systems/<it>.yaml` into a draft), give it a new
   `system_id` (and the file its name), make the one change, add the `hypothesis:` block (`against`
   the baseline's `system_id`), and put it in with `evh data-put`. Commit.
3. `evh run --system S --dataset D --dry-run`, then `evh arm-smoke --system S --dataset D` and read the
   replies, then `evh run --system S --dataset D --goal G --repeat N` with the baseline's number of
   repeats.
4. `evh pair-test --dataset-id D --a NEW --b BASELINE --json`, and read the items (step 5).

The same on the tutorial kit, with `tickets_lead1_v1` standing as the baseline:

```evh
evh data-put goals/tickets_summary.yaml tutorial/goals/tickets_summary.yaml
evh goals --goal tickets_summary --json
D=$(mktemp -d)
evh data-show --text systems/tickets_lead1_v1.yaml | sed -e 's/tickets_lead1_v1/tickets_lead3_v1/' -e 's/sentences: 1/sentences: 3/' > "$D"/tickets_lead3_v1.yaml
cat >> "$D"/tickets_lead3_v1.yaml <<'EOF'
hypothesis:
  against: tickets_lead1_v1
  measure: overlap_f1
  direction: better
  statement: "three leading sentences recover more of the gold summary than one"
EOF
evh data-put systems/tickets_lead3_v1.yaml "$D"/tickets_lead3_v1.yaml && rm -r "$D"
git add -A && git commit -qm "tickets_lead3_v1: one change against lead1, its hypothesis" --allow-empty
evh run --system tickets_lead3_v1 --dataset tickets_v1 --dry-run
evh arm-smoke --system tickets_lead3_v1 --dataset tickets_v1
evh run --system tickets_lead3_v1 --dataset tickets_v1 --goal tickets_summary --repeat 3
git add -A && git commit -qm "tickets_lead3_v1: runs" --allow-empty
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
