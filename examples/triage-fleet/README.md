# Triage fleet: an agent's decisions, measured on what happened next

**Status: the walking skeleton (0.6.0, in progress).** The path runs end to end on the fleet's 236
Orrery decisions with a stand-in model, offline. Real models, the owner's verdicts, the data on
Hugging Face and the numbers come next ([the application plan](../../research/internal/PLAN_0.6.0_FLEET.md)).

A triage agent reads error signals, asks up to three probes (logs, metrics, traces, the source's
state), and decides: dismiss, file an issue, escalate to a person, or clean up. This example replays
each real decision through the agent's own code, with another model, on the probe answers as of the
decision's time, and scores it against what the person who later closed the issue said it was.

| file | what it is |
|---|---|
| `importer.py` | one record per decision from the fleet's export: the body is what the agent sees (`{signal, probes}`); the outcome fields are what the reference rules read |
| `adapter.py` | replays a decision through the fleet's `investigate()`, with its tracing off and every call tagged `evh-eval`; `score()` gives `false_dismiss`, `false_alarm`, `escalated`, `correct`, `silent_drop` |
| `outcomes.yaml` | the rules from an outcome to a label (shown beside the owner's verdicts, never deciding) |
| `fieldset_triage.yaml` | the item fields: evidence level, what production decided, model, stage, fingerprint, date |
| `goal_triage.yaml` | the goal: `false_dismiss` decides, lower; no limits in v1 |
| `configs/` | the arms; for now two stand-ins (`provider: stub`) |
| `test_triage.py` | the scorer's rules, the importer, and the adapter through the fleet's code |

The fleet's code is not copied here: set `TRIAGE_FLEET_SRC` to the `signal-fleet` folder of the
fleet's repository (at the commit the runs record).

```bash
evh capture --importer examples/triage-fleet/importer.py:Importer \
    --query '{"path": "orrery-triage-items.jsonl"}' --capture orrery_2026_10
evh dataset-from-capture orrery_2026_10 --dataset-id orrery_triage_v1 --fieldset triage \
    --field evidence_level --field fleet_disposition --field fleet_model --field stage \
    --field fingerprint --field decision_date
evh dataset-materialize --dataset-id orrery_triage_v1
evh reference-from-outcomes --dataset-id orrery_triage_v1 --capture orrery_2026_10 \
    --map examples/triage-fleet/outcomes.yaml --name silver/orrery_triage_v1_outcomes
TRIAGE_FLEET_SRC=/path/to/signal-fleet evh experiment-run --config <arm config>
evh goals --goal triage_orrery
```
