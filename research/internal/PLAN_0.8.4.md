# 0.8.4: the plan

**Status:** 2026-11-28, a first draft, written the day 0.8.3 was released (tag `v0.8.3` on `c6524b189`, GitHub Release
run `46120689274`, production deployed from the same commit, run `46121128853`, `deploy-verify --project evals` PASS).
Branch `084`, from `origin/main` at `c6524b189`. The owner is collecting feedback to decide whether 0.8.4 ships or the
work moves to 0.9.0 ([PLAN_0.9.0.md](PLAN_0.9.0.md)); this plan collects what could go in a patch meanwhile. Nothing in
it is built. The owner decides scope and order; items marked **open** wait for the owner's word.

## How this release is worked (carried over from 0.8.3)

- Quality, consistency and completeness come before the timeline. Every finding is fixed, the nits included.
- The docs describe what exists now, and every documented command works (`check_commands`, `check_shown_commands`,
  `guide-check`).
- The work goes to subagents on a lower tier (Sonnet implementers and reviewers, Haiku for mechanical work, Fable for the
  advisor). A subagent's "passes" is checked by running it again.
- Each finding gets a failing test first, then the fix.
- The gates run on a committed tree, and nothing is committed while they run.
- Real calls go through the homelab LiteLLM gateway: the release-check key (`~/.config/eval-harness/release-litellm.env`,
  `eval-gpt-mini` and `eval-claude-haiku`, $1 cap) for the real-call check; the scenario needs the project key
  (`~/.config/eval-harness/scenario-litellm.env`, key `eval-harness`, $100 cap: `eval-mistral-small`, `eval-llama-scout`,
  `eval-opus-5`), copied into the scenario project's git-ignored `.env`.
- The release follows `harness/docs/RELEASING.md`. Learned on 0.8.3:
  - `make release-smoke ARGS=--release` refuses a working copy that holds fetched gold references (the release guard,
    as designed), while `make verify`'s rescore test needs them. Run the smoke on a clean checkout of the candidate
    (a detached worktree with the venv linked), not in the worktree that ran `reproduce.py`.
  - After the deploy, `deploy-verify --project evals` needs one MCP tool call first (the skill says how): evals-mcp
    logs and traces only at startup and per tool call.

A patch release should not move a result. Each item says whether it can. One that does goes to 0.9.0 or the owner
decides.

## P. Left from 0.8.3

| Item | What | Done when | Moves a result |
| --- | --- | --- | --- |
| P1 | `run-compare` between two rounds' runs in an installed project reads `instrument differs: harness.commit` and "not a controlled comparison" when only the project's own commit moved (`commit` is the project's tree; `version` and `code_sha256` equal). **Open:** the owner put it in 0.9.0 (PLAN_0.9.0, C); it is display only, so it could be a patch | the owner's choice; if here: a moved project commit with the same `version` and `code_sha256` is named as the project's change and left out of the confounds, tested | no (display; no hash changes) |
| P2 | `comparison-show`'s Conditions showed `deployment.model` in the 0.8.3 newcomer run, where `catalog_adapter.conditions` says the arm's model is left out (what an arm varies). Not checked which is wrong | the code and its docstring agree, with a test | no |
| P3 | The note "no goal or adapter says which way is better; read as higher-is-better" is printed for runs with no goal (a job on `briefs_v2`), on judged leaderboards and in `validate`, after the goal declared `direction: higher` | said once where it applies, or the runs it covers named | no |
| P4 | The dry run's "at most" estimate for the frontier arm was 15x what it spent (`~$0.7574` at `max_tokens 1500` against $0.0489). It is the bound it says it is; a newcomer under a $1 cap hesitates | the estimate's line makes the bound's cause plain (the `max_tokens`), or the typical figure leads when one exists | no |
| P5 | The newcomer run did not exercise, for real: a 403 from a provider, the retries on a persistent 429 or 5xx, and retiring an arm from the Workbench's Close screen (covered offline: `tests/test_providers_wire.py`, the Workbench browser suites) | each exercised once, or the reason it is not written in SCENARIO | no |

## B. The beta projects on 0.8.3

| Item | What | Done when | Moves a result |
| --- | --- | --- | --- |
| B1 | robotics-evals, podcast-scraper-eval-data and fleet-eval-data move their pins to `v0.8.3`; homelab's evh-serve instances (`agentic-ai-homelab` `infra/evh-serve/instances/`) move with each project's pin | each reports `evh validate` and what moved; a break is an item here | no |
| B2 | harness-bakeoff (evh 0.8.0) and agent-rules-eval (0.8.0.dev0), paused until next week, cross 0.8.1, 0.8.2 and 0.8.3 at once | each runs the check the others ran (non-ASCII ids, `validate`, a re-read of its results); what breaks is an item here | no |

## Housekeeping

**Done 2026-11-28, the owner's go:** removed the 083, 080 (with `build/clean-wt`), 080-rfc038 and mbpp-code worktrees,
`baseline-tmp/baseline-diff-080`, the 083 branch (local and remote) and the remote `0811-fix`; the scenario folders of
0.8.0, 0.8.1 and 0.8.3 (with the scratch copy of the gateway key). The scenario key is kept once, in
`~/.config/eval-harness/scenario-litellm.env` (mode 600). Local branches 080-rfc038 and mbpp-code are kept.

- **Open:** `worktrees/044` (branch 044, no remote, last commit 2026-10-28) holds uncommitted work: 13 modified files and
  6 untracked under `site/art/` (sketches, masters, `make_sketches.py`, `experiments/`). Not removed; the owner decides.
- `/work/evh-scenario-040` and `040b` (0.4.0's scenario runs) still hold copies of the gateway key in their `.env`; not in
  the approved list.

## Not in this plan

- Everything in [PLAN_0.9.0.md](PLAN_0.9.0.md): G1-G6, V1-V4, M, C (unless P1 moves here), the removal of
  `EVAL_JUDGE_<NAME>`, and eval's answers on G1, G4 and G6 (waiting on its key's re-mint).
- Scenarios (RFC-035, RFC-036, RFC-037): 0.9.0.

## Where the evidence is

- **0.8.3's release:** PR #41 (its description lists every gate and the scenario's result); the tag `v0.8.3`; release run
  `46120689274`; deploy dry run `46120787656` and deploy `46121128853`.
- **The 0.8.3 newcomer run:** `/work/evh-scenario-083` (the project) and `/work/evh-scenario-083-notes` (NOTES, spend,
  screenshots); SCENARIO's "Still open"; $0.17 billed.
- **Plans:** [PLAN_0.8.3.md](PLAN_0.8.3.md), [PLAN_0.9.0.md](PLAN_0.9.0.md).
