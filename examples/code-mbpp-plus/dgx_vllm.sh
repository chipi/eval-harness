#!/usr/bin/env bash
# Serve ONE model with vLLM on the DGX for the MBPP+ vllm arms, or stop it.
#
#   run_dgx_arms.sh pipes this file to `ssh dgx-llm-1 bash -s start <model> <rev> <dtype>`
#   (or `... bash -s stop`), with one line in front of it that sets the API key.
#
# It never
# touches the gpu-mode stacks: the GPU must already be in `free` mode (the driver checks),
# and `stop` removes only the container named below, so `gpu-mode prod` can take the GPU back.
#
# The API key arrives as the first line of this script's stdin (EVAL_VLLM_API_KEY=...),
# never on an ssh or script command line. The port is bound to the DGX's tailnet address only.
set -euo pipefail
NAME=eval-mbpp-vllm
PORT=9100
IMAGE=nvcr.io/nvidia/vllm:26.05-py3
TAILNET_IP=$(tailscale ip -4 2>/dev/null | head -1)

case "${1:-}" in
  start)
    model=$2; rev=$3; dtype=$4
    [ -n "$TAILNET_IP" ] || { echo "no tailnet address"; exit 1; }
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    docker run -d --name "$NAME" --runtime nvidia --ipc host \
      -e NVIDIA_VISIBLE_DEVICES=all -e HF_HOME=/root/.cache/huggingface \
      -e VLLM_DISABLE_TORCH_COMPILE=1 -e "VLLM_API_KEY=$EVAL_VLLM_API_KEY" \
      -p "$TAILNET_IP:$PORT:$PORT" \
      -v /opt/llm-models/huggingface:/root/.cache/huggingface \
      "$IMAGE" vllm serve "$model" --revision "$rev" --dtype "$dtype" \
        --host 0.0.0.0 --port "$PORT" --max-model-len 4096 \
        --gpu-memory-utilization "${GPU_UTIL:-0.60}" --max-num-seqs "${MAX_SEQS:-8}" --seed 0 >/dev/null
    # Wait for /health; first start of a model includes its download.
    for _ in $(seq 1 360); do
      if curl -sf "http://$TAILNET_IP:$PORT/health" >/dev/null; then echo "ready $model"; exit 0; fi
      if ! docker ps -q -f "name=^$NAME$" | grep -q .; then
        echo "container exited:"; docker logs --tail 40 "$NAME"; exit 1
      fi
      sleep 10
    done
    echo "not ready after 60 min"; docker logs --tail 40 "$NAME"; exit 1
    ;;
  stop)
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    echo "stopped"
    ;;
  *)
    echo "usage: start <model> <revision> <dtype> | stop"; exit 2
    ;;
esac
