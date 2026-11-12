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


class Registro:
    def __init__(self):
        DATI.mkdir(exist_ok=True)
        self.file = (DATI / "activity.jsonl").open("a", encoding="utf-8")
        self.db = sqlite3.connect(DATI / "contacts.sqlite", check_same_thread=False, timeout=10)
        self.db.execute("CREATE TABLE IF NOT EXISTS contatti (giorno TEXT, servizio TEXT, host TEXT, esito TEXT, "
                        "n INTEGER, ultimo TEXT, PRIMARY KEY (giorno, servizio, host, esito))")
        self.visti = {}         # (servizio, host, esito) -> ultimo salvataggio: un contatto al minuto basta
        self.lucchetto = threading.Lock()

    def scrivi(self, **voce):
        voce = {"ora": time.strftime("%Y-%m-%d %H:%M:%S"), **voce}
        with self.lucchetto:
            self.file.write(json.dumps(voce, ensure_ascii=False) + "\n")
            self.file.flush()
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
