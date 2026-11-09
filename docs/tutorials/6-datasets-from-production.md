# Tutorial 6 · Datasets from production

Getting started froze six tickets someone wrote by hand. A real project often has something better: what its
system did in production, and what happened afterwards. This tutorial keeps that as a **capture**, makes a
dataset from it, turns the outcomes into labels, splits validation from test, then scores production's own decisions
against what happened, finds where it was wrong, and picks those tickets for the next version of a dataset you
govern. It runs offline, on the kit's support-desk export (`tutorial/production/desk_export.jsonl`: the same six
tickets, with when each arrived, its channel, where the desk's router sent it, and how it ended). The design is
[RFC-019](../rfc/RFC-019-datasets-from-production.md) and [RFC-023](../rfc/RFC-023-labels-and-references.md);
every command is in the [RUNBOOK §15](../../harness/docs/RUNBOOK.md#15-datasets-from-production-the-capture-lane)
and [§15b](../../harness/docs/RUNBOOK.md#15b-evaluating-what-production-did).

Start from a project with the kit, under version control: `evh init --tutorial`, then `git init -q && git add -A
&& git commit -qm kit`.

## 1 · Capture

```bash
evh capture --importer jsonl --query '{"path": "tutorial/production/desk_export.jsonl"}' --capture desk_2026_10
```
```text
data/captures/desk_2026_10: 6 record(s) from jsonl
  commit it (and what you make from it) before any billed run: untracked data marks runs dirty
```

Each line became a **record**: its `id`, its `body` (the ticket), its `fields` (here `channel`), its time and
its `outcome` (how it ended). `data/captures/desk_2026_10/capture.json` keeps every record's hash, and
`records/` the records. The importer is the built-in `jsonl`; `tsv`, `github` (issues, with the comment written
beside each close) and `langfuse` (traces) come with the harness, and your own is a class with a `records(query)`
method (`evh importer-check` tests it against the contract).

```bash
evh captures
```
```text
desk_2026_10: 6 record(s) from jsonl, captured ...
  records from 2026-10-01T08:12:00Z to 2026-10-05T10:00:00Z
  datasets made from it: none
```

A production source is often far larger than a test needs: `--sample-rate 0.001 --seed 7` keeps one record in
a thousand, chosen by a hash of each id, as the records are read, so the same rule draws the same records again and
the whole source is never held at once. A project importer receives the rule and may sample at the source itself.

A production export can hold what must not leave the project: `evh capture-scrub desk_2026_10 --command
"python your_scrubber.py {records}"` runs your scrubber over the records and re-hashes the ones it changed.

## 2 · A dataset from the capture

```bash
evh dataset-from-capture desk_2026_10 --dataset-id tickets_desk_v1 --tag source=support-desk --tag channel=all
evh dataset-materialize --dataset-id tickets_desk_v1
```
```text
data/datasets/tickets_desk_v1.json  (6 item(s); 6 of 6 records kept)
data/materialized/tickets_desk_v1  (6 item(s), all hashes verified)
```

Only the body becomes the item: what the system received, nothing about what happened next. A selection is
part of the dataset's record: `--where channel:email`, `--one-per F` (one record per value, the newest, for
independent items), `--dedup text`. Tags label the dataset outside its identity; the
catalog's datasets page groups by them, and `evh datasets --tag source=support-desk` filters by them.

The six-ticket arms of Getting started run on it unchanged: copy a config and set `dataset_id:
tickets_desk_v1`.

## 3 · Labels from outcomes

```bash
evh label-from-capture --dataset-id tickets_desk_v1 --capture desk_2026_10 \
    --map tutorial/production/outcomes.yaml --set desk_outcomes
```
```text
data/labels/tickets_desk_v1/desk_outcomes: 5 of 6 item(s) labelled (1 skipped, 0 matched no rule, 0 not in the capture)
```

`outcomes.yaml` is a rule list, first match wins:

```yaml
- {when: {resolution: duplicate}, skip: true}
- {when: {resolution: fixed}, label: needs-engineering}
- {when: {resolution: answered}, label: support-only}
```

Each label is what the desk did afterwards, not a person's judgement of what was right: the set's source is
`rule`, the capture and the mapping's hash. Labels are not a reference. Score arms against them as they are
(`evh rescore --dataset-id tickets_desk_v1 --labels desk_outcomes`), or, when you decide they are the yardstick,
promote them, at the tier you choose and with the reason
([ADR-0022](../adr/ADR-0022-references-are-promoted-labels.md)). They are what a classifier ("does this ticket
need engineering?") would be scored against, beside a person's labels; the six-ticket summarisers are not.
`examples/triage-fleet/` is a full project built this way, on a real agent's decisions.

## 4 · Validation and test

```bash
evh dataset-split tickets_desk_v1 --test 0.34 --seed 7
```
```text
data/datasets/tickets_desk_v1_validation.json  (5 item(s))
data/datasets/tickets_desk_v1_test.json  (1 item(s))
```

Each item goes to test when the hash of the seed and its key falls below the share, so it keeps its side in
every later version. `--key F` keeps every item sharing a field value on one side (one fingerprint, one
customer); `--split-by time --key F` makes the newest share test.

`evh validate` checks the capture too (V17): every record against the hash it was captured with.

## 5 · Later: what came since, and how it ended

Production goes on after the capture. Two things change: new records arrive, and the outcomes of the records
you hold move on (a ticket still open then is closed now). Each is its own capture.

**What came since.** `--since-capture` continues from where the earlier capture ended:

```bash
evh capture --importer jsonl --query '{"path": "tutorial/production/desk_export.jsonl"}' \
    --capture desk_2026_11 --since-capture desk_2026_10
```
```text
data/captures/desk_2026_11: 0 record(s) from jsonl (1 already in desk_2026_10)
```

The query's `since` becomes the time the earlier capture ended, and records it already holds are skipped by
id. The kit's export has nothing newer, so nothing is captured; on a live system this is where the next
dataset version comes from (`dataset-from-capture desk_2026_11 --dataset-id tickets_desk_v2`). Every record must
fall inside the window the capture records: one that doesn't (an importer that ignores `since`) is named and
nothing is written. `--late` keeps the ones older than `since` that the earlier capture never saw, listed in
`capture.json` as `late`. `evh importer-check` tests that your importer keeps to `since`.

**How it ended.** A continued capture never reads a record it holds again, so its outcomes stay as they were.
For newer outcomes of the same records, take a fresh capture of the same query and label from it:

```bash
evh capture --importer jsonl --query '{"path": "tutorial/production/desk_export.jsonl"}' \
    --capture desk_2026_11_outcomes
evh label-from-capture --dataset-id tickets_desk_v1 --capture desk_2026_11_outcomes \
    --map tutorial/production/outcomes.yaml --set desk_outcomes_2026_11
```
```text
data/captures/desk_2026_11_outcomes: 6 record(s) from jsonl
data/labels/tickets_desk_v1/desk_outcomes_2026_11: 5 of 6 item(s) labelled (1 skipped, 0 matched no rule, 0 not in the capture)
```

The items are matched by id, so the dataset stays as it was frozen and only its labels move. A rule's
`min_age_days` counts from the new capture, so a record too young to judge then may be judged now. On the
triage fleet, three days later, today's outcomes labelled 7 more of 233 decisions and changed none. Each is a set
of its own (a set is never edited): the runs scored against the older one still read it.

## 6 · What production decided, against what happened

The desk's router sent each ticket somewhere when it arrived: the export's `routed` field. That is production's
decision, and it can be scored like any arm, against the outcome labels of §3:

```bash
evh arm-from-capture --dataset-id tickets_desk_v1 --capture desk_2026_10 --as desk_router_v1 \
    --field routed --labels desk_outcomes
```
```text
  a recorded arm: 6 output(s) read from the capture desk_2026_10, no system called
  scoring against the label set labels/tickets_desk_v1/desk_outcomes (labels, not a reference)
  ...
```

No model was called: each output is the capture's record of the same id (`--field routed`; a project's adapter
reads it with `recorded_output(record)`), and it costs nothing. Scored against a label set, the run lands beside
the others, in `data/runs-labels-tickets_desk_v1-desk_outcomes/`. Where was it wrong?

```bash
evh inspect --sheet --dataset-id tickets_desk_v1 --runs desk_router_v1 --wrong-against desk_outcomes
```
```text
tickets_desk_v1: 2 of 6 item(s) (wrong) · wrong 2 · read on overlap_f1 (higher is better)
  ...
label them: evh label-sheet --dataset-id tickets_desk_v1 --item t01_login --item t04_api --out sheet.csv --runs desk_router_v1
```

Each row is a ticket: what each run wrote and its scores, every label it has with its source (the author's labels
from Getting started are there too: the same tickets, by their bytes), and the signals (`--disagree`, `--split`,
`--new-vs`, `--unlabelled`, and `--where` on its fields). The sheet writes nothing: it ends with the commands for its
rows. The inspector shows the same, from the dataset page's "Open its sheet".

Say the routing set you govern was frozen from the email tickets only. The router's two mistakes came on a web and
an API ticket it does not hold: pick them for it, and make its next version from the picks.

```bash
evh dataset-from-capture desk_2026_10 --dataset-id tickets_routing_v1 --where channel:email
evh pick --dataset-id tickets_desk_v1 --item t01_login --item t04_api --for tickets_routing_v1 \
    --tag case=misrouted --note "routed to support; it needed engineering"
evh picks --for tickets_routing_v1
evh dataset-extend tickets_routing_v1 --dataset-id tickets_routing_v2 --picks
```
```text
picked 2 item(s) of tickets_desk_v1 for tickets_routing_v1; evh picks lists what waits
tickets_routing_v1: 2 pick(s) waiting
  ...
data/datasets/tickets_routing_v2.json  (4 item(s): 2 of tickets_routing_v1, 2 picked)
  derived from tickets_routing_v1: 2 added, 0 removed, 0 changed
```

A pick waits in `data/picks.jsonl` (append-only; the latest line for an item wins, `pick --drop` takes one off)
until a version uses it. `tickets_routing_v2` holds v1's tickets and the two picked, each with where it came from
(`extended_from`), and their labels follow them; nothing is promoted by it. What you promote stays your decision:
the deploy sheet (`evh deploy-sheet --config ARM [--capture C]`) then says what production must match to run it,
and whether a capture shows it did ([RUNBOOK §15b](../../harness/docs/RUNBOOK.md#15b-evaluating-what-production-did)).

## Data you may measure but not publish

`dataset-from-capture --hide-text` marks the dataset `text: hidden`: its items, its arms' outputs, its
references' texts and its text fields stay off every public page, the public inspector and a public `evh mcp`,
while its numbers are shown.
