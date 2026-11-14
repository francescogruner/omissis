# -*- coding: utf-8 -*-
"""Le frasi del programma nelle varie lingue.

Stanno tutte in panel\\locales\\<codice>.json, un file per lingua con le stesse chiavi: lo stesso
file serve alla pagina del pannello e a questo modulo, cosi' una frase si traduce in un posto solo.
L'italiano e' la lingua di riferimento: una chiave che manca altrove viene presa da li'.

Per aggiungere una lingua: copiare it.json col codice della lingua (es. de.json), tradurre i valori
(mai le chiavi, mai le parole tra graffe), mettere il nome della lingua in "_lingua". Compare da
sola nelle Impostazioni. check_languages.py dice cosa manca.

Impostazione "lingua": auto (quella di Windows; inglese se quella lingua non c'e') oppure un codice.
La variabile OMISSIS_LANG, se c'e', vince sull'impostazione (serve alle prove automatiche).
"""
import json
import os
import re
import sys
from pathlib import Path

import settings

FOLDER = Path(__file__).resolve().parent / "panel" / "locales"
REFERENCE = "it"
_cache = {}


def _read(code):
    f = FOLDER / f"{code}.json"
    try:
        m = f.stat().st_mtime
    except OSError:
        return {}
    if _cache.get(code, (None, None))[0] != m:
        try:
            _cache[code] = (m, json.loads(f.read_text(encoding="utf-8")))
        except ValueError:
            _cache[code] = (m, {})
    return _cache[code][1]


def available():
    """[{"codice": "it", "nome": "Italiano"}, ...] in ordine di nome."""
    out = [{"code": f.stem, "name": _read(f.stem).get("_language", f.stem)} for f in FOLDER.glob("*.json") if re.fullmatch(r"[a-z]{2,3}(-[A-Za-z]{2,4})?", f.stem)]
    return sorted(out, key=lambda x: x["name"].lower())


def di_windows():
    """Il codice della lingua in cui l'utente usa Windows (es. "it"), o None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        import locale
        name = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage())
        return name.split("_")[0].lower() if name else None
    except Exception:   # noqa: BLE001
        return None


def choice():
    return str(os.environ.get("OMISSIS_LANG") or settings.read().get("language") or "auto")


def active():
    """Il codice della lingua da usare adesso."""
    codes = {x["code"] for x in available()}
    wanted = choice()
    if wanted in codes:
        return wanted
    system = di_windows()
    if system in codes:
        return system
    return "en" if "en" in codes else REFERENCE


def t(key, **values):
    """La frase per una chiave nella lingua attiva, con i valori tra graffe sostituiti."""
    phrase = _read(active()).get(key) or _read(REFERENCE).get(key) or key
    return re.sub(r"\{(\w+)\}", lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(), phrase) if values else phrase
