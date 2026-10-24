# ADR-0004 — Experiment rounds, and a catalog that guides them (0.4.0)

**Status:** Proposed (2026-10-24). The owner decided the shape: rounds are optional, the catalog
stays read-only, and decisions are commands run locally. The specifics below (files, commands,
pages) are proposed for the owner's review. Dataset lineage and the conditions check (G) are
decided and built.
**Date:** 2026-10-24

## Context

The newcomer trial (`harness/docs/SCENARIO.md`) ran two experiments in one round each: five arms,
results on gold, on a frontier model's silver and by two judges, a baseline promoted. The natural
next step was a second round: drop the three CPU arms, tune the cheap hosted model's prompt
against the frontier's silver, and compare. Experiments go like that, round on round: each one
changes a few things, retires what lost, and keeps what won, until a combination meets the goal.

The harness records none of it. Runs are a flat set per dataset; config versions (`_v1`, `_v2`)
and `--match` scope a table; a baseline is one run per dataset, replaced on promotion. Nothing says
which arms belonged to which round, why an arm was dropped, what a round set out to learn, or what
it concluded. The catalog shows every arm at once, and compares each arm with a reference or a
baseline, never one round with another. The owner: the catalog "is not helping us, but it could:
a little experiment workflow that guides us, where we make decisions and see how things are
going", with comparisons "between the experiments, not only versus the reference: the first run
versus the second versus the third versus the baseline versus silver".

## Decision

**A. Rounds are optional.** A config that names no round behaves exactly as today: runs, tables
and pages are unchanged. A round adds a record and the workflow on top; nothing requires one.

**B. A round is a file**, `data/rounds/<goal_id>/<round_id>.yaml`, validated by
`schemas/round.schema.json`. A round answers one goal on one dataset.

| field | what it holds |
| --- | --- |
| `round_id`, `goal`, `dataset_id` | `r1`, `r2`, ...; the goal it answers; the dataset its arms run on |
| `from` | the round it continues, if any |
| `hypothesis` | what this round sets out to learn, in a sentence |
| `changes` | what changed against `from`, and why (free text, one line each) |
| `baseline` | the run (or promoted baseline) it starts from and is measured against |
| `arms` | the config ids in it; a config names its round (`round: r2`), and every run records it |
| `retired` | config ids dropped, each with a reason and a date |
| `budget_usd` | optional: what the round may spend |
| `status`, `conclusion` | `open` or `closed`; when closed, the conclusion and the run promoted |

`validate` checks them (the goal and dataset resolve; every run naming a round is in it; a closed
round has a conclusion). `experiment-run` refuses a config naming a closed round.

**C. Decisions are commands, run locally.** The catalog and the inspector never write (ADR-0002);
they show each suggested decision as the command that makes it, with a copy button.

```bash
evh round-open  --goal brief_summary --dataset briefs_v1 --from r1 \
                --hypothesis "a one-sentence prompt closes the gap to the frontier" \
                --retire briefs_t5_small_v1,briefs_flan_t5_small_v1,briefs_lead1_v1 \
                --reason "separated worse than the leader on gold after Holm (r1)"
evh round-retire --round r2 --arm briefs_llama_v1 --reason "…"
evh rounds --goal brief_summary            # status in the terminal: arms, spend, verdicts, suggestions
evh round-close --round r2 --conclusion "…" --promote <run_id>   # closes, and promotes with it as the reason
```

`leaderboard`, `family-test`, `pair-test` and the inspector take `--round` (`round=` in the
inspector) to scope to one round's arms.

**D. Comparisons across rounds.** Arms of different rounds on the same dataset and reference
measured the same items, so the paired test already applies; what is missing is the view. The
inspector gets a round picker, and a goal's round page compares:
- each round's arms against the baseline the round started from;
- **round against round**: each round's best arm against the previous round's best, and against
  the promoted baseline and the arm that wrote the silver reference;
- a progress line: the best score per round, its cost per item, and whether it is separated from
  the previous round's best.

Gold, silver and judged scores stay separate views, as now. Rounds on different dataset versions
are linked through the lineage (G) and never tested against each other.

**E. Guidance, computed from the evidence and offered as suggestions**, on the goal page and in
`evh rounds`, each with the command that acts on it:
- retire: arms separated as worse than the round's leader after Holm;
- more items: arms the leader is not separated from, with how many items `rank-stability` says the
  order needs;
- stop or change course: no arm in this round is separated from the previous round's best;
- spend: the round's billed cost against its `budget_usd`;
- conditions: arms measured under different conditions (G) before their numbers are compared.

**F. The goal page leads with the answer.** Without rounds: the promoted baseline and its reason
first, then each dataset with its references, then the arms grouped by what they are scored
against (the leader chosen within a group, never the arm that wrote the reference). With rounds:
the latest conclusion, the open round's status and suggestions, then the rounds, newest first,
each with what changed, its arms (retired ones greyed with their reason), its verdicts and its
conclusion. Long tables show 10 rows with "show 10 more" and "show all", and the filter searches
every row.

**G. Decided and built on 2026-10-24 (commit 8025a41a):** dataset lineage
(`dataset-create --from`, `derived_from`, V2, version links on the catalog's dataset pages), and
the inspector's conditions check (from each run's fingerprint: machine, library versions,
harness, scorer, items, reference bytes; with warnings when the scorer or the reference bytes
differ, or latency is compared across machines).

## Consequences

- A project that never opens a round sees no change but paging and the goal page's order.
- One more file kind (rounds), one more schema, four commands, one more validate rule; the run
  record gains `round`. The catalog stays read-only, so its public deployment is unaffected.
- The newcomer scenario gains a second round per experiment, which is also this design's test.
- Not in it: rounds across goals, automatic retirement, a server that writes.

## Alternatives considered

- **The local inspector writes decisions** (a retire button). Smoother, but it ends "the server
  never writes", which the public deployment depends on. Set aside; it can come later, local only.
- **Rounds required.** Simpler model, but it taxes a quick experiment. The owner chose optional.
- **Rounds as a naming convention** (`_r2` in config ids) or git tags. No place for a hypothesis,
  a retirement reason or a conclusion, and nothing to validate.
- **Rounds per dataset rather than per goal.** A round's conclusion answers a goal's decision; the
  dataset is a field of the round.
