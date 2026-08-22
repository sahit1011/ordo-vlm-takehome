"""Sweet-spot visualization suite: per-model panels (accuracy / encoder
latency / TTFT vs measured image tokens, Mac + phone side by side) plus the
overall accuracy-vs-TTFT Pareto per device. Data = twice-verified cell medians
(accuracy: judged where available; devices proven accuracy-invariant).
Palette validated (dataviz six checks) this session."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
C = {"qwen": "#2a78d6", "lfm2": "#eb6834", "smol": "#1baf7a"}
INK, MUT = "#1a1d21", "#6a6f76"

# (label, tokens, enc_mac_s, ttft_mac_s, enc_ph_s, ttft_ph_s, acc/30, star)
QWEN = [("@96",   116, None,  None, 0.31, 0.82, 12, 0),
        ("@128",  146, 0.124, 0.29, 0.39, 0.93, 14, 0),
        ("@256",  262, None,  None, 0.82, 1.70, 17, 0),
        ("@320",  326, 0.316, 0.64, 1.13, 2.11, 21, 0),
        ("@448",  449, None,  None, 1.80, 3.11, 22, 0),
        ("@576",  580, 0.652, 1.16, 2.67, 4.61, 26, 1),
        ("@1024", 1008, None, None, 9.46, 13.2, 26, 0)]
LFM2 = [("512px",  173, 0.041, 0.09, 0.31, 0.66,  9, 0),
        ("1024px", 278, 0.076, 0.15, 0.32, 0.62, 11, 0),
        ("1152px", 796, 0.228, 0.39, None, None, 15, 0),
        ("1280px", 796, 0.228, 0.40, None, None, 17, 1),
        ("1344px", 796, None,  None, 0.92, 1.57, 16, 0),
        ("native", 2317, 0.673, 1.14, 3.08, 5.98, 21, 0)]
SMOL = [("1-tile", 160, 0.154, 0.22, 0.56, 0.96,  9, 0),
        ("@320",   227, None,  None, 1.13, 2.19, 13, 0),
        ("@448",   426, 0.458, 0.70, None, None, 12, 0),
        ("@576",   494, 0.534, 0.95, 2.51, 4.48, 15, 1),
        ("native", 691, None,  None, 4.30, 6.36,  7*2, 0)]  # 7/15 scaled to /30

MODELS = [("Qwen3-VL-2B Q4_0 — no tiling: one encoder pass, smooth token dial", QWEN, "qwen"),
          ("LFM2-VL-450M Q8 — tile quanta: cost jumps at the 1024→1152 px flip", LFM2, "lfm2"),
          ("SmolVLM-500M Q8 — capacity-flat: resolution can't buy accuracy", SMOL, "smol")]


def panel(rows, color, fname, title):
    fig, (a1, a2, a3) = plt.subplots(3, 1, figsize=(8.6, 8.6), sharex=True,
                                     gridspec_kw={"height_ratios": [1.1, 1, 1]})
    x = [r[1] for r in rows]
    # accuracy (device-invariant — proven)
    a1.plot(x, [r[6] for r in rows], "o-", color=color, ms=6)
    for r in rows:
        a1.annotate(("★ " if r[7] else "") + r[0], (r[1], r[6]), xytext=(0, 9),
                    textcoords="offset points", ha="center", fontsize=8.5,
                    fontweight="bold" if r[7] else "normal", color=INK)
    a1.set_ylabel("accuracy /30")
    a1.set_ylim(0, 30)
    # encoder latency
    for i, (dev, ls, mk) in enumerate((("phone (Adreno)", "-", "o"), ("mac (Metal)", "--", "s"))):
        xs = [r[1] for r in rows if r[4 - 2 * i] is not None]
        ys = [r[4 - 2 * i] for r in rows if r[4 - 2 * i] is not None]
        a2.plot(xs, ys, ls, marker=mk, color=color, alpha=1 - 0.45 * i, ms=5, label=dev)
    a2.set_ylabel("encoder latency s")
    a2.set_yscale("log")
    a2.legend(fontsize=8, frameon=False)
    # ttft
    for i, (dev, ls, mk) in enumerate((("phone (Adreno)", "-", "o"), ("mac (Metal)", "--", "s"))):
        xs = [r[1] for r in rows if r[5 - 2 * i] is not None]
        ys = [r[5 - 2 * i] for r in rows if r[5 - 2 * i] is not None]
        a3.plot(xs, ys, ls, marker=mk, color=color, alpha=1 - 0.45 * i, ms=5, label=dev)
    a3.set_ylabel("TTFT s (serial)")
    a3.set_yscale("log")
    a3.set_xlabel("measured image tokens (log)")
    a3.set_xscale("log")
    for a in (a1, a2, a3):
        a.grid(alpha=0.25, which="both")
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
    star = next(r for r in rows if r[7])
    for a, v in ((a2, star[2] or star[4]), (a3, star[3] or star[5])):
        a.axvline(star[1], color=color, alpha=0.25, lw=6)
    a1.axvline(star[1], color=color, alpha=0.25, lw=6)
    a1.set_title(title + "\n(★ column shaded = benchmarked default · accuracy is device-invariant, verified)",
                 fontsize=11.5)
    fig.tight_layout()
    fig.savefig(ROOT / f"report/figures/{fname}", dpi=130)
    print(fname)


for title, rows, key in MODELS:
    panel(rows, C[key], f"sweet_{key}.png", title)

# overall pareto: acc vs ttft per device
fig, axes = plt.subplots(1, 2, figsize=(11.5, 5), sharey=True)
for ax, dev, ti, tj in ((axes[0], "phone (Adreno GPU)", 5, 5), (axes[1], "mac (Metal)", 3, 3)):
    for label, rows, key in MODELS:
        idx = 5 if "phone" in dev else 3
        pts = sorted([(r[idx], r[6], r[0], r[7]) for r in rows if r[idx] is not None])
        ax.plot([p[0] for p in pts], [p[1] for p in pts], "o-", color=C[key], ms=5,
                label=label.split(" —")[0])
        for p in pts:
            if p[3] or p[2] in ("@320", "1280px", "@1024"):
                ax.annotate(("★" if p[3] else "") + p[2], (p[0], p[1]), xytext=(5, -11 if p[2]=="@320" else 6),
                            textcoords="offset points", fontsize=8, color=INK)
    ax.set_xscale("log")
    ax.set_xlabel("TTFT s (serial, log)")
    ax.set_title(dev, fontsize=11)
    ax.grid(alpha=0.25, which="both")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
axes[0].set_ylabel("accuracy /30 (judged)")
axes[0].set_ylim(0, 30)
axes[0].legend(fontsize=8.5, frameon=False, loc="lower right")
fig.suptitle("Accuracy vs TTFT — every measured operating point, both devices (★ = benchmarked default)", fontsize=12)
fig.tight_layout()
fig.savefig(ROOT / "report/figures/sweet_overall.png", dpi=130)
print("sweet_overall.png")
