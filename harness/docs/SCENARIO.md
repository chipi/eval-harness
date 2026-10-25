# The newcomer scenario

A person who has never used the harness pins a release candidate into an empty folder and,
using only the published docs, runs two small experiments end to end: a summariser and a
classifier, each with a small CPU model, cheap hosted LLMs, an expensive frontier model whose run
becomes the reference, and LLM judges. They take the summariser through two experiment rounds
and a new dataset version, then browse everything in the catalog and the inspector. It costs
under $1 and takes about two hours. Run it before every release (RELEASING step 4), and keep the
friction log.

`make guide-check` already proves that getting started and the offline tutorials (3, 4 and 5)
run as written. This covers what it cannot: real models, a project's own adapters, two tasks in
one project, a frontier reference, real judges, rounds over real evidence, and what a newcomer
has to guess.

First run: 2026-10-24, on the 0.4.0 branch; it found 39 items. Second run: the same day, on the
0.4.0 candidate `e91ff94c`, through a LiteLLM proxy, for $0.17; its friction log found nothing
that blocked, 8 items that needed a guess and 22 of noise or polish. What is still open is listed
at the end.

## Rules for the run

- **Only the published docs.** README → getting started → the tutorials → INTEGRATION →
  RUNBOOK, as a newcomer would reach them. Do not read the code to find out how something works.
  When you have to, that is a finding.
- **A friction log as you go**, one line per item: **B** blocks a newcomer, **F** needs a guess,
  **N** is noise or polish. Note also what worked (OK). Say which doc or command, quote the output.
