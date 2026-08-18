"""Single choke-point for recording ANY measurement into dashboard history.

Policy (learned the hard way, three backfills deep): if a script measures an
inference — any runtime, any platform, any port — it records here. The
dashboard history (results/dashboard_runs.jsonl) is the one ledger; runs that
bypass it don't exist.

Usage:
    from record import record_run
    record_run(runtime="llama.cpp", engine="mac-metal", config="qwen3-2b-q4",
               question=..., answer=..., ttft_s=..., encode_ms=..., ...)
"""

import json
import pathlib
import time

LEDGER = pathlib.Path(__file__).resolve().parent.parent / "results/dashboard_runs.jsonl"

FIELDS = ["device", "runtime", "engine", "config", "imt", "cached", "image", "question",
          "answer", "correct", "answer_gt", "accept_also", "enc_backend", "dec_backend",
          "ttft_s", "total_s", "encode_ms", "prefill_ms",
          "prompt_n", "prefill_tps", "decode_tps", "decode_n", "decode_ms",
          "peak_ram_mb", "peak_soc_temp_c", "threads"]


def record_run(**kw):
    rec = {"ts": time.time()}
    for f in FIELDS:
        rec[f] = kw.get(f)
    extra = set(kw) - set(FIELDS)
    if extra:
        raise ValueError(f"unknown fields: {extra}")
    LEDGER.parent.mkdir(exist_ok=True)
    with open(LEDGER, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec
