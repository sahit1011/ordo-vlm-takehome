"""Ordo Bench — local dashboard for on-phone VLM benchmarking.

FastAPI backend on the laptop: manages the phone connection and llama-server
lifecycle (phone CPU / phone GPU / mac), proxies image+question queries,
samples device stats during inference, and serves the accumulated results.

Run:  python3 dashboard/app.py   →  http://localhost:8090
"""

import json
import pathlib
import re
import subprocess
import sys
import threading
import time

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import requests
import uvicorn

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
import client as llm            # noqa: E402
import metrics                  # noqa: E402
from run_eval import CONFIGS    # noqa: E402
import score                    # noqa: E402

PHONE_DIR = "/data/local/tmp/ordo"
PHONE_PORT = 8080
LOCAL_PORT = 18080
MAC_PORT = 8080
MAC_BIN = pathlib.Path.home() / "Desktop/llama.cpp/build/bin/llama-server"
RUNS_FILE = ROOT / "results/dashboard_runs.jsonl"
UPLOADS = ROOT / "results/raw/uploads"
ENCODE_RE = re.compile(r"(?:image|slice).{0,40}?(?:encod|process)\w*\s+in\s+(\d+)\s*ms", re.I)

ENGINES = {
    "phone-gpu": {"dir": "ocl", "ld": f"{PHONE_DIR}/ocl:/vendor/lib64", "ngl": "99",
                  "runtime": "llama.cpp", "device": "Adreno GPU (OpenCL)", "available": True},
    "phone-cpu": {"dir": "cpu", "ld": f"{PHONE_DIR}/cpu", "ngl": None,
                  "runtime": "llama.cpp", "device": "CPU (i8mm/KleidiAI)", "available": True},
    "phone-compat": {"dir": "compat", "ld": f"{PHONE_DIR}/compat", "ngl": None,
                     "runtime": "llama.cpp", "device": "CPU portable (any arm64 Android 8+)", "available": True},
    "mac":       {"runtime": "llama.cpp", "device": "M3 Pro Metal (dev ref)", "available": True},
    # roadmap runtimes — selectable once integrated; kept visible so the run
    # matrix shows what a full runtime comparison would cover
    "litert-npu":  {"runtime": "LiteRT/MediaPipe", "device": "GPU/NPU (Gemma-class)", "available": False},
    "qnn-genie":   {"runtime": "Qualcomm Genie", "device": "Hexagon NPU", "available": False},
}

app = FastAPI()
state = {"engine": None, "config": None, "imt": None, "threads": None,
         "mac_proc": None, "log_offset": 0, "load_s": None, "ready": False}
lock = threading.Lock()


def ensure_serial():
    """Pin ANDROID_SERIAL so multi-transport (TCP + mDNS) doesn't break adb."""
    import os
    if os.environ.get("ANDROID_SERIAL"):
        return
    out = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=10).stdout
    serials = [l.split("\t")[0] for l in out.splitlines()[1:] if "\tdevice" in l]
    # prefer the plain ip:port transport over the mDNS name
    serials.sort(key=lambda s: 0 if ":" in s and "_" not in s else 1)
    if serials:
        os.environ["ANDROID_SERIAL"] = serials[0]


def adb(*args, timeout=25):
    ensure_serial()
    return subprocess.run(["adb", *args], capture_output=True, text=True, timeout=timeout)


def adb_out(*args, timeout=25) -> str:
    return adb(*args, timeout=timeout).stdout.strip()


def phone_connected() -> bool:
    return any(l.strip().endswith("device") or "\tdevice" in l
               for l in adb_out("devices").splitlines()[1:])


def read_server_log() -> str:
    if state["engine"] == "mac":
        p = ROOT / "results/raw/server_dash.log"
        return p.read_text(errors="replace") if p.exists() else ""
    return adb_out("shell", "cat", f"{PHONE_DIR}/server.log")


def encode_ms_since_last():
    log = read_server_log()
    new = log[state["log_offset"]:]
    state["log_offset"] = len(log)
    hits = [int(m) for m in ENCODE_RE.findall(new)]
    return sum(hits) if hits else None


def stop_server(sweep_mac: bool = False):
    if state.get("mac_proc"):
        state["mac_proc"].terminate()
        try:
            state["mac_proc"].wait(timeout=15)
        except subprocess.TimeoutExpired:
            state["mac_proc"].kill()
        state["mac_proc"] = None
    if sweep_mac:
        # sweep mac llama-servers orphaned by a previous app instance — ONLY
        # when we're about to bind the mac port ourselves; otherwise this
        # kills harness-owned local servers (it did — see lab notes)
        subprocess.run(["pkill", "-f", "build/bin/llama-server"], capture_output=True)
    if phone_connected():
        adb("shell", "pkill", "llama-server")
    state.update(ready=False, engine=None, config=None, load_s=None)


