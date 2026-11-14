# The ceiling, not an arm

These two systems are kept OUT of `systems/`, so a sweep over that folder cannot pick them up.

They are reference-grade models. Their job is to be the ceiling you measure toward, and to
author a **silver** reference set where no human one exists. An arm is something you might
actually choose to deploy; these are the answer to "how good does this get", which is a
different question and belongs in a different place.

Two concrete reasons, and the second is a correctness one:

1. **They distort the ranking they appear in.** A leaderboard is for choosing, and an arm
   at 40x the price of its neighbours crowds out the comparison that matters — which of
   the affordable models gets closest. The first sweep here made the point: Opus won
   ROUGE-L at $0.185 per 20 items while Gemma-4-31b reached 93% of it for $0.00168. The
   interesting row was the cheap one.

2. **As a reference author, an arm scored against itself is circular.** Where the
   reference is silver — authored by one of these — an arm running that same model scores
   near 1.0 by construction, exactly like a regression anchor re-frozen from the run it is
   scoring. It measures agreement with itself and reads as quality.

   It does not bite in THIS example, because CNN/DailyMail ships human `highlights` and
   the reference here is gold. It bites in every example that has no human reference, and
   the rule is cheaper to keep than to remember.

To use one as a reference-set author: run it as an arm, take its outputs as a model's labels, and promote them:

    evh run --system cnn_anthropic_opus_v1 --dataset <id>
    evh label-from-run --run <that run> --set opus_silver --not-redistributed
    evh reference-promote --dataset-id <id> --labels opus_silver --tier silver --reason "…" --by <you>
