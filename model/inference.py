# -*- coding: utf-8 -*-
"""Inferenza: modello (finestre scorrevoli) + regole + elenchi.

    det = Detector(model_folder)
    det.analyze(text) -> [[start, end, label], ...]

Tre strati:
  modello   riconosce cio' che dipende dal contesto (nomi, aziende, indirizzi, password in chiaro...)
  regole    formati certi con checksum e segreti (rules.py)
  elenchi   nomi noti da lasciare in chiaro (known.py + lists/never.txt) e termini da mascherare
            sempre (lists/always.txt): sono l'extra che ogni installazione puo' personalizzare

Il modello gira in due modi, con gli stessi risultati:
  PyTorch   quello dell'addestramento; usa la scheda grafica se c'e'
  ONNX      solo processore, ma senza PyTorch: bastano onnxruntime e tokenizers (decine di MB invece
            di GB). Serve il file model.onnx nella cartella del modello (lo scrive export_onnx.py).
Senza PyTorch installato si usa ONNX; con OMISSIS_ENGINE=onnx lo si sceglie comunque.
"""
import json
import os
import re
import types
from pathlib import Path

try:
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer
except ImportError:   # installazione leggera: solo ONNX
    torch = None

import known as _well_known
import rules as _rules

WINDOW, STRIDE = 512, 128
TOKENS_PER_RUN = 2048   # motore ONNX: token passati al modello in una volta (4 finestre piene, o piu' finestre corte)
LISTS = Path(os.environ.get("OMISSIS_LISTS") or Path(__file__).resolve().parent / "lists")   # liste personali


# Sotto questa lunghezza un valore non puo' essere cio' che l'etichetta dice (una partita IVA di due caratteri, un CAP di
# una cifra): sono pezzetti che la rete lascia cadere qua e la', soprattutto su stringhe senza contesto, e mascherarli
# rovina il testo senza proteggere nulla. Vale per cio' che trova la rete, non per le regole, che controllano gia' la forma.
MINIMUM = {"EMAIL": 6, "CAP": 3, "DATA_NASCITA": 4, "CF": 8, "PIVA": 8, "IBAN": 8, "CARTA": 8, "DOC_ID": 4, "TARGA": 5,
          "ID_VEICOLO": 8, "ID_PRATICA": 3, "ID_UTENZA": 4, "IP": 3, "MAC": 8, "DOMINIO": 4, "URL": 4, "SEGRETO": 3, "ID_CLOUD": 6,
          "ID_DISPOSITIVO": 3, "CARTA_SEC": 3}


