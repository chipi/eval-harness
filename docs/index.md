# eval-harness documentation

The reference for the harness and the five experiments behind
[the findings site](https://chipi.github.io/eval-harness/).

| page | what it answers |
|---|---|
| [Reproduce it](REPRODUCE.md) | Rerun any experiment and check its findings: five levels, from recomputing every number ($0) to rerunning every model with one key, and adding your own. |
| [Protocol](PROTOCOL.md) | What each experiment measured, on which data and metric, and how that relates to the field's standard protocol — with a calibration row per experiment. |
| [Reference](REFERENCE.md) | Every metric, model, dataset and statistical test, with sources. |
| [Concepts](../harness/docs/CONCEPTS.md) | The ideas the harness is built on: frozen datasets, fingerprints, paired tests. |
| [Runbook](../harness/docs/RUNBOOK.md) | How to run it: datasets, experiments, the analysis scripts. |
| [Integration](../harness/docs/INTEGRATION.md) | How to drop the harness into another project. |
| [Evidence](evidence/README.md) | Captured external facts — model sizes and licences, calibration results — checkable offline. |
| [Papers](papers/README.md) | The papers the work cites. |

The experiment reports themselves live in the repository's
[`research/`](https://github.com/chipi/eval-harness/tree/main/research) directory, and
the lab notebook — handovers, review rounds, the journal — in
[`research/internal/`](https://github.com/chipi/eval-harness/tree/main/research/internal).
