#!/usr/bin/env bash
# Run MBPP+ vllm arms against the DGX, one model at a time, from this machine.
#
#   examples/code-mbpp-plus/run_dgx_arms.sh qwencoder_15b [more arms...]
#
# Preconditions, checked here: the DGX is in `free` mode (the operator switched it), and
# EVAL_VLLM_API_KEY is set in harness/.env. Model code is executed and scored HERE, in the
# sandbox; the DGX only generates. Each model's container is stopped after its arm, and on
# any exit, so the GPU can go back to prod.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
HARNESS="$HERE/../../harness"
DGX=markodragoljevic@dgx-llm-1
SSH=(ssh -o BatchMode=yes "$DGX")

mode=$("${SSH[@]}" '~/bin/gpu-mode-swap.sh --mode-only' 2>/dev/null)
if [ "$mode" != "free" ] && [ "$mode" != "idle" ]; then
  echo "DGX is in mode '$mode', not free: refusing (the operator switches it, not this script)"
  exit 2
fi
set -a; . "$HARNESS/.env"; set +a
[ -n "${EVAL_VLLM_API_KEY:-}" ] || { echo "EVAL_VLLM_API_KEY not set in harness/.env"; exit 2; }

remote() {  # remote <args...>: run dgx_vllm.sh there, the key as stdin's first line
  { printf 'EVAL_VLLM_API_KEY=%q\n' "$EVAL_VLLM_API_KEY"; cat "$HERE/dgx_vllm.sh"; } \
    | "${SSH[@]}" "bash -s $*"
}
stop() { remote stop; }
trap stop EXIT

for a in "$@"; do
  cfg="$HERE/configs/arm_vllm_${a}_n378.yaml"
  read -r model rev dtype < <(python3 -c "
import sys, yaml
p = yaml.safe_load(open(sys.argv[1]))['params']
d = {'fp32': 'float32', 'bf16': 'bfloat16', 'fp16': 'float16'}[p.get('precision', 'bf16')]
print(p['model'], p['revision'], d)" "$cfg")
  echo "[$a] START $(date -u +%H:%M:%S) $model $dtype"
  if ! remote start "$model" "$rev" "$dtype"; then
    echo "[$a] SERVE FAILED"; continue
  fi
  (cd "$HARNESS" && "$HERE/.venv/bin/python" scripts/experiment_run.py --config "$cfg")
  echo "[$a] END rc=$? $(date -u +%H:%M:%S)"
  stop
done
