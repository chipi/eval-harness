#!/usr/bin/env bash
# install_alloy.sh — install this repo's Alloy drop-in into the shared node Alloy, validated as
# the SET Alloy will load, then prove the reload took. Runs on the box as deploy@.
# Copied unchanged in logic from chipi/humancopilot.eu infra/deploy/install_alloy.sh (the
# prod session's pattern); only the file name differs.
#
#   install_alloy.sh <path/to/evals.alloy>
#
# Pattern copied from podcast_scraper's scripts/ops/deploy_config_alloy.sh (same box, same
# Alloy). Why the whole set: Alloy loads config.d as ONE configuration, so our file is only
# valid together with base.alloy (which defines discovery.docker "app" and loki.write
# "logs_sink") and every other tenant's drop-in. A refused HUP keeps the OLD config running and
# only logs "failed to reload config", so the verdict is read from Alloy's own
# alloy_config_last_load_* metrics, and our file is rolled back if the reload was refused or
# gave no verdict. We only ever write config.d/evals.alloy.
# Env: DRY_RUN=true validates only.
set -euo pipefail

SRC="${1:?usage: install_alloy.sh <evals.alloy>}"
NAME=evals.alloy
DIR=/opt/vps-observability/config.d
CAND="$(mktemp -d /tmp/evals-alloy-candidate.XXXXXX)"   # visible to the container at /rootfs/tmp
BK="$(mktemp -d)"
trap 'rm -rf "$CAND" "$BK"' EXIT

[ -d "$DIR" ] || { echo "::error::$DIR missing; is the node Alloy installed?"; exit 1; }
if [ -f "$DIR/$NAME" ] && cmp -s "$SRC" "$DIR/$NAME"; then changed=0; else changed=1; fi

cp "$DIR"/*.alloy "$CAND"/
cp "$SRC" "$CAND/$NAME"
chmod 0755 "$CAND"; chmod 0644 "$CAND"/*.alloy
if docker exec alloy alloy validate "/rootfs$CAND" >/dev/null 2>&1; then
  echo "  alloy set valid with $NAME ($(find "$CAND" -name '*.alloy' | wc -l) files)"
else
  echo "::error::alloy set INVALID with $NAME; nothing installed, no HUP"
  docker exec alloy alloy validate "/rootfs$CAND" 2>&1 | head -30 >&2 || true
  exit 1
fi

metric() {
  curl -fsS --max-time 5 http://127.0.0.1:12345/metrics 2>/dev/null \
    | awk -v m="$1" '$1 == m { v = $2 } END { if (v != "") print v }' || true
}
before="$(metric alloy_config_last_load_success_timestamp_seconds)"

if [ "${DRY_RUN:-false}" = "true" ]; then echo "  DRY-RUN: valid; nothing installed"; exit 0; fi
if [ "$changed" = 0 ]; then echo "  $NAME unchanged; alloy not reloaded"; exit 0; fi
[ -n "$before" ] || { echo "::error::cannot read alloy's metrics; nothing installed, no HUP"; exit 1; }

# Stage-then-rename: a half-written *.alloy must never be loadable. The staging name does not
# end in .alloy, so Alloy ignores it.
[ -f "$DIR/$NAME" ] && cp -a "$DIR/$NAME" "$BK/$NAME"
cp "$SRC" "$DIR/.$NAME.incoming" && chmod 0644 "$DIR/.$NAME.incoming" && mv -f "$DIR/.$NAME.incoming" "$DIR/$NAME"

restore() {
  if [ -f "$BK/$NAME" ]; then cp "$BK/$NAME" "$DIR/.$NAME.incoming" && mv -f "$DIR/.$NAME.incoming" "$DIR/$NAME"
  else rm -f "$DIR/$NAME"; fi
  docker kill -s HUP alloy >/dev/null || true
}

docker kill -s HUP alloy >/dev/null || { echo "::error::could not HUP alloy; rolling back"; restore; exit 1; }
verdict=""
for _ in $(seq 1 15); do
  sleep 2
  ok="$(metric alloy_config_last_load_successful)"
  ts="$(metric alloy_config_last_load_success_timestamp_seconds)"
  if [ "$ok" = "0" ]; then verdict=failed; break; fi
  if [ "$ok" = "1" ] && [ -n "$ts" ] && [ "$ts" != "$before" ]; then verdict=ok; break; fi
done
case "$verdict" in
  ok) echo "  alloy reloaded with $NAME" ;;
  failed)
    echo "::error::alloy REFUSED the reload; restoring the previous $NAME"
    docker logs alloy --since 2m 2>&1 | grep 'failed to reload config' | tail -3 >&2 || true
    restore; exit 1 ;;
  *) echo "::error::alloy gave no reload verdict within 30s; restoring the previous $NAME"; restore; exit 1 ;;
esac
