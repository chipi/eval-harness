# ADR-0001 — Judge scorers: re-measuring frozen outputs with a validated LLM judge

**Status:** Proposed
**Date:** 2026-10-19

## Context

The harness separates what a run *produced* from how it was *measured*. A run's outputs
(`predictions.jsonl`) are the expensive, frozen record; its scores are arithmetic over them,
and `make rescore` recomputes them for $0 into a separate directory, never over the
originals. That covers every change to a scorer written as code.

Two experiments in this repository now show the next step is needed:

- The summarisation experiment ranks 29 arms by `coverage`, the repository's own overlap
  metric.
- The SummEval experiment measured how well scorers agree with human experts. `coverage`
  agrees at τ 0.1011, below plain ROUGE-1 (0.1487). The best LLM judges reach 0.5195, 93% of
  one expert's agreement with the other two (92% when the judge is chosen on half the
  articles and scored on the other half).

So one experiment has validated a better instrument for another. Scoring techniques keep
improving; the data, the arms and their outputs do not need to change when they do. The
harness should let a frozen experiment be **re-measured** with a better scorer, and record
which scorer produced which numbers.

An LLM judge is not a code scorer, and four properties make `rescore` the wrong home for it:

1. **It costs money and is not deterministic.** Hosted models at temperature 0 matched
   their own output 9.8% of the time across three repeats (summarisation report §3.3). A
   judge's scores have noise, as an arm's do.
2. **It is a model.** Its identity is a model id, a provider, a prompt and a protocol, all of
   which must be fingerprinted like an arm's.
3. **Its validity is established elsewhere and transfers only under the same protocol.**
   SummEval validated judges that read the article and score **all its summaries in one
   call** (listwise, 16 summaries, arm identities hidden). `rescore` calls `score()` once per
   output, inside one run.
4. **It can prefer its own family.** When each hosted LLM wrote the reference summaries, 22
   of 24 pushed their own model family up the ranking, by 7.4 places on average
   (summarisation report §3.3).

## Three kinds of re-measurement

The same frozen outputs can be measured again in three ways, and the experiments here need
all three:

| kind | what changes | cost | mechanism | first uses |
|---|---|---|---|---|
| **new reference** | what an output is scored against (e.g. adjudicated gold) | $0 | `make rescore REFERENCE=…` (exists) | AG News, DBpedia: the disputed gold labels, adjudicated |
| **new code scorer** | the metric, written as code | $0 | `make rescore` with a new scorer (exists) | Few-NERD: the standard micro-F1 for every arm, so all arms are comparable with published numbers |
| **judge scorer** | the metric, delivered by a model | billed | `make judge` (this ADR) | summarisation (validated on SummEval); SciFact's unlabelled abstracts (unvalidated until checked against a human sample) |

The first two exist and need no new machinery, only a reference set or a scorer and a
recorded decision to use it. The rest of this ADR is about the third.

## Decision

**A judge scorer is a new artifact, and judging is a cross-run pass over frozen outputs.**

1. **The scorer artifact.** `data/scorers/<scorer_id>.yaml` declares:
   - `kind: judge` (code scorers stay in the adapter and `rescore`);
   - the judge models, each a full arm-style model spec;
   - the prompt (hashed) and the protocol: listwise, the number of outputs per call, blinding
     and the order seed;
   - a `validation` block: the experiment, metric and value that justify the judge
     (e.g. `summeval_100`, mean τ vs experts, 0.5195 = 93% of one expert);
   - a cost cap.
   Its fingerprint is recorded with every score it produces.

2. **The validation gate.** The harness refuses a judge scorer whose `validation` block is
   missing or names no committed run. `--unvalidated` overrides it, and every number then
   carries the label "unvalidated judge" in tables and reports. "Silver is not gold" is
   enforced, not advised.

