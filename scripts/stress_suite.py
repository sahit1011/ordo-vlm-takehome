"""Part 4 stress suite — sustained load, thermal soak, memory pressure, battery.

Deliberately NO cool-gates inside phases (that's the point). Drives the
dashboard API on the champion config; all runs land in dashboard history.

Phases:
  1. sustained+soak: continuous queries for 10 minutes (>= 20 queries),
     per-query TTFT/decode/temp -> throughput-decay curve, battery before/after
  2. memory pressure: launch heavy apps, re-run 5 queries, compare
Run with the phone UNPLUGGED for honest battery numbers.

Usage: python3 scripts/stress_suite.py [config] [imt]
"""

import json
import pathlib
import subprocess
import sys
import time

import requests

DASH = "http://127.0.0.1:8090"
ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = sys.argv[1] if len(sys.argv) > 1 else "qwen3-2b-q4"
IMT = int(sys.argv[2]) if len(sys.argv) > 2 else 576
SOAK_MIN = 10
HEAVY_APPS = ["com.google.android.youtube", "com.android.chrome",
              "com.instagram.android", "com.google.android.apps.maps"]
IMG = ROOT / "eval/photos/p01_supplements.jpg"
Q = "How many tablets are in the Vitamin D3 K2 bottle? Answer briefly with just the fact."
OUT = ROOT / f"results/stress_{CONFIG}_{time.strftime('%Y%m%d-%H%M%S')}.jsonl"


def adb(*a):
    return subprocess.run(["adb", "shell", *a], capture_output=True, text=True, timeout=30).stdout.strip()


def phone():
    return requests.get(f"{DASH}/api/phone", timeout=15).json()


def query():
    with open(IMG, "rb") as f:
        return requests.post(f"{DASH}/api/infer", timeout=1200,
                             files={"image": (IMG.name, f, "image/jpeg")},
                             data={"question": Q, "max_tokens": 48,
                                   "answer_gt": "120", "accept_also": "120 tablets"}).json()


def log(rec):
    with open(OUT, "a") as f:
        f.write(json.dumps(rec) + "\n")


p0 = phone()
print(f"START: SoC {p0['soc_temp_c']}°C · battery {p0['battery_pct']}% "
      f"({'UNPLUGGED — good' if True else ''})", flush=True)
r = requests.post(f"{DASH}/api/server", data={"engine": "phone-gpu", "config": CONFIG,
                                              "threads": 6, "imt": IMT}, timeout=420).json()
assert r.get("ok"), r
print(f"server up in {r['load_s']}s", flush=True)

print(f"== PHASE 1: sustained + {SOAK_MIN}-min soak (no cooling) ==", flush=True)
t_end = time.monotonic() + SOAK_MIN * 60
n = 0
while time.monotonic() < t_end:
    n += 1
    rec = query()
    if "error" in rec:
        print(f"  q{n}: ERROR {rec['error']}", flush=True)
        break
    st = phone()
    row = {"phase": "sustained", "n": n, "ttft_s": rec["ttft_s"],
           "encode_ms": rec["encode_ms"], "decode_tps": rec["decode_tps"],
           "correct": rec["correct"], "soc_c": st["soc_temp_c"],
           "batt_pct": st["battery_pct"], "batt_c": st["battery_temp_c"],
           "clock_prime": st["clock_prime_mhz"], "ts": time.time()}
    log(row)
    print(f"  q{n:02d} ttft={rec['ttft_s']:.2f}s dec={rec['decode_tps'] and round(rec['decode_tps'],1)} "
          f"SoC={st['soc_temp_c']}°C batt={st['battery_pct']}% clk={st['clock_prime_mhz']}MHz "
          f"{'Y' if rec['correct'] else 'n'}", flush=True)
p1 = phone()
print(f"PHASE 1 done: {n} queries · battery {p0['battery_pct']}→{p1['battery_pct']}% "
      f"· SoC {p0['soc_temp_c']}→{p1['soc_temp_c']}°C", flush=True)

print("== PHASE 2: memory pressure (heavy apps alongside) ==", flush=True)
for pkg in HEAVY_APPS:
    adb("monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(4)
mem = adb("grep", "MemAvailable", "/proc/meminfo")
print(f"  apps launched · {mem}", flush=True)
for i in range(5):
    rec = query()
    if "error" in rec:
        print(f"  mq{i+1}: ERROR {rec['error']}", flush=True)
        continue
    st = phone()
    log({"phase": "mempressure", "n": i + 1, "ttft_s": rec["ttft_s"],
         "encode_ms": rec["encode_ms"], "decode_tps": rec["decode_tps"],
         "correct": rec["correct"], "soc_c": st["soc_temp_c"],
         "mem_available_mb": st["mem_available_mb"], "ts": time.time()})
    print(f"  mq{i+1} ttft={rec['ttft_s']:.2f}s dec={rec['decode_tps'] and round(rec['decode_tps'],1)} "
          f"free={st['mem_available_mb']}MB {'Y' if rec['correct'] else 'n'}", flush=True)

pf = phone()
print(f"SUITE DONE -> {OUT}", flush=True)
print(f"battery total: {p0['battery_pct']}% -> {pf['battery_pct']}%  "
      f"(drain {p0['battery_pct'] - pf['battery_pct']}%)", flush=True)
