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

QUI = Path(__file__).resolve().parent

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cartella, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 400
    testi = [json.loads(x)["testo"] for x in (QUI / "data" / "dev.jsonl").open(encoding="utf-8")][:n]
    testi += ["\n\n".join(testi[k:k + 12]) for k in range(0, 60, 12)]   # cinque testi lunghi
    import inference
    a = inference.Rilevatore(cartella, device="cpu")
    t0 = time.perf_counter()
    con_torch = a.molti(testi, completo=True)
    t_torch = time.perf_counter() - t0
    os.environ["OMISSIS_ENGINE"] = "onnx"
    b = inference.Rilevatore(cartella)
    t0 = time.perf_counter()
    con_onnx = b.molti(testi, completo=True)
    t_onnx = time.perf_counter() - t0
    uguali = sum(x == y for x, y in zip(con_torch, con_onnx))
    dati_torch, dati_onnx = sum(len(x) for x in con_torch), sum(len(x) for x in con_onnx)
    comuni = sum(len({tuple(s) for s in x} & {tuple(s) for s in y}) for x, y in zip(con_torch, con_onnx))
    print(f"testi: {len(testi)} · identici: {uguali} · dati trovati: PyTorch {dati_torch}, ONNX {dati_onnx}, in comune {comuni}")
    print(f"tempo per testo sul processore: PyTorch {t_torch / len(testi) * 1000:.0f} ms · ONNX {t_onnx / len(testi) * 1000:.0f} ms")
    sys.exit(0 if uguali >= len(testi) * 0.995 else 1)
