# 0.8.0: realignment with the field, and what it brings

**Status:** 2026-11-05, step 2 of the 0.8.0 order in [RECONCILE_0.8.0](RECONCILE_0.8.0.md). Read-only analysis of
branch `080` (code = v0.7.2). Every claim about our code cites the file and line read; every claim about the field
cites the page read on 2026-11-05. Where something could not be checked it says "not verified". Nothing here is
decided: each recommendation is for the owner.

## 1. Summary

**What this changes for 0.8.0: two statistics fixes move ahead of the dataset work, and the dataset work gets a
concrete shape.** First, the tie rule (step 3) should be rebuilt as an *equivalence* check on the interval we already
compute, not on "not significant": the field's position (Lakens 2017) is that a non-significant difference is not
evidence of no difference, and `axes.py:50-59` makes an arm a contender on exactly that. Second, our paired test
treats every item as independent (`stats.py:116-168`), while Miller's *Adding Error Bars to Evals* (2024) shows that
items drawn in related groups need clustered errors (2-3x wider on his examples) and inspect_ai ships
`stderr(cluster=...)`. Our triage dataset is that case: 236 decisions over 172 fingerprints
(`HF_DATASETS_0.6.0.md:88`). A cluster option on the sign-flip test is small and belongs with step 3, because the tie
rule's interval must be the right width. Two candidates named earlier turned out to be **already shipped**:
chance-corrected label agreement (Cohen's kappa, Krippendorff's alpha with MASI distance, `_label_sets.py:106-149`,
0.6.0) and multi-answer labels (`_label_sets.py:62-73`); they need no work, only a line in INFLUENCES.

For datasets (step 4), the finding is that **our dataset record says nothing about where its items came from, under
what licence, or at which upstream revision**. `ag_news_200.json` holds `dataset_id`, `version: "1.0"`,
`description`, `created_at`, `source_dir` and items, nothing else; the schema forbids anything else
(`dataset.schema.json:7`). The Hugging Face name lives only in each `fetch.py` and a gitignored side file, and the six
public fetchers read the latest revision with no pin (`hf_rows.py:111-113`; the `/rows` API takes no revision). The
field has converged on one provider-neutral description, **MLCommons Croissant** (a format, not a host: 1.0 March 2024,
1.1 January 2026), which Hugging Face, Kaggle and OpenML emit. The recommendation is: a small `source` block and a
`card` block on our dataset record (Datasheets/Data Cards questions, keyed so they map 1:1 to Croissant and its RAI
extension), Croissant 1.1 as the import/export format, and a provider interface modelled on the capture importers that
already exist (`_importers.py:3-71`). Local folders and URL manifests are already two providers (`dataset_create.py`,
ADR-0003); making them the first two implementations of the interface, before Hugging Face, is what proves "no default
provider".

## 2. Area by area

Size: **small** = one module and its tests, under a day; **medium** = a command or a schema change with docs, a few
days; **large** = a new subsystem or a change across commands.

### 2.1 Datasets and metadata

