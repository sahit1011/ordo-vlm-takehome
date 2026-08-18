#!/usr/bin/env bash
# Cross-compile llama.cpp for the phone (arm64, CPU backend with i8mm/dotprod).
# Requires the Android NDK (scripts/setup_ndk.sh downloads it without sudo).
set -euo pipefail

NDK="${NDK:-$HOME/.local/android-ndk}"
SRC="${SRC:-$HOME/Desktop/llama.cpp}"
BUILD="$SRC/build-android"

[ -d "$NDK" ] || { echo "NDK not found at $NDK — run scripts/setup_ndk.sh first"; exit 1; }

cmake -S "$SRC" -B "$BUILD" \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a \
  -DANDROID_PLATFORM=android-28 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="-march=armv8.7-a+i8mm+dotprod" \
  -DCMAKE_CXX_FLAGS="-march=armv8.7-a+i8mm+dotprod" \
  -DGGML_OPENMP=OFF \
  -DLLAMA_CURL=OFF

cmake --build "$BUILD" -j8 --target llama-server llama-mtmd-cli llama-bench
echo "Binaries in $BUILD/bin"
