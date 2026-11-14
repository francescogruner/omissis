# -*- coding: utf-8 -*-
"""Dove stanno le cose: la cartella del modello, l'interprete Python che lo fa girare, i pesi.

Il programma (questa cartella) e il modello vivono in due cartelle sorelle e in due ambienti Python
diversi: quello del modello porta con se' PyTorch, quello del programma no.

  OMISSIS_PYTHON    interprete da usare per il modello (se non e' in <cartella del modello>\\.venv)
  OMISSIS_DATA      cartella dei dati (archivio, impostazioni, registro, certificato), se non quella solita
  OMISSIS_LISTS     cartella delle liste personali (never.txt, always.txt), se non quella solita

Una copia INSTALLATA (accanto alle cartelle del programma c'e' installed.json, scritto da chi costruisce il
pacchetto) tiene dati, liste e modelli scaricati in %LOCALAPPDATA%\\Omissis: la cartella del programma viene
riscritta a ogni aggiornamento e non deve contenere nulla dell'utente. Una copia lanciata dai sorgenti tiene
tutto accanto al codice, come sempre.
  OMISSIS_PORT     prima di quattro porte consecutive: motore, pannello, gateway (predefinita 8765).
                    Serve a far girare una seconda copia di prova accanto a quella in uso.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_MODEL = "omissis-small"
ENGINE_PORT = int(os.environ.get("OMISSIS_PORT") or 8765)
PANEL_PORT, GATEWAY_PORT = ENGINE_PORT + 1, ENGINE_PORT + 2
_OLD_NAMES = {"v3-base": "omissis-base", "v3-small": "omissis-small"}


def _installed():
    try:
        return json.loads((ROOT / "installed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


INSTALLED = _installed()   # None = copia lanciata dai sorgenti; altrimenti {"versione": ..., "canale": "github" | "store"}


def _data():
    if os.environ.get("OMISSIS_DATA"):
        return Path(os.environ["OMISSIS_DATA"])
    if INSTALLED is not None:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Omissis"
    return HERE / "data"


DATA = _data()


def lists():
    """Le liste personali (never.txt, always.txt): dell'utente, quindi fuori dalla cartella del programma se installato."""
    if os.environ.get("OMISSIS_LISTS"):
        return Path(os.environ["OMISSIS_LISTS"])
    return DATA / "lists" if INSTALLED is not None else model_folder() / "lists"


def model_folder():
    """La cartella con inference.py, le liste e i pesi."""
    for name in ("model",):
        if (ROOT / name / "inference.py").exists():
            return ROOT / name
    return ROOT / "model"


def python_model():
    chosen = [os.environ.get("OMISSIS_PYTHON"), model_folder() / ".venv" / "Scripts" / "python.exe",
              model_folder() / ".venv" / "bin" / "python", ROOT / "benchmark" / ".venv" / "Scripts" / "python.exe"]
    for p in chosen:
        if p and Path(p).exists():
            return Path(p)
    return Path(sys.executable)


def mitmdump():
    """Il comando che avvia il proxy: l'eseguibile accanto all'interprete in uso (o in .venv); dove non c'e', come
    nella copia installata che porta con se' il proprio Python, lo stesso programma chiamato dall'interprete."""
    for folder in (Path(sys.executable).parent, HERE / ".venv" / "Scripts", HERE / ".venv" / "bin"):
        for name in ("mitmdump.exe", "mitmdump"):
            if (folder / name).exists():
                return [str(folder / name)]
    return [sys.executable, "-c", "from mitmproxy.tools.main import mitmdump; mitmdump()"]


def test_browser():
    """Il Chromium scaricato da Playwright per le prove (None se non c'e')."""
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or HERE / ".playwright")
    return next(base.glob("chromium-*/chrome-win64/chrome.exe"), None)


def model(name):
    """Cartella dei pesi: un percorso completo, oppure il nome di un modello dentro <cartella del modello>\\modelli."""
    if Path(name).is_dir():
        return Path(name)
    name = _OLD_NAMES.get(name, name)
    downloaded, beside = DATA / "models" / name, model_folder() / "models" / name
    if INSTALLED is not None or (downloaded.is_dir() and not beside.is_dir()):
        return downloaded   # quelli scaricati dal programma stanno tra i dati
    return beside
