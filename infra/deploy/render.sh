#!/usr/bin/env bash
# render.sh — assemble one release directory of the `evals` stack, every deploy-time token filled.
#
#   infra/deploy/render.sh <out-dir> <release-sha>
#
# Runs on the CI runner (python3 with pip and pyyaml: the wheel build, the catalog build). The output is what gets
# rsynced to /srv/evals/releases/<sha>/ on the box:
#
#   sites/evals.humancopilot.eu/public/           the findings site (site/public, committed)
#   sites/catalog.evals.humancopilot.eu/public/   the catalog, built here by catalog_build.py
#   inspector/pkg/                                the harness package, installed from its wheel
#   inspector/data/                               runs*, references, datasets, goals: what the
#                                                 inspector reads (no corpora, no materialized text)
#   nginx/  caddy/  observability/  deploy/  compose.yml  RELEASE
#
# Env:
#   EVALS_PORT       loopback port of evals-nginx      (default 8096)
#   INSPECTOR_PORT   loopback port of evals-inspector  (default 8097)
# Template: chipi/humancopilot.eu infra/deploy/render.sh.
set -euo pipefail

OUT="${1:?usage: render.sh <out-dir> <release-sha>}"
SHA="${2:?usage: render.sh <out-dir> <release-sha>}"
PORT="${EVALS_PORT:-8096}"
IPORT="${INSPECTOR_PORT:-8097}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RELEASE_DIR="/srv/evals/releases/${SHA}"
SITE=evals.humancopilot.eu
CATALOG=catalog.evals.humancopilot.eu

[[ "$SHA" =~ ^[0-9a-f]{7,40}$ ]] || { echo "::error::release sha must be hex: $SHA"; exit 1; }
[[ "$PORT" =~ ^[0-9]+$ && "$IPORT" =~ ^[0-9]+$ ]] || { echo "::error::ports must be numeric"; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT"/{sites,nginx,caddy,observability,deploy,inspector/pkg,inspector/data}
cp -a "$ROOT/infra/nginx/." "$OUT/nginx/"
cp -a "$ROOT/infra/caddy/." "$OUT/caddy/"
cp -a "$ROOT/infra/observability/evals.alloy" "$OUT/observability/"
cp -a "$ROOT/infra/deploy/deploy.sh" "$ROOT/infra/deploy/install_vhosts.sh" "$ROOT/infra/deploy/install_alloy.sh" \
  "$ROOT/infra/deploy/probe_link.sh" "$OUT/deploy/"
cp -a "$ROOT/infra/compose.yml" "$OUT/compose.yml"

# The findings site, as committed (`make ci` fails when site/public is stale).
mkdir -p "$OUT/sites/$SITE"
cp -a "$ROOT/site/public" "$OUT/sites/$SITE/public"

# The inspector: the harness PACKAGE, installed from the wheel pyproject.toml builds (a copy
# of scripts/ would hide anything package-data leaves out, the reason the tests install the
# wheel too), and the data the catalog and the inspector read (runs, references, datasets,
# goals, baselines, rounds, configs, scorers, judging sets and verdicts), nothing else: without
# baselines and rounds the goal pages showed neither. A directory of files: nothing is
# installed on the box.
python3 "$ROOT/harness/tools/_wheel.py" install "$OUT/inspector/pkg"
# The inspector reads the goals (YAML) and runs on the stock Python image, which has no PyYAML:
# its pure-Python package goes beside the harness. The compiled extension is dropped, so it runs
# on any architecture (PyYAML falls back to Python without it). Without it every comparison
# answered 500 while /api/health stayed 200.
python3 -m pip install --quiet --no-deps --target "$OUT/inspector/.pyyaml" "pyyaml==6.0.2"
cp -a "$OUT/inspector/.pyyaml/yaml" "$OUT/inspector/pkg/yaml"
rm -rf "$OUT/inspector/.pyyaml"
find "$OUT/inspector/pkg/yaml" -name '_yaml*.so' -delete
for d in "$ROOT"/harness/data/runs* "$ROOT"/harness/data/{references,datasets,goals,baselines,rounds,configs,scorers,judging-sets,judge-verdicts}; do
  [ -d "$d" ] && cp -a "$d" "$OUT/inspector/data/"
done

# The catalog, built from that same copy of the data, so the pages and the API cannot disagree.
# The runs name their adapters (examples/<example>/adapter.py), whose METRIC_DESCRIPTIONS and
# METRIC_KINDS the metric pages read: they sit beside the data for the build only, not shipped.
cp -a "$ROOT/examples" "$OUT/inspector/examples"
EVAL_HOME="$OUT/inspector" python3 "$OUT/inspector/pkg/evaluation_harness/catalog_build.py" \
  --out "$OUT/sites/$CATALOG/public" \
  --link "Findings=https://$SITE/" --link "Docs=https://docs.$SITE/"
rm -rf "$OUT/inspector/examples"
# The build above ran the package's code; its bytecode is not part of the release.
find "$OUT/inspector/pkg" -name __pycache__ -type d -prune -exec rm -rf {} +

for site_dir in "$OUT"/sites/*/; do
  domain="$(basename "$site_dir")"
  [ -f "$ROOT/infra/nginx/sites/${domain}.conf" ] || { echo "::error::sites/$domain has no infra/nginx/sites/${domain}.conf"; exit 1; }
  CSP_REPORT_URI=""
  # infra/sites/<domain>.cfg, not .env: the repo ignores every *.env so no secret is ever
  # committed, and this file (public settings only) must be.
  # shellcheck disable=SC1090
  [ -f "$ROOT/infra/sites/${domain}.cfg" ] && . "$ROOT/infra/sites/${domain}.cfg"

  # Cache-bust: assets are cached for an hour under fixed names, so every reference carries the
  # release sha (relative references too: ../assets/ from a page one level down).
  find "$site_dir/public" -name '*.html' -exec \
    sed -i -E "s#((href|src)=\"(/|(\.\./)*)assets/[^\"?]+)\"#\\1?v=${SHA}\"#g" {} +

  snippet="$OUT/nginx/snippets/${domain}-headers.conf"
  if [ -n "$CSP_REPORT_URI" ]; then
    [[ "$CSP_REPORT_URI" =~ ^https://[A-Za-z0-9./?=_-]+$ ]] || { echo "::error::$domain CSP_REPORT_URI has unexpected characters"; exit 1; }
    sed -i "s#__CSP_REPORT__#report-uri ${CSP_REPORT_URI};#" "$snippet"
  else
    sed -i 's#; __CSP_REPORT__#;#; s#__CSP_REPORT__##' "$snippet"
  fi
done

find "$OUT/nginx" -type f -exec sed -i "s#__RELEASE_DIR__#${RELEASE_DIR}#g" {} +
find "$OUT/caddy" -type f -name '*.caddy' -exec sed -i "s#__EVALS_PORT__#${PORT}#g; s#__INSPECTOR_PORT__#${IPORT}#g" {} +
printf '%s\n' "$SHA" > "$OUT/RELEASE"

# Any token left means a placeholder nobody filled: never ship it.
if left="$(grep -rnoE '__[A-Z][A-Z0-9_]+__' "$OUT/nginx" "$OUT/caddy" "$OUT/sites" "$OUT/compose.yml" 2>/dev/null | grep -v '__pycache__')"; then
  echo "::error::unrendered tokens in the release:"; echo "$left"; exit 1
fi
echo "rendered release $SHA into $OUT (nginx $PORT, inspector $IPORT)"
