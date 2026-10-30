# Data inventory for 0.6.0: what we test the capture lane on

Status: 2026-10-30. Every piece of data the 0.6.0 build and its use cases need. For each one: what it is, where it
lives now, how big it is, whether it can be public, what produces it, which phase and test use it, and whether we
have it or must make it. Phases are the engineering plan's
([PLAN_0.6.0.md](PLAN_0.6.0.md)); the use cases are the application plan's
([PLAN_0.6.0_FLEET.md](PLAN_0.6.0_FLEET.md)).

## 1. Test fixtures for the lane itself (small, committed, offline in CI)

| # | data | what it tests | produced by | size | public | status |
|---|---|---|---|---|---|---|
| F1 | a jsonl file of records | P1 `jsonl` mapping, `where` (an empty cell too), window, dropped rows; P2 capture end to end; P3 selection | written by the test | about 20 lines | yes, synthetic | to make |
| F2 | a tsv file with a header | P1 `tsv`, the same cases | written by the test | about 20 rows | yes, synthetic | to make |
| F3 | recorded GitHub GraphQL answers: issues with a duplicate, a reopen and its comment, a page break | P1 `github` through a stand-in `gh` (`EVH_GH`) | recorded once from chipi/orrery (public issues), trimmed | 2–3 JSON pages | yes | to record |
| F4 | recorded Langfuse API answers: a page of traces and one trace with observations | P1 `langfuse` through a local HTTP stand-in | shaped after a real fleet trace, contents synthetic | 2 JSON files | yes, synthetic | to make |
| F5 | records with outcome fields covering every rule key | P4 mapping (`when`, `unless`, `exists`, `absent`, signed `range`, `min_age_days`, skip, unmatched) | written by the test | about 15 records | yes, synthetic | to make |
| F6 | a fixture catalog: one dataset, `gold/<D>`, a run scored on it, `silver/<name>` and its rescore | P4's proof: exactly one recommendation on the goal page | built by the test from the tutorial kit (`harness/tutorial/`) | tutorial-sized | yes | to make |
| F7 | a hidden dataset with planted markers in sources, outputs, reference texts, judge reasons, field values, URLs | P6 marker test across every surface | built by the test | a few items | yes, synthetic | to make |
| F8 | a record id with `:` | P3 ids through materialize, a run, the inspector and MCP (r2-m4) | written by the test | 1 item | yes | to make |

Rule for all of them: no network in CI, everything generated or recorded into the test, nothing read from the
mini.

## 2. The triage fleet's data (the use cases)

| # | data | what it is | where it lives now | size | public | produced by | status |
|---|---|---|---|---|---|---|---|
| D1 | the decisions | 236 Orrery triage decisions, each signal + probe table as of its time + fleet decision + outcome + provenance | session scratchpad (`orrery-triage-items.jsonl`, sha256 `cacaf75f…`); built on the mini | 1.39 MB | yes, after the fleet's `scrub.py` (gitleaks: no leaks) | homelab's `build_orrery_items.py` | have v1; **to rebuild** with close comments and the escalation join (D3) |
| D2 | the issue verdicts | the close comment of all 42 Orrery issues: fixed / noise / duplicate / open | review 3's `closers.json` (from `gh api graphql`) | 42 issues | yes (public repo) | GitHub | have; to fold into D1 by the build script |
| D3 | the build script | reads the ledgers, GlitchTip, Langfuse, VictoriaLogs/Metrics/Traces, GitHub; anchors probes at decision time; scrubs | the mini only (`~/evh-datasets/…/build_orrery_items.py`), not in any repo | one script | yes | homelab | **to commit and pin** in the fleet's repo (prerequisite) |
| D4 | the owner's verdicts | the 42 issue verdicts confirmed (fixed / noise / unknown) and the 33 exact items labelled | — | 42 + 33 | yes | the owner, from a sheet (P8 `label_sheet.py`) | **to make**: about an hour of the owner's time |
| D5 | the fixture labels | 9 hand labels from the fleet's frozen fixtures, carried by fingerprint | in D1 (`ground_truth`) | 9 | yes | the fleet's EVAL.md work | have |
| D6 | the fleet's frozen fixtures | 23 triage items (12 Orrery) with full probe tables and hand labels, July | agentic-ai-homelab `signal-fleet/reference/` (committed) | 284 KB | yes (public repo) | the fleet's `freeze.py` | have; cross-check only |
| D7 | the de-duplication corpus | 100 scrubbed GlitchTip signals | agentic-ai-homelab `signal-fleet/reference-dedup/corpus.json` (committed) | 60 KB | yes (public repo) | the fleet | have |
| D8 | per-decision captures | every new decision, as the model saw it (signal, every probe answer, the text the model read, the decision) | the mini, `~/signal-fleet/results/probes/`, mode 600 | about 12 KB a decision; about 33 Orrery decisions a fortnight | after `scrub.py` | the fleet, live since 2026-10-29 22:13 UTC | accumulating; the first monthly version from about the end of November |
| D9 | the ledgers | `dispositions.tsv` (13,361 rows, every repo), `filed.tsv` | the mini, `~/signal-fleet/results/` | — | no (production identifiers); a scrubbed slice yes | the fleet | have; a scrubbed slice of a few rows is the `tsv` importer's real-data check |
| D10 | Langfuse traces | the fleet's triage traces; the full conversation since 2026-10-15 09:52 | the mini's Langfuse, 30-day retention | 140+ traces | no as such; used through D1 | the gateway | rolls off after 30 days; D8 replaces it |

