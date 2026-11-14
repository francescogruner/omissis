# -*- coding: utf-8 -*-
"""Addestra Omissis partendo dal backbone grezzo (mai dai pesi di altri modelli PII).

Uso:  python train.py <cartella_backbone> <cartella_uscita> [--epochs 1] [--lr 8e-5] [--batch 32]
          [--ema 0.999] [--llrd 0.95] [--fgm 0.5] [--mask 0.08] [--smooth 0.05]
          [--teacher <cartella>] [--temp 2] [--alpha 0.5]      (python train.py -h per i dettagli)
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

from taxonomy import CLASSES, LABELS, CLASS_ID, OFF

HERE = Path(__file__).resolve().parent
MAXLEN, SEED = 512, 11
# Le fonti dei dati non annotano le stesse cose (vedi build_train.py). Per ogni fonte, le classi che un token senza
# etichetta puo' comunque avere senza essere punito: "niente", piu' tutte le etichette che quella fonte non annota.
SOURCES = ["ours"]


def open_classes():
    f = HERE / "data" / "schema.json"
    schema = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"ours": LABELS}
    SOURCES[:] = list(schema)
    open_ones = torch.zeros(len(SOURCES), len(CLASSES), dtype=torch.bool)
    open_ones[:, 0] = True
    for i, source in enumerate(SOURCES):
        for e in LABELS:
            if e not in schema[source]:
                open_ones[i, CLASS_ID["B-" + e]] = open_ones[i, CLASS_ID["I-" + e]] = True
    return open_ones


def read(name):
    return [json.loads(x) for x in (HERE / "data" / name).open(encoding="utf-8")]


def _classes_token(text, offs, spans):
    """Per ogni token la classe BIO data dagli span (0 = niente, -100 = token speciale)."""
    j, prev, lab = 0, -1, []
    for s, e in offs:
        if s == e:
            lab.append(-100)
            continue
        s2, e2 = s, e
        while s2 < e2 and text[s2].isspace():
            s2 += 1
        while e2 > s2 and text[e2 - 1].isspace():
            e2 -= 1
        if s2 < e2:
            s, e = s2, e2
        while j < len(spans) and spans[j][1] <= s:
            j += 1
        if j < len(spans) and spans[j][0] < e:
            lab.append(CLASS_ID[("I-" if prev == j else "B-") + spans[j][2]])
            prev = j
        else:
            lab.append(0)
    return lab


def encoding(tok, docs, in_chunks=20000):
    """(identificativi, classi, classi «forse», fonte) per ogni testo. «forse»: dove il modello precedente vede una sua
    etichetta che la fonte non annota; li' quella classe non viene punita (e nemmeno "niente")."""
    examples = []
    for k in range(0, len(docs), in_chunks):
        chunk = docs[k:k + in_chunks]
        enc = tok([d["testo"] for d in chunk], return_offsets_mapping=True, truncation=True, max_length=MAXLEN)
        for d, ids, offs in zip(chunk, enc["input_ids"], enc["offset_mapping"]):
            lab = _classes_token(d["testo"], offs, d["spans"])
            maybe = _classes_token(d["testo"], offs, sorted(d["forse"])) if d.get("forse") else None
            examples.append((ids, lab, maybe, SOURCES.index(d.get("dom", "ours")) if d.get("dom", "ours") in SOURCES else 0))
    return examples


def batches(examples, n, r, tokens=0):
    """Lotti di testi di lunghezza simile, al massimo n per lotto. gettoni > 0: un lotto non supera quel numero di token,
    riempitivo compreso; cosi' i testi lunghi vanno in lotti piu' piccoli e non esauriscono la memoria della scheda."""
    idx = list(range(len(examples)))
    r.shuffle(idx)
    out = []
    for k in range(0, len(idx), n * 50):
        batch = []
        for i in sorted(idx[k:k + n * 50], key=lambda i: len(examples[i][0])):
            if batch and (len(batch) == n or (tokens and (len(batch) + 1) * len(examples[i][0]) > tokens)):
                out.append(batch)
                batch = []
            batch.append(i)
        if batch:
            out.append(batch)
    r.shuffle(out)
    return out


def tensors(examples, idx, pad, device):
    m = max(len(examples[i][0]) for i in idx)
    ids = torch.tensor([examples[i][0] + [pad] * (m - len(examples[i][0])) for i in idx], device=device)
    lab = torch.tensor([examples[i][1] + [-100] * (m - len(examples[i][1])) for i in idx], device=device)
    maybe = torch.tensor([(examples[i][2] or [0] * len(examples[i][0])) + [0] * (m - len(examples[i][0])) for i in idx], device=device).clamp(min=0)
    source = torch.tensor([examples[i][3] for i in idx], device=device)
    return ids, (ids != pad).long(), lab, maybe, source


