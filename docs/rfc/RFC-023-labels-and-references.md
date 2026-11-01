# RFC-023: Labels, and the references promoted from them

- **Status**: Accepted (owner, 2026-11-01), built in steps (0.6.0, planned): the commands named here do not exist
  until their step lands, and the marker comes off when the last one does.
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-002](../prd/PRD-002-references.md) (references: gold, silver),
  [PRD-014](../prd/PRD-014-datasets-from-production.md) (datasets from production)
- **Related RFCs**: [RFC-019](RFC-019-datasets-from-production.md) (captures; its references from outcomes are
  replaced here), [RFC-002](RFC-002-run-records-and-derived-runs.md) (derived runs: a recorded arm is one),
  [RFC-022](RFC-022-scoring-that-evolves.md) (re-scoring)
- **Related ADRs**: [ADR-0020](../adr/ADR-0020-second-references-are-silver.md) (superseded when this is accepted)
- **Code**: `reference_create.py`, `reference_from_outcomes.py` (replaced); new label, pick, extend, recorded-arm and
  deploy-sheet commands; `rescore.py`, `experiment_run.py` (scoring against labels); `catalog_views.py` (the
  inspector's rows); `catalog_build.py`, `catalog_serve.py` (the views; the pages never write); `_common.py`,
  `_models.py`, `catalog_serve.py`, `mcp_server.py` (several projects at once)

## Abstract

A **label** says what the right answer for one item is, and who said it: a person, a model, or a rule over what
production recorded. Labels are cheap and ongoing; an item can have several. A **reference** is labels you
**promote**: a governed, frozen set for one dataset, chosen on purpose, with a reason, at the tier you decide.
Who labelled is the label's source, never its tier: a person's labels can be poor and never promoted.

Evaluating what production did scores production's own decisions, the deployed config and candidates against
labels; it never creates a reference. Exploring those results row by row shows what is worth keeping; you **pick**
those items, and a later version of a governed dataset is made from its items and the picks you choose.

## Problem

The owner's flow (2026-11-01):

1. On the datasets we have, we establish gold and silver references, work in rounds, try, settle on something.
2. Silver and gold, as always.
3. We deploy the models we think are good.
4. They run in production for some time.
5. We get data from production as new datasets: all of it, a sample, or whatever we choose.
6. We evaluate, on these new datasets, how the models in production work.

And then: after many rounds of step 6, make the next version of a key dataset from a few production records that
would most help the model's quality, and re-establish its references.

The harness cannot do steps 6 and after:

- **`reference-create` asks a model what it would do and calls the answer a reference.** `--from-run` makes a
  run's outputs the reference; `--config` runs an arm in a pass of its own for the same. Both are a model doing the
  task, not anyone saying what is right. On new production data that is a test run, not a reference.
- **Labelling lives outside the harness.** The triage example's gold came from the example's own scripts
  (`label_sheet.py`, `label_with_model.py`, `write_verdicts.py`, `write_gold.py`); every gold reference in this
  repository came from a dataset's own labels (`fetch.py`) or from those scripts.
- **The tier is taken on the user's word.** `reference-create --config … --tier gold` is accepted as
  "human-reviewed"; a file copied into `references/gold/` is never checked. Only gold from a run is refused.
- **References from outcomes stretched "silver"** (ADR-0020) to mean a third thing, and their command defaults
  to the name `gold/<dataset>` (`reference-from-outcomes --name`'s help), against that ADR.
- **Production's own decisions cannot be scored**: the baseline arm re-runs production's model; what production
  decided is in the capture and reaches no scorer.
- **Nothing shows what to keep, or keeps it**: the dataset page lists items, the inspector shows one in full, and
  no view puts the signals that matter side by side; there is no list of candidates and no way to build a version
  from some of them.

## Design

### Labels

- **A label set** is one labelling pass over one dataset by one source: `data/labels/<dataset>/<set>/`, one
  `<item_id>.txt` per labelled item (the text a scorer reads, as a reference's item is today) and `labels.json`:
  the dataset, the set's name, its **source**, when, each item's sha256, and an optional note per item.
- **The source** is one of:
  - `person`: who (`--by`), from a sheet they filled;
  - `model`: the run whose outputs were taken, with its config and fingerprint;
  - `rule`: a mapping over a capture's recorded outcomes, with the rule file's hash, whoever wrote the outcome
    (owner, 2026-11-01).
- **A set records the guideline it was labelled by** when there is one: the sheet's instructions, a labelling
  prompt, the rule file, hashed into `labels.json`, so two sets labelled by different guidelines are never read as
  one ("it's hard to annotate data, but it's even harder to create annotation guidelines", AIE ch. 8). Optional
  (owner, 2026-11-01).
- **A set is never edited.** A correction is a new set; the old one stays, so a score always says which labels it
  used. An item without a label in a set is not scored against that set.
- **Labels follow the item, not the dataset** (owner, 2026-11-01): a set records each item's sha256, and an item
  with the same bytes in another dataset (a later version, a production dataset) has the same labels. An edited
  item has another hash, and its old labels do not follow it.

### References

- **Promotion is the only way to make one.** `reference-promote` copies the chosen labels into
  `references/<tier>/<name>/`, the layout runs, rescore and goals read today, unchanged; its manifest records
  `promoted_from: {labels, source}`, the reason, who and when.
- **The tier is decided at promotion**, not by the source, and no rule constrains it (owner, 2026-11-01): you
  choose which labels become a reference and at which tier. The promotion records the set's source beside the
  tier, so a reader always sees both.
- Runs keep recording `reference_id` and `reference_tier`; goals and rounds read references as today.

### Scoring against labels

- `evh rescore --labels D/S` (and `experiment-run --labels D/S`) scores against a label set without promoting it.
  The run records `scored_against: {labels: D/S, source}` in place of a reference, and every view names it by its
  source: "against your labels of 2026-11-15", "against model M's labels".
- As built (step 4, 2026-11-01): the run records `reference_id: labels/<dataset>/<set>` and `reference_tier:
  labels` in place of a separate field, so every reader resolves it through one function (`scored_against_dir`) and
  none can take it for gold or silver; the fingerprint hashes the set's files. Only a set of the run's own dataset
  is scored against (labels are read by item id); one on another dataset is promoted first. A re-score goes to
  `data/runs-labels-<dataset>-<set>/`, a plain runs folder every reader already finds, never the re-score place goals
  read in place of a run. An arm scored against a `model` set of its own outputs is flagged, as a reference's author
  is.
- A goal suggests a finalist for a group scored against a label set as it does for a reference's group, the group
  headed by its labels; you choose the baseline either way (owner, 2026-11-01).

### Production as an arm, and agreement

- `evh arm-from-capture --dataset-id D --capture C --as production_2026_11` makes **a recorded arm**: one output
  per item, from what production recorded, through an adapter hook `recorded_output(record) -> str` (triage: the
  record's `fleet_disposition`, as the decision JSON the scorer reads). No model is called; it is a derived run
  (RFC-002, `derived.kind: recorded`) naming the capture, scored and compared like any arm.
- **Agreement** is how often two arms decided the same, per item, through an adapter hook `same(a, b)` (default:
  the same text). The deployed config re-run against production's recorded arm says whether the replay is
  faithful; a candidate against it says where to look.

### The rows view: exploring, and what to pick

In the inspector, for one dataset (`evh inspect --dataset-id D --rows`):

- **One row per item**: its fields, production's decision, each chosen arm's decision, every label with its
  source chip, and the markers below. A row opens the item in full: its fields, the item itself, every output and
  every label.
- **The signals, each a filter and a sort**:
  - **wrong**: production's decision is wrong against a label set (for triage, a missed real problem or a false
    alarm), `--wrong-against SET`;
  - **disagree**: two chosen arms decided differently, `--disagree` (production the baseline by default);
  - **split**: the candidates disagree among themselves, a hard case, `--split`;
  - **new**: a field value the governed dataset has never had (an alert name, an evidence level, a source), a gap
    in its coverage, `--new-vs D_governed`;
  - **unlabelled**: no label in any set yet, `--unlabelled`;
  - and the inspector's `--where field:value` and `--by field`.
- **The pages never write** (owner, 2026-11-01, keeping PRD-004's non-goal and ADR-0004): the view selects, and
  gives the command. Select one row or several, and the page shows `evh pick --dataset-id D --item … --item …`
  for them, with a target, tags and a note to fill in, and `evh label-sheet --dataset-id D --item … ` to label
  them; you run it. A row already picked says so, and for which datasets.
- The terminal prints the same rows; `evh label-sheet --items disagree` puts the same rows in a sheet.

### Picks

- **A pick** is a production item marked as a candidate for one or more governed datasets: `evh pick --dataset-id
  <production dataset> --item <id> … [--for D …] [--tag key=value …] [--note "…"]`, the command the rows view gives
  for the rows you select. `--for` may
  name several datasets, or none yet; tags group candidates (`case=oom`, `kind=missed-regression`).
- **Where they wait**: the project's one list, `data/picks.jsonl`, in git like the rest of `data/` (owner,
  2026-11-01). Each line: the item, its sha256, where it came from (the production dataset, its capture), its
  targets, tags, note, who and when. The list is append-only: retargeting or retagging a pick (`evh pick --item X
  --for D2`) adds a line and the latest wins; `evh pick --drop X` drops it; the history stays.
- **Seeing them**: `evh picks [--for D] [--tag k=v]` lists what waits, per target (and those with none yet), each
  with where it came from, its labels by source ("none yet" says what to label first), its tags and note. The
  target dataset's page shows its picks waiting.
- **The project** is what it is today: the folder `evh` works in, with its `data/` (`EVAL_HOME`, a checkout, or the
  nearest directory up that has `data/`); see "Several projects in parallel".

### The next version of a governed dataset

- `evh dataset-extend <v1> --dataset-id <v2>` with `--picks` (every pick waiting for v1) or `--pick ITEM`
  (repeatable: the ones you choose, any pick): v1's items plus the chosen picks, the lineage recorded per item (the
  capture and production dataset each came from), as `dataset-create --from` records a version today. The picks
  used are marked used: they leave the waiting list and keep their history.
- **In the catalog** you tick which waiting picks to include and the page shows the exact command: making a
  version, like promoting a reference, is a governed step you run on purpose.
- **Its references**: the picked items arrive with their labels (labels follow the item); `evh labels --dataset-id
  <v2>` shows every set covering v2, and you promote the ones you choose. Nothing is promoted by the extension.

### The deploy sheet

After you promote an arm, `evh deploy-sheet --config <arm>` (and the arm's page) prints everything production must
match to run what you measured: the model and its build (the model record's deployment: tag, digest, server and
its settings), every setting the arm sends, the prompt and its hash, the adapter and its version, and the dataset
and reference it was promoted on. A capture whose records carry what production ran (for triage, the ledger's
`model`, `prompt_ver`, `prompt_sha`) is checked against it: "every captured decision was made by the promoted
model and prompt", or what differs. Without that check, step 6 can evaluate a model that is not the one in
production.

### Several projects in parallel

A project is a folder with its own `data/`; several run side by side, as several checkouts, each pinning its own
harness version. What a project writes is already its own (data, runs, `.cache/`, `.build/catalog`). Three things
are not, and are fixed here:

- **Ports.** `catalog-serve` (8765) and `mcp --http` (8766) have fixed defaults; a second project gets "port in
  use". Each project gets a stable port of its own, derived from its path (the same URL every time), the next free
  one if that is taken; the command prints the URL, and `--port` still overrides.
- **The shell's environment.** `EVAL_HOME`, `EVAL_DATA_DIR`, `EVAL_RUNS_DIR` and `EVAL_GOALS_DIR` override the
  project for every command in that shell. Every command notes when `EVAL_HOME` points away from the folder you are
  in; `catalog-serve` and a local catalog name their project (as built: ADR-0024).
- **A lock shared across projects.** A model record is written under `/tmp/evh-model-<model_id>.lock`, keyed by the
  id only; it is keyed by the record's path instead.

### What this does not do

The harness evaluates what production did, offline, after it did it. It runs no online evaluation (A/B, shadow,
canary) and does not detect drift; comparing one production dataset with the next shows a change after the fact.
The docs and the site say so and imply neither.

### Commands

| Command | What it does | Replaces |
| --- | --- | --- |
| `evh label-sheet --dataset-id D --out sheet.csv [--items unlabelled\|all\|disagree --runs A,B] [--item ID …] [--propose SET\|RUN]` | a sheet: item, a short view of it, what production or an arm decided, a proposal, an empty `label` column | `label_sheet.py` |
| `evh label-import sheet.csv --dataset-id D --set S --by NAME [--guideline FILE]` | the filled rows become a `person` set | `write_verdicts.py`, `write_gold.py` |
| `evh label-from-run --run R --set S [--guideline FILE]` | a run's outputs become a `model` set | `reference-create --from-run`, `--config` |
| `evh label-from-capture --dataset-id D --capture C --map rules.yaml --set S` | rules over recorded outcomes become a `rule` set | `reference-from-outcomes` |
| `evh labels [--dataset-id D]` | every set: source, coverage, guideline, how often two sets agree, what was promoted | — |
| `evh reference-promote --dataset-id D --labels S [--items …] --tier gold\|silver --reason "…"` | the chosen labels become a reference, recording the set, its source and the reason | `reference-create` |
| `evh rescore --labels D/S`, `evh experiment-run --labels D/S` | score against a label set, without promoting it | — |
| `evh arm-from-capture --dataset-id D --capture C --as NAME` | production's recorded decisions as an arm | — |
| `evh inspect --dataset-id D --rows …` | every row with its signals (wrong, disagree, split, new, unlabelled), to explore, label and pick from | — |
| `evh pick`, `evh picks`, `evh pick --drop` | mark an item for datasets (targets, tags, note), list what waits, drop one | — |
| `evh dataset-extend V1 --dataset-id V2 --picks\|--pick ITEM …` | the next version: v1's items and the chosen picks, with their lineage | — |
| `evh deploy-sheet --config ARM` | what production must match; checked against a capture | — |

The catalog and the inspector do the same where they can; every view or action has its command.

## The catalog

Page by page (UXS-001 and UXS-002 updated with the build):

- **Gold and silver, at a glance**: a large pill in each tier's own colour wherever a reference or a tier is named
  (the reference list, every "scored against", the goal's groups, the arm rows), in place of today's small word.
- **"Scored against"** everywhere names either a reference (with its tier pill) or a label set (with its source
  chip: person, model, rule; never gold or silver colours), so a number against labels is never read as one
  against a reference.
- **The Data menu**: Datasets, Captures, Labels, References.
- **The Labels page**: every label set, its dataset, its source chip, coverage (N of M items), its guideline, when,
  and what was promoted from it into which reference.
- **The dataset page**: a labels section (each set, its source, coverage, how often two sets agree); for a
  governed dataset, its picks waiting, each with where it came from, its labels, tags and note; select the ones to
  include and the page gives the `dataset-extend` command for them; for a version made from picks, the items it added, each
  with its capture, production dataset and the labels it carried.
- **The references page and each reference's page**: "promoted from <label set> (<source>), <date>: <reason>".
- **The Captures page**: beside the datasets made from each capture, the label sets on them and the recorded arm.
- **The arms page and an arm's page**: a recorded arm carries a "recorded" badge, its capture linked, no model,
  no cost, and a filter for it; a promoted arm's page shows its deploy sheet.
- **The goal page**: a group scored against a label set gets its suggested finalist as a reference's group does,
  headed by the set's source chip and name, never a tier pill; the deploy sheet beside the baseline, with whether
  production matches it.
- **The inspector** (UXS-002): label sets as "scored against", the disagreement filter, every label in the item
  view; the rows view with its signals as filters and sorts, and a selection that gives the `evh pick` and
  `evh label-sheet` commands for its rows. Nothing on a page writes.
- **The header** names the project the catalog was built from, and `catalog-serve` prints its own port, so two
  catalogs open side by side are never confused.

## The triage fleet, worked through

1. `evh capture` (sampled if large), `evh dataset-from-capture` → `orrery_triage_2026_11`.
2. `evh arm-from-capture … --as production_2026_11`: production's decisions, scored like an arm.
3. Run the deployed config (`triage_baseline_pro`) and round 3's leader on it.
4. `evh label-from-capture --map outcomes.yaml --set issue_verdicts`: your verdicts on the fleet's issues, where
   an issue reached the decision (a `rule` set).
5. `evh label-sheet --items disagree --runs production_2026_11,<leader> --propose issue_verdicts` (or the sheet
   the rows view's selection gives): you label where they disagree, plus a small random slice, then
   `evh label-import` → the set `owner_2026_11` (`person`).
6. `evh rescore --labels orrery_triage_2026_11/owner_2026_11`: production, the deployed config and the leader,
   against your labels; agreement everywhere; `evh deploy-sheet` says whether production ran what was promoted.
7. `evh inspect --dataset-id orrery_triage_2026_11 --rows --runs production_2026_11,<leader> --wrong-against
   owner_2026_11 --new-vs orrery_triage_v1_labelled`: where production was wrong on something v1 does not cover;
   pick those worth keeping, for `orrery_triage_v1_labelled`, tagged by case.
8. Steps 1 to 7 again on later captures; the picks accumulate (`evh picks --for orrery_triage_v1_labelled`).
9. A month on: `evh dataset-extend orrery_triage_v1_labelled --dataset-id orrery_triage_v2_labelled --pick … --pick
   …` (the seven you choose of the twelve waiting), then `evh labels --dataset-id orrery_triage_v2_labelled`, then
   `evh reference-promote … --tier gold --reason …`.

## Migration (no shims)

As built (step 3, 2026-11-01): every reference's manifest gains `promoted_from` and the reason; the 6 whose texts
are kept here became label sets, byte for byte (209 labels); the 14 whose texts are fetched elsewhere (a dataset's own
labels, not redistributed) record their source and no set, since a label set is never made of text that is not here.
Every reference's fingerprint digest was compared before and after: identical. `reference-create` and
`reference-from-outcomes` are removed in step 9, with the docs that teach them (owner, 2026-11-01).

As designed: each existing reference becomes a label set (its source from its manifest: a dataset's own labels or the owner's
verdicts → `person`; `from_run` → `model`; `from_outcomes` → `rule`) and a promotion record with the reason
"promoted before labels existed (0.6.0)". `reference-create` and `reference-from-outcomes` are removed; docs,
tutorials, the site and the CLI help move to the new commands. ADR-0020 is superseded; RFC-019's references from
outcomes are replaced.

## Alternatives considered

- **Keep `reference-create` and add labelling beside it.** Rejected: two ways to make a reference, one of which
  asks a model what it would do and names the answer a reference.
- **Tier from the source** (a person's labels are gold). Rejected by the owner: a person's labelling can be poor;
  promotion is the decision.
- **A judge in place of labels for step 6.** Rejected for now: a model saying what is right is a `model` label set
  made by a labelling prompt (`label-from-run` on a labelling arm), the same mechanism as everything else.
- **Picks per governed dataset.** Rejected by the owner: a good item is often seen before its target is known.
- **Building a version from the catalog.** Rejected: making a version is a governed step; the catalog shows the
  command.
- **Label and pick boxes that write through `catalog-serve`** (local only, never public). Rejected by the owner for
  now: the pages never write (PRD-004, ADR-0004); another way to label in the browser is a later question.

## Testing

- Each command and its refusals (a set edited in place; promotion without a reason; a pick of an item that is not
  in the named dataset; an extension with a pick that is already used).
- The migration on this repository's references, with every run's score unchanged (the reference files are the
  same bytes).
- Labels following an item into a new version by its hash, and not following an edited one.
- The rows view's signals on a small fixture, each against a hand-counted answer.
- Two projects at once: both serve their catalogs on their own ports, write their model records and run their
  arms, and neither sees the other's.
- The triage walk-through above as the acceptance case, on the fleet's 233 Orrery decisions split by time (owner,
  2026-11-01): the older half captured and made the governed dataset; the newer half captured as a continuation
  (`--since-capture`), standing in for production after deployment; step 6, the rows view and picks on it; then v2
  from the governed v1 and the picks chosen. `check_guide` runs the tutorial that teaches it.

## Decisions (owner, 2026-11-01)

- **A1** No tier rule is enforced: the promotion chooses, and records the source.
- **A2** Labels a rule reads from recorded outcomes are `rule` labels, whoever wrote the outcome.
- **A3** A goal suggests from a label set as from a reference; you choose.
- **A4** The names: "label set", the sources `person`, `model`, `rule` (ours kept over the books' `hand` and
  `natural`; see [LABELS_ANALYSIS_0.6.0](https://github.com/chipi/eval-harness/blob/main/research/internal/LABELS_ANALYSIS_0.6.0.md)),
  and the commands in the table above.
- **A5** Labels follow the item by its sha256.
- **A6** One pick list per project; a pick names its targets (several, or none yet) and may carry tags.
- **A8** A label set records the guideline it was labelled by when one is given: optional (`--guideline FILE`),
  hashed into the set (owner, 2026-11-01: "1A").
- **A7** The pages never write (PRD-004's non-goal, ADR-0004, kept): the rows view and the dataset page select and
  give the command; labelling is the sheet.

