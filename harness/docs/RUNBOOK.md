# Runbook — from raw inputs to a defensible baseline

Follow this top to bottom. It is the same path `make help` lists, with the
reasoning attached. You should not need to open a script.

New here? **[Use the harness](../../docs/GUIDE.md)** walks the whole path once on a
bundled example, offline, with the real output of every command — including building a
golden dataset. This page is the reference for each step.

---

## 0. Prove it works before you touch it

```bash
make demo
```

That freezes a dataset from the bundled samples, materializes it, runs an
experiment three times, and validates the tree. No API key. If that works, the
skeleton is wired correctly and anything that breaks later is your change.

---

## 1. Put your inputs in `data/sources/`

Anything file-shaped: transcripts, tickets, documents, diffs, JSON payloads.

**`sources/` is immutable.** Once an item is in a dataset, its bytes are what a
published number was measured on. If an input genuinely changes, that is a *new*
dataset (`_v2`), never an edit in place. This is not bureaucracy — editing a
source silently invalidates every number already reported against it, and
nothing will tell you.

---

## 2. Freeze a selection

```bash
make dataset-create DATASET_ID=my_v1
make dataset-create DATASET_ID=my_smoke_v1 ARGS="--limit 5"     # a fast cut
```

This writes `data/datasets/my_v1.json`: the item list plus a **sha256 per item**.

The `dataset_id` is the comparison contract. Every run records it, and
`run-compare` refuses to compare across two different ones. Name it for what it
*is* (`support_tickets_2026q1_v1`), not for what you were doing at the time
(`test2`).

---

## 3. Materialize

```bash
make dataset-materialize DATASET_ID=my_v1
```

Copies the items into `data/materialized/<dataset_id>/` and **re-verifies every
hash**. If a source changed since the freeze, this fails loudly rather than
quietly measuring different bytes than the dataset claims.

`materialized/` is derived. Delete it any time; `make dataset-materialize`
rebuilds it. If something in there cannot be rebuilt, it is in the wrong place.

---

## 4. Point the harness at your system

Edit **one function**, `call_system()` in `scripts/adapter.py`:

```python
def call_system(text, params):
    from myproject.summarise import summarise      # your existing code
    out = summarise(text, model=params["model"])
    return Result(output=out.text,
                  tokens_in=out.usage.prompt_tokens,
                  tokens_out=out.usage.completion_tokens)
```

Then describe each arm in `data/configs/<name>.yaml` — the knobs belong in the
config, not in code, so an arm is reproducible and diffable:

```yaml
config_id: my_config_v1
dataset_id: my_v1
params:
  provider: anthropic
  model: claude-sonnet-4-6
  temperature: 0.0
  usd_per_mtok_in: 3.0      # so the run records what it cost
  usd_per_mtok_out: 15.0
```

Full detail in [INTEGRATION.md](INTEGRATION.md).

---

## 4b. Author ground truth — you cannot score quality without it

Most projects have none. Generate it with the best model you have:

```bash
make reference-create DATASET_ID=my_v1 CONFIG=data/configs/best_model.yaml ARGS="--limit 10"
```

That writes **silver** references — model-generated, therefore consistent
rather than correct. Enough to rank arms against each other; not a claim about
truth.

**Gold** is what a person wrote or checked: one `<item_id>.txt` per item under
`data/references/gold/<dataset_id>/` — write them, or review silver ones and keep the
ones you would sign (`TIER=gold` authors straight into gold, for a system whose output you
have reviewed). Gold always wins over silver for new runs. Runs made before the gold set
existed are re-scored against it for $0:
`make rescore DATASET_ID=my_v1 REFERENCE=gold/my_v1 OUT=data/runs-gold`.

Every later run is scored against these automatically and records which tier it
used. Ten items is enough to rank four arms; keep the first pass cheap.

---

## 5. Measure the arm's own noise — **before** you compare anything

```bash
make experiment-run CONFIG=data/configs/my_config.yaml REPEAT=3
```

