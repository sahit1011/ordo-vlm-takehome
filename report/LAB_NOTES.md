# Lab notes — running observations

Chronological record of every experiment, bug, and behavior change.
The final report (README) is assembled from here. Newest entries at the bottom.

---

## Day 1–2 (2026-08-18)

### Setup & porting observations

1. **Homebrew unusable on this Mac** (owned by another user, needs sudo).
   Worked around: adb from Google's platform-tools zip, cmake via pip.
   *Lesson for reproduction docs: assume no admin rights.*
2. **Full GGUF ladder exists prebuilt** for Qwen2.5-VL-3B (ggml-org: F16/Q8/Q4_K_M
   + mmproj F16/Q8; unsloth: Q2_K, Q4_0, and ~20 more). Zero conversion work needed —
   model choice validated.
3. **NDK dmg mount path contains spaces** ("/Volumes/Android NDK r27c") — broke
   naive `awk $NF` parsing. Also user's shell aliases `cp` → breaks scripts;
   scripts must use `/bin/cp`.
4. **`adb shell "nohup … &"` never returns** on Android 16 adbd even with
   stdin/stdout/stderr all redirected. Fix: `Popen` without waiting, gate on
   HTTP `/health`, then terminate the adb client. Cost us ~1 h.
5. **llama-server has no per-request vision-encode timing.** Patched
   `tools/server/server-context.cpp` to log `image encoded in N ms` around
   `mtmd_batch_encode()`. This patch is required for the entire stage-separated
   methodology.
6. **`--log-verbosity 1` silences llama-server entirely** (semantics inverted
   from expectation). Default verbosity already logs INFO.
7. **Prompt caching poisons repeat measurements**: same image → vision tokens
   cached → TTFT drops 2.1 s → 0.08 s. Must send `cache_prompt: false`.
8. **Server "prefill" timing includes the encode pass** — true prefill =
   `prompt_ms − encode_ms`. Naive reading understates prefill by ~2×
   (Mac: 293 "apparent" vs 654 true tok/s).
9. **OnePlus 15R (CPH2767, SM8845 "canoe")**: 8 cores, no efficiency cores —
   6× 3.32 GHz + 2× 3.80 GHz; i8mm, SVE2, **SME** present. 12 GB RAM
   (11.4 usable, ~3 free in daily state; ~4.5–5 after `free_ram.sh`).
   `/data/local/tmp` allows exec; Adreno OpenCL driver present
   (`/vendor/lib64/libOpenCL_adreno.so`, device reports "Adreno 829").
10. **RAM ≠ speed** (user question worth answering in report): capacity decides
    what fits; speed = compute + memory bandwidth + thermals. M3 Pro ≈ 150 GB/s
    + GPU + fans vs phone ≈ ~60 GB/s shared, CPU-only, ~4 W chassis.

### Mac measurements (M3 Pro 18 GB, Metal)

llama-bench, pp512 / tg64 (tok/s):

| Variant | Size | GPU pp | GPU tg | CPU pp | CPU tg |
|---|---|---|---|---|---|
| F16 | 5.75 GiB | 747 | 20.3 | – | – |
| Q8_0 | 3.05 GiB | 712 | 37.3 | – | – |
| Q4_K_M | 1.79 GiB | 679 | 58.5 | 159 | 52.3 |
| Q4_0 | 1.70 GiB | 719 | 60.9 | 220 | 57.2 |
| Q2_K | 1.18 GiB | 670 | 61.7 | – | – |

**Laws established:**
- Prefill is compute-bound → quantization does NOT speed it (≈flat, slightly negative).
- Decode is bandwidth-bound → tracks bytes almost linearly; Q2's gain over Q4 is
  only ~5% (dequant overhead) for real accuracy risk → Q4 is the knee.
- GPU vs CPU: prefill 4.3× faster on GPU, decode ≈ tie (same DRAM).
- Q4_0 beats Q4_K_M on ARM CPU (+39% prefill, +9% decode) via i8mm repack path.

