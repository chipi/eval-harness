# Getting started

Your first evaluation, in about fifteen minutes, offline and with no API key: create a
dataset, run a few systems on it, make a reference from the best one's run, compare them
honestly, and choose one. Every command below was run as written, and the output shown is
what it printed (`make guide-check` runs this page in a fresh project on every change).

You work in a project of your own, as you will for real: a new folder, the harness installed
as a package, and the tutorial kit copied in. The running example is a support-ticket
summariser. The kit ([`harness/tutorial/`](../harness/tutorial/README.md) in this repository)
has six invented tickets, four arm configs and a goal. The "systems" are the harness's offline
`echo` provider, which returns the first *n* sentences of its input: a stand-in that behaves
like a model without needing one. A real model, local or hosted, is the
[tutorials](#where-to-go-next)' subject.

## The loop in one picture

```text
 sources/ ──dataset-create──▶ datasets/<id>.json ──dataset-materialize──▶ materialized/<id>/
 (your items)                 (item list + sha256)                         (hash-checked copy)

 configs/<arm>.yaml ──experiment-run──▶ runs/<run_id>/   outputs, per-item scores, cost, speed,
 (one system = one arm)                                   fingerprint: data + code + model + build
                                              │
                    reference-create --from-run ──▶ references/silver/<id>/   (optional)
                                              │
                         leaderboard · pair-test · family-test
                                              │
                              run-promote ──▶ baselines/<id>_baseline.json  (a decision + why)
```

| term | what it is | lives in | edited? |
|---|---|---|---|
| **source** | one input item, any file | `data/sources/` or anywhere | never, once frozen |
| **dataset** | a frozen list of items with the sha256 of each: the comparison contract | `data/datasets/<id>.json` | never; a change is `_v2` |
| **materialized** | a hash-checked working copy of the dataset | `data/materialized/<id>/` | derived; delete freely |
| **arm** | one system under test: a config naming provider, model, prompt, settings | `data/configs/*.yaml` | a change is a new `config_id` |
| **run** | one pass of an arm over a dataset: outputs, scores, fingerprint | `data/runs/<run_id>/` | never |
| **reference** | what each item is scored against: **gold** (a person wrote it) or **silver** (a model did) | `data/references/<tier>/<id>/` | never; a change is a new set |
| **goal** | what the evaluation is for: who uses the output, the decision, the measure | `data/goals/<goal_id>.yaml` | yes |
| **baseline** | the run you chose to measure future changes against, with why | `data/baselines/` | replaced by the next choice, never edited |

## 0 · Set up

A new folder, a virtual environment, and the harness pinned to a release. One install is
everything: the hosted-model clients, the judges, the catalog. Nothing else to add.

<!-- guide-check: skip -->
```bash
mkdir my-evals && cd my-evals
python3 -m venv .venv && . .venv/bin/activate
pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.4.0#subdirectory=harness"
```

Then the project's folders and the tutorial kit, under version control from the start:

```bash
evh init --tutorial
git init -q && git add -A && git commit -qm "Start: the tutorial kit"
```
```text
  folders  data/sources, data/configs, data/goals, data/fields
  wrote    24 file(s), the tutorial kit under tutorial/
```

`data/` is where everything the harness freezes and records will live; `tutorial/` is the
kit; `.gitignore` already keeps out what the harness derives (materialized copies, the
catalog build, caches, your `.env`). Every command from here runs from this folder.

## 1 · Create a dataset

```bash
evh dataset-create --dataset-id tickets_v1 --source-dir tutorial/tickets
```
```text
data/datasets/tickets_v1.json  (6 item(s))
```

`data/datasets/tickets_v1.json` lists every item with the sha256 of its bytes. From now on
`tickets_v1` *means* those six byte strings: every run records the dataset's hash, and
`run-compare` refuses to compare runs across two different datasets. Name a dataset for what
it is (`support_tickets_2026q1_v1`), not for what you are doing (`test2`). If an input
changes, make `tickets_v2`: editing a frozen item silently invalidates every number measured
on it ([tutorial 4](tutorials/4-rounds-and-versions.md) makes a version).

**Keep your sources under version control** (or gitignore them, if you cannot redistribute
them: the dataset's hashes are the record either way). An untracked input makes the tree
"dirty", and a run from a dirty tree cannot become a reference or a baseline.

## 2 · Materialize

```bash
evh dataset-materialize --dataset-id tickets_v1
```
```text
data/materialized/tickets_v1  (6 item(s), all hashes verified)
```

A working copy, re-checked against the frozen hashes. If a source changed since the freeze,
this fails instead of quietly measuring different bytes.

## 3 · Describe your arms

An arm is a YAML file. Everything that defines the system goes in `params`, so two arms differ
only where their configs do, and the run's fingerprint will say exactly where.

```yaml
# data/configs/tickets_lead2.yaml
config_id: tickets_lead2_v1     # unique, versioned: change the system, bump the id
dataset_id: tickets_v1          # the contract it is measured on
params:
  provider: echo                # your adapter decides what these mean
  sentences: 2
```

```bash
cp tutorial/configs/tickets_*.yaml data/configs/
```

The four arms: `lead1` (one sentence), `lead2` (two), `lead2_noisy` (two, with random word
drops: what a model at temperature > 0 looks like), and `author` (three), the most thorough
system we have, which will write the reference.

**Say what the evaluation is for.** A goal names who uses the output, the decision it informs,
the measure that decides it and which direction is better, and the datasets it rests on. It is
optional, and worth the minute: every run that names it records it, and the catalog's goal page
leads with the decision.

```bash
cp tutorial/goals/tickets_summary.yaml data/goals/
for f in data/configs/tickets_*.yaml; do echo "goal: tickets_summary" >> "$f"; done
```

## 4 · Run the best arm first

Commit **before** measuring. A run records the commit it ran on; from a dirty tree that commit
does not describe what ran, and the run cannot become a reference or a baseline. (Run
directories themselves never count as dirt.)

```bash
git add -A && git commit -qm "tickets_v1: dataset, arms, goal"
```

A dry run calls nothing and shows what a pass will cost:

```bash
evh experiment-run --config data/configs/tickets_author.yaml --dry-run
```
```text
  config      tickets_author_v1  (echo)
  dataset     tickets_v1  (6 items)
  API calls   6
  No price in the config, so no estimate. Add usd_per_mtok_in /
  usd_per_mtok_out and the run will record what it actually cost.
  cap         NONE — set EVAL_MAX_COST_USD
```

You cannot score quality without something to score against, and most projects start with
nothing. The usual first move is to run the best system you have, often an expensive model you
would not run in production, and let its outputs be the answers the others are measured
against:

```bash
evh experiment-run --config data/configs/tickets_author.yaml
```
```text
  no references for tickets_v1 — quality cannot be scored.
  ...
wrote 1 run(s) to .../my-evals/data/runs
```

With no reference it records only what needs none (the output's length, its cost, how long
each call took).

## 5 · Make its run the reference (optional)

```bash
evh reference-create --dataset-id tickets_v1 --from-run <the tickets_author_v1 run_id>
git add data/references && git commit -qm "silver/tickets_v1 from the author arm's run"
```
```text
silver reference(s) for 6 item(s) from run tickets_author_v1_...: no calls
data/references/silver/tickets_v1  (6 item(s), tier=silver, $0.0000)
Runs against this dataset will now be scored against it automatically.
```

`evh runs-list` prints the run ids. `--from-run` copies the run's outputs and calls nothing,
and the reference records the run, its config and its fingerprint. These are **silver**
references: consistent, cheap, and *not correct*. They encode the author's opinion, mistakes
included: good enough to rank the other arms by how close they come to it, and every run
scored against them says so. The step is optional: if you already have answers a person wrote
(**gold**), put them in `data/references/gold/tickets_v1/` instead and skip it
([tutorial 3](tutorials/3-frontier-reference-and-judging.md) adds gold to this project and shows
what silver got wrong).

## 6 · Run the other arms, three times each

```bash
for a in lead1 lead2 lead2_noisy; do
  evh experiment-run --config data/configs/tickets_$a.yaml --repeat 3
done
```
<!-- guide-check: varies treat -->
```text
  scoring against SILVER references for tickets_v1
  ...
  Arm spread over 3 repeats (max - min on identical input):
    ...
    overlap_f1     spread=0.000000   deterministic
  ...
  Arm spread over 3 repeats (max - min on identical input):
    ...
    overlap_f1     spread=0.029372   treat deltas below 0.029372 as noise
```

Each arm prints its runs, then its spread for every metric; above are `lead2`'s `overlap_f1`
and then `lead2_noisy`'s. **This is the step people skip.** The spread is how far the arm
disagrees with *itself* on identical input. Any difference between two arms smaller than that
is noise, whatever the table says. A deterministic arm (spread 0) makes every delta real; a
real model at temperature 0 often is not deterministic. Your `lead2_noisy` numbers will differ
from these: it is unseeded on purpose. (`latency_ms` has a spread too: the harness times every
call.)

## 7 · Compare

**All arms at once:**

```bash
evh leaderboard --dataset-id tickets_v1
```
<!-- guide-check: varies lead2_noisy global distinguishable -->
```text
  arm                      runs        overlap_f1      output_words
  tickets_lead2_v1            3          0.900088         28.500000
  tickets_lead2_noisy_v1      3          0.798988         22.611111
  tickets_lead1_v1            3          0.640917         16.000000
  tickets_author_v1           1                 —         35.166667
  ...
  IS THE ORDERING REAL?   metric=overlap_f1  k=3 arms  N=6 items
    global test (permutation on within-item ranks): p = 0.0002  ->  an arm effect exists
    ...
    pairs distinguishable: 1 of 3
  ...
  Scored against SILVER references (model-generated). Good for ranking
  these arms against each other; not a claim that any of them is correct.
```

The leaderboard *sorts*; the block underneath says how much of the order is real. Read that
block, not the row numbers. `author` has no score: it is the reference. The table also carries
each arm's cost and speed (all zero here: `echo` is free and instant).

**One pair you named in advance**, tested item by item:

```bash
evh pair-test --dataset-id tickets_v1 --a tickets_lead2_v1 --b tickets_lead1_v1
```
```text
    items A wins       6/6
    sign-flip p        0.0312  (exact, all 2^6 sign patterns)
    verdict            SEPARATED at 0.05
    (uncorrected: valid only if this pair was named before the table was read)
```

**A winner claim.** "lead2 is the best" means *separated from every other arm*, with the
correction for testing several at once. If you picked the pair *after* looking at the
leaderboard, the `pair-test` p-value above is wrong; `family-test` corrects for every
comparison you could have made:

```bash
evh family-test --dataset-id tickets_v1 --a tickets_lead2_v1 --against tickets_
```
<!-- guide-check: varies lead2_noisy ahead -->
```text
  family size m=2, declared before the p-values were read
  Holm step-down at alpha=0.05
    opponent                     delta      wins        p   thresh   verdict
    tickets_lead1_v1           +0.2592    6/6      0.0312   0.0250   --
    tickets_lead2_noisy_v1     +0.1011    6/6      0.0312   0.0500   --

    separated from 0 of 2 opponents; ahead on the point estimate against 2 of 2
```

Ahead of both on every ticket, and separated from neither: on six items the smallest p a
paired test can reach is 0.0312, and with two comparisons the first must beat 0.025. Six items
are enough to learn the loop, not to pick a winner. `run-compare` diffs two runs' fingerprints
and scores (`evh run-compare --baseline <run_id> --candidate <run_id> --noise <spread>`).

## 8 · Choose

A baseline is the run future changes are measured against: a **decision**, recorded with its
reason. The reason has to say what the tests showed, not what you hoped:

```bash
evh run-promote --run <the tickets_lead2_v1 run_id> \
  --reason "lead2 is closest to the author's silver on all six tickets but separates from neither arm at n=6; working baseline until the dataset grows"
evh runs-list --baselines
```
```text
tickets_v1_baseline
    dataset  tickets_v1
    ...
    scored   silver references, adapter scripts/adapter.py
    why      lead2 is closest to the author's silver on all six tickets but separates from neither arm at n=6; working baseline until the dataset grows
```

Refused if the run came from a dirty tree, if its build is unknown, or if the reason is under
three words: six months from now, "why is this the baseline?" must have an answer. The next
promotion replaces this baseline, and git keeps it.

Last, check that everything recorded still holds together. Run it in CI; it exits non-zero:

```bash
git add data/baselines && git commit -qm "tickets_v1: baseline"
evh validate
```
```text
  ok   V2 every run's dataset_id resolves (1 dataset(s) known)
  ok   V3 every run identifies its build
  ok   V4 materialized copies match their frozen hashes (1 of 1 datasets materialized here)
  ok   V6 every baseline's source run still exists and matches what the baseline carries
  ...
VALIDATION PASSED
```

That is the loop: a dataset, arms, a reference, a comparison that says what it can and cannot
tell, and a recorded choice.

## Where to go next

Each tutorial starts from where this page ends, or from a project of your own:

| | |
|---|---|
| [**1 · A local model against a baseline**](tutorials/1-local-model.md) | your own items, your own `adapter.py`, a small model on CPU against a no-model baseline |
| [**2 · A hosted LLM, with your own key**](tutorials/2-hosted-llm.md) | the providers you can choose (OpenAI-compatible endpoints such as OpenRouter, Anthropic, a LiteLLM proxy), the variable each one reads, prices and a spend cap |
| [**3 · A frontier model's run as the reference, gold, and judging**](tutorials/3-frontier-reference-and-judging.md) | how good the silver was, measured against answers a person wrote, and re-measuring the stored outputs with LLM judges |
| [**4 · Experiment rounds and dataset versions**](tutorials/4-rounds-and-versions.md) | round on round: keep what wins, drop what lost, record why; a new version of a dataset that remembers where it came from |
| [**5 · The catalog and the inspector**](tutorials/5-catalog-and-inspector.md) | pages over your runs, an inspector that tests arms item by item, and the `evh` command behind every view |

And the references, for when you know what you are looking for:
[INTEGRATION](../harness/docs/INTEGRATION.md) (your system in the harness: the adapter, what
it returns, a catalog of your own layout), [RUNBOOK](../harness/docs/RUNBOOK.md) (every
command, flag, environment variable and exit code), [CONCEPTS](../harness/docs/CONCEPTS.md)
(why each refusal exists).
