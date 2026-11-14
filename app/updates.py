# -*- coding: utf-8 -*-
"""Controllo e installazione degli aggiornamenti del programma.

Una volta al giorno legge dalla pagina pubblica delle versioni un foglio (update.json) che
dice qual e' l'ultima versione, come si chiama il file e che impronta ha. E' una semplice lettura:
non viene inviato nulla, ne' dati ne' identificativi del PC.

Il foglio vale solo se e' FIRMATO con la chiave privata dell'autore (qui sotto c'e' la meta'
pubblica): chi riuscisse a manomettere la pagina delle versioni, o la rete, non potrebbe comunque
far installare un programma suo. Il file dell'installer viene accettato solo se dimensione e
impronta SHA-256 sono quelle del foglio firmato, e ricontrollato un attimo prima di lanciarlo.
Una versione piu' vecchia di quella installata non viene mai accettata.

Impostazione "aggiornamenti":  automatici  scarica da solo; installa al prossimo avvio o con «Installa ora»
                               avvisa      controlla e avvisa soltanto
                               mai         nessun controllo
Solo una copia installata con l'installer si aggiorna da sola. Quella dello Store la aggiorna lo
Store (qui nessun controllo); quella lanciata dai sorgenti riceve soltanto l'avviso.

  OMISSIS_UPDATES_URL   altro indirizzo da cui leggere (prove, o copia interna aziendale): la firma vale lo stesso
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import settings
import i18n
import weights
import paths
from version import VERSION

PUBLIC_KEY = "FTc5/hItV90nAewMfdnTO7X4CgDXLyerwg5ks8fMFIc="
ORIGIN = (os.environ.get("OMISSIS_UPDATES_URL") or "https://github.com/francescogruner/omissis/releases/latest/download").rstrip("/")
PAGE = "https://github.com/francescogruner/omissis/releases/latest"
FOLDER = paths.DATA / "updates"
RX_FILE = re.compile(r"^[A-Za-z0-9][\w.-]{3,80}\.exe$")
RX_VERSION = re.compile(r"^\d{1,4}(\.\d{1,4}){1,3}$")
# fase: mai | controllo | aggiornato | disponibile | scarico | pronto | errore
STATUS = {"phase": "never", "version": "", "notes": "", "error": "", "last_check": "", "completed": 0, "total": 0}
_sheet = {}
_lock = threading.Lock()


class Error(Exception):
    pass


def numbers(v):
    return tuple(int(x) for x in v.split("."))


def channel():
    """github (installer, si aggiorna da solo) | store (ci pensa lo Store) | sorgenti."""
    return (paths.INSTALLED or {}).get("channel") or "source_code"


def mode():
    if channel() == "store":
        return "store"
    choice = settings.read().get("updates", "automatic")
    return choice if choice in ("automatic", "notify", "never") else "automatic"


def installable():
    return channel() == "github" and sys.platform == "win32"


def _verify(sheet, signature):
    """Il foglio e' autentico? Restituisce il contenuto, o solleva Errore."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        raise Error(i18n.t("updates.error.library")) from None
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(PUBLIC_KEY)).verify(base64.b64decode(signature.strip(), validate=True), sheet)
        d = json.loads(sheet.decode("utf-8"))
    except (InvalidSignature, ValueError):
        raise Error(i18n.t("updates.error.signature")) from None
    if (not isinstance(d, dict) or d.get("product") != "omissis" or not RX_VERSION.match(str(d.get("version", "")))
            or not RX_FILE.match(str(d.get("file", ""))) or not re.fullmatch(r"[0-9a-f]{64}", str(d.get("sha256", "")))
            or not isinstance(d.get("byte"), int) or not 0 < d["byte"] < 2_000_000_000):
        raise Error(i18n.t("updates.error.fmt"))
    return d


