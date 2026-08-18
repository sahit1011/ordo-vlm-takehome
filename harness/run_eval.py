"""Quantization-ladder driver.

For each precision config: start llama-server (on the Mac or on the phone via
adb), run every eval item, and log one JSON line per query with accuracy and
the full latency breakdown (client TTFT, server prompt/decode timings, image
encode ms parsed from the server log, peak RAM, thermals).

Usage:
  python harness/run_eval.py --target phone --configs q4,q8 --repeats 3
  python harness/run_eval.py --target mac --configs f16
"""

import argparse
import csv
import json
import pathlib
import re
import subprocess
import time

import client
import metrics
import score

ROOT = pathlib.Path(__file__).resolve().parent.parent
MAC_BIN = pathlib.Path.home() / "Desktop/llama.cpp/build/bin/llama-server"
MAC_MODELS = ROOT / "models"
PHONE_DIR = "/data/local/tmp/ordo"
PORT = 8080
LOCAL_PORT = 18080  # adb-forwarded when target=phone

# decoder ladder + encoder-axis variants (mmproj quantized independently)
CONFIGS = {
    "f16":      {"model": "Qwen2.5-VL-3B-Instruct-f16.gguf",    "mmproj": "mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf"},
    "q8":       {"model": "Qwen2.5-VL-3B-Instruct-Q8_0.gguf",   "mmproj": "mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf"},
    "q4":       {"model": "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf", "mmproj": "mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf"},
    "q2":       {"model": "Qwen2.5-VL-3B-Instruct-Q2_K.gguf",   "mmproj": "mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf"},
    "q4-mmq8":  {"model": "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf", "mmproj": "mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf"},
    "q8-mmq8":  {"model": "Qwen2.5-VL-3B-Instruct-Q8_0.gguf",   "mmproj": "mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf"},
}

ENCODE_RE = re.compile(r"(?:image|slice).{0,40}?(?:encod|process)\w*\s+in\s+(\d+)\s*ms", re.I)


class Server:
    """Lifecycle of one llama-server instance, local or on-phone."""

    def __init__(self, target: str, cfg: dict, threads: int):
        self.target, self.cfg, self.threads = target, cfg, threads
        self.proc = None
        self.log_path = None
        self._log_offset = 0

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{LOCAL_PORT if self.target == 'phone' else PORT}"

    def start(self):
        if self.target == "mac":
            self.log_path = ROOT / "results/raw/server_mac.log"
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.proc = subprocess.Popen(
                [str(MAC_BIN), "-m", str(MAC_MODELS / self.cfg["model"]),
                 "--mmproj", str(MAC_MODELS / self.cfg["mmproj"]),
                 "--host", "127.0.0.1", "--port", str(PORT), "-c", "8192"],
                stdout=open(self.log_path, "w"), stderr=subprocess.STDOUT)
        else:
            subprocess.run(["adb", "shell", "pkill", "llama-server"], capture_output=True)
            subprocess.run(["adb", "forward", f"tcp:{LOCAL_PORT}", f"tcp:{PORT}"], check=True)
            self.log_path = f"{PHONE_DIR}/server.log"
            cmd = (f"cd {PHONE_DIR} && LD_LIBRARY_PATH={PHONE_DIR} "
                   f"nohup ./llama-server -m models/{self.cfg['model']} "
                   f"--mmproj models/{self.cfg['mmproj']} "
                   f"--host 127.0.0.1 --port {PORT} -t {self.threads} -c 8192 "
                   f"> server.log 2>&1 &")
            subprocess.run(["adb", "shell", cmd], check=True)
        client.wait_ready(self.url)
        self._log_offset = len(self._read_log())

    def _read_log(self) -> str:
        if self.target == "mac":
            return pathlib.Path(self.log_path).read_text(errors="replace")
        return subprocess.run(["adb", "shell", "cat", self.log_path],
                              capture_output=True, text=True).stdout

    def encode_ms_since_last(self) -> float | None:
        """Sum of image-encode times logged since the previous call."""
        log = self._read_log()
        new, self._log_offset = log[self._log_offset:], len(log)
        hits = [int(m) for m in ENCODE_RE.findall(new)]
        return sum(hits) if hits else None

    def stop(self):
        if self.target == "mac" and self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=30)
        elif self.target == "phone":
            subprocess.run(["adb", "shell", "pkill", "llama-server"], capture_output=True)


def load_eval(gt_path: pathlib.Path) -> list[dict]:
    with open(gt_path) as f:
        rows = [r for r in csv.DictReader(f) if not r["notes"].startswith("delete")]
    assert rows, "ground_truth.csv has no real rows yet"
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=["mac", "phone"], required=True)
    ap.add_argument("--configs", default="q4", help="comma-separated CONFIGS keys")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--max-tokens", type=int, default=48)
    ap.add_argument("--threads", type=int, default=6, help="phone decode threads")
    ap.add_argument("--gt", default=str(ROOT / "eval/ground_truth.csv"))
    args = ap.parse_args()

    items = load_eval(pathlib.Path(args.gt))
    run_id = time.strftime("%Y%m%d-%H%M%S")

    for name in args.configs.split(","):
        cfg = CONFIGS[name]
        out = ROOT / f"results/{args.target}-{name}-{run_id}.jsonl"
        out.parent.mkdir(exist_ok=True)
        srv = Server(args.target, cfg, args.threads)
        print(f"[{name}] starting server ({cfg['model']}) ...")
        srv.start()
        batt_start = metrics.battery() if args.target == "phone" else {}

        with open(out, "w") as fout:
            for rep in range(args.repeats):
                for it in items:
                    img = str(ROOT / "eval" / it["file"])
                    sampler = metrics.Sampler() if args.target == "phone" else None
                    ctx = sampler if sampler else _null()
                    with ctx:
                        res = client.query(srv.url, img, it["question"],
                                           max_tokens=args.max_tokens)
                    rec = {
                        "config": name, "target": args.target, "rep": rep,
                        "id": it["id"], "difficulty": it["difficulty"],
                        "category": it["category"], "question": it["question"],
                        "prediction": res["text"],
                        "correct": score.is_correct(res["text"], it["answer"], it["accept_also"]),
                        "anls": score.anls(res["text"], it["answer"], it["accept_also"]),
                        "ttft_client_s": res["ttft_client_s"],
                        "total_s": res["total_s"],
                        "timings": res["timings"],
                        "encode_ms": srv.encode_ms_since_last(),
                        "peak_vm_hwm_kb": sampler.peak_vm_hwm_kb if sampler else None,
                        "peak_cpu_temp": sampler.peak_cpu_temp if sampler else None,
                        "ts": time.time(),
                    }
                    fout.write(json.dumps(rec) + "\n")
                    fout.flush()
                    mark = "Y" if rec["correct"] else "n"
                    print(f"  [{name} r{rep}] {it['id']} {mark} "
                          f"ttft={res['ttft_client_s']:.2f}s :: {res['text'][:60]!r}")

        if args.target == "phone":
            print(f"[{name}] battery: {batt_start} -> {metrics.battery()}")
        srv.stop()
        print(f"[{name}] wrote {out}")


class _null:
    def __enter__(self): return self
    def __exit__(self, *a): pass


if __name__ == "__main__":
    main()
