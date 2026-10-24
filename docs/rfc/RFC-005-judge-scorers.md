# RFC-005: Judge scorers and the judging pass

- **Status**: Completed (0.3.0); judge-scorer YAMLs hashed by content in 0.4.0 ([RFC-001](RFC-001-fingerprint-and-code-identity.md))
- **Authors**: Marko Dragoljevic
- **Related PRD**: [PRD-003](../prd/PRD-003-judging.md)
- **Related ADR**: [ADR-0001](../adr/ADR-0001-judge-scorers.md)
- **Related RFCs**: [RFC-002](RFC-002-run-records-and-derived-runs.md) (judged runs are derived runs)
- **Code**: `harness/scripts/judge_score.py` (the pass), `harness/scripts/judging.py` (prompt,
  parser, judge client, rank statistics), `harness/schemas/scorer.schema.json`,
  `judging-set.schema.json`, `verdict.schema.json`; test `harness/tests/test_judge_score.py`

## Abstract

A judge scorer re-measures frozen outputs with LLM judges, as a cross-run pass: one judging item
is one source item with every arm's output for it, judged listwise and blind, and the verdicts
are projected back to one score per arm per item, written as derived runs that every existing
test reads. A gate refuses a judge until a committed run validates it against human ratings.
This RFC holds the design that [ADR-0001](../adr/ADR-0001-judge-scorers.md) recorded, and what
its first uses found.

## Problem Statement

The harness separates what a run produced from how it was measured, and `rescore` recomputes
code scorers for $0. In this repository, the summarisation experiment ranks 29 arms by
`coverage`, its own overlap metric, while the SummEval experiment measured that `coverage` agrees
with human experts at τ 0.1011, below plain ROUGE-1 (0.1487), and the best LLM judges at 0.5195,
93% of one expert's agreement with the other two. One experiment had validated a better
instrument for another. A judge is not a code scorer, and four properties make `rescore` the wrong
home for it:

1. it costs money and is not deterministic (hosted models at temperature 0 matched their own
   output 9.8% of the time across three repeats, summarisation report §3.3);
2. it is a model, identified by a model id, a provider, a prompt and a protocol;
3. its validity transfers only under the protocol it was validated with (SummEval: the article
   and all its summaries in one call, 16 summaries, arms hidden), while `rescore` calls `score()`
   once per output;
4. it can prefer its own family (when each hosted LLM wrote the reference summaries, 22 of 24
   pushed their own family up the ranking, by 7.4 places on average).

### Three kinds of re-measurement

| kind | what changes | cost | mechanism |
| --- | --- | --- | --- |
| new reference | what an output is scored against | $0 | `evh rescore --reference-id …` |
| new code scorer | the metric, as code | $0 | `evh rescore` with the new scorer |
| judge scorer | the metric, delivered by a model | billed | `evh judge-score` (this RFC) |

## Design

### The scorer artifact

`data/scorers/<scorer_id>.yaml` (`scorer.schema.json`): `scorer_id` (the file name),
`kind: judge`, `dataset_id`, `judges` (arm-style model specs, each with a vendor `family`;
at least two families), `prompt`, `protocol`, and optionally `task`, `validation`, `arms_match`
and `cost_cap_usd`. The `task` block names what an item is (`source_label`), what the arms wrote
(`output_label`), the `dimensions` and the `scale`; without it the scorer judges SummEval's
news-summary task (ARTICLE, SUMMARIES, coherence, consistency, fluency, relevance, 1–5). The
protocol sets `outputs_per_call`, `blinding`, `order_seed`, `position_check_fraction`,
`noise_check_fraction` and `contested_threshold`. Since 0.4.0 the YAML is hashed by its parsed
content, so a comment is not a new scorer.

### The gate

A scorer runs only if its `validation` block names, for each judge, a committed run whose metric
equals the stated value (and is at least `min_metric` when set) and whose model, temperature,
reasoning, provider, max tokens, prompt file and prompt sha256 are the judge's. `--unvalidated`
runs it anyway and labels every number "unvalidated judge" (exit 3 without it). `provider: fake`
judges never pass. The gate checks that a validation exists and is current, not that it
transfers to the outputs being judged.

### The pass (`evh judge-score --dataset-id D --scorer S`)

1. **Gate**, as above.
2. **Judging set**: one item is the source plus every arm's output for it (one run per arm, the
   latest). Arm identities are hidden and their order shuffled per item with the seed. The arm
   set, the outputs, the seed, the block size and a declared task are hashed into the set's id;
   the manifest goes to `data/judging-sets/`. A different arm set is a different set, never an
   append. `--match` or `--arms` choose the arm set.
