#!/bin/bash
mkdir -p /logs/verifier
passed=0
total=0
results=""
check() {
  total=$((total + 1))
  if eval "$2"; then passed=$((passed + 1)); s=passed; else s=failed; fi
  results="$results{\"name\": \"$1\", \"status\": \"$s\"},"
}
check script_is_executable 'test -x /app/hi.sh'
check script_prints_hi_there '[ "$(/app/hi.sh)" = "hi there" ]'
failed=$((total - passed))
printf '{"results": {"tool": {"name": "shell"}, "summary": {"tests": %d, "passed": %d, "failed": %d}, "tests": [%s]}}\n' \
  "$total" "$passed" "$failed" "${results%,}" > /logs/verifier/ctrf.json
if [ "$failed" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
