#!/usr/bin/env bash
# install_vhosts.sh — sync this repo's vhosts into the shared Caddy edge, gated by `caddy adapt`.
#
#   install_vhosts.sh <caddy-src-dir>     (runs on the box as deploy@)
#
# Ownership (podcast_scraper ADR-114): the edge engine, base Caddyfile, `hardened` snippet and the
# deploy@ reload grant belong to podcast_scraper. This script touches ONLY the files this repo
# owns: the basenames of <src>/*.caddy. It never lists, edits or removes anyone else's vhost.
#
#   - a name in <src>/enabled.txt   → installed (or updated) in /etc/caddy/sites/
#   - an owned name not listed      → removed from /etc/caddy/sites/ if present
#
# Then the merged config is checked with `caddy adapt` (not `validate`: validate opens the
# caddy-owned log files and fails as deploy@). On failure every touched file is restored and
# Caddy is not reloaded. Reload is graceful (admin unix socket); restart only as a fallback.
# Pattern copied from orrery's ops/deploy_caddy_vhosts.sh, which runs against the same edge.
# Copied unchanged from chipi/humancopilot.eu infra/deploy/install_vhosts.sh.
# Env: DRY_RUN=true installs + adapts, then restores and does not reload.
set -euo pipefail

SRC="${1:?usage: install_vhosts.sh <caddy-src-dir>}"
SITES=/etc/caddy/sites
BK="$(mktemp -d)"
trap 'rm -rf "$BK"' EXIT

# One lock for every tenant that edits /etc/caddy/sites (proposed by the prod session for
# podcast_scraper and orrery too), so two install → adapt → reload sequences never interleave.
LOCK=/tmp/caddy-sites.lock
exec 9>>"$LOCK"
flock -w 300 9 || { echo "::error::could not take $LOCK within 5 minutes; another tenant is editing the edge"; exit 1; }

mapfile -t OWNED < <(find "$SRC" -maxdepth 1 -name '*.caddy' -printf '%f\n' | sed 's/\.caddy$//' | sort)
mapfile -t ENABLED < <(grep -vE '^\s*(#|$)' "$SRC/enabled.txt" 2>/dev/null | tr -d ' \t' | sort -u)

for e in "${ENABLED[@]}"; do
  printf '%s\n' "${OWNED[@]}" | grep -qx "$e" || { echo "::error::enabled.txt names '$e', which is not a vhost in $SRC"; exit 1; }
done

# A vhost whose hostname does not resolve makes Caddy retry ACME and burn Let's Encrypt's
# failure budget. An enabled vhost is installed only when EVERY site address in it resolves;
# otherwise it is left out (warning) and the next deploy after DNS is live picks it up.
# Pattern from orrery's deploy_caddy_vhosts.sh.
ready=()
for e in "${ENABLED[@]}"; do
  missing=""
  while read -r name; do
    getent hosts "$name" >/dev/null 2>&1 || missing="$missing $name"
  done < <(grep -oE '^[a-z0-9.-]+\.[a-z]{2,}( [a-z0-9.-]+\.[a-z]{2,})* \{' "$SRC/$e.caddy" | tr -d '{' | tr ' ' '\n' | grep .)
  if [ -n "$missing" ]; then
    echo "::warning::$e.caddy not installed: does not resolve yet:$missing (no ACME churn; redeploy once DNS is live)"
  else
    ready+=("$e")
  fi
done
ENABLED=(${ready[@]+"${ready[@]}"})

changed=0
touched=()
for v in "${OWNED[@]}"; do
  cur="$SITES/$v.caddy"
  if printf '%s\n' "${ENABLED[@]}" | grep -qx "$v"; then
    if [ -f "$cur" ] && cmp -s "$SRC/$v.caddy" "$cur"; then echo "  $v.caddy unchanged"; continue; fi
    [ -f "$cur" ] && cp -a "$cur" "$BK/$v.caddy"
    touched+=("$v")
    cp "$SRC/$v.caddy" "$cur" && chmod 0644 "$cur"
    changed=1; echo "  $v.caddy installed"
  elif [ -f "$cur" ]; then
    cp -a "$cur" "$BK/$v.caddy"
    touched+=("$v")
    rm -f "$cur"
    changed=1; echo "  $v.caddy removed (not in enabled.txt)"
  fi
done

restore() {
  for v in "${touched[@]}"; do
    if [ -f "$BK/$v.caddy" ]; then cp "$BK/$v.caddy" "$SITES/$v.caddy"; else rm -f "$SITES/$v.caddy"; fi
  done
  return 0
}

if [ "$changed" = 0 ]; then echo "  no vhost changed; caddy not reloaded"; exit 0; fi

# The base Caddyfile interpolates env from caddy's systemd drop-ins; resolve it for adapt.
# Accept both `Environment=K=v` and `Environment="K=v1 v2"` (podcast_scraper quotes the bind
# line so systemd keeps the IPv6 address; same reader as its scripts).
envval() { sed -n -E "s/^Environment=\"?$1=([^\"]*)\"?[[:space:]]*\$/\\1/p" "$2" 2>/dev/null || true; }
BIND="$(envval CADDY_BIND_ADDRS /etc/systemd/system/caddy.service.d/10-public-bind.conf)"
GT="$(envval GLITCHTIP_UPSTREAM /etc/systemd/system/caddy.service.d/20-glitchtip-upstream.conf)"
if [ -z "$BIND" ]; then
  echo "::error::could not read CADDY_BIND_ADDRS from caddy's systemd drop-in; restoring, NOT reloading"
  restore; exit 1
fi
adapt() { CADDY_BIND_ADDRS="$BIND" GLITCHTIP_UPSTREAM="$GT" caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile; }

if adapt >/dev/null 2>&1; then
  echo "  caddy config valid"
else
  echo "::error::caddy config INVALID with our vhosts; restoring, NOT reloading"
  restore
  adapt 2>&1 >/dev/null | head -20 >&2 || true
  exit 1
fi

if [ "${DRY_RUN:-false}" = "true" ]; then echo "  DRY-RUN: valid; restoring, not reloading"; restore; exit 0; fi

if sudo -n /usr/bin/systemctl reload caddy && systemctl is-active --quiet caddy; then
  echo "  caddy reloaded"
elif echo "::warning::caddy refused the reload; RESTARTING THE SHARED EDGE (drops every tenant's connections for seconds)" &&
     sudo -n /usr/bin/systemctl restart caddy && systemctl is-active --quiet caddy; then
  echo "::warning::caddy restarted (reload refused)"
else
  echo "::error::caddy failed to load; restoring our vhosts and restarting the shared edge to last-good"
  restore
  sudo -n /usr/bin/systemctl restart caddy || true
  exit 1
fi
