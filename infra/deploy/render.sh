#!/usr/bin/env bash
# render.sh — assemble one release directory of the `evals` stack, every deploy-time token filled.
#
#   infra/deploy/render.sh <out-dir> <release-sha>
#
# Runs on the CI runner (python3 with pip and pyyaml: the wheel build, the catalog build). The output is what gets
# rsynced to /srv/evals/releases/<sha>/ on the box:
#
#   sites/evals.humancopilot.eu/public/           the findings site (site/public, committed)
#   sites/evals.humancopilot.eu/catalog/public/   the catalog, built here by catalog_build.py
#   inspector/pkg/                                the harness package, installed from its wheel
#   inspector/hooks.py, inspector/vendor/         the observability layer and its SDKs (infra/inspector/)
#   inspector/data/                               runs*, references, datasets, goals, profiles,
#                                                 models.yaml: what the catalog and inspector read
#                                                 (no corpora, no materialized text;
#                                                 harness/tests/test_render_data.py checks the list)
#   nginx/  caddy/  observability/  deploy/  compose.yml  RELEASE
#
# Env:
#   EVALS_PORT       loopback port of evals-nginx      (default 8096)
#   INSPECTOR_PORT   loopback port of evals-inspector  (default 8097)
#   MCP_PORT         loopback port of evals-mcp        (default 8098)
# Template: chipi/humancopilot.eu infra/deploy/render.sh.
set -euo pipefail

OUT="${1:?usage: render.sh <out-dir> <release-sha>}"
SHA="${2:?usage: render.sh <out-dir> <release-sha>}"
PORT="${EVALS_PORT:-8096}"
IPORT="${INSPECTOR_PORT:-8097}"
MPORT="${MCP_PORT:-8098}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RELEASE_DIR="/srv/evals/releases/${SHA}"
SITE=evals.humancopilot.eu

[[ "$SHA" =~ ^[0-9a-f]{7,40}$ ]] || { echo "::error::release sha must be hex: $SHA"; exit 1; }
[[ "$PORT" =~ ^[0-9]+$ && "$IPORT" =~ ^[0-9]+$ && "$MPORT" =~ ^[0-9]+$ ]] || { echo "::error::ports must be numeric"; exit 1; }

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
# The observability layer (infra/inspector/hooks.py, the harness's --hooks): this deployment's, not
# the harness's. Its SDKs as pure-Python wheels only, pinned, beside the package (PYTHONPATH in
# compose.yml), so the stock image runs them; nothing is installed on the box.
python3 -m pip install --quiet --no-deps --no-compile --target "$OUT/inspector/vendor" \
  --only-binary=:all: --platform any --implementation py --python-version 3.12 \
  -r "$ROOT/infra/inspector/requirements.txt"
cp -a "$ROOT/infra/inspector/hooks.py" "$OUT/inspector/hooks.py"
# The MCP server (evals-mcp, RFC-018): the same package and data, plus the official MCP SDK and its
# dependencies, pinned (infra/mcp/requirements.txt), as wheels for the box (x86_64, musl: the
# image is Alpine), beside the package; its hooks (GlitchTip, traces, /metrics, Umami) reuse the
# inspector's vendored SDKs. Nothing is installed on the box.
python3 -m pip install --quiet --no-deps --no-compile --target "$OUT/inspector/mcpvendor" \
  --only-binary=:all: --platform musllinux_1_2_x86_64 --platform musllinux_1_1_x86_64 \
  --implementation cp --python-version 3.12 \
  --abi cp312 --abi abi3 --abi none --require-hashes -r "$ROOT/infra/mcp/requirements.txt"
