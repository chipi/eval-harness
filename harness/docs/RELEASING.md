# Releasing the harness

The harness is installed from **GitHub only**. Nothing of ours is on PyPI, under any name.

Its package name is **`evaluation-harness`**, its import `evaluation_harness`, its command
`evh`. None of them is `eval-harness` or `eval_harness`: on PyPI those belong to an
unrelated project, which a bare `pip install eval-harness` installs. A bare
`pip install evaluation-harness` finds nothing and fails, which is the point.

## For a project that depends on it

Pin a release tag:

```toml
# pyproject.toml
"evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.8.0#subdirectory=harness",
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

1. **Bump the version** in `harness/scripts/_version.py` (semantic versioning):
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

A failed release leaves no Release behind. Fix the problem, delete the tag
(`git push --delete origin vX.Y.Z`) and tag again. **Never move a tag that has a Release:**
someone may already have pinned it. Cut the next patch version instead.

## One-time repository settings (done by a maintainer in GitHub)

- **Settings → Rules → Rulesets → New tag ruleset.** Target `v*`, and block updates and
  deletions, so a released tag cannot move under its users.
- **Settings → Actions → General → Workflow permissions** must allow the workflow token to
  write contents, or the release step cannot create the Release (the workflow asks for
  `contents: write`).
