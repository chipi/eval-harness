# runs/ — individual results

One directory per run: `metrics.json` and `predictions.jsonl`.

`metrics.json` carries the three things that make a number mean something —
`dataset_id` (what it measured), `config_id` (the instrument), and `build`
(the system under test). A run missing any of them cannot be attributed, and
`make validate` fails on it.

**A run you make now shows up as untracked, not ignored.** Since 2026-09-29 the rules
force-include `metrics.json`, `predictions.jsonl` and `outputs/` for every run directory,
so `git status` will offer you a new one. Verified: a fresh `data/runs/<id>/` appears as
`?? data/runs/<id>/`, and `git check-ignore -v` names the un-ignore rule
(`!data/runs/*/metrics.json`). Commit the ones you promote (see `baselines/`), not every
experiment — and note that smoke, tuning and superseded directories ARE still excluded by
name. See [What is committed here](#what-is-committed-here-and-what-is-not-2026-09-29).

---

## What is committed here, and what is not (2026-09-29)

An external review found that no real run was in the repo — only the demo — so **not one
number in the five reports could be recomputed by anyone but the author, on one laptop.**
A repository whose whole argument is "verify the instrument" was itself unverifiable.
That is now fixed, with one bounded exception.

| | committed | why |
|---|---|---|
| `metrics.json` | **yes** (~1 MB) | every leaderboard, cost figure and headline number |
| `predictions.jsonl` | **yes** (~39 MB) | per-item scores, so every separation test, rank-stability curve and holdout can be rerun |
| `outputs/` | **yes** (8.3 MB content, 32,710 files) | the models' generated text, which `rescore.py` reads. Excluded until 2026-09-29 on an estimate of "128 MB of copyrighted derivatives" that was wrong on both counts: 8.3 MB, and four of the five examples are single class words, document ids, or CC BY-SA 4.0 entity spans. Only summarisation's 1.7 MB of ~60-word model paraphrases raises the question at all |

**What committing `outputs/` does NOT buy.** A clone still cannot rescore, because the
corpora are gitignored — none of the four is ours to redistribute. A clone has 7
reference files against the 1,382 these runs were scored on, so six reference sets must
be rebuilt with each example's seeded `fetch.py` first: `ag_news_200`, `cnn_dailymail_20`,
`cnn_dailymail_200`, `dbpedia_280`, `few_nerd_280`, `scifact_200`. What did change is
that the irreplaceable half now ships: corpora are a free deterministic re-fetch, model
outputs were paid for once.

Running `rescore.py` without them used to exit 0 and report a plausible wrong number —
f1 0.1071 for an arm whose recorded f1 is 0.6798, every prediction a false positive
against an empty gold set. It now refuses and names the fetcher. Verified the other way
too: with the references restored, rescoring in a fresh clone reproduces all 23 numeric
metrics at the stored precision.

**Cost, both readings.** 8.3 MB as content; 128 MB as disk, since 32,710 files of a few
hundred bytes each sit in 4 KB blocks. A whole clone is 30 MB downloaded, 228 MB on disk.
One `outputs.jsonl` per run would make that ~47 MB and 143 files, and is the better
layout — open, and recorded in `research/KNOWN_ISSUES.md`.

**Checked before committing: `predictions.jsonl` carries no article text.** `_meta` holds
provider metadata, a predicted label, a list of document ids, or Few-NERD entity spans
(CC BY-SA 4.0, redistributable with attribution). No summary, no source sentence, no
abstract.

### The exception: 72 summarisation dev runs

`cnn_dailymail_20`, three repeats each, are **excluded**. They predate `_portable_id` and
record an absolute adapter path containing a username and a former project name.

They are excluded rather than edited: rewriting a field inside a finished run would leave
`fingerprint.hash` — computed over the original bytes — describing content that no longer
exists, which is a worse failure than withholding a file. **No measurement run is
affected**; every number in the reports comes from the n=200/280 runs, which are all here.
What cannot be recomputed from this repo alone is the n=20 dev-slice half of
`REPORT_SUMMARIZATION.md` §3.6 and its variance decomposition. Regenerate with:

```bash
make experiment-run CONFIG=../examples/summarization-cnn-dailymail/configs/arm_<x>.yaml ARGS="--repeat 3"
```

That the repo's own `validate_tree` caught the leak on the first attempt to commit these
is the reason it exists.
