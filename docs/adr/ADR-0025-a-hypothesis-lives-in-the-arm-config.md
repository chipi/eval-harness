# ADR-0025 — A hypothesis is written in the arm's config, and committed before the run (0.7.0)

**Status:** Accepted (owner, 2026-11-04); built in 0.7.0.
**Date:** 2026-11-04
**Detail:** [RUNBOOK §4](../../harness/docs/RUNBOOK.md#4-point-the-harness-at-your-system) (the config block),
[CONCEPTS](../../harness/docs/CONCEPTS.md#a-comparison-is-named-before-the-results-are-read) (why)

## Context

`evh pair-test` is uncorrected, and says so: "valid only if this pair was named before the table was read".
Nothing recorded the naming, so a pair picked after reading the leaderboard and a pair planned a week earlier
printed the same line. A beta agent measuring one change against a baseline asked for the prediction to be on
the record.

## Decision

- **Where it lives: the arm's config**, beside the change it predicts (`hypothesis: {against, measure, direction,
  statement, items?}`). The alternatives (a round's file, a separate pre-registration file) put the prediction
  away from the change, and a config that has runs is never edited, so the block cannot drift from its run.
- **What a run records:** the block (`hypothesis`) and `hypothesis_in_advance`: whether the commit that last
  changed the block in the config's history is an ancestor of the run's build commit and was made no later than
  the run's start. `true`, `false`, or `null`: not determinable outside git, for a build that is not a git commit
  (`EVAL_BUILD_REF`) and on a dirty tree, where the config on disk may not be the committed one.
- **The fingerprint does not change.** A hypothesis predicts; it does not change what was measured. It is a
  config key outside `params`, which is all the fingerprint reads of a config, and a test pins the hash with and
  without one.
- **Checked** by `evh validate` (V20) and by `evh run`, before anything is spent: the keys, the direction
  (better, worse, no-worse), `against` an existing config, `measure` one of the arm's metrics.
- **Reported** by `evh pair-test` (named in advance: yes, with the commit, no, or not determinable; and whether
  the result agrees with the direction) and by `evh goals --goal` beside the arm.
- **A hypothesis found in the config that the run does not carry reads "no"**: it was added after the run. That is
  the one way a "no" is reached for a run made before the block existed.
- **A pair the tool chose is not a named pair.** `pair-test --round` without `--a` takes the round's leader, so
  it is corrected for the arms in play (Bonferroni) and says so.

## Consequences

- "Named before the table was read" becomes a fact on the run, with a commit to look at, not a sentence in the
  output.
- It is a record of when the prediction was committed, not of what its author had read: the strongest honest
  claim git can support. A new arm committed with a hypothesis after its author read other arms' results reads
  "yes" for its own run, which is true: the prediction came before that run.
- The block is optional. A project without one sees no change except V20 and a `hypothesis` column that appears
  only when an arm has one.
- Old runs carry no block; they print what they always did.

## Alternatives considered

- **A pre-registration file per round.** Rejected: a round lists arms, not the change each carries; the
  prediction would sit away from the config it is about.
- **Hashing the block into the fingerprint.** Rejected: two arms differing only in their prediction measured the
  same thing; the fingerprint's job is to say a comparison held one variable.
- **Trusting the run's start time alone, without git.** Rejected: nothing proves the block existed then; git does.
