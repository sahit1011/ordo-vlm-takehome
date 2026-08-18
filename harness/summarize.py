"""Aggregate results/*.jsonl into the report table.

Usage: python harness/summarize.py [results/phone-q4-*.jsonl ...]
With no args, summarizes every JSONL under results/, grouped by (target, config).
"""

import glob
import json
import pathlib
import statistics as st
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def pctl(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(p / 100 * len(vals)))] if vals else None


def summarize(paths):
    groups: dict[tuple, list[dict]] = {}
    for p in paths:
        for line in pathlib.Path(p).read_text().splitlines():
            r = json.loads(line)
            groups.setdefault((r["target"], r["config"]), []).append(r)

    hdr = ["run", "n", "acc%", "anls", "peakRAM_MB", "encode_ms", "prefill_tok/s",
           "decode_tok/s", "TTFT_p50_s", "TTFT_p90_s"]
    rows = []
    for (target, cfg), rs in sorted(groups.items()):
        t = [r["timings"] for r in rs if r.get("timings")]
        ttfts = [r["ttft_client_s"] for r in rs if r.get("ttft_client_s")]
        # true prefill: server's prompt_ms includes the vision-encode pass,
        # so subtract our separately-parsed encode_ms before computing tok/s
        prefill = [r["timings"]["prompt_n"] / (r["timings"]["prompt_ms"] - r["encode_ms"]) * 1000
                   for r in rs
                   if r.get("timings") and r.get("encode_ms")
                   and r["timings"]["prompt_ms"] > r["encode_ms"]]
        rows.append([
            f"{target}-{cfg}",
            len(rs),
            round(100 * sum(r["correct"] for r in rs) / len(rs), 1),
            round(st.mean(r["anls"] for r in rs), 3),
            round(max((r.get("peak_vm_hwm_kb") or 0) for r in rs) / 1024) or "-",
            round(st.median(r["encode_ms"] for r in rs if r.get("encode_ms"))) if any(r.get("encode_ms") for r in rs) else "-",
            round(st.median(prefill), 1) if prefill else
            (round(st.median(x["prompt_per_second"] for x in t if x.get("prompt_per_second")), 1) if t else "-"),
            round(st.median(x["predicted_per_second"] for x in t if x.get("predicted_per_second")), 1) if t else "-",
            round(pctl(ttfts, 50), 2) if ttfts else "-",
            round(pctl(ttfts, 90), 2) if ttfts else "-",
        ])

    widths = [max(len(str(x)) for x in [h] + [r[i] for r in rows]) for i, h in enumerate(hdr)]
    for line in [hdr] + rows:
        print("  ".join(str(x).ljust(w) for x, w in zip(line, widths)))

    # markdown for the README
    print("\n| " + " | ".join(hdr) + " |")
    print("|" + "---|" * len(hdr))
    for r in rows:
        print("| " + " | ".join(str(x) for x in r) + " |")


if __name__ == "__main__":
    paths = sys.argv[1:] or glob.glob(str(ROOT / "results/*.jsonl"))
    summarize(paths)
