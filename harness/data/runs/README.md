# runs/ — individual results

One directory per run: `metrics.json` and `predictions.jsonl`.

`metrics.json` carries the three things that make a number mean something —
`dataset_id` (what it measured), `config_id` (the instrument), and `build`
(the system under test). A run missing any of them cannot be attributed, and
`make validate` fails on it.

**A run you make shows up as untracked, not ignored.** The rules force-include
`metrics.json`, `predictions.jsonl` and `outputs/` for every run directory, so `git status`
offers you a new one: a fresh `data/runs/<id>/` appears as `?? data/runs/<id>/`, and
`git check-ignore -v` names the un-ignore rule (`!data/runs/*/metrics.json`). Commit the
ones you promote (see `baselines/`), not every experiment. Every other `data/runs-*/`
directory (a smoke pass, a scratch or tuning sweep) is ignored, except `runs-repeats/`,
`runs-linux/` and `runs-pair/`. See [What is committed here](#what-is-committed-here-and-what-is-not).

---

## What is committed here, and what is not

Every run directory's `metrics.json`, `predictions.jsonl` and `outputs/` is committed, so
every number in the reports can be recomputed by anyone, not only by its author.

| | committed | why |
|---|---|---|
| `metrics.json` | **yes** (~0.7 MB) | every leaderboard, cost figure and headline number |
| `predictions.jsonl` | **yes** (~47 MB) | per-item scores, so every separation test, rank-stability curve and holdout can be rerun |
| `outputs/` | **yes** (9.8 MB content, 35,626 files) | the models' generated text, which `rescore.py` reads. Most of it is single class words, document ids, or CC BY-SA 4.0 entity spans; only summarisation's ~60-word model paraphrases raise a copyright question |

**What committing `outputs/` does NOT buy.** A clone still cannot rescore, because the
corpora are gitignored — none of them is ours to redistribute. A clone has the smoke
example's five reference files and none of the reference sets the example runs were scored
on, so those must be rebuilt with each example's seeded `fetch.py` first: `ag_news_200`,
`cnn_dailymail_20`, `cnn_dailymail_200`, `cnn_dailymail_dm200`, `dbpedia_280`,
`few_nerd_280`, `scifact_200`, `summeval_100`. Corpora are a free deterministic re-fetch;
model outputs were paid for once, and they ship.

Running `rescore.py` without the references refuses and names the fetcher: scoring would
treat every gold set as empty and report a plausible wrong number (f1 0.1071 for an arm
whose recorded f1 is 0.6798, every prediction a false positive).

**Cost, both readings.** 9.8 MB as content; 139 MB as disk, since 35,626 files of a few
hundred bytes each sit in 4 KB blocks. One `outputs.jsonl` per run is the better layout —
open, and recorded in `research/internal/KNOWN_ISSUES.md`.

**Checked before committing: `predictions.jsonl` carries no article text.** `_meta` holds
provider metadata, a predicted label, a list of document ids, or Few-NERD entity spans
(CC BY-SA 4.0, redistributable with attribution). No summary, no source sentence, no
abstract.

### The exception: the summarisation dev runs

`cnn_dailymail_20`'s three-repeat runs are **excluded**. They predate `_portable_id` and
record an absolute adapter path containing a username and a former project name.

They are excluded rather than edited: rewriting a field inside a finished run would leave
`fingerprint.hash` — computed over the original bytes — describing content that no longer
exists, which is a worse failure than withholding a file. **No measurement run is
affected**; every number in the reports comes from the committed runs.
What cannot be recomputed from this repo alone is the n=20 dev-slice half of
`REPORT_SUMMARIZATION.md` §3.6 and its variance decomposition. Regenerate with:

```bash
make experiment-run CONFIG=../examples/summarization-cnn-dailymail/configs/arm_<x>.yaml ARGS="--repeat 3"
```
