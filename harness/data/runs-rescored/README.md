# `runs-rescored/` — the same runs, scored again, and the copy that counts

Every directory here has a twin in [`../runs/`](../runs/README.md) with the same name.
They hold **the same model outputs** and, for four of them, **different scores**.

**These are the figures `REPORT_NER.md` states.** `check_report_claims.py` reads this
directory for every NER claim, and `make ci` fails if a report and this directory
disagree.

## Why there are two copies at all

`rescore.py` recomputes scores from stored outputs without calling any model. It exists
because the scorer has been wrong twice, and a scorer fix is worthless if the only way
to apply it is to pay for the sweep again.

So `../runs/` holds each run **as it was measured** — with the scorer of that day — and
this directory holds it **as the current scorer reads it**. Neither is stale and neither
is a draft. They answer different questions: *what did we measure* and *what do those
outputs score now*.

## Where they disagree, and why

Four NER runs differ, all from scorer fixes found by external review:

| run | `../runs/` f1 | here | what moved |
|---|---|---|---|
| `fn_glm_l_n200_v1` | 0.5484 | **0.5662** | an unreadable answer was scoring 1.0 on empty-gold items (−0.0214), then the greedy `[.*]` array matcher was refusing 14 answers that were there (+0.0393) |
| `fn_llama_l_n200_v1` | 0.5911 | **0.5990** | the same array matcher: 3 of its 4 unreadable items were readable |
| `fn_llama_m_n200_v1` | 0.5704 | **0.5740** | the same, 3 of 16 |
| `fn_deepseek_m_n200_v1` | 0.6122 | **0.6148** | it answered `[[{...}]]`, doubly wrapped, and the old parser dropped the inner list as a non-object and returned an **empty set** — six found entities scored as "correctly found nothing" |

The other 23 runs here carry identical scores to their twins; only their timestamps and
fingerprint hashes differ.

## How to tell which you are reading

Every file here carries `rescored_from`, `rescored_at` and `rescored_with` (the adapter
id and its sha256), and its `fingerprint.hash` is **null**, with
`hash_invalid_because` saying why: the hash was computed over a scorer that did not
produce these numbers. A run in `../runs/` has a real hash and none of those fields.

`data.references_sha256` here is recomputed against the reference files actually read,
not copied from the source run — and if the two differ, both are kept
(`references_sha256_at_measurement`) and the rescore warns.

## What is NOT here

`outputs/` is not committed in this directory. It would be a byte-identical copy of
`../runs/<same name>/outputs/`, which is committed — 32,710 files duplicated for
nothing. Regenerate this whole directory with:

```bash
make rescore DATASET_ID=few_nerd_280
```

Costs nothing and calls no model. It needs the corpus, which is gitignored: run the
example's `fetch.py` first, or `rescore.py` will refuse rather than score every
prediction against an empty gold set.
