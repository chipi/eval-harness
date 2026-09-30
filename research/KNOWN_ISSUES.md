# Known issues — read before reviewing

Everything here is **open and known**. Re-finding it costs a reviewer time that would be
better spent on what is not on this list. Fixes are in the git log, not here.

Last updated 2026-09-29, after **round 2**.

## What round 2 says about round 1, and about this file

The previous version of this paragraph read: *"round 1 — 4 high-severity and ~20 further
findings, all reproduced in code before fixing, **all fixed except where noted below**."*

That was wrong, and it is the most useful thing on this page. Round 2, reviewing the
same repo after those fixes, found **6 round-1 findings still open** and **26 new ones**,
several of them created or left by the round-1 fixes themselves:

| what round 1 was told | what round 2 found |
|---|---|
| the `EVAL_PROMOTE_REASON` injection is closed | `make run-promote` raised `NameError` on **every** invocation — the fix shipped broken, and the only test of that script was `--help` |
| `check_terminology.py` reporting green while reading zero files is fixed | fixed in that one file. `check_links.py` printed broken links and **exited 0**; `check_report_claims.py` printed "0/0 claims verified" and **exited 0** with no runs. The lesson was learned as an instance when the finding was a class |
| the cost figures are corrected to what the provider billed | corrected in **one** of the four reports. Two others shipped the correction *notice* over 31 uncorrected cells |
| the parsers are fixed | the round-1 fixes were inert — re-running them over the stored outputs moved nothing, which I reported as "the parsers are settled". The real bug was underneath, in both array matchers, and moved **seven arms across two experiments** |
| `rescore.py` works from a clone now that outputs are committed | for four of five examples. Summarisation's 24 committed runs record their adapter relative to a path `rescore` never tried, so the experiment this repo leads with could not be rescored at all |
| DeepSeek-V4.1-Flash is ~765 GB | 510 GB, measured. 765 was computed by assuming one byte per `I8` element; those tensors are packed at ~4 bits |

**The pattern, stated so a third round can look for it rather than re-find it:** the
recurring failure here is not a wrong answer, it is a *check that cannot fail* — a
script that exits 0 whatever it saw, a test that only runs `--help`, a correction
notice copied without the correction, a claims file that covers the numbers I was
proud of and not the ones most recently found wrong. Round 2 added
`test_the_checks_can_actually_fail`, which points each `make ci` checker at a tree that
must make it fail and asserts on the exit code. That test exists because I fixed this
class of bug twice while believing each time that I had fixed the class.

**Not claimed:** that round 2's fixes are complete or that the same pattern is now
absent. Every round-2 fix was verified by reverting the code and confirming the new
test fails — which is evidence about those fixes, and says nothing about what neither
of us thought to check.

---

## Measurements that were never taken

| gap | consequence | why |
|---|---|---|
| **`fn_mistral_l_n200_v1`** never ran | every "of 26" in REPORT_NER is a family of 26, not 27 | `mistral-large-2512` is rate-limited upstream on OpenRouter's shared pool; 3 items in 7 minutes. [Handover](HANDOVER_NER_BLOCKED_ARM.md) |
| **5 frontier SciFact rerankers** never ran | the top tie (12–13 arms) is a tie among *cheap* models; the report cannot say whether a frontier model reranks better | ≈$12 (price-table; $8–$45 once the 0.67×–3.76× billing spread is allowed for) against that sweep's $1.94 billed. Was stated as $31.40 until 2026-09-29, on a multiplier that did not survive checking. [Handover](HANDOVER_RETRIEVAL_FRONTIER_ARMS.md) |
| **6 local ML checkpoints** never ran | DBpedia has no fine-tuned local arm at all, so it cannot answer the fine-tune-vs-pay question its twin answers | pickle checkpoints need torch ≥ 2.6; no Intel-Mac wheel above 2.2.2. [Run them](RUN_THE_BLOCKED_ML_ARMS.md) |
| **No quantised arm was measured** | §0's ≤64 GB column assumes int8/int4 preserve quality. int8 usually does, int4 often does not | would need a local serving stack |
| **No throughput measured anywhere** | every latency figure is per-item at concurrency 1. A 44 MB model and a 70B model scale completely differently and nothing here says how | out of scope as built |

