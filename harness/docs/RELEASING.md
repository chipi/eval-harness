# Releasing the harness

The harness is installed from **GitHub only**. Nothing of ours is on PyPI, under any name.

Its package name is **`evaluation-harness`**, its import `evaluation_harness`, its command
`evh`. None of them is `eval-harness` or `eval_harness`: on PyPI those belong to an
unrelated project, which a bare `pip install eval-harness` installs. A bare
`pip install evaluation-harness` finds nothing and fails, which is the point.

## Quick release smoke

From the repository root:

```bash
make release-smoke                  # under a minute, offline, $0
make release-smoke ARGS=--release   # also the rendered release's container and header checks (docker, network)
```

It prints one `ok` or `FAIL` line per check with the command it ran, and ends with `RELEASE SMOKE: PASS` or
`RELEASE SMOKE: FAIL (n of m)` (exit 0 or 1). Run it **before the release pull request is merged** (once the version
is bumped, with step 4b's upgrade check and step 5's scenario where they apply), and **again after the deploy**, beside
what already watches a deploy: the `deploy-prod.yml` workflow's public probe (it fetches the site, the catalog, the
docs and the Workbench at the deployed address and fails on a page that is not this release's), and, for what the
live server reports, the `deploy-verify` and `o11y-prod` skills (`AGENTS.md`). After a deploy the smoke still
answers only whether the build in the checkout works; it does not look at the live site.

What it covers:

- **One version everywhere.** `_version.py`, every bundled skill's `harness-version`, the top `CHANGELOG.md`
  section, `UPGRADING.md`'s newest "From X to Y" heading and every install pin in the docs (`site/build.py`'s pin
  check) name the same release.
- **The built package.** The wheel `pyproject.toml` builds, installed in a fresh venv outside the checkout: `evh
  --version` prints the version, the package comes from the venv and not the checkout, `evh --help` shows "Start
  here", `evh docs` lists the three shipped docs and `evh docs runbook --print` prints the runbook.
- **A newcomer's first loop, on both stores.** In a fresh project made with `evh init --tutorial`, on `files` and
  then on `sqlite`: a dataset from the tutorial kit, `run --dry-run` and `run` of two echo-provider systems,
  `leaderboard` and `validate`.
- **The servers from the install.** `evh catalog-serve` answers the catalog home, `/api/v1/goals` and `/workbench/`;
  `evh mcp --http` answers `/mcp/health` and `tools/list`; with `--no-agent-tools` every tool is read-only. Each
  server is stopped by its PID, also when a check fails or the run is interrupted.
- **With `--release`: the deployment.** `infra/deploy/render.sh` into a temp folder, then `smoke_release.py` (the
  inspector's and the MCP server's containers answer as compose starts them) and `headers_check.py` (one header
  across the site, catalog, Workbench and docs). Without docker it says "skipped: no docker".

What it does not cover:

- **Paid calls.** No hosted model, no judge, no key: the echo provider only. Whether a hosted arm or a judge works
  with a real key is for the scenario (step 5) or a run of your own.
- **The newcomer scenario.** [SCENARIO.md](SCENARIO.md) follows the published docs from an empty folder, with two
  evals on real models and one CPU model; the smoke follows the GUIDE's offline commands only, and reads none of the
  prose a newcomer reads.
- **The upgrade over an install.** An existing project on the previous release, migrated: `make -C harness
  upgrade-check` (step 4b).
- **The store matrix.** Every test file on the sqlite store (`make stores-check`); the smoke runs one short loop on
  each store.
- **The browser suites.** `make browser-check` and `make browser-real-check`: no page is rendered in a browser (only
  with `--release`, `headers_check.py` drives one, for the header).
- **`make verify` and `make ci`.** No report, claim, committed run or the self-test is recomputed or re-checked; the
  smoke does not replace them.
- **The tutorials.** Tutorials 1 to 9 need models, keys or a browser; none is followed.
- **The data in `harness/data`.** The smoke makes its own projects in a temp folder, and reads nothing of this
  repository's runs.
- **The live site.** Nothing is fetched over the network, so a deploy that did not take, a certificate or a proxy
  rule is for the deploy's probe and `deploy-verify`.
