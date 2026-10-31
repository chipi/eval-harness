# Tutorial 6 · Datasets from production

Getting started froze six tickets someone wrote by hand. A real project often has something better: what its
system did in production, and what happened afterwards. This tutorial keeps that as a **capture**, makes a
dataset from it, turns the outcomes into labels, and splits dev from heldout. It runs offline, on the kit's
support-desk export (`tutorial/production/desk_export.jsonl`: the same six tickets, with when each arrived,
its channel, and how it ended). The design is [RFC-019](../rfc/RFC-019-datasets-from-production.md); every
command is in the [RUNBOOK §15](../../harness/docs/RUNBOOK.md#15-datasets-from-production-the-capture-lane).

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
desk_2026_10: 6 record(s) from jsonl, captured 2026-10-30T14:37:38Z
  records from 2026-10-01T08:12:00Z to 2026-10-05T10:00:00Z
  datasets made from it: none
```

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
independent items), `--dedup text`, `--sample N --seed S`. Tags label the dataset outside its identity; the
catalog's datasets page groups by them, and `evh datasets --tag source=support-desk` filters by them.

The six-ticket arms of Getting started run on it unchanged: copy a config and set `dataset_id:
tickets_desk_v1`.

## 3 · Labels from outcomes

```bash
evh reference-from-outcomes --dataset-id tickets_desk_v1 --capture desk_2026_10 \
    --map tutorial/production/outcomes.yaml --name silver/tickets_desk_v1_outcomes
```
```text
data/references/silver/tickets_desk_v1_outcomes: 5 of 6 item(s) labelled (1 skipped, 0 matched no rule, 0 not in the capture)
```

`outcomes.yaml` is a rule list, first match wins:

```yaml
- {when: {resolution: duplicate}, skip: true}
- {when: {resolution: fixed}, label: needs-engineering}
- {when: {resolution: answered}, label: support-only}
```

Each label is what the desk did afterwards, not a person's judgement of what was right, so the reference is
**silver**, with a caveat saying so. A goal never decides on it: with a gold reference beside it, the goal
recommends from gold and shows the outcome group as "shown, not recommended"; without gold, it recommends
nothing ([ADR-0020](../adr/ADR-0020-second-references-are-silver.md)). It is the reference a classifier ("does
this ticket need engineering?") would be scored against, beside a person's gold; the six-ticket summarisers
are not. `examples/triage-fleet/` is a full project built this way, on a real agent's decisions.

## 4 · Dev and heldout

```bash
evh dataset-split tickets_desk_v1 --heldout 0.34 --seed 7
```
```text
data/datasets/tickets_desk_v1_dev.json  (5 item(s))
data/datasets/tickets_desk_v1_heldout.json  (1 item(s))
```

Each item goes to heldout when the hash of the seed and its key falls below the share, so it keeps its side in
every later version. `--key F` keeps every item sharing a field value on one side (one fingerprint, one
customer); `--by time --key F` makes the newest share heldout.

`evh validate` checks the capture too (V17): every record against the hash it was captured with.

## Data you may measure but not publish

`dataset-from-capture --hide-text` marks the dataset `text: hidden`: its items, its arms' outputs, its
references' texts and its text fields stay off every public page, the public inspector and a public `evh mcp`,
while its numbers are shown.
