# AGENTS.md: eval-harness

Rules for coding agents working in this repository. The harness is the package in `harness/`; `infra/` is the
deployment of evals.humancopilot.eu; `docs/` holds the decisions (ADRs), designs (RFCs), product and UX specs.
`llms.txt` indexes the docs: by area of the code and by service, so you open only what your change needs
(`make llms` writes it; edit `tools/llms.in.txt`, never `llms.txt` itself).

## Observability: dev and prod

Dev and prod observability are kept apart (the contract: agentic-ai-homelab `docs/recipes/o11y-dev.md`).

- **Run the servers with the dev hooks** when a change touches them: `make serve-dev` (catalog and inspector) or
  `make mcp-dev` (the MCP server). Their errors, traces and log lines reach the dev targets labelled
  `environment=dev` and `worktree=<your branch>` (`infra/README.md`, "Dev observability").
- **Before opening a PR, run the `o11y-dev` skill** in this worktree and read your branch's errors, logs and traces.
  Fix what your change caused; leave the rest.
- **A dev error never becomes a GitHub issue**, and a dev agent never resolves, ignores or deletes a GlitchTip issue:
  `evals-dev` issues close on their own three days after they were last seen.
- **Never point a dev run at a prod target** (the hooks refuse a prod GlitchTip project in dev, and the dev project
  in prod). Prod questions use the `o11y-prod` skill; after a deploy, `deploy-verify`.
