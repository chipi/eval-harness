# RFC-017: The record store: records, ids and one store contract

- **Status**: Draft (0.5.0), revision 2 (2026-10-27): new in the simplification pass
- **Authors**: Marko Dragoljevic
- **Related PRDs**: [PRD-011](../prd/PRD-011-evidence-registry.md), [PRD-012](../prd/PRD-012-agent-ready.md),
  [PRD-013](../prd/PRD-013-identity-and-ties.md)
- **Related RFCs**: [RFC-009](RFC-009-prompt-versions.md) (prompt versions), [RFC-010](RFC-010-studies.md) (studies),
  [RFC-012](RFC-012-evidence-registry.md) (evidence), [RFC-014](RFC-014-identity-baselines-migration.md)
  (baselines, ids), [RFC-015](RFC-015-noninferiority-looks-power.md) (looks)
- **Code**: new `harness/scripts/_store.py` (the contract and the files provider); every command that writes a
  0.5.0 record goes through it

## Abstract

0.5.0 adds records: baseline versions, prompt versions, study trials, decisions on heldout data. Today each
command writes its own files its own way. This RFC fixes how every new record is stored: a typed document with an
id that can never collide, written through one small store contract. The files-in-git provider implements the
contract with plain files that merge cleanly; a database provider, planned for team use, will implement the same
contract with transactions, so the commands do not change when it comes.

## Problem Statement

- Teams will use the harness, first through git (several clones, merged later), then through a shared database.
- A per-machine lock file protects one machine, not two clones: git meets their writes only at merge.
- Sequential numbers (`3.json` then `4.json`) collide when two branches both make the next one.
- A shared index file (`index.json`) that every write edits conflicts on every concurrent change.
- Stored copies of what can be computed (a count of looks, a spend total, a list of versions) drift from the
  records they summarise.

## Design

### Records

| record | written by | where (files provider) | id |
| --- | --- | --- | --- |
| baseline version | `run-promote`, `round-close --promote` | `data/baselines/<goal>/<dataset>/<version>.json` | `baseline:<goal>/<dataset>/<version>` |
| prompt version | a run that sees new bytes, `prompt-version` | `data/prompts/<name>/<sha16>.txt` and `.json` | `prompt:<name>/<sha16>` |
| study | `study-run` (the spec is the person's file) | `data/studies/<goal>/<study>.yaml` | `study:<goal>/<study>` |
| study event | the study loop, `study-tell`, the heldout check | `data/studies/<goal>/<study>.events.jsonl` (append) | `trial:<goal>/<study>/<k>` for a trial |
| run | `experiment-run`, `import-run` | `data/<runs dir>/<run id>/` (as today) | `run:<runs dir>/<run id>` |

Runs, goals, configs, datasets, references and rounds keep their 0.4.0 files.

### Ids that never collide

- A **version id** is `<UTC time to the millisecond>_<4 hex>` (`20261027T101500.123Z_7f3a`), the same shape as a
  run id's tail; a **content id** is the first 16 hex digits of the sha256 of the bytes. Two clones never make
  the same id for different records.
- Numbers a person reads ("version 3", "v4") are computed for display: the position of the record when the
  records are sorted by time. They are never stored and never used as ids.

### Nothing derivable is stored

- **Current baseline**: the newest version of a goal on a dataset. A rollback is a new version that re-promotes an
  earlier version's run, with `rollback_of` naming it; it is newer, so it is current.
- **Versions of a prompt**: the files in its directory, sorted by `created_at`.
- **Heldout looks**: counted from the decisions recorded on a heldout dataset (baseline versions with evidence on
  it, studies' heldout checks) (RFC-015).
- **Use before 0.5.0**: counted from runs whose fingerprint names a harness before 0.5.0.
- **Spend**: summed from the runs' recorded cost.

No index, pointer, ledger or count file exists for any of these.

### The store contract (`_store.py`)

```python
class Store(Protocol):
    def create(self, kind: str, path: str, doc: dict | bytes) -> Id: ...   # fails if it exists (the one primitive)
    def get(self, id: Id) -> dict | bytes: ...
    def list(self, kind: str, prefix: str = "") -> list[Id]: ...
    def append(self, kind: str, path: str, event: dict) -> None: ...       # an event to an append-only log
```

- Records are written once and never rewritten. A change is a new record (a new version, a new event).
- `create` fails if the id exists, which with the ids above happens only on a real duplicate (the same prompt
  bytes, which is then reused). It is the only concurrency primitive the commands rely on.
- **Files provider**: `create` writes a temporary file and links it into place (`os.link`, which fails if the
  target exists); `append` writes one line with `O_APPEND`, under 4 KB so a line is never interleaved;
  `list` reads a directory. No lock files.
- **Database provider** (not in 0.5.0): `create` is an insert with a unique key, `append` an insert, `list` a query.
  The commands do not change.

### After a merge (files provider)

Git merges records that are separate files without conflict. What git cannot see, `validate` reports:

- **Two baseline versions that replaced the same version** (two people promoted on two branches): reported as a
  fork, naming both; the newer is current until a person promotes again with a reason.
- **Two decisions that took the same look number** on one heldout dataset: reported as a double-spent look, with
  both decisions; RFC-015 explains why the levels are then too generous.
- An event log with lines from two branches is merged by git as two appended blocks; `validate` checks that each
  study's trial numbers are unique and reports a duplicate.

These are the limits of a store without a centre; the database provider removes them.

## Alternatives Considered

- **Lock files and index files** (the first draft of RFC-009 and RFC-014). Rejected: they protect one machine
  against itself, conflict across clones, and duplicate what the records already say.
- **Sequential version numbers.** Rejected: they collide across branches.
- **The database now.** Deferred: 0.5.0 keeps files in git; the contract is what makes the database a provider
  rather than a rewrite.

## Testing

- `harness/tests/test_store.py`: `create` refuses an existing id; two processes creating the same content id get
  one record; `append` from eight processes keeps every line whole; ids sort by time; display numbers follow
  creation order.
- `harness/tests/test_merge.py`: two clones promote on one goal and dataset, merge, and `validate` reports the fork;
  two clones take a look on one heldout dataset, merge, and `validate` reports the double-spent look.

## Decisions (ADR candidates)

1. Every new 0.5.0 record is a write-once document with a collision-free id, written through one store contract
   whose only concurrency primitive is create-if-absent.
2. Nothing that can be derived from records is stored: no index, pointer, ledger or count files.
3. On git, conflicts that git cannot see are reported by `validate` after a merge; a database provider removes them.
