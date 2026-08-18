# Ordo - Take-Home: A Vision Model on a Phone

---

## Why we're asking

Ordo has a camera at ear level. The model has to look at what you're looking at and answer about it - running on the device, inside a conversational time budget

Every one of those constraints costs accuracy. This exercise is about measuring exactly how much, on real hardware, and then deciding what you'd actually ship.

**There is no target number to hit.** We care about how you build the measurement, what you notice, and how you defend the call you make at the end. 

Disclaimer :- Using tools like claude and Codex is a plus plus to fasten up the process and reduce the TAT.

---

# Part 1 - Get a vision model onto a phone

Pick a small vision-language model that publishes quantized weights - **Qwen-VL, SmolVLM, Moondream, PaliGemma, Gemma multimodal, LFM2-VL** - in the **0.3B–4B** range. Tell us why you picked it.

Get it running **on a phone**. Android preferred; iPhone is fine. Runtime is your choice - llama.cpp, MLX, MediaPipe, LiteRT, MLC, whatever gets you there.

**Report what it took.** Which runtimes you tried, what failed, what you had to convert or patch. 

Also tell us:

- Did anything reach the GPU or NPU, or was it all CPU?
- How would a 1–2 GB model actually get onto a user's phone in a shipped app?

---

# Part 2 - Build the eval set

Before measuring anything, you need something trustworthy to measure against.

**Take 25–40 photos yourself.** Phone camera is fine. Each should contain text in the real world that someone might reasonably ask about out loud:

restaurant menus · product labels · street signs · handwritten notes · receipts · medicine packaging · book spines · a whiteboard · an appliance display

For each, write the **question you'd ask** and the **ground truth** answer.

Two things matter here:

- **Your own photos only.** No public benchmark - we want to be certain the model hasn't seen them.
- Some easy, some genuinely hard: bad light, sharp angle, glare, small text, partial occlusion. Tell us how you chose the spread and roughly how many land in each bucket.

Then: **how would you know whether this eval set is any good?**

---

# Part 3 - Run the quantization ladder

Run the model against your eval set at **at least three precisions** - for example FP16, Q8, Q4, and Q2 if you can get it.

### Measure, per precision

| Metric | Notes |
| --- | --- |
| **Accuracy** on your eval set | Tell us which metric you chose, and why |
| **Model size on disk** |  |
| **Peak RAM during inference** |  |
| **Image encode time** | The vision encoder pass, on its own |
| **Prefill throughput** | Image tokens + prompt through the decoder |
| **Decode throughput** | Generation, tok/s |
| **Time to first token** | What the user actually feels |

**Report image encoding, prefill and decode as three separate numbers.** They behave differently and scale differently, and separating them is most of what this exercise is about.

### And tell us

- **Where does it break first?** Which photos fail at Q4 that passed at FP16 - and is there a pattern?
- Which degrades faster - the vision encoder or the language decoder? How can you tell?

---

# Part 4 - Under stress

Pick your best-looking configuration and push it:

1. **Sustained load** - 20 consecutive queries. Does throughput hold, or fall away?
2. **Thermals** - what happens to the phone, and to your numbers, after ten minutes?
3. **Memory pressure** - several heavy apps open alongside
4. **Battery** - drain across those 20 queries

---

# Finally

---

Take the quantized model and **LoRA fine-tune it** on examples in the style of your eval task. Does it recover any of the accuracy quantization cost you?

---

# What to send back

3–5 pages, or a repo with a README. Cover:

1. **Getting it running** - what worked, what didn't, what you had to build
2. **The eval set** - how you built it, difficulty spread.
3. **Setup** - model, runtime, device, how to reproduce
4. **Results** - a table is fine

| Precision | Size | Accuracy | Peak RAM | Encode ms | Prefill tok/s | Decode tok/s | TTFT |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |
1. **Where it breaks** - the failure pattern, with example images if useful
2. **Your recommendation** - and the reasoning behind it
3. **What surprised you** ← the section I'll read first
4. **What you cut, and why** - plus anything you couldn't get working

---

## Few Points to Notice

- Quantization halves the bytes. Does it halve the latency? Which stage benefits most, and which barely moves?
- Why might a vision encoder tolerate quantization differently from a language decoder?
- A 500-token prompt and one image. Which contributes more to time-to-first-token?
- If the answer has to be spoken, ASR and TTS also want a slice of those two seconds. What's left for the model, and does that change your recommendation?