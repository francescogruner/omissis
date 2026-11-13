# -*- coding: utf-8 -*-
"""Measures a model on public PII-masking benchmarks. Prints counts and scores only.

  python benchmark.py <model folder> [--mode full|model] [--limit N] [--save]
  python benchmark.py <hub id of another model> --mode other [--save]

Benchmarks (test data is downloaded once into data/benchmarks/, data files only):

  PIIMB          https://huggingface.co/datasets/piimb/pii-masking-benchmark   (CC BY-NC 4.0)
                 ~150,000 sentences in six tasks. Mostly English; Italian appears in two tasks:
                 ai4privacy-multi (synthetic, 23 languages) and mapa-eur-lex (real EUR-Lex legal
                 text, annotated by hand in English and projected onto the official translations).
  CV-PII-Bench   https://huggingface.co/datasets/abamerdeen/cv-pii-bench       (Apache 2.0)
                 200 fictional CVs in 12 languages, character-level spans.

Scores are the PIIMB "masking" metrics: character level and label agnostic. Overlapping spans are
merged, then precision = predicted characters that are PII, recall = PII characters that are
covered, F2 weighs recall twice as much as precision, FPR = non-PII characters predicted as PII.
Counts are accumulated over all the documents of a group before computing the ratios.

Modes:
  model   the network alone, most likely class per token: what PIIMB runs for token classifiers
  full    what Omissis really does: decision threshold, checksum rules, list of well-known names
          (personal lists are left empty so the result does not depend on the PC)
  other   any token-classification model of the Hugging Face hub, measured like "model": the network
          alone, most likely class, whatever is not "O" counts as masked (other_models.py). It is how
          the comparison tables are made: same code, same texts, for every model

Profiles (models from version 2 on): "strict" turns on every category the model knows; "standard" is
how Omissis ships, with the extra categories (dates, ages, occupations, special categories) left in
clear because removing them changes the meaning of the text.

These test sets were never used to train or tune the models.
"""
import argparse
import collections
import json
import sys
import time
import urllib.request
from pathlib import Path

from inference import Rilevatore

HERE = Path(__file__).resolve().parent
DATA = HERE / "data" / "benchmarks"
SOURCES = {
    "piimb_sentences.jsonl": "https://huggingface.co/datasets/piimb/pii-masking-benchmark/resolve/main/data/test_sentences.jsonl",
    **{f"cv_{split}.jsonl": f"https://huggingface.co/datasets/abamerdeen/cv-pii-bench/resolve/main/{split}.jsonl"
       for split in ("holdout", "devhard", "devsynth", "probe20")},
}


def fetch():
    DATA.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        target = DATA / name
        if target.exists() and target.stat().st_size:
            continue
        print(f"downloading {name} …", flush=True)
        request = urllib.request.Request(url, headers={"User-Agent": "omissis-benchmark"})
        with urllib.request.urlopen(request, timeout=120) as answer, open(target.with_suffix(".part"), "wb") as out:
            while chunk := answer.read(1 << 20):
                out.write(chunk)
        target.with_suffix(".part").replace(target)