cp -a "$ROOT/infra/mcp/hooks.py" "$OUT/inspector/mcp_hooks.py"
# Its Umami events go to the site's own website (the id is public, site/analytics.json); where to
# send them (UMAMI_SEND_URL, on the tailnet) is in observability.env, rendered by the deploy.
python3 - "$ROOT/site/analytics.json" > "$OUT/inspector/mcp_umami.json" <<'PY'
import json, sys
print(json.dumps({"website_id": json.load(open(sys.argv[1])).get("website_id") or ""}))
PY
for d in "$ROOT"/harness/data/runs* "$ROOT"/harness/data/{references,datasets,goals,baselines,rounds,configs,scorers,judging-sets,judge-verdicts,profiles,fields}; do
  [ -d "$d" ] && cp -a "$d" "$OUT/inspector/data/"
done
# The data files the catalog reads beside the directories (0.4.2's models.yaml: the arms page's
# weights; without it every model read as unknown on the deployed pages).
if [ -f "$ROOT/harness/data/models.yaml" ]; then
  cp -a "$ROOT/harness/data/models.yaml" "$OUT/inspector/data/"
fi

# The documentation, under /docs/ on the site (mkdocs.yml, site_url .../docs/).
python3 -m mkdocs build --strict --quiet -f "$ROOT/mkdocs.yml" -d "$OUT/sites/$SITE/public/docs"

# The catalog, built from that same copy of the data, so the pages and the API cannot disagree.
# The runs name their adapters (examples/<example>/adapter.py), whose METRIC_DESCRIPTIONS and
# METRIC_KINDS the metric pages read: they sit beside the data for the build only, not shipped.
cp -a "$ROOT/examples" "$OUT/inspector/examples"
# This deployment's analytics in the catalog's pages (the harness adds none): the site's Umami tag,
# from the same site/analytics.json, through catalog_build's --head.
python3 - "$ROOT/site/analytics.json" > "$OUT/catalog-head.html" <<'PY'
import html, json, sys
c = json.load(open(sys.argv[1]))
if c.get("umami_src") and c.get("website_id"):
    d = f' data-domains="{html.escape(c["domains"])}"' if c.get("domains") else ""
    print(f'<script defer src="{html.escape(c["umami_src"])}" data-website-id="{html.escape(c["website_id"])}"{d}></script>')
PY
# The goals' tests the build runs are kept (stats' EVH_P_CACHE), so the MCP server's commands, each
# a fresh process, read them instead of drawing them again (~50 s a view without it). The file is
# part of the release, read-only on the box.
mkdir -p "$OUT/inspector/cache"
EVH_P_CACHE="$OUT/inspector/cache/evh-p.jsonl" \
  EVAL_HOME="$OUT/inspector" python3 "$OUT/inspector/pkg/evaluation_harness/catalog_build.py" \
  --out "$OUT/sites/$SITE/public/catalog" \
  --link "Harness=https://$SITE/" --link "Catalog=." --link "Docs=https://$SITE/docs/" --link "MCP=https://$SITE/#mcp" \
  --mcp "https://$SITE/mcp" --mcp-howto "https://$SITE/docs/harness/INTEGRATION/#for-an-agent-evh-mcp" --brand eval-harness --api /catalog/api/ \
  --head "$OUT/catalog-head.html" --about "$ROOT/infra/catalog/about.html" \
  --repo "https://github.com/${GITHUB_REPOSITORY:-chipi/eval-harness}/blob/main/"
rm -rf "$OUT/inspector/examples" "$OUT/catalog-head.html"
# The build above ran the package's code; its bytecode is not part of the release.
find "$OUT/inspector/pkg" -name __pycache__ -type d -prune -exec rm -rf {} +

