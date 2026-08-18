# The journey — decisions, pivots, and dead ends

Companion to [LAB_NOTES.md](LAB_NOTES.md) (findings) and the [README](../README.md)
(final report). This is the chronological record of *how* we got there and *why*
each fork was taken. Dates are 2026-08.

---

## Day 1 (08-18 morning) — framing and scaffolding

**Decision: treat this as a measurement-engineering exercise, not a porting
exercise.** The brief tips its hand ("separating encode/prefill/decode is most
of what this exercise is about"). Everything downstream — the patched server,
the per-stage JSONL logging, the thermal gates — follows from this call.

**Decision: Qwen2.5-VL-3B-Instruct as primary model.** Reasons at the time:
best OCR-class reader in 0.3–4 B, official multi-precision GGUFs (the whole
ladder prebuilt — zero conversion work), first-class llama.cpp support, and a
dynamic-resolution ViT giving a controllable image-token knob. (Later partially
superseded by Qwen3-VL-2B — see Day 3 — which is the healthy outcome of
keeping the bracket open.)

**Decision: llama.cpp as backbone runtime.** Only runtime giving every quant
level plus separable stage timings. Alternatives noted for later: MLC, LiteRT,
QNN.

**Pivot: NDK cross-compile + `/data/local/tmp`, not Termux.** Termux was the
plan on paper; switched because adb-driven binaries are fully scriptable from
the laptop (no on-phone interaction), which the whole harness then relied on.

**Dead end #1: Homebrew.** Owned by another user, needs sudo. Routed around:
adb from Google's zip, cmake via pip. Lesson: assume no admin rights anywhere.

**Environment quirks that cost real time:** the user's shell aliases `cp` to
another tool (scripts must use `/bin/cp`); the NDK dmg mounts at a path with
spaces; `--log-verbosity 1` silences llama-server entirely.

## Day 1 (afternoon) — the measurement traps

Validated the entire pipeline on the Mac *before* touching the phone — the
single best process decision of the project. It surfaced four traps that would
have silently corrupted every later number:

1. Prompt caching fakes TTFT on repeats → `cache_prompt: false` for measurement
   (and — beautifully — the same flag became the *product* answer on Day 3).
2. llama-server has **no** vision-encode timing → patched
   `server-context.cpp` to log it. Assignment asked "what did you patch": this.
3. The server's "prefill" secretly includes encode → decomposed in analysis.
4. ANLS scored sentences against short ground truths → span-based scorer.

**Decision: the encoder axis is experimental, not rhetorical.** Because mmproj
is a separate file, encoder and decoder quantize independently → 2D matrix
instead of hand-waving about "which degrades faster".

## Day 2 — the phone fights back

**Wireless adb saga:** sandbox kept killing the adb daemon (persistent
background server fixed it); pairing dialog timing; and the classic:
`adb shell "nohup … &"` never returns even with all streams redirected —
launch-and-health-gate instead of waiting.

**The thermal education, in three acts:**
1. First on-device run: decode 0.4 tok/s at 95.8 °C — measured a *hot* phone,
   not the model (TTFT 685 s on a 12 MP photo).
2. "Awake" rerun still broken → clock logs showed cores pinned at ~50%:
   self-inflicted (`set-fixed-performance-mode` means *sustained* mode = capped
   clocks). Undone.
3. Fake sensors: `cpu-hw-trip-*` zones read a constant 95 °C and polluted every
   peak-temp sample until excluded. Every benchmark thereafter runs behind a
   real-sensor cool-gate.

**Decision: measure image tokens, not trust flags.** The 12 MP photo exploded
to 4,043 tokens uncapped; `--image-max-tokens 576` became the working point.
Later learned LFM2 interprets the same flag per-tile — nominal caps are not
comparable across architectures; only measured `prompt_n` is.

**GPU milestone:** OpenCL/Adreno worked — decoder *and* encoder (proven by
`--no-mmproj-offload` A/B: 7.8 s vs 22.6 s). One linker landmine: exporting
`LD_LIBRARY_PATH=/vendor/lib64` shell-wide breaks `nohup`; scope it with `env`.

**Cut: CPU decode pathology root-cause.** Decode stayed 0.4–1.8 tok/s on CPU
even cool/awake/no-mmap while prefill was healthy. Timeboxed out once the GPU
proved stable (18.5 tok/s) — documented as open question rather than sunk cost.

**Cut: NPU integration (initially).** Assessed as out of timebox; downgraded to
a written analysis — then partially reversed on Day 3 when GenieX (open-source,
OpenAI-compatible) surfaced and made a timeboxed attempt rational.

**Decision: build the dashboard.** Turned the pile of scripts into an
instrument anyone can drive (connect phone → pick model/runtime/tokens → drop
photo → live meters, stage waterfall, history). Also forced honest plumbing:
every run lands in one JSONL regardless of who triggered it.

## Day 2–3 — the model bracket earns its keep

**SmolVLM (500M/2.2B):** 500M is fast and can't read labels (wrong tier);
2.2B reads tiny text only via 7.8k-token brute force. At equal budget, Qwen
wins — "smaller model" costs more accuracy than quantization ever did.

**LFM2-VL-1.6B:** Mac star (CPU ≈ GPU decode, 0.6 s TTFT easy scenes); phone
flop — its encoder is 4× slower per token on Adreno and worse on phone CPU.
Encoder speed is a property of model×runtime×silicon, not of the model.

**Resolution axis:** pre-downscaling loses accuracy faster than model-side
capping (dynamic-res pipelines downsample smarter than we do).

**Protocol v2:** Qwen3-VL's verbosity exposed a truncation confound — scored
wrong while knowing the answer. Fix: brevity instruction (product-realistic
for voice) + higher token ceiling. Retroactively re-ran affected configs.

**Qwen3-VL-2B takes the crown (Day 3):** under v2, 3/3 at native res (only
model to read "Watermelon Wave" exactly); at @576 on the phone it beats
Qwen2.5-3B on *every* axis (TTFT 5.2 vs 7.5 s, prefill 2×, decode +40%,
cooler) with equal accuracy. Cross-platform determinism observed: identical
answers — including the same wrong one — on Metal and Adreno.

## Day 3 — the 1-second question

External pressure (user + an advice table quoting NPU-class targets) forced
the question: why is TTFT 5 s? Decomposition said encoder 61% → three routes:

1. **NPU** — the advice table's implicit stack. Discovery: Qualcomm's GenieX
   (open-source, GGUF VLMs on Hexagon/GPU/CPU, OpenAI-compatible server) makes
   this a plug-in candidate for our harness. Timeboxed for integration.
2. **Smaller budgets** — measured: breaks fine print. Rejected as a global
   setting; viable per-query (routing/ROI).
3. **Architecture** — the winner. The camera sees the scene before the user
   finishes speaking → two-phase flow (warm the KV cache during speech via
   `cache_prompt`, then the question hits a cache with only text left to
   prefill). Measured perceived TTFT: **1.17–1.46 s full-accuracy, 0.25–0.37 s
   right-sized** — versus 8.8 s serial. The flag we disabled for honest
   measurement became the product feature.

**The resolution knife-edge (final Day-3 finding):** server-side resize from
12 MP → 564 tokens reads "120"; our own resize to ~540 tokens reads "10".
A 4% pixel difference flips the smallest digits — even patch-aligned Lanczos
didn't save it (double resampling). The robust config uploads full-res during
the hidden phase and pays ~1.3 s; the fast config is for big-text queries.

**Recommendation shape this journey converges on:** Qwen3-VL-2B Q4_0 + Q8
encoder + @576 + Adreno GPU + two-phase caching; two-tier token budgets per
query class; NPU (GenieX) as the lever that could collapse the serial path;
LoRA to claw back capped-budget accuracy. Final validation gated on the
32-photo eval set.

## Day 3 (late) — the requirements triangle and the runtime hunt

**The user set the final bar**: <1 s (ideally <500 ms) including encode, no
accuracy compromise, device-agnostic. Our analysis: that's a pick-two triangle
on today's silicon. Response was three-pronged: squeeze the GPU serial path
(closed — knobs don't move it; F16 encoder falsified at 1.9× slower), keep the
caching architecture (meets the bar as *perceived* latency), and hunt a
second runtime for the serial encoder.

**Resize falsification trilogy.** Three attempts to make phase-B uploads cheap
by client-side resizing (1344 px, patch-aligned Lanczos, 2016 px rich
intermediate) all destroyed knife-edge digits that server-side resize from the
same original preserves at the same token count. Conclusion: never resample
twice; the fast tier is for big-text queries only. Negative results, fully
banked.

**The bracket grew to five on user request** (+ a <1B slot). Real photos
arrived (user's "ordo-dataset" album: 30 items — flagged honestly: 24 are
WhatsApp-sourced, provenance-labeled; camera replacements requested). The
real set **discriminated what synthetics couldn't**: 47→87% spread vs
92–100% compression — the eval-validity finding of the project. The 450M's
synthetic heroics collapsed on real photos (+30 pt inflation); the champion
held (26/30).

**Runtime scouting, honestly:** GenieX = SDK-only, device-list excludes our
chip → docs-only. LiteRT = can't run Qwen3-VL at all. AI Edge Gallery = per-SoC
APK installs, Gemma datapoint pending. MNN Chat app = the real find: healthy
CPU decode where llama.cpp's is broken, OpenCL ≈ tie with our stack, and **no
NPU option exposed on SM8845** — closing every zero-integration NPU door. So
the encoder wall (~2.5 s serial) is now evidenced across two engines × five
backends. Next: MNN CLI cross-compiled into our own dashboard (their engine
has an unexposed QNN plugin flag — one experiment left).

**Process evolution under fire:** a hit API image ceiling turned all visual
work (GT drafting for 30 photos, app UI driving, screenshot reading) into
subagent delegations — which worked well enough to become the standing
pattern. Ops: wireless adb drops mid-chain, benchmark apps parking gigabytes
(MNN held 2.4 GB after use), fake-sensor #3 (`socd` = battery %, not 57 °C).

**Deliberate deferral:** LoRA parked by user decision to concentrate on the
runtime × encode frontier. Part 4 closed with the day's best sentence:
sustained load costs a stable 40% throughput tax and zero accuracy.

## Standing process rules (earned, not assumed)

- Validate the whole pipeline on the dev box before the device.
- Never benchmark a phone without a real-sensor cool-gate; report steady-state
  (first query carries ~3 s OpenCL warmup).
- Never trust a nominal knob (caps, flags) — record what the system actually
  did (`prompt_n`, logs).
- Every surprising number gets an attribution experiment (A/B) before a story.
- Write down the wrong answers verbatim — failure modes carry more information
  than accuracy percentages.
