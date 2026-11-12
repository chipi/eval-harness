# replay-filing: replay the code that ran, and prove it faithful (RFC-030)

A filing stage turns an alert into an issue: a new one, or a comment on (or a reopen of) the issue its key already
has. It reads an issue tracker and its own ledger, and writes. To measure a change to it on production's history,
the harness runs **its own code**, each decision at the commit production ran then, against the tracker as it was,
and scores that replay only once it reproduces what production did, decision by decision.

Everything here is synthetic and made by a script, so it runs anywhere at $0. It is the triage fleet's filing replay
(`signal-fleet-filing`: 324 of 324 rows agreeing, 253 decisions and 34 sweeps on 21 commits) cut down to a
system of 55 lines.

## Run it

From your project (with the example copied into it, so its adapter is the project's):

```bash
cp -r <harness>/examples/replay-filing examples/
python examples/replay-filing/make_history.py --out replay-filing
evh capture --importer jsonl --query '{"path": "replay-filing/rows.jsonl"}' --capture filing_prod
evh dataset-from-capture filing_prod --dataset-id filing_history_v1 --fieldset filing \
    --field ts --field started --field production_issue
evh dataset-materialize --dataset-id filing_history_v1
evh run --config data/configs/filing_production_v1.yaml                 # production's arm
evh faithfulness --config data/configs/filing_replay_v1.yaml --production <that run>
evh label-import replay-filing/gold --dataset-id filing_history_v1 --set gold --by person:you
evh reference-promote --dataset-id filing_history_v1 --labels gold --tier gold \
    --reason "what each decision should have done" --by person:you
evh run --config data/configs/filing_replay_v1.yaml                     # the replay, scored
evh run --config data/configs/filing_candidate_v3.yaml                  # every decision at the third commit
python examples/replay-filing/mutants.py --system replay-filing/system --production <that run>
```

`tests/test_replay.py` runs this sequence and checks what each step should show.

## What is here

| file | what it is |
|---|---|
| `system/v1..v3/filing.py` | the system under test, three versions: v2 keys alerts without case or numbers, v3 files no info alert and holds a scheduled job's alert until its third failure |
| `make_history.py` | makes the system's git repository (one commit per version) and production: a day per version, 20 decisions, people closing issues between them, all frozen as `decisions.jsonl` and `issues.jsonl` (each issue's timeline); writes the code record (`data/models/toy_filing.yaml`, `kind: code`), the field set, the configs and the goal |
| `replay_world.py` | **R3, the world a replay reads**: the tracker as it stood at any time, from the frozen timelines, with the replay's own writes kept in it so a later decision reads what an earlier one did; a call it does not know is refused |
| `production_actions.py` | **R4, what production did**: each fleet write joined to the decision whose write window holds it (from the stamp before it to its own, plus a measured clock slack), since a write carries no decision id |
| `replay_filing.py` | the adapter: imports `filing.py` from the commit each decision ran (`_codeload.use`), sets its two seams (the tracker, the ledger file) again at each switch, reads the tracker when the decision started |
| `mutants.py` | **R5**: four named edits, each applied to every commit of a clone; `evh faithfulness` must disagree somewhere |

## What it shows

- **Production's own writes, hidden (RFC-031 P1).** `filing_replay_hidden_v1` hides production's own reopens made inside the
  replayed window (`replay.hide: {kinds: [reopened]}`): the replay's own reopens stand in for them and still agree with
  production on all 20, which `evh faithfulness` must show for this config before it is scored. `filing_candidate_v3_hidden`
  merges the alert production filed at d05 into an existing issue; a person closed production's issue on day 3, a
  reaction to an action the candidate never took: its history confound, 1 of 20.
- **Each decision at its commit.** The replay at the recorded commits agrees with production on all 20: the reopen
  after a person closed an issue, the v2 key that files a new issue for an alert v1 had filed under another key, the
  v3 info rule. Run every decision at v3 instead (the candidate) and they differ: that difference is what a change
  is measured by.
- **The gate catches a replay bug.** An adapter that reads the tracker at the decision's stamp, after its own writes,
  sees production's reopen and comments instead: faithfulness lists those decisions, and scoring is refused until
  each is fixed or named.
- **Coverage.** No decision in the history comes from a scheduled job, so v3's `_cron_waits` never runs; the record
  names it, and the mutant that changes it survives for exactly that reason.

## What it does not show

- A real tracker's API, pagination or rate limits; the stand-in answers four calls.
- Clock skew between machines beyond the slack the join allows; the history's clocks agree.
- A system with compiled extensions, which the harness cannot switch between versions in one process.
- Changes to the frozen world or to the config's `params` after a faithfulness record: the gate does not see them.
