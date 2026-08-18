"""Sweet-spot sweep: enumeration recall vs image-token budget vs TTFT.

One image (the 12MP supplements stack), one query ("name all visible
supplements"), swept across --image-max-tokens on Mac Metal for every model in
the final bracket. X-axis truth is measured prompt_n, not the nominal cap
(LFM2/SmolVLM caps bind per-tile, so nominal values aren't comparable across
architectures). Every run lands in the dashboard ledger via record_run.

Output: results/sweetspot-supps-mac-<ts>.jsonl, a printed table, and
report/figures/sweetspot_supps_mac.png (recall + TTFT vs measured tokens,
sweet spot starred per model).

Usage: python3 scripts/sweetspot_supps_mac.py
"""

import json
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import client            # noqa: E402
from record import record_run  # noqa: E402
from run_eval import CONFIGS   # noqa: E402  (model/mmproj registry)

BIN = pathlib.Path.home() / "Desktop/llama.cpp/build/bin/llama-server"
MODELS = ROOT / "models"
PORT = 8082  # own port: never collides with dashboard(8090)/harness(8080)
IMAGE = ROOT / "eval/photos/p01_supplements.jpg"
QUESTION = "Name all the visible supplements present in the image."
MAX_TOKENS = 160  # enumeration needs room for 9 items; brief-suffix not used

GT = {"moringa": ["moringa", "sorghum"], "creatine": ["creatine"], "d3+k2": ["d3"],
      "magnesium glycinate": ["magnesium"], "multivitamin": ["multi"],
      "omega-3": ["omega"], "hydrasalt": ["hydra", "electrolyte"],
      "zinc": ["zinc"], "amla": ["amla"]}

# fine ladder for the champion (knee-hunting); coarser for contrast models
SWEEP = [
    ("qwen3-2b-q4",  [64, 96, 128, 160, 192, 256, 320, 448, 576, 768, 1024, 0]),
    ("q4_0",         [128, 256, 320, 448, 576, 1024, 0]),   # Qwen2.5-VL-3B
    ("smol500-q8",   [64, 128, 256, 448, 576, 1024, 0]),
    ("lfm2-q4",      [64, 128, 256, 448, 576, 1024, 0]),    # LFM2-VL-1.6B
    ("lfm2-450-q8",  [64, 128, 256, 448, 576, 1024, 0]),
]

ENCODE_RE = re.compile(r"(?:image|slice).{0,40}?(?:encod|process)\w*\s+in\s+(\d+)\s*ms", re.I)
LOG = ROOT / "results/raw/server_sweetspot.log"


def recall(ans: str) -> tuple[int, list[str]]:
    a = ans.lower()
    hits = [k for k, alts in GT.items() if any(s in a for s in alts)]
    return len(hits), hits


def run_config(name: str, imts: list[int], fout):
    cfg = CONFIGS[name]
    model, mmproj = MODELS / cfg["model"], MODELS / cfg["mmproj"]
    if not model.exists() or not mmproj.exists():
        print(f"[{name}] SKIP — missing {model.name if not model.exists() else mmproj.name}")
        return []
    rows = []
    for imt in imts:
        args = [str(BIN), "-m", str(model), "--mmproj", str(mmproj),
                "--host", "127.0.0.1", "--port", str(PORT), "-c", "8192"]
        if imt:
            args += ["--image-max-tokens", str(imt)]
        LOG.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(args, stdout=open(LOG, "w"), stderr=subprocess.STDOUT)
        try:
            client.wait_ready(f"http://127.0.0.1:{PORT}")
            res = client.query(f"http://127.0.0.1:{PORT}", str(IMAGE), QUESTION,
                               max_tokens=MAX_TOKENS)
            hits_n, hits = recall(res["text"])
            enc = ENCODE_RE.findall(LOG.read_text(errors="replace"))
            enc_ms = sum(int(m) for m in enc) if enc else None
            rss_kb = subprocess.run(["ps", "-o", "rss=", "-p", str(proc.pid)],
                                    capture_output=True, text=True).stdout.strip()
            t = res["timings"]
            row = {"config": name, "imt": imt, "prompt_n": t.get("prompt_n"),
                   "encode_ms": enc_ms, "ttft_s": res["ttft_client_s"],
                   "total_s": res["total_s"], "recall": hits_n, "hits": hits,
                   "answer": res["text"], "timings": t}
            rows.append(row)
            fout.write(json.dumps(row) + "\n")
            fout.flush()
            record_run(device="mac", runtime="llama.cpp", engine="mac", config=name,
                       imt=imt or None, cached=False, image=IMAGE.name,
                       question=QUESTION, answer=res["text"][:400], correct=None,
                       ttft_s=round(res["ttft_client_s"], 3), total_s=round(res["total_s"], 3),
                       encode_ms=enc_ms, prefill_ms=t.get("prompt_ms"),
                       prompt_n=t.get("prompt_n"), prefill_tps=t.get("prompt_per_second"),
                       decode_tps=t.get("predicted_per_second"), decode_n=t.get("predicted_n"),
                       decode_ms=t.get("predicted_ms"),
                       peak_ram_mb=round(int(rss_kb) / 1024) if rss_kb else None)
            print(f"  [{name}] imt={imt or 'native':>6} prompt_n={t.get('prompt_n'):>5} "
                  f"enc={enc_ms}ms ttft={res['ttft_client_s']:.2f}s recall={hits_n}/9")
        except Exception as e:  # a failed step is a data point, not a crash
            print(f"  [{name}] imt={imt} FAILED: {e}")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
        time.sleep(1)
    return rows


