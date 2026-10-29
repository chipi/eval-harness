# ADR-0016 — An MCP server, skills and llms.txt for agents (0.5.0)

**Status:** Accepted (2026-10-26), design; not yet built. Revision 3 (2026-10-27): no resources, no elicitation, three skills. Revision 2: no grant store, no spend ledger.
**Date:** 2026-10-26
**Detail:** [PRD-012](../prd/PRD-012-agent-ready.md) FR4, FR5, FR6, FR8,
[RFC-016](../rfc/RFC-016-mcp-server-and-skills.md)

## Context

The test for 0.5.0 is that an agent in a project, given a goal, sets up and runs a study, and the
catalog looks as if a careful person did it. Agents work best through tools with schemas and
through short procedures they can load, and an agent's client is not to be trusted for who is
acting.

## Decision

- **`evh mcp`** is a stdio MCP server for one project, built on the official Python SDK (the
  owner's decision; it brings its own dependencies, listed in the release notes). Its tools are
  generated from the command declarations, each run as a child `evh … --json` with a timeout,
  killed on cancel, its output capped. Records are read through read tools; there are no resources.
  0.4.5 shipped the read-only start early (RFC-018 on `main`): the read commands as tools, their
  schemas taken from each command's parser, over stdio and `--http` (a team's server, or the public
  one at `evals.humancopilot.eu/mcp`). 0.5.0 keeps those tools' names and answers, generates every
  tool from the declarations instead, and adds the writing tools, consent and, before they reach a
  shared server, users (RFC-016).
- **Long work returns a job id** followed with `jobs-status`; MCP tasks when the SDK implements the
  extension.
- **The server never decides who acts or consents**: the actor is fixed when it starts; actor and
  consent flags are never tool arguments; consent comes only from the person running the command the
  agent was refused with. Limits live in a tracked file the server
  never writes and reads only when committed, so every change has an author. Path arguments
  cannot reach it.
- **Budgets are checked against the spend the runs record**, with no ledger; every job runs under a
  cost cap of what is left.
- **Three skills ship with the package** in the Agent Skills format (evaluate and compare, run a study,
  follow a job), installed by a command, their commands tested in CI, and every command covered by one.
- **`llms.txt` is generated with the documentation**, and a glossary maps the harness's terms to
  other tools'.

## Consequences

An agent can do everything a person can through tools and skills, and every decision with
consequences still reaches the person. The server cannot stop an agent that also has a shell; the
records and the skills are the defence there.
