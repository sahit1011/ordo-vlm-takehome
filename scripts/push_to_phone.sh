#!/usr/bin/env bash
# Push llama.cpp binaries + selected models to the phone (/data/local/tmp/ordo).
# Usage: ./scripts/push_to_phone.sh [model.gguf ...]   (no args = binaries only)
set -euo pipefail

BUILD="$HOME/Desktop/llama.cpp/build-android/bin"
DIR=/data/local/tmp/ordo

adb shell mkdir -p "$DIR/models"
for b in llama-server llama-mtmd-cli llama-bench; do
  [ -f "$BUILD/$b" ] && adb push "$BUILD/$b" "$DIR/" && adb shell chmod +x "$DIR/$b"
done
# shared libs if the build produced them
for lib in "$BUILD"/*.so; do
  [ -e "$lib" ] && adb push "$lib" "$DIR/"
done

for m in "$@"; do
  echo "pushing $m (this can take a while over Wi-Fi) ..."
  adb push "models/$m" "$DIR/models/"
done
adb shell ls -lh "$DIR" "$DIR/models"