## Known weaknesses in what *was* measured

- **One pass per arm, temperature 0.** Every interval is over *items*, never over *runs*.
  Temperature 0 is not reproducible here: two runs of an identical SciFact config scored
  0.6691 and 0.6617, because OpenRouter routes across providers.
- **Hosted model identity is unverifiable.** Runs record `identity_declared: true`, not
  proof. A provider can change weights behind an alias.
- **Boundary vs detection errors are not separated in NER.** Few-NERD's IO tagging makes
  some gold spans unrecoverable by construction; that share is unquantified.
- **`gliner`'s 0.5 threshold is untuned**, so the +0.3134 training effect is an upper
  bound on that comparison.
- **No confidence anywhere hosted.** Logprobs were never requested, so calibration exists
  only for the three local arms that supply a probability.
- ~~**Nemenyi above k=25 prints no pairwise verdict.**~~ **CLOSED 2026-09-30.** This
  entry said the gap was deliberate because "the table stops at 25 and guessing is
  worse". Guessing is worse; stopping was not the only alternative. The critical values
  are a one-dimensional integral over the studentised range, about thirty lines of
  stdlib — [`scripts/nemenyi_table.py`](../harness/scripts/nemenyi_table.py) computes
  them, reproduces all 24 of Demsar's published values to within 0.0007, and
  `test_nemenyi_table_is_computed_not_copied` asserts both that and that the table
  shipped in `leaderboard.py` is what the computation gives. All five experiments now
  carry a critical-difference line. Found by external review, who also supplied the k=26
  to k=30 values independently — they match the computation to four decimals.

## Reproducibility, and what a clone still needs

Committed: `metrics.json`, `predictions.jsonl` **and `outputs/`** for every measurement
run, plus the rescored NER set that REPORT_NER's figures actually come from. `make ci`
runs `check_report_claims.py`, which verifies 17 headline numbers against them.

`outputs/` was excluded until 2026-09-29 on an estimate of mine that was wrong — "128 MB
of copyrighted derivatives". Measured, it is 8.3 MB of content, and four of the five
examples are single class words, document ids, or CC BY-SA 4.0 entity spans. Only the
1.7 MB of summarisation output raises a copyright question at all, and those are
~60-word model paraphrases rather than corpus text. Committed; the one-line reversal is
in `harness/.gitignore`.

**What a clone still needs before it can rescore: the corpora.** This is the part
committing outputs did not solve. `data/sources/<id>/` and
`data/references/{gold,silver}/<id>/` are gitignored for all four corpora — none is ours
to redistribute — so a fresh clone has 7 reference files against the 1,382 these runs
were scored on. Six reference sets must be rebuilt before `rescore.py` will run:
`ag_news_200`, `cnn_dailymail_20`, `cnn_dailymail_200`, `dbpedia_280`, `few_nerd_280`,
`scifact_200`. Each example's `fetch.py` is seeded and rebuilds its slice byte-for-byte,
free, from the public dataset.

**This was worse than a missing file until 2026-09-29, and finding it is the reason to
say so plainly.** Cloning this repo and running `rescore.py` without the corpora did not
fail. It exited 0 and reported `f1 = 0.1071` for an arm whose recorded `f1` is `0.6798`
— every prediction counted as a false positive against an empty gold set. A missing
*output* called `die()`; a missing *reference* fell through as `None`, two lines apart.
So the guarded artifact was the expensive one and the unguarded one was the corpus, which
is precisely what a clone lacks. `rescore.py` now refuses a declared-but-absent reference
set and names the fetcher; a partial set warns. Regression test:
`test_rescore_refuses_a_missing_reference_set`.

Verified end-to-end: with the `few_nerd_280` references restored, rescoring
`fn_anthropic_l_n200_v1` in a fresh `git clone` reproduces **all 23 of its numeric
metrics** at the stored six-decimal precision.

