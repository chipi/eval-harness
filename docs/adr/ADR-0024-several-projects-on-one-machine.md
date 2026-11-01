# ADR-0024 — Several projects run on one machine, and share nothing (0.6.0)

**Status:** Proposed (2026-11-01), agreed with the owner in RFC-023's review; accepted when RFC-023 is.
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
- Commands **name the project** they act on, and warn when `EVAL_HOME` points away from the folder they run in.
- A lock is keyed by **what it protects inside the project** (a model record's path), never by a name two projects
  share.
- A test runs two projects at once: both serve, write their records and run their arms, and neither sees the
  other's.

## Consequences

- Two catalogs open side by side, each at the same URL every time, each saying which project it shows.
- A shell left pointing at one project says so instead of writing there silently.
- What two projects share on purpose (one model server, one GPU) stays outside the harness.

## Alternatives considered

- **Keep fixed ports; pass `--port` by hand.** Rejected: every second project fails first.
- **A random free port each time.** Rejected: the URL changes on every start.
