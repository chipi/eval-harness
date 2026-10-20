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
"evaluation-harness @ git+https://github.com/chipi/eval-harness@v0.2.0#subdirectory=harness",
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
   Anything that can move a number goes under **Changed**, in words a consumer can act on.
3. **Merge to `main`.** The `harness-package` workflow builds the package, installs it in
   a clean venv, runs it outside the checkout, and checks the changelog section exists.
4. **Tag and push:**
   ```bash
   git tag vX.Y.Z && git push origin vX.Y.Z
   ```
   The `harness-release` workflow then:
   - refuses the tag unless it matches `_version.py` and the changelog section is dated;
   - runs `make verify`;
   - builds the wheel and sdist, and checks the installed CLI reports the tag;
   - creates the GitHub Release with the changelog section as notes and the package
     attached.

A failed release leaves no Release behind. Fix the problem, delete the tag
(`git push --delete origin vX.Y.Z`) and tag again. **Never move a tag that has a Release:**
someone may already have pinned it. Cut the next patch version instead.

## One-time repository settings (done by a maintainer in GitHub)

- **Settings → Rules → Rulesets → New tag ruleset.** Target `v*`, and block updates and
  deletions, so a released tag cannot move under its users.
- **Settings → Actions → General → Workflow permissions** must allow the workflow token to
  write contents, or the release step cannot create the Release (the workflow asks for
  `contents: write`).