class Detector:
    def __init__(self, folder, device=None, rules=True, threshold="auto", well_known=True, never=None, always=None, off="auto"):
        """soglia: un token resta "non sensibile" solo se il modello ne e' sicuro almeno quanto la soglia
        (None = classe piu' probabile). Alzarla protegge di piu' e maschera di piu'.
        "auto" usa quella scelta per il modello (file omissis.json nella sua cartella), se c'e'.
        spente: etichette che il modello conosce ma che non vanno restituite (per esempio date e professioni, che di
        serie restano in chiaro). La loro probabilita' viene contata come "non sensibile": cosi' spegnerle non sposta
        le altre decisioni. "auto" usa l'elenco del modello (omissis.json), [] le accende tutte."""
        f = Path(folder) / "omissis.json"
        choices = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        if threshold == "auto":
            threshold = choices.get("threshold")
        self.off_model = list(choices.get("off") or [])
        # soglie proprie di singole etichette: dove sbagliare costa di piu' (il nome di un cliente) si maschera piu' volentieri
        self.thresholds = dict(choices.get("thresholds") or {})
        # calibrate.py puo' aver abbassato nei pesi il punteggio di "niente" (cosi' il modello e' prudente anche per chi lo
        # usa senza questo codice): quando qui si applica una soglia propria, quel tanto va rimesso, e nulla cambia
        self.shift = float(choices.get("shift") or 0.0)
        # lo stesso per le soglie proprie di singole etichette: {etichetta: di quanto e' stato alzato il suo punteggio}
        self.shifts = {k: float(v) for k, v in (choices.get("shifts") or {}).items()}
        self.onnx = torch is None or os.environ.get("OMISSIS_ENGINE") == "onnx"
        if self.onnx:
            self._open_onnx(Path(folder))
        else:
            self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
            self.tok = AutoTokenizer.from_pretrained(folder)
            self.mod = AutoModelForTokenClassification.from_pretrained(folder).to(self.device).eval()
            self.classes = [self.mod.config.id2label[i] for i in range(self.mod.config.num_labels)]
        self.rules, self.threshold, self.well_known = rules, threshold, well_known
        self.configure_off(self.off_model if off == "auto" else off)
        self.configure_lists(never, always)
        self.col_shifted = [([i for i, c in enumerate(self.classes) if c != "O" and c[2:] == e], d) for e, d in self.shifts.items() if d]

    def _weights_class(self):
        """Per ogni classe quanto pesa la sua probabilita' contro quella di "niente": soglia / (1 - soglia).
        Una parola viene mascherata se la somma delle probabilita' sensibili, cosi' pesate, supera quella di "niente", e
        prende l'etichetta che pesa di piu'. Con una soglia sola e' esattamente "niente non raggiunge la soglia"; con
        soglie diverse per etichetta, una parola contesa tra due etichette (il nome di un server, tra HOSTNAME e
        DOMINIO) non viene persa solo perche' la piu' probabile delle due ha la soglia severa."""
        thresholds = [min(self.thresholds.get(c[2:], self.threshold), 0.9999) for c in self.classes]
        return [0.0 if c == "O" else s / (1 - s) for c, s in zip(self.classes, thresholds)]

    def configure_off(self, labels):
        """Sceglie le etichette da non restituire (vedi __init__). Si puo' cambiare a modello gia' caricato."""
        self.off = sorted(set(labels or []))
        self.col_off = [i for i, c in enumerate(self.classes) if c != "O" and c[2:] in self.off]

    def configure_lists(self, never=None, always=None):
        """Carica (o ricarica) gli elenchi personali: None = dai file lists\\never.txt e lists\\always.txt."""
        never = _well_known.read_listing(LISTS / "never.txt") if never is None else never
        always = _well_known.read_listing(LISTS / "always.txt") if always is None else always
        self.never = frozenset(_well_known.norm(x) for x in never)
        terms = sorted({x.strip() for x in always if len(x.strip()) >= 2}, key=len, reverse=True)
        self.rx_always = re.compile(r"(?<![^\W_])(?:" + "|".join(re.escape(x) for x in terms) + r")(?![^\W_])", re.I) if terms else None

    def _open_onnx(self, folder):
        import numpy
        import onnxruntime
        from tokenizers import Tokenizer
        if not (folder / "model.onnx").exists():
            raise FileNotFoundError(f"in {folder} manca model.onnx: crearlo con export_onnx.py, oppure installare PyTorch")
        self.np = numpy
        conf = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        self.classes = [conf["id2label"][str(i)] for i in range(len(conf["id2label"]))]
        self.filler = conf.get("pad_token_id") or 0
        self.tok = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.tok.enable_truncation(max_length=WINDOW, stride=STRIDE)
        self.tok.no_padding()
        self.session = onnxruntime.InferenceSession(str(folder / "model.onnx"), providers=["CPUExecutionProvider"])
        self.device = "cpu"
        self.mod = types.SimpleNamespace(name_or_path=str(folder))

    def _token_onnx(self, texts):
        np = self.np
        windows = []   # (testo a cui appartiene, identificativi, posizioni nel testo)
        for doc, e in enumerate(self.tok.encode_batch(list(texts))):
            for w in [e] + list(e.overflowing):
                windows.append((doc, w.ids, w.offsets))
        best_ones = [dict() for _ in texts]
        order = sorted(range(len(windows)), key=lambda i: len(windows[i][1]))   # lunghezze simili insieme: meno riempitivo
        # Quante finestre per volta: tante se corte, poche se piene (al massimo GETTONI_PER_GIRO token in tutto).
        # Misurato: sul processore passarne 16 piene insieme non fa guadagnare tempo rispetto a 4, ma fa tenere
        # al programma 3,2 GB di memoria invece di 1,7 dopo un testo lungo (ONNX non la restituisce).
        groups, k = [], 0
        while k < len(order):
            end = k + 1
            while end < len(order) and end - k < 32 and (end - k + 1) * len(windows[order[end]][1]) <= TOKENS_PER_RUN:
                end += 1
            groups.append([windows[i] for i in order[k:end]])
            k = end
        for group in groups:
            long = max(len(g[1]) for g in group)
            ids = np.full((len(group), long), self.filler, dtype=np.int64)
            att = np.zeros((len(group), long), dtype=np.int64)
            for r, (_, w, _) in enumerate(group):
                ids[r, :len(w)], att[r, :len(w)] = w, 1
            logits = self.session.run(None, {"input_ids": ids, "attention_mask": att})[0].astype(np.float64)
            if self.threshold is None and not self.col_off:
                pred = logits.argmax(-1)
            else:
                if self.threshold is not None:
                    logits[..., 0] += self.shift
                    for columns, how_much in self.col_shifted:
                        logits[..., columns] -= how_much
                prob = np.exp(logits - logits.max(-1, keepdims=True))
                prob /= prob.sum(-1, keepdims=True)
                if self.col_off:   # cio' che e' spento vale come "non sensibile"
                    prob[..., 0] += prob[..., self.col_off].sum(-1)
                    prob[..., self.col_off] = 0.0
                if self.threshold is None:
                    pred = prob.argmax(-1)
                else:   # vedi _pesi_classe
                    weighted = prob * np.asarray(self._weights_class())
                    pred = np.where(prob[..., 0] >= weighted.sum(-1), 0, weighted.argmax(-1))
            for r, (doc, w, off) in enumerate(group):
                n = len(w)
                for i in range(n):
                    s, e = off[i]
                    if s == e:
                        continue
                    center = min(i, n - 1 - i)
                    if (s, e) not in best_ones[doc] or center > best_ones[doc][(s, e)][0]:
                        best_ones[doc][(s, e)] = (center, int(pred[r, i]))
        return [sorted((s, e, self.classes[c]) for (s, e), (_, c) in m.items()) for m in best_ones]

    def _token(self, texts):
        """Per ogni testo: lista ordinata di (inizio, fine, classe) per token."""
        if self.onnx:
            return self._token_onnx(texts)
        with torch.no_grad():
            return self._token_torch(texts)

    def _token_torch(self, texts):
        enc = self.tok(texts, return_offsets_mapping=True, truncation=True, max_length=WINDOW, stride=STRIDE,
                       return_overflowing_tokens=True, padding=True, return_tensors="pt")
        off, mapping = enc.pop("offset_mapping").tolist(), enc.pop("overflow_to_sample_mapping").tolist()
        with torch.autocast(self.device, dtype=torch.bfloat16, enabled=self.device == "cuda"):
            # 32 finestre per volta: un testo molto lungo non deve esaurire la memoria
            logits = torch.cat([self.mod(input_ids=enc["input_ids"][k:k + 32].to(self.device),
                                         attention_mask=enc["attention_mask"][k:k + 32].to(self.device)).logits
                                for k in range(0, len(mapping), 32)])
        if self.threshold is None and not self.col_off:
            pred = logits.argmax(-1).tolist()
        else:
            logits = logits.float()
            if self.threshold is not None:
                logits[..., 0] += self.shift
                for columns, how_much in self.col_shifted:
                    logits[..., columns] -= how_much
            prob = logits.softmax(-1)
            if self.col_off:   # cio' che e' spento vale come "non sensibile"
                prob[..., 0] += prob[..., self.col_off].sum(-1)
                prob[..., self.col_off] = 0.0
            if self.threshold is None:
                pred = prob.argmax(-1).tolist()
            else:   # vedi _pesi_classe
                weighted = prob * torch.tensor(self._weights_class(), device=prob.device, dtype=prob.dtype)
                best = weighted.argmax(-1)
                pred = torch.where(prob[..., 0] >= weighted.sum(-1), torch.zeros_like(best), best).tolist()
        n_tok = enc["attention_mask"].sum(1).tolist()
        best_ones = [dict() for _ in texts]
        for w, doc in enumerate(mapping):
            for t in range(n_tok[w]):
                s, e = off[w][t]
                if s == e:
                    continue
                center = min(t, n_tok[w] - 1 - t)
                if (s, e) not in best_ones[doc] or center > best_ones[doc][(s, e)][0]:
                    best_ones[doc][(s, e)] = (center, pred[w][t])
        return [sorted((s, e, self.classes[c]) for (s, e), (_, c) in m.items()) for m in best_ones]

    @staticmethod
    def _span(text, token):
        spans, cur = [], None
        for s, e, c in token:
            if c == "O":
                cur = None
                continue
            kind = c[2:]
            if cur and cur[2] == kind and (c[0] == "I" or s < cur[1]):
                cur[1] = max(cur[1], e)
            else:
                cur = [s, e, kind]
                spans.append(cur)
        out = []
        for s, e, l in spans:
            while s < e and text[s].isspace():
                s += 1
            # la virgola o i due punti che seguono un valore non ne fanno parte: tenerli darebbe alla stessa azienda
            # due segnaposto diversi, uno con la virgola e uno senza (una password invece puo' finire cosi')
            # ... e nemmeno una parentesi che si apre o un trattino staccato ("Brescia (", "via Garibaldi, 12 -")
            while e > s and l != "SEGRETO" and (text[e - 1].isspace() or text[e - 1] in ",;:([" or (
                    text[e - 1] in "-–" and text[e - 2:e - 1].isspace())):
                e -= 1
            while e > s and text[e - 1].isspace():
                e -= 1
            if e > s and any(ch.isalnum() for ch in text[s:e]):   # niente span di soli simboli o caratteri invisibili
                out.append([s, e, l])
        # pezzi che si toccano con etichette diverse, o divisi da una sola barra, trattino o punto quando uno dei due e' un
        # pezzetto, sono un valore solo che la rete ha etichettato a tratti: "1/27/13" non deve diventare quattro
        # segnaposto. Diventano un dato solo, con l'etichetta del pezzo piu' lungo
        fused = []
        for s, e, l in out:
            if fused:
                ps, pe, pl, long = fused[-1]
                between = text[pe:s]
                if (between == "" and pl != l) or (len(between) == 1 and between in "/-." and min(e - s, pe - ps) < 3):
                    fused[-1] = [ps, e, l if e - s > long else pl, max(long, e - s)]
                    continue
            fused.append([s, e, l, e - s])
        out = [x[:3] for x in fused]
        # troppo corti per la loro etichetta (vedi MINIMO). Un valore scritto a gruppi ("4910 5209 24641") arriva in piu'
        # pezzi vicini, a volte con etichette diverse: conta la lunghezza di tutti insieme, non quella di ciascuno
        kept, i = [], 0
        while i < len(out):
            j = i + 1
            while j < len(out) and out[j][0] - out[j - 1][1] <= 2 and not any(ch.isalnum() for ch in text[out[j - 1][1]:out[j][0]]):
                j += 1
            together = sum(e - s for s, e, _ in out[i:j])
            kept += [x for x in out[i:j] if together >= MINIMUM.get(x[2], 1)]
            i = j
        return kept

    def model(self, texts):
        return [self._span(t, tk) for t, tk in zip(texts, self._token(texts))]

    def _complete(self, text, spans):
        """Aggiunge agli span del modello gli elenchi e le regole."""
        if self.well_known or self.never:
            spans = [m for m in spans if not ((m[2] == "ORG" and self.well_known and _well_known.is_known(text[m[0]:m[1]], self.never))
                                              or _well_known.norm(text[m[0]:m[1]]) in self.never)]
        certain = _rules.detect(text) if self.rules else []
        if self.never and certain:   # «non mascherare mai» vale anche per cio' che trovano le regole (es. l'email generica dell'azienda)
            certain = [r for r in certain if _well_known.norm(text[r[0]:r[1]]) not in self.never]
        if self.rx_always:
            certain += [[m.start(), m.end(), "ELENCO"] for m in self.rx_always.finditer(text)]
        if certain:
            spans = certain + [m for m in spans if not any(r[0] <= m[0] and m[1] <= r[1] for r in certain)]
        if self.well_known:   # indirizzi tecnici di dominio pubblico: localhost, DNS pubblici, siti di produttori ed enti
            spans = [m for m in spans if m[2] not in ("IP", "URL", "DOMINIO", "HOSTNAME") or not _well_known.public_technical(text[m[0]:m[1]], m[2])]
        return sorted(spans)

    def analyze(self, text):
        return self._complete(text, self.model([text])[0] if text.strip() else [])

    def many(self, texts, batch=32, complete=False):
        """A lotti ordinati per lunghezza (per le valutazioni). completo=True aggiunge regole ed elenchi."""
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = [None] * len(texts)
        for k in range(0, len(order), batch):
            idx = order[k:k + batch]
            for i, sp in zip(idx, self.model([texts[i] or " " for i in idx])):
                out[i] = self._complete(texts[i], sp) if complete else sp
        return out

