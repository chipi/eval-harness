# systems/ — what is evaluated: a model, a prompt, its settings, with no dataset

One YAML per system, named by its `system_id` (RFC-032). Required: `system_id` and `params`; optional `adapter`,
`model_record`, `deployment` and the keys `schemas/system.schema.json` lists, and nothing else (`validate` V1).
Everything under `params` is handed to the adapter's `call_system()` untouched — model, temperature, prompt version,
thresholds.

A system runs on any dataset: `evh run --system <id> --dataset <id>`, with `--goal` and `--round` when the run is
for one. To compare two things, write two systems and run both on the same dataset.
