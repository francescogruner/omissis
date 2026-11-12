# -*- coding: utf-8 -*-
"""Esporta un modello nel formato ONNX, che gira senza PyTorch (basta onnxruntime: decine di MB invece di GB).

  python esporta_onnx.py modelli\\omissis-small [--int8]

Scrive model.onnx nella cartella del modello (e, con --int8, model.int8.onnx: pesi a 8 bit, un quarto
delle dimensioni e piu' veloce sul processore, da usare solo se il confronto regge). Poi confronta le
uscite con quelle di PyTorch su testi di controllo: l'esportazione vale solo se coincidono.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

QUI = Path(__file__).resolve().parent


class Involucro(torch.nn.Module):
    def __init__(self, modello):
        super().__init__()
        self.modello = modello

    def forward(self, input_ids, attention_mask):
        return self.modello(input_ids=input_ids, attention_mask=attention_mask).logits


def testi_di_controllo(n):
    f = QUI / "dati" / "dev.jsonl"
    if f.exists():
        righe = [json.loads(x) for x in f.open(encoding="utf-8")][:n]
        return [r.get("testo") or r.get("text") or "" for r in righe]
    return ["Buongiorno, sono Giulia Ferraresi della Nevatek S.r.l., il mio numero è 347 5551234."] * n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cartella")
    ap.add_argument("--int8", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cartella = Path(a.cartella)
    tok = AutoTokenizer.from_pretrained(cartella)
    try:   # l'attenzione "semplice" e' quella che si esporta senza sorprese
        mod = AutoModelForTokenClassification.from_pretrained(cartella, attn_implementation="eager", reference_compile=False).eval()
    except TypeError:
        mod = AutoModelForTokenClassification.from_pretrained(cartella).eval()
    esempio = tok(["Scrivi a Giulia Ferraresi, giulia.ferraresi@nevatek.example.", "Ciao."], padding=True, return_tensors="pt")
    uscita = cartella / "model.onnx"
    t0 = time.perf_counter()
    torch.onnx.export(Involucro(mod), (esempio["input_ids"], esempio["attention_mask"]), str(uscita), input_names=["input_ids", "attention_mask"],
                      output_names=["logits"], dynamic_axes={"input_ids": {0: "lotto", 1: "lunghezza"}, "attention_mask": {0: "lotto", 1: "lunghezza"},
                                                             "logits": {0: "lotto", 1: "lunghezza"}}, opset_version=17, dynamo=False)
    print(f"esportato {uscita.name}: {uscita.stat().st_size / 1e6:.0f} MB in {time.perf_counter() - t0:.0f} s")

    import onnxruntime as ort
    file = [uscita]
    if a.int8:
        from onnxruntime.quantization import QuantType, quantize_dynamic
        piccolo = cartella / "model.int8.onnx"
        quantize_dynamic(str(uscita), str(piccolo), weight_type=QuantType.QInt8)
        print(f"esportato {piccolo.name}: {piccolo.stat().st_size / 1e6:.0f} MB")
        file.append(piccolo)

    testi = [t for t in testi_di_controllo(200) if t.strip()]
    enc = tok(testi, padding=True, truncation=True, max_length=512, return_tensors="pt")
    with torch.no_grad():
        t0 = time.perf_counter()
        rif = torch.cat([mod(input_ids=enc["input_ids"][k:k + 8], attention_mask=enc["attention_mask"][k:k + 8]).logits for k in range(0, len(testi), 8)]).numpy()
        t_torch = time.perf_counter() - t0
    maschera = enc["attention_mask"].numpy().astype(bool)
    print(f"PyTorch su processore: {t_torch / len(testi) * 1000:.0f} ms per testo ({len(testi)} testi, {int(maschera.sum())} token)")
    for f in file:
        ses = ort.InferenceSession(str(f), providers=["CPUExecutionProvider"])
        ids, att = enc["input_ids"].numpy(), enc["attention_mask"].numpy()
        t0 = time.perf_counter()
        out = np.concatenate([ses.run(None, {"input_ids": ids[k:k + 8], "attention_mask": att[k:k + 8]})[0] for k in range(0, len(testi), 8)])
        t = time.perf_counter() - t0
        uguali = (out.argmax(-1) == rif.argmax(-1))[maschera].mean()
        scarto = np.abs(out - rif)[maschera].max()
        print(f"{f.name}: {t / len(testi) * 1000:.0f} ms per testo · stessa classe sul {uguali * 100:.3f}% dei token · scarto massimo {scarto:.4f}")
