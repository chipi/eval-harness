# RFC-001: The run fingerprint and code identity (version 4)

- **Status**: Completed (0.4.0, unreleased)
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-001](../prd/PRD-001-experiments-and-comparison.md), [PRD-002](../prd/PRD-002-references.md)
- **Related RFCs**: [RFC-002](RFC-002-run-records-and-derived-runs.md) (the record that carries it),
  [RFC-003](RFC-003-catalog-adapter.md) (the inspector's conditions check reads it)
- **Code**: `harness/scripts/_fingerprint.py`, `harness/scripts/_codeid.py`; tests
  `harness/tests/test_codeid.py`, `harness/tests/test_code_hashes.py`

## Abstract

Every run records a **fingerprint**: what its numbers depended on, in three parts (the system
under test, the instrument that scored it, and the data), plus the machine and the arm, and one
sha256 over all of it. Two runs with the same hash varied nothing but what the fingerprint
excludes by design; two with different hashes say which fields drifted. Version 4 (0.4.0)
changes how **code** is identified: by what it does, its syntax tree without documentation, so
a docstring, a comment, a reformat or a metric description never makes a scorer look new.

## Problem Statement

A comparison is valid only if exactly one thing moved. Before version 4, code was hashed by its
bytes. Adding `METRIC_DESCRIPTIONS` to an adapter (a 0.4.0 feature) changed the adapter's hash,
so `run-compare` and the inspector called every earlier run "not the same conditions". The same
held for a reworded caveat in a silver reference's manifest, and for `ast.dump`, whose text
differs between Python 3.11, 3.12 and 3.14 for the same file.

## Design

### The fingerprint (`build_fingerprint`)

| part | fields | why |
| --- | --- | --- |
| `version` | `4` | digests of different versions are not comparable; the version says so |
| `instrument.harness` | `commit` and `dirty` (the project's git tree), `version`, `code_sha256`, `installed` | which harness measured; `code_sha256` is the only identity that survives installation |
| `instrument.adapter` | `id`, `sha256` | the scorer: the adapter holds `score()`, so its code is part of what a number means |
| `system_under_test.model` | whatever the adapter's optional `fingerprint(params)` returns (`id`, `revision`, `revision_source`, `device`, `precision`), with `identity_declared`; a missing revision is recorded as missing | the core defines a vocabulary, not a mechanism |
| `system_under_test.libraries` | versions of watched distributions (torch, transformers, scikit-learn, sentence-transformers, numpy, openai, anthropic, datasets, rouge-score), read from metadata without importing them | a library upgrade can move a number |
| `data` | `dataset_id`, `items_sha256`, `n_items`, `reference_id`, `reference_tier`, `references_sha256` | the item bytes and the reference bytes, not just their names |
| `host` | `label` (`EVAL_HOST_LABEL`), `platform`, `release`, `processor`, `cpu_count`, `python` | latency means something only per machine |
| `arm` | `config_id`, `params` | what the arm varies |
| `hash` | sha256 over everything above, keys sorted | one comparison answers "did anything else move?" |

`goal` and `format` are recorded on the run beside the fingerprint, not in it: they change what
a run answers, not what it measured. Item **fields** are outside it too: `items_sha256` hashes
item ids and their `source_sha256` only ([RFC-006](RFC-006-item-fields-and-url-items.md)).

### Code identity (`_codeid`)

- `source_sha256(text)`: parse the Python source, drop module, class and function docstrings and
  any module-level assignment to `METRIC_DESCRIPTIONS`, and hash `tree_text(tree)`. Comments and
  formatting are gone once parsed. Source that does not parse is hashed as bytes.
- `tree_text(node)`: a serialisation of the syntax tree that leaves out empty and `None` fields,
  so one file hashes the same on Python 3.11, 3.12 and 3.14 (`ast.dump` does not).
- `file_sha256(path)`: `source_sha256` for a `.py` file, bytes for anything else.
- `content_sha256(obj)`: a parsed YAML or JSON document by content (keys as strings, sorted):
  used for a judge scorer YAML, so its comments and layout are not identity.

### Where it applies

- **The adapter** (`instrument.adapter.sha256`): `file_sha256` of the adapter file.
- **The harness** (`instrument.harness.code_sha256`): over the **measuring modules**: the
  run-writing commands (`experiment_run.py`, `rescore.py`, `judge_score.py`, `import_run.py`,
  `reference_create.py`, `adapter.py`) and every module beside them they import, at any depth,
  found by reading their imports. Editing a test or a read-only command does not move it.
- **`import-run --scorer-file`**: the harness hashes the given scoring code by the same rule
  (several files in a fixed order are hashed together), and the hash is the run's
  `instrument.adapter.sha256`, inside the fingerprint. It replaced `--scorer-sha256`, which sat
  only in `imported`, outside the hash.
- **The reference digest** (`references_sha256`): every file in the reference directory by name
  order, a `manifest.json` included, minus the manifest's `caveat`.
- **judge-score's own hash**, judge scorer YAMLs (`content_sha256`), and the examples'
  `code_digest`.

### Who reads it

- `evh run-compare` names every differing dotted path (`differing_paths`).
- The inspector and `evh inspect` flatten each arm's fingerprints into conditions (`machine.*`,
  `library.*`, `harness.version`, `harness.code_sha256`, `scorer.id`, `scorer.sha256`,
  `data.items_sha256`, `reference.sha256`, `fingerprint.version`) and warn on a different scorer,
  different reference bytes, different item bytes, or latency across machines
  ([UXS-002](../uxs/UXS-002-inspector.md#conditions)).

## Migration

Version 3 and version 4 digests are not comparable. The committed version 3 runs in this
repository were migrated: each recorded hash was matched to the code or reference state it came
from (git history, unreachable objects included) and recomputed; no score changed
([CHANGELOG](../../harness/CHANGELOG.md), 0.4.0, Changed).

## Alternatives Considered

- **Hash bytes and accept the noise.** Rejected: documentation edits made controlled
  comparisons look uncontrolled, and the inspector's conditions check would cry wolf.
- **Hash a normalised text (strip comments with a regex).** Rejected: fragile, and it still
  moves on reformatting and docstrings.
- **`ast.dump`.** Rejected: its text differs across Python versions for the same file.
- **Hash every `.py` file of the harness.** It was the 0.3.0 rule; rejected because editing a
  test made two runs look like different instruments.

## Testing

- `harness/tests/test_codeid.py`: code identity, documentation never moves a hash.
- `harness/tests/test_code_hashes.py`: the scoring-code hashes the runs record.
- `evh validate` V10: a derived run naming a scorer that is not the code in this tree.