**Cost of committing outputs, both readings.** 8.3 MB as content; 128 MB as disk, because
32,710 files of a few hundred bytes each sit in 4 KB blocks. A whole clone is 30 MB
downloaded and 228 MB on disk. One `outputs.jsonl` per run would cut that to ~47 MB and
143 files, and it is the better layout — not done, because it rewrites the writer, the
resume reader, `rescore`, two report scripts and a self-test, which is the crash-safety
path reviewed in round 1. Open, and cheap to do later.

**Also not committed: 72 summarisation dev runs** (`cnn_dailymail_20`, 3 repeats). They
predate `_portable_id` and record an absolute path containing a username. Excluded rather
than edited, because rewriting a field inside a finished run would leave
`fingerprint.hash` describing bytes that no longer exist. REPORT_SUMMARIZATION §3.6's
n=20 half therefore cannot be recomputed from this repo.

## Judgement calls a reviewer may disagree with

These are decisions, not oversights. Argue with them by all means.

1. **Costs are what the provider billed** (`usage.cost`), not a price table. The table was
   wrong per arm by 0.67×–3.76× because an alias is not a price.
2. **The `nothing` / `random` / `constant` arms are calibration checks first**, baselines
   second. A floor whose score is predictable is how you find a scorer bug.
3. **Label noise is kept, degenerate items are filtered.** A mislabelled item still poses
   the task; a one-character sentence does not.
4. **The retrieval example's adapter is not refactored to match the others.** Round 1
   flagged the drift; the two differences that changed a score were fixed, and the rest is
   style in a file that is deliberately not shared code.
5. **Only the 12 cheapest hosted arms ran on SciFact**, by a price-ordered cut declared
   before any result was read.

## What round 1 found that is now checked automatically

So a second round can assume these and look elsewhere. Each fails loudly rather than
passing vacuously — the failure mode of the first version of `check_terminology.py`, which
hardcoded an absolute path and read zero files while reporting green.

| check | guards |
|---|---|
| `check_report_claims.py` | 17 headline numbers against the committed runs |
| `check_model_facts.py` | model sizes and licences against a dated offline capture |
| `check_links.py` | every relative link and `#anchor` |
| `check_terminology.py` | canonical `Task · Dataset` labels |
| `test_code_hashes.py` | every scoring hash moves when its code or constants move |
| `test_retrieval_scorer.py`, `test_ner_parser.py`, `test_extraction_scorer.py` | the per-item scoring conventions, in both directions |
| `self_test.py` | resume durability, fingerprint reference coverage, metric-kind verdicts, tie-correct Spearman, rescore refusing an absent reference set |

**The round-1 parser fixes changed zero recorded numbers. The round-2 ones changed
four arms in each of two experiments, and the round-1 result is exactly why that is
worth stating carefully.** After round 1 I measured that re-parsing every stored output
left `glm_l` at 46 → 46 unreadable and 0 of 760 retrieval outputs parsing differently,
and reported that the parsers were settled. They were not; the round-1 fixes were.

Round 2 found the deeper bug in both parsers — the array matcher, not the wrappers:

| | before | after |
|---|---|---|
| NER `glm_l` f1 | 0.5269 | **0.5662** (46 unreadable → 32) |
| NER `llama_l` f1 | 0.5911 | **0.5990** |
| NER `llama_m` f1 | 0.5704 | **0.5740** |
| NER `deepseek_m` f1 | 0.6122 | **0.6148** |
| SciFact `qwen_s` nDCG@10 | 0.7338 | **0.7183** |

*This table listed `llama_l` (0.7281 → 0.6864) and `llama_s` (0.7172 → 0.7129) until
2026-09-30. Both were artifacts of the round-2 fix itself: its new comma path let the
line parser accept `[8925851` and `21884449]` as document ids out of a reply that had
opened with an array and then corrected itself in prose. With the parser tightened,
both arms return to their original scores and only `qwen_s` moves. Found by external
review — the round-3 reviewers measured the like-for-like `llama_l` delta at 0.0126,
inside noise.*

The lesson I take from the pair: "I re-ran the fixed parser over the stored outputs and
nothing moved" proves the fix I just made was inert. It says nothing about whether the
parser is correct, because it only exercises the inputs the fix was aimed at. The round-2
findings came from reading what the rejected outputs actually contained.
