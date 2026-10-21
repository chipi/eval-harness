#!/usr/bin/env bash
# Run MBPP+ vllm arms on the DGX inside an operator-given window.
#
#   STOP_STARTING_AT=21:00 [CONCURRENCY=N] examples/code-mbpp-plus/run_dgx_window.sh arm[:util[:seqs]] ...
#
# Each arm sends `seqs` calls at once by default (experiment_run --concurrency), matching the
# server's --max-num-seqs, so vLLM batches them.
#
# Like run_dgx_arms.sh, plus: a per-arm GPU memory cap and concurrency (arm:util:seqs), and a
# deadline (HH:MM UTC, today) after which no new model is started; the one in progress
# finishes. Hand-back to prod is the operator's switch, done after this exits.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
HARNESS="$HERE/../../harness"
DGX=markodragoljevic@dgx-llm-1
SSH=(ssh -o BatchMode=yes "$DGX")
DEADLINE=$(date -u -d "today ${STOP_STARTING_AT:?set STOP_STARTING_AT=HH:MM (UTC)}" +%s)

mode=$("${SSH[@]}" '~/bin/gpu-mode-swap.sh --mode-only' 2>/dev/null)
if [ "$mode" != "free" ] && [ "$mode" != "idle" ]; then
  echo "DGX is in mode '$mode', not free: refusing (the operator switches it, not this script)"
  exit 2
fi
set -a; . "$HARNESS/.env"; set +a
[ -n "${EVAL_VLLM_API_KEY:-}" ] || { echo "EVAL_VLLM_API_KEY not set in harness/.env"; exit 2; }

remote() {  # remote <util> <seqs> <args...>: dgx_vllm.sh there, settings as stdin's first lines
  local util=$1 seqs=$2; shift 2
  { printf 'EVAL_VLLM_API_KEY=%q\nGPU_UTIL=%q\nMAX_SEQS=%q\n' "$EVAL_VLLM_API_KEY" "$util" "$seqs"
    cat "$HERE/dgx_vllm.sh"; } | "${SSH[@]}" "bash -s $*"
}
stop() { remote 0.60 8 stop; }
trap stop EXIT

for spec in "$@"; do
  IFS=: read -r a util seqs <<<"$spec"
  util=${util:-0.60}; seqs=${seqs:-8}
  if [ "$(date -u +%s)" -ge "$DEADLINE" ]; then
    echo "[$a] SKIPPED: past STOP_STARTING_AT=$STOP_STARTING_AT UTC"; continue
  fi
  cfg="$HERE/configs/arm_vllm_${a}_n378.yaml"
  read -r model rev dtype < <(python3 -c "
import sys, yaml
p = yaml.safe_load(open(sys.argv[1]))['params']
d = {'fp32': 'float32', 'bf16': 'bfloat16', 'fp16': 'float16'}[p.get('precision', 'bf16')]
print(p['model'], p['revision'], d)" "$cfg")
  echo "[$a] START $(date -u +%H:%M:%S) $model $dtype util=$util seqs=$seqs"
  if ! remote "$util" "$seqs" start "$model" "$rev" "$dtype"; then
    echo "[$a] SERVE FAILED"; stop; continue
  fi
  (cd "$HARNESS" && "$HERE/.venv/bin/python" scripts/experiment_run.py --config "$cfg" --concurrency "${CONCURRENCY:-$seqs}")
  echo "[$a] END rc=$? $(date -u +%H:%M:%S)"
  stop
done
echo "WINDOW DONE $(date -u +%H:%M:%S)"