### Image-token cap sweep (Q4, Mac, 12 MP supplement photo)

| Cap | Image tokens | Encode | TTFT | Small-text reading |
|---|---|---|---|---|
| native | **4,043** | 13.9 s | 20.7 s | partial |
| 1024 | 1,000 | 2.1 s | 3.9 s | kept |
| **576** | 568 | 1.06 s | 2.14 s | kept |
| 256 | 262 | 0.47 s | 1.16 s | **broken** (hallucinates: "100 tablets", "Blueberry") |

- **TTFT is decided by image tokens, not by quant level.** All quants show the
  same TTFT at a given cap. Answer to assignment teaser: one image ≫ a
  500-token prompt (uncapped a 12 MP photo is ~4,000 tokens ≈ 8× a 500-token prompt).
- 576 is the working sweet spot (13× encode reduction vs native, answers intact);
  256 is below the OCR floor for label-size text. (n=3 — revalidate on full eval set.)
- Qwen-VL warns it wants ≥1024 tokens for *grounding* tasks; our extraction QA
  survives 576. Grounding ≠ reading.

### Quant-vs-accuracy on smoke set (n=3 — indicative only)

All quants F16→Q4 answer identically (2/3). Q2 once "beat" F16 uncapped
(read creatine flavour) — vanished at the cap → sampling luck, not signal.
Demonstrates why the 32-photo eval set matters before any accuracy claims.

### SmolVLM contrast (Mac)

| Model @ config | Image tok | Encode | TTFT | Flavour | Tablets |
|---|---|---|---|---|---|
| Qwen-3B @576 | 568 | 1.1 s | 2.1 s | ✗ | ✓ |
| SmolVLM2-2.2B native | **7,844** | 23.1 s | 34.5 s | ✓ | ✓ |
| SmolVLM2-2.2B @576 | 600 | 1.7 s | 2.7 s | ✗ "unanswerable" | ✗ "1000 mg" |
| SmolVLM-500M any | 481–3,353 | 0.5–3.7 s | 1–5 s | ✗ | ✗ ("40", "200") |

