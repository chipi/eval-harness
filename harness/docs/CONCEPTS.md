# Concepts — why this refuses things

The tooling is small. The discipline is the product. Each rule below is
enforced in code, and each exists because its absence produced a wrong answer
that nobody noticed.

---

## Three inputs, or the number means nothing

Every run records three things:

| input | field | drop it and… |
| --- | --- | --- |
| **system under test** | `build.ref` | you cannot tell a code change from an eval change |
| **instrument** | `config_id` | you cannot tell a config change from a code change |
| **data** | `dataset_id` | you cannot compare anything to anything |

`evh validate` fails on a run missing any of them. `EVAL_BUILD_REF` sets the
first when the project is not the system under test, or is not a git repository — a version, an image digest, a
pinned dependency ref, whatever actually identifies the thing being measured.

**Pin it.** An eval against a moving target measures the target's movement, and
you will lose a day attributing that to your change.

---

## `dataset_id` is a contract, not a label

> A metric compared across two different `dataset_id`s is not a comparison.
> It is a coincidence.

`evh run-compare` refuses outright when the two runs disagree. Not a warning —
a refusal, because a warning above a number that looks authoritative gets
scrolled past.

This is also why `sources/` is immutable and why a dataset records a sha256 per
item. If an input changes under a frozen dataset, every number already reported
against it is describing bytes that no longer exist.
`evh dataset-materialize` re-verifies every hash and fails loudly rather than
quietly measuring something else.

