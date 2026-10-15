# Candidate next experiments

*A research note for planning, not a result: what new experiments would add a genuinely different angle (answer shape, metric family, harness capability), each with a cleanly licensed dataset, CPU-runnable local models and a published calibration number. Researched 2026-10-15; licences, model ids and sizes were checked on the source pages that day and should be re-checked before building.*


*I checked every licence, model id and size against the HF Hub API or the source page on that date. The prices behind the cost estimates come from OpenRouter's live `/api/v1/models` for the 23 hosted arms in `examples/models.json` that are still listed. `qwen/qwen3-max` is no longer listed, so I estimated its price.*

## What the existing five leave open

The repository names its own gaps. `research/REPORT_SYNTHESIS.md` (around lines 1022–1045) lists them:
- "all English, all text": nothing multilingual, multimodal, long-context, agentic or generative-quality;
- "Nothing here measures factual accuracy, safety, or instruction-following";
- run-to-run variance is unmeasured for hosted arms;
- every fine-tune was tested on its own training distribution.

`docs/REFERENCE.md` adds two more. Hosted arms never supply `confidence`, because logprobs were never requested. Macro-F1-style corpus metrics need the bootstrap, which is documented as anti-conservative.

Three harness facts drive the cost estimates below:
- **Price of running every hosted arm.** Summed over the 23 listed arms, the price is about **$22.4 per million input tokens and $108 per million output tokens** (Opus 5 $5/$25, GPT-5.5 $5/$30). So 200 items cost about `200 × (T_in×22.4 + T_out×108) / 1e6` dollars. Output tokens dominate, and the expensive output prices make generative tasks 5–10× dearer than labelling tasks.
- **Image input.** 18 of the 24 arms accept images. The six that do not are deepseek-v4-flash, deepseek-v4-pro, the three GLM arms and llama-3.3-70b.
- **Audio input.** None of the 24 accepts audio.
- **Logprobs.** 12 of the 23 accept the `logprobs` parameter: all DeepSeek, Gemma, Llama and Qwen arms, plus glm-5 and mistral-small. None of the Anthropic or OpenAI arms do. That split is itself an own-vs-rent finding.

---

## Candidates

### 1. Summary-quality judging: SummEval meta-evaluation ("can a model judge like an expert?")

1. **What's new.** The model rates *other systems'* outputs, and the gold is a continuous human judgement. That gives a **new metric family: rank correlation (Kendall τ / Spearman)**.
   - **It stays per-item.** At summary level, each item is one article. The model scores the 16 system summaries of that article, and the item's score is τ between those scores and the expert means. The existing sign-flip permutation test and Holm still apply unchanged. That avoids the corpus-level-metric problem STS-B would have (see "Rejected").
   - **It answers questions the harness already asks.** Is an LLM-as-judge trustworthy? That is the agent-trust question and `make silver-calibrate`. Is ROUGE any good? That question is about the harness's own summarisation `coverage` metric.
