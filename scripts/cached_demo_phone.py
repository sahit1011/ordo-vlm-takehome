"""Mint ledger-backed cached (warm-on-drop) rows on the phone champion.

Reproduces the day-3 perceived-TTFT measurement through the dashboard so the
rows land in history with cached=true: warm the image (phase A: encode +
image-prefill during 'user speech'), then stream queries with cache_prompt on
— perceived TTFT = text prefill + first token only.
"""

import json
import pathlib
import time

import requests

DASH = "http://127.0.0.1:8090"
ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGE = ROOT / "eval/photos/p01_supplements.jpg"
QUESTIONS = [
    "How many tablets are in the Vitamin D3 K2 bottle? Answer briefly with just the fact.",
    "What flavour is the creatine? Answer briefly with just the fact.",
    "Name the supplement in the green bottle. Answer briefly with just the fact.",
]

r = requests.post(f"{DASH}/api/server", data={"engine": "phone-gpu", "config": "qwen3-2b-q4",
                                              "threads": 6, "imt": 576}, timeout=420).json()
assert r.get("ok"), r
print(f"server up in {r['load_s']}s enc={r.get('enc_backend')} dec={r.get('dec_backend')}", flush=True)

with open(IMAGE, "rb") as f:
    w = requests.post(f"{DASH}/api/warm", timeout=1800,
                      files={"image": (IMAGE.name, f, "image/jpeg")}).json()
print(f"warm (encode + image prefill, hidden from user clock): {w}", flush=True)

for q in QUESTIONS:
    with open(IMAGE, "rb") as f:
        resp = requests.post(f"{DASH}/api/infer_stream", stream=True, timeout=1800,
                             files={"image": (IMAGE.name, f, "image/jpeg")},
                             data={"question": q, "max_tokens": 48, "cached": "1"})
        rec = None
        for line in resp.iter_lines():
            if line.startswith(b"data: "):
                obj = json.loads(line[6:])
                if obj.get("type") == "done":
                    rec = obj["record"]
    print(f"cached ttft={rec['ttft_s']:.2f}s total={rec['total_s']:.2f}s "
          f":: {rec['answer'][:40]!r}", flush=True)
    time.sleep(2)
print("CACHED DEMO DONE", flush=True)