3. **The judging pass.** `make judge EXP=<exp> SCORER=<scorer_id>`:
   - builds a derived, hash-frozen **judging set** from the committed runs. One item is one
     source item with every arm's output for it. The arm set is pinned in the judging set's
     id;
   - hides arm identities and shuffles their order per item with a recorded seed;
   - runs each judge as an arm over the judging set with the existing machinery (dataset
     hashes, fingerprints, cost caps, resume, stored outputs), so a judge's raw verdicts are
     themselves a frozen record and re-reading them is $0;
   - projects the verdicts back to one score per arm per item and writes them as scored runs
     in `data/runs-judged/<scorer_id>/`. The originals are never touched. The leaderboard,
     `family_test` and `pair_test` read that directory like any rescored one, so every test
     applies unchanged.

4. **Controls that are part of the pass, not optional.**
   - **At least two judges from different vendor families.** Each judge is reported, their
     agreement is reported, and the scorer's primary score is their mean. An arm from a
     judge's own family is flagged in that judge's column.
   - **Position.** A second shuffle on a subset measures how much a verdict depends on
     order.
   - **Noise.** A repeat on a subset measures the judge's own disagreement, so a difference
     between arms can be read against it.

5. **Records.** A report states which version of each layer it reads: the outputs, the
   scorer, the decision rule (e.g. "outputs v1 · scorer `judge-v1` · Holm sign-flip v1").
   Changing an experiment's primary metric is a recorded decision, made with a reason as a
   baseline promotion is. The old metric stays, as history, beside the new one.

The first use is the summarisation experiment, re-measured with judges validated on SummEval.
The second is SciFact. Its relevance labels are incomplete: 227 judgments cover 200 queries,
so a relevant but unlabelled abstract ranked first counts against an arm. A judge can label
those abstracts, but no judge here has been validated on scientific relevance. That run goes
through the gate as "unvalidated" until a small human-labelled sample validates it, which is
exactly the case the gate exists for.
The decision layer (how a pick is chosen from a group the test cannot separate) is versioned
the same way but is out of scope here.

## Consequences

**Positive**
- An experiment can be re-measured as scoring improves, without regenerating outputs or
  paying for the arms again.
- One experiment can validate the instrument of another, and the link is recorded.
- Judge verdicts are frozen and fingerprinted, so they are reproducible and re-readable for
  $0, like any run.
- All existing statistics apply unchanged.

**Negative**
- **Listwise scores depend on the arm set.** A judge ranking 29 summaries together scores
  each against the others. Adding an arm later changes the comparison, so it needs a new
  judging pass, a new version, not an append. The arm set is pinned in the judging set's id
  for this reason.
- **The validation transfers only partly.** SummEval validated 16 summaries per call, from
  2019-era systems; summarisation has 29 per article, all modern. The report must state the
  difference. Choosing how many outputs per call (all 29, or blocks of 16) is an open
  parameter, decided and recorded in the first scorer.
- Judging costs money and adds a noise source. It has a cost cap, and its noise is measured.
- One more artifact type and one more command to learn.

**Neutral**
- Code scorers and `make rescore` are unchanged.
- The lifecycle gains a ninth artifact (scorers), shown on the "Use it" page beside
  datasets, references, arms and runs.

## Alternatives considered

- **A judge inside `score()`, run by `rescore`.** This would be the smallest change, but
  `score()` sees one output at a time, so the judge would be pointwise. Pointwise was not
  validated: SummEval's validated judges are listwise, and its one pointwise scorer, UniEval,
  reached 64%. It would also hide paid, non-deterministic calls inside a command documented
  as "no API calls, no money". Rejected.
- **A new experiment ("summarisation, judged").** This would duplicate the arms and outputs
  under a second name, lose the link to the run that produced them, and split one question
  into two. Re-measurement is a property of the experiment, not a new one. Rejected.
- **One judge.** This is cheaper, but it leaves self-preference unmeasured, and the
  reference-writing result shows that preference is large. Rejected.
- **Human scoring of the summarisation outputs.** This is the gold standard, but no budget
  exists for 200 × 29 summaries. A small human slice to check the judges on this data is a
  natural follow-up. Deferred.
