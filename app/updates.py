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
from version import VERSIONE

CHIAVE_PUBBLICA = "FTc5/hItV90nAewMfdnTO7X4CgDXLyerwg5ks8fMFIc="
ORIGINE = (os.environ.get("OMISSIS_UPDATES_URL") or "https://github.com/francescogruner/omissis/releases/latest/download").rstrip("/")
PAGINA = "https://github.com/francescogruner/omissis/releases/latest"
CARTELLA = paths.DATI / "updates"
RX_FILE = re.compile(r"^[A-Za-z0-9][\w.-]{3,80}\.exe$")
RX_VERSIONE = re.compile(r"^\d{1,4}(\.\d{1,4}){1,3}$")
# fase: mai | controllo | aggiornato | disponibile | scarico | pronto | errore
STATO = {"fase": "mai", "versione": "", "note": "", "errore": "", "controllato": "", "fatti": 0, "totale": 0}
_foglio = {}
_lucchetto = threading.Lock()


class Errore(Exception):
    pass


def numeri(v):
    return tuple(int(x) for x in v.split("."))


def canale():
    """github (installer, si aggiorna da solo) | store (ci pensa lo Store) | sorgenti."""
    return (paths.INSTALLATA or {}).get("canale") or "sorgenti"


def modalita():
    if canale() == "store":
        return "store"
    scelta = settings.leggi().get("aggiornamenti", "automatici")
    return scelta if scelta in ("automatici", "avvisa", "mai") else "automatici"


def installabile():
    return canale() == "github" and sys.platform == "win32"


def _verifica(foglio, firma):
    """Il foglio e' autentico? Restituisce il contenuto, o solleva Errore."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        raise Errore(i18n.t("aggiornamenti.errore.libreria")) from None
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(CHIAVE_PUBBLICA)).verify(base64.b64decode(firma.strip(), validate=True), foglio)
        d = json.loads(foglio.decode("utf-8"))
    except (InvalidSignature, ValueError):
        raise Errore(i18n.t("aggiornamenti.errore.firma")) from None
    if (not isinstance(d, dict) or d.get("prodotto") != "omissis" or not RX_VERSIONE.match(str(d.get("versione", "")))
            or not RX_FILE.match(str(d.get("file", ""))) or not re.fullmatch(r"[0-9a-f]{64}", str(d.get("sha256", "")))
            or not isinstance(d.get("byte"), int) or not 0 < d["byte"] < 2_000_000_000):
        raise Errore(i18n.t("aggiornamenti.errore.formato"))
    return d


def _leggi(nome, massimo):
    indirizzo = f"{ORIGINE}/{nome}"
    if not indirizzo.startswith("https://") and not indirizzo.startswith("http://127.0.0.1"):
        raise Errore(i18n.t("aggiornamenti.errore.indirizzo"))
    rich = urllib.request.Request(indirizzo, headers={"User-Agent": f"Omissis/{VERSIONE}"})
    with urllib.request.urlopen(rich, timeout=30) as r:
        dati = r.read(massimo + 1)
    if len(dati) > massimo:
        raise Errore(i18n.t("aggiornamenti.errore.grande"))
    return dati


def controlla():
    """Legge e verifica il foglio. Aggiorna STATO e lo restituisce."""
    global _foglio
    if STATO["fase"] in ("scarico", "controllo"):
        return STATO
    prima = STATO["fase"]
    STATO.update(fase="controllo", errore="")
    try:
        foglio, firma = _leggi("update.json", 65536), _leggi("update.json.sig", 4096)
        d = _verifica(foglio, firma)
        if numeri(d["versione"]) <= numeri(VERSIONE):
            STATO.update(fase="aggiornato", versione="", note="")
        elif prima == "pronto" and STATO["versione"] == d["versione"]:
            STATO.update(fase="pronto")
        else:
            _foglio = {"dati": d, "foglio": foglio, "firma": firma}
            STATO.update(fase="disponibile", versione=d["versione"], note=str(d.get("note", ""))[:600], fatti=0, totale=d["byte"])
    except urllib.error.HTTPError as ex:
        if ex.code == 404:   # nessuna versione pubblicata
            STATO.update(fase="aggiornato", versione="", note="")
        else:
            STATO.update(fase="errore", errore=i18n.t("aggiornamenti.errore.pagina", codice=ex.code))
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as ex:
        STATO.update(fase="errore", errore=i18n.t("aggiornamenti.errore.controllo", motivo=getattr(ex, "reason", ex)))
    except Errore as ex:
        STATO.update(fase="errore", errore=str(ex))
    STATO["controllato"] = time.strftime("%Y-%m-%d %H:%M")
    return STATO


def scarica():
    """Scarica l'installer della versione disponibile e lo tiene pronto, insieme al foglio firmato."""
    if not installabile():
        raise Errore(i18n.t("aggiornamenti.errore.non_da_sola"))
    if STATO["fase"] != "disponibile" or not _foglio:
        raise Errore(i18n.t("aggiornamenti.errore.niente"))
    if not _lucchetto.acquire(blocking=False):
        return STATO
    try:
        d = _foglio["dati"]
        STATO.update(fase="scarico", fatti=0, totale=d["byte"], errore="")
        CARTELLA.mkdir(parents=True, exist_ok=True)
        for vecchio in CARTELLA.iterdir():   # un solo aggiornamento per volta
            if vecchio.name not in (d["file"], d["file"] + ".parte"):
                vecchio.unlink(missing_ok=True)
        weights.un_file(f"{ORIGINE}/{d['file']}", CARTELLA / d["file"], {"byte": d["byte"], "sha256": d["sha256"]}, STATO, "aggiornamento")
        (CARTELLA / "update.json").write_bytes(_foglio["foglio"])
        (CARTELLA / "update.json.sig").write_bytes(_foglio["firma"])
        STATO.update(fase="pronto")
    except (weights.Errore, OSError) as ex:
        STATO.update(fase="errore", errore=str(ex))
    finally:
        _lucchetto.release()
    return STATO


