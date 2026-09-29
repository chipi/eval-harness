#!/bin/bash
# Provision a Claude Code on the web session: the harness venv plus each example's
# base uv environment (no `--extra local`, so no torch). Idempotent.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR/harness"
make install

for d in "$CLAUDE_PROJECT_DIR"/examples/*/; do
  [ -f "$d/pyproject.toml" ] || continue
  (cd "$d" && uv sync --frozen -q)
done
