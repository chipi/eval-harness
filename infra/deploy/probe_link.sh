#!/usr/bin/env bash
# The query of the first "inspect these arms together" link on the built dataset pages: several
# arms (a comma in runs=) and its metric. Prints nothing when no page has one.
#   bash probe_link.sh <catalog public dir>/d
set -euo pipefail
dir="${1:?usage: probe_link.sh <dir of dataset pages>}"
# sed -n 1p rather than head: head closing the pipe early is a SIGPIPE under pipefail.
grep -ohE 'inspect\.html\?runs=[^"]*,[^"]*"' "$dir"/*.html 2>/dev/null |
  sed -n '1{s/^inspect\.html?//; s/"$//; s/&amp;/\&/g; p}' || true
