# The newcomer scenario

A person who has never used the harness pins a release candidate into an empty folder and,
using only the published docs, runs two small evals end to end: a summariser and a
classifier, with no-model baselines, cheap hosted LLMs, an expensive frontier model whose run
becomes the reference, and LLM judges, and one small CPU model, the fastest, for the summaries. They
take the summariser through two eval rounds and a new dataset version, research it in a study on a
validation set confirmed once on a held-out test, run a job, draw the evidence charts, do the loop's steps
again in the Workbench, then browse everything in the catalog and the inspector. It costs under $1 and
keeps a friction log.

**It is a smoke test of the newcomer's path, not a release ritual.** Run it when something a
newcomer touches changed since the last recorded run: the install, getting started, the
tutorials, or the commands and files those steps use (RELEASING step 5). When nothing on that path
changed, skip it and say so in the release PR. One CPU model is enough to show that a local model
runs through an adapter; more only lengthen the run (the first runs used three and took about two
hours, most of it waiting on them).

`make guide-check` already proves that getting started and the offline tutorials (3, 4 and 5)
run as written. This covers what it cannot: real models, a project's own adapters, two tasks in
one project, a frontier reference, real judges, rounds over real evidence, and what a newcomer
has to guess.

First run: 2026-10-24, on the 0.4.0 branch; it found 39 items. Second run: the same day, on the
0.4.0 candidate `e91ff94c`, through a LiteLLM proxy, for $0.17; its friction log found nothing
that blocked, 8 items that needed a guess and 22 of noise or polish. Third run: 2026-10-25, on the
release candidate `80e8f3f5`, through the proxy, for $0.17; nothing blocked, 10 items needed a guess,
23 of noise or polish. Fourth run: 2026-11-02, on the 0.6.0 candidate `797c07e5`, through the proxy,
one CPU model, in 50 minutes, for $0.149; 1 item blocked (fixed before the release), 9 needed a guess,
about 15 of noise or polish. Fifth run: 2026-11-04, on the 0.7.0 release, through the LiteLLM proxy,
one CPU model, in 26 minutes 38 seconds, for $0.1992 printed by the commands plus about $0.03 from arm-smoke
calls; 1 item blocked (judge replies cut off mid-reasoning: a reasoning judge spent max_tokens thinking
and returned nothing, fixed in 0.7.1), 10 needed a guess, about 15 of noise or polish. Sixth run: 2026-11-19, on the
0.8.0 candidate `84237576`, through the LiteLLM proxy, one CPU model, in about an hour, for $0.37 billed (the
frontier classifier run three times and one judging pass that parsed nothing among it); 3 items blocked, 24 needed
a guess, 15 of noise or polish. What each run fixed, and what is still open, is listed at the end.

## Rules for the run

- **Only the published docs.** README → getting started → the tutorials → INTEGRATION →
  RUNBOOK, as a newcomer would reach them. Do not read the code to find out how something works.
  When you have to, that is a finding.
- **A friction log as you go**, one line per item: **B** blocks a newcomer, **F** needs a guess,
  **N** is noise or polish. Note also what worked (OK). Say which doc or command, quote the output.
