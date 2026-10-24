# The newcomer scenario

A person who has never used the harness pins a release candidate into an empty folder and,
using only the published docs, runs two small experiments end to end: a summariser and a
classifier, each with a small CPU model, cheap hosted LLMs, an expensive frontier model and an
LLM judge. Then they browse the results in the catalog and the inspector. It costs under $1 and
takes about two hours. Run it before every release (RELEASING step 4), and keep the friction log.

`make guide-check` already proves the GUIDE's offline tutorial runs as written. This covers what
it cannot: real models, a project's own adapters, two tasks in one project, a frontier reference,
judging, and what a newcomer has to guess.

First run: 2026-10-24, on the 0.4.0 branch. It found 38 items; the ones still open are listed at
the end.

## Rules for the run

- **Only the published docs.** README → harness README → INTEGRATION → GUIDE → RUNBOOK, as a
  newcomer would reach them. Do not read the code to find out how something works. When you have
  to, that is a finding.
- **A friction log as you go**, one line per item: **B** blocks a newcomer, **F** needs a guess,
  **N** is noise or polish. Note also what worked (OK). Say which doc or command, quote the output.
- **Your own key.** Any provider the bundled adapter supports: an OpenAI-compatible endpoint
  (OpenRouter is one), Anthropic, or a LiteLLM proxy. Put it in the project's `.env`
  (`evh env-check` lists the variables) with `EVAL_MAX_COST_USD=1`. Add up what each command
  prints it spent.
- **Screenshots of every catalog and inspector page** listed under step 9, at 1400 px wide.

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

One per experiment in `data/goals/` (copy the shape from the tutorial's goal): who uses the
output, the decision ("which system runs it, given that a frontier model is too expensive to run
on every item"), the measure that decides (`rouge_l`; `accuracy`), the dataset, the references.
Every config names its goal (`goal: …`).

## 3 · Adapters and arms

- `adapter.py` at the project root for the summaries: a **lead** provider (the first sentence;
  no model), an **hf** provider (a seq2seq model through `AutoModelForSeq2SeqLM.generate`), and the
  bundled hosted providers (`from evaluation_harness.adapter import PROVIDERS, Result`);
  `score()` returns `rouge_1`, `rouge_l` and `output_words`; `PRIMARY_METRIC = "rouge_l"`.
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

Give the frontier arm room to finish: `max_tokens: 300`.

## 4 · Measure

```bash
git add -A && git commit -qm "datasets, gold, goals, adapters, arms"
evh experiment-run --config data/configs/briefs_mistral_small.yaml --dry-run    # price it first
evh experiment-run --config data/configs/<arm>.yaml                              # every arm
evh experiment-run --config data/configs/<hosted arm>.yaml --repeat 3            # the noise floor
evh leaderboard --dataset-id briefs_v1
evh family-test --dataset-id briefs_v1 --a briefs_mistral_small_v1 --against briefs_ --metric rouge_l
```

The same for `intents_v1` (`--metric accuracy`).

## 5 · The frontier arm's run becomes the silver reference

```bash
evh reference-create --dataset-id briefs_v1 --from-run <the briefs_opus run_id>
git add data/references && git commit -qm "silver/briefs_v1 from the frontier arm"
evh reference-create --dataset-id intents_v1 --from-run <the intents_opus run_id>
git add data/references && git commit -qm "silver/intents_v1 from the frontier arm"
evh rescore --dataset-id briefs_v1 --reference-id silver/briefs_v1 --out data/runs-silver
evh rescore --dataset-id intents_v1 --reference-id silver/intents_v1 --out data/runs-silver
EVAL_RUNS_DIR=data/runs-silver evh leaderboard --dataset-id briefs_v1    # the author's row is marked
evh silver-calibrate --dataset-id briefs_v1                              # silver authors vs your gold
```

Commit each reference before the next run: an uncommitted reference makes every later run dirty,
and `--from-run` refuses a dirty run.

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

## 7 · Baselines

Promote, per dataset, the cheap arm closest to the frontier on gold, with a reason that says
what the family test showed:

```bash
evh run-promote --run <run_id> --reason "<what the tests showed, and what it costs against the frontier arm>"
```

## 8 · Validate

```bash
evh validate
```

## 9 · Browse it

```bash
evh catalog && evh catalog-serve
```

Screenshot: the catalog index; the goals page and each goal's page; each dataset page; for each
dataset, the inspector testing every arm on gold against the baseline, on silver against the
frontier arm, and on the judge's score; one item opened in each; and what a goal page's "test
every arm against the leader" link opens.

## What to check

- Every command either succeeds or refuses with a message that says what to do; no traceback
  from the harness.
- The inspector's verdicts and p-values equal `family-test`'s for the same arms and baseline.
- No console errors on any page.
- A newcomer could tell from each page what the goal is, what was compared, against which
  reference, and which run is the baseline.
- The spend stays under the cap and matches the sum of what each command printed.

## Open after the 2026-10-24 run

Fixed on the 0.4.0 branch: `reference-create --from-run`; references refuse empty and cut-off
outputs; the leaderboard marks the reference's author; reference-create's gold and commit notes.
Still open:

- The hosted providers' clients are an extra (`[llm]`) that only RUNBOOK §12 mentions: one pinned
  install should enable everything.
- The docs should present providers as a choice (any OpenAI-compatible endpoint, Anthropic, a
  LiteLLM proxy; OpenRouter as one example) and say plainly that you bring your own key.
- The core does not time `call_system`; an adapter written as INTEGRATION shows records no
  latency, and the leaderboard drops the cost/speed frontier without saying why.
- An adapter exception leaves a run directory with no `metrics.json`, prints only a traceback (no
  run id, no `--resume`), and the next `validate` fails V7.
- `experiment-run` does not warn when outputs hit `max_tokens`; the bundled OpenAI-compatible
  provider records no `finish_reason`.
- `validate` V5 fails two different arms that are both perfect on a binary metric.
- The goal page ranks gold- and silver-scored runs together and makes the reference's author,
  graded on its own outputs, the leader.
- The catalog shows no promoted baseline; it labels judged arms "scored against gold"; the
  inspector's item view does not show the item itself.
- `evh init`'s `.gitignore` lacks `__pycache__/`; `resumed` and the judge's `self_family_*`
  flags are listed as metrics; the bundled adapter and some `--help` texts carry development
  history; the README mixes `make` and `evh` for a pinned user.
