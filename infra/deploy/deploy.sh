#!/usr/bin/env bash
# deploy.sh — activate one rendered release of the `evals` stack on the prod VPS.
#
# Runs ON THE BOX as deploy@, from the release directory the workflow just rsynced:
#   bash /srv/evals/releases/<sha>/deploy/deploy.sh
#
# Steps, each one a gate (template: chipi/humancopilot.eu infra/deploy/deploy.sh):
#   1. Preflight: both loopback ports are free or already ours.
#   2. `nginx -t` on the NEW release's config, in a throwaway container, before anything moves.
#   2b. Ship the Alloy drop-in (install_alloy.sh: validates the whole set, confirms the reload),
#      BEFORE the containers are recreated, so their log tailers start under this release's rules.
#   3. Switch the `current` symlink atomically, `compose up` (both containers are recreated: the
#      inspector loads the new release's code and data, and each gets a new Alloy log tailer with the
#      release's labels), reload nginx.
#   4. Health: every site answers 200 on / and 404 on a missing page, on the loopback port with
#      its own Host header; the inspector answers /api/health and a real comparison.
#      On any failure in 3 or 4: point `current` back at the previous release, `compose up` its
#      compose.yml (undoes an image bump) and reload. Steps 2b and 6 have their own restore.
#   6. Install/remove our Caddy vhosts per caddy/enabled.txt (install_vhosts.sh).
#   7. Keep the last 5 releases.
#
# Env: EVALS_PORT (default 8096), INSPECTOR_PORT (default 8097). DRY_RUN=true stops after step 2.
set -euo pipefail

BASE=/srv/evals
REL="$(cd "$(dirname "$0")/.." && pwd)"
SHA="$(cat "$REL/RELEASE")"
PORT="${EVALS_PORT:-8096}"
IPORT="${INSPECTOR_PORT:-8097}"
NGINX=evals-nginx
INSPECTOR=evals-inspector
SITE_HOST=evals.humancopilot.eu
IMAGE="$(sed -n 's/^ *image: *\(nginxinc\/.*\)/\1/p;T;q' "$REL/compose.yml")"
COMPOSE=(docker compose -p evals -f "$BASE/current/compose.yml")
export EVALS_PORT="$PORT" INSPECTOR_PORT="$IPORT"

[ "$REL" = "$BASE/releases/$SHA" ] || { echo "::error::release dir $REL is not $BASE/releases/$SHA"; exit 1; }
echo "== deploying evals release $SHA (nginx $PORT, inspector $IPORT)"

# 1. Ports: free, or held by our own containers.
for pair in "$PORT:$NGINX" "$IPORT:$INSPECTOR"; do
  p="${pair%%:*}"; want="${pair#*:}"
  holder="$(docker ps --filter "publish=$p" --format '{{.Names}}' || true)"
  if ss -ltnH "sport = :$p" | grep -q . && [ "$holder" != "$want" ]; then
    echo "::error::127.0.0.1:$p is in use by something other than $want (${holder:-a host process}); refusing to deploy"
    exit 1
  fi
done

# 2. Validate the new config before switching anything.
docker run --rm --read-only --tmpfs /tmp:uid=101,gid=101 -v "$BASE:$BASE:ro" \
  --entrypoint nginx "$IMAGE" -t -q -c "$REL/nginx/nginx.conf"
echo "  nginx config valid"
if [ "${DRY_RUN:-false}" = "true" ]; then echo "  DRY-RUN: stopping before the switch"; exit 0; fi

# 2b. Logs: our Alloy drop-in (evals-nginx, evals-inspector), validated with the whole set (it
# restores the previous set itself if Alloy refuses). BEFORE the containers are recreated: Alloy
# keeps a running container's log tailer on the label set it started with across a reload, so a
# container started before a changed drop-in loads ships without the new labels until it is
# recreated (0.4.2: evals-nginx without `release`; homelab reproduced it). Recreated after this
# step, both get tailers under this release's rules. The inspector's /metrics scrape reads up=0
# for the seconds until step 3 has it running.
bash "$REL/deploy/install_alloy.sh" "$REL/observability/evals.alloy"

