#!/usr/bin/env bash
# Build llama.cpp with the OpenCL (Adreno) backend for Android.
# Follows llama.cpp docs/backend/OPENCL.md: OpenCL headers + ICD loader get
# installed into the NDK sysroot, then llama.cpp builds with GGML_OPENCL=ON.
set -euo pipefail

NDK="${NDK:-$HOME/.local/android-ndk}"
SRC="${SRC:-$HOME/Desktop/llama.cpp}"
DEPS="$HOME/.local/ocl-android"
SYSROOT="$NDK/toolchains/llvm/prebuilt/darwin-x86_64/sysroot"
BUILD="$SRC/build-android-ocl"

mkdir -p "$DEPS" && cd "$DEPS"
[ -d OpenCL-Headers ] || git clone --depth 1 https://github.com/KhronosGroup/OpenCL-Headers
/bin/cp -r OpenCL-Headers/CL "$SYSROOT/usr/include/"

[ -d OpenCL-ICD-Loader ] || git clone --depth 1 https://github.com/KhronosGroup/OpenCL-ICD-Loader
cmake -S OpenCL-ICD-Loader -B OpenCL-ICD-Loader/build \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-28 \
  -DOPENCL_ICD_LOADER_HEADERS_DIR="$DEPS/OpenCL-Headers" \
  -DCMAKE_BUILD_TYPE=Release
cmake --build OpenCL-ICD-Loader/build -j8
/bin/cp OpenCL-ICD-Loader/build/libOpenCL.so "$SYSROOT/usr/lib/aarch64-linux-android/"

cmake -S "$SRC" -B "$BUILD" \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a \
  -DANDROID_PLATFORM=android-28 \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="-march=armv8.7-a+i8mm+dotprod" \
  -DCMAKE_CXX_FLAGS="-march=armv8.7-a+i8mm+dotprod" \
  -DGGML_OPENCL=ON \
  -DGGML_OPENMP=OFF \
  -DLLAMA_CURL=OFF

cmake --build "$BUILD" -j8 --target llama-server llama-mtmd-cli llama-bench
echo "OpenCL binaries in $BUILD/bin"
