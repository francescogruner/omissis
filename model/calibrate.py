# -*- coding: utf-8 -*-
"""Bakes the decision threshold into the weights, so that the model is cautious also for whoever uses it without
this project's code (transformers pipeline, other tools, benchmarks).

  python calibrate.py <model folder> [--threshold 0.9] [--label ORG=0.98 DOMINIO=0.4 ...]

A token classifier normally answers with the most likely class. For privacy that is the wrong default: a word should
stay "not sensitive" only if the model is quite sure, not merely more sure than not. inference.py does it with a
threshold on the probability of "nothing"; this script obtains the same effect inside the weights, by lowering the
score of the "nothing" class by log(threshold / (1 - threshold)).

A label can have a threshold of its own (--label): higher where a miss costs more (the name of a customer), lower where
the model sees the label too easily (a domain name in English prose). It goes into the weights the same way: the scores
of that label are raised by log(t_label / (1 - t_label)) - log(threshold / (1 - threshold)), which is the same decision
whenever one label clearly leads, that is almost always.

The amounts are written to omissis.json ("shift", "shifts") together with the thresholds ("threshold",
"thresholds"), and inference.py takes them back before applying its own thresholds, so the results of this project do not
change at all. Run export_onnx.py again afterwards.
"""
import argparse
import json
import math
import sys
from pathlib import Path

from safetensors.torch import load_file, save_file


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("model", type=Path)
    ap.add_argument("--threshold", type=float, default=0.9)
    ap.add_argument("--label", nargs="*", default=[], help="thresholds of single labels, for example ORG=0.98")
    a = ap.parse_args()
    own = {pair.split("=")[0]: float(pair.split("=")[1]) for pair in a.label}
    settings_file = a.model / "omissis.json"
    settings = json.loads(settings_file.read_text(encoding="utf-8")) if settings_file.exists() else {}
    weights = load_file(str(a.model / "model.safetensors"))
    key = next(k for k in weights if k.endswith("classifier.bias"))
    config = json.loads((a.model / "config.json").read_text(encoding="utf-8"))
    nothing = int(config["label2id"]["O"])
    unknown = [label for label in own if "B-" + label not in config["label2id"]]
    if unknown:
        sys.exit(f"labels the model does not have: {', '.join(unknown)}")
    logit = lambda p: math.log(p / (1 - p))   # noqa: E731
    shift = logit(a.threshold)
    already = float(settings.get("shift") or 0.0)
    weights[key][nothing] -= shift - already          # running it twice, or with another threshold, does not add up
    shifts, before = {label: round(logit(t) - shift, 6) for label, t in own.items()}, settings.get("shifts") or {}
    for label in set(shifts) | set(before):
        for prefix in ("B-", "I-"):
            weights[key][int(config["label2id"][prefix + label])] += shifts.get(label, 0.0) - float(before.get(label, 0.0))
    save_file(weights, str(a.model / "model.safetensors"), metadata={"format": "pt"})
    settings.update(threshold=a.threshold, shift=round(shift, 6), thresholds=own, shifts=shifts)
    settings_file.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    print(f"{a.model.name}: score of \"nothing\" lowered by {shift:.3f} (threshold {a.threshold})"
          + "".join(f"; {label} {'raised' if d >= 0 else 'lowered'} by {abs(d):.3f} (threshold {own[label]})" for label, d in shifts.items())
          + "; omissis.json updated. Now run export_onnx.py")


if __name__ == "__main__":
    main()
