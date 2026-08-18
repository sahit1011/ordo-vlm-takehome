#!/usr/bin/env bash
# Download the Android NDK into ~/.local (no sudo, no Android Studio).
set -euo pipefail

VER=r27c
DEST="$HOME/.local/android-ndk"
[ -d "$DEST" ] && { echo "NDK already at $DEST"; exit 0; }

cd "$(mktemp -d)"
echo "Downloading NDK $VER ..."
curl -L -o ndk.dmg "https://dl.google.com/android/repository/android-ndk-${VER}-darwin.dmg"
MOUNT=$(hdiutil attach ndk.dmg | awk '/\/Volumes/{print $NF; exit}')
APP=$(find "$MOUNT" -maxdepth 2 -name "AndroidNDK*.app" | head -1)
cp -R "$APP/Contents/NDK" "$DEST"
hdiutil detach "$MOUNT" -quiet
echo "NDK installed at $DEST"
"$DEST/toolchains/llvm/prebuilt/darwin-x86_64/bin/clang" --version | head -1
