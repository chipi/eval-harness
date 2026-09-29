# External review — 2026-09-29

Three independent read-only reviews of the repository at commit `51e7d9d` (main), split
by area: `harness/`, `examples/`, and the written work (`research/`, `docs/`, READMEs).
Nothing in the tree was changed by the review. This file is the hand-off: every finding
is stated with its location, a failure scenario, and a suggested fix, so it can be worked
without the reviewers.

**Verdict labels.** CONFIRMED = the reviewer reproduced it (scratch copy, counterexample,
or arithmetic) or checked it against a primary source. PLAUSIBLE = read from the code or
docs but not reproduced. Two items were additionally re-checked by hand against the code
(marked ✔): harness H1 and harness M5.

**Standing caveat.** No experiment run is committed — `harness/data/runs/` holds only demo
runs. No number in the five reports or the synthesis can be recomputed from the
repository; the docs review could only check documents against each other, against
arithmetic, and against external sources. External facts were checked by web search
(huggingface.co and openrouter.ai are egress-blocked in the review container).

---

## Suggested order of work

1. Harness H1 + H2 — make per-item outputs durable and make resume score resumed items (paid data).
2. Fingerprint coverage — harness H3 (reference content), examples H3 + H4 (parser/regex hashes).
3. Examples H1 + H5 — retrieval and NER parsers; examples H2 — `METRIC_KINDS`.
4. Docs H1 + H2 — DeepSeek/Mistral facts; then docs H4 — one cost source; regenerate tables.
5. Harness M1–M4 — Nemenyi q for k>25, midrank `P(1st)`, `--asc`, `EVAL_RUNS_DIR`.
6. Harness M5 / docs M1 — make the terminology check and its self-test real.
7. Docs H3, H5, M3–M12 — tie-group wording, stale numbers, contradictions, paths.

---

## 1. Harness (`harness/`)

Statistical core verified correct: Friedman-as-permutation (monotone in χ²_F, within-item
shuffle, `(hits+1)/(B+1)`), midranks with tolerance, Nemenyi table for k ≤ 25 (max error
7×10⁻⁴), sign-flip permutation, Holm step-down, Spearman-on-midranks with NaN on
degenerate halves, paired bootstrap, `yaml.safe_load` everywhere, conservative dirty-tree
detection, `make demo` leaves the tree clean.

### HIGH

**H1 ✔. `--resume` produces a run with zero predictions and empty scores.** CONFIRMED.
`harness/scripts/experiment_run.py:270-273` — a resumed item reads the stored output and
`continue`s: no prediction row, not scored, not in `scores`/`n_items`. Repro:
`--run-id base1` → 5 rows; `--run-id resumed1 --resume base1` → `predictions.jsonl` 0 lines,
`metrics.scores == {}`, `n_items == 0`, while `outputs/` holds 5 files. The cost-cap message
(`:562-563`) prints exactly this command. Partially resumed runs report means over only
the newly paid items.
*Fix:* fall through to scoring with `Result(output=done.read_text(), ...)` (no latency/cost),
or make scoring a separate pass over `outputs`.

**H2. A non-transient failure at item k loses every paid output.** CONFIRMED.
`experiment_run.py:509-517` writes `predictions.jsonl` and `outputs/` only after `one_pass()`
returns; an exception in the loop (`:287` re-raising a permanent error, or `score()` raising)
unwinds first. Repro: adapter raising `ValueError` on item 3/5 → no run directory. The
comment at `:268-270` ("A sweep that died at item 15 of 20 resumes at 16") is false today.
*Fix:* write each output (and prediction row) as it arrives, or catch per-item errors,
record `{"item_id", "_error"}` and continue.

**H3. The fingerprint does not cover reference content.** CONFIRMED.
`harness/scripts/_fingerprint.py:198-206` records `reference_id` (a directory name) and
tier, not content; `reference_create.py --force` overwrites. Repro: demo `overlap_f1
0.415895`; edit `data/references/silver/smoke_v1/item_01.txt`; rerun → `0.327006`, identical
fingerprint hash, `validate_tree` passes, `compare_runs` prints "reference … identical".
`rescore.py:106` also scores against whatever is on disk.
*Fix:* add `reference_sha256` (digest over sorted `<item_id>:<sha256(file)>`) to `fp["data"]`;
add a V7 in `validate_tree` verifying the reference manifest.

