# RFC-037: Conversational scenarios: a user who talks back

- **Status**: Draft, waits for its first case. Split out of RFC-035 by the owner, 2026-11-18. Owner decision kept from
  RFC-035: the simulated user is any model, local or online, named the way a judge is, and part of the run's
  fingerprint.
- **Authors**: Marko Dragoljevic
- **Related**: [RFC-035](RFC-035-scenarios.md) (the base: scenario, transcript, runner contract, statistics),
  [RFC-036](RFC-036-agentic-scenarios.md) (agents: tools, stations, the path), [RFC-019](RFC-019-datasets-from-production.md)
  (datasets from production), [RFC-034](RFC-034-charts-and-judge-reasons.md) (judge reasons)

## Abstract

Some systems need a user who answers: a chatbot that asks back, a checkout that asks for an address, an agent that
stops to ask for what it is missing. The user's next turn depends on what the system just said, so one input is not
enough. This RFC adds the user's side to [RFC-035](RFC-035-scenarios.md)'s scenario and transcript: a **session** runner
the harness drives turn by turn, and three ways to play the user: a **script**, a **person**, a **simulated user**. It
sits on RFC-035; it does not need [RFC-036](RFC-036-agentic-scenarios.md), and works with it when the system is also an
agent.

Its first case: the bugfix chain can end "needs info from the reporter"; the fleet's bake-off already has a simulated
reporter who answers (`reporter_answer.sh`): the chain asks, the reporter answers, the chain runs again.

## 1. Who plays the user

| driver | what it is | cost |
| --- | --- | --- |
| **script** | the user's turns are fixed in the scenario, in order | $0, the same every run |
| **person** | someone runs the scenario by hand and records what happened | a person's time |
| **simulated user** | a model follows the scenario's plan and writes each next turn from what the system just did | a model's calls |

The user's side stays in the harness because it is part of the instrument: two systems are comparable only under the
same user, so the script, or the simulated user's model and prompt, are the harness's to fix and to fingerprint, as a
judge's are.

## 2. The session runner

```
start(scenario, system)      -> session            # a fresh, isolated run, given the scenario's input and env
step(session, user_turn)     -> system_turn        # what the system did with that turn: its reply, its actions, done?
end(session)                 -> final_state        # what the outcome check reads, then the session is gone
```

The harness keeps the loop: the user's turn depends on the system's last reply, the stop rule (the user says it is
done, `user_done`; the conversation's length limit; a timeout) is part of the measurement, and the transcript is recorded as it happens by the side that
scores it. A batch run of [RFC-035](RFC-035-scenarios.md#2-the-runner-contract) is a session with one step, so both
record the same transcript.

## 3. A conversational scenario

[RFC-035](RFC-035-scenarios.md#3-a-scenario)'s fields, plus the user's side:

```yaml
input: Show my top customers                    # the user's first message, as RFC-035's input
plan: |                         # for a simulated user; or `turns:` for a script (the user's turns, in order)
  You want your top customers in the EU for last quarter. Say "EU" and "last quarter" only when asked.
  If you get a list, ask for just the top 5.
```

`success` is never shown to the simulated user. Here *turn* means a step of the conversation (the user's, the
system's), not RFC-036's model call: RFC-035's open question 1.

## 4. The drivers, in order

1. **Script** first: the scenario's `turns:` are sent in order. Deterministic, $0 on the harness's side, and it proves
   the session runner, the loop and the transcript's user turns before any model plays a user.
2. **Simulated user** second: a model named as a judge is (any provider, local or online), given the plan and the
   transcript so far, never the success criteria, writes the next turn or says it is done. Its model, settings and prompt
   are part of the run's fingerprint; a run under another simulated user is another measurement.

## 5. The person, and the path between manual and automated

- **A person as the driver**: the scenarios exported as a sheet; someone runs each by hand against the system and fills
  in what happened and whether it worked; the sheet comes back as a run (`sheet-import`).
- **A person as the grader**: as in RFC-035, through the sheet.

The path from manual to automated reuses one scenario at every step: a person runs it (a manual run); a person's session
is recorded once and becomes the scenario's `turns:` (a script); the script runs every time; a simulated user varies it
(the plan).

## 6. Scoring a conversation

Beyond RFC-035's: needless questions and repeated asks (a judge, counted per scenario), turns to success, and whether the
system asked for what it actually lacked. Every judge is validated against people's labels on transcripts.

## 7. Real conversations as scenarios

A capture of real conversations (RFC-019) becomes scenarios: the first message as `start`, a plan written by a person
(or proposed by a model, accepted by a person) from what the user went on to say, `success` from the outcome production
recorded. A production failure becomes a scenario that must pass from then on.

## 8. What it adds to the surfaces

A system names its driver and, for a simulated user, its model; the transcript view draws the user's turns (RFC-035's
renderer already has them). No new screen, no new command beyond what RFC-035 adds.

## 9. The build, in order

1. The session runner and the scripted driver, on the `local` runner.
2. The simulated user.
3. The person as driver through the sheet; real conversations as scenarios.

Started when a system that converses needs it: the first is the bugfix chain's question to its reporter, after
[RFC-036](RFC-036-agentic-scenarios.md)'s bugfix step.
