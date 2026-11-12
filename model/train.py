# -*- coding: utf-8 -*-
"""Addestra msp-pii partendo dal backbone grezzo (mai dai pesi di altri modelli PII).

Uso:  python train.py <cartella_backbone> <cartella_uscita> [--epoche 1] [--lr 8e-5] [--lotto 32]
          [--ema 0.999] [--llrd 0.95] [--fgm 0.5] [--maschera 0.08] [--smooth 0.05]
          [--insegnante <cartella>] [--temp 2] [--alfa 0.5]      (python train.py -h per i dettagli)
"""
import argparse
import collections
import json
import math
import os
import random
import re
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForTokenClassification, AutoTokenizer

from taxonomy import CLASSI, ID_CLASSE

QUI = Path(__file__).resolve().parent
MAXLEN, SEME = 512, 11


def leggi(nome):
    return [json.loads(x) for x in (QUI / "data" / nome).open(encoding="utf-8")]


def codifica(tok, docs):
    enc = tok([d["testo"] for d in docs], return_offsets_mapping=True, truncation=True, max_length=MAXLEN)
    esempi = []
    for d, ids, offs in zip(docs, enc["input_ids"], enc["offset_mapping"]):
        testo, spans, j, prec, lab = d["testo"], d["spans"], 0, -1, []
        for s, e in offs:
            if s == e:
                lab.append(-100)
                continue
            s2, e2 = s, e
            while s2 < e2 and testo[s2].isspace():
                s2 += 1
            while e2 > s2 and testo[e2 - 1].isspace():
                e2 -= 1
            if s2 < e2:
                s, e = s2, e2
            while j < len(spans) and spans[j][1] <= s:
                j += 1
            if j < len(spans) and spans[j][0] < e:
                lab.append(ID_CLASSE[("I-" if prec == j else "B-") + spans[j][2]])
                prec = j
            else:
                lab.append(0)
        esempi.append((ids, lab))
    return esempi


def lotti(esempi, n, r):
    idx = list(range(len(esempi)))
    r.shuffle(idx)
    out = []
    for k in range(0, len(idx), n * 50):
        pezzo = sorted(idx[k:k + n * 50], key=lambda i: len(esempi[i][0]))
        out += [pezzo[i:i + n] for i in range(0, len(pezzo), n)]
    r.shuffle(out)
    return out


def tensori(esempi, idx, pad, device):
    m = max(len(esempi[i][0]) for i in idx)
    ids = torch.tensor([esempi[i][0] + [pad] * (m - len(esempi[i][0])) for i in idx], device=device)
    lab = torch.tensor([esempi[i][1] + [-100] * (m - len(esempi[i][1])) for i in idx], device=device)
    return ids, (ids != pad).long(), lab


def valuta_dev(ril, docs):
    """Stessa metrica del benchmark: entita' protetta se tutti i suoi caratteri alfanumerici sono coperti."""
    tot, ok, tp, fp = collections.Counter(), collections.Counter(), 0, 0
    for d, pred in zip(docs, ril.molti([d["testo"] for d in docs])):
        testo = d["testo"]
        cop = [False] * len(testo)
        for s, e, _ in pred:
            for i in range(s, min(e, len(testo))):
                cop[i] = True
        for s, e, l in d["spans"]:
            idx = [i for i in range(s, e) if testo[i].isalnum()]
            tot[l] += 1
            ok[l] += all(cop[i] for i in idx)
        for s, e, _ in pred:
            if any(s < g[1] and g[0] < e for g in d["spans"]):
                tp += 1
            else:
                fp += 1
    return {"protette": sum(ok.values()) / max(1, sum(tot.values())), "precision": tp / max(1, tp + fp),
            "per_etichetta": {l: round(ok[l] / tot[l], 3) for l in sorted(tot)}}