**H4. `rescore` silently passes `source_text=None` unless files are `<item_id>.txt`.** CONFIRMED.
`harness/scripts/rescore.py:134` reads `old.get("source_path")`, which `experiment_run.py:310-321`
never writes — dead branch. Repro: `.md` dataset + 3-arg scorer: original `has_src=1.0,
src_len=56.0`; rescored `0.0, 0.0`, no warning.
*Fix:* look up `source_path` from `load_dataset(m["dataset_id"])` by `item_id`; `die` when a
scorer wants the source and none is found.

### MEDIUM

**M1. Nemenyi q falls back to the k=25 value for k>25.** CONFIRMED (fallback) / PLAUSIBLE (a pair flips).
`harness/scripts/leaderboard.py:177` `_NEMENYI_Q05.get(k, 3.658)`. Exact q₀.₀₅: k=26 3.678,
27 3.696, 28 3.715, 30 3.749 → CD understated 0.5–2.5 %. DBpedia is k=27
(`research/HANDOVER_CLASSIFICATION_DBPEDIA.md:14`), AG News k=28
(`research/HANDOVER_CLASSIFICATION_AG_NEWS.md:21`, "34 of 378 pairs").
*Fix:* compute q directly (stdlib quadrature, ~15 lines) or extend the table and `die` for
unsupported k.

**M2. Leaderboard `P(1st)`/`P(top n)` break ties alphabetically.** CONFIRMED.
`leaderboard.py:211` `sorted(arms, key=lambda x: -mu[x])` is stable. Two byte-identical
arms → `P(1st)` 1.00 vs 0.00. On saturated accuracy (DBpedia) the column measures the
alphabet — the defect `rank_stability.py` already documents and fixed.
*Fix:* midranks (reuse `rank_stability.ranks_on`); count 1st only for a unique best, or split credit.

**M3. `--asc` inverts the significance block and frontier.** CONFIRMED.
`leaderboard.py:130` ranks `reverse=True` unconditionally; `:211` sorts by `-mu`; `_frontier`
(`:254`) assumes higher is better. With `--sort latency_ms --asc` the slowest arm gets avg
rank 1.40, `P(1st)=0.77`. Friedman p and CD unaffected.
*Fix:* pass `higher_is_better = lower_is_better(sort_key) xor args.asc` into `_significance`/`_frontier`.

**M4. `pair_test.py` and `family_test.py` ignore `EVAL_RUNS_DIR`.** CONFIRMED.
`pair_test.py:80`, `family_test.py:85` default to `DATA / "runs"`, not `_common.RUNS`. The
documented `EVAL_RUNS_DIR=data/runs-rescored make …` workflow pair-tests un-rescored runs.
*Fix:* default to `RUNS`, keep `--runs-dir` as override.

**M5 ✔. `check_terminology.py` is vacuous off the author's machine.** CONFIRMED.
`harness/scripts/check_terminology.py:16` hardcodes `/Users/claude/projects/eval-harness`;
`rglob` yields nothing → success, exit 0. `self_test.py:85-92` runs it with `--help`, which
this argparse-less script ignores. (Re-pointed at the tree it passes today.) Coverage is
also narrow: only the first cell of tables headed `| experiment |`; prose, other headers
and the spelling rule (`docs/REFERENCE.md:300-306`) are unchecked.
*Fix:* `root = Path(__file__).resolve().parents[2]`; self-test runs it for real plus a negative case.

**M6. `silver_calibrate` cannot load adapters recorded relative to the harness root.** CONFIRMED.
`silver_calibrate.py:122` resolves only `ROOT.parent / spec`; runs record
`scripts/adapter.py`. `rescore.py:94-98` already does the two-base search — reuse it.

