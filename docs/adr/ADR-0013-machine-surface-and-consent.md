# ADR-0013 — One declaration per command; JSON, exit codes, refusals, actors, consent (0.7.0)

**Status:** Accepted (2026-10-26), design; not yet built. Revision 3 (2026-10-27): one consent path; a smaller exit-code table. Revision 2: no grant store: consent is the person's own command.
**Date:** 2026-10-26
**Detail:** [PRD-012](../prd/PRD-012-agent-ready.md), [RFC-013](../rfc/RFC-013-machine-surface.md)

## Context

An agent could use the harness only by running commands and reading tables. Nothing described a
command's arguments outside running it; results and progress shared stdout; exit 1 meant a refusal,
nothing measured and a failed check alike; records did not say who acted; and a decision with
consequences (a promotion) was the same whether a person or an agent made it.

## Decision

- **Each command declares itself once** beside its `argparse` parser (purpose, effects, consent
  kinds, output schema, examples). Help, `evh commands --json` and the MCP tools are generated
  from it.
- **Results on stdout, everything else on stderr**; `--json` everywhere with an output schema per
  command; `--dry-run` writes and calls nothing.
- **Exit codes are a table**: 0, 1 refusal, 2 usage, 3 judge not validated (unchanged), 4 budget, 5 partly failed,
  6 a check found problems, 7 nothing measured, 70 internal error, 75 try again later, 130 interrupted; kinds of
  refusal are told apart by the refusal's code. Splitting
  1 and 2 is a breaking change; no code changes its 0.4.0 meaning.
- **Refusals are RFC 9457 problem details** with a stable `type` from a registry.
- **Every record says who acted and for whom** (PROV); an actor that does not name itself and is
  not on a terminal is recorded as `unknown`, never as a person.
- **Consent is a person's, never only an agent's**: asked at run time by kind (promotion, an extra
  look, an override, spending, a shared host) and given only by the person running the command (the
  refusal an agent gets names the exact command, which the person runs with `--confirm`). Nothing is
  stored between asking and consenting. An agent's own `--confirm` is refused.
- **One project `config.yaml`** for directories, runners and limits; environment variables win.
- **Python 3.10 or later**, so the official MCP SDK can be a default dependency.

## Consequences

Every command is usable by an agent without parsing tables, and every decision is attributable.
The harness cannot prove a claimed person is one: an agent with a shell can impersonate one. The
records show the route each consent took, so a person can audit them.
