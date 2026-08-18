"""Decision map — every measured combo, worst -> best TTFT (the whole journey).

Horizontal bars on a log TTFT axis, phone measurements only; each row is one
exact combo (model . precision . input budget . condition), labeled with its
accuracy on the 30-photo real set and, where a decision hinged on it, the
numbered decision note. Chronology of decisions runs (1)->(7) in the footer.
Palette validated (dataviz six checks, all-pairs CVD) 2026-08-19.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
FAM = {"q3": "#2a78d6", "q25": "#c0508c", "smol": "#1baf7a", "lfm": "#eb6834"}
INK, MUT = "#1a1d21", "#6a6f76"

# ttft_s, combo, family, accuracy, decision note, is_ship
ROWS = [
    (37.3, "Qwen3-2B Q2_K @576 — decoder silently on CPU",           "q3",  "85%",   "⑥ no OpenCL Q2_K kernels → kernel-coverage law", 0),
    (36.6, "Qwen3-2B Q4_0 @576 — defective tuned-CPU build",         "q3",  "—",     "② 100× decode defect isolated → CPU engine fixed", 0),
    (17.3, "Qwen3-2B via MNN · OpenCL (618 tok)",                    "q3",  "✗",     "③ vision 5–6× slower, wrong answer → runtime rejected", 0),
    (13.2, "Qwen3-2B Q4_0 @1024",                                    "q3",  "87%",   "judged: no gain over @576 — too slow to ship", 0),
    (11.7, "LFM2-1.6B Q4_0 native — encoder on CPU (op gap)",        "lfm", "74%",   "③ encoder off-GPU → cells cancelled", 0),
    (10.5, "Qwen3-2B BF16 @576 (feasibility probe)",                 "q3",  "✓",     "GPU-resident but 3.2 GB — feasible, pointless", 0),
    (6.4,  "SmolVLM-500M Q8 native",                                 "smol","47%",   "", 0),
    (6.3,  "Qwen3-2B Q8_0 @576",                                     "q3",  "90%",   "flat within ±1 of Q4_0 at +38% TTFT", 0),
    (6.0,  "LFM2-450M Q8 native 12 MP",                              "lfm", "72%",   "", 0),
    (4.6,  "Qwen3-2B Q4_0 @576 — serial champion",                   "q3",  "87%",   "④ champion switch (2.5-3B dethroned by measurement)", 0),
    (4.5,  "SmolVLM-500M Q8 @576",                                   "smol","50%",   "capacity-flat ~40–50% at every setting", 0),
    (3.1,  "Qwen3-2B Q4_0 @448",                                     "q3",  "73%",   "⑤ the token dial: −128 tok ≈ −1 s", 0),
    (2.2,  "SmolVLM-500M Q8 @320",                                   "smol","43%",   "", 0),
    (2.1,  "Qwen3-2B Q4_0 @320",                                     "q3",  "70%",   "enumeration sweet spot (8/9 recall)", 0),
    (1.7,  "Qwen3-2B Q4_0 @256",                                     "q3",  "57%",   "", 0),
    (1.6,  "LFM2-450M Q8 · 1344 px input",                           "lfm", "53%",   "", 0),
    (1.3,  "Qwen3-2B Q4_0 @576 + warm-on-drop ⚡",                    "q3",  "87%",   "⑦ THE SHIPPING CONFIG ★  (perceived 1.17–1.46 s)", 1),
    (0.96, "SmolVLM-500M Q8 · 512 px (1-tile)",                      "smol","30%",   "", 0),
    (0.93, "Qwen3-2B Q4_0 @128",                                     "q3",  "47%",   "sub-second club: champion", 0),
    (0.82, "Qwen3-2B Q4_0 @96",                                      "q3",  "40%",   "wins the small models' own speed class", 0),
    (0.66, "LFM2-450M Q8 · 512 px (1-tile)",                         "lfm", "30%",   "", 0),
    (0.62, "LFM2-450M Q8 · 1024 px input",                           "lfm", "37%",   "", 0),
    (0.44, "LFM2-450M Q8 @64 · small 1-tile photo",                  "lfm", "✗",     "the floor — single sighting, knife-edge digits lost", 0),
]

fig, ax = plt.subplots(figsize=(11.5, 11.5))
ys = range(len(ROWS) - 1, -1, -1)  # worst at top
for y, (ttft, combo, fam, acc, note, ship) in zip(ys, ROWS):
    ax.barh(y, ttft, height=0.62, color=FAM[fam], zorder=3,
            edgecolor=INK if ship else "none", linewidth=1.4 if ship else 0)
    ax.annotate(f"{ttft:g} s", (ttft, y), xytext=(5, 0), textcoords="offset points",
                va="center", fontsize=8.5, color=INK, fontweight="bold", zorder=4)
    tail = f"{acc}" + (f"   ·  {note}" if note else "")
    ax.annotate(tail, (ttft, y), xytext=(46, 0), textcoords="offset points",
                va="center", fontsize=8, color=MUT, zorder=4)
    ax.annotate(combo, (0.4, y), xytext=(-6, 0), textcoords="offset points",
                va="center", ha="right", fontsize=8.6, color=INK,
                annotation_clip=False)

ax.set_xscale("log")
ax.set_xlim(0.4, 3000)
ax.set_ylim(-0.8, len(ROWS) - 0.2)
ax.set_yticks([])
ax.set_xticks([1, 10, 37])
ax.set_xticklabels(["1 s", "10 s", "37 s"], fontsize=9)
ax.grid(axis="x", alpha=0.25, zorder=0)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.set_xlabel("TTFT — full serial pipeline on the phone (log scale; ⚡ = perceived, cached)", fontsize=10)
ax.set_title("Decision map — every combo on the road from 37 s to 0.44 s\n"
             "worst → best TTFT · % = LLM-judge accuracy on the 30-photo real set · ★ = shipping config\n(the 685 s thermal-disaster run is off this scale — protocol story in LAB_NOTES)",
             fontsize=13, pad=14)
ax.legend(handles=[Patch(color=FAM["q3"], label="Qwen3-VL-2B"),
                   Patch(color=FAM["lfm"], label="LFM2-VL"),
                   Patch(color=FAM["smol"], label="SmolVLM")],
          loc="lower right", fontsize=9, frameon=False)
fig.text(0.5, 0.030, "decision chronology:  ① thermal protocol (the off-scale 685 s run) → ② build defect fixed → ③ rivals & off-GPU architectures rejected",
         ha="center", fontsize=8.6, color=MUT)
fig.text(0.5, 0.012, "→ ④ champion switch → ⑤ token Pareto mapped → ⑥ kernel-coverage law → ⑦ ship it: warm-on-drop caching",
         ha="center", fontsize=8.6, color=MUT)
fig.subplots_adjust(left=0.30, right=0.985, top=0.92, bottom=0.095)
out = ROOT / "report/figures/decision_map.png"
fig.savefig(out, dpi=130)
print(f"chart -> {out}")
