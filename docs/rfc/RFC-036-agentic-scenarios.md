# RFC-036: Agentic scenarios: tools, stations and the path

- **Status**: Draft (0.9.0, built with [RFC-035](RFC-035-scenarios.md)). Split out of RFC-035 by the owner,
  2026-11-18. Owner decisions the same day: the first users are Flotilla's agents, with scenarios part of their
  acceptance; one shape in two layers (on the flotilla session's proposal); the offline path; the evaluation pieces
  first-class in Flotilla's v2 design; any agent can be tested, not only Flotilla's.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-035](RFC-035-scenarios.md) (the base: scenario, transcript, runner contract, statistics),
  [RFC-037](RFC-037-conversational-scenarios.md) (a user who talks back), [RFC-034](RFC-034-charts-and-judge-reasons.md)
  (judge reasons), [RFC-031](RFC-031-held-out-discipline-and-outcome-labels.md) (held-out discipline)

## Abstract

An agent chooses its own next steps: it calls tools, reads what they return, and acts. Whether it got the right answer
is not enough; how it got there matters (did it look before it acted, did it skip the check that matters), and so does
which of several agents in a chain went wrong. This RFC adds to [RFC-035](RFC-035-scenarios.md)'s scenario and
transcript what an agent needs: **actions** (each tool call with its arguments and result), **stations** (one agent of
several, each with its own model and harness), the **path** and forbidden paths, per-station scores, and **recorded tool
results**, so an agent can be run many times against the same world.

Any agent can be tested this way: a runner for it writes the transcript. The first runner is the one for Flotilla's
agents, and Flotilla's v2 design builds what that runner needs.

## Decisions (owner, 2026-11-18)

1. **The first users are Flotilla's agents**: every Flotilla agent is evaluated with scenarios as part of its
   acceptance. The fleet session's count: three of Flotilla's routines call a model, triage (`triage/cycle`), the bugfix
   chain (`bugfix/fix`) and `fix-podcast`; the rest call none. The order is triage, then bugfix, then fix-podcast; each
   takes one input and works alone, so each scenario is one step of [RFC-035](RFC-035-scenarios.md)'s runner contract.
2. **One shape in two layers**, on the flotilla session's proposal: an **episode** (one station's run) inside the
   harness's **transcript**, embedded verbatim, never converted. Names: *station* (one agent), *episode* (one station's
   run), *turn* (one model call), *action* (one tool call).
3. **Any agent**: the episode is defined generically in the harness's transcript schema; Flotilla's
   `runtime/episode.schema.json` is that shape plus Flotilla's own fields, so its runner embeds its episodes unchanged
   and a runner for another agent writes the generic shape. Confirmed by the flotilla session (2026-11-18): Flotilla
   vendors a pinned copy of the generic schema by version under its `runtime/testdata/` and tests every episode against
   it; no runtime reference, and a new version of the harness's schema is a deliberate bump on Flotilla's side.
