# ADR-0024 — Several projects run on one machine, and share nothing (0.6.0)

**Status:** Accepted (owner, 2026-11-01), with RFC-023; built in 0.6.0 (2026-11-01).
**Date:** 2026-11-01
**Detail:** [RFC-023](../rfc/RFC-023-labels-and-references.md) (several projects in parallel),
[PRD-007](../prd/PRD-007-packaging-and-providers.md) (FR2.5 to FR2.7), [PRD-004](../prd/PRD-004-catalog-and-inspector.md) (FR2.7)

## Context

A project is a folder with its own `data/`; the owner works on several at once, as several checkouts, each pinning
its own harness version. What a project writes is already its own (data, runs, `.cache/`, `.build/catalog`), but
three things are not: `catalog-serve` and `mcp --http` take fixed ports (8765, 8766), so a second project is told
the port is in use; `EVAL_HOME` and the `EVAL_*_DIR` variables in a shell send every command to one project
wherever it runs; and a model record is written under a lock in the system's temporary folder keyed only by the
model's id, which two projects share.

## Decision

- Each project gets a **stable port of its own**, derived from its path, the next free one if that is taken;
  `catalog-serve` and `mcp --http` print the URL, and `--port` overrides.
- The project is **named** where two can be confused: `catalog-serve` prints it, and a local catalog (the default
  name, no `--link`) shows it in its header and tab title. Every command notes on stderr when `EVAL_HOME` points
  away from the project of the folder it runs in.
- A lock is keyed by **what it protects inside the project** (a model record's path), never by a name two projects
  share.
- A test runs two projects at once: both serve, write their records and run their arms, and neither sees the
  other's.

## As built (0.6.0)

- The ranges: `catalog-serve` in 18000–18999, `mcp --http` in 19000–19999, at the same offset (from the root's
  resolved path), so a project's two servers read as a pair; the next free port when one is held, probed as the
  servers bind (`SO_REUSEADDR`, so a port a stopped server left in TIME_WAIT is still its own).
- `--public` keeps 8765 as its default (a deployment names its port anyway); `--port` overrides everywhere.
- `harness/tests/test_parallel_projects.py`: two projects serve at once, each its own catalog; the same port on a
  restart, the next one when held; the MCP port at the catalog's offset; the EVAL_HOME note; two model locks.

## Consequences

- Two catalogs open side by side, each at the same URL every time, each saying which project it shows.
- A shell left pointing at one project says so instead of writing there silently.
- What two projects share on purpose (one model server, one GPU) stays outside the harness.

## Alternatives considered

- **Keep fixed ports; pass `--port` by hand.** Rejected: every second project fails first.
- **A random free port each time.** Rejected: the URL changes on every start.