# The site's and the docs' footers say "build: local" (a commit cannot hold its own hash): the
# release names the commit it was built from. A page left saying "build: local" fails the render.
link="build: <a href=\"https://github.com/${GITHUB_REPOSITORY:-chipi/eval-harness}/commit/${SHA}\">${SHA:0:7}</a>"
{ grep -rlF --include='*.html' 'build: local' "$OUT/sites" || true; } | xargs -r sed -i "s#build: local#${link}#g"
left="$({ grep -rlF --include='*.html' 'build: local' "$OUT/sites" || true; } | wc -l)"
[ "$left" -eq 0 ] || { echo "::error::$left page(s) still say 'build: local'"; exit 1; }
{ grep -rlF --include='*.html' "${SHA:0:7}</a>" "$OUT/sites" || true; } | grep -q . \
  || { echo "::error::no page names the commit ${SHA:0:7}"; exit 1; }

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

  # The site's header snippets: its own, its docs' and its catalog's (<domain>-*-headers.conf).
  for snippet in "$OUT/nginx/snippets/${domain}"*-headers.conf; do
    if [ -n "$CSP_REPORT_URI" ]; then
      [[ "$CSP_REPORT_URI" =~ ^https://[A-Za-z0-9./?=_-]+$ ]] || { echo "::error::$domain CSP_REPORT_URI has unexpected characters"; exit 1; }
      sed -i "s#__CSP_REPORT__#report-uri ${CSP_REPORT_URI};#" "$snippet"
    else
      sed -i 's#; __CSP_REPORT__#;#; s#__CSP_REPORT__##' "$snippet"
    fi
  done
done

find "$OUT/nginx" -type f -exec sed -i "s#__RELEASE_DIR__#${RELEASE_DIR}#g" {} +
find "$OUT/caddy" -type f -name '*.caddy' -exec sed -i "s#__EVALS_PORT__#${PORT}#g; s#__INSPECTOR_PORT__#${IPORT}#g; s#__MCP_PORT__#${MPORT}#g" {} +
printf '%s\n' "$SHA" > "$OUT/RELEASE"
# The containers' `release` label, as the hooks name it (sha-<7>): one string in the logs, GlitchTip
# and the traces.
sed -i "s#__RELEASE__#sha-${SHA:0:7}#g" "$OUT/compose.yml"

# Any token left means a placeholder nobody filled: never ship it.
# JavaScript and source maps are skipped: the docs theme's bundles carry __PURE__ annotations.
if left="$(grep -rnoE --exclude='*.js' --exclude='*.map' '__[A-Z][A-Z0-9_]+__' "$OUT/nginx" "$OUT/caddy" "$OUT/sites" "$OUT/compose.yml" 2>/dev/null | grep -v '__pycache__')"; then
  echo "::error::unrendered tokens in the release:"; echo "$left"; exit 1
fi
# What a release must never carry, whatever the checkout it was rendered from holds: reference texts
# git does not track (a gold reference is not committed; a working copy may have fetched it) and
# materialized items. The tracked ones (the synthetic smoke_v1 silver) are public already. The
# list is built whole, never cut by `head` in the pipe: under pipefail that killed `find` with
# SIGPIPE, the assignment failed, and the check passed with 1,657 texts in the release (an
# independent review, 2026-10-29).
tracked_refs="$(git -C "$ROOT" ls-files -- harness/data/references | sed 's#^harness/data/##' | sort)"
leaked="$( (cd "$OUT/inspector/data" 2>/dev/null && find references -type f ! -name manifest.json | sort) | comm -23 - <(printf '%s\n' "$tracked_refs") || true)"
if [ -n "$leaked" ]; then
  echo "::error::$(wc -l <<<"$leaked") reference text(s) git does not track in the release (not public), e.g.:"
  sed -n '1,3p' <<<"$leaked"; exit 1
fi
[ ! -e "$OUT/inspector/data/materialized" ] || { echo "::error::materialized items in the release"; exit 1; }
# The MCP server's precomputed goals' tests: without them each view takes ~50 s.
[ -s "$OUT/inspector/cache/evh-p.jsonl" ] || { echo "::error::the p cache (inspector/cache/evh-p.jsonl) is missing or empty"; exit 1; }
echo "rendered release $SHA into $OUT (nginx $PORT, inspector $IPORT, mcp $MPORT)"