Output ends with:

```text
Arm spread over 3 repeats (max - min on identical input):
  overlap_f1   spread=0.043888   treat deltas below 0.043888 as noise
```

**This step is the difference between measuring and guessing.** A real example
from the project this came from: one model showed **0.058 spread on
byte-identical input** — wider than most of the deltas people were arguing
about. Without knowing that, every one of those arguments was about noise.

If the spread is `0.000000`, the arm is deterministic and any delta is real.
Write the number down; you need it in step 7.

---

## 6. Run the arms you want to compare

```bash
make experiment-run CONFIG=data/configs/arm_a.yaml
make experiment-run CONFIG=data/configs/arm_b.yaml
make runs-list
```

A run is only attributable if it knows its build. `runs-list` marks runs from a
dirty tree with `*` — their `build.ref` does not describe what actually ran.
**Commit before you measure** — dataset, configs, references — so the runs you keep are
clean the first time. Re-running an arm into `data/runs` after the fact leaves two
measurements of one config, which `make validate` refuses (V8); explore in a scratch
directory instead (`EVAL_RUNS_DIR=data/runs-scratch`).

### When a run dies partway: `--resume`

A sweep that is interrupted — a crash, a 429 that outlasts the retries, or the
`EVAL_MAX_COST_USD` cap — leaves its finished items on disk. Outputs are written
**as each item is produced**, so what you already paid for survives.

```bash
make experiment-run CONFIG=data/configs/arm_a.yaml ARGS="--resume arm_a_v1_20260929T101500Z"
```

The run id is the directory under `data/runs/`, and the cost cap prints the exact
command when it stops you. A resumed pass **re-reads every finished output and scores
it again**, rather than skipping it — so the new run is complete, not a fragment — and
calls the model only for the items that are missing.

Three things worth knowing:

- **It costs nothing to replay.** Items read from disk make no API call, and the cost
  cap cannot stop them, because they spend nothing.
- **A replayed item keeps what was measured for it** — cost, tokens, latency and
  `_meta` all carry over from the pass that produced it, and every replayed row is
  flagged `resumed: 1` so you can separate them. It reports what the *results* cost,
  not what this pass cost. The values come from the rows appended to
  `outputs/_rows.jsonl` as each item completes, so a crashed run, which never wrote
  `predictions.jsonl`, still carries them.
- **You cannot resume from a different arm, or from one that cannot be identified.**
  The source's `config_id` and `dataset_id` are checked against the config you are
  launching and a mismatch is refused. Identity comes from `run.json`, written **before
  the first item** precisely so a crashed run can still answer the question
  (`metrics.json`, which a crashed run does not have, could not).

  A directory with neither file is refused outright. `--resume-unverified` overrides
  that, for runs made before `run.json` existed; it will record another arm's answers
  under your config if you are wrong about whose outputs those are.

Exit codes: `0` complete, `2` stopped early by the cost cap with usable partial
results, `1` nothing was measured at all.

---

## 7. Compare, with the noise floor you measured

```bash
make run-compare BASE=<run_id> CAND=<run_id> NOISE=0.043888
```

Quality, cost and speed appear side by side — `overlap_f1` next to
`total_cost_usd` and `latency_ms`. "Better" and "better and 4x the price" are
different findings, and only one of them is a decision.

Read the verdict column, not the delta. A `+0.02` that is below your measured
spread is **noise**, and the tool says so. Without `NOISE=` it nags, because a
delta judged against nothing is not evidence.

It refuses outright if the two runs used different `dataset_id`s.

---

## 7b. The analysis tools

Sections 0–7 walk one arm from data to comparison. Everything that turns a pile of runs
into a *finding* is a separate verb: these are the tools behind the numbers in `research/`.

