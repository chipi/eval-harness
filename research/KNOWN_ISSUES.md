# Known issues — read before reviewing

Everything here is **open and known**. Re-finding it costs a reviewer time that would be
better spent on what is not on this list. Fixes are in the git log, not here.

Last updated 2026-09-30, after **round 4**, which reviewed the six local ML arms.

## What running the six local ML arms found (2026-09-30)

The six checkpoints that needed torch ≥ 2.6 ran on Linux (results in the classification
and summarisation reports; journal entry 59). Running them surfaced four things about the
instrument and one about the block itself; re-timing and re-checking them surfaced two more about latency and one about precision.

| finding | status |
|---|---|
| **The lock did not deliver torch ≥ 2.6 on Linux.** `torch>=2.2` off Intel Mac let uv's universal resolver settle on one torch for every platform, and in four of five examples it chose 2.2.2 — the version that blocks these checkpoints. Only summarisation's lock had forked to 2.14, by chance. `RUN_THE_BLOCKED_ML_ARMS.md` said "the lock resolves 2.14 on Linux", true for 3 of the 6 arms | **Fixed** (`4068ea23`): `torch>=2.6` off Intel Mac in all five examples; Intel Mac still 2.2.2, every other platform 2.14.0. Only torch and its own dependency tree moved — triton 2.2.0 → 3.8.0, the CUDA stack cu12 → cu13 (~30 packages), setuptools added; `transformers`, `numpy` and every non-torch package unchanged. (This row first said "no other package moved", which the lock diff contradicts.) |
| **Every run after the first on a machine is recorded `dirty: true`.** Earlier run directories under `data/runs/` are untracked files, and `build_info` treats any `git status --porcelain` output as dirt — so "commit before you run" really means "commit after every run". The code was byte-identical to the recorded commit | **Open.** Workaround used: `EVAL_RUNS_DIR` outside the git tree, then copy the finished runs in. The fix is to ignore untracked files under `data/runs*/` in the dirty check |
| **Resume dropped the adapter's own metrics.** `Result.extra` — `input_truncated`, `truncated`, `reasoning_tokens` — was not carried onto replayed rows, and the aggregate averages only rows that carry a key, so a resumed `bart_s` reported `input_truncated` 0.75 (3 of the 4 fresh items) against a true 0.23. The demo adapter emits no `extra`, which is why every resume test passed | **Fixed**, with a fixture-adapter test that fails when the fix is reverted. The affected run is kept only as a repeat (`data/runs-repeats/`) |
| **Fingerprints record `revision: null` and no `weight_files` for 5 of the 6.** `transformers` loaded `main`'s pickle and fetched the Hub's safetensors conversion PR in the background, so the cache holds two snapshots and `hf_identity.resolved_revision` refuses to pick one | **Open.** The `main` commits each run loaded are in [`docs/REFERENCE.md`](../docs/REFERENCE.md), read from the cache. The durable fix is `revision:` pinned in every local config — round 1's L9 |
| **The block was avoidable — for five of the six.** Every one has a safetensors conversion PR on the Hub (`refs/pr/1`, `/2`, `/9`, `/29`). On torch 2.2.2+cpu, through each arm's own adapter (`docs/evidence/conversion_pr_check.py`): loading `main` fails with the CVE refusal for all six; the PR reproduces the recorded outputs byte for byte for the three BERTs on every item and for `bart_m` and `bart_l_xsum` on 20 of 20. **`bart_s` fails**: its PR is fp16 and torch 2.2.2 has no fp16 LayerNorm on CPU; cast to fp32 it matches 19 of 20, a different computation. This row first said all six, from 40 items of one model | **Open by decision.** The configs were not changed, so the committed runs stay identifiable as runs of `main`'s pickle. A future config version can pin the PR |
| **The published pilot ρ for AG News (0.852) and DBpedia (0.728) cannot be re-derived from committed data.** They came from dev-slice runs that were never committed. Ranking the dev items inside the committed full runs gives 0.677 and 0.757, with a 10- to 13-way tie at the top of the dev slice | **Open.** Stated in both reports; the "pilot picked the wrong winner" finding rests on the committed runs and stands |
| **The latency column spans two machines, and one figure was contaminated.** `bart_l`, `lead3`, `bert_mini` and every hosted arm were timed on a 12-core Intel Mac; the six new arms on a 4-core Linux container, which runs `bart_l` 1.7× *faster* (6.3 s against 10.7 s median). The reports first compared the two directly ("half the latency", "distillations take 4.5–5.1 s" against 11.0 s). The recorded `bart_s` mean, 4,484 ms, was also slowed by analysis I ran on the same CPU mid-run (its idle median is 3,387 ms) | **Fixed in the reports.** All nine local arms were re-timed on the Linux machine alone, idle, one at a time (`harness/data/runs-linux/`); every local-vs-local claim now uses that table, and local-vs-hosted ratios that cross machines are labelled as such. The recorded runs are unchanged |
| **`precision` is a label, not a setting — and for `bart_s` it is wrong.** Every local config declares `precision: fp32`, and the fingerprint records it, but no adapter passes it to `from_pretrained`/`pipeline`, so each model runs in its stored dtype. That is fp32 for seven of the eight model-backed local arms of summarisation and classification (NER and retrieval not checked); `distilbart-cnn-6-6` is stored at fp16 and **ran at fp16** (measured on torch 2.14: `next(model.parameters()).dtype`). Its quality and latency are fp16 figures under an fp32 label. An earlier note said it "was upcast to fp32 at load", which was never measured | **Open.** The runs stand as what they are; the reports now say fp16. The fix is to apply `precision` as `torch_dtype` in the local adapters (or record the loaded dtype), which changes what `bart_s` computes, so it needs a new config version |
| **Local-arm means include a first-call cost the warm-up does not absorb.** `warmup()` loads the model but runs no forward pass, so items 1–3 pay lazy initialisation — up to **24 s on one item** in the two `bert_base_fy` re-runs, which lifts their means from ~60 ms to 166–202 ms. The `latency_ms` column is a mean; `docs/REFERENCE.md` says it excludes warm-up, which is true of the model load only | **Open.** The same-machine table uses the median. The fix is one untimed forward pass in each local adapter's `warmup()` — a change to the instrument, so it waits for a config version |
| `check_report_claims.py`'s Pareto check found hosted summarisation arms by excluding two names (`bart_l`, `lead3`); three more local arms would have been counted as hosted | **Fixed**: hosted = the run's recorded `provider` is `litellm` |

