# Evidence — the external facts, captured so they can be checked offline

Three independent reviews could not verify any model size, licence or provenance claim in
this repo, because **HuggingFace and OpenRouter were blocked from their container**. They
fell back to web search, and one factual error survived that way while another was
reported that turned out to be a definitional difference rather than a mistake.

This directory removes that gap. `model_facts.json` is a verbatim capture of what the
HuggingFace API returned for every model this repo cites, on **2026-09-29**.

```bash
python harness/scripts/check_model_facts.py    # reports vs this snapshot, no network
```

## What it holds

Per model: whether the repo exists, its `license` tag, whether it is `gated`, the
`safetensors` parameter total **and the per-dtype breakdown**, the pipeline tag, and the
commit `sha` of the revision that answered.

The per-dtype breakdown is the field that matters most, and it is why one review finding
resolved as a definitional difference rather than an error. DeepSeek-V4.1-Flash reports
763B parameters across `I8`, `F8_E4M3`, `BF16` and `F32`; its model card headlines **552B
backbone** parameters, because a 196B Engram memory ships alongside. Both numbers are
correct about different things, and only the dtype breakdown makes that visible.

## What it is not

**A snapshot, not a source of truth.** A model can be relicensed, re-uploaded or
withdrawn, and this file will not notice. It records what was true on the date at the top,
which is the honest basis for a claim in a dated report — and it lets a reviewer
distinguish *"this repo got the fact wrong"* from *"the fact changed"*, which without the
snapshot are indistinguishable.

Re-capture with `docs/evidence/capture.sh` when the facts need refreshing. The reports
cite these values; `check_model_facts.py` fails if a report and this file disagree.

## `conversion_pr_check.py` / `.json` — the safetensors conversion PRs, on torch 2.2.2

The six local arms added on 2026-09-30 load `main`'s pickle, which needs torch ≥ 2.6. The
script loads each checkpoint's Hub safetensors conversion PR on **torch 2.2.2**, the
newest Intel-Mac wheel, and runs it through the arm's own adapter with the arm's own
params. The `.json` records the results from 2026-09-30:

- `main` is refused by the CVE-2025-32434 guard for all six.
- The three BERTs reproduce the recorded outputs byte for byte on every item (200, 200 and
  280). So do `bart_m` and `bart_l_xsum`, on the first 20 items: beam search costs 3–6 s
  per item, so the BARTs were checked on a subset.
- `bart_s` does not run. Its PR is fp16, as its pickle is, and torch 2.2.2 has no fp16
  LayerNorm on CPU. Cast to fp32 it matches 19 of 20, but that is a different computation:
  the recorded run was fp16.

The usage line is in the script's docstring. It needs the datasets materialised under
`harness/data/materialized/` and network access to the Hub.
