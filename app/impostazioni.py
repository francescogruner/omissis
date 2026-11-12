# -*- coding: utf-8 -*-
"""Impostazioni condivise tra pannello e proxy: dati\\impostazioni.json."""
import json
from pathlib import Path

import catalogo
import percorsi

FILE = percorsi.DATI / "impostazioni.json"
PREDEFINITE = {
    "modello": "omissis-base",   # omissis-base (piu' preciso) oppure omissis-small (piu' leggero)
    "device": "auto",            # auto | cpu | cuda
    "porta": 8080,
    "ripristina": True,          # False: le risposte restano con i segnaposto (per vedere cosa riceve il servizio)
    "blocca_file": False,        # True: blocca il caricamento di file, che il proxy non sa mascherare
    "politiche": {},             # id del servizio -> proteggi | registra | blocca | ignora (assente = predefinita)
    "casella": True,             # sostituisce i dati gia' nella casella di scrittura, prima dell'invio (la difesa piu' stabile)
    "aggiornamenti": "automatici",   # automatici (scarica e installa) | avvisa (controlla soltanto) | mai
    "lingua": "auto",            # auto (quella di Windows) oppure il codice di una lingua presente in pannello\\lingue
    "tema": "auto",              # auto (come il sistema) | chiaro | scuro
    "vista": "semplice",         # semplice (stato, testo, documenti, guida) | avanzata (tutto, per il tecnico)
}
_cache = {"mtime": None, "dati": None}


def leggi():
    try:
        m = FILE.stat().st_mtime
    except OSError:
        return dict(PREDEFINITE)
    if _cache["mtime"] != m:
        try:
            _cache.update(mtime=m, dati={**PREDEFINITE, **json.loads(FILE.read_text(encoding="utf-8"))})
        except ValueError:
            _cache.update(mtime=m, dati=dict(PREDEFINITE))
    return _cache["dati"]


def scrivi(dati):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    puliti = {k: dati.get(k, v) for k, v in PREDEFINITE.items()}
    puliti["politiche"] = {k: v for k, v in (puliti["politiche"] or {}).items()
                           if k in catalogo.PER_ID and v in catalogo.POLITICHE}
    FILE.write_text(json.dumps(puliti, ensure_ascii=False, indent=1), encoding="utf-8")
    return puliti


def politica(servizio, imp=None):
    imp = imp or leggi()
    return imp["politiche"].get(servizio["id"]) or catalogo.politica_predefinita(servizio)


def protetti(imp=None):
    return [s for s in catalogo.SERVIZI if s["adattatore"] and politica(s, imp) == "proteggi"]