@app.get("/")
def index():
    return FileResponse(pathlib.Path(__file__).parent / "static/index.html")


@app.get("/api/configs")
def configs():
    out = []
    for name, cfg in CONFIGS.items():
        f = ROOT / "models" / cfg["model"]
        out.append({"name": name, "model": cfg["model"], "mmproj": cfg["mmproj"],
                    "size_gb": round(f.stat().st_size / 1e9, 2) if f.exists() else None})
    return {"configs": out,
            "engines": [{"name": k, "runtime": v.get("runtime"), "device": v.get("device"),
                         "available": v.get("available", False)} for k, v in ENGINES.items()],
            "imt_options": [0, 256, 576, 1024]}


@app.get("/api/phone")
def phone():
    if not phone_connected():
        return {"connected": False}
    batt, zones = metrics.battery(), metrics.thermal_zones()
    mem = {}
    for line in adb_out("shell", "grep -E 'MemTotal|MemAvailable' /proc/meminfo").splitlines():
        k, v = line.split(":")
        mem[k.strip()] = int(v.split()[0])
    clocks = adb_out(
        "shell",
        "echo $(cat /sys/devices/system/cpu/cpu6/cpufreq/scaling_cur_freq) "
        "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)").split()
    pid = metrics.server_pid()
    return {
        "connected": True,
        "model": adb_out("shell", "getprop", "ro.product.model"),
        "battery_pct": batt.get("level_pct"),
        "battery_temp_c": batt.get("temp_c"),
        "soc_temp_c": metrics.cpu_temp_best_guess(zones),
        "mem_available_mb": round(mem.get("MemAvailable", 0) / 1024),
        "mem_total_mb": round(mem.get("MemTotal", 0) / 1024),
        "clock_prime_mhz": round(int(clocks[0]) / 1000) if clocks else None,
        "clock_perf_mhz": round(int(clocks[1]) / 1000) if len(clocks) > 1 else None,
        "server_running": bool(pid) or bool(state.get("mac_proc")),
        "server": {k: state[k] for k in ("engine", "config", "imt", "threads", "load_s", "ready")},
    }


@app.post("/api/connect")
def connect(addr: str = Form(...), code: str = Form(None)):
    if code:
        r = adb("pair", addr, code, timeout=30)
    else:
        r = adb("connect", addr, timeout=30)
    return {"ok": r.returncode == 0, "out": (r.stdout + r.stderr).strip()}


