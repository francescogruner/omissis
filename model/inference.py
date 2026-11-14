# -*- coding: utf-8 -*-
"""Inferenza: modello (finestre scorrevoli) + regole + elenchi.

    ril = Rilevatore(cartella_modello)
    ril.analizza(testo) -> [[inizio, fine, etichetta], ...]

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

import known as _noti
import rules as _regole

FINESTRA, PASSO = 512, 128
GETTONI_PER_GIRO = 2048   # motore ONNX: token passati al modello in una volta (4 finestre piene, o piu' finestre corte)
LISTE = Path(os.environ.get("OMISSIS_LISTS") or Path(__file__).resolve().parent / "lists")   # liste personali


# Sotto questa lunghezza un valore non puo' essere cio' che l'etichetta dice (una partita IVA di due caratteri, un CAP di
# una cifra): sono pezzetti che la rete lascia cadere qua e la', soprattutto su stringhe senza contesto, e mascherarli
# rovina il testo senza proteggere nulla. Vale per cio' che trova la rete, non per le regole, che controllano gia' la forma.
MINIMO = {"EMAIL": 6, "CAP": 3, "DATA_NASCITA": 4, "CF": 8, "PIVA": 8, "IBAN": 8, "CARTA": 8, "DOC_ID": 4, "TARGA": 5,
          "ID_VEICOLO": 8, "ID_PRATICA": 3, "ID_UTENZA": 4, "IP": 3, "MAC": 8, "DOMINIO": 4, "URL": 4, "SEGRETO": 3, "ID_CLOUD": 6,
          "ID_DISPOSITIVO": 3, "CARTA_SEC": 3}


class Rilevatore:
    def __init__(self, cartella, device=None, regole=True, soglia="auto", noti=True, mai=None, sempre=None, spente="auto"):
        """soglia: un token resta "non sensibile" solo se il modello ne e' sicuro almeno quanto la soglia
        (None = classe piu' probabile). Alzarla protegge di piu' e maschera di piu'.
        "auto" usa quella scelta per il modello (file omissis.json nella sua cartella), se c'e'.
        spente: etichette che il modello conosce ma che non vanno restituite (per esempio date e professioni, che di
        serie restano in chiaro). La loro probabilita' viene contata come "non sensibile": cosi' spegnerle non sposta
        le altre decisioni. "auto" usa l'elenco del modello (omissis.json), [] le accende tutte."""
        f = Path(cartella) / "omissis.json"
        scelte = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        if soglia == "auto":
            soglia = scelte.get("soglia")
        self.spente_modello = list(scelte.get("spente") or [])
        # soglie proprie di singole etichette: dove sbagliare costa di piu' (il nome di un cliente) si maschera piu' volentieri
        self.soglie = dict(scelte.get("soglie") or {})
        # calibrate.py puo' aver abbassato nei pesi il punteggio di "niente" (cosi' il modello e' prudente anche per chi lo
        # usa senza questo codice): quando qui si applica una soglia propria, quel tanto va rimesso, e nulla cambia
        self.spostamento = float(scelte.get("spostamento") or 0.0)
        # lo stesso per le soglie proprie di singole etichette: {etichetta: di quanto e' stato alzato il suo punteggio}
        self.spostamenti = {k: float(v) for k, v in (scelte.get("spostamenti") or {}).items()}
        self.onnx = torch is None or os.environ.get("OMISSIS_ENGINE") == "onnx"
        if self.onnx:
            self._apri_onnx(Path(cartella))
        else:
            self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
            self.tok = AutoTokenizer.from_pretrained(cartella)
            self.mod = AutoModelForTokenClassification.from_pretrained(cartella).to(self.device).eval()
            self.classi = [self.mod.config.id2label[i] for i in range(self.mod.config.num_labels)]
        self.regole, self.soglia, self.noti = regole, soglia, noti
        self.imposta_spente(self.spente_modello if spente == "auto" else spente)
        self.imposta_liste(mai, sempre)
        self.col_spostate = [([i for i, c in enumerate(self.classi) if c != "O" and c[2:] == e], d) for e, d in self.spostamenti.items() if d]

    def _pesi_classe(self):
        """Per ogni classe quanto pesa la sua probabilita' contro quella di "niente": soglia / (1 - soglia).
        Una parola viene mascherata se la somma delle probabilita' sensibili, cosi' pesate, supera quella di "niente", e
        prende l'etichetta che pesa di piu'. Con una soglia sola e' esattamente "niente non raggiunge la soglia"; con
        soglie diverse per etichetta, una parola contesa tra due etichette (il nome di un server, tra HOSTNAME e
        DOMINIO) non viene persa solo perche' la piu' probabile delle due ha la soglia severa."""
        soglie = [min(self.soglie.get(c[2:], self.soglia), 0.9999) for c in self.classi]
        return [0.0 if c == "O" else s / (1 - s) for c, s in zip(self.classi, soglie)]

    def imposta_spente(self, etichette):
        """Sceglie le etichette da non restituire (vedi __init__). Si puo' cambiare a modello gia' caricato."""
        self.spente = sorted(set(etichette or []))
        self.col_spente = [i for i, c in enumerate(self.classi) if c != "O" and c[2:] in self.spente]

    def imposta_liste(self, mai=None, sempre=None):
        """Carica (o ricarica) gli elenchi personali: None = dai file lists\\never.txt e lists\\always.txt."""
        mai = _noti.leggi_elenco(LISTE / "never.txt") if mai is None else mai
        sempre = _noti.leggi_elenco(LISTE / "always.txt") if sempre is None else sempre
        self.mai = frozenset(_noti.norma(x) for x in mai)
        termini = sorted({x.strip() for x in sempre if len(x.strip()) >= 2}, key=len, reverse=True)
        self.rx_sempre = re.compile(r"(?<![^\W_])(?:" + "|".join(re.escape(x) for x in termini) + r")(?![^\W_])", re.I) if termini else None

    def _apri_onnx(self, cartella):
        import numpy
        import onnxruntime
        from tokenizers import Tokenizer
        if not (cartella / "model.onnx").exists():
            raise FileNotFoundError(f"in {cartella} manca model.onnx: crearlo con export_onnx.py, oppure installare PyTorch")
        self.np = numpy
        conf = json.loads((cartella / "config.json").read_text(encoding="utf-8"))
        self.classi = [conf["id2label"][str(i)] for i in range(len(conf["id2label"]))]
        self.riempitivo = conf.get("pad_token_id") or 0
        self.tok = Tokenizer.from_file(str(cartella / "tokenizer.json"))
        self.tok.enable_truncation(max_length=FINESTRA, stride=PASSO)
        self.tok.no_padding()
        self.sessione = onnxruntime.InferenceSession(str(cartella / "model.onnx"), providers=["CPUExecutionProvider"])
        self.device = "cpu"
        self.mod = types.SimpleNamespace(name_or_path=str(cartella))

    def _token_onnx(self, testi):
        np = self.np
        finestre = []   # (testo a cui appartiene, identificativi, posizioni nel testo)
        for doc, e in enumerate(self.tok.encode_batch(list(testi))):
            for w in [e] + list(e.overflowing):
                finestre.append((doc, w.ids, w.offsets))
        migliori = [dict() for _ in testi]
        ordine = sorted(range(len(finestre)), key=lambda i: len(finestre[i][1]))   # lunghezze simili insieme: meno riempitivo
        # Quante finestre per volta: tante se corte, poche se piene (al massimo GETTONI_PER_GIRO token in tutto).
        # Misurato: sul processore passarne 16 piene insieme non fa guadagnare tempo rispetto a 4, ma fa tenere
        # al programma 3,2 GB di memoria invece di 1,7 dopo un testo lungo (ONNX non la restituisce).
        gruppi, k = [], 0
        while k < len(ordine):
            fine = k + 1
            while fine < len(ordine) and fine - k < 32 and (fine - k + 1) * len(finestre[ordine[fine]][1]) <= GETTONI_PER_GIRO:
                fine += 1
            gruppi.append([finestre[i] for i in ordine[k:fine]])
            k = fine
        for gruppo in gruppi:
            lungo = max(len(g[1]) for g in gruppo)
            ids = np.full((len(gruppo), lungo), self.riempitivo, dtype=np.int64)
            att = np.zeros((len(gruppo), lungo), dtype=np.int64)
            for r, (_, w, _) in enumerate(gruppo):
                ids[r, :len(w)], att[r, :len(w)] = w, 1
            logits = self.sessione.run(None, {"input_ids": ids, "attention_mask": att})[0].astype(np.float64)
            if self.soglia is None and not self.col_spente:
                pred = logits.argmax(-1)
            else:
                if self.soglia is not None:
                    logits[..., 0] += self.spostamento
                    for colonne, quanto in self.col_spostate:
                        logits[..., colonne] -= quanto
                prob = np.exp(logits - logits.max(-1, keepdims=True))
                prob /= prob.sum(-1, keepdims=True)
                if self.col_spente:   # cio' che e' spento vale come "non sensibile"
                    prob[..., 0] += prob[..., self.col_spente].sum(-1)
                    prob[..., self.col_spente] = 0.0
                if self.soglia is None:
                    pred = prob.argmax(-1)
                else:   # vedi _pesi_classe
                    pesate = prob * np.asarray(self._pesi_classe())
                    pred = np.where(prob[..., 0] >= pesate.sum(-1), 0, pesate.argmax(-1))
            for r, (doc, w, off) in enumerate(gruppo):
                n = len(w)
                for i in range(n):
                    s, e = off[i]
                    if s == e:
                        continue
                    centro = min(i, n - 1 - i)
                    if (s, e) not in migliori[doc] or centro > migliori[doc][(s, e)][0]:
                        migliori[doc][(s, e)] = (centro, int(pred[r, i]))
        return [sorted((s, e, self.classi[c]) for (s, e), (_, c) in m.items()) for m in migliori]

    def _token(self, testi):
        """Per ogni testo: lista ordinata di (inizio, fine, classe) per token."""
        if self.onnx:
            return self._token_onnx(testi)
        with torch.no_grad():
            return self._token_torch(testi)

    def _token_torch(self, testi):
        enc = self.tok(testi, return_offsets_mapping=True, truncation=True, max_length=FINESTRA, stride=PASSO,
                       return_overflowing_tokens=True, padding=True, return_tensors="pt")
        off, mappa = enc.pop("offset_mapping").tolist(), enc.pop("overflow_to_sample_mapping").tolist()
        with torch.autocast(self.device, dtype=torch.bfloat16, enabled=self.device == "cuda"):
            # 32 finestre per volta: un testo molto lungo non deve esaurire la memoria
            logits = torch.cat([self.mod(input_ids=enc["input_ids"][k:k + 32].to(self.device),
                                         attention_mask=enc["attention_mask"][k:k + 32].to(self.device)).logits
                                for k in range(0, len(mappa), 32)])
        if self.soglia is None and not self.col_spente:
            pred = logits.argmax(-1).tolist()
        else:
            logits = logits.float()
            if self.soglia is not None:
                logits[..., 0] += self.spostamento
                for colonne, quanto in self.col_spostate:
                    logits[..., colonne] -= quanto
            prob = logits.softmax(-1)
            if self.col_spente:   # cio' che e' spento vale come "non sensibile"
                prob[..., 0] += prob[..., self.col_spente].sum(-1)
                prob[..., self.col_spente] = 0.0
            if self.soglia is None:
                pred = prob.argmax(-1).tolist()
            else:   # vedi _pesi_classe
                pesate = prob * torch.tensor(self._pesi_classe(), device=prob.device, dtype=prob.dtype)
                migliore = pesate.argmax(-1)
                pred = torch.where(prob[..., 0] >= pesate.sum(-1), torch.zeros_like(migliore), migliore).tolist()
        n_tok = enc["attention_mask"].sum(1).tolist()
        migliori = [dict() for _ in testi]
        for w, doc in enumerate(mappa):
            for t in range(n_tok[w]):
                s, e = off[w][t]
                if s == e:
                    continue
                centro = min(t, n_tok[w] - 1 - t)
                if (s, e) not in migliori[doc] or centro > migliori[doc][(s, e)][0]:
                    migliori[doc][(s, e)] = (centro, pred[w][t])
        return [sorted((s, e, self.classi[c]) for (s, e), (_, c) in m.items()) for m in migliori]

    @staticmethod
    def _span(testo, token):
        spans, cur = [], None
        for s, e, c in token:
            if c == "O":
                cur = None
                continue
            tipo = c[2:]
            if cur and cur[2] == tipo and (c[0] == "I" or s < cur[1]):
                cur[1] = max(cur[1], e)
            else:
                cur = [s, e, tipo]
                spans.append(cur)
        out = []
        for s, e, l in spans:
            while s < e and testo[s].isspace():
                s += 1
            # la virgola o i due punti che seguono un valore non ne fanno parte: tenerli darebbe alla stessa azienda
            # due segnaposto diversi, uno con la virgola e uno senza (una password invece puo' finire cosi')
            # ... e nemmeno una parentesi che si apre o un trattino staccato ("Brescia (", "via Garibaldi, 12 -")
            while e > s and l != "SEGRETO" and (testo[e - 1].isspace() or testo[e - 1] in ",;:([" or (
                    testo[e - 1] in "-–" and testo[e - 2:e - 1].isspace())):
                e -= 1
            while e > s and testo[e - 1].isspace():
                e -= 1
            if e > s and any(ch.isalnum() for ch in testo[s:e]):   # niente span di soli simboli o caratteri invisibili
                out.append([s, e, l])
        # pezzi che si toccano con etichette diverse, o divisi da una sola barra, trattino o punto quando uno dei due e' un
        # pezzetto, sono un valore solo che la rete ha etichettato a tratti: "1/27/13" non deve diventare quattro
        # segnaposto. Diventano un dato solo, con l'etichetta del pezzo piu' lungo
        fusi = []
        for s, e, l in out:
            if fusi:
                ps, pe, pl, lungo = fusi[-1]
                tra = testo[pe:s]
                if (tra == "" and pl != l) or (len(tra) == 1 and tra in "/-." and min(e - s, pe - ps) < 3):
                    fusi[-1] = [ps, e, l if e - s > lungo else pl, max(lungo, e - s)]
                    continue
            fusi.append([s, e, l, e - s])
        out = [x[:3] for x in fusi]
        # troppo corti per la loro etichetta (vedi MINIMO). Un valore scritto a gruppi ("4910 5209 24641") arriva in piu'
        # pezzi vicini, a volte con etichette diverse: conta la lunghezza di tutti insieme, non quella di ciascuno
        tenuti, i = [], 0
        while i < len(out):
            j = i + 1
            while j < len(out) and out[j][0] - out[j - 1][1] <= 2 and not any(ch.isalnum() for ch in testo[out[j - 1][1]:out[j][0]]):
                j += 1
            insieme = sum(e - s for s, e, _ in out[i:j])
            tenuti += [x for x in out[i:j] if insieme >= MINIMO.get(x[2], 1)]
            i = j
        return tenuti

    def modello(self, testi):
        return [self._span(t, tk) for t, tk in zip(testi, self._token(testi))]

    def _completa(self, testo, spans):
        """Aggiunge agli span del modello gli elenchi e le regole."""
        if self.noti or self.mai:
            spans = [m for m in spans if not ((m[2] == "ORG" and self.noti and _noti.e_noto(testo[m[0]:m[1]], self.mai))
                                              or _noti.norma(testo[m[0]:m[1]]) in self.mai)]
        certi = _regole.rileva(testo) if self.regole else []
        if self.mai and certi:   # «non mascherare mai» vale anche per cio' che trovano le regole (es. l'email generica dell'azienda)
            certi = [r for r in certi if _noti.norma(testo[r[0]:r[1]]) not in self.mai]
        if self.rx_sempre:
            certi += [[m.start(), m.end(), "ELENCO"] for m in self.rx_sempre.finditer(testo)]
        if certi:
            spans = certi + [m for m in spans if not any(r[0] <= m[0] and m[1] <= r[1] for r in certi)]
        if self.noti:   # indirizzi tecnici di dominio pubblico: localhost, DNS pubblici, siti di produttori ed enti
            spans = [m for m in spans if m[2] not in ("IP", "URL", "DOMINIO", "HOSTNAME") or not _noti.tecnico_pubblico(testo[m[0]:m[1]], m[2])]
        return sorted(spans)

    def analizza(self, testo):
        return self._completa(testo, self.modello([testo])[0] if testo.strip() else [])

    def molti(self, testi, lotto=32, completo=False):
        """A lotti ordinati per lunghezza (per le valutazioni). completo=True aggiunge regole ed elenchi."""
        ordine = sorted(range(len(testi)), key=lambda i: len(testi[i]))
        out = [None] * len(testi)
        for k in range(0, len(ordine), lotto):
            idx = ordine[k:k + lotto]
            for i, sp in zip(idx, self.modello([testi[i] or " " for i in idx])):
                out[i] = self._completa(testi[i], sp) if completo else sp
        return out

    # ---- English names of the interface the program uses. The Italian ones stay until the model code is renamed too.
    off_model = property(lambda self: self.spente_modello)
    off = property(lambda self: self.spente)
    threshold = property(lambda self: self.soglia)
    never = property(lambda self: self.mai)
    rx_always = property(lambda self: self.rx_sempre)

    def configure_off(self, labels):
        return self.imposta_spente(labels)

    def configure_lists(self, never=None, always=None):
        return self.imposta_liste(never, always)

    def many(self, texts, batch=32, complete=False):
        return self.molti(texts, batch, complete)


Detector = Rilevatore
