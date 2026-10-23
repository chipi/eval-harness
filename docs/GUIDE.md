# Use the harness

Your first evaluation, end to end, in about twenty minutes — offline, no API key. You will
freeze a dataset, author references, build a small **golden dataset**, measure four
systems, compare them honestly, promote a baseline and, if you want, re-measure the same
outputs with an LLM judge. Every command below was run as written; the output shown is what
it printed.

You work in a project of your own, as you will for real: a new folder, the harness installed
as a package, and the tutorial kit copied in. The running example is a support-ticket
summariser. The kit ([`harness/tutorial/`](../harness/tutorial/README.md) in this repository)
has six invented tickets, a one-line summary of each written by a person, four arm configs,
a goal and a judge scorer. The "systems" are the harness's offline `echo` provider, which
returns the first *n* sentences of its input — a stand-in that behaves like a model without
needing one. Swapping in your own system is one function, covered
[at the end](#doing-it-for-real).

## The lifecycle in one picture

```text
 your inputs          frozen               derived              ground truth
 ───────────          ──────               ───────              ────────────
 sources/  ──create──▶ datasets/<id>.json ──materialize──▶ materialized/<id>/
 (any files)          (item list + sha256)  (hash-checked copy)

                                         references/silver/<id>/   model-written
                                         references/gold/<id>/     person-written
                                                     │
 configs/<arm>.yaml ──experiment-run──▶ runs/<run_id>/  (outputs, per-item scores,
 (one system = one arm)                  fingerprint: data + code + model + build)
                                                     │
                      leaderboard · run-compare · pair-test · family-test
                                                     │
                                       run-promote ──▶ baselines/<id>_baseline.json
                                                     (a decision, with its reason)

 optional, any time later: re-measure the same frozen outputs, without re-running an arm
   rescore      new reference or new code scorer, $0  ──▶ runs-rescored/ (or OUT=…)
   judge-score  a validated LLM judge, billed + capped ──▶ runs-judged/<scorer>/
                the originals are never touched; point the leaderboard at the new directory
```

| term | what it is | lives in | edited? |
|---|---|---|---|
| **source** | one input item, any file | `data/sources/` or anywhere | never, once frozen |
| **dataset** | a frozen list of items with the sha256 of each — the comparison contract | `data/datasets/<id>.json` | never; a change is `_v2` |
| **materialized** | a hash-checked working copy of the dataset | `data/materialized/<id>/` | derived; delete freely |
| **arm** | one system under test: a config naming provider, model, prompt, settings | `data/configs/*.yaml` | a change is a new `config_id` |
| **run** | one pass of an arm over a dataset: outputs, scores, fingerprint | `data/runs/<run_id>/` | never |
| **reference** | the answer each item is scored against — **gold** (a person) or **silver** (a model) | `data/references/<tier>/<id>/` | never; a change is a new set |
| **baseline** | the run you decided to measure future changes against, with why | `data/baselines/` | replaced by the next promotion, never edited |
| **judge scorer** | optional: LLM judges, their prompt, the task they score, and the runs that validated them | `data/scorers/<id>.yaml` | a change is a new `scorer_id` |

## 0 · Set up

A new folder, a virtual environment, and the harness pinned to a release:

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

## 1 · Freeze a dataset

The tickets, and what you know about each one: the part of the product it is about, the
customer's plan, whether it names a deadline. Those facts are **fields**, and you declare
them yourself, in a field set; the harness defines none.

```bash
cp tutorial/fields/tickets.yaml data/fields/
evh dataset-create --dataset-id tickets_v1 --source-dir tutorial/tickets \
    --fieldset tickets --fields tutorial/ticket_fields.csv
```
```text
data/datasets/tickets_v1.json  (6 item(s))
```

`data/datasets/tickets_v1.json` lists every item with the sha256 of its bytes. From now
on `tickets_v1` *means* those six byte strings: every run records the dataset's hash, and
`run-compare` refuses to compare runs across two different datasets. Name a dataset for
what it is (`support_tickets_2026q1_v1`), not for what you are doing (`test2`). If an
input changes, make `tickets_v2` — editing a frozen item silently invalidates every number
measured on it.

**Fields describe an item; they are not what it is.** `data/fields/tickets.yaml` gives each
field a type (`choice` with its values, `boolean`, `number`, `integer`, `duration`, `date`,
`url` or `text`) and says whether it is `required` and `public`. `--fields` reads one row per
item from a CSV or JSONL, and refuses a column the field set does not declare or a value of
the wrong type. The run fingerprint hashes the items' bytes, not their fields, so correcting
a field later (`evh dataset-create --dataset-id tickets_v1 --update-fields --fields fix.csv`)
invalidates no run. Items that live at a URL instead of on disk come in through `--manifest`:
one row per item with its `source_url` and `source_sha256`, and `dataset-materialize` refuses
bytes that hash to anything else.

**Keep your sources under version control** (or gitignore them, if you cannot redistribute
them — the dataset's hashes are the record either way). An untracked input makes the tree
"dirty", and a run from a dirty tree cannot be promoted (step 9).

## 2 · Materialize

```bash
evh dataset-materialize --dataset-id tickets_v1
```
```text
data/materialized/tickets_v1  (6 item(s), all hashes verified)
```

A working copy, re-checked against the frozen hashes. If a source changed since the
freeze, this fails instead of quietly measuring different bytes.

## 3 · Describe your arms

An arm is a YAML file. Everything that defines the system goes in `params`, so two arms
differ only where their configs do — and the run's fingerprint will say exactly where.

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
drops — what a model at temperature > 0 looks like), and `author` (three) — the one we
will trust to write references.

**Say what the evaluation is for.** A goal names who uses the output, the decision it
informs, the measure that decides it and which direction is better, and the datasets it
rests on. The tutorial has one:

```bash
mkdir -p data/goals && cp tutorial/goals/tickets_summary.yaml data/goals/
for f in data/configs/tickets_*.yaml; do echo "goal: tickets_summary" >> "$f"; done
```

Each config now names it, and every run records it:

```yaml
# data/configs/tickets_lead2.yaml
config_id: tickets_lead2_v1
dataset_id: tickets_v1
params:
  provider: echo
  sentences: 2
goal: tickets_summary
```

A config naming a goal that does not exist is refused before it runs. Goals are optional:
nothing requires one until a project sets a date from which every new run must name one
(`required_from` in `data/goals/policy.yaml`).

## 4 · Author silver references

You cannot score quality without something to score against, and most projects start with
nothing. The usual first move is to let the best system you have write the answers:

```bash
evh reference-create --dataset-id tickets_v1 --config data/configs/tickets_author.yaml
```
```text
authoring 6 silver reference(s) with tickets_author_v1
  ...
data/references/silver/tickets_v1  (6 item(s), tier=silver, $0.0000)
Runs against this dataset will now be scored against it automatically.
```

These are **silver**: consistent, cheap, and *not correct* — they encode the author's
opinion, mistakes included. Good enough to start ranking; every run scored against them
says so. Step 7 shows exactly what they get wrong.

## 5 · Commit, then measure

```bash
git add data/datasets/tickets_v1.json data/fields/tickets.yaml data/configs/tickets_*.yaml data/goals/tickets_summary.yaml data/references/silver/tickets_v1
git commit -m "tickets_v1: dataset, arms, goal, silver references"
```

Commit **before** measuring. A run records the commit it ran on; from a dirty tree that
commit does not describe what ran, and the run cannot become a baseline. (Run directories
themselves never count as dirt.)

First a dry run — it calls nothing and shows what a sweep will cost:

```bash
evh experiment-run --config data/configs/tickets_lead2.yaml --dry-run
```
```text
  config      tickets_lead2_v1  (echo)
  dataset     tickets_v1  (6 items)
  API calls   6
  No price in the config, so no estimate. Add usd_per_mtok_in /
  usd_per_mtok_out and the run will record what it actually cost.
  cap         NONE — set EVAL_MAX_COST_USD
```

Then each arm, **three times**:

```bash
for a in lead1 lead2 lead2_noisy author; do
  evh experiment-run --config data/configs/tickets_$a.yaml --repeat 3
done
```
<!-- guide-check: varies treat -->
```text
  ...
  Arm spread over 3 repeats (max - min on identical input):
    ...
    overlap_f1     spread=0.000000   deterministic
  ...
  Arm spread over 3 repeats (max - min on identical input):
    ...
    overlap_f1     spread=0.029372   treat deltas below 0.029372 as noise
```

Each arm prints its runs, then its spread for every metric; above are `lead2`'s
`overlap_f1` and then `lead2_noisy`'s. **This is the step people skip.** The spread is how far the arm disagrees with *itself* on
identical input. Any difference between two arms smaller than that is noise, whatever the
table says. A deterministic arm (spread 0) makes every delta real; a real model at
temperature 0 often is not deterministic. Your `lead2_noisy` numbers will differ from
these — it is unseeded on purpose.

## 6 · Compare

**All arms at once:**

```bash
evh leaderboard --dataset-id tickets_v1
```
<!-- guide-check: varies lead2_noisy distinguishable -->
```text
  arm                      runs        overlap_f1      output_words
  tickets_author_v1           3          1.000000         35.166667
  tickets_lead2_v1            3          0.900088         28.500000
  tickets_lead2_noisy_v1      3          0.801971         22.611111
  tickets_lead1_v1            3          0.640917         16.000000

  IS THE ORDERING REAL?   metric=overlap_f1  k=4 arms  N=6 items
    global test (permutation on within-item ranks): p = 0.0002  ->  an arm effect exists
    pairs distinguishable: 3 of 6
```

The leaderboard *sorts*; the block underneath says how much of the order is real. Read
that block, not the row numbers.

**Two runs, side by side, against the noise floor you measured:**

```bash
evh run-compare --baseline <a tickets_lead1_v1 run_id> --candidate <a tickets_lead2_v1 run_id> --noise 0.044
```
```text
  Fingerprints DIFFER. Fields that moved:
      arm.config_id
      arm.params.sentences

  metric             baseline    candidate        delta   verdict
  output_words      16.000000    28.500000   +12.500000   changed
  overlap_f1         0.640917     0.900088    +0.259171   better
```

The fingerprint diff is the point: it proves the two runs differ in exactly one parameter,
so the delta belongs to it. `evh runs-list` prints the run ids.

**One pair you named in advance**, tested item by item:

```bash
evh pair-test --dataset-id tickets_v1 --a tickets_lead2_v1 --b tickets_lead1_v1 --metric overlap_f1
```
```text
    items A wins       6/6
    sign-flip p        0.0312  (exact, all 2^6 sign patterns)
    verdict            SEPARATED at 0.05
    (uncorrected: valid only if this pair was named before the table was read)
```

If you picked the pair *after* looking at the leaderboard, that p-value is wrong — use
`family-test` (step 8), which corrects for every comparison you could have made.

## 7 · Make it golden

So far `author` wins with a perfect 1.000 — because it is being graded against its own
answers. That is what silver does to whoever wrote it, and why a **golden dataset** — a
reference a person wrote or checked — is the thing to build next.

A gold set is plain files: one `<item_id>.txt` per item, under
`data/references/gold/<dataset_id>/`. Write them yourself, or review silver ones and keep
those you would sign. The kit has six, written by hand:

```bash
mkdir -p data/references/gold/tickets_v1
cp tutorial/gold/*.txt data/references/gold/tickets_v1/
git add data/references/gold/tickets_v1 && git commit -m "tickets_v1: gold references"
```

From now on every new run on `tickets_v1` is scored against gold automatically (gold
always wins over silver, and the run records which it used). The runs you already have
need not be paid for again: their outputs are stored, so re-scoring is arithmetic.

```bash
evh rescore --dataset-id tickets_v1 --reference-id gold/tickets_v1 --out data/runs-gold
EVAL_RUNS_DIR=data/runs-gold evh leaderboard --dataset-id tickets_v1
```
<!-- guide-check: varies lead2_noisy global distinguishable sorted ordering -->
```text
  tickets_lead2_v1            3          0.243426
  tickets_lead2_noisy_v1      3          0.237659
  tickets_author_v1           3          0.231219
  tickets_lead1_v1            3          0.201010
  ...
    global test (permutation on within-item ranks): p = 0.1808  ->  NO detectable arm effect
    pairs distinguishable: 0 of 6
    The table above is sorted, but these runs do not show the arms differ.
    Do not report an ordering from it.
```

Two lessons in one table. `author` lost first place to `lead2` the moment it stopped
grading itself. And against what a person actually wrote, six items can almost never tell
these arms apart: in a simulation of this step, 290 runs in 300 found no arm effect, and the
other 10 were `lead2_noisy`'s luck of the draw. The pairs "distinguishable" on silver were the
author's opinion, measured precisely. Rescored runs go to a separate directory, never over the originals, and each
records both the reference it was measured against and the one it is scored against now.

**How good was the silver, then?** `silver-calibrate` tries every arm as a silver author
and asks how closely its ranking matches gold's:

```bash
EVAL_RUNS_DIR=data/runs-gold evh silver-calibrate --dataset-id tickets_v1
```
<!-- guide-check: varies author lead1 lead2 -->
```text
  trusted reference: gold/tickets_v1
  ...
  silver author          rho vs trusted  sibling lift
  tickets_author                  1.000             —   (0 sibling(s))
  tickets_lead1                   1.000             —   (0 sibling(s))
  tickets_lead2_noisy             1.000             —   (0 sibling(s))
  tickets_lead2                   0.500             —   (0 sibling(s))
```

Your rows will differ from these: with four arms, `lead2_noisy`'s place in each ranking
moves every rho.

On six items these correlations are coarse, but the habit is the point: before you rank
by silver, check it against a gold slice. How big a gold set must be is a measurement
too — `evh rank-stability` shows how many items it takes before the order stops moving.

**Golden datasets, the rules:**

- **Gold is frozen like a dataset.** Every score was measured against those bytes; the
  run fingerprint hashes them. Fix a gold answer → new set (`tickets_v2`), or a rescore
  that records the change.
- **Never mix tiers in one number.** A run is scored against gold *or* silver, and says
  which. If you publish a silver-scored number, say so.
- **Keep a dev slice apart.** Tune prompts on a small nested dataset (`tickets_dev_v1`)
  and report on the rest — `evh holdout` re-tests excluding it.
- **Disputed gold is a finding, not noise.** When most strong systems disagree with a
  gold answer, read it: in this repository's AG News and DBpedia experiments, one reader
  adjudicated those items by topic, shown the hosted answer, and found the gold wrong on all
  20 (AG News 17, DBpedia 3). The dataset's own gold stays primary; the adjudicated one sits
  beside it.

## 8 · Decide: is the winner separated?

A claim like "lead2 is the best" means *separated from every other arm*, with the
correction for testing several at once:

```bash
evh family-test --dataset-id tickets_v1 --a tickets_lead2_v1 --against tickets_ \
    --metric overlap_f1 --runs-dir data/runs-gold
```
<!-- guide-check: varies tickets_lead1_v1 tickets_author_v1 lead2_noisy ahead -->
```text
  family size m=3, declared before the p-values were read
  Holm step-down at alpha=0.05
    opponent                     delta      wins        p   thresh   verdict
    tickets_lead1_v1           +0.0424    5/6      0.0938   0.0167   --
    tickets_author_v1          +0.0122    4/6      0.3125   0.0250   --
    tickets_lead2_noisy_v1     +0.0058    2/6      0.9062   0.0500   --

    separated from 0 of 3 opponents; ahead on the point estimate against 3 of 3
```

Ahead of `lead1` and `author`, separated from no one; against `lead2_noisy` the delta is
smaller than that arm's own spread, and its sign can change from one run to the next. That
is the honest state of this experiment: a bigger gold set is the next step, not a conclusion.

## 9 · Promote a baseline

A baseline is the run future changes are measured against — a **decision**, recorded with
its reason. The reason has to say what the tests showed, not what you hoped:

```bash
evh run-promote --run <the tickets_lead2_v1 run_id> \
  --reason "lead2 leads on gold for tickets_v1 (n=6) but separates from no arm; working baseline until the gold set grows"
evh runs-list --baselines
```

Refused if the run came from a dirty tree, if its build is unknown, or if the reason is a
single word: six months from now, "why is this the baseline?" must have an answer. The
next promotion replaces this baseline, and git keeps it.

## 10 · Optional: re-measure with an LLM judge

Word overlap is a weak measure of a summary, and you will not always have gold to score
against. An LLM judge can read each ticket and rate every arm's summary instead. It does
not re-run any arm: it reads the outputs already stored, so it is a second measurement of
the same frozen record, written to its own directory. Nothing here is required. Skip this
step and every other one still works.

A judge is a **judge scorer**, one file. The kit has one whose two judges are `provider:
fake`, a deterministic stand-in that calls nothing, so this step stays offline and $0:

```yaml
# data/scorers/tickets-judge-v1.yaml (abridged)
scorer_id: tickets-judge-v1
kind: judge
dataset_id: tickets_v1
task:                          # what is judged; omit it for SummEval's news-summary task
  source_label: TICKET
  output_label: SUMMARIES
  dimensions: [accuracy, usefulness]
  scale: [1, 5]
judges:                        # at least two, from different vendor families
  - {id: judge_a, params: {provider: fake, model: fake-a, family: vendor_a, ...}}
  - {id: judge_b, params: {provider: fake, model: fake-b, family: vendor_b, ...}}
prompt:
  file: tutorial/judge_prompt.txt   # "{n}" in it becomes the number of summaries per call
protocol: {outputs_per_call: 16, blinding: true, order_seed: 0, ...}
cost_cap_usd: 0.01
```

```bash
mkdir -p data/scorers && cp tutorial/scorers/tickets-judge-v1.yaml data/scorers/
evh judge-score --dataset-id tickets_v1 --scorer tickets-judge-v1
```
```text
REFUSED: judge scorer tickets-judge-v1 is not validated:
  - judge 'judge_a' uses provider: fake, a stand-in that can never be validated
  - judge 'judge_b' uses provider: fake, a stand-in that can never be validated
  Fix the `validation` block, or pass --unvalidated to run it labelled 'unvalidated judge'.
```

**The harness refuses a judge nobody has checked.** A judge is a model's opinion, as silver
is, so before its scores count it must be validated: a `validation` block names the
committed runs that measured each judge against human ratings, on data like yours. Fake
judges can never pass. To try the pass anyway, say so, and every number is labelled.
Price it first; `--dry-run` calls nothing:

```bash
evh judge-score --dataset-id tickets_v1 --scorer tickets-judge-v1 --unvalidated --dry-run
```
<!-- guide-check: varies 4arms judge_a judge_b TOTAL -->
```text
WARNING: UNVALIDATED JUDGE. Every number is labelled; 2 problem(s):
  ...
judging set  tickets_v1-4arms-79d240d2469e
  arms 4, items 6, blocks per item [4], position items 3, noise items 3
DRY RUN (nothing called; tokens are chars/4 estimates, cost from the scorer's price table)
  judge judge_a  calls    12 (stored 0)  tokens in      4,976  out      456  est $0.0000
  judge judge_b  calls    12 (stored 0)  tokens in      4,976  out      456  est $0.0000
  TOTAL        calls    24  tokens in      9,952  out      912  est $0.0000   cap $0.01
```

The **judging set** is frozen first: each ticket with every arm's summary, the arms' names
hidden and their order shuffled per ticket. Its id hashes all of that, so a different arm
set is a different judging set, never an addition to this one. 24 calls: each judge reads
each ticket once, plus a second shuffle on half the tickets (the **position** check: does
order change the verdict?) and a repeat on half (the **noise** check: does the judge agree
with itself?). Then:

```bash
evh judge-score --dataset-id tickets_v1 --scorer tickets-judge-v1 --unvalidated
EVAL_RUNS_DIR=data/runs-judged/tickets-judge-v1 evh leaderboard --dataset-id tickets_v1
```
<!-- guide-check: varies lead2_noisy global distinguishable -->
```text
4 scored run(s) -> .../data/runs-judged/tickets-judge-v1  (6/6 items, unvalidated judge)
  calls 24, billed this run $0.0000, stored total $0.0000

dataset: tickets_v1   ranked by: judge_score_unvalidated (higher is better)

  arm                      runs  judge_judge_a_unvalidated  judge_judge_b_unvalidated  judge_score_unvalidated
  tickets_lead2_noisy_v1      1          3.833333          2.833333          3.333333
  tickets_author_v1           1          3.000000          3.500000          3.250000
  tickets_lead2_v1            1          2.833333          3.000000          2.916667
  tickets_lead1_v1            1          2.333333          1.833333          2.083333
  ...
  IS THE ORDERING REAL?   metric=judge_score_unvalidated  k=4 arms  N=6 items
    global test (permutation on within-item ranks): p = 0.2096  ->  NO detectable arm effect
  ...
  Scored by an LLM judge, not against references: tickets-judge-v1, unvalidated judge.
```

Your judging-set id, token counts and p-value will differ from these: `lead2_noisy` is
unseeded, so its outputs, and the set built from them, differ on every run.

Each judge's raw reply is stored under `data/judge-verdicts/`, so the same command again
calls nothing, and `--no-calls` rebuilds the scored runs from the stored verdicts for
$0. The judged runs read like any others: `leaderboard`, `pair-test` and `family-test`
work on them unchanged, through `EVAL_RUNS_DIR`. The fake judges' numbers mean nothing,
and the test says so: no detectable arm effect.

**When a real judge's scores disagree with your primary metric**, nothing changes until you
decide it should. The primary metric stays what it was; making a judge's score primary is a
recorded decision, with the old score kept beside it. Real judges, the validation block and
the controls: [RUNBOOK §12](../harness/docs/RUNBOOK.md#12-re-measure-with-a-validated-judge).
Why the gate exists: [Concepts](../harness/docs/CONCEPTS.md#re-measuring-a-frozen-experiment)
and [ADR-0001](adr/ADR-0001-judge-scorers.md).

## 11 · Validate

```bash
evh validate
```
```text
  ok   V1 schemas — 44 document(s) validated
  ok   V2 every run's dataset_id resolves (1 dataset(s) known)
  ok   V3 every run identifies its build
  ok   V4 materialized copies match their frozen hashes (1 of 1 datasets materialized here)
  ok   V5 no two configs report byte-identical scores
  ok   V6 every baseline's source run still exists and matches what the baseline carries
  ...
  ok   V8 no two runs share a config_id (outside a --repeat set)
  ...
  ok   V14 goals — 1 goal(s), every goal named resolves; optional (no required_from set)
  ok   V15 item fields — 1 field set(s), 1 dataset(s) with fields, every value declared and typed
VALIDATION PASSED
```

Run it in CI; it exits non-zero. V4 can only check a dataset whose
materialized copy is on the machine, and names each one it could not check; a CI job without
the sources checks none of them, so materialize first where the copy matters. Two independent
arms never agree to full float precision — V5 catches a copied number or a mis-wired arm, V8
two measurements quietly averaged into one row. V14 checks every goal and everything that
names one; V15 every field value against its field set, and the fields' hash against a hand
edit.

## 12 · Browse it: the catalog and the inspector

Tables answer the questions you thought to ask. To look around, build the catalog and start
the inspector:

```bash
evh catalog
```
```text
catalog: .../my-evals/.build/catalog — 1 goals, 1 datasets, 12 arms, 2 references
inspect: evh catalog-serve, then open the address it prints
```

<!-- guide-check: background -->
```bash
evh catalog-serve
```
```text
catalog: http://127.0.0.1:8765/.build/catalog/   (Ctrl-C to stop)
  it reads the runs once: restart it to see runs made after it started
```

Open the address it prints (if another program holds port 8765, add `--port 8766`). It reads
the runs when it starts, so after a new run, stop it and start it again.

- **The catalog** is static pages: one per dataset with every arm and its headline number, a
  goals page, and a page per goal ranking the arms that record its measure. Counts and means
  only, never an item's text, so the pages can be published. The dataset page lists its
  fields and how many tickets fill each; it summarises the values of a field marked `public`
  (Area, Plan) and no other (Names a deadline).
- **The inspector** is the server behind them, on 127.0.0.1 only. Pick arms on one dataset
  and it tests each against a baseline with the same paired test as `pair-test`: lead2
  against lead1 on gold gives p = 0.0938, as step 8's numbers do. It charts the per-ticket
  scores, and for one ticket shows its fields and each arm's output beside the reference.
- **Fields in a comparison.** Filter it to the tickets whose field matches (Area = account),
  or break it down by a choice or yes/no field (Names a deadline): the paired test within
  each group, Holm-corrected over every group together. Here two tickets name a deadline and
  four do not, and on two tickets no test can reach 0.05: a breakdown needs items in every
  group, and the page says when it has too few.
- **Its refusals** are the tests' refusals: no comparison across two datasets, and on a metric
  scored against a reference, no arm scored against another reference than the baseline's (a
  silver-scored run against a gold-scored one).

**No code needed here**, because this project keeps its data in the harness's layout
(`data/datasets/`, `data/runs*/`, `data/references/`, `data/goals/`). If your runs live in
another layout, write one adapter that answers the catalog's
questions (which arms exist, what each scored per item, which references exist, what one item
looked like) and name it in `config.yaml`: `catalog: {adapter: path/to/file.py:Class}`.
[INTEGRATION](../harness/docs/INTEGRATION.md#the-catalog-and-the-inspector) shows how.

## Doing it for real

- **Your system.** Write an adapter: a Python file whose `call_system()` takes the text in
  and returns the output plus tokens, and whose `score()` says what good means. Call it
  `adapter.py` at the project root and every arm that names no adapter uses it; with several
  tasks, name one in each arm's config, `adapter: adapters/my_system.py`. The tutorial's arms
  used the bundled one; start from a copy of it (`python -c "import evaluation_harness, os; print(os.path.join(evaluation_harness.__path__[0], 'adapter.py'))"`
  prints where it is). The contract, and how to wrap a non-Python system:
  [INTEGRATION](../harness/docs/INTEGRATION.md).
- **Hosted models.** Put prices in the config (`usd_per_mtok_in`, `usd_per_mtok_out`) and
  a ceiling in the project's `.env` (`EVAL_MAX_COST_USD`): a run that hits it stops, keeps what
  it has, and prints the `--resume` command so nothing is paid for twice. The worked
  examples' adapters record what the provider billed, from its response; yours can too.
- **Exploration vs. the record.** Point exploratory runs elsewhere —
  `EVAL_RUNS_DIR=data/runs-scratch evh experiment-run …` — and measure into `data/runs`
  only from a committed tree, once per arm. Re-running an arm into the same directory
  makes two measurements of one config, which validation refuses.
- **What the system is.** If the thing under test is not this repository, say what it
  is: `EVAL_BUILD_REF=v2.3.1 evh experiment-run …` (a tag, a commit, an image digest).
- **Scorer changed?** `evh rescore` recomputes every score from stored outputs, $0.
- **A metric you do not trust?** Re-measure with real LLM judges (step 10), validated
  first against human ratings on outputs like yours. The judges in a scorer are ordinary
  model specs, routed through a LiteLLM proxy or OpenRouter:
  [RUNBOOK §12](../harness/docs/RUNBOOK.md#12-re-measure-with-a-validated-judge).

## Every verb

| step | command |
|---|---|
| start a project | `evh init [--tutorial]` |
| freeze | `evh dataset-create --dataset-id … --source-dir …` |
| materialize | `evh dataset-materialize --dataset-id …` |
| silver references | `evh reference-create --dataset-id … --config …` |
| gold references | files in `data/references/gold/<dataset_id>/<item_id>.txt` |
| cost before spending | `evh experiment-run --config … --dry-run` |
| measure (+ own noise) | `evh experiment-run --config … --repeat 3` |
| many arms | `evh sweep --configs "data/configs/arm_*.yaml"` |
| list runs | `evh runs-list` |
| rank, with the test | `evh leaderboard --dataset-id …` |
| two runs | `evh run-compare --baseline … --candidate … --noise …` |
| a pre-named pair | `evh pair-test --dataset-id … --a … --b …` |
| a winner claim | `evh family-test --dataset-id … --a … --against …` |
| re-score, $0 | `evh rescore --dataset-id … [--reference-id gold/…] --out …` |
| re-measure with a judge (optional) | `evh judge-score --dataset-id … --scorer … [--dry-run]` |
| read the judged runs | `EVAL_RUNS_DIR=data/runs-judged/<scorer> evh leaderboard --dataset-id …` |
| is silver good enough | `evh silver-calibrate --dataset-id …` |
| how many items | `evh rank-stability --dataset-id …` |
| dev-slice-free result | `evh holdout --dataset-id … --exclude-dataset …` |
| billed cost | `evh cost-report` |
| baseline | `evh run-promote --run … --reason "…"` · `evh runs-list --baselines` |
| what it is for | `data/goals/<goal_id>.yaml`, and `goal:` on each config |
| browse and inspect | `evh catalog` · `evh catalog-serve` |
| consistency | `evh validate` |

In a checkout of this repository each is also a `make` target (`make pair-test DATASET_ID=…
A=… B=…`): the same scripts, with make variables for flags. `make help` lists them.

The reasoning behind each rule is in [Concepts](../harness/docs/CONCEPTS.md); every flag
and edge case — resuming, the judge panel, judge scorers, choosing the system under test —
in the [Runbook](../harness/docs/RUNBOOK.md).
