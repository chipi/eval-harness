# 0.8.0: building what the field comparison found

**Status:** 2026-11-05. The work list from [FIELD_ALIGNMENT_0.8.0.md](FIELD_ALIGNMENT_0.8.0.md), with the owner's
decisions of 2026-11-05: cover every item now; the licence is an optional field with an easy way to choose one;
the dataset version is designed properly; Hugging Face specifics (revision pinning, its parquet files, publishing)
wait for the providers step, and what is built now is the common ground every dataset home will use; every source
we can think of is in scope later; error tagging is in 0.8.0.

Each package below is built, tested and committed on its own, in this order. A package that needs a design decision
says so and gets a short design note before its code.

## A. Statistics (the build order's step 3)

| # | what | why (report §) | size |
| --- | --- | --- | --- |
| A1 | **Clusters.** `--cluster FIELD` on `pair-test`, `family-test`, `goals` and the inspector's tests: the sign-flip test flips one sign per cluster on the cluster's summed difference; a cluster-robust interval; `bootstrap-test` resamples clusters. The field comes from the dataset's item fields. | 2.3: items that share a source are not independent (Miller 2024); the triage data has 236 decisions over 172 sources | small-medium |
| A2 | **Contenders by equivalence.** A contender is an arm whose whole interval for its difference from the leader lies inside the margin, not "not significant and within 2% on the point estimate". Validated first: the 0.8.0-plan simulations re-run against today's `stats.py`, plus the interval's coverage at the margin for 0/1 and continuous measures, with and without clusters. | 2.3: a non-significant difference is not equivalence (Lakens 2017) | medium |
| A3 | **Can this dataset show a difference of X?** The minimum detectable effect for a goal's dataset and margin, using the clustered variance when a cluster is declared; shown on the goal and by a command. | 2.3: power before running (Miller rec. 5) | medium |
| A4 | **Named reducers for repeats**: `mean` (today), `majority` and `at_least_k` for 0/1 measures. | 2.3: inspect_ai epochs | small |

Owner decision in A2: what existing goals show when their contenders change (a note on the goal page and in
`goals --json` naming the rule that decided).

## B. Labels

| # | what | why | size |
| --- | --- | --- | --- |
| B1 | Krippendorff's alpha over more than two label sets at once, with a bootstrap interval. | 2.2 | small |
| B2 | Per item, how many person label sets agree with the reference: an `inspect` column, so contested items show. | 2.2: human label variation (Plank 2022) | small |

## C. Judging

| # | what | why | size |
| --- | --- | --- | --- |
| C1 | `scale: [0, 1]` documented as the start for a project's own judge; 1-5 kept where experts used it (SummEval). | 2.4 (Husain) | small |
| C2 | Per judge, the correlation of its score with output length, in the judging summary. | 2.4: length bias | small |
| C3 | A `note` when a rubric changes, carried like a promotion's reason. | 2.4: criteria drift (Shankar 2024) | small |

## D. Error analysis

