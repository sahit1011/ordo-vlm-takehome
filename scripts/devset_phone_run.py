"""Run the dev eval set on the phone (best config) via the dashboard API.

Serial mode (measurement-honest), cool-gate every few queries, scoring via
answer_gt/accept_also so history rows carry correctness.

Usage: python3 scripts/devset_phone_run.py [config] [imt]
"""

import csv
import pathlib
import sys
import time

import requests

DASH = "http://127.0.0.1:8090"
ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = sys.argv[1] if len(sys.argv) > 1 else "qwen3-2b-q4"
IMT = int(sys.argv[2]) if len(sys.argv) > 2 else 576
BRIEF = " Answer briefly with just the fact."
COOL_EVERY = 4
COOL_SOC_C = 55.0


def soc():
    try:
        return requests.get(f"{DASH}/api/phone", timeout=15).json().get("soc_temp_c") or 99
    except requests.RequestException:
        return 99


def cool():
    while True:
        t = soc()
        print(f"  [cool] SoC {t:.1f}", flush=True)
        if t <= COOL_SOC_C:
            return
        time.sleep(30)


GT = sys.argv[3] if len(sys.argv) > 3 else "eval/dev_ground_truth.csv"
ENGINE = sys.argv[4] if len(sys.argv) > 4 else "phone-gpu"
rows = list(csv.DictReader(open(ROOT / GT)))
if "dev_ground_truth" in GT:
    rows += [r for r in csv.DictReader(open(ROOT / "eval/smoke_gt.csv")) if r["id"].startswith("p01")]

cool()
r = requests.post(f"{DASH}/api/server", data={"engine": ENGINE, "config": CONFIG,
                                              "threads": 6, "imt": IMT}, timeout=420).json()
assert r.get("ok"), r
print(f"server up ({ENGINE} {CONFIG} imt={IMT}) in {r['load_s']}s "
      f"enc={r.get('enc_backend')} dec={r.get('dec_backend')}", flush=True)

good = 0
for i, it in enumerate(rows):
    if i and i % COOL_EVERY == 0:
        cool()
    p = ROOT / "eval" / it["file"]
    with open(p, "rb") as f:
        rec = requests.post(f"{DASH}/api/infer", timeout=1200,
                            files={"image": (p.name, f, "image/jpeg")},
                            data={"question": it["question"] + BRIEF, "max_tokens": 96,
                                  "answer_gt": it["answer"], "accept_also": it["accept_also"]}).json()
    if "error" in rec:
        print(f"  {it['id']}: ERROR {rec['error']}", flush=True)
        continue
    good += bool(rec["correct"])
    print(f"  {it['id']:5s} {it['difficulty']:6s} {'Y' if rec['correct'] else 'n'} "
          f"ttft={rec['ttft_s']:.2f} enc={rec['encode_ms']}ms :: {rec['answer'][:40]!r}", flush=True)

print(f"devset phone: {good}/{len(rows)} correct", flush=True)
