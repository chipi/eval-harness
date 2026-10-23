# Handover: harness 0.4.0 (catalog, inspector, goals, VPS move)

**To:** the "eval on omarchy" agent, which owns this work from 2026-10-22. It can talk to the
prod session and the other agents; the cloud session that wrote this cannot.

**From:** the cloud session that built layers 1–4b (Claude-Session
`session_018c4N2pyntad3mUe32DavDa`).

Facts and locations only. The design and every owner decision are in
[`docs/adr/ADR-0002-catalog-inspector-goals.md`](../../docs/adr/ADR-0002-catalog-inspector-goals.md).
The release notes so far are in [`harness/CHANGELOG.md`](../../harness/CHANGELOG.md) under
`0.4.0 — unreleased`. The VPS runbook is [`infra/README.md`](../../infra/README.md).

## Where things are

| what | where | state |
|---|---|---|
| the 0.4.0 work | branch `harness-0.4.0`, chipi/eval-harness PR #22 (draft) | layers 1, 2, 3 and 4b (code) pushed; `make ci` green; GitHub CI green on the last checked head |
| old branch name | `claude/friendly-cerf-6vs6nj` on GitHub | already merged history; the cloud session could not delete it: **delete it** |
| podcast repo | chipi/podcast-scraper-eval-data, `master` (806a231), pins harness v0.3.0 | its own catalog/inspector in `tools/catalog/` (the code layer 2 was ported from) |
| issue #7 (judge the dev paragraph summaries) | chipi/podcast-scraper-eval-data #7 | body rewritten 2026-10-21 for v0.3.0 and master; not started. It needs the LiteLLM proxy, so it was always yours |
| deploy template | chipi/humancopilot.eu (`infra/`, `.github/workflows/deploy-prod.yml`) | copied and adapted into `infra/` |
| prod facts | the prod session's scratchpad `evals-on-prod-vps.md` (its own write-up) | tailnet name, host key, ports, the Umami id, GlitchTip; kept out of this public repo on purpose |

## Owner decisions (all 2026-10-21/22, also in ADR-0002)

1. **Exact p-values in `pair-test`/`family-test` at 30 items or fewer.** Yes. No published
   verdict moved: all 201 report claims re-derive unchanged.
2. **Goals:** required only from a date a project sets (`data/goals/policy.yaml`
   `required_from`). None is set here.
3. **The harness's own catalog is public.**
4. **No intermediate releases.** One branch, layer by layer, one 0.4.0 release.
5. **Hosting:**
   - `evals.humancopilot.eu`: the findings site, moving to the prod VPS;
   - `catalog.evals.humancopilot.eu`: the catalog and inspector of the example experiments,
     treated as a full deployment of the harness, item outputs shown;
   - `docs.evals.humancopilot.eu`: the docs, on GitHub Pages.
6. **CSP reports:** GlitchTip project `evals-web` (id 36), created 2026-10-22, through the
   shared `telemetry.humancopilot.eu` vhost; `infra/sites/*.cfg` holds the report URI.
7. **Branch names:** meaningful, never `claude/...`.

## Done (on the branch)

- **Layer 1, stats:**
  - `harness/scripts/stats.py` is the one paired test (`exact_p`, `sign_flip_p`, `holm`,
    `exact_ci`, `compare`). `pair_test.py` and `family_test.py` call it.
  - Exact at 30 items or fewer; above that, the old seeded estimate, bit for bit.
  - The exact count is ~4× faster (sums by doubling), and `exact_ci` bisects 30 steps
    (1.4 s at n=30).
  - Tests: `scripts/test_stats.py` (23).
- **Layer 2, catalog:**
  - `catalog_adapter.py`: the `Adapter` protocol, plus `HarnessAdapter`, whose arm id is
    `<runs dir>/<dataset_id>/<config_id>`, repeats averaged as `pair-test` does.
  - `catalog_build.py` (`evh catalog`), `catalog_serve.py` (`evh catalog-serve`), and the
    front-end in `harness/catalog_assets/` (packaged).
  - API: `/api/compare`, `/api/item` (was `/api/episode` in the podcast repo), and
    `/api/health`.
  - Tests: `tests/test_catalog.py` (33).
