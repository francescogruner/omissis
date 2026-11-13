# -*- coding: utf-8 -*-
"""The public PIIMB leaderboard as a table, next to our own results.   python leaderboard.py [--refresh]

Downloads the published result files of every model (https://huggingface.co/datasets/piimb/pii-masking-benchmark-results,
MIT) into data/benchmarks/leaderboard/ and prints, per model, the masking F2 of the six tasks and their average, which is
the ranking metric. Our rows come from data/benchmarks/results/*.json written by benchmark.py --save.

The others are measured as PIIMB measures everybody: the network alone, every label, most likely class. The fair
comparison for us is therefore a result saved with "--mode model --profile strict".
"""
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "benchmarks" / "leaderboard"
API = "https://huggingface.co/api/datasets/piimb/pii-masking-benchmark-results/tree/main/results"
RAW = "https://huggingface.co/datasets/piimb/pii-masking-benchmark-results/resolve/main/results/"
TASKS = ["ai4privacy-en", "ai4privacy-multi", "nemotron-pii", "gretel", "privy", "mapa-eur-lex"]


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "omissis-benchmark"}), timeout=60) as answer:
        return answer.read()


def refresh():
    OUT.mkdir(parents=True, exist_ok=True)
    models = [x["path"].split("/")[-1] for x in json.loads(get(API)) if x["type"] == "directory"]
    for model in models:
        scores = {}
        for task in TASKS:
            try:
                data = json.loads(get(RAW + urllib.request.quote(model) + f"/{task}.json"))
                s = data["scores"]["test"][0]
                scores[task] = {k: s.get(k) for k in ("f2", "f1", "precision", "recall", "fpr")}
            except Exception:   # noqa: BLE001  (a model without that task)
                pass
        (OUT / f"{model}.json").write_text(json.dumps(scores), encoding="utf-8")
        print("fetched", model, len(scores), "tasks", flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--refresh" in sys.argv or not OUT.exists():
        refresh()
    rows = []
    for f in sorted(OUT.glob("*.json")):
        scores = json.loads(f.read_text(encoding="utf-8"))
        if len(scores) == len(TASKS):
            rows.append((f.stem.rsplit("__", 1)[0].replace("__", "/"), {t: scores[t]["f2"] for t in TASKS}, {t: scores[t]["recall"] for t in TASKS}))
    for f in sorted((HERE / "data" / "benchmarks" / "results").glob("*.json")):
        ours = json.loads(f.read_text(encoding="utf-8"))["scores"]
        if all(f"PIIMB {t}" in ours for t in TASKS):
            rows.append((">> " + f.stem, {t: ours[f"PIIMB {t}"]["f2"] for t in TASKS}, {t: ours[f"PIIMB {t}"]["recall"] for t in TASKS}))
    rows.sort(key=lambda r: -sum(r[1].values()) / len(TASKS))
    print(f"\n{'#':>2} {'model':58} {'avg F2':>6}  " + " ".join(f"{t[:10]:>10}" for t in TASKS))
    for i, (name, f2, _) in enumerate(rows, 1):
        print(f"{i:2} {name[:58]:58} {sum(f2.values()) / len(TASKS):6.3f}  " + " ".join(f"{f2[t]:10.3f}" for t in TASKS))


if __name__ == "__main__":
    main()