## What round 4 says about round 3

Round 4 reviewed the merged ML-arm work and the three rounds of fixes underneath it. It
found **3 high, 5 medium, 5 low, and overturned one of round 3's own rulings.** All are
closed; what follows is only the part a reviewer still needs.

Two findings are worth carrying forward as a pattern, because they are the same pattern
every round has found:

- **A check that cannot fail.** R4-H1: the cost check skipped every arm whose recorded
  cost already equalled its bill, on a comment that said "the table happens to be right"
  — a statement about the *run*, never about the number in the report. Every arm measured
  after the 2026-09-29 adapter fix was unchecked. R4-M1: the guard that exists to prove
  checks can fail *skipped silently* when its anchor drifted, and exercised one defect
  class per checker when the claims checker has five. Both were found by mutation, not
  by reading.

- **A correction that reaches the report and not the thing that generates it.** R4-M5:
  `reparse.py`'s docstring still told the retracted three-arms story that its own fix
  disproved. Fourth occurrence across four rounds.

**I overturned round 3's ruling 2 wrongly, and that is on me.** Round 3 said Few-NERD's
annotation share was 38%, not ~7%. I recorded it in `REPORT_NER.md` as a disagreement and
wrote that I "could not reproduce 38% from any pairing of the committed numbers" — while
lines 34, 82 and 323 of that same file said 38% and always had. Round 3 was pointing at
an internal inconsistency in one document; I read it as an outside claim and disputed my
own number. The arithmetic: the lead over `openai_m` is 0.0810 and falls to 0.0503 under
the annotation bound, so 1 − 0.0503/0.0810 = 37.9%. The "~7%" divided `span_marker`'s own
0.0060 gain by the margin, which is the wrong quantity — a margin moves by the
*difference* between two arms' gains, and `openai_m` gains 0.0365. §4 now states 38% with
both components shown and the disputing paragraph deleted.

## What round 3 says about round 2

Round 2's 32 findings were all addressed. Round 3 — four reviewers, fresh clones, Linux
— found **`make ci` RED on their machines and green on mine**, plus 9 high, ~20 medium
and ~15 low findings. The pattern from round 2 held and sharpened:

