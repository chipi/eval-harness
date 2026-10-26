# PRD-013: Baselines per goal, the host beside the hash, non-inferiority, one grammar

- **Status**: Draft (0.5.0), round 3
- **Authors**: Marko Dragoljevic
- **Related RFCs**: [RFC-001](../rfc/RFC-001-fingerprint-and-code-identity.md) (the fingerprint, to
  gain version 5), [RFC-004](../rfc/RFC-004-experiment-rounds.md) (rounds and baselines); RFC-014
  (these changes and `evh migrate`), to be written
- **Related ADRs**: [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md) (goal ties, superseded in
  part by this PRD)
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md),
  [PRD-005](PRD-005-goals-and-rounds.md), [PRD-009](PRD-009-prompts-and-optimisation.md),
  [PRD-010](PRD-010-runners.md), [PRD-011](PRD-011-evidence-registry.md),
  [PRD-012](PRD-012-agent-ready.md)

## Summary

The 0.5.0 reviews found things in 0.4.0 that the new work would build on and get wrong. A baseline
belongs to a **dataset**, so two goals on one dataset share one; it should belong to a goal on a
dataset. The **host** label is inside the fingerprint's hash, so the same arm on a GPU host and on a
laptop reads as an uncontrolled comparison; the label should sit beside the hash, while what can
change results (Python version, CPU architecture, the accelerator stack) stays in it. A goal calls an
arm **tied** with the leader when the test cannot separate them and their means are within a margin
computed from the data being judged; that treats "no evidence of a difference" as "no difference".
Tie-breaks become **non-inferiority** against a margin the goal **declares** in advance (one-sided,
2.5%, the 95% interval the harness already computes), and an arm that cannot be shown non-inferior is
**inconclusive**. Two runs started in the same second share a **run directory**. Identifiers for
prompts, baselines and champions need **one grammar**. And the committed data needs **`evh migrate`**,
for this repository and for every project on the harness. 0.5.0 fixes all of it and states beside every
verdict how large the difference is and how precisely it is known.

## Background & Context

- `run-promote` names a baseline `<dataset_id>_baseline` (`promote_baseline.py:141`), and the name is
  read in `rounds.py`, `rescore.py`, `validate_tree.py`, `catalog_build.py`, `catalog_views.py` and
  `cli.py`. Champions, studies and the evidence registry need one per goal.
- `_host_identity` (`_fingerprint.py:258-273`) records the host label, the platform and architecture,
  the kernel release, the processor, the CPU count and the Python version, all inside the hash
  (`_fingerprint.py:370`); `run-compare` reports any difference outside
  `arm` as a confound. The accelerator stack (CUDA, torch) that changes a local model's numbers is not
  recorded.
- ADR-0006: an arm ties the quality leader when it is "not separated, and within the margin"; the
  default margin is 2% of the leader's observed mean; `frugal` admits anything the paired test cannot
  separate. With 200 items and a ROUGE-L margin near 0.006, a 95% interval that narrow needs roughly
  270 items or more, so an honest rule makes ties rare on today's goals: the change must be decided,
  not discovered.
- `stats.exact_ci` is the 95% interval of the paired mean difference obtained by inverting the
  sign-flip test up to 30 items, a t-based interval above (`stats.py:193-210`), and none at 5 items or
  fewer. The inspector shows it ("95% CI of Δ"); `pair-test` and `family-test` print p and Holm's
  threshold without it.
- A run id is the config id plus a UTC timestamp to the second (`experiment_run.py:586`), its directory
  created with `exist_ok=True`.
- Goal dataset roles are free text; this repository uses `dev` and `heldout`
  ([PRD-009](PRD-009-prompts-and-optimisation.md) uses `validation` and `test`).
- No migration command exists; 0.4.0's data changes were one-off scripts. The podcast project carries
  242 imported runs on the 0.4.0 format.

## Goals

- A baseline answers one goal on one dataset; promotion, rounds, studies and champions agree on it.
- The same arm on two hosts compares as controlled on quality when only the host label differs; a
  difference that can change results still shows.
- A tie-break is a claim the data supports, against a margin chosen before the data.
- No two runs can share a directory, and a job's run id is known before it starts.
- One grammar names every versioned thing.
- Every verdict says how large the difference is and how precisely it is known; a test that cannot
  separate anything says so before it runs.
- Every project migrates with one command, a dry run and a way back.

## Non-Goals

- No change to the test that separates arms (the paired sign-flip test with Holm stays).
- No automatic choice of a margin: a goal without one gets no tie-breaks.

## Personas

- **The team lead** with two goals on one dataset (a quality goal and a cost goal).
- **The engineer** running the same arm on a GPU host and a laptop.
- **Anyone reading a verdict.**
- **A project on the harness** upgrading to 0.5.0.

## User Stories

- _As a team lead, I promote one baseline for "summary quality" and another for "cheap summaries" on
  the same dataset, and each goal's page shows its own._
- _As an engineer, I compare an arm run on the GPU host with the same arm on my laptop; quality compares
  as controlled, and the page says the host label differs and flags the speed comparison._