3. **Blocks**: with more arms than `outputs_per_call`, an item is judged in the fewest blocks of
   at most that size, sizes as equal as possible (29 arms with 16 per call are 15 + 14). Arms are
   assigned to blocks by the per-item shuffle; the judge scores each output on an absolute scale
   per dimension, which is what lets blocks be averaged, an assumption the position check tests.
4. **Verdicts**: each judge reads each block and answers with JSON scores; each raw reply is
   stored atomically under `data/judge-verdicts/`, so a rerun skips what is stored (resume),
   `--no-calls` re-reads for $0, and `--retry-unparsed` calls again for replies that did not
   parse. The cost cap (`cost_cap_usd`, `EVAL_MAX_COST_USD`) stops the pass mid-run with what was
   bought kept.
5. **Controls**: a second shuffle on `position_check_fraction` of the items (it re-forms the
   blocks) measures position bias; a repeat on `noise_check_fraction` measures the judge's own
   noise; each judge's agreement with the others is reported; an arm from a judge's own family is
   flagged (`self_family_<judge>`), with the raw own-minus-others gap, which is not a bias
   estimate since families differ in real quality.
6. **Projection**: one score per arm per item (the mean of the dimensions per judge;
   `judge_score`, the primary, is the mean over judges), written as derived runs
   (`derived.kind: judge`) in `data/runs-judged/<scorer_id>/`, plus a `summary.json` with the
   controls. `EVAL_RUNS_DIR=data/runs-judged/<scorer_id>` makes the leaderboard, `pair-test` and
   `family-test` read them.

`--dry-run` builds the judging set and prints calls, tokens and the estimated cost, calling
nothing. `evh judge` stays the older pointwise judge panel.

## What the first uses found

The first use was the summarisation experiment, re-measured with judges validated on SummEval.
Validated on 2019-era summaries, the judges ranked every LLM above every BART model. The one human
check on these outputs went the other way (one non-expert reader, 20 pairs on truncated articles,
14 to 6 for BART, p = 0.115), which confirms neither. On three 2022 systems (GPT-3, BRIO and T0)
the judges matched the annotators' agreement with each other, and preferred the LLM summary to
BRIO's more often than the annotators did, within noise. Neither shows whether the validation
transfers to this experiment's outputs; calibrate on comparable human data before a judged score
replaces a primary. Larger, dearer judges did not settle it either: the two highest-scoring
SummEval judges from vendors not in the first pair (`judge-summ-v2`, the same prompt, reasoning
off, at 41× the cost) reached the same verdict and the same 20-to-0 preference on the human-check
pairs. Checked against crowd ratings of LLM-era summaries (Zhang et al. 2024), all four judges
track the raters better than one rater does on coherence and relevance (they trail one on
faithfulness) and, by mean coherence and relevance, rank a BART-based fine-tune first or second of
19, so they show no blanket preference for LLM-written summaries; they still deviate from the
raters system by system in both directions. This experiment's own outputs are still unchecked by
people beyond the one reader.

The second is SciFact: 227 relevance judgments cover 200 queries, so a relevant but unlabelled
abstract ranked first counts against an arm. A judge can label those abstracts, but no judge here
is validated on scientific relevance, so that run goes through the gate as "unvalidated" until a
human-labelled sample validates it, the case the gate exists for.

## Alternatives Considered

- **Extend the judge panel.** Pointwise on 1–5, not what SummEval validated; its verdicts are not
  frozen runs; it judges only finalists. Rejected as the vehicle; its cost abort and disagreement
  flag were reused.
- **A judge inside `score()`, run by `rescore`.** Pointwise, which was not validated (SummEval's
  one pointwise scorer, UniEval, reached 64%), and it would hide paid, non-deterministic calls in a
  command documented as free. Rejected.
- **A new experiment ("summarisation, judged").** Duplicates arms and outputs and loses the link
  to the runs that produced them. Rejected.
- **One judge.** Leaves self-preference unmeasured. Rejected.
- **Human scoring of every output.** The gold standard, with no budget for 200 × 29 summaries; a
  20-pair human check was done (`examples/summarization-cnn-dailymail/human_check_judge.json`), a
  larger one is open.

## Consequences

- Listwise scores depend on the arm set; adding an arm needs a new judging pass.
- The validation transfers only partly (16 summaries per call from 2019-era systems against 29
  current arms here, in blocks of 15 and 14), and a report must say so.
- Judging costs money and adds a noise source; it is capped and its noise is measured.

## Testing

`harness/tests/test_judge_score.py` (the judging pass), `evh validate` V11 (judging sets), V12
(verdicts), V13 (judge scorers), and GUIDE step 10 offline with fake judges.
