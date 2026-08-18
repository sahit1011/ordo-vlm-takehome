#!/usr/bin/env bash
# Download the Android NDK into ~/.local (no sudo, no Android Studio).
set -euo pipefail

VER=r27c
DEST="$HOME/.local/android-ndk"
[ -d "$DEST" ] && { echo "NDK already at $DEST"; exit 0; }

cd "$(mktemp -d)"
echo "Downloading NDK $VER ..."
curl -sL -o ndk.dmg "https://dl.google.com/android/repository/android-ndk-${VER}-darwin.dmg"
# mount point can contain spaces ("/Volumes/Android NDK r27c") — take the
# whole field after the mount device, not awk's last column
MOUNT=$(hdiutil attach ndk.dmg | sed -n 's/.*\(\/Volumes\/.*\)$/\1/p' | head -1)
APP=$(find "$MOUNT" -maxdepth 2 -name "AndroidNDK*.app" | head -1)
/bin/cp -R "$APP/Contents/NDK" "$DEST"   # /bin/cp: user shell aliases cp
hdiutil detach "$MOUNT" -quiet
echo "NDK installed at $DEST"
"$DEST/toolchains/llvm/prebuilt/darwin-x86_64/bin/clang" --version | head -1
