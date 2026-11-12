# -*- coding: utf-8 -*-
"""Dove stanno le cose: la cartella del modello, l'interprete Python che lo fa girare, i pesi.

Il programma (questa cartella) e il modello vivono in due cartelle sorelle e in due ambienti Python
diversi: quello del modello porta con se' PyTorch, quello del programma no.

  OMISSIS_PYTHON    interprete da usare per il modello (se non e' in <cartella del modello>\\.venv)
  OMISSIS_DATI      cartella dei dati (archivio, impostazioni, registro, certificato), se non quella solita
  OMISSIS_LISTE     cartella delle liste personali (mai.txt, sempre.txt), se non quella solita

Una copia INSTALLATA (accanto alle cartelle del programma c'e' installato.json, scritto da chi costruisce il
pacchetto) tiene dati, liste e modelli scaricati in %LOCALAPPDATA%\\Omissis: la cartella del programma viene
riscritta a ogni aggiornamento e non deve contenere nulla dell'utente. Una copia lanciata dai sorgenti tiene
tutto accanto al codice, come sempre.
  OMISSIS_PORTE     prima di quattro porte consecutive: motore, pannello, gateway (predefinita 8765).
                    Serve a far girare una seconda copia di prova accanto a quella in uso.
"""
import json
import os
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parent
RADICE = QUI.parent
MODELLO_PREDEFINITO = "omissis-base"
PORTA_MOTORE = int(os.environ.get("OMISSIS_PORTE") or 8765)
PORTA_PANNELLO, PORTA_GATEWAY = PORTA_MOTORE + 1, PORTA_MOTORE + 2
_NOMI_VECCHI = {"v3-base": "omissis-base", "v3-small": "omissis-small"}


def _installata():
    try:
        return json.loads((RADICE / "installato.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


INSTALLATA = _installata()   # None = copia lanciata dai sorgenti; altrimenti {"versione": ..., "canale": "github" | "store"}


def _dati():
    if os.environ.get("OMISSIS_DATI"):
        return Path(os.environ["OMISSIS_DATI"])
    if INSTALLATA is not None:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Omissis"
    return QUI / "dati"


DATI = _dati()


def liste():
    """Le liste personali (mai.txt, sempre.txt): dell'utente, quindi fuori dalla cartella del programma se installato."""
    if os.environ.get("OMISSIS_LISTE"):
        return Path(os.environ["OMISSIS_LISTE"])
    return DATI / "liste" if INSTALLATA is not None else cartella_modello() / "liste"


def cartella_modello():
    """La cartella con inferenza.py, le liste e i pesi."""
    for nome in ("modello", "msp-pii"):
        if (RADICE / nome / "inferenza.py").exists():
            return RADICE / nome
    return RADICE / "modello"


def python_modello():
    scelti = [os.environ.get("OMISSIS_PYTHON"), cartella_modello() / ".venv" / "Scripts" / "python.exe",
              cartella_modello() / ".venv" / "bin" / "python", RADICE / "benchmark" / ".venv" / "Scripts" / "python.exe"]
    for p in scelti:
        if p and Path(p).exists():
            return Path(p)
    return Path(sys.executable)


def mitmdump():
    """Il comando che avvia il proxy: l'eseguibile accanto all'interprete in uso (o in .venv); dove non c'e', come
    nella copia installata che porta con se' il proprio Python, lo stesso programma chiamato dall'interprete."""
    for cartella in (Path(sys.executable).parent, QUI / ".venv" / "Scripts", QUI / ".venv" / "bin"):
        for nome in ("mitmdump.exe", "mitmdump"):
            if (cartella / nome).exists():
                return [str(cartella / nome)]
    return [sys.executable, "-c", "from mitmproxy.tools.main import mitmdump; mitmdump()"]


def browser_di_prova():
    """Il Chromium scaricato da Playwright per le prove (None se non c'e')."""
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or QUI / ".playwright")
    return next(base.glob("chromium-*/chrome-win64/chrome.exe"), None)


def modello(nome):
    """Cartella dei pesi: un percorso completo, oppure il nome di un modello dentro <cartella del modello>\\modelli."""
    if Path(nome).is_dir():
        return Path(nome)
    nome = _NOMI_VECCHI.get(nome, nome)
    scaricato, accanto = DATI / "modelli" / nome, cartella_modello() / "modelli" / nome
    if INSTALLATA is not None or (scaricato.is_dir() and not accanto.is_dir()):
        return scaricato   # quelli scaricati dal programma stanno tra i dati
    return accanto
