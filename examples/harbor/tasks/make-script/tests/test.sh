#!/bin/bash
mkdir -p /logs/verifier
passed=0
total=0
results=""
# check NAME: runs the function of that name and records whether it succeeded
check() {
  total=$((total + 1))
  if "$1"; then passed=$((passed + 1)); s=passed; else s=failed; fi
  results="$results{\"name\": \"$1\", \"status\": \"$s\"},"
}
script_is_executable() { test -x /app/hi.sh; }
script_prints_hi_there() { [ "$(/app/hi.sh)" = "hi there" ]; }
check script_is_executable
check script_prints_hi_there
failed=$((total - passed))
printf '{"results": {"tool": {"name": "shell"}, "summary": {"tests": %d, "passed": %d, "failed": %d}, "tests": [%s]}}\n' \
  "$total" "$passed" "$failed" "${results%,}" > /logs/verifier/ctrf.json
if [ "$failed" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