- _As a reader, a goal page recommends a cheaper arm only when it is shown non-inferior to the leader by
  the goal's declared margin; otherwise it says "inconclusive" and why (too few items, interval too
  wide)._
- _As a project, I run `evh migrate --dry-run`, read what will change and what it refuses, run it, and
  my pages show the same baselines as before._

## Functional Requirements

- **FR1: Baselines per goal and dataset.** A baseline is the current champion of a goal on a dataset
  ([PRD-011](PRD-011-evidence-registry.md)); `run-promote`, `round-close --promote` and every command
  or page that reads a baseline use it. A run with no goal promotes
  to the dataset's goal-less baseline.
- **FR2: The host beside the hash.** Fingerprint version 5 records the host label, the kernel release,
  the processor string and the CPU count beside the hash; the platform and architecture, the Python
  version and, when the system uses one, the accelerator stack (declared by the adapter: CUDA and
  driver, torch) stay inside it. `run-compare` reports a
  host-label difference as such, not as a confound on quality, and flags speed and cost comparisons
  across hosts.
- **FR3: Non-inferiority, declared.**
  - **FR3.1**: A goal declares its margin per measure (the smallest difference that matters, in the
    measure's units), before its runs are judged. A goal without one gets no tie-breaks: its
    recommendation is the quality leader, and `validate` notes the missing margin.
  - **FR3.2**: An arm is **non-inferior** to the leader when the lower bound of the 95% interval of the
    paired difference (arm − leader, quality direction) is above −margin (one-sided, 2.5%). It is
    **inconclusive** when the interval is too wide to tell, or when no interval exists (5 items or
    fewer). Two-sided **equivalence** (the interval inside ±margin) is used only when a claim of
    "no difference" is made.
  - **FR3.3**: Strategies: `balanced` and `frugal` recommend, among arms non-inferior to the leader,
    the best on the tie-break (default cost, then speed), `frugal` with the goal's wider declared margin
    for cost if it has one; `quality_first` recommends the leader only. An inconclusive arm is never
    recommended on a tie-break.
  - **FR3.4**: Verdict precedence: an arm separated as better or worse is reported as that, even when its
    interval also lies inside the margin ("different, but within the margin" is shown as a note).
  - **FR3.5**: ADR-0006 is superseded in part by an ADR that records this. The recommendations that
    change on this repository's goals are listed in the release notes, each with its reason.
- **FR4: Unique run ids.** A run id adds milliseconds and a short random suffix; a job records its run id
  before it starts, so a resumed job finds its run; creating a run refuses an existing directory.
- **FR5: Intervals beside verdicts.** Every verdict (`pair-test`, `family-test`, the inspector, goal
  pages, rounds, studies) shows the effect as the mean paired difference in the measure's units, with
  its 95% interval, beside p and the threshold. Intervals are labelled unadjusted (Holm applies to the
  separation, not to them). Above 30 items the interval is computed to agree with the test it sits
  beside (RFC-014 decides how: a permutation interval, or the test's own estimate).
- **FR6: Power before spending.** The smallest p a set of items can reach is computed from the items
  whose paired difference is not zero, shown as "at best" when no run exists yet. The minimum
  detectable effect (at the declared level and 80% power) is computed from data: earlier runs' paired
  differences on the dataset, or a pilot; `rank-stability` reports it, and a dry run reports it when
  such data exists.
- **FR7: One grammar.** Every versioned thing is named `<kind>:<path>/<n>` (a fixed version) or
  `<kind>:<path>@<alias>` (a moving pointer): `prompt:summary/system/3`, `prompt:summary/system@production`,
  `champion:news_summary/cnn_200/3`, `champion:news_summary/cnn_200@current`. A goal and a dataset are
  always both named, so nothing is ambiguous when a goal has several datasets. Prompt aliases are set by
  a command and named by the project; a champion records the prompt versions it used, and promotion
  never moves a prompt alias.
- **FR8: `evh migrate`.** One command migrates a project's committed data to the 0.5.0 format: baselines
  to goal and dataset, fingerprints to version 5, goal dataset roles `dev` → `validation` and `heldout`
  → `test`, the test-look counts seeded from past promotions, run ids unchanged. `--dry-run` lists every
  change and every case it refuses with the command that resolves it (a custom baseline id, a goal-less
  run on a goal's dataset, two goals sharing one baseline); it writes only after the dry run is clean,
  records the harness version and a pre-migration tag to return to, and `evh validate` passes after it.
  This repository and the podcast project are migrated with it.

## Success Criteria

- `evh migrate` runs cleanly on this repository and on the podcast project's data; goal pages show the
  same baselines as before where one goal used a dataset; `validate` passes.
- A test shows two goals on one dataset with different baselines; a run pair differing only in host label
  compares as controlled on quality; a pair differing in Python version does not.
- A planted cheaper arm equal in quality is non-inferior at 200 items and inconclusive at 10; a planted
  worse arm is never recommended.

## Related Documents

- RFC-014 (to be written); [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md).
  References ([INFLUENCES](../INFLUENCES.md)): Schuirmann 1987 and Lakens 2017 (equivalence and
  non-inferiority), Miller 2024 (error bars), Card et al. 2020 (power).