- **Your own key, your choice of provider.** Any provider the bundled adapter supports: OpenAI or
  any OpenAI-compatible endpoint, OpenRouter, Anthropic, or a LiteLLM proxy (tutorial 2 lists the
  variable each reads). Put the key in the project's `.env` with `EVAL_MAX_COST_USD=1`, and check
  with `evh env-check`. Add up what each command prints it spent (`evh run`:
  `spent $…`; `judge-score`: `spent this run $…`). What that figure is, the provider's bill
  or the system's price table, depends on the provider
  ([RUNBOOK §4](RUNBOOK.md#4-point-the-harness-at-your-system)).
- **Screenshots and logs outside the project folder.** Keep screenshots and the pip install log outside
  the project's `evh-scenario/` folder (e.g. `~/screenshots/` or `/tmp/`) so they do not end up as
  untracked files in the scenario's git tree when you share it.
- **Screenshots of every catalog and inspector page** listed under step 15, at 1400 px wide, and of every
  Workbench screen listed under step 14, at 1400 px and at 390 px (a phone).

## 0 · A project

```bash
mkdir evh-scenario && cd evh-scenario && git init -q
python3 -m venv .venv && . .venv/bin/activate        # or: uv venv --seed --python 3.11 (--seed adds pip)
pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@<candidate sha>#subdirectory=harness"
evh init --store files
pip install torch --index-url https://download.pytorch.org/whl/cpu    # the small models' runtime
pip install transformers sentencepiece rouge-score
```

## 1 · Two datasets, with gold

Write the items yourself, so nothing has to be fetched or licensed:

- **briefs_v1**: 20 short invented local-news briefs (5 sentences each) in
  `data/sources/briefs/`, and a one-sentence summary of each, written by you, in
  `data/sources/briefs_gold/<item_id>.txt`.
- **intents_v1**: 32 one- or two-sentence customer messages in `data/sources/messages/`, each
  labelled billing, technical, account or shipping, in `data/sources/messages_gold/<item_id>.txt`.
  Include a couple that sit between two intents (a shipping refund is billing).

Your answers become a person's labels, promoted to gold with why (a reference set is only ever labels promoted on
purpose):

```bash
evh dataset-create --dataset-id briefs_v1 --source-dir data/sources/briefs --glob "*.txt"
evh dataset-create --dataset-id intents_v1 --source-dir data/sources/messages --glob "*.txt"
evh dataset-materialize --dataset-id briefs_v1 && evh dataset-materialize --dataset-id intents_v1
evh label-import --sheet data/sources/briefs_gold --dataset-id briefs_v1 --set my_gold --by me
evh label-import --sheet data/sources/messages_gold --dataset-id intents_v1 --set my_gold --by me
evh reference-promote --dataset-id briefs_v1 --labels my_gold --tier gold --reason "my own summaries" --by me
evh reference-promote --dataset-id intents_v1 --labels my_gold --tier gold --reason "my own intents" --by me
```

## 2 · Goals

One per eval in `data/goals/`, `brief_summary` and `intent_routing`
([RUNBOOK §4c](RUNBOOK.md#4c-the-goal-file-field-by-field) has every field and its allowed
values): who uses the output, the decision ("which system runs it, given that a frontier model is
too expensive to run on every item"), the measure that decides (`rouge_l`; `accuracy`), the
dataset, the references. A system names no goal: every run names it (`evh run … --goal`).

## 3 · Adapters and arms

- `adapter.py` at the project root for the summaries (tutorial 1's): a **lead** provider (the
  first `sentences` sentences, 1 by default; no model), an **hf** provider (a seq2seq model through
  `AutoModelForSeq2SeqLM.generate`), and the bundled hosted providers
  (`from evaluation_harness.adapter import PROVIDERS, Result`); `score()` returns `rouge_1`,
  `rouge_l` and `output_words`; `PRIMARY_METRIC = "rouge_l"`; `METRIC_DESCRIPTIONS`.
- `adapters/intent.py` for the classifier, named by each intents system (`adapter:`): keyword
  rules, and the hosted providers asked to
  answer `label: <intent>` / `reason: <one sentence>`; `score()` reads the label from the output
  and from the reference (gold is a bare label, silver is a model's two lines);
  `PRIMARY_METRIC = "accuracy"`.

| arm | summaries (`briefs_*`) | classifier (`intents_*`) |
|---|---|---|
| no model | `lead1` | `keywords` |
| small model, CPU (one, the fastest) | `t5_small` | — |
| cheap hosted | `mistral_small` | `mistral_small`, `llama_scout` |
| frontier | `opus` (an expensive model you would not run in production) | `opus` |

Every arm's first system id ends `_v1` (the frontier summariser is `briefs_opus_v1`). Give the
frontier arm room to finish: `max_tokens: 600` (a frontier model that reasons spends part of it
thinking; at 300 one of 32 intents replies stopped short, and a reference refuses a reply cut off).
Silence the model libraries' progress bars and warnings in the adapter as tutorial 1's does, so the
run's output is the harness's.

## 4 · Measure

```bash
git add -A && git commit -qm "datasets, gold, goals, adapters, systems"
evh run --system briefs_mistral_small_v1 --dataset briefs_v1 --goal brief_summary --repeat 3 --dry-run   # price it first
evh arm-smoke --system briefs_mistral_small_v1 --dataset briefs_v1   # a few items, before the full run; prints "spent $…"
evh run --system <hosted id> --dataset briefs_v1 --goal brief_summary --repeat 3   # each cheap hosted arm: its measurement and its noise floor
evh run --system <id> --dataset briefs_v1 --goal brief_summary       # each other arm, once
evh leaderboard briefs_v1
evh family-test briefs_v1 --a briefs_mistral_small_v1 --against briefs_ --metric rouge_l
```

The same for `intents_v1` (`--metric accuracy`). A hosted arm is measured once, as its `--repeat 3` set: that set
is the arm's measurement and shows its noise. A plain run and then a repeat set of the same arm would be two
measurements of it, and `evh run` refuses the set (to measure a run's noise afterwards, repeat that run:
`--purpose repeat --of <run_id>`). The smoke runs and the repeats print what they spent. The slow CPU arm's
progress lines say how long it has left.

## 5 · The frontier arm's outputs become the silver reference

```bash
evh label-from-run --run <the briefs_opus_v1 run_id> --set opus_v1
evh reference-promote --dataset-id briefs_v1 --labels opus_v1 --tier silver --reason "The frontier arm ranks the rest." --by me
evh label-from-run --run <the intents_opus_v1 run_id> --set opus_v1
evh reference-promote --dataset-id intents_v1 --labels opus_v1 --tier silver --reason "The frontier arm ranks the rest." --by me
git add data/labels data/references && git commit -qm "silver from the frontier arm's labels"
evh rescore --dataset-id briefs_v1 --reference-id silver/briefs_v1
evh rescore --dataset-id intents_v1 --reference-id silver/intents_v1
git add data/runs && git commit -qm "the runs re-scored against silver"
evh leaderboard briefs_v1 --label silver    # the author's row is marked
evh silver-calibrate --dataset-id briefs_v1                              # silver authors vs your gold
```

Commit before any other run: an uncommitted label set or reference makes every run after it dirty, and
`label-from-run` refuses a dirty run. If a frontier reply was cut off, `label-from-run` refuses it and names the fix
(more `max_tokens`, a new system id).

**What each step writes; commit all of it** (AGENTS.md rule 3: commit `data/` as the harness writes it; the
`.gitignore` from `evh init` leaves out only `data/materialized/`, caches, `.env`, a pass's checkpoint and the
`.build/` folder a `--scratch` pass writes to):

- Step 4: `evh run` writes `data/runs/<run_id>/`; `arm-smoke` records its report in the model record, `data/models/`.
- This step: `label-from-run` and `reference-promote` write `data/labels/` and `data/references/`; `rescore`
  writes each run's score against silver beside its other scores, `data/runs/<run_id>/scores/<scorer>@silver.…/`.
- Step 6: `judge-score` writes `data/judging-sets/`, `data/judge-verdicts/`, `data/judge-summaries/` and each run's
  judged score, `data/runs/<run_id>/scores/<scorer>@…/`.
- Step 7: `run-promote` writes `data/baselines/`.
- Steps 8 and 9: `round-open`, `round-retire` and `round-close` write `data/rounds/`.
- Step 11: `dataset-split` writes the two sides' datasets and references; `study-run` writes `data/studies/`.

Gold outranks silver, so new runs keep scoring against gold; each run also keeps its score against
silver (`--label silver` reads it). On silver the frontier arm is the yardstick: the leaderboard marks its row and
leaves it out of the ordering test and the frontier, and a goal page never tests it against the leader.

## 6 · Judge

A judge scorer per dataset in `data/scorers/` (two judges from different vendor families, a
`task` block, `explain: true` so each verdict says why), for the summaries' faithfulness and coverage and the
classifier's label fit and reason quality. Its prompt has `{n}`, names each of the task's dimensions and asks for
one JSON object with a list of `{n}` numbers per dimension, as tutorial 3's prompt does: `judge-score` refuses a
prompt that does not name them, before any call. They are not validated, so:

```bash
evh judge-score --dataset-id briefs_v1 --scorer briefs-judge-v1 --unvalidated --dry-run
evh judge-score --dataset-id briefs_v1 --scorer briefs-judge-v1 --unvalidated
evh judge-score --dataset-id briefs_v1 --scorer briefs-judge-v1 --unvalidated --retry-unparsed
evh leaderboard briefs_v1 --label judged/briefs-judge-v1
evh judge-verdicts briefs-judge-v1 --limit 10     # the lowest scores first, each with its reason
```

The same for `intents_v1` with its scorer, then commit what the judging wrote:

```bash
git add data/judging-sets data/judge-verdicts data/judge-summaries data/runs && git commit -qm "the judged runs"
```

A reply that did not parse and is not bare JSON is
committed only as its hash; its text is in the `.withheld/` file the log names, so read why it
failed before `--retry-unparsed`. The judged leaderboard prints the judging pass's agreement and
its position and noise checks under its table: read them before the ranking. A judge billed far from the prices
its scorer declares is named at the end of the pass; correct the prices, or every later dry run estimates wrong.

## 7 · Baselines

Promote, per dataset, the cheap arm closest to the frontier on gold, with a reason that says
what the family test showed and what it costs against the frontier arm. For an arm run with
`--repeat 3`, promote any of its repeats: the baseline records all three and their mean under
`repeats`, the number the catalog, the inspector and the tests read. A promotion is a decision and records who made
it: at a terminal your login, from a script `--by person:NAME`.

```bash
evh run-promote --run <run_id> --reason "<what the tests showed, and what it costs against the frontier arm>"
git add data/baselines && git commit -qm "baselines"
evh baselines                                     # each goal's baseline: current, why, its evidence
```

## 8 · Round 1 of the summariser, after the fact

Make what you have done round 1 of `brief_summary`: carry every arm in, drop the ones the
evidence ruled out, and close it with what it showed.

```bash
evh round-open --goal brief_summary --dataset briefs_v1 \
    --hypothesis "which of four systems, from no model to a frontier LLM, best summarises a brief in one sentence" \
    --keep briefs_lead1_v1,briefs_t5_small_v1,briefs_mistral_small_v1,briefs_opus_v1
git add data/rounds && git commit -qm "brief_summary r1: open"
evh round-evidence brief_summary r1             # the evidence, and the suggested decisions
evh round-retire --goal brief_summary --round r1 --arm briefs_t5_small_v1 --reason "<what the test showed>"
evh round-close --goal brief_summary --round r1 --conclusion "<what r1 showed, and what it decided>"
git add data/rounds && git commit -qm "brief_summary r1: closed"
evh round-list brief_summary                    # the goal's rounds, a line each
```

The carried arms need no system change and no new run: `round-open` says so, and their runs
already count. Use the commands `evh round-evidence` suggests (it prints each as the command that makes
it), and check that its verdicts are `family-test`'s for the same arms against the same leader.

## 9 · Round 2: change one thing

```bash
evh round-open --goal brief_summary --dataset briefs_v1 --from r1 \
    --hypothesis "a prompt that asks for the key facts brings mistral-small closer to the hand-written summaries" \
    --change "briefs_mistral_small_v2: the prompt asks for the news and its key facts, at most 25 words" \
    --keep briefs_mistral_small_v1,briefs_opus_v1 \
    --retire briefs_lead1_v1 --reason "<why it is dropped>" --budget-usd 0.05
# data/systems/briefs_mistral_small_v2.yaml: a new system_id, its prompt in a file, at the top level of the system
# (beside params, not in it), and no params.prompt:
#   prompts: {summary: {file: prompts/brief_summary.txt}}
git add -A && git commit -qm "brief_summary r2: open; mistral-small v2"
evh run --system briefs_mistral_small_v2 --dataset briefs_v1 --goal brief_summary --round r2 --repeat 3
git add data/runs data/prompts && git commit -qm "brief_summary r2: runs"
evh prompt-list && evh prompt-show --name summary --text   # the version the runs used, and its text
evh round-evidence brief_summary r2             # r2 against r1's best, the baseline, the budget
evh chart gain-cost --goal brief_summary --round r2         # each arm's gain against its cost, named only when tested
evh comparison-show --round r2 --goal brief_summary --baseline briefs_mistral_small_v1
evh leaderboard briefs_v1 --round r2
evh catalog && evh catalog-serve                   # screenshot the goal page's rounds now: r2's suggestions show only while it is open
evh round-close --goal brief_summary --round r2 --conclusion "<what r2 showed>" [--promote <run_id>]
git add data/rounds data/baselines && git commit -qm "brief_summary r2: closed"
evh run --system briefs_mistral_small_v2 --dataset briefs_v1 --goal brief_summary --round r2 --dry-run   # refused: r2 is closed
```

`--promote` only if r2 chose a new baseline; it then records the conclusion as the reason. A closed round keeps the
numbers it closed on: it reads the runs it recorded, and names any later run of its systems beside them.

## 10 · A new dataset version

The second version drops one brief and adds one, in a folder of its own, so `briefs_v1`'s sources
stay as they were frozen. The trial's `data/sources/briefs_v2/` is `briefs/` without
`b20_train.txt` and with a new `b21_ferry.txt`; make yours the same way:

```bash
mkdir -p data/sources/briefs_v2 && cp data/sources/briefs/*.txt data/sources/briefs_v2/
rm data/sources/briefs_v2/<one brief>.txt                       # the trial dropped b20_train
$EDITOR data/sources/briefs_v2/<a new brief>.txt                # the trial added b21_ferry
evh dataset-create --dataset-id briefs_v2 --source-dir data/sources/briefs_v2 --glob "*.txt" --from briefs_v1
evh dataset-materialize --dataset-id briefs_v2
evh dataset-show briefs_v2                # made from briefs_v1: 1 added, 1 removed, 0 changed
git add data/sources data/datasets && git commit -qm "briefs_v2 from briefs_v1"
```

## 11 · A study on a validation set, confirmed once on a held-out test

Research belongs on a validation set; a test set is read once, for the decision. Split `briefs_v1`: each side gets
`briefs_v1`'s references on its own items, promoted from the same label sets and recorded with who split it. Add
both sides to `brief_summary`'s `datasets:` (`role: validation` and `role: test`):

```bash
evh dataset-split --dataset-id briefs_v1 --test 0.4 --seed 7 --by me     # briefs_v1_validation, briefs_v1_test, their references
evh dataset-materialize --dataset-id briefs_v1_validation && evh dataset-materialize --dataset-id briefs_v1_test
git add -A && git commit -qm "briefs_v1 split, each side with its references"
```

The study starts from a no-model arm that keeps two sentences, `briefs_lead2_v1` (a new system: the `lead` provider
with `sentences: 2`), and tries one and three. It costs nothing. `lead_study.yaml`, committed with the new system
before anything runs (an uncommitted file makes a run dirty):

```yaml
dataset: briefs_v1_validation
baseline: {system: briefs_lead2_v1}
measure: rouge_l
sampler: grid
accept: {point: {min_gain: 0}}
stop: {trials: 5}
space:
  groups:
    - {name: length, reason: how much of the brief to keep, params: {sentences: [1, 3]}}
```

```bash
git add -A && git commit -qm "briefs_lead2_v1 and the lead_length study's spec"
evh run --system briefs_lead2_v1 --dataset briefs_v1_validation --goal brief_summary   # the study starts from it
git add data/runs && git commit -qm "lead2 on the validation side"
evh study-run --study brief_summary/lead_length --spec lead_study.yaml --dry-run
evh study-run --study brief_summary/lead_length --spec lead_study.yaml
evh study-show brief_summary lead_length
evh chart study-progress --goal brief_summary --study lead_length
evh study-confirm --study brief_summary/lead_length --test briefs_v1_test --rule superiority --dry-run
evh study-confirm --study brief_summary/lead_length --test briefs_v1_test --rule superiority
evh looks                                          # the test set's looks, and the next one's level
git add -A && git commit -qm "brief_summary: the lead_length study, confirmed"
```

A study never promotes: the confirmation is one look at the test set's next level and suggests a promotion only
when the outcome meets the rule. Whatever it finds is the answer; check it says so plainly. With no trial kept,
`study-confirm` refuses and the test set is not read.

## 12 · A job

The Workbench runs its work as jobs; the terminal starts the same ones. Run the no-model arm over `briefs_v2`
as a job and follow it:

```bash
evh jobs-start run --arg system=briefs_lead1_v1 --arg dataset=briefs_v2 --max-cost-usd 0.01   # a free arm spends nothing under any cap
evh jobs-status
evh jobs-logs <job id> --follow
git add data/runs && git commit -qm "lead1 on briefs_v2, as a job"
```

## 13 · The evidence charts

```bash
evh chart intervals --goal brief_summary --dataset briefs_v1     # each arm against the leader, with its interval
evh chart latency --goal brief_summary --dataset briefs_v1
evh chart rank-stability --dataset briefs_v1
evh chart agreement --scorer briefs-judge-v1                       # the two judges, how far they agree
evh chart trend --goal brief_summary
evh chart gain-cost --goal brief_summary --round r2 --svg gain-cost.svg   # outside the project folder
```

Each prints the table it draws and its caption. Check that a quadrant such as "better and cheaper" is named only for a
difference the tests support, and that the numbers are `family-test`'s and `round-evidence`'s for the same arms.

## 14 · The same loop in the Workbench

```bash
evh catalog && evh catalog-serve      # open the Workbench link it prints
```

Follow [tutorial 8](../../docs/tutorials/8-the-workbench.md). Screenshot each screen
at 1400 px and at 390 px: the home (every goal with its next step, what is running, the job from step 12);
`brief_summary`'s steps 1 to 4 (the goal, its datasets, `briefs_v1`'s preparation and reference set, the systems);
the eval (its rounds as tabs, each with its evidence and its decisions); "Review the outputs" (two arms on
`briefs_v1`); "A judge for this goal" (each verdict with its reason); "The held-out test" (the split from step 11,
its look); "Every job"; "Settings". Each screen shows the command it runs: run that command in the terminal and
check the numbers are the screen's.

Then do one round from the Workbench: in "Choose the systems", clone `briefs_mistral_small_v1` with one thing
changed (its temperature); in the eval, open the next round on `briefs_v1`, carrying `briefs_lead1_v1` and
`briefs_mistral_small_v1` (tick each; carried arms are not run again), run the clone in it as a sweep under a $0.05
cap, retire one arm with why, and close the round. Check that `evh round-evidence brief_summary <the round>` and
`evh jobs-status` show what the screens did, with your name as the actor.

## 15 · Validate, then browse it

```bash
evh validate
evh catalog && evh catalog-serve
```

Screenshot: the home page (the tiles, goals at a glance, activity and spend in USD and in tokens,
coverage, what was recorded; the period picker and the tiles' trends); the datasets page and each dataset page (its
baseline with reason, arms grouped by what they are scored against, `briefs_v1` ↔ `briefs_v2`
linked both ways); an arm page (its metrics table, runs, system, conditions, rounds); the goals
page and each goal's page (its answer, its arms grouped by what they are scored against, each
group's recommendation with its reasons, the cost and speed columns and the trade-off charts, the
closed rounds with their conclusions and retired arms; r2's suggestions were captured in step 9,
while r2 was open); each reference page; the metrics page and a metric page (what it measures, its
kind, the goals it decides, per-dataset strip chart); for each dataset, the inspector testing every
arm on gold against the baseline, on silver against the baseline too (the frontier arm wrote that
reference, so against it every other arm reads as worse, as `evh comparison-show` notes), and on the
judge's score; one
item opened in each (the item itself beside the reference and every output); the inspector over r2's
arms; and what a goal page's "test every arm against the leader" link opens. For each page, run its
command (`evh overview-show`, `evh dataset-list`, `evh arm-list`, `evh reference-list`, `evh metric-list`,
`evh goal-leaderboard <goal>`, `evh round-evidence …`, `evh comparison-show --runs …`, `evh comparison-item --runs …
--item …`) and check the numbers are the page's.

## What to check

- Every command either succeeds or refuses with a message that says what to do; no traceback
  from the harness.
- The inspector's verdicts and p-values equal `pair-test`'s for the same pair, and `evh round-evidence`'s
  equal the inspector's for the round's arms. `family-test`'s verdicts are the same; its p-values
  are the same up to 30 items and may differ in the third decimal above that (it says "p: a
  seeded estimate").
- No console errors on any page or screen.
- A newcomer could tell from each page what the goal is, what was compared, against which
  reference, which run is the baseline and why, and what each round decided.
- The spend stays under the cap and matches the sum of what each command printed.
- Every Workbench screen shows its command, and that command in the terminal gives the screen's numbers;
  nothing on a screen is cut off or scrolls the page sideways at 390 px.
- The study's trials ran on the validation side only, its confirmation read the test side once (`evh looks`:
  one look), and every judge verdict in step 6 carries a reason or says it is missing or withheld.
- A closed round keeps the numbers it closed on: a run of its systems made after it closed (the Workbench round's)
  is named beside them, never mixed in.
- Each goal group's recommendation follows its strategy and says why, whatever your numbers are: `evh
  goal-leaderboard`, the goal page and the home page's glance say the same.
- `evh validate` passes at the end.

## Open after the 2026-10-24 runs

Fixed on the 0.4.0 branch: `reference-create --from-run`; references refuse empty and cut-off
outputs; the leaderboard marks the reference's author; reference-create's gold and commit notes;
one install calls hosted models (`openai` and `anthropic` are core, `[llm]` is gone); providers
are documented as a choice, with the variable each reads (tutorial 2); the core times every call;
a run that stops mid-pass names itself and its `--resume` command; `evh run` warns when
outputs stop at `max_tokens`, and the OpenAI-compatible provider records `finish_reason`; V5 no
longer fails two different perfect arms; the goal page groups arms by what they are scored
against and never makes the reference's author the leader; the catalog shows the promoted
baseline and labels judged arms "judge"; the inspector's item view shows the item; `evh init`'s
`.gitignore` has `__pycache__/`; the README and the RUNBOOK lead with `evh` for a pinned user.
Since then: `dataset-create --help` (`--recursive`) and the bundled adapter's retry comment carry
no development history;
`evh env-check` and the `litellm` provider no longer mention `.env.example`; `provider:
openrouter` reads `OPENROUTER_API_KEY` and calls OpenRouter's address by default; with no
reference, `experiment-run` (now `evh run`) named `reference-create --from-run` first, and `evh --help`
described `reference-create` as making references from a run or with a system (both since replaced: a
reference set is labels you promote, 0.6.0); `leaderboard` prints one
table per reference and never averages across them; the bundled adapter stores `overlap_f1`
unrounded, so the rounding note no longer fires for it; `run-promote` prints no `resumed`;
`evh comparison-show --round` reads the goal's measure against the round's leader and names the arms it
leaves out; judged runs are grouped by their judge, and the leaderboard's NOTE names each way
the runs were scored rather than calling "no reference" a reference; `evh round-list` reads a round
against the reference most of its arms use and names the arms it does not compare; the
`pair-test --metric` and `evh --help` texts describe `--round` and the inspect views.

After the second run (0.4.0 candidate `e91ff94c`), fixed in code: `run-promote` of one of an
arm's repeats records every repeat and their mean (`repeats`); `round-open --keep` says carried
arms need no change and no new run; `evh round-list` no longer suggests promoting the run that is
already the baseline; `leaderboard --round` no longer warns about two versions of an arm in a
round that compares them; a judge reply that is not committed keeps its text, git-ignored, in
`.withheld/` beside its record, and the log names the file; the judged leaderboard has a frontier
and prints the judging pass's agreement and position and noise checks; the silver author is left
out of the ordering test and the frontier; the dataset page and `evh dataset-list` sort arms by what
they are scored against; the goal page and `evh goal-leaderboard` show a judge's group, and `evh goal-list
--goal` lists the rounds and marks retired arms; every command prints p the same way (four
decimals, `<0.0001`), and `family-test` says whether its p is exact or a seeded estimate and
labels its column `A wins`; `evh run` prints what it spent and calls the cost and speed
spread what it is; `judge-score` says its spend is the provider's bill where one is reported,
else the price table; `silver-calibrate` explains rho and sibling lift; the catalog counts the
systems behind its arms; "filed" reads "filed under this goal"; the item view says it shows the
latest of N repeats beside their mean, and `evh comparison-item --item` prints the run and the same note;
`evh cost-report` sees the bundled adapter's bills (`_meta.usage.cost`); `evh dataset-list` counts the
systems behind the arms; judged arms keep their version in the inspector; a heading
scrolled to is not hidden under the header; `env-check` names example arms only in a checkout; the
kit's judge scorer points at tutorial 3. Fixed in the docs: every goal field and its allowed
values (RUNBOOK §4c); what each provider records as cost (RUNBOOK §4, tutorial 2); which repeat
to promote; family-test's p against pair-test's above 30 items; tutorial 1's adapter silences the
model library's bars and warnings; this page's system ids (`_v1` throughout), step 10's data and
step 11's screenshots.

After the third run (candidate `80e8f3f5`), fixed in code: `evh round-list` suggests retiring the arm
that wrote a silver reference when the round is read against gold (only on its own silver is it the
yardstick), never suggests retiring the baseline the round started from, says "significantly worse
than" r(n-1)'s best when it is, and suggests `--promote` only for a leader significantly better than
the baseline it started from and not behind the previous round's best (otherwise it says why it
promotes nothing); the goal page's "leader" mark and its "test every arm against its leader" link
use the decision's leader, never a retired arm. Fixed in the docs: how many `--retry-unparsed`
passes, and that a judged table is built from each arm's latest run over the parsed items
(tutorial 3); what `score()` returns with no reference (INTEGRATION); where a provider's model
names come from (tutorial 2); step 11 tests silver against the baseline, not its author. The
paid-run bills are confirmed: `evh cost-report` read 1.00× on all 14 paid runs.

Still open:

- `family-test` and `pair-test`/the inspector read the same pair from different random streams
  above 30 items, so their p can differ in the third decimal; documented, by design.
- The inspector's `wins–losses` reads the row's arm against the baseline, `family-test`'s `A wins`
  reads A against each opponent: labelled, still opposite directions.
- Changed: "filed under this goal" now reads "filed" with the explanation in the text above each
  table (UXS-001 §goal page). Not re-checked by a person since this change: whether it reads clearly, and the heading under the sticky header in a full-page screenshot.
- Judged runs made before the fix have no frontier until they are rebuilt from their stored
  verdicts (`evh judge-score … --no-calls`, $0).
- Not exercised by a run: the direct OpenAI, Anthropic and OpenRouter paths (both runs went
  through a LiteLLM proxy).

After the fourth run (candidate `797c07e5`), fixed in code: the installed `evh` read no project
`.env` (`env-check` said "loaded 0 var(s)"), so a key or a cost cap put there was never in force:
the command imported the module that loads `.env` before it named the command's script, and that
module loads it only for a harness command. `tests/test_installed_commands.py` now runs `env-check`
through an entry script as pip installs it. What was still open from it, and what the fifth run found, is
fixed in 0.7.1:

- Judging: a reply that came back empty is withheld like any other unparsed reply, so V12 passes, and V12
  names the command that rewrites older ones; each unparsed reply says why; a pass whose replies were cut off
  at the token limit ends with a `HINT` (a reasoning judge's `max_tokens`); progress lines arrive as they
  happen through a pipe.
- The inspector names the silver reference's author and marks its row; item cards show each arm's score;
  the goal page's "test every arm against its leader" leaves out retired arms; a judged group below the goal's
  `min_items` says so; home tiles keep their number on one line at 1400 px.
- `family-test --round` takes the round's leader and every other arm in play; `comparison-show --round` names the
  round's leader as such; `silver-calibrate` says what `--ref-match` and `--arm-match` take, with an example
  from your runs; `rescore` ends with a whole sentence and warns about outputs cut off at `max_tokens`;
  `score-preview` says when a goal holds no measured run to re-score.
- `evh run`'s "spent" says whether it is the provider's bill or the system's price table; no "warmed up in
  0ms" for arms with nothing to load; the dry run counts the system's prompt; `arm-smoke` prints each reply
  and what it spent, and the overview and the catalog count smoke spend.
- Leaderboards fit the terminal (`--wide` for every column), and "dominated" says what it means;
  `cost-report` names each repeat; `evh baselines` shows the repeats' mean; `evh round-list` prints a
  round's conclusion whole; the `comparison-show` conditions table and `evh goal-leaderboard` headers no longer cut or
  misalign.
- Step 0: `uv venv` makes a venv with no pip; `--seed` adds it.

Not exercised by a run yet: the direct OpenAI, Anthropic and OpenRouter paths (every run went through a
LiteLLM proxy).

The fifth run (the 0.7.0 release) confirmed that fix: `env-check` said "loaded 4 var(s)".

After the sixth run (candidate `84237576`), fixed in code:

- A repeat set run beside a plain run of the same arm is refused by `evh run`, before any call, with the way to
  repeat a run instead (`--purpose repeat --of <run_id>`): two measurements of one system no longer reach `evh
  validate` (V8).
- The Workbench's round form carries arms one by one, and only from a round on the same dataset; a measured system
  is carried, never run again. `round-carry` takes a measured system too.
- A closed round reads the runs it recorded: a later run of its systems is named "since then", not mixed into its
  numbers.
- `dataset-split` gives each side the parent's references on its own items, recorded with who split it (`--by`).
- `judge-score` refuses a grade prompt that does not name the task's dimensions, before any call, and an unparsed
  grade names the keys it expected. A judge or an arm billed far from the prices its file declares is named.
- `jobs-start` says a spending job's cap must be above 0.
- The leaderboard says why the goal recommends what it does, under the goal's line; `family-test` prints wins,
  losses and ties; `round-evidence`, `evh baselines` and the records print p and scores the way every command does.
- `env-check` says where each variable came from (the shell or `.env`); a CPU arm's progress line says how long it
  has left; `rank-stability` measures the sizes it reports.
- The Workbench: no sideways scroll at 390 px, no console errors where a chart has nothing to draw yet (`optional=1`),
  Home shows its commands, and the open-round form is on the last round's tab only. The catalog leaves the silver
  author out of a leader link's test.

Fixed in the docs: a run names its goal, not a system (step 2); the frontier arm's `max_tokens` is 600 (step 3); a
hosted arm is measured once, as its `--repeat 3` set (step 4); commit after each label-from-run (step 5); the judge
prompt names its dimensions (step 6); the actor of a decision (step 7); `round-evidence` for a round's evidence
(steps 8 and 9); where a system's prompt file goes (step 9); `briefs_v2` is materialized (step 10); each side's
references come with the split, and the study starts from a two-sentence arm so it has something to find (step 11);
the job's cap (step 12); the Workbench round is the next one, whatever its number (step 14); `goal-leaderboard` and
`comparison-item` (step 15); no removed variable or folder of runs left in any doc (`tests/check_commands.py` now
refuses a variable nothing reads and a folder of runs beside `data/runs`).

Still open from the sixth run:

- `rank-stability` counts `briefs_mistral_small_v1` and `_v2` as two arms: they are two systems, by design.
- `evh arm-list` shows the baseline arm "retired in r4" when a round retired it: accurate, kept.
- The inspector's Conditions header was reported to leave out `t5_small_v1`; a screenshot shows the header, with
  "baseline" on the next line in the plain text. Not reproduced.
- The Workbench's evidence charts were reported to read "Reading the chart…" for over 2.5 s; measured at 0.15 to
  0.47 s each. Not changed.
- Not re-checked by a run: whether "Review the outputs" shows its command before a sheet is made, and whether a name
  typed in the Workbench is the round record's actor when the server was started with `EVH_ACTOR` set.
- The full-page screenshots repeat the sticky header mid-page: a capture artefact.
