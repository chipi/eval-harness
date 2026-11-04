# Triage fleet: an agent's decisions, measured on what happened next

A triage agent (the homelab's signal fleet) reads production error signals, asks up to three probes (the
error's latest event, its history, logs, metrics, a trace, the app's data state), and decides: dismiss, file an
issue, escalate to a person, or clean up. Its own deterministic gates may then change the decision (a dismissal
without independent corroboration becomes an escalation). This example replays each real decision through the
agent's own code, with another model, on the probe answers as of the decision's time, and scores it against
what the operator later said it was.

**The data** is published on Hugging Face as `chipi-nbgd/orrery-triage` at revision `v1`: 233 Orrery decisions
(2026-07-25 to 2026-10-29) and `verdicts.jsonl`, the labels with who gave each. Git holds the ids and hashes;
`fetch.py` downloads the pinned revision and restores the rest.

| file | what it is |
|---|---|
| `fetch.py` | downloads `v1` (each file sha256-pinned) and restores the capture's records and the datasets' items |
| `importer.py` | one record per decision: the body is what the agent sees (`{signal, probes}`); fields (evidence level, who decided, what production decided, `labelled`); the outcome fields the rules read, with each issue's verdict from the operator's close comment |
| `adapter.py` | replays a decision through the fleet's `investigate()`, tracing off, every call tagged `evh-eval`; an arm may name its own server (`url`, for a self-hosted Ollama). `score()` gives `triage_cost` (a missed real problem costs 5 false alarms; `_p3` and `_p10` beside it), `false_dismiss`, `false_alarm`, `correct`, `escalated` as the fleet decided, and `model_*` the same for the model's own decision before the gates |
| `label_sheet.py`, `label_with_model.py`, `write_verdicts.py`, `labels_from_verdicts.py` | how the labels were made: a sheet of the operator's issue verdicts, a labeller model's proposal for each exact decision (answered by the operator where it disagreed), `verdicts.jsonl`, and a source's labels from it, one file per item, for `evh label-import`; the owner's are promoted to gold (`evh reference-promote`) |
| `outcomes.yaml` | the rules from an outcome to a label: `silver/…_outcomes`, shown beside gold, never deciding |
| `configs/` | hosted arms (proprietary, and open-weight models' hosted twins); `configs/local/` the same open-weight models self-hosted (Ollama 0.40.13) on three machines. Ollama 0.40 hands gpt-oss's every answer back as a tool call to `assistant`, with no text; its arms set `reply_in_tool_call: assistant` so the adapter reads it (production on that server would get nothing) |
| `test_triage.py` | the scorer, the importer, the adapter through the fleet's code |

The goal and the item fields are the project's own, one copy each: `harness/data/goals/triage_orrery.yaml`
(`triage_cost` decides, lower; a ceiling on false alarms; frugal) and `harness/data/fields/triage.yaml`.

```bash
python examples/triage-fleet/fetch.py                       # needs the revision public, or a token
evh dataset-materialize --dataset-id orrery_triage_v1_labelled
TRIAGE_FLEET_SRC=/path/to/signal-fleet evh run --config examples/triage-fleet/configs/<arm>.yaml
evh goals --goal triage_orrery
```

The fleet's code is not copied here: `TRIAGE_FLEET_SRC` names the `signal-fleet` folder of its repository, at
the commit the runs record. Each run's fingerprint carries the fleet's code hash and prompt hash; set
`TRIAGE_FLEET_COMMIT=<sha>` (or `fleet_commit` in an arm's params) for it to carry the commit too. What the eval taught about the fleet itself is in
the fleet's own repository, [signal-fleet/EVAL-LESSONS-0.6.0.md](https://github.com/chipi/agentic-ai-homelab/blob/main/signal-fleet/EVAL-LESSONS-0.6.0.md).

**On the X3, a second Ollama shares the GPU.** Since 2026-11-03 the homelab assistant runs there as the systemd user
unit `ollama-assistant` (100.92.54.65:11435, the same binary and model directory as the arms' Ollama on
127.0.0.1:11434), and keeps a 21.8 GB model loaded. Beside a large model it skews the numbers (gpt-oss:120b beside it
ran 37% on the CPU, swap 16 → 41 GB). So for an arm whose model is over about 35 GB:

```bash
systemctl --user stop ollama-assistant     # before the run; nothing depends on it until the homelab's failover
evh run --config examples/triage-fleet/configs/local/<arm>.yaml
systemctl --user start ollama-assistant    # after; its alert x3-assistant-down fires after 15 minutes stopped
```

The rule is the homelab's: chipi/agentic-ai-homelab `infra/x3/AGENTS.md` and `docs/recipes/x3-deploy.md`. While
the unit is stopped the homelab assistant has no model: anything using it, an agent running on it included, stops
answering until it is started again.
