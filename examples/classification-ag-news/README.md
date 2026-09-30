# Classifying news, 24 models and four things that are not models

One task — put a news article into one of four topics — measured across 24 hosted models
from 8 vendors, a fine-tuned 44MB classifier, a zero-shot NLI model, a hand-written rule
set, and a constant.

It is the second worked example for [`../../harness`](../../harness), and it exists
because classification breaks things the summarisation example never touched. The
interesting parts of this one are mostly about the instrument rather than the models.

---

## Get the data

**Nothing is committed.** The slice is downloaded to your machine and gitignored.

```bash
cd examples/classification-ag-news
uv sync                       # provisions its own Python 3.11 and deps
uv run fetch.py --n 200       # ~2 seconds, stdlib only, no `datasets` library
uv run fetch.py --n 20        # the dev slice, a strict subset of the 200
```

That writes texts into `../../harness/data/sources/ag_news_<n>/` and their labels into
`../../harness/data/references/gold/ag_news_<n>/`. Then freeze them:

```bash
cd ../../harness
PYTHON=../examples/classification-ag-news/.venv/bin/python make dataset-create \
    DATASET_ID=ag_news_200 ARGS='--source-dir data/sources/ag_news_200'
PYTHON=../examples/classification-ag-news/.venv/bin/python make dataset-materialize \
    DATASET_ID=ag_news_200
```

`materialize` hashes every item against the frozen `source_sha256`, so a refetch that
produces different bytes is caught rather than silently compared.

### The fetcher stratifies, and the summarisation one does not

AG News's test split is not shuffled. Paging from offset 0, the way the CNN/DailyMail
fetcher does, gives this:

```
first  20: {'Business': 1, 'Sci/Tech': 19}
first 200: {'Business': 29, 'Sci/Tech': 57, 'Sports': 53, 'World': 61}
```

A 20-item slice that is 95% one class is not a hard eval, it is a broken one — a constant
answer scores 0.95 and the table ranks constants above models. So `fetch.py` takes n/4 per
class in split order: deterministic without a seed, and nested, so the 20-item slice stays
a strict subset of the 200 and `holdout_significance --exclude-dataset` still means what
it says.

Balanced by construction means the floor is known exactly, not approximately: a constant
answer scores **0.2500**. The `ag_constant` arm exists to check that it does. Any other
value would mean the slice is unbalanced or the scorer is wrong, and no other row in the
table could be trusted.

### Licence — weaker than the summarisation example's

The HuggingFace dataset card lists AG News as **`unknown`**. The corpus's own description
says it is *"provided by the academic community for research purposes … and any other
non-commercial activity."* That is a statement of intent by the people who assembled it,
not a grant of rights.

This repo ships a download recipe and redistributes nothing, which is the same posture the
summarisation example takes with CNN/DailyMail. The difference is that CNN/DailyMail
carried an explicit apache-2.0 grant behind it and this does not. **Do not read permission
into the fact that this example exists** — anyone wanting to use AG News commercially has
to resolve that themselves.

### A caveat that caps what any number here means

Many AG News texts carry their syndication tag inline: `(AP)`, `(Reuters)`, `(SPACE.com)`.
Those tags correlate with the label — SPACE.com is Sci/Tech essentially always — so an arm
can score well by reading the byline rather than the article. It affects every arm equally,
so the comparison stands, but it caps how much "understanding" any accuracy figure here
can be said to demonstrate.

---

## Run it

```bash
cd ../../harness
PY=../examples/classification-ag-news/.venv/bin/python
CFG=../examples/classification-ag-news/configs

$PY scripts/experiment_run.py --config $CFG/arm_deepseek_m_n200.yaml --dry-run
$PY scripts/experiment_run.py --config $CFG/arm_deepseek_m_n200.yaml

$PY scripts/leaderboard.py --dataset-id ag_news_200
$PY scripts/classification_report.py --dataset-id ag_news_200
$PY scripts/classification_report.py --dataset-id ag_news_200 --arm ag_keyword_n200_v1
```

The hosted arms need a LiteLLM proxy; copy `../../harness/.env.example` to `.env` and
point it at yours. The four free arms need nothing, and two of them need no model either.

