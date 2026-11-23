# Tutorial 9 · Your own system: a custom adapter

[INTEGRATION](../../harness/docs/INTEGRATION.md) says what an adapter is. This tutorial writes one, small, and runs the
whole loop through it: `adapter.py`'s two functions, a system with prices, a dataset, a goal, `evh run`, `evh
leaderboard`, `evh pair-test`, the goal's view and the catalog. It runs offline and costs $0: the "system" is a stub
that answers from its input, in the place where your own code would go. Every command is run as written by `make
guide-check`, and every output quoted below is compared with what the command prints.

The stub writes a **headline** for a support ticket: the ticket's first sentence, cut at a limit of words. The adapter
reports how many words it wrote, and a headline is better the shorter it is, a direction that no name tells the harness
and that the adapter does not declare.

Start from the project Getting started leaves (or from `evh init --store files --tutorial`, under version control).

## 1 · The adapter

A system whose code is not the bundled one names its own adapter: a file with `call_system()` and `score()`. This one
goes in `adapters/`, so the bundled adapter keeps running the systems of the other pages.

```bash
mkdir -p adapters
cat > adapters/headline.py <<'EOF'
from evaluation_harness.adapter import Result

PRIMARY_METRIC = "words_out"
METRIC_KINDS = {"words_out": "quality"}
METRIC_DESCRIPTIONS = {"words_out": "words in the headline"}
CALLS_PER_ITEM = 1


def call_system(text, params):
    words = []
    for word in text.split()[: params["words"]]:
        words.append(word)
        if word.endswith("."):
            break
    tokens_in, tokens_out = len(text.split()), len(words)
    cost = (tokens_in * params["usd_per_mtok_in"] + tokens_out * params["usd_per_mtok_out"]) / 1e6
    return Result(output=" ".join(words), tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost)


def score(output, reference):
    return {"words_out": float(len(output.split()))}
EOF
```

- `call_system(text, params)` receives one item's text and the system's `params`, and returns a `Result`. The
  harness times the call itself. The tokens and the cost are the adapter's to report: **the harness never prices a
  custom adapter's tokens**, so a `cost_usd` that is left out is recorded as unknown, not as zero. This one computes it
  from the prices its system declares.
- `score(output, reference)` returns numbers. It is called with `reference=None` when there is no reference, as
  here, so a measure that needs none (a length, a format check) is the one to start with.
- Beside them, the adapter says what its metrics are. `METRIC_KINDS` gives `words_out` the kind `quality`: ranked,
  not just shown. It says nothing about **which way** is better: `METRIC_DIRECTIONS = {"words_out": "lower"}` would, and
  a goal can, which is the next step but one. `PRIMARY_METRIC` is the measure the commands read when none is named.
  `METRIC_DESCRIPTIONS` is the sentence the catalog shows.
- `CALLS_PER_ITEM` is read by the dry run alone, to count the calls.

## 2 · Two systems, with prices

A system is a file. Its prices live in it, so a run records what it was costed at, and the adapter above reads them
from `params`. Two systems on one adapter differ in one number:

```bash
cat > data/systems/headline_6w_v1.yaml <<'EOF'
system_id: headline_6w_v1
adapter: adapters/headline.py
params: {words: 6, usd_per_mtok_in: 3.0, usd_per_mtok_out: 15.0}
EOF
cat > data/systems/headline_12w_v1.yaml <<'EOF'
system_id: headline_12w_v1
adapter: adapters/headline.py
params: {words: 12, usd_per_mtok_in: 3.0, usd_per_mtok_out: 15.0}
EOF
```

(In a `--store sqlite` project put the files with `evh data-put --path systems/<file> --file <file>`, as Getting
started does.)

## 3 · A dataset, and a goal that says which way is better

The six tickets of the kit, frozen as a dataset of their own:

```bash
evh dataset-create --dataset-id headlines_v1 --source-dir tutorial/tickets
evh dataset-materialize --dataset-id headlines_v1
```
```text
data/datasets/headlines_v1.json  (6 item(s))
data/materialized/headlines_v1  (6 item(s), all hashes verified)
```

The goal names the measure that decides and its direction. `words_out` is a measure the adapter declared only as a kind,
so the goal is where `lower` is said:

```bash
cat > data/goals/headline_short.yaml <<'EOF'
goal_id: headline_short
schema_version: "0.1"
title: Short ticket headlines
statement: A headline for the queue view, as short as it can be while still naming the problem.
status: active
context:
  audience: the person triaging the support queue