- **Your own key, your choice of provider.** Any provider the bundled adapter supports: OpenAI or
  any OpenAI-compatible endpoint, OpenRouter, Anthropic, or a LiteLLM proxy (tutorial 2 lists the
  variable each reads). Put the key in the project's `.env` with `EVAL_MAX_COST_USD=1`, and check
  with `evh env-check`. Add up what each command prints it spent (`experiment-run`:
  `spent $…`; `judge-score`: `spent this run $…`). What that figure is, the provider's bill
  or the config's price table, depends on the provider
  ([RUNBOOK §4](RUNBOOK.md#4-point-the-harness-at-your-system)).
- **Screenshots of every catalog and inspector page** listed under step 11, at 1400 px wide.

## 0 · A project

```bash
mkdir evh-scenario && cd evh-scenario && git init -q
python3 -m venv .venv && . .venv/bin/activate        # or: uv venv --python 3.11
pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@<candidate sha>#subdirectory=harness"
evh init
pip install torch --index-url https://download.pytorch.org/whl/cpu    # the small models' runtime
pip install transformers sentencepiece rouge-score
```

## 1 · Two datasets, with gold

Write the items yourself, so nothing has to be fetched or licensed:

- **briefs_v1**: 20 short invented local-news briefs (5 sentences each) in
  `data/sources/briefs/`, and a one-sentence summary of each, written by you, in
  `data/references/gold/briefs_v1/<item_id>.txt`.
- **intents_v1**: 32 one- or two-sentence customer messages in `data/sources/messages/`, each
  labelled billing, technical, account or shipping, in `data/references/gold/intents_v1/`.
  Include a couple that sit between two intents (a shipping refund is billing).

```bash
evh dataset-create --dataset-id briefs_v1 --source-dir data/sources/briefs --glob "*.txt"
evh dataset-create --dataset-id intents_v1 --source-dir data/sources/messages --glob "*.txt"
evh dataset-materialize --dataset-id briefs_v1 && evh dataset-materialize --dataset-id intents_v1
```

## 2 · Goals

One per experiment in `data/goals/`, `brief_summary` and `intent_routing`
([RUNBOOK §4c](RUNBOOK.md#4c-the-goal-file-field-by-field) has every field and its allowed
values): who uses the output, the decision ("which system runs it, given that a frontier model is
too expensive to run on every item"), the measure that decides (`rouge_l`; `accuracy`), the
dataset, the references. Every config names its goal (`goal: …`).

## 3 · Adapters and arms

- `adapter.py` at the project root for the summaries (tutorial 1's): a **lead** provider (the
  first sentence; no model), an **hf** provider (a seq2seq model through
  `AutoModelForSeq2SeqLM.generate`), and the bundled hosted providers
  (`from evaluation_harness.adapter import PROVIDERS, Result`); `score()` returns `rouge_1`,
  `rouge_l` and `output_words`; `PRIMARY_METRIC = "rouge_l"`; `METRIC_DESCRIPTIONS`.
- `adapters/intent.py` for the classifier, named by each intents config (`adapter:`): keyword
  rules, zero-shot NLI (`pipeline("zero-shot-classification")`), and the hosted providers asked to
  answer `label: <intent>` / `reason: <one sentence>`; `score()` reads the label from the output
  and from the reference (gold is a bare label, silver is a model's two lines);
  `PRIMARY_METRIC = "accuracy"`.

| arm | summaries (`briefs_*`) | classifier (`intents_*`) |
|---|---|---|
| no model | `lead1` | `keywords` |
| small model, CPU | `t5_small`, `flan_t5_small` | `nli_distilbert` (`typeform/distilbert-base-uncased-mnli`) |
| cheap hosted | `mistral_small` | `mistral_small`, `llama_scout` |
| frontier | `opus` (an expensive model you would not run in production) | `opus` |

Every arm's first config id ends `_v1` (the frontier summariser is `briefs_opus_v1`). Give the
frontier arm room to finish: `max_tokens: 300`. Silence the model libraries' progress bars and
warnings in the adapter as tutorial 1's does, so the run's output is the harness's.

## 4 · Measure

```bash
git add -A && git commit -qm "datasets, gold, goals, adapters, arms"
evh experiment-run --config data/configs/briefs_mistral_small.yaml --dry-run    # price it first
evh experiment-run --config data/configs/<arm>.yaml                              # every arm
evh experiment-run --config data/configs/<hosted arm>.yaml --repeat 3            # the noise floor; prints "spent $…"
evh leaderboard --dataset-id briefs_v1
evh family-test --dataset-id briefs_v1 --a briefs_mistral_small_v1 --against briefs_ --metric rouge_l
```

The same for `intents_v1` (`--metric accuracy`).

## 5 · The frontier arm's run becomes the silver reference

```bash
evh reference-create --dataset-id briefs_v1 --from-run <the briefs_opus_v1 run_id>
git add data/references && git commit -qm "silver/briefs_v1 from the frontier arm"
evh reference-create --dataset-id intents_v1 --from-run <the intents_opus_v1 run_id>
git add data/references && git commit -qm "silver/intents_v1 from the frontier arm"
evh rescore --dataset-id briefs_v1 --reference-id silver/briefs_v1 --out data/runs-silver
evh rescore --dataset-id intents_v1 --reference-id silver/intents_v1 --out data/runs-silver
EVAL_RUNS_DIR=data/runs-silver evh leaderboard --dataset-id briefs_v1    # the author's row is marked
evh silver-calibrate --dataset-id briefs_v1                              # silver authors vs your gold
```

Commit each reference before the next run: an uncommitted reference makes every later run dirty,
and `--from-run` refuses a dirty run. Gold outranks silver, so new runs keep scoring against
gold; `data/runs-silver` holds the same runs scored against the frontier arm. On silver the
frontier arm is the yardstick: the leaderboard marks its row and leaves it out of the ordering
test and the frontier.

## 6 · Judge

A judge scorer per dataset in `data/scorers/` (two judges from different vendor families, a
`task` block, a prompt with `{n}`), for the summaries' faithfulness and coverage and the
classifier's label fit and reason quality. They are not validated, so:

```bash
evh judge-score --dataset-id briefs_v1 --scorer briefs-judge-v1 --unvalidated --dry-run
evh judge-score --dataset-id briefs_v1 --scorer briefs-judge-v1 --unvalidated
evh judge-score --dataset-id briefs_v1 --scorer briefs-judge-v1 --unvalidated --retry-unparsed
EVAL_RUNS_DIR=data/runs-judged/briefs-judge-v1 evh leaderboard --dataset-id briefs_v1
```

The same for `intents_v1` with its scorer. A reply that did not parse and is not bare JSON is
committed only as its hash; its text is in the `.withheld/` file the log names, so read why it
failed before `--retry-unparsed`. The judged leaderboard prints the judging pass's agreement and
its position and noise checks under its table: read them before the ranking.

## 7 · Baselines

Promote, per dataset, the cheap arm closest to the frontier on gold, with a reason that says
what the family test showed and what it costs against the frontier arm. For an arm run with
`--repeat 3`, promote any of its repeats: the baseline records all three and their mean under
`repeats`, the number the catalog, the inspector and the tests read.

```bash
evh run-promote --run <run_id> --reason "<what the tests showed, and what it costs against the frontier arm>"
git add data/baselines && git commit -qm "baselines"
```

## 8 · Round 1 of the summariser, after the fact

Make what you have done round 1 of `brief_summary`: carry every arm in, drop the ones the
evidence ruled out, and close it with what it showed.

```bash
evh round-open --goal brief_summary --dataset briefs_v1 \
    --hypothesis "which of five systems, from no model to a frontier LLM, best summarises a brief in one sentence" \
    --keep briefs_lead1_v1,briefs_t5_small_v1,briefs_flan_t5_small_v1,briefs_mistral_small_v1,briefs_opus_v1
git add data/rounds && git commit -qm "brief_summary r1: open"
evh rounds --goal brief_summary                    # the evidence, and the suggested decisions
evh round-retire --goal brief_summary --round r1 --arm briefs_flan_t5_small_v1 --reason "<what the test showed>"
evh round-retire --goal brief_summary --round r1 --arm briefs_t5_small_v1 --reason "<what the test showed>"
evh round-close --goal brief_summary --round r1 --conclusion "<what r1 showed, and what it decided>"
git add data/rounds && git commit -qm "brief_summary r1: closed"
```

The carried arms need no config change and no new run: `round-open` says so, and their runs
already count. Use the commands `evh rounds` suggests (it prints each as the command that makes
it), and check that its verdicts are `family-test`'s for the same arms against the same leader.

## 9 · Round 2: change one thing

```bash
evh round-open --goal brief_summary --dataset briefs_v1 --from r1 \
    --hypothesis "a prompt that asks for the key facts brings mistral-small closer to the hand-written summaries" \
    --change "briefs_mistral_small_v2: the prompt asks for the news and its key facts, at most 25 words" \
    --keep briefs_mistral_small_v1,briefs_opus_v1 \
    --retire briefs_lead1_v1 --reason "<why it is dropped>" --budget-usd 0.05
# data/configs/briefs_mistral_small_v2.yaml: the new prompt, a new config_id, and `round: r2` beside `goal:`
git add -A && git commit -qm "brief_summary r2: open; mistral-small v2"
evh experiment-run --config data/configs/briefs_mistral_small_v2.yaml --repeat 3
git add data/runs && git commit -qm "brief_summary r2: runs"
evh rounds --goal brief_summary                    # r2 against r1's best, the baseline, the budget
evh inspect --round r2 --goal brief_summary --baseline briefs_mistral_small_v1
evh leaderboard --dataset-id briefs_v1 --round r2
evh catalog && evh catalog-serve                   # screenshot the goal page's rounds now: r2's suggestions show only while it is open
evh round-close --goal brief_summary --round r2 --conclusion "<what r2 showed>" [--promote <run_id>]
git add data/rounds data/baselines && git commit -qm "brief_summary r2: closed"
evh experiment-run --config data/configs/briefs_mistral_small_v2.yaml --dry-run   # refused: r2 is closed
```

`--promote` only if r2 chose a new baseline; it then records the conclusion as the reason.

## 10 · A new dataset version

The second version drops one brief and adds one, in a folder of its own, so `briefs_v1`'s sources
stay as they were frozen. The trial's `data/sources/briefs_v2/` is `briefs/` without
`b20_train.txt` and with a new `b21_ferry.txt`; make yours the same way:

```bash
mkdir -p data/sources/briefs_v2 && cp data/sources/briefs/*.txt data/sources/briefs_v2/
rm data/sources/briefs_v2/<one brief>.txt                       # the trial dropped b20_train
$EDITOR data/sources/briefs_v2/<a new brief>.txt                # the trial added b21_ferry
evh dataset-create --dataset-id briefs_v2 --source-dir data/sources/briefs_v2 --glob "*.txt" --from briefs_v1
evh datasets --dataset-id briefs_v2                # made from briefs_v1: 1 added, 1 removed, 0 changed
git add data/sources data/datasets && git commit -qm "briefs_v2 from briefs_v1"
```

## 11 · Validate, then browse it

```bash
evh validate
evh catalog && evh catalog-serve
```

Screenshot: the home page (the tiles, goals at a glance, activity and spend in USD and in tokens,
coverage, what was recorded; last 14 days and all time); the datasets page and each dataset page (its
baseline with reason, arms grouped by what they are scored against, `briefs_v1` ↔ `briefs_v2`
linked both ways); an arm page (its metrics table, runs, config, conditions, rounds); the goals
page and each goal's page (its answer, its arms grouped by what they are scored against, the
closed rounds with their conclusions and retired arms; r2's suggestions were captured in step 9,
while r2 was open); each reference page; the metrics page and a metric page (what it measures, its
kind, the goals it decides, per-dataset strip chart); for each dataset, the inspector testing every
arm on gold against the baseline, on silver against the frontier arm, and on the judge's score; one
item opened in each (the item itself beside the reference and every output); the inspector over r2's
arms; and what a goal page's "test every arm against the leader" link opens. For each page, run its
command (`evh overview`, `evh datasets`, `evh arms`, `evh references`, `evh metrics`, `evh goals
--goal …`, `evh rounds --goal …`, `evh inspect --runs …`, `--item …`) and check the numbers are
the page's.

## What to check

- Every command either succeeds or refuses with a message that says what to do; no traceback
  from the harness.
- The inspector's verdicts and p-values equal `pair-test`'s for the same pair, and `evh rounds`'
  equal the inspector's for the round's arms. `family-test`'s verdicts are the same; its p-values
  are the same up to 30 items and may differ in the third decimal above that (it says "p: a
  seeded estimate").
- No console errors on any page.
- A newcomer could tell from each page what the goal is, what was compared, against which
  reference, which run is the baseline and why, and what each round decided.
- The spend stays under the cap and matches the sum of what each command printed.

## Open after the 2026-10-24 runs

Fixed on the 0.4.0 branch: `reference-create --from-run`; references refuse empty and cut-off
outputs; the leaderboard marks the reference's author; reference-create's gold and commit notes;
one install calls hosted models (`openai` and `anthropic` are core, `[llm]` is gone); providers
are documented as a choice, with the variable each reads (tutorial 2); the core times every call;
a run that stops mid-pass names itself and its `--resume` command; `experiment-run` warns when
outputs stop at `max_tokens`, and the OpenAI-compatible provider records `finish_reason`; V5 no
longer fails two different perfect arms; the goal page groups arms by what they are scored
against and never makes the reference's author the leader; the catalog shows the promoted
baseline and labels judged arms "judge"; the inspector's item view shows the item; `evh init`'s
`.gitignore` has `__pycache__/`; the README and the RUNBOOK lead with `evh` for a pinned user.
Since then: `dataset-create --help` (`--recursive`) and the bundled adapter's retry comment carry
no development history;
`evh env-check` and the `litellm` provider no longer mention `.env.example`; `provider:
openrouter` reads `OPENROUTER_API_KEY` and calls OpenRouter's address by default; with no
reference, `experiment-run` names `reference-create --from-run` first, and `evh --help` describes
`reference-create` as making references from a run or with a config; `leaderboard` prints one
table per reference and never averages across them; the bundled adapter stores `overlap_f1`
unrounded, so the rounding note no longer fires for it; `run-promote` prints no `resumed`;
`evh inspect --round` reads the goal's measure against the round's leader and names the arms it
leaves out; judged runs are grouped by their judge, and the leaderboard's NOTE names each way
the runs were scored rather than calling "no reference" a reference; `evh rounds` reads a round
against the reference most of its arms use and names the arms it does not compare; the
`pair-test --metric` and `evh --help` texts describe `--round` and the inspect views.

After the second run (0.4.0 candidate `e91ff94c`), fixed in code: `run-promote` of one of an
arm's repeats records every repeat and their mean (`repeats`); `round-open --keep` says carried
arms need no change and no new run; `evh rounds` no longer suggests promoting the run that is
already the baseline; `leaderboard --round` no longer warns about two versions of an arm in a
round that compares them; a judge reply that is not committed keeps its text, git-ignored, in
`.withheld/` beside its record, and the log names the file; the judged leaderboard has a frontier
and prints the judging pass's agreement and position and noise checks; the silver author is left
out of the ordering test and the frontier; the dataset page and `evh datasets` sort arms by what
they are scored against; the goal page and `evh goals --goal` show a judge's group, and `evh goals
--goal` lists the rounds and marks retired arms; every command prints p the same way (four
decimals, `<0.0001`), and `family-test` says whether its p is exact or a seeded estimate and
labels its column `A wins`; `experiment-run` prints what it spent and calls the cost and speed
spread what it is; `judge-score` says its spend is the provider's bill where one is reported,
else the price table; `silver-calibrate` explains rho and sibling lift; the catalog counts the
configs behind its arms; "filed" reads "filed under this goal"; the item view says it shows the
latest of N repeats beside their mean, and `evh inspect --item` prints the run and the same note;
`evh cost-report` sees the bundled adapter's bills (`_meta.usage.cost`); `evh datasets` counts the
configs behind the arms; judged arms keep their version in the inspector; a heading
scrolled to is not hidden under the header; `env-check` names example arms only in a checkout; the
kit's judge scorer points at tutorial 3. Fixed in the docs: every goal field and its allowed
values (RUNBOOK §4c); what each provider records as cost (RUNBOOK §4, tutorial 2); which repeat
to promote; family-test's p against pair-test's above 30 items; tutorial 1's adapter silences the
model library's bars and warnings; this page's config ids (`_v1` throughout), step 10's data and
step 11's screenshots.

Still open:

- The second run's own runs predate `f0c2ed3c`, so `evh cost-report` reads them as price table
  only, although the proxy billed them (`briefs_mistral_small_v1`'s per-item costs are not the
  config's prices × tokens). Runs made from `f0c2ed3c` on keep the bill in `_meta.usage.cost`;
  not yet exercised by a paid run.
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