2. **Dataset.** SummEval: 100 CNN/DM test articles, 16 systems, 1,600 summaries. Each summary was rated by 3 experts and 5 crowd workers on coherence, consistency, fluency and relevance.
   - **Source.** HF [`mteb/summeval`](https://huggingface.co/datasets/mteb/summeval) (100 rows, test only), licensed **MIT**. The original repo [Yale-LILY/SummEval](https://github.com/Yale-LILY/SummEval) is MIT, and the repo states no separate licence for the annotations.
   - **Source articles.** These are CNN/DM, which the harness already uses ([abisee/cnn_dailymail](https://huggingface.co/datasets/abisee/cnn_dailymail), Apache-2.0).
   - **Gold quality.** Use expert means. Crowd ratings are known to be noisier.
3. **Free local models.** I found no fine-tune on SummEval itself; the evaluators below are its natural competitors.
   - **UniEval** [`MingZhong/unieval-sum`](https://huggingface.co/MingZhong/unieval-sum): a T5 evaluator trained for exactly these four dimensions. The HF card states no licence; the [GitHub repo](https://github.com/maszhongming/UniEval) is MIT. The checkpoint is about 3 GB `pytorch_model.bin` (a pickle, which this repo has had trouble loading before). CPU is fine.
   - **BARTScore**, using `facebook/bart-large-cnn`, which the harness already runs as `bart_l`.
   - **BERTScore** with roberta-large.
   - **Non-model baselines:** ROUGE-1/2/L and the harness's own `coverage`.
4. **Calibration row.** G-Eval ([Liu et al. 2023, Table 1](https://arxiv.org/abs/2303.16634)) reports summary-level average Spearman for ROUGE-1 **0.192** (τ 0.150), BERTScore 0.225, UniEval **0.474**, G-Eval-4 0.514. Reproducing ROUGE-1 = 0.192 costs $0 and uses all 100 articles, so it is a perfect calibration row. UniEval 0.474 makes a second, local one.
5. **Metric subtleties.**
   - LLMs give integer 1–5 scores with many ties, so use τ-b and report the tie rate.
   - Decide whether all 16 summaries go into one prompt (cheaper, and lets the model compare them) or one summary per call (independent scores). These are different systems and should be separate arms.
   - G-Eval's probability-weighted score needs logprobs, which only 12 arms support.
   - Score one dimension per run (consistency is the most useful, since it is the factuality proxy) or all four.
6. **Cost.** With all 16 summaries in one call: about 2,100 tokens in and about 250 out per article. 100 × (2100×22.4 + 250×108)/1e6 ≈ **$7** for all 24 arms and four dimensions, or about $3 for consistency alone. One summary per call costs about $40. All local scoring runs on CPU in minutes.
7. **Risks.**
   - SummEval is famous, so the annotation file may be in training data. Memorising per-summary scores is unlikely, but say so.
   - n = 100 items, which is under the usual 200.
   - The 16 systems are 2019-era, so it measures judging old-style summaries. The 24 arms' own summaries from the existing experiment can't be used, because they have no human ratings.

### 2. Speech-to-text: Earnings-22 (plus AMI) — Whisper on CPU vs hosted audio LLMs

1. **What's new.**
   - **New modality:** binary audio items. The fingerprint has to hash audio bytes, which is the "corpus is not the items" lesson again.
   - **New metric family:** WER. It is an edit distance, and pooled corpus WER differs from mean per-utterance WER.
   - **A different hosted field.** None of the 24 arms takes audio. The audio-capable models on OpenRouter are Gemini 2.5/3.x flash and pro, `openai/gpt-audio` and `gpt-audio-mini`, `mistralai/voxtral-small-24b-2507`, `qwen/qwen3.8-omni-flash` and Xiaomi MiMo. That is about 8–10 arms, which breaks the 8 vendors × 3 tiers design.
   - **The sharpest own-vs-rent case.** Whisper is open, small and very good. It also fits the author's podcast product directly.
2. **Dataset.**
   - **Earnings-22:** 119 h of English earnings calls with accents from 27 countries, heavy on numbers and named entities. Licence **CC BY-SA 4.0**: [revdotcom/speech-datasets](https://github.com/revdotcom/speech-datasets/tree/main/earnings22) and the [ESB test-only card](https://huggingface.co/datasets/hf-audio/esb-datasets-test-only-sorted). Use the ESB test subset (about 5 h of segmented audio). [`distil-whisper/earnings22`](https://huggingface.co/datasets/distil-whisper/earnings22) states no licence on HF, so take the ESB copy.
   - **AMI meetings** as a second slice. Licence CC-BY-4.0: [edinburghcstr/ami](https://huggingface.co/datasets/edinburghcstr/ami), 12,643 IHM test rows.
   - **Avoid:** TED-LIUM (**CC-BY-NC-ND 3.0**) and SPGISpeech (Kensho user agreement), per the [ESB card](https://huggingface.co/datasets/hf-audio/esb-datasets-test-only-sorted).
   - **Gold quality:** professional transcripts. Earnings-22 has some formatting conventions (numbers, disfluencies).
3. **Free local models.** All need no GPU.

   | model | licence | size |
   |---|---|---|
   | [`openai/whisper-base.en`](https://huggingface.co/openai/whisper-base.en) | Apache-2.0 | 73M |
   | [`openai/whisper-small`](https://huggingface.co/openai/whisper-small) | Apache-2.0 | 244M, 967 MB |
   | [`distil-whisper/distil-small.en`](https://huggingface.co/distil-whisper/distil-small.en) | MIT | 332 MB |
   | [`moonshine-ai/moonshine-base`](https://huggingface.co/moonshine-ai/moonshine-base) | MIT | 61.5M, 246 MB |

   `faster-whisper` int8 is the practical CPU runtime. None of these is fine-tuned on Earnings-22, so this is a zero-shot vs zero-shot comparison, which is honest. A Whisper fine-tuned on Earnings-22 would be the fine-tune arm if one is found.
4. **Calibration row.** On the Open ASR / ESB Earnings-22 test, **Whisper base.en WER 15.09** and Moonshine Base 17.65; on AMI, 21.13 and 17.79. Source: [Moonshine paper, Table 2](https://arxiv.org/abs/2410.15608). The [Open ASR Leaderboard paper](https://arxiv.org/abs/2510.06961) and [repo](https://github.com/huggingface/open_asr_leaderboard) give the normaliser and evaluation code. Running base.en over the full 5 h on a laptop CPU takes well under an hour.
5. **Metric subtleties.**
   - Normalisation dominates. Use Whisper's `EnglishTextNormalizer`, as the Open ASR Leaderboard does; whether "$5" or "five dollars" counts as an error decides the ranking on earnings calls.
   - Store per-item `errors` and `ref_words` so that corpus WER can be pooled, the same way the NER experiment pools tp/fp/fn.
   - WER can exceed 1: Moonshine reports >100% on very short clips from repeated tokens. Cap it, or report it raw and say which.
   - Hosted chat-audio models may "clean up" disfluencies, summarise or refuse. That is a failure mode worth reporting, the same way the label parser was.
6. **Cost.** Use 200 segments of about 7 s. Gemini bills about 32 tokens per second of audio, so about 45k audio tokens per model: cents. `gpt-audio` bills audio at $32/M, so about $1.50. All arms together come to **under $5**. CPU: whisper-small at about 0.3× real time handles 25 min of audio in about 10 min.
7. **Risks.**
   - Whisper's 680k-hour web training set may contain public earnings calls, which is contamination on the local side.
   - The hosted set is about 10 arms and 3 vendors, not 24, so the price-vs-quality findings are weaker.
   - Audio has to be sent base64 through OpenRouter, so `_shared/gateway.py` needs a new code path.
   - Podcasts are long-form, but this test is short-form segments. The [long-form Earnings-22 track](https://huggingface.co/datasets/distil-whisper/earnings22) (125 full calls) is the follow-up. There, the chunking strategy becomes part of the system.

### 3. Code generation scored by execution: MBPP+ (EvalPlus)

1. **What's new.**
   - **Correctness by running tests:** pass@1, scored 0/1 per item. It is a new metric *source* rather than a new shape.
   - **Sandboxed execution of untrusted model output.** This is a new harness capability, and it needs a new refusal: never execute outside the sandbox.
   - **A referee that is not an annotator.** Every existing experiment ended up adjudicating disputed gold. With execution the referee is a test suite. The EvalPlus story itself shows tests are imperfect, but they can be audited, which disputed labels can't.
   - **The most likely place for the "$0 answer in every experiment" claim to fail.** That makes it a deliberately falsifying test.
2. **Dataset.**
   - **MBPP+:** [`evalplus/mbppplus`](https://huggingface.co/datasets/evalplus/mbppplus), **378** test tasks, **Apache-2.0**. EvalPlus removed broken MBPP tasks and added stronger tests.
   - **HumanEval+:** [`evalplus/humanevalplus`](https://huggingface.co/datasets/evalplus/humanevalplus), 164 tasks, Apache-2.0. Too few on its own.
   - **Fallback with less contamination:** [`bigcode/bigcodebench-hard`](https://huggingface.co/datasets/bigcode/bigcodebench-hard), 148 tasks. **The HF card states no licence** (flag), and the sandbox needs many third-party libraries.
3. **Free local models.**
   - [`Qwen/Qwen2.5-Coder-1.5B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct): Apache-2.0, 1.54B params, about 3 GB in bf16, about 1 GB as Q4 GGUF from [`Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF`](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF).
   - The 0.5B and 7B versions are the same family. 7B at Q4 is about 4.7 GB and slow but feasible on a 64 GB CPU.
   - No model is fine-tuned on MBPP itself, but code-instruct tuning is the "task-specific training" analogue.
   - **Baseline:** the canonical solution must score 100%, which is a sandbox self-test. An empty-function baseline should score 0%.
4. **Calibration row.** [Qwen2.5-Coder tech report](https://arxiv.org/abs/2409.12186) (EvalPlus):
   - **Qwen2.5-Coder-1.5B-Instruct: MBPP+ 59.4, HumanEval+ 66.5**;
   - 0.5B: 43.7 / 57.3;
   - 7B: 71.7 / 84.1.

   The full 378-task MBPP+ set runs locally for $0.
5. **Metric subtleties.**
   - **Sandbox:** no network, CPU and memory limits, per-test timeout, and a fresh process per item. EvalPlus ships its own harness; run it in a container.
   - **Timeouts on a slow CPU** can turn correct code into failures, so record `timeout` separately from `fail`.
   - **Extracting code from chat output** is the new label parser. Given the parser findings in the classification experiment, expect it to move arms by points.
   - **Report base and plus tests separately.** The gap between them measures how weak the tests are.
   - **Temperature 0 gives pass@1.** Pass@k would need k samples per arm and k× the cost, and it is the natural place to finally measure run-to-run variance.
6. **Cost.** About 200 tokens in and about 250 out (code), so 200 items cost **about $6** for 24 arms. Reasoning models may emit hidden tokens. Record `reasoning_tokens` as the harness already does, and budget 2–3×. Local 1.5B Q4 on CPU runs at about 20–40 tok/s, so 378 tasks take about an hour.
7. **Risks.**
   - **Contamination is near-certain** for MBPP and HumanEval in every 2024+ model, and frontier models sit near MBPP+'s ceiling of about 80%. Expect a saturated, DBpedia-like top.
   - Building and securing the sandbox is real engineering effort.
   - Licence is clean.

### 4. Document-to-JSON extraction: CORD v2 receipts (image or OCR text → nested schema)

1. **What's new.**
   - **Answer shape:** a **nested JSON object** with lists of line items. Scoring checks schema validity, field-level F1 and tree-edit-distance accuracy.
   - **First image-input task.** 18 of 24 arms take images. The six text-only arms can get the OCR words that ship with the data, which makes for a clean "image vs OCR-text" pair of arms.
   - **The commonest real enterprise LLM job** (invoices, receipts, forms).
   - **A fine-tune vs LLM case with a famous fine-tune.**
   - `structured_outputs` is supported by 22 of 23 arms, so "JSON mode on vs off" is a natural one-variable comparison.
2. **Dataset.** [`naver-clova-ix/cord-v2`](https://huggingface.co/datasets/naver-clova-ix/cord-v2), **CC-BY-4.0**, splits 800/100/100.
   - **Test is only 100 receipts.** Use test + validation (200), since neither is used in training, or accept n = 100.
   - Ground truth is `gt_parse` JSON plus word-level OCR in `valid_line`.
   - Indonesian receipts, so mildly multilingual.
3. **Free local models.**
   - **Fine-tune:** [`naver-clova-ix/donut-base-finetuned-cord-v2`](https://huggingface.co/naver-clova-ix/donut-base-finetuned-cord-v2), **MIT**, about 800 MB, 143M params (Swin + BART). It reads the image directly on CPU.
   - **Pipeline baseline:** Tesseract OCR plus regex for `total`.
   - **Small-local-VLM arm (optional):** e.g. Qwen2.5-VL-3B. Not verified here.
4. **Calibration row.** The [Donut paper (ECCV 2022), Table 2](https://arxiv.org/abs/2111.15664) reports **CORD field-level F1 84.1, TED accuracy 90.9**, 1.2 s per image. The [official repo](https://github.com/clovaai/donut) quotes 93.7 for its later released checkpoint, so check which checkpoint the HF weights are before calibrating.
5. **Metric subtleties.**
   - **Matching lists of menu items** is a set-of-objects alignment, NER's one-to-one matching one level deeper.
   - **Normalisation:** "Rp 12.000" vs "12000", and whitespace.
   - **TED accuracy needs a tree-edit-distance implementation.** Donut's repo has one; reuse it rather than reimplement.
   - **Invalid JSON** must score 0, not crash. That is the NER lesson: "an unreadable answer scored 1.0".
6. **Cost.** A receipt image is about 1,000–1,700 tokens and the output about 250 tokens of JSON. The 18 vision arms at 200 items cost about $11. The OCR-text arm for all 24 costs about $7. **About $18 in total**, the most expensive candidate here because of JSON output on dear output prices. Donut on CPU takes about 1–3 s per image.
7. **Risks.**
   - CORD is public and may be in VLM training data.
   - The scorer is the hardest of all the candidates to get right, and this repo's history says the scorer is where errors hide.
   - The vision subset changes the arm set per input mode.
   - **BFCL alternative.** For agentic tool calls rather than documents, BFCL ([`gorilla-llm/Berkeley-Function-Calling-Leaderboard`](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard), Apache-2.0, AST-matched) covers the same answer shape. But its best small local fine-tune, [`Salesforce/xLAM-2-1b-fc-r`](https://huggingface.co/Salesforce/xLAM-2-1b-fc-r), is **CC-BY-NC-4.0**, and the leaderboard numbers move, which makes a weak calibration row.

### 5. Confidence and selective prediction (abstention), as an add-on to AG News and DBpedia

1. **What's new.**
   - **A new output field per item:** a confidence or probability.
   - **New metrics:** Brier score and log-loss, which are proper scoring rules and decomposable per item, so the existing permutation test works unchanged. Also ECE, which is binned and corpus-level, and the risk-coverage curve / AUROC.
   - **It fills a documented gap.** REFERENCE.md says no hosted arm supplies `confidence`.
   - **The practical question:** "can I auto-accept the model's answer when it is sure, and send the rest to a human?" Accuracy at 80% coverage is often the deployable number, not raw accuracy.
2. **Dataset.** The already-frozen AG News and DBpedia-14 sets: no new data or licence work. The harness already handles AG News (train-derived licence notes in DATA.md).
3. **Local models.** The fine-tuned BERTs already emit softmax confidence. Temperature scaling on a held-out slice is a $0 extra arm.
4. **Calibration row.** None needed for accuracy (it already exists). For calibration itself there is no standard published ECE for these exact checkpoints, which is a weakness. The fine-tunes' ECE becomes the house reference.
5. **Metric subtleties.**
   - Verbalised confidence ("0–100") is available for all 24 arms; token logprob for only 12 (no Anthropic or OpenAI). These are two different systems, so record which one each arm used.
   - Verbalised confidences cluster at 90/95, so ECE bins are mostly empty. Prefer Brier plus AUROC.
   - The label-noise items (17 on AG News) will show as "confident and wrong". That is useful, because it ties to the disputed-gold findings.
7. **Cost.** About 170 tokens in and 15 out, so **about $1** per dataset for all 24 arms. Effort is an afternoon of adapter changes plus a scorer.
8. **Risks.** It is not a new task, so it does not count as a "sixth experiment" in the README's terms. Hosted runs must be redone because the prompt changes, and the hash will rightly differ.

### 6. Machine translation: WMT24++ (en→de, plus one Croatian/Serbian pair)

1. **What's new.**
   - **Multilingual output**, the first non-English output.
   - **A learned metric (COMET):** a 2.3 GB neural model becomes part of the scorer. That needs a fingerprint for the *metric's* weights, which extends the NER lesson that no fingerprint covered the scorer.
   - **chrF** is the n-gram baseline.
   - **Paragraph-level segments** from literary, social and speech domains.
2. **Dataset.** [`google/wmt24pp`](https://huggingface.co/datasets/google/wmt24pp), **Apache-2.0**: 55 English→X pairs, 998 rows each, with post-edited references.
   - Includes `en-de_DE`, `en-hr_HR` and `en-sr_RS`.
   - Drop the `is_bad_source` rows (one canary per pair), as the card instructs.
   - **Not FLORES+:** [openlanguagedata/flores_plus](https://huggingface.co/datasets/openlanguagedata/flores_plus) is CC-BY-SA-4.0 and **gated**, so it is fine for calibration but awkward as the main set.
3. **Free local models.**
   - [`Helsinki-NLP/opus-mt-en-de`](https://huggingface.co/Helsinki-NLP/opus-mt-en-de) and [`opus-mt-tc-big-en-fr`](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-fr), CC-BY-4.0, about 0.2B params. These are task-specific MT models, the fine-tune analogue.
   - [`facebook/m2m100_418M`](https://huggingface.co/facebook/m2m100_418M), MIT.
   - [`google/madlad400-3b-mt`](https://huggingface.co/google/madlad400-3b-mt), Apache-2.0. 3B, slow on CPU.
   - **Avoid NLLB:** [`facebook/nllb-200-distilled-600M`](https://huggingface.co/facebook/nllb-200-distilled-600M) is **CC-BY-NC-4.0**.
   - **Scoring model:** [`Unbabel/wmt22-comet-da`](https://huggingface.co/Unbabel/wmt22-comet-da), Apache-2.0, about 2.3 GB, runs on CPU. The reference-free CometKiwi is **CC-BY-NC-SA and gated**, so avoid it.
4. **Calibration row.** `opus-mt-tc-big-en-fr` on flores101-devtest reports **chrF 0.725 / BLEU 52.2** over 1,012 sentences ([model card](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-fr)). It is reproducible on FLORES+ devtest, with the caveat that FLORES+ has corrections relative to FLORES-101. The [WMT24++ paper](https://arxiv.org/abs/2502.12404) benchmarks LLMs and MT providers, but I did not verify a per-system number from it.
5. **Metric subtleties.**
   - Use sacreBLEU signatures for chrF.
   - COMET is segment-level, so it is per-item and decomposable. It is also slow on CPU (about 6k segments × 30 arms takes tens of minutes) and must be pinned.
   - Marian's 512-token limit truncates long paragraphs, so the local arm needs sentence splitting, which then becomes part of the system.
6. **Cost.** About 250 tokens in and 200 out, so **about $5.4 per language pair** for 24 arms.
7. **Risks.**
   - Its shape, continuous text vs reference, is the same as summarisation's. The new parts are the language and the learned metric.
   - COMET is known to favour LLM-style output.
   - Low contamination: references were post-edited in 2025.

### 7. Extractive QA with unanswerable questions: SQuAD 2.0

1. **What's new.**
   - **Answer shape:** a *span or nothing*. Scoring is EM and token F1 with SQuAD normalisation.
   - **The key behaviour is abstention**, i.e. "no answer" when the passage doesn't contain one. That is the hallucination question in miniature, and it touches the "factual accuracy" gap.
2. **Dataset.** [`rajpurkar/squad_v2`](https://huggingface.co/datasets/rajpurkar/squad_v2), **CC BY-SA 4.0**. Validation has 11,873 questions (5,928 answerable, 5,945 not); the test set is hidden. Gold quality is good, with multiple reference answers.
3. **Free local models.** Both are fine-tuned on this data:
   - [`deepset/roberta-base-squad2`](https://huggingface.co/deepset/roberta-base-squad2), CC-BY-4.0, 0.1B params, about 500 MB;
   - [`deepset/tinyroberta-squad2`](https://huggingface.co/deepset/tinyroberta-squad2), CC-BY-4.0.

   The built-in non-model baseline is "always abstain", which scores **50.07 EM** (5,945/11,873) and exposes the metric's structure.
4. **Calibration row.** `deepset/roberta-base-squad2` on the full dev set: **EM 79.87, F1 82.91** (HasAns F1 84.03 / NoAns 81.80), per the [model card](https://huggingface.co/deepset/roberta-base-squad2). Running all 11.9k items on CPU takes about 20 min.
5. **Metric subtleties.**
   - **Official normalisation:** lowercase, strip punctuation, articles and whitespace.
   - **Max over references.**
   - **Score HasAns and NoAns separately.** Otherwise a model's abstention propensity, not its reading, decides the ranking.
   - **LLMs paraphrase spans,** so EM punishes them unfairly and token F1 is fairer. Report both, and the parser rate.
6. **Cost.** About 300 tokens in and 15 out, so **about $1.7**.
7. **Risks.**
   - **Very heavily contaminated** (2018, everywhere), and near-saturated.
   - The token-F1 metric is close to the ROUGE family already covered.
   - The genuinely new content, abstention, could instead be bolted onto candidate 5.
   - The SA licence carries share-alike obligations on derived outputs, as SciFact's does.

### 8. Multi-label emotion: GoEmotions (weak)

1. **What's new.** A label *set* per text, with per-label thresholds and micro- vs macro-F1. That is close to NER's set-matching shape, so the novelty is small. What is distinctive is very low inter-annotator agreement: per-emotion κ runs from 0.095 (grief) to 0.749 (gratitude) ([paper](https://arxiv.org/abs/2005.00547)). It would be a stress test of "the gold is the problem".
2. **Dataset.** [`google-research-datasets/go_emotions`](https://huggingface.co/datasets/google-research-datasets/go_emotions), Apache-2.0, 5,427 test examples, 28 labels.
3. **Local fine-tune.** [`SamLowe/roberta-base-go_emotions`](https://huggingface.co/SamLowe/roberta-base-go_emotions), MIT, 0.1B params. It reports test F1 0.450 at threshold 0.5 and 0.541 with per-label thresholds.
4. **Calibration row.** BERT baseline macro-F1 **0.46** (P 0.40 / R 0.63), [Demszky et al. 2020, Table 4](https://arxiv.org/abs/2005.00547).
6. **Cost.** About $1.
7. **Verdict.** Cheap and clean, but it mostly repeats the AG News "fine-tune learned the corpus's labelling" finding with noisier gold. Low marginal value.

---

## Considered and rejected

- **STS-B (semantic similarity regression).** The answer shape (continuous gold) is good, but the **licence is unknown or "other"**: [`sentence-transformers/stsb`](https://huggingface.co/datasets/sentence-transformers/stsb) states none, [`mteb/stsbenchmark-sts`](https://huggingface.co/datasets/mteb/stsbenchmark-sts) says "unknown", and [GLUE](https://huggingface.co/datasets/nyu-mll/glue) says "other" and defers to the original sources. That is the same reason WNUT was rejected.
  - Pearson and Spearman are also corpus-level, which would need the anti-conservative bootstrap.
  - SummEval (#1) gives continuous human gold with a clean MIT licence *and* a per-item correlation.
  - For the record: [SBERT Table 2](https://arxiv.org/abs/1908.10084) reports SBERT-NLI-STSb-base Spearman 85.35 on the STSb test set.
- **Long-context QA.** At about 30k tokens × 200 items × 24 arms, the input bill alone is about $135 at this field's prices. That is two orders of magnitude above the harness's per-experiment budget ($12.05 for all five so far).
- **Toxicity / safety classification** (e.g. Jigsaw / civil_comments). It is binary 0/1 again. The only new content would be LLM refusals to label offensive text, which is a parser-robustness finding rather than a new shape.
- **Tabular / time-series forecasting** (e.g. Chronos-Bolt vs LLMs). It does give a new metric family (MASE/CRPS), but "do I need an LLM?" has a foregone answer, and there is little decision value for this audience.

## Ranking by value per effort

| rank | candidate | new thing | effort | hosted $ | licence | contamination |
|---|---|---|---|---|---|---|
| 1 | **SummEval judging** | correlation metric, LLM-as-judge, audits the harness's own ROUGE | **low** (100 rows, reuses BART/ROUGE) | ~$3–7 | MIT | low–medium |
| 2 | **Confidence / abstention add-on** | confidence field, Brier, risk-coverage | **very low** (existing data) | ~$2 | already cleared | n/a |
| 3 | **ASR (Earnings-22 + AMI)** | audio modality, WER, own-vs-rent at its sharpest | medium (audio items, gateway path) | <$5 | CC-BY-SA / CC-BY | medium (Whisper's web data) |
| 4 | **Code exec (MBPP+)** | execution-based correctness, sandbox | medium–high (sandbox) | ~$6–15 | Apache-2.0 | **high** |
| 5 | **CORD receipts → JSON** | nested JSON, images, TED | high (scorer, vision split) | ~$18 | CC-BY-4.0 | medium |
| 6 | MT (WMT24++) | multilingual, learned metric | medium | ~$5/pair | Apache-2.0 | low |
| 7 | SQuAD 2.0 | span + abstention | low | ~$2 | CC-BY-SA | **very high** |
| 8 | GoEmotions | multi-label | low | ~$1 | Apache-2.0 | medium |

## Top 3 recommendations

**1. SummEval: does a model judge summaries like an expert?** It is the highest value for the least work, and it turns the harness's lens on its own foundations.
- **It reuses what already exists.** The articles are CNN/DM, which the harness already handles. Two of its strongest local competitors are already in the stack (BART for BARTScore, ROUGE for the baseline). The dataset is 100 MIT-licensed rows.
- **It asks something none of the five can.** Can the thing I'd use to grade my system be trusted? That is the agent-trust question and the silver-reference question (`make silver-calibrate`) in measurable form.
- **The calibration row is free and pointed.** The published summary-level Spearman of ROUGE-1 against experts is 0.192. Reproducing it puts a number on how much the summarisation experiment's `coverage` metric can be believed.
- **It stays inside the existing statistics.** A per-article τ is per-item, so the permutation test and Holm apply unchanged.
- **The outcome is unknown in advance.** The judge field may span 0.2–0.5, and price may or may not buy judgement. That uncertainty is what makes an experiment worth running.

**2. Speech-to-text on Earnings-22 (and AMI): Whisper on a laptop vs hosted audio LLMs.** This one breaks the most in the harness:
- binary audio items whose bytes must be fingerprinted;
- a new gateway path (base64 audio);
- a hosted field that is *not* the 24, since none of them takes audio;
- a metric whose normaliser decides the ranking. "$5" vs "five dollars" on earnings calls is the WER equivalent of the AG News label parser.

It is also where own-vs-rent is sharpest. Whisper and Moonshine are open, a few hundred MB and CPU-fast, and the published reference (Whisper base.en WER 15.09 on Earnings-22) is reproducible on the full set in under an hour. The licences are clean if TED-LIUM and SPGISpeech are avoided. Earnings calls (accents, numbers, names, conversation) are the closest permissively licensed proxy for podcast audio, so the result transfers directly to the author's podcast product. The long-form track is the natural sequel. Hosted cost is under $5.

**3. Code generation scored by execution (MBPP+).** Every experiment so far ended up adjudicating disputed gold labels. Here the referee is a test suite, and how weak those tests are can itself be measured as the gap between the base and plus tests.
- **It adds a harness capability with a safety edge:** sandboxed execution of untrusted output, with timeouts recorded separately from failures.
- **It forces a new refusal:** never execute outside the sandbox.
- **It is where the repo's headline "$0 answer in every experiment" is most likely to fail.** A 1.5B Qwen-Coder on CPU (published MBPP+ 59.4) against frontier models near 80 is the honest test of that claim. Running it is better than leaving the claim untested on the task people most often buy LLMs for.
- **Contamination is the known weakness.** Pre-register it, and keep BigCodeBench-Hard (licence unstated, so check it first) as the contamination check.

**Why CORD missed the top 3, and two things to do anyway.** CORD receipts → JSON is the strongest runner-up. It covers the commonest enterprise extraction job and has a famous MIT fine-tune (Donut, F1 84.1). It drops to fourth because its scorer (nested-list alignment plus tree edit distance) is the most error-prone to build, and this repository's history says the scorer is where errors hide. Separately, the **confidence/abstention add-on** is not a new experiment, but at about $2 and an afternoon it closes a gap REFERENCE.md documents. It should be done regardless.

## Sources

**Datasets**
- [mteb/summeval](https://huggingface.co/datasets/mteb/summeval) · [Yale-LILY/SummEval](https://github.com/Yale-LILY/SummEval)
- [ESB test-only (per-subset licences)](https://huggingface.co/datasets/hf-audio/esb-datasets-test-only-sorted) · [Earnings-22 licence](https://github.com/revdotcom/speech-datasets/tree/main/earnings22) · [distil-whisper/earnings22](https://huggingface.co/datasets/distil-whisper/earnings22) · [AMI](https://huggingface.co/datasets/edinburghcstr/ami)
- [MBPP+](https://huggingface.co/datasets/evalplus/mbppplus) · [HumanEval+](https://huggingface.co/datasets/evalplus/humanevalplus) · [BigCodeBench-Hard](https://huggingface.co/datasets/bigcode/bigcodebench-hard)
- [CORD v2](https://huggingface.co/datasets/naver-clova-ix/cord-v2) · [BFCL](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard)
- [WMT24++](https://huggingface.co/datasets/google/wmt24pp) · [FLORES+](https://huggingface.co/datasets/openlanguagedata/flores_plus)
- [SQuAD v2](https://huggingface.co/datasets/rajpurkar/squad_v2) · [GoEmotions](https://huggingface.co/datasets/google-research-datasets/go_emotions)
- STS-B copies: [sentence-transformers/stsb](https://huggingface.co/datasets/sentence-transformers/stsb) · [mteb/stsbenchmark-sts](https://huggingface.co/datasets/mteb/stsbenchmark-sts) · [GLUE](https://huggingface.co/datasets/nyu-mll/glue)

**Models**
- Evaluators: [UniEval HF](https://huggingface.co/MingZhong/unieval-sum) · [UniEval repo](https://github.com/maszhongming/UniEval)
- ASR: [whisper-base.en](https://huggingface.co/openai/whisper-base.en) · [whisper-small](https://huggingface.co/openai/whisper-small) · [distil-small.en](https://huggingface.co/distil-whisper/distil-small.en) · [moonshine-base](https://huggingface.co/moonshine-ai/moonshine-base)
- Code: [Qwen2.5-Coder-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct) · [GGUF](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF)
- Extraction: [Donut CORD](https://huggingface.co/naver-clova-ix/donut-base-finetuned-cord-v2) · [Donut repo](https://github.com/clovaai/donut) · [xLAM-2-1b-fc-r](https://huggingface.co/Salesforce/xLAM-2-1b-fc-r)
- MT: [opus-mt-en-de](https://huggingface.co/Helsinki-NLP/opus-mt-en-de) · [opus-mt-tc-big-en-fr](https://huggingface.co/Helsinki-NLP/opus-mt-tc-big-en-fr) · [m2m100_418M](https://huggingface.co/facebook/m2m100_418M) · [madlad400-3b-mt](https://huggingface.co/google/madlad400-3b-mt) · [NLLB-600M](https://huggingface.co/facebook/nllb-200-distilled-600M) · [COMET-22](https://huggingface.co/Unbabel/wmt22-comet-da)
- QA and classification: [roberta-base-squad2](https://huggingface.co/deepset/roberta-base-squad2) · [tinyroberta-squad2](https://huggingface.co/deepset/tinyroberta-squad2) · [roberta-base-go_emotions](https://huggingface.co/SamLowe/roberta-base-go_emotions)

**Papers**
- [G-Eval (2303.16634)](https://arxiv.org/abs/2303.16634) · [Moonshine (2410.15608)](https://arxiv.org/abs/2410.15608) · [Open ASR Leaderboard (2510.06961)](https://arxiv.org/abs/2510.06961) · [Qwen2.5-Coder (2409.12186)](https://arxiv.org/abs/2409.12186) · [Donut (2111.15664)](https://arxiv.org/abs/2111.15664) · [WMT24++ (2502.12404)](https://arxiv.org/abs/2502.12404) · [GoEmotions (2005.00547)](https://arxiv.org/abs/2005.00547) · [SBERT (1908.10084)](https://arxiv.org/abs/1908.10084)

**Infrastructure**
- [OpenRouter models API](https://openrouter.ai/api/v1/models) (prices, modalities, supported parameters) · [OpenRouter audio input docs](https://openrouter.ai/docs/features/multimodal/audio) · [Open ASR Leaderboard code](https://github.com/huggingface/open_asr_leaderboard)
