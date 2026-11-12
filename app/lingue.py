# -*- coding: utf-8 -*-
"""Le frasi del programma nelle varie lingue.

Stanno tutte in pannello\\lingue\\<codice>.json, un file per lingua con le stesse chiavi: lo stesso
file serve alla pagina del pannello e a questo modulo, cosi' una frase si traduce in un posto solo.
L'italiano e' la lingua di riferimento: una chiave che manca altrove viene presa da li'.

Per aggiungere una lingua: copiare it.json col codice della lingua (es. de.json), tradurre i valori
(mai le chiavi, mai le parole tra graffe), mettere il nome della lingua in "_lingua". Compare da
sola nelle Impostazioni. controlla_lingue.py dice cosa manca.

Impostazione "lingua": auto (quella di Windows; inglese se quella lingua non c'e') oppure un codice.
La variabile OMISSIS_LINGUA, se c'e', vince sull'impostazione (serve alle prove automatiche).
"""
import json
import os
import re
import sys
from pathlib import Path

import impostazioni

CARTELLA = Path(__file__).resolve().parent / "pannello" / "lingue"
RIFERIMENTO = "it"
_cache = {}


def _leggi(codice):
    f = CARTELLA / f"{codice}.json"
    try:
        m = f.stat().st_mtime
    except OSError:
        return {}
    if _cache.get(codice, (None, None))[0] != m:
        try:
            _cache[codice] = (m, json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            _cache[codice] = (m, {})
    return _cache[codice][1]


def disponibili():
    """[{"codice": "it", "nome": "Italiano"}, ...] in ordine di nome."""
    out = [{"codice": f.stem, "nome": _leggi(f.stem).get("_lingua", f.stem)} for f in CARTELLA.glob("*.json") if re.fullmatch(r"[a-z]{2,3}(-[A-Za-z]{2,4})?", f.stem)]
    return sorted(out, key=lambda x: x["nome"].lower())


def di_windows():
    """Il codice della lingua in cui l'utente usa Windows (es. "it"), o None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import locale
        nome = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage())
        return nome.split("_")[0].lower() if nome else None
    except Exception:   # noqa: BLE001
        return None


def scelta():
    return str(os.environ.get("OMISSIS_LINGUA") or impostazioni.leggi().get("lingua") or "auto")


def attiva():
    """Il codice della lingua da usare adesso."""
    codici = {x["codice"] for x in disponibili()}
    voluta = scelta()
    if voluta in codici:
        return voluta
    sistema = di_windows()
    if sistema in codici:
        return sistema
    return "en" if "en" in codici else RIFERIMENTO


def t(chiave, **valori):
    """La frase per una chiave nella lingua attiva, con i valori tra graffe sostituiti."""
    frase = _leggi(attiva()).get(chiave) or _leggi(RIFERIMENTO).get(chiave) or chiave
    return re.sub(r"\{(\w+)\}", lambda m: str(valori[m.group(1)]) if m.group(1) in valori else m.group(), frase) if valori else frase
