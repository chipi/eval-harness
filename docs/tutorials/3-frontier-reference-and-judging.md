# Tutorial 3 · A frontier model's run as the reference, gold, and judging

In [getting started](../GUIDE.md) the `author` arm ran first and its run became the silver
reference that every other arm was scored against. In a real project the author is a
frontier model: too expensive to run on every item in production, cheap enough to run once.
You pay for one pass, and the cheaper arms are measured by how close they come to it.

This tutorial asks the next question: **how good was that silver?** It adds answers a person
wrote (gold), re-scores every run against them for $0, measures how far silver drifted, and then
re-measures the same stored outputs with LLM judges. Steps 2 to 5 run offline in the project
getting started left, with the tutorial kit's hand-written summaries and two stand-in judges;
`make guide-check` runs them as written. Steps 1 and 6 are the same moves with real models,
which need a key ([tutorial 2](2-hosted-llm.md)).

## 1. The frontier arm, with a real model

The author is an arm like any other. With a hosted model it is a config such as this one, from
the newcomer scenario this release was tried on (a LiteLLM proxy's model name; any provider of
[tutorial 2](2-hosted-llm.md) works):

```yaml
# data/configs/briefs_opus.yaml
config_id: briefs_opus_v1
dataset_id: briefs_v1
params:
  provider: litellm
  model: eval-opus-5
  temperature: 0.0
  max_tokens: 300          # room to finish: a reference cut off mid-sentence is refused
  prompt: "Summarise the following news brief in one sentence."
  usd_per_mtok_in: 5.0
  usd_per_mtok_out: 25.0
goal: brief_summary
```

<!-- guide-check: skip -->
```bash
evh experiment-run --config data/configs/briefs_opus.yaml --dry-run     # price it first
evh experiment-run --config data/configs/briefs_opus.yaml
evh reference-create --dataset-id briefs_v1 --from-run <the briefs_opus_v1 run_id>
git add data/references && git commit -qm "silver/briefs_v1 from the frontier arm's run"
```

What `reference-create --from-run` refuses, and why:

- **An empty output, or one that stopped at `max_tokens`.** In the scenario's first run a
  frontier arm at `max_tokens: 80` wrote 19 of 20 summaries cut off mid-sentence; frozen as the
  reference, every arm would have been graded against fragments. That is why the config above
  has room to finish. If yours stops at the cap, raise `max_tokens` in a new `config_id`
  (`briefs_opus_v2`) and run again (`--allow-cut-off` is for outputs that end at the cap by
  design). `experiment-run`
  already warns, naming the items, when outputs stop at the cap.
- **A run from a dirty tree, or of an unknown build** (as `run-promote` does), an unfinished run,
  a derived one (rescored or judged), or a run on another dataset.
- **`--tier gold`.** Gold is what a person wrote or checked, never a model's run.

Commit each reference before the next run: an uncommitted reference makes every run after it
dirty. `--config` instead of `--from-run` authors the reference in a pass of its own, one call per
item, when there is no run to read first; its outputs may then differ from the run you looked at.

## 2. Make it golden

A gold set is plain files: one `<item_id>.txt` per item, under
`data/references/gold/<dataset_id>/`. Write them yourself, or review silver ones and keep those
you would sign. The kit has six, written by hand:

```bash
mkdir -p data/references/gold/tickets_v1
cp tutorial/gold/*.txt data/references/gold/tickets_v1/
git add data/references/gold/tickets_v1 && git commit -qm "tickets_v1: gold references"
```

From now on every new run on `tickets_v1` is scored against gold automatically (gold always
wins over silver, and the run records which it used). The runs you already have need not be
paid for again: their outputs are stored, so re-scoring is arithmetic.

