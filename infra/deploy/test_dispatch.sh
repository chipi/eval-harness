#!/usr/bin/env bash
# Tests infra/deploy/dispatch.sh against a stubbed `gh` on PATH and a throwaway git repo with an
# `origin`: nothing here reaches GitHub. Run from the repository root: bash infra/deploy/test_dispatch.sh
set -uo pipefail

SCRIPT="$(cd "$(dirname "$0")" && pwd)/dispatch.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git init -q --bare "$WORK/origin.git"
git init -q "$WORK/repo"
(
  cd "$WORK/repo" || exit 1
  git config user.email t@example.invalid
  git config user.name t
  git commit -q --allow-empty -m one
  git remote add origin "$WORK/origin.git"
  git push -q origin HEAD:refs/heads/main
)
SHA="$(git -C "$WORK/repo" rev-parse HEAD)"
OTHER=0000000000000000000000000000000000000000

mkdir -p "$WORK/bin"
cat > "$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
# `workflow run` appends the run it would start to runs.json; `run list` prints runs.json;
# `run watch` exits with $STUB_WATCH_EXIT. Every call is logged to calls.
echo "$*" >> "$STUB_DIR/calls"
case "$1 $2" in
  "workflow run")
    [ "${STUB_NO_NEW_RUN:-0}" = 1 ] && exit 0
    dry=false; sha=""
    for a in "$@"; do
      [ "$a" = "dry_run=true" ] && dry=true
      case "$a" in sha=*) sha="${a#sha=}" ;; esac
    done
    id=$(( $(jq '[.[].databaseId] | max // 0' "$STUB_DIR/runs.json") + 1 ))
    jq --argjson id "$id" --arg t "Deploy evals to prod VPS (dry_run=$dry sha=$sha)" --arg sha "${STUB_RUN_SHA:-$STUB_SHA}" \
      '. + [{databaseId:$id,displayTitle:$t,headSha:$sha,headBranch:"main",event:"workflow_dispatch",status:"completed",conclusion:"success"}]' \
      "$STUB_DIR/runs.json" > "$STUB_DIR/runs.new" && mv "$STUB_DIR/runs.new" "$STUB_DIR/runs.json" ;;
  "run list") cat "$STUB_DIR/runs.json" ;;
  "run watch") exit "${STUB_WATCH_EXIT:-0}" ;;
  *) echo "stub gh: unexpected: $*" >&2; exit 99 ;;
esac
STUB
chmod +x "$WORK/bin/gh"

fails=0
# run_case NAME EXPECTED_EXIT MODE RUNS_JSON [ENV=VALUE...]; then CHECK commands read $WORK/out and $WORK/stub/calls
run_case() {
  local name=$1 want=$2 mode=$3 runs=$4; shift 4
  rm -rf "$WORK/stub"; mkdir -p "$WORK/stub"
  printf '%s\n' "$runs" > "$WORK/stub/runs.json"
  (cd "$WORK/repo" && env PATH="$WORK/bin:$PATH" STUB_DIR="$WORK/stub" STUB_SHA="$SHA" \
     DEPLOY_POLL_SECONDS=0 DEPLOY_POLL_TRIES=3 "$@" bash "$SCRIPT" "$mode") > "$WORK/out" 2>&1
  local got=$?
  if [ "$got" = "$want" ]; then echo "PASS $name (exit $got)"; else
    echo "FAIL $name: exit $got, wanted $want"; sed 's/^/    | /' "$WORK/out"; fails=$((fails + 1)); fi
}
expect_calls() {  # NAME PATTERN WANT(yes|no)
  if grep -q -- "$2" "$WORK/stub/calls" 2>/dev/null; then have=yes; else have=no; fi
  if [ "$have" = "$3" ]; then echo "PASS $1"; else echo "FAIL $1: '$2' in calls = $have, wanted $3"; fails=$((fails + 1)); fi
}
expect_out() {
  if grep -q -- "$2" "$WORK/out"; then echo "PASS $1"; else echo "FAIL $1: output lacks '$2'"; sed 's/^/    | /' "$WORK/out"; fails=$((fails + 1)); fi
}
run() {  # sha, title, conclusion, event
  printf '{"databaseId":7,"displayTitle":"%s","headSha":"%s","headBranch":"main","event":"%s","status":"completed","conclusion":"%s"}' "$2" "$1" "${4:-workflow_dispatch}" "$3"
}

# deploy-dry dispatches dry_run=true on origin/main's commit and watches the run it started
run_case "dry: dispatches and watches" 0 dry "[]"
expect_calls "dry: dispatched dry_run=true" "workflow run deploy-prod.yml.*dry_run=true" yes
expect_calls "dry: watched with --exit-status" "run watch .*--exit-status" yes
expect_calls "dry: no real dispatch" "dry_run=false" no
run_case "dry: a failing watch fails" 1 dry "[]" STUB_WATCH_EXIT=1
run_case "dry: no run appears" 1 dry "[]" STUB_NO_NEW_RUN=1
expect_out "dry: says it found no run" "no new run"

