# ADR-0006 — A goal weighs cost, quality and speed; a strategy picks (0.4.0)

**Status:** Accepted (2026-10-25), as built.
**Date:** 2026-10-25
**Detail:** [PRD-005](../prd/PRD-005-goals-and-rounds.md) (requirements),
[UXS-001](../uxs/UXS-001-catalog.md) (the goal page, the home page's glance),
[UXS-002](../uxs/UXS-002-inspector.md) (the scatter's axes),
[RUNBOOK §4c](../../harness/docs/RUNBOOK.md#4c-the-goal-file-field-by-field) (the goal fields)

## Context

A goal named one measure that decides (`success_criteria.primary`). Everything else it cared
about was in `secondary` and `guardrails`: lists the harness kept but never read. So the goal
page ranked arms on quality alone, and the cost and the speed of each arm, which the runs
already record per item (`cost_usd`, `tokens_in`, `tokens_out`, `latency_ms`), took no part in
the answer. A reader deciding which system to run looks at cost against quality against speed,
and some goals care about a measure of their own as well (grounding, a word error rate).

The first rule tried was "among the arms the paired test cannot separate from the quality
leader, pick the cheapest". On the intent-routing scenario (32 customer messages) it picked a
free keyword matcher at accuracy 0.875 over the frontier model at 1.000: 4 items differ, and on
32 items the test could not separate them. A test that cannot tell two arms apart on a small
set is not evidence that they are equally good.

## Decision

- **Axes.** A goal weighs quality (its primary measure) and two built-in axes that need no
  entry: **cost** (`cost_usd`, the mean per item, with tokens in + out shown beside it, for a
  local model that is free but not costless) and **speed** (`latency_ms`, read on its p95, the
  slow tail; p50 is shown beside it). `success_criteria.axes` adds a limit, a role (`ignore`:
  an overnight batch does not weigh speed), another measure for a built-in (`usd_per_min`), or
  a **project axis**: any per-item metric its runs record, one entry and nothing else.
- **Limits first.** An arm past an axis's limit is out, with the reason (a speed limit reads
  the p95). So is an arm measured on fewer items than the group's most-measured arm ("n 4 of 20
  items": its mean is over other items, so it could lead on a part of the set), and one that
  shares fewer than two items with the leader (the paired test cannot run). A flagged arm (it
  wrote the reference, too few items for `min_items`, a format the goal does not take) and an
  arm a round retired are shown and never recommended.
- **The leader** is the best eligible arm on quality; among equal values the first by label,
  so the order the arms come in never decides.
- **A strategy says who is tied with the quality leader** (`success_criteria.strategy`):
  - `balanced` (the default): not separated by the paired test AND within the quality margin
    (`axes.quality.margin`; by default 2% of the leader's mean, so it means the same on a 0-1
    rate and a 1-5 score, and 2% of the group's range when the leader is 0, where a share of
    the leader would tie nothing. With only two arms that range is their gap, so a 0 leader
    needs the goal's own margin, and the reasons say so);
  - `quality_first`: the same quality only;
  - `frugal`: anything the paired test cannot separate.
  Identical per-item scores are tied in every strategy. A judge's group decides on the judge's
  score, so the goal's quality limit and margin (written for its own measure) do not apply there.
- **A tie-break picks among the tied** (`success_criteria.tie_break`, default cost then speed,
  any axis the goal weighs; validate's V14 refuses one it does not).
- **What is not known is said.** A number an arm does not record is "not recorded", never 0,
  and is never a reason to drop it. An axis that some tied arm does not record cannot break the
  tie: it is skipped with the reason and the next axis decides (an unpriced hosted call must not
  lose on cost to a priced one). Speed is not compared, nor used to break a tie, between arms
  whose runs recorded different machines; arms that recorded none count as one machine.
- **Guardrails stay words** (`{name, rule, source}`): shown on the goal page and by
  `evh goals --goal`, never computed.
- **`secondary` is removed**; its entries become axes.
- The rule recommends. Promoting a baseline is still `evh run-promote`, a person's decision.

## Consequences

- **Positive.** The goal page shows, per group, the recommendation and why: the strategy, who
  was tied, who was out and for what. Beside the reasons it shows each arm's cost and speed, and
  a chart of quality against each axis. The home page's glance gains the recommended arm with
  its cost and speed against the baseline; the dataset and arm pages show cost and speed; the
  inspector's scatter takes cost and tokens. `evh goals --goal` and `evh overview` print the
  same. A project adds its own axis with one line.
- **Negative.** A goal with `secondary:` fails validation until it is moved to `axes:`
  (UPGRADING). The default margin is a convention: a goal whose measure has a natural
  tolerance should set its own.
- **Neutral.** The decision is computed per group (one dataset, scored against one reference
  or one judge), as the leader always was; numbers from different references are still never
  weighed together.

## Alternatives considered

- **A weighted score** (quality minus w × cost). Rejected: the weights are arbitrary, and one
  number hides the trade-off a reader needs to see.
- **The frontier only** (the arms no other beats on every axis). Kept as the charts, rejected as
  the rule: it does not pick one.
- **One fixed rule.** Rejected: whether a free arm 0.125 behind is good enough is the goal's
  call, not the harness's; hence the strategies, with a default.