| field practice | source | what we do | gap | recommendation | size |
|---|---|---|---|---|---|
| A dataset carries its licence as a field (`license`, required in Croissant; `license` in the HF card YAML; `licence` in OpenML's API) | [Croissant 1.0 spec](https://docs.mlcommons.org/croissant/docs/croissant-spec.html) (required: name, description, license, url, creator, datePublished); [HF card spec](https://raw.githubusercontent.com/huggingface/hub-docs/main/datasetcard.md); OpenML `GET /api/v1/json/data/61` (read 2026-11-05: `"licence":"Public"`) | No licence on a dataset: `dataset.schema.json:8-77` has no such key and `additionalProperties: false`. Licences live in prose (`DATA.md:240-250`) and in `fetch.py` docstrings. Model records do have one (`model.schema.json:14`) | A reader of a dataset file, or a publish command, cannot know the terms | **Adopt**: `licence` (SPDX id where one exists, else the publisher's text and a URL) in a `source` or `card` block. Whether it is required is an owner decision (AG News's is `unknown`, `DATA.md:243`) | small |
| Pin the upstream revision a dataset was read at | HF: every dataset has a commit `sha` (read `GET /api/datasets/fancyzhx/ag_news` 2026-11-05: `eb185aad…`); TFDS `name:MAJOR.MINOR.PATCH` ([versioning](https://www.tensorflow.org/datasets/datasets_versioning)); Kaggle `owner/dataset/versions/N` ([kagglehub](https://github.com/Kaggle/kagglehub)); Zenodo one DOI per version plus a concept DOI | Our own two HF datasets pin a tag (`signal-fleet-dedup/fetch.py:26,41`; `triage-fleet/fetch.py:47,78`). The six public ones do not: `/rows` is called with dataset, config, split, offset, length only (`hf_rows.py:111-113`), and the parquet fallback reads the current conversion (`hf_rows.py:44`). The profile's `source` has name, url, config, split, no revision (`profile.schema.json:27-35`) | Item hashes still catch a silent change (materialize refuses), so no wrong number can result; but we cannot say which upstream version we sampled, and cannot re-fetch it after an upstream change | **Adopt**: record the resolved revision at freeze time. For HF public sets that means reading by revision through `resolve/<sha>/<file>` or the parquet files at a pinned ref, not `/rows`, which has no revision parameter ([rows docs](https://huggingface.co/docs/dataset-viewer/rows)) | medium |
| A dataset card answering fixed questions: motivation, composition, collection, preprocessing/labelling, uses, distribution, maintenance | [Datasheets for Datasets](https://arxiv.org/abs/1803.09010) (Gebru et al., v8 2021); [Data Cards](https://arxiv.org/abs/2204.01075) (Pushkarna et al., FAccT 2022); HF `README.md` card | `description` is one free string (`dataset_create.py:234`), defaulting to "N item(s) from X/" (`dataset_create.py:405`). The HF card we wrote by hand for triage (`HF_DATASETS_0.6.0.md:75-91`) already answers most Datasheets questions | No structured place for intended use, limitations, collection, labelling | **Adapt**: a short `card` block whose keys are a subset of Croissant RAI properties (`dataCollection`, `dataAnnotationProtocol`, `dataLimitations`, `dataBiases`, `dataUseCases`, `personalSensitiveInformation`, `dataReleaseMaintenancePlan`: [RAI spec](https://docs.mlcommons.org/croissant/docs/croissant-rai-spec.html)), so one record exports to Croissant, a Datasheet and an HF README. Do not copy the whole Datasheets questionnaire: most of it is about training corpora | medium |
| Provenance as machine-readable links | Croissant 1.1 `prov:wasDerivedFrom`, `prov:wasGeneratedBy`, `prov:wasAttributedTo` ([1.1 spec](https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html)) | We already have richer lineage than the spec asks: `derived_from` with added/removed/changed ids (`dataset_create.py:179-194`), `made_from` a capture with its query and sha256 (`dataset.schema.json:42-59`), `extended_from` picks (`:33-41`), `split` (`:31`) | None in substance; only the vocabulary differs | **Keep**, and map on export: `derived_from`/`extended_from`/`split.from` → `prov:wasDerivedFrom`, `made_from` → `prov:wasGeneratedBy`, the capture's importer and its sha256 → the activity | small (part of export) |
| Content checksums | Croissant recommends `sha256` per FileObject; HF's generated Croissant puts a placeholder there (`"sha256": "https://github.com/mlcommons/croissant/issues/80"`, [HF Croissant docs](https://huggingface.co/docs/dataset-viewer/croissant)); OpenML gives one `md5_checksum`; Zenodo `md5:` per file (read 2026-11-05) | sha256 per item (`dataset_create.py:390`), one digest over all items in the run's fingerprint (`_fingerprint.py:650-664, 727-736`) | We are finer-grained than every provider | **Keep**, and say why in INFLUENCES: a provider's file checksum proves the file; ours proves the selection a number was measured on | — |
| Typed features | HF `dataset_info.features`; Croissant `RecordSet`/`Field` with `dataType`; `/rows` returns `features` | Field sets with eight types (`fieldset.schema.json:20`), declared by the project, not part of identity (`_fields.py:1-9`) | No mapping from a provider's features to a field set; an item is "a file", its columns are not described | **Adapt**: on import, propose a field set from the provider's features (choice for a `ClassLabel`, number, text); never auto-declare silently | medium |
| Configs and splits | HF `configs`; Croissant `cr:Split`; lm-eval `validation_split`/`test_split` ([task guide](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/task_guide.md)) | `config` and `split` only in the gitignored rows file and the profile (`hf_rows.py:82-88`); our own split is `dataset-split` → `_validation`/`_test` (`dataset.schema.json:31`) | Upstream config/split not on the dataset record | **Adopt** in the `source` block; **keep** our own split vocabulary (validation/test already matches the field) | small |
| Gating and access | HF `extra_gated_fields`, `gated` (API returned `gated: false` for AG News); private repos | `text: hidden` controls what is published (`dataset.schema.json:32`, `_release.py:5-14`); tokens per role (ADR-0005) | No record that a source needs a login or an agreement | **Adopt** a `gated` flag in `source`; the provider reads its own credential | small |
| Semantic version of a dataset | Croissant 1.1 `version` MAJOR.MINOR.PATCH; TFDS the same | A new version is a new id (`_v2`), recorded with its lineage (`GUIDE.md:84-87`). The key `version` is always `"1.0"` (`dataset_create.py:234`) and means nothing a reader can use | `version` collides with the field's meaning | **Owner decision**: drop `version` or rename it to a schema version; on export, Croissant `version` can be derived (a new id with only `added` ids is a MINOR, any `removed`/`changed` a MAJOR) | small |
| Live datasets | Croissant 1.1 `isLiveDataset` | Production datasets are frozen captures (`PRD-014` non-goals: no drift detection, no schedule) | None: we freeze on purpose | **Keep** | — |
| A row viewer link per item | HF viewer `…/viewer/{config}/{split}?row=N` | Implemented (`hf_rows.py:49`, `dataset_profile.py:131-154`) | HF only, through a side file | **Adapt**: `item_url(locator)` becomes a provider method (§3) | small |

### 2.2 Labels and references

| field practice | source | what we do | gap | recommendation | size |
|---|---|---|---|---|---|
| Chance-corrected agreement between annotators | Krippendorff's alpha, Cohen's kappa; PRD-002 cites Artstein & Poesio 2008 | **Shipped in 0.6.0**: `compare()` returns same, share, Cohen's kappa, Krippendorff's alpha (nominal, or MASI when a label accepts several answers) and the confusion matrix (`_label_sets.py:94-149`, kappa at `:145`, alpha at `:146`); tested on a textbook table (`tests/test_label_sets.py:333-339`) | Two sets at a time only; no interval on kappa/alpha | **Keep**. **Adapt** (optional): alpha over more than two sets at once (alpha is defined for any number of coders), and a bootstrap interval on it, so "alpha 0.62" says how sure. The earlier candidate "raw counts only" was wrong | small |
| Human label variation: disagreement is signal, not noise; evaluate against un-aggregated labels | [Plank 2022](https://arxiv.org/abs/2211.02570), EMNLP (a position paper: it names the problem across data, modelling and evaluation; the abstract prescribes no single method) | A label may accept several right answers, `{"accept": [...]}` (`_label_sets.py:62-80`), which is "more than one answer is right", not "annotators differ". Several sets can coexist on one dataset, one per source (`_label_sets.py:1-15`), and are compared; a reference is promoted from one set (ADR-0022) | We keep the disagreement (sets are never merged), but scoring reads one reference; no score against the spread of several person sets | **Keep-and-say-why** for scoring: a goal needs one yardstick, and Husain's practice (below) puts one domain expert in charge of it. **Adapt** for reporting: show, per item, how many person sets agree with the reference, so a reader sees which items are contested (an `inspect` column from data we already hold) | small |
| Multiple acceptable targets | inspect_ai `Sample.target: str \| list[str]` ([datasets](https://inspect.aisi.org.uk/datasets.html)); HELM references tagged correct | `{"accept": [...]}` (`_label_sets.py:62-73`) | None | **Keep**; add the mapping to REFERENCE "The same words elsewhere" | small |
| Annotation guidelines recorded with labels | Datasheets "labeling" questions; Croissant RAI `dataAnnotationProtocol` | A set records its guideline's path and sha256 (`_label_sets.py:152-164`) | Not exported anywhere | **Keep**; map to `rai:dataAnnotationProtocol` and `rai:annotationsPerItem` on export | small |
| Model-written labels declared as such | Croissant RAI `machineAnnotationTools` | Source `model` with its run (`_label_sets.py:38`), tier silver/gold on references (ADR-0020) | None | **Keep**; map on export | — |

### 2.3 Statistics and uncertainty

| field practice | source | what we do | gap | recommendation | size |
|---|---|---|---|---|---|
| Clustered standard errors when items come in related groups | [Miller 2024](https://arxiv.org/html/2411.00640), recommendation 2 (clustered SEs 3.05x naive on DROP, 1.88x on MGSM, 1.10x on RACE-H); inspect_ai `stderr(cluster="category")` ([metrics](https://inspect.aisi.org.uk/metrics.html)) | The sign-flip test flips each item's sign independently (`stats.py:144-152`); above 30 items the interval is a t interval over items (`stats.py:332-337`). No cluster argument anywhere in `stats.py` | p-values and intervals too narrow when items share a cluster (triage: 172 fingerprints over 236 decisions, `HF_DATASETS_0.6.0.md:88`; SciFact queries sharing documents not checked) | **Adopt**: `--cluster FIELD` on pair-test/family-test and in the inspector: flip one sign per cluster on the cluster's summed delta (a cluster permutation), and a cluster-robust interval. The key comes from a choice/text field (fields already exist per item) | small-medium |
| Paired differences, not two separate means | Miller rec. 4 | Paired sign-flip on per-item deltas (`stats.py:353-402`; `pair_test.py:24-30`) | None | **Keep** | — |
| Reduce within-item variance by resampling and averaging | Miller rec. 3; inspect_ai epochs with reducers (`mean`, `mode`, `pass_at_k`, `at_least_k`) | `--repeat N` writes `<id>_r1..rN` (`_runs.py:197-220`); repeats are averaged per item before the test (`pair_test.py:24, 386`) | Only the mean is offered as the reducer | **Keep**; **adapt** (optional): name the reducer, and add `majority`/`at_least_k` for 0/1 measures, under our word "repeat", mapped to inspect's "epochs" in the glossary | small |
| Power analysis before running | Miller rec. 5 | `min_attainable_p(n)` (`stats.py:315-317`) and `rank-stability` (`cli.py:93`); no minimum detectable effect | No "can this dataset detect a difference of X?" | **Adopt** in step 8 (test looks and power, already planned); the MDE must use the clustered variance when a cluster is declared | medium |
| A non-significant difference is not equivalence | [Lakens 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5502906/), TOST | `balanced`: a contender is "not significantly different AND within the 2% margin" on the point estimate (`axes.py:50-59`); `frugal`: not significantly different alone | On a small or noisy set every arm is a contender, and the cheapest wins: the less data, the more ties | **Adopt**: a contender is an arm whose whole interval for the difference from the leader lies inside the margin (TOST at the same alpha, read off `exact_ci`, `stats.py:320-350`). This is RECONCILE's step 3, and it needs the 080-plan simulations re-run (RECONCILE §6) | medium |
| Multiple comparisons | Holm 1979; Demšar 2006 | Holm (`stats.py:300-312`), joint Holm across groups (`stats.py:418-446`), Friedman/Nemenyi in the leaderboard (`cli.py:88`) | None | **Keep** | — |
| Corpus-level metrics | bootstrap; Dror et al. 2018 | `bootstrap-test` for macro-F1, documented as anti-conservative (REFERENCE §Statistical tests, `docs/REFERENCE.md:311-326`) | A cluster bootstrap is not offered | **Adapt** together with clustering: resample clusters, not items, when a cluster is declared | small |

### 2.4 Judging

| field practice | source | what we do | gap | recommendation | size |
|---|---|---|---|---|---|
| Validate the judge against people before trusting it | [Shankar et al. 2024](https://arxiv.org/abs/2404.12272) | A gate: the scorer must name a committed validation run per judge, or every number is labelled "unvalidated" (`judge_score.py:12-14`); SummEval validation against experts | The gate checks a validation exists, not that it transfers (a stated non-goal, PRD-003) | **Keep** | — |
| Criteria drift: grading outputs changes the criteria | Shankar et al. 2024 | A declared task is hashed into the judging set (`judge_score.py:28-31`), so a changed rubric is a new set | Nothing records why a rubric changed or which outputs led to it | **Adapt** (optional): a `note` on a rubric change, carried like a promotion's reason | small |
| Binary pass/fail over Likert scales | [Husain, evals FAQ](https://hamel.dev/blog/posts/evals-faq/) | `grade` on a declared integer scale, default 1-5 (`judging.py:61, 86-95`); `pick` and `pairwise` (`judging.py:15-18`). A `[0, 1]` scale passes the check at `judging.py:95` | Binary works but is not documented or offered as the default for new scorers | **Adapt**: document `scale: [0, 1]` as the recommended start for a project's own judge; keep 1-5 for SummEval, where the experts used it | small |
| Position bias, noise, self-preference | widely reported; our own design | Position pass (second shuffle / swapped pair) and noise pass (`judge_score.py:127, 462-472`); same-vendor-family gap (`judge_score.py:1174, 1217-1222, 1291`) | No length-bias check: a search for "length bias"/"verbos" in `judge_score.py`, `judge_panel.py` found nothing | **Adopt** (optional): report the correlation of judge score with output length per judge in `summary.json`, from data already stored | small |

### 2.5 Error analysis and inspection

| field practice | source | what we do | gap | recommendation | size |
|---|---|---|---|---|---|
| Error analysis first: read ~30, then ~100 traces; open coding (free notes), then axial coding into a failure taxonomy | Husain, evals FAQ | `inspect --item`, `--where`, `--by` a choice field (`catalog_views.py:1283`), `--crosstab` (`catalog_views.py:1360`), a sheet with `note` columns that `sheet-import` reads back (`catalog_views.py:1341`) | Notes land in label sets (per item), not per arm's output; there is no place for "failure mode" categories on an output, and nothing counts them | **Adapt**: a per-output tag set ("failure modes": a choice list the project declares, like a field set) filled in the sheet's note step and counted per arm in `inspect`. This is the field's first activity and our weakest surface. Scope is an owner decision: it is a new record type | medium-large |
| One domain expert decides quality ("benevolent dictator") | Husain, evals FAQ | Promotion by one `--by` with a reason (PRD-002 FR3.1); tiers say whose labels | None | **Keep**, and cite it: it is why one reference is scored, not a vote | — |
| Per-group results | inspect_ai `grouped(accuracy(), "category")` | `--by` with one Holm correction over all groups (`stats.py:418-446`) | None; ours corrects across groups, inspect's `grouped` does not say it does (not verified) | **Keep** | — |

### 2.6 Vocabulary and concepts

The glossary in `docs/REFERENCE.md:374-415` already maps our words to inspect_ai, lm-evaluation-harness, HELM, OpenAI
evals, Braintrust, LangSmith, Langfuse and Hugging Face. Rows to add, none of which renames anything:

| our word | field word | source | recommendation |
|---|---|---|---|
| repeat (`--repeat N`) | epochs (inspect_ai), repeats (lm-eval `repeats`) | [inspect metrics](https://inspect.aisi.org.uk/metrics.html); [lm-eval task guide](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/task_guide.md) | add to the glossary |
| a label accepting several answers | `target: list[str]` (inspect_ai) | [inspect datasets](https://inspect.aisi.org.uk/datasets.html) | add |
| dataset `description` + (proposed) `card` | dataset card (HF), datasheet (Gebru), Data Card (Google), Croissant RAI | §2.1 | add when the card exists |
| `derived_from`, `made_from` | `prov:wasDerivedFrom`, `prov:wasGeneratedBy` (Croissant 1.1) | §2.1 | add |
| (proposed) cluster | cluster (Miller; inspect `stderr(cluster=)`) | §2.3 | adopt the field's word as is |
| contenders | — (no field equivalent found); the nearest is "practically equivalent" (TOST) | Lakens 2017 | keep the word; define it by the equivalence rule once step 3 lands |
| `version` on a dataset (always "1.0") | `version` = content version (Croissant, TFDS) | §2.1 | **owner decision**: drop or rename to `schema_version` |
| arm | variant / configuration; no framework uses "arm" (`docs/REFERENCE.md:381` shows "—" in every column) | — | keep (already explained in REFERENCE) |

### 2.7 Agent and automation surface

| field practice | source | what we do | gap | recommendation | size |
|---|---|---|---|---|---|
| Machine-readable dataset metadata an agent can fetch | Croissant JSON-LD; HF `/api/datasets/<id>/croissant` (200 for `fancyzhx/ag_news`, read 2026-11-05) | `evh datasets --json` (MCP read tools, RECONCILE §Agent-ready) | Our own description is not in any standard form | **Adopt**: `evh dataset-card --format croissant` (the export of §2.1), so an agent reads our datasets with the same tooling it uses for HF's | small, after 4b |
| Provider tooling agents already use | HF has an MCP server (used by this session, authenticated as `chipi-nbgd`) | Not used by the harness | — | **Keep** out of the core: an agent can use the provider's own tools; the core needs only the provider interface | — |

## 3. Dataset providers

What each home exposes, read on 2026-11-05. "Read" means the page or API answered; "not verified" means it did not, or
was not tried.

| provider | what it is | pull | metadata | revision pin | licence | auth | publish | read how |
|---|---|---|---|---|---|---|---|---|
| **Local folder** (today) | files under `--source-dir` | yes (`dataset_create.py:362-394`) | none | git commit of the sources, if tracked | none | none | — | code |
| **URL manifest** (today, ADR-0003) | one URL per item, pinned by sha256 | yes (`dataset_create.py:118-176`, `_fetch.py`) | none | the sha256 is the pin | none | none | — | code |
| **Hugging Face Hub** | git repos of files; a viewer; a parquet conversion | `resolve/<rev>/<path>` (used: `triage-fleet/fetch.py:78`); `/rows` (no revision); parquet listing (current conversion only) | card YAML (licence, task, configs, features); Croissant at `/api/datasets/<id>/croissant` (HTTP 200 read) | commit `sha` from `/api/datasets/<id>` (read: `eb185aad…` for AG News); tags | `cardData.license` (read: `unknown` for AG News) | token for private/gated | yes, plain HTTP: create, commit (NDJSON), tag, read back, delete, all tested 2026-10-30 (`HF_DATASETS_0.6.0.md:139-151`) | API + docs |
| **Kaggle** (Google) | versioned datasets | `kagglehub.dataset_download('owner/name/versions/N')` | Croissant: the documented URL `kaggle.com/datasets/<owner>/<name>/croissant/download` returned **404** for `uciml/iris` without login: **not verified** | `versions/N` | not verified | token (`KAGGLE_API_TOKEN`, `~/.kaggle/access_token`, legacy `kaggle.json`) | `kagglehub.dataset_upload` makes a new version | [kagglehub README](https://github.com/Kaggle/kagglehub). Whether a plain HTTP API works without the `kagglehub` package: **not verified** |
| **OpenML** | datasets with versions, mostly tabular | `parquet_url` per dataset (read) | JSON description: `version`, `licence`, `creator`, `citation`, `default_target_attribute`, `md5_checksum` (read `GET /api/v1/json/data/61`) | integer `version` per name, and a dataset id per version | `licence` (read) | none to read | upload exists (not verified) | curl, 2026-11-05. Croissant per dataset: the file URL I tried did not answer: **not verified** |
| **Zenodo** (CERN) | archive with DOIs | files per record | `metadata` with title, creators, license, keywords, relations (read) | one DOI per version, a concept DOI across versions (read: `doi`, `conceptdoi`) | `license.id` (read: `cc-by-4.0`) | token to publish | REST deposit API (not verified) | curl `GET /api/records`, 2026-11-05 |
| **TFDS** (Google) | a catalogue of builders, not a host: a builder downloads from the original source | `tfds.load('name:1.2.0')` | builder info | MAJOR.MINOR.PATCH with stated semantics | in builder metadata (not verified) | — | — (you write a builder) | [TFDS versioning](https://www.tensorflow.org/datasets/datasets_versioning) |
| **Google Dataset Search** | a search engine over schema.org `Dataset` markup on publishers' pages | — | — | — | — | — | — | No official public API found ([Google blog](https://blog.google/products/search/making-it-easier-discover-datasets/)); third parties sell scraping APIs. Not a provider |
| **MLCommons Croissant** | **a format, not a host** (spec 1.0, 2024-03-01; 1.1, 2026-01-29). MLCommons reports Croissant on Hugging Face, Kaggle and OpenML ([announcement](https://mlcommons.org/2026/02/croissant-1-1-standard/)) | via `mlcroissant` (a library) | the format | `version`, `sha256` per FileObject | `license` required | — | — | spec pages above |
| **Google Data Cards** | **a documentation framework**, not a host or an API | — | — | — | — | — | — | [paper](https://arxiv.org/abs/2204.01075) |
| Dataverse, CKAN | data repositories reported to load Croissant | not verified | not verified | not verified | not verified | not verified | not verified | named in the MLCommons announcement only |

So of the owner's three examples, only Hugging Face is a host. "Google" is three things (Kaggle a host, TFDS a
catalogue, Data Cards a documentation practice); "MLCommons" is the description format. The interface therefore has
two halves: **sources** (where bytes and metadata come from) and **one description format** (what we store and
export), and the format is not owned by any source.

### 3.1 The minimum common interface

Modelled on the capture importers, which already resolve built-in, project and path implementations by name and record
the implementation's sha256 (`_importers.py:9-13, 43-76`). A source is a class:

```text
resolve(ref) -> Pinned
    ref: the provider's own address ("fancyzhx/ag_news", "owner/name/versions/3", a Zenodo DOI, a folder, a manifest)
    Pinned: {provider, ref, revision, resolved_at}; revision is whatever makes the bytes reproducible
    (HF commit sha, Kaggle version, OpenML id, Zenodo version DOI, git commit, or null for a manifest,
    whose per-item sha256 is the pin)

describe(pinned) -> Description
    the provider's metadata, normalised to our card keys (title, licence, licence_url, creators, citation,
    task, configs/splits, features, gated, url), plus the raw document and its sha256, plus the provider's
    Croissant when it offers one

items(pinned, config, split, select) -> iterator of {item_id, bytes, locator, fields}
    select: first n / seeded n / ids; locator: the provider's address of the item (row number, file path, URL)

item_url(pinned, locator) -> str | None          the viewer link (today hf_rows.VIEWER)

capabilities: {"publish": bool, "gated": bool, "needs_token": bool}

publish(dataset, card, target, private=True) -> Pinned        optional; only when capabilities say so
```

Rules that keep the loop the same whichever source: everything after `items()` is today's code (freeze, hashes,
materialize, labels, runs); the dataset record stores `Pinned` and the `Description` hash, never a provider-specific
key; the core imports no source until one is named (as `_importers.py:13`); a source reads its own credential (ADR-0005
pattern); no source is a default, and `dataset-create` with no source named keeps today's folder behaviour as one
source among others.

### 3.2 What the core needs that does not exist yet

1. **A `source` block on the dataset record** (`Pinned` plus config, split, licence, gated, the description's sha256).
   The schema forbids new keys (`dataset.schema.json:7`), so it is a schema change and a migration of the 20 committed
   datasets (owner's rule: migrate, no shim). Today that information is in `fetch.py` files and a gitignored
   `*.rows.json` (`hf_rows.py:72-96`).
2. **A `card` block** (§2.1), and `evh dataset-card` to show it and export it as Croissant 1.1 JSON-LD and as an HF
   README.
3. **A source registry** like `_importers.resolve`, and `dataset-create --source NAME --ref REF [--config C --split S
   --select …]`. The six example `fetch.py` files would become calls to it (their sampling rules stay in the examples).
4. **The profile reading its `source` from the dataset**, not from the side file (`dataset_profile.py:131-154`).
5. **A publish command** with refusals reusing `_release.py:5-14` (`text: hidden`, not redistributed, licence not
   permitting, dirty tree), private first, read-back sha256 check. The tested HTTP calls exist only in a scratchpad
   script (`HF_DATASETS_0.6.0.md:148-151`); nothing is committed.
6. **A validate rule** for the new blocks (the next free code after V20, `validate_tree.py:35-41`).
7. **No new dependency for Hugging Face or OpenML or Zenodo pulls**: their JSON and file APIs answered to plain HTTP.
   Kaggle may need `kagglehub` (not verified), and HF's parquet path needs `pyarrow`, which only the examples have
   (`hf_rows.py:183`). Each is an owner decision.

## 4. What this changes in the 0.8.0 build order

| step | change |
|---|---|
| 1 agent fixes | none |
| 2 this analysis | done; the owner decisions are listed at the end of this section |
| 3 tie rule | **Widen it to "equivalence plus clusters".** (a) a contender is an arm whose interval for the difference lies inside the margin (TOST), replacing "not significant and within 2% on the point estimate" (`axes.py:50-59`); (b) `--cluster FIELD` on the paired test and the interval, done first, because (a) reads that interval. Re-run the 080-plan simulations (`research/internal/stats-0.8.0/` on 080-plan) with both |
| 4a interface | Use §3.1. **Implement the folder and the URL manifest as the first two sources** (no behaviour change, tests unchanged), so the interface is proven neutral before any remote source |
| 4b description format | Internal: the `source` and `card` blocks (§3.2.1-2). Interchange: Croissant 1.1 (with RAI keys) for export and import; HF README generated from the card. Do not store HF YAML or any provider's document as our format |
| 4c second source | Hugging Face first (pull by pinned revision, metadata, Croissant, and the publish calls already tested). For the second, prefer **Zenodo or OpenML**: both answered unauthenticated JSON on 2026-11-05 and have different version models (DOI per version; integer version), which tests the interface harder than a second git-like host. Kaggle third: login needed and its Croissant URL was not verified |
| 4d round trip | HF publish from the card (private first, read-back by sha256). Zenodo publish needs a token and was not tried |
| 4e validate recomputes hashes | Extend to the new blocks: the description's sha256 against the stored raw document; re-resolving a revision over the network stays opt-in, so validate stays offline |
| 5 actor + per-goal baselines | The actor maps to Croissant `prov:wasAttributedTo` on export; nothing else changes |
| 6 background runs | none |
| 7 prompt versions / item failures / code_ref | `code_ref` maps to `prov:wasGeneratedBy` for datasets made by code (captures); item failures should be counted, never dropped, as `UNPARSED` already is (`_labels.py:19-22`) |
| 8 studies / test looks | Power and MDE (Miller rec. 5) live here and must use the clustered variance when a cluster is declared |

New items not in the order, each small, for the owner to place: per-item "how many person sets agree with the
reference" in `inspect` (§2.2); alpha over more than two sets with an interval (§2.2); binary scale documented for new
judges and a length-bias line in judge summaries (§2.4); glossary rows (§2.6); INFLUENCES gains Miller, Plank,
Lakens, Shankar, Husain, Gebru, Pushkarna, Croissant. One medium-large item: failure-mode tags on outputs (§2.5).

**Owner decisions this raises:** licence required or optional on a dataset; the fate of `version: "1.0"`; whether the
six public fetchers switch from `/rows` to revision-pinned files (it changes how the examples fetch, and may need
`pyarrow`); which second source; whether failure-mode tags are in 0.8.0; `kagglehub`/`pyarrow` as dependencies.

## 5. NOT covered / NOT verified

**Not read at all:**

- The Chip Huyen books themselves; only INFLUENCES' summary of them (`INFLUENCES.md:18-28`). No claim here rests on them.
- The full text of Plank 2022, Gebru et al., Pushkarna et al., Shankar et al.: only abstracts. Their specific
  recommendations beyond the abstracts are not cited and not verified.
- Miller 2024 was read through the arXiv HTML summary of its five recommendations and its three cluster ratios, not
  the derivations; whether its cluster-robust formula matches a cluster permutation test is my reasoning, not his.
- HELM and OpenAI evals docs were not re-read this time; their rows rely on REFERENCE's table of 2026-11 (`docs/REFERENCE.md:374-405`).
- Other frameworks and tools not looked at: promptfoo, DeepEval, Ragas, Weave, Phoenix, MLflow evaluate, lighteval's
  details, Argilla (labelling), Label Studio. Their vocabulary and methods are not mapped.
- 2025-2026 eval-methodology papers beyond the ones named (e.g. on benchmark contamination, LLM-judge reliability
  surveys, item response theory for evals such as tinyBenchmarks, agent evals). Not searched; "current thought
  leadership" here means Miller, Husain, Shankar, Plank, Lakens, Croissant only.
- The Croissant 1.1 spec was read through a summary of its changes; the full property list, ODRL policy shapes and
  `usageInfo` were not checked against a validator. `mlcroissant` was not installed or run.
- The HF dataset-card spec: only the list of YAML keys; the semantics of `dataset_info` features were not checked.

**Not verified (tried, or a claim I could not check):**

- Kaggle: the Croissant download URL returned 404 for `uciml/iris` unauthenticated; whether it needs a login, a
  different slug, or no longer exists is unknown. Kaggle's licence field, and whether its REST API works without
  `kagglehub`, were not tried.
- OpenML: a Croissant file per dataset (the URL I guessed did not answer); upload API not tried.
- Zenodo: publish/deposit API not tried; the `version` field was null on the one record read, so the per-version
  model rests on its `doi`/`conceptdoi` fields only.
- TFDS licence metadata; Dataverse and CKAN Croissant support (named only in MLCommons' announcement).
- Google Dataset Search: "no official public API" means I did not find one, not that none exists.
- Whether HF's `/api/datasets/<id>/parquet/...` listing can be pinned to a revision (the code reads the current
  conversion, `hf_rows.py:44`); whether `refs/convert/parquet` can be read at an older commit was not tried.
- Whether inspect_ai's `grouped()` applies any multiple-comparison correction.
- Whether SciFact, Few-NERD or CNN/DM items fall into clusters large enough to change any published verdict. The
  clustered test was not run on any committed data; the size of its effect on our numbers is unknown, and it may
  change none of them.
- The equivalence rule's effect on existing goals and their contenders: not simulated here; the 080-plan simulations
  exist and were not re-run.

**Not done in this analysis:**

- No code was changed, no test run, no paid call made.
- The size estimates are judgement from reading the code, not from a prototype.
- `harness/tests/` was read only for the kappa test (`test_label_sets.py:333-339`); the other claims about shipped
  behaviour rest on the code, not on running it.
- The UXS pages (`docs/uxs/`) and the catalog's pages were not checked for where a card, a source block or failure
  tags would appear.
- The 0.8.0 drafts on branch 080-plan were not re-read; this report relies on RECONCILE's account of them.
- No search for prior internal analyses of Datasheets or Croissant beyond `HF_DATASETS_0.6.0.md`, which (read in full)
  maps neither; RECONCILE's open question (`RECONCILE_0.8.0.md:287-288`) is answered: it does not.
