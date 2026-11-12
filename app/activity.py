# -*- coding: utf-8 -*-
"""Registro delle richieste e dei contatti verso i servizi AI. Lo scrivono il proxy (addon.py) e il
motore per conto dell'estensione del browser (bridge.py).

  data\\activity.jsonl    una riga per richiesta: solo conteggi e nomi dei campi, mai i testi
  data\\contacts.sqlite   quante volte al giorno e' stato contattato ciascun servizio (Shadow AI)
"""
import json
import re
import sqlite3
import threading
import time
from pathlib import Path

import paths   # noqa: E402

DATI = paths.DATI
RX_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}|[0-9a-fA-F]{16,}|\d{4,}")


def forma(nodo, prof=0):
    """Struttura di un corpo JSON senza i valori: nomi dei campi, tipi, lunghezze delle stringhe."""
    if isinstance(nodo, dict):
        return {k: forma(v, prof + 1) for k, v in list(nodo.items())[:40]} if prof < 4 else "{...}"
    if isinstance(nodo, list):
        return [forma(nodo[0], prof + 1), f"x{len(nodo)}"] if nodo and prof < 4 else f"[x{len(nodo)}]"
    if isinstance(nodo, str):
        return f"str{len(nodo)}"
    return type(nodo).__name__


def percorso_pulito(percorso):
    """Percorso senza parametri e senza identificativi (che potrebbero indicare una conversazione)."""
    return RX_ID.sub("{id}", percorso.split("?")[0])


COMPATIBILITA = ("CREATE TABLE IF NOT EXISTS compatibilita (servizio TEXT, via TEXT, cliente TEXT, metodo TEXT, esito TEXT, "
                 "n INTEGER, primo TEXT, ultimo TEXT, PRIMARY KEY (servizio, via, cliente, metodo, esito))")
# prodotti che compaiono nell'intestazione User-Agent di qualunque browser: non dicono quale programma e'
GENERICI = {"mozilla", "applewebkit", "khtml", "gecko", "safari", "chrome", "chromium", "electron", "edg", "version", "mobile"}


def cliente_da_ua(ua):
    """«Claude 1.2.3» da un'intestazione User-Agent: il primo prodotto proprio del programma; per un browser, il suo nome."""
    prodotti = re.findall(r"([A-Za-z][\w.-]*)/(\d[\w.]*)", str(ua or ""))
    for nome, versione in prodotti:
        if nome.lower() not in GENERICI:
            return f"{nome} {versione}"[:60]
    for sigla, nome in (("Edg", "Edge"), ("Electron", "Electron"), ("Chrome", "Chrome"), ("Safari", "Safari")):
        versione = next((v for n, v in prodotti if n == sigla), None)
        if versione:
            return f"{nome} {versione}"[:60]
    return re.sub(r"[^\w .()/-]", "", str(ua or ""))[:40]


def segnale_di(voce):
    """(servizio, via, programma, metodo, esito) se la riga di registro dice qualcosa sulla compatibilita', altrimenti None.
    esito: ok (dati sostituiti prima dell'invio) | ripristino (valori rimessi nella risposta) | non_letto (formato non riconosciuto)."""
    servizio, evento = voce.get("servizio"), str(voce.get("evento") or "")
    if not servizio:
        return None
    if evento in ("mascherata", "allegato mascherato") and sum((voce.get("sostituzioni") or {}).values()) > 0:
        esito = "ok"
    elif evento.startswith("risposta") and voce.get("ripristinati"):
        esito = "ripristino"
    elif "nessun campo di testo riconosciuto" in evento:
        esito = "non_letto"
    else:
        return None
    via = voce.get("via") or "proxy"
    metodo = voce.get("metodo") if voce.get("metodo") in ("casella", "allegato") else {"gateway": "api", "proxy": "proxy", "websocket": "proxy"}.get(via, "rete")
    return str(servizio), "proxy" if via == "websocket" else via, str(voce.get("cliente") or "")[:60], metodo, esito


