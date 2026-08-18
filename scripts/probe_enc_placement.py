"""Resolve the unknown encoder placements (the '?' rows): LFM2-450M,
SmolVLM-500M, SmolVLM2-2.2B on phone-gpu.

For each config: push model+mmproj, launch via the dashboard (whose launch-log
scan is the detector), print the verdict, run one supps query so a labeled row
lands in history, janitor the files. Then rewrite the ledger, filling
enc_backend/dec_backend on the historical rows of that config with the
log-confirmed verdict.

RUN ONLY WHEN THE PHONE IS FREE (after CHAIN2 COMPLETE) — the launcher waits.
"""

import json
import os
import pathlib
import subprocess
import time

import requests

DASH = "http://127.0.0.1:8090"
ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "results/dashboard_runs.jsonl"
IMAGE = ROOT / "eval/photos/p01_supplements.jpg"
PHONE_MODELS = "/data/local/tmp/ordo/models"

PROBES = {
    "lfm2-450-q8": ["LFM2-VL-450M-Q8_0.gguf", "mmproj-LFM2-VL-450M-Q8_0.gguf"],
    "smol500-q8": ["SmolVLM-500M-Instruct-Q8_0.gguf", "mmproj-SmolVLM-500M-Instruct-Q8_0.gguf"],
    "smol22-q4": ["SmolVLM2-2.2B-Instruct-Q4_K_M.gguf", "mmproj-SmolVLM2-2.2B-Instruct-Q8_0.gguf"],
}


def cool(limit=55.0):
    while True:
        try:
            t = requests.get(f"{DASH}/api/phone", timeout=15).json().get("soc_temp_c") or 99
        except requests.RequestException:
            t = 99
        print(f"  [cool] SoC {t:.1f}", flush=True)
        if t <= limit:
            return
        time.sleep(30)


verdicts = {}
for cfg, files in PROBES.items():
    print(f"[{cfg}] pushing {files}", flush=True)
    subprocess.run(["adb", "push", *[str(ROOT / "models" / f) for f in files],
                    PHONE_MODELS], capture_output=True)
    cool()
    r = requests.post(f"{DASH}/api/server", data={"engine": "phone-gpu", "config": cfg,
                                                  "threads": 6, "imt": 576}, timeout=420).json()
    if not r.get("ok"):
        print(f"[{cfg}] server failed: {r}", flush=True)
        continue
    verdicts[cfg] = (r.get("enc_backend"), r.get("dec_backend"))
    print(f"[{cfg}] VERDICT enc={r.get('enc_backend')} dec={r.get('dec_backend')}", flush=True)
    with open(IMAGE, "rb") as f:  # one labeled row into history as evidence
        rec = requests.post(f"{DASH}/api/infer", timeout=1800,
                            files={"image": (IMAGE.name, f, "image/jpeg")},
                            data={"question": "Name all the visible supplements present in the image.",
                                  "max_tokens": 160}).json()
    print(f"[{cfg}] enc={rec.get('encode_ms')}ms ttft={rec.get('ttft_s'):.2f}s "
          f":: {rec.get('answer', '')[:60]!r}", flush=True)
    subprocess.run(["adb", "shell", f"cd {PHONE_MODELS} && rm -f {' '.join(files)}"],
                   capture_output=True)

subprocess.run(["adb", "shell", "pkill", "llama-server"], capture_output=True)

if verdicts:  # backfill historical rows — safe: nothing else appends now
    out, n = [], 0
    for line in open(LEDGER):
        r = json.loads(line)
        if (r.get("engine") == "phone-gpu" and not r.get("enc_backend")
                and r.get("config") in verdicts):
            r["enc_backend"], r["dec_backend"] = verdicts[r["config"]]
            n += 1
        out.append(json.dumps(r))
    tmp = LEDGER.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(out) + "\n")
    os.replace(tmp, LEDGER)
    print(f"ledger: filled {n} historical rows -> {verdicts}", flush=True)
print("PROBE COMPLETE", flush=True)
