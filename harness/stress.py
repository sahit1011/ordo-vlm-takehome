"""Part 4 — stress runs against an already-running phone server.

Modes:
  sustained : 20 back-to-back queries, no cooldown; per-query throughput trend
  thermal   : keep querying for N minutes; log temps + throughput each query
  battery   : snapshot battery before/after a sustained run (run unplugged!)

Memory pressure is manual: open several heavy apps, then re-run `sustained`.

Usage:
  python harness/stress.py sustained --image eval/photos/m01.jpg --question "..."
  python harness/stress.py thermal --minutes 10 --image ... --question "..."
"""

import argparse
import json
import pathlib
import time

import client
import metrics

ROOT = pathlib.Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:18080"  # adb-forwarded phone server


def one(image, question, max_tokens):
    with metrics.Sampler() as s:
        r = client.query(URL, image, question, max_tokens=max_tokens)
    t = r.get("timings", {})
    return {
        "ttft_s": r["ttft_client_s"], "total_s": r["total_s"],
        "prefill_tps": t.get("prompt_per_second"),
        "decode_tps": t.get("predicted_per_second"),
        "peak_ram_kb": s.peak_vm_hwm_kb, "cpu_temp": s.peak_cpu_temp,
        "battery": metrics.battery(), "ts": time.time(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["sustained", "thermal", "battery"])
    ap.add_argument("--image", required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--queries", type=int, default=20)
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--max-tokens", type=int, default=48)
    args = ap.parse_args()

    out = ROOT / f"results/stress-{args.mode}-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    client.wait_ready(URL)
    print(f"battery at start: {metrics.battery()}")

    with open(out, "w") as f:
        i, t_end = 0, time.monotonic() + args.minutes * 60
        while True:
            i += 1
            rec = {"i": i, **one(str(ROOT / args.image), args.question, args.max_tokens)}
            f.write(json.dumps(rec) + "\n")
            f.flush()
            print(f"[{i}] ttft={rec['ttft_s']:.2f}s decode={rec['decode_tps'] or '?'} tok/s "
                  f"temp={rec['cpu_temp'] or '?'}°C batt={rec['battery'].get('level_pct')}%")
            if args.mode in ("sustained", "battery") and i >= args.queries:
                break
            if args.mode == "thermal" and time.monotonic() > t_end:
                break

    print(f"battery at end: {metrics.battery()}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
