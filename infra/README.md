# infra: this repository on the prod VPS

Four addresses, one repository:

| address | what | served by |
|---|---|---|
| `evals.humancopilot.eu` | the harness site: the harness and its findings (`site/public`, built by `make site`) | prod VPS: `evals-nginx` |
| `evals.humancopilot.eu/catalog` | the harness deployed on these example experiments: the catalog, goal pages and run inspector | prod VPS: `evals-nginx` (pages) + `evals-inspector` (`/api/*`) |
| `evals.humancopilot.eu/mcp` | the same experiments for an agent: the harness's read commands as MCP tools (Streamable HTTP, read-only, no sign-in) | prod VPS: `evals-mcp` |
| `evals.humancopilot.eu/docs` | the documentation (mkdocs) | prod VPS: `evals-nginx` (built into each release by `render.sh`); the same docs are also on GitHub Pages, `chipi.github.io/eval-harness` (`.github/workflows/pages.yml`) |

Everything on the VPS follows the box's tenant pattern, copied from chipi/humancopilot.eu
(owner of the edge: podcast_scraper, its ADR-114):
- the shared Caddy edge in front;
- each tenant with its own compose project, containers, loopback ports and `/srv/<tenant>`;
- releases deployed from GitHub Actions over the tailnet as `deploy@`.

```
infra/
  compose.yml            evals-nginx (127.0.0.1:8096), evals-inspector (127.0.0.1:8097),
                         evals-mcp (127.0.0.1:8098)
  mcp/                   hooks.py (the MCP server's observability), requirements.txt (its SDK, pinned)
  nginx/                 nginx.conf, one server block per host, the security headers
  caddy/                 evals.caddy, catalog.caddy, enabled.txt (which ones are live)
  sites/<host>.cfg       per-host public settings (the CSP report address)
  observability/         evals.alloy: both containers' logs to VictoriaLogs (app=evals; service
                         evals-web for nginx, evals-inspector for the inspector; `release` and,
                         on nginx's error lines, `level` as structured metadata), and the
                         inspector's /metrics scrape
  deploy/                render.sh (CI), deploy.sh + install_vhosts.sh + install_alloy.sh (box)
.github/workflows/deploy-prod.yml   render, upload, activate, probe
.github/actions/prod-ssh-key/       the CI key and the pinned host key
```

## The containers

- **evals-nginx:** the template's nginx, plus a per-visitor limit (20 requests a second, a burst of 200,
  32 connections; the visitor by `X-Real-IP`, set by Caddy; nothing in front throttles). It is unprivileged, read-only, has every
  capability dropped, and is limited to 64 MB, half a CPU and 64 processes. It serves two hosts.
  Unknown hosts are closed (444). `/docs/` serves the documentation, with its own headers.
