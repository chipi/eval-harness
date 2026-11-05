# 0.8.0: the plan

**Status:** 2026-11-05. The one current plan for 0.8.0 (branch `080`, from v0.7.2). It brings together the
reconciliation of the agent-ready drafts with what 0.5.0 to 0.7.2 shipped, and the comparison with the field
([FIELD_ALIGNMENT_0.8.0.md](FIELD_ALIGNMENT_0.8.0.md), the evidence). Each package is built, tested and committed
on its own; the owner decides scope and the open questions below.

## The order

1. Agent basics — **done** (pushed)
2. The comparison with the field — **done** (pushed)
3. **A** statistics → **B** labels → **C** judging → **D** error tagging → **E** datasets, the common ground →
   **F** documentation → **P** provider integrations → **S** scale to 1,000-10,000 items
4. Then the agent-ready pieces from the drafts: who acted and per-goal baselines, background runs, prompt versions
   and item failures, studies and test-set looks (their place after S is not confirmed by the owner)
5. **R** replay and faithfulness for code adapters (owner, 2026-11-05: in scope, at the end of 0.8.0)
6. The fleet agent's feedback, when it finishes (entries 19-22 and later)
7. Release

## 1. Agent basics — done

Exit codes with one meaning each (4 cost cap, 5 sweep partly failed, 6 checks failed, 7 nothing measured, 70
uncaught, 75 server not reached, 130 Ctrl-C); every refusal `ERROR (<kind>): <why>`, one of twelve kinds (owner:
a dozen general kinds, not one per situation); `--help` names the command; a cancelled MCP call stops its command;
`validate` survives a file that does not parse. Commit `df1540215`.

## 2. The comparison with the field — done

`FIELD_ALIGNMENT_0.8.0.md`. Owner decisions on it (2026-11-05): build every item now; the licence is optional,
picked easily from a list; the dataset version is designed properly; Hugging Face specifics wait for P and the
common ground comes first; every dataset home we can think of is in scope; error tagging is in 0.8.0.

## 3. The field items

### A. Statistics

