# Runbook — from raw inputs to a defensible baseline

Follow this top to bottom: every step, with the reasoning attached, as `evh` commands in a
project that pins the package. You should not need to open a script. In a checkout of this
repository each command is also a `make` target (`make pair-test DATASET_ID=… A=… B=…`, flags
through `ARGS="…"`); `make help` lists them.

New here? **[Getting started](../../docs/GUIDE.md)** walks the loop once, offline, with the real
output of every command, and the [tutorials](../../docs/GUIDE.md#where-to-go-next) take it
further. This page is the reference for each step.

## Every command

| step | command |
|---|---|
| start a project | `evh init [--tutorial]` |
| what is configured | `evh env-check` |
| freeze | `evh dataset-create --dataset-id … --source-dir …` |
| a new version | `evh dataset-create --dataset-id …_v2 --source-dir … --from …_v1` |
| fields on an existing dataset | `evh dataset-create --dataset-id … --update-fields --fieldset … --fields …` |
| materialize | `evh dataset-materialize --dataset-id …` |
| a model's labels (a run's outputs) | `evh label-from-run --run <run_id> --set … [--not-redistributed]` |
| a person's labels | `evh label-sheet --dataset-id … --out sheet.csv` · `evh label-import sheet.csv --dataset-id … --set … --by …` (or a folder of `<item_id>.txt`) |
| the label sets | `evh labels [--dataset-id …]` |
| a reference (labels you promote) | `evh reference-promote --dataset-id … --labels … --tier gold\|silver --reason "…" --by …` |
| gold a script builds, promoted | `evh reference-manifest --reference-id gold/… --source … --labelled-by … --reason "…" --by …` |
| score against labels | `evh rescore --dataset-id … --labels …` · `evh run --config … --labels …` |
| cost before spending | `evh run --config … --dry-run` |
| measure (+ own noise) | `evh run --config … --repeat 3` |
| many arms | `evh sweep --configs "data/configs/arm_*.yaml"` |
| list runs | `evh runs-list` |
| rank, with the test | `evh leaderboard --dataset-id …` |
| two runs | `evh run-compare --baseline … --candidate … --noise …` |
| a pre-named pair | `evh pair-test --dataset-id … --a … --b …` (or `--round rN`: A its leader, B the baseline it started from; a leader chosen from the table is corrected for the arms in play). A `hypothesis:` committed in A's config before the run is what makes the pair "named in advance" (§4) |
| a winner claim | `evh family-test --dataset-id … --a … --against …` |
| re-score, $0 | `evh rescore --dataset-id … [--reference-id gold/…] --out …` |
| re-measure with a judge (optional) | `evh judge-score --dataset-id … --scorer … [--dry-run]` |
| read the judged runs | `EVAL_RUNS_DIR=data/runs-judged/<scorer> evh leaderboard --dataset-id …` |
| is silver good enough | `evh silver-calibrate --dataset-id …` |
| how many items | `evh rank-stability --dataset-id …` |
| pilot-slice-free result | `evh holdout --dataset-id … --exclude-dataset …` |
| scores made elsewhere | `evh import-run --dataset-id … --config-id … --scores … --scorer-file …` |
| billed cost | `evh cost-report` |
| baseline | `evh run-promote --run … --reason "…"` · `evh runs-list --baselines` |
| what it is for | `data/goals/<goal_id>.yaml` (every field: [§4c](#4c-the-goal-file-field-by-field)), and `goal:` on each config |
| rounds (optional) | `evh round-open` · `evh round-retire` · `evh round-close` · `evh rounds --goal …` |
| browse and inspect | `evh catalog` · `evh catalog-serve` · `evh dataset-profile` · `evh dataset-items` |
| ask from an agent | `evh mcp` |
| the same, in the terminal | `evh overview [--period P]` · `evh activity` · `evh datasets` · `evh arms` (`--by …`, `--configs`, `--arm …`) · `evh references` · `evh metrics --metric …` · `evh goals` · `evh goals --goal G [--arms PATTERN] [--top N]` (a goal with many arms: only the arms matching, or the first N, always with the baseline, the leader and the recommended arm; each arm's paired test against the leader) · `evh search …` · `evh inspect --runs …` (`--analysis`, `--item …`) · `evh inspect --sheet --dataset-id … --runs …`; every list takes `--period P` |
| consistency | `evh validate` |
| does the installed harness work here | `evh self-test` |
| keep a production system's records | `evh capture --importer jsonl --query '{"path": "export.jsonl"}' --capture c1` · `evh captures` ([§15](#15-datasets-from-production-the-capture-lane)) |
| test an importer | `evh importer-check path/to/importer.py:Importer --query …` |
| scrub a capture | `evh capture-scrub c1 --command "python scrub.py {records}"` |
| a dataset from a capture | `evh dataset-from-capture c1 --dataset-id … [--where F:V] [--one-per F] [--tag K=V]` |
| labels from what happened afterwards | `evh label-from-capture --dataset-id … --capture c1 --map rules.yaml --set …` |
| validation and test | `evh dataset-split … --test 0.3 --seed 7 [--key F]` |
| production's own decisions as an arm | `evh arm-from-capture --dataset-id … --capture c1 --as production_v1 [--like CONFIG]` ([§15b](#15b-evaluating-what-production-did)) |
| where arms decided differently | `evh inspect --runs A,B --disagree` |
| the sheet: every item, every arm's output and scores, the labels, the winner, the signals | `evh inspect --sheet --dataset-id … --runs A,B [--wrong-against SET] [--new-vs V] [--csv FILE [--fill label\|pick\|scores]]` |
| how two per-item scores relate, by a recorded field (a gate that saved a false dismissal, one that cost a false alarm) | `evh inspect --runs A --crosstab M1,M2 [--group _meta.gates [--group-match REGEX]] [--where F:V]` ([§14](#14-browse-the-catalog-and-the-inspector)) |
| why items flipped: each run's whole output beside the reference, many items at once | `evh inspect --runs A,B --items-out [--disagree] [--where F:V] [--max-chars N] --json` ([§14](#14-browse-the-catalog-and-the-inspector)) |
| a result with and without a set of items | `evh pair-test … --items FILE` (only the ids in the file, one per line; the rest is a second file, or `--exclude-dataset D` when the set is a dataset) · `evh inspect --runs A,B --where F:V` (the items with that field value; a boolean or choice field marking the set) |
| a sheet filled elsewhere, read back | `evh sheet-import sheet.csv --dataset-id … --by WHO [--set S \| --scorer S]` |
| pick for the next version | `evh pick --dataset-id … --item … --for V` · `evh picks [--for V]` |
| the next version of a dataset | `evh dataset-extend V1 --dataset-id V2 --picks` (or `--pick ITEM …`) |
| what production must match | `evh deploy-sheet --config ARM [--capture C]` |

---

## 0. Prove it works before you touch it

In a project that pins the package:

```bash
evh self-test
```

That runs the paired test's own suite and the tutorial end to end in a scratch folder,
offline and at $0. (In a checkout of the harness, `make demo` freezes a dataset from the
bundled samples, runs one arm three times and validates the tree.) No API key. If it
works, the harness is wired correctly and anything that breaks later is your change.

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
evh dataset-create --dataset-id my_v1 --source-dir data/sources/my_v1
evh dataset-create --dataset-id my_smoke_v1 --source-dir data/sources/my_v1 --limit 5   # a fast cut
```

This writes `data/datasets/my_v1.json`: the item list plus a **sha256 per item**.

The `dataset_id` is the comparison contract. Every run records it, and
`run-compare` refuses to compare across two different ones. Name it for what it
*is* (`support_tickets_2026q1_v1`), not for what you were doing at the time
(`test2`).

**A new version** of a dataset names the one it came from: `--from my_v1` on `my_v2` records
its parent and the item ids it adds, removes and changes (`derived_from` in the dataset file).
`evh datasets --dataset-id my_v2` prints the lineage, the catalog links the versions both ways,
and `validate` V2 fails a version whose parent is gone.

**What you know about each item goes in fields** (ADR-0003). Declare them once in a
field set, `data/fields/<fieldset_id>.yaml` (`schemas/fieldset.schema.json`): a name and
a type for each (`text`, `number`, `integer`, `boolean`, `date`, `duration`, `url`, or
`choice` with its `values`), optionally `required` and `public`. Then attach the values,
one row per `item_id`, from a CSV or JSONL:

```bash
evh dataset-create --dataset-id my_v1 --source-dir data/sources/my_v1 --fieldset tickets --fields fields.csv
evh dataset-create --dataset-id my_v1 --update-fields --fields fixes.csv     # later
```

A column the field set does not declare, a value of the wrong type or outside a
choice, and a required field left empty are refused. With `--update-fields`, a value in
the file replaces that value, an empty cell clears it, and every column and item the file
leaves out is kept. Fields are not the dataset's
identity: runs hash the items' bytes, so correcting a field invalidates no run, and
`fields_sha256` records that the fields changed. `--update-fields --fieldset tickets` attaches
a field set to a dataset that had none. `evh validate` (V15) checks every
value. The catalog summarises a field's values only when it is `public`; the local
inspector shows them all, filters a comparison by them, and breaks it down by a
`choice` or `boolean` field.

**Items that live at a URL** come in through a manifest, one row per item:
`item_id`, `source_url` and `source_sha256` (leave the hash empty and the bytes are
fetched and pinned now), plus any field columns:

```bash
evh dataset-create --dataset-id episodes_v1 --manifest items.csv --fieldset episodes
```

`evh dataset-materialize` downloads each one into `.cache/items/` and refuses bytes
that hash to anything else, the same failure as a changed file under `sources/`. A
transient failure (429, 5xx, a timeout) is retried like a provider call. A host that needs
a header gets it from `EVAL_FETCH_HEADERS` in `.env`, a JSON object
`{"media.example.com": {"Authorization": "Bearer …"}}`: only that host receives it, a
redirect to another host does not, and it is never written into a dataset.

---

## 3. Materialize

```bash
evh dataset-materialize --dataset-id my_v1
```

Copies the items into `data/materialized/<dataset_id>/` and **re-verifies every
hash**. If a source changed since the freeze, this fails loudly rather than
quietly measuring different bytes than the dataset claims.

`materialized/` is derived. Delete it any time; `evh dataset-materialize`
rebuilds it. If something in there cannot be rebuilt, it is in the wrong place.

---

## 4. Point the harness at your system

Write **one function**, `call_system()`, in `adapter.py` at the project root. An arm whose
config names no `adapter:` uses it (and records `adapter.py`); without one, the adapter
bundled with the harness runs. A project with several tasks names one per arm,
`adapter: adapters/ner.py`, relative to the config or the project:

```python
from evaluation_harness.adapter import Result

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

`provider: anthropic` is one choice: the bundled providers also call OpenAI or any
OpenAI-compatible endpoint, OpenRouter and a LiteLLM proxy, each with your own key in `.env`.
Which variable each reads: [tutorial 2](../../docs/tutorials/2-hosted-llm.md#1-choose-a-provider).
Full detail in [INTEGRATION.md](INTEGRATION.md).

**A hypothesis, written before the run (optional).** A paired test is valid uncorrected only for a
comparison named before the results were read. When an arm is a change you expect to matter, write the
prediction into its config, beside the change, and commit it before `evh run`:

```yaml
hypothesis:
  against: my_config_v1          # the config_id it is compared with (must exist)
  measure: false_alarm           # one of the arm's metrics
  direction: better              # better | worse | no-worse (not significantly worse)
  statement: "the shorter prompt lowers false alarms"
  items: data/expected_flips.txt # optional: a file of item ids expected to flip
```

`evh validate` (V20) and `evh run` refuse a block with a missing key, an unknown direction, an `against`
that is no config of the project or a `measure` that is none of the arm's metrics, in words, before
anything is spent. The run copies the block into `metrics.json` (`hypothesis`) with
`hypothesis_in_advance`: `named: true` when the commit that last changed the block is an ancestor of the
run's build commit and was made before the run started, `false` when it is in no such commit, `null` (not
determinable) outside git, for a build that is not a git commit (`EVAL_BUILD_REF`) and on a dirty tree.
It is not part of the fingerprint: a hypothesis does not change what was measured. `evh pair-test --a A
--b B` prints it when A's run carries a hypothesis against B on the tested metric: `named in advance: yes
(committed <sha> before the run)`, `no` or `not determinable`, and whether the result agrees with the
stated direction (`yes`, `no`, `not shown`); a hypothesis found in A's config that its run does not carry
reads `no` (added after the run). `evh goals --goal G` shows it in a `hypothesis` column beside the arm.
[ADR-0025](../../docs/adr/ADR-0025-a-hypothesis-lives-in-the-arm-config.md).

**What a run records as its cost.** Each call's `cost_usd` is the provider's bill when the
response carries one (`usage.cost`), and otherwise the config's price table, tokens ×
`usd_per_mtok_in` / `usd_per_mtok_out`. With no price table and no bill the cost is unknown, not
zero. Per provider:

| `provider:` | what the run records |
|---|---|
| `openrouter` | the bill: the provider asks OpenRouter for it on every call |
| `litellm` | the proxy's bill, when the proxy passes `usage.cost` through (the 2026-10-24 scenario's proxy did); else the price table |
| `openai` | the price table (OpenAI's API reports tokens, not a cost); an OpenAI-compatible endpoint that returns `usage.cost` is billed |
| `anthropic` | the price table |
| `echo`, your own adapter | what the adapter returns as `cost_usd` (tutorial 1's local model returns 0.0) |

The bill is the measurement and the price table a guess: in this repository's runs they differed
by 0.67× to 3.76× per arm. When a response reported a bill, the bundled adapter also keeps it in
the item's `_meta.usage.cost` (in `predictions.jsonl`), so an item with that key was billed and
one without it was priced from the table. `evh cost-report` sets each run's bill, summed from
`_meta.usage.cost`, against its recorded cost, and lists apart the runs with no bill there. Only
runs made with harness 0.4.0 from commit `f0c2ed3c` on carry the key: older runs of the bundled
adapter read in `cost-report` as price table only, even where their `cost_usd` was a bill. Judges
follow the same rule (§12); their verdicts keep `usage`.

---

## 4b. Author ground truth — you cannot score quality without it

A **label** says what is right for one item, and who said it: a `person`, a `model` or a `rule`. Labels
come in **sets**, never edited (a correction is a new set), under `data/labels/<dataset>/<set>/`, and
follow an item by its bytes into any dataset holding it. A **reference** is labels promoted on purpose,
with a reason, at the tier you choose: no rule ties the tier to the source, and the reference records
both ([ADR-0022](../../docs/adr/ADR-0022-references-are-promoted-labels.md)).

Most projects have none. Run the best model you have as an arm (an expensive one you would
not run in production is the usual choice), read its results, take its outputs as a model's labels,
and promote them:

```bash
evh run --config data/configs/best_model.yaml
evh label-from-run --run <that run_id> --set best_v1
evh reference-promote --dataset-id my_v1 --labels best_v1 --tier silver \
    --reason "The best system we have ranks the rest until a person writes gold." --by <you>
```

Promoted as **silver**: a model's answers, consistent rather than correct, enough to rank
arms against each other; not a claim about truth. `label-from-run` calls nothing, and the set names
the run, config, fingerprint and build it came from. It refuses a run from a dirty tree or of an
unknown build (as `run-promote` does), an unfinished or derived run, and an empty output or one that
stopped at `max_tokens` (raise `max_tokens` in a new config_id; `--allow-cut-off` for outputs that end
at the cap by design). The reference records which set it was promoted from, by whom, when and why.
Commit both before the next run: an uncommitted reference makes every later run dirty.

When the texts may not be redistributed (the run's outputs quote a corpus you may not publish),
add `--not-redistributed`: the set's directory gets a `.gitignore` for its texts, and `labels.json`
records that and the command that rebuilds them; run on a checkout with `labels.json` alone, that
command writes the texts from the run again, checks them against the set's checksums (it refuses,
writing nothing, if the run's outputs changed since). A reference promoted from it is kept out of git
too, and the same promotion rebuilds its texts from the set.

Arms can be scored against a label set without promoting it, `evh rescore --dataset-id my_v1 --labels
best_v1` (or `evh run --labels`): the runs land beside the others, in
`data/runs-labels-<dataset>-<set>/`, and every view names the set by its source, never with a tier.

Scored against silver, the arm that wrote it is graded against its own outputs: the leaderboard
marks its row (`arm *`) and leaves it out of the ordering test and the frontier ("The ordering
test and the frontier leave out <config> (it wrote the reference)"): it is the yardstick, not a
contender. The others are measured by how close they come to it, the usual way to choose a
cheaper system: pay for the expensive one once, then chase it.

**Gold** is a person's labels promoted at gold: label the items in a sheet (`evh label-sheet
--dataset-id my_v1 --out sheet.csv`, `--propose best_v1 --items all` to start from the model's
answers, `yes` taking one; where more than one answer is right, the others go in `also right`, separated by `|`),
or write one `<item_id>.txt` per item in a folder (`{"accept": ["escalate", "file"]}` for several), then `evh label-import`
it as a person's set and promote it with `--tier gold`. The sheet is CSV that Excel opens as it is (UTF-8 with
the mark Excel needs); save it back as CSV, `,` or `;` both read. `--choices file,dismiss,escalate` writes the
allowed answers into the label column's header, and the import refuses any other, naming its rows. Gold always wins over silver for new runs. Runs made before the gold set existed are re-scored against it for $0:
`evh rescore --dataset-id my_v1 --reference-id gold/my_v1 --out data/runs-gold`.

Gold that a script builds (a dataset's own labels, fetched from where it is published) is promoted where the
script puts it, its manifest recording the promotion as `reference-promote` does: whose labels they are, how they
are built, why and who said so, and the checksum of every item's text:
`evh reference-manifest --reference-id gold/my_v1 --source scripts/fetch.py --labelled-by "the dataset's authors"
--reason "…" --by <you>` (`--kind model` or `rule` when they are not a person's). Commit the
manifest even when the texts may not be redistributed (`--not-redistributed`): `evh validate`
(V16) then checks any rebuilt copy against it, and the catalog lists the reference as fetched.
`reference-promote` writes the manifest of the references it makes. Texts copied into
`data/references/<tier>/<id>/` with no manifest fail `validate` (V16): nothing says where they came from. Import
them as labels where they are and promote them (`evh label-import data/references/<tier>/<id> …`, then
`evh reference-promote`): the promotion adopts the folder, its texts being the labels'.

Every later run is scored against these automatically and records which tier it
used. Ten items is enough to rank four arms; keep the first pass cheap.

---

## 4c. The goal file, field by field

A goal says what the evaluation is for ([CONCEPTS](CONCEPTS.md#a-goal-says-what-the-evaluation-is-for)).
It is optional: one YAML file per goal, `data/goals/<goal_id>.yaml`, and each config names it
with `goal: <goal_id>` (every run and baseline then carries it). The schema is
[`goal.schema.json`](../schemas/goal.schema.json); `evh validate` checks every goal against it
(V1, V14). A goal for a classifier:

```yaml
# data/goals/intent_routing.yaml
goal_id: intent_routing
schema_version: "0.1"
title: Route customer messages by intent
statement: Label each customer message with its intent, so it reaches the right queue without a person reading it first.
status: active
context:
  audience: the support team's routing rules
decision: Which classifier routes the inbox.
output_contract:
  - {id: label, format: label, structure: "label: <intent> / reason: <one sentence>", language: en}
success_criteria:
  primary: {measure: accuracy, direction: higher}
  min_items: 30
datasets:
  - {dataset_id: intents_v1, role: validation, notes: "32 hand-written messages, a few between two intents"}
references:
  - {reference_id: gold/intents_v1, tier: gold, format: label}
measures:
  - {id: accuracy, kind: metric, validity: unvalidated}
```

Required: `goal_id`, `title`, `statement`, `decision`, `success_criteria` (with `primary`) and
`datasets`. Where the schema gives a field no fixed values it is free text, and the table says
what reads it. A project may add fields of its own; the harness ignores them.

| field | allowed values | what reads it |
|---|---|---|
| `goal_id` | lowercase letters, digits and `_`, starting with a letter or digit; **equals the file name** | V14 fails a file whose `goal_id` is not its name. Permanent: a materially different purpose is a new goal |
| `schema_version` | any string (`"0.1"`) | nothing |
| `title` | any string | the goal page's heading, `evh goals` |
| `statement` | one sentence, "X for Y so that Z" | the goal page, `evh goals --goal` |
| `status` | `active`, `draft`, `exploratory`, `dormant` or `superseded` | shown on the goal page |
| `superseded_by` | the `goal_id` that replaces this one | nothing (for the reader) |
| `context.audience`, `context.usage` | any string | `audience` is shown on the goal page |
| `decision` | the decision an answer informs | the goal page and `evh goals --goal` lead with it |
| `output_contract[]` | a list of shapes, each `{format}` (required) plus optional `id`, `length`, `structure`, `language` | A config may declare `format:` (any non-empty string); when the goal has a contract, that format must be one of its `format`s (V14 fails it, and the goal page flags the arm "format f not in the contract"). `format` is your own word for a shape (`paragraph`, `label`, `json`): the harness has no list of them. A config without `format:` is not checked |
| `success_criteria.primary.measure` | a per-item metric as the runs record it (`rouge_l`, `accuracy`, `overlap_f1`) | the goal page, `evh goals --goal`, `evh rounds` and `inspect --round` read the arms on it; an arm that does not record it is not listed (a judged arm is shown in its judge's group, on the judge's score) |
| `success_criteria.primary.direction` | `higher`, `lower` or `non_inferior` | `higher`/`lower` rank the arms. `non_inferior` is a guard (no significant drop against a baseline) and ranks nothing. V14 fails a direction that contradicts what the runs record, or `higher` on a cost, latency or token count |
| `success_criteria.primary.threshold` | any value | shown beside the measure on the goal page |
| `success_criteria.min_items` | an integer, at least 1 | The fewest items a winner-picking comparison may rest on: an arm with fewer is flagged "n k < min_items m" on the goal page and is never a group's leader; `evh validate` notes a goal dataset smaller than it (a note, not a failure) |
| `success_criteria.axes` | a map of name → `{measure, direction, stat, limit, margin, role, unit, note}`, all optional. `cost` (`cost_usd`, mean, tokens shown beside it) and `speed` (`latency_ms`, p95) are built in and need no entry; `quality` takes only a `limit`, a `margin` and a `note` (its measure and direction are the primary's), and `margin` belongs to quality alone; any other name is the project's own axis, a per-item metric its runs record (`measure` defaults to the name, `direction` to the adapter's `METRIC_DIRECTIONS`, else `higher`, `stat` to `mean`). `role: ignore` drops an axis. `limit: baseline` in place of a number: an arm is out when the paired test finds it worse than the group's promoted baseline on that axis (p < 0.05, each arm on its own, not corrected across the arms; RFC-022); with no baseline promoted, no limit applies and the decision says so | The goal's decision ([ADR-0006](../../docs/adr/ADR-0006-goal-axes-and-strategies.md)): an arm past a `limit` is out, with the reason; `margin` (default 2% of the leader's mean) is how close an arm not significantly different from the leader must be to count as a contender under `balanced`. The goal page and `evh goals --goal` show a column per axis; V14 refuses an unknown key in an entry |
| `success_criteria.strategy` | `balanced` (the default), `quality_first` or `frugal` | Who the contenders are beside the quality leader: `balanced` not significantly different by the paired test AND within the margin; `quality_first` the same quality only; `frugal` anything not significantly different |
| `success_criteria.tie_break` | a list of axis names, default `[cost, speed]`; `quality` may be one | Among the contenders, the axes that pick, in order (`[cost, quality]`: the cheapest, then the best of the equally cheap). V14 fails a name the goal does not weigh |
| `success_criteria.guardrails[]` | `{name, rule}` (required), `source` | Rules in words that no number checks: a "guardrails" row on the goal page, a line each in `evh goals --goal`; never computed |
| `success_criteria.secondary` | removed in 0.4.0 | V14 fails a goal that still has it: move its entries to `axes` (UPGRADING) |
| `datasets[]` | `{dataset_id}` (required), `role`, `decides` (false: the goal never decides on it), `notes`. An empty list is a goal checked by a gate rather than measured on a dataset | Each dataset gets a section on the goal page and in `evh goals --goal`. `role` is free text (`validation`, `test`, `pilot`, `smoke`, `generalization`), shown beside the dataset. `decides: false` makes a dataset one the goal never decides on: its groups keep their leader but recommend nothing, and the home page's glance leaves it out. `notes` is shown under it |
| `references[]` | `{reference_id, tier, format}`, all strings; `tier` is `gold` or `silver` by convention, `format` your word for the reference text's shape (`label` for a bare-label gold) | nothing: which reference an arm is scored against comes from its run, not from the goal |
| `measures[]` | `{id, kind, validity}`, all strings; `validity` says how far the measure is trusted (`unvalidated`, or what it was validated against) | nothing (for the reader) |
| `links[]` | `{url, note}` | nothing (for the reader) |

`data/goals/policy.yaml` is not a goal: `required_from: YYYY-MM-DD` makes every run created on or
after that date name a goal (V14). Without it, goals are optional.

---

## 5. Measure the arm's own noise — **before** you compare anything

```bash
evh run --config data/configs/my_config.yaml --repeat 3
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
Write the number down; you need it in step 7. Cost and speed have a spread too, and their rows
say what they are (`latency_ms   spread=0.003833   speed, not a quality metric`): they move
with the tokens and the machine, and say nothing about whether the arm is deterministic.

When the command spent anything it prints the total over every run it wrote, so nobody adds
up `total_cost_usd` by hand across repeats (§4 says where the number comes from):

```text
spent $0.001063 (price table x tokens, or the provider's bill where it sends one)
```

---

## 6. Run the arms you want to compare

```bash
evh run --config data/configs/arm_a.yaml
evh run --config data/configs/arm_b.yaml
evh runs-list
```

A run is only attributable if it knows its build. `runs-list` marks runs from a
dirty tree with `*` — their `build.ref` does not describe what actually ran.
**Commit before you measure** — dataset, configs, references — so the runs you keep are
clean the first time. Re-running an arm into `data/runs` after the fact leaves two
measurements of one config, which `evh validate` refuses (V8); explore in a scratch
directory instead (`EVAL_RUNS_DIR=data/runs-smoke`).

**Where runs go.** Measured runs go in `data/runs`: leave `EVAL_RUNS_DIR` unset, on every
machine, so a run made on a laptop and one made on a GPU box land in the same place. An
ignored run is not committed, so a fresh clone, CI and the published catalog never see it.
Two kinds of directory sit beside `data/runs` on purpose:

- **throwaway** (`data/runs-smoke*`, `data/runs-tune*`): smoke passes and sweeps, never committed;
- **derived sets** (`data/runs-repeats`, `data/runs-rescored/<scorer>/<source>`, `data/runs-judged/<scorer>` …):
  re-scored or repeated runs that keep the measured runs' `config_id`s, so they cannot share
  `data/runs` (V8).

The `.gitignore` `evh init` writes ignores only the throwaway directories, so a project commits
its derived sets like its measured runs. This repository's own `.gitignore` is stricter: it
ignores every `data/runs-*` directory and re-allows each derived set by name.

`evh run` and `rescore` print a `WARNING` when they write to a directory git ignores
that is neither, or to one outside the project's data, and `evh validate` notes any ignored
directory that already holds finished runs. The catalog, `evh goals` and `evh arms` read only
the directories git keeps, so what you see locally is what a clone, CI and the published
catalog see: a smoke pass in `data/runs-smoke*` never shows up as a result.

**When the scoring changes** (RFC-022), develop it, then apply it one of two ways:

```bash
evh score-preview --goal my_goal                                    # what it would move; writes nothing
evh rescore --goal my_goal --round r1 --why "what changed, and why"  # re-score a round with it, $0
evh round-open --goal my_goal --dataset my_v1 --from r1 --keep all \
  --scoring "what changed, and why"                                  # or adopt it from the next round
```

Re-scores land in `data/runs-rescored/<scorer>/<source>/`, the place the tool designates, so a new scorer never
needs a directory of its own (or a `.gitignore` block). A re-score stands in for the run it re-read: the goal
pages, `evh goals`, the rounds and the recommendation read one row per arm, from its latest re-score against the
same reference, and say how many arms they read that way. The measured run keeps its own page, and says there, on
the arms page and in `evh arms` that the goals read its re-score. A round records the scorer it is judged by, and
`evh rounds` shows it with each scoring change. A goal whose first round was run as plain runs gets one with
`evh round-open --goal G --dataset D --adopt`.

`evh run` warns, naming the items, when outputs stop at `max_tokens` (the provider's
`finish_reason`, or tokens out reaching the cap): they are scored as if complete. The harness
times every call (`latency_ms`) unless the adapter reports its own.

### When a run dies partway: `--resume`

A sweep that is interrupted — a crash, a 429 that outlasts the retries, or the
`EVAL_MAX_COST_USD` cap — leaves its finished items on disk. Outputs are written
**as each item is produced**, so what you already paid for survives.

```bash
evh run --config data/configs/arm_a.yaml --resume arm_a_v1_20260929T101500Z
```

The run id is the directory under `data/runs/`. A run that stops, whatever the cause, prints
which run it was, after how many items, and the exact `--resume` command; or delete the
directory (until one or the other, `validate` fails V7 on it). A resumed pass **re-reads every finished output and scores
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

  A directory with neither file is refused outright, as is one whose rows were not written
  by this version of the harness.

Exit codes: `0` complete, `2` stopped early by the cost cap with usable partial
results, `1` nothing was measured at all.

---

## 7. Compare, with the noise floor you measured

```bash
evh run-compare --baseline <run_id> --candidate <run_id> --noise 0.043888
```

Quality, cost and speed appear side by side — `overlap_f1` next to
`total_cost_usd` and `latency_ms`. "Better" and "better and 4x the price" are
different findings, and only one of them is a decision.

Read the verdict column, not the delta. A `+0.02` that is below your measured
spread is **noise**, and the tool says so. Without `--noise` it nags, because a
delta judged against nothing is not evidence.

It refuses outright if the two runs used different `dataset_id`s.

---

## 7b. The analysis tools

Sections 0–7 walk one arm from data to comparison. Everything that turns a pile of runs
into a *finding* is a separate verb: these are the tools behind the numbers in `research/`.

| verb | answers |
|---|---|
| `evh leaderboard --dataset-id …` | how do all the arms rank, on every metric at once |
| `evh family-test --dataset-id … --a … --against …` | does arm A differ significantly from a **pre-declared family**, Holm step-down. This is what every significance claim in the reports rests on |
| `evh pair-test --dataset-id … --a … --b …` | are these two arms different — paired, per item. Uncorrected, so only legitimate for a pair named in advance: the arm's `hypothesis:` records that it was (§4). With `--round` and no `--a`, A is the round's leader, chosen from the table, so the test is Bonferroni-corrected for the arms in play (`--family N` overrides; below 1 is refused) |
| `evh holdout --dataset-id … --exclude-dataset …` | does the result survive on the items the pilot slice never contained |
| `evh rank-stability --dataset-id …` | how many items before the ordering stops moving — measured, not assumed from a power table |
| `evh bootstrap-test --dataset-id … --a … --against …` | a percentile interval for a corpus-level metric that has no per-item value |
| `evh rescore --dataset-id … --out …` | recompute every score from stored outputs under the current scorer — or, with `--reference-id gold/…`, against a reference set that arrived later. **$0, no API calls** |
| `evh cost-report` | what each arm actually cost, from the provider's bill (`_meta.usage.cost` in its predictions) against the cost the run recorded; runs with no bill there are listed apart (§4) |
| `evh silver-calibrate --dataset-id …` | does a model-authored reference rank arms the way the trusted one does |

`pair-test` and `family-test` count the exact p over all 2^n sign patterns when a pair shares 30
items or fewer, and estimate it from 20,000 permutations above that; both say which (`family-test`:
"p: exact, over all 2^6 sign patterns", or "p: a seeded estimate (20000 permutations, one random
stream for the family)"). Up to 30 items every command, the inspector included, prints the same
p. Above that the estimate is seeded, so it repeats, but `family-test` draws one random stream
for the whole family while `pair-test` and the inspector draw one per pair: the same pair's p can
differ in the third decimal between them (32 items in the 2026-10-24 scenario: 0.0297 from
`family-test`, 0.0327 from `pair-test` and the inspector). The verdicts are read against the same
thresholds; a p that close to one is not a result either way. `pair-test` calls an arm significantly different from
the baseline at `p ≤ threshold`, and `family-test` marks an estimated p with `~` when the family
mixes exact and estimated rows. Every command prints p to four decimals, and `<0.0001` for what
would print as 0.0000. `family-test`'s `A wins` column counts the items A wins; the inspector's
`wins–losses` is each row's arm against the baseline.
Without `--metric` they read the primary metric the runs recorded. Which way is better is
inferred once for every command: a flag (`--asc`, `--desc`), else the goal the runs name, else
the adapter's `METRIC_DIRECTIONS`, else the name (cost, latency and token metrics go down).
`leaderboard`, `family-test`, `pair-test` and `inspect` take `--round rN` for the arms in play in
a round (`pair-test --round` and `inspect --round` also default the metric to the goal's measure).
When a dataset's runs were scored more than one way, `leaderboard` prints one table for each
(`=== scored against <ref> ===`, gold first; `=== scored by judge <scorer_id> ===` for judged
runs; runs scored against none get one too), each with its own tests, under a NOTE naming them
all, and never averages across them.

Two that are easy to reach for and wrong:

- **`pair-test` on a pair you chose after seeing the leaderboard** is the winner's
  curse with extra steps. If you did not name the pair in advance, use `family-test`.
- **`leaderboard` as a ranking.** It sorts; it does not separate. Five of the six
  evals here have a top group its own tests cannot tell apart, and the table
  still prints them 1, 2, 3.

---

## 8. Promote — a decision, not a copy

```bash
evh run-promote --run <run_id> --reason "beat prev baseline by 6% on my_v1 n=40, spread 0.004"
```

Refused if the run came from a dirty tree, if its build is unknown, or if the
reason is under three words. Those refusals exist for the same reason: in six months, *"why is this the
baseline?"* must have an answer.

The baseline carries what its number means, from the run: the reference tier it was scored
against, the adapter that scored it, its fingerprint hash, and its goal and format
(`validate` V6 fails a baseline that no longer matches its run). Promoting another run
replaces the baseline, and git keeps the one it replaced; a baseline is never edited.

**An arm run with `--repeat`.** You promote one run, and the arm has several. Promote any of
its repeats (`_r1` is as good as `_r3`): the baseline records that run's own `scores` (V6 compares
them with the run) and, under `repeats`, every repeat's run id and the mean of each score over
them ([`baseline.schema.json`](../schemas/baseline.schema.json)). The catalog, the inspector and
the tests read the arm as that mean, so the mean is the number to quote. `run-promote` prints
the two side by side:

```text
  NOTE: tickets_lead2_v1 has 3 repeats; the catalog, the inspector and the tests read their mean.
        The baseline records this run's own scores and, under `repeats`, the mean:
    ...
    overlap_f1     0.900088   (mean of 3: 0.900088)
```

```bash
evh runs-list --baselines
```

`evh round-close --promote <run_id>` promotes too, with the round's conclusion as the reason
(§13).

---

## 9. Validate before you trust anything

```bash
evh validate
```

Twenty checks (V1–V20): schema conformance (datasets, runs, baselines, configs, judge
scorers, judging sets, verdicts, dataset profiles), every run's `dataset_id` resolves, every run
identifies its build, materialized copies still match their hashes, no two
configs reporting byte-identical scores and per-item results (two arms with different outputs
that are both perfect are two measurements, not a copy), no baseline pointing at a
deleted run or disagreeing with it, every committed run readable and present on disk, no two runs claiming one
`config_id`, no derived run naming a scorer that is not the code in this tree, every judging
set matching its stored hash, every judge verdict naming a real set, item, pass and block,
every judge scorer yaml loading and well-formed, every goal and round well-formed and named by
every run that must name one, every item field declared, typed and matching its hash, and every
reference made by promotion (a manifest saying where it came from) with texts matching its checksums, every capture's
records matching the hashes it recorded, every model record and the configs naming it consistent, and every label set
matching its hashes and its dataset, and every `hypothesis:` in an arm config sound (V20). V4
checks only datasets materialized on this machine, and names each one it could not check (a CI
job without the sources checks none: materialize first where the copy matters).

What it holds *your* project to is yours to declare, in `data/validate.json` (all optional):

```json
{
  "committed": ["runs", "runs-adjudicated"],
  "floors": {"runs-adjudicated": 12},
  "scorer_sources": [{"dir": "runs-adjudicated", "glob": "*", "path": ["derived", "with", "scorer"],
                      "module": "../my_scorer.py", "callable": "scorer_id"}],
  "duplicate_ok": [["my_v1", "smoke_arm_v1"]],
  "configs": ["arms/*.yaml"]
}
```

`committed` is the run directories your reports cite, each with its `floors`; every other
git-tracked `data/runs*` directory is checked too, so one re-allowed in `.gitignore` is never
skipped. `floors` makes deleting cited runs fail. `scorer_sources` lets V10 check that derived
runs carry the current scorer's hash (`module` is a path from the project root). `duplicate_ok`
names the (dataset, config) pairs allowed to repeat. `configs` adds globs (from the project root)
of arm configs kept outside `data/configs`, so V18's notes on the arms that name a model record
see them.

The duplicate-score check catches a specific and nasty failure: two
independent arms do not agree to full float precision. When they do, one of them
is not its own measurement — a copied number, a mis-wired arm, a cached result.

Run it in CI. It exits non-zero.

---

## 10. Optional — the judge panel

When the cheap metric is biased in your domain but you have an expensive judge
you trust:

```bash
evh judge --config tutorial/judge_panel.yaml --use-fake-judge   # keyless; the kit's config
```

Triage on the cheap metric, decide with the judge, cost-capped with a mid-run
abort that preserves partial results. Each finalist is judged on its stored outputs. Knobs
in the config (`tutorial/judge_panel.yaml` from `evh init --tutorial`, or
`config.example.yaml` in a checkout); the reasoning is in the harness README.
`judging.primary_judge` (and `cross_judge`) is declared as a judge-score judge is: `id`,
`provider`, `model`, `usd_per_mtok_in`, `usd_per_mtok_out`, and optionally `temperature`,
`max_tokens`, `base_url`, `api_key_env`; its key is read as `EVAL_JUDGE_<NAME>` first. A judge
whose key is missing stops the panel before any call; the fake judge runs only with
`--use-fake-judge`.

---

## 11. Adjudicate disputed gold

When strong arms agree against the gold, the gold may be wrong. Check it, and re-score for
$0:

1. **Pick the items from both sides.** Take the items most arms miss, and also the items
   your best arms miss. Reviewing only one side flatters the other.
2. **Record each verdict** in an `adjudication.json` beside the eval: the item, the
   gold, what the adjudicator was shown, the verdict and the reason. Who adjudicated goes
   in the file too.
3. **Build the reference set and re-score:**

   ```bash
   python examples/_shared/adjudicate.py examples/<eval>/adjudication.json
   evh rescore --dataset-id <id> --reference-id gold/<id>_adj1 --out data/runs-adjudicated
   EVAL_RUNS_DIR=data/runs-adjudicated evh leaderboard --dataset-id <id>
   ```

4. **Add a claim check** for every new number you report. It can recompute them from the
   committed predictions and the adjudication file, so the re-scored runs need not be
   committed.
5. **Decide what is primary, and record why** (CONCEPTS: Re-measuring a frozen
   eval).

Worked example: `examples/classification-ag-news/adjudication.json`.

---

## 12. Re-measure with a validated judge

When a better instrument exists than the metric the eval ranks by (SummEval showed
`coverage` agrees with experts at τ 0.10, a validated LLM judge at 0.52), measure the frozen
outputs again, billed and capped. Design: [ADR-0001](../../docs/adr/ADR-0001-judge-scorers.md).
This is not `evh judge`, the older judge panel. **It is optional:** nothing else in the
harness needs it, and it never changes a committed run. To see the whole pass offline and
for $0 first, run [tutorial 3, step 5](../../docs/tutorials/3-frontier-reference-and-judging.md#5-re-measure-with-an-llm-judge-optional).

```bash
evh judge-score --dataset-id my_v1 --scorer my-judge-v1 --dry-run   # free
evh judge-score --dataset-id my_v1 --scorer my-judge-v1
EVAL_RUNS_DIR=data/runs-judged/my-judge-v1 evh leaderboard --dataset-id my_v1
```

A project needs only its own data directory, scorer, prompt and runs: the judging code, the
prompt builder and the judge client are all in `evaluation_harness`.
`validate_judge_goyal.py` and `validate_judge_zhang.py`, which check a scorer against the Goyal
et al. human preferences and the Zhang et al. crowd ratings (CNN/DailyMail articles), stay
scripts of this repository: each is specific to its download
and to the news-summary judge, so neither is an `evh` command.

1. **The scorer** is `data/scorers/<id>.yaml`: two or more judges from different vendor
   families, the task, the prompt, the protocol, a `validation` block and a cost cap. The
   protocol must state `position_check_fraction` and `noise_check_fraction`: the noise check
   above 0, and the position check above 0 whenever `outputs_per_call` is above 1 (ADR-0001 §4);
   a scorer without them is refused. The command refuses a scorer whose validation does not name a committed run with the stated
   value and the judge's model. `--unvalidated` overrides it and labels every number
   "unvalidated judge" (the primary metric becomes `judge_score_unvalidated`). Templates:
   [`judge-summ-v1.yaml`](../data/scorers/judge-summ-v1.yaml), real and validated, and
   [`tickets-judge-v1.yaml`](../tutorial/scorers/tickets-judge-v1.yaml), fake, with a `task`.
   - **`task`** says what is judged: `source_label` (what each item is, e.g. `TICKET`,
     `QUERY`), `output_label` (what the arms wrote, e.g. `SUMMARIES`, `ANSWERS`),
     `dimensions` (the names the judge must score, each a JSON key in its reply) and `scale`
     (`[low, high]`, whole numbers; a score outside it makes the reply unparsed). The judge receives the
     prompt, then `<source_label>:` and the item, then `<output_label>:` and the outputs
     numbered 1..n. Leave `task` out and it is SummEval's news-summary task (`ARTICLE`,
     `SUMMARIES`, coherence/consistency/fluency/relevance, 1-5), which the committed
     summarisation scorer uses. A declared `task` is hashed into the judging set's id.
   - **The prompt** writes `{n}` wherever the number of outputs in a call goes ("rate each of
     the {n} numbered answers", "a list of {n} integers"); the pass replaces it per call. It
     must ask for JSON with one list of n numbers per dimension. A prompt without `{n}` is
     taken to be SummEval's, whose own count phrases are rewritten instead; a prompt with both
     is refused, since its fixed phrases would keep saying 16.
   - **Which arms.** Every arm on the dataset (its latest run per `config_id`) unless the
     scorer sets `arms_match` (a `config_id` substring), or `--match …` or `--arms a,b,c`
     narrows it. A subset is its own judging set. If the arms mix config versions
     (`_v1` and `_v2` of one arm), the pass warns: each version is judged as its own arm.
   - **`prompt.file`** is looked up in this order, first hit wins: an absolute path as
     written; the project root (`EVAL_HOME`; else, in a checkout, the checkout; else the nearest
     directory up from where you run that has `data/`); the directory of
     the scorer file itself; and, only in a checkout of this repository, the repository root,
     which is where the committed scorers' `examples/summeval-judging/prompt.txt` points. A
     project keeps its prompt wherever it likes and names it relative to its root
     (`prompts/judge.txt`). `sha256_at_16` is the hash of the file's text rendered for 16
     summaries; the gate recomputes it.
   - **Routing.** A judge's `provider:` in its `params` decides where its calls go. Each provider
     reads environment variables: arms read `<VAR>`, judges read `EVAL_JUDGE_<VAR>` first (for
     their own keys and budgets), then fall back to `<VAR>` to share the arms' credentials. A
     judge's own `base_url` and `api_key_env` in params override the environment. See
     [tutorial 2](../../docs/tutorials/2-hosted-llm.md) for the providers and their variables.
     Billed cost is read from the response; the scorer's price table is the fallback. Before
     anything is called (and in `--dry-run`), each judge's line says where its calls go and
     which key pays ("judging's own" or "shared with the arms"); a missing key or address is
     printed as `MISSING:` and the pass stops with nothing sent.
   - **`provider: fake`** judges call nothing and cost nothing. They exist to try a scorer
     end to end and to test one; the gate refuses them whatever the `validation` block says,
     so they only run with `--unvalidated`.
2. **Dry-run first.** It builds the judging set and prints calls, tokens and estimated cost
   per judge, and calls nothing.
3. **The judging set** is one item = the source plus every arm's primary output, arm ids
   hidden, order shuffled per item by the seed. Its id pins the arm set, and its manifest is
   frozen in `data/judging-sets/`. Add an arm and you get a new set and a new pass.
4. **Blocks.** SummEval validated 16 summaries per call, so an item's arms are judged in the
   fewest blocks of at most `outputs_per_call`: 29 arms are 15 + 14. Scores are absolute on
   the task's scale per dimension, so blocks are pooled. Validate at the block size you run.
5. **Verdicts** are stored per call in `data/judge-verdicts/`. A rerun skips what is
   stored; `--no-calls` projects from them for $0. At the cost cap the pass stops and
   keeps everything bought; raise the cap to continue. A reply that does not parse (wrong
   shape, missing dimension, a score off the scale) is stored and reported as
   `unparsed reply: …`; an item counts only when every one of its primary blocks parsed. A
   reply that is not bare JSON scores (a judge reasoning aloud, a reply cut off) or that
   repeats 8 consecutive words of the item or an output is committed only as its hash, so the
   source's text is never committed by accident; `validate` V12 checks every committed reply.
   Its text is kept on your machine, git-ignored, beside its record:
   `data/judge-verdicts/<scorer>/<judging set>/<judge>/.withheld/<item>.<pass>.b<block>.txt`
   (the directory ignores itself). The log names the file ("reply not committed as text (…),
   only its hash; readable, git-ignored, at …"), so you can read why a reply did not parse
   before you retry. Real judges do this: on the Zhang et al. validation `gemma_l` left 1 of its
   200 replies unparsed and `qwen_s` 2
   (`data/judge-validation/judge-summ-v1/zhang2023-cnndm/report.json`). `--retry-unparsed` calls
   again for those blocks only. The pass prints what it spent: "spent this run $…, stored total
   $… (the provider's bill where it reports one, else the price table)", the same rule as an
   arm's cost (§4).
6. **Read the judging pass's checks before the ranking.** The judged leaderboard
   (`EVAL_RUNS_DIR=data/runs-judged/<id> evh leaderboard …`) prints them under its table, from
   `data/runs-judged/<id>/summary.json`: how far the judges agree (item tau, and the Spearman of
   the arms' order), and per judge the position check (a second shuffle on a subset) and the
   noise check (the same call repeated on a subset):

   ```text
     The judging pass (tickets-judge-v1, 6/6 items, unvalidated judge), from summary.json:
       judges judge_a and judge_b agree: item tau 0.040, arm order spearman 0.400
       judge_a: reshuffled outputs tau 1.000 (position), the same call repeated tau 1.000 (noise)
   ```

   A difference between arms smaller than the noise check's is not a difference.
   `summary.json` also has the per-judge columns and which arms share a judge's family. A judged
   run keeps its source run's cost and speed, so the judged leaderboard has its frontier.
7. **Record the decision.** Changing an eval's primary metric is a recorded decision
   with a reason; the old metric stays beside the new one (CONCEPTS: Re-measuring a frozen
   eval).

### Judging modes: grade, pick, pairwise

What a judge is asked is the scorer's `mode` ([RFC-005](../../docs/rfc/RFC-005-judge-scorers.md), "Judging
modes"), and a judge is validated in the mode it is used (`validation.mode` must equal `mode`):

- **`grade`** (the default, everything above): each output scored per dimension on the scale.
- **`pick`**: one call per item with every arm's output, blind and shuffled; the judge names the best
  (`{"best": [3]}`, several when they are equally best). `protocol.outputs_per_call` must be at least the number of
  arms: a pick made in blocks would name each block's winner, so it is refused.
- **`pairwise`**: one call per pair of arms on every item (`{"better": 1}`, `2` or `"tie"`);
  `outputs_per_call` is 2. That is n(n − 1)/2 calls an item: read `--dry-run` first.

Pick and pairwise project `won` per arm per item: 1 for an arm picked alone, 1/k when k share the best, else 0
(pick); the share of its pairs it won, a tie a half (pairwise). The judged runs' primary is `judge_won`
(`judge_won_unvalidated` with `--unvalidated`), and goals, rounds, `inspect` and the sheet read them as they read
`judge_score`. `summary.json` and the terminal add each arm's win rate (its mean `won`) and its Bradley-Terry
strength with a 95% interval from resampling the items; the position check (a re-shuffle, or the pair swapped) and
the noise check (the same call repeated) are reported as the share of verdicts that held.
This repository's two, `judge-summ-pick-v1` and `judge-summ-pairwise-v1`, use
`judge-summ-v1`'s judges (`gemma_l`, `qwen_s`), each validated in its mode on SummEval:

```bash
evh judge-score --dataset-id cnn_dailymail_200 --scorer judge-summ-pick-v1 --dry-run   # free
evh judge-score --dataset-id cnn_dailymail_200 --scorer judge-summ-pick-v1
evh inspect --sheet --dataset-id cnn_dailymail_200 --runs … --metric judge-summ-pick-v1/judge_won
```

### Validating a judge: what the gate needs

A validation is an ordinary eval whose **arms are the judges** and whose items carry
human ratings. Each judge runs as an arm (same `model`, `temperature`, `reasoning`,
`max_tokens`, `provider` and prompt file as in the scorer) over items people have already
rated, and its score is how well it agrees with them: rank correlation for ratings, accuracy
for preferences. The scorer's `validation` block then names those runs:

```yaml
validation:
  dataset_id: <the human-rated dataset_id>
  metric: tau                      # the validation run's primary metric
  what: mean Kendall tau-b against the mean of three expert annotators
  differs_from_this_use: <how the rated outputs differ from the ones you will judge>
  runs:
    - {judge: gemma_l, run: <run_id>, value: 0.538416, min_metric: 0.371714}
```

A pick or pairwise scorer adds `mode: pick` (or `pairwise`) to the block, and its `metric` is the validation
run's in that mode: `top1` or `pair_agreement` in the SummEval example (below).

The gate reads each named run's `metrics.json` and refuses unless the metric equals
`value`, is at least `min_metric` (set it to the best free scorer's score on the same data,
so a judge must beat it), and the run's model, params, prompt file and prompt sha256 are the
scorer's. The worked example is
[`examples/summeval-judging/`](../../examples/summeval-judging/README.md): its adapter turns
a judge's JSON reply into tau against the experts, and `judge-summ-v1` cites two of its runs. An arm with
`mode: pick` in its params picks the best of an article's 16 summaries (`prompt_pick.txt`), scored `top1` beside
`top1_chance`; one with `mode: pairwise` judges seeded pairs (`prompt_pairwise.txt`), scored `pair_agreement` (with
`n_pairs`); the `random` arm in each mode is the floor `min_metric` names (`configs/arm_*_pick_n100.yaml`,
`arm_*_pairwise_n100.yaml`). The adapter's `primary_metric(params)` makes each arm's primary its mode's metric
([INTEGRATION](INTEGRATION.md)); `judge-summ-pick-v1` and `judge-summ-pairwise-v1` cite those runs.

**Validate on outputs like the ones you will judge.** In this repository, judges validated
on SummEval's 2019 summaries ranked modern LLM summaries above a fine-tuned BART; one blind
human check (one non-expert reader, 20 pairs, truncated articles) preferred the BART 14 to 6,
p = 0.115 (REPORT_SUMMARIZATION §3.8). Neither result is confirmed on those outputs. Larger,
dearer judges did not change it: the two highest-scoring SummEval judges from vendors not in the
first pair, with the same prompt and reasoning off, at 41× the price, gave the same verdict
(`judge-summ-v2`). On crowd ratings of 2022 LLM summaries (Zhang et al. 2024,
`validate_judge_zhang.py`) all four judges track people better than one rater does on coherence and
relevance (not on faithfulness), while
deviating from them system by system in both directions. The gate checks that a validation exists and is
current, not that it transfers. `differs_from_this_use` is where
you say how far it has to travel, and the honest next step is a small human check on your
own outputs.

---

## 13. Rounds of an eval (optional)

Evals go round on round: try some arms, keep what wins, drop what lost, change something,
compare again. A round records it, beside its goal, in `data/rounds/<goal>/<round>.yaml`; the
commands are its only writers, and a project that never opens one sees none of it. Design:
[ADR-0004](../../docs/adr/ADR-0004-eval-rounds.md). Walkthrough, offline:
[tutorial 4](../../docs/tutorials/4-rounds-and-versions.md).

```bash
evh round-open --goal my_goal --dataset my_v1 --hypothesis "what this round sets out to learn" \
    --keep arm_a_v1,arm_b_v1                       # round 1: carry in arms already run
evh rounds --goal my_goal                          # the evidence, and the next decisions as commands
evh round-retire --goal my_goal --round r1 --arm arm_b_v1 --reason "why it is dropped"
evh round-retire --goal my_goal --round r1 --arm arm_b_v1 --runs-dir runs-linux --reason "..."  # one copy only
evh round-close --goal my_goal --round r1 --conclusion "what it showed" [--promote <run_id>]
evh round-open --goal my_goal --dataset my_v1 --from r1 --change "what changed and why" \
    --keep arm_a_v1 --retire arm_c_v1 --reason "why" --budget-usd 0.50
```

- **A new arm joins a round** by naming it in its config, `round: r2` beside `goal:`; every run
  records it. **Carried arms (`--keep`) need no config change and no new run:** their runs
  already count, and `round-open` says so ("Carried in as they are, their runs already count: …
  (their configs need no change and they need not run again)"). Commit the round file before
  the runs.
- **`evh rounds` never suggests promoting the run that already is the baseline**: its close
  suggestion then reads "close the round with what it showed (<arm> is already the baseline)",
  with no `--promote`. `leaderboard --round` does not warn about two versions of one arm (`_v1`,
  `_v2`) in a round: comparing them is what the round is for.
- **`evh rounds`** reads the evidence the way the inspector does (the round's arms against its
  leader, Holm-corrected; its leader against the previous round's best, the baseline it started
  from and the arm that wrote a silver reference of the dataset; its spend against `--budget-usd`,
  and the cost per item), read against the reference most of its arms use (gold before silver on
  a tie), naming the arms scored against another (`NOTE: read against <ref>; not compared: …`),
  and suggests the next decision as the command that makes it: retire an
  arm, measure more items, close the round. It never suggests retiring the baseline the round
  started from, nor, when the round is read against that arm's own silver, the arm that wrote
  it: there it is the yardstick, not an arm under test (against gold it is an arm like any other). The
  close suggestion carries `--promote` only for a leader significantly better than the baseline it
  started from (read, like the round's arms, from its re-score where it has one), with the test
  corrected for the leader having been chosen from the round's arms (Bonferroni over them: every
  arm could have been the best mean); not behind the previous round's best; separated from the
  round's other arms (none `not significant` against it after Holm); and with the round's arms
  measured by the same scorer. Otherwise it says why it promotes nothing. A closed round suggests
  nothing, in its text and in `--json`. It decides nothing.
- **`round-close --promote <run_id>`** promotes that run to the dataset's baseline, with the
  conclusion as its reason. A closed round refuses new runs; one round per goal is open at a
  time.
- A round compares arms scored against one reference: when gold arrives mid-way, new runs are
  scored against gold while carried arms were scored against silver, so re-score them first.
- `leaderboard`, `family-test`, `pair-test` and `inspect` take `--round rN`. `inspect --round`
  reads the goal's measure against the round's leader, and names the arms with no score on it;
  `pair-test --round` tests the round's leader against the baseline it started from unless
  `--a`/`--b` say otherwise, and refuses an arm not in play. `validate` (V14) checks the round
  files; the catalog's goal page shows the rounds, newest first, each with an inspect button.

---

## 14. Browse the catalog and the inspector

```bash
evh catalog                                             # build static pages into .build/catalog/
evh catalog-serve [--port N]                           # the catalog and inspector on 127.0.0.1, a port of the project's own
evh catalog-serve --public catalog.example.com --publish outputs --client-header X-Real-IP  # public deployment
evh dataset-profile --dataset-id my_v1 [--with-text]   # what is inside a dataset, for its page (text: committed items only)
evh dataset-items --dataset-id my_v1 [--item ID]       # the same in the terminal
evh mcp                                                 # the read commands as MCP tools, over stdio
evh mcp --http --bind 0.0.0.0 --allowed-host evals.team.example --public  # a shared MCP server
```

**The catalog** is static pages over runs: one per dataset and goal, one per reference, the
label sets and the captures (§15, §15b), a metrics page, and a search; the inspector adds each
dataset's sheet. Every page carries counts and means only, and item text only where
the repository already publishes it (a profile written `--with-text`, refused unless git has
committed every item's file); otherwise item text is the local inspector's only. Build it offline with `evh catalog`, or together with the inspector. A dataset's
page shows what is inside it once `evh dataset-profile` has written its profile where the
dataset is materialized: the items' lengths, the gold's labels or shape, and each item's link to
its source when one is recorded; commit `data/profiles/` and a catalog built anywhere shows it.

**For an agent with a shell**, these read commands take `--json`: the views, `inspect`,
`leaderboard`, `pair-test`, `family-test`, `rank-stability`, `run-compare`, `rounds` and `runs-list`
(not yet `bootstrap-test`, `holdout` or `cost-report`)
(and `evh run`, below). Stdout is then exactly one object,
`{"command", "version", "result": {"blocks": [...], "values": {...}}}`: `blocks` is what the
command prints, each table as `columns` and `rows` with its raw numbers (NaN as null), and
`values` its key results by name (`pair-test`'s `delta`, `p`, `method`, `verdict`;
`leaderboard`'s `groups` with each arm's rank and metrics and the `ordering` test;
`family-test`'s rows with `p_holm`, the Holm-adjusted p; `runs-list`'s `count`). A refusal prints its
message on stderr, nothing on stdout, and exits non-zero. `evh run` prints `  run <run_id>` for each
run it wrote; with `--json` its progress goes to stderr and `values.runs` lists each run's
`run_id`, `config_id`, `dataset_id`, `dir`, `n_items`, `total_cost_usd` and `capped_at` (`--dry-run
--json`: `values.dry_run`, the projection). The text output without `--json` is unchanged.

**For an agent without one**, `evh mcp` serves the same read commands as MCP tools; how to connect
each client is in [the integration guide](INTEGRATION.md#for-an-agent-evh-mcp).

- **The tools** (23) are `overview`, `datasets`, `dataset-items`, `arms`, `models`, `goals`, `references`,
  `metrics`, `activity`, `search`, `inspect`, `leaderboard`, `pair-test`, `family-test`,
  `rank-stability`, `run-compare`, `rounds`, `runs-list`, `validate`, `captures`, `labels`,
  `picks` and `deploy-sheet`. Each takes the
  command's own options, named as on the command line (`dataset-id`, `period`), except those
  that name a server path (`--runs-dir`, `--items` on `pair-test` and `family-test`). Each call runs
  the command as a child process, with `--json`, so the answer is what you would
  see. No tool writes project data, spends or runs a model. What a call writes is computed
  answers in `<project>/.cache/`: the p cache, `evh-p.jsonl` (below, `EVH_P_CACHE`), and
  `family-test`'s results.
- **Refused before anything runs:** an argument the tool does not have, a missing required one,
  a value of the wrong kind (a list for a one-value option, a flag that is not `true`/`false`),
  any value that starts with `-`, and a dataset id that is not a plain name.
- **Stdio** (the default): the agent starts `evh mcp --project /path/to/project`. A desktop client
  starts it with its own `PATH` and working directory, so give the full path to `evh` and
  `--project`.
- **`--http`**: Streamable HTTP, stateless, JSON answers, at `--path` (default `/mcp`) on `--bind`
  (default `127.0.0.1`) and `--port` (default: the project's own, in 19000–19999, the same every time; `catalog-serve` has one in 18000–18999). `<path>/health` answers `{"ok", "version",
  "tools", "public"}`. Beyond the loopback, `--allowed-host` is required: a request for another Host
  is answered 421 (DNS rebinding). `--allowed-origin` names the browser origins it accepts; an
  agent sends no Origin.
- **`--public`**, for a server anyone can reach: no option that answers with an item's text or a label
  (`inspect --item`, `--items-out` and the sheet's options, `dataset-items --item`), no `inspect --group`
  (a recorded field can hold text; `--crosstab` of two scores stays), and no `validate`.
- **Load:** `--concurrent N` commands at once (default 4; a call that waits 30 s for a slot is
  refused, "busy"), `--timeout S` per call (default 300; the command is stopped, exit 124),
  `--rate N` calls a minute per caller and `--rate-total N` for everyone together (default: no
  limit), and over HTTP one call at a time per caller. Every call counts toward the caller's rate, a
  refused one too; the total counts only calls that run a command, so a flood of refusals never
  locks others out. An IPv6 caller is counted by its /64. Below the tools, the HTTP layer:
  `--request-rate N` HTTP requests a minute per caller to the endpoint, every method (a tool call
  is about three), `--max-body BYTES` (default 65536; larger is 413), `--max-connections N`
  (default 64; more are 503), at most 8 requests open per caller (more are 429), a body due in
  full within 10 s (else 408), and a GET on the endpoint is 405 (stateless: no stream to hold);
  `/mcp/` is the endpoint too, never a redirect.
  With `--public`, an answer is kept by its command line (16 MB of text in all, for an hour: a
  view's default period moves with the date), since the data under the server never changes, and a refusal is told without server paths or a traceback.
  A value with a NUL byte, or longer than 512 characters, is refused. `--client-header NAME` names the header your proxy sets for
  the caller's address. Trust it only when nothing but the proxy reaches the port: a caller who
  can set it can name itself anything (the total still holds).
- **`--hooks FILE`**: the deployment's error reporting, tracing, metrics and analytics, in
  `catalog-serve --hooks`' shape (`start`, `request` after each call, `error`, `routes`). A hook
  gets the tool, its arguments' names, how it ended, its time, and the caller's address and user
  agent. The log line on stderr, one JSON line per call, carries neither.

**The run inspector** is a local server (`evh catalog-serve`) that tests chosen arms against a
baseline with the same paired test as the command line, and shows outputs beside references.
Its "re-score" box (shown when the adapter can re-score) scores what is not on record; `evh
inspect --no-rescore` is the box unticked.

**A crosstab of two per-item scores** (terminal only): `evh inspect --runs A --crosstab M1,M2
[--group FIELD [--group-match REGEX]] [--where F:V] [--max-ids N] [--json]`. For each group, the run's
items counted by their value of `M1` (down) and `M2` (across), with totals, and the item ids of every cell
off the diagonal (`M1` value differing from `M2` value; text lists up to `--max-ids`, default 8, then
"and N more"; `--json` carries every id, and the diagonal cells' too). `M1` and `M2` are any per-item
scores in the run's `predictions.jsonl`; an item with no value counts as `none`. `FIELD` is a dotted path
into a prediction row (`_meta.gates`), not a dataset field: the group is its whole value. A recorded
field that packs several facts in one string (`i:n/a/c:n/a/d:downgraded (no corroboration)/e:n/a`) is
cut with `--group-match`: the group is the regex's first `(…)` found in the value (the whole match
without one), `none` when it does not match. `--where` is the usual dataset-field filter. Several runs
give each its own groups. Example, the triage baseline's dismiss gate:

```
evh inspect --runs triage_baseline_pro_v1 --crosstab model_false_dismiss,false_dismiss \
    --group _meta.gates --group-match 'd:(n/a|[^/]+)'
```

For `downgraded (no corroboration)` the cell `model_false_dismiss=1, false_dismiss=0` holds 12 items (the
gate saved a false dismissal); the same group under `model_false_alarm,false_alarm` holds 8 in
`model_false_alarm=0, false_alarm=1` (a right dismissal turned into a false alarm). The 12 and the 8 are
different items, so a gate's net effect is read from both.

**Each item's outputs and reference together** (terminal only): `evh inspect --runs A,B --items-out
[--disagree] [--where F:V] [--baseline A] [--max-chars N] [--json]`. `--sheet` carries each run's
decision, scores and the labels but cuts them for a cell (`--json` too) and has no run's whole output;
`--items-out` is the record per item: `item_id`, the item's start, its fields, the signals, and per run its
`decision`, whole `output` text, `scores` and the `_meta` the adapter recorded, then the `references` and
`labels`. Text prints each as a block with an output cut at `--max-chars` (default 300, 0 = whole), a
JSON-object output without its `_`-keys (a probe trace; the `_` keys are counted), and how long a cut
output was. `--json` carries everything whole under `result.values.items_out`. `--disagree` keeps the
items the other runs decided differently on from the first (`--baseline A` puts `A` first). All runs
must be on one dataset. Not served by `--public`.

**Public deployments** (`--public HOST`): the server answers only the named hosts, each client
gets `--rate` requests per minute, and at most `--max-arms` arms per comparison. `--publish`
names what text to serve besides numbers: `outputs`, `references`, or both. The item itself is
never served publicly. `--client-header NAME` names the header that identifies each client (e.g.
`CF-Connecting-IP` behind Cloudflare), trusted only when a reverse proxy you control sets it on
requests from an origin no one else can reach.

**Partial reference coverage:** `evh run` refuses, before a call, a reference with no
file for any of the dataset's items, and warns when only some items have one. The run records
`reference_coverage` (`{items_with_reference, items}`) and the leaderboard prints a NOTE for
it: its quality columns are means over the items that have a reference.

**Dataset profiles.** `evh dataset-profile --dataset-id D` writes `data/profiles/D.json`
(`schemas/profile.schema.json`); `--with-text` adds each item's text and is refused unless git has
committed every item's file; `--json` prints what it wrote, in the views' envelope. An item links
to its source by its own `source_url`, else by `data/sources/<dataset_id>.rows.json` (`{"source":
{"name", "url"}, "item_url": "...{row}...", "rows": {item_id: {"row", "sha256"}}}`), an entry
counting only when its sha256 is the item's; only an http(s) address becomes a link. `evh
dataset-items --dataset-id D [--item ID] [--json]` prints the profile.

**`--json` on the views** (`overview`, `datasets`, `arms`, `goals`, `references`, `metrics`,
`activity`, `search`, `inspect`): one object, `{"command", "version", "result": {"blocks": [...]}}`,
each table as columns and rows. 0.8.0 gives each command its own result and retires `blocks`: do not
build on it. `captures`, `labels`, `picks` and `deploy-sheet` already answer `--json` with an object of their
own (`{"captures": …}`, `{"sets": …}`, `{"picks": …}`, the sheet).

**The catalog's footer** names each page's command (`evh goals --goal G`); `evh catalog --mcp URL`
adds the same as an MCP tool call, with the server and a "how to connect" link (`--mcp-howto URL`,
the harness's INTEGRATION guide by default). Every page carries a share card (its title and its
opening line as the description); `--card URL` adds the image a shared link shows. The pages stay
`noindex`: a card is for a person pasting a link, not for a search engine.

**`evh mcp --hooks`** gets, in `start`, `{"version", "tools", "public", "transport"}`, and in
`request`, after each call, `{"tool", "args", "agent", "client", "exit", "ms", "bytes"}`, plus
`"refused"` (`rate`, `rate_total`, `tool`, `arguments`, `busy`, or `command` for a command that ran and refused: exit 1, its `ERROR:` line) or `"cached": true`. `tool` is
`unknown` for a name the server does not have; `args` are argument names, never values.

**In the terminal:** every view has a command. `evh overview [--period P]` for the home page,
`evh activity` for the activity page, `evh arms` (`--by config`, `--configs`) for the arms page,
`evh datasets`, `evh arms --arm …`, `evh references`, `evh metrics --metric …` and
`evh goals --goal …` for the others, `evh inspect --runs …` (`--analysis` for the charts, `--item <id>`
for one item) for the inspector, `evh labels` and `evh captures` for the Labels and Captures pages,
`evh inspect --sheet --dataset-id … --runs …` for a dataset's sheet (the inspector's per-item scores too),
`evh inspect --runs … --crosstab M1,M2` and `--items-out` for the two per-item reads above,
`evh picks` for the picks waiting and `evh deploy-sheet --config …` for a goal's deploy sheet.

---

## 15. Datasets from production: the capture lane

A dataset can come from what a production system did: its decisions, requests or answers, and what
happened afterwards. The lane is a layer beside the rest: nothing here runs in production, and a project
that never captures sees none of it. Design: [RFC-019](../../docs/rfc/RFC-019-datasets-from-production.md),
[ADR-0019](../../docs/adr/ADR-0019-capture-lane.md); a worked example on a real agent:
`examples/triage-fleet/`.

```bash
evh capture --importer jsonl --query '{"path": "decisions.jsonl"}' --capture prod_2026_10   # or tsv, github, langfuse, path.py:Class
evh captures --capture prod_2026_10                                    # what was read, when, the hashes
evh capture-scrub prod_2026_10 --command "python scrub.py {records}"   # your scrubber; changed records re-hashed
evh dataset-from-capture prod_2026_10 --dataset-id prod_v1 --one-per fingerprint --tag source=prod
evh dataset-materialize --dataset-id prod_v1
evh label-from-capture --dataset-id prod_v1 --capture prod_2026_10 --map rules.yaml \
    --set prod_outcomes                                                # a rule set: what happened afterwards
evh dataset-split prod_v1 --test 0.3 --seed 7 --key fingerprint     # prod_v1_validation, prod_v1_test
```

- **A capture** is `data/captures/<id>/capture.json` (each record's id and hashes) and `records/` (the
  records). V17 checks them. A project may keep `records/` out of git and fetch them from where it
  publishes them; a capture without its records is then named "not fetched", not failed.
- **An importer** is a class with `records(query)` yielding `{id, body, fields, created_at, source,
  outcome}`. The built-in ones read JSON lines, TSV, GitHub issues (with the comment beside each close)
  and Langfuse traces. `evh importer-check` runs a new one against the contract, including that it keeps
  to a query's `since` and `until`.
- **The JSON-lines and TSV query** maps your columns; every key but `path` is optional: `path` (the
  file, relative to the current directory); `id` (the id column, default `id`); `body` (the content
  column, default `body` when the rows have it, `"row"` for the whole row); `fields` (the columns kept
  as fields, default every column but id, body, created_at and outcome); `created_at` (default
  `created_at`); `outcome` (what happened afterwards, default `outcome`); `url` (a link, with
  `{column}` placeholders); `system` (default the file's name); `where` (`{column: value or [values]}`,
  compared as text); `since`/`until` (ISO times, `[since, until)` on created_at). TSV also takes
  `delimiter` (`","` for a comma-separated file).
- **A sample is the capture's.** `evh capture … --sample-rate 0.001 --seed 7` keeps one record in a
  thousand, by a hash of each id, as the records are read: the same rule draws the same records again,
  and a source far larger than the sample is never held at once. The importer receives the rule as its
  `sample` option (`{"rate", "seed"}`) and may sample at the source; `evaluation_harness._importers.sampled`
  is the rule. `dataset-from-capture` selects (`--where`, `--one-per`, `--dedup`); it does not sample.
- **Later: what came since, and how it ended.** `--since-capture <earlier>` captures what came after an
  earlier capture: records it holds are skipped by id, and every record must fall inside the window
  recorded (one outside it is named and nothing is written; `--late` keeps the ones older than `since`
  the earlier capture never saw, listed as `late`). A continued capture never re-reads a record it holds,
  so for newer outcomes take a fresh capture of the same query and run `label-from-capture --capture`
  on it into a new set: the dataset stays as frozen, only the labels move (tutorial 6 §5).
- **The catalog's Captures page** lists every capture (records, importer, the time its records span,
  what it continues) with the datasets made from each; a dataset's origin links to it.
- **Only the body becomes the item.** Fields are typed by a field set: `--fieldset S` keeps every field
  it declares, `--field F` (repeatable) only the ones named. The outcome stays in the capture, for labels.
- **A version from a capture** (`--from D_prev`): the earlier version's items stay, the capture's new
  records are added, and a record of an item the earlier version has replaces it, so a corrected body
  is counted as changed in the lineage (`derived_from`: added, removed, changed).
- **An importer named by path** (`path/to/importer.py:Class`) is found from the current directory,
  else from the project root: the path a capture records works from either.
- **Labels from outcomes are a `rule` set**: what production recorded afterwards, mapped by a rule set
  you commit. It can repeat what production decided (an item nothing happened to reads as right), so
  read it beside a person's labels; promoted, it is a reference like any (ADR-0022).
- **`text: hidden`** (`dataset-from-capture --hide-text`) keeps a dataset's text, and every text derived
  from it, off every public surface, for data a project may measure but not publish.

## 15b. Evaluating what production did

A capture keeps what production did; the governed datasets, labels and references stay yours. The
loop, on any project ([RFC-023](../../docs/rfc/RFC-023-labels-and-references.md); worked on the triage
fleet in `examples/triage-fleet/`):

```bash
evh arm-from-capture --dataset-id prod_v1 --capture prod_2026_11 --as production_v1 \
    --like data/configs/deployed.yaml                                  # production's decisions, as an arm
evh run --config data/configs/deployed.yaml                 # the deployed config, replayed
evh label-sheet --dataset-id prod_v1 --items disagree --runs production_v1,deployed_v1 --out sheet.csv
evh label-import sheet.csv --dataset-id prod_v1 --set owner_2026_11 --by <you>
evh rescore --dataset-id prod_v1 --labels owner_2026_11                # every arm, against your labels
evh inspect --sheet --dataset-id prod_v1 --runs production_v1,deployed_v1 \
    --wrong-against owner_2026_11 --new-vs governed_v1                  # where production was wrong on something new
evh pick --dataset-id prod_v1 --item … --for governed_v1 --tag case=…  # worth keeping
evh dataset-extend governed_v1 --dataset-id governed_v2 --picks        # the next version, from the picks
evh deploy-sheet --config deployed_v1 --capture prod_2026_11           # did production run what you promoted?
```

- **Production's recorded arm** (`provider: recorded`): each output is the capture's record of the same
  id, read by the adapter's `recorded_output(record)` (else `--field`). It is scored, tested and compared
  like any arm; it costs nothing and its speed is not measured.
- **Agreement**: two outputs are one decision when the adapter's `same(a, b)` says so (default: the same
  decision, by the adapter's `decision(output)`, else the same text). `inspect --disagree` and
  `label-sheet --items disagree` keep the items where the arms differ.
- **More than one right answer**: a label can accept several (`also right` in the sheet, `label: [file, escalate]`
  in a rule), written `{"accept": ["escalate", "file"]}` and shown "escalate or file", for answers each fully
  right, never for "unsure which". A decision is **wrong** against a label when it is none of them.
- **Agreement between label sets** (`evh labels --dataset-id D [--confusion]`, the dataset page): on the items
  both label, how many accept the same answers, how many share one (apart: a label accepting more agrees more
  easily), Cohen's kappa and Krippendorff's alpha (MASI distance for several answers), which correct for the
  agreement chance alone gives when one class dominates. Free-text labels are not compared as text. An adapter's `score` reads such a reference with `answers(reference)` from `evaluation_harness.adapter`.
- **The sheet** (`evh inspect --sheet --dataset-id D --runs A,B,…`) shows the dataset's items down (each by the
  first arm's adapter's `title(item)` when it has one, else its start) and a column per arm across: what it wrote (the adapter's `decision(output)`, else its output, shortened; `--scores-only` leaves
  it out) and every score it has on the item: its run's metrics, and a judging pass's where one under
  `data/runs-judged/<scorer>/` covered the run (`--metric M`, or `SCORER/M` for a judge's, picks the one the sheet
  is read on); a column per label set or reference set; the
  winner per item (the best arm on that metric, and a pick or pairwise judge's choice where one covers the run);
  the signals; the fields; and a footer per arm: its mean, its win rate (the share of the rows it was scored on
  that it wins, a shared win split, "—" for an arm scored on none; on a pick or pairwise verdict, each arm's share of what the judge gave over the
  rows it judged, so a shared pick counts its share, a row given to an arm not shown is nobody's, and with every arm
  shown it is the judging pass's own win rate) and its verdict (the goal's decision when a goal names the dataset, else the paired test
  against the leader). The signals: **wrong** (the first run against a label set, `--wrong-against`),
  **disagree**, **split** (the candidates among themselves), **new** (a field value the dataset in `--new-vs` never
  had), **unlabelled**. Each is a filter (`--disagree`, `--split`, `--unlabelled`, beside `--where` and `--by`);
  the sheet ends with the `evh pick` and `evh label-sheet` commands for its rows. `--csv FILE` writes it (UTF-8
  with the mark Excel needs). The inspector shows the same (the dataset page's "Open its sheet"), with downloads
  of the CSV for the rows shown or ticked (the local inspector only; the page writes nothing).
- **A sheet filled elsewhere.** `--csv sheet.csv --fill label` adds the empty `label`, `also right` and `note`
  columns (`--choices a,b,c` puts the allowed answers in the label's header); `--fill pick` or `--fill scores`
  writes the arms' outputs as blind columns A, B, C… shuffled per row (`--seed`, default 0), a `pick` column or a
  `score: X` column per output (`--scale LO..HI`, default 1..5), the rubric as the first row (`#rubric`;
  `--rubric FILE`, else a plain one) and the key beside the sheet (`sheet.key.json`: which letter was which arm,
  the rubric and its sha256). A person or any AI tool fills it; `evh sheet-import sheet.csv --dataset-id D --by
  WHO` reads it back: a `label` column as a label set (`--set S`; `--kind model` when a tool filled it), a `pick`
  (`A|B` for a tie) or `score:` columns as judged runs under `data/runs-judged/<scorer>/` (`--scorer S`), one per
  arm, with `judge_won_unvalidated` or `judge_score_unvalidated` per item: unvalidated until the same judge is
  validated as any judge is. A row or text the key does not have, a letter not on its row, a score off the scale
  and a name already used are refused, and nothing is written.
- **Picks** wait in `data/picks.jsonl`, append-only: the latest line for an item wins; `pick --drop` takes
  one off. `dataset-extend` makes V2 of V1's items and the picks chosen, records `extended_from`, and the
  picks used leave the list; labels follow the items into V2. Nothing is promoted by it.
- **The deploy sheet** is what production must match to run what was measured: the model and its record,
  every setting sent (and a record's setting that was not), what each item reported, the adapter. With a
  capture, each record's account (the adapter's `production_ran(record)`) is checked against it; it exits 1
  unless every record matches.
- **Several projects at once**: each serves its catalog on a port of its own (18000–18999) and its MCP
  server on another (19000–19999), the same every time, the next free one if taken; a local catalog names
  its project in its header.

## 16. Set up a model before you test it

An arm is a model *and how it is called*. Servers and providers choose defaults for what an arm leaves
unset — whether the model reasons first, how long a reply may run, which build of the weights a tag
names — and those defaults differ from model to model. An arm that leaves them unset compares the
defaults as much as the models. Settle them before the full run, on purpose, and write them down
(RFC-020, RFC-021).

```bash
evh model-onboard gemma4-12b --deployment mac   # once per deployment: build, reasoning, JSON, determinism
evh arm-smoke --config configs/my_arm.yaml       # once per arm, on its own task, before its full run
evh models                                       # what is onboarded, vetted (an arm smoke passed), where it runs
```

1. **Pin the build, per deployment.** Record the tag and its digest in the model record
   (`data/models/<model>.yaml`) as one entry of `deployments`, one per place the model runs (`mac`, `dgx`,
   `x3`, a hosted route with its `provider_routing`). One tag name can name different builds on different
   machines (an MLX build on a Mac, an older pull on another host): compare digests across every deployment
   that will run the arm, and against the registry, before the first run. `evh model-onboard <model>
   --deployment dgx` probes one deployment and writes its onboarding. An arm names the record and the
   deployment (`model_record: gem`, `deployment: dgx`); its run's fingerprint then takes the weights, server
   and hardware from that entry (`source: record`), and `metrics.json` records `deployment_id`.
2. **Smoke a few items.** `evh arm-smoke --config <arm>` runs three with the arm's own settings and writes
   no run: each item's time and output, whether the scorer can read it, a projection of the full run, and
   whether the same item twice gives the same output. For an LLM arm it measures every model call: tokens
   out, whether it reasoned, whether an answer came back, why it ended. An adapter that makes several calls
   per item reports them as `meta["calls"]` (the triage example does). SMOKE CHECK lists what to revisit.
3. **Choose the settings on purpose.**
   - *Reasoning*: off (`reasoning_effort: none`) unless the task needs it; some models only offer low,
     medium or high. Left to the default, one model reasons at length and the next not at all, and a
     reasoning model can loop without ever answering.
   - *A reply cap* (`max_tokens`): a few times the longest normal answer. Without one, a reply is
     unbounded and a loop runs until the call limit.
   - *A call limit* (`call_timeout_s`, seconds; the built-in providers pass it to the SDK as its timeout,
     whose own default is 10 minutes): a few times the slowest normal call, not the slowest model's. A
     generous limit on a fast model only makes its failures slow.
   - *The server's own settings*: context length, quantization, KV cache — the same everywhere the arm
     runs. They are the deployment's: its `server_settings` in the record, not the record's `settings`.
4. **Write them down**, each where it holds. In the model record: each deployment's build, the settings
   that hold whatever the task (reasoning; an ML model's device and precision) with one line of why
   (`settings_why`), and each change in `history`. In the arm: the task's own (its reply cap, its call
   limit), with a comment saying why; the schema refuses them in a record, where they would reach every
   other eval's arms. The arm smokes are kept in the record, and an arm smoke that passed is what makes
   the model *vetted* on the Models page.
   - *Onboarding finds the settings that work*: probe, read the flags, change the record's settings (with why),
     probe again, until it passes or what remains is the model's own nature. Some models cannot stop reasoning
     (gpt-oss: `none` and `low` both reason; a hosted route answers "Reasoning is mandatory"): set the least they
     take and accept the flag in the record, `accepted: {reasoning: "<why>"}`. Onboarding and arm smokes then
     report it as accepted, with the why, and do not count it against the status. What one deployment always
     raises goes on that deployment, `accepted` under it: a hosted gateway has no build to pin (`where it ran`)
     and its repeats vary (`determinism`); another deployment of the same model is still checked.
   - Several machines may be onboarded at once: each command writes only its own deployment (or smoke) into the
     record, re-read under a lock, so one never erases another's result.
5. **Know what a repeat measures.** A self-hosted model at temperature 0 gives the same output on the same
   machine every time: a second pass there adds nothing. The spread comes from other machines and other
   builds; a hosted model's repeats do vary.

## Exit codes

Every command, `make` target and `evh` subcommand, for scripts and CI that branch on them:

| Exit | Meaning | From |
|---|---|---|
| `0` | done | every command |
| `1` | refused, or nothing was measured: `ERROR: <why>` on stderr | every command |
| `2` | a usage error: an unknown command or argument (the usage is printed) | `evh`, every command's argument parser |
| `2` | stopped early by the cost cap; the partial results are kept and resumable | `evh run`, `judge-score` |
| `3` | the judge scorer is not validated; `--unvalidated` runs it labelled as such | `judge-score` |

The two meanings of `2` are told apart by stderr: a usage error prints the usage, a stopped
run prints how many items it measured and how to resume.

## Environment variables

Read from the environment or the project's `.env` (an exported value wins; `evh init`
gitignores `.env`, so a key in it is never committed). Which provider you use is your choice,
and the key is yours: [tutorial 2](../../docs/tutorials/2-hosted-llm.md#1-choose-a-provider).
`evh env-check` reports what is set. In a checkout, `harness/.env.example` carries the ones a
project usually sets, with the reasoning. The harness's commands read
`.env` when they start; a program that only imports the harness (an adapter's own tests, a
notebook) reads no `.env`, and the project's paths are resolved on first use, so it can set
`EVAL_HOME` after the import.

| Variable | What it does |
|---|---|
| `EVAL_HOME` | the project root (default: the nearest directory up from where you run that has `data/`) |
| `EVAL_DATA_DIR` | the data root, when it is not `<project>/data` |
| `EVAL_RUNS_DIR` | read and write runs here instead of `data/runs` (`validate` too) |
| `EVAL_GOALS_DIR` | read goals here instead of `<data>/goals`, relative to the project (for goals kept outside the data root) |
| `EVAL_MAX_COST_USD` | per-run ceiling on billed spend; the run stops, keeps its results, resumes |
| `EVAL_MAX_RETRIES`, `EVAL_RETRY_MAX_DELAY` | retries around every provider call |
| `EVAL_BUILD_REF` | the identity of the system under test (default: the git SHA) |
| `EVAL_HOST_LABEL` | a name for this machine, the runner (fingerprint v5's `runner.label`, outside its hash): latency of a model run in process, and the network part of a remote one, is comparable across runs only from the same runner |
| `EVAL_FINGERPRINT_WEIGHTS` | `1`: hash a local model's weight files into the fingerprint |
| `EVAL_MODELS_FILE` | the alias to upstream-model table judges are routed by |
| `EVAL_FETCH_HEADERS` | JSON `{"host": {"Header": "value"}}` for URL items behind a login |
| `EVAL_NO_CACHE` | `1`: `family-test` recomputes instead of replaying an identical earlier run |
| `EVH_P_CACHE` | a file that keeps every estimated p of the paired test between processes (one JSON line each, read back exactly); `evh mcp` sets it to `<project>/.cache/evh-p.jsonl`. Unset by default: nothing is stored. A file that cannot be read is no cache; a read-only one is read and never written |
| `OPENAI_API_KEY` (and `OPENAI_BASE_URL`) | `provider: openai`: OpenAI, or any OpenAI-compatible endpoint; an arm's `api_key_env` names another variable |
| `OPENROUTER_API_KEY` | `provider: openrouter` (OpenRouter's address by default; an arm's `base_url` or `api_key_env` overrides it), and judges routed straight to OpenRouter |
| `ANTHROPIC_API_KEY` | `provider: anthropic` |
| `LITELLM_BASE_URL` + `LITELLM_API_KEY` | `provider: litellm`, a LiteLLM proxy, and judges routed through it (a judge takes the proxy when both it and `OPENROUTER_API_KEY` are set) |

---

## Choosing what to evaluate against

The **system under test** is recorded as `build.ref`. It defaults to the project's
git SHA, which is right only if the project *is* the system under test.

Declare it instead. No code edit:

```bash
EVAL_BUILD_REF=v2.3.1                evh run --config ...
EVAL_BUILD_REF=sha256:ab12…          evh run --config ...   # image digest
EVAL_BUILD_REF=$(git -C ../my-system rev-parse HEAD)   evh run --config ...  # the system's repo
```

**Pin it.** An eval against a moving target measures the target's movement, and
you will spend a day attributing that to your change.

`evh validate` fails on any run whose build is `unknown`, and `evh run-promote`
refuses one — a baseline that names no system cannot be acted on.

---

## When a number looks wrong

In order, because each is cheaper than the next:

1. `evh validate` — is the tree even consistent?
2. `evh runs-list` — was the run from a dirty tree?
3. `--repeat 3` — is the delta inside the arm's own spread?
4. Same `dataset_id` on both sides? (`run-compare` refuses, but check the ids)
5. Scored against **silver**? A run's `metrics.json` records `reference_tier` — silver
   ranks arms, it does not establish correctness.
6. Did a source change? `evh dataset-materialize --dataset-id ... --force`
   re-verifies every hash.
7. Do the runs share their conditions? `evh run-compare` names the fingerprint part that moved
   (instrument, data, deployment, settings); `evh inspect --runs a,b` names every condition that differs
   (the runner's machine and libraries, where the deployment ran, harness, scorer, items, reference bytes).
   The runner (where `evh` ran) is outside the fingerprint's hash: the same deployment run from two machines
   is the same measurement, and the runner is shown as a condition.

Most "regressions" are one of the first three.
