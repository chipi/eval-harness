# configs/ — experiment definitions

One YAML per arm. Required: `config_id`, `dataset_id` and `params`; optional `adapter`,
`goal` and `format`, and nothing else (`validate` V1). Everything under `params` is handed
to the adapter's `call_system()` untouched — model, temperature, prompt version,
thresholds.

An arm is a config. To compare two things, write two configs against the SAME
`dataset_id` and run both.