| # | what | why | size |
| --- | --- | --- | --- |
| D1 | **Failure-mode tags.** A project declares a list of failure modes (like a field set); a person or an agent tags outputs in the sheet; tags are a new record (who tagged, when, on which run's output), counted per arm in `inspect` and on the goal. | 2.5: error analysis first (Husain); our weakest area | medium-large |

Needs a design note first: the record's shape, where it lives, how it joins runs and labels, and the sheet step.

## E. Datasets: the common ground every source uses

| # | what | why | size |
| --- | --- | --- | --- |
| E1 | **A `source` block** on the dataset record: provider, ref, revision (whatever pins the bytes), config, split, gated, the description's sha256. Provider-neutral: no key belongs to one host. | 2.1, 3.2.1 | small |
| E2 | **Licence, optional, easy to choose.** `licence` (an SPDX id, or the publisher's text and a URL); `evh licences` lists the common ones with a line each (as GitHub's picker does); `--licence` on the dataset-making commands checks the id against that list. No dependency: the list ships with the package. | owner 2026-11-05 | small |
| E3 | **The dataset version, designed.** Today `version` is always `"1.0"` and means nothing. Design note first (below). | owner 2026-11-05 | small-medium |
| E4 | **A `card` block**: the questions a datasheet asks, as a subset of Croissant's responsible-AI keys (collection, annotation protocol, limitations, biases, uses, personal information, maintenance). | 2.1 (Gebru, Pushkarna, Croissant RAI) | small |
| E5 | **The source interface and registry**: `resolve`, `describe`, `items`, `item_url`, optional `publish`, resolved by name like the capture importers. The local folder and the URL manifest become its first two sources, with no change in behaviour. | 3.1 | medium |
| E6 | **Croissant 1.1 out**: `evh dataset-card --dataset-id D [--format croissant]` shows the card and exports JSON-LD, lineage mapped to `prov:` keys, labels' guidelines to the annotation keys. | 2.1, 2.7 | small-medium |
| E7 | **Croissant 1.1 in**: a `croissant` source that reads any Croissant file or URL, which Hugging Face, Kaggle and OpenML all publish. This is the one source that reaches several homes without code for each. | 2.1, 3 | medium |
| E8 | **Field sets proposed from a source's features** (a choice for a class label, number, text), shown for the person to accept; never declared silently. | 2.1 | medium |
| E9 | **Migrate the committed datasets** to the new record (no shim), the profile reads `source` from the dataset, and a validate rule (the next free code after V20) checks the new blocks. | 3.2.1, 3.2.4, 3.2.6 | small-medium |

### E3 design note: what a dataset's version is

A dataset is frozen: its id names one set of items, byte for byte, and a change is a new id (`tickets_v1` →
`tickets_v2`), linked by `derived_from` / `extended_from` / `split`. That is already a version history; what is
missing is a number a reader and other tools understand.

Proposal (for the owner):

- **The id stays the identity.** Nothing cites a dataset by a version number.
- **`version` becomes the dataset's content version, MAJOR.MINOR, computed at freeze time from its lineage**, never
  typed: a first dataset is `1.0`; one made from another adds `0.1` when it only adds items (`extended_from`, or
  `derived_from` with only `added` ids) and `1.0` when it removes or changes any (a new major). A split's two sides
  keep their parent's major and record which side they are.
- **`schema` names the record format** (today implicit), so a reader knows which keys to expect.
- On export the version is Croissant's `version`; on import a source's own version (an HF commit, a Zenodo version
  DOI, an OpenML integer) is the `source.revision`, not ours.
- Migration: each committed dataset gets the version its lineage gives.

## F. Documentation

| # | what | why |
| --- | --- | --- |
| F1 | REFERENCE "The same words elsewhere": repeat = epochs, a label with several answers = `target` list, card, cluster, `prov:` lineage. | 2.6 |
| F2 | INFLUENCES: Miller 2024, Plank 2022, Lakens 2017, Shankar 2024, Husain, Gebru, Pushkarna, Croissant; why our checksum proves the selection, not the file; why one reference is scored (one domain expert). | 2.1, 2.5 |

## Left for the providers step (owner, 2026-11-05)

- Hugging Face: reading by pinned revision (`resolve/<sha>`, parquet at a ref), its metadata, the README written
  from the card, publishing. `pyarrow` is decided then.
- Kaggle (`kagglehub`?), OpenML, Zenodo as sources of their own: after E7 shows how far Croissant alone reaches.

## NOT covered by this plan

- Sizes are estimates from the report, not measured.
- A2's outcome is open until the simulations run: if no interval holds its level for 0/1 measures at small n, the
  rule says "too few items to call a tie" there, and that changes what small goals show.
- D1's shape is not designed yet; its size can move.
- E7 depends on how complete real Croissant files are (HF's puts a placeholder where the sha256 belongs, report
  §2.1): an import may have to fetch and hash every file itself.
- Nothing here has been checked against the fleet's feedback that is still to come.