| what round 2 was told | what round 3 found |
|---|---|
| `make ci` is green in a fresh clone | green on APFS, **red on ext4**. Five glob sites picked among duplicate `config_id`s by filesystem order, and the failure was real: two cost cells were genuinely stale. I had verified on one OS and reported it as verified |
| the checks can now fail | the guard covered 3 of 9 checkers, only their missing-input path, and `check_report_claims` never reached its own guard there — it died on `FileNotFoundError` and exited 1 for an unrelated reason. A checker printing FAIL and exiting 0 passed all of it |
| the cost correction is applied | 21 more stale cells, in fenced **code blocks** that both scanners skipped. The AG column summed to $0.49 under a header saying $0.58 |
| the retrieval parser is fixed | my fix **created** the worst number in the example. Its new comma path accepted `[8925851` as a document id, and the harvested ranking scored below the BM25 fallback. Two of the three arms I "corrected" were unchanged all along |
| the NER parser hash covers the parser | it covered a regex my own fix had made dead. Gutting the real function left the digest byte-identical |
| resume keeps what was measured | true for a tidy re-run; false for a crash, which is the only case resume is for. A crashed run has no `predictions.jsonl`, so every replayed row came back `latency: None, cost: None` |
| Nemenyi above k=25 is a deliberate gap | about thirty lines of stdlib. Now computed, validated against all 24 published values, and all five experiments have a CD line |

**Three findings I disputed and was right about** (the retrieval sub-conclusion does not
reverse; the tie is 12–13 arms not 11; Few-NERD's +5.9% is correct) — all three because
round 3 measured them on runs carrying **my** parser bug. **One I disputed and lost**:
NER's 21st recoverable item is real, and `_balanced_arrays` stopping at the first
unclosed `[` is why I found only 20.

**The lesson that keeps recurring, stated for round 4:** every round, a fix of mine has
recreated the class of bug it fixed — a checker validating its own constants, a hash
that stops covering refactored code, a correction applied where it was found and
nowhere else. Assume this round's fixes did it again, and start by asking what it would
take for a green check to be red.

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
| ~~**6 local ML checkpoints** never ran~~ | **Ran 2026-09-30.** DBpedia's fine-tune ties the top group (not above it); AG News gained two fine-tunes that took 1st and 2nd; the XSum control finished last of 29 | pickle checkpoints needed torch ≥ 2.6, run on Linux. See the section at the top of this file |
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

## What the automated checks do NOT cover

`make ci` verifies 33 report claims, 37 model facts, every arm row in every leaderboard
table and code block, every relative link and anchor, and that each checker still fails
on the defect it exists to catch. The gaps below are known and are the ones a reviewer
should spend time on.

- **Numbers in PROSE are only NARROWLY checked.** The arm-row checker reads markdown
  table rows and fenced code blocks; a figure inside a sentence was invisible to it, and
  that is how several stale numbers survived three review rounds.

  A narrow slice is now covered: a 4-decimal number that follows an arm name
  *immediately*, through one of four connectives — `` `span_marker` scored 0.7674 ``,
  `(0.7674)`, `at 0.7674`, `— 0.7674`. Measured over all four reports: **5 true, 0
  false**.

  The **general** case is still open, and the reason is measured too. The obvious rule
  (any 4-decimal number within 60 characters of an arm name on the same line) produces
  **21 false positives on the current, correct repo**: `anthropic_l shows 0.6897` is that
  arm's *cost* beside its name, `openai_m shows 0.4693` a different statistic entirely. A
  check that cries wolf on correct text gets muted, and this repo learned that the
  expensive way. So a figure that names its arm three words earlier, or sits in a
  sentence that mentions two arms, is still unchecked. Covering prose properly means the
  reports interpolating from a structured figures block rather than restating numbers — a
  real change, not a tightening.

- **Exec summaries, READMEs, handovers and KNOWN_ISSUES itself** are outside the
  arm-row scan entirely; only the four experiment reports are in it. This file's own
  numbers are checked by nothing.

- **Deleting evidence is now caught, at the level of a file.** V9 fails when any run file
  git tracks is absent from disk, and when `runs-reparsed`, `runs-rescored`, `runs-pair`
  or `runs-repeats` falls below its floor. Verified by reproducing round 4's own
  mutation: `rm -rf data/runs/sf_mpnet_*` now reports 202 missing files where it
  previously left `make ci` green.

  What V9 does **not** catch: a run deleted from disk *and* from the index in one commit,
  and a floor lowered in the same change that empties a directory. Both are visible in a
  diff and neither is caught by a check.

- **Scorer drift is now caught for DERIVED runs only.** V10 imports each scorer and
  compares its hash to what every run in `runs-reparsed` and `runs-rescored` claims —
  those two directories exist to be re-derivable, so a run there naming a scorer that is
  not in the tree is a failure. Verified by mutating `_ARTICLES` in `extraction.py` (27
  of 27 rescored runs go red) and `_ID_TOKEN` in `retrieval.py` (19 of 19 reparsed).

  For `data/runs` it is a **note, never a gate** — a measurement run legitimately carries
  the hash it was measured with, and all 27 NER runs predate the current parser. What V10
  does not cover: classification and summarisation record no comparable scorer hash, so
  only the NER and retrieval scorers are watched; and it compares hashes, which tells you
  the code moved, not whether the stored numbers would change.

---

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
