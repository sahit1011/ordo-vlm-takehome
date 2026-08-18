# Ordo take-home — a vision model on a phone

Qwen2.5-VL-3B-Instruct running on a OnePlus 15R (12 GB) via llama.cpp,
measured across a quantization ladder against a self-shot 32-photo
text-in-the-wild eval set.

> **Status: in progress.** Sections fill in as results land.

## 1. Getting it running

**Path that worked:** llama.cpp cross-compiled with the Android NDK (r27c,
arm64, `-march=armv8.7-a+i8mm+dotprod`, KleidiAI on), binaries run directly
from `/data/local/tmp` over wireless adb — no app, no Termux, fully
scriptable from the laptop. `llama-server` on the phone + a Python harness
on the laptop over an adb-forwarded port.

**What we had to patch:** `llama-server` does not expose the vision-encoder
pass as a separate timing anywhere — and separating encode from prefill is
the core of this exercise. We patched `tools/server/server-context.cpp` to
log per-request image-encode duration around `mtmd_batch_encode()`.

**Measurement traps found and fixed** (each would have silently corrupted
results):
1. **Prompt caching**: llama-server reuses cached image tokens across
   queries on the same image — repeat measurements showed 0.08 s TTFT
   instead of 2.1 s. Fixed with `cache_prompt: false` per request.
2. **"Prefill" includes encode** in the server's reported timings; true
   prefill = `prompt_ms − encode_ms`, decomposed in our summarizer.
3. **`adb shell "nohup … &"` never returns** on modern adbd even with all
   three streams redirected — the harness must launch without waiting and
   gate on the HTTP health check instead.
4. **Thermal contamination**: a hot phone (95.8 °C SoC observed) throttles
   decode from ~double-digit tok/s to 0.4 tok/s. Every benchmark now waits
   behind a battery-temperature cool-gate.

**GPU/NPU status:** OpenCL (Adreno) backend cross-compiled; vendor driver
confirmed present on the OnePlus 15R (`/vendor/lib64/libOpenCL_adreno.so`);
on-device results pending. NPU (Hexagon/QNN) assessed as out of timebox —
requires the QNN SDK toolchain and model re-export; discussed in §6.

**How would a 1–2 GB model ship to users?** Not inside the APK (Play Store
caps and update amplification). The standard pattern: post-install download
from a CDN via WorkManager — resumable, checksummed, Wi-Fi-gated, with
Play Asset Delivery (2 GB/pack) as an alternative for install-time
delivery. iOS equivalents: On-Demand Resources or post-install download.
Quantization is also a distribution lever: Q4 (1.8 GB) vs F16 (5.8 GB) is
the difference between a plausible and an abusive first-launch download.

## 2. The eval set
_32 own photos, 9 categories, difficulty spread 13 easy / 11 medium / 8 hard.
Protocol in [eval/SHOT_LIST.md](eval/SHOT_LIST.md). Validity checks: ceiling
test, discrimination test, test-retest._

## 3. Setup & reproduction

- Model: Qwen2.5-VL-3B-Instruct (GGUF, ggml-org + unsloth quants)
- Runtime: llama.cpp (`llama-server` + mmproj), CPU on-device
- Device: OnePlus 15R, 12 GB RAM; laptop: MacBook (M3 Pro) as harness driver
- Reproduce: `scripts/` in order — `setup_ndk.sh`, `build_android.sh`,
  `connect_phone.sh`, `push_to_phone.sh`, then `python harness/run_eval.py`

## 4. Results

| Precision | Size | Accuracy | Peak RAM | Encode ms | Prefill tok/s | Decode tok/s | TTFT |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F16 |  |  |  |  |  |  |  |
| Q8_0 |  |  |  |  |  |  |  |
| Q4_K_M |  |  |  |  |  |  |  |
| Q2_K |  |  |  |  |  |  |  |

_Encoder-axis matrix (mmproj F16 vs Q8_0) reported separately._

## 5. Where it breaks
_Which photos fail at Q4 that pass at F16; the pattern._

## 6. Recommendation
_The config we'd ship and why, framed against a ~2 s conversational budget
with ASR + TTS taking their slice._

## 7. What surprised us

## 8. What we cut, and why

## 9. Under stress
_20-query sustained run, 10-minute thermal soak, memory pressure, battery._

## 10. LoRA
_QLoRA on Colab over a disjoint self-shot training set; accuracy recovery
at Q4._
