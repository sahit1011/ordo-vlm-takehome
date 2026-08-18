# %% [markdown]
# # QLoRA fine-tune — Qwen3-VL-2B on eval-style extraction data (Colab, T4/A100)
#
# Assignment: "LoRA fine-tune the quantized model on examples in the style of
# your eval task. Does it recover accuracy quantization cost?"
#
# Plan: QLoRA (4-bit base = the quantized model) on synthetic + real photo QA
# pairs, **images pre-capped at the deployment budget (576 tokens)** so the
# model adapts to the resolution it will actually see on-device.
#
# Prepare locally, then upload to Colab:
#   cd ~/Desktop/Ordo-a && zip -r train_data.zip eval/train_synth eval/train_synth_gt.csv eval/train_photos
#
# Export at the end: LoRA adapter -> GGUF via llama.cpp for on-device use.

# %%
# 1) Install (Colab)
!pip install -q unsloth
# fallback if unsloth lacks Qwen3-VL in this release: pip install -q -U transformers peft trl bitsandbytes

# %%
# 2) Load 4-bit base — champion model. If Qwen3-VL unsupported by this unsloth
#    build, switch MODEL to "unsloth/Qwen2.5-VL-3B-Instruct-bnb-4bit" (measured
#    accuracy delta between the two is small at 576 tokens).
from unsloth import FastVisionModel
import torch

MODEL = "unsloth/Qwen3-VL-2B-Instruct"   # 4-bit via load_in_4bit
model, tokenizer = FastVisionModel.from_pretrained(
    MODEL, load_in_4bit=True, use_gradient_checkpointing="unsloth")

model = FastVisionModel.get_peft_model(
    model,
    finetune_vision_layers=False,     # decoder-side adaptation (encoder frozen —
    finetune_language_layers=True,    # our data showed decoder degrades first)
    finetune_attention_modules=True,
    finetune_mlp_modules=True,
    r=16, lora_alpha=16, lora_dropout=0, bias="none", random_state=42)

# %%
# 3) Dataset: (image, question, brief answer) -> chat format.
#    Images resized to the deployment budget before training.
import csv, io, zipfile, math
from PIL import Image

with zipfile.ZipFile("train_data.zip") as z:
    z.extractall(".")

def cap_resize(im, budget_patches=2304, patch=28):
    w, h = im.size
    scale = math.sqrt(budget_patches * patch * patch / (w * h))
    if scale < 1:
        im = im.resize((int(w*scale)//patch*patch, int(h*scale)//patch*patch), Image.LANCZOS)
    return im

BRIEF = " Answer briefly with just the fact."
samples = []
for row in csv.DictReader(open("eval/train_synth_gt.csv")):
    img = cap_resize(Image.open("eval/" + row["file"]).convert("RGB"))
    samples.append({"messages": [
        {"role": "user", "content": [
            {"type": "image", "image": img},
            {"type": "text", "text": row["question"] + BRIEF}]},
        {"role": "assistant", "content": [{"type": "text", "text": row["answer"]}]},
    ]})
print(len(samples), "training samples")

# %%
# 4) Train
from unsloth.trainer import UnslothVisionDataCollator
from trl import SFTTrainer, SFTConfig

FastVisionModel.for_training(model)
trainer = SFTTrainer(
    model=model, tokenizer=tokenizer,
    data_collator=UnslothVisionDataCollator(model, tokenizer),
    train_dataset=samples,
    args=SFTConfig(
        per_device_train_batch_size=1, gradient_accumulation_steps=8,
        num_train_epochs=2, learning_rate=2e-4, warmup_ratio=0.05,
        logging_steps=5, output_dir="qlora_out", optim="adamw_8bit",
        lr_scheduler_type="cosine", seed=42,
        remove_unused_columns=False, dataset_text_field="",
        dataset_kwargs={"skip_prepare_dataset": True}, max_seq_length=2048),
)
trainer.train()

# %%
# 5) Export adapter -> GGUF for llama.cpp on the phone
model.save_pretrained("lora_adapter")
tokenizer.save_pretrained("lora_adapter")
!git clone --depth 1 https://github.com/ggml-org/llama.cpp
!pip install -q gguf
!python llama.cpp/convert_lora_to_gguf.py lora_adapter --outfile qwen3vl2b-ocr-lora.gguf
# download qwen3vl2b-ocr-lora.gguf, then on the phone:
#   llama-server ... --lora qwen3vl2b-ocr-lora.gguf
from google.colab import files
files.download("qwen3vl2b-ocr-lora.gguf")