- **Dependencies from the index.** The wheel is installed without the network, its dependencies the checkout's venv's;
  `--online-deps` installs them from the package index as a user's `pip install` does, and a pin that no longer
  resolves is found only there.
- **A hosted-image difference.** Without `--release` no container runs, so a module the box's Python lacks (the
  0.8.1 incident, EVALS-INSPECTOR-3) is found only by the deploy's own `smoke_release.py` or `--release`.

## For a project that depends on it

Pin a release tag:

```toml
# pyproject.toml
"evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.8.2#subdirectory=harness",
```

- **Pin a tag, never a branch.** A branch moves; a run recorded against it cannot be
  reproduced.
- **What a tag does not guarantee.** A tag can be moved by someone with push rights. If
  that matters, pin the commit the tag points to (`@<sha>`, with the tag in a comment), or
  install the wheel attached to the GitHub Release with `--require-hashes`.
- Every run records the harness `version` and a `code_sha256` of its code, so a result
  says which harness produced it whatever the pin was.
- To upgrade, change the pin, reinstall, run `evh self-test` and
  `evh validate`, and re-score committed runs to see whether any number moves
  (`docs/UPGRADING.md`).

## Cutting a release

1. **Bump the version** in `harness/scripts/_version.py`, and the `harness-version` each bundled skill names
   (`harness/skills/*/SKILL.md`; `tests/test_skills.py` fails a skill that names another), using semantic versioning:
   - patch: a fix that cannot move a result;
   - minor: new capability, or any change that can move a result;
   - major: a change to the run format or the CLI that breaks existing projects.
2. **Write its section** at the top of `harness/CHANGELOG.md` (`## X.Y.Z — YYYY-MM-DD`).
   **A section is short: at most 4,000 characters** (from 0.8.0 on; `make -C harness site-check`
   fails a longer one, `site/releases.py` `SECTION_LIMIT`). Open it with a short paragraph a reader
   can take in at once: what the release lets you do, and whether upgrading changes any result.
   Anything that can move a number is named there or under **Changed**, in words a consumer can
   act on. When the release has more to say than fits, write the full notes, every change by area,
   in `docs/releases/X.Y.Z.md` (a page of the docs site) and end the section with a link to it:
   `[docs/releases/X.Y.Z.md](https://github.com/chipi/eval-harness/blob/main/docs/releases/X.Y.Z.md)`.
   The check also fails a section that links a notes page that does not exist, and a notes page
   its section does not link to. The section is the release notes in three places: the GitHub
   Release (the workflow copies it), the docs site and the harness site's release notes page; the
   link carries the reader to the full notes from each. Use absolute links: the GitHub Release
   cannot resolve relative ones. A section written this way never reaches `harness-release.yml`'s
   cut at 120,000 characters (GitHub's limit is 125,000), which stays as a backstop.
   Write the matching "From X to Y" section of `docs/UPGRADING.md` in the same step: each bullet of the CHANGELOG that
   can stop a run that worked has a bullet there.
3. **Move every install pin to the new tag** (`@vX.Y.Z#subdirectory=harness`): the READMEs,
   the getting-started guide, the tutorials and these docs. `make -C harness site-check` fails on a
   pin that names an older release than the changelog's newest dated section, so dating the
   section and moving the pins go in the same commit.
4. **Rebuild the validation reports that CI cannot.** The Goyal et al. annotations and the
   Zhang et al. ratings are downloaded at run time and never committed, so CI checks each
   committed `data/judge-validation/<scorer>/<set>/report.json` only against its records (their
   hash, count, bill, unparsed and withheld counts) and the scorer's hash, not its figures.
   Before a release, with the human data downloaded (the scripts fetch it), run
   `python tools/validate_judge_goyal.py --scorer <scorer> --no-calls` and
   `python tools/validate_judge_zhang.py --scorer <scorer> --no-calls` for each scorer that
   has the records; they recompute every figure for $0. Commit any change, and run `make ci`,
   which then recomputes the report's claims from the human data too.

   **4b. Check the upgrade over an install.** `make -C harness upgrade-check` (network and an authenticated `gh`; a
   minute or two) installs the previous release's wheel in a throwaway venv, makes a `files` and a `sqlite` project on
   it, installs this tree's build over it as `docs/UPGRADING.md` says, and runs `evh --version`, `migrate --check`,
   `migrate --dry-run`, `validate`, `runs-list` and `leaderboard` in each. It also checks UPGRADING's claim that a plain
   `pip install` of a build that reports the installed version keeps the old code. Run it on the release pull request, once
   the version is bumped; a failure is a release that breaks the project of someone who upgrades.

   **4c. Check that the readers agree on this repository's own data.** `make -C harness reader-agreement-repo` (15 to 25
   minutes; not in the self-test) asks the CLI, the API, the MCP reads, the catalog export and the inspector for the same
   facts of `harness/data`, on a copy, and fails when two of them differ. The self-test's version runs the same check on
   small projects; this one runs it on the real ones, where a migration or a re-score leaves a shape no fixture has.
   Run it on the release pull request; a disagreement is a reader that says something different from the others about
   a project someone is using.
