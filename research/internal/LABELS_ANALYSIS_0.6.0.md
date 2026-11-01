# Labels, baselines and references against the books (0.6.0, for RFC-023)

The owner's question (2026-11-01): are we approaching labelling well, and how does it work with baselines and
references, checked against Chip Huyen's books, which `docs/INFLUENCES.md` names as the foundation? Every
quotation below is from her own published chapter summaries, the sources `INFLUENCES.md` cites so each line can be
checked ([DMLS](https://github.com/chiphuyen/dmls-book/blob/main/summary.md),
[AIE](https://github.com/chiphuyen/aie-book/blob/main/chapter-summaries.md)), read on 2026-11-01. What the summaries
do not say is marked as not checked.

## What the books say, and where RFC-023 stands

| The books | RFC-023 | Fit |
| --- | --- | --- |
| DMLS ch. 4: "Hand labels can be expensive and slow." | `person` labels, through a sheet or the inspector; only where they change a comparison | aligned |
| DMLS ch. 4: "Natural labels are usually delayed, and the time it takes from when a prediction is served until when the feedback on it is provided is the feedback loop length." | `rule` labels over what production recorded afterwards (an issue fixed, a signal seen again) | **the same idea, under another name**; the delay is what we measured: 3 days after v1, 7 more of 233 triage decisions had a label |
| DMLS ch. 4: the alternatives to hand labels are "weak supervision, semi-supervision, transfer learning, and active learning" | labelling the items where arms disagree (`label-sheet --items disagree`), and picks | **active learning in practice**: label the items that decide the comparison. The summary names active learning only; choosing items by disagreement between models is query-by-committee, from the wider literature, not checked in her text |
| DMLS ch. 6: "Evaluation metrics don't mean much unless you have a baseline to compare them to." | production's recorded decisions as an arm (`arm-from-capture`); the promoted baseline | aligned: production is the existing solution every candidate is compared with |
| DMLS ch. 8: covariate shift, label shift, concept drift; monitoring with "operational metrics" and "ML-specific metrics" | a new production dataset each capture, evaluated the same way | partly: comparing versions shows a shift after the fact; nothing detects one |
| DMLS ch. 9: continual learning needs "online evaluation" | step 6 evaluates production's data offline | **not covered**: the harness evaluates what production did, after it did it; it runs no online test (A/B, shadow, canary are not named in the summary and not built) |
| AIE ch. 3: "AI-as-a-judge evaluation is subjective"; scores "by different AI judges might not be comparable" | `model` labels record the model; scores are grouped by label set, never pooled | aligned |
| AIE ch. 3: "Having humans in the loop for sanity checks is always helpful, and in many cases, human evaluation is essential." | `person` labels on the disagreements and a random slice | aligned |
| AIE ch. 8: "It's hard to annotate data, but it's even harder to create annotation guidelines." | nothing: a label set records who and when, not the guideline they followed | **a gap**: a set should record the guideline it was labelled by |
| AIE ch. 8: "A small amount of high-quality data can outperform a large amount of noisy data." | picks: 5 to 10 chosen production items into the next governed version | aligned |
| AIE ch. 10: user feedback for "analytics, product improvement, and the data flywheel" | capture, label, pick, the next version, the next round | the same loop; the books call it the data flywheel |

## What this suggests for RFC-023

1. **Name the sources as the books do** (A4): `hand` for a person's labels, `natural` for labels from what
   production recorded afterwards, `model` for a model's. "Natural labels" and "feedback loop length" are the words
   a reader of the books already has; "rule" is ours.
2. **A label set records its guideline**: the file the labeller followed (the sheet's instructions, a labelling
   prompt, the rule file for natural labels), hashed, so two sets labelled by different guidelines are never read
   as one.
3. **Say what is not covered**: the harness evaluates production offline, on what it did; it does not run online
   tests and does not detect drift. The docs and the site should not imply either.
4. **Keep the rest**: hand labels where they decide something (active learning), production as the baseline to
   beat, model labels grouped by model, a small curated set over a large noisy one, the loop as the data flywheel.

## Baselines and references, as the harness has them

- **A baseline** is an arm you promote (`run-promote`, with a reason): the number later work is compared with. In
  the books' sense it is the comparison point; production's recorded arm is the natural one after deployment.
- **A reference** (RFC-023) is labels you promote: the yardstick a dataset's arms are scored against, its tier your
  decision. The two promotions are separate: one picks an arm, the other picks an answer key.

## Not checked

- Label multiplicity and data lineage, which DMLS ch. 4 covers in the book, are not in the summary; RFC-023's
  several sets per item and its recorded sources match them as I remember the book, not as checked here.
- The book's own list of baseline kinds (random, heuristic, human, existing solutions) is not in the summary.
- AIE ch. 4 defers "using user feedback to evaluate production applications" to ch. 10; ch. 10's detail beyond the
  sentence quoted is not in the summary.