@app.post("/api/server")
def start_server(engine: str = Form(...), config: str = Form(...),
                 threads: int = Form(6), imt: int = Form(576)):
    with lock:
        if not ENGINES.get(engine, {}).get("available"):
            return JSONResponse({"error": f"runtime '{engine}' is not integrated yet — see lab notes roadmap"},
                                status_code=400)
        cfg = CONFIGS[config]
        stop_server(sweep_mac=(engine == "mac"))
        extra = f"--image-max-tokens {imt}" if imt else ""
        t0 = time.monotonic()
        if engine == "mac":
            log = ROOT / "results/raw/server_dash.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            args = [str(MAC_BIN), "-m", str(ROOT / "models" / cfg["model"]),
                    "--mmproj", str(ROOT / "models" / cfg["mmproj"]),
                    "--host", "127.0.0.1", "--port", str(MAC_PORT), "-c", "8192",
                 "-np", "1"]
            if imt:
                args += ["--image-max-tokens", str(imt)]
            state["mac_proc"] = subprocess.Popen(args, stdout=open(log, "w"),
                                                 stderr=subprocess.STDOUT)
            url = f"http://127.0.0.1:{MAC_PORT}"
        else:
            e = ENGINES[engine]
            if not phone_connected():
                return JSONResponse({"error": "phone not connected"}, status_code=409)
            subprocess.run(["adb", "forward", f"tcp:{LOCAL_PORT}", f"tcp:{PHONE_PORT}"], check=True)
            ngl = f"-ngl {e['ngl']}" if e["ngl"] else ""
            # LD_LIBRARY_PATH must apply ONLY to llama-server: exporting it
            # shell-wide makes system tools (nohup) link vendor libs and die
            cmd = (f"cd {PHONE_DIR}/{e['dir']} && "
                   f"nohup env LD_LIBRARY_PATH={e['ld']} ./llama-server -m ../models/{cfg['model']} "
                   f"--mmproj ../models/{cfg['mmproj']} "
                   f"--host 127.0.0.1 --port {PHONE_PORT} -t {threads} -c 8192 -np 1 {ngl} {extra} "
                   f"> {PHONE_DIR}/server.log 2>&1 < /dev/null &")
            # never wait on adb-shell-with-& (adbd holds the session open)
            launcher = subprocess.Popen(["adb", "shell", cmd],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            url = f"http://127.0.0.1:{LOCAL_PORT}"
        try:
            llm.wait_ready(url, timeout_s=300)
        except TimeoutError:
            stop_server()
            return JSONResponse({"error": "server did not become ready — see log"},
                                status_code=500)
        if engine != "mac" and launcher.poll() is None:
            launcher.terminate()
        state.update(engine=engine, config=config, imt=imt, threads=threads,
                     ready=True, load_s=round(time.monotonic() - t0, 1),
                     log_offset=len(read_server_log()))
        return {"ok": True, "load_s": state["load_s"]}


@app.post("/api/infer")
def infer(image: UploadFile = File(...), question: str = Form(...),
          max_tokens: int = Form(64), answer_gt: str = Form(None),
          accept_also: str = Form("")):
    with lock:
        if not state["ready"]:
            return JSONResponse({"error": "start a server first"}, status_code=409)
        UPLOADS.mkdir(parents=True, exist_ok=True)
        ext = (image.filename or "img.jpg").rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png"):
            return JSONResponse({"error": "jpg/jpeg/png only"}, status_code=400)
        path = UPLOADS / f"up_{int(time.time())}.{ext}"
        path.write_bytes(image.file.read())

        url = f"http://127.0.0.1:{MAC_PORT if state['engine'] == 'mac' else LOCAL_PORT}"
        on_phone = state["engine"] != "mac"
        batt0 = metrics.battery() if on_phone else {}
        sampler = metrics.Sampler(interval_s=1.0) if on_phone else None
        ctx = sampler if sampler else _Null()
        with ctx:
            res = llm.query(url, str(path), question, max_tokens=max_tokens)
        t = res.get("timings", {})
        enc = encode_ms_since_last()
        prompt_ms = t.get("prompt_ms")
        rec = {
            "ts": time.time(),
            "engine": state["engine"], "config": state["config"],
            "runtime": ENGINES.get(state["engine"], {}).get("runtime"),
            "imt": state["imt"], "threads": state["threads"],
            "image": path.name, "question": question,
            "answer": res["text"],
            "correct": score.is_correct(res["text"], answer_gt, accept_also) if answer_gt else None,
            "ttft_s": res["ttft_client_s"], "total_s": res["total_s"],
            "encode_ms": enc,
            "prefill_ms": round(prompt_ms - enc) if (prompt_ms and enc) else prompt_ms,
            "prompt_n": t.get("prompt_n"),
            "prefill_tps": round(t["prompt_n"] / (prompt_ms - enc) * 1000, 1)
                           if (prompt_ms and enc and prompt_ms > enc) else t.get("prompt_per_second"),
            "decode_tps": t.get("predicted_per_second"),
            "decode_n": t.get("predicted_n"),
            "decode_ms": t.get("predicted_ms"),
            "peak_ram_mb": round(sampler.peak_vm_hwm_kb / 1024) if sampler and sampler.peak_vm_hwm_kb else None,
            "peak_soc_temp_c": sampler.peak_cpu_temp if sampler else None,
            "battery_before": batt0, "battery_after": metrics.battery() if on_phone else {},
        }
        RUNS_FILE.parent.mkdir(exist_ok=True)
        with open(RUNS_FILE, "a") as f:
            f.write(json.dumps(rec) + "\n")
        return rec


@app.post("/api/warm")
def warm(image: UploadFile = File(...)):
    """Two-phase flow, phase A: encode + image-prefill into the KV cache while
    the user is still typing/speaking. Perceived TTFT then = text prefill only."""
    if not state["ready"]:
        return JSONResponse({"error": "start a server first"}, status_code=409)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / "warm_current.jpg"
    path.write_bytes(image.file.read())
    url = f"http://127.0.0.1:{MAC_PORT if state['engine'] == 'mac' else LOCAL_PORT}"
    t0 = time.monotonic()
    try:
        requests.post(f"{url}/v1/chat/completions", timeout=1200, json={
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": llm.image_data_url(str(path))}},
                {"type": "text", "text": ""}]}],
            "max_tokens": 1, "temperature": 0.0, "cache_prompt": True})
    except requests.RequestException as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    state["log_offset"] = len(read_server_log())  # warm's encode isn't the query's
    return {"ok": True, "warm_s": round(time.monotonic() - t0, 2)}


