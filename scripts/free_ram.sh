#!/usr/bin/env bash
# Free phone RAM before a heavy run (F16 load, stress tests).
# Safe: leaves WhatsApp/Gmail/Messages alone so notifications keep working.
set -euo pipefail

adb shell am kill-all
for pkg in com.instagram.android com.linkedin.android com.snapchat.android \
           com.google.android.youtube com.heytap.browser com.android.launcher; do
  adb shell am force-stop "$pkg" || true
done
sleep 3
adb shell "grep -E 'MemTotal|MemAvailable|SwapFree' /proc/meminfo"
