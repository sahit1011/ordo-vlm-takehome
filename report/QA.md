# Assignment Q&A — every question, answered with measurements

Questions quoted from [assignment.md](../assignment.md); answers link to the
evidence in [README](../README.md), [LAB_NOTES](LAB_NOTES.md), [JOURNEY](JOURNEY.md).

---

## Part 1 — Get a vision model onto a phone

**Q: Pick a small VLM (0.3B–4B) that publishes quantized weights. Tell us why you picked it.**
Started with Qwen2.5-VL-3B-Instruct (best OCR-class reader in range, official
multi-precision GGUFs, first-class llama.cpp support, dynamic-resolution ViT =
a controllable image-token knob). Mid-project, data dethroned it:
**Qwen3-VL-2B-Instruct** matched or beat it on accuracy while being 2× faster
on every stage and half the size — so the final pick is Qwen3-VL-2B Q4_0, and
the bracket ultimately covered five models (SmolVLM-500M, SmolVLM2-2.2B,
LFM2-VL-450M/1.6B measured too).

**Q: Which runtimes you tried, what failed, what you had to convert or patch.**
- **llama.cpp** (champion): three NDK builds (Adreno OpenCL / tuned CPU /
  portable armv8.2 compat). **Patched** `server-context.cpp` to expose
  per-request vision-encode time — it doesn't exist upstream and the
  assignment's stage separation is impossible without it.
- **MNN**: built from source for Android and macOS. First build silently
  dropped image input (missing `MNN_BUILD_OPENCV` → `<img>` tags no-op —
  the model hallucinated answers while blind; caught via its logcat stats
  showing `vision 0.00s / 0.00MP`). Fair rebuild: accurate text engine, best
  cold-start (7.5 s e2e), healthy CPU decode — but vision encode 5–6× slower
  than llama.cpp on both platforms and wrong on fine print at matched budgets.
- **LiteRT**: prebuilt CLI deployed by hand-building a **stub library**
  (their binary requires an undistributed `.so`; we generated its three
  symbols as no-ops with matching symbol-version). Text-only CLI; fastest
  model init measured (0.8 s for 3 GB); slowest compute (prefill 23 t/s,
  decode 7.3 t/s); GPU accelerator binaries not publicly distributed
  (4 channels checked); cannot run Qwen at all (Gemma-family lock-in).
- **Assessed with documented reasons, not integrated**: GenieX
  (Gradle-SDK-only, device list excludes SM8845), MediaPipe/AI Edge Gallery
  (per-SoC APK installs; its NPU stack ships inside the APK — the one
  remaining NPU door), ExecuTorch/QNN (weeks-scale export pipeline).
- **Conversions**: none needed for llama.cpp (full GGUF ladder published);
  MNN/LiteRT used their official model conversions.

**Q: Did anything reach the GPU or NPU, or was it all CPU?**
**GPU: yes — both stages, proven by ablation, not logs.** Vision encoder:
7.8 s on Adreno vs 22.6 s forced-CPU (`--no-mmproj-offload` A/B). Decoder
prefill: ~410 t/s GPU vs ~55 CPU. **NPU: no accessible path on this device**
— evidenced at every layer: no Hexagon HTP runtime libs in `/vendor/lib64`;
LiteRT accepts `--backend=npu` and loads QNN libs but the public model bundle
ships CPU/GPU graphs only (NPU needs per-SoC compiled bundles; none published
for Qualcomm); MNN's app exposes CPU/OpenCL only on this SoC; GenieX gates on
flagship chips. On Snapdragon today, the NPU is vendor-privileged.

**Q: How would a 1–2 GB model actually get onto a user's phone in a shipped app?**
Post-install download from a CDN (WorkManager: resumable, checksummed,
Wi-Fi-gated), or Play Asset Delivery (2 GB/pack) for install-time; iOS:
On-Demand Resources. Quantization is a distribution feature: our champion is a
1.0 GB download vs 5.8 GB for F16-3B. Measured transfer reality: ~10–20 MB/s
even on local Wi-Fi — a first-launch download UX is mandatory, not optional.

---

## Part 2 — Build the eval set

**Q: How the set was built; difficulty spread.**
Three tiers (synthetic 24-item pipeline set with controlled degradations and
exact auto-GT, 9/9/6 easy/med/hard; a 30-item real-photo set with per-item
provenance, human-verified GT, 17/10/3 spread; camera-shot final set pending —
shot list prepared with per-category difficulty recipes). Full detail README §2.
*Honest gap declared: 24/30 current real items are WhatsApp-sourced; the
assignment's own-photos rule requires camera replacements before submission.*

**Q: How would you know whether this eval set is any good?**
**By whether it discriminates — and we measured that.** The synthetic set
scored all models 92–100% (useless for ranking); the real set spread the same
models 47%→87% and exposed a +30-point synthetic inflation for small models.
Additional validity checks used: test-retest stability (repeat runs, temp 0),
cross-platform answer consistency (identical answers — including identical
wrong ones — on Metal and Adreno), difficulty-gradient sanity (easy > medium >
hard monotonic for the champion), and per-item auditability (every judgment
stored with the raw prediction; GT corrections re-score offline without
re-running).