**M7. `--recursive` datasets produce `item_id`s with `/`; writers crash.** CONFIRMED.
`dataset_create.py:103` → `sub/nested`; `experiment_run.py:517` `FileNotFoundError` after
`predictions.jsonl` is written. Same assumption in `reference_create.py:142`, `rescore.py:168`,
`silver_calibrate.py:95`. Hand-edited ids with `..` or leading `/` would escape the run dir.
*Fix:* slugify at creation (`/`→`__`) and reject `..`/absolute ids, or `mkdir(parents=True)` everywhere.

**M8. `--source-dir` outside ROOT, or materialize from another CWD, fails as "changed since frozen".** CONFIRMED.
`dataset_create.py:28-37` stores the bare dir name when outside ROOT; `materialize.py:40`
resolves relative to CWD. *Fix:* resolve against ROOT; warn at creation; distinguish
"not found" from "hash drift".

**M9. Cost-cap bookkeeping.** CONFIRMED.
`capped_at` printed but not persisted (`experiment_run.py:519-549`); `EVAL_MAX_COST_USD=0`
caps before item 1 (`:277`) while dry-run/`env_check.py` say "NONE" (truthiness). Leaderboard
intersects item sets (`leaderboard.py:117`) without saying which arm shrank them.
*Fix:* persist `capped_at`/`spent_usd`; refuse cap ≤ 0; print per-arm item counts when they differ.

**M10. Two retry layers multiply attempts for the bundled adapter.** CONFIRMED.
`harness/scripts/adapter.py:82-109` `_with_retries` (substring `"500"` matching that
`_retry.py:34-36` calls wrong) runs inside `_retry.call_with_retries` (`experiment_run.py:287`).
Always-429 provider, `EVAL_MAX_RETRIES=3` → 9 calls; defaults → 64 calls, ~8 min; `latency_ms`
includes inner sleeps. *Fix:* delete `_with_retries`; time the single call.

### LOW

- **L1.** `runner.py:398` judge fallback picks the first non-`total_` score when
  `primary_metric` is unset — `cost_usd` on harness runs (dearer = better). Require it.
- **L2.** `Makefile:216` `--reason "$(REASON)"` is shell-injectable
  (`REASON='x "; echo INJECTED; echo "'`); `A`, `B`, `MATCH`, `EXCLUDE` unquoted.
- **L3.** "rescore regenerates at full precision" is false for the bundled adapter
  (`adapter.py:136` rounds to 6 dp).
- **L4.** `pair_test.py:85`, `family_test.py:93`, `holdout_significance.py:74-77` derive item
  sets from `data/sources/<id>/*.txt`, not the dataset JSON; a missing dir excludes nothing silently.
- **L5.** `experiment_run.py:530` records `params` verbatim and `:321` raw `_meta`; no
  redaction of `api_key`/`token`/credentialed `base_url`. PLAUSIBLE.
- **L6.** Tie tolerance inconsistent (1e-9 in leaderboard, exact equality in
  `rank_stability.py:106`, `silver_calibrate.py:58`); `silver_calibrate._spearman` returns 0.0
  on zero variance where `rank_stability` deliberately returns NaN. PLAUSIBLE.
- **L7.** `env_check.py` shows `EVAL_MAX_RETRIES` default 3; real default is 8.
- **L8.** `leaderboard.py:368-371` unweighted mean of per-repeat means regardless of `n_items`. PLAUSIBLE.
- **L9.** `make clean` (`Makefile:247-250`) deletes tracked files when not in a git repo. PLAUSIBLE.
- **L10.** RUNBOOK §3 / README say `dataset-materialize` re-verifies hashes; without
  `--force` it prints "nothing to do" (`materialize.py:43-45`).
- **L11.** `runner.py:342-348` `_git_sha()` runs in caller CWD, not the harness root.
- **L12.** `dataset_create.py:103` `rsplit(".",1)` on the path: `sub.dir/file` → `sub`. PLAUSIBLE.

---

## 2. Examples (`examples/`)

No finding corrupts the recorded headline numbers (rerank pipelines always emit JSON, so
`score()` is unaffected by the parser bugs as run). The HIGH items are where a plausible
output or a one-line edit changes scores without the instrument noticing.

### HIGH

