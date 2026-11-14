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

DATA = paths.DATA
RX_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}|[0-9a-fA-F]{16,}|\d{4,}")


def shape(node, prof=0):
    """Struttura di un corpo JSON senza i valori: nomi dei campi, tipi, lunghezze delle stringhe."""
    if isinstance(node, dict):
        return {k: shape(v, prof + 1) for k, v in list(node.items())[:40]} if prof < 4 else "{...}"
    if isinstance(node, list):
        return [shape(node[0], prof + 1), f"x{len(node)}"] if node and prof < 4 else f"[x{len(node)}]"
    if isinstance(node, str):
        return f"str{len(node)}"
    return type(node).__name__


def clean_path(path):
    """Percorso senza parametri e senza identificativi (che potrebbero indicare una conversazione)."""
    return RX_ID.sub("{id}", path.split("?")[0])


COMPATIBILITY = ("CREATE TABLE IF NOT EXISTS compatibility (service TEXT, via TEXT, client TEXT, method TEXT, outcome TEXT, "
                 "n INTEGER, first TEXT, last TEXT, PRIMARY KEY (service, via, client, method, outcome))")
# prodotti che compaiono nell'intestazione User-Agent di qualunque browser: non dicono quale programma e'
GENERIC = {"mozilla", "applewebkit", "khtml", "gecko", "safari", "chrome", "chromium", "electron", "edg", "version", "mobile"}


def client_from_ua(ua):
    """«Claude 1.2.3» da un'intestazione User-Agent: il primo prodotto proprio del programma; per un browser, il suo nome."""
    products = re.findall(r"([A-Za-z][\w.-]*)/(\d[\w.]*)", str(ua or ""))
    for name, version in products:
        if name.lower() not in GENERIC:
            return f"{name} {version}"[:60]
    for abbr, name in (("Edg", "Edge"), ("Electron", "Electron"), ("Chrome", "Chrome"), ("Safari", "Safari")):
        version = next((v for n, v in products if n == abbr), None)
        if version:
            return f"{name} {version}"[:60]
    return re.sub(r"[^\w .()/-]", "", str(ua or ""))[:40]


def signal_of(entry):
    """(servizio, via, programma, metodo, esito) se la riga di registro dice qualcosa sulla compatibilita', altrimenti None.
    esito: ok (dati sostituiti prima dell'invio) | ripristino (valori rimessi nella risposta) | non_letto (formato non riconosciuto)."""
    service, event = entry.get("service"), str(entry.get("event") or "")
    if not service or service == "manual":   # l'uso manuale non passa da nessun programma: non dice nulla sulla compatibilita'
        return None
    if event in ("masked", "attachment_masked") and sum((entry.get("replacements") or {}).values()) > 0:
        outcome = "ok"
    elif event.startswith("response") and entry.get("restored"):
        outcome = "restoring"
    elif "no_text_field" in event:
        outcome = "unread"
    else:
        return None
    via = entry.get("via") or "proxy"
    method = entry.get("method") if entry.get("method") in ("box", "attachment") else {"gateway": "api", "proxy": "proxy", "websocket": "proxy"}.get(via, "network")
    return str(service), "proxy" if via == "websocket" else via, str(entry.get("client") or "")[:60], method, outcome


def compatibility():
    """Il registro delle versioni, raggruppato per servizio, strada e programma. Sola lettura (lo usa il pannello)."""
    f = DATA / "contacts.sqlite"
    if not f.exists():
        return []
    try:
        db = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True)
        lines = db.execute("SELECT service, via, client, method, outcome, n, first, last FROM compatibility").fetchall()
        db.close()
    except sqlite3.Error:
        return []
    groups = {}
    for service, via, client, method, outcome, n, first, last in lines:
        g = groups.setdefault((service, via, client), {"service": service, "via": via, "client": client, "methods": set(), "first": first,
                                                         "ok": 0, "restoring": 0, "unread": 0, "last_ok": "", "last_unread": ""})
        g[outcome] += n
        g["first"] = min(g["first"], first)
        if outcome == "ok":
            g["methods"].add(method)
            g["last_ok"] = max(g["last_ok"], last)
        elif outcome == "unread":
            g["last_unread"] = max(g["last_unread"], last)
    out = []
    for g in groups.values():
        # funziona: l'ultima cosa successa e' una sostituzione riuscita; da ricontrollare: dopo, un formato non e' stato riconosciuto
        g["status"] = "works" if g["ok"] and g["last_ok"] >= g["last_unread"] else "to_recheck"
        g["methods"] = sorted(g["methods"])
        out.append(g)
    return sorted(out, key=lambda g: (g["service"], g["via"], g["client"]))


class Log:
    def __init__(self):
        DATA.mkdir(exist_ok=True)
        self.file = (DATA / "activity.jsonl").open("a", encoding="utf-8")
        self.db = sqlite3.connect(DATA / "contacts.sqlite", check_same_thread=False, timeout=10)
        self.db.execute("CREATE TABLE IF NOT EXISTS contacts (day TEXT, service TEXT, host TEXT, outcome TEXT, "
                        "n INTEGER, last TEXT, PRIMARY KEY (day, service, host, outcome))")
        self.db.execute(COMPATIBILITY)
        self.sightings = {}         # (servizio, host, esito) -> ultimo salvataggio: un contatto al minuto basta
        self.lock = threading.Lock()

    def write(self, **entry):
        entry = {"stamp": time.strftime("%Y-%m-%d %H:%M:%S"), **entry}
        with self.lock:
            self.file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self.file.flush()
            signal = signal_of(entry)
            if signal:   # la riga dice anche se, con quel programma e quella versione, la protezione ha funzionato
                try:
                    self.db.execute("INSERT INTO compatibility VALUES (?, ?, ?, ?, ?, 1, ?, ?) ON CONFLICT (service, via, client, method, outcome) "
                                    "DO UPDATE SET n = n + 1, last = excluded.last", (*signal, entry["stamp"], entry["stamp"]))
                    self.db.commit()
                except sqlite3.Error:
                    pass
        return entry

    def contact(self, service, host, outcome):
        key, stamp = (service, host, outcome), time.time()
        with self.lock:
            if stamp - self.sightings.get(key, 0) < 60:
                return
            self.sightings[key] = stamp
            self.db.execute("INSERT INTO contacts VALUES (?, ?, ?, ?, 1, ?) ON CONFLICT (day, service, host, outcome) "
                            "DO UPDATE SET n = n + 1, last = excluded.last",
                            (time.strftime("%Y-%m-%d"), service, host, outcome, time.strftime("%Y-%m-%d %H:%M:%S")))
            self.db.commit()
