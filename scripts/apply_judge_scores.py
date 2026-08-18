"""Apply LLM-as-judge verdicts and recompute cited-cell accuracies.

Inputs: scratchpad judge_out_*.json (verdicts for every row substring-scoring
marked wrong; judge = Claude Fable 5, threshold: correct if score > 0.5).
Effects:
  - ledger rows gain judge_score + correct_judge (substring `correct` kept
    untouched — both metrics coexist; substring-correct rows get judge 1.0
    by construction, since the judge only re-examines negatives)
  - results/llm_judge_rescores.jsonl = full row-level audit trail
  - prints the old -> new accuracy table for every cell the report cites
RUN ONLY WHEN NOTHING APPENDS TO THE LEDGER.
"""

import csv
import glob
import json
import os
import pathlib
import statistics as st
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRATCH = pathlib.Path("/private/tmp/claude-502/-Users-anil-Desktop-Ordo-a/71bd18e1-64a7-41d0-9f34-6b8285c3b21c/scratchpad")

judge = {}
why = {}
for f in sorted(SCRATCH.glob("judge_out_*.json")):
    for v in json.load(open(f)):
        judge[v["src"]] = float(v["score"])
        why[v["src"]] = v.get("why", "")
inp = {r["src"]: r for r in json.load(open(SCRATCH / "judge_in.json"))}
missing = set(inp) - set(judge)
print(f"verdicts: {len(judge)} · inputs: {len(inp)} · missing: {len(missing)}")

# audit trail
with open(ROOT / "results/llm_judge_rescores.jsonl", "w") as f:
    for src, r in inp.items():
        f.write(json.dumps({**r, "judge_score": judge.get(src),
                            "flipped": (judge.get(src) or 0) > 0.5,
                            "why": why.get(src)}) + "\n")

# ledger rewrite (adds judge fields; substring verdicts untouched)
gt_answers = {r["answer"].strip().lower() for r in csv.DictReader(open(ROOT / "eval/ordo_ground_truth_draft.csv"))}
lines = open(ROOT / "results/dashboard_runs.jsonl").read().splitlines()
out, n_flip = [], 0
for i, l in enumerate(lines):
    r = json.loads(l)
    src = f"ledger:{i}"
    if src in judge:
        r["judge_score"] = judge[src]
        r["correct_judge"] = judge[src] > 0.5
        n_flip += r["correct_judge"]
    elif r.get("correct") is True and (r.get("answer_gt") or "").strip().lower() in gt_answers:
        r["judge_score"], r["correct_judge"] = 1.0, True
    out.append(json.dumps(r))
tmp = (ROOT / "results/dashboard_runs.jsonl").with_suffix(".tmp")
tmp.write_text("\n".join(out) + "\n")
os.replace(tmp, ROOT / "results/dashboard_runs.jsonl")
print(f"ledger updated · {n_flip} rows flipped to correct by judge")

# ---- per-cell old -> new (mirrors the tuning-grid grouping) ----
def cell_of(r, i):
    eng, cfg, imt = r.get("engine"), r.get("config"), r.get("imt") or 0
    if not (eng or "").startswith("phone") or r.get("cached"):
        return None
    if (r.get("answer_gt") or "").strip().lower() not in gt_answers:
        return None
    if cfg == "smol500-q8" and imt == 0:
        return (eng, cfg, "1-tile" if (r.get("prompt_n") or 999) < 400 else "native")
    if cfg == "lfm2-450-q8" and imt == 0:
        pn = r.get("prompt_n") or 0
        b = "512/1024px" if pn < 400 else ("1344px" if pn < 1200 else "native")
        return (eng, cfg, b)
    return (eng, cfg, imt)

rows = [json.loads(l) for l in open(ROOT / "results/dashboard_runs.jsonl")]
cells = defaultdict(lambda: [0, 0, 0])
for i, r in enumerate(rows):
    c = cell_of(r, i)
    if c is None or r.get("correct") is None:
        continue
    cells[c][0] += bool(r["correct"])
    cells[c][1] += bool(r.get("correct_judge", r["correct"]))
    cells[c][2] += 1
print(f"\n{'cell':52s} {'substring':>10s} {'judge':>8s}")
for c, (old, new, n) in sorted(cells.items(), key=lambda kv: str(kv[0])):
    mark = "  <-- changed" if new != old else ""
    print(f"{str(c):52s} {old:>6d}/{n:<3d} {new:>5d}/{n:<3d}{mark}")

# mac harness cells
print()
gt_ids = {r["id"] for r in csv.DictReader(open(ROOT / "eval/ordo_ground_truth_draft.csv"))}
for f in sorted(glob.glob(str(ROOT / "results/mac-qwen3-2b-*-ladder-ordo-*.jsonl")) +
                glob.glob(str(ROOT / "results/mac-lfm2-450-*ordoset*.jsonl")) +
                glob.glob(str(ROOT / "results/mac-smol500-q8-ordoset*.jsonl"))):
    name = pathlib.Path(f).name
    old = new = n = 0
    for i, l in enumerate(open(f)):
        r = json.loads(l)
        if r.get("correct") is None:
            continue
        n += 1
        old += bool(r["correct"])
        s = judge.get(f"{name}:{i}")
        new += bool(r["correct"]) or (s or 0) > 0.5
    mark = "  <-- changed" if new != old else ""
    print(f"{name:60s} {old:>3d}/{n:<3d} -> {new}/{n}{mark}")
