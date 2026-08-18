#!/usr/bin/env bash
# Portable Android build: runs on ANY recent arm64 Android (2018+ SoCs),
# not just this Snapdragon. armv8.2-a+dotprod baseline (Cortex-A75+ era,
# covers Snapdragon/Dimensity/Exynos/Tensor); CPU-only so no vendor GPU
# driver is required; KleidiAI still dispatches i8mm/SME at runtime when
# the silicon has them.
set -euo pipefail

NDK="${NDK:-$HOME/.local/android-ndk}"
SRC="${SRC:-$HOME/Desktop/llama.cpp}"
BUILD="$SRC/build-android-compat"

cmake -S "$SRC" -B "$BUILD" \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a \
  -DANDROID_PLATFORM=android-26 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="-march=armv8.2-a+dotprod" \
  -DCMAKE_CXX_FLAGS="-march=armv8.2-a+dotprod" \
  -DGGML_CPU_KLEIDIAI=ON \
  -DGGML_OPENMP=OFF \
  -DLLAMA_CURL=OFF

cmake --build "$BUILD" -j8 --target llama-server llama-mtmd-cli llama-bench
echo "Portable binaries in $BUILD/bin"
