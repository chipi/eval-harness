# PRD-002: Labels, and the reference sets promoted from them

- **Status**: Implemented (v0.4.0) for gold, silver and re-scoring; labels (FR2), promotion (FR3) and scoring against
  labels (FR6) built for 0.6.0 ([RFC-023](../rfc/RFC-023-labels-and-references.md)); they replace
  `reference-create`
- **Authors**: Marko Dragoljevic
- **Related UX specs**: [UXS-001](../uxs/UXS-001-catalog.md) (the Labels and Reference sets pages, the tier pills, row
  tints), [UXS-002](../uxs/UXS-002-inspector.md) (what the inspector refuses to compare; labels in the item view),
  [UXS-003](../uxs/UXS-003-cli-and-onboarding.md) (the label and promotion commands)
- **Related RFCs**: [RFC-023](../rfc/RFC-023-labels-and-references.md) (labels and promotion),
  [RFC-002](../rfc/RFC-002-run-records-and-derived-runs.md) (derived runs: re-scoring onto another reference)
- **Related ADRs**: [ADR-0022](../adr/ADR-0022-references-are-promoted-labels.md) (a reference set is labels you promote)
- **Related PRDs**: [PRD-001](PRD-001-evals-and-comparison.md), [PRD-003](PRD-003-judging.md),
  [PRD-014](PRD-014-datasets-from-production.md) (labels on production data)

## Summary

Most quality metrics score an output against what each item's answer should be. A **label** says that for one
item, and who said it: a person, a model, or a rule over what production recorded. Labels are cheap and ongoing;
an item can have several, from several sources. A **reference** is labels you **promote**: a frozen, governed set
for one dataset, chosen on purpose, with a reason, at the tier you decide. **Gold** and **silver** are tiers of a
reference, never of a label: who labelled is recorded on the label, and you decide what to promote and how. When
the reference changes, every arm is re-scored from its stored outputs for $0, and arms can be scored against a
label set without promoting it.

## Background & Context

