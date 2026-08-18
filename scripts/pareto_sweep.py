"""Phone Pareto sweep: configs × images through the dashboard API.

Drives http://localhost:8090 so every run lands in dashboard history and
results/dashboard_runs.jsonl. Cool-gates on real SoC temp between configs.

Usage: python3 scripts/pareto_sweep.py
"""

import pathlib
import sys
import time

import requests

DASH = "http://127.0.0.1:8090"
ROOT = pathlib.Path(__file__).resolve().parent.parent
COOL_SOC_C = 50.0

# (config, imt, [(image, question)])
QUERIES_FULL = [
    ("eval/photos/smoke.png", "How much does the paneer tikka cost?"),
    ("eval/photos/p01_supplements.jpg", "How many tablets are in the Vitamin D3 K2 bottle?"),
    ("eval/photos/p01_supplements.jpg", "What flavour is the creatine?"),
]
QUERIES_1024 = [
    ("eval/photos/smoke.png", "How much does the paneer tikka cost?"),
    ("eval/photos/p01_1024.jpg", "How many tablets are in the Vitamin D3 K2 bottle?"),
    ("eval/photos/p01_1024.jpg", "What flavour is the creatine?"),
]
SWEEP = [
    ("q4_0",    576, QUERIES_FULL),
    ("q4_0",    256, QUERIES_FULL),
    ("lfm2-q4", 0,   QUERIES_FULL),
    ("lfm2-q4", 0,   QUERIES_1024),
]


def soc_temp():
    try:
        return requests.get(f"{DASH}/api/phone", timeout=15).json().get("soc_temp_c") or 99
    except requests.RequestException:
        return 99


def cool_gate():
    while True:
        t = soc_temp()
        print(f"  [cool-gate] SoC {t:.1f} °C (need <= {COOL_SOC_C})", flush=True)
        if t <= COOL_SOC_C:
            return
        time.sleep(30)


for config, imt, queries in SWEEP:
    cool_gate()
    print(f"== {config} imt={imt}", flush=True)
    r = requests.post(f"{DASH}/api/server", data={
        "engine": "phone-gpu", "config": config, "threads": 6, "imt": imt},
        timeout=420).json()
    if not r.get("ok"):
        print(f"  SERVER FAILED: {r} — recording and moving on", flush=True)
        continue
    print(f"  loaded in {r['load_s']}s", flush=True)
    for img, q in queries:
        p = ROOT / img
        with open(p, "rb") as f:
            rec = requests.post(f"{DASH}/api/infer", timeout=1200,
                                files={"image": (p.name, f, "image/jpeg")},
                                data={"question": q, "max_tokens": 48}).json()
        if "error" in rec:
            print(f"  {img.split('/')[-1]}: ERROR {rec['error']}", flush=True)
            continue
        print(f"  {img.split('/')[-1]:22s} ttft={rec['ttft_s']:.2f}s enc={rec['encode_ms']}ms "
              f"pn={rec['prompt_n']} pf={rec['prefill_tps']} dec={rec['decode_tps'] and round(rec['decode_tps'],1)} "
              f"peak={rec['peak_soc_temp_c']}°C :: {rec['answer'][:55]!r}", flush=True)

print("sweep complete", flush=True)