| verb | answers |
|---|---|
| `make leaderboard DATASET_ID=…` | how do all the arms rank, on every metric at once |
| `make family-test DATASET_ID=… A=… AGAINST=…` | is arm A separated from a **pre-declared family**, Holm step-down. This is what every separation claim in the reports rests on |
| `make pair-test DATASET_ID=… A=… B=…` | are these two arms different — paired, per item. Uncorrected, so only legitimate for a pair named in advance |
| `make holdout DATASET_ID=… EXCLUDE=…` | does the result survive on the items the dev slice never contained |
| `make rank-stability DATASET_ID=…` | how many items before the ordering stops moving — measured, not assumed from a power table |
| `make bootstrap-test DATASET_ID=… A=… AGAINST=…` | a percentile interval for a corpus-level metric that has no per-item value |
| `make rescore DATASET_ID=…` | recompute every score from stored outputs under the current scorer — or, with `REFERENCE=gold/…`, against a reference set that arrived later. **$0, no API calls** |
| `make cost-report` | what each arm actually cost, from the provider's bill rather than a price table |
| `make silver-calibrate DATASET_ID=…` | does a model-authored reference rank arms the way the trusted one does |

Two that are easy to reach for and wrong:

- **`pair-test` on a pair you chose after seeing the leaderboard** is the winner's
  curse with extra steps. If you did not name the pair in advance, use `family-test`.
- **`leaderboard` as a ranking.** It sorts; it does not separate. Five of the six
  experiments here have a top group its own tests cannot tell apart, and the table
  still prints them 1, 2, 3.

---

## 8. Promote — a decision, not a copy

```bash
make run-promote RUN=<run_id> REASON="beat prev baseline by 6% on my_v1 n=40, spread 0.004"
```

Refused if the run came from a dirty tree, if its build is unknown, or if the
reason is a single word. Those refusals exist for the same reason: in six months, *"why is this the
baseline?"* must have an answer.

The previous baseline is archived under `data/baselines/superseded/`. A baseline
is never edited, only superseded.

```bash
make baselines-list
```

---

## 9. Validate before you trust anything

```bash
make validate
```

Ten checks (V1–V10): schema conformance, every run's `dataset_id` resolves, every run
identifies its build, materialized copies still match their hashes, no two
configs reporting byte-identical scores and per-item results, no baseline pointing at a
deleted run, every committed run readable and present on disk, no two runs claiming one
`config_id`, and no derived run naming a scorer that is not the code in this tree.

The duplicate-score check catches a specific and nasty failure: two
independent arms do not agree to full float precision. When they do, one of them
is not its own measurement — a copied number, a mis-wired arm, a cached result.

Run it in CI. It exits non-zero.

---

## 10. Optional — the judge panel

When the cheap metric is biased in your domain but you have an expensive judge
you trust:

```bash
make judge      # FakeJudge, keyless
```

Triage on the cheap metric, decide with the judge, cost-capped with a mid-run
abort that preserves partial results. Knobs in `config.example.yaml`; the
reasoning is in the main README.

---

## 11. Adjudicate disputed gold

When strong arms agree against the gold, the gold may be wrong. Check it, and re-score for
$0:

1. **Pick the items from both sides.** Take the items most arms miss, and also the items
   your best arms miss. Reviewing only one side flatters the other.
2. **Record each verdict** in an `adjudication.json` beside the experiment: the item, the
   gold, what the adjudicator was shown, the verdict and the reason. Who adjudicated goes
   in the file too.
3. **Build the reference set and re-score:**

   ```bash
   python examples/_shared/adjudicate.py examples/<experiment>/adjudication.json
   cd harness && python scripts/rescore.py --dataset-id <id> \
       --reference-id gold/<id>_adj1 --out data/runs-adjudicated
   EVAL_RUNS_DIR=data/runs-adjudicated make leaderboard DATASET_ID=<id>
   ```

4. **Add a claim check** for every new number you report. It can recompute them from the
   committed predictions and the adjudication file, so the re-scored runs need not be
   committed.
5. **Decide what is primary, and record why** (CONCEPTS: Re-measuring a frozen
   experiment).