def open_loss(logits, lab, maybe, source, open_ones):
    """Entropia incrociata dove l'etichetta e' data; dove non c'e' etichetta, conta la probabilita' complessiva delle
    classi ammesse per quella fonte ("niente", le etichette che la fonte non annota, l'eventuale «forse»)."""
    valid = lab != -100
    allowed = torch.zeros_like(logits, dtype=torch.bool)
    allowed.scatter_(2, lab.clamp(min=0).unsqueeze(-1), True)
    empty = (lab == 0).unsqueeze(-1)
    allowed |= empty & open_ones[source].unsqueeze(1)
    allowed.scatter_(2, maybe.unsqueeze(-1), True)        # «forse»: un'alternativa ammessa, anche sopra un'etichetta data
    allowed[..., 0] = lab == 0                            # "niente" solo dove non c'e' un'etichetta
    allowed &= valid.unsqueeze(-1)
    logp = torch.log_softmax(logits, -1)
    ll = torch.logsumexp(logp.masked_fill(~allowed, float("-inf")), -1)
    return -(ll[valid]).mean()


def evaluate_dev(det, docs):
    """Stessa metrica del benchmark: entita' protetta se tutti i suoi caratteri alfanumerici sono coperti."""
    tot, ok, tp, fp = collections.Counter(), collections.Counter(), 0, 0
    for d, pred in zip(docs, det.many([d["testo"] for d in docs])):
        text = d["testo"]
        cop = [False] * len(text)
        for s, e, _ in pred:
            for i in range(s, min(e, len(text))):
                cop[i] = True
        for s, e, l in d["spans"]:
            idx = [i for i in range(s, e) if text[i].isalnum()]
            tot[l] += 1
            ok[l] += all(cop[i] for i in idx)
        for s, e, _ in pred:
            if any(s < g[1] and g[0] < e for g in d["spans"]):
                tp += 1
            else:
                fp += 1
    return {"protette": sum(ok.values()) / max(1, sum(tot.values())), "precision": tp / max(1, tp + fp),
            "per_etichetta": {l: round(ok[l] / tot[l], 3) for l in sorted(tot)}}