5. **Run the [newcomer scenario](SCENARIO.md)** on the release candidate **when the newcomer's path
   changed** since its last recorded run: the install, getting started, the tutorials, or the
   commands and files they use. It is a smoke test: a fresh project, the published docs only, two
   evals with real models and one CPU model (the fastest), under $1. Fix what blocks a
   newcomer; record the rest in its "Open" list. When nothing on that path changed, skip it and
   say so in the release PR.
6. **Merge to `main`.** The `harness-package` workflow builds the package, installs it in
   a clean venv, runs it outside the checkout, and checks the changelog section exists.
7. **Tag and push:**
   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```
   The `harness-release` workflow then:
   - refuses the tag unless it matches `_version.py` and the changelog section is dated;
   - refuses it unless CI on the tagged commit is green on `main` (`reproduce` and `quality`, not `rerun`, which
     fetches from Hugging Face and only reports,
     and `guards` when it ran), waiting up to 40 minutes for runs still going. It does not
     re-run them, so tag the merge commit on `main`, not a branch commit;
   - builds the wheel and sdist, and checks the installed CLI reports the tag;
   - creates the GitHub Release with the changelog section as notes and the package
     attached.

8. **Deploy, when the release changes what the site or catalog show.** A merge to `main` deploys
   nothing: the production deploy is its own step, run from the repository root with an
   authenticated `gh`:
   ```bash
   make deploy-dry   # dispatches deploy-prod.yml with dry_run=true on origin/main's head and watches it
   make deploy       # refuses unless a dry run of that same commit passed; then the real deploy
   ```
   `infra/deploy/dispatch.sh` recognises a dry run by `dry_run=true sha=<sha>` in the workflow run's title
   (`run-name`) and by the same head sha, and passes the sha as a required input that the workflow's first
   step checks against the commit it got, so a main that moves meanwhile deploys nothing
   (`infra/README.md`, "Cutover").

A failed release leaves no Release behind. Fix the problem and cut the next patch version: the
`release tags` ruleset refuses deleting or moving a `v*` tag for everyone, an admin included (it
has no bypass list since 2026-11-23). To reuse the number of a tag that has no Release, a maintainer
sets the ruleset's enforcement to Disabled (Settings → Rules → Rulesets → `release tags`), deletes
the tag (`git push --delete origin vX.Y.Z`), sets it back to Active, and tags again: moving a tag
is a change to the ruleset made on purpose. **Never move a tag that has a Release:** someone may
already have pinned it. Cut the next patch version instead.

## One-time repository settings (done by a maintainer in GitHub)

- **Settings → Rules → Rulesets → New tag ruleset.** Target `v*`, and block updates and
  deletions, so a released tag cannot move under its users. Leave its bypass list empty, so it
  holds for an admin too: a bypass lets a tag be deleted and then created again on another commit
  (the ruleset has no creation rule, because the release creates tags).
- **Settings → Actions → General → Workflow permissions** must allow the workflow token to
  write contents, or the release step cannot create the Release (the workflow asks for
  `contents: write`).
