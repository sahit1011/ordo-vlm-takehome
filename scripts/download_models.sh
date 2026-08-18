#!/usr/bin/env bash
# Download the full GGUF ladder into models/ (~15 GB total).
set -euo pipefail
cd "$(dirname "$0")/.."

hf download ggml-org/Qwen2.5-VL-3B-Instruct-GGUF \
  Qwen2.5-VL-3B-Instruct-f16.gguf \
  Qwen2.5-VL-3B-Instruct-Q8_0.gguf \
  Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf \
  mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf \
  mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf \
  --local-dir models/

# Q2 comes from unsloth (ggml-org doesn't publish one)
hf download unsloth/Qwen2.5-VL-3B-Instruct-GGUF \
  Qwen2.5-VL-3B-Instruct-Q2_K.gguf \
  --local-dir models/

ls -lh models/*.gguf