def compatibilita():
    """Il registro delle versioni, raggruppato per servizio, strada e programma. Sola lettura (lo usa il pannello)."""
    f = DATI / "contacts.sqlite"
    if not f.exists():
        return []
    try:
        db = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True)
        righe = db.execute("SELECT servizio, via, cliente, metodo, esito, n, primo, ultimo FROM compatibilita").fetchall()
        db.close()
    except sqlite3.Error:
        return []
    gruppi = {}
    for servizio, via, cliente, metodo, esito, n, primo, ultimo in righe:
        g = gruppi.setdefault((servizio, via, cliente), {"servizio": servizio, "via": via, "cliente": cliente, "metodi": set(), "primo": primo,
                                                         "ok": 0, "ripristino": 0, "non_letto": 0, "ultimo_ok": "", "ultimo_non_letto": ""})
        g[esito] += n
        g["primo"] = min(g["primo"], primo)
        if esito == "ok":
            g["metodi"].add(metodo)
            g["ultimo_ok"] = max(g["ultimo_ok"], ultimo)
        elif esito == "non_letto":
            g["ultimo_non_letto"] = max(g["ultimo_non_letto"], ultimo)
    out = []
    for g in gruppi.values():
        # funziona: l'ultima cosa successa e' una sostituzione riuscita; da ricontrollare: dopo, un formato non e' stato riconosciuto
        g["stato"] = "funziona" if g["ok"] and g["ultimo_ok"] >= g["ultimo_non_letto"] else "da_ricontrollare"
        g["metodi"] = sorted(g["metodi"])
        out.append(g)
    return sorted(out, key=lambda g: (g["servizio"], g["via"], g["cliente"]))


class Registro:
    def __init__(self):
        DATI.mkdir(exist_ok=True)
        self.file = (DATI / "activity.jsonl").open("a", encoding="utf-8")
        self.db = sqlite3.connect(DATI / "contacts.sqlite", check_same_thread=False, timeout=10)
        self.db.execute("CREATE TABLE IF NOT EXISTS contatti (giorno TEXT, servizio TEXT, host TEXT, esito TEXT, "
                        "n INTEGER, ultimo TEXT, PRIMARY KEY (giorno, servizio, host, esito))")
        self.db.execute(COMPATIBILITA)
        self.visti = {}         # (servizio, host, esito) -> ultimo salvataggio: un contatto al minuto basta
        self.lucchetto = threading.Lock()

    def scrivi(self, **voce):
        voce = {"ora": time.strftime("%Y-%m-%d %H:%M:%S"), **voce}
        with self.lucchetto:
            self.file.write(json.dumps(voce, ensure_ascii=False) + "\n")
            self.file.flush()
            segnale = segnale_di(voce)
            if segnale:   # la riga dice anche se, con quel programma e quella versione, la protezione ha funzionato
                try:
                    self.db.execute("INSERT INTO compatibilita VALUES (?, ?, ?, ?, ?, 1, ?, ?) ON CONFLICT (servizio, via, cliente, metodo, esito) "
                                    "DO UPDATE SET n = n + 1, ultimo = excluded.ultimo", (*segnale, voce["ora"], voce["ora"]))
                    self.db.commit()
                except sqlite3.Error:
                    pass
        return voce

    def contatto(self, servizio, host, esito):
        chiave, ora = (servizio, host, esito), time.time()
        with self.lucchetto:
            if ora - self.visti.get(chiave, 0) < 60:
                return
            self.visti[chiave] = ora
            self.db.execute("INSERT INTO contatti VALUES (?, ?, ?, ?, 1, ?) ON CONFLICT (giorno, servizio, host, esito) "
                            "DO UPDATE SET n = n + 1, ultimo = excluded.ultimo",
                            (time.strftime("%Y-%m-%d"), servizio, host, esito, time.strftime("%Y-%m-%d %H:%M:%S")))
            self.db.commit()