## 3. Datasets the use cases make from it

| dataset | from | items | role |
|---|---|---|---|
| `orrery_triage_v1` | D1 rebuilt, test signals out | about 233 | the decisions; arms run on it |
| `gold/orrery_triage_v1` | D4 | about 138 labelled, one per fingerprint | the reference the goal decides on |
| `silver/orrery_triage_v1_outcomes` | D1's outcome fields, the v3 mapping | 169 labelled | shown beside it |
| `silver/orrery_triage_v1_hand` | D5 | 9 | shown beside it |
| `orrery_triage_smoke` | D1, 2 items | 2 | the smoke step before any billed run |
| `fleet_dedup_v1` | D7 | 100 | the dedup regression guard |
| `orrery_triage_v2` and on | D8, monthly | about 60 a month, all exact | production's own question |

## 3a. Where the triage data lives: Hugging Face (owner, 2026-10-30)

The raw items are kept the way every experiment here keeps them: **not in git, fetched and hash-checked**.

- **What this repository commits:** `data/sources/<dataset>/` stays gitignored (`harness/.gitignore:108`). What
  is committed is the dataset files (item ids and sha256s), the references, the runs and a `fetch.py`.
- **Hugging Face is the dataset's own git.** A public dataset repository holds the items, one tagged revision
  per version, with a dataset card. `fetch.py` downloads a pinned revision and checks every item against the
  committed hashes, as `examples/_shared/hf_rows.py` does for the six existing experiments.

**The repositories and their versions:**

| HF dataset | type | v1 | later versions |
|---|---|---|---|
| `orrery-triage-decisions` | **agent decisions captured from production, replayable**: per item the signal the triage agent received, the answers to every probe it could ask (as of the decision's time; exact, rebuilt or unavailable, marked per probe), and the decision production made. An evaluation set for a classifier-like agent step (dismiss, file, escalate, cleanup), not a training set | revision `v1`: the 236 Orrery decisions 2026-07-25 → 2026-10-29 (test signals removed), all evidence levels, scrubbed by the fleet's `scrub.py` | `v2`, `v3`, …: monthly, from the fleet's per-decision capture, all exact |
| `orrery-triage-verdicts` (or a config of the same repository) | **a reference**: per item the label the evaluation is decided on, from the owner's verdicts on the issues and his labels on exact items; plus the outcome mapping's labels, marked as outcomes | revision `v1`, beside the decisions' `v1` | with each version |
| `signal-fleet-dedup` | **signals for a deterministic stage**: scrubbed error signals, to replay through the fleet's de-duplication functions; no model | revision `v1`: the 100 signals of the fleet's `reference-dedup/corpus.json` | when the corpus grows |

Each dataset card says:
- what an item is, and its type (above);
- how it was built: the fleet's build script at its commit, the scrubber;
- the evidence levels and what "rebuilt" means;
- what it is not: a training set, or a benchmark of models in general;
- the licence;
- how this repository uses it.

The licence is the owner's choice when the repository is created. Which Hugging Face account owns it is too:
the connector is logged in as `chipi-nbgd`.

## 4. What has to happen before each use

- **The walking skeleton** (the engineering plan's first pass, $0): F1, F5, F6, and D1 as it is, with a stand-in
  model. Nothing else is needed.
- **The breadth:** F2–F4, F7, F8, and D7 for P9.
- **The billed runs:** D3 committed; D1 rebuilt; D4 made; aliases and keys in the gateway (the application plan,
  §5).
- **Monthly:** D8 exported and scrubbed through the fleet's script, then captured with `--since-capture`.
