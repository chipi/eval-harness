#!/usr/bin/env bash
# Dispatches deploy-prod.yml on origin/main's head and watches the run to its end.
#   dispatch.sh dry    dry_run=true: uploads and validates on the box, switches nothing
#   dispatch.sh real   dry_run=false: refuses unless a dry run of this same commit passed
# Run through `make deploy-dry` and `make deploy` (the root Makefile). A merge to main deploys nothing.
#
# How a dry run is recognised: deploy-prod.yml's `run-name` carries the input and the commit, "... (dry_run=true sha=<sha>)",
# and `gh run list --json displayTitle` returns it; a dispatch's inputs are not in that list's JSON.
# A run counts only if it is a workflow_dispatch on main, for this exact head sha (also the sha in its title), concluded
# `success`, with dry_run=true in its title. The sha is also passed as the workflow's required `sha` input, and the
# workflow's first step fails unless it is the commit the run got, so a main that moves between the check and the
# dispatch cannot deploy a commit nobody dry-ran.
#
# Environment: REPO (default chipi/eval-harness); DEPLOY_POLL_SECONDS / DEPLOY_POLL_TRIES (how long to
# wait for the dispatched run to appear; the tests set them to 0).
set -euo pipefail

WORKFLOW=deploy-prod.yml
REPO="${REPO:-chipi/eval-harness}"
FIELDS=databaseId,displayTitle,headSha,headBranch,event,status,conclusion

die() { echo "ERROR: $*" >&2; exit 1; }

mode="${1:-}"
case "$mode" in dry | real) ;; *) echo "usage: $0 dry|real" >&2; exit 2 ;; esac

git fetch --quiet origin main
sha="$(git rev-parse origin/main)"

runs() {
  gh run list -R "$REPO" --workflow "$WORKFLOW" --branch main --event workflow_dispatch \
    --limit 100 --json "$FIELDS"
}

if [ "$mode" = real ]; then
  passed="$(runs | jq -r --arg sha "$sha" '[.[] | select(.headSha == $sha and .event == "workflow_dispatch"
      and .headBranch == "main" and .conclusion == "success"
      and (.displayTitle | contains("dry_run=true sha=" + $sha)))] | length')"
  if [ "$passed" = 0 ]; then
    die "no successful dry run of ${sha:0:12} (origin/main). Run 'make deploy-dry' first; nothing was dispatched."
  fi
  echo "dry run of ${sha:0:12} passed; dispatching the real deploy"
  dry=false
else
  dry=true
fi

# The run we start is the first one numbered above every run that exists now: no clock to trust.
before="$(runs | jq '[.[].databaseId] | max // 0')"
gh workflow run "$WORKFLOW" -R "$REPO" --ref main -f "dry_run=$dry" -f "sha=$sha"
echo "dispatched $WORKFLOW on ${sha:0:12} with dry_run=$dry"

id=""
for _ in $(seq "${DEPLOY_POLL_TRIES:-20}"); do
  id="$(runs | jq -r --argjson before "$before" --arg sha "$sha" --arg dry "dry_run=$dry" \
    '[.[] | select(.databaseId > $before and .headSha == $sha and (.displayTitle | contains($dry + " sha=" + $sha)))
      | .databaseId] | min // empty')"
  [ -n "$id" ] && break
  sleep "${DEPLOY_POLL_SECONDS:-3}"
done
[ -n "$id" ] || die "no new run of $WORKFLOW for ${sha:0:12} appeared after the dispatch (origin/main may have moved); look at: gh run list -R $REPO --workflow $WORKFLOW"

echo "watching run $id"
gh run watch "$id" -R "$REPO" --exit-status
echo "run $id finished: dry_run=$dry on ${sha:0:12} succeeded"