**Cost.** Billed, a 200-item hosted arm ranges from $0.0014 to $0.1750 and all 28 come
to **$0.58** — well under a dollar — two orders of magnitude cheaper than the summarisation sweep, because the
answer is one word. That is why no arm is selected on its dev score: selecting would save
nothing and buy a bias.

### Dev and measurement slices

`ag_news_20` is the **dev** slice. Prompt and parser may be tuned against it. `ag_news_200`
is where the claim is made, and because the 20 are nested inside the 200, the honest read
is on the 180 it does not contain:

```bash
make holdout DATASET_ID=ag_news_200 EXCLUDE=ag_news_20
```

Tuning on the set you then report is the winner's curse. The summarisation study watched a
0.0737 lead become 0.00008 exactly that way, on arms selected from a 20-item slice.

---

## What classification breaks that summarisation did not

**1. The parser is part of the system under test.** A model answering `Sports`, `Sports.`,
`**Sports**` or `This article is about sports` is right or wrong depending entirely on who
wrote `_parse_label`. In summarisation the prompt was fingerprinted because it shapes the
output; here the parser has to be, for the same reason. It is — `parser_sha256` sits beside
`prompt_sha256` on every arm, including the local ones that never touch it, because the
question it answers is "would this number change if the parser changed?" and an identical
hash across both kinds is what makes "no" checkable rather than assumed.

**2. The per-item score is binary.** `correct` is 1.0 or 0.0, so its mean is accuracy —
fine for a mean, awkward for the statistics. On most items most arms simply agree, so
within-item ranks are mostly ties and the paired tests have far less to work with than
continuous ROUGE gave them. Read the significance block here with more suspicion than the
summarisation one, not less.

**3. Macro-F1 cannot be a per-item metric.** Accuracy can: score each item, take the mean.
F1 needs a confusion matrix, which is not a property of any single item, so the harness's
average-the-per-item-metric shape cannot express it. The workaround people reach for — a
per-item pseudo-F1 that averages to something F1-shaped — does not equal macro-F1, has no
interpretation, and would sit in the leaderboard looking exactly as authoritative as the
real thing.

So accuracy stays the per-item metric and the ranking metric, every prediction is recorded
in `meta.predicted`, and `scripts/classification_report.py` builds the confusion matrix,
macro-F1 and per-class precision/recall from the stored predictions. **This is a real
limitation of the harness, written down rather than papered over.**

**4. The label set is the task.** Add a class, rename `Sci/Tech`, or reorder the list, and
the prompt, the zero-shot hypotheses, the parser's alias table and a fine-tuned head's
positional mapping all change meaning at once. `labels_sha256` is on every arm so that
"these two runs were asked the same question" is checkable.

**5. Confidence exists.** A classifier reports one; a summariser does not. It is recorded
as `confidence` and marked descriptive — a confident wrong answer is worse than a hesitant
one, so it is not quality — but it is the input to a calibration question that no
summarisation metric could have asked.

---

## The arms

| arm | what it is | cost |
| --- | --- | --- |
| 24 hosted | 8 vendors × small/mid/large, same aliases and prices as the summarisation example | $0.0014–$0.1750 per 200, billed |
| `bert_mini` | 44MB BERT fine-tuned on AG News | 0 |
| `bart_mnli` | `bart-large-mnli`, zero-shot via NLI, no task fine-tune | 0 |
| `keyword` | ~20 hand-written regex rules, first match wins, default World | 0 |
| `constant` | always answers World | 0 |

`bart_mnli` is the control the summarisation study could not run. That study ended with
BART tied for first against 24 hosted models, and the objection was that it had been
fine-tuned on exactly that corpus. This is the same architecture family with **no**
exposure to AG News, run beside a model that was fine-tuned on it — so "BART is good" and
"that checkpoint saw the test distribution" stop being the same hypothesis.

`keyword` is the one with a life outside this repo. A rule-based classifier of exactly that
shape — ordered patterns, a catch-all default — runs in production in a sibling project and
has never been measured against anything. Its rules here were written from the four label
names and general knowledge of news desks, **not** by reading the slice and patching what
it got wrong. That distinction is the difference between a baseline and a model fitted on
the eval set, and it is not checkable after the fact, so it is recorded before the numbers
exist.

---

## Results

See [`../../research/`](../../research/).