- **evals-inspector:** the stock Python image (pinned by digest) running the release's copy of the package, installed from its wheel on the CI runner by
  `render.sh`: `inspector/pkg/evaluation_harness/catalog_serve.py --public evals.humancopilot.eu --publish outputs --client-header X-Real-IP` (the full command is in `compose.yml`).
  The `--publish outputs` flag exposes the arms' outputs (already public in the repo); the
  `--client-header X-Real-IP` rate-limits by the address Caddy resolved and set on every request
  it forwards (`evals.caddy`: `header_up X-Real-IP {client_ip}`). The shared base takes
  `CF-Connecting-IP` only from Cloudflare's ranges (`trusted_proxies`), and a client's own
  `X-Real-IP` is overwritten, so the value holds even without the origin lock. The origin lock is
  the hosting provider's firewall, owned by the box's infra
  repository (its ADR-118, `CLOUDFLARE_ORIGIN_LOCK`): port 443 accepts only Cloudflare's
  ranges, and port 80 only redirects. The prod session checked it on 2026-10-27: straight to the
  origin from a non-Cloudflare address, 443 timed out and 80 answered 308. Not checked: IPv6.
  - **Nothing is built or installed on the box.** The server's code, and the Sentry and
    OpenTelemetry SDKs its hooks use, come in the release, vendored by `render.sh` on the
    runner; it reads the release's copy of the runs from the read-only mount.
  - **Hardening:** it runs as nobody, read-only, every capability dropped, limited to 256 MB,
    half a CPU and 64 processes.
  - **Observability (0.4.2), this deployment's layer, not the harness's:**
    `inspector/hooks.py` (from `infra/inspector/hooks.py`) is passed as `--hooks`, the
    harness's generic hook point. It reports errors to GlitchTip through the Sentry SDK
    (environment `prod`, release `sha-<7>` from `RELEASE`), sends one OpenTelemetry span per API
    request to VictoriaTraces (service `evals-inspector`, namespace `evals`), and serves
    `/metrics` (requests and latency per route and status, the caches, resident memory) on the
    container's port, which only the box's Alloy scrapes (`observability/evals.alloy`): Caddy
    forwards nothing but `/catalog/api/` to the inspector. The SDKs
    (`infra/inspector/requirements.txt`, pinned, pure-Python wheels) are vendored by `render.sh`
    into `inspector/vendor/` and found through `PYTHONPATH`; together they cost about 20 MB of the
    256 MB (measured locally 2026-10-27: 27 MB idle without, 44 MB with).
  - **Settings, never in the repository and never placed on the box by hand:**
    `/srv/evals/observability.env`, rendered by the deploy workflow on every deploy (as
    podcast_scraper renders its `.env`): `SENTRY_DSN` from the environment secret
    `EVALS_SENTRY_DSN_INSPECTOR` (the GlitchTip project's DSN, through the tailnet's TLS node),
    `MCP_SENTRY_DSN` from `EVALS_SENTRY_DSN_MCP` (the MCP server's project), and, built from
    `vars.PROD_TAILNET_FQDN` so no tailnet name is committed, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
    (the tailnet's VictoriaTraces node, `/insert/opentelemetry/v1/traces`) and `UMAMI_SEND_URL`
    (the homelab Umami's `/api/send`, for the MCP server's events). Those keys only, written
    through /dev/shm and moved into place; mode 640, `deploy:deploy`, which the inspector and the
    MCP server read through `group_add` 1001 in `compose.yml` and no other account on the box can.
    The workflow prints the mode, owner and key names, never a value. Without the secret,
    GlitchTip is off and the rest is on; without the file, or a key, that part is off and the
    inspector serves as before; the start line says which parts are on (`hooks: sha-…; GlitchTip
    on, traces on, /metrics on`).
  - **Network:** without the settings it calls out to nothing; with them, to GlitchTip and
    VictoriaTraces only.
  - **What it answers:** only the catalog host, 60 requests a minute per client (identified by the
    `X-Real-IP` header Caddy sets), at most 40 arms per comparison, two computations at a time, every
    answer cached. At start it computes every comparison the catalog's own pages link to.
- **evals-mcp (0.4.5):** the harness's MCP server, `evh mcp` (RFC-018), at `/mcp`: the read
  commands as tools for any agent, over Streamable HTTP, stateless. The same stock image, package
  and data as the inspector; the MCP SDK and its dependencies (`infra/mcp/requirements.txt`,
  pinned, compiled wheels for the box: x86_64 musl) vendored by `render.sh` into
  `inspector/mcpvendor/`, found through `PYTHONPATH`.
  - **Read-only by construction:** its tools are the commands that only read (none writes, spends
    or runs a model); `--public` leaves out the options that answer with an item's text and the
    `validate` tool (the release's copy of the data is not a whole project); it reads the read-only
    mount. No authentication: it answers what the site and the catalog already publish.
  - **Load and speed:** the server throttles itself (Cloudflare only proxies): `--rate 30` calls a
    minute per caller (`X-Real-IP`, as for the inspector), `--rate-total 120` for everyone,
    one call at a time per caller, `--request-rate 300` HTTP requests a minute per caller, a 64 KB body
    (Caddy and the server), 64 connections, GET on `/mcp` 405,
    two commands at a time, 60 s each. Each call is a fresh `evh` process; the goals'
    paired tests, which a view would otherwise draw again (~50 s), come precomputed in
    `inspector/cache/evh-p.jsonl` (`render.sh` fills it during the catalog build; `EVH_P_CACHE`).
  - **Hardening:** as the inspector, with a hard 384 MB memory limit (the server and two commands;
    the box has no swap and runs a nightly pipeline).
  - **Observability:** `inspector/mcp_hooks.py` (from `infra/mcp/hooks.py`) as `--hooks`: errors
    to GlitchTip project `evals-mcp` (`MCP_SENTRY_DSN` in `observability.env`, from the secret
    `EVALS_SENTRY_DSN_MCP`), one span per tool call to VictoriaTraces (service `evals-mcp`),
    `/metrics` on the container's port only (Caddy forwards nothing but `/mcp`), and one Umami event
    per call (`mcp:<tool>`, on the site's website; `UMAMI_SEND_URL`, the homelab Umami on the
    tailnet, rendered like the traces endpoint). A call is logged as one JSON line: the tool, its
    arguments' names (never their values), how it ended, its time; never the caller's address or
    user agent (those go to the hooks only, for the Umami visitor count).

## What `deploy.sh` checks before a release counts as live

0. Room on `/srv`: at least 2 GB and 300,000 inodes free, else it refuses. Then only the live
   release and this one are kept: whatever an earlier failed deploy or dry run left is pruned.
1. The three loopback ports are free or already held by our containers.
2. `nginx -t` passes on the new release's config, in a throwaway container. **A dry run
   (`workflow_dispatch` with `dry_run`) stops here.**
3. The `current` symlink switches atomically. nginx comes up, and the inspector and the MCP server are recreated
   so they load the new code and data. nginx reloads.
4. Each host answers 200 on `/` and 404 on a missing page. The inspector answers
   `/api/health` and two real comparisons taken from the catalog's own links: one arm, and
   the first group of arms on one metric (`deploy/probe_link.sh` picks it; `make -C harness
   test` runs the same probe against the tutorial project). Both must come back with verdict
   rows. The MCP server answers `/mcp/health` and a real `goals` call (up to 120 s; a warning
   past 30 s, which means the precomputed p cache was not read: without it the call takes ~50 s).
5. The inspector once `--warm` is done (its log line, up to 300 s): running, never restarted,
   under 80% of its memory limit, else the release rolls back.
6. After the edge vhosts, it prunes again: the live release and the previous one stay, for a
   rollback. A release is ~69k files; the upload hard-links those the live release already has
   (`rsync --checksum --link-dest`), so a release costs new inodes only for what changed.

Any failure in 3 or 4 rolls back to the previous release: the symlink, the containers (the MCP
server removed when the previous release had none) and
the config. Then the Alloy drop-in and the Caddy vhosts are installed, each validated with
the whole shared set and restored on failure.

Verified before the first deploy: the release rendered, then deploy.sh steps 1–4 run on a
local Docker with the pinned images. Both sites passed; the inspector answered with the same
p-value as `pair-test`; a browser passed both hosts with zero violations of the production CSP.

## One-time setup

**The operator, on GitHub (chipi/eval-harness → Settings):**

1. **Environments → New environment `prod`.** Deployment branches: selected branches, `main`
   only. Required reviewers: none, unless you want a gate.
2. **In `prod`, three secrets:**
   - `TS_OAUTH_CLIENT_ID` and `TS_OAUTH_SECRET`: a Tailscale OAuth client of this
     repository's own, with tag `tag:gha-deployer`.
   - `PROD_SSH_PRIVATE_KEY`: a new key used only by this workflow. Make it on your own
     machine, never in a shared session:
     ```
     ssh-keygen -t ed25519 -N '' -C gha-evals-deploy -f gha-evals-deploy
     ```
     The secret is the content of `gha-evals-deploy`. Send the prod session only
     `gha-evals-deploy.pub`.
3. **In `prod`, two variables:** `PROD_TAILNET_FQDN` and `PROD_SSH_HOST_KEY`. Copy both from
   chipi/humancopilot.eu's `prod` environment.

**The prod session, on the box:**
- create `/srv/evals` (deploy:deploy 0755);
- add the public key to deploy@ with a tailnet `from=`;
- add `evals-nginx` and `evals-inspector` to podcast_scraper's `unscoped.alloy`, so their logs
  don't ship twice;
- record ports 8096 and 8097 in ADR-114.

**GlitchTip (done 2026-10-22):** project `evals-web` (id 36) receives both hosts' CSP violation
reports, through the shared `telemetry.humancopilot.eu` ingest vhost; `infra/sites/*.cfg` holds
the report URI, and a probe report proved the path end to end. To point it elsewhere: create
the project (the handbook's superuser recipe), and put its security endpoint in
`infra/sites/evals.humancopilot.eu.cfg` and `infra/sites/evals.humancopilot.eu/catalog.cfg` as
`CSP_REPORT_URI`. An empty value turns reporting off; the CSP is enforced either way.

## Cutover, in this order

The deploy workflow runs only from `main`: the prod environment allows no other branch. Two
repository variables keep the merge itself from changing anything public: a push deploys to the
VPS only once `PROD_AUTO_DEPLOY` is `true`, and publishes the docs to Pages only once
`DOCS_ON_OWN_DOMAIN` is `true`. Both start unset, so after the merge GitHub Pages keeps serving
the harness site on `evals.humancopilot.eu` until step 5 moves it. A dispatch of either workflow
always runs.

**Already done (2026-10-22):**

| What | Evidence |
|---|---|
| `prod` environment: 3 secrets, 2 variables, `main` only | `gh secret list --env prod`, `gh variable list --env prod -R chipi/eval-harness` |
| Deploy key in `deploy@`'s `authorized_keys` (tailnet-only `from=`), `/srv/evals`, ports 8096/8097, the Alloy split, the tailnet ACL | the prod session's report |
| GlitchTip `evals-web` (36) and `infra/sites/*.cfg` | a probe report through `telemetry.humancopilot.eu` became an issue (then deleted) |
| `main` protected: `verify`, `browser` and the three `rerun` jobs required | `gh api repos/chipi/eval-harness/branches/main/protection` |

**The steps.** Steps 0 to 3 can be days apart; 4 to 6 belong together, within minutes.

0. **Before the merge** (operator). PR #22's checks are green and its review is done.
1. **Merge PR #22** (operator). Nothing deploys and nothing public changes.
   - *Confirm:* the merge commit's `deploy-prod` and `pages` deploy jobs show as skipped.
2. **Release** (operator; after layer 4, before the first deploy). Date the CHANGELOG section,
   tag `v0.4.0` (`harness/docs/RELEASING.md`). The deployed pages show `@v0.4.0` install lines,
   which work only once the tag exists.
   - *Confirm:* the `harness-release` run on the tag is green, and
     `pip install "evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.4.0#subdirectory=harness"`
     installs in a fresh venv.
3. **First deploy, by hand** (operator or this repo's session; tell the prod session first, it
   watches the box).
   - `gh workflow run deploy-prod.yml -R chipi/eval-harness -f dry_run=true`: uploads and
     validates on the box (port preflight, `nginx -t`), switches nothing.
   - `gh workflow run deploy-prod.yml -R chipi/eval-harness`: goes live on the loopback ports
     only (`enabled.txt` is empty). The on-box health check is the gate: both sites 200 on `/`
     and 404 on a missing page, the inspector's `/api/health`, one single-arm comparison and one
     group comparison (`deploy/probe_link.sh`).
   - Then `gh variable set PROD_AUTO_DEPLOY --body true -R chipi/eval-harness`: later pushes
     deploy.
   - *Confirm:* both runs green; the log ends `== release <sha> live on 127.0.0.1:8096 (nginx)
     and 127.0.0.1:8097 (inspector)`.
   - *If it fails:* nothing public has changed and the box rolled itself back. Read the run's
     log, fix, dispatch again.
4. **DNS in Cloudflare** (operator).
   - `evals.humancopilot.eu` and `evals.humancopilot.eu/catalog`: A + AAAA to the VPS (the
     same addresses as the box's other sites; the prod session has them), proxied.
   - `evals.humancopilot.eu/docs`: CNAME `chipi.github.io`, DNS only.
   - *Confirm:* `dig +short evals.humancopilot.eu/docs` names `chipi.github.io`; the two proxied
     names resolve to Cloudflare addresses.
   - From here `evals.humancopilot.eu` reaches the VPS, which has no vhost for it yet: go
     straight on.
5. **Docs on their own domain** (operator or this repo's session).
   - `gh api -X PUT repos/chipi/eval-harness/pages -f cname=evals.humancopilot.eu/docs`
   - `gh workflow run pages.yml -R chipi/eval-harness`
   - `gh variable set DOCS_ON_OWN_DOMAIN --body true -R chipi/eval-harness`
   - *Confirm:* the `pages` run's crawl check is green (robots.txt, sitemap.xml and every
     sitemap URL answer on `evals.humancopilot.eu/docs`).
6. **Enable the vhosts** (this repo's session, with the operator's go; tell the prod session, it
   watches certificate issuance). Add `evals` and `catalog` to `infra/caddy/enabled.txt` and
   push. The deploy installs both vhosts; Caddy gets their certificates over HTTP-01 through
   Cloudflare's proxy. Never before step 4: `install_vhosts.sh` checks that a name resolves, not
   where, and Caddy would burn Let's Encrypt attempts on a name that still points at GitHub.
   - *Confirm:* `curl -sI https://evals.humancopilot.eu/` and `curl -sI
     https://evals.humancopilot.eu/catalog/` answer 200;
     `curl -s https://evals.humancopilot.eu/catalog/api/health` answers.
7. **Check** (anyone).
   - `curl -sI https://evals.humancopilot.eu/docs/GUIDE/ | grep -i '^location'` names
     `https://evals.humancopilot.eu/docs/GUIDE/`.
   - The catalog's pages open and a group "Inspect" link answers with verdicts.
   - GlitchTip `evals-web` stays empty in normal use: an issue there is a page loading
     something the CSP blocks.

Later deploys need none of this: a push to `main` that touches what ships redeploys, docs and
site changes included, once CI on that commit is green.

**What happened instead of steps 4 and 5:** the docs were never moved to Pages under this
domain. `render.sh` builds them into each release, so `evals.humancopilot.eu/docs` is served by
the VPS. The docs are also published to GitHub Pages, at `chipi.github.io/eval-harness` with no
custom domain, by `pages.yml` on every push to `main` that touches them.

**Rollback:**
- a bad release: re-run an older successful `deploy-prod` run (it redeploys that sha), or
  `git revert` on `main`;
- one host off the edge: remove its name from `enabled.txt` and push;
- stop pushes deploying: `gh variable delete PROD_AUTO_DEPLOY -R chipi/eval-harness`.