- 500M decodes at 262 tok/s CPU (5× the 3B) but cannot read label-size text → wrong tier for Ordo.
- SmolVLM2-2.2B reads tiny text only via brute-force tiling (7.8k tokens, 2× Qwen's native!).
- **At equal token budget (~600), Qwen-3B wins.** Accuracy-per-image-token is the
  currency; Qwen has the best curve. "Use a smaller model" costs more accuracy
  than quantization does.
- Fun: 500M CPU decode (262 t/s) beats its own Metal decode (222 t/s) — GPU
  launch overhead dominates for tiny models.

### Phone measurements — the thermal/governor saga

- **Hot phone (95.8 °C SoC after ~40 min load)**: decode 0.4 tok/s, 12 MP photo
  encode 5.8 min, TTFT 685 s. Thermal throttling is a 10–40× penalty, not a
  rounding error. Battery temp lags SoC by minutes — cool-gates on battery temp
  alone are insufficient for back-to-back runs.
- **Screen-off governor**: erratic bench numbers (decode ±70%, worse at 6 threads
  than 4). Clock log: cores held at ~50% (1.65/1.9 GHz of 3.8/3.32 max).
- **Self-inflicted**: `cmd power set-fixed-performance-mode-enabled true` enables
  *sustained* mode = deliberately capped clocks. Wrong tool for peak benching. Undone.
- **Phone GPU (OpenCL/Adreno 829) works**: pp512 **260 tok/s ± 1.9**, tg64
  **18.45 ± 0.44** — stable, cool, and immune to page-cache eviction (OpenCL pins
  its buffers). ~8× CPU prefill. Decode ≈ within 2× of Mac Metal (bandwidth-tie law).
- **Phone CPU decode still pathological** (0.4–1 tok/s) even awake + RAM freed +
  `-mmp 0` while prefill is healthy (50–63 t/s @ t8). Suspect: governor drops
  clocks during memory-stall-heavy decode, or scheduler vs llama.cpp threadpool.
  OPEN QUESTION — timeboxed; GPU chosen regardless.
- Wi-Fi adb push throughput: ~5–11 MB/s. Budget ~3 min/GB for transfers.

### Working optimized config (as of Day 2 end)

**Qwen2.5-VL-3B Q4_0 + mmproj Q8_0 + `--image-max-tokens 576` + Adreno GPU
(`-ngl 99`)** — projected TTFT ~4–6 s on-device if the vision encoder also runs
on GPU (encoder A/B pending: the deciding experiment).

### Assignment teaser answers (running)

- *Does halving bytes halve latency?* No. Decode ~halves; prefill flat; encode
  untouched (separate mmproj file). TTFT barely moves.
- *Why might the encoder tolerate quantization differently?* Encoder errors
  corrupt all downstream tokens (no language prior to recover); ViT activations
  have outliers; and it's only ~0.4B of the total — quantizing it saves little
  for outsized risk. (Empirically mmproj Q8 = F16 on our set so far.)
- *500-token prompt vs one image?* The image, by ~8× uncapped; still ~equal at
  a 576 cap. Image resolution policy is the #1 TTFT lever.
- *ASR+TTS take their slice of 2 s — what's left?* At current numbers even GPU
  TTFT (~5 s) exceeds the whole budget → recommendation will argue staged UX
  (early TTS, encode-during-speech) + smaller image budgets, and name NPU as
  the real unlock. To be finalized with measured data.

### Dashboard ("Ordo Bench")

Built a local FastAPI + single-page dashboard: connect phone, pick variant/
engine/imt/threads, start server, drop photo + question, run e2e; shows live
SoC temp strip, stage waterfall (encode/prefill/decode), per-run tiles, and a
history table backed by `results/dashboard_runs.jsonl`. Stage palette validated
for CVD on the dark surface (dataviz validator: all checks pass).

### Measurement-integrity find #5: fake thermal sensors

`cpu-hw-trip-0/1` zones read a constant 95000 (they are throttle *setpoints*,
not sensors). Our hottest-cpu-zone heuristic picked them whenever real sensors
were cooler → **every sampled peak-temp before this fix was floored at 95.0 °C**
(the 95.8 °C hot-run reading was real — it exceeded the trip value). Fixed by
excluding `*trip*` zones. Real idle SoC: ~38–45 °C.

### Dashboard v2 — realtime

Live SSE token streaming (answer grows in place, TTFT stamped at first token),
meter-style gauges with % of max clock and delta-since-run-start badges, live
building waterfall, 1 s device polling during runs. Verified e2e on mac engine:
stream shows TTFT 2.067 s then ~58 tok/s live.

### Portability audit (is this setup device-agnostic?)

- **Methodology** (stage-separated timing, thermal gates, eval protocol,
  scoring): fully device-agnostic — anything that runs llama-server.
- **Plumbing**: any arm64 **Android 10+** with wireless debugging — adb pinning,
  thermal-zone/clock discovery, and the dashboard are vendor-generic. Caveats:
  (a) build flags assume ARMv8.6+ (i8mm) — older SoCs need a lower `-march`
  rebuild; (b) the GPU path is **Adreno-optimized OpenCL** — Mali/Xclipse GPUs
  have weaker llama.cpp OpenCL support, expect CPU-only there; (c)
  `free_ram.sh` app list is per-user.
- **iPhone: no.** No adb, no sideloaded binaries — same methodology would need
  an Xcode-built llama.cpp/Metal or MLX app. Out of scope; noted in report.

### The <1 s TTFT question — measured frontier so far (phone GPU)

TTFT = encode + prefill(image tokens + prompt) + sampling. With measured
prefill 260 tok/s (Qwen-3B Q4_0, Adreno):
- Qwen-3B @576 → prefill alone ≈ 2.3 s → 3B cannot reach 1 s at reading-grade
  token budgets on this GPU. Optimized floor ≈ 2.5–4 s (encoder pending).
- Path to <1 s: smaller decoder (LFM2-VL-1.6B ≈ 2× prefill; 500M ≈ 6×) ×
  smaller image budget (≤256 tok) × GPU encoder. Accuracy cost measured on the
  eval set → deliverable is the **accuracy-vs-TTFT Pareto curve**, and the
  recommendation picks the knee. Product-level levers outside the model:
  ROI cropping before encode; overlap encode with ASR (user is still speaking).

### Model bracket (0.3–4B) — final three

1. **Qwen2.5-VL-3B** — accuracy anchor, best OCR-per-token curve.
2. **LFM2-VL-1.6B** — edge-designed challenger (fast encoder, official Q4_0/Q8
   GGUFs); the realistic <1 s candidate with acceptable accuracy. TO MEASURE.
3. **SmolVLM2-2.2B** — measured: wins uncapped tiny-text via 7.8k-token tiling
   (unaffordable on-device); loses at equal budget. SmolVLM-500M kept as the
   speed-floor reference (fails label-text reading).

### Assignment question checklist (final doc must answer all)

- [ ] P1: why this model; which runtimes tried & what failed/patched
- [ ] P1: did anything reach GPU/NPU? (GPU: YES, Adreno via OpenCL — evidence;
      NPU: no, why + what it would take)
- [ ] P1: how a 1–2 GB model ships to users (drafted in README §1)
- [ ] P2: eval construction, difficulty spread, per-bucket counts
- [ ] P2: "how would you know the eval set is any good" (ceiling/discrimination/
      test-retest — run them)
- [ ] P3: per-precision table: accuracy · size · peak RAM · encode ms ·
      prefill tok/s · decode tok/s · TTFT (phone, cool, protocol stated)
- [ ] P3: where does it break first at Q4 vs F16 — failure pattern w/ examples
- [ ] P3: encoder vs decoder degradation — which degrades faster + HOW WE KNOW
      (independent mmproj×decoder quant matrix)
- [ ] P4: sustained 20q; thermals @10 min; memory pressure; battery drain
- [ ] LoRA: recovers quant loss? (+ our capped-token training variant)
- [ ] Teasers: bytes-vs-latency; encoder quant tolerance; image vs 500-tok
      prompt; ASR/TTS budget slice (drafts in place, finalize with data)
- [ ] What surprised us; what we cut and why

### PHONE GPU — full evidence (assignment P1 "did anything reach the GPU?": YES)

- OpenCL/Adreno 829 initializes and runs BOTH stages. Launch landmine: exporting
  `LD_LIBRARY_PATH=…:/vendor/lib64` shell-wide makes `nohup` link vendor
  libcrypto and die ("phdr mmap failed") — must scope via `nohup env LD_…=… ./llama-server`.
- **E2E optimized config on-device** (q4_0 + mmproj Q8 + imt576, supplement
  photo, real question): correct answer, **TTFT 12.8 s** = encode 7.78 s (61%)
  + prefill 3.12 s (574 tok @ 184 t/s) + sampling; decode 11.8 t/s; total 14.0 s;
  peak RAM 797 MB (VmHWM misses OpenCL driver buffers — under-reports GPU runs);
  **peak SoC 98.9 °C from ONE query** (real sensor, post-fix) — single-query
  thermal spikes are real; sustained use must throttle.
- **Encoder A/B (--no-mmproj-offload)**: encoder GPU 7.78 s vs CPU 22.6 s →
  **2.9× GPU speedup; encoder confirmed on Adreno**. Decoder stayed GPU in both
  (CPU-encoder run still prefilled at 250 t/s = GPU bench value — consistency ✓).
- vs hot-CPU baseline on same photo class earlier today (TTFT 685 s): **~50×**.
- Even ON the GPU the ViT encoder is 61% of TTFT → the next lever is a smaller/
  faster encoder (LFM2-VL) or lower token budgets, not more decoder tuning.

### LFM2-VL-1.6B (Mac) + the resolution axis

- Engine: 661 MiB file (1.17 B params). Metal pp 1966 / tg 162; **CPU pp 610 /
  tg 157** — CPU ≈ GPU decode (tiny model ≈ tiny bandwidth need). Easy photo
  TTFT 0.60 s native on Mac.
- Accuracy: full-res tiled (~1.8–2.1k tokens): 3/3 incl. creatine flavour
  (verbose, one hallucinated extra). Its `--image-max-tokens` caps **per tile**,
  not per image — nominal caps are NOT comparable across architectures; only
  measured `prompt_n` is.
- **Resolution axis (12 MP → 1024 px pre-downscale)**: LFM2 drops to 252 tokens
  / 0.32 s encode but **hallucinates on small text ("60 tablets")**; Qwen@1024px
  (1,027 tok, 2.1 s) ≈ same accuracy as Qwen@576-on-full-res (568 tok, 1.06 s).
  → **Pre-downscaling loses accuracy faster than model-side token capping**:
  dynamic-res pipelines downsample smartly from full pixels; pre-shrinking
  destroys glyphs first. "Just send smaller pictures" is the wrong lever.
- Recommendation shaping: **two-tier routing** — LFM2 fast-pass (sub-second
  class) for big-text scenes; Qwen-3B@576 for fine print. To validate on the
  full eval set.

### Phone Pareto sweep #1 (cool-gated, Adreno GPU, steady-state)

| Config | TTFT | Encode | Prefill | Decode | Fine print |
|---|---|---|---|---|---|
| Qwen2.5-3B @576 | **7.5 s** | 3.8 s | 237 t/s | 18 t/s | ✓ |
| Qwen2.5-3B @256 | 4.0 s | 1.7 s | 246 t/s | 20 t/s | ✗ hallucinates |
| LFM2 easy (254 tok) | 6.3 s | 5.8 s | 589 t/s | 55 t/s | ✓ big text |
| LFM2 full (1.8k tok) | 45 s | 41 s | 650 t/s | 48 t/s | ✓ unusable |
| LFM2 @1024px input | 6.3 s | 5.7 s | 559 t/s | 50 t/s | ✗ |

- First query after server start carries ~3 s OpenCL warmup in encode.
- **Encoder speed flips across platforms**: LFM2 encoder fast on Metal, ~4×
  slower per token than Qwen on Adreno; forced-CPU is even worse (9–10 s easy
  scene) → encoder speed is a property of model×runtime×silicon, not model.
  LFM2 out of the phone speed tier despite superb decoder (650 pf / 50 dec).
- On-device confirmation: @256 hallucinates exactly as on Mac.

### Protocol v2 + Qwen3-VL-2B

- **Truncation confound found**: verbose models (Qwen3-VL) spend 48 max_tokens
  on preamble before the fact → scored wrong despite knowing. Fix (protocol
  v2, uniform, product-realistic): append "Answer briefly with just the fact."
  + max_tokens 96. All final numbers re-run under v2.
- **Qwen3-VL-2B under v2, native res (Mac): 3/3 — "240" / "Watermelon Wave" /
  "120"** — best accuracy of any model tested, incl. exact flavour name. Cost:
  ~4k image tokens. At @576 it collapses (hallucinates "Mushroom"/"liquid") —
  its DeepStack ViT needs resolution more than Qwen2.5's. Engine: 1002 MiB,
  Metal pp 1372 / tg 104; CPU pp 407 / tg 96 (≈2× Qwen2.5-3B).
- Landscape: Qwen3-2B = accuracy champion at high budget; Qwen2.5-3B = best at
  capped budget; LFM2 = Mac-only speed tier; NPU claims (pasted advice) map to
  Qualcomm Genie/Hexagon stack, not LiteRT/llama.cpp — LiteRT+QNN added as
  planned runtimes in dashboard; runtime-gap experiment: same Qwen3-VL-2B on
  our stack vs Qualcomm's published 8 Elite numbers.
- Portable build variant added (`build_android_compat.sh`, armv8.2-a+dotprod,
  CPU-only, runtime KleidiAI dispatch) → runs on any recent arm64 Android;
  registered as `phone-compat` engine in dashboard.

### The <1 s answer: two-phase caching (measured on-device, Qwen3-2B@576, Adreno)

Product insight: the camera frame exists before the user finishes speaking →
encode + image prefill run during speech (llama-server `cache_prompt`), and
perceived TTFT = text prefill + first token. Measured:

| Path | Perceived TTFT | Fine print |
|---|---|---|
| Serial (no cache) | 8.8 s | ✓ |
| **Cached, full-res image** | **1.17–1.46 s** | ✓ ("120") |
| Cached + pre-resized (~540 tok) | **0.25–0.37 s** | ✗ knife-edge digits flip ("10") |

- Cache hit confirmed (cache_n 569); follow-up questions on the same scene
  are ~1.2 s (full-res) / ~0.3 s (resized) — Ordo's multi-question flow is
  nearly free.
- **The resolution knife edge**: server-side smart-resize from 12 MP @576
  → 564 tokens reads "120"; client-side resize to ~540 tokens loses the
  digit ("10") — a 4% pixel difference flips the smallest text. Patch-aligned
  Lanczos did not rescue it (double-resample + fewer tokens). Robust config:
  full-res upload in the hidden phase, same bytes re-sent on query (the
  1.2–1.5 s number); the remaining overhead is re-upload + 12 MP re-decode +
  hash, not model time.
- Verdict for the report: **<1 s perceived TTFT is achieved architecturally**
  for brand/big-text queries; **~1.2–1.5 s with full fine-print accuracy**;
  serial-path floor stays ~5 s. NPU (GenieX) is the lever that could make the
  serial path itself ~1–2 s. Native-res accuracy (3/3) costs 138.7 s serial
  on-device — measured once, never again.

### GPU serial-path tuning sweep (Qwen3-2B@576, Adreno, cool-gated) — closed

| Variant | Encode ms | TTFT | Verdict |
|---|---|---|---|
| A baseline (mmproj Q8) | 2,547 | 5.08 s | reference |
| B mmproj F16 | **4,761** | 7.09 s | ✗ 1.9× slower — encoder is bandwidth-bound too; Q8 wins |
| C --mtmd-batch-max-tokens 2048 | 2,489 | 5.51 s | no effect (576 tok fits one batch) |
| D -ub 1024 | 2,534 | 4.80 s | marginal |

**Conclusion: the Adreno serial floor is ~4.8–5.1 s TTFT for this workload,
encoder-bound, insensitive to standard knobs.** Remaining levers are
architectural (caching: 1.2–1.5 s perceived, deployed in dashboard as
warm-on-drop) and silicon (Hexagon NPU via GenieX — next timebox).
Also: warm-on-drop verified through the dashboard itself (mac engine:
0.23 s cached vs 1.25 s serial, same correct answer).

### Dev eval set (interim, synthetic — NOT the assignment set)

Assignment requires user's own photos; internet images would break the
"model has never seen them" guarantee. Interim: `harness/make_dev_set.py`
renders 24 images (menus/receipts/medicine/signs/handwriting/whiteboard/
book-spines/appliance) with controlled degradations (rotation/blur/dim/
glare/occlusion), 9 easy / 9 medium / 6 hard, exact auto-generated ground
truth. Provably unseen, unlimited, difficulty-controlled. Final claims stay
reserved for the user's 32 real photos.

### Dev-set ladder (24 synthetic items, Mac @576, protocol v2) — first real quant separation

| Config | Total | Easy | Med | Hard |
|---|---|---|---|---|
| F16 | 24/24 | 9/9 | 9/9 | 6/6 |
| Q8_0 | 24/24 | 9/9 | 9/9 | 6/6 |
| Qwen3-2B Q4_0 | 24/24 | 9/9 | 9/9 | 6/6 |
| Q4_0 | 23/24 | 9/9 | 8/9 | 6/6 |
| Q4_K_M | 22/24 | 9/9 | 8/9 | 5/6 |
| Q2_K | 22/24 | 9/9 | 8/9 | 5/6 |
| SmolVLM-500M | 22/24 | 9/9 | 9/9 | 4/6 |

**"Where does it break first?" — answered.** Quantized Qwen2.5 (Q4/Q2) breaks
FIRST on the handwriting-font whiteboard items — and the failure mode is
**salience retreat, not gibberish**: instead of reading the harder handwritten
list, the model answers "Todo" (the big legible header). Encoder was constant
(mmproj F16) across these configs → the damage is decoder-side reading
confidence, direct evidence for "the decoder degrades first" (encoder Q8 vs
F16 showed zero delta throughout). SmolVLM-500M fails differently: dense
receipt → echoes all text without extracting (capacity, not quant).
Q4_0 again > Q4_K_M (23 vs 22). Q2 = Q4_K_M on this set (no further drop —
synthetic fonts too clean; real photos expected to separate them).

**Phone dev-set (Qwen3-2B @576, serial, cool-gated): 25/26 (96%)** — all 24
synthetic + real tablet count; only the creatine knife-edge missed. TTFT
3.9–5.5 s stable across 26 consecutive queries — no thermal decay with
4-query gate cadence. Synthetic ≫ easier than real photos (24/24 vs 1/2) —
empirical proof that only own-photos give trustworthy accuracy (feeds the
"is the eval set any good" section).

**Ops lesson (cost us two Mac runs):** dashboard phone-engine starts swept
away harness-owned Mac servers (`pkill` orphan cleanup). Fixed: sweep only
when binding the mac port. Rule: one owner per device at a time; phone chain
and Mac harness serialize around dashboard restarts.

### Best-environment protocol (standing, per user directive)

Every measurement runs: background apps killed (`free_ram.sh`) · real-sensor
cool-gate (SoC ≤ 50–55 °C) · screen awake · engine warmed (first query
discarded — OpenCL compile ~3 s) · single model resident (server pkill between
configs) · models deleted from device after their e2e run (janitor) · serial
mode for measurement, cache only in product-mode runs (flagged in records).

### Part 4 stress suite — COMPLETE (champion config, unplugged, no cooling)

- **Sustained (59 q / 10 min):** decode 23 → 14–15 t/s by q10 then FLAT to q59;
  TTFT equilibrium ~6.8 s (+65% vs cool 4.1 s). Degradation plateaus — no spiral.
- **Thermals:** SoC equilibrium 56–68 °C (peak 78) — soft landing, no hard
  throttle. 59/59 correct: **accuracy is thermally invariant; heat taxes speed only.**
- **Memory pressure** (4 heavy apps launched): zero measurable impact — GPU-pinned
  buffers immune to eviction (converse of the CPU page-thrash pathology).
- **Battery: 3% / 64 queries ≈ 0.05%/query** (~21 queries per 1%).
- Dev-set bracket (Mac @576): LFM2-450M **23/24** wins the <1B slot over
  SmolVLM-500M (22/24, hard 4/6). On-device: Qwen3-2B 25/26 @4.1 s p50 ≫
  Qwen2.5-3B (accurate, 8.6 s p50, encoder 2× slower on Adreno).

### Open items

- [ ] Encoder A/B on phone: mtmd on OpenCL vs CPU (decides TTFT story)
- [ ] Phone CPU decode pathology: root-cause or timebox out
- [ ] 32 eval photos (user) + 50 LoRA photos (user) — critical path
- [ ] Full ladder on phone with thermal protocol (after photos)
- [ ] Stress: sustained 20q / 10-min soak / memory pressure / battery (scripts ready)
- [ ] QLoRA on Colab; extra experiment: train at deployment image budget (576)
- [ ] Eval-set validity checks: cloud-model ceiling, discrimination, test-retest