def _read(name, maximum):
    address = f"{ORIGIN}/{name}"
    if not address.startswith("https://") and not address.startswith("http://127.0.0.1"):
        raise Error(i18n.t("updates.error.address"))
    req = urllib.request.Request(address, headers={"User-Agent": f"Omissis/{VERSION}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(maximum + 1)
    if len(data) > maximum:
        raise Error(i18n.t("updates.error.large"))
    return data


def check():
    """Legge e verifica il foglio. Aggiorna STATO e lo restituisce."""
    global _sheet
    if STATUS["phase"] in ("downloading", "check"):
        return STATUS
    before = STATUS["phase"]
    STATUS.update(phase="check", error="")
    try:
        sheet, signature = _read("update.json", 65536), _read("update.json.sig", 4096)
        d = _verify(sheet, signature)
        if numbers(d["version"]) <= numbers(VERSION):
            STATUS.update(phase="updated", version="", notes="")
        elif before == "ready_now" and STATUS["version"] == d["version"]:
            STATUS.update(phase="ready_now")
        else:
            _sheet = {"data": d, "sheet": sheet, "signature": signature}
            STATUS.update(phase="available", version=d["version"], notes=str(d.get("notes", ""))[:600], completed=0, total=d["byte"])
    except urllib.error.HTTPError as ex:
        if ex.code == 404:   # nessuna versione pubblicata
            STATUS.update(phase="updated", version="", notes="")
        else:
            STATUS.update(phase="error", error=i18n.t("updates.error.page", code=ex.code))
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as ex:
        STATUS.update(phase="error", error=i18n.t("updates.error.check", reason=getattr(ex, "reason", ex)))
    except Error as ex:
        STATUS.update(phase="error", error=str(ex))
    STATUS["last_check"] = time.strftime("%Y-%m-%d %H:%M")
    return STATUS


def download():
    """Scarica l'installer della versione disponibile e lo tiene pronto, insieme al foglio firmato."""
    if not installable():
        raise Error(i18n.t("updates.error.not_by_itself"))
    if STATUS["phase"] != "available" or not _sheet:
        raise Error(i18n.t("updates.error.nothing"))
    if not _lock.acquire(blocking=False):
        return STATUS
    try:
        d = _sheet["data"]
        STATUS.update(phase="downloading", completed=0, total=d["byte"], error="")
        FOLDER.mkdir(parents=True, exist_ok=True)
        for old in FOLDER.iterdir():   # un solo aggiornamento per volta
            if old.name not in (d["file"], d["file"] + ".part"):
                old.unlink(missing_ok=True)
        weights.un_file(f"{ORIGIN}/{d['file']}", FOLDER / d["file"], {"byte": d["byte"], "sha256": d["sha256"]}, STATUS, "update")
        (FOLDER / "update.json").write_bytes(_sheet["sheet"])
        (FOLDER / "update.json.sig").write_bytes(_sheet["signature"])
        STATUS.update(phase="ready_now")
    except (weights.Error, OSError) as ex:
        STATUS.update(phase="error", error=str(ex))
    finally:
        _lock.release()
    return STATUS


def ready_now():
    """C'e' un installer gia' scaricato, autentico e piu' nuovo di questa versione? Controllo senza rete: rilegge la
    firma del foglio e l'impronta del file. Restituisce (percorso, versione) oppure None."""
    if not installable() or mode() == "never":
        return None
    try:
        d = _verify((FOLDER / "update.json").read_bytes(), (FOLDER / "update.json.sig").read_bytes())
        file = FOLDER / d["file"]
        if numbers(d["version"]) <= numbers(VERSION):   # gia' installato: si fa pulizia
            for old in FOLDER.iterdir():
                old.unlink(missing_ok=True)
            return None
        h = hashlib.sha256()
        with file.open("rb") as s:
            for chunk in iter(lambda: s.read(1 << 20), b""):
                h.update(chunk)
        if file.stat().st_size != d["byte"] or h.hexdigest() != d["sha256"]:
            file.unlink(missing_ok=True)
            return None
        return file, d["version"]
    except (OSError, Error):
        return None


def install(automatic=False):
    """Lancia l'installer scaricato, in silenzio: chiude il programma, lo sostituisce e lo riapre. Chi chiama deve
    poi fermare tutto e uscire. Restituisce la versione che sta per essere installata, o None se non c'era nulla.
    All'avvio (automatico=True) ogni versione viene tentata una volta sola: se l'installazione non riesce, il
    programma deve comunque partire, e si riprova dal pannello."""
    found = ready_now()
    if found is None:
        return None
    file, version = found
    attempted = FOLDER / "attempted.txt"
    if automatic and attempted.exists() and attempted.read_text(encoding="utf-8").strip() == version:
        return None
    attempted.write_text(version, encoding="utf-8")
    detached = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: deve sopravvivere a questo programma
    subprocess.Popen([str(file), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RIAVVIA=1"], creationflags=detached, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return version


def status():
    return {**STATUS, "current": VERSION, "channel": channel(), "mode": mode(), "installable": installable(), "page": PAGE}


def loop(after=45, every=86400):
    """Controllo periodico: poco dopo l'avvio e poi una volta al giorno, secondo l'impostazione."""
    time.sleep(after)
    while True:
        m = mode()
        if m in ("automatic", "notify"):
            try:
                check()
                if m == "automatic" and installable() and STATUS["phase"] == "available":
                    download()
            except Exception:   # noqa: BLE001  (un controllo fallito non deve mai fermare il programma)
                pass
        time.sleep(every)