```bash
evh rescore --dataset-id tickets_v1 --reference-id gold/tickets_v1 --out data/runs-gold
EVAL_RUNS_DIR=data/runs-gold evh leaderboard --dataset-id tickets_v1
```
<!-- guide-check: varies lead2_noisy author global distinguishable sorted ordering -->
```text
  tickets_lead2_v1            3          0.243426
  tickets_author_v1           1          0.231219
  tickets_lead2_noisy_v1      3          0.228799
  tickets_lead1_v1            3          0.201010
  ...
    global test (permutation on within-item ranks): p = 0.1262  ->  NO detectable arm effect
    pairs distinguishable: 0 of 6
    The table above is sorted, but these runs do not show the arms differ.
    Do not report an ordering from it.
```

Two lessons in one table. `author`, the reference everyone chased, is not first once a person's
answers are the measure. And against what a person actually wrote, six items can almost never
tell these arms apart: the pair that looked distinguishable on silver was the author's opinion,
measured precisely. Rescored runs go to a separate directory, never over the originals, and each
records both the reference it was measured against and the one it is scored against now.

## 3. How good was the silver?

`silver-calibrate` tries every arm as a silver author and asks how closely its ranking matches
gold's:

```bash
EVAL_RUNS_DIR=data/runs-gold evh silver-calibrate --dataset-id tickets_v1
```
<!-- guide-check: varies author lead1 lead2 -->
```text
  trusted reference: gold/tickets_v1
  ...
  silver author          rho vs trusted  sibling lift
  tickets_author                  1.000             —   (0 sibling(s))
  tickets_lead2                   1.000             —   (0 sibling(s))
  tickets_lead2_noisy             1.000             —   (0 sibling(s))
  tickets_lead1                   0.500             —   (0 sibling(s))

  rho: how far the arms' order on this author's silver agrees with their order on the
  ...
```

Your rows will differ from these: with four arms, `lead2_noisy`'s place in each ranking moves
every rho. The command explains its columns under the table: rho is how far the arms' order on
that author's silver agrees with their order on gold (1 is the same order); sibling lift is how
many places the silver moves the author's own family up, "—" when no other arm shares it (here
none does). Arms are named without their `_vN` suffix: an arm's versions are pooled. On six items these correlations are coarse, but the habit is the point: before you
rank by silver, check it against a gold slice. How big a gold set must be is a measurement too:
`evh rank-stability` shows how many items it takes before the order stops moving.

## 4. Is the winner separated, on gold?

```bash
evh family-test --dataset-id tickets_v1 --a tickets_lead2_v1 --against tickets_ \
    --runs-dir data/runs-gold
```
<!-- guide-check: varies tickets_lead1_v1 tickets_author_v1 lead2_noisy ahead -->
```text
  family size m=3, declared before the p-values were read
  Holm step-down at alpha=0.05
  p: exact, over all 2^6 sign patterns

    opponent                     delta    A wins        p   thresh   verdict
    tickets_lead1_v1           +0.0424    5/6      0.0938   0.0167   --
    tickets_lead2_noisy_v1     +0.0146    4/6      0.1562   0.0250   --
    tickets_author_v1          +0.0122    4/6      0.3125   0.0500   --

    separated from 0 of 3 opponents; ahead on the point estimate against 3 of 3
```

Ahead of every arm on the point estimate, separated from none; against `lead2_noisy` the delta is
smaller than that arm's own spread, and its sign can change from one run to the next. That is the
honest state of this experiment: a bigger gold set is the next step, not a conclusion.

**Golden datasets, the rules:**

- **Gold is frozen like a dataset.** Every score was measured against those bytes; the run
  fingerprint hashes them. Fix a gold answer → a new set, or a rescore that records the change.
- **Never mix tiers in one number.** A run is scored against gold *or* silver, and says which.
  If you publish a silver-scored number, say so.
- **Keep a dev slice apart.** Tune prompts on a small nested dataset (`tickets_dev_v1`) and
  report on the rest: `evh holdout` re-tests excluding it.
