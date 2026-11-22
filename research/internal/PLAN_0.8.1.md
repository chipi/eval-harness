# 0.8.1: the plan

**Status:** 2026-11-22, written the day 0.8.0 was released (tag `v0.8.0` on `094aa680a`, GitHub Release with the
wheel and sdist, production deployed from the same commit). Branch `081`, from `origin/main` at `094aa680a`.
Everything below is what 0.8.0 left open, found while hardening and releasing it. Nothing in it is built.
The owner decides scope and order.

## How this release is worked (the owner's rules for 0.8.0, carried over)

- Quality, consistency and completeness come before the timeline. Every finding is fixed, the nits (N) included.
- The docs describe what exists now, and every documented command works (`check_commands`, `check_shown_commands`,
  `guide-check` prove it).
- The work goes to subagents: Explore, implementer and docs-writer on Sonnet; tester on Haiku; never Opus. A
  subagent's "passes" is checked by running it again: a Haiku tester said Playwright was missing and never ran its tests.
- Each finding gets a failing test first, then the fix.
- The gates run on a committed tree, never while an agent is still editing. The full set is
  `~/.cache/evh-tests/runner/step3_gates.sh` under the `long-job` skill. Watch it with Monitor.
- The owner approves every push; for 0.8.0 an arc approval covered pushes of the branch, never main.
- Merge, tag and deploy need the owner's go.
- The release follows `harness/docs/RELEASING.md`.

## The order (recommended)

1. **Trust first**: T1 (the paid run path), T2 (release tags).
2. **CI that fails only for real**: C1 (tests that time out under load), C2 (fonts in layout checks), C3 (the SQLite
   browser gaps).
3. **The process**: P1 (production deploys on every push), P2 (the size of a release's notes), P3 (`make site`
   without a store).
