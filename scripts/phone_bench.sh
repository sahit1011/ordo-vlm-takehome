#!/usr/bin/env bash
# Thermal-gated benchmark matrix on the phone.
# Each run waits for the battery to cool below the gate first, so no
# measurement inherits heat from the previous one.
#
# Usage: ./scripts/phone_bench.sh [gate_tenths_C]   (default 370 = 37.0°C)
set -euo pipefail

DIR=/data/local/tmp/ordo
GATE="${1:-370}"
OUT="results/phone_bench_$(date +%Y%m%d-%H%M%S).txt"
mkdir -p results

cool() {
  while :; do
    t=$(adb shell dumpsys battery | awk -F': ' '/temperature/{print $2}' | tr -d '\r')
    echo "  [cool-gate] battery ${t} (need <= ${GATE})"
    [ "$t" -le "$GATE" ] && return
    sleep 30
  done
}

bench() { # bench <builddir> <model> <extra ld path> <bench args...>
  local build=$1 model=$2 ld=$3; shift 3
  cool
  echo "=== $build $model $*" | tee -a "$OUT"
  adb shell "cd $DIR/$build && LD_LIBRARY_PATH=.$ld ./llama-bench -m ../models/$model $*" 2>&1 | tee -a "$OUT"
}

# 1) CPU thread sweep on Q4_K_M — one invocation per thread count so each is cool
for t in 4 6 8; do
  bench cpu Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf "" -t $t -p 512 -n 64 -r 2
done

# 2) CPU Q4_0 (KleidiAI/SME repack path) at the same thread counts
for t in 4 6; do
  [ -z "$(adb shell ls $DIR/models/Qwen2.5-VL-3B-Instruct-Q4_0.gguf 2>/dev/null)" ] && break
  bench cpu Qwen2.5-VL-3B-Instruct-Q4_0.gguf "" -t $t -p 512 -n 64 -r 2
done

# 3) OpenCL/Adreno GPU — vendor driver resolved via /vendor/lib64
bench ocl Qwen2.5-VL-3B-Instruct-Q4_0.gguf ":/vendor/lib64" -ngl 99 -p 512 -n 64 -r 2 || \
  echo "OpenCL bench FAILED (finding for the report)" | tee -a "$OUT"

echo "done -> $OUT"