**H1. `parse_ranking` destroys non-JSON lists of numeric ids (SciFact ids are numeric).** CONFIRMED.
`examples/_shared/retrieval.py:212-214` `lstrip("-*0123456789. )")` strips digits as
enumeration markers: `"4983\n13734012"`, `"1. 4983"`, `"- 4983"`, `"4983, 13734012"` → `None`.
In `retrieval-scifact/adapter.py:309-325` that falls back to BM25 order with `llm_parsed=0`.
`test_retrieval_scorer.py:79-88` uses only alphabetic ids.
*Fix:* `re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", ln)`; add numeric-id tests.

**H2. `llm_named_unknown` / `llm_parsed` not in `METRIC_KINDS` → direction error.** CONFIRMED.
Emitted at `retrieval-scifact/adapter.py:346-347`; `_shared/retrieval.py:219-236` lists
neither; `leaderboard.py:316-319` defaults to quality, so hallucinated-id count is
higher-is-better. Docstring `adapter.py:24` promises `first_stage_recall_at_k` per item; nothing records it.
*Fix:* extend `METRIC_KINDS` (`llm_parsed: quality`, `llm_named_unknown: descriptive`); add or drop the recall claim.

**H3. Fingerprint hashes miss module-level regexes the hashed functions use.** CONFIRMED.
- `_shared/classification.py:159-167` `parser_sha256` omits `_LEADIN` (`:51`) and the cleaning
  char-set; `score()` (`:458-478`) is hashed nowhere and classification exposes no `scorer_id()`
  (`rescore.py:185-190` can't record it).
- `ner-few-nerd/adapter.py:180-184` omits `_FENCE`, `_ARRAY`, `_TRAILING_COMMA`, `_BARE_KEY` (`:104-109`).
- `_shared/extraction.py:109-126` omits `_PUNCT`/`_WS` (`:75-76`).
- `retrieval-scifact/adapter.py:536-540` `_tokenizer_sha256` omits `_TOKEN` (`:130`).
*Fix:* include `.pattern` of every constant each hashed function closes over.

**H4. Retrieval's output parser is in no hash.** CONFIRMED.
`_shared/retrieval.py:85-88` hashes `normalize_id, dedupe, dcg, score_ranking`, not
`parse_ranking`, which `score()` re-runs at rescore. Fixing H1 would change rescored numbers
with every hash unchanged. *Fix:* add `parse_ranking` (accept the one-time hash change).

**H5. NER parser rejects an array followed by prose.** CONFIRMED.
`ner-few-nerd/adapter.py:126-139`: body starting `[` goes whole to `json.loads`; a trailing
sentence fails all repairs → `parsed=0`, `f1=0`. Otherwise greedy `_ARRAY = \[.*\]` (`:105`)
spans to the last `]`, so `[...] See [1].` fails. Two fenced blocks pick the first. May
explain part of the "46 unreadable items" attributed to one arm.
*Fix:* bracket-depth scan for the first balanced array; add a postscript test.

### MEDIUM

- **M1. Grade-0 qrels count as relevant for recall/MRR, not nDCG.** CONFIRMED (latent on SciFact).
  `_shared/retrieval.py:118,147-164`. *Fix:* `qrels = {d: g for d, g in qrels.items() if g > 0}`.
- **M2. Macro-F1 report uses a frozen parse; `correct` re-parses.** CONFIRMED.
  `classification_report.py:80` reads `_meta.predicted`; `rescore.py:40-50` never rewrites it.
  *Fix:* re-parse `outputs/<item>.txt` via `parse_label`, or refresh `_meta.predicted` on rescore.
- **M3. `compare_runs.py` ignores adapter `METRIC_KINDS`.** CONFIRMED.
  `compare_runs.py:26,128` uses name-based `verdict_for` (`_common.py:226-238`); descriptive
  metrics (`compression`, `fmt_*`, `truncated`, `unknown_ids`, …) get better/worse.
  *Fix:* `classify_metrics(a["metric_kinds"] | b["metric_kinds"])`; descriptive → "changed".
- **M4. LEAD-3 fingerprint claims a hosted identity.** CONFIRMED.
  `summarization-cnn-dailymail/adapter.py:492-533` has no `lead_k` branch → `endpoint`,
  `prompt_sha256`, `id_source: alias-unresolved`. *Fix:* explicit branch with `sentences` and splitter hash.
- **M5. Retrieval `_litellm` drifted from the other adapters.** CONFIRMED.
  `retrieval-scifact/adapter.py:352-407`: `reasoning_tokens=0.0` when unreported; unpriced
  calls `cost_usd=0.0` not `None`; missing key → `""` not `SystemExit`; tokens default 0;
  no truncation heuristic; `TRANSIENT_MARKERS` (`:72-74`) duplicates core's list.
  *Fix:* lift `_litellm/_billed/_reasoning_tokens/_as_dict/_price` into `_shared/`.
- **M6. `index_built_this_run` is inside the model fingerprint.** CONFIRMED.
  `retrieval-scifact/adapter.py:588`: cache-cold vs warm runs of the same arm differ in hash;
  `compare_runs` flags a confound. *Fix:* record beside `warmup_ms`, not in the fingerprint.
- **M7. "2**rel − 1 matches pytrec_eval/BEIR" is likely wrong.** PLAUSIBLE.
  `_shared/retrieval.py:44-48`, METHOD.md. trec_eval `ndcg_cut` uses linear gain. Identical on
  binary SciFact. Verify against `m_ndcg_cut.c`; at minimum reword.
- **M8. `score()` takes the corpus for `unknown_ids` from `EVAL_CORPUS_ID`, not the arm.** CONFIRMED.
  `retrieval-scifact/adapter.py:526` vs `params["corpus_id"]` in `call_system`.

### LOW

- **L1.** Malformed gold JSON → empty gold → `[]` prediction scores 1.0 (`_shared/extraction.py:199-202`). Raise.
- **L2.** `_COT` narration flag false-positives on ordinary prose ("First, investigators…",
  "Analysis: markets fell") (`summarization adapter.py:575-580`); README quotes "77 of 1440" from it.
- **L3.** Classification `hf_local` (`_shared/classification.py:242`) `truncation=True` without
  setting `model_max_length` — the sentinel bug summarization fixed at `:116-124`. PLAUSIBLE.
- **L4.** `tune_*.yaml` omit `reasoning: {enabled: false}` and use `max_tokens: 400` vs arms' 700.
- **L5.** `parse_ranking` on a list of objects returns `"{'id': '4983'}"` as an id (`retrieval.py:209`).
- **L6.** DBpedia `hf_zeroshot` hypotheses use CamelCase labels ("EducationalInstitution"). PLAUSIBLE.
- **L7.** Summarization README "No local model arm yet", "24 arms" (29 configs incl. `bart_*`,
  `lead3`); `experiment_run.py:163` says classification scores macro-F1 (it scores accuracy).
- **L8.** Classification fallback picks the earliest alias: "not about sports, it is business" → Sports.
- **L9.** Local ML configs pin no `revision:`; `hf_identity.resolved_revision` depends on a single-snapshot cache.

---

## 3. Written work (`research/`, `docs/`, READMEs)

### HIGH

**H1. DeepSeek-V4.1-Flash size is wrong; the hardware section rests on it.** CONFIRMED (web).
Published: 552B params, ~510 GB native (FP8 with FP4 experts). Repo says 763B / ~765 GB:
`research/REPORT_SUMMARIZATION.md:28,49`; `research/REPORT_SYNTHESIS.md:53,221,232-233,268,276`.
At 510 GB it fits a 640 GB node → "two do not fit" becomes one (GLM-4.6); 478× becomes ~320×;
"at BF16" is wrong for an FP8/FP4 checkpoint; `SYNTHESIS:255` claims sizes were read from the
safetensors index. "3.2 TB" (`:251`) is unattributed.
*Fix:* re-read the index; correct every derived figure; state checkpoint dtype.

**H2. `mistral_l` (mistral-large-2512) is open-weight Apache-2.0.** CONFIRMED (web: Mistral Large 3,
675B MoE, weights on HF). `docs/REFERENCE.md:152,162` lists it proprietary;
`REPORT_SYNTHESIS.md:40-43,172-184,332-333,337` build on 13 open / 11 proprietary and the
$14,255/$40,422 tier bills. `HANDOVER_NER_BLOCKED_ARM.md:118` shows the single-provider ⇒
closed inference was the basis. Head-to-head table unaffected. Also another >700 GB model.
*Fix:* 14/10; recompute tier bills; replace the heuristic with an explicit HF-repo check.

**H3. "ML wins by 0.0650" on AG News contradicts the repo's own Holm test.** CONFIRMED.
`REPORT_CLASSIFICATION.md:27,29,42-43`; `REPORT_SYNTHESIS.md:219,225`. `REPORT_CLASSIFICATION.md:173-176`
and `HANDOVER_CLASSIFICATION_AG_NEWS.md:43-46`: bert_mini not separated from llama_m (or gemma_s
by carry-forward). `REFERENCE.md:296` defines "separated" as the only licensed "better".
*Fix:* "ahead by 0.0650, not separated", as the SciFact row already does.

**H4. §3 tables carry price-table costs; prose and synthesis use billed costs.** CONFIRMED.
- `REPORT_SUMMARIZATION.md:225` deepseek_m 0.0296 vs `:57` $0.0381 → `README.md:89` "66×" vs report/examples "52×".
- `REPORT_CLASSIFICATION.md:186-188` vs `:62-63,210` → DBpedia ratio printed as 115×, 116× (`SYNTHESIS:680`), 126× (`REPORT_CLASSIFICATION:334`, `README.md:93`, `examples/classification-dbpedia-14/README.md:84`).
- `REPORT_CLASSIFICATION.md:153` AG anthropic_m 0.1054 vs `SYNTHESIS:161,604,637` "$351/mo" (⇒ 0.0702).
- `REPORT_NER.md:222-232` family block `gemma_m $0.0057`, `anthropic_m $0.4269`, `gemma_l $0.0080` vs table `:178-180`; `:420` stale.
- `REPORT_RETRIEVAL.md:156-176` table price-table while `:5,:7` say billed; `:178-179` cites the 2.4× multiplier that §7 (`:369-375`) retracts.
- The "Correction … figures below are corrected" appendix sits at the end with nothing below (`:576`, `:421`, `:582`).
*Fix:* regenerate §3 tables from `_meta.usage.cost`; one number per ratio; fix the appendix wording.

**H5. Superseded summarisation rank-stability numbers survive.** CONFIRMED.
§3.6 (`REPORT_SUMMARIZATION.md:363-375`, 26 arms): ρ 0.416 @20, 0.799 @100, P(same winner) 0.14/0.01.
Old 24-arm figures (ρ 0.753 / 0.346, 58 %/15 %) remain at `:87-91,432,465` and `README.md:90-91`.
*Fix:* propagate, or state both with the arm count.

### MEDIUM

- **M1.** Terminology check vacuous (= harness M5) and narrow in coverage.
- **M2.** Hardware arithmetic: `gemma_s` "55 GB" offered under the 85 %-of-64 GB = 54.4 GB rule
  (`REPORT_CLASSIFICATION.md:29`); GLM-4.5-Air is 106B not 110B (`REPORT_RETRIEVAL:29`) → int4 ≈ 53 GB
  qualifies, flipping "only SciFact loses anything at 64 GB" (`SYNTHESIS:271-273`, `REPORT_RETRIEVAL:31,56-59`);
  Llama-70B int4 "~35 GB" ignores scales/embeddings (real 37–43 GB); no context length stated for
  the KV budget. *Fix:* state context + KV formula once, apply the rule uniformly, show margins.
- **M3.** "costs 0.0078 on one task and nothing on the other four" (`SYNTHESIS:53-54,276-277`) —
  SciFact loses 0.0074 on its own table (`:267`).
- **M4.** Orderings inside tied groups in the deployment tables (`SYNTHESIS:262-268`: DBpedia
  0.9857 = 0.9857 broken for GLM; AG Llama vs gemma_s; SciFact GLM-Air vs Gemma). "every fine-tuned
  model ranked first (3 of 3)" (`:35,142,147`) counts bart_l +0.0001 at p=0.99. *Fix:* "first or tied-first".
- **M5.** Tier bills $14,255 / $40,422 have no provenance (`SYNTHESIS:42-43,323-324,332-333`) and sum
  bills nobody pays. Drop or define and add to the reproduction block.
- **M6.** Latency ratios use 10 ms while bert_mini is stated as 7 ms (`SYNTHESIS:164,665-666,697,702-703,739`
  vs `REPORT_CLASSIFICATION:180` 270×).
- **M7.** `REPORT_NER.md`: `:62-64` "19 of 26 … the eight" (26−19 = 7; block lists 7); `:410-411` "~7 %
  of 0.0876" vs "38 % of 0.0810" (`:34,82,323-324`); `:521` "26 spans" vs "34 of 768".
- **M8.** `REPORT_RETRIEVAL.md`: `:3` "234 judgments" vs `:96` sum 227; `:33,:295` "11 of 12 within 4
  points of the cap 0.8163" (they are 7–11 below); `:5` "$1.94 billed" vs "$2.45" elsewhere;
  `HANDOVER_RETRIEVAL_FRONTIER_ARMS.md:21` $31.40 uses the retracted 2.41× multiplier (quoted in
  `examples/README:147`, `SYNTHESIS:775`, `REPORT_RETRIEVAL:362`).
- **M9.** Tie-group sizes disagree: AG "tied with 5" / "top six" / "9 of 26" / "group of 9";
  DBpedia "18 of 25" (family is 26); Few-NERD "8 hosted arms" vs "0 arms". Define once.
- **M10.** Stale example READMEs: summarization README is the n=20 study with no banner, says
  "No local model arm yet", refers to `../eval-harness`; AG README "~$0.022 upper bound" (~8× low);
  NER README `$2.05`, `openai_m $0.2034`, `121×` (report: $2.57, $0.6507, 78×); DBpedia README
  `$1.25`, `126×`, points to a handover; SciFact README "$2.45 enforced".
- **M11.** Broken commands: `REPORT_SUMMARIZATION.md:531,535` and summarization README `:714-715,735`,
  `HANDOVER.md:70-72` use `../eval-harness` and wrong config paths; `RUNBOOK.md:348,415` `make promote`
  (target is `run-promote`); `INTEGRATION.md:20,158`, `harness/README.md:447` `cp -r eval-harness`;
  `REPORT_SUMMARIZATION.md:399` "§3.2" should be §3.1.
- **M12.** "Three of those four are under 2 GB" (`SYNTHESIS:293-300`) — all four are.

### LOW

- **L1.** `docs/papers/README.md:9` anchor `#why-nothing-is-committed` does not exist (only broken anchor in 45 files).
- **L2.** Arm-count denominators drift in SYNTHESIS ("16 of 25", "1 of 25" vs "1 of 26", "9 of 17" vs "18 of 18").
- **L3.** `SYNTHESIS:591-592` "a 91× step buys about 11 points of F1" ≈ 8 points (11 is relative %).
- **L4.** `SYNTHESIS:348-350` "glm_m at the 70th percentile" — no computation anywhere.
- **L5.** Latency used as a deployment input despite §2's "machine-bound, not a model property" caveat.
- **L6.** Gemma licences differ within the family (gemma_s gated, others Apache-2.0) — add a note.
- **L7.** `SYNTHESIS:790` "prices snapshot 2026-09-28/29" — summarisation ran 2026-09-26.
- **L8.** RUNBOOK never mentions `leaderboard`, `family-test`, `pair-test`, `rescore`.
- **L9.** `HANDOVER.md:9-21` describes the pre-move layout with no "superseded" banner.

### External claims checked and correct

CVE-2025-32434 ↔ GHSA-53q9-r3pm-6pq6; no Intel-Mac torch wheel above 2.2.2; BEIR BM25
SciFact nDCG@10 0.665; GLM-4.5-Air MIT; GLM-4.6 ~355B MIT; Gemma-4-26B-A4B Apache-2.0;
Llama-3.3-70B 70.6B ≈ 141 GB BF16; dataset licences. Arithmetic that passes: 127 arms,
$12.01 total, 56 NOTES entries, 3,205×/109×/1/14 size ratios, $9,826 and $191/mo,
0.0074/0.0078 deltas, 0.786–0.797 prediction bounds, 171/276/351/378 pair counts.