def pronto():
    """C'e' un installer gia' scaricato, autentico e piu' nuovo di questa versione? Controllo senza rete: rilegge la
    firma del foglio e l'impronta del file. Restituisce (percorso, versione) oppure None."""
    if not installabile() or modalita() == "mai":
        return None
    try:
        d = _verifica((CARTELLA / "update.json").read_bytes(), (CARTELLA / "update.json.sig").read_bytes())
        file = CARTELLA / d["file"]
        if numeri(d["versione"]) <= numeri(VERSIONE):   # gia' installato: si fa pulizia
            for vecchio in CARTELLA.iterdir():
                vecchio.unlink(missing_ok=True)
            return None
        h = hashlib.sha256()
        with file.open("rb") as s:
            for pezzo in iter(lambda: s.read(1 << 20), b""):
                h.update(pezzo)
        if file.stat().st_size != d["byte"] or h.hexdigest() != d["sha256"]:
            file.unlink(missing_ok=True)
            return None
        return file, d["versione"]
    except (OSError, Errore):
        return None


def installa(automatico=False):
    """Lancia l'installer scaricato, in silenzio: chiude il programma, lo sostituisce e lo riapre. Chi chiama deve
    poi fermare tutto e uscire. Restituisce la versione che sta per essere installata, o None se non c'era nulla.
    All'avvio (automatico=True) ogni versione viene tentata una volta sola: se l'installazione non riesce, il
    programma deve comunque partire, e si riprova dal pannello."""
    trovato = pronto()
    if trovato is None:
        return None
    file, versione = trovato
    tentato = CARTELLA / "attempted.txt"
    if automatico and tentato.exists() and tentato.read_text(encoding="utf-8").strip() == versione:
        return None
    tentato.write_text(versione, encoding="utf-8")
    staccato = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: deve sopravvivere a questo programma
    subprocess.Popen([str(file), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RIAVVIA=1"], creationflags=staccato, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return versione


def stato():
    return {**STATO, "attuale": VERSIONE, "canale": canale(), "modalita": modalita(), "installabile": installabile(), "pagina": PAGINA}


def ciclo(dopo=45, ogni=86400):
    """Controllo periodico: poco dopo l'avvio e poi una volta al giorno, secondo l'impostazione."""
    time.sleep(dopo)
    while True:
        m = modalita()
        if m in ("automatici", "avvisa"):
            try:
                controlla()
                if m == "automatici" and installabile() and STATO["fase"] == "disponibile":
                    scarica()
            except Exception:   # noqa: BLE001  (un controllo fallito non deve mai fermare il programma)
                pass
        time.sleep(ogni)
