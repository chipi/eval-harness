# ADR-0017 — Write-once records with collision-free ids, through one store contract (0.5.0)

**Status:** Accepted (2026-10-27), design; not yet built. Added in revision 2.
**Date:** 2026-10-27
**Detail:** [RFC-017](../rfc/RFC-017-record-store.md) (records, ids, the contract, what `validate` reports after a
merge)

## Context

0.5.0 adds records (baseline versions, prompt versions, study events, decisions on heldout data). The first drafts
stored them with sequential numbers, index files, pointer files, lock files, a look store and a spend ledger. The
harness is meant for teams: first several clones of one repository, merged through git, then a shared database. A lock
file protects one machine, not two clones; sequential numbers collide across branches; an index file every write
edits conflicts on every concurrent change; and a stored count or total drifts from the records it summarises.

## Decision

- **Every new record is written once**, with an id that two clones cannot both make: a time-and-suffix id, or a
  content hash. Numbers a person reads ("version 3") are computed for display.
- **Nothing derivable is stored**: the current baseline is the newest version; a prompt's versions are its directory;
  heldout looks are counted from recorded decisions; use before 0.5.0 and spend are computed from runs. No index,
  pointer, lock, look or ledger file.
- **One store contract**: create-if-absent, get, list, append. The files-in-git provider implements it with plain
  files; a database provider will implement it with transactions, without changing the commands.
- **What git cannot see, `validate` reports after a merge**: a baseline promoted on two branches (a fork), two
  decisions with one look number, a duplicate trial number.

## Consequences

Records merge cleanly and the data tree stays readable by hand: one file per thing that happened. Two conflicts stay
possible on git and are reported rather than prevented; the database provider removes them.
