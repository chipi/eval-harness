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
6. The fleet agent's feedback, when it finishes (entries 19-22 and later; 2026-11-05: a regression-guard arm, `expect_identical_to:`, so V5 checks a pair that must agree instead of flagging it)
   - homelab, 2026-11-05 (relayed as the operator's go; not yet confirmed in this session): a private mode for
     `catalog-serve` behind a proxy, e.g. `--behind-proxy HOST[,HOST]`: listens on `--bind 0.0.0.0` in a container,
     serves the full local inspector (items, outputs, references), accepts only the named Host headers, no rate
     limit or stripping as `--public` does. For the fleet's private catalog on the tailnet (Caddy in front, no
     published port). They switch the deployment when a release has it.
   - fleet, 2026-11-05 (feedback entry 27): code under test has no record of its own. A `kind: code` record beside
     `data/models/`: the commit, the periods it was deployed, its faithfulness result against recorded production,
     the arms that ran it; listed in the catalog like models. The record side of R1 (an item names the code
     version its output came from).
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
| A3 | Can this dataset show a difference of X: the minimum detectable effect for a goal's dataset and margin, clustered when declared | built |
| A4 | Named reducers for repeats: `mean`, `majority`, `at_least_k` | built |
| A5 | What a failed item scores (moved here from 4.3: it is a statistics decision, the advisor's review): a failure as 0 and counted (Miller, inspect_ai), not missing, so the paired tests and `n k of m items` are not changed by it; an unreachable server still stops the pass | built |
| A6 | Test contenders against a declared reference (the promoted baseline) instead of the data-chosen leader, which makes every arm look worse than it is (with 29 arms on 200 items nobody can be shown within 5%). Owner 2026-11-05: an opt-in, `axes.quality.reference: baseline`, for goals about replacing what runs now; the default stays the leader; the page says which | built |

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
| B1 | Krippendorff's alpha over more than two label sets at once, with a bootstrap interval | built |
| B2 | Per item, how many person label sets agree with the reference (an `inspect` column) | built |

### C. Judging

| # | what | status |
| --- | --- | --- |
| C1 | `scale: [0, 1]` documented as the start for a project's own judge | built |
| C2 | Per judge, the correlation of its score with output length, in the judging summary | built |
| C3 | A `note` when a rubric changes | built |

### D. Error tagging

D1: a project declares its failure modes (like a field set); outputs are tagged in the sheet by a person or an
agent; tags are a record (who, when, which run's output), counted per arm in `inspect` and on the goal. Built:
`data/failure-modes/<id>.yaml`; `inspect --sheet --fill tags --modes`, `sheet-import --tags --modes`; `evh tags`
(an MCP tool), the goal page's counts per arm, an `<arm>: failure modes` column in the sheet; V21; a release keeps
the modes of a hidden dataset's tags, never their notes. The design is in `_tags.py`'s docstring and the RUNBOOK
(no separate note was written).

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

Built 2026-11-05, a commit each: E3 `f2512999b`, E2 `37803dd4e`, E1+E9 `a59cf283c`, E4 `eebe2596a`, E5
`f083eff09`, E6 `de7c80ec9`, E7 `2f92dffae` + `bc77a8613` (pyarrow, owner yes), E8 `d502f3aec`. Not covered: E6's
export is not run through mlcroissant; E7 does not read a FileSet, so Hugging Face's own descriptions wait for P;
E7 does not read E6's own export back (E6 writes jsonPath sources, E7 reads columns).

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

Built 2026-11-05: P1 `802e65124` (read, pinned) + `c8c24e97b` (README) + `0af013f08` (publish; huggingface_hub a
dependency, owner yes; checked live, the repo deleted), P2 `f143411d9`, P3 `324e4efe2` (Kaggle needs no kagglehub for a
public dataset), P4 `42448857f`. Not covered: Zenodo's item read is checked offline only (its describe live); gated
and private datasets on Kaggle and the Hub are not tried (no Kaggle credentials here); publishing is to the Hub only.

### S. Scale: 1,000 to 10,000 items

| # | what |
| --- | --- |
| S1 | Measure first: synthetic projects of 1k and 10k items, 5 and 50 arms; timings of every command, the catalog, the inspector, the MCP answers |
| S2 | The tests at scale: a large-sample approximation where simulation shows it accurate at 1k and 10k, else cheaper resampling |
| S3 | Pages at scale: per-item tables paged or summarised, charts from bins, the browser budget at 10k |

Known already: the A2 catalog build made `budget-check` take 11 minutes (3 min 45 s before), the bootstrap-t's
9,999 resamples in pure Python.

**S1 measured (2026-11-05).** Synthetic projects (the bundled echo adapter, 5 sentence counts × 10 noise levels = 50
arms that call nothing, a gold reference, one goal); seconds, on the workstation:

| step | 1,000 items | 10,000 items |
| --- | --- | --- |
| `run`, one arm (median) | 5.8 | 55.8 |
| `run`, 50 arms | 292 | 2,811 |
| `dataset-create`, `materialize`, `label-import`, `reference-promote` | 0.1 each | 0.2 to 1.1 |
| `catalog` (50 arms) | 144 | 1,532 |
| `goals`, `goals --goal`, `goals --goal --json` (the MCP tool), each | 142 to 144 | 1,499 to 1,516 |
| `/api/compare`, 5 arms / 40 (its cap) | 2.4 / 17.6 | 23.8 / 169.6 |
| `inspect --sheet --csv`, 5 arms / 50 | 13.0 / 143.2 | 175.3 / 1,566.8 |
| `pair-test` | 0.8 | 7.2 |
| `family-test` (49 against 1) | 35.5 | 332.5 |
| `validate` | 0.8 | 1.5 |

Where the time goes (cProfile, the 5-arm sheet at 1,000 items): 40.6 of 46.0 s in `stats.bootstrap_t_p`'s 9,999
resamples, drawn item by item in pure Python (40 million `randrange` calls), recomputed by every new process (`goals`
right after `catalog` took as long again). `family-test` is the sign-flip permutations, the same shape. Second: the
sheet loads and parses the whole dataset record once per item (`_common.item_path`, 1,002 loads at 1,000 items:
quadratic). Third: a run's own cost, 5.6 ms an item with an adapter that does nothing, not yet profiled. Files: a run
is one file per item (RFC-024), and the 10,000-item project filled `/tmp`'s inodes on the first attempt.

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
out, 133/135. Its `examples/signal-fleet-filing/replay.py` and `faithfulness.py` are the reference implementation.
Handed over 2026-11-05 after its full run agreed (324/324 over 10-02..11-05, 6 mutants killed, 1 survivor explained by
coverage): /work/eval-harness-v072, branch fleet/signal-fleet-filing, commit 9a318e61 (local), the two files and a
README of what they assume; the owner mapping and host time zone are settings (REPLAY_SCRUBBED_OWNER, REPLAY_REAL_OWNER,
REPLAY_HOST_TZ). Its fixes (reads as of the cycle, keys from the code that ran, the scrubber's host renaming, a create
scored by its repo) are test cases R2 must catch by itself.

| # | what |
| --- | --- |
| R1 | The code version per item: the version a recorded output came from (extends 4.3's `code_ref`); a code adapter runs each item at its version (a worktree per version, cached) |
| R2 | The faithfulness gate: the replay at the recorded versions against the recorded outputs, item by item; a run against gold refused, or labelled unfaithful, until it agrees or each disagreement is named; which code paths the corpus never exercised is reported |
| R3 | A recorded-world contract: an item carries the world it read as of decision time, and the adapter gets a stand-in that answers reads from it and records writes |
| R4 | Outcome joins by time window and order, documented as a pattern |
| R5 | Mutation checks as a command: a named mutant applied across versions, the gate expected to fail |

R3 to R5 start as example code; R1 and R2 are the core.

## Open for the owner

1. (none for A-D: A5 (a) and D1 approved by the owner, 2026-11-05)
2. Where step 4 goes against P and S.
3. Keep or drop the drafts' ssh runner and phases, stages and OTLP import, the process adapter: nothing asks for
   them.

## NOT done or NOT verified

- Pushed: up to `01dea13f2` (A2). Committed, not pushed: A3/A4/A6, B and C, A5, D1. A push needs the owner's yes.
- E, F, P, S, step 4, R, the fleet's feedback (6) and the release (7) are not built.
- Sizes of every package are estimates, not measured.
- The clustered bootstrap-t was simulated at 100 clusters of 3 only; other cluster sizes and shapes are not.
- D1: modes are tagged by hand in a sheet; no agent was asked to tag, and no committed dataset has tags.
- `dataset-extend` (picks) is not run through E3's version rule end to end; its lineage is the same `derived_from`.
- Nothing here has been checked against the fleet's feedback still to come.
