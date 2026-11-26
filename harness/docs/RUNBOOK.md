# Runbook — from raw inputs to a defensible baseline

Follow this top to bottom: every step, with the reasoning attached, as `evh` commands in a
project that pins the package. You should not need to open a script. In a checkout of this
repository each command is also a `make` target (`make pair-test DATASET_ID=… A=… B=…`, flags
through `ARGS="…"`); `make help` lists them.

New here? **[Getting started](../../docs/GUIDE.md)** walks the loop once, offline, with the real
output of every command, and the [tutorials](../../docs/GUIDE.md#where-to-go-next) take it
further. This page is the reference for each step.

## Every command

The loop comes first; the rest, by what it is for, below it.

### The loop

What [Getting started](../../docs/GUIDE.md) walks: a dataset, its reference, runs, a comparison, a choice.

| step | command |
|---|---|
| start a project | `evh init --store files\|sqlite [--tutorial]` |
| what is configured | `evh env-check` |
| freeze | `evh dataset-create --dataset-id … --source-dir … [--licence ID]` |
| materialize | `evh dataset-materialize --dataset-id …` |
| a person's labels | `evh label-sheet --dataset-id … --out sheet.csv` · `evh label-import --sheet sheet.csv --dataset-id … --set … --by …` (or a folder of `<item_id>.txt`) |
| a reference (labels you promote) | `evh reference-promote --dataset-id … --labels … --tier gold\|silver --reason "…" --by …` |
| cost before spending | `evh run --system … --dataset … --dry-run` |
| measure (+ own noise) | `evh run --system … --dataset … [--goal G] --repeat 3` |
| many systems | `evh sweep --systems A B … --dataset …` |
| list runs | `evh runs-list` |
| rank, with the test | `evh leaderboard …` |
| two runs | `evh run-compare --baseline … --candidate … --noise …` |
| a pre-named pair | `evh pair-test … --a … --b …` (or `--round rN`: A its leader, B the baseline it started from; a leader chosen from the table is corrected for the comparisons it could have been, every arm in play but B). A `hypothesis:` committed in A's system before the run is what makes the pair "named in advance" (§4) |
| a winner claim | `evh family-test … --a … --against …` |
| what it is for | `data/goals/<goal_id>.yaml` (every field: [§4c](#4c-the-goal-file-field-by-field)); a run names it with `evh run --goal <goal_id>` |
| baseline | `evh run-promote --run … --reason "…"` · `evh baselines` · `evh baseline-rollback --goal G --dataset D --to N --reason "…"` |
| browse and inspect | `evh catalog` · `evh catalog-serve` · `evh dataset-profile` · `evh dataset-items` |
| consistency | `evh validate` |
| does the installed harness work here | `evh self-test` |

### Datasets

| step | command |
|---|---|
| a licence, a description (no new version) | `evh licences` · `evh dataset-describe --dataset-id … --licence …` |
| the card; as Croissant 1.1 | `evh dataset-card …` · `… --format croissant --creator … > card.json` (it prints; redirect it) |
| a new version | `evh dataset-create --dataset-id …_v2 --source-dir … --from …_v1` |
| fields on an existing dataset | `evh dataset-create --dataset-id … --update-fields --fieldset … --fields …` |
| validation and test | `evh dataset-split … --test 0.3 --seed 7 [--key F]` · the split rule is `--split-by hash\|time` (hash is the default, and the seed applies to hash; the hash split's share is approximate, each item picking its side on its own: `--test 0.4` on 20 items can give 10 and 10) |
| a sealed held-out side | `evh dataset-split … --split-by time --key F --at T --seal [--count-by F,…]` · Each side gets the parent's references on its own items, promoted from the same label set at the same tier, recorded with who split it; an existing reference is kept; the sealed test side gets none and the command to run after unsealing is printed. A parent with references needs `--by` or `EVH_ACTOR` (bad-argument otherwise). `evh dataset-unseal …_test --system S --reason "…"` |
| who read a held-out item; counts only | `evh exposure-add --dataset-id …_test --item ID --what "…"` · `evh exposure` · `evh exposure-check --dataset-id …_test` · `evh sealed-counts …_test` · `evh dataset-seal-counts --dataset-id …_test --add F --reason "…"` |
| pick for the next version | `evh pick --dataset-id … --item … --for V` · `evh picks [--for V]` |
| the next version of a dataset | `evh dataset-extend --dataset V1 --dataset-id V2 --picks` (or `--pick ITEM …`) |

### Labels, references and scoring

| step | command |
|---|---|
| a model's labels (a run's outputs) | `evh label-from-run --run <run_id> --set … [--not-redistributed]` |
| the label sets | `evh label-set-list …` |
| how arms fail (failure modes) | `evh sheet-export --dataset-id … --runs A,B --csv tags.csv --fill tags --modes …` · `evh sheet-import --sheet tags.csv --dataset-id … --by … --tags … --modes …` · `evh tag-set-list …` |
| gold a script builds, promoted | `evh reference-manifest --reference-id gold/… --source … --labelled-by … --reason "…" --by …` |
| score against labels | `evh rescore --dataset-id … --labels …` · `evh run --system … --dataset … --labels …` |
| re-score, $0 | `evh rescore --dataset-id … [--reference-id gold/…]` |
| re-measure with a judge (optional) | `evh judge-score --dataset-id … --scorer … [--dry-run]` |
| read the judged runs | `evh leaderboard … --label judged/<scorer>` |
| is silver good enough | `evh silver-calibrate --dataset-id …` |
| scores made elsewhere | `evh import-run --dataset-id … --system-id … --scores … --scorer-file …` |
| billed cost | `evh cost-report` |

### Statistics beyond the pair

| step | command |
|---|---|
| how many items | `evh rank-stability …` |
| pilot-slice-free result | `evh holdout --dataset-id … --exclude-dataset …` |
| rounds (optional) | `evh round-open` · `evh round-retire` · `evh round-close` · `evh round-list …` · `evh round-evidence …` |
| a result with and without a set of items | `evh pair-test … --items FILE` (only the ids in the file, one per line; the rest is a second file, or `--exclude-dataset D` when the set is a dataset) · `evh comparison-show --runs A,B --where F:V` (the items with that field value; a boolean or choice field marking the set) |

### Reading results

| step | command |
|---|---|
| the same, in the terminal | `evh overview-show [--period P]` · `evh activity-show` · `evh dataset-list` · `evh arm-list` (`--systems 1`) · `evh arm-show LABEL DATASET SYSTEM` · `evh reference-list` · `evh metric-show …` · `evh goal-list` · `evh goal-leaderboard G [--arms PATTERN] [--top N]` (a goal with many arms: only the arms matching, or the first N, always with the baseline, the leader and the recommended arm; each arm's paired test against the leader) · `evh search …` · `evh comparison-show --runs …` (`--analysis`) · `evh comparison-item --runs … --item ID` · `evh sheet-show … --runs …`; every list takes `--period P` |
| the evidence drawn (RFC-034): a round's or a study's gain against cost, each arm against the leader, a study's trials, rank stability, latency, label or judge agreement, arms by items, a goal or a code record over time | `evh chart gain-cost --goal G --round R \| --study S` · `evh chart intervals\|latency\|items --goal G [--dataset D]` · `evh chart study-progress --goal G --study S` · `evh chart rank-stability --dataset D [--metric M]` · `evh chart agreement --dataset D \| --scorer S` · `evh chart trend --goal G [--dataset D] \| --model M`; each with `[--json] [--svg FILE]`: the table it draws, its caption, the drawing as SVG |
| where arms decided differently | `evh comparison-show --runs A,B --disagree` |
| the sheet: every item, every arm's output and scores, the labels, the winner, the signals | `evh sheet-export --dataset-id … --runs A,B --csv FILE [--wrong-against SET] [--new-vs V] [--fill label\|pick\|scores\|tags]` (the API: `POST /api/v1/datasets/{dataset}/sheets`, a job keeping the sheet and its key) |
| how two per-item scores relate, by a recorded field (a gate that saved a false dismissal, one that cost a false alarm) | `evh comparison-crosstab --runs A --crosstab M1,M2 [--group _meta.gates [--group-match REGEX]] [--where F:V]` ([§14](#14-browse-the-catalog-and-the-inspector)) |
| why items flipped: each run's whole output beside the reference, many items at once | `evh comparison-items --runs A,B [--disagree] [--where F:V] [--max-chars N] --json` ([§14](#14-browse-the-catalog-and-the-inspector)) |
| a sheet filled elsewhere, read back | `evh sheet-import --sheet sheet.csv --dataset-id … --by WHO [--set S \| --scorer S] [--key K \| --export-job JOB]` (`--export-job`: the key the sheet-export job kept, never served) |

### Production

[§15](#15-datasets-from-production-the-capture-lane) onwards.

| step | command |
|---|---|
| keep a production system's records | `evh capture --importer jsonl --query '{"path": "export.jsonl"}' --capture c1` · `evh capture-list` ([§15](#15-datasets-from-production-the-capture-lane)) |
| test an importer | `evh importer-check --importer path/to/importer.py:Importer --query …` |
| scrub a capture | `evh capture-scrub c1 --command "python scrub.py {records}"` |
| a capture's records again (a fresh clone) | `evh capture-restore --capture c1 [--query path=…]` |
| a dataset from a capture | `evh dataset-from-capture --capture c1 --dataset-id … [--where F:V] [--one-per F] [--tag K=V]` |
| labels from what happened afterwards | `evh label-from-capture --dataset-id … --capture c1 --map rules.yaml --set …` |
| how far outcome rules label a dataset now | `evh label-coverage-show … --capture c1 --map rules.yaml` |
| an outcome from another system; relabels that only add | `evh label-from-capture … --outcomes C2 --join F=F --within -1m,+15m` · `… --set s2 --from-set s1` · `evh label-coverage-show … --from-set s1` |
| the labeller tested; labels where production is reproduced | `evh label-mutants … --capture c1 --map rules.yaml` · `evh label-from-capture … --reproduced-by REPLAY_RUN --production RUN` |
| production's own decisions as an arm | `evh arm-from-capture --dataset-id … --capture c1 --as production_v1 [--like SYSTEM]` ([§15b](#15b-evaluating-what-production-did)) |
| what production must match | `evh deploy-sheet S [--capture C]` |
| replay the code that ran, item by item | `evh run --system REPLAY --dataset …` (a system with `replay:` and `model_record:` a `kind: code` record) · `evh model-show …` ([§15c](#15c-replaying-the-code-that-ran)) |
| is the replay faithful to production | `evh faithfulness --system REPLAY --dataset … --production RUN` · `evh faithfulness-show …` · `evh faithfulness-name --model … --item … --cause "…"` |
| a past period at its own code, beside a candidate | `evh periods …` · `evh period-compare REPLAY --dataset … --candidate C --production P --period N` |

### Agents and jobs

| step | command |
|---|---|
| ask from an agent | `evh mcp` |
| background jobs (the Workbench's) | `evh jobs-start run --arg system=ID --arg dataset=D --max-cost-usd N` · `evh jobs-status [--state S,S] [--operation OP] [--goal G]` · `evh jobs-logs JOB --follow` · `evh jobs-stop JOB` · `evh jobs-resume JOB` |

---

## 0. Prove it works before you touch it

In a project that pins the package:

```bash
evh self-test
```

That runs the full development suite in a checkout, or the installed package's own suite end to end in a scratch folder,
offline and at $0. No API key. If it
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
`evh dataset-show my_v2` prints the lineage, the catalog links the versions both ways,
and `validate` V2 fails a version whose parent is gone. "What did the new version change for this
arm?" is `evh pair-test my_v1 --a ARM_v1 --b ARM_v2 --b-dataset my_v2`: the arm's runs
on each version, paired by item id (below, under `pair-test`).
A version made without `--from`, and already cited by runs, gains the link afterwards:
`evh dataset-create --dataset-id my_v2 --from my_v1 --lineage-only` records the parent and what changed, and
recomputes the version from it; the items, `created_at` and the rest of the record are untouched, so no run moves.
It refuses a dataset that already names another parent, a split side (its split is its lineage) and a loop.

**The version number** in the dataset file says how far the items moved; the id stays the identity. It is
MAJOR.MINOR, two integers (1.10 follows 1.9), and the harness computes it: a first dataset is 1.0; one made `--from`
another (or by `dataset-extend`) that only adds items is the parent's MAJOR with MINOR + 1; one that removes or
changes any item is MAJOR + 1, MINOR 0; the same items under a new id keep the parent's. Each side of a split is a
new dataset at 1.0 and names its parent's version (`split.from_version`). A licence or description change is not a
new version. `validate` (V22) recomputes the number; `evh migrate` writes it for records in the old layout.
A source's own version (a Hub revision) is never this number.

**A licence** is optional: `--licence ID` on `dataset-create`, or `evh dataset-describe --dataset-id D --licence ID`
on a dataset that exists (no new version: the items are the same). `evh licences` lists the ids, SPDX's, a line
each on what the licence allows (`--search`, `--json`); `unknown` when the source states none, `LicenseRef-<name>`
for a licence of its own. A split side and an extended version keep their parent's.

**Where the items came from** is the record's `source` block, the same keys whatever the source: `provider`
(huggingface, kaggle, openml, croissant, url, folder, or a project's own), `ref` (its name for the dataset),
`url`, `revision` (its own version of it, never the dataset's `version`), `config`, `split`, `gated`,
`description_sha256`, and `item_url`, a template for one item's page with `{row}` or `{item_id}`; a value nobody
recorded is null. A fetcher writes `data/sources/<dataset_id>.rows.json` beside the items (the block, the template
and per item its row and sha256, as `examples/_shared/hf_rows.py` does); `dataset-create` reads it into the record,
a row only for an item whose bytes are the ones written, and the profile and catalog link each item from it.
Splits and extensions keep the parent's block.

**A dataset source** reads items from anywhere through one interface: `evh dataset-create --dataset-id D --source
NAME --query '{…}'`. A source is a class `Source(options)` with `describe(query)` (its `source` block, and when it
knows them `licence`, `description`, `card`, `features`) and `items(query)` (per item its `item_id` and `text`,
`file` or `source_url`, with `row` and `fields`); the items are written to `data/sources/D/`, which is refused when
it already has files (`--force` replaces them). It is found by name as an importer is: a built-in (`folder`,
`manifest`), the project's own `data/dataset_sources/NAME.py`, or `path/to/source.py:Class`. `--source-dir` and
`--manifest` are the same two built-ins read in place.

**From a Croissant description** (Hugging Face, Kaggle and OpenML publish them): `--source croissant --query
'{"url": "…", "record_set": "default", "text": "text", "id": "id", "fields": ["label"], "limit": 200}'`.
It reads a record set whose fields are columns of one parquet, CSV, JSON or JSON-lines FileObject, checked against
its sha256, and records the source block (the publisher's version as `source.revision`), the licence when `evh
licences` knows it, and the `rai:` properties as the card. A FileSet (many files) is refused: which files it holds is
the host's to say, so a Hugging Face description, whose parquet is a FileSet in the dataset's repository, is refused
(listing those files needs the Hub itself): read it with the `huggingface` source instead.

**From the Hugging Face Hub**: `--source huggingface --query '{"ref": "fancyzhx/ag_news", "split": "test",
"text": "text", "fields": ["label"], "limit": 200}'` (`config`, `id`, `offset` and `revision` too). It reads the
Hub's parquet conversion of the split at one commit, each file checked against the sha256 the Hub lists, and records
that commit as `source.revision`, so the same query with `"revision"` reads the same bytes again; the viewer page
of each row is its link. The card's licence and its metadata (tasks, annotators, language and source datasets) fill
the licence and the card. A gated dataset's token goes in `EVAL_FETCH_HEADERS`; `HF_ENDPOINT` names another Hub.

**From Zenodo**: `--source zenodo --query '{"record": 42, "file": "x.csv", "text": "…"}'` reads one parquet,
CSV, JSON or JSON-lines file of a record, checked against the md5 Zenodo lists; the record id (a version's own) is
`source.revision`, the concept record `source.ref`. **From OpenML**: `--source openml --query '{"dataset": 61,
"text": "class"}'` reads the dataset's parquet copy (OpenML lists an md5 only for its ARFF file, so those bytes
are not checked against the source; each item is still frozen by its sha256), with its version and its features'
types. `ZENODO_ENDPOINT` and `OPENML_ENDPOINT` name other servers.

**From Kaggle**: `--source kaggle --query '{"ref": "uciml/iris", "version": 2, "file": "Iris.csv", "text":
"Species"}'` reads a table file of a dataset's zip at a version (the current one when none is named; recorded as
`source.revision`), through Kaggle's own API: no kagglehub, and no credentials for a public dataset (a private one
takes them in `EVAL_FETCH_HEADERS`). Kaggle lists no checksum; each item is frozen by its sha256. Its licence name
is mapped to SPDX when it is one of Kaggle's picker's.

**Publishing to the Hub**: `evh dataset-publish --dataset-id D --to huggingface --query '{"repo": "owner/name"}'`
writes a new repo, private unless `"public": true`: the items as `data/test.parquet` (item_id, text,
source_sha256, each field), the record as `evh/D.json` and the card as README.md, in one commit; it reads every
file back at that commit and checks its sha256, and each item's text against its own, and records the publish on
the dataset (`published`: repo, revision, url, private, when, each file's sha256; no new version). It refuses a
repo that exists, items not materialized here, and a dataset whose text is hidden. The token is huggingface_hub's
(`HF_TOKEN`, or `hf auth login`).

**A source before a dataset**: `evh source-preview --source NAME --query '{…}' [--rows N]` prints what the source
describes and its first items (the start of each text, its answer when the query names one), writing nothing under
data/; the API's `POST /api/v1/source-previews` runs it as a job.

**The dataset's own answers**: a source's query may name the expected answer's column, `"answer": COLUMN` (the
huggingface, croissant, kaggle, openml and zenodo sources read it). `dataset-create` then writes those answers as a label set,
`answers` by default (`--answer-set NAME`), of source `dataset` (the provider, the column, the pinned revision), frozen
as every label set; `evh reference-promote --dataset-id D --labels answers --tier gold --reason "…"` makes it the
reference. A dataset made again with `--force` is refused while that set exists: name another with --answer-set.

**A field set from a source's features**: `evh fieldset-propose --source NAME --query '{…}' --fieldset-id ID`
prints a field set from what the source describes: each feature's type as the field set's (schema.org's, Hugging
Face's and Python's spellings), a text feature with at most `--max-choices` distinct values among `--sample` items
as a choice of them, the items' text and id left out. Read it; `--write` writes `data/fields/ID.yaml` (never over
one that exists), and `dataset-create --fieldset ID` uses it as it is.

**The card** answers the datasheet questions (what the dataset is for, how it was collected and labelled, its
biases and limits, who maintains it) under Croissant RAI 1.0's property names, so an export writes them as they
are: `evh dataset-describe --card-template > card.yaml` prints each key with its question, `evh dataset-describe
--dataset-id D --card card.yaml` records the answered ones (it replaces the card; no new version). All optional;
`validate` (V22) refuses a key that is not one of them. `evh dataset-card D` prints the card (what
the dataset is, where it came from, each answered question); `--format croissant [--creator NAME] [--out F]`
writes it as Croissant 1.1 JSON-LD: the record (licence as its SPDX page, the card as `rai:` properties, the parent
as PROV-O's `prov:wasDerivedFrom`), its files with their sha256, one record set of the items with the field set's types. A required
property the record cannot give (a creator, a url, a licence) is left out and named on stderr. The document is
checked against the spec's keys; it is not run through `mlcroissant`, which the harness does not depend on.
`--format hf-readme` writes a Hugging Face dataset README: the Hub's metadata keys (`license` as the Hub spells
it, `pretty_name`) and the card's answers under the Hub template's headings (Uses, Dataset Creation, Annotations,
Bias, Risks, and Limitations, …); an unanswered question and an `unknown` licence are left out. `validate` (V22) refuses an id
not on the list. The line is a picker, not legal advice: the licence text is what binds.

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
leaves out is kept. The rest of the record (its card, tags, split, hidden-text flag) is kept too. Fields are not the dataset's
identity: runs hash the items' bytes, so correcting a field invalidates no run, and
`fields_sha256` records that the fields changed. `--update-fields --fieldset tickets` attaches
a field set to a dataset that had none. `evh validate` (V15) checks every
value. The catalog summarises a field's values only when it is `public`; the local
inspector shows them all, filters a comparison by them, and breaks it down by a
`choice` or `boolean` field.

**Items that live at a URL** come in through a manifest, one row per item:
`item_id`, `source_url` and `source_sha256` (leave the hash empty and the bytes are
fetched and pinned now), plus any field columns. A `source_url` may also be a path inside the project (relative to its
root, e.g. `records/sources/x/p01.txt`) when `source_sha256` pins it: the harness does not read a local path to hash it,
so a local row with no hash is refused at create naming the row. `dataset-materialize` reads the file and checks the
hash; `validate` (V4) fails a file whose bytes changed and notes one that is not there:

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
system names no `adapter:` uses it (and records `adapter.py`); without one, the adapter
bundled with the harness runs. A project with several tasks names one per arm,
`adapter: adapters/ner.py` (a top-level key of the system's YAML, beside `params:`, not in it), relative to the
system or the project:

```python
from evaluation_harness.adapter import Result

def call_system(text, params):
    from myproject.summarise import summarise      # your existing code
    out = summarise(text, model=params["model"])
    return Result(output=out.text,
                  tokens_in=out.usage.prompt_tokens,
                  tokens_out=out.usage.completion_tokens)
```

Then describe each system in `data/systems/<system_id>.yaml` — the knobs belong in the
system, not in code, so it is reproducible and diffable. A system names no dataset: a run puts it
on one (`evh run --system my_system_v1 --dataset my_v1`), and the same system runs on any:

```yaml
system_id: my_system_v1
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
comparison named before the results were read. When a system is a change you expect to matter, write the
prediction into it, beside the change, and commit it before `evh run`:

```yaml
hypothesis:
  against: my_system_v1          # the system it is compared with (must exist)
  measure: false_alarm           # one of the arm's metrics
  direction: better              # better | worse | no-worse (not significantly worse)
  statement: "the shorter prompt lowers false alarms"
  items: data/expected_flips.txt # optional: a file of item ids expected to flip
```

`evh validate` (V20) and `evh run` refuse a block with a missing key, an unknown direction, an `against`
that is no system of the project or a `measure` that is none of the system's metrics, in words, before
anything is spent. The run copies the block into `metrics.json` (`hypothesis`) with
`hypothesis_in_advance`: `named: true` when the commit that last changed the block is an ancestor of the
run's build commit and was made before the run started, `false` when it is in no such commit, `null` (not
determinable) outside git, for a build that is not a git commit (`EVAL_BUILD_REF`) and on a dirty tree.
It is not part of the fingerprint: a hypothesis does not change what was measured. `evh pair-test --a A
--b B` prints it when A's run carries a hypothesis against B on the tested metric: `named in advance: yes
(committed <sha> before the run)`, `no` or `not determinable`, and whether the result agrees with the
stated direction (`yes`, `no`, `not shown`); a hypothesis found in A's system that its run does not carry
reads `no` (added after the run). `evh goal-leaderboard G` shows it in a `hypothesis` column beside the arm.
[ADR-0025](../../docs/adr/ADR-0025-a-hypothesis-lives-in-the-arm-config.md).

**A regression guard (optional).** A system that must give exactly what another gives (the same code at a newer
commit, a refactor, a dependency bump) says so:

```yaml
expect_identical_to: my_system_v1   # its runs must reproduce that system's, item for item, output for output
```

`evh validate` (V5) otherwise reads two systems with identical outputs as a result that was not measured or a knob
with no effect; with the declaration it reads them as the agreement asked for, and fails the guard instead when its
per-item results or its outputs differ from the latest run of the system it names on the same dataset ("must
reproduce my_system_v1: its outputs differ from …"). The run records the key in `metrics.json`; it is not part of
the fingerprint. A run made before its system said so (runs are frozen) is held to the system's declaration as it
stands. The declarations are read from every system of the project: `data/systems/` and the folders validate.json's
`systems` globs name (for systems kept elsewhere in the project):

```json
{"systems": ["projects/signal-fleet-dedup/systems/*.yaml"]}
```

**What a run records as its cost.** Each call's `cost_usd` is the provider's bill when the
response carries one (`usage.cost`), and otherwise the system's price table, tokens ×
`usd_per_mtok_in` / `usd_per_mtok_out`. With no price table and no bill the cost is unknown, not
zero. Per provider:

| `provider:` | what the run records |
|---|---|
| `openrouter` | the bill: the provider asks OpenRouter for it on every call |
| `litellm` | the proxy's bill, when the proxy passes `usage.cost` through; else the price table |
| `openai` | the price table (OpenAI's API reports tokens, not a cost); an OpenAI-compatible endpoint that returns `usage.cost` is billed |
| `anthropic` | the price table |
| `echo`, your own adapter | what the adapter returns as `cost_usd` (tutorial 1's local model returns 0.0) |

When a response reported a bill, the bundled adapter also keeps it in
the item's `_meta.usage.cost` (in `predictions.jsonl`), so an item with that key was billed and
one without it was priced from the table. `evh cost-report` sets each run's bill, summed from
`_meta.usage.cost`, against its recorded cost, and lists apart the runs with no bill there. Judges
follow the same rule (§12); their verdicts keep `usage`.

---

## 4b. Author ground truth — you cannot score quality without it

A **label** says what is right for one item, and who said it: a `person`, a `model` or a `rule`. Labels
come in **sets**, never edited (a correction is a new set), under `data/labels/<dataset>/<set>/`, and
follow an item by its bytes into any dataset holding it. A **reference** is labels promoted on purpose,
with a reason, at the tier you choose: no rule ties the tier to the source, and the reference records
both ([ADR-0022](../../docs/adr/ADR-0022-references-are-promoted-labels.md)).

Most projects have none. Run the best model you have as a system (an expensive one you would
not run in production is the usual choice), read its results, take its outputs as a model's labels,
and promote them:

```bash
evh run --system best_model_v1 --dataset my_v1
evh label-from-run --run <that run_id> --set best_v1
evh reference-promote --dataset-id my_v1 --labels best_v1 --tier silver \
    --reason "The best system we have ranks the rest until a person writes gold." --by <you>
```

Promoted as **silver**: a model's answers, consistent rather than correct, enough to rank
arms against each other; not a claim about truth. `label-from-run` calls nothing, and the set names
the run, system, fingerprint and build it came from. It refuses a run from a dirty tree or of an
unknown build (as `run-promote` does), an unfinished or derived run, and an empty output or one that
stopped at `max_tokens` (raise `max_tokens` in a new system_id; `--allow-cut-off` for outputs that end
at the cap by design). The reference records which set it was promoted from, by whom, when and why.
Commit both before the next run: an uncommitted reference makes every later run dirty.

When the texts may not be redistributed (the run's outputs quote a corpus you may not publish),
add `--not-redistributed`: the set's directory gets a `.gitignore` for its texts, and `labels.json`
records that and the command that rebuilds them; run on a checkout with `labels.json` alone, that
command writes the texts from the run again, checks them against the set's checksums (it refuses,
writing nothing, if the run's outputs changed since). A reference promoted from it is kept out of git
too, and the same promotion rebuilds its texts from the set.

Arms can be scored against a label set without promoting it, `evh rescore --dataset-id my_v1 --labels
best_v1` (or `evh run --labels`): the scores land under the runs, read under the label
`labels-<dataset>-<set>`, and every view names the set by its source, never with a tier.

Scored against silver, the arm that wrote it is graded against its own outputs: the leaderboard
marks its row (`arm *`) and leaves it out of the ordering test and the frontier ("The ordering
test and the frontier leave out <system> (it wrote the reference)"): it is the yardstick, not a
contender. The others are measured by how close they come to it, the usual way to choose a
cheaper system: pay for the expensive one once, then chase it.

**Gold** is a person's labels promoted at gold: label the items in a sheet (`evh label-sheet
--dataset-id my_v1 --out sheet.csv`, `--propose best_v1 --items all` to start from the model's
answers, `yes` taking one; where more than one answer is right, the others go in `also right`, separated by `|`),
or write one `<item_id>.txt` per item in a folder (`{"accept": ["escalate", "file"]}` for several), then `evh label-import`
it as a person's set and promote it with `--tier gold`. The sheet is CSV that Excel opens as it is (UTF-8 with
the mark Excel needs); save it back as CSV, `,` or `;` both read. `--choices file,dismiss,escalate` writes the
allowed answers into the label column's header, and the import refuses any other, naming its rows. Gold always wins over silver for new runs. Runs made before the gold set existed are re-scored against it for $0:
`evh rescore --dataset-id my_v1 --reference-id gold/my_v1`.

Gold that a script builds (a dataset's own labels, fetched from where it is published) is promoted where the
script puts it, its manifest recording the promotion as `reference-promote` does: whose labels they are, how they
are built, why and who said so, and the checksum of every item's text:
`evh reference-manifest --reference-id gold/my_v1 --source scripts/fetch.py --labelled-by "the dataset's authors"
--reason "…" --by <you>` (`--kind model` or `rule` when they are not a person's). Commit the
manifest even when the texts may not be redistributed (`--not-redistributed`): `evh validate`
(V16) then checks any rebuilt copy against it, and the catalog lists the reference as fetched.
`reference-promote` writes the manifest of the references it makes. Texts copied into
`data/references/<tier>/<id>/` with no manifest fail `validate` (V16): nothing says where they came from. Import
them as labels where they are and promote them (`evh label-import --sheet data/references/<tier>/<id> …`, then
`evh reference-promote`): the promotion adopts the folder, its texts being the labels'.

Every later run is scored against these automatically and records which tier it
used. Ten items is enough to rank four arms; keep the first pass cheap.

---

## 4c. The goal file, field by field

A goal says what the evaluation is for ([CONCEPTS](CONCEPTS.md#a-goal-says-what-the-evaluation-is-for)).
It is optional: one YAML file per goal, `data/goals/<goal_id>.yaml`, and a run names it with
`evh run … --goal <goal_id>` (the run and a baseline promoted from it carry it; a system file names no goal,
and `evh validate` refuses one that does). The schema is
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

A small complete example: the required fields, plus the `output_contract` and `references` most goals
set:

```yaml
# data/goals/summary_quality.yaml
goal_id: summary_quality
title: One-line ticket summaries
statement: Summarise a ticket in a line so the queue triage does not open each one.
decision: Which summariser to run in production.
output_contract:
  - {format: paragraph, length: one or two sentences}
success_criteria:
  primary: {measure: overlap_f1, direction: higher}
datasets:
  - {dataset_id: tickets_v1}
references:
  - {reference_id: gold/tickets_v1, tier: gold}
```

| field | allowed values | what reads it |
|---|---|---|
| `goal_id` | lowercase letters, digits and `_`, starting with a letter or digit; **equals the file name** | V14 fails a file whose `goal_id` is not its name. Permanent: a materially different purpose is a new goal |
| `schema_version` | any string (`"0.1"`) | nothing |
| `title` | any string | the goal page's heading, `evh goal-list` |
| `statement` | one sentence, "X for Y so that Z" | the goal page, `evh goal-leaderboard` |
| `status` | `active`, `draft`, `exploratory`, `dormant` or `superseded` | shown on the goal page |
| `superseded_by` | the `goal_id` that replaces this one | nothing (for the reader) |
| `context.audience`, `context.usage` | any string | `audience` is shown on the goal page |
| `decision` | the decision an answer informs | the goal page and `evh goal-leaderboard` lead with it |
| `output_contract[]` | a list of shapes, each `{format}` (required) plus optional `id`, `length`, `structure`, `language` | A system may declare `format:` (any non-empty string); when the goal has a contract, that format must be one of its `format`s (V14 fails it, and the goal page flags the arm "format f not in the contract"). `format` is your own word for a shape (`paragraph`, `label`, `json`): the harness has no list of them. A system without `format:` is not checked |
| `success_criteria.primary.measure` | a per-item metric as the runs record it (`rouge_l`, `accuracy`, `overlap_f1`) | the goal page, `evh goal-leaderboard`, `evh round-evidence` and `comparison-show --round` read the arms on it; an arm that does not record it is not listed (a judged arm is shown in its judge's group, on the judge's score) |
| `success_criteria.primary.direction` | `higher`, `lower` or `non_inferior` | `higher`/`lower` rank the arms. `non_inferior` is a guard (no significant drop against a baseline) and ranks nothing. V14 fails a direction that contradicts what the runs record, or `higher` on a cost, latency or token count |
| `success_criteria.primary.threshold` | any value | shown beside the measure on the goal page |
| `success_criteria.primary.reduce` | `mean` (the default), `majority` or `at_least_K` | how an arm's repeats make one score per item on the goal's measure: the mean, or for 0/1 scores right when more than half (or at least K) of the repeats are right |
| `success_criteria.min_items` | an integer, at least 1 | The fewest items a winner-picking comparison may rest on: an arm with fewer is flagged "n k < min_items m" on the goal page and is never a group's leader; `evh validate` notes a goal dataset smaller than it (a note, not a failure) |
| `success_criteria.axes` | a map of name → `{measure, direction, stat, limit, margin, role, unit, note}`, all optional. `cost` (`cost_usd`, mean, tokens shown beside it) and `speed` (`latency_ms`, p95) are built in and need no entry; `quality` takes only a `limit`, a `margin`, a `reference` and a `note` (its measure and direction are the primary's), and `margin` belongs to quality alone; any other name is the project's own axis, a per-item metric its runs record (`measure` defaults to the name, `direction` to what the runs record (the adapter's `METRIC_DIRECTIONS`), else the name table, else the default `higher`: nothing declares it, and a ranking on it prints a `NOTE`; `stat` to `mean`). `role: ignore` drops an axis. `limit: baseline` in place of a number: an arm is out when the paired test finds it worse than the group's promoted baseline on that axis (p < 0.05, each arm on its own, not corrected across the arms; RFC-022); with no baseline promoted, no limit applies and the decision says so | The goal's decision ([ADR-0006](../../docs/adr/ADR-0006-goal-axes-and-strategies.md)): an arm past a `limit` is out, with the reason; `margin`, in the measure's units, is how much worse than the leader an arm may be and still be a contender: the arm must be *shown* no worse by more than it (a one-sided non-inferiority test against the leader, Holm across the candidates: Tango's score test for 0/1 scores at any size, the bootstrap-t from 100 items or equal clusters, 250 effective clusters when they differ in size, for other scores, "too few items to call a tie" below). With no margin set, the strategy's default: `balanced` 5% of the leader's mean, `frugal` 10%; `evh validate` notes each goal on a default. `quality: {reference: baseline}` tests contenders against the group's promoted baseline instead ("no worse than what runs now", for a goal about replacing it; the margin is then a share of the baseline's mean; with none promoted the leader is used, and said). The decision also says which margin the group can detect at all: with k candidates on n items (or clusters), a truly equal arm is shown within about (z(1 − 0.025/k) + z(0.8)) × the paired standard error, 80% of the time; a goal margin under it rarely admits anyone. It does not count the leader being chosen from the same data, which raises the bar further. The goal page and `evh goal-leaderboard` show a column per axis; V14 refuses an unknown key in an entry |
| `success_criteria.secondary` | not allowed; the schema refuses it (V1/V14) | move its entries to `axes` |
| `success_criteria.strategy` | `balanced` (the default), `quality_first` or `frugal` | Who the contenders are beside the quality leader: `balanced` shown no worse than the leader by more than the margin (default 5% of the leader); `quality_first` the same quality only; `frugal` the same test with a wider default margin (10%), so the cheaper arm wins more often |
| `success_criteria.tie_break` | a list of axis names, default `[cost, speed]`; `quality` may be one | Among the contenders, the axes that pick, in order (`[cost, quality]`: the cheapest, then the best of the equally cheap). V14 fails a name the goal does not weigh |
| `success_criteria.guardrails[]` | `{name, rule}` (required), `source` | Rules in words that no number checks: a "guardrails" row on the goal page, a line each in `evh goal-leaderboard`; never computed |
| `datasets[]` | `{dataset_id}` (required), `role`, `cluster` (an item field: related items count once in every test), `decides` (false: the goal never decides on it), `notes`. An empty list is a goal checked by a gate rather than measured on a dataset | Each dataset gets a section on the goal page and in `evh goal-leaderboard`. `role` is free text (`validation`, `test`, `pilot`, `smoke`, `generalization`), shown beside the dataset. `evh goal-status` and the home page never ask for a baseline on a `validation` or `test` dataset: a study reads those and never promotes on them. `cluster: FIELD` names an item field whose items are not independent (one thread's comments, one document's questions): every paired test on that dataset, on the goal page, in `evh goal-list`, the inspector and `pair-test`/`family-test --round`, flips one sign per value of it, and says so. `decides: false` makes a dataset one the goal never decides on: its groups keep their leader but recommend nothing, and the home page's glance leaves it out. `notes` is shown under it |
| `references[]` | `{reference_id, tier, format}`, all strings; `tier` is `gold` or `silver` by convention, `format` your word for the reference text's shape (`label` for a bare-label gold) | nothing: which reference an arm is scored against comes from its run, not from the goal |
| `measures[]` | `{id, kind, validity}`, all strings; `validity` says how far the measure is trusted (`unvalidated`, or what it was validated against) | nothing (for the reader) |
| `links[]` | `{url, note}` | nothing (for the reader) |

`data/goals/policy.yaml` is not a goal: its one key, `required_from: YYYY-MM-DD` (a file of that single line;
you create it), makes every run created on or after that date name a goal (V14). From that date `evh run` and `evh import-run` refuse a run with no `--goal`
(`bad-argument`; `evh run --scratch` is exempt), where validate only failed it afterwards. Without it, goals are optional.

---

## 5. Measure the arm's own noise — **before** you compare anything

```bash
evh run --system my_system_v1 --dataset my_v1 --repeat 3
```

Output includes:

```text
Arm spread over 3 repeats (max - min on identical input):
  overlap_f1   spread=0.043888   treat deltas below 0.043888 as noise
```

**This step is the difference between measuring and guessing.** The spread tells you which deltas are noise.

If the spread is `0.000000`, the arm prints the word `deterministic` and any delta is real.
Write the number down; you need it in step 7. Cost and speed have a spread too, and their rows
say what they are (`latency_ms   spread=0.003833   speed, not a quality metric`): they move
with the tokens and the machine, and say nothing about whether the arm is deterministic.

The last line is per item: `per item, on overlap_f1: 3 runs, the same score on 38 of 40 items (near-copies, not independent samples); read 40 items, not 120 item-runs (pair-test counts each item once)` (the near-copies note appears when at least 90% of the items agree). The arm's spread can be 0 while items move, and repeats
that score nearly every item the same are one observation, not three: count items, never item-runs. `pair-test` does: an arm's repeats are averaged per item,
and its `repeats` line (JSON `repeats`) names each arm's runs and how many items they agree on.

`--repeat N` is refused (`would-overwrite`) when the system already has a measured run on the dataset (a previous repeat set counts too). To measure the arm's noise, repeat the run it has: `evh run --system S --dataset D --purpose repeat --of <run_id>` once per repeat (the refusal names the system's latest run), or delete it first with `evh data-rm --path runs/<run_id>`. A repeat run as that run was run (the same data, deployment, settings and adapter in the two fingerprints; a later build of the harness does not matter, and is named) joins that run's arm, which is then read as one measurement over all its runs. `evh run` says before its first call, and in its last line, whether the repeat joins, and what differs when it does not: that run is read under `repeats`, as another measurement. `--purpose repeat` with no `--of` is refused (`bad-argument`; `--scratch` excepted), and so is an `--of` that names another system's or dataset's run (`mismatch`). Not refused: `--resume`, `--scratch`, `--labels`, another `--purpose`, a pair listed in validate.json `duplicate_ok`.

When the command spent anything it prints the total over every run it wrote, so nobody adds
up `total_cost_usd` by hand across repeats (§4 says where the number comes from). The basis is one of: "(the provider's bill)", "(the system's price table: tokens x usd_per_mtok_in / usd_per_mtok_out, the provider sent no bill)", "$x the provider's bill, $y…", or the adapter's own figure:

```text
spent $0.001063 (the provider's bill)
```

---

## 6. Run the arms you want to compare

```bash
evh run --system arm_a_v1 --dataset smoke_v1
evh run --system arm_b_v1 --dataset smoke_v1
evh runs-list
```

A run is only attributable if it knows its build. `runs-list` marks runs from a
dirty tree with `*` — their `build.ref` does not describe what actually ran — and a run whose tree was never checked
(`EVAL_BUILD_REF` set, a run brought in by `evh import-run`, or no build recorded) with `?`; `--json` gives `dirty: true | false | null`, null being unknown.
A run re-scored in place or rewritten by a migration is dated by the time in its run id, not by its record's `created_at`.
**Commit before you measure** — dataset, systems, references — so the runs you keep are
clean the first time. Re-running an arm into `data/runs` after the fact leaves two
measurements of one system, which `evh validate` refuses (V8) unless `duplicate_ok` lists the pair; explore with a throwaway pass
instead (`evh run --scratch` or `evh sweep --scratch`, written under `.build/scratch/runs`, where nothing that reads runs looks).

**Prompt files, and the system's code** (RFC-028). An arm whose system reads its prompts from files declares them,
wherever they live, and every run records the version it used:

```yaml
prompts:
  summary/user: {file: prompts/summary_user.j2}
prompt_root:                     # or the directory the system loads prompts from
  name: lib
  path: ../podcast_scraper/src/podcast_scraper/prompts
  vary: [openai/summarization/long_v1.j2]
code: {path: ../podcast_scraper}  # the system's own checkout
```

- Each run hashes the declared files, records any bytes not seen before as a version in `data/prompts/<name>/` (once:
  named by its content, so runs at once write one), and records the hashes under the fingerprint's `settings`, so two
  arms that differ only in a prompt differ there and nowhere else. Untracked versions do not make a tree dirty.
- The adapter gets `params["prompts"]` (`{name: {text, path, version, sha256}}`) and, for a root,
  `params["prompt_root"]`: a copy of the directory made for this run under `.build/prompt-roots/`, removed after.
  A system run as a subprocess takes it as its prompt directory (`PROMPT_DIR=<copy>`); a library in the same process
  is pointed at it and its template cache cleared.
- `code:` records the checkout's remote, commit and changed files as `deployment.code` (its path outside the hash);
  an adapter's `fingerprint()` hook may return `code_ref` with the same keys instead, for a system the harness cannot
  read.
- `evh prompt-list [NAME]` (versions, lineage, the runs that used each), `evh prompt-diff A B`, `evh prompt-version --name NAME
  --from-file F --parent ID --note "..."` (a version with its lineage: record it before a run does, since a version is
  written once), `evh prompt-export --id ID --to PATH`. The catalog's Prompts page shows names and versions; their text
  only with `catalog: {publish: [prompts]}` in `config.yaml`. `validate` V24 checks every version against its bytes.

**Test sets and their looks** (RFC-029). A test set is a goal's dataset with `role: test`, or a split's sealed side.
Each decision written on it is a look: an unseal (`dataset-unseal`), or a promotion compared with its current
baseline there. Look k decides one-sided at 2.5%·6/(π²k²): 1.52%, 0.38%, 0.17%, ..., so looking again and again
cannot manufacture a result. One question (the two systems, the measure, the rule) is one look however often it is
asked: an unseal for a candidate and its later promotion against the same arm share it. Past 10 looks (or a goal's
`test_looks: K`) a look needs the person's own `--confirm-extra-look` (an agent cannot give it); fresh items are the
better way out. A promotion whose items could never reach its look's level (5 items reach 1/32 at best, above 1.52%)
is refused, or with the person's `--override-no-evidence` recorded inconclusive. `pair-test` on a test set labels its
answer "nominal, not a look"; `evh looks` lists each test set's looks and the next level, and a goal's page and
`evh goal-list` say it under each test set; `round-close --promote` takes the same two flags. V25 reports a number two
decisions took (two clones deciding at once).

**Studies** (RFC-029): research by ask/tell, then one confirmation. A spec names the validation dataset, the arm it
starts from, the measure, the sampler and when to stop:

```yaml
dataset: tickets_val
baseline: {system: lead1_v1}
measure: overlap_f1
sampler: grid                       # or agent, or {command: "python my_sampler.py"}
accept: {point: {min_gain: 0}}      # or test (separated as better); limits: [{metric, direction, limit}]
stop: {trials: 20, usd: 5, patience: 5}
space:
  groups:
    - {name: length, reason: how much to keep, params: {sentences: [2, 3, 4]}}
```

`stop` needs one bound: `trials`, `usd` or `wall_h`; the study ends at the first rule that fires (those, or `patience`).

`evh study-run --study <goal>/<id> --spec spec.yaml` writes the spec, opens the study's round (it holds no other round back
and closes with the study) and runs the loop: each trial is the best so far with one change, run on the validation
set, kept or dropped by the rule (its p values nominal: this is research), its limits checked against the baseline so
concessions cannot add up. With `sampler: agent` the agent asks and tells: `evh study-ask --study <study>` gives the state and an
ask id, `evh study-tell --study <study> --ask ID --proposal-json '{"params": {...}, "prompts": {...}, "hypothesis": "..."}'`
runs it (both also MCP tools, for an agent with `EVH_ACTOR=agent:NAME` and `EVH_FOR=person:NAME`). `evh study-show`,
`evh goal-list`, `evh study-stop`. A study never promotes: `evh study-confirm --study <study> --test <test set> --rule superiority`
runs the best trial and the baseline once on the test items no study saw, as one look at the set's next level, and
suggests the promotion only when the outcome meets the rule. It is a decision and needs a named actor (`--by`), except
under `--dry-run`, which prints the look and decides nothing. `evh study-import --file results.tsv --goal G --study ID` brings
a past autoresearch loop in, closed and not confirmable.

**Where runs go.** Every run goes in `data/runs/<run_id>/`, on every machine, so a run made on a
laptop and one made on a GPU box land in the same place. What is derived from a run stays with it,
read under a label of its own so it never shares a row with the measurement it came from:

- **a repeat** of a measured run (`evh run --purpose repeat --of <run_id>`; `--of` is required) is a run of its own. It
  is read in the arm of the run it repeats when it is the same measurement taken again (the same system and dataset,
  and equal data, deployment, settings and adapter parts in the two fingerprints; the harness build may differ), and
  the arm then averages them per item. A repeat that differs in one of those, whose original is gone, or whose original
  is itself read under `repeats` is read under `repeats`, with the reason. A repeat of a repeat follows `--of` to the
  first run. `--repeat N` instead writes N runs `<id>_r1` .. `_rN`, each recording its `repeat_index` (the id makes no
  set: `foo_r1` and `foo_r2` made by hand are two plain runs), read under the plain label. A closed round's numbers
  never change: a repeat that joins after it closed is listed in its "since then". A `retime` or `pair` run is read
  under its own label, and `--of` on it names a run of its own system and dataset too;
- **a re-score** (`evh rescore`) is a score under the run it re-read,
  `data/runs/<run_id>/scores/<scorer>@<reference>/`, read under `rescored <scorer>` (or `--label`);
- **a judge's verdicts** (`evh judge-score`) are a score under each judged run, read under `judged/<scorer>`, with
  the pass's checks in `data/judge-summaries/`.

`evh runs-list` names the labels present, and `evh leaderboard <dataset> --label <label>` reads one. A throwaway
pass (a smoke, a sweep you will not report) is `evh run --scratch`: written under `.build/scratch/runs`, never
committed, read by nothing.

The `.gitignore` `evh init` writes commits each run's record, outputs and scores (`run.json`, `outputs.jsonl`, and
each score's `score.json`, `metrics.json`, `predictions.jsonl`) and ignores a pass's checkpoint, `.build/` and the
SQLite database.

**Files or SQLite** (RFC-025). A project names its store; there is no default (`evh init --store files|sqlite` writes
it, and a project whose `config.yaml` names none is refused, `not-configured`). The files store keeps everything under
`data/` as files git can diff and review; the SQLite store keeps it in one database, `data/project.sqlite`:

```yaml
store: sqlite        # files or sqlite: required
```

or `EVAL_STORE=sqlite`, which wins over the file. A project is either files or its database, never
both: every command, the catalog and the inspector read and write the database, nothing under
`data/` is a file but it, and a run's outputs and rows are committed as they are produced, so a crash
keeps everything committed before it. Python code is never in the database: keep it outside `data/`
and name it by path. Move a project after setting the key, either way:

```bash
evh data-migrate --to sqlite --dry-run   # what would move
evh data-migrate --to sqlite             # every file read back by its sha256, then removed from disk
evh data-migrate --to files              # back, after setting store: files (a score's rows come back as canonical lines)
```

**A score's per-item rows in SQLite** (RFC-033, [ADR-0030](../../docs/adr/ADR-0030-per-item-results-as-tables.md)). The
database does not keep a score set's rows as lines of text. `score_sets` has one row per score set (its key is the
score's folder under `data/`), `score_rows` one per item (its `_meta`, its `_extra` and the fields that are not
numbers), `score_values` one per numeric field (the metric named once in `metrics`), `call_facts` what a run's call to
one item was, held once for every score set of the run, and `rows_partial` the crash checkpoint, verbatim. The files
store keeps `predictions.jsonl`, one canonical JSON line per item. Code reads a score set's rows as dicts in either
store (`_runs.item_rows`, `_outputs.rows`): the same dict, keys sorted, an integer still an integer and a float a float;
`_outputs.rows_text` derives the lines from them. A reader that needs the item and the numbers only passes
`meta=False`: the SQLite store then does not decode `_meta` and `_extra` and the rows it gives may lack them, while the
files store gives them whole. A line that is not a JSON object with an `item_id` is refused at write (`ERROR
(invalid-file)`) in both stores; the crash checkpoint is exempt. The files store still reads a hand-edited
`predictions.jsonl`. The rows the cache shares between readers are
the cache's own: a command that changes one copies it first, and `EVH_FREEZE_ROWS=1` (below) makes a change that does
not raise.

`data-migrate` compares every score set's rows as canonical text (`row_line` of each row), not as bytes, so the
equality it proves is of the rows' content; in either direction it writes canonical lines, so a `predictions.jsonl`
that was not in key order comes back canonical. It refuses a project whose file holds a line that is no row, until it is
corrected. Into SQLite it writes the outputs, the score sets and the `files` table in the order of each run's time
(`run.json`'s `started_at`, else `created_at`), then the key, so a run added later lands after the older ones and a
deploy's rsync of the database stays small.

`data-migrate` refuses while the project's store is not the target, while `data/` holds Python, and
while a run is still in the old layout (`evh migrate` first); a move a crash stopped is
finished by the next one. In SQLite mode a setting you write (a goal, a system) gets in through the
`evh data-put` (below), and a folder of files through `data-migrate`. `validate` V23 names a database beside files, or files beside the database; V7 and V9, which
read git, say why they do not apply. A release (`_release.py copy-data`, what a deployment ships) is files, or with
`--store sqlite` one sealed database (`data/project.sqlite` alone, out of write-ahead logging, at 16 KiB pages, and a `config.yaml` saying
`store: sqlite`), a hidden dataset's text left out either way. A database nothing may write, a release on a read-only
mount, is opened read-only when `EVAL_STORE_READONLY=1` or its folder is not writable (SQLite's `immutable` mode: no lock
file, no journal, nothing created): every read works, and every write refuses as `ERROR (not-allowed)`.

**The project's data, in either store** (PRD-016): the settings (systems, goals, fieldsets, judge scorers,
model records, failure-mode lists, `validate.json`) are created, changed and deleted with these commands; a setting
is saved only after it passes the check (it matches its schema, and, but for a system, its id is its file
name), keeping the file's comments and every line it does not change. A setting is refused when the change makes validate say something it did not say before (the change is put back, its reasons shown). Harness-written data is read-only; a run
is the one kind of data `data-rm` deletes, whole:

```bash
evh data-ls [PATH] [--find TEXT]          # the overview, a folder, or every file whose path holds TEXT
evh data-show goals/x.yaml                # one file: its text, size, sha256, and who writes it
evh data-show systems/x_v1.yaml --fields  # a setting's fields, one dotted key a line
evh data-put --path systems/x_v1.yaml --set params.sentences=2 --unset params.noise   # the form's Save, a field at a time
evh data-put --path goals/x.yaml --file x.yaml --check  # a whole file: the check alone
evh data-put --path goals/x.yaml --file x.yaml [--new]  # a whole file saved (--file - reads stdin); --new refuses a name taken
evh data-rm --path runs/<run> --dry-run          # what would go; without --dry-run, a setting or a whole run
```

`evh run` prints a `WARNING` when it writes to `data/runs` and that directory is ignored by git.
`evh validate` notes any ignored directory that already holds finished runs. The catalog reads only
the directories git keeps, so what you see locally is what a clone, CI and the published
catalog see: a throwaway pass (`evh run --scratch`, under `.build/`, or `evh sweep --scratch`) never shows up as a result.

**When the scoring changes** (RFC-022), develop it, then apply it one of two ways:

```bash
evh score-preview --goal my_goal                                    # what it would move; writes nothing
evh rescore --goal my_goal --round r1 --why "what changed, and why"  # re-score a round with it, $0
evh round-open --goal my_goal --dataset my_v1 --from r1 --keep all \
  --scoring "what changed, and why"                                  # or adopt it from the next round
```

A re-score is a score under the run it re-read (`data/runs/<run_id>/scores/<scorer>@<reference>/`), so a new
scorer never needs a directory of its own (or a `.gitignore` block). A re-score stands in for the run it re-read: the goal
pages, `evh goal-list`, the rounds and the recommendation read one row per arm, from its latest re-score against the
same reference, and say how many arms they read that way. The measured run keeps its own page, and says there, on
the arms page and in `evh arm-list` that the goals read its re-score. A round records the scorer it is judged by, and
`evh round-show` shows it with each scoring change. A goal whose first round was run as plain runs gets one with
`evh round-open --goal G --dataset D --adopt`.

**The dry run and the run's output.** `evh run --system S --dataset D --dry-run` calls nothing. Its `ESTIMATE` says what it is:
"at most ~$X, if every reply used `max_tokens` N". It counts one call per item (or the adapter's declared
`CALLS_PER_ITEM`), each the prompt in and `max_tokens` out, so it is a ceiling on the replies' length: for a model that
answers in a sentence it is many times the bill (a frontier arm at `max_tokens: 1500` was estimated at $0.76 and billed
$0.05; the 0.8.0 newcomer's was 15 times its spend). It does not bound the calls: an adapter that makes several calls per
item, or a conversation that grows (each probe turn re-sends it), costs more. Where the system's earlier runs (the latest
five) recorded output tokens, `TYPICAL` shows the same estimate at their mean tokens out per item; no recorded number
changes. Beside them, `MEASURED` shows what the last `evh arm-smoke` of this
system recorded in its model record (the cost per item, projected over the items and repeats, and when it was
measured); with none it says so and names the command (a system that names no model record has nowhere to keep a smoke: it
says so and names `model_record:`, the cap comes from the smoke's own `full run:` line, and `evh sweep --dry-run` says it
once for a model, not for each of its systems). A dataset with no reference set is a note under the dry run's header, not
an error: `evh run` is not refused for it; the bundled adapter records `output_words` only, and a project's own adapter
has its `score(output, None)` called (the checks it makes without a reference), and `label-from-run` (only when the
dataset has a run) and `label-sheet` are offered as the way to a reference set. Set `EVAL_MAX_COST_USD` from `MEASURED`, not from the
estimate. While a run goes it prints one line per finished item,
`[3/65] <item_id> <ok | error | empty | resumed | the primary metric's value> 4.2s`, with the running cost
once there is one, flushed as it is written even when stdout is a log file or a pipe (a detached job is watched
through its log). Once the estimate is 30 s or more, it adds "about N min left" (or "about N s left" under 90 s). Above 2,000 items it prints every k-th item and the last, and says so once.

**What a command may spend** (RFC-026). `EVAL_MAX_COST_USD` (a job's `max_cost_usd`) is the most one command
spends, in all: `run --repeat 3` stops at one cap, not three, and `arm-smoke` stops at it too (flagged `cost:
stopped at the cap`). The commands count what each call reports; the bundled provider layer counts the same calls
again, so an adapter that reports less than its calls cost is still stopped at the cap. `sweep` and `model-onboard`
give each child what the ones before it left (a child that is killed before it can say what it spent is counted at
all it was given).

**A cap of 0 means spend nothing.** A system runs under it only when it is known to be free before any call: a
provider of `echo`, a recorded arm (`provider: recorded`), or both `usd_per_mtok_in: 0` and `usd_per_mtok_out: 0` in the
system (a judge: provider `fake`); anything else, a hosted provider or a project adapter whatever it calls its provider, is
stopped before its first call (exit 7, nothing measured) and the message says how to declare it free. A cost of 0
reported after a call does not make a system known free.

**A round's budget is enforced.** A run (or a smoke) of an arm whose system names an open round with `budget_usd`
reserves, before its first call, the least of its own cap and what the round has left, in the round's ledger
(`.build/rounds/<goal>/<round>.json`); it spends at most that. What a round has left is its budget, less what its
runs spent, less what running commands reserved, less what a stopped or killed run's items paid (its run is not
listed, its items were paid for). So arms started at once share the budget: give each its own
`EVAL_MAX_COST_USD`, or the first takes all that is left. With nothing left a run is refused before any call
(`ERROR (over-budget)`); `evh round-evidence` shows what is left beside what was spent.

**An arm with no price is refused in a round with a budget.** What a budget counts is what runs recorded, so an arm
whose system declares no `usd_per_mtok_in` and `usd_per_mtok_out` (an explicit 0 is a price, for a model that costs
nothing per token) would be counted as $0. `evh run` and `evh arm-smoke` refuse it before any call (`ERROR
(not-configured)`), naming the arm, its model and where the prices go. `--allow-unpriced` (on `run`, `arm-smoke` and
`sweep`) starts it anyway: the round records it (`unpriced_allowed` in the round file: the system, its model, who and
when), and `evh round-show` and `evh round-evidence` say the budget leaves that arm's cost out. A round without a
budget never asks, and neither does an arm on the bundled adapter whose provider makes no paid call (`echo`): it
costs nothing. A project adapter is asked whatever its `provider` says: the name proves nothing of what it spends.

`evh run` warns, naming the items, when outputs stop at `max_tokens` (the provider's
`finish_reason`, or tokens out reaching the cap): they are scored as if complete. The harness
times every call (`latency_ms`) unless the adapter reports its own.

### When a run dies partway: `--resume`

A sweep that is interrupted — a crash, a 429 that outlasts the retries, or the
`EVAL_MAX_COST_USD` cap — leaves its finished items on disk. Outputs are written
**as each item is produced**, so what you already paid for survives.

**One item that fails does not stop the run.** A call that fails for that item (a refusal, an input the provider
rejects: an error that is not transient) is recorded in `metrics.json` (`failed_items`, with the error), its row
carries `failed: 1` (so the mean of `failed` is the share that failed), it is scored as an empty answer (0 on most
measures; an adapter that knows better defines `score_failure(reference)`), and its output is not written, so
`--resume` calls it again. Two things still stop the run: a transient error (a 429, a timeout) that outlasts the
retries, or a server that cannot be reached, exit `75` (resume later); and more than 5 failures that are also over
20% of the items called, which is the adapter or the configuration, not the items (`ERROR (failed)`).

```bash
evh run --system arm_a_v1 --dataset smoke_v1 --resume arm_a_v1_20260929T101500Z
```

The run id is the directory under `data/runs/`. It is the system id and the start time to the second; a run never writes into an existing run's directory, so a second run started in the same second takes the next second's id, and a `--run-id` that exists is refused. A run that stops, whatever the cause, prints
which run it was, after how many items, and the exact `--resume` command; or delete the
directory (until one or the other, `validate` fails V7 on it). A resumed pass **re-reads every finished output and scores
it again**, rather than skipping it — so the new run is complete, not a fragment — and
calls the model only for the items that are missing.

An item whose score is not a number (NaN, an infinity, None; the adapter's `score()` returned it) is a failed item, with its reason
(`score q is not a number: nan`), scored as a failed item is and never averaged; the run goes on, and `--resume` calls it again
(RFC-041 F7). `rescore`, `judge-score`, `sheet-import` and `import-run` refuse such a score by name; `arm-smoke` says the
item was not scored. A run recorded before this can hold such a score; every reader reads it the same way, as a failed item
scored 0, on read as on write, so the verdict on old data with one can move.

A writer records a fact a reader will follow, or refuses it by name (RFC-041 F7), before it spends or writes: a `--run-id` (and
import-run's `--system-id`, and reference-promote's `--name`) is a plain name, ASCII letters, digits, `.`, `_`, `-`, never a path,
a space or unicode (`bad-argument`); `--purpose repeat` names its run with `--of` (`bad-argument`), and an `--of` of any purpose
names a run of the same system and dataset (`mismatch`); import-run's `--reference-id` is free-form and may be kept outside `data/references/` (it
imports, with a note on stderr that the harness cannot find it; a project that keeps references in other folders names
them in its `config.yaml`, `references: {roots: [records/references]}`, each holding `<tier>/<name>` as `data/references/` does:
an id found in `data/references/` or a root is accepted without the note, `validate` (V16) checks the root's folders
against their manifests, `rescore --reference-id` reads them, and an id found in none is refused (`not-found`) naming the folders
searched; with no `references:` key nothing changes), its tier is the one given, else the id's (`gold/x` is gold; a
`--reference-tier` that contradicts a `gold/` or `silver/` id is `mismatch`, one with no reference is `bad-argument`), and `--goal` names the goal the run answers, which `evh run` and import-run both require from the
date `data/goals/policy.yaml` gives as `required_from` (`bad-argument` without one); `arm-smoke` refuses a `--goal` or `--round`
that is not there, or a `--round` with no `--goal`. A cost no item reported is no `total_cost_usd` (unknown, never `0`); every item
reporting `0` is `0.0`; only some items reporting one records `cost_coverage: {items_with_cost, items}` (the total is of those).
`goal-new` and `goal-set` say when the goal's primary measure is recorded by no run on its datasets, or its direction is neither
`lower` nor `higher`, and so does `run-promote` for a run that records no value of the goal's measure.

**An arm that calls each item once** (its adapter declares `CALL_ONCE`, or `call_once(params)`, for a call with an effect a
retry would repeat: an agent run in a container, a deploy; [INTEGRATION](INTEGRATION.md#the-second-function)) is never retried,
a transient failure included, and says so when it starts (`evh run --dry-run` too). A failed item keeps the `meta` and the
cost its exception carried (a trial's directory). Its `--resume` differs in one thing: it does not call again an item that
**may already have had its effect**. An item with an output is read and scored again; an item never attempted (no row, no
start mark) is called; an item whose row says `failed`, and an item with a start mark and no row (the process died during
its call), are listed by id with their error, stay failed items of the new run, and are not called. `evh run … --resume RUN
--recall-failed` calls exactly those, once each, and the run records them (`recalled`, in `run.json`); the flag is refused
on an arm that is not call-once and without `--resume`. The start mark is one synced line of the run's checkpoint, written
before each call (`rows.partial.jsonl`, or the `rows_partial` table), read in both stores. `evh arm-smoke` of such an arm
calls item 1 once and does not check determinism; `--repeat N` is allowed, each repeat N more real calls. `--resume RUN --dry-run` says what the resume would call (and prices only that), with and without `--recall-failed`; the Workbench's job screen lists the held items of a finished run with the same dry run and the decision to call them again.

Three things worth knowing:

- **It costs nothing to replay.** Items read from disk make no API call, and the cost
  cap cannot stop them, because they spend nothing.
- **A replayed item keeps what was measured for it** — cost, tokens, latency and
  `_meta` all carry over from the pass that produced it, and every replayed row is
  flagged `resumed: 1` so you can separate them. It reports what the *results* cost,
  not what this pass cost. The values come from the rows appended to
  `rows.partial.jsonl` as each item completes, so a crashed run, which never wrote
  `predictions.jsonl`, still carries them. A run's outputs are one file, `outputs.jsonl`, a line per item appended
  as it is produced (a torn last line from a kill is not an output, so that item is called again) and rewritten in
  dataset order when the run completes; a derived run (a re-score, a judging, a sheet import) keeps no outputs of its
  own and reads its source's (RFC-024). With the sqlite store the same outputs and rows are in tables of
  `data/project.sqlite` (the rows in the per-item tables above, the checkpoint in `rows_partial`), each committed as it is
  produced (RFC-025).
- **You cannot resume from a different arm, or from one that cannot be identified.**
  The source's system (`system_id`) and `dataset_id` are checked against the system and
  dataset you are launching and a mismatch is refused. Identity comes from `run.json`, written **before
  the first item** precisely so a crashed run can still answer the question
  (`metrics.json`, which a crashed run does not have, could not).

  A directory with neither file is refused outright, as is one whose rows were not written
  by this version of the harness.

Exit codes: `0` complete, `4` stopped early by the cost cap with usable partial
results, `7` nothing was measured at all, `75` a server could not be reached (run the same
command again; it resumes). The full table: [Exit codes](#exit-codes).

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
| `evh leaderboard …` | how do all the arms rank, on every metric at once (the columns that fit the terminal, the ranking metric first, and a line naming the rest; `--wide` or `--json` for all) |
| `evh family-test … --a … --against …` | does arm A differ significantly from a **pre-declared family**, Holm step-down. This is what every significance claim in the reports rests on |
| `evh pair-test … --a … --b …` | are these two arms different — paired, per item. Uncorrected, so only legitimate for a pair named in advance: the arm's `hypothesis:` records that it was (§4). With `--round` and no `--a`, A is the round's leader, chosen from the table, so the test is Bonferroni-corrected for the comparisons it could have been, every arm in play but B (`--family N` overrides; below 1 is refused) |
| `evh pair-test D1 --a … --b … --b-dataset D2` | **two versions of one dataset**: A's runs on D1 against B's on D2, paired by item id (the same arm on both is "what did the change do to it"). Refused, on stderr and non-zero, unless the items it uses are in both datasets by id (at least 3), the reference each arm was scored against has the same text for each of them (compared item by item by checksum; the first differing ids are named), and both arms are scored on one metric in one direction. The output says it is a cross-version comparison and names both datasets: the difference is the effect of the dataset change plus the arms' run-to-run noise, and the test cannot tell the two apart; repeats are averaged per item as in any pair-test. It names the runs of each side and the label they were read from (`--label` for another set, e.g. the re-scored runs; JSON `run_ids_a`, `run_ids_b`). A metric one side's runs do not store per item is refused as a missing metric, with what they do store (a measure computed at re-score is only in the re-scored runs). Not with `--round`; `run-compare` still refuses across datasets |
| `evh pair-test … --a … --b … --margin M` | **is A no worse than B by more than M** (in the metric's units): the contender test goals use ([ADR-0026](../../docs/adr/ADR-0026-contenders-by-non-inferiority.md)), for one pair and uncorrected: Tango for 0/1 scores, the bootstrap-t from 100 items or equal clusters (250 effective when they differ), "too few" below; with `--cluster` by clusters. JSON `noninferior` (verdict, method, p, level, units) |
| `evh pair-test … --reduce majority` | how an arm's repeats make one score per item: `mean` (the default), `majority` or `at_least_K` for 0/1 scores (`at_least_1`: did any of the repeats get it right). With `--round`, the goal's `primary.reduce` is the default; `family-test` takes it too |
| `evh pair-test … --cluster FIELD` | items that share a value of FIELD count as one: one sign per cluster (and `--margin` by clusters). With `--round`, the goal's `cluster:` is the default |
| `evh holdout --dataset-id … --exclude-dataset …` | does the result survive on the items the pilot slice never contained |
| `evh rank-stability …` | how many items before the ordering stops moving — measured, not assumed from a power table: two disjoint halves of 10, 20, 50 and 100 items where the dataset has them, plus halves of 5 and of half the dataset, so 20 items give a line (5, 10), not one point; "saturated" is read from halves of 10 up, where ties mean something |
| `evh bootstrap-test --dataset-id … --a … --against …` | a percentile interval for a corpus-level metric that has no per-item value |
| `evh rescore --dataset-id …` | recompute every score from stored outputs under the current scorer — or, with `--reference-id gold/…`, against a reference set that arrived later. **$0, no API calls** |
| `evh cost-report` | what each arm actually cost, from the provider's bill (`_meta.usage.cost` in its predictions) against the cost the run recorded; runs with no bill there are listed apart (§4); then what judging cost, per scorer, judging set and judge, from the verdicts' own cost |
| `evh silver-calibrate --dataset-id …` | does a model-authored reference rank arms the way the trusted one does |

`pair-test` and `family-test` count the exact p over all 2^n sign patterns when a pair shares 30
items or fewer, estimate it from 20,000 permutations above that, and from 10,000 items (or clusters)
take the permutation distribution's normal limit, which the estimate approaches (ADR-0028); both say
which, in the text and in `--json`'s `method` (`exact`, `sampled`, `normal limit`; `family-test`:
"p: exact, over all 2^6 sign patterns", or "p: a seeded estimate (20000 permutations, one random
stream for the family)"). A p from the limit is not a count over draws: it can print `<0.0001`
because it is 0.0. The contender test's bootstrap-t does the same from 10,000 units. Up to 30 items every command, the inspector included, prints the same
p. Above that the estimate is seeded, so it repeats, but `family-test` draws one random stream
for the whole family while `pair-test` and the inspector draw one per pair: the same pair's p can
differ in the third decimal between them (a 32-item dataset shows 0.0297 from
`family-test` vs 0.0327 from `pair-test`). The verdicts are read against the same
thresholds; a p that close to one is not a result either way. `pair-test` calls an arm significantly different from
the baseline at `p ≤ threshold`, and `family-test` marks an estimated p with `~` when the family
mixes exact and estimated rows (and a p from the normal limit with `*` when it mixes that in too). Every command prints p to four decimals, and `<0.0001` for what
would print as 0.0000. `family-test`'s `A wins-losses (ties)` column counts the items A wins and loses against each
opponent, and the ties apart; the inspector's `wins–losses` is each row's arm against the baseline.
Without `--metric` they read the metric that decides on the dataset, one answer for every command: the goal that
lists the dataset, when a run records its measure, else the primary metric the runs recorded (the adapter's
`PRIMARY_METRIC`); with neither, they refuse and name what is recorded. A goal whose measure no run records decides
nothing (V14 notes it): `evh leaderboard` of the dataset then ranks each arm on its own headline with one `NOTE`, and with
`--goal` it refuses (exit `7`, nothing measured) and names what the arms record.

Which way is better is inferred once for every command, by the first of these that answers:

1. a flag (`--asc`, `--desc`);
2. a goal that declares the measure with a `lower` or `higher` direction, as its primary measure or as an axis. For a
   question about a dataset the goals are heard in this order: a goal that lists the dataset, then a goal the runs name.
   A goal that names the dataset speaks for it; a run's `goal` only says what the run was made for, and the run may be on
   a dataset that goal does not decide. A goal on another dataset says nothing about this one. A goal with `datasets: []`
   (checked by a gate, not measured on a dataset) lists none, so it is heard only through a run that names it; a question
   with no dataset (`metric-list`, `metric-show`, a metric's page) is answered by any goal, those included. `non_inferior`
   is a decision rule, not a direction, and declares nothing. V14 fails two goals that give one measure opposite
   directions on one dataset (both list it, or both list none);
3. what the runs record: the adapter's `METRIC_DIRECTIONS`, `import-run --asc`, then the kinds they declare
   (`METRIC_KINDS`: a descriptive measure is neutral);
4. the name: **lower** is better for `cost_usd`, `total_cost_usd`, `tokens_in`, `tokens_out`, `total_tokens_in`,
   `total_tokens_out` (any name from `total_tokens`), `latency_ms`, `latency_s`, `wer`, `cer` and `der`; **neutral**
   (they say what the output was, not whether it was good, so a table prints "neutral: a description" and a movement
   reads `changed`) for `output_words`, `output_chars`, `lines`, `chars`, `n_items` and `reasoning_tokens`;
5. the default (nothing declares it): higher.

`leaderboard`, `run-compare` and `goal-leaderboard` say so in a `NOTE` line when a ranking rests on the default, and
`evh validate` notes each goal measure and each primary metric that does; declare the direction to settle it. A measure
whose datasets disagree reads "mixed", with each dataset's own answer ("lower on asr_v1; higher on dev_v1").

`leaderboard`, `family-test`, `pair-test` and `comparison-show` take `--round rN` for the arms in play in
a round (`pair-test --round`, `family-test --round` and `comparison-show --round` also default the metric to the
goal's measure; `family-test --round` tests the round's leader against every other arm in play unless
`--a`/`--against` say otherwise).
When a dataset's runs were scored more than one way, `leaderboard` prints one table for each
(`=== scored against <ref> ===`, gold first; `=== scored by judge <scorer_id> ===` for judged
runs; runs scored against none get one too), each with its own tests, under a NOTE naming them
all, and never averages across them.
`leaderboard` ranks an arm's re-score in place of the arm when every run of the arm was re-scored against the reference it
was measured on, as the goals, the rounds and the catalog read it (RFC-022): the arm it replaces is left out, and `arm-list`
names it (`superseded_by`). An arm's value in a row is the mean over its items, an item's score being the mean of its
repeats' (what `arm-show` and `metric-show` give too, where runs score different item counts); its `spread` is the range
of its runs' values.

Two that are easy to reach for and wrong:

- **`pair-test` on a pair you chose after seeing the leaderboard** is the winner's
  curse with extra steps. If you did not name the pair in advance, use `family-test`.
- **`leaderboard` as a ranking.** It sorts; it does not separate. Its own tests often cannot tell the top group apart, and the table
  still prints them 1, 2, 3.

---

## 8. Promote — a decision, not a copy

```bash
evh run-promote --run <run_id> --reason "beat prev baseline by 6% on my_v1 n=40, spread 0.004"
```

Refused if the run came from a dirty tree, if its build is unknown, if its build records `dirty: null` with no `source` (a run
from before 0.8.0, which says nothing of its tree: as `label-from-run` refuses a build git could not read), or if the
reason is under three words. Those refusals exist for the same reason: in six months, *"why is this the
baseline?"* must have an answer. `--allow-dirty` and `--allow-unknown-build` override those checks when needed.

**A baseline is a goal's, in versions** (RFC-027). It lives at `data/baselines/<goal>/<dataset>/<n>.json`: the
run's own goal by default, another of the dataset's goals with `--goal G`, and the dataset's
own (`_dataset/<dataset>/`, goal null) for a run with no goal or with `--no-goal`, for ad-hoc experiments no goal
reads. Promoting writes the next version beside the current one, never over it; two promotions at once land as
n + 1 and n + 2. `evh baseline-rollback --goal G --dataset D --to N --reason "…"` goes back, as one more version
that restores N. A goal reads its own line; the inspector's comparison, with no goal named, the dataset's own.

**The evidence is frozen in.** Each version records the paired test that justified it, against the version it
replaced, on the goal's primary measure, exactly as `pair-test` answers it (the two arms, their runs pooled and
repeats reduced as pair-test does, the goal's cluster; with `round-close --promote`, read as the round reads them):
the verdict, delta, p, n, a hash of the items compared and what it was computed with. It is never recomputed: a
later `pair-test` answers a later question. A promotion is not refused for a "not significant" or "worse" verdict;
the record and the pages show it. The first version has nothing to compare with; another run of the same arm
records no test, and says why.

The baseline also carries what its number means, from the run: the reference tier it was scored against, the
adapter that scored it, its fingerprint hash and its format (`validate` V6 fails a version that no longer matches
its run, and a line whose versions do not run 1..n).

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
    overlap_f1     0.9001   (mean of 3: 0.9001)
```

```bash
evh baselines                         # each goal's line, and each dataset's own: current, why, evidence
evh baselines --goal G --all-versions # the history
evh baselines --json                  # the export a production system reads: the same bytes until a promotion
```

`evh round-close --promote <run_id>` promotes too, with the round's conclusion as the reason
(§13).

**Who acted.** Every record a command writes names its actor (`actor` in the record): a person, or
an agent and the person it acted for. From a terminal it is your login; `--by person:NAME` (every
writing command takes it) or `EVH_ACTOR` names someone else, and an agent sets
`EVH_ACTOR=agent:NAME` with `EVH_FOR=person:NAME`, the operator who asked. It is a recorded claim,
not an identity. These commands refuse an actor they cannot name (no terminal, no `--by`, no `EVH_ACTOR`):
`run-promote`, `round-close`, `dataset-unseal`, `baseline-rollback`, `round-carry`, `dataset-seal-counts`,
`study-confirm`, `study-tell`, `faithfulness-name`, and `--unfaithful` on `run`, `rescore`, `run-promote`.
These require `--by` or `EVH_ACTOR` and refuse with `bad-argument` when missing:
`label-import`, `sheet-import`, `reference-promote`, `reference-manifest`,
and `dataset-split` when the parent has references. Every other command records it as `unknown`
and goes ahead.

---

### What another reader sees while a command writes

A command can be read from while it writes: a second terminal, a job (RFC-026), the catalog server. Every file is
written whole (a new file renamed over the old one on disk, one committed statement in the database), so a reader
never sees one cut short. What a command writes in several files, it writes in an order that keeps what the harness
lists whole (`tests/test_write_order.py` checks the three that matter by stopping each partway):

| command | writes, in order | a reader partway sees |
| --- | --- | --- |
| `run` | `run.json` (that it started), its outputs item by item, `predictions.jsonl`, then `metrics.json` last | no run until `metrics.json`: a run stopped partway is not listed, and `--resume` continues it |
| `rescore`, `judge-score` | the rows, then `metrics.json` last | no re-scored or judged run until its `metrics.json` |
| `reference-promote`, `label-import`, `sheet-import`, `label-from-*` | the whole set in a hidden folder beside its place, moved in at once | no reference or label set, then the whole one |
| `capture`, `capture-restore` | the records (a restore in a hidden folder, moved in), then `capture.json` last | no capture until `capture.json` |
| `run-promote`, `baseline-rollback` | one new version file, created exclusively | the previous version as current, then the new one |
| `dataset-split` | the validation side's record, then the test side's | the validation side alone for a moment, then both |
| `dataset-create`, `dataset-unseal`, and every other single record | one file, whole | the old record or the new one |

## 9. Validate before you trust anything

```bash
evh validate
```

Thirty checks (V1–V30): schema conformance (datasets, runs, baselines, systems, judge
scorers, judging sets, verdicts, dataset profiles), every run's `dataset_id` resolves, every run
identifies its build, materialized copies still match their hashes, no two
systems reporting byte-identical scores and per-item results (two arms with different outputs
that are both perfect are two measurements, not a copy), no baseline pointing at a
deleted run or disagreeing with it, every committed run readable and present on disk, no two runs claiming one
`system_id`, no derived run naming a scorer that is not the code in this tree, every judging
set matching its stored hash, every judge verdict naming a real set, item, pass and block,
every judge scorer yaml loading and well-formed, every goal and round well-formed and named by
every run that must name one, every item field declared, typed and matching its hash, and every
reference made by promotion (a manifest saying where it came from) with texts matching its checksums, every capture's
records matching the hashes it recorded, every model record and the systems naming it consistent, and every label set
matching its hashes and its dataset, every `hypothesis:` in a system sound (V20), and every failure-mode list well formed with every tag set naming its modes and its dataset's items (V21), and every dataset's version the one its lineage gives, its licence
on the list, its source block in form and its card's keys Croissant RAI's (V22); V24 checks every prompt version against its bytes, V25 reports a look number two questions took, V26 checks every faithfulness record and the systems naming it, and V27 examines every study and V28 names a row that is not a JSON object with an `item_id`. V29 fails a run's `of` (a repeat's, a re-timing's, a pair's) that names a run of another system or dataset, and notes, without failing, an `of` whose run is gone (the repeat is read under `repeats`) and a round that recorded a repeat under `repeats` where it now joins its arm (the round reads what it recorded), and V30 fails a harness-scored run whose reference or label set is gone, named with the file that holds the link (as V6 names a baseline's run and V14 a round's run); a goal `datasets:` entry that names no dataset is a note (a plain id fails from 0.9), and an imported run's reference outside `data/` is a note. V4
checks only datasets materialized on this machine, and names each one it could not check (a CI
job without the sources checks none: materialize first where the copy matters). Every run's outputs are readable: a derived run finds its source's (V23).

What it holds *your* project to is yours to declare, in `data/validate.json` (all optional):

```json
{
  "committed": ["runs", "pair", "repeats", "adjudicated", "judged-scorer1"],
  "floors": {"adjudicated": 12},
  "scorer_sources": [{"glob": "*", "path": ["derived", "with", "scorer"], "arms": "runs",
                      "module": "../my_scorer.py", "callable": "scorer_id"}],
  "duplicate_ok": [["my_v1", "smoke_arm_v1"]],
  "systems": ["arms/*.yaml"]
}
```

`committed` is the arm label prefixes (`runs`, `pair`, `repeats`, `adjudicated`, `judged-<scorer>`, etc.) your reports cite, each with its `floors`; every other arm with a score git tracks is checked too, so one re-allowed in `.gitignore` is never
skipped. `floors` makes deleting cited runs fail. `scorer_sources` lets V10 check that derived
runs carry the current scorer's hash; each has `arms` (the label prefix its runs are under), `glob`, `path`, `module` (from project root), and `callable`. `duplicate_ok`
names the (dataset, system) pairs allowed to repeat. `systems` adds globs (from the project root)
of systems kept outside `data/systems`, so every check of systems (V1's schema, V5, V18, V20) sees them.

The duplicate-score check catches a specific and nasty failure: two
independent arms do not agree to full float precision. When they do, one of them
is not its own measurement — a copied number, a mis-wired arm, a cached result.

Run it in CI. It exits non-zero.

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
   evh rescore --dataset-id <id> --reference-id gold/<id>_adj1 --label adjudicated
   evh leaderboard <id> --label adjudicated
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
**It is optional:** nothing else in the
harness needs it, and it never changes a committed run. To see the whole pass offline and
for $0 first, run [tutorial 3, step 5](../../docs/tutorials/3-frontier-reference-and-judging.md#5-re-measure-with-an-llm-judge-optional).

```bash
evh judge-score --dataset-id my_v1 --scorer my-judge-v1 --dry-run   # free
evh judge-score --dataset-id my_v1 --scorer my-judge-v1
evh leaderboard my_v1 --label judged/my-judge-v1
```

A project needs only its own data directory, scorer, prompt and runs: the judging code, the
prompt builder and the judge client are all in `evaluation_harness`, and so is the check of a judge
against people, `evh judge-validate` ("Validating a judge", below).
`validate_judge_goyal.py` and `validate_judge_zhang.py`, which check a scorer against the Goyal
et al. human preferences and the Zhang et al. crowd ratings (CNN/DailyMail articles), predate it and
stay scripts of this repository, outside the package, as the evidence of `research/REPORT_SUMMARIZATION.md`: their published
figures are defined differently from the command's, so each is specific to its download and to the news-summary judge, and
neither is an `evh` command; an installed project uses `evh judge-validate`. Their two downloads are also dataset sources
for the command, `examples/judge-validation-goyal/` and `examples/judge-validation-zhang/`, and their committed records are
read as eight recorded runs of those datasets (`tools/reproject_judge_validation.py`, $0; `evh scorer-show judge-summ-v1`
lists them).

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
     A worked prompt is `prompts/judge_prompt_example.txt`, which `evh init` writes into every project (the tutorial
     kit's is `tutorial/judge_prompt.txt`). Copy it and match the scorer: `{n}`, each name in `task.dimensions` as a JSON
     key (`judge-score` refuses a prompt that leaves one out) and `task.scale`. The prompt file is sent whole, so it holds
     the prompt only; `source_label` and `output_label` are added after it, and `explain: true` adds the request for a
     reason, so the prompt does not ask for `why`.
   - **Which arms.** Every arm on the dataset (its latest run per `system_id`) unless the
     scorer sets `arms_match` (a `system_id` substring), or `--match …` or `--arms a,b,c`
     narrows it. A subset is its own judging set. If the arms mix system versions
     (`_v1` and `_v2` of one arm), the pass warns: each version is judged as its own arm.
   - **`prompt.file`** is looked up in this order, first hit wins: an absolute path as
     written; the project root (`EVAL_HOME`; else the nearest
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
   `unparsed reply: …` (with the cause: empty, cut off at the token limit, JSON that stops before its closing brace,
   not JSON, or the wrong shape); an item counts only when every one of its primary blocks parsed. A
   reply that is not bare JSON scores (a judge reasoning aloud, a reply cut off) or that
   repeats 8 consecutive words of the item or an output is committed only as its hash, so the
   source's text is never committed by accident; `validate` V12 checks every committed reply.
   Its text is kept on your machine, git-ignored, beside its record:
   `data/judge-verdicts/<scorer>/<judging set>/<judge>/.withheld/<item>.<pass>.b<block>.txt`
   (the directory ignores itself). The log names the file ("reply not committed as text (…),
   only its hash; readable, git-ignored, at …"), so you can read why a reply did not parse
   before you retry. `--retry-unparsed` calls
   again for those blocks only. The pass prints what it spent: "spent this run $…, stored total
   $… (the provider's bill where it reports one, else the price table)", the same rule as an
   arm's cost (§4). After the arm spend line: a NOTE when the provider billed more than 1.2× (either way) what the declared prices give, naming where to correct them (a new scorer version, since editing the judged scorer's prices makes its next pass refuse; the system).
6. **Read the judging pass's checks before the ranking.** The judged leaderboard
   (`evh leaderboard … --label judged/<id>`) prints them under its table, from
   `data/judge-summaries/<scorer>@<judging set>.json`: how far the judges agree (item tau, and the Spearman of
   the arms' order), and per judge the position check (a second shuffle on a subset) and the
   noise check (the same call repeated on a subset):

   ```text
     The judging pass (tickets-judge-v1, 6/6 items, unvalidated judge), from data/judge-summaries:
       judges judge_a and judge_b agree: item tau 0.040, arm order spearman 0.400
       judge_a: reshuffled outputs tau 1.000 (position), the same call repeated tau 1.000 (noise)
   ```

   A difference between arms smaller than the noise check's is not a difference.
   `data/judge-summaries/<scorer>@<judging set>.json` also has the per-judge columns and which arms share a judge's family. A judged
   run keeps its source run's cost and speed, so the judged leaderboard has its frontier.
7. **Record the decision.** Changing an eval's primary metric is a recorded decision
   with a reason; the old metric stays beside the new one (CONCEPTS: Re-measuring a frozen
   eval).

### Judging modes: grade, pick, pairwise

What a judge is asked is the scorer's `mode` ([RFC-005](../../docs/rfc/RFC-005-judge-scorers.md), "Judging
modes"), and a judge is validated in the mode it is used (`validation.mode` must equal `mode`):

- **`grade`** (the default, everything above): each output scored per dimension on the scale. For a project's own judge, start with `scale: [0, 1]`, a pass/fail per dimension with the rubric saying what passes: two values are easier to judge consistently and to check against people than five (Husain's advice from practice); keep 1-5 where people already scored on it, as SummEval's experts did. `data/judge-summaries/<scorer>@<judging set>.json` gives each judge's `length_bias`: Spearman's rho of its score with the output's length in words; a rho well above 0 says the judge may favour longer answers (judge-summ-v1's two judges: 0.23 and 0.29). A changed rubric, prompt or set of judges is a new scorer (a frozen judging set is never rewritten): give it `supersedes: <the old scorer_id>` and `why:`, a sentence on what changed and which outputs led to it (criteria drift, Shankar et al. 2024); `validate` (V13) checks both, and `judge-score` prints them. Grade-mode prompt not naming every task dimension is refused (invalid-file) before any call, `--no-calls` skips that check; pick and pairwise need none. A wrong-shape grade's unparsed line names its keys and the keys expected.
- **`pick`**: one call per item with every arm's output, blind and shuffled; the judge names the best
  (`{"best": [3]}`, several when they are equally best). `protocol.outputs_per_call` must be at least the number of
  arms: a pick made in blocks would name each block's winner, so it is refused.
- **`pairwise`**: one call per pair of arms on every item (`{"better": 1}`, `2` or `"tie"`);
  `outputs_per_call` is 2. That is n(n − 1)/2 calls an item: read `--dry-run` first.

Pick and pairwise project `won` per arm per item: 1 for an arm picked alone, 1/k when k share the best, else 0
(pick); the share of its pairs it won, a tie a half (pairwise). The judged runs' primary is `judge_won`
(`judge_won_unvalidated` with `--unvalidated`), and goals, rounds, `comparison-show` and the sheet read them as they read
`judge_score`. `data/judge-summaries/<scorer>@<judging set>.json` and the terminal add each arm's win rate (its mean `won`) and its Bradley-Terry
strength with a 95% interval from resampling the items; the position check (a re-shuffle, or the pair swapped) and
the noise check (the same call repeated) are reported as the share of verdicts that held.
This repository's two, `judge-summ-pick-v1` and `judge-summ-pairwise-v1`, use
`judge-summ-v1`'s judges (`gemma_l`, `qwen_s`), each validated in its mode on SummEval:

```bash
evh judge-score --dataset-id cnn_dailymail_200 --scorer judge-summ-pick-v1 --dry-run   # free
evh judge-score --dataset-id cnn_dailymail_200 --scorer judge-summ-pick-v1
evh sheet-show cnn_dailymail_200 --runs … --metric judge-summ-pick-v1/judge_won
```

### Judges that say why

A scorer with `explain: true` (what `evh scorer-new` writes) asks each judge for a short reason inside its verdict,
after the scores and in the same JSON object: one sentence per graded output, or one for a pick or a pair. It is the
same call, so it costs output tokens, not calls; the dry run counts them. The verdict stores the reason as `why`. One
that repeats eight words of the item or the outputs is not committed (`why_withheld`, kept in the git-ignored local copy
as a withheld reply is), and one that is missing is marked so (`why_missing`); the scores stand either way.

```bash
evh judge-verdicts <scorer> --limit 10              # the lowest scores first, each with its reason
evh judge-verdicts <scorer> --item <id> --order item # one item, every arm and judge
```

A judge asked for its reason is a different judge (its message changes), so the gate compares `explain` with its
validation runs: validate it with `explain: true` in the judge arm's params (`evh judge-validate` sets it from the scorer, and the
SummEval adapter asks in the same words). A scorer without the field gives no reasons and keeps its judging sets and messages as they were.

### Validating a judge: what the gate needs

A validation is an ordinary eval whose **arms are the judges** and whose items carry
human ratings. Each judge runs as an arm (same `model`, `temperature`, `reasoning`,
`max_tokens`, `provider` and prompt file as in the scorer) over items people have already
rated, and its score is how well it agrees with them: rank correlation for ratings, accuracy
for preferences.

**`evh judge-validate` does the route, every step by the harness.** It takes the scorer and a
*rated dataset*: each item is one JSON document `{"source": text, "outputs": [text, ...]}`, and its
reference (gold or silver) is `{"ratings": {dimension: [one number per output]}, "raters": [{dimension:
[...]}, ...]}`, the mean of the people's ratings over the scorer's `task.dimensions`, or over some of them when the
people did not rate all (the same in every item; only their order is used, so any scale) and, optionally, each person's own. A dataset source writes that shape and
hands the ratings on as the dataset's own answers (`dataset-create --query '{"answer": ...}'`, then
`reference-promote`): the two sources in `examples/judge-validation-goyal/` and
`examples/judge-validation-zhang/` are worked ones.

```bash
evh judge-validate --scorer my-judge-v1 --dataset my_rated_v1 --dry-run     # the calls, the estimate and the cap; free
evh judge-validate --scorer my-judge-v1 --dataset my_rated_v1               # the runs, and the block they make
evh judge-validate --scorer my-judge-v1 --dataset my_rated_v1 --fill --reason "..." --by person:ana
```

It writes one system per judge, `data/systems/<scorer>__<judge>__validation.yaml` (its params the
judge's, and the scorer's mode, `explain`, prompt and protocol; its adapter the core's
`scripts/judge_validation.py`, so the judge is sent the message `judge-score` sends, block by
block), and a floor of seeded random verdicts at $0, `<scorer>__random__validation` (`--floor-run
RUN` names the best free scorer's run instead). It runs each as `evh run` does, in the scorer's mode
(grade: `tau`, tau-b of the judge's scores with the ratings per dimension, averaged; pick: `top1`
beside `top1_chance`; pairwise: `pair_agreement` over eight seeded pairs per item that people rank
apart): the cap (`cost_cap_usd` or the environment, and it refuses to call without one), the
fingerprint, the progress, `--resume` (a finished run is used as it is, one that stopped is
continued). The outputs are shown to the judge in a blinded order seeded by `order_seed` and the item, as `judge-score` shows its arms (`order: original` in a hand-written system shows them as the item lists them). That is why a figure from the command differs from one made in the original order: `gemma_l` on SummEval's 100 articles is tau 0.5156 blinded, 0.5360 in the original order and 0.5384 in the committed hand-made run (RFC-038 section 8). A run stores each verdict in the item's own order and, for a reply that does not parse,
only its sha256, finish reason and length: a reply can quote the rated item. With `raters`,
`human_tau` (`human_top1`, `human_pair_agreement`) is scored beside the judge: one person against the
mean of the others, which is how well people agree with people. It prints, per judge, the metric,
the floor, the run and the `validation` block these runs make. `--fill` writes that block and
`prompt.sha256_at_16` into the scorer through the scorer's own operation, as a decision (`--reason`
goes into the block's `why`, `--by` into the scorer's history), then prints what the gate
(`validation_problems`) answers. It refuses before any call: a dataset that is not rated (an item that
is not `{source, outputs}`, a reference without `ratings`, a dimension of the scorer the ratings lack,
a list that is not one number per output), a pairwise scorer with an item of one output, a pick scorer
whose `outputs_per_call` is below the outputs, a grade prompt that does not name every dimension, no
cost cap; and `--fill`: a `provider: fake` judge (its runs are allowed, as a test of the plumbing for
$0), a scorer that has judged (a new version is `scorer-new --set supersedes=...`), a block already there
without `--replace`, only some of the judges. A dimension of the task the ratings do not carry is not averaged in: the block records
the ones it validates (`validation.dimensions`), the gate names the rest (`dimension fluency: not validated on <dataset>
(its ratings carry ...)`), and `evh scorer-show` and the Workbench say the same for each validation run. `evh scorer-show`
lists the validation runs and the
datasets that are rated for the scorer; the Workbench's "A judge for this goal" does the same steps (the
cost first, the runs, the write) and prints the commands.

The scorer's `validation` block then names those runs:

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
run's in that mode: `top1` or `pair_agreement` (the command's, and the SummEval example's, below).
`evh judge-validate --fill` writes the block, with `why` (who validated it and why), so nobody types the values.

The gate reads each named run's `metrics.json` and refuses unless the metric equals
`value`, is at least `min_metric` (set it to the best free scorer's score on the same data,
so a judge must beat it), and the run's model, params, prompt file and prompt sha256 are the
scorer's. The worked example is
[`examples/summeval-judging/`](../../examples/summeval-judging/README.md): its adapter turns
a judge's JSON reply into tau against the experts, and `judge-summ-v1` cites two of its runs. An arm with
`mode: pick` in its params picks the best of an article's 16 summaries (`prompt_pick.txt`), scored `top1` beside
`top1_chance`; one with `mode: pairwise` judges seeded pairs (`prompt_pairwise.txt`), scored `pair_agreement` (with
`n_pairs`); the `random` arm in each mode is the floor `min_metric` names (`systems/se_*_n100_pick_v1.yaml`,
`se_*_n100_pairwise_v1.yaml`). The adapter's `primary_metric(params)` makes each arm's primary its mode's metric
([INTEGRATION](INTEGRATION.md)); `judge-summ-pick-v1` and `judge-summ-pairwise-v1` cite those runs.

**Validate on outputs like the ones you will judge.** A judge validated on one set may not transfer to another. The gate checks that a validation exists and is
current, not that it transfers. `differs_from_this_use` is where
you say how far it has to travel, and the honest next step is a small human check on your
own outputs. The evidence for the rule: judges validated on SummEval's 2019 summaries ranked modern LLM summaries above a fine-tuned BART, while one reader's check preferred BART 14 to 6 (p = 0.115), (`research/REPORT_SUMMARIZATION.md` §3.8).

---

## 12b. A goal, through the model

The goal is the first record the harness keeps through its model (RFC-032): one schema, one place
(`data/goals/<goal_id>.yaml`), read and written only by these commands and the API's resources, which give the same
answers.

```sh
evh goal-list                                   # every goal: its status, measure and title
evh goal-show tickets_summary                   # one goal, as stored
evh goal-status tickets_summary                 # where it stands, and the next step with its command
evh goal-new tickets_summary --set title="Ticket summaries" --set datasets.0.dataset_id=tickets_v1 ...
evh goal-set tickets_summary --set status=dormant --unset links
evh goal-history tickets_summary                # its saves, newest first: when, by whom, what it was
```

A save is checked first: against the goal's schema, its id against its file's name, and every dataset and reference
it names against the project. A save that does not check writes nothing and names each field
(`ERROR (invalid-file)`). Only the lines a change touches move, so the file keeps its comments. Each save records who
made it (`--by`, as RFC-027) and the goal as it was. The project's full check (`evh validate`) is not part of a save:
run it, or let the Workbench run it as a job. A goal a job is writing is refused, not waited on (`ERROR
(not-allowed)`, naming the job). `--set` takes a dotted key and a YAML value, as `evh data-put --set` does.

Through the API (`catalog-serve`, its token, RFC-026), the same operations are resources:

| Command | Resource |
| --- | --- |
| `goal-list` | `GET /api/v1/goals` |
| `goal-show` | `GET /api/v1/goals/{goal}` |
| `goal-status` | `GET /api/v1/goals/{goal}/status` |
| `goal-history` | `GET /api/v1/goals/{goal}/history` |
| `goal-new` | `POST /api/v1/goals/{goal}` with `{"set": {...}, "by": "person:NAME"}` |
| `goal-set` | `PATCH /api/v1/goals/{goal}` with `{"set": {...}, "unset": [...], "by": "person:NAME"}` |

The Workbench (PRD-017) is served by `evh catalog-serve` under `/workbench/`, on this machine only, as the API is.
Its startup prints the link that signs in (`/api/v1/session?token=…&next=/workbench/`: the token once, then a cookie)
to a terminal; when its output goes to a file or a pipe (a background job, CI), the link names the token's file
(`.build/api-token`) instead, and the access log masks the token, so no log file holds one. A terminal recorder
(`script`, asciinema, tmux's `pipe-pane`) runs in a terminal and records the link with its token.
Every screen reads and writes the project through these operations, each showing the command it runs:
[tutorial 8](../../docs/tutorials/8-the-workbench.md) walks them.

Each answers `{"command", "version", "result"}`, the `result` the command's `--json` gives. A write needs the
`X-EVH-Data: 1` header and `by` (an agent: `"by": "agent:NAME", "for": "person:NAME"`); a refusal answers its kind
and, for a goal that does not check, each problem with its field (`422`).

## 13. Rounds of an eval (optional)

Evals go round on round: try some arms, keep what wins, drop what lost, change something,
compare again. A round records it, beside its goal, in `data/rounds/<goal>/<round>.yaml`; the
commands are its only writers, and a project that never opens one sees none of it. Design:
[ADR-0004](../../docs/adr/ADR-0004-eval-rounds.md). Walkthrough, offline:
[tutorial 4](../../docs/tutorials/4-rounds-and-versions.md).

```bash
evh round-open --goal my_goal --dataset my_v1 --hypothesis "what this round sets out to learn" \
    --keep arm_a_v1,arm_b_v1 --baseline arm_a_v1   # round 1: carry in arms already run, one as the baseline
evh round-evidence my_goal r1                   # the evidence, and the next decisions as commands
evh round-list my_goal                          # the goal's rounds, a line each
evh round-show my_goal r1                       # the stored round: hypothesis, changes, harness, scorer, scoring changes, each arm with its runs, how it entered and its retirement
evh round-carry --goal my_goal --round r2 --arm arm_a_v1  # carry an arm of the round before, or a system measured on the round's dataset, into the open round
evh round-retire --goal my_goal --round r1 --arm arm_b_v1 --reason "why it is dropped"   # a decision, like round-close: it names who made it (at a terminal your login; a script --by person:NAME)
evh round-retire --goal my_goal --round r1 --arm arm_b_v1 --label linux --reason "..."  # only the arm under that label
evh round-close --goal my_goal --round r1 --conclusion "what it showed" [--promote <run_id>]
evh round-open --goal my_goal --dataset my_v1 --from r1 --change "what changed and why" \
    --keep arm_a_v1 --retire arm_c_v1 --reason "why" --budget-usd 0.50  # --keep all: every arm of --from (needs --from)
# a goal's first round: evh round-open --goal my_goal --dataset my_v1 --adopt (refused once the goal has rounds)
```

- **A new arm joins a round** by running in it, `evh run --goal G --round r2`; every run
  records it. **Carried arms (`--keep`) need no system change and no new run:** their runs
  already count, and `round-open` says so ("Carried in as they are, their runs already count: <ids>
  (they need not run again)."). Commit the round file before
  the runs. `evh round-carry` carries an arm of the round before, or a system already measured on the round's dataset, into the open round; a named actor; refused if the arm is in play or the round closed. An arm of the round before keeps its runs only when that round was on the same dataset, otherwise the system is read through its own plain runs on the round's dataset (not-found if none); a measured system is carried, never run again. Workbench: "Open the next round" ticks the last round's arms in play one by one (all ticked), and an open round has "Carry it in".
- **The run a round starts from** is the dataset's promoted baseline when it has one. Without one (a goal's first
  rounds, or arms carried in with `--keep`), name it: `--baseline <system id>` takes that system's latest measured
  run on the dataset, or give a run id. `round-open` says which run the round starts from; `pair-test --round` and
  `evh round-evidence` read the round's arms against it.
- **A round records the harness code it opened on** (its version, the project's commit and the hash of the code
  that can change a measurement, as every run records it). Harness code taken mid-round measures some arms with other
  code than the rest: `evh round-evidence` names each run of the round that recorded other code (`NOTE: N run(s) ran on other
  harness code than the round opened on …`) and how to run it on the round's code: a worktree at the round's commit,
  or the round's version pinned when the harness is installed. Or open a new round on the new code.
  The two ids identify different things. `commit` is the git commit of **your project** (in a checkout of
  eval-harness, the harness itself) and moves with every commit you make. The `code` hash `round-open` prints
  ("On harness V (code 3076a3525f0e)": the first 12 characters of the recorded `code_sha256`) is a hash of the
  **harness** modules that can change a measurement; it changes only when that code does, and it is the identity
  that survives installation. `round-open` prints the commit only for a checkout of the harness.
- **`evh round-evidence` never suggests promoting the run that already is the baseline**: its close
  suggestion then reads "close the round with what it showed (<arm> is already the baseline)",
  with no `--promote`. `leaderboard --round` does not warn about two versions of one arm (`_v1`,
  `_v2`) in a round: comparing them is what the round is for.
- **`evh round-evidence`** reads the evidence the way the inspector does (the round's arms against its
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
  nothing, in its text and in `--json`. It decides nothing. Every view of a round reads the runs the round recorded; a later run of one of its systems is named "since then" in its notes ("<system>: N run(s) since then not read here (<ids>); the round reads the M it recorded"), never mixed into its means and tests.
- **`round-close --promote <run_id>`** promotes that run to the goal's baseline on the round's dataset, with the
  conclusion as its reason and the evidence read as the round reads its arms. A closed round refuses new runs; one round per goal is open at a
  time.
- A round compares arms scored against one reference: when gold arrives mid-way, new runs are
  scored against gold while carried arms were scored against silver, so re-score them first.
- `leaderboard`, `family-test`, `pair-test` and `comparison-show` take `--round rN`. `comparison-show --round`
  reads the goal's measure against the round's leader, and names the arms with no score on it;
  `pair-test --round` tests the round's leader against the baseline it started from unless
  `--a`/`--b` say otherwise, and refuses an arm not in play. `round-show` names the stored round (hypothesis, changes, harness, scorer, scoring changes, each arm with its runs, how it entered and its retirement); `round-list` lists the goal's rounds (one line per round with goal, rounds). `validate` (V14) checks the round
  files; the catalog's goal page shows the rounds, newest first, each with an inspect button.

---

## 14. Browse the catalog and the inspector

```bash
evh catalog                                             # build static pages into .build/catalog/
evh catalog-serve [--port N] [--brand NAME]            # the catalog and inspector on 127.0.0.1, a port of the project's own; takes evh catalog's page options
evh catalog-serve --public catalog.example.com --publish outputs --client-header X-Real-IP  # public deployment
evh dataset-profile --dataset-id my_v1 [--with-text]   # what is inside a dataset, for its page (text: committed items only)
evh dataset-items my_v1 [--item ID]       # the same in the terminal
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

**The inspector's page is addressed by its URL**, and each query parameter is the flag of `evh comparison-show` of the
same name: `runs=A,B`, `baseline=`, `metric=`, `where=FIELD:VALUE`, and `item=ITEM_ID` for one item, the item beside
the reference and each arm's output (`evh comparison-item --runs … --item ID`, the same view in the terminal). Open
an item by clicking its row, or by adding `&item=ITEM_ID` to a comparison's address (a link, a script); the full list is in
[tutorial 5](../../docs/tutorials/5-catalog-and-inspector.md).

**An item's artifact** (what its adapter left to open: an agent's trial directory, a report; `meta["artifact"]`, a path
inside the project, [INTEGRATION](INTEGRATION.md#the-one-function)) is a link under the arm's output in the inspector, a
`(run R · artifact artifacts/…)` line under it in `evh comparison-item` (`--json`: `views[arm].artifact` and
`artifacts`, `{arm, path, kind, url}`), and under the reply of each item of `evh arm-smoke` and of the Workbench's check on
three items. Its URL is under a directory the local inspector serves read-only (`artifacts/` at the project root, `data/`
and the adapter's `served_dirs`), with `nosniff` and `sandbox`, and a symlink out of it is a 404. A path outside the
project, a stored one a hand edited, is `refused`, never linked. A public server shows no artifact, a release of a hidden dataset drops the path from its rows (and is refused when it lies under `data/runs/`), and any other release copies the row without the directory (`artifacts/` is not under `data/`; the copy carries `release.json`, and there a missing artifact reads "not in this deployment").

**For an agent with a shell**, every command the API serves takes `--json` (RFC-026): one object, `{"command", "version", "result": {...}}`. Most reads return the operation's own structured result (`result.datasets` for `dataset-list`, `result.runs` and `result.count` for `runs-list`, `result.arms`, `result.baseline`, `result.rows`, `result.conditions` and `result.notes` for `comparison-show`, and so on). Only `leaderboard`, `validate`, `cost-report`, `rank-stability`, `pair-test`, `family-test`, `sheet-show`, `comparison-item` and `run-compare` answer
`{"command", "version", "result": {"blocks": [...], "values": {...}}}`: `blocks` is what the
command prints (each table with `columns` and `rows`, raw numbers as NaN=null), and `values` its key results by name.
`leaderboard`'s `values.groups` has each arm's rank and metrics, with the `ordering` test; `pair-test`'s `values` has `delta`, `p`, `method` and `verdict`; `family-test`'s table has `p_holm`, the Holm-adjusted p.
For writes (`evh run`, `sweep`, `catalog`, `dataset-create`, `import-run`, `run-promote`, `rescore` and others):
`values` only, naming their results.
A refusal prints its message on stderr, nothing on stdout, and exits non-zero. `evh run` prints `  run <run_id>` for each run it wrote; with `--json` its progress goes to stderr and `values.runs` lists each run's
`run_id`, `system_id`, `dataset_id`, `dir`, `n_items`, `total_cost_usd` and `capped_at` (`--dry-run --json`: `values.dry_run`, the projection). The text output without `--json` is unchanged.

**For an agent without one**, `evh mcp` serves the same reads as MCP tools; how to connect
each client is in [the integration guide](INTEGRATION.md#for-an-agent-evh-mcp).

- **The tools** are the read operations of the registry (`evaluation_harness/ops`), each named as the operation, the
  command and the API's resource are: 75 on your machine, among them `study-ask` and `study-tell` (`goal-list`, `goal-leaderboard`, `dataset-list`,
  `dataset-show`, `arm-list`, `comparison-show`, `comparison-items`, `sheet-show`, `leaderboard`, `pair-test`,
  `family-test`, `rank-stability`, `run-compare`, `runs-list`, `validate`, `data-ls`, `search`, ... as `evh mcp --help`
  and the client's tool list show); the agent sampler's `study-ask` and `study-tell` are not offered by a public server
  (62 tools on a public one). A tool takes the operation's own inputs, typed (`dataset`, `period`, `runs`; a list is an array, a flag a
  boolean), except those that name a path of the server's (`items` on `pair-test` and `family-test`). A call is
  answered in the server's own process by the same operation the command and the API are made from, so its answer is
  what `--json` gives: the operation's result, as structured content and as JSON text, with no process started. No tool
  writes project data, spends or runs a model, except the local server's `study-ask` and `study-tell` which write the study and run a trial. What a call writes is computed answers in `<project>/.cache/`: the p
  cache, `evh-p.jsonl` (below, `EVH_P_CACHE`), and `family-test`'s results. The tools removed from public: `comparison-item`, `comparison-items`, `sheet-show`, `judge-verdicts`, `label-coverage-show`, `exposure`, `sealed-counts`, `label-mutants`, `validate`, `data-ls`, `data-show`, `study-ask`, `study-tell`.
- **Refused before anything runs:** an argument the tool does not have, a missing required one, a value of the
  wrong type (checked against the tool's JSON Schema), a value with a NUL byte or longer than 512 characters. What the
  operation refuses (a dataset id that is not a plain name, a goal that is not there) is its own refusal, with its
  kind, as on the command line.
- **Stdio** (the default): the agent starts `evh mcp --project /path/to/project`. A desktop client
  starts it with its own `PATH` and working directory, so give the full path to `evh` and
  `--project`.
- **`--http`**: Streamable HTTP, stateless, JSON answers, at `--path` (default `/mcp`) on `--bind`
  (default `127.0.0.1`) and `--port` (default: the project's own, in 19000–19999, the same every time; `catalog-serve` has one in 18000–18999). `<path>/health` answers `{"ok", "version",
  "tools", "public"}`. Beyond the loopback, `--allowed-host` is required: a request for another Host
  is answered 421 (DNS rebinding). `--allowed-origin` names the browser origins it accepts; an
  agent sends no Origin.
- **`--public`**, for a server anyone can reach: each call is made with the public flag, so what `--public` hides on
  the command line stays hidden (a hidden dataset's text and labels, an item's text), and the tools that answer with
  an item's text, an arm's output or a label, or read the project's files, are not offered (`comparison-item`,
  `comparison-items`, `sheet-show`, `label-coverage-show`, `label-mutants`, `sealed-counts`, `exposure`, `data-ls`,
  `data-show`, `validate`, and the agent sampler's two); the inputs that would answer with one are not offered either
  (`item` of `dataset-items`, `group` of `comparison-crosstab`: a recorded field can hold text; `crosstab` of two scores
  stays).
- **Load:** `--concurrent N` calls at once (default 4; a call that waits 30 s for a slot is
  refused, "busy"), `--timeout S` per call (default 300; a call that has run that long is told as "stopped waiting
  after S s": it is answered in the server's own process, which cannot stop it, so it keeps running to its end, its
  slot given back at once),
  `--rate N` calls a minute per caller and `--rate-total N` for everyone together (default: no
  limit), and over HTTP one call at a time per caller. Every call counts toward the caller's rate, a
  refused one too; the total counts only calls that run a command, so a flood of refusals never
  locks others out. An IPv6 caller is counted by its /64. Below the tools, the HTTP layer:
  `--request-rate N` HTTP requests a minute per caller to the endpoint, every method (a tool call
  is about three), `--max-body BYTES` (default 65536; larger is 413), `--max-connections N`
  (default 64; more are 503), at most 8 requests open per caller (more are 429), a body due in
  full within 10 s (else 408), and a GET on the endpoint is 405 (stateless: no stream to hold);
  `/mcp/` is the endpoint too, never a redirect.
  With `--public`, an answer is kept by the tool and its arguments (16 MB of text in all, for an hour: a
  view's default period moves with the date), since the data under the server never changes, and a refusal is told without server paths or a traceback.
  A value with a NUL byte, or longer than 512 characters, is refused. `--client-header NAME` names the header your proxy sets for
  the caller's address. Trust it only when nothing but the proxy reaches the port: a caller who
  can set it can name itself anything (the total still holds).
- **`--hooks FILE`**: the deployment's error reporting, tracing, metrics and analytics, in
  `catalog-serve --hooks`' shape (`start`, `request` after each call, `error`, `routes`). A hook
  gets the tool, its arguments' names, how it ended, its time, and the caller's address and user
  agent. The log line on stderr, one JSON line per call, carries neither.

**The API** (RFC-026; the Workbench's, PRD-017): a local `evh catalog-serve` also answers `/api/v1/` for the
operations: a read is its own resource (`GET /api/v1/goals`, `/api/v1/datasets/{dataset}/arms`, ...), and a decision or a
work operation is a job (below). Every call needs the token the server writes at start to
`.build/api-token` (readable by you only): `Authorization: Bearer <token>`, or the cookie `GET
/api/v1/session?token=<token>` sets; another Host or a foreign Origin is refused, and a call that is not a read needs
`X-EVH-Data: 1`. `evh openapi` (and `GET /api/v1/openapi.json`) lists every operation with its inputs: whether it
spends, a system id checked to exist, a file as an `upload` or as an `artifact` a job writes; what loads code or names a
path of the server's (`--adapter`, output folders) is never taken, and a query's `path` must be inside the project. A read answers what the command answers with `--json`; `evh openapi` describes every resource. A refusal is a 4xx with
`{"error", "kind", "problems"}`; a read asked with `optional=1` (a page that shows the answer only when there is one,
as the Workbench's charts do) answers a `not-enough` or `not-found` refusal with 200 and `{"command","version","result":null,"empty":<why>,"kind"}` instead, so a browser logs no error for "nothing yet". A server started `--behind-proxy` answers no `/api/v1/` call. A server started `--public` answers only the reads, with no token, and refuses every write, job, `POST /estimate`, `/jobs` and `/session` (RFC-039).

**Jobs.** A decision or a work operation runs as a job: a POST on its own resource (`POST
/api/v1/goals/{goal}/rounds/{round}/close`, `POST /api/v1/systems/{system}/runs`, ...; `evh openapi` lists them) with
its inputs as the body, or `POST /api/v1/jobs` with `{"operation", "inputs", "by", "for", "max_cost_usd"}`, answers
`202`: a detached process that goes on when the page closes or the server restarts, in `.build/jobs/<id>/` (its record
`job.json`, the operation and its inputs; `inputs.json`, what its command reads; its state, its `log`, its envelope as
`result`, its `progress` and `spent_usd` as it goes). Every job names who asked (`by`; an agent names whom it acts for,
`for`), one that spends carries `max_cost_usd`, and a decision's reason is one of its inputs; an input is named as the
operation names it (`dataset_id`). A file input is sent as `{"name", "content_base64"}` (at most 50 MB a call) or, for a
file the job writes, named and fetched with `GET
/api/v1/jobs/<id>/files/<name>`. `GET /api/v1/jobs` (`?state=`), `GET /api/v1/jobs/<id>`, `GET
/api/v1/jobs/<id>/log?from=<byte>`; `POST /api/v1/jobs/<id>/stop` (SIGTERM to its process group, SIGKILL after 10 s:
`cancelled`) and `.../resume` (a stopped run, continued with `run --resume`; a run job is given its run id up front,
`<system_id>_<job id>`). The cap is the job's, not each attempt's: the new job is given what the stopped one left of
its `max_cost_usd` (the job keeps what it spent as it goes, in `spent.json` in its folder; a call in flight when it
was killed was never reported and is not counted), and a job that spent it all is not resumed. Two jobs that write the same thing never run at once: each takes a lock per thing it writes
(a system, a dataset, a goal's baselines, the captures, the catalog; the whole project for a migration), and one
whose lock is held waits, `queued`, saying which job holds it. The command holds its locks itself, so they outlive
the supervisor: a job whose supervisor died reads `running (unsupervised)` while its command lives, `lost` after.
The terminal has the same jobs, no server needed: `evh jobs-start OPERATION --arg NAME=VALUE ...` (the operation's
input names, as the operation's `--help` shows them with underscores; repeated for a list, `@FILE` uploads a file;
`--max-cost-usd`, `--by`: a job records who asked, and the flag goes before the operation,
`evh jobs-start --by person:NAME run --arg ...`; without one the command refuses and says so),
`evh jobs-status [JOB]`, `evh jobs-logs JOB [--follow]`, `evh jobs-stop JOB`, `evh jobs-resume JOB`. A job started
there is listed and stopped by the API, and one the Workbench started is followed there.
`POST /api/v1/estimate` with `{"operation", "inputs"}` runs a job operation's own dry run (`run`, `sweep`,
`judge-score`, `faithfulness`, `study-run`, `study-confirm`, `data-rm` and the two migrations have one) and answers what
it printed and its result; a stopped run job's round reservation is
closed by its supervisor with what the run's items paid.
`evh catalog` builds beside the served folder and
swaps it in, from the terminal or as a job, so a server keeps serving the old pages until the new ones are whole (the
swap is one system call on Linux and macOS; elsewhere two renames, with the folder absent between them). While a migration holds the
project (`data-migrate` and the other `*-migrate` jobs), the server answers every call `503` with `Retry-After: 5`
and lets go of the project's database, so `data-migrate --to files` runs as a job with the server up; when it ends,
the server reads the project's store again.

**The run inspector** is a local server (`evh catalog-serve`) that tests chosen arms against a
baseline with the same paired test as the command line, and shows outputs beside references.
Its "re-score" box (shown when the adapter can re-score) scores what is not on record; `evh
comparison-show --rescore 0` is the box unticked.

**A crosstab of two per-item scores** (terminal only): `evh comparison-crosstab --runs A --crosstab M1,M2
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
evh comparison-crosstab --runs triage_baseline_pro_v1 --crosstab model_false_dismiss,false_dismiss \
    --group _meta.gates --group-match 'd:(n/a|[^/]+)'
```

For `downgraded (no corroboration)` the cell `model_false_dismiss=1, false_dismiss=0` holds 12 items (the
gate saved a false dismissal); the same group under `model_false_alarm,false_alarm` holds 8 in
`model_false_alarm=0, false_alarm=1` (a right dismissal turned into a false alarm). The 12 and the 8 are
different items, so a gate's net effect is read from both.

**Each item's outputs and reference together** (terminal only): `evh comparison-items --runs A,B
[--disagree] [--where F:V] [--baseline A] [--max-chars N] [--json]`. `evh sheet-show D --runs A,B` carries each run's
decision, scores and the labels but cuts them for a cell (`--json` too) and has no run's whole output;
`comparison-items` is the record per item: `item_id`, the item's start, its fields, the signals, and per run its
`decision`, whole `output` text, `scores` and the `_meta` the adapter recorded, then the `references` and
`labels`. Text prints each as a block with an output cut at `--max-chars` (default 300, 0 = whole), a
JSON-object output without its `_`-keys (a probe trace; the `_` keys are counted), and how long a cut
output was. `--json` carries everything whole under `result.values.items_out`. `--disagree` keeps the
items the other runs decided differently on from the first (`--baseline A` puts `A` first). All runs
must be on one dataset. Not served by `--public`.

**Public deployments** (`--public HOST`): the server answers only the named hosts, each client
gets `--rate` requests per minute, and at most `--max-arms` arms per comparison. `--publish`
names what text to serve besides numbers: `outputs`, `references`, `prompts` (a system's `params.prompt` and a recorded prompt file's text, as `catalog: {publish: [prompts]}` does for the pages and the public MCP), or any of them. The item itself is
never served publicly. `--client-header NAME` names the header that identifies each client (e.g.
`CF-Connecting-IP` behind Cloudflare), trusted only when a reverse proxy you control sets it on
requests from an origin no one else can reach. A public server also serves the Workbench at `/workbench/`, read-only:
the reads the public MCP server answers, under the same text rules, and no control that acts. `--catalog-at PATH`
(default `/`) names where the deployment serves the catalog, so the Workbench links there.

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
dataset-items D [--item ID] [--json]` prints the profile.

**`--json` on the reads** (`comparison-show`, `goal-list`, `goal-show`, `goal-leaderboard`, `dataset-list`, `dataset-show`, `arm-list`, `reference-list`, `metric-list`, `metric-show`, `overview-show`, `activity-show`, `runs-list`, `round-list`, `round-show`, `round-evidence`, `baselines`, `looks`, `capture-list`, `label-set-list`, `model-list`, `model-show`, `prompt-list`, `study-list`, `failure-modes-list`, `tag-set-list`, `system-list`, `scorer-list`, `fieldset-list`): one object,
`{"command", "version", "result": {...}}`, the result the operation's own structured answer (`result.datasets` for
`dataset-list`, `result.runs` for `runs-list`, and so on). `leaderboard`, `validate`, `cost-report`, `rank-stability`,
`pair-test`, `family-test`, `sheet-show`, `comparison-item` and `run-compare` give `result.blocks` and `result.values`.

**The catalog's footer** names each page's command (`evh goal-leaderboard G`); `evh catalog --mcp URL`
adds the same as an MCP tool call, with the server and a "how to connect" link (`--mcp-howto URL`,
the harness's INTEGRATION guide by default). Every page carries a share card (its title and its
opening line as the description); `--card URL` adds the image a shared link shows. The pages stay
`noindex`: a card is for a person pasting a link, not for a search engine.

**`evh mcp --hooks`** gets, in `start`, `{"version", "tools", "public", "transport"}`, and in
`request`, after each call, `{"tool", "args", "agent", "client", "exit", "ms", "bytes"}`, plus
`"refused"` (`rate`, `rate_total`, `tool`, `arguments`, `busy`, or `command` for a command that ran and refused: exit 1, its `ERROR:` line) or `"cached": true`. `tool` is
`unknown` for a name the server does not have; `args` are argument names, never values.

**In the terminal:** every view has a command. `evh overview-show [--period P]` for the home page,
`evh activity-show` for the activity page, `evh arm-list` (`--systems 1`) for the arms page,
`evh dataset-list`, `evh arm-show LABEL DATASET …`, `evh reference-list`, `evh metric-show …` and
`evh goal-leaderboard …` for the others, `evh comparison-show --runs …` (arms by arm id or by system id; a system measured on two datasets is refused as
ambiguous and the message lists its arm ids, `runs/<dataset>/<system>`; `--analysis` for the charts;
`evh comparison-item --runs … --item <id>` for one item) for the inspector, `evh label-set-list D` and `evh capture-list` for the Labels and Captures pages,
`evh sheet-show … --runs …` for a dataset's sheet (the inspector's per-item scores too),
`evh comparison-crosstab --runs … --crosstab M1,M2` and `evh comparison-items` for the two per-item reads above,
`evh picks` for the picks waiting and `evh deploy-sheet …` for a goal's deploy sheet.

---

## 15. Datasets from production: the capture lane

A dataset can come from what a production system did: its decisions, requests or answers, and what
happened afterwards. The lane is a layer beside the rest: nothing here runs in production, and a project
that never captures sees none of it. Design: [RFC-019](../../docs/rfc/RFC-019-datasets-from-production.md),
[ADR-0019](../../docs/adr/ADR-0019-capture-lane.md); a worked example on a real agent:
`examples/triage-fleet/`.

```bash
evh capture --importer jsonl --query '{"path": "decisions.jsonl"}' --capture prod_2026_10   # or tsv, github, langfuse, path.py:Class
evh capture-show prod_2026_10                                    # what was read, when, the hashes
evh capture-scrub prod_2026_10 --command "python scrub.py {records}"   # your scrubber; changed records re-hashed
evh dataset-from-capture --capture prod_2026_10 --dataset-id prod_v1 --one-per fingerprint --tag source=prod
evh dataset-materialize --dataset-id prod_v1
evh label-from-capture --dataset-id prod_v1 --capture prod_2026_10 --map rules.yaml \
    --set prod_outcomes                                                # a rule set: what happened afterwards
evh label-coverage-show prod_v1 --capture prod_2026_10 --map rules.yaml   # how far the rules label it now
evh dataset-split --dataset-id prod_v1 --test 0.3 --seed 7 --key fingerprint     # prod_v1_validation, prod_v1_test
```

- **A capture** is `data/captures/<id>/capture.json` (each record's id and hashes) and `records/` (the
  records). V17 checks them. A project may keep `records/` out of git and fetch them from where it
  publishes them; a capture without its records is then named "not fetched", not failed.
  `evh capture-restore --capture <id>` reads them again from the source the recorded query names
  (`--query KEY=VALUE` replaces one key, e.g. the same files in a download folder), runs a recorded
  scrubber again, and writes the item files of every dataset made from the capture. Every record and
  item is checked against its recorded sha256 first: one that differs is named and nothing is written.
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
- **How far the rules label it, before writing a set.** `evh label-coverage-show D --capture C --map
  rules.yaml` applies the same rules and writes nothing: each item is labelled now, skipped by design, not yet
  mature (a rule fits it but for `min_age_days`, and the date it matures is named), matched by no rule (with the
  outcome fields those items lack) or not in the capture; per rule, the items it takes now and when mature.
  `--items` lists every item; `--json` gives all of it. A rule waiting to mature that comes before the one that
  labels an item today counts the item as not yet mature, with today's label beside it: that label can change.
- **An outcome from another system** ([RFC-031](../../docs/rfc/RFC-031-held-out-discipline-and-outcome-labels.md)
  L1). A decision's outcome often lives on another object: the issue it filed, the errors that followed. Capture that
  source too (its own importer: what was read is kept, hashed and dated), then join it: `label-from-capture` and
  `label-coverage-show` take `--outcomes issues_2026_11 --join fingerprint=fingerprint [--within -1m,+15m]
  [--outcomes-as issue]`, and the rules read `issue.<field>`, `issue.count` and `issue.created_at` beside the item's
  own outcome (one name across later captures of the same source). `--identity first_seen=first_seen` makes a match
  whose identity differs (an id reused after a project was deleted) "gone from the source, or its id reused"; with
  `--gone-if-missing`, when the other capture holds the very objects the items name, an item none carries is gone too.
  A gone item is its own class: never "no outcome", never a negative label (X3). Outcomes from several systems (an
  issue's close reason and the errors' recurrence): `--outcomes` again, each followed by its own `--outcomes-as`,
  `--join` and the rest up to the next one; the rules read each under its name, and the label set records each.
- **Two dates per label, and relabels that only add** (L2). A rule's `date: FIELD` names when its outcome happened (an
  issue's `closed_at`); a label becomes knowable at the item's time plus `min_age_days`, else when it happened. Both
  are kept per item, and the set records `as_of`. A relabel is a new set: `label-from-capture … --set s2 --from-set s1`
  keeps s1's labels, adds what matured since, and marks an item whose outcome changed after maturing (a reopen, a
  recurrence) `changed_after_maturing`; a label s1 has that no rule gives today is refused unless `--keep-vanished`
  keeps it, said. `label-coverage-show --from-set s1` says what a relabel would add and change today.
- **A label that holds only under production's action** (L3). `under: action` on a rule: the outcome was observed
  because production acted so (an issue's close reason exists because production filed it). With `--action-field F`
  the set keeps production's action per item; a run or rescore against it does not score an item where its output is
  not that action (the adapter's `same()`), says "N item(s) not scorable under this variant", and records them
  (`not_scorable`). Related decisions (one fingerprint decided many times) count once with a goal's `cluster:`.
- **The labeller mutation-tested** (RFC-031 X1). `evh label-mutants D --capture C --map rules.yaml
  [--outcomes …] [--mutants my_mutants.py]` labels again with each named change (each `min_age_days` halved and one
  and a half times, neighbouring rules swapped, each `when` value replaced, the join's window moved an hour; a
  project's own from `mutants(rules)` and `join_mutants(join)`) and counts the labels each moves. A mutant that moves
  none survives: the labelled items do not reach what it changes, a finding to read; the command exits 6.
- **A label counts only where production's decision is reproduced** (RFC-031 X2). `label-from-capture …
  --reproduced-by REPLAY_RUN --production PROD_RUN` keeps a label only where the replay at the recorded versions
  (RFC-030) gives production's decision on that item, and leaves the rest out, counted. An item whose version's
  deployment was dated by commit time (`dated_by: commit` in the code record: the host no longer records its pull) is
  kept as `reproduced: approximate`, counted apart from the ones dated by the pull.
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
- **A held-out side, sealed.** `evh dataset-split --dataset-id prod_v1 --split-by time --key opened --at 2026-11-07T00:00:00Z
  --seal` puts every item at or after the boundary on the test side and seals it: no run, label, label sheet,
  reference, rescore or judging is written onto it, refused before anything is called. Tune on the validation
  side; when one candidate is ready, give its system a hypothesis (`against`, `measure`, `direction`, `statement`,
  ADR-0025), commit it, and `evh dataset-unseal --dataset-id prod_v1_test --system cand_v1 --reason "..."`: the side opens to
  that system and the one its hypothesis is against, and the look is recorded (when, why, the hypothesis, the
  commit). Every other system is still refused; each unseal is one more look.
  `validate` (V22) fails when the validation side's items changed after the seal, or a run on the sealed side has
  no unseal behind it. In the project's database the systems are not in git: there the unseal itself, timestamped
  before any run it allows, is the naming in advance, and the look records the commit as not determinable.
- **A read of a held-out item is recorded, and the item counts in no score after it**
  ([RFC-031](../../docs/rfc/RFC-031-held-out-discipline-and-outcome-labels.md) H1). A seal refuses runs and labels;
  a read is neither. `evh exposure-add --dataset-id prod_v1_test --item ID --what "decision and reason"
  [--read-by agent:NAME] [--at T]` (or `--from reads.tsv`: `item_id`, `what`, and optionally `by`, `at`) records a
  read; the harness records its own when it shows a held-out item's text, an output or a label on it (`comparison-item`,
  `sheet-show`, `comparison-items`, `label-sheet`, `dataset-items --item`, the inspector). Every score on the side
  (`pair-test`, `family-test`, the leaderboard, goals, the catalog and the inspector) leaves the read items out and
  says "<dataset>: N item(s) left out (exposed: read on the held-out side; RFC-031)"; `pair-test --include-exposed` shows the full number beside it, marked as not
  the one that counts. `evh exposure --dataset prod_v1_test` counts the reads (`--ids`, a person only, lists
  them). `evh exposure-check --dataset-id prod_v1_test [--out leaks.tsv]` searches the public repos `config.yaml`
  names (`exposure: {public_repos: [...], ids: [fields], ids_hook: file.py:fn}`) for each item's ids in commits made
  after its time, exits 6 on one the register lacks, and says what it cannot catch (a paraphrase, a title, a list
  written without the ids' prefix).
- **Counts over a held-out side, for safety only** (RFC-031 H2). `dataset-split … --seal --count-by kind,gate` fixes
  the fields its counts may be grouped by; `evh sealed-counts prod_v1_test [--by kind] [--capture
  live]` counts per day by them (with `--capture`, also a capture's records on the held-out side of the boundary:
  the live watch), prints no id or text, and records no read. A person widens the list with `evh
  dataset-seal-counts --dataset-id prod_v1_test --add F --reason "..."` (recorded); an agent cannot.

## 15b. Evaluating what production did

A capture keeps what production did; the governed datasets, labels and references stay yours. The
loop, on any project ([RFC-023](../../docs/rfc/RFC-023-labels-and-references.md); worked on the triage
fleet in `examples/triage-fleet/`):

```bash
evh arm-from-capture --dataset-id prod_v1 --capture prod_2026_11 --as production_v1 \
    --like deployed_v1                                                 # production's decisions, as a system
evh run --system deployed_v1 --dataset prod_v1              # the deployed system, run again
evh label-sheet --dataset-id prod_v1 --items disagree --runs production_v1,deployed_v1 --out sheet.csv
evh label-import --sheet sheet.csv --dataset-id prod_v1 --set owner_2026_11 --by <you>
evh rescore --dataset-id prod_v1 --labels owner_2026_11                # every arm, against your labels
evh sheet-show prod_v1 --runs production_v1,deployed_v1 \
    --wrong-against owner_2026_11 --new-vs governed_v1                  # where production was wrong on something new
evh pick --dataset-id prod_v1 --item … --for governed_v1 --tag case=…  # worth keeping
evh dataset-extend --dataset governed_v1 --dataset-id governed_v2 --picks        # the next version, from the picks
evh deploy-sheet deployed_v1 --capture prod_2026_11           # did production run what you promoted?
```

- **Production's recorded arm** (`provider: recorded`): each output is the capture's record of the same
  id, read by the adapter's `recorded_output(record)` (else `--field`). It is scored, tested and compared
  like any arm; it costs nothing and its speed is not measured.
- **Agreement**: two outputs are one decision when the adapter's `same(a, b)` says so (default: the same
  decision, by the adapter's `decision(output)`, else the same text). `comparison-show --disagree 1` and
  `label-sheet --items disagree` keep the items where the arms differ.
- **More than one right answer**: a label can accept several (`also right` in the sheet, `label: [file, escalate]`
  in a rule), written `{"accept": ["escalate", "file"]}` and shown "escalate or file", for answers each fully
  right, never for "unsure which". A decision is **wrong** against a label when it is none of them.
- **Agreement between label sets** (`evh label-set-list D`, the dataset page; each pair's confusion matrix is in the answer): on the items
  both label, how many accept the same answers, how many share one (apart: a label accepting more agrees more
  easily), Cohen's kappa and Krippendorff's alpha (MASI distance for several answers), which correct for the
  agreement chance alone gives when one class dominates. With three sets or more, also all of them together: one Krippendorff's alpha over every item labelled twice or more, with a 95% bootstrap interval (JSON `agreement_all`). `--contested`: per item, how many people's sets agree with the gold reference (sharing an answer with it), the most contested first, the set the reference was promoted from left out (JSON `contested`). Free-text labels are not compared as text. An adapter's `score` reads such a reference with `answers(reference)` from `evaluation_harness.adapter`.
- **Failure modes: how an arm fails, not only how often** (`evh dataset-list`). A mean says an arm is wrong on 12% of the
  items; the tags say how. Name the ways once, `data/failure-modes/<id>.yaml` (`failure_modes_id`, then `modes`:
  each an `id`, and a `description` a tagger reads first; write it after reading some outputs with open notes, so
  the modes are the ones that happen). `evh sheet-export … --csv tags.csv --fill tags --modes <id>` writes a
  sheet with each arm's output and a `failure_modes: <arm>` cell beside it (not blind: a tag is about whose output
  it is), its first row listing the modes, and a key beside it. Fill a cell with modes (`too-long|misses-ask` for
  several), `ok` for an output read and found fine, or leave it blank (not read, so an unfinished sheet never reads
  as fine). `evh sheet-import --sheet tags.csv --dataset-id D --by <who> --tags <name> --modes <id>` checks the key (an
  edited output, a mode not in the list, a name already used are refused) and writes the tag set,
  `data/tags/<dataset>/<name>/tags.json`, never edited after. `evh tag-set-list D` and the goal page count per
  arm the outputs read, how many had a failure and each mode; the sheet (`evh sheet-show`, its CSV) shows each
  item's modes in an `<arm>: failure modes` column (`ok` read and fine, blank not read); `validate` (V21) checks the lists and the sets. A tag
  scores nothing: it explains a score.
- **The sheet** (`evh sheet-show D --runs A,B,…`) shows the dataset's items down (each by the
  first arm's adapter's `title(item)` when it has one, else its start) and a column per arm across: what it wrote (the adapter's `decision(output)`, else its output, shortened; `--scores-only` leaves
  it out) and every score it has on the item: its run's metrics, and a judging pass's where one under
  `judged/<scorer>` covered the run (`--metric M`, or `SCORER/M` for a judge's, picks the one the sheet
  is read on); a column per label set or reference set; the
  winner per item (the best arm on that metric, and a pick or pairwise judge's choice where one covers the run);
  the signals; the fields; and a footer per arm: its mean, its win rate (the share of the rows it was scored on
  that it wins, a shared win split, "—" for an arm scored on none; on a pick or pairwise verdict, each arm's share of what the judge gave over the
  rows it judged, so a shared pick counts its share, a row given to an arm not shown is nobody's, and with every arm
  shown it is the judging pass's own win rate) and its verdict (the goal's decision when a goal names the dataset, else the paired test
  against the leader). The signals: **wrong** (the first run against a label set, `--wrong-against`),
  **disagree**, **split** (the candidates among themselves), **new** (a field value the dataset in `--new-vs` never
  had), **unlabelled**, **judge** (a judge on a validation, `evh judge-validate`, whose term of the validation figure on the item is under chance: it disagrees with the people). Each is a filter (`--disagree`, `--split`, `--unlabelled`, `--judge-disagrees`, beside `--where` and `--by`);
  the sheet ends with the `evh pick` and `evh label-sheet` commands for its rows. `--csv FILE` writes it (UTF-8
  with the mark Excel needs). The inspector shows the same (the dataset page's "Open its sheet"), with downloads
  of the CSV for the rows shown or ticked (the local inspector only; the page writes nothing).
- **A sheet filled elsewhere.** `--csv sheet.csv --fill label` adds the empty `label`, `also right` and `note`
  columns (`--choices a,b,c` puts the allowed answers in the label's header); `--fill pick` or `--fill scores`
  writes the arms' outputs as blind columns A, B, C… shuffled per row (`--seed`, default 0), a `pick` column or a
  `score: X` column per output (`--scale LO..HI`, default 1..5), the rubric as the first row (`#rubric`;
  `--rubric FILE`, else a plain one) and the key beside the sheet (`sheet.key.json`: which letter was which arm,
  the rubric and its sha256). A person or any AI tool fills it; `evh sheet-import --sheet sheet.csv --dataset-id D --by
  WHO` reads it back: a `label` column as a label set (`--set S`; `--kind model` when a tool filled it), a `pick`
  (`A|B` for a tie) or `score:` columns as judged scores under each arm's run, read as `judged/<scorer>` (`--scorer S`), one per
  arm, with `judge_won_unvalidated` or `judge_score_unvalidated` per item: unvalidated until the same judge is
  validated as any judge is. A row or text the key does not have, a letter not on its row, a score off the scale
  and a name already used are refused, and nothing is written.
- **Picks** wait in `data/picks.jsonl`, append-only: the latest line for an item wins; `pick --drop` takes
  one off. `dataset-extend` makes V2 of V1's items and the picks chosen, records `extended_from`, and the
  picks used leave the list; labels follow the items into V2. Nothing is promoted by it.
- **The deploy sheet** is what production must match to run what was measured: the model and its record,
  every setting sent (and a record's setting that was not), what each item reported, the adapter. With a
  capture, each record's account (the adapter's `production_ran(record)`) is checked against it; it exits 6
  unless every record matches.
- **Several projects at once**: each serves its catalog on a port of its own (18000–18999) and its MCP
  server on another (19000–19999), the same every time, the next free one if taken; a local catalog names
  its project in its header.

## 15c. Replaying the code that ran

Some systems under test are code with state and side effects: a filing stage that reads an issue tracker and its own
ledger, and writes. To measure a change to it on production's own history, the harness replays the **real code**,
each item at the commit that ran it, and scores the replay only once it is shown to reproduce production
([RFC-030](../../docs/rfc/RFC-030-replay-and-faithfulness.md); worked end to end in `examples/replay-filing/`, $0).

- **The code record** is a model record of `kind: code` (`data/models/<id>.yaml`, [§16](#16-set-up-a-model-before-you-test-it)):
  its `repo`, `checkout` (a local clone to read versions from, when `repo` is a URL) and `versions`, each a `commit`
  and when it was `deployed` (`[{from, to}]`, date-times with an offset; no two versions at one moment, V18). Each
  commit a replay needs is unpacked once with `git archive` under `.build/code/<id>/<commit>/`.
- **A replay system** names it, `model_record: <id>`, and adds `replay: {order: [fields], time_field: F,
  version_field: F, support: [modules]}`. Items run in `order` (item fields; `datetime` is a field type), each at the
  version deployed when its `time_field` falls (or the commit its `version_field` names). The adapter gets `params["item"]` (its id
  and fields) and `params["code"]` (`record`, `commit`, `path` of the copy, `changed` on the first item at a new
  commit). At a change it imports the version with `_codeload.use(path, [modules])`, which drops every module of
  another version first, and sets its seams again; state kept across items lives in files or the adapter, never in
  the system's modules. `support` names the adapter's own modules beside it (a stand-in world), hashed with it.
- **A replay run** calls each item once (a retry would repeat side effects, the rule an adapter's `CALL_ONCE` gives any
  arm, `--resume` ("When a run dies partway", above)) and, because its items depend on each other, refuses `--resume`,
  `--items` and `--repeat` above 1. It sets `EVH_REPLAY=1`, so a system can refuse real calls under it. Its fingerprint's
  `deployment.code` names the record, the deployments' hash and each commit with its item count.
- **A candidate**: `replay: {…, commit: <sha>}` runs every item at that commit; the arm a change is measured as.
- **Faithfulness**: `evh faithfulness --system REPLAY --dataset D --production RUN` replays every item at the recorded commits and
  compares each with production's arm (a recorded arm, §15b) by the adapter's `same(a, b)`. It writes
  `data/faithfulness/<id>/<n>.json` once: the counts, each disagreement with both sides, and the coverage (per
  commit, the functions of the system the replay entered and those it never did: a rule no item reaches is named).
  Each version's summary goes into the code record's `faithfulness` (agreed of items, the named exceptions, the
  record), which the Models page and `evh model-show <id>` show.
- **The gate**: a replay, or a candidate made from it, is scored against a reference or label set (`run`, `rescore`,
  `run-promote`) only when the newest faithfulness record made with its adapter and support modules agrees on every
  item, on the same items and deployments. A disagreement whose cause is outside the system is named with
  `evh faithfulness-name --model ID --item I --cause "…"` (a person's decision, kept beside the record). Otherwise a
  person may pass `--unfaithful`: the run, its re-scores and baselines say "unfaithful replay" and who chose it, and
  the catalog marks the arm. An agent is refused both.
- **Not covered by the gate**: the system's `params` (a system's own setting a candidate may vary) and any data the
  adapter reads that is not one of its `support` files (a frozen world under the project): change those and run
  `evh faithfulness` again yourself. A system with compiled extensions cannot switch versions in one process and is
  refused.
- `evh faithfulness-show ID [--n N]` prints a record whole (the disagreements, who named which, the
  coverage); a replay's arm page names its code record and its faithfulness. `validate` V26 checks the records.
- **Production's own writes, hidden** ([RFC-031](../../docs/rfc/RFC-031-held-out-discipline-and-outcome-labels.md)
  P1). A frozen history carries production's own writes (its labels, its reopens); a variant replayed over it sees
  them and acts on production's decisions instead of its own. `replay: {…, hide: {kinds: [reopened]}}`
  passes the adapter `params["hide"]` (`kinds`, and `since`: the first replayed item's time); its stand-in hides
  production's own writes of those kinds made since then, the replay's own stand in for them, and a person's stay
  (they are history). The setting is part of the adapter's identity, so the gate needs a faithfulness record made with
  it: the default variant with hiding on must still reproduce production before any variant counts.
- **The history confound**: hiding cannot remove a person's reaction to an action production took and a variant did
  not. The adapter marks each such item (`Result.extra["history_confound"] = 1`); the run records `history_confound:
  {items, of}` and writes the ids to `confound.jsonl` beside it (a count only on a held-out side), and the run and
  every score on it say "history confound: N of M". `examples/replay-filing/` shows both (`filing_replay_hidden_v1`,
  `filing_candidate_v3_hidden`).
- **A past period at its own code** (RFC-031 P2). A window over several deployments mixes a fix's before and after.
  `evh periods ID [--system REPLAY --dataset D]` numbers the code record's deployed periods (each with how it was dated:
  `dated_by: pull`, or `commit` when the host no longer records the pull, approximate) and counts the items in each;
  `evh period-compare REPLAY --dataset D --candidate C [--production P] --period N` (or `--from T --to T`) reads the
  latest run of each on the period's items: what production recorded, the code that ran then (it must agree with
  production on those items, or the report says it does not count) and the candidate, with the paired test between
  the last two. Nothing is called: run them first.

## 16. Set up a model before you test it

An arm is a model *and how it is called*. Servers and providers choose defaults for what an arm leaves
unset — whether the model reasons first, how long a reply may run, which build of the weights a tag
names — and those defaults differ from model to model. An arm that leaves them unset compares the
defaults as much as the models. Settle them before the full run, on purpose, and write them down
(RFC-020, RFC-021).

```bash
evh model-new gemma4-12b --set kind=llm --set aliases.0=gemma4:12b   # the model's own facts
evh deployment-new gemma4-12b mac --set where=mac --set tag=gemma4:12b # one per place it runs
evh model-onboard --model-id gemma4-12b --deployment mac   # once per deployment: build, reasoning, JSON, determinism
evh arm-smoke --system my_system_v1 --dataset my_v1   # once per system, on its own task, before its full run
evh model-list                                       # what is onboarded, vetted (an arm smoke passed), where it runs
```

1. **Pin the build, per deployment.** Record the tag and its digest in the deployment's own record
   (`data/deployments/<model>/<deployment>.yaml`, `evh deployment-new` / `deployment-set`), one per place the
   model runs (`mac`, `dgx`, `x3`, a hosted route with its `provider_routing`). One tag name can name different builds on different
   machines (an MLX build on a Mac, an older pull on another host): compare digests across every deployment
   that will run the arm, and against the registry, before the first run. `evh model-onboard --model-id <model>
   --deployment dgx` probes one deployment and writes its onboarding. A system names the record and the
   deployment (`model_record: gem`, `deployment: dgx`); its run's fingerprint then takes the weights, server
   and hardware from that entry (`source: record`), and `metrics.json` records `deployment_id`.
2. **Smoke a few items.** `evh arm-smoke --system <id> --dataset <id>` runs three with the system's own settings and writes
   no run: each item's time and output, whether the scorer can read it, a projection of the full run, and
   whether the same item twice gives the same output. For an LLM arm it measures every model call: tokens
   out, whether it reasoned, whether an answer came back, why it ended. An adapter that makes several calls
   per item reports them as `meta["calls"]` (the triage example does). It prints each reply (its first 300
   characters; `--replies` for all), so you read what the model wrote, and what the smoke spent, saying whether
   that is the provider's bill or the system's price table; `--json` gives the same as values. SMOKE CHECK
   lists what to revisit. SMOKE PASS exits 0 and SMOKE CHECK exits 6 ([Exit codes](#exit-codes)). A flag is not a failure: a hosted model at
   temperature 0 can answer item 1 differently twice (`determinism: ... repeats will vary`) and the smoke exits 6, so a
   shell chain `evh arm-smoke ... && evh run ...` stops there; run them as separate commands.
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
   other eval's arms. Each onboarding, arm smoke and acceptance is kept as a dated check of the
   deployment it ran on (`evh deployment-show`, `--json` for all of them): an arm smoke on the deployment the arm
   names, or the model's only one. An arm smoke that passed is what makes the model *vetted* on the Models page.
   - *Onboarding finds the settings that work*: probe, read the flags, change the record's settings (with why),
     probe again, until it passes or what remains is the model's own nature. Some models cannot stop reasoning
     (gpt-oss: `none` and `low` both reason; a hosted route answers "Reasoning is mandatory"): set the least they
     take and accept the flag in the record, `accepted: {reasoning: "<why>"}`. Onboarding and arm smokes then
     report it as accepted, with the why, and do not count it against the status. What one deployment always
     raises goes on that deployment: `evh deployment-accept <model> <deployment> --flag "where it ran" --why "<a
     sentence>"` keeps it under its `accepted` and the decision in its checks. A hosted gateway has no build to pin (`where it ran`)
     and its repeats vary (`determinism`); another deployment of the same model is still checked.
   - Several machines may be onboarded at once: each command adds its check to its own deployment's record,
     re-read under a lock, so one never erases another's result.
5. **Know what a repeat measures.** A self-hosted model at temperature 0 gives the same output on the same
   machine every time: a second pass there adds nothing. The spread comes from other machines and other
   builds; a hosted model's repeats do vary.

## The data's format, and migrating it

A project's data has a format: one number, `format` in `data/project.yaml` (RFC-032). `evh init` writes it, and each
release reads one format. `evh migrate --check` compares the two:

```sh
evh migrate --check      # data format 7; this release reads 7 (exit 0), or ERROR (old-format) / ERROR (mismatch)
evh migrate --dry-run    # what each step would change, from the real steps on a scratch copy of the data; the project is not written
evh migrate              # the steps the data needs, each recorded as it lands
```

A project with no `project.yaml` is at format 0: the data in the old layout. Data a later release wrote is
refused (`mismatch`), naming that release. The steps (`evaluation_harness/migrations/`) each bring the data one format
on, and the format is recorded after each, so a step that fails leaves the project at the last one that held.

A dry run needs disk: it copies the data (and config.yaml and the config folders it names) into the project's ignored
`.build/`, runs every step on the copy so that each reads what the one before wrote, prints each step's counts from it and
deletes it. The copy is as large as the data while the dry run lasts (a SQLite project's database too); the project itself
is never written. Format 7 (RFC-033) moves a SQLite project's per-item rows into tables and then vacuums the database,
which needs free disk about the size of the database; a VACUUM that cannot run leaves the data moved and says so.

Before its first change, `migrate` copies a SQLite project's database beside it
(`data/project.sqlite-before-format-<n>-<time>`, `n` the format the data was at); restoring it is the undo, and once
the project works on the new format it can be deleted. A files project's undo is git: `migrate`
names the uncommitted changes under `data/` first. There is no step back down: a release's rollback after a migration
restores that copy, or git, and loses what was written since.

**A deployed project is migrated by its deploy.** Every deploy runs `evh migrate --check` on the data it ships and
stops when it fails (this repository's `infra/deploy/render.sh` does, on the release's copy of the data). A deployment
that keeps data of its own on the server (a database, captures, a Workbench) runs the migration as a deploy step, each a
gate: check the live data's format against the release's (keep `evh migrate --dry-run --json` with the deploy), stop
the writers (jobs finish or pause), back up, `evh migrate`, check the numbers its pages show, then switch to the
release; on a failure, restore the backup and the previous release together. The harness ships the commands; each
deployment's own scripts call them.

## Exit codes

Every command, `make` target and `evh` subcommand, for scripts and CI that branch on them:

| Exit | Meaning | From |
|---|---|---|
| `0` | done | every command |
| `1` | refused, nothing done: `ERROR (<kind>): <why>` on stderr ([Refusals](#refusals)) | every command |
| `2` | a usage error: an unknown command or argument (the usage is printed) | `evh`, every command's argument parser |
| `3` | the judge scorer is not validated; `--unvalidated` runs it labelled as such | `judge-score` |
| `4` | stopped early: the cost cap, or a judge call that kept failing; the partial results are kept and the same command resumes | `run`, `judge-score` |
| `5` | some of several runs failed; the others are kept | `sweep` |
| `6` | the command's checks ran and some failed; the output lists them | `validate`, `self-test`, `env-check`, `importer-check`, `arm-smoke`, `model-onboard`, `deploy-sheet --capture`, `label-mutants`, `exposure-check` |
| `7` | it ran and measured nothing | `run`, `judge-score`, `leaderboard --goal` (a goal whose measure no run records) |
| `70` | an error nothing caught: a traceback on stderr, from the harness or the project's own code (an adapter, a scorer) | `evh` |
| `75` | a server could not be reached: nothing is wrong with the command; run it again later and it resumes | `run` |
| `130` | interrupted (Ctrl-C) | `evh` |

Each number has one meaning, so a script or an agent branches on it without reading the text.
In a checkout, `make` runs the same scripts but exits `2` for any failed target; the script's
own code is in make's last line (`make: *** [Makefile:…: run] Error 4`).

## Refusals

A command that refuses exits `1` and prints one line on stderr, `ERROR (<kind>): <why>`, for example
`ERROR (not-found): no goal 'tickets_summry': one of tickets_summary`. The kind is one of the words below
and does not change when a message is reworded, so a script or an agent reads the kind and a person reads
the rest.

| Kind | Meaning |
|---|---|
| `not-found` | the dataset, run, arm, goal, file or other thing named does not exist |
| `bad-argument` | an option is missing, malformed, or not allowed with another |
| `would-overwrite` | what it would write is already there; it is never overwritten |
| `mismatch` | two things that must agree do not: datasets, hashes, a run and its system |
| `invalid-file` | a file the project wrote (a system, a scorer, a sheet, records) is malformed |
| `not-materialized` | the data is not on this machine: fetch or materialize it first |
| `not-enough` | too little to work on: too few items, arms or outputs |
| `nothing-measured` | the thing named is there and nothing it reads was measured (exit 7) |
| `not-public` | the text asked for is not shown on a public server or for a hidden dataset |
| `not-allowed` | a rule refuses it: a dirty build, a closed round, a bind beyond this machine |
| `not-configured` | a key, a cost cap, a build ref, an endpoint or the project's store is not set |
| `failed` | something outside the command failed: an importer, a server, a hook, the warm-up |
| `missing-dependency` | a package or a part of the installation is missing |
| `over-budget` | a round's budget is spent (what its runs spent and its running commands reserved) |
| `old-format` | the project's data is in an older format than this release reads: run evh migrate |

## The words a reader prints

The words a command prints for a verdict, a missing number or a refusal to say, as they are written in the code. A
script or a test may match them; one that matches another string is matching something that is not documented.

| Words | Printed by | Means |
|---|---|---|
| `an arm effect exists` / `NO detectable arm effect` | `evh leaderboard`, the "IS THE ORDERING REAL?" block: `global test (permutation on within-item ranks): p = 0.0002  ->  an arm effect exists` | the global test's p is under 0.05 / is not |
| `Not enough paired data for a significance test (K arm(s), N shared item(s))` | `evh leaderboard`, in place of that block | fewer than 2 arms, or fewer than 3 items every arm scored |
| `SIGNIFICANT` / `NOT-SIGNIFICANT` | `evh pair-test`: `verdict            SIGNIFICANT at 0.05`, or `Bonferroni/N     threshold 0.0125 -> NOT-SIGNIFICANT` with `--family N` | the paired p is at or under the level (0.05, or the family's threshold) / is not |
| `not separated`, `too few items` | the catalog's and the inspector's charts, as a row's verdict word | the tests do not support a difference from the leader / baseline; the pair shares too few items to test |
| `shares fewer than 2 items with the leader` (or `shares N items with the leader, in G <field> clusters: the clustered test needs at least 2`) | `evh goal-leaderboard` and the goal page, as the reason an arm is out (`X is out: ...`) | the arm cannot be tested against the leader, so it is shown and never recommended |
| `lower on asr_v1; higher on dev_v1` | `evh metric-list`, `metric-show` and the metric pages, for "which way is better" | the measure's datasets disagree: "mixed", with each dataset's answer |
| `neutral: a description` | the same, and the heading of `evh leaderboard` (`ranked by: output_words (neutral: a description)`) | a descriptive measure: it says what the output was, not whether it was good |
| `changed` | `evh run-compare`, in the verdict column | a descriptive measure moved; the other verdicts are `better`, `worse`, `identical` and `NOISE (<= x)` |
| `NOTE: <measure>: no goal or adapter says which way is better; read as higher-is-better (declare it)` | `evh leaderboard`, `run-compare` and `goal-leaderboard`; `evh validate` prints it as `note: V14 runs: ...` | the direction is the default (nothing declares it) |
| `internal error` | a public server (`catalog-serve --public`, the public MCP server), for a crash: `{"error": "internal error"}`, or `internal error: the command failed; it is reported to the server's maintainers` | a traceback is never shown to a public caller; the log and the error tracker have it |
| `—` | `evh cost-report`'s ratio column, and `evh rank-stability`'s rho and winner rate (`null` in `--json`) | nothing to divide by or to correlate: 0 billed against 0 recorded is no ratio, not 0 |
| `n/a` | `evh pair-test` and the other tests, where a p is printed | the paired differences do not vary, so the test has no p |

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
| `EVH_ACTOR` | who acts (RFC-027): `person:NAME`, or `agent:NAME` with `EVH_FOR`; recorded on every record a command writes (`--by` wins) |
| `EVH_FOR` | `person:NAME`: the operator an agent acts for (required with `EVH_ACTOR=agent:…`) |
| `EVAL_DATA_DIR` | the data root, when it is not `<project>/data` |
| `EVAL_STORE` | `files` or `sqlite`: the project's store, over its `config.yaml`'s `store:` (RFC-025; above) |
| `EVAL_STORE_READONLY` | `1`: open the project's database read-only (a release is; a folder that is not writable does it without this); a write is refused, never made |
| (see env-check) | `evh env-check` says where each set variable came from ((.env), (shell), (shell, over .env)) |
| `EVAL_GOALS_DIR` | read goals here instead of `<data>/goals`, relative to the project (for goals kept outside the data root) |
| `EVAL_MAX_COST_USD` | the most one command spends, every pass of `--repeat` together; the run stops, keeps its results, resumes; 0 runs only a system known to be free (provider echo, a recorded arm, or both prices declared 0) |
| `EVAL_MAX_RETRIES`, `EVAL_RETRY_MAX_DELAY` | retries around every provider call: 8 attempts, a 60 s backoff cap by default (`evh env-check` prints the values in force) |
| `EVAL_BUILD_REF` | the identity of the system under test (default: the git SHA) |
| `EVAL_HOST_LABEL` | a name for this machine, the runner (fingerprint v5's `runner.label`, outside its hash): latency of a model run in process, and the network part of a remote one, is comparable across runs only from the same runner |
| `EVAL_FINGERPRINT_WEIGHTS` | `1`: read only by the examples' shared code (examples/_shared/hf_identity.py), not by the package — hash a local model's weight files into the fingerprint |
| `EVAL_JUDGE_MAX_COST_USD` | a judge-score job's cost cap, alongside scorer's `cost_cap_usd` and `EVAL_MAX_COST_USD`: the smallest of the three is used, and judge-score refuses when none is set |
| `EVAL_FETCH_HEADERS` | JSON `{"host": {"Header": "value"}}` for URL items behind a login |
| `EVAL_NO_CACHE` | `1`: `family-test` recomputes instead of replaying an identical earlier run |
| `EVH_P_CACHE` | a file that keeps every estimated p of the paired test between processes (one JSON line each, read back exactly); every `evh` command (and `evh mcp`, and `evh catalog-serve`, also when started as `python catalog_serve.py`) uses `<project>/.cache/evh-p.jsonl` when it is unset; an empty value turns it off (ADR-0028). A library import (an adapter, a notebook) stores nothing unless it is set. A file that cannot be read is no cache; a read-only one is read and never written |
| `EVH_VIEW_CACHE_VALUES` | how many per-item scores the view cache keeps in a process that answers more than one view (`catalog-serve`, the MCP server, a notebook): default 2,000,000, ~72 bytes each (this repository's catalog is 1.4 million, ~100 MB); a catalog that does not fit is answered right and not made faster. Lower it for a process with less room, such as the public inspector's 384 MB container |
| `EVH_FREEZE_ROWS` | `1`: every row the kept-rows cache holds is frozen (RFC-033): a view or command that changes a row it shares with other readers raises `TypeError` where it does, and a copy (`copy.deepcopy`, `dict(row)`) is a plain dict. The harness's test suite runs under it; set it when writing code that reads rows |
| `EVH_VIEW_CACHE` | `0`: the view cache keeps nothing (every view is read from the data again); for a test that compares a view with and without it |
| `EVH_WORKERS` | how many child processes may draw a command's resampled tests at once (the same p's); default: the CPUs the process may use, capped by its container's CPU quota, so under one whole CPU none; `1` turns it off |
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
EVAL_BUILD_REF=v2.3.1                evh run --system ... --dataset ...
EVAL_BUILD_REF=sha256:ab12…          evh run --system ... --dataset ...   # image digest
EVAL_BUILD_REF=$(git -C ../my-system rev-parse HEAD)   evh run --system ... --dataset ...  # the system's repo
```

**Pin it.** An eval against a moving target measures the target's movement, and
you will spend a day attributing that to your change.

`evh validate` fails on any run whose build is `unknown`, and `evh run-promote`
refuses one — a baseline that names no system cannot be acted on.

---

## When a number looks wrong

In order, because each is cheaper than the next:

1. `evh validate` — is the tree even consistent?
2. `evh runs-list` — was the run from a dirty tree (`*`), or is that unknown (`?`)?
3. `--repeat 3` — is the delta inside the arm's own spread?
4. Same `dataset_id` on both sides? (`run-compare` refuses, but check the ids)
5. Scored against **silver**? A run's `metrics.json` records `reference_tier` — silver
   ranks arms, it does not establish correctness.
6. Did a source change? `evh dataset-materialize --dataset-id ... --force`
   re-verifies every hash.
7. Do the runs share their conditions? `evh run-compare` names the fingerprint part that moved
   (instrument, data, deployment, settings); `evh comparison-show --runs a,b` names every condition that differs
   (the runner's machine and libraries, where the deployment ran, harness, scorer, items, reference bytes).
   The runner (where `evh` ran) is outside the fingerprint's hash: the same deployment run from two machines
   is the same measurement, and the runner is shown as a condition.

Most "regressions" are one of the first three.