Gold is expensive and often missing at the start; the common practice is to run the strongest model, read its
outputs and score cheaper arms against what it wrote. Before 0.6.0 that was `reference-create`: it asked a model
what *it would do* and made the answer the reference, so a model doing the task and someone saying what is right
were the same command. Labelling itself lived outside the harness (the triage example's own scripts), the tier was
taken on the user's word (`--tier gold` was accepted as "human-reviewed"), and a second reference from outcomes
stretched "silver" to mean a third thing (ADR-0020). Evaluating production data (PRD-014) needs someone to say
what was right on new items without making a reference each time.

The reasoning is in [Concepts: Gold is not silver, and a label is not a reference](../../harness/docs/CONCEPTS.md#gold-is-not-silver-and-a-label-is-not-a-reference); the analysis
against the books in [LABELS_ANALYSIS_0.6.0](https://github.com/chipi/eval-harness/blob/main/research/internal/LABELS_ANALYSIS_0.6.0.md).

## Goals

- Every scored number says what it was scored against: a reference with its tier, or a label set with its source.
- Silver and gold numbers are never ranked together or tested against each other; nor are numbers against two
  different label sets.
- A label always says who gave it (`person`, `model`, `rule`), when, and the guideline it followed.
- A reference is made only by promoting labels, with a reason, and says which set it came from and its source.
- A run's outputs can become labels without a second paid pass, recording the run, its config and fingerprint.
- Labels follow an item by its content, into later versions and other datasets with the same item.
- Changing the reference costs nothing: stored outputs are re-scored, never regenerated.
- How far silver drifts from gold can be measured once gold exists.

## Non-Goals

- **No labelling in the pages.** The pages never write (PRD-004); a person labels in a sheet
  (`label-sheet`, `label-import`), and the inspector's selection gives the command that makes one.
- **No tier rule.** Nothing makes a person's labels gold or forbids a model's: the promotion decides and records
  the source beside the tier (owner, 2026-11-01).
- **No automatic promotion**: no command makes a reference as a side effect.
- No redistribution of a dataset's gold where its licence does not allow it; the examples fetch it
  ([Data & licences](../DATA.md)).

## Personas

- **The engineer with no gold yet**: needs a usable yardstick today, labelled for what it is.
- **The annotator or domain expert**: labels a subset, later, in a sheet.
- **The engineer evaluating production**: needs labels on new items without making a reference each time.
- **The reviewer**: needs to see at a glance which numbers rest on whose labels, and at which tier.

## User Stories

- _As an engineer, I run a frontier model as an arm, read its results, and take that run's outputs as a label set
  (`evh label-from-run --run … --set …`), so the labels are exactly what I read._
- _As an annotator, I get a sheet of the items to label (`evh label-sheet`), fill the `label` column, and import it
  as my set (`evh label-import … --by me`)._
- _As an engineer, I promote the labels I trust into a reference (`evh reference-promote … --tier gold --reason …`),
  and the reference says where they came from._
- _As an engineer, I score arms against a label set without promoting it (`evh rescore --labels D/S`)._
- _As a researcher, when gold arrives after the runs, I re-score every run against it for $0._
- _As a reviewer, I see which arm's outputs a table's labels came from, so I do not read its row as a result._

## Functional Requirements

### FR1: Two tiers, on references

- **FR1.1**: Gold lives in `data/references/gold/<dataset_id>/<item_id>.txt`; silver in
  `data/references/silver/<name>/`, each with a `manifest.json`.
- **FR1.2**: A run records the reference it was scored against (`reference_id`, tier) and a hash of the reference's
  bytes inside its fingerprint (RFC-001), so an edited reference file shows as a different measurement.

### FR2: Labels (0.6.0)

- **FR2.1**: A label set is `data/labels/<dataset>/<set>/`: one `<item_id>.txt` per labelled item and
  `labels.json` (the dataset, the set, its source, when, each item's sha256, an optional note per item, and the
  guideline's hash when one is given).
- **FR2.2**: The source is `person` (`--by`), `model` (the run, its config and fingerprint) or `rule` (the rule file's
  hash).
- **FR2.3**: `evh label-sheet` writes a sheet of the chosen items (`--items unlabelled|all|disagree`, `--item`), with
  what production or an arm decided and an optional proposal; `evh label-import` makes a `person` set of the
  filled rows. The sheet is CSV that Excel opens and saves (UTF-8 with its mark; `,` or `;`); `--choices`
  writes the allowed answers into the label column's header and the import refuses any other; a workbook
  (.xlsx) is refused, saying how to save it as CSV. The local inspector downloads the same sheet.
- **FR2.3b** (0.6.0): The sheet of `evh inspect --sheet … --csv FILE --fill label` is filled the same way, and
  `evh sheet-import FILE --dataset-id D --by WHO --set S` makes its `label` column a set: `person`, or `model` with
  `--kind model` when a tool filled it. A filled `pick` or `score:` column is a judgement, not a label: it becomes
  unvalidated judged runs (`--scorer`, PRD-003), never a label set.
- **FR2.4**: `evh label-from-run --run R --set S` makes a `model` set of a finished run's outputs and calls nothing;
  it refuses what `run-promote` refuses (a dirty tree, an unknown build), an unfinished, derived or other-dataset
  run, an empty output and outputs that stopped at `max_tokens` (`--allow-cut-off`).
- **FR2.5**: `evh label-from-capture` makes a `rule` set from a capture's recorded outcomes (PRD-014).
- **FR2.6**: A set is never edited; a correction is a new set. Labels follow the item by its sha256.
- **FR2.7**: `evh labels [--dataset-id D]` lists every set: source, coverage, guideline, and how often two sets
  agree (FR2.10); the pages show what was promoted from it (UXS-001).
- **FR2.8**: `evh validate` V19 checks every set's labels against the sha256 it recorded.
- **FR2.9**: A label is one right answer, or several when more than one is right for the item (owner, 2026-11-02),
  written `{"accept": ["escalate", "file"]}`, sorted and without repeats; the sheet's `also right` column, a rule's
  `label: [a, b]` and a folder's text make one. A decision is wrong against a label when it is none of them; a
  scorer reads a reference through `answers()`.
- **FR2.10**: Two label sets are compared on the items both label: on how many they accept the same answers, on
  how many they share one (counted apart, never as agreement), Cohen's kappa and Krippendorff's alpha (nominal,
  or with MASI distance when a label accepts several answers; Artstein & Poesio 2008), and the confusion matrix.
  Free-text labels are not compared as text.

### FR3: Promotion (0.6.0)

- **FR3.1**: `evh reference-promote --dataset-id D --labels S [--items …] --tier gold|silver --by WHO --reason "…"`
  copies the chosen labels (the set on this dataset, or `DATASET/SET` on another with the same items) into
  `references/<tier>/<name>/`; the manifest records `promoted_from` (the set, its dataset, its source), the reason,
  who and when, and for a `model` set who authored the texts (its config, model and run). A reason must be a
  sentence; a reference set is never overwritten.
- **FR3.2** (0.6.0): `reference-create` and `reference-from-outcomes` are removed; `label-from-run` keeps their
  refusals and `--not-redistributed`, `label-from-capture` their rule language.
- **FR3.3**: Every existing reference records how it was promoted ("promoted before labels existed"), with every
  run's fingerprint unchanged (its texts and authorship are what runs hash). Its texts kept here are copied byte for
  byte into a label set; a reference whose texts are fetched elsewhere (a dataset's own labels, not redistributed)
  records its source and no set (`harness/tools/migrate_references_to_labels.py`).

### FR4: The arm whose outputs became the labels

- **FR4.1**: The leaderboard marks it (`arm *`, with a note) when a reference promoted from its `model` set is the
  one scored against.
- **FR4.2**: The catalog tints its row and a goal page flags it, so it is never a group's leader
  ([UXS-001](../uxs/UXS-001-catalog.md)).

### FR5: Changing the reference

- **FR5.1**: `evh rescore --dataset-id … --reference-id gold/… --out data/runs-gold` re-scores every run's stored
  outputs against another reference, $0, into a separate directory; the originals are never touched (RFC-002).
- **FR5.2**: A re-scored run records the reference it was first measured against (`reference_id_at_measurement`).
- **FR5.3**: `evh silver-calibrate --dataset-id …` reports how far silver references drift from gold.
- **FR5.4**: The inspector, on a metric scored against a reference, does not test an arm scored against another
  reference than the baseline's; it names it and says why ([UXS-002](../uxs/UXS-002-inspector.md)).

### FR6: Scoring against labels (0.6.0)

- **FR6.1**: `evh rescore --dataset-id D --labels SET` and `evh run --config C --labels SET` score against
  a label set of the run's own dataset without promoting it (a set on another dataset is refused: promote it, or
  label this one). The run records `reference_id: labels/<dataset>/<set>` and `reference_tier: labels`, and its
  fingerprint hashes the set's files. A run scored against a set, measured or re-scored, is written beside the
  runs, `data/runs-labels-<dataset>-<set>/`: an arm of its own, never one more run of the config's arm on gold or
  silver, and never where a goal reads a re-score in place of a run.
- **FR6.2** (0.6.0): Every view names it by its source (the set's source chip and name, made by whom and when on
  the labels page), never as a reference or with a tier; arms against different sets are never compared, as for references
  (FR5.4).
- **FR6.3**: A goal suggests a finalist for a group scored against a label set as it does for a reference's group
  (PRD-005); the arm whose outputs a `model` set holds is flagged, as the author of a reference is, and never
  recommended; the baseline stays your choice.

## Success Criteria

- A label set from a run records where it came from, and the refusals above hold (today
  `harness/tests/test_reference_from_run.py`; its successor tests `label-from-run`).
- The migration leaves every run's score unchanged: the reference files are the same bytes.
- No table on the pages or in the terminal ranks a silver-scored arm with a gold-scored one, or arms scored against
  two different label sets.

## Related Documents

- [RFC-023](../rfc/RFC-023-labels-and-references.md), [ADR-0022](../adr/ADR-0022-references-are-promoted-labels.md).
- [RFC-002](../rfc/RFC-002-run-records-and-derived-runs.md): derived runs.
- [Runbook §11, adjudicating disputed gold](../../harness/docs/RUNBOOK.md#11-adjudicate-disputed-gold).