def rows(name):
    with open(DATA / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def mask(length, spans):
    m = bytearray(length)
    for start, end in spans:
        start, end = max(0, start), min(length, end)
        if end > start:
            m[start:end] = b"\x01" * (end - start)
    return m


class Score:
    """Character counts for one group of documents."""

    def __init__(self):
        self.gold = self.predicted = self.hit = self.clear = self.false_alarm = self.documents = self.leaking = 0

    def add(self, text, gold_spans, predicted_spans, ignore_spans=()):
        gold, predicted, ignore = mask(len(text), gold_spans), mask(len(text), predicted_spans), mask(len(text), ignore_spans)
        missed = 0
        for g, p, i in zip(gold, predicted, ignore):
            if i:   # ambiguous on purpose: neither rewarded nor penalised
                continue
            self.gold += g
            self.predicted += p
            self.hit += g & p
            self.clear += 1 - g
            self.false_alarm += p & (1 - g)
            missed += g & (1 - p)
        self.documents += 1
        self.leaking += missed > 0

    def values(self):
        p = self.hit / self.predicted if self.predicted else 0.0
        r = self.hit / self.gold if self.gold else 0.0
        f = lambda beta: (1 + beta * beta) * p * r / (beta * beta * p + r) if p + r else 0.0   # noqa: E731
        return {"documents": self.documents, "pii_characters": self.gold, "precision": p, "recall": r, "f1": f(1), "f2": f(2),
                "fpr": self.false_alarm / self.clear if self.clear else 0.0, "documents_with_a_miss": self.leaking}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--mode", choices=["full", "model", "other"], default="full")
    ap.add_argument("--profile", choices=["strict", "standard"], default="strict",
                    help="strict: every category the model knows; standard: as Omissis ships, extra categories left in clear")
    ap.add_argument("--limit", type=int, default=0, help="only the first N rows of each file (to try it out)")
    ap.add_argument("--by-label", dest="by_label", default="", help="also print recall per benchmark label: 'all', or a piece of a task name (e.g. Italian, mapa)")
    ap.add_argument("--save", action="store_true", help="write the scores to data/benchmarks/results/<model>-<mode>.json")
    a = ap.parse_args()
    fetch()
    extra = {} if a.profile == "standard" else {"spente": []}
    if a.mode == "other":
        from other_models import Other
        detector = Other(a.model)
    elif a.mode == "model":
        detector = Rilevatore(a.model, regole=False, soglia=None, noti=False, mai=[], sempre=[], **extra)
    else:
        detector = Rilevatore(a.model, mai=[], sempre=[], **extra)

    def predict(texts):
        t0, out = time.time(), detector.molti(texts, completo=a.mode == "full")
        return [[(s, e) for s, e, _ in spans] for spans in out], time.time() - t0

    groups, seconds, sentences = collections.defaultdict(Score), 0.0, 0
    by_label = collections.defaultdict(lambda: [0, 0, 0, 0])   # (group, label) -> entities, characters, covered characters, entities fully missed
    piimb = rows("piimb_sentences.jsonl")
    piimb = piimb[:a.limit] if a.limit else piimb
    predicted, took = predict([r["text"] for r in piimb])
    seconds, sentences = seconds + took, sentences + len(piimb)
    for r, spans in zip(piimb, predicted):
        gold = [(e["start"], e["end"]) for e in r["entities"]]
        language = str(r.get("language", "")).lower()
        if a.by_label:
            covered = mask(len(r["text"]), spans)
            for e in r["entities"]:
                n = sum(covered[e["start"]:e["end"]])
                for group in (r["task_name"], *([f"{r['task_name']} · Italian"] if language.startswith("it") else [])):
                    row = by_label[(group, e["label"])]
                    row[0] += 1
                    row[1] += e["end"] - e["start"]
                    row[2] += n
                    row[3] += n == 0
        for group in (f"PIIMB {r['task_name']}", *([f"PIIMB {r['task_name']} · Italian"] if language.startswith("it") else []),
                      *(["PIIMB all Italian sentences"] if language.startswith("it") else [])):
            groups[group].add(r["text"], gold, spans)

    for split in ("holdout", "devhard", "devsynth", "probe20"):
        cvs = rows(f"cv_{split}.jsonl")
        cvs = cvs[:a.limit] if a.limit else cvs
        predicted, took = predict([r["text"] for r in cvs])
        seconds, sentences = seconds + took, sentences + len(cvs)
        for r, spans in zip(cvs, predicted):
            gold = [(s["start"], s["end"]) for s in r["spans"] if s.get("required", True)]
            ignore = [(s["start"], s["end"]) for s in r["spans"] if not s.get("required", True)]
            for group in ((f"CV-PII-Bench {split}",) + ((f"CV-PII-Bench {split} · Italian",) if r.get("lang") == "it" else ())
                          + (("CV-PII-Bench all Italian CVs",) if r.get("lang") == "it" else ())):
                groups[group].add(r["text"], gold, spans, ignore)

    name = a.model.replace("/", "__") if a.mode == "other" and not Path(a.model).is_dir() else Path(a.model).name
    print(f"\n{name} · mode {a.mode} · profile {a.profile} · {sentences:,} texts in {seconds:.0f} s ({1000 * seconds / max(1, sentences):.1f} ms each)\n")
    print(f"{'group':44} {'docs':>7} {'recall':>7} {'prec.':>7} {'F1':>6} {'F2':>6} {'FPR':>6} {'with a miss':>12}")
    results = {}
    for group in sorted(groups):
        v = results[group] = groups[group].values()
        print(f"{group:44} {v['documents']:7,} {v['recall']:7.1%} {v['precision']:7.1%} {v['f1']:6.3f} {v['f2']:6.3f} {v['fpr']:6.1%} "
              f"{v['documents_with_a_miss']:6,} ({v['documents_with_a_miss'] / max(1, v['documents']):.0%})")
    tasks = [v for g, v in results.items() if g.startswith("PIIMB ") and "Italian" not in g]
    if tasks and not a.limit:
        print(f"\nPIIMB average over the {len(tasks)} tasks: F2 {sum(v['f2'] for v in tasks) / len(tasks):.3f} · "
              f"recall {sum(v['recall'] for v in tasks) / len(tasks):.1%} · precision {sum(v['precision'] for v in tasks) / len(tasks):.1%}")
    if a.by_label:   # where the misses are: per benchmark label, how much of it is covered
        for group in sorted({g for g, _ in by_label}):
            if a.by_label != "all" and a.by_label not in group:
                continue
            print(f"\n{group}: recall per label of the benchmark")
            for (_, label), (n, chars, hit, missed) in sorted(((k, v) for k, v in by_label.items() if k[0] == group), key=lambda kv: -kv[1][1]):
                print(f"  {label:28} {n:6,} entities  {hit / max(1, chars):6.1%} of characters covered  {missed:6,} fully missed")
    if a.save:
        target = DATA / "results" / f"{name}-{a.mode}-{a.profile}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"model": name, "mode": a.mode, "profile": a.profile, "texts": sentences, "seconds": round(seconds, 1), "scores": results},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        print("saved", target)


if __name__ == "__main__":
    main()