4. **The offline path**: Flotilla's agents run outside flotillad, on the version's stations and its own command
   ([§5](#5-the-first-runner-flotilla)).
5. The evaluation pieces are first-class parts of Flotilla's v2 build ([§5](#5-the-first-runner-flotilla)).

## 1. A scenario of an agent

[RFC-035](RFC-035-scenarios.md#3-a-scenario)'s fields, plus:

```yaml
expected_path: [ledger_read, policy_lookup, escalate]
path_order: loose               # loose | strict | none
forbidden: [refund_issue]       # an action that fails the path wherever it appears
recorded_results: recorded/refund-over-limit.json   # optional: tool results to answer the agent's calls with
```

`expected_path`, `path_order` and `forbidden` are reference, held in a reference set as `success` is. Recorded tool
results are matched by station, tool name and normalised arguments, never by order, so `k` runs of a live model replay
against one world; a call with no recording fails the run and is never sent live.

## 2. A transcript of an agent

[RFC-035](RFC-035-scenarios.md#4-a-transcript)'s transcript, plus `stations: [episode, …]` in run order, kick-backs
included. A run of one agent has one station; the bugfix chain has five (verdict, reproducer, fix, review, advisor).

An episode, generic (`episode` in the harness's transcript schema; field shapes from the flotilla session, 2026-11-18):

| field | shape |
| --- | --- |
| `schema_version` | on the episode itself; additional properties allowed, so a runner's superset validates |
| `station` | `{name, sequence}` |
| `version`, `spec_hash` | the system's version and its spec's hash |
| `harness` | `{name, version}` (`pi`, `0.80.10`): stream shapes change between versions, so the version is part of what was measured |
| `turns[]` | one model call each: `model_alias` (what the system asked for) and `model` (the upstream model that answered, when reported); `text`; `tokens` `{input, output, cache_read, cache_write, reasoning}`, each null when not reported, never 0 for unknown; `started_at` (ISO 8601 UTC); `latency_ms`; `prompts` `{name: {text?, sha256, ref?}}`, one per declared text, the text inline only under a size cap |
| `actions[]` | one tool call each, under its turn: `name` (`server__tool` for MCP); `args` and `result`, each whole or `{sha256, length}` above a size cap; `redacted` (credentials masked before recording: without it a masked value cannot be told from a real one); `ok`; `started_at`; `duration_ms` |
| `answer` | the station's last answer |
| `exit_reason` | an open set: `completed`, `turn_cap`, `timeout`, `error` at its core; RFC-037 adds `user_done`; a harness may add its own |
| `cost` | `{usd, source}`, `source` one of `gateway`, `provider`, `harness_estimate` and required: no figure without its source |

A runner may add its own fields (Flotilla's: `session_id` to resume after a kill, `notes` for prompt changes a harness
forced, `raw_path` for the native stream); the harness keeps them and ignores them.

Arguments and results are kept whole only after the runner's redaction (credentials masked), and above a size cap (set
in the schema) as a hash and a length, so a record cannot balloon or carry raw source text. The transcript view draws
actions under their turn and stations as sections.

## 3. Scoring an agent

| what | question | scorer |
| --- | --- | --- |
| path | did the agent take a valid path? | `path_match`: the expected actions against the actions taken, as a set (loose) or in order (strict); a forbidden action fails it |
| behaviour | invented facts, needless steps | a judge, counted per scenario |
| per station | which agent of the chain went wrong? | any scorer of RFC-035 or above, on one station's episode: did the reproducer's test fail on the base, did the review approve a wrong fix |

For a chain, a station's score often says more than the whole run's. Judges are validated as in RFC-035.

## 4. Any agent

A runner for an agent starts it with the scenario's input, gives it its tools (or answers its calls from the recorded
results), isolates it, and writes the transcript. Examples beyond Flotilla: a coding CLI run in a fresh home and
worktree, an MCP server driven by a model with a tool loop, a project's own agent behind its API. The harness never
learns which.

## 5. The first runner: Flotilla

**Can Flotilla be where scenarios run?** Read 2026-11-18 at flotilla `main` 0ed0d28: not as it was, and not by its own
rule: "Evaluation in any form lives outside flotilla" (flotilla `docs/rfc/RFC-0002-job-runtime.md` item 9); a run took
no input; isolation was per worker role, with no reset per scenario. The pattern that already existed ran outside both
projects: fleet-eval-data's bugfix driver runs a routine's entry point in a container from Flotilla's worker image, with
Flotilla mounted read only (fleet-eval-data `projects/bugfix-eval/PLAN.md`). So Flotilla's agents are systems under
test, and their runner lives beside fleet-eval-data.

**Flotilla's v2 design** (flotilla `docs/wip/v2-design.md`, final at 9b58673, both reviewers' go; designed, not built):
every routine gets versions; a new version runs in shadow beside the live one with no effect, over the same frozen
input; live and shadow results are exported as pairs. "Evals have the same guarantees": an eval runs through flotillad
as a shadow run on a given input, or offline; either way no write credential is reachable.

**Scenarios take the offline path** (the flotilla session's recommendation, the owner's decision): the runner takes the
version's stations from `flotillad -stations <version> -models <config>`, runs the version's own `run:` command through
the offline entry point with the scenario's input and a fresh state folder, and wraps the episodes the run writes in a
transcript: isolation and reset per scenario, many trials, no load on the live platform, exactly the version that would
go live. Through flotillad does not fit: v2's shadows start from live inputs and are paired with them.

**What v2 builds for it** (on the owner's request that these be first-class; build steps are v2's):

| piece | v2 step | what it is |
| --- | --- | --- |
| episode schema | 3 | `runtime/episode.schema.json`, versioned, in the same step as the offline entry point that writes episodes; every adapter validated against it. An episode carries the raw stream's path, never the stream |
| offline entry point | 3, its test in 5 | a tested, sealed contract (`flotillad -run-offline`, flags settled at build): the version's own `run:` in the routine's shadow worker image, a fresh HOME, the read-only environment (never the caller's), its own models config (an eval spends on its own key), the run's API an in-process stand-in that turns every write into a decision record and accepts no live flotillad address or token; outputs to a folder the caller names, outside the state and the fleets tree. Stations on adopted harnesses get the input's commit in a fixture workspace, with no network but the gateway. The harness's runner starts it; Flotilla provides and tests it, on authored fixtures only |
| frozen input | 2 | `runtime/input.schema.json`: the handed input, the ledger mark, the case keys, the commit, the routine and version; live-only fields optional, so dataset-built inputs validate. It may carry recorded tool results ([§1](#1-a-scenario-of-an-agent); RFC-0002 §8 model replay). A captured input exports with the ledger slice as of the mark and a state snapshot |
| acceptance | 1 | `acceptance:` in routine.yaml lists the required kinds (`pairs`, `replay`, `scenario_eval`; `[pairs]` when absent). Promote records the bar in force and the evidence (an eval-harness run id and its verdict line) and refuses evidence that is missing or FAILED unless the operator gives a reason. Flotilla reads the verdict; it never computes it |

A captured live input carries production data, written outside any repository until scrubbed: making it a scenario is
a copy and a scrub, and it lands in the installation's private data (fleet-eval-data), never a public repository. A
frozen input is a scenario's `input`; a pair's sides are transcripts.

**Where scenarios sit in Flotilla's acceptance** (the installation's bars, flotilla-fleets
`docs/fleets-v2-requirements.md`, draft; the fleet session's summary): a new version is accepted by the operator after
replay gates, a model replay (triage: k>=3, false dismissals and silent drops no worse than live; bugfix: approved plans
that fail the oracle = 0 and approved plans and oracle passes at least live's, cost from the gateway key) and a shadow
comparison of at least seven days. Scenarios are the eval part of those bars; the shadow pairs stay Flotilla's.

## 6. Triage, the first scenario set

From the fleet session (2026-11-18): a triage scenario's input is one signal (a GlitchTip issue or a log pattern) with
its six read-only probes' recorded results and a ledger fixture; one step; its actions are the probes the model chose;
its final state is the decision (file, escalate, dismiss, cleanup), its certainty and reason, and what it would file in
a dry run. Success is the reference decision; dismissing or cleaning up without the evidence probe is forbidden. Much of
this exists already as items with frozen tool results; what scenarios add is the path and the outcome check on what it
would file.

## 7. The build, in order

1. The episode in the transcript schema (generic, with a runner's own fields kept); actions and stations in the
   transcript view.
2. `path_match` and per-station scoring; recorded tool results in the scenario.
3. Triage: its scenarios and its runner beside fleet-eval-data, on Flotilla's offline entry point once v2's step 3 has
   landed; the first acceptance.
4. The bugfix chain, then fix-podcast.

Built with [RFC-035](RFC-035-scenarios.md#10-the-build-in-order)'s steps 1 to 3, in 0.9.0.

## Open questions

1. Decided: the generic episode is the harness's, Flotilla's a pinned superset (decision 3).
2. The generic schema's path and commit, when built (RFC-036's step 1), sent to the flotilla session to pin; Flotilla's
   superset commit, when its v2 step 3 lands, for §2 to reference.
