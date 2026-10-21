# Use the harness

Your first evaluation, end to end, in about twenty minutes — offline, no API key. You will
freeze a dataset, author references, build a small **golden dataset**, measure four
systems, compare them honestly, promote a baseline and, if you want, re-measure the same
outputs with an LLM judge. Every command below was run as written; the output shown is what
it printed.

The running example is a support-ticket summariser. The tutorial kit in
[`harness/tutorial/`](../harness/tutorial/README.md) has six invented tickets, a one-line
summary of each written by a person, and four arm configs. The "systems" are the
harness's offline `echo` provider, which returns the first *n* sentences of its input — a
stand-in that behaves like a model without needing one. Swapping in your own system is one
function, covered [at the end](#doing-it-for-real).

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
| **baseline** | the run you decided to measure future changes against, with why | `data/baselines/` | superseded, never edited |
| **judge scorer** | optional: LLM judges, their prompt, the task they score, and the runs that validated them | `data/scorers/<id>.yaml` | a change is a new `scorer_id` |

## 0 · Set up

```bash
git clone https://github.com/chipi/eval-harness && cd eval-harness/harness
make install          # a venv with the harness's few dependencies
make demo             # the whole loop on bundled data — proves the install works
```

## 1 · Freeze a dataset

```bash
make dataset-create DATASET_ID=tickets_v1 ARGS="--source-dir tutorial/tickets"
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

**Keep your sources under version control** (or gitignore them, if you cannot redistribute
them — the dataset's hashes are the record either way). An untracked input makes the tree
"dirty", and a run from a dirty tree cannot be promoted (step 9).

## 2 · Materialize

```bash
make dataset-materialize DATASET_ID=tickets_v1
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

## 4 · Author silver references

You cannot score quality without something to score against, and most projects start with
nothing. The usual first move is to let the best system you have write the answers:

```bash
make reference-create DATASET_ID=tickets_v1 CONFIG=data/configs/tickets_author.yaml
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
git add data/datasets/tickets_v1.json data/configs/tickets_*.yaml data/references/silver/tickets_v1
git commit -m "tickets_v1: dataset, arms, silver references"
```

Commit **before** measuring. A run records the commit it ran on; from a dirty tree that
commit does not describe what ran, and the run cannot become a baseline. (Run directories
themselves never count as dirt.)

First a dry run — it calls nothing and shows what a sweep will cost:

```bash
make experiment-dry-run CONFIG=data/configs/tickets_lead2.yaml
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
  make experiment-run CONFIG=data/configs/tickets_$a.yaml REPEAT=3
done
```
```text
  Arm spread over 3 repeats (max - min on identical input):      ← lead2
    overlap_f1     spread=0.000000   deterministic
  Arm spread over 3 repeats (max - min on identical input):      ← lead2_noisy
    overlap_f1     spread=0.044479   treat deltas below 0.044479 as noise
```

**This is the step people skip.** The spread is how far the arm disagrees with *itself* on
identical input. Any difference between two arms smaller than that is noise, whatever the
table says. A deterministic arm (spread 0) makes every delta real; a real model at
temperature 0 often is not deterministic. Your `lead2_noisy` numbers will differ from
these — it is unseeded on purpose.

## 6 · Compare

**All arms at once:**

```bash
make leaderboard DATASET_ID=tickets_v1
```
```text
  arm                      runs        overlap_f1      output_words
  tickets_author_v1           3          1.000000         35.166667
  tickets_lead2_v1            3          0.900088         28.500000
  tickets_lead2_noisy_v1      3          0.822425         23.555555
  tickets_lead1_v1            3          0.640917         16.000000

  IS THE ORDERING REAL?   metric=overlap_f1  k=4 arms  N=6 items
    global test (permutation on within-item ranks): p = 0.0002  ->  an arm effect exists
    pairs distinguishable: 3 of 6
```

The leaderboard *sorts*; the block underneath says how much of the order is real. Read
that block, not the row numbers.

**Two runs, side by side, against the noise floor you measured:**

```bash
make run-compare BASE=<a tickets_lead1_v1 run_id> CAND=<a tickets_lead2_v1 run_id> NOISE=0.044
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
so the delta belongs to it. `make runs-list` prints the run ids.

**One pair you named in advance**, tested item by item:

```bash
make pair-test DATASET_ID=tickets_v1 A=tickets_lead2_v1 B=tickets_lead1_v1 METRIC=overlap_f1
```
```text
    items A wins       6/6
    sign-flip p        0.0330  (20000 permutations)
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
make rescore DATASET_ID=tickets_v1 REFERENCE=gold/tickets_v1 OUT=data/runs-gold
EVAL_RUNS_DIR=data/runs-gold make leaderboard DATASET_ID=tickets_v1
```
```text
  tickets_lead2_v1            3          0.243426
  tickets_author_v1           3          0.231219
  tickets_lead2_noisy_v1      3          0.224900
  tickets_lead1_v1            3          0.201010

    global test (permutation on within-item ranks): p = 0.2124  ->  NO detectable arm effect
    pairs distinguishable: 0 of 6
    The table above is sorted, but these runs do not show the arms differ.
    Do not report an ordering from it.
```

Two lessons in one table. `author` fell from first to second the moment it stopped grading
itself. And against what a person actually wrote, six items cannot tell these arms apart
at all — the "3 of 6 distinguishable" on silver was the author's opinion, measured
precisely. Rescored runs go to a separate directory, never over the originals, and each
records both the reference it was measured against and the one it is scored against now.

**How good was the silver, then?** `silver-calibrate` tries every arm as a silver author
and asks how closely its ranking matches gold's:

```bash
EVAL_RUNS_DIR=data/runs-gold make silver-calibrate DATASET_ID=tickets_v1
```
```text
  trusted reference: gold/tickets_v1
  silver author          rho vs trusted
  tickets_author                  1.000
  tickets_lead2_noisy             1.000
  tickets_lead1                   0.500
  tickets_lead2                   0.500
```

On six items these correlations are coarse, but the habit is the point: before you rank
by silver, check it against a gold slice. How big a gold set must be is a measurement
too — `make rank-stability` shows how many items it takes before the order stops moving.

**Golden datasets, the rules:**

- **Gold is frozen like a dataset.** Every score was measured against those bytes; the
  run fingerprint hashes them. Fix a gold answer → new set (`tickets_v2`), or a rescore
  that records the change.
- **Never mix tiers in one number.** A run is scored against gold *or* silver, and says
  which. If you publish a silver-scored number, say so.
- **Keep a dev slice apart.** Tune prompts on a small nested dataset (`tickets_dev_v1`)
  and report on the rest — `make holdout` re-tests excluding it.
- **Disputed gold is a finding, not noise.** When most strong systems disagree with a
  gold answer, read it: in this repository's AG News and DBpedia experiments, one reader
  adjudicated those items by topic, shown the hosted answer, and found the gold wrong on all
  20 (AG News 17, DBpedia 3). The dataset's own gold stays primary; the adjudicated one sits
  beside it.

## 8 · Decide: is the winner separated?

A claim like "lead2 is the best" means *separated from every other arm*, with the
correction for testing several at once:

```bash
make family-test DATASET_ID=tickets_v1 A=tickets_lead2_v1 AGAINST=tickets_ \
     METRIC=overlap_f1 RUNS_DIR=data/runs-gold
```
```text
  family size m=3, declared before the p-values were read
  Holm step-down at alpha=0.05
    opponent                     delta      wins        p   thresh   verdict
    tickets_lead1_v1           +0.0424    5/6      0.0955   0.0167   --
    tickets_lead2_noisy_v1     +0.0185    4/6      0.3050   0.0250   --
    tickets_author_v1          +0.0122    4/6      0.3133   0.0500   --

    separated from 0 of 3 opponents; ahead on the point estimate against 3 of 3
```

Ahead of everyone, separated from no one. That is the honest state of this experiment: a
bigger gold set is the next step, not a conclusion.

## 9 · Promote a baseline

A baseline is the run future changes are measured against — a **decision**, recorded with
its reason. The reason has to say what the tests showed, not what you hoped:

```bash
make run-promote RUN=<the tickets_lead2_v1 run_id> \
  REASON="lead2 leads on gold for tickets_v1 (n=6) but separates from no arm; working baseline until the gold set grows"
make baselines-list
```

Refused if the run came from a dirty tree, if its build is unknown, or if the reason is a
single word: six months from now, "why is this the baseline?" must have an answer. The
previous baseline is archived, never edited.

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
make judge-score DATASET_ID=tickets_v1 SCORER=tickets-judge-v1
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
make judge-score DATASET_ID=tickets_v1 SCORER=tickets-judge-v1 ARGS="--unvalidated --dry-run"
```
```text
judging set  tickets_v1-4arms-4b9495ca9db6
  arms 4, items 6, blocks per item [4], position items 3, noise items 3
DRY RUN (nothing called; tokens are chars/4 estimates, cost from the scorer's price table)
  judge judge_a  calls    12 (stored 0)  tokens in      4,947  out      456  est $0.0000
  judge judge_b  calls    12 (stored 0)  tokens in      4,947  out      456  est $0.0000
  TOTAL        calls    24  tokens in      9,894  out      912  est $0.0000   cap $0.01
```

The **judging set** is frozen first: each ticket with every arm's summary, the arms' names
hidden and their order shuffled per ticket. Its id hashes all of that, so a different arm
set is a different judging set, never an addition to this one. 24 calls: each judge reads
each ticket once, plus a second shuffle on half the tickets (the **position** check: does
order change the verdict?) and a repeat on half (the **noise** check: does the judge agree
with itself?). Then:

```bash
make judge-score DATASET_ID=tickets_v1 SCORER=tickets-judge-v1 ARGS=--unvalidated
EVAL_RUNS_DIR=data/runs-judged/tickets-judge-v1 make leaderboard DATASET_ID=tickets_v1
```
```text
4 scored run(s) -> data/runs-judged/tickets-judge-v1  (6/6 items, unvalidated judge)
  calls 24, billed this run $0.0000, stored total $0.0000

dataset: tickets_v1   ranked by: judge_score_unvalidated (higher is better)

  arm                      runs  judge_judge_a_unvalidated  judge_judge_b_unvalidated  judge_score_unvalidated
  tickets_author_v1           1          3.000000          3.500000          3.250000
  tickets_lead2_noisy_v1      1          3.666667          2.500000          3.083333
  tickets_lead2_v1            1          2.833333          3.000000          2.916667
  tickets_lead1_v1            1          2.333333          1.833333          2.083333
  ...
  IS THE ORDERING REAL?   metric=judge_score_unvalidated  k=4 arms  N=6 items
    global test (permutation on within-item ranks): p = 0.2889  ->  NO detectable arm effect
  ...
  Scored by an LLM judge, not against references: tickets-judge-v1, unvalidated judge.
```

Each judge's raw reply is stored under `data/judge-verdicts/`, so the same command again
calls nothing, and `ARGS=--no-calls` rebuilds the scored runs from the stored verdicts for
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
make validate
```
```text
  ok   V1 schemas — 183 document(s) validated
  ok   V2 every run's dataset_id resolves
  ok   V4 materialized copies match their frozen hashes
  ok   V5 no two configs report byte-identical scores
  ok   V6 every baseline's source run still exists
  ok   V8 no two runs share a config_id (outside a --repeat set)
  ...
VALIDATION PASSED
```

Run it in CI; it exits non-zero. Two independent arms never agree to full float
precision — V5 catches a copied number or a mis-wired arm, V8 two measurements quietly
averaged into one row.

## Doing it for real

- **Your system.** Replace `call_system()` in `scripts/adapter.py` — one function, text
  in, output plus tokens out — or point a config's `adapter:` at your own file. The
  contract, the second function (`score`) and how to wrap a non-Python system:
  [INTEGRATION](../harness/docs/INTEGRATION.md).
- **Hosted models.** Put prices in the config (`usd_per_mtok_in`, `usd_per_mtok_out`) and
  a ceiling in `harness/.env` (`EVAL_MAX_COST_USD`): a run that hits it stops, keeps what
  it has, and prints the `--resume` command so nothing is paid for twice. The worked
  examples' adapters record what the provider billed, from its response; yours can too.
- **Exploration vs. the record.** Point exploratory runs elsewhere —
  `EVAL_RUNS_DIR=data/runs-scratch make experiment-run …` — and measure into `data/runs`
  only from a committed tree, once per arm. Re-running an arm into the same directory
  makes two measurements of one config, which validation refuses.
- **What the system is.** If the thing under test is not this repository, say what it
  is: `EVAL_BUILD_REF=v2.3.1 make experiment-run …` (a tag, a commit, an image digest).
- **Scorer changed?** `make rescore` recomputes every score from stored outputs, $0.
- **A metric you do not trust?** Re-measure with real LLM judges (step 10), validated
  first against human ratings on outputs like yours. The judges in a scorer are ordinary
  model specs, routed through a LiteLLM proxy or OpenRouter:
  [RUNBOOK §12](../harness/docs/RUNBOOK.md#12-re-measure-with-a-validated-judge).

## Every verb

| step | command |
|---|---|
| freeze | `make dataset-create DATASET_ID=… ARGS="--source-dir …"` |
| materialize | `make dataset-materialize DATASET_ID=…` |
| silver references | `make reference-create DATASET_ID=… CONFIG=…` |
| gold references | files in `data/references/gold/<dataset_id>/<item_id>.txt` |
| cost before spending | `make experiment-dry-run CONFIG=…` |
| measure (+ own noise) | `make experiment-run CONFIG=… REPEAT=3` |
| many arms | `make sweep CONFIGS="data/configs/arm_*.yaml"` |
| list runs | `make runs-list` |
| rank, with the test | `make leaderboard DATASET_ID=…` |
| two runs | `make run-compare BASE=… CAND=… NOISE=…` |
| a pre-named pair | `make pair-test DATASET_ID=… A=… B=…` |
| a winner claim | `make family-test DATASET_ID=… A=… AGAINST=…` |
| re-score, $0 | `make rescore DATASET_ID=… [REFERENCE=gold/…] OUT=…` |
| re-measure with a judge (optional) | `make judge-score DATASET_ID=… SCORER=… [ARGS=--dry-run]` |
| read the judged runs | `EVAL_RUNS_DIR=data/runs-judged/<scorer> make leaderboard DATASET_ID=…` |
| is silver good enough | `make silver-calibrate DATASET_ID=…` |
| how many items | `make rank-stability DATASET_ID=…` |
| dev-slice-free result | `make holdout DATASET_ID=… EXCLUDE=…` |
| billed cost | `make cost-report` |
| baseline | `make run-promote RUN=… REASON="…"` · `make baselines-list` |
| consistency | `make validate` · `make check` |

The reasoning behind each rule is in [Concepts](../harness/docs/CONCEPTS.md); every flag
and edge case — resuming, the judge panel, judge scorers, choosing the system under test —
in the [Runbook](../harness/docs/RUNBOOK.md).