def groups_lr(mod, lr, llrd):
    """Tasso di apprendimento decrescente verso gli strati bassi (layer-wise lr decay)."""
    n_layers = mod.config.num_hidden_layers
    groups = collections.defaultdict(list)
    for name, par in mod.named_parameters():
        m = re.search(r"layers\.(\d+)\.", name)
        if m:
            prof = n_layers - int(m.group(1))
        elif "embeddings" in name:
            prof = n_layers + 1
        else:
            prof = 0   # testa di classificazione e norma finale
        nodecay = par.ndim < 2 or "norm" in name.lower() or name.endswith(".bias")
        groups[(prof, nodecay)].append(par)
    return [{"params": ps, "lr": lr * llrd ** prof, "weight_decay": 0.0 if nodecay else 0.01}
            for (prof, nodecay), ps in groups.items()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("backbone")
    ap.add_argument("output", type=Path)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--lr", type=float, default=8e-5)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--train", default="train.jsonl")
    ap.add_argument("--tokens", type=int, default=0, help="tetto di token per lotto (es. 8000); 0 = nessun tetto")
    ap.add_argument("--ema", type=float, default=0.0, help="media mobile dei pesi (es. 0.999); 0 = spenta")
    ap.add_argument("--llrd", type=float, default=1.0, help="decadimento del lr per strato (es. 0.95); 1 = spento")
    ap.add_argument("--fgm", type=float, default=0.0, help="addestramento avversario sugli embedding (es. 0.5); 0 = spento")
    ap.add_argument("--mask", type=float, default=0.0, help="quota di token d'ingresso sostituiti con [MASK]")
    ap.add_argument("--smooth", type=float, default=0.0, help="(non piu' usato: la perdita ammette gia' piu' classi)")
    ap.add_argument("--teacher", default=None, help="cartella di un modello Omissis piu' grande da distillare")
    ap.add_argument("--temp", type=float, default=2.0)
    ap.add_argument("--alpha", type=float, default=0.5, help="peso della perdita di distillazione")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args()
    n = a.batch
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    torch.manual_seed(a.seed)
    r = random.Random(a.seed)
    device = "cuda"
    tok = AutoTokenizer.from_pretrained(a.backbone)
    mod = AutoModelForTokenClassification.from_pretrained(
        a.backbone, num_labels=len(CLASSES), id2label=dict(enumerate(CLASSES)), label2id=CLASS_ID).to(device)
    ins = None
    if a.teacher:
        ins = AutoModelForTokenClassification.from_pretrained(a.teacher).to(device).eval()
        assert AutoTokenizer.from_pretrained(a.teacher).get_vocab() == tok.get_vocab(), "tokenizer diversi"
    train, dev = read(a.train), read("dev.jsonl")
    if os.environ.get("MSP_LIMITE"):   # prova rapida della catena
        train, dev = train[:int(os.environ["MSP_LIMITE"])], dev[:200]
    t0 = time.time()
    open_ones = open_classes().to(device)
    es = encoding(tok, train)
    print(f"{len(es)} esempi, {sum(len(x[0]) for x in es) / len(es):.0f} token medi, "
          f"{sum(len(x[0]) >= MAXLEN for x in es)} troncati, codifica {time.time() - t0:.0f}s; fonti: {SOURCES}")
    ott = torch.optim.AdamW(groups_lr(mod, a.lr, a.llrd))
    runs = [batches(es, n, r, a.tokens) for _ in range(a.epochs)]
    steps = sum(len(g) for g in runs)
    print(f"{steps} passi in {a.epochs} epoche")
    hot = int(0.06 * steps)
    plan = torch.optim.lr_scheduler.LambdaLR(
        ott, lambda p: p / max(1, hot) if p < hot else max(0.0, (steps - p) / max(1, steps - hot)))
    ema = {k: v.detach().clone() for k, v in mod.named_parameters()} if a.ema else None
    emb = mod.get_input_embeddings().weight
    special = torch.tensor(tok.all_special_ids, device=device)
    p = 0
    for ep in range(a.epochs):
        mod.train()
        tally, t0 = 0.0, time.time()
        for k, idx in enumerate(runs[ep]):
            ids, att, lab, maybe, source = tensors(es, idx, tok.pad_token_id, device)
            ids_in = ids
            if a.mask:   # rumore sull'ingresso: il modello non puo' appoggiarsi a una singola parola del contesto
                street = (torch.rand(ids.shape, device=device) < a.mask) & ~torch.isin(ids, special)
                ids_in = torch.where(street, torch.full_like(ids, tok.mask_token_id), ids)
            soft = None
            if ins is not None:
                with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
                    soft = torch.softmax(ins(input_ids=ids, attention_mask=att).logits.float() / a.temp, -1)

            def compute():
                with torch.autocast("cuda", dtype=torch.bfloat16):
                    logits = mod(input_ids=ids_in, attention_mask=att).logits.float()
                per = open_loss(logits, lab, maybe, source, open_ones)
                if soft is not None:
                    valid = (lab != -100).unsqueeze(-1)
                    kl = -(soft * torch.log_softmax(logits / a.temp, -1)).sum(-1, keepdim=True)
                    per = (1 - a.alpha) * per + a.alpha * a.temp ** 2 * (kl * valid).sum() / valid.sum()
                return per

            loss = compute()
            loss.backward()
            if a.fgm and emb.grad is not None:   # secondo passaggio con gli embedding spostati nella direzione peggiore
                delta = a.fgm * emb.grad / (emb.grad.norm() + 1e-12)
                emb.data.add_(delta)
                compute().backward()
                emb.data.sub_(delta)
            torch.nn.utils.clip_grad_norm_(mod.parameters(), 1.0)
            ott.step()
            plan.step()
            ott.zero_grad(set_to_none=True)
            if ema is not None:
                d = min(a.ema, (1 + p) / (10 + p))
                with torch.no_grad():
                    for name, par in mod.named_parameters():
                        ema[name].mul_(d).add_(par.detach(), alpha=1 - d)
            tally += loss.item()
            p += 1
            if (k + 1) % 2000 == 0:
                print(f"  epoca {ep + 1} passo {k + 1}: perdita {tally / (k + 1):.4f} ({time.time() - t0:.0f}s)")
        print(f"epoca {ep + 1}: perdita media {tally / (k + 1):.4f}, {time.time() - t0:.0f}s")
    if ema is not None:
        with torch.no_grad():
            for name, par in mod.named_parameters():
                par.copy_(ema[name])
    a.output.mkdir(parents=True, exist_ok=True)
    mod.save_pretrained(a.output)
    tok.save_pretrained(a.output)
    del ins
    from inference import Detector
    (a.output / "omissis.json").write_text(json.dumps({"threshold": 0.85, "off": OFF}, ensure_ascii=False), encoding="utf-8")
    v = evaluate_dev(Detector(str(a.output), rules=False, off=[]), dev)
    (a.output / "addestramento.json").write_text(json.dumps(
        {**{k: str(x) if isinstance(x, Path) else x for k, x in vars(a).items()}, "esempi": len(es), "dev": v},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"dev sintetico: protette {v['protette']:.3f}, precision {v['precision']:.3f}")
    print("  ", v["per_etichetta"])


if __name__ == "__main__":
    main()