@app.post("/api/infer_stream")
def infer_stream(image: UploadFile = File(...), question: str = Form(...),
                 max_tokens: int = Form(64), cached: int = Form(0)):
    """Same as /api/infer but streams SSE: token events live, then a done record."""
    if not state["ready"]:
        return JSONResponse({"error": "start a server first"}, status_code=409)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    ext = (image.filename or "img.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png"):
        return JSONResponse({"error": "jpg/jpeg/png only"}, status_code=400)
    path = UPLOADS / f"up_{int(time.time())}.{ext}"
    path.write_bytes(image.file.read())
    url = f"http://127.0.0.1:{MAC_PORT if state['engine'] == 'mac' else LOCAL_PORT}"
    on_phone = state["engine"] != "mac"

    def gen():
        batt0 = metrics.battery() if on_phone else {}
        sampler = metrics.Sampler(interval_s=1.0) if on_phone else None
        if sampler:
            sampler.__enter__()
        payload = {
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": llm.image_data_url(str(path))}},
                {"type": "text", "text": question}]}],
            "max_tokens": max_tokens, "temperature": 0.0, "seed": 42,
            "stream": True, "timings_per_token": True,
            # measurement mode: no cache (honest serial numbers);
            # product mode (warm-on-drop): cache hit -> perceived TTFT
            "cache_prompt": bool(cached),
        }
        t0 = time.monotonic()
        t_first = None
        pieces, timings = [], {}
        try:
            with requests.post(f"{url}/v1/chat/completions", json=payload,
                               stream=True, timeout=1800) as r:
                for line in r.iter_lines():
                    if not line or not line.startswith(b"data: "):
                        continue
                    data = line[len(b"data: "):]
                    if data == b"[DONE]":
                        break
                    obj = json.loads(data)
                    if "timings" in obj:
                        timings = obj["timings"]
                    piece = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                    if piece:
                        if t_first is None:
                            t_first = time.monotonic()
                        pieces.append(piece)
                        yield ("data: " + json.dumps({
                            "type": "token", "text": piece, "n": len(pieces),
                            "elapsed": round(time.monotonic() - t0, 3),
                            "ttft": round(t_first - t0, 3)}) + "\n\n")
        except requests.RequestException as e:
            yield "data: " + json.dumps({"type": "error", "error": str(e)}) + "\n\n"
        finally:
            if sampler:
                sampler.__exit__(None, None, None)
        enc = encode_ms_since_last()
        prompt_ms = timings.get("prompt_ms")
        rec = {
            "ts": time.time(), "engine": state["engine"], "config": state["config"],
            "runtime": ENGINES.get(state["engine"], {}).get("runtime"),
            "imt": state["imt"], "threads": state["threads"], "cached": bool(cached),
            "image": path.name, "question": question, "answer": "".join(pieces).strip(),
            "correct": None,
            "ttft_s": (t_first - t0) if t_first else None,
            "total_s": time.monotonic() - t0,
            "encode_ms": enc,
            "prefill_ms": round(prompt_ms - enc) if (prompt_ms and enc) else prompt_ms,
            "prompt_n": timings.get("prompt_n"),
            "prefill_tps": round(timings["prompt_n"] / (prompt_ms - enc) * 1000, 1)
                           if (prompt_ms and enc and prompt_ms > enc) else timings.get("prompt_per_second"),
            "decode_tps": timings.get("predicted_per_second"),
            "decode_n": timings.get("predicted_n"),
            "decode_ms": timings.get("predicted_ms"),
            "peak_ram_mb": round(sampler.peak_vm_hwm_kb / 1024) if sampler and sampler.peak_vm_hwm_kb else None,
            "peak_soc_temp_c": sampler.peak_cpu_temp if sampler else None,
            "battery_before": batt0, "battery_after": metrics.battery() if on_phone else {},
        }
        RUNS_FILE.parent.mkdir(exist_ok=True)
        with open(RUNS_FILE, "a") as f:
            f.write(json.dumps(rec) + "\n")
        yield "data: " + json.dumps({"type": "done", "record": rec}) + "\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/runs")
def runs():
    if not RUNS_FILE.exists():
        return {"runs": []}
    return {"runs": [json.loads(l) for l in RUNS_FILE.read_text().splitlines() if l.strip()]}


class _Null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8090, log_level="warning")
