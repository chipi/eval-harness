#!/usr/bin/env bash
# Read-only hardware facts for a Linux host.
echo "hostname: $(hostname)"
echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//')"
echo "threads: $(nproc)"
echo "memory_kb: $(grep MemTotal /proc/meminfo | awk '{print $2}')"
for f in /sys/class/drm/card*/device/product_name /sys/devices/virtual/dmi/id/product_name /sys/devices/virtual/dmi/id/sys_vendor; do
  [ -r "$f" ] && echo "$(basename "$(dirname "$f")")/$(basename "$f"): $(cat "$f")"
done
command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/gpu: /'
# shellcheck source=/dev/null  # the host's own file, not part of this repo
echo "os: $(. /etc/os-release && echo "$PRETTY_NAME") $(uname -r)"