# 3. Switch. From here on any failure rolls back the WHOLE release: content, configs, and the
# containers themselves (compose.yml of the previous release, so an image bump is undone too).
prev="$(readlink "$BASE/current" 2>/dev/null || true)"
rollback() {
  echo "::error::$1"
  if [ -n "$prev" ] && [ -d "$prev" ]; then
    ln -sfn "$prev" "$BASE/current.new" && mv -T "$BASE/current.new" "$BASE/current"
    "${COMPOSE[@]}" up -d --wait --wait-timeout 90 --force-recreate inspector || echo "::error::compose up of $prev failed too"
    "${COMPOSE[@]}" up -d --wait --wait-timeout 60 --force-recreate nginx || true
    docker exec "$NGINX" nginx -c "$BASE/current/nginx/nginx.conf" -s reload || true
    echo "  rolled back: current -> $prev (containers and config)"
  else
    echo "  no previous release to roll back to (first deploy); stopping the stack"
    "${COMPOSE[@]}" down || true
  fi
  exit 1
}
ln -sfn "$REL" "$BASE/current.new" && mv -T "$BASE/current.new" "$BASE/current"
# Recreated on every release too, not only when compose sees a change: a new container is a new
# log tailer in Alloy, under the rules step 2b installed, so its lines carry this release's labels.
"${COMPOSE[@]}" up -d --wait --wait-timeout 60 --force-recreate nginx || rollback "compose up of nginx ($SHA) failed"
# The inspector keeps its code, data and caches in memory: recreate it on every release.
"${COMPOSE[@]}" up -d --wait --wait-timeout 90 --force-recreate inspector || rollback "compose up of the inspector ($SHA) failed"
docker exec "$NGINX" nginx -c "$BASE/current/nginx/nginx.conf" -s reload || rollback "nginx reload of $SHA failed"
echo "  current -> $REL (previous: ${prev:-none})"

# 4. Health, per site, through nginx with the real Host header; then the inspector.
sleep 1
for site in "$REL"/sites/*/; do
  host="$(basename "$site")"
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $host" "http://127.0.0.1:$PORT/")"
  [ "$code" = 200 ] || rollback "health check failed: $host / returned $code"
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $host" "http://127.0.0.1:$PORT/no-such-page-$SHA")"
  [ "$code" = 404 ] || rollback "health check failed: $host 404 page returned $code"
  echo "  $host ok"
done
# The catalog's pages and the docs, under /catalog/ and /docs/ on the site's host.
for path in catalog docs; do
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $SITE_HOST" "http://127.0.0.1:$PORT/$path/")"
  [ "$code" = 200 ] || rollback "health check failed: $SITE_HOST/$path/ returned $code"
  echo "  $SITE_HOST/$path/ ok"
done
code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $SITE_HOST" "http://127.0.0.1:$IPORT/api/health")"
[ "$code" = 200 ] || rollback "health check failed: inspector /api/health returned $code"
# A real question, one arm from a dataset page's own links: the inspector reads this release's
# data. probe_link.sh holds the extraction, so it is tested off the box (make -C harness test).
q="$(bash "$REL/deploy/probe_link.sh" "$REL/sites/$SITE_HOST/public/catalog/d" one)"
if [ -n "$q" ]; then
  body="$(curl -s -m 120 -H "Host: $SITE_HOST" "http://127.0.0.1:$IPORT/api/compare?$q")"
  grep -q '"rows"' <<<"$body" || rollback "health check failed: the inspector did not answer a comparison (${body:0:200})"
fi
# And the question readers send most: a dataset page's group button, several arms on one
# metric (its URL carries `,` and `&metric=`). It must come back with verdict rows, not an
# error. probe_link.sh holds the extraction, so it is tested off the box (make -C harness test).
q2="$(bash "$REL/deploy/probe_link.sh" "$REL/sites/$SITE_HOST/public/catalog/d")"
if [ -n "$q2" ]; then
  body="$(curl -s -m 180 -H "Host: $SITE_HOST" "http://127.0.0.1:$IPORT/api/compare?$q2")"
  if ! { grep -q '"rows": \[{' <<<"$body" && ! grep -q '"error"' <<<"$body"; }; then
    rollback "health check failed: the inspector did not test a group of arms (${body:0:200})"
  fi
fi
echo "  inspector ok"

# 6. Edge vhosts.
bash "$REL/deploy/install_vhosts.sh" "$REL/caddy"

# 7. Prune: keep the 5 newest releases, never the current one.
cur="$(readlink "$BASE/current")"
find "$BASE/releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -rn | tail -n +6 | cut -d' ' -f2- |
  while read -r old; do
    [ "$old" = "$cur" ] || rm -rf -- "$old"
  done
echo "== release $SHA live on 127.0.0.1:$PORT (nginx) and 127.0.0.1:$IPORT (inspector)"
