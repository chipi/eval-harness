#!/usr/bin/env bash
# Read-only hardware facts for a macOS host.
echo "hostname: $(scutil --get ComputerName 2>/dev/null || hostname)"
echo "model: $(sysctl -n hw.model)"
echo "cpu: $(sysctl -n machdep.cpu.brand_string)"
echo "threads: $(sysctl -n hw.logicalcpu)"
echo "cores: $(sysctl -n hw.physicalcpu)"
echo "memory_bytes: $(sysctl -n hw.memsize)"
echo "arch: $(uname -m)"
echo "os: $(sw_vers -productName) $(sw_vers -productVersion)"
system_profiler SPHardwareDataType 2>/dev/null | grep -E "Model Name|Chip|Processor Name|Memory:" | sed 's/^ *//'
