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

### Real-photo eval (ordo-dataset, 30 items, draft GT, Mac @576 v2)

| Model | Real | Synthetic | Note |
|---|---|---|---|
| Qwen3-VL-2B Q4 | **26/30** | 24/24 | champion confirmed |
| LFM2-VL-1.6B Q4 | 24/30 | 24/24 | beats Qwen2.5-3B on real photos |
| Qwen2.5-VL-3B Q4_0 | 23/30 | 23/24 | |
| LFM2-VL-450M Q8 | 18/30 | 24/26 | synthetic inflated by +30 pts |
| SmolVLM2-2.2B | 16/30 | 24/24 | capped budget kills it on real data |
| SmolVLM-500M | 14/30 | 22/24 | |

**Eval-validity finding (assignment: "how would you know the set is any
good?"):** the real set discriminates a 47→87% spread that the synthetic set
compressed to 92–100%. Rendered text is too clean — small models pass it and
fail reality. Synthetic sets are pipeline tools, never accuracy evidence.
Provenance caveat: 24/30 items are WhatsApp-recompressed, 3 screenshots,
3 camera — final set needs camera-shot replacements (assignment requires own
photos; also missing menu/receipt/handwriting/appliance categories; skews
easy: 17/10/3).

### Runtime scouting round-up (Day 3 evening)

- **GenieX (Qualcomm)**: open-source, GGUF VLMs on Hexagon/GPU/CPU — but
  Android integration is **Gradle-SDK-only** (no adb-pushable binaries, no
  server mode), documented devices are Snapdragon **8 Elite / 8 Elite Gen 5**
  (SM8845 not listed). Verdict: docs-only "what it would take" writeup unless
  time surplus appears.
- **LiteRT / AI Edge Gallery**: LiteRT cannot run Qwen3-VL at all (vision
  catalog is Gemma-family). Gallery per-SoC APK (sm8850 build) **installs
  cleanly on the SM8845**; Gemma-3n datapoint pending user's HF-login model
  download in-app. NPU delegate: early-access gated.
- **MNN (Alibaba) — the real second runtime.** In-app benchmark on our phone,
  Qwen3-VL-2B, PP128/TG128:
  | Backend | Prefill | Decode | Peak mem |
  |---|---|---|---|
  | OpenCL | 255.5 ± 46 t/s | 22.6 t/s | 2.5 GB |
  | CPU | 78.7 ± 7 t/s | **24.6 t/s** | 4.5 GB |
  Backend list on this device: **CPU + OpenCL only — no QNN/NPU exposed.**
  vs llama.cpp: GPU ≈ tie (decode bandwidth-bound both; prefill not better at
  长 context), **CPU decisively healthier** (24.6 t/s decode where llama.cpp
  CPU decode is pathological on this phone) → MNN-CPU is the better
  device-agnostic tier. Vision-encode time NOT covered by their benchmark —
  measuring ourselves via MNN CLI (NDK cross-compile like llama.cpp,
  `-DMNN_BUILD_LLM=ON -DMNN_OPENCL=ON`; engine also has `-DMNN_QNN=ON` plugin
  worth one experiment). Build + MNN-format model download in flight.
- Every zero-integration NPU path on this device is now exhausted: the serial
  encoder wall (~2.5 s) stands across llama.cpp ×3 builds and MNN ×2 backends.

### Rich-intermediate resize: falsified (trilogy complete)

2016 px patch-aligned Lanczos intermediate → answers got WORSE ('190'/'white').
With v2 (1344 px) and v3 (2016 px) both failing while server-side resize from
the 12 MP original succeeds at the same ~545–564 token count: **any client-side
resample destroys knife-edge glyphs; only single-pass resize from original
pixels preserves them.** Full-accuracy perceived floor: 1.17–1.46 s
(full-res upload). 0.25–0.44 s tier = big-text queries only.

### Ops lessons (accumulating)

- `socd` thermal zone = battery state-of-charge masquerading as 57 °C
  (fake-sensor #3; excluded with trip/ibat).
- Wireless adb can drop mid-chain (transient "device offline") — scripts need
  retries; runs crash-recover from JSONL.
- Benchmark apps (MNN Chat) park multi-GB engines after use — freed 2.4 GB by
  force-stop; always sweep foreign AI apps before measuring.
- API image-count ceiling in long sessions → all screenshot/photo viewing
  delegated to fresh-context subagents (GT drafting, app driving, screenshot
  reading all ran as agents successfully).
- User decision: LoRA deferred; current focus = runtime × encode-latency
  frontier on Qwen3-VL-2B.

### MNN CLI on-device (our own build, NDK cross-compile, dashboard-grade test)

Build: shared-libs required (their LLM cmake breaks static); OpenCL driver libs
copied local (vendor-path linker landmine, MNN flavor: trips on power-HAL lib).
Qwen3-VL-2B-MNN (their official conversion), greedy sampling, on our phone:

- **Cold-start e2e (load + encode + answer): 7.5–9.2 s** — remarkable; llama.cpp
  needs ~13 s load alone. MNN's mmap/init is the best cold-start measured.
- **Vision accuracy: fails items llama.cpp passes at comparable pixel budgets.**
  Default `image_size: 420` → "1000 tablets"; `<hw>1148,1540</hw>` override →
  "500 tablets"; brand question (our 540-token tier gets "TATA" right) →
  hallucinated "Nature's Answer". Their image preprocessing loses fine print —
  4th confirmation of resample sensitivity, now cross-runtime.
- No stage timing in llm_demo without patching; llm_bench is text-only.

**Runtime hunt CLOSED.** Across llama.cpp (CPU/OpenCL/compat), MNN (app +
our CLI, CPU/OpenCL), GenieX (device-gated), LiteRT (no Qwen support),
AI Edge Gallery (Gemma-only): **llama.cpp + Adreno remains the best
accuracy-per-second stack on this device**; MNN's niches are cold-start
(7.5 s e2e!) and CPU-only devices (working 24.6 t/s decode). No accessible
runtime reaches <1 s serial encode at reading accuracy on SM8845 —
the caching architecture is not merely the best route to <1 s perceived,
it is the only one, now proven exhaustively.

### Token-budget Pareto on REAL photos (phone GPU, champion, serial)

| Cap | Accuracy | TTFT p50 | Encode med | Tokens actual |
|---|---|---|---|---|
| 576 | 25/30 (83%) | ~4.3 s | 2.6 s | 570 |
| 448 | 21/30 (70%) | 3.1 s | 1.8 s | 449 |
| 320 | 19/30 (63%) | 2.1 s | 1.1 s | 326 |

≈ every −128 tokens: −1 s TTFT, −7–10 pts accuracy. On diverse real photos the
budget trade is a smooth slope (unlike the synthetic knife-edge cliff) —
strongest argument for per-query routing over any fixed cap.
QNN check: **no Hexagon HTP runtime libs in /vendor/lib64** — the MNN_QNN
build has nothing to bind; NPU on this device is vendor-privileged only.
(First-query encode again carried warmup: 4.3 s vs 1.8 s steady — excluded.)

### MNN verdict v2 — CORRECTED (measurement trap #7: silent feature omission)

Our first MNN build omitted `-DMNN_BUILD_OPENCV=ON` → `LLM_SUPPORT_VISION`
never compiled → `<img>` tags silently ignored (logcat stats: prompt 28 tok,
vision 0.00 s, 0.00 MP). **Every earlier MNN "accuracy failure" was a blind
hallucination — retracted.** Trap #7: a build flag that doesn't error, just
quietly drops your image. (Also: MNN_PRINT routes to logcat on Android —
stats were never on stdout.)

Vision-enabled rebuild, real numbers (Qwen3-VL-2B-MNN, OpenCL, on-device):
- **Answer "120" — CORRECT.** MNN's conversion is accurate.
- **vision time = 122.35 s for 1.77 MP (0.014 MP/s)** — MNN's Adreno vision
  encoder is ~15–50× slower than llama.cpp's (2.6 s / 570 tok). Decode dragged
  to 7.3 t/s by the 1,758-token context. CPU vision run froze the phone
  (user rebooted) — consistent ≥2 min class.

**Runtime chapter closed, final form: llama.cpp's Adreno vision kernels are
the best available open-source mobile vision-encode path** — MNN wins text
cold-start and CPU decode, loses vision by orders of magnitude. Champion
stack unchanged and now proven against every accessible alternative.

### Cross-runtime grid — COMPLETE (same image, same question, serial, warm)

**Mac (M3 Pro):** llama.cpp Metal: enc 0.64 s · TTFT 1.36 s · 62.8 t/s · "120"✓ |
llama.cpp CPU: enc 3.90 s · TTFT 5.55 s · 80.2 t/s (!CPU decode > Metal) · ✓ |
MNN Metal: enc 3.24 s · TTFT ~4.2 s · "10"✗ | MNN CPU: enc 3.69 s · ~5.6 s · ✗ |
LiteRT mac: binaries missing dylibs — undistributable, documented.

**Phone:** llama.cpp Adreno: enc 2.6 s · TTFT 4.1 s · 25.9 t/s · ✓ (champion) |
MNN OpenCL fair: enc 14.4 s · TTFT 17.3 s · "100"✗ | MNN CPU: froze device |
LiteRT CPU (Gemma 3n, text): 7.6 t/s decode, 13 s cold e2e; GPU: accelerator
libs not shipped; **NPU: backend valid, APK QNN libs load, but "Model requires
one of [cpu,gpu]"** — NPU needs per-SoC compiled bundles; none public for
Qualcomm (only mediatek.mt6993 exists). Last NPU door: Gallery in-app download.

**LiteRT integration war stories:** version lock (v0.7 binary can't read new
bundle format; v0.11+ needs libGemmaModelConstraintProvider — solved with a
versioned stub .so exporting 3 no-op symbols); macOS binaries missing chained
dylibs. Grid conclusions: llama.cpp wins encode 5–6× on BOTH platforms and is
the only runtime reading fine print; decode clusters everywhere (bandwidth);
CPU>GPU decode for small models on both platforms; each rival lost to a
different failure class (MNN: vision preprocessing; LiteRT: distribution +
model-catalog lock-in).

### Enumeration matrix (real photo, "name all visible supplements", recall /9)

| Cell | TTFT | Encode | Decode | Recall |
|---|---|---|---|---|
| Mac Qwen3-2B Metal | 1.27 s | 0.63 s | 98 t/s | **8/9** |
| Mac Qwen3-2B CPU | 5.54 s | 3.92 s | 76 t/s | 7/9 |
| Mac MNN Metal | 3.80 s | 3.24 s | 85 t/s | 2/9 |
| Mac LFM2-450M Metal | 1.22 s | **0.19 s** | 253 t/s | 5/9 |
| Mac Smol-500M Metal | **0.98 s** | **0.08 s** | 207 t/s | 4/9 |
| Phone Qwen3-2B GPU @576 | 4.92 s | 2.54 s | 26.5 t/s | 7/9 |
| Phone Qwen3-2B GPU @320 | **2.97 s** | 1.11 s | 28.4 t/s | **7/9** (= @576!) |
| Phone Qwen3-2B CPU | 36.6 s | 20.7 s | 0.4 t/s | 7/9 (285 s total) |

Phone sub-1B (GPU @576): LFM2-450M TTFT 8.34 s enc 1.6 s dec 52 t/s **recall
7/9** (matches champion — but its 2,104-token tiling makes it 2.8× slower than
Qwen3@320 at equal recall); Smol-500M TTFT 6.84 s recall 4/9. **Token-efficiency
law, final form: TTFT is a property of token count, not kernel speed** — LFM2's
3× faster encoder is fully repaid by 3.8× more tokens through prefill
(Mac: 191 ms + 834 ms vs Qwen's 632 ms + 444 ms → dead-heat TTFT, 5 vs 8 recall).
Findings: recall tracks parameters monotonically (8→5→4→2); sub-1B encoders
are blazing (75–191 ms Metal) but miss half the shelf; **@320 matches @576
recall on enumeration at −40% TTFT** → per-query token routing validated
(fine print needs 576; product-naming doesn't); backend never changes recall
(GPU=CPU answers at 29× speed apart).

### LiteRT on Mac — closed from all four directions

v0.7 binary runs but: current .litertlm = format-ahead ("audio_encoder_hw"),
.task preview bundle = wrong container ("Failed to parse LlmMetadata").
v0.9–v0.16 binaries: unresolvable dylib chains. Source: Bazel Apple crosstool
demands full Xcode (CLT insufficient — same CLT built llama.cpp and MNN fine).
LiteRT is unbuildable/unrunnable on this Mac from any public artifact.

### Qwen3-2B precision ladder — Mac Metal reference (30 real photos, @576)

| Precision | Size | Accuracy | TTFT p50 | Decode | prompt_n p50 |
|---|---|---|---|---|---|
| BF16 | 3.2 GB | 24/30 | 1.23 s | 32.3 t/s | 580 |
| Q8_0 | 1.7 GB | 24/30 | 1.17 s | 62.3 t/s | 580 |
| Q2_K | 742 MB | 24/30 | 1.20 s | 96.9 t/s | 580 |

**Accuracy perfectly flat BF16→Q2_K on the 2B champion** — the real-photo set
detects zero quantization damage even at Q2_K, while decode scales 3× with
bytes and TTFT doesn't move (prefill compute-bound, encode untouched — the
ladder laws hold exactly). Contrast: Qwen2.5-3B showed its knee at Q4 on
synthetic fine-print items. Two readings: (a) the 2B's knife-edge items are
already lost at @576 (its misses are resolution-bound, not precision-bound), so
precision has no accuracy left to take; (b) Q2_K of the 2B (742 MB) becomes the
size-floor candidate — phone confirmation cells in flight (files:
results/mac-qwen3-2b-{bf16,q8,q2}-ladder-ordo-20260818-230849.jsonl).

### Sweet-spot sweep — supps enumeration vs token budget (Mac Metal, 40 runs)

One image (12MP shelf), one query ("name all visible supplements", recall /9),
five models × fine `--image-max-tokens` ladder; x-axis = measured prompt_n
(nominal caps bind per-tile on LFM2/Smol → incomparable). Chart:
figures/sweetspot_supps_mac.png · data: results/sweetspot-supps-mac-20260818-231325.jsonl.

- **Qwen3-2B Q4_0 knee at 320 tok: 8/9 @ 0.83 s** — 0–2/9 below 256, flat 8/9
  from 320→1024 (2.9× TTFT for nothing), **9/9 only at native 4,035 tok /
  16.7 s** — the 9th (knife-edge) label costs 20× the sweet spot.
- Real dip at 448 (6/9): smart-resize grid effect, deterministic, not noise.
- **LFM2 token knob doesn't bind**: tiler floors at ~1,618 tok on this image
  at every cap 64→native → its TTFT floor is architectural. 450M rides the
  floor to 8/9 @ 0.99 s (enumeration-competitive!); 1.6B same recall at 3.2 s.
- SmolVLM-500M: 4/9 ceiling, and native *degrades* to 1/9 (tiling fragmentation).
- Qwen2.5-3B dominated everywhere (encoder 2× slower/token, ceiling 7/9 @ 21 s).
- Product read: route enumeration at 320; escalate to native-res only on a
  "read the fine print" intent; never park between 576–1024 for this task class.

### MXFP4 rung (the "what about FP4?" answer, measured)

NVFP4 = Blackwell-only (HW FP4 + FP8 block scales; no llama.cpp/Adreno/Metal
path). Its open cousin MXFP4 (E2M1 + E8M0 per-32 scales) IS in our build — but
**trap #8: `MXFP4_MOE` is a silent no-op on dense models** (produced pure Q8_0,
byte-identical size; verified by tensor dump: 0 MXFP4 tensors). Real rung
forced via `--tensor-type attn_*/ffn_*=mxfp4`: 196/197 matrices MXFP4,
1.09 GB (vs Q4_0 1.06 GB). **30-photo Mac cell @576: 25/30, TTFT p50 1.18 s,
decode 89.5 t/s** — best accuracy on the Mac ladder (BF16/Q8/Q2 all 24/30;
±1 item = noise) at Q4 size with near-Q2 decode. Caveat before crowning it:
Metal has MXFP4 kernels (GPT-OSS era); the OpenCL/Adreno backend may not —
phone cell required before it counts for deployment (queued after mega-chain).

### LFM2-1.6B on phone: encoder is NOT on the GPU (OpenCL op gap)

Server log during the 1.6B phone cells:
`WARNING: the CLIP graph uses unsupported operators by the backend (backend=OpenCL)`
→ the SigLIP2-so400m encoder falls back to CPU. ~11 s per 512-px tile; 3-tile
photos (≈790 tok) = ~33 s encode, TTFT 35.7 s. The 450M's smaller encoder ran
its tiles in 1.6 s total, and Qwen3's encoder is fully OpenCL-resident (2.6 s
@576) — so the 1.6B's phone TTFTs are a *CPU-encoder* number, not a GPU one.
Grid footnote required: on Adreno, "GPU run" for LFM2-1.6B means GPU decode +
CPU vision. Same log also warns `flash attention not supported by OpenCL` —
pre-answers the phone FA A/B (fa=1 should no-op on Adreno; llama-bench cell
will confirm).

### FA / quantized-KV A/B on Adreno (llama-bench, champion Q4_0, cool-gated)

| fa | KV | pp512 t/s | tg128 t/s |
|---|---|---|---|
| 0 | f16 | 327.2 | 15.8 |
| 0 | q4_0 | **context creation fails** (quantized KV requires FA — same as Mac) |  |
| 1 | f16 | **347.5 (+6%)** | **17.3 (+10%)** |
| 1 | q4_0 | 325.7 | 13.8 (**−20%** vs fa=1/f16) |

FA on OpenCL works for the Qwen3 graph and pays (+6% prefill / +10% decode);
the earlier "flash attention not supported by OpenCL" warning was the LFM2
server's — FA support is per-graph (head-dim dependent), another per-model
placement fact the enc/dec column can't capture alone. q4_0 KV costs 2.5× more
decode on Adreno than on Metal (−20% vs −8%): use only if context RAM binds.
Defaults (fa on, f16 KV) were already optimal on both platforms.

### Q2_K on Adreno: the DECODER falls back to CPU too (k-quants have no OpenCL kernels)

Phone Q2_K @576 rows: prefill 17–21 t/s (vs Q8's 248–374), decode 0.4–0.5 t/s
(vs 12–23), TTFT 22–37 s, RAM *higher* than Q8 (1.32 vs 1.02 GB — CPU-side
buffers), encode unchanged (mmproj Q8 still GPU), SoC to 85 °C. No log warning
this time — the OpenCL backend declines unsupported weight types *silently* at
tensor-placement (only the CLIP graph case warns). First write-up overclaimed
"all k-quants fall back" — the ledger rate scan falsified it within minutes:

| config (phone-gpu, uncached, >100 tok) | n | prefill t/s p50 | class |
|---|---|---|---|
| lfm2-450-q8 | 117 | 1483 | GPU |
| smol500-q8 | 129 | 527 | GPU |
| lfm2-q4 (Q4_0) | 64 | 461 | GPU |
| qwen3-2b-q4 (Q4_0) | 220 | 406 | GPU |
| qwen3-2b-q8 | 30 | 265 | GPU |
| q4_0 (Qwen2.5 Q4_0) | 23 | 217 | GPU |
| smol22-q4 (**Q4_K_M**) | 1 | 213 | **GPU** |
| qwen3-2b-q2 (**Q2_K**) | 12 | **18** | **CPU** |

Corrected rule: **kernel coverage is per weight-type — Q4_K_M has OpenCL
kernels (213 t/s measured); Q2_K does not (18 t/s, the only CPU-class config
of eight).** BF16 coverage unknown → feasibility probe queued. Kills the
742 MB Q2_K size-floor for Android (Mac-Metal only). Detector hardened in the
dashboard: decoder placement is now *measured* at every server launch (text-only
~250-token probe prefill; GPU class 250–420 t/s vs CPU 17–55 on this device —
an order of magnitude apart) and stamped with the rate, since logs at default
verbosity say nothing. Q2 cell allowed to finish for the accuracy datum;
BF16 30-photo cell trimmed to the probe.

### Qwen3-2B phone ladder @576 (30 real photos, Adreno)

Q4_0 **25/30**, TTFT p50 4.1 s (champion) · Q8_0 **25/30**, 6.3 s (accuracy
flat, +54% TTFT from bandwidth) · Q2_K accuracy tracking ~flat (11/13 mid-run)
**but decoder on CPU** → 37 s TTFT, unshippable on this backend. Phone story
matches Mac: precision doesn't buy or cost accuracy on the 2B champion —
backend kernel coverage decides what's deployable.

### LFM2-1.6B remaining phone cells cancelled (user call, 2026-08-18 ~23:40)

@1344 and full-res cells stopped mid-run: the encoder's CPU fallback makes
them a measurement of a config we'd never ship (TTFT 12–36 s). Kept: the
completed @1024 cell (19/30), Mac reference cells, sweet-spot sweep, and the
op-gap finding itself. Partial @1344 rows remain in the ledger (flagged
enc=cpu). Chain relaunched from FA/KV A/B onward + MXFP4 phone cell appended.

### Chain 3B results — BF16 probe, MXFP4 phone, placement probes (2026-08-19 ~00:45)

**BF16 on Adreno: GPU-resident, bandwidth-bound.** llama-bench pp512 157 t/s /
tg64 14.9 t/s; launch probe dec=adreno-ocl (133 t/s); scored query correct
("120") at 10.5 s TTFT. Feasible, pointless — 3× the download of Q8 for equal
accuracy and worse latency.

**MXFP4 on Adreno: no OpenCL kernels — Metal-only rung.** Launch probe caught
it instantly: dec=cpu-fallback (25 t/s). Supps enum @576 still 7/9 (equals
champion — backend never changes recall) but 22 s TTFT; @320 5/9 (below the
champion's 7/9 @320 — CPU decode also ran hotter-throttled). Verdict: the
best-scoring Mac rung (25/30) is undeployable on this phone.

**Placement probes — the '?' rows resolved (249 rows backfilled):**
- LFM2-450M: **enc=cpu (op gap)** — same SigLIP2 fallback as the 1.6B; the
  earlier timing hint ("looks GPU") was wrong — refusing to stamp it was right.
  Its 86M tower is just small enough to hide on CPU (1.6–4 s). dec GPU 1065 t/s.
- SmolVLM-500M: **enc=adreno-ocl** — the only non-Qwen encoder that runs on
  this GPU. dec 818 t/s.
- SmolVLM2-2.2B: **enc=cpu (op gap)**, 55 s encode at @576 — explains its
  single catastrophic phone row. dec GPU 259 t/s.

Tally: 3 of 6 model-encoders silently fall off the Adreno GPU (LFM2×2,
SmolVLM2); only Qwen and SmolVLM-500M encoders are OpenCL-resident. Final
deployable Android ladder: **Q4_0 / Q8_0 / F16-BF16(slow)**. Phone released,
all probe files janitored.

### LFM2-450M phone cap ladder (5-photo confirmation cell, 2026-08-19)

Same 5 real photos at imt 64/256/1024/native. The cap does NOT change tile
count but DOES scale per-tile tokens: 1-tile photo (o03) encode 157→542→853 ms
across 64/256/1024; 3-tile photos ~4.5→5.0→9.0 s (CPU encoder). Accuracy:
2/5 at 64/256/native; **1024 degrades to 1/5** ("Titan"→"Citizen",
"Lemon"→"Black", one "Cannot read") — upscaling past the native tile grid
hurts, matching the Mac 576-dip and SmolVLM native-degradation pattern.
o03 at imt=64 hit **0.44 s TTFT** (the Mac-class number) but read the plate
worse. Best phone setting: imt 256/native → ~8 s TTFT multi-tile / ~1 s
single-tile, still dominated by the champion on both axes. All rows in ledger
with cpu⚠ encoder labels.

### LFM2 1-tile mode: auto-preprocess shipped + 30-photo phone cell (2026-08-19)

Dashboard now downscales uploads to the 1-tile budget (max side 512) whenever
the active config is LFM2 — the only latency lever that works on this
architecture, since imt trims within tiles and geometry sets tile count. Qwen
configs never resized (smart-resize from original pixels = accuracy path).
Verified 1-tile on Mac first (161–225 prompt tokens). Phone cell, all 30 real
photos: **TTFT 0.53–1.05 s (p50 0.67 s), encode 243–589 ms — and 9/30.**
Same score as the @1024 rung: below ~1344px input this model is fully
resolution-starved on our question set. LFM2-450M's fast operating point is
real (sub-second on a phone, CPU encoder and all) but answers scene-level
questions only. Resolution ladder now: 512→9, 1024→9, 1344→15, native→19 /30.

### Decoder-placement labeling: evidence classes (correction of method)

Encoder labels are ground truth (mtmd prints the unsupported-ops warning; its
absence = graph accepted on GPU). Decoder labels were rate-classified — not
good enough. Taxonomy now explicit: launch config < probe rate (CLASSIFIES,
order-of-magnitude gap) < **ngl ablation (CONFIRMS: -ngl 0 vs 99; if the flag
changes nothing, compute is CPU — buffer/log lines can't prove compute
placement because weights can sit in GPU buffers while ops run on CPU)**.
Suspicious probe rates are labeled "cpu? (probe N t/s — confirm by ngl
ablation)" until ablated.

**Q2_K ngl ablation result (phone, llama-bench):**

| | pp512 | tg16 |
|---|---|---|
| -ngl 99 | 31.5 t/s | **0.43 t/s** |
| -ngl 0 | 34.1 t/s | **29.98 t/s** |

Prefill identical → no OpenCL Q2_K kernels, CONFIRMED. And the twist: with
ngl 99 the weights sit in GPU buffers while ops run on CPU, so every decode
step round-trips data — **offloading Q2_K isn't just useless, it's 70×
destructive** (0.43 vs 30 t/s). Pure-CPU Q2_K actually decodes fine (30 t/s —
the CPU's repacked kernels like it); it's the ~34 t/s CPU prefill that kills
TTFT (~18 s @576). Also retro-explains the day-2 "pathological 0.4 t/s"
sightings: that number is the offloaded-but-unsupported signature. 26 Q2
ledger rows stamped with the ablation verdict.

### Sub-second head-to-head + champion low-token curve (phone, 30 photos, 2026-08-19)

Question: can Qwen match LFM2's 1-tile encode latency (~300 ms)? Answer: yes,
and it wins accuracy at every point.

| config | tok p50 | enc p50 | TTFT p50 | acc |
|---|---|---|---|---|
| LFM2-450M 1-tile | ~160–290 | ~0.30 s | 0.67 s | 9/30 |
| qwen3-2b-q4 @96 | 116 | 0.31 s | 0.82 s | 11/30 |
| qwen3-2b-q4 @128 | 146 | 0.39 s | 0.93 s | 12/30 |
| qwen3-2b-q4 @256 | 262 | 0.82 s | 1.70 s | 15/30 |
| qwen3-2b-q4 @576 (ref) | ~560 | 2.6 s | 4.1 s | 25/30 |

Law, final form: **TTFT = tokens × per-token cost(architecture, backend)** —
equal tokens equalize prefill only; encode price differs by tower (LFM2 86M:
~1.2 ms/tok even on CPU; Qwen: ~3.3 ms/tok on Adreno). Accuracy mechanism at
equal tokens = **pixels-per-token**: Qwen 3,136 px/tok full-frame vs LFM2
~800 px/tok in a 512-px tile → 4× more image per token → 15 vs 9 of 30.
Product: one model covers both tiers — fast @96–128 (sub-second serial),
reading @576+cache. Champion's phone token curve now: 96→11, 128→12, 256→15,
320→19, 576→25, 1024→26 (/30).

### LLM-as-judge rescoring pass (2026-08-19) + trio v2 + cached rows

Substring matching under-credits near-misses → all 457 negative verdicts
re-judged (Claude Fable 5 × 4 independent instances; rubric: same-fact
formatting/plural/spelling/separator → correct; ANY digit deviation → wrong;
success >0.5; positives kept). **44/457 flipped (~10%), zero digit errors
forgiven, ordering unchanged, cells +0–7 pts.** Audit:
results/llm_judge_rescores.jsonl · ledger carries correct + correct_judge.
Headlines (substring → judge): champion @576 phone 25→26/30; Q8 25→27; @1024
26→26 — **judged, @576 = @1024: the last resolution rung buys nothing**;
sub-second club: Qwen @96 12/30, @128 14/30 vs LFM2/Smol 1-tile 9/30 each
(champion's fast-tier lead widens); Mac ladder BF16/Q8/Q2 26/26/25, MXFP4 26.

Trio v2 (fixed CPU engine, judge-scored): qwen @128 14/30 · smol 1-tile 9/30 ·
lfm2 1-tile 9/30 — backend-invariance 3/3, CPU TTFTs now honest physics.
Cached warm-on-drop rows minted (ledger, full-res 12 MP uploads): perceived
1.52–2.60 s — day-3's 1.17–1.46 s figure ratified in class; the 0.25–0.44 s
tier remains the right-sized-capture variant.

### CPU-column anatomy (user-spotted): why same-variant TTFTs spread 2.5–11 s

The v2 CPU qwen @128 rows varied 2.5→10.9 s at identical imt/resolution. Three
stacked causes: (1) **the encoder wasn't on CPU** — `-ngl 0` moves decoder
layers only; the mmproj offloads to GPU by default (encodes 0.34–0.63 s = GPU
class, caught against the GPU cell's 391 ms p50). Engine now passes
`--no-mmproj-offload`; 60 mislabeled rows corrected. (2) **CPU prefill
collapses under sustained load**: 78→15 t/s within one cell (peaks 58–75 °C
between 4-query cool-gates) — at ~145 tokens that alone spans 1.9→9.6 s.
(3) **server-mode decode pathology reproduces on the healthy binary**:
0.3–0.4 t/s serving vs 45 t/s llama-bench on the same ocl -ngl 0 build — the
day-2 mystery is MODE-dependent (suspect: governor downclocks during
memory-stall-heavy decode in the serve loop; bench's tight loop keeps clocks
up). First token at 0.3 t/s adds ~3 s to TTFT — the other half of the spread.
Status: CPU decode pathology re-opened, precisely scoped (any build, server
mode, sustained). GPU path unaffected.

### Open items

- [x] Encoder A/B on phone: mtmd on OpenCL vs CPU — done (7.8 vs 22.6 s; and
      per-model op-gap map: LFM2 both sizes + Smol2.2B fall back, log-confirmed)
- [x] Phone CPU decode pathology: TWO distinct causes, one still open. (1) The
      0.4 t/s signature on "GPU" runs = offloaded-but-unsupported weight types
      (Q2_K ablation: ngl99 0.43 vs ngl0 30 t/s). (2) The tuned-CPU *build
      binary* has its own pathological decode — resurfaced in the CPU-only
      trio (smol500: 0.3–0.6 t/s, prefill 11–20 t/s, cpu/cpu labels, no GPU
      anywhere) while the *ocl build at -ngl 0* decodes ~30 t/s on the same
      silicon. Earlier "root-caused" claim was half right. FIX SHIPPED: the
      dashboard's phone-cpu engine now runs the ocl build with -ngl 0 (honest
      CPU physics); cpu-build root cause (suspect: KleidiAI repack path or
      -march=armv8.7 flags) documented open. Bench A/B landed: cpu build
      pp256 = 31.0 / tg32 = **0.45 t/s**; ocl build -ngl 0 = **59.1 / 45.1 t/s**
      — 100× decode defect + 1.9× prefill deficit, isolated on identical
      silicon. Healthy phone-CPU decode = 45 t/s (usable!). Trio
      re-run on the fixed engine.
- [x] Full ladder on phone with thermal protocol — done (Q4_0/Q8_0 25/30,
      Q2_K CPU-bound, BF16 probe, MXFP4 Metal-only)
- [x] Stress suite (Part 4) — done day 3
- [x] Eval-set validity checks — done (synthetic 92–100% vs real 47–87%)
- [ ] CPU-only fast-trio cells (qwen@128 / smol 1-tile / lfm2 1-tile) — running
- [ ] Camera re-shoots for eval set (user) + GT review of draft csv (user)
- [ ] QLoRA on Colab (user; script ready in notebooks/) — train at deployment
      budget 576; Part 5 write-up after
- [ ] AI Edge Gallery NPU test (user's own)
- [ ] Revoke the HF token exposed in session transcript (user)
