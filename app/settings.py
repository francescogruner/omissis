# -*- coding: utf-8 -*-
"""Impostazioni condivise tra pannello e proxy: data\\settings.json."""
import json
import re
import urllib.parse
from pathlib import Path

import catalog
import paths

FILE = paths.DATA / "settings.json"
DEFAULTS = {
    "model": "omissis-base",   # omissis-base (piu' preciso) oppure omissis-small (piu' leggero)
    "device": "auto",            # auto | cpu | cuda
    "port": 8080,
    "restore": True,          # False: le risposte restano con i segnaposto (per vedere cosa riceve il servizio)
    "attachments": True,            # anonimizza i file allegati ai messaggi (Word, Excel, PowerPoint, testo, PDF, immagini con testo)
    "block_files": False,        # True: blocca il caricamento di file, che il proxy non sa mascherare
    "policies": {},             # id del servizio -> proteggi | registra | blocca | ignora (assente = predefinita)
    "box": True,             # sostituisce i dati gia' nella casella di scrittura, prima dell'invio (la difesa piu' stabile)
    "updates": "automatic",   # automatici (scarica e installa) | avvisa (controlla soltanto) | mai
    "language": "auto",            # auto (quella di Windows) oppure il codice di una lingua presente in panel\\lingue
    "theme": "auto",              # auto (come il sistema) | chiaro | scuro
    "view": "simple",         # semplice (stato, testo, documenti, guida) | avanzata (tutto, per il tecnico)
    # scorciatoie da tastiera, valide in ogni programma; "" = spenta. sostituisci: maschera sul posto il testo selezionato
    "shortcuts": {"replace": "ctrl+alt+s", "mask": "ctrl+alt+m", "restore": "ctrl+alt+r"},
    "scan": "weekly",    # analisi degli strumenti AI sul PC: settimanale | giornaliera | mai (resta quella a mano)
    "vault_days": 0,        # 0 = l'archivio tiene tutto; N = toglie da solo le voci non usate da N giorni
    "categories": [],             # categorie in piu' da sostituire (DATA, PROFESSIONE, SALUTE...): di serie restano in chiaro
    "mcp_folders": [],            # cartelle in piu' che il server MCP puo' usare, oltre a Documenti, Desktop e Download
    "gateway_upstreams": {},      # chi ha gia' un proprio gateway: nome usato nell'indirizzo (anthropic, openai...) -> dove inoltrare
    "groups_off": [],             # gruppi di dati che chi usa il PC ha scelto di NON sostituire (vedi GROUPS): di serie nessuno
}
_cache = {"mtime": None, "data": None}


def read():
    try:
        m = FILE.stat().st_mtime
    except OSError:
        return dict(DEFAULTS)
    if _cache["mtime"] != m:
        try:
            _cache.update(mtime=m, data={**DEFAULTS, **json.loads(FILE.read_text(encoding="utf-8"))})
        except ValueError:
            _cache.update(mtime=m, data=dict(DEFAULTS))
    return _cache["data"]


# I gruppi di dati che si possono spegnere (Impostazioni > Riconoscimento > Cosa sostituire). Serve a chi lavora proprio su
# quei dati: un tecnico che fa ragionare l'AI su una rete, uno studio che vuole leggere i numeri di pratica nelle risposte.
GROUPS = {"payments": ["IBAN", "CARTA", "CARTA_SEC", "PIVA"],
          "organizations": ["ORG"],
          "it": ["IP", "MAC", "HOSTNAME", "DOMINIO", "URL", "ACCOUNT", "ID_CLOUD", "ID_DISPOSITIVO"],
          "records": ["ID_PRATICA", "CATASTO", "ID_UTENZA", "TARGA", "ID_VEICOLO"]}
# Questi non si spengono: sono il motivo per cui il programma esiste.
ALWAYS_ON = {"people": ["PERSONA", "EMAIL", "TELEFONO", "INDIRIZZO", "CAP", "CITTA", "DATA_NASCITA", "CF", "DOC_ID"], "secrets": ["SEGRETO"]}


def labels_off(cfg=None):
    """Le etichette che, per scelta di chi usa il PC, non vanno sostituite."""
    chosen = (cfg or read()).get("groups_off") or []
    return {label for g in chosen if g in GROUPS for label in GROUPS[g]}


def address_ok(text):
    """Un indirizzo a cui si puo' inoltrare: http o https, con il nome del computer."""
    try:
        u = urllib.parse.urlsplit(str(text).strip())
        return u.scheme in ("http", "https") and bool(u.hostname) and not u.query and not u.fragment
    except ValueError:
        return False


def write(data):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: data.get(k, v) for k, v in DEFAULTS.items()}
    clean["policies"] = {k: v for k, v in (clean["policies"] or {}).items()
                           if k in catalog.PER_ID and v in catalog.POLICIES}
    date = clean["shortcuts"] if isinstance(clean["shortcuts"], dict) else {}
    clean["shortcuts"] = {k: str(date.get(k, v)).strip().lower()[:40] for k, v in DEFAULTS["shortcuts"].items()}
    clean["categories"] = sorted({str(x) for x in clean["categories"] or [] if str(x).isupper() and len(str(x)) <= 24})
    own = clean["gateway_upstreams"] if isinstance(clean["gateway_upstreams"], dict) else {}
    clean["gateway_upstreams"] = {str(k): str(v).strip().rstrip("/") for k, v in own.items()
                                  if re.fullmatch(r"[a-z0-9-]{1,30}", str(k)) and str(k) != "codex" and address_ok(v)}
    clean["groups_off"] = sorted({str(g) for g in (clean["groups_off"] if isinstance(clean["groups_off"], list) else []) if str(g) in GROUPS})
    extra = clean["mcp_folders"] if isinstance(clean["mcp_folders"], list) else []
    clean["mcp_folders"] = list(dict.fromkeys(str(x).strip().strip('"') for x in extra if str(x).strip()))[:20]
    if clean["scan"] not in ("weekly", "daily", "never"):
        clean["scan"] = DEFAULTS["scan"]
    try:
        clean["vault_days"] = min(3650, max(0, int(clean["vault_days"] or 0)))
    except (TypeError, ValueError):
        clean["vault_days"] = 0
    FILE.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    return clean


def policy(service, cfg=None):
    cfg = cfg or read()
    return cfg["policies"].get(service["id"]) or catalog.default_policy(service)


def guarded(cfg=None):
    return [s for s in catalog.SERVICES if s["adapter"] and policy(s, cfg) == "protect"]