- **Layer 3, goals:**
  - `schemas/goal.schema.json` and `data/goals/*.yaml` (the six experiments), plus
    `tutorial/goals/tickets_summary.yaml`.
  - `goal:` and `format:` on configs: `experiment-run` refuses an unknown goal and records
    both on the run; `run-promote` carries them onto the baseline.
  - validate V14, and the goal pages.
  - Tests: `tests/test_goals.py` (14).
- **Layer 4b, VPS code** (see `infra/README.md`):
  - `infra/` follows the box's tenant pattern: `evals-nginx` on 127.0.0.1:8096, and
    `evals-inspector` on 127.0.0.1:8097 (stock `python:3.12.14-alpine3.23` by digest,
    running the release's own `catalog_serve.py --public`).
  - Deploy: `render.sh` builds the release in CI; `deploy.sh` runs on the box.
  - The workflow is `.github/workflows/deploy-prod.yml`; `pages.yml` publishes the docs only.
  - `site/csp.py` moves the findings site's inline scripts and styles into files, so the CSP
    needs no `'unsafe-inline'`.
  - Site changes: a 404 page; analytics from `analytics.humancopilot.eu`; the privacy page
    reworded for the VPS; docs links pointing to the docs host.

## Verified, and how to re-verify

- `cd harness && make ci` (about 15 minutes) must end with `ci: green`. It includes all
  201 report claims, the site check, and the three new suites.
- **The deploy, on a local Docker.** The cloud session had to start `dockerd` by hand, with
  the proxy variables.
  1. `bash infra/deploy/render.sh /srv/evals/releases/<sha12> <sha12>`
  2. `ln -sfn /srv/evals/releases/<sha12> /srv/evals/current`
  3. `bash /srv/evals/releases/<sha12>/deploy/deploy.sh`

  Steps 1–4 passed: nginx -t, the switch, both containers healthy, both hosts 200/404, the
  inspector answering a real comparison with the same p as `pair-test` (0.1360 on the CNN
  anthropic_l/m pair). It stops at step 5 without the box's Alloy, which is expected.
  `ss` was missing on that machine and is on the box.
- **A browser on both hosts under the production CSP** (Playwright routing the hostnames to
  the containers, as Caddy will): zero violations. The site pages were pixel-identical
  before and after `csp.py` at 1280 and 390 px wide.
- **Not verified (no access):** the real box (Alloy, Caddy, `install_vhosts.sh`), certificate
  issuance, Cloudflare, and the tailnet join from Actions.

## What is left, in order

### A. VPS cutover (layer 4b, operator plus prod session)

Everything is in `infra/README.md` ("One-time setup", "Cutover"). In short:

Status 2026-10-22: steps 1 and 2 are done (the environment read back with `gh secret list` /
`gh variable list --env prod`, branch policy `main`; the prod session reported its side, with
the key's fingerprint). Step 3 is done too
(GlitchTip `evals-web`, below).
`main` is protected: required checks `verify`, `browser` and the three `rerun` jobs.

1. **GitHub `prod` environment** on chipi/eval-harness, `main` only:
   - secrets `TS_OAUTH_CLIENT_ID` and `TS_OAUTH_SECRET` (a Tailscale OAuth client of this
     repo's own, `tag:gha-deployer`), and `PROD_SSH_PRIVATE_KEY` (minted by the operator,
     comment `gha-evals-deploy`);
   - vars `PROD_TAILNET_FQDN` and `PROD_SSH_HOST_KEY`, copied from chipi/humancopilot.eu's
     `prod` environment.
2. **Prod session:**
   - create `/srv/evals` (deploy:deploy 0755);
   - add the deploy key's public half with a tailnet `from=`;
   - add `evals-nginx` and `evals-inspector` to podcast_scraper's `unscoped.alloy`;
   - record ports 8096 and 8097 in ADR-114;
   - review `infra/` before the first deploy.
3. **GlitchTip:** done 2026-10-22: project `evals-web` (36); `CSP_REPORT_URI` in both
   `infra/sites/*.cfg`; a probe report returned 201, appeared as an issue, and was deleted.
4. **The cutover** (`infra/README.md`, "Cutover, in this order", is the source):
   - merge PR #22. Nothing deploys by itself: a push deploys to the VPS only once the repo
     variable `PROD_AUTO_DEPLOY` is `true`, and publishes the docs only once
     `DOCS_ON_OWN_DOMAIN` is `true`; both start unset, so Pages keeps serving the harness site;
   - after layer 4, date the CHANGELOG and tag `v0.4.0`: the deployed pages show `@v0.4.0`
     install lines, so the tag comes before the first deploy;
   - dispatch `deploy-prod` with `dry_run=true`, then for real (loopback only), then set
     `PROD_AUTO_DEPLOY`;
   - Cloudflare: `evals.` and `catalog.evals.` get A + AAAA to the VPS, proxied;
     `docs.evals.` gets a CNAME to `chipi.github.io`, DNS only;
   - set the Pages custom domain to `docs.evals.humancopilot.eu`, dispatch `pages`, set
     `DOCS_ON_OWN_DOMAIN`;
   - add `evals` and `catalog` to `infra/caddy/enabled.txt` and push.

   **Never list a vhost in `enabled.txt` before its DNS points at the box:**
   `install_vhosts.sh` checks that a name resolves, not where, and Caddy would burn Let's
   Encrypt attempts.

The merge is the operator's. Decided 2026-10-22: PR #22 merges to main first, after the
operator's manual review of the docs, catalog and inspector; layer 4 (the podcast repo on the
harness, including the read-only audit of its dataset registry that replaces the lost
dataset-registry note) follows on main, and what it finds is fixed before 0.4.0 is tagged.

### B. Layer 4: the podcast repo on the branch (the proof the split is right)

The podcast repo's own catalog and inspector must become an adapter over the harness. Its
pages must stay the same, apart from intended changes.

- **Pin** `evaluation-harness @ git+https://github.com/chipi/eval-harness@<branch head sha>#subdirectory=harness`
  in its `pyproject.toml`.
- **Turn `tools/catalog/podcast_adapter.py` into a class** implementing
  `catalog_adapter.Adapter`. The mapping:

  | protocol | podcast function |
  |---|---|
  | `arms()`, `arms_of(path)` | `arms_of` (paths are data/eval-relative; arm ids may carry `#engine`) |
  | `describe` | `describe` (add `reference`, `goal`, `format` keys if present) |
  | `scores(arm, rescore)` | `scores`; set `can_rescore = True` |
  | `recorded_means`, `input_hashes`, `notes` | the same names |
  | `lower_is_better`, `is_neutral` | the same names |
  | `references()`, `reference_format(ref)` | the same names |
  | `reference_archived(ref)` | `(_reference(ref) or {}).get("archived")` |
  | `output_format(arm)` | `summary_format(EVAL / split_arm(arm)[0])` |
  | `item_view(arm, item)` | `episode_view` |
  | `reference_view(ref, item)` | the same name |
  | `goals()`, `goal_of(arm)` | read `data/eval/goals/*.yaml` |
  | attributes | `item_word = "episode"`, `data_dir = EVAL`, `shape_metrics = ("output words", "latency_s")`, `preferred_metrics` = the old `serve.PREFERRED` |
- **Serve** with `evh catalog-serve --adapter tools/catalog/podcast_adapter.py:Adapter`,
  pointing `--build-dir` at the podcast build. Then delete `tools/catalog/serve.py`,
  `inspect_core.py` and the `assets/` copies.
  - The harness server serves the build dir and `data_dir` only. The podcast build lives in
    `.build/catalog`, and its "files" links point into `data/eval/`, so check they still open.
  - The podcast `assets/inspect.js` used `/api/episode?ep=`; the harness's uses
    `/api/item?item=`, with views keyed by arm id. Use the harness's assets.
- **Move its second registry into item fields** (ADR-0003). The podcast datasets keep facts
  about each episode (title, show, duration, links) in a registry beside the frozen dataset.
  Not yet done; it is part of this switch:
  - declare them in a field set, `data/eval/fields/<id>.yaml` (`schemas/fieldset.schema.json`),
    marking `public` only what the public catalog may show;
  - attach the values with `evh dataset-create --dataset-id <id> --update-fields --fields
    <file>`: no run's fingerprint changes, because fields are not the identity;
  - items published as audio at a URL come in through `--manifest` (`source_url` +
    `source_sha256`), so `dataset-materialize` fetches and hash-checks them;
  - give the adapter `item_fields(dataset)`, or let `HarnessAdapter` read the datasets, so
    the catalog and inspector show, filter and break down by them;
  - `evh validate` V15 passes, and the old registry is deleted.
- **`tools/catalog/build.py` stays project-side** (its pages are podcast-specific).
  - Swap its `page()` shell and its assets for the harness's: `catalog_build.page` takes
    `nav`, `brand`, `item`, `serve` and `footer`, and `copy_assets`.
  - Keep its podcast-only pages.
  - `goals.py` can call the harness goal pages, or stay.
- **Proof:**
  - its full suite (1,212 passed and 4 skipped on 0.3.0) passes;
  - `make catalog` gives the same pages: diff `.build/catalog` before and after; the only
    changes are the intended ones (the API path, item vs episode wording only where the
    harness assets changed it);
  - `make validate` passes (its own A10 goals check can then defer to harness V14 or stay).
- **Watch for:** the podcast repo's tests import `tools.catalog.inspect_core`
  (`tests/unit/tools/test_inspect_core.py`) and `serve` (`test_inspect_server.py`). Port the
  ones that test podcast behaviour; delete the ones the harness now tests.

### C. Layer 5: the release

- **`harness/CHANGELOG.md`:** finish the 0.4.0 section and date it. The workflow refuses a
  tag without its section, and the site's releases page renders the changelog: run
  `make site` after editing it.
- **`harness/docs/UPGRADING.md`:** a 0.3.0 → 0.4.0 section. What can change: exact p at
  n ≤ 30, and the family-test cache recomputing. What's new and optional: catalog, goals.
- **`docs/GUIDE.md`:**
  - a goals step (copy `tutorial/goals/tickets_summary.yaml`, add `goal:` to the configs);
  - a catalog step (`make catalog`, `make catalog-serve`);
  - the tutorial outputs in steps 6 and 8 are already updated for exact p.
- **Merge, then tag `v0.4.0`** (owner). The tag workflow builds the package and the release.

## Things that will bite

- **Branch `harness-0.4.0` is behind `main`.** Merge `main` in before pushing more (the last
  merge brought `validate` V4). `harness/CHANGELOG.md` and `site/public/releases.html`
  conflict every time: keep both sides' changelog bullets, then regenerate the site with
  `make site`. Don't hand-merge the HTML.
- **`make ci` checks that `site/public` is fresh.** Any change to `site/*.py`,
  `site/analytics.json` or `harness/CHANGELOG.md` needs `make site`, committed.
- **`family-test` caches answers in `.cache/family_test`.** The key includes `stats.py`, so a
  change there recomputes (minutes).
- **The tutorial's noisy arm is random.** Its row in GUIDE step 8 differs between runs; that
  predates 0.4.0.
- **`render.sh` builds the catalog with `python3`**, which needs `pyyaml` (the workflow
  installs it).
- **The inspector recomputes nothing between restarts.** `deploy.sh` recreates it on every
  release, and `--warm` refills the cache from the catalog's links (minutes at 0.5 CPU).
- **The docker.io anonymous pull limit** hit once from the cloud proxy. The box pulls the
  pinned digests on first deploy.

## Rules that still hold

- **Private data never goes to a public remote.** The podcast repo is private; this one is
  public. Prod details (tailnet name, host key, IPs) live in GitHub environment vars and the
  prod session, never in a file here.
- **Comparisons always on one `dataset_id`.** `sources/` is immutable.
- **Commit only when tests pass.** Merging and tagging are the owner's.
- **No model identifiers** in commits, PRs or files.
