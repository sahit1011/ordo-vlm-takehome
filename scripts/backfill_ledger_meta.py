"""Backfill answer_gt/accept_also and enc/dec backend placement into the ledger.

ONLY RUN WHILE NOTHING IS APPENDING to results/dashboard_runs.jsonl (the
rewrite is read-transform-replace; a concurrent append would be lost).

- GT: joined by question text (brief suffix stripped) against every eval csv.
- Backends: launch-config truth for llama.cpp rows; the phone-gpu encoder is
  marked "cpu (op gap)" only where the fallback was log-confirmed (lfm2-q4,
  i.e. LFM2-VL-1.6B). LFM2-450M/SmolVLM phone encoders stay unknown — their
  server logs are gone (overwritten per launch); do not guess. MNN/LiteRT rows
  untouched (backend is part of their runtime story already).
"""

import csv
import json
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "results/dashboard_runs.jsonl"
BRIEF = " Answer briefly with just the fact."
GT_CSVS = ["eval/ordo_ground_truth_draft.csv", "eval/ordo_gt_1024.csv",
           "eval/ordo_gt_1344.csv", "eval/dev_ground_truth.csv", "eval/smoke_gt.csv"]

gt_map = {}
for rel in GT_CSVS:
    p = ROOT / rel
    if not p.exists():
        continue
    for row in csv.DictReader(open(p)):
        q = row["question"].strip()
        gt_map.setdefault(q, (row["answer"], row.get("accept_also") or None))

DEC = {"mac": "metal", "phone-gpu": "adreno-ocl", "phone-cpu": "cpu"}
CONFIRMED_CPU_ENC = {"lfm2-q4"}  # log-verified CLIP fallback on OpenCL
KNOWN_GPU_ENC = ("qwen3-2b", "q4", "q8", "q2", "f16", "bf16", "mxfp4")  # Qwen encoder A/B-proven

out, filled_gt, filled_bk = [], 0, 0
for line in open(LEDGER):
    r = json.loads(line)
    q = (r.get("question") or "").replace(BRIEF, "").strip()
    if not r.get("answer_gt") and q in gt_map:
        r["answer_gt"], r["accept_also"] = gt_map[q]
        filled_gt += 1
    if not r.get("enc_backend") and (r.get("runtime") or "llama.cpp") == "llama.cpp":
        eng = r.get("engine")
        if eng in DEC:
            r["dec_backend"] = DEC[eng]
            if eng != "phone-gpu":
                r["enc_backend"] = DEC[eng]
            elif r.get("config") in CONFIRMED_CPU_ENC:
                r["enc_backend"] = "cpu (op gap)"
            elif (r.get("config") or "").startswith(KNOWN_GPU_ENC):
                r["enc_backend"] = "adreno-ocl"
            filled_bk += 1
    out.append(json.dumps(r))

tmp = LEDGER.with_suffix(".jsonl.tmp")
tmp.write_text("\n".join(out) + "\n")
os.replace(tmp, LEDGER)
print(f"{len(out)} rows · GT filled on {filled_gt} · backends on {filled_bk}")
