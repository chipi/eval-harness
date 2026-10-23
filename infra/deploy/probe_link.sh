#!/usr/bin/env bash
# The query of an inspector link on the built dataset pages, for the deploy's health probes.
#   bash probe_link.sh <catalog public dir>/d [group|one]
# group (default): the first "inspect these arms together" link: several arms (a comma in runs=)
#                  and its metric.
# one:             the first single-arm link (no comma, no other parameter).
# Prints nothing when no page has one. Both are tested off the box (make -C harness test).
set -euo pipefail
dir="${1:?usage: probe_link.sh <dir of dataset pages> [group|one]}"
mode="${2:-group}"
case "$mode" in
  group) pattern='inspect\.html\?runs=[^"]*,[^"]*"' ;;
  one) pattern='inspect\.html\?runs=[^",&]+"' ;;
  *) echo "probe_link.sh: mode is group or one, not $mode" >&2; exit 2 ;;
esac
# sed -n 1p rather than head: head closing the pipe early is a SIGPIPE under pipefail.
grep -ohE "$pattern" "$dir"/*.html 2>/dev/null |
  sed -n '1{s/^inspect\.html?//; s/"$//; s/&amp;/\&/g; p}' || true
