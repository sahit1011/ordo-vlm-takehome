"""Phone-side measurements over adb: peak RAM, thermals, battery.

All functions shell out to `adb shell`; they assume a single device is
connected (or ANDROID_SERIAL is set). On-device paths target the llama-server
process we launch in /data/local/tmp/ordo.
"""

import subprocess
import threading
import time


def adb(*args: str) -> str:
    out = subprocess.run(["adb", "shell", *args], capture_output=True, text=True, timeout=30)
    return out.stdout.strip()


def server_pid() -> int | None:
    pid = adb("pidof", "llama-server")
    return int(pid.split()[0]) if pid else None


def vm_hwm_kb(pid: int) -> int | None:
    """Peak resident set (high-water mark) of the process, in kB."""
    for line in adb("cat", f"/proc/{pid}/status").splitlines():
        if line.startswith("VmHWM"):
            return int(line.split()[1])
    return None


def battery() -> dict:
    """Battery level (%) and temperature (0.1 °C units) from dumpsys."""
    info = {}
    for line in adb("dumpsys", "battery").splitlines():
        line = line.strip()
        if line.startswith("level:"):
            info["level_pct"] = int(line.split(":")[1])
        elif line.startswith("temperature:"):
            info["temp_c"] = int(line.split(":")[1]) / 10.0
    return info


def thermal_zones() -> dict:
    """Read every thermal zone as {type: °C}. Zone set varies by SoC."""
    raw = adb(
        "for z in /sys/class/thermal/thermal_zone*/; do "
        'echo "$(cat $z/type 2>/dev/null):$(cat $z/temp 2>/dev/null)"; done'
    )
    zones = {}
    for line in raw.splitlines():
        name, _, val = line.partition(":")
        if name and val.lstrip("-").isdigit():
            t = int(val)
            zones[name] = t / 1000.0 if abs(t) > 1000 else float(t)
    return zones


def cpu_temp_best_guess(zones: dict) -> float | None:
    """Hottest CPU-looking zone, excluding trip-point setpoints (constant
    thresholds like cpu-hw-trip-* = 95.0 that read as fake sensors)."""
    cpu = [v for k, v in zones.items()
           if any(s in k.lower() for s in ("cpu", "soc", "tsens"))
           and "trip" not in k.lower()]
    return max(cpu) if cpu else (max(zones.values()) if zones else None)


class Sampler:
    """Polls RAM + thermals in a thread while a query runs; keeps the peaks."""

    def __init__(self, interval_s: float = 1.0):
        self.interval = interval_s
        self.peak_vm_hwm_kb = None
        self.peak_cpu_temp = None
        self._stop = threading.Event()
        self._thread = None

    def _loop(self):
        while not self._stop.is_set():
            pid = server_pid()
            if pid:
                hwm = vm_hwm_kb(pid)
                if hwm and (self.peak_vm_hwm_kb is None or hwm > self.peak_vm_hwm_kb):
                    self.peak_vm_hwm_kb = hwm
            t = cpu_temp_best_guess(thermal_zones())
            if t and (self.peak_cpu_temp is None or t > self.peak_cpu_temp):
                self.peak_cpu_temp = t
            self._stop.wait(self.interval)

    def __enter__(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=5)
