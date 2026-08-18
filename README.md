# Ordo take-home — a vision model on a phone

Qwen2.5-VL-3B-Instruct running on a OnePlus 15R (12 GB) via llama.cpp,
measured across a quantization ladder against a self-shot 32-photo
text-in-the-wild eval set.

> **Status: in progress.** Sections fill in as results land.

## 1. Getting it running
_What worked, what didn't, what had to be built. GPU/NPU attempts and
outcomes. How a 1–2 GB model would ship to users' phones._

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
