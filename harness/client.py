"""Client for llama-server's OpenAI-compatible endpoint.

Measures TTFT client-side via streaming, and collects llama-server's own
timing breakdown (prompt_ms / predicted_ms and per-second rates) from the
final response payload. Image-encode time is parsed separately from the
server log by run_eval.py, since the server reports it there, not in the API.
"""

import base64
import json
import time

import requests


def image_data_url(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}[ext]
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def wait_ready(server: str, timeout_s: float = 900.0) -> None:
    """Block until the server has loaded the model (503 until then)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if requests.get(f"{server}/health", timeout=5).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError(f"llama-server at {server} not ready after {timeout_s}s")


def query(server: str, image_path: str, question: str,
          max_tokens: int = 64, timeout: float = 1200.0) -> dict:
    """One image+question round trip. Returns text, client TTFT, and server timings."""
    payload = {
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_data_url(image_path)}},
                {"type": "text", "text": question},
            ],
        }],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "seed": 42,
        "stream": True,
        "timings_per_token": True,
        # measurement integrity: without this, repeat queries on the same image
        # reuse cached vision tokens and report near-zero TTFT/prefill
        "cache_prompt": False,
    }

    t_start = time.monotonic()
    t_first = None
    chunks: list[str] = []
    timings: dict = {}

    with requests.post(f"{server}/v1/chat/completions", json=payload,
                       stream=True, timeout=timeout) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line or not line.startswith(b"data: "):
                continue
            data = line[len(b"data: "):]
            if data == b"[DONE]":
                break
            obj = json.loads(data)
            if "timings" in obj:
                timings = obj["timings"]
            delta = obj.get("choices", [{}])[0].get("delta", {})
            piece = delta.get("content")
            if piece:
                if t_first is None:
                    t_first = time.monotonic()
                chunks.append(piece)
    t_end = time.monotonic()

    return {
        "text": "".join(chunks).strip(),
        "ttft_client_s": (t_first - t_start) if t_first else None,
        "total_s": t_end - t_start,
        # server-side breakdown (n_prompt/n_predicted counts + ms + tok/s rates)
        "timings": timings,
    }
