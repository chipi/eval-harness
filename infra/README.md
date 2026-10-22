# infra: this repository on the prod VPS

Three addresses, one repository:

| address | what | served by |
|---|---|---|
| `evals.humancopilot.eu` | the harness site: the harness and its findings (`site/public`, built by `make site`) | prod VPS: `evals-nginx` |
| `catalog.evals.humancopilot.eu` | the harness deployed on these example experiments: the catalog, goal pages and run inspector | prod VPS: `evals-nginx` (pages) + `evals-inspector` (`/api/*`) |
| `docs.evals.humancopilot.eu` | the documentation (mkdocs) | GitHub Pages (`.github/workflows/pages.yml`) |

Everything on the VPS follows the box's tenant pattern, copied from chipi/humancopilot.eu
(owner of the edge: podcast_scraper, its ADR-114):
- the shared Caddy edge in front;
- each tenant with its own compose project, containers, loopback ports and `/srv/<tenant>`;
- releases deployed from GitHub Actions over the tailnet as `deploy@`.

```
infra/
  compose.yml            evals-nginx (127.0.0.1:8096), evals-inspector (127.0.0.1:8097)
  nginx/                 nginx.conf, one server block per host, the security headers
  caddy/                 evals.caddy, catalog.caddy, enabled.txt (which ones are live)
  sites/<host>.env       per-host public settings (the CSP report address)
  observability/         evals.alloy: both containers' logs to VictoriaLogs, app=evals
  deploy/                render.sh (CI), deploy.sh + install_vhosts.sh + install_alloy.sh (box)
.github/workflows/deploy-prod.yml   render, upload, activate, probe
.github/actions/prod-ssh-key/       the CI key and the pinned host key
```

## The containers

- **evals-nginx:** the template's nginx unchanged. It is unprivileged, read-only, has every
  capability dropped, and is limited to 64 MB, half a CPU and 64 processes. It serves two hosts.
  Unknown hosts are closed (444). `/docs/...` redirects 301 to the same page on the docs host.
- **evals-inspector:** the stock Python image (pinned by digest) running the release's own
  `harness/scripts/catalog_serve.py --public catalog.evals.humancopilot.eu`.
  - **Nothing is built or installed on the box.** The server is standard library only and
    reads the release's copy of the runs from the read-only mount.
  - **Hardening:** it runs as nobody, read-only, every capability dropped, limited to 256 MB,
    half a CPU and 64 processes.
  - **Network:** it calls out to nothing.
  - **What it answers:** only the catalog host, 60 requests a minute per client, at most 40
    arms per comparison, two computations at a time, every answer cached. At start it
    computes every comparison the catalog's own pages link to.

## What `deploy.sh` checks before a release counts as live

1. Both loopback ports are free or already held by our containers.
2. `nginx -t` passes on the new release's config, in a throwaway container. **A dry run
   (`workflow_dispatch` with `dry_run`) stops here.**
3. The `current` symlink switches atomically. nginx comes up, and the inspector is recreated
   so it loads the new code and data. nginx reloads.
4. Each host answers 200 on `/` and 404 on a missing page. The inspector answers
   `/api/health` and two real comparisons taken from the catalog's own links: one arm, and
   the first group of arms on one metric (`deploy/probe_link.sh` picks it; `make -C harness
   test` runs the same probe against the tutorial project). Both must come back with verdict
   rows.

Any failure in 3 or 4 rolls back to the previous release: the symlink, the containers and
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

**GlitchTip (needs the superuser):** create a project for evals. Put its security endpoint in
`infra/sites/evals.humancopilot.eu.env` and `infra/sites/catalog.evals.humancopilot.eu.env`
as `CSP_REPORT_URI`. Until then the CSP is enforced without reports.

## Cutover, in this order

The deploy workflow runs only from `main`: the prod environment allows no other branch. So the
first deploy comes with the merge of the 0.4.0 branch, and so does the switch of `pages.yml` to
docs only. Between the merge and the DNS change, `evals.humancopilot.eu` (still on GitHub
Pages) shows the docs instead of the harness site. Do steps 2–5 together, in a few minutes.

0. **Before the merge:** the one-time setup above is done, and the prod session confirms
   `/srv/evals` and the key.
1. **Merge the 0.4.0 branch.** The deploy goes live on the loopback ports only (`enabled.txt`
   is empty), and the on-box health check is the gate. If it fails, nothing public has
   changed yet: fix and re-run it.
2. **Cloudflare:**
   - `evals.humancopilot.eu` and `catalog.evals.humancopilot.eu`: A + AAAA to the VPS,
     proxied.
   - `docs.evals.humancopilot.eu`: CNAME to `chipi.github.io`, DNS only.
3. **GitHub Pages:** set the custom domain to `docs.evals.humancopilot.eu`, then re-run the
   `pages` workflow.
4. **Enable the vhosts:** add `evals` and `catalog` to `infra/caddy/enabled.txt` and push. The
   deploy installs both vhosts; Caddy gets their certificates over HTTP-01 (through Cloudflare's
   proxy, verified by the prod session). The workflow probes both public hosts, and the
   inspector API on the catalog host. Don't list them before step 2: install_vhosts.sh only
   checks that a name resolves, not where, and today `evals` resolves to GitHub, so Caddy
   would try for a certificate it cannot get.
5. **Check:** the `pages` workflow's crawl check passes on the docs host, and an old
   `evals.humancopilot.eu/docs/GUIDE/` link lands on `docs.evals.humancopilot.eu/GUIDE/`.

Later deploys need none of this: a push to `main` that touches what ships redeploys.

**Rollback:**
- re-run an older successful deploy;
- or `git revert` on main;
- or remove a name from `enabled.txt` to take that host off the edge.
