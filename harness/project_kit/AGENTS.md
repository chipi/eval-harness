# Working in this project: for an agent

This project measures a system with **eval-harness** (the `evh` command): it freezes a dataset,
runs one or more versions of the system on it ("arms"), scores every output against a
reference, and tests whether one arm is really better than another. `evh init` wrote this file;
edit it to add what is particular to this project.

Everything you need runs in a shell. **You do not need the catalog** (`evh catalog`,
`evh catalog-serve`: HTML pages for a person) **or `evh mcp`** (the same read commands as MCP
tools, for an agent without a shell, or for a team). Every page and every tool is also a
command; read them with `--json`.

The procedures are skills: `evh skills-install` copies them into `.claude/skills/` (or
`--target` any agent's skill directory): `evh-evaluate-a-system` (from nothing to a decision),
`evh-compare-and-read` (which arm leads, and whether it is real), `evh-promote-with-evidence`
(recording the choice). This file holds the rules they follow.

## The rules

1. **Frozen means frozen.** Never edit or delete anything under `data/datasets/`, `data/runs*/`,
   `data/labels/`, `data/references/` or `data/baselines/`. A change is a new id: a dataset
   `_v2`, a new label set, a new reference.
2. **One change, one new `config_id`.** An arm is a config in `data/configs/`. To try a change
   (a prompt, a model, a setting), copy the config and give it a new `config_id`; never edit a
   config that has runs. Running the same config again is `evh run --repeat N`, a deliberate
   repeat; any other second run of a `config_id` fails `evh validate` (V8).
3. **Commit before you run.** A run records the commit it was made from; a run from a dirty tree
   is refused later (`label-from-run`, `run-promote`). Commit `data/` as the harness writes it,
   runs included: they are the evidence. `.gitignore` already keeps out what is derived.
4. **Spending is capped, and checked first.** Before any run that calls a paid model, set
   `EVAL_MAX_COST_USD` (with none, a run has no cap). `evh run --config C --dry-run` estimates one
   call per item and is not an upper bound: an arm that makes several calls per item costs more.
   Run `evh arm-smoke --config C` (a few items), read the replies, and set the cap from the
   measured cost it records (the dry run then shows it as `MEASURED`) before the full run.
5. **What you may do** (the owner's rule for agents, 2026-11-04): run arms, make labels and
   references, and promote a baseline **when your operator asked for that task**, within the
   cap. A promotion's `--reason` says who asked and why. Closing a round, and anything past the
   cap, stay your operator's: hand over the exact command.
6. **Labels say who made them.** `evh label-import` records a set as **a person's**: never use it
   for labels you made. Your labels go in a sheet read back with
   `evh sheet-import --kind model`; outcomes your system's production recorded become labels
   with `evh label-from-capture` (rules over the outcomes). Gold is a person's labels: the
   harness records each set's source but does not stop you, so never promote your own labels
   at gold (silver is for those).
7. **Validate, then report with evidence.** `evh validate` checks the whole tree. A claim that
   one arm is better cites the paired test that says so (`evh pair-test`, `evh goals`), not a
   mean.
8. **Name the comparison before the run.** Write a `hypothesis:` into the new arm's config
   (`against`, `measure`, `direction`, `statement`) and commit it before `evh run`. `evh pair-test`
   then reports "named in advance: yes"; a pair you chose after reading the table is a search, and
   `evh family-test` is its test.

## From nothing to a decision

```bash
evh init                                        # done: folders, .gitignore, this file
# production records -> a dataset (or files: evh dataset-create --dataset-id D --source-dir data/sources/NAME)
evh capture --importer jsonl --query '{"path": "prod.jsonl"}' --capture prod_c1
evh dataset-from-capture prod_c1 --dataset-id prod_v1
evh dataset-materialize --dataset-id prod_v1
# what is right for each item: a person's labels (gold), production's outcomes, or yours (model)
evh label-from-capture --dataset-id prod_v1 --capture prod_c1 --map rules.yaml --set outcomes
evh reference-promote --dataset-id prod_v1 --labels outcomes --tier silver --reason "..." --by "<who>"
# arms: one config per version of your system (data/configs/*.yaml), your adapter if it is yours
git add -A && git commit -m "dataset, reference, arms"
evh run --config data/configs/<arm>.yaml --dry-run
evh arm-smoke --config data/configs/<arm>.yaml
evh run --config data/configs/<arm>.yaml        # prints the run id it wrote
git add -A && git commit -m "runs"
# compare and decide
evh leaderboard --dataset-id prod_v1 --json
evh pair-test --dataset-id prod_v1 --a <new_config_id> --b <baseline_config_id> --json
evh run-promote --run <run_id> --reason "<who asked>: <why>"
```

A goal (`data/goals/<goal_id>.yaml`) says what the evaluation is for and which measure decides;
with one, `evh goals --goal <goal_id> --json` gives the leader, the baseline, the paired test
and what the goal recommends, in one answer.

Rounds are optional: a round is one line of investigation of a goal, with its hypothesis, its arms,
the ones retired and a conclusion (`evh round-open`, `evh round-retire`, `evh rounds --goal G --json`
for what the evidence suggests next). Open the round **before** its arms run: a new arm names it in
its config (`round: rN`); an arm already run joins only through `round-open --keep CONFIG_ID`.
Closing it is your operator's (rule 5).

## Reading results

| question | command |
| --- | --- |
| what is in the project | `evh overview --json`, `evh datasets --json`, `evh arms --json` |
| which arm leads, and is it significant | `evh goals --goal G --json`; `evh leaderboard --dataset-id D --json` |
| is A better than B | `evh pair-test --dataset-id D --a A --b B --json` |
| one arm against several, corrected | `evh family-test --dataset-id D --a A --against B,C --json` (`--against`: a comma list of config ids, or one substring) |
| where two arms differ, item by item | `evh inspect --runs A,B --json` |
| what two runs did differently | `evh run-compare --baseline RUN_A --candidate RUN_B --json` |
| is the tree consistent | `evh validate` |

Every command takes `--help`: it is the reference for every flag. The full documentation:
https://evals.humancopilot.eu/docs/ (start at "Getting started"; "Integration" for your own
system; "Runbook" for every command).
