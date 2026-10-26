# PRD-013: Baselines per goal, the host beside the hash, ties as equivalence

- **Status**: Draft (0.5.0), round 2
- **Authors**: Marko Dragoljevic
- **Related RFCs**: [RFC-001](../rfc/RFC-001-fingerprint-and-code-identity.md) (the fingerprint, to
  gain version 5), [RFC-004](../rfc/RFC-004-experiment-rounds.md) (rounds and baselines); RFC-014
  (these changes and their migrations), to be written
- **Related ADRs**: [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md) (goal ties, which this
  PRD changes)
- **Related PRDs**: [PRD-001](PRD-001-experiments-and-comparison.md),
  [PRD-005](PRD-005-goals-and-rounds.md), [PRD-009](PRD-009-prompts-and-optimisation.md),
  [PRD-010](PRD-010-runners.md), [PRD-011](PRD-011-evidence-registry.md)

## Summary

The 0.5.0 reviews found four things in 0.4.0 that the new work would build on and get wrong. A
baseline belongs to a **dataset**, so two goals on one dataset share one baseline; it should belong
to a goal on a dataset. The **host** a run used is inside the fingerprint's hash, so a run on a GPU
host and the same arm on a laptop read as an uncontrolled comparison; the host should be recorded
beside the hash. A goal calls two arms **tied** when the test does not separate them and their
means are within a margin, which treats "no evidence of a difference" as "no difference"; a tie
should mean the paired difference's confidence interval lies inside the margin, the standard
equivalence test. And two runs of one config started in the same second share a **run directory**
without a word. 0.5.0 fixes all four, migrates the committed data, and says beside every verdict
how big the difference is and how sure.

## Background & Context

- `run-promote` names a baseline `<dataset_id>_baseline` (`promote_baseline.py:141`) and carries
  the goal from the run; rounds read the dataset's baseline. Champions, loops and the evidence
  registry ([PRD-009](PRD-009-prompts-and-optimisation.md), [PRD-011](PRD-011-evidence-registry.md))
  all need one per goal.
- The fingerprint's hash covers `host` (`_fingerprint.py:370`), and `run-compare` reports any
  difference outside `arm` as a confound. Runners ([PRD-010](PRD-010-runners.md)) make cross-host
  comparisons ordinary. Speed does depend on the host, quality does not (for a deterministic
  system), so the host belongs beside the hash, still shown, still flagging speed comparisons.
- ADR-0006: an arm ties the quality leader when it is "not separated, and within the margin".
  With few items nearly everything is not separated, so cheaper arms tie easily, and in a loop a
  chain of such ties can drift below the start (PRD-009 FR2.3). The literature's answer is an
  equivalence or non-inferiority test with a margin declared in advance (Schuirmann 1987, TOST;
  Lakens 2017).
- A run id is the config id plus a UTC timestamp to the second (`experiment_run.py:586`), and its
  directory is created with `exist_ok=True`.
- The inspector shows each verdict's interval (`stats.compare` → `exact_ci`, the "95% CI of Δ"
  column); `pair-test` and `family-test` print p and Holm's threshold without it.
  Miller (2024, *Adding Error Bars to Evals*) recommends intervals beside every comparison and
  power analysis before it.

## Goals

- A baseline answers one goal on one dataset; promotion, rounds, loops and champions agree on it.
- Two runs of the same arm on different hosts compare as controlled on quality, and the record
  still says which host made each and flags speed comparisons across hosts.
- "Tied" is a claim the data supports: the interval of the paired difference inside the margin.
- No two runs can share a directory.
- Every verdict says how large the difference is and how precisely it is known, and a test that
  cannot separate anything says so before it runs.
- All committed data is migrated; nothing keeps reading the old shape.

## Non-Goals

- No change to which test separates arms (the paired sign-flip test with Holm stays).
- No new margin defaults beyond what goals already declare (ADR-0006's are kept, now applied to the
  interval).

## Personas

- **The team lead** with two goals on one dataset (a quality goal and a cost goal).
- **The engineer** running the same arm on a GPU host and a laptop.
- **Anyone reading a verdict.**

## User Stories

- _As a team lead, I promote one baseline for "summary quality" and another for "cheap summaries"
  on the same dataset, and each goal's page shows its own._
- _As an engineer, I compare an arm run on the GPU host with the same arm on my laptop and the
  quality comparison is controlled; the speed axis says the hosts differ._
- _As a reader, a goal page calls an arm tied only when its interval sits inside the margin; an arm
  with too few items to tell is "not determined", not "tied"._

## Functional Requirements

- **FR1**: A baseline is per goal and dataset (`<goal_id>/<dataset_id>`); `run-promote`,
  `round-close --promote`, rounds, `leaderboard` and the catalog use it. A run with no goal
  promotes to the dataset's goal-less baseline, as before. The committed baselines are migrated to
  the new layout by a migration that refuses ambiguous cases with the command that resolves them.
- **FR2**: Fingerprint version 5 records `host` beside the hash; `run-compare` reports a host
  difference as such (not as a confound on quality); speed and cost comparisons across hosts are
  flagged. The committed runs are migrated to version 5.
- **FR3**: A goal's tie is: the confidence interval of the paired difference on the goal's measure
  lies within the margin. An arm whose interval is too wide to tell is "not determined" and is
  never recommended over the leader on a tie-break. Goal pages, `evh goals` and loops use this
  rule. ADR-0006 is superseded by an ADR that records the change.
- **FR4**: A run id includes enough to be unique (a timestamp to the millisecond and a short random
  suffix), and creating a run refuses an existing directory.
- **FR5**: Every verdict (`pair-test`, `family-test`, the inspector, goal pages, rounds, loops) shows
  the effect size and its 95% interval beside p and the threshold.
- **FR6**: `rank-stability` and `--dry-run` state the smallest detectable effect for the items
  given (the minimum detectable effect at the declared α), and the smallest p the item count can
  reach.

## Success Criteria

- The example project and this repository's data migrate and validate; goal pages show the same
  baselines as before where one goal used a dataset.
- A test shows two goals on one dataset with different baselines; a run pair differing only in host
  compares as controlled on quality; a planted near-equal pair with 5 items is "not determined",
  with 200 items "tied".
- The recommendations that change on this repository's goals under the new tie rule are listed in
  the release notes, each with its reason.

## Related Documents

- RFC-014 (to be written); [ADR-0006](../adr/ADR-0006-goal-axes-and-strategies.md).
  References: Schuirmann 1987 and Lakens 2017 (equivalence testing), Miller 2024 (error bars for
  evals), Card et al. 2020 (power).