- **Disputed gold is a finding, not noise.** When most strong systems disagree with a gold
  answer, read it: in this repository's AG News and DBpedia experiments, one reader adjudicated
  those items by topic, shown the hosted answer, and found the gold wrong on all 20 (AG News 17,
  DBpedia 3). The dataset's own gold stays primary; the adjudicated one sits beside it
  ([RUNBOOK §11](../../harness/docs/RUNBOOK.md#11-adjudicate-disputed-gold)).

## 5. Re-measure with an LLM judge (optional)

Word overlap is a weak measure of a summary, and you will not always have gold to score against.
An LLM judge can read each ticket and rate every arm's summary instead. It does not re-run any
arm: it reads the outputs already stored, so it is a second measurement of the same frozen
record, written to its own directory. Nothing here is required.

A judge is a **judge scorer**, one file. The kit has one whose two judges are `provider: fake`,
a deterministic stand-in that calls nothing, so this step stays offline and $0:

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
protocol: {outputs_per_call: 16, blinding: true, order_seed: 0,
           position_check_fraction: 0.5, noise_check_fraction: 0.5}   # both required
cost_cap_usd: 0.01
```

The two check fractions are required: a scorer without them is refused. The noise check must be
above 0, and so must the position check whenever a call sees more than one output.

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

**The harness refuses a judge nobody has checked.** A judge is a model's opinion, as silver is,
so before its scores count it must be validated: a `validation` block names the committed runs
that measured each judge against human ratings, on data like yours. Fake judges can never pass.
To try the pass anyway, say so, and every number is labelled. Price it first; `--dry-run` calls
nothing:

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
hidden and their order shuffled per ticket. Its id hashes all of that, so a different arm set is
a different judging set, never an addition to this one. 24 calls: each judge reads each ticket
once, plus a second shuffle on half the tickets (the **position** check: does order change the
verdict?) and a repeat on half (the **noise** check: does the judge agree with itself?). Then:

```bash
evh judge-score --dataset-id tickets_v1 --scorer tickets-judge-v1 --unvalidated
EVAL_RUNS_DIR=data/runs-judged/tickets-judge-v1 evh leaderboard --dataset-id tickets_v1
```
<!-- guide-check: varies tickets_ global FRONTIER agree reshuffled -->
```text
4 scored run(s) -> .../data/runs-judged/tickets-judge-v1  (6/6 items, unvalidated judge)
  calls 24, spent this run $0.0000, stored total $0.0000  (the provider's bill where it reports one, else the price table)
  ...
dataset: tickets_v1   ranked by: judge_score_unvalidated (higher is better)

  arm                      runs  judge_judge_a_unvalidated  judge_judge_b_unvalidated  judge_score_unvalidated
  tickets_author_v1           1          3.000000          3.500000          3.250000
  tickets_lead2_v1            1          2.833333          3.000000          2.916667
  tickets_lead2_noisy_v1      1          2.166667          3.000000          2.583333
  tickets_lead1_v1            1          2.333333          1.833333          2.083333
  ...
  IS THE ORDERING REAL?   metric=judge_score_unvalidated  k=4 arms  N=6 items
    global test (permutation on within-item ranks): p = 0.3825  ->  NO detectable arm effect
  ...
  FRONTIER on judge_score_unvalidated / total_cost_usd / latency_ms — 3 of 4 arms
  ...
  Scored by an LLM judge, not against references: tickets-judge-v1, unvalidated judge.
  ...
  The judging pass (tickets-judge-v1, 6/6 items, unvalidated judge), from summary.json:
    judges judge_a and judge_b agree: item tau 0.040, arm order spearman 0.400
    judge_a: reshuffled outputs tau 1.000 (position), the same call repeated tau 1.000 (noise)
  ...
```

Your judging-set id, token counts, scores and p-value will differ from these: `lead2_noisy` is
unseeded, so its outputs, and the set built from them, differ on every run. One judge scored
every arm the same way, so all four share one table, `author` included: its run predates the
reference, but the judge does not read one. A judged run keeps its source run's cost and speed,
so the table has its frontier. Under it the leaderboard prints the judging pass's own checks,
from the pass's `summary.json`: how far the two judges agree, and for each judge how much its
verdict moves when the outputs are reshuffled (position) and when the same call is repeated
(noise). Read them before the ranking: a difference between arms smaller than the noise check's
is not one. ([RUNBOOK §12](../../harness/docs/RUNBOOK.md#12-re-measure-with-a-validated-judge),
step 6.)

Each judge's raw reply is stored under `data/judge-verdicts/`, so the same command again calls
nothing, and `--no-calls` rebuilds the scored runs from the stored verdicts for $0. The judged
runs read like any others: `leaderboard`, `pair-test` and `family-test` work on them unchanged,
through `EVAL_RUNS_DIR`. The fake judges' numbers mean nothing, and the test says so: no
detectable arm effect.

**When a real judge's scores disagree with your primary metric**, nothing changes until you
decide it should. The primary metric stays what it was; making a judge's score primary is a
recorded decision, with the old score kept beside it. Why the gate exists:
[CONCEPTS](../../harness/docs/CONCEPTS.md#re-measuring-a-frozen-experiment) and
[ADR-0001](../adr/ADR-0001-judge-scorers.md).

## 6. Real judges

A real judge is an ordinary model spec in the scorer's `judges` list: two or more, from different
vendor families, so one vendor's taste is not the verdict. From the same newcomer scenario:

```yaml
judges:
  - id: gemma_l
    params: {provider: litellm, model: eval-gemma-31b, family: gemma, temperature: 0.0,
             reasoning: {enabled: false}, max_tokens: 400, usd_per_mtok_in: 0.1, usd_per_mtok_out: 0.2}
  - id: qwen_s
    params: {provider: litellm, model: eval-qwen-flash, family: qwen, temperature: 0.0,
             reasoning: {enabled: false}, max_tokens: 400, usd_per_mtok_in: 0.05, usd_per_mtok_out: 0.2}
```

Each judge's `provider:` names where its calls are routed ([tutorial 2](2-hosted-llm.md) lists
the providers). A judge reads credentials by role: it reads `EVAL_JUDGE_<VAR>` first (so judges
can have their own keys and budgets), then falls back to `<VAR>` (so judges can share the arms'
credentials). A judge's own `base_url` or `api_key_env` in its params overrides the environment.

<!-- guide-check: skip -->
```bash
evh judge-score --dataset-id briefs_v1 --scorer briefs-judge-v1 --unvalidated --dry-run
evh judge-score --dataset-id briefs_v1 --scorer briefs-judge-v1 --unvalidated
evh judge-score --dataset-id briefs_v1 --scorer briefs-judge-v1 --unvalidated --retry-unparsed
EVAL_RUNS_DIR=data/runs-judged/briefs-judge-v1 evh leaderboard --dataset-id briefs_v1
```

Real judges sometimes reply with something that does not parse (reasoning aloud, a reply cut
off); the pass reports it, and `--retry-unparsed` calls again for those blocks only. An item
counts only when all its blocks parsed. In the scenario, 2 of 80 replies on the briefs and 15 of
128 on the intents did not parse the first time. A reply that is not bare JSON (one JSON object,
a `json` code fence allowed), or that repeats the item, is committed only as its hash, so
an item's text never reaches git by accident. Its text is kept beside its record, git-ignored,
in `data/judge-verdicts/<scorer>/<judging set>/<judge>/.withheld/<item>.<pass>.b<block>.txt`, and
the log line names that file: read it before you retry, to see why the reply failed.

Retry until a pass recovers nothing new (in the scenario, two passes took the intents from 26 of
32 items to 31). An item still failing after that stays out of the judged table, which counts the
items it holds; if it is a large share, change the judge's prompt or `max_tokens` rather than
retrying again. The judged table is built from one run per arm, the latest, over the items that
parsed, so an arm's cost and speed there can differ slightly from its row on gold.

Validating a judge (the `validation` block, the runs it names, what the gate checks), the
prompt's `{n}`, blocks and the cost cap:
[RUNBOOK §12](../../harness/docs/RUNBOOK.md#12-re-measure-with-a-validated-judge).