decision: Which headline length to use for the queue view.
output_contract:
  - {id: headline, format: paragraph, length: under a dozen words, language: en}
success_criteria:
  primary: {measure: words_out, direction: lower}
  min_items: 6
datasets:
  - {dataset_id: headlines_v1, role: validation}
measures:
  - {id: words_out, kind: metric, validity: unvalidated}
EOF
git add -A && git commit -qm "Tutorial 9: a headline adapter, two systems, a goal"
```

The commit keeps the tree clean: a run from a dirty tree records that its code is not identified.

## 4 · Run

`--dry-run` first: it calls nothing, and counts the calls the adapter says it makes.

```bash
evh run --system headline_6w_v1 --dataset headlines_v1 --dry-run
```
```text
  API calls   6
              1 per item, declared by the adapter (CALLS_PER_ITEM)
```

Its dollar estimate is made for a model's reply of up to `max_tokens`; for a stub it says nothing, and the run
records what the adapter reports. The runs name the goal, so each records what it was for:

```bash
evh run --system headline_6w_v1 --dataset headlines_v1 --goal headline_short
evh run --system headline_12w_v1 --dataset headlines_v1 --goal headline_short
```
```text
spent $0.001977 (the adapter's own figure, the provider sent no bill)
spent $0.002427 (the adapter's own figure, the provider sent no bill)
```

"The adapter's own figure" is the `cost_usd` of the stub's `Result`: with no bill from a provider and no
`meta["cost_source"]`, that is what the harness can say about where it came from.

## 5 · Compare

```bash
evh leaderboard headlines_v1
```
```text
dataset: headlines_v1   ranked by: words_out (lower is better)
headline_6w_v1       1     6.0000  0.000329
headline_12w_v1      1    11.0000  0.000404
```

(The rows go on to the latency, the tokens and the total cost.) The direction is the goal's, read from the runs that
name it: without it the same table would rank `words_out` higher-is-better, the name telling nothing. The paired test
reads it too:

```bash
evh pair-test headlines_v1 --a headline_6w_v1 --b headline_12w_v1
```
```text
headline_6w_v1  vs  headline_12w_v1    metric=words_out  N=6
delta (A - B)      -5.0000
items A wins       6/6 (lower is better)
sign-flip p        0.0312  (exact, all 2^6 sign patterns)
verdict            SIGNIFICANT at 0.05
```

Six items is a smoke test, as Getting started says: the p is the smallest a six-item paired test can give, and it
says only that the plumbing works. The goal's own view adds what the goal decides:

```bash
evh goal-leaderboard headline_short
```
```text
decides    words_out, lower is better
headline_6w_v1 [recommended]  6.000  6
headline_12w_v1  11.0  6  +5.000, p 0.0312, significant: worse
recommended: headline_6w_v1
```

## 6 · The catalog

Every page is a command too. The catalog builds its pages over the adapter's own metric:

```bash
evh catalog --out .build/catalog
```
```text
inspect: evh catalog-serve, then open the address it prints
```
```bash
evh metric-show words_out
```
```text
words in the headline
better       lower
kind         quality: measured against a reference or by a judge
decides      headline_short
```

The sentence is the adapter's `METRIC_DESCRIPTIONS`, the direction is the goal's and the kind is `METRIC_KINDS`'s: the
metrics page of the catalog (`.build/catalog/m/words_out.html`) shows the same.

## 7 · A call that has an effect

The stub is harmless to call twice. An adapter whose call has an effect (an agent that spends money, a deploy, a message
sent) must never be retried. It says so beside `CALLS_PER_ITEM`, and the harness calls each item once, with no retry:

```bash
echo 'CALL_ONCE = True' >> adapters/headline.py
evh run --system headline_6w_v1 --dataset headlines_v1 --dry-run
```
```text
calls each item once (the adapter declares CALL_ONCE): no retry, a failure is a failed item, and --resume
does not call a failed or in-doubt item again unless --recall-failed names them
```

`CALL_ONCE` is a fact of the adapter's code and is hashed into the fingerprint with it: a system file cannot turn it off.
The rest of what an adapter can declare (`METRIC_DIRECTIONS`, `score_run` for a measure of a whole run, `warmup`, a
catalog of your own layout) is in [INTEGRATION](../../harness/docs/INTEGRATION.md#the-one-function).