What a dataset holds can be shown without its text, which its licence may not let you
publish: `evh dataset-profile --dataset-id my_corpus_v1`, where it is materialized, writes
`data/profiles/my_corpus_v1.json` (how many items and how long, the gold's labels or shape,
each item's link to its source when one is recorded). Commit it, and the dataset's catalog
page shows "what's inside"; `evh dataset-items` prints it.

When data genuinely changes, that is a new version — `my_corpus_v2` — never an
edit in place. The new version names the one it came from (`--from my_corpus_v1`) and records
the items it adds, removes and changes, so "what changed between v1 and v2?" has an answer
that is not a diff someone has to remember to run.

---

## Fields describe an item; they do not identify it

What you know about an item (the product area of a ticket, the show an episode came from,
its length) belongs with the item, typed and checked, not in a spreadsheet beside the
dataset that drifts from it. So a project declares its fields in a field set and the dataset
carries the values. But a field is a description, not the bytes that were measured: correct
a title and every run measured on that item is still a measurement of the same item. The
fingerprint therefore hashes the items' bytes and ignores their fields, and the dataset
records a separate hash of its fields, so a change to them is visible without invalidating
anything.

A field is also what makes "better on long episodes, worse on short ones" testable. Breaking a
comparison into groups is several comparisons at once, though, so the per-group tests are
corrected together: a group is held to a stricter threshold than it would be alone.

## Measure the arm's own noise before believing any delta

```bash
evh experiment-run --config ... --repeat 3
```

```text
Arm spread over 3 repeats (max - min on identical input):
  overlap_f1   spread=0.043888   treat deltas below 0.043888 as noise
```

A real case from the project this came from: an ASR model showed **0.058 WER
spread on byte-identical input** — wider than most of the deltas people were
arguing about. Every one of those arguments was about noise, and nobody knew,
because nobody had measured the arm against itself.

`run-compare` takes `--noise` and marks anything at or below it as noise. Omit it
and the tool nags, because a delta judged against nothing is not evidence.

`--noise 0` is a real answer — it means the arm is deterministic — and is treated
differently from omitting the flag.

---

## Gold is not silver

| tier | means |
| --- | --- |
| **gold** | human-authored or human-reviewed. The only thing you can honestly call correct. |
| **silver** | model-generated. Consistent, cheap, plentiful — and it encodes that model's opinion, including its mistakes. |

Silver is a legitimate starting point: it lets you **rank arms against each
other** today. It is not a claim about correctness, and a number scored against
it must say so.

Every run records `reference_tier`. The manifest beside the references carries
the caveat in full, and a reference made from a run (`reference-create --from-run`) names the run
it came from. The failure this prevents is quiet: silver numbers get quoted in a decision six
months later as though they were ground truth, and the model that authored them is the one
being evaluated. That is why the leaderboard marks the arm that wrote the reference it is scored
against, and why a goal page never makes it the leader: its row measures agreement with itself.

---

## Re-measuring a frozen experiment

A run's outputs are the expensive, frozen record; its scores are arithmetic over them. So
an experiment can be measured again, without regenerating anything, when a better
instrument arrives. There are three kinds:

| kind | what changes | cost | how |
| --- | --- | --- | --- |
| new reference | what an output is scored against, e.g. gold adjudicated by a person | $0 | `evh rescore --reference-id …` |
| new code scorer | the metric, written as code | $0 | `evh rescore` with the new scorer |
| judge scorer | the metric, delivered by a validated model | billed | `evh judge-score` ([ADR-0001](../../docs/adr/ADR-0001-judge-scorers.md), [RUNBOOK §12](RUNBOOK.md)) |

Two rules hold for all three. The originals are never overwritten: a re-measurement is
written to its own runs directory, and the leaderboard is pointed at it. And an
experiment's primary measurement changes only by a recorded decision, with the old one
kept beside it. In this repository AG News and DBpedia keep the dataset's own gold as
primary, because anyone can repeat it, and report the adjudicated gold beside it.

---

## Cost and speed are part of quality

A run records `latency_ms`, `tokens_in`, `tokens_out` and `cost_usd` per item,
and totals for the ones you are billed for. The harness times every call itself, so an adapter
that reports nothing still records its speed. "Model B scores higher" and "model
B scores higher and costs 4× per item" are different findings, and only one of
them is a decision.

A call's cost is the provider's bill when its response carries one (OpenRouter, and a LiteLLM
proxy that passes `usage.cost` through), and otherwise the config's prices × tokens. Prices live
in the experiment config, not in code, so a run records the prices it was costed at. A figure
computed from today's price list is not comparable to one from last quarter without saying so.
Which provider records which: [RUNBOOK §4](RUNBOOK.md#4-point-the-harness-at-your-system).

---

## A baseline is a decision

`evh run-promote` refuses three things:

- a run from a **dirty tree** — its `build.ref` does not describe what ran
- a run whose **build is unknown** — a different and worse problem, so it takes
  its own flag
- a **reason under three words** — because *"why is this the baseline?"* must have an
  answer in six months

A baseline is never edited. Promoting a new one replaces it, and git keeps the old one:
the commit history is the record of what the baseline was, and when. It carries what its number
means (the reference tier it was scored against, the adapter, the run's fingerprint), so a
baseline scored against silver cannot pass for one scored against gold.

---

## A goal says what the evaluation is for

A number answers a question only if someone wrote the question down. A goal names who uses the
output, the decision it informs, the measure that decides it and which way is better, and the
datasets it rests on; each config names its goal, and every run records it. It is optional until
a project sets a date from which every run must name one (`required_from`). The catalog's goal
page leads with its answer, the promoted baseline and why, or "no decision yet". Every field of a
goal file and its allowed values:
[RUNBOOK §4c](RUNBOOK.md#4c-the-goal-file-field-by-field).

---

## A round records a decision, not just a result

Experiments go round on round, and the reasons an arm was dropped are the first thing lost. An
optional round ([ADR-0004](../../docs/adr/ADR-0004-experiment-rounds.md)) records what it set out
to learn, what changed, which arms it carried in and which it dropped and why, and what it
concluded. `evh rounds` suggests the next decision from the evidence, as a command; it never
makes one. A closed round refuses new runs, so its evidence cannot grow after its conclusion.

---

## An agent reads; a person decides

An agent can look at what the catalog shows: `evh mcp` serves its views as tools (the ranking
and the statistics commands, `leaderboard`, `pair-test` and the like, are not tools yet)
([INTEGRATION](INTEGRATION.md#for-an-agent-evh-mcp)), and each call runs the command itself, so
the agent's numbers are yours, refusals included. It cannot act on them. Running an arm spends
money, promoting a baseline is a decision with a reason, closing a round fixes its evidence:
each of those has a consequence someone must own, so they stay commands a person runs. An agent
can prepare one and hand you the exact command. What an agent may also do, with whose consent,
is 0.7.0's to design.

A shared server answers anyone who can reach it, so `--public` holds back what a project may not
redistribute (an item's text), and the rates bound what a script can cost the machine.

---

## Two arms cannot agree to full precision

`evh validate` fails when two different configs report byte-identical scores and per-item results on
the same dataset. Independent arms do not agree to seventeen significant
figures; when they do, one of them is not its own measurement — a copied number,
a mis-wired arm, a cached result. Two arms that are both perfect on a binary metric agree on
every score too, so their outputs decide: different outputs are two measurements, not a copy.

This check exists because exactly that happened: a published figure for one
model turned out to be another model's output, identical to the last digit,
sitting in a report for months.

---

## Why so many refusals

A tool that always produces a number teaches people to trust numbers. The
refusals are the part that makes the numbers worth trusting — they are the
difference between a measurement and a plausible-looking figure.

If a refusal is wrong for your situation, override it explicitly and say why in
the reason field. That override is then recorded, which is the point.
