"""MXFP4-on-Adreno cell: the supps image at @576 and @320, via the dashboard.

Runs the enumeration query (recall /9) plus the two p01 fact questions (GT
scored) at each budget. Prints the enc/dec backend the dashboard detected at
launch — the run doubles as the 'does OpenCL have MXFP4 kernels?' probe:
GPU-class decode t/s = yes; single-digit = silent CPU matmul fallback.

Caller pushes/removes the model file; this script only drives the API.
"""

import pathlib
import sys
import time

import requests

DASH = "http://127.0.0.1:8090"
ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGE = ROOT / "eval/photos/p01_supplements.jpg"
BRIEF = " Answer briefly with just the fact."
ENUM_Q = "Name all the visible supplements present in the image."

GT = {"moringa": ["moringa", "sorghum"], "creatine": ["creatine"], "d3+k2": ["d3"],
      "magnesium glycinate": ["magnesium"], "multivitamin": ["multi"],
      "omega-3": ["omega"], "hydrasalt": ["hydra", "electrolyte"],
      "zinc": ["zinc"], "amla": ["amla"]}
FACTS = [("What flavour is the creatine?", "watermelon", "watermelon wave"),
         ("How many tablets are in the Vitamin D3 K2 bottle?", "120", "120 tablets")]


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


def infer(question, max_tokens, gt=None, alt=""):
    with open(IMAGE, "rb") as f:
        data = {"question": question, "max_tokens": max_tokens}
        if gt:
            data.update(answer_gt=gt, accept_also=alt)
        return requests.post(f"{DASH}/api/infer", timeout=1800, data=data,
                             files={"image": (IMAGE.name, f, "image/jpeg")}).json()


for imt in (576, 320):
    cool()
    r = requests.post(f"{DASH}/api/server",
                      data={"engine": "phone-gpu", "config": "qwen3-2b-mxfp4",
                            "threads": 6, "imt": imt}, timeout=420).json()
    if not r.get("ok"):
        print(f"MXFP4 @{imt}: server failed -> {r}", flush=True)
        sys.exit(1)
    print(f"MXFP4 @{imt}: up in {r['load_s']}s  enc={r.get('enc_backend')} "
          f"dec={r.get('dec_backend')}", flush=True)

    rec = infer(ENUM_Q, 160)
    a = (rec.get("answer") or "").lower()
    hits = [k for k, alts in GT.items() if any(s in a for s in alts)]
    print(f"  enum   recall {len(hits)}/9  ttft={rec.get('ttft_s'):.2f}s "
          f"enc={rec.get('encode_ms')}ms dec={rec.get('decode_tps')}t/s -> {hits}", flush=True)

    for q, gt, alt in FACTS:
        rec = infer(q + BRIEF, 96, gt, alt)
        print(f"  fact   {'Y' if rec.get('correct') else 'n'}  ttft={rec.get('ttft_s'):.2f}s "
              f":: {rec.get('answer', '')[:50]!r} (gt: {gt})", flush=True)
