#!/usr/bin/env bash
# Wireless adb setup for the OnePlus 15R (both devices on the same Wi-Fi).
#
# One-time pairing (whenever the phone forgets this laptop):
#   On the phone: Settings > System > Developer options > Wireless debugging (ON)
#   > "Pair device with pairing code" — it shows an IP:PORT and a 6-digit code.
#   Then:   ./scripts/connect_phone.sh pair <ip:port> <code>
#
# Every session after that:
#   The Wireless-debugging main screen shows a (different) IP:PORT.
#   Then:   ./scripts/connect_phone.sh connect <ip:port>
set -euo pipefail

case "${1:-}" in
  pair)
    adb pair "$2" "$3"
    echo "Paired. Now run: $0 connect <ip:port from the wireless-debugging main screen>"
    ;;
  connect)
    adb connect "$2"
    adb devices -l
    adb shell getprop ro.product.model
    ;;
  status)
    adb devices -l
    ;;
  *)
    grep '^#' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
