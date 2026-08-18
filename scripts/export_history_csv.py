"""Export the full dashboard ledger to results/history_all_runs.csv.

Every inference of the whole experiment, chronological, one row each — the
proof trail behind every number in the report. Regenerated automatically by
scripts/render_submission.py so the CSV can never drift from the ledger.
"""

import csv
import json
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER = ROOT / "results/dashboard_runs.jsonl"
OUT = ROOT / "results/history_all_runs.csv"

COLS = ["time", "device", "runtime", "engine", "config", "imt", "mode", "prompt_n",
        "enc_backend", "dec_backend", "ttft_s", "total_s", "encode_ms", "prefill_ms",
        "prefill_tps", "decode_tps", "decode_n", "peak_ram_mb", "peak_soc_temp_c",
        "threads", "image", "question", "answer", "answer_gt", "accept_also", "correct"]


def export() -> int:
    rows = [json.loads(l) for l in open(LEDGER)]
    rows.sort(key=lambda r: r.get("ts") or 0)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            r["time"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r.get("ts") or 0))
            r["mode"] = "cached" if r.get("cached") else "serial"
            w.writerow(r)
    return len(rows)


if __name__ == "__main__":
    print(f"{export()} rows -> {OUT}")
