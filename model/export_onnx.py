# -*- coding: utf-8 -*-
"""Esporta un modello nel formato ONNX, che gira senza PyTorch (basta onnxruntime: decine di MB invece di GB).

  python export_onnx.py models\\omissis-small [--int8] [--solo-snellire]

Scrive model.onnx nella cartella del modello, snellito (vedi snellisci: circa il doppio piu' veloce sul processore,
stesse uscite), e, con --int8, model.int8.onnx: pesi a 8 bit, piu' veloce ma con risultati diversi (misurato il
14/11/2026 su omissis-base: fino a 1,8 volte piu' veloce, ma dallo 0,3 allo 0,7% dei token cambia classe e il
risultato dipende dal processore: non adottato). Poi confronta le uscite con quelle di PyTorch su testi di
controllo: l'esportazione vale solo se coincidono.
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


def snellisci(percorso):
    """Toglie dal grafo esportato il lavoro inutile attorno alla maschera di attenzione. Non cambia i risultati.

    L'esportazione dell'attenzione lascia in OGNI strato, su una matrice [lotto, teste, token, token]:
      Where(maschera, 0, -inf)   la maschera vero/falso tradotta in numeri: la stessa in tutti gli strati che usano
                                 la stessa maschera (ce ne sono due: attenzione globale e locale)
      IsNaN + Where              dopo la Softmax: rimette 0 nelle righe che non possono guardare nessun token (quelle
                                 del riempitivo, quando nel gruppo ci sono testi piu' corti), dove -inf su tutta la
                                 riga darebbe un valore non valido che poi si propagherebbe a tutto il testo
    Misurato sul processore: queste operazioni prendevano piu' del 40% del tempo. Qui la maschera numerica si calcola
    una volta per tipo e al posto di -inf si usa il numero piu' negativo che esiste: per i token veri non cambia nulla
    (il peso di un token mascherato resta esattamente 0), mentre una riga tutta mascherata da' pesi uguali invece di
    un valore non valido, quindi il controllo dopo la Softmax non serve piu'. Cambiano solo le uscite nelle posizioni
    di riempitivo, che nessuno legge. Restituisce (controlli tolti, maschere riunite)."""
    import onnx
    from onnx import numpy_helper
    modello = onnx.load(str(percorso))
    g = modello.graph
    produce = {u: n for n in g.node for u in n.output}
    costanti = {n.output[0]: numpy_helper.to_array(n.attribute[0].t) for n in g.node
                if n.op_type == "Constant" and n.attribute and n.attribute[0].name == "value"}
    sostituisci, via, viste, guardie = {}, set(), {}, []
    for n in g.node:
        if n.op_type != "Where":
            continue
        condizione = produce.get(n.input[0])
        if condizione is not None and condizione.op_type == "IsNaN" and produce.get(condizione.input[0]) is not None \
                and produce[condizione.input[0]].op_type == "Softmax" and n.input[2] == condizione.input[0]:
            guardie.append((n, condizione))
        elif n.input[1] in costanti and n.input[2] in costanti and costanti[n.input[1]].dtype == np.float32 \
                and any(np.isneginf(costanti[i]).all() for i in n.input[1:3]):
            chiave = (n.input[0], costanti[n.input[1]].tobytes(), costanti[n.input[2]].tobytes())
            if chiave in viste:
                sostituisci[n.output[0]] = viste[chiave]   # stessa maschera, stessi valori: basta la prima
                via.add(n.name)
            else:
                viste[chiave] = n.output[0]
                if "omissis_meno_grande" not in {i.name for i in g.initializer}:
                    g.initializer.append(numpy_helper.from_array(np.array(np.finfo(np.float32).min, dtype=np.float32), "omissis_meno_grande"))
                for k in (1, 2):
                    if np.isneginf(costanti[n.input[k]]).all():
                        n.input[k] = "omissis_meno_grande"
    riunite = len(via)
    if viste:   # senza la maschera resa finita il controllo dopo la Softmax serve ancora
        for n, condizione in guardie:
            sostituisci[n.output[0]] = n.input[2]          # chi leggeva il risultato corretto legge la Softmax
            via.update({n.name, condizione.name})
    tolti = (len(via) - riunite) // 2
    if not via:
        return 0, 0
    nodi = [n for n in g.node if n.name not in via]
    for n in nodi:
        for k, ingresso in enumerate(n.input):
            if ingresso in sostituisci:
                n.input[k] = sostituisci[ingresso]
    usati = {i for n in nodi for i in n.input} | {u.name for u in g.output}
    nodi = [n for n in nodi if n.op_type != "Constant" or n.output[0] in usati]   # le costanti rimaste senza lettori
    del g.node[:]
    g.node.extend(nodi)
    onnx.checker.check_model(modello)
    onnx.save(modello, str(percorso))
    return tolti, riunite


def testi_di_controllo(n):
    f = QUI / "data" / "dev.jsonl"
    if f.exists():
        righe = [json.loads(x) for x in f.open(encoding="utf-8")][:n]
        return [r.get("testo") or r.get("text") or "" for r in righe]
    return ["Buongiorno, sono Giulia Ferraresi della Nevatek S.r.l., il mio numero è 347 5551234."] * n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cartella")
    ap.add_argument("--int8", action="store_true")
    ap.add_argument("--solo-snellire", action="store_true", help="non riesporta: snellisce il model.onnx che c'e' gia' (vedi snellisci)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    cartella = Path(a.cartella)
    if a.solo_snellire:
        print("snellito model.onnx: controlli tolti {}, maschere riunite {}".format(*snellisci(cartella / "model.onnx")))
        sys.exit()
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
    print("snellito: controlli tolti {}, maschere riunite {}".format(*snellisci(uscita)))

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
