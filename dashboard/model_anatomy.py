"""Model anatomy: parse the loaded GGUF pair and describe the computation
graph — real metadata (layers/dims/heads/quant mix per tensor) plus the
MEASURED per-backend op coverage from this project's evidence, so the graph
shows where each stage actually executes per engine."""

import pathlib
import sys
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path.home() / "Desktop/llama.cpp/gguf-py"))
from gguf import GGUFReader  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
_CACHE: dict = {}

# measured coverage (this project's evidence: launch-log scans, probes, ngl ablations)
OCL_WEIGHT_OK = {"F32", "F16", "BF16", "Q4_0", "Q8_0", "Q4_K", "Q6_K", "Q5_0"}
OCL_WEIGHT_BAD = {"Q2_K", "Q3_K", "MXFP4"}          # ablation/probe-confirmed CPU fallback
OCL_CLIP_BAD_ARCH = {"lfm2", "smolvlm2"}             # CLIP graph op-gap (log-confirmed)


def _val(r, key):
    f = r.fields.get(key)
    if f is None:
        return None
    v = f.parts[f.data[0]]
    try:
        if hasattr(v, "tobytes") and f.types and f.types[-1].name == "STRING":
            return v.tobytes().decode()
        return v.tolist()[0] if hasattr(v, "tolist") else v
    except Exception:
        return None


def _types(reader):
    agg = defaultdict(lambda: [0, 0])
    for t in reader.tensors:
        a = agg[t.tensor_type.name]
        a[0] += 1
        a[1] += int(t.n_bytes)
    return [{"type": k, "count": c, "mb": round(b / 1e6)}
            for k, (c, b) in sorted(agg.items(), key=lambda kv: -kv[1][1])]


def anatomy(config: str, cfg: dict, engine: str) -> dict:
    key = (config, engine)
    if key in _CACHE:
        return _CACHE[key]
    mp, pp = ROOT / "models" / cfg["model"], ROOT / "models" / cfg["mmproj"]
    r = GGUFReader(str(mp))
    arch = _val(r, "general.architecture") or "?"
    g = lambda k: _val(r, f"{arch}.{k}")
    rp = GGUFReader(str(pp))
    v = lambda k: _val(rp, f"clip.vision.{k}")

    types = _types(r)
    dec_bad = [t["type"] for t in types
               if t["type"] in OCL_WEIGHT_BAD] if engine.startswith("phone") else []
    clip_gap = any(a in (cfg["model"].lower() + cfg["mmproj"].lower()) for a in OCL_CLIP_BAD_ARCH)
    if engine == "mac":
        enc_bk = dec_bk = "metal"
    elif engine == "phone-cpu":
        enc_bk = dec_bk = "cpu"
    else:
        enc_bk = "cpu (op gap)" if clip_gap else "adreno-ocl"
        dec_bk = f"cpu-fallback (no OpenCL kernels: {','.join(dec_bad)})" if dec_bad else "adreno-ocl"

    out = {
        "config": config, "engine": engine, "arch": arch,
        "model_file": cfg["model"], "model_mb": round(mp.stat().st_size / 1e6),
        "mmproj_file": cfg["mmproj"], "mmproj_mb": round(pp.stat().st_size / 1e6),
        "n_layer": g("block_count"), "n_embd": g("embedding_length"),
        "n_head": g("attention.head_count"), "n_head_kv": g("attention.head_count_kv"),
        "n_ff": g("feed_forward_length"), "n_ctx_train": g("context_length"),
        "vocab": _val(r, "tokenizer.ggml.model") and len(r.fields.get("tokenizer.ggml.tokens").data or []),
        "types": types, "mm_types": _types(rp),
        "vision": {"image_size": v("image_size"), "patch": v("patch_size"),
                   "blocks": v("block_count"), "embd": v("embedding_length")},
        "enc_backend": enc_bk, "dec_backend": dec_bk,
        "fa": "unsupported for this graph (log)" if clip_gap and engine == "phone-gpu"
              else ("supported, +6% pp / +10% tg (measured)" if engine == "phone-gpu" else "on by default"),
    }
    _CACHE[key] = out
    return out