Worked example: `examples/classification-ag-news/adjudication.json`.

---

## 12. Re-measure with a validated judge

When a better instrument exists than the metric the experiment ranks by (SummEval showed
`coverage` agrees with experts at τ 0.10, a validated LLM judge at 0.52), measure the frozen
outputs again, billed and capped. Design: [ADR-0001](../../docs/adr/ADR-0001-judge-scorers.md).
This is not `make judge`, the older judge panel.

```bash
make judge-score DATASET_ID=cnn_dailymail_200 SCORER=judge-summ-v1 ARGS=--dry-run   # free
make judge-score DATASET_ID=cnn_dailymail_200 SCORER=judge-summ-v1
EVAL_RUNS_DIR=data/runs-judged/judge-summ-v1 make leaderboard DATASET_ID=cnn_dailymail_200
```

1. **The scorer** is `data/scorers/<id>.yaml`: two or more judges from different vendor
   families, the prompt, the protocol, a `validation` block and a cost cap. The command
   refuses a scorer whose validation does not name a committed run with the stated value and
   the judge's model. `ARGS=--unvalidated` overrides it and labels every number
   "unvalidated judge" (the primary metric becomes `judge_score_unvalidated`).
2. **Dry-run first.** It builds the judging set and prints calls, tokens and estimated cost
   per judge, and calls nothing.
3. **The judging set** is one item = the article plus every arm's primary output, arm ids
   hidden, order shuffled per item by the seed. Its id pins the arm set, and its manifest is
   frozen in `data/judging-sets/`. Add an arm and you get a new set and a new pass.
4. **Blocks.** SummEval validated 16 summaries per call, so an item's arms are judged in the
   fewest blocks of at most `outputs_per_call`: 29 arms are 15 + 14. Scores are absolute
   1–5 per dimension, so blocks are pooled.
5. **Verdicts** are stored raw per call in `data/judge-verdicts/`. A rerun skips what is
   stored; `ARGS=--no-calls` projects from them for $0. At the cost cap the pass stops and
   keeps everything bought; raise the cap to continue.
6. **Read `data/runs-judged/<id>/summary.json` before the leaderboard:** per-judge columns,
   inter-judge agreement, which arms share a judge's family, the position check (a second
   shuffle on a subset) and the noise check (a repeat on a subset). A difference between arms
   smaller than the noise check's is not a difference.
7. **Record the decision.** Changing an experiment's primary metric is a recorded decision
   with a reason; the old metric stays beside the new one (CONCEPTS: Re-measuring a frozen
   experiment).

---

## Choosing what to evaluate against

The **system under test** is recorded as `build.ref`. It defaults to this tree's
git SHA, which is right only if this tree *is* the system — and a drop-in
usually is not.

Declare it instead. No code edit:

```bash
EVAL_BUILD_REF=v2.3.1                make experiment-run CONFIG=...
EVAL_BUILD_REF=sha256:ab12…          make experiment-run CONFIG=...   # image digest
EVAL_BUILD_REF=$(git -C ../ rev-parse HEAD)   make experiment-run ...  # the parent repo
```

**Pin it.** An eval against a moving target measures the target's movement, and
you will spend a day attributing that to your change.

`make validate` fails on any run whose build is `unknown`, and `make run-promote`
refuses one — a baseline that names no system cannot be acted on.

---

## When a number looks wrong

In order, because each is cheaper than the next:

1. `make validate` — is the tree even consistent?
2. `make runs-list` — was the run from a dirty tree?
3. `REPEAT=3` — is the delta inside the arm's own spread?
4. Same `dataset_id` on both sides? (`run-compare` refuses, but check the ids)
5. Scored against **silver**? A run's `metrics.json` records `reference_tier` — silver
   ranks arms, it does not establish correctness.
6. Did a source change? `make dataset-materialize DATASET_ID=... ARGS=--force`
   re-verifies every hash.

Most "regressions" are one of the first three.
