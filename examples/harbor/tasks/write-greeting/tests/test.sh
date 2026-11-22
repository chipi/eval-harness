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
file_exists() { test -f /app/greeting.txt; }
content_is_hello() { [ "$(cat /app/greeting.txt)" = hello ]; }
check file_exists
check content_is_hello
failed=$((total - passed))
printf '{"results": {"tool": {"name": "shell"}, "summary": {"tests": %d, "passed": %d, "failed": %d}, "tests": [%s]}}\n' \
  "$total" "$passed" "$failed" "${results%,}" > /logs/verifier/ctrf.json
if [ "$failed" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