---

## Part 3 — The quantization ladder

**Q: Accuracy metric — which and why.**
Normalized substring/alias match on short factual answers (with a uniform
brevity instruction), plus span-based ANLS as secondary. Ordo's task is
extracting one fact aloud: binary fact-presence matches the product, is
human-auditable per item, and avoids rewarding fluent near-misses. Two
scoring traps were found and fixed on the way (sentence-vs-span ANLS;
truncation of verbose models mis-scored as wrong).

**Q: The per-precision table.** README §4 carries the full table (size,
accuracy, prefill, decode per precision; encode measured separately via our
patch; peak RAM via VmHWM sampling with the GPU-buffer caveat; TTFT
client-measured). Headline: F16 5.75 GiB → Q4_0 1.70 GiB costs **one item in
24**; decode triples (20→61 t/s); prefill does not improve; **TTFT does not
improve** — encode+prefill own it.

**Q: Where does it break first? Pattern?**
**Handwriting, by salience retreat.** Q4/Q2 answer with the big legible
header ("Todo") instead of reading the harder handwritten lines beneath —
confidence collapse on the hardest glyph class, not gibberish. F16/Q8 read
them fine. Small models fail differently (dense-text extraction failure), and
token starvation fails differently again (confident hallucination of digits).

**Q: Which degrades faster — vision encoder or language decoder? How can you tell?**
**The decoder — and we can tell because the mmproj is a separate file, so we
quantized them independently.** All decoder-quant failures occurred with the
encoder held constant at F16; meanwhile encoder Q8 vs F16 produced zero
accuracy or answer differences across every model and platform (and on the
phone GPU, F16 encode is *slower* — bandwidth). The encoder both tolerates
quantization better and contributes less risk.

---

## Part 4 — Under stress

**Q: Sustained load — 20 consecutive queries.**
Ran 59. Decode settles 23→14–15 t/s by query 10, then **holds flat**; TTFT
equilibrium ~6.8 s (+65% vs cool). A plateau, not a spiral.

**Q: Thermals after ten minutes.**
SoC equilibrium 56–68 °C (peak 78) — soft landing, no hard-throttle collapse.
59/59 answers correct: **heat taxes speed, never accuracy.** (Worst case also
measured: a 95.8 °C phone delivers 0.4 t/s and a 685 s TTFT — thermal state is
a 10–40× lever, hence cool-gated protocol for all lab numbers.)

**Q: Memory pressure — heavy apps alongside.**
YouTube, Chrome, Instagram, Maps launched mid-run: **zero measurable impact**
— OpenCL-pinned buffers are immune to app eviction. (Converse finding: the
CPU path *is* vulnerable — page-cache eviction produced 0.4 t/s decode.)

**Q: Battery across those queries.**
3% across 64 queries ≈ **0.05%/query** (unplugged, screen on).

---

## Finally — LoRA

**Q: Does LoRA recover accuracy that quantization cost?**
Prepped, run pending (deferred by prioritization): QLoRA on the 4-bit
champion, decoder-side adapters (the decoder is what degrades), trained on
eval-style extraction pairs with **images pre-capped at the deployment
budget** — designed to test recovery of both the Q4 delta and the
token-budget losses. 192 disjoint synthetic training images +
`notebooks/qlora_qwen3vl_colab.py` ready; adapter applies on-device via
`--lora`.

---

## The "Few Points to Notice" teasers

**Q: Quantization halves the bytes. Does it halve the latency?**
No. Decode roughly follows bytes (bandwidth-bound); prefill is flat
(compute-bound); encode is untouched (separate file). **TTFT — what the user
feels — barely moves.** Quantization is a download/RAM/decode feature, not a
latency feature.

**Q: Why might a vision encoder tolerate quantization differently from a decoder?**
Empirically it tolerates it *better* here (mmproj Q8 = F16 everywhere).
Mechanistically: the encoder is a small fraction of total parameters (little
to gain), its errors would corrupt all downstream tokens (high risk — so
grateful they don't at Q8), while the decoder's language prior can absorb
small perturbations — until it can't: our data shows decoder quantization
failing first, as confidence collapse on hard glyphs.

**Q: A 500-token prompt and one image — which contributes more to TTFT?**
The image — overwhelmingly. Uncapped, one 12 MP photo is ~4,000 tokens (8× a
500-token prompt) plus the encode pass itself; even capped to 576, the image
is ~97% of TTFT (the ~15-token question costs ~40 ms). Image-token policy is
the #1 TTFT lever; the text prompt is a rounding error.

**Q: If the answer must be spoken, ASR and TTS want a slice of the two
seconds. What's left for the model, and does that change your recommendation?**
It *defines* the recommendation. Serially, nothing viable is left (~4 s model
TTFT alone). But the same speech that costs ASR time *gives* the vision
pipeline a hiding place: encode + image prefill run while the user is still
talking (two-phase caching, measured 1.17–1.46 s perceived TTFT, full
accuracy), so model-first-token lands within the budget and TTS starts on the
first phrase. The recommendation is therefore an architecture, not just a
model: **overlap vision with speech; route token budgets per query; ship
llama.cpp+Adreno where available and the compat CPU tier elsewhere.**
