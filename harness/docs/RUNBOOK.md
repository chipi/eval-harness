# Runbook — from raw inputs to a defensible baseline

Follow this top to bottom. It is the same path `make help` lists, with the
reasoning attached. You should not need to open a script.

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
truth. Review some by hand and re-run with `TIER=gold` for the ones a human
has actually checked.

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
For anything you intend to promote, commit first and re-run.

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
  not what this pass cost.

  *This was false for a crash until 2026-09-30, which is the only case resume is for.*
  The carried values were read from `predictions.jsonl`, which is written **after** the
  pass returns — so a crashed run had none and every replayed row came back with
  `latency_ms: None, cost_usd: None`. Rows are now appended to
  `outputs/_rows.jsonl` as each item completes. Found by external review.
- **You cannot resume from a different arm, or from one that cannot be identified.**
  The source's `config_id` and `dataset_id` are checked against the config you are
  launching and a mismatch is refused. Identity comes from `run.json`, written **before
  the first item** precisely so a crashed run can still answer the question — until
  2026-09-30 it came from `metrics.json`, which a crashed run does not have, so the
  check could only warn and `arm_a --resume <crashed arm_b run>` exited 0 having
  recorded arm_a with arm_b's answers.

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

## 7b. The analysis tools, none of which this runbook used to name

Sections 0–7 walk one arm from data to comparison. Everything that turns a pile of runs
into a *finding* is a separate verb, and this runbook listed none of them — so the tools
that produced every number in `research/` were discoverable only by reading the
Makefile. Found by external review.

| verb | answers |
|---|---|
| `make leaderboard DATASET_ID=…` | how do all the arms rank, on every metric at once |
| `make family-test DATASET_ID=… A=… AGAINST=…` | is arm A separated from a **pre-declared family**, Holm step-down. This is what every separation claim in the reports rests on |
| `make pair-test DATASET_ID=… A=… B=…` | are these two arms different — paired, per item. Uncorrected, so only legitimate for a pair named in advance |
| `make holdout DATASET_ID=… EXCLUDE_DATASET=…` | does the result survive on the items the dev slice never contained |
| `make rank-stability DATASET_ID=…` | how many items before the ordering stops moving — measured, not assumed from a power table |
| `make bootstrap-test DATASET_ID=…` | a percentile interval for a corpus-level metric that has no per-item value |
| `make rescore DATASET_ID=…` | recompute every score from stored outputs under the current scorer. **$0, no API calls** |
| `make cost-report DATASET_ID=…` | what each arm actually cost, from the provider's bill rather than a price table |
| `make silver-calibrate DATASET_ID=…` | does a model-authored reference rank arms the way the trusted one does |

Two that are easy to reach for and wrong:

- **`pair-test` on a pair you chose after seeing the leaderboard** is the winner's
  curse with extra steps. If you did not name the pair in advance, use `family-test`.
- **`leaderboard` as a ranking.** It sorts; it does not separate. Four of the five
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

Six checks: schema conformance, every run's `dataset_id` resolves, every run
identifies its build, materialized copies still match their hashes, no two
configs reporting byte-identical scores, and no baseline pointing at a deleted
run.

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
5. Scored against **silver**? `make runs-list` shows the tier — silver ranks
   arms, it does not establish correctness.
6. Did a source change? `make dataset-materialize DATASET_ID=... ARGS=--force`
   re-verifies every hash.

Most "regressions" are one of the first three.