# deploy refuses without a passed dry run of the same commit
run_case "real: refuses with no run at all" 1 real "[]"
expect_calls "real: nothing dispatched" "workflow run" no
expect_out "real: names the remedy" "make deploy-dry"
run_case "real: refuses a dry run of another commit" 1 real "[$(run "$OTHER" "Deploy evals to prod VPS (dry_run=true sha=$OTHER)" success)]"
expect_calls "real: nothing dispatched (other sha)" "workflow run" no
run_case "real: refuses a failed dry run" 1 real "[$(run "$SHA" "Deploy evals to prod VPS (dry_run=true sha=$SHA)" failure)]"
expect_calls "real: nothing dispatched (failed)" "workflow run" no
run_case "real: refuses a green REAL run (not a dry run)" 1 real "[$(run "$SHA" "Deploy evals to prod VPS (dry_run=false sha=$SHA)" success)]"
expect_calls "real: nothing dispatched (not dry)" "workflow run" no
run_case "real: refuses a push-triggered run" 1 real "[$(run "$SHA" "Deploy evals to prod VPS (dry_run=true sha=$SHA)" success push)]"
run_case "real: accepts a passed dry run of the same commit" 0 real "[$(run "$SHA" "Deploy evals to prod VPS (dry_run=true sha=$SHA)" success)]"
expect_calls "real: dispatched dry_run=false" "workflow run deploy-prod.yml.*dry_run=false" yes
expect_calls "real: watched" "run watch .*--exit-status" yes


# the dispatch names the commit it validated, so main moving in between cannot deploy another one
run_case "dry: passes sha=<validated commit>" 0 dry "[]"
expect_calls "dry: -f sha=SHA" "workflow run deploy-prod.yml.* sha=$SHA" yes
run_case "real: passes sha=<validated commit>" 0 real "[$(run "$SHA" "Deploy evals to prod VPS (dry_run=true sha=$SHA)" success)]"
expect_calls "real: -f sha=SHA" "workflow run deploy-prod.yml.* sha=$SHA.*dry_run=false\|workflow run deploy-prod.yml.*dry_run=false.* sha=$SHA" yes
run_case "real: main moved, the run is of another headSha: never reported as succeeded" 1 real "[$(run "$SHA" "Deploy evals to prod VPS (dry_run=true sha=$SHA)" success)]" STUB_RUN_SHA="$OTHER"
expect_out "real (moved): says no run for the commit" "no new run"
if grep -q "succeeded" "$WORK/out"; then echo "FAIL real (moved): output claims success"; fails=$((fails + 1)); else echo "PASS real (moved): output does not claim success"; fi
expect_calls "real (moved): did not watch a run" "run watch" no
run_case "dry: main moved, the run is of another headSha: not reported as succeeded" 1 dry "[]" STUB_RUN_SHA="$OTHER"
run_case "real: a dry-run title naming another sha does not count" 1 real "[$(run "$SHA" "Deploy evals to prod VPS (dry_run=true sha=$OTHER)" success)]"
expect_calls "real (title sha): nothing dispatched" "workflow run" no

# the workflow's guard step, run the way a runner would: bash, the ${{ }} values supplied, a pass and a fail case
WF="$(cd "$(dirname "$SCRIPT")/../.." && pwd)/.github/workflows/deploy-prod.yml"
STEP="Guard: this run is the commit that was validated"
PYBIN="${PYTHON:-python3}"  # needs PyYAML: make deploy-check passes the venv's
guard() {  # github.sha inputs.sha
  "$PYBIN" "$(dirname "$SCRIPT")/workflow_step.py" "$WF" deploy "$STEP" --sub "github.sha=$1" --sub "inputs.sha=$2" > "$WORK/guard.sh" \
    && (cd "$WORK" && env -i PATH="$PATH" HOME="$WORK" GITHUB_ENV="$WORK/gh_env" GITHUB_OUTPUT="$WORK/gh_out" bash -e "$WORK/guard.sh") > "$WORK/guard.out" 2>&1
}
if guard "$SHA" "$SHA"; then echo "PASS guard: github.sha == inputs.sha passes"; else echo "FAIL guard: same sha was refused"; sed 's/^/    | /' "$WORK/guard.out"; fails=$((fails + 1)); fi
if guard "$OTHER" "$SHA"; then echo "FAIL guard: a moved main was not refused"; fails=$((fails + 1)); else
  if grep -q "$SHA" "$WORK/guard.out" && grep -q "$OTHER" "$WORK/guard.out"; then echo "PASS guard: github.sha != inputs.sha fails, naming both"; else echo "FAIL guard: refused without naming both shas"; sed 's/^/    | /' "$WORK/guard.out"; fails=$((fails + 1)); fi
fi
if guard "$SHA" ""; then echo "FAIL guard: an empty sha input was accepted"; fails=$((fails + 1)); else echo "PASS guard: an empty inputs.sha fails"; fi
if [ "$(grep -n -m1 'name: "Guard: ' "$WF" | cut -d: -f1)" -lt "$(grep -n -m1 'uses: actions/checkout' "$WF" | cut -d: -f1)" ]; then
  echo "PASS guard: it is the first step, before checkout, render and any secret"; else echo "FAIL guard: not before checkout"; fails=$((fails + 1)); fi

# bad usage
run_case "usage: unknown mode" 2 nonsense "[]"

if [ "$fails" = 0 ]; then echo "test_dispatch: PASS"; else echo "test_dispatch: FAIL ($fails)"; exit 1; fi