def chart(all_rows: dict[str, list[dict]]):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    STYLE = {"qwen3-2b-q4": ("#2a78d6", "Qwen3-VL-2B Q4_0"),
             "q4_0": ("#1b4e8a", "Qwen2.5-VL-3B Q4_0"),
             "smol500-q8": ("#1baf7a", "SmolVLM-500M Q8"),
             "lfm2-q4": ("#eb6834", "LFM2-VL-1.6B Q4_0"),
             "lfm2-450-q8": ("#f2a25c", "LFM2-VL-450M Q8")}
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [1, 1.2]})
    for name, rows in all_rows.items():
        rows = sorted((r for r in rows if r.get("prompt_n")), key=lambda r: r["prompt_n"])
        if not rows:
            continue
        c, label = STYLE[name]
        x = [r["prompt_n"] for r in rows]
        ax1.plot(x, [r["recall"] for r in rows], "o-", color=c, label=label, ms=5)
        ax2.plot(x, [r["ttft_s"] for r in rows], "o-", color=c, label=label, ms=5)
        best = max(r["recall"] for r in rows)
        sweet = min((r for r in rows if r["recall"] >= best - 1), key=lambda r: r["ttft_s"])
        for ax, y in ((ax1, sweet["recall"]), (ax2, sweet["ttft_s"])):
            ax.plot(sweet["prompt_n"], y, "*", color=c, ms=17,
                    markeredgecolor="black", markeredgewidth=0.6, zorder=5)
        offs = {"qwen3-2b-q4": (-14, 14), "q4_0": (10, -16), "smol500-q8": (10, 4),
                "lfm2-q4": (10, -16), "lfm2-450-q8": (10, 8)}
        ax2.annotate(f"{sweet['ttft_s']:.2f}s @ {sweet['prompt_n']} tok",
                     (sweet["prompt_n"], sweet["ttft_s"]), textcoords="offset points",
                     xytext=offs.get(name, (8, 8)), fontsize=8, color=c)
    ax1.set_ylabel("enumeration recall (/9 items)")
    ax1.set_ylim(0, 9.5)
    ax1.grid(alpha=0.3)
    ax1.legend(fontsize=8, loc="lower right")
    ax2.set_ylabel("TTFT s (serial, Mac Metal)")
    ax2.set_xlabel("measured prompt tokens (image + ~18 text) — log scale")
    ax2.set_xscale("log")
    ax2.grid(alpha=0.3, which="both")
    ax1.set_title("Sweet spot — supps-stack enumeration: recall vs token budget vs TTFT\n"
                  "(★ = cheapest point within 1 recall of that model's best)")
    out = ROOT / "report/figures/sweetspot_supps_mac.png"
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    print(f"chart -> {out}")


def main():
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = ROOT / f"results/sweetspot-supps-mac-{ts}.jsonl"
    all_rows = {}
    with open(out, "w") as fout:
        for name, imts in SWEEP:
            print(f"[{name}] sweeping {imts}")
            all_rows[name] = run_config(name, imts, fout)
    print(f"\nwrote {out}")
    print(f"{'config':14s} {'imt':>6} {'tok':>5} {'enc_ms':>7} {'ttft':>6} recall")
    for name, rows in all_rows.items():
        for r in rows:
            print(f"{name:14s} {r['imt'] or 'native':>6} {r['prompt_n'] or '?':>5} "
                  f"{r['encode_ms'] or '?':>7} {r['ttft_s']:>6.2f} {r['recall']}/9")
    chart(all_rows)


def replot():
    """Regenerate the chart from the newest sweep jsonl (no re-run)."""
    import glob
    f = sorted(glob.glob(str(ROOT / "results/sweetspot-supps-mac-*.jsonl")))[-1]
    all_rows: dict[str, list[dict]] = {}
    for line in open(f):
        r = json.loads(line)
        all_rows.setdefault(r["config"], []).append(r)
    chart(all_rows)


if __name__ == "__main__":
    replot() if "replot" in sys.argv[1:] else main()
