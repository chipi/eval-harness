# Tutorial 4 · Experiment rounds and dataset versions

Experiments go round on round: try some arms, keep what wins, drop what lost, change something,
compare again. **Rounds** record that, optionally: what each round set out to learn, what
changed, which arms were carried in and which were dropped and why, and what it concluded. A
project that never opens a round sees none of it. **Dataset versions** are the other thing
that changes between rounds: a new item arrives, and the dataset that includes it is a new
version that remembers where it came from.

This tutorial starts from the project [getting started](../GUIDE.md) leaves, offline, and
`make guide-check` runs it as written. Do it before adding gold
([tutorial 3](3-frontier-reference-and-judging.md)), or in a fresh copy of the project: once
gold exists, a new arm is scored against gold while the arms you carry in were scored against
silver, and a round compares arms only on one reference. Design:
[ADR-0004](../adr/ADR-0004-experiment-rounds.md).

## 1. Round 1: the arms you already have

Getting started ran three arms against the author's silver. Make that round 1 after the fact:
carry those arms in with `--keep` (they are not run again) and say what the round asks.

```bash
evh round-open --goal tickets_summary --dataset tickets_v1 \
    --hypothesis "how many leading sentences make the best one-line summary" \
    --keep tickets_lead1_v1,tickets_lead2_v1,tickets_lead2_noisy_v1
git add data/rounds && git commit -qm "tickets_summary r1: open"
```
```text
data/rounds/tickets_summary/r1.yaml: round r1 of tickets_summary, open
  Name it in each arm's config (round: r1, beside goal: tickets_summary), run them, then: evh rounds --goal tickets_summary
  Commit the round file before the runs: an uncommitted file makes them dirty.
```

A round belongs to a goal and one dataset, and is a file beside the goal,
`data/rounds/<goal>/<round>.yaml`. The commands are its only writers.

## 2. Read the evidence

```bash
evh rounds --goal tickets_summary
```
<!-- guide-check: varies lead2_noisy -->
```text
  r1   open    tickets_v1  3 arm(s), 0 retired

r1 · open · tickets_v1
  hypothesis: how many leading sentences make the best one-line summary

  on overlap_f1: 3 arm(s) in play, leader tickets_lead2_v1
    tickets_lead1_v1                 not separated      Δ -0.2592  p 0.0312
    tickets_lead2_noisy_v1           not separated      Δ -0.1011  p 0.0312

  suggested next:
    - 2 arm(s) tie with the leader (tickets_lead1_v1, tickets_lead2_noisy_v1): more items would separate them
        evh rank-stability --dataset-id tickets_v1
    - close the round with what it showed
        evh round-close --goal tickets_summary --round r1 --conclusion "..." --promote tickets_lead2_v1_...
```

