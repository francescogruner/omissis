# -*- coding: utf-8 -*-
"""Confronta i due motori (PyTorch e ONNX) sugli stessi testi: devono trovare gli stessi dati.

  python compare_engines.py models\\omissis-small [quanti testi = 400]

Usa dati\\dev.jsonl (testi sintetici) e aggiunge alcuni testi lunghi, che richiedono piu' finestre.
"""
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    folder, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 400
    texts = [json.loads(x)["testo"] for x in (HERE / "data" / "dev.jsonl").open(encoding="utf-8")][:n]
    texts += ["\n\n".join(texts[k:k + 12]) for k in range(0, 60, 12)]   # cinque testi lunghi
    import inference
    a = inference.Detector(folder, device="cpu")
    t0 = time.perf_counter()
    con_torch = a.many(texts, complete=True)
    t_torch = time.perf_counter() - t0
    os.environ["OMISSIS_ENGINE"] = "onnx"
    b = inference.Detector(folder)
    t0 = time.perf_counter()
    con_onnx = b.many(texts, complete=True)
    t_onnx = time.perf_counter() - t0
    equal = sum(x == y for x, y in zip(con_torch, con_onnx))
    data_torch, data_onnx = sum(len(x) for x in con_torch), sum(len(x) for x in con_onnx)
    common = sum(len({tuple(s) for s in x} & {tuple(s) for s in y}) for x, y in zip(con_torch, con_onnx))
    print(f"testi: {len(texts)} · identici: {equal} · dati trovati: PyTorch {data_torch}, ONNX {data_onnx}, in comune {common}")
    print(f"tempo per testo sul processore: PyTorch {t_torch / len(texts) * 1000:.0f} ms · ONNX {t_onnx / len(texts) * 1000:.0f} ms")
    sys.exit(0 if equal >= len(texts) * 0.995 else 1)
