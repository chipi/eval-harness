<div class="eh-kicker">Documentation <span>· eval-harness</span></div>

# The harness, the method, and the evidence.

How to use [eval-harness](https://evals.humancopilot.eu/) on your own system, the
ideas it is built on, and the reference behind
[its six experiments](https://evals.humancopilot.eu/experiments.html): what each
measured, every metric, model and test with its source, and how to rerun all of it yourself.

<div class="eh-kicker">The harness</div>

<div class="eh-cards" markdown>

[<span class="n">01</span><b>Use the harness</b><span class="d">Your first evaluation end to end, offline: freeze a dataset, say what it is for, build a golden reference set, measure, compare honestly, promote a baseline, optionally re-measure with an LLM judge, and browse it all in the catalog.</span>](GUIDE.md)

[<span class="n">02</span><b>Concepts</b><span class="d">The ideas it is built on: frozen datasets, fingerprints, gold and silver references, paired tests.</span>](../harness/docs/CONCEPTS.md)

[<span class="n">03</span><b>Integration</b><span class="d">Drop the harness into another project: one adapter, four functions.</span>](../harness/docs/INTEGRATION.md)

[<span class="n">04</span><b>Runbook</b><span class="d">Every step and every verb: datasets, runs, the analysis scripts, and judge scorers.</span>](../harness/docs/RUNBOOK.md)

[<span class="n">05</span><b>Release notes</b><span class="d">What each release shipped, what can move a result, and how to upgrade.</span>](../harness/CHANGELOG.md)

[<span class="n">06</span><b>Architecture</b><span class="d">How the harness is built, layer by layer; the decisions behind it (ADRs) and the proposals under discussion (RFCs).</span>](architecture/ARCHITECTURE.md)

</div>

<div class="eh-kicker">The experiments</div>

<div class="eh-cards" markdown>

[<span class="n">07</span><b>Reproduce it</b><span class="d">Rerun any experiment and check its findings, from recomputing every number for $0 to rerunning every model with one key, and adding your own.</span>](REPRODUCE.md)

[<span class="n">08</span><b>Protocol</b><span class="d">What each experiment measured, on which data and metric, and how that relates to the field's standard, with a calibration row each.</span>](PROTOCOL.md)

[<span class="n">09</span><b>Reference</b><span class="d">Every metric, model, dataset and statistical test, with sources and licences.</span>](REFERENCE.md)

[<span class="n">10</span><b>Evidence</b><span class="d">Captured external facts (model sizes, licences, calibration results), checkable offline.</span>](evidence/README.md)

</div>

<div class="eh-kicker">Background</div>

<div class="eh-cards" markdown>

[<span class="n">11</span><b>Data & licences</b><span class="d">What of each dataset is in the repository, what you download, each licence, and what it asks of you.</span>](DATA.md)

[<span class="n">12</span><b>Influences</b><span class="d">The approach builds on Chip Huyen's books: idea by idea, with chapters, and the statistics it also stands on.</span>](INFLUENCES.md)

[<span class="n">13</span><b>Papers</b><span class="d">The papers the work cites, and what each is cited for.</span>](papers/README.md)

</div>

The experiment reports live in the repository's
[`research/`](https://github.com/chipi/eval-harness/tree/main/research) directory, and
the lab notebook — handovers, review rounds, the journal, every correction — in
[`research/internal/`](https://github.com/chipi/eval-harness/tree/main/research/internal).

[← Back to the site](https://evals.humancopilot.eu/){ .eh-back }