| # | what | status |
| --- | --- | --- |
| A1 | Clusters: `--cluster FIELD`, a goal's `cluster:`; one sign per cluster, a cluster-robust interval, the bootstrap draws clusters | built, committed `3a17d7943` |
| A2 | Contenders shown no worse than the leader, Holm across the candidates (owner) (non-inferiority: Tango for 0/1 at any size, the bootstrap-t from 100 items or clusters, else "too few items to call a tie"); a strategy is a default margin: `quality_first` 0, `balanced` 5%, `frugal` 10% of the leader; a goal's margin wins; [ADR-0026](../../docs/adr/ADR-0026-contenders-by-non-inferiority.md) | built: Holm at one level, the unequal-cluster floor, the test shown on the page, `evh goals` and `pair-test --margin` |
| A3 | Can this dataset show a difference of X: the minimum detectable effect for a goal's dataset and margin, clustered when declared | to do |
| A4 | Named reducers for repeats: `mean`, `majority`, `at_least_k` | to do |
| A5 | What a failed item scores (moved here from 4.3: it is a statistics decision, the advisor's review): a failure as 0 and counted (Miller, inspect_ai), not missing, so the paired tests and `n k of m items` are not changed by it; an unreachable server still stops the pass | to do |
| A6 | Test contenders against a declared reference (the promoted baseline) instead of the data-chosen leader, which makes every arm look worse than it is (with 29 arms on 200 items nobody can be shown within 5%). Owner 2026-11-05: an opt-in, `axes.quality.reference: baseline`, for goals about replacing what runs now; the default stays the leader; the page says which | to do |

A2's before and after on the 7 committed goals (contenders, leader included · recommended), Holm across the
candidates (owner, 2026-11-05, after first choosing each arm on its own on my wrong recommendation: the tie-break
picks the cheapest arm that passed, so testing each alone recommended a too-weak arm 7%, 17%, 24%, 40% of the time
with 3, 8, 13, 20 candidates; Holm 2-3%, against 2.5%):

| goal | strategy | before | after |
| --- | --- | --- | --- |
| few_nerd | balanced | 1 · span_marker | 1 · span_marker |
| dbpedia | frugal | 20 · bert | 25 · bert |
| cnn | balanced | 2 · bart_l | 1 · bart_l |
| ag_news | balanced | 3 · none | 1 · bert_base_ta |
| scifact | frugal | 13 · e5_base | 9 · deepseek_s (e5_base: p 0.0105 alone, Holm threshold 0.0016) |
| summeval | frugal | 6 · gemma_l | 7 · gemma_l |
| triage | frugal | 52 · none | 1 · qwen3 local (65 labelled decisions: too few for a tie) |

The default at 2% left every goal with the leader alone; 10% for every strategy admitted 25 on dbpedia and left cnn
and ag_news undecided. The statistics simulations, re-run on 0.8.0's code, gave their first runs' numbers exactly.

### B. Labels

| # | what | status |
| --- | --- | --- |
| B1 | Krippendorff's alpha over more than two label sets at once, with a bootstrap interval | to do |
| B2 | Per item, how many person label sets agree with the reference (an `inspect` column) | to do |

### C. Judging

| # | what | status |
| --- | --- | --- |
| C1 | `scale: [0, 1]` documented as the start for a project's own judge | to do |
| C2 | Per judge, the correlation of its score with output length, in the judging summary | to do |
| C3 | A `note` when a rubric changes | to do |

### D. Error tagging

D1: a project declares its failure modes (like a field set); outputs are tagged in the sheet by a person or an
agent; tags are a record (who, when, which run's output), counted per arm in `inspect` and on the goal. A short
design note comes first.

### E. Datasets: the common ground every source uses

| # | what |
| --- | --- |
| E1 | A `source` block: provider, ref, revision, config, split, gated, the description's sha256; no key belongs to one host |
| E2 | Licence: optional; `evh licences` lists the common ones (SPDX ids, a line each), `--licence` checks against it; the list ships with the package |
| E3 | The dataset version, designed: proposal below |
| E4 | A `card` block: the datasheet questions as a subset of Croissant's responsible-AI keys |
| E5 | The source interface (`resolve`, `describe`, `items`, `item_url`, optional `publish`), resolved by name like the capture importers; the local folder and the URL manifest are its first two sources |
| E6 | Croissant 1.1 out: `evh dataset-card --dataset-id D [--format croissant]` |
| E7 | Croissant 1.1 in: one source that reads any Croissant file or URL (Hugging Face, Kaggle and OpenML publish it) |
| E8 | Field sets proposed from a source's features, shown for a person to accept |
| E9 | The committed datasets migrated (no shim), the profile reads `source`, a validate rule for the new blocks |

**E3, accepted by the owner (2026-11-05), and as revised after the review (accepted the same day).** The id stays the
identity. `version` is the content version MAJOR.MINOR, two integers (1.10 follows 1.9; "+0.1" on a decimal would
make 1.9 + 0.1 = 2.0, a major bump): a first dataset is 1.0; one made from another that only adds items is the
parent's MAJOR and MINOR + 1; one that removes or changes any item is MAJOR + 1, MINOR 0. A split is a new dataset
of its own (both sides 1.0, their `split.from` naming the parent and its version), since a side removes items by
design. A change to the card, the licence or the description is not a new version: the items are the same, so
the id and the version stay (no PATCH). Stored at freeze time, and `validate` recomputes it from the lineage, so
a stored value that disagrees is caught. `schema` names the record format. A source's own version is
`source.revision`, never ours. Each committed dataset is migrated to the version its lineage gives.

### F. Documentation

F1: REFERENCE "The same words elsewhere" (repeat = epochs, several answers = a `target` list, card, cluster,
`prov:` lineage). F2: INFLUENCES (Miller 2024, Plank 2022, Lakens 2017, Shankar 2024, Husain, Gebru, Pushkarna,
Croissant; why our checksum proves the selection, not the file; why one reference is scored).

### P. Provider integrations

On E5 and E7; no source is a default, none is coupled into the core.

| # | what |
| --- | --- |
| P1 | Hugging Face: pinned revisions (`resolve/<sha>`, parquet at a ref), its metadata mapped to the card, a README from the card, publishing (private first, read back by sha256); `pyarrow` decided here |
| P2 | Zenodo and OpenML |
| P3 | Kaggle: whether its API works without `kagglehub` |
| P4 | The six example `fetch.py` files become calls to their source |

### S. Scale: 1,000 to 10,000 items

| # | what |
| --- | --- |
| S1 | Measure first: synthetic projects of 1k and 10k items, 5 and 50 arms; timings of every command, the catalog, the inspector, the MCP answers |
| S2 | The tests at scale: a large-sample approximation where simulation shows it accurate at 1k and 10k, else cheaper resampling |
| S3 | Pages at scale: per-item tables paged or summarised, charts from bins, the browser budget at 10k |

Known already: the A2 catalog build made `budget-check` take 11 minutes (3 min 45 s before), the bootstrap-t's
9,999 resamples in pure Python.

## 4. The agent-ready pieces from the drafts

| # | what |
| --- | --- |
| 4.1 | Who acted on every record (a person, or an agent its operator asked; the owner's rule of 2026-11-04), then baselines per goal: versions, the evidence frozen, rollback, `evidence-check`; the reproduce block reuses `deploy-sheet` |
| 4.2 | Background runs: a job set with a detached supervisor, `jobs-status`, `jobs-logs` |
| 4.3 | Prompt versions; a standard `code_ref` in the fingerprint hook (item failures moved to A5) |
| 4.4 | Studies (spec, ask/tell, samplers, stop rules) and test-set looks (the look budget, attainable p); they need 4.1 and 4.2 |

Dropped from the drafts (superseded by what shipped): their fingerprint v5 design and migration script, `arm.system`,
prompts in the arm's hash, the "prefer MCP" rule, the study and job skills.

## 5. R. Replay and faithfulness for code adapters

Proposed by the fleet session (2026-11-05), taken into 0.8.0 by the owner the same day. A replay arm runs each item
at the code version its production record names; a faithfulness gate requires the replay to reproduce what
production recorded, or each disagreement named with its cause, before the replay is scored against gold; mutants
check that the gate fails when the code is broken. The fleet's numbers: a first naive replay agreed 86/92 and all 6
misses were bugs in its adapter or data, none in the system; with each decision on the version the host had checked
out, 133/135. Its `examples/signal-fleet-filing/replay.py` and `faithfulness.py` are the reference implementation,
handed over when its full run agrees.

| # | what |
| --- | --- |
| R1 | The code version per item: the version a recorded output came from (extends 4.3's `code_ref`); a code adapter runs each item at its version (a worktree per version, cached) |
| R2 | The faithfulness gate: the replay at the recorded versions against the recorded outputs, item by item; a run against gold refused, or labelled unfaithful, until it agrees or each disagreement is named; which code paths the corpus never exercised is reported |
| R3 | A recorded-world contract: an item carries the world it read as of decision time, and the adapter gets a stand-in that answers reads from it and records writes |
| R4 | Outcome joins by time window and order, documented as a pattern |
| R5 | Mutation checks as a command: a named mutant applied across versions, the gate expected to fail |

R3 to R5 start as example code; R1 and R2 are the core.

## Open for the owner

1. D1's shape (after its design note).
2. Where step 4 goes against P and S.
3. Keep or drop the drafts' ssh runner and phases, stages and OTLP import, the process adapter: nothing asks for
   them.

## NOT done or NOT verified

- A2 is not committed: its gate passed quality's code checks, `verify`'s tests, `budget-check` and `browser-check`,
  and failed only `site-check` (the two picks above); the spelling fix after `quality` failed is not re-run yet.
- A3, A4, B to F, P, S and step 4 are not started.
- Sizes of every package are estimates, not measured.
- The clustered bootstrap-t was simulated at 100 clusters of 3 only; other cluster sizes and shapes are not.
- D1 and E3 are not designed.
- Nothing here has been checked against the fleet's feedback still to come.