def gruppi_lr(mod, lr, llrd):
    """Tasso di apprendimento decrescente verso gli strati bassi (layer-wise lr decay)."""
    n_strati = mod.config.num_hidden_layers
    gruppi = collections.defaultdict(list)
    for nome, par in mod.named_parameters():
        m = re.search(r"layers\.(\d+)\.", nome)
        if m:
            prof = n_strati - int(m.group(1))
        elif "embeddings" in nome:
            prof = n_strati + 1
        else:
            prof = 0   # testa di classificazione e norma finale
        nodecay = par.ndim < 2 or "norm" in nome.lower() or nome.endswith(".bias")
        gruppi[(prof, nodecay)].append(par)
    return [{"params": ps, "lr": lr * llrd ** prof, "weight_decay": 0.0 if nodecay else 0.01}
            for (prof, nodecay), ps in gruppi.items()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("backbone")
    ap.add_argument("uscita", type=Path)
    ap.add_argument("--epoche", type=int, default=1)
    ap.add_argument("--lr", type=float, default=8e-5)
    ap.add_argument("--lotto", type=int, default=32)
    ap.add_argument("--train", default="train.jsonl")
    ap.add_argument("--ema", type=float, default=0.0, help="media mobile dei pesi (es. 0.999); 0 = spenta")
    ap.add_argument("--llrd", type=float, default=1.0, help="decadimento del lr per strato (es. 0.95); 1 = spento")
    ap.add_argument("--fgm", type=float, default=0.0, help="addestramento avversario sugli embedding (es. 0.5); 0 = spento")
    ap.add_argument("--maschera", type=float, default=0.0, help="quota di token d'ingresso sostituiti con [MASK]")
    ap.add_argument("--smooth", type=float, default=0.0, help="label smoothing")
    ap.add_argument("--insegnante", default=None, help="cartella di un modello msp-pii piu' grande da distillare")
    ap.add_argument("--temp", type=float, default=2.0)
    ap.add_argument("--alfa", type=float, default=0.5, help="peso della perdita di distillazione")
    ap.add_argument("--seme", type=int, default=SEME)
    a = ap.parse_args()
    n = a.lotto
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    torch.manual_seed(a.seme)
    r = random.Random(a.seme)
    device = "cuda"
    tok = AutoTokenizer.from_pretrained(a.backbone)
    mod = AutoModelForTokenClassification.from_pretrained(
        a.backbone, num_labels=len(CLASSI), id2label=dict(enumerate(CLASSI)), label2id=ID_CLASSE).to(device)
    ins = None
    if a.insegnante:
        ins = AutoModelForTokenClassification.from_pretrained(a.insegnante).to(device).eval()
        assert AutoTokenizer.from_pretrained(a.insegnante).get_vocab() == tok.get_vocab(), "tokenizer diversi"
    train, dev = leggi(a.train), leggi("dev.jsonl")
    if os.environ.get("MSP_LIMITE"):   # prova rapida della catena
        train, dev = train[:int(os.environ["MSP_LIMITE"])], dev[:200]
    t0 = time.time()
    es = codifica(tok, train)
    print(f"{len(es)} esempi, {sum(len(i) for i, _ in es) / len(es):.0f} token medi, "
          f"{sum(len(i) >= MAXLEN for i, _ in es)} troncati, codifica {time.time() - t0:.0f}s")
    ott = torch.optim.AdamW(gruppi_lr(mod, a.lr, a.llrd))
    passi = a.epoche * math.ceil(len(es) / n)
    caldo = int(0.06 * passi)
    piano = torch.optim.lr_scheduler.LambdaLR(
        ott, lambda p: p / max(1, caldo) if p < caldo else max(0.0, (passi - p) / max(1, passi - caldo)))
    ema = {k: v.detach().clone() for k, v in mod.named_parameters()} if a.ema else None
    emb = mod.get_input_embeddings().weight
    speciali = torch.tensor(tok.all_special_ids, device=device)
    ce = torch.nn.CrossEntropyLoss(ignore_index=-100, label_smoothing=a.smooth)
    p = 0
    for ep in range(a.epoche):
        mod.train()
        somma, t0 = 0.0, time.time()
        for k, idx in enumerate(lotti(es, n, r)):
            ids, att, lab = tensori(es, idx, tok.pad_token_id, device)
            ids_in = ids
            if a.maschera:   # rumore sull'ingresso: il modello non puo' appoggiarsi a una singola parola del contesto
                via = (torch.rand(ids.shape, device=device) < a.maschera) & ~torch.isin(ids, speciali)
                ids_in = torch.where(via, torch.full_like(ids, tok.mask_token_id), ids)
            morbide = None
            if ins is not None:
                with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
                    morbide = torch.softmax(ins(input_ids=ids, attention_mask=att).logits.float() / a.temp, -1)

            def calcola():
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    logits = mod(input_ids=ids_in, attention_mask=att).logits.float()
                per = ce(logits.view(-1, logits.size(-1)), lab.view(-1))
                if morbide is not None:
                    valido = (lab != -100).unsqueeze(-1)
                    kl = -(morbide * torch.log_softmax(logits / a.temp, -1)).sum(-1, keepdim=True)
                    per = (1 - a.alfa) * per + a.alfa * a.temp ** 2 * (kl * valido).sum() / valido.sum()
                return per

            perdita = calcola()
            perdita.backward()
            if a.fgm and emb.grad is not None:   # secondo passaggio con gli embedding spostati nella direzione peggiore
                delta = a.fgm * emb.grad / (emb.grad.norm() + 1e-12)
                emb.data.add_(delta)
                calcola().backward()
                emb.data.sub_(delta)
            torch.nn.utils.clip_grad_norm_(mod.parameters(), 1.0)
            ott.step()
            piano.step()
            ott.zero_grad(set_to_none=True)
            if ema is not None:
                d = min(a.ema, (1 + p) / (10 + p))
                with torch.no_grad():
                    for nome, par in mod.named_parameters():
                        ema[nome].mul_(d).add_(par.detach(), alpha=1 - d)
            somma += perdita.item()
            p += 1
            if (k + 1) % 1000 == 0:
                print(f"  epoca {ep + 1} passo {k + 1}: perdita {somma / (k + 1):.4f} ({time.time() - t0:.0f}s)")
        print(f"epoca {ep + 1}: perdita media {somma / (k + 1):.4f}, {time.time() - t0:.0f}s")
    if ema is not None:
        with torch.no_grad():
            for nome, par in mod.named_parameters():
                par.copy_(ema[nome])
    a.uscita.mkdir(parents=True, exist_ok=True)
    mod.save_pretrained(a.uscita)
    tok.save_pretrained(a.uscita)
    del ins
    from inference import Rilevatore
    v = valuta_dev(Rilevatore(str(a.uscita), regole=False), dev)
    (a.uscita / "addestramento.json").write_text(json.dumps(
        {**{k: str(x) if isinstance(x, Path) else x for k, x in vars(a).items()}, "esempi": len(es), "dev": v},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"dev sintetico: protette {v['protette']:.3f}, precision {v['precision']:.3f}")
    print("  ", v["per_etichetta"])


if __name__ == "__main__":
    main()
