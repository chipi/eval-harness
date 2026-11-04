---
name: evh-promote-with-evidence
description: Record a decision in eval-harness (evh) — promote a run to the dataset's baseline with the test that supports it and who asked for it — and check the project tree before reporting. Use when asked to "pick", "choose", "promote", "ship" or "make it the baseline", after a comparison, or before telling anyone an arm won.
metadata:
  harness-version: "0.7.0"
---

# Promote a baseline, with its evidence

A baseline is the run future changes are measured against: one per dataset, written once, replaced
by the next promotion and never edited. Promoting is a decision with a consequence, so:

- **Only when your operator asked for it** (the owner's rule for agents). Otherwise prepare the
  command below and hand it over.
- **The reason carries the evidence and who asked**: the measure, the test and its result, the
  number of items, and the operator's request. A reader of the baseline file must be able to tell
  why without asking you.
- **A tie is a decision too.** When the test does not separate the arms, say so in the reason and
  why this one (cheaper, faster, the incumbent); never write that it won.

The blocks run as written on the tutorial kit after `evh-evaluate-a-system`.

## Promote

Find the run (its id from `evh run`, or the list), then promote it:

```evh
RUN=$(evh runs-list --json | python3 -c 'import json,sys; rows=[r for b in json.load(sys.stdin)["result"]["blocks"] for r in b.get("rows", [])]; print(next(r["run_id"] for r in rows if r.get("config_id") == "tickets_lead2_v1"))')
evh run-promote --run "$RUN" --reason "operator asked for a working baseline: lead2 is closest to the author's silver on all six tickets but not significantly different from lead1 at n=6 (pair-test p > 0.05); kept until the dataset grows"
git add -A && git commit -qm "tickets_v1: baseline"
```

## Check, then report

```evh
evh runs-list --baselines
evh validate
```

`evh validate` checks the whole tree (frozen hashes, one run per `config_id`, references, goals).
A failure is reported with its check name; fix the cause, never the check.

## Stays the operator's

Closing a round (`evh round-close`), anything past the spending cap, deleting or rewriting anything
committed. Hand over the exact command instead.
