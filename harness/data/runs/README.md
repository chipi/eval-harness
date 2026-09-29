# runs/ — individual results

One directory per run: `metrics.json` and `predictions.jsonl`.

`metrics.json` carries the three things that make a number mean something —
`dataset_id` (what it measured), `config_id` (the instrument), and `build`
(the system under test). A run missing any of them cannot be attributed, and
`make validate` fails on it.

Gitignored by default. Commit the ones you promote (see `baselines/`), not every
experiment.

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
| `outputs/` | **no** | the models' generated text. For CNN/DailyMail that is derived from copyrighted articles, and only `rescore.py` needs it |

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