4. **Small items**: S1 to S4.
5. **The new features**: F1 and F2 (both in 0.8.1, the owner's decisions of 2026-11-22 and 2026-11-23).

A patch release should not move a result. Each item below says whether it can. If one does, it goes to 0.9.0 or
the owner decides.

## T. Trust

### T1. The Workbench's paid run, end to end

**What is open.** No gate and no scenario run has pressed "Run them" with money behind it. The pieces that are
untested together:

- "See the cost first";
- the spend cap a run takes from the round's budget;
- a run over uncommitted files recorded dirty (`evh runs-list` stars it and prints the legend);
- the commit notice above the button (UXS-005), checked so far at 1400 px only.

The 080d replay stopped before the spend (owner's rule: no paid run in the re-check).

**Done when:** a browser test drives the real path against a stub provider that bills (no real money), and asserts:

- the estimate shown;
- the cap passed to the job;
- the run's `build.dirty` with and without a commit;
- the legend in `runs-list`;
- the notice above the button at 390 px.

Then one real run of under $0.05 in a scenario project, read by eye.

**Moves a result:** no.

**Found by the real run (2026-11-22, `/work/evh-scenario-081t1`, $0.00017 on `eval-mistral-small`):**

- **T1a. The estimate's dollar figure is hidden.** "See the cost first" shows the whole dry run in a `.reply` box capped
  at 252 px (`workbench.css:486`); the `ESTIMATE ~$…` and `cap` lines are below its fold, at 1400 px and at 390 px. The
  filter to the cost lines (`live.js:1048`) applies only to `result.blocks`, and the sweep estimate's answer had none,
  so the page fell back to the full text. The browser test read the text, not what is visible, so it passed.
  - **Done when:** the estimate and the cap are visible without scrolling the box, at 1400 and 390 px, proved by a
    browser check that fails before the fix.
- **T1b. `runs-list` showed an unknown tree as clean.** Fixed in `663fc3265` (`?` and `dirty: null`).

### T2. Can a release tag move?

**What is open.** On 2026-11-22 the `release tags` ruleset (target `refs/tags/v*`, rules `deletion`,
`non_fast_forward`, `update`) refused `git push origin --delete v0.8.0` with "Cannot delete this tag". The very next
`git push origin v0.8.0`, with the tag now on another commit, succeeded: `git ls-remote` showed `v0.8.0` on
`094aa680a`, where it had been on `448d34baa`.

- The ruleset's bypass list is the admin repository role (`actor_id` 5, `always`). That may be why.
- RELEASING.md says the ruleset blocks updates and deletions "so a released tag cannot move under its users".
- No Release existed for the old tag, so nothing pinned was broken.

**Cause (found 2026-11-23, `gh api repos/chipi/eval-harness/rulesets/rule-suites?ref=refs/tags/v0.8.0`):** the
delete was not refused, it was bypassed. Rule suite `5291225265` (16:34:45): `result: bypass`, its `deletion` rule
`fail` ("Cannot delete this tag"), let through by the bypass actor (repository role 5, admin, `always`; the only
collaborator, `chipi`, is admin). Rule suite `5291225643` (16:34:47): `pass`, `before=0000000 after=094aa680a`: a tag
created anew, and the ruleset has no `creation` rule. So an admin can move any release tag: delete (bypassed), then
create. Recommended: remove the bypass actor (a mistaken tag is then fixed by editing the ruleset on purpose, which
leaves a trace), keep creation allowed (the release workflow creates tags), and RELEASING.md says so. A change to the
live repository: the owner's go.

**Done when:** the cause is known from GitHub's rule evaluation (the ruleset's insights page or its API), and either:

- the ruleset holds against an admin's push too (bypass only on a pull request, or none), or
- RELEASING.md says plainly who can move a tag.

**Moves a result:** no.

## C. CI that fails only for real

### C1. Tests that fail under machine load

**What is open.**

- **`tests/test_workbench_live_browser.py` failed twice on 2026-11-22**, each time with the load average around 11 to 12:
  - `Page.reload: net::ERR_NETWORK_CHANGED` at `rail_of`, line ~2406;
  - `Page.wait_for_selector("main h2", timeout=20000)` on a round page, line ~2383.

  Each time it then passed 240/240 when run alone, once at load 12.
- **`test_prefetch.py`** failed "the children ran at the same time (3.3 s against 1.9 s one by one)" while the store
  matrix ran 6 jobs beside it. Alone it passed 32/32 (0.3 s against 0.9 s).

The cause of neither is known.

**Done when:**

- each is reproduced on purpose (`EVH_TEST_SLOW_MO`, `EVH_TEST_FETCH_DELAY_MS` and CPU load from `stress-ng`, if the
  owner approves installing it);
- the cause is named;
- the test either waits on the state it needs (not a fixed 20 s) or, for the timing check, measures what does not
  depend on load (CPU time, or the number of children alive at once).

A timeout made larger with no cause found is not a fix.

**Moves a result:** no.

### C2. Layout checks depend on the machine's fonts

**What is open.** Two of 0.8.0's CI failures were widths that fit locally and not in CI, where the fonts are wider:

- the goal page's answers table on `triage_orrery`: 1002 px locally, 1061 px in CI, of a 1132 px box;
- three Workbench placeholders at 390 px: 301, 308 and 331 px needed in CI, 298 px available.

The fixes left margin (about 17 % on the placeholders, the table at 76 % of its box locally). The next near-miss will
fail the same way.

**Done when:**

- the browser tests load one bundled font (as a test-only stylesheet, so the product is unchanged) and use it on every
  machine;
- the checks keep their thresholds;
- a test that fails in CI fails locally too (proved by narrowing one box until both fail at the same width).

**Moves a result:** no.

### C3. The inspector and the real catalog are not browser-tested on SQLite

**What is open.** In the 080 worktree:

- `EVAL_STORE=sqlite tests/test_inspector_browser.py` errors "no field set 'tickets'";
- `EVAL_STORE=sqlite tests/test_catalog_real_browser.py` times out at line ~694 (`wait_for_selector("span.chip.v-better…",
  timeout=120000)`), with and without 0.8.0's last changes.

The store matrix skips every `*_browser.py`, and `make browser-check` runs them on files only.

**Done when:** both run on SQLite (their fixture written to the store the test runs on), pass, and
`make browser-check` runs them on both stores, or the owner decides a store's browser coverage is files only and the
Makefile says so.

**Moves a result:** no.

## P. The process

### P1. Every push to main deploys to production at once

**What is open.**

- **Pushes deploy.** `.github/workflows/deploy-*.yml` deploys on a push once the repository variable
  `PROD_AUTO_DEPLOY` is `"true"`, and it is.
- **The dry run was skipped.** On 2026-11-22 the owner approved "a dry run, then the real deploy" for the Alloy fix,
  and merging PR #36 deployed for real before any dry run.
- **Deploys can surprise.** The deploy before it failed safely, at its Alloy check, before switching releases. A
  push of 0.8.0's merge was a deploy nobody had asked for in so many words.

**Decided (owner, 2026-11-22):** auto-deploy is off; a deploy is its own step, run from make.

**Done when:**

- `deploy-prod.yml` has no `push:` trigger, only `workflow_dispatch`, so `PROD_AUTO_DEPLOY` no longer decides
  anything;
- `make deploy-dry` dispatches the workflow with `dry_run: true` and watches it to its end;
- `make deploy` dispatches the real deploy, and refuses unless a dry run of the same commit passed;
- RELEASING.md, the deploy recipe and the workflow's header say a merge to main deploys nothing;
- the repository variable `PROD_AUTO_DEPLOY` is deleted, on the owner's go (a change to the live repository).

**Moves a result:** no.

### P2. A release's notes are too long to read

**What is open.**

- **The section broke the Release.** The 0.8.0 CHANGELOG section is 161,797 bytes. Its first release run failed:
  "body is too long (maximum is 125000 characters)". `harness-release.yml` now cuts a section past 120,000
  characters to its opening, its headings and a link (#36), so the Release exists.
- **Nobody reads that much.** A section that size is not read, and the docs site and the site's release-notes page
  show all of it.

**Decided (owner, 2026-11-22):** a short CHANGELOG section that links to the full notes in `docs/`, not a cap.

**Done when:** a release's CHANGELOG section is short and links to its full notes in `docs/`; RELEASING.md says
so, `site/releases.py` and the docs site show the short section with the link, and `harness-release.yml`'s cut
is no longer reached by a release written this way.

**Moves a result:** no.

### P3. `make site` without a store rewrites the site

**What is open.** An agent reported that `make -C harness site` without `EVAL_STORE=files` rewrote or deleted most of
`site/public` and `site-check` then failed; with `EVAL_STORE=files` it is clean. The gates and CI set it, so nothing
caught it. The cause was not looked for. (0.8.0 has no default store: `evh init --store files|sqlite`.)

**Done when:** `site/build.py` and the site Makefile targets either refuse with `ERROR (not-configured)` naming the
variable, or read the store from the repository's own `harness/config.yaml`. A test runs `make site` with no
`EVAL_STORE` and fails before the fix.

**Moves a result:** no.

## S. Small items parked during 0.8.0

- **S1. The sheet's arm names.** 0.8.0's fix gave the inspector one naming rule: drop only the dataset id prefix,
  always keep the " · …" tail and ×N. The sheet view still uses the old shared-prefix rule, because its names are
  paths (`rescored-…/…/triage_baseline_pro_v1`); see `shorten()` in `harness/catalog_assets/inspect.js`, the sheet
  call without `dsOf`, about line 790.
  - **Done when:** one rule for every view, with a browser check.
  - **Moves a result:** no.
- **S2. A crowded scatter's labels.** In the judged 4-arm scatter the `lead1` label still lies over a few dots in the
  crowded lower left: when no clear place exists, the placement falls back to the old rule so a name is never left
  out.
  - **Done when:** the label moves to a leader line or the legend when no clear place exists.
  - **Moves a result:** no.
- **S3. `check_hf_source.py` and a Hugging Face 502.** On 2026-11-21 a 502 failed the ag-news rerun job once, and
  rerunning that one job passed (run `44822094401`, attempt 1). The 502 came from the datasets-server's `/rows`,
  which the script reads only to compare (`rows_api`, line 57), and `rows_api` already retried it: 4 tries, 30 s of
  sleeps, on any exception, a 4xx included.
  - **Decided (owner, 2026-11-22):** retry 5xx and connection errors only, with a longer bounded backoff (about
    2 min), each retry logged; a 4xx fails at once; still 5xx at the end exits 1 with one line ("datasets-server
    /rows unavailable (502) after N tries: not a difference"), never a skip.
  - **Done when:** a test with a stubbed `urlopen` proves 502, 502, 200 passes; 404 fails with no retry; 502 every
    time fails with that line.
  - **Moves a result:** no.
- **S4. Leftovers that are harmless and should go.**
  - **Mockup text:** dead mockup text in `harness/workbench/workbench.js`, and `0.8.0.dev0` in
    `harness/workbench/mockup/mock.js`, which the live Workbench does not load.
  - **Untracked file:** `server.pid` at the repository root of the 080 worktree, untracked; check what writes it and
    ignore it or stop it being written.
  - **Done when:** they are gone or ignored, with `make quality` green.

## F. Features (in 0.8.1: owner, 2026-11-22 and 2026-11-23)

### F1. Where the judge and the gold disagree, on the inspector

From the 080d screenshot review (inspector part 3, #9). An item page shows the judge's verdicts and the reference,
but not whether the judge agreed with the gold on that item. A marker per item, and a filter "the judge disagrees with
the gold", would let a reader find the items that make a judge's validation figure.

- **Scope:** UXS-002 first, then the page.
- **Moves a result:** no. It is new behaviour; the owner wants it in 0.8.1 all the same.

### F2. The Workbench, read-only, on the deployed site

**Decided (owner, 2026-11-23):** a visitor who is not signed in sees the Workbench as a viewer: everything readable,
nothing written, nothing spent, no token. This amends PRD-017's non-goal "a public, multi-user service" and D8 ("the
Workbench is refused behind a proxy"), so a decision record (an RFC or ADR amending D8, `new-doc`) comes first.

**What is there now.** `catalog_serve.py:617-623` answers 404 for `/api/v1/` and `/workbench/` on any public or
proxied server. Writes and spends already need the server's token, and operations already split reads from jobs
(`op.is_job()`; MCP marks the reads `read_only_hint`).

**What the deployed copy holds (checked 2026-11-23),** so what a viewer could read: no item text (dataset records
carry row numbers and hashes; `data/materialized/` is gitignored, `harness/.gitignore:5`); the arms' outputs (313
`outputs.jsonl`, already published by `--publish outputs`); gold references as manifests, except 132 one-word Orrery
triage labels; no dataset is `text: hidden`. For this site nothing private is exposed. For a project that commits
text, the reads must still follow the public text rules.

**Done when:**

- the decision record amends D8 and PRD-017, and UXS-005 describes the viewer;
- on a public server, `/workbench/` and the `/api/v1` read operations answer without a token; every job (write,
  spend, run a model) and `POST /estimate` (it starts a child process) is refused without one, tested at the server,
  not only in the page;
- with no token, the page shows no control that acts (open, run, estimate, close, retire, carry in, promote, the
  screens that exist only to act) and says it is a read-only view and how to run your own;
- every read served publicly applies `_visibility.text_shown(..., public=True)` and the `--publish` setting, as the
  public inspector does: a browser test on a fixture with a `text: hidden` dataset shows none of its text, and a
  request for the sheet or an item's input is refused;
- the reads are under the public inspector's rate limit and memory budget (256 MiB, `budget-check`);
- `infra/` serves it on evals.humancopilot.eu (compose and Caddy), the site and catalog link to it, and
  `deploy-verify` passes after the deploy.

**Moves a result:** no.

## Not in this plan

- **The Qwen subscription** as a judge or an arm. The owner, 2026-11-21: "leave this as it is right now".
- **The beta users' own projects.** They own their migrations. 0.8.0's two `evh migrate` fixes for imported runs (steps
  4 and 6) are released, and podcast-scraper-eval-data migrated and validated on them (its session, 2026-11-22).
- **0.8.0's known-limits list** (the "Not covered" of PR #33): an Intel-Mac install, gated or private datasets on
  Kaggle and the Hub, and publishing to the Hub beyond the one live check. These stay as they are unless the owner
  asks.

## Where the evidence is

- **0.8.0's last scenario run:** findings in `~/.cache/evh-tests/080d-review/` (scenario.md, the six screenshot
  reviews, recheck2.md); the project in `/work/evh-scenario-080d`; screenshots in `~/.cache/evh-scenario-080d-shots/`.
- **The release:**
  - PR #33 (the 0.8.0 squash): its description lists what was checked and what was not.
  - PR #36: the release-notes cut and the Alloy check.
  - Release run `45039096650`.
  - The deploy of `094aa680a`, run `45036678416`.
- **Plans:** this plan's predecessor is [PLAN_0.8.0.md](PLAN_0.8.0.md).