`evh rounds` reads the evidence the way the inspector does (every arm in play against the
round's leader, Holm-corrected) and suggests the next decision, each as the command that makes
it. It decides nothing: you do, with the commands. Here every arm is behind `lead2` on every
ticket and none is separated at six items, so the honest decisions are about wording, not
winners.

## 3. Drop an arm, and close the round

`lead1` is behind `lead2` on every ticket. Drop it from the round, with the reason, then close
the round with what it showed:

```bash
evh round-retire --goal tickets_summary --round r1 --arm tickets_lead1_v1 \
    --reason "one sentence is behind two on every ticket"
evh round-close --goal tickets_summary --round r1 \
    --conclusion "lead2 is ahead of lead1 and lead2_noisy on all six tickets, separated from neither at n=6; lead2 stays the baseline"
git add data/rounds && git commit -qm "tickets_summary r1: closed"
```
```text
tickets_lead1_v1 retired from r1: one sentence is behind two on every ticket
round r1 of tickets_summary closed
```

`--promote <run_id>` on `round-close` would also promote that run to the dataset's baseline, with
the conclusion as its reason; `lead2` already is the baseline, so there is nothing to promote.
A closed round refuses new runs.

## 4. Round 2: change one thing

Round 2 continues round 1 (`--from r1`): it carries `lead2` in unchanged, drops `lead2_noisy` for
a new version of it, and records the change and what the round sets out to learn. `--budget-usd`
is what the round may spend; `evh rounds` sets its spend against it.

```bash
evh round-open --goal tickets_summary --dataset tickets_v1 --from r1 \
    --hypothesis "a noisy summariser that drops fewer words comes closer to lead2" \
    --change "tickets_lead2_noisy_v2: drops 5% of words instead of 20%" \
    --keep tickets_lead2_v1 \
    --retire tickets_lead2_noisy_v1 --reason "replaced by v2, which drops fewer words" \
    --budget-usd 0.01
```
```text
data/rounds/tickets_summary/r2.yaml: round r2 of tickets_summary, open
```

A new arm joins a round by naming it in its config, beside its goal:

```bash
cat > data/configs/tickets_lead2_noisy_v2.yaml <<'EOF'
config_id: tickets_lead2_noisy_v2
dataset_id: tickets_v1
params:
  provider: echo
  sentences: 2
  noise: 0.05
goal: tickets_summary
round: r2
EOF
git add -A && git commit -qm "tickets_summary r2: open; lead2_noisy v2"
evh experiment-run --config data/configs/tickets_lead2_noisy_v2.yaml --repeat 3
```
<!-- guide-check: varies spread -->
```text
  scoring against SILVER references for tickets_v1
  ...
wrote 3 run(s) to .../my-evals/data/runs
```

Every run records the round it ran in.

## 5. Read round 2, then close it

```bash
evh rounds --goal tickets_summary
```
<!-- guide-check: varies tickets_lead2_noisy_v2 retire separated -->
```text
  r1   closed  tickets_v1  2 arm(s), 1 retired  lead2 is ahead of lead1 and lead2_noisy on all six tickets, separated
  r2   open    tickets_v1  2 arm(s), 1 retired

r2 · open · tickets_v1 · from r1
  hypothesis: a noisy summariser that drops fewer words comes closer to lead2
  changed: tickets_lead2_noisy_v2: drops 5% of words instead of 20%
  retired: tickets_lead2_noisy_v1 (replaced by v2, which drops fewer words)
  ...
  on overlap_f1: 2 arm(s) in play, leader tickets_lead2_v1
    tickets_lead2_noisy_v2           separated: worse   Δ -0.0207  p 0.0312
  NOTE: spent $0.0000 of $0.01

  suggested next:
    - retire tickets_lead2_noisy_v2
        evh round-retire --goal tickets_summary --round r2 --arm tickets_lead2_noisy_v2 --reason "separated worse than tickets_lead2_v1 on overlap_f1 after Holm (p 0.0312)"
    - close the round with what it showed
  ...
```

Your Δ will differ (the arm is unseeded), and on a draw where it drops no word from one ticket it
is not separated, and the first suggestion goes. The same comparison, as the inspector would draw
it, and the round's leaderboard:

```bash
evh inspect --round r2 --baseline tickets_lead2_v1
evh leaderboard --dataset-id tickets_v1 --round r2
```
<!-- guide-check: varies tickets_lead2_noisy_v2 -->
```text
overlap_f1 (higher is better) · baseline tickets_lead2_v1 ×3: mean 0.900 · Holm across 1
  ...
Same conditions: all 15 recorded fields match (machine, libraries, harness, scorer, items, reference bytes).
  ...
  tickets_lead2_v1            3          0.900088         28.500000
```

Then close it, with what it showed:

```bash
evh round-close --goal tickets_summary --round r2 \
    --conclusion "dropping 5% of words instead of 20% still trails lead2 on every ticket; lead2 stays the baseline"
git add data/rounds && git commit -qm "tickets_summary r2: closed"
```
```text
round r2 of tickets_summary closed
```

A run naming a closed round is refused before it calls anything, so a round's evidence cannot
grow after its conclusion:

```bash
evh experiment-run --config data/configs/tickets_lead2_noisy_v2.yaml
```
```text
ERROR: data/configs/tickets_lead2_noisy_v2.yaml: round r2 of tickets_summary is closed; open the next one (evh round-open --from r2)
```

`evh validate` (V14) checks the round files; `evh family-test --round r2` takes the opponents in
play in a round, as `leaderboard --round` does. The catalog's goal page shows the rounds, newest
first, with the open round's suggestions ([tutorial 5](5-catalog-and-inspector.md)).

## 6. A new version of the dataset

A seventh ticket arrives. `tickets_v1` is frozen, so the dataset that includes it is
`tickets_v2`, made `--from tickets_v1`: it records where it came from and which items it adds,
removes and changes.

```bash
mkdir -p data/sources/tickets && cp tutorial/tickets/*.txt data/sources/tickets/
printf 'The export to CSV button on the reports page does nothing. I tried Firefox and Chrome. We need the monthly report for an audit on Friday.\n' > data/sources/tickets/t07_reports.txt
evh dataset-create --dataset-id tickets_v2 --source-dir data/sources/tickets --from tickets_v1
```
```text
data/datasets/tickets_v2.json  (7 item(s))
  derived from tickets_v1: 1 added, 0 removed, 0 changed
```

```bash
evh datasets
evh datasets --dataset-id tickets_v2
```
```text
  dataset     items  arms  references         made from
  tickets_v1  6      5     silver/tickets_v1
  tickets_v2  7      0     —                  tickets_v1
tickets_v2: 7 items, 0 arms

made from tickets_v1: 1 added, 0 removed, 0 changed
  added: t07_reports

no arm has run on it yet
```

Nothing measured on `tickets_v1` moves: its runs, references and baseline stay its own. An arm
measured on `tickets_v2` is a config with `dataset_id: tickets_v2`, and needs a reference for
`tickets_v2` (silver from a run, as in getting started, or gold). `evh validate` (V2) fails a
version whose parent dataset is gone, and the catalog links the versions both ways with what
changed.

Commit the sources and the new dataset:

```bash
git add data/sources data/datasets && git commit -qm "tickets_v2 from tickets_v1: t07_reports"
```
