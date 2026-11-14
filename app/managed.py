# -*- coding: utf-8 -*-
"""Impostazioni imposte da chi amministra il PC.

Chi gestisce i computer di un'azienda puo' fissare alcune scelte (le regole per servizio, gli aggiornamenti,
l'indirizzo della console centrale...) scrivendole in una chiave del registro di Windows che un utente normale non
puo' modificare:

  HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Omissis

Ogni valore ha il nome di un'impostazione (gli stessi di settings.json). Un numero (REG_DWORD) per le scelte si'/no
e per i numeri, un testo (REG_SZ) per il resto; elenchi e tabelle si scrivono in JSON dentro il testo, oppure, gli
elenchi, come REG_MULTI_SZ. Lo script Set-OmissisPolicy.ps1 del kit di distribuzione fa tutto questo.

Le impostazioni scritte qui vincono su quelle dell'utente e nel pannello compaiono bloccate. Non c'e' nessuna
password: comanda chi ha i diritti di amministratore sul PC.

Che cosa NON e': una difesa da chi manomette il programma. Omissis e' installato nel profilo dell'utente, che puo'
quindi modificarne i file; il blocco ferma i cambi fatti dal pannello e dal file delle impostazioni.

  OMISSIS_MANAGED_FILE   un file JSON con altre impostazioni da imporre (per le prove). Puo' solo aggiungere:
                         cio' che sta nel registro vince sempre.
  OMISSIS_TEST           nelle prove le impostazioni imposte vengono rilette ogni due secondi invece che ogni mezzo minuto
"""
import json
import os
import sys
import time

KEY = r"SOFTWARE\Policies\Omissis"
_cache = {"until": 0.0, "data": {}}


def _value(raw, kind):
    """Il valore di registro nella forma che ha in settings.json; i testi che sembrano JSON vengono letti come tali."""
    if isinstance(raw, list):   # REG_MULTI_SZ
        return [str(x) for x in raw if str(x).strip()]
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if text[:1] in "[{" or text.lower() in ("true", "false") or text.lstrip("-").isdigit():
        try:
            return json.loads(text.lower() if text.lower() in ("true", "false") else text)
        except ValueError:
            pass
    return text


def from_registry(hive=None, key=KEY):
    """I valori di una chiave di registro, da tutte e due le viste (64 e 32 bit: alcuni strumenti di distribuzione
    lanciano gli script a 32 bit e scrivono nell'altra). Vince la vista a 64 bit."""
    if sys.platform != "win32":
        return {}
    import winreg
    out = {}
    for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
        try:
            with winreg.OpenKey(hive if hive is not None else winreg.HKEY_LOCAL_MACHINE, key, 0, winreg.KEY_READ | view) as k:
                i = 0
                while True:
                    try:
                        name, raw, kind = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    if name:
                        out[name] = _value(raw, kind)
        except OSError:
            continue
    return out


def _from_file():
    path = os.environ.get("OMISSIS_MANAGED_FILE")
    if not path:
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read(fresh=False):
    """Le impostazioni imposte, cosi' come sono scritte (settings.py le ripulisce). Riletto al piu' una volta ogni mezzo
    minuto: il motore le chiede a ogni richiesta."""
    now = time.monotonic()
    if fresh or now >= _cache["until"]:
        data = {**_from_file(), **from_registry()}
        if data != _cache["data"]:
            _cache["data"] = data   # un oggetto nuovo solo se e' cambiato qualcosa: chi lo usa se ne accorge da questo
        _cache["until"] = now + (2 if os.environ.get("OMISSIS_TEST") else 30)
    return _cache["data"]
