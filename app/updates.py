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

Ogni sistema ha il suo foglio e il suo tipo di file, firmati con la stessa chiave:
  Windows   update.json             un installer (.exe), lanciato in silenzio: chiude, sostituisce e riapre
  Mac       update-mac-arm64.json   l'immagine disco (.dmg) della pagina delle versioni. Appena scaricata viene
                                    scompattata e controllata accanto alla versione in uso (macapp.unpack); lo scambio
                                    avviene a programma chiuso, e se la versione nuova non parte torna quella di prima
Sul Mac si aggiorna da sola solo l'app che sta in un posto suo (di solito Applicazioni): aperta dal disco di
installazione non puo' sostituirsi, e il pannello propone di spostarla.

  OMISSIS_UPDATES_URL        altro indirizzo da cui leggere (prove, o copia interna aziendale): la firma vale lo stesso
  OMISSIS_UPDATES_TEST_KEY   solo in una copia di prova (OMISSIS_TEST=1): la chiave pubblica, usa e getta, con cui la
                             prova firma i suoi fogli. Una copia normale la ignora
"""
import base64
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import settings
import i18n
import macapp
import sistema
import weights
import paths
from version import VERSION

PUBLIC_KEY = "FTc5/hItV90nAewMfdnTO7X4CgDXLyerwg5ks8fMFIc="
ORIGIN = (os.environ.get("OMISSIS_UPDATES_URL") or "https://github.com/francescogruner/omissis/releases/latest/download").rstrip("/")
PAGE = "https://github.com/francescogruner/omissis/releases/latest"
FOLDER = paths.DATA / "updates"
RX_FILE = re.compile(r"^[A-Za-z0-9][\w.-]{3,80}\.exe$")
# fuori da Windows: l'immagine disco del Mac; su Linux (solo prove) un archivio tar con dentro la stessa cartella
RX_PACKAGE = {"mac": re.compile(r"^[A-Za-z0-9][\w.-]{3,80}\.dmg$"), "linux": re.compile(r"^[A-Za-z0-9][\w.-]{3,80}\.tar\.gz$")}
RX_VERSION = re.compile(r"^\d{1,4}(\.\d{1,4}){1,3}$")
# fase: mai | controllo | aggiornato | disponibile | scarico | preparo (solo Mac) | pronto | errore
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


def target():
    """Per quale sistema si cercano gli aggiornamenti: windows | mac-arm64 | mac-x86_64 (linux-...: solo nelle prove)."""
    if sistema.WINDOWS:
        return "windows"
    return f"{'mac' if sistema.MAC else 'linux'}-{'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'x86_64'}"


def sheet_name():
    """Il foglio da leggere nella pagina delle versioni. Quello di Windows tiene il nome di sempre: lo cercano le
    copie gia' installate."""
    return "update.json" if target() == "windows" else f"update-{target()}.json"


def installable():
    """Questa copia puo' sostituirsi da sola? Su Windows quella messa dall'installer; sul Mac l'app che sta in un posto
    suo, dove chi usa il Mac puo' scrivere."""
    if channel() != "github":
        return False
    return True if sistema.WINDOWS else macapp.location() == "ok"


def reason():
    """Perche' questa copia non si aggiorna da sola: "" (si aggiorna) | store | source_code | move | locked."""
    if installable():
        return ""
    where = macapp.location()   # sul Mac conta prima di tutto dove sta l'app
    return where if where in ("move", "locked") else channel() if channel() != "github" else "source_code"


def _key():
    """La chiave pubblica con cui si controllano le firme. Solo una copia di prova accetta quella, usa e getta, che la
    prova le indica: cosi' tutto il giro si prova senza la chiave vera, che non lascia mai il PC di chi pubblica."""
    test = os.environ.get("OMISSIS_UPDATES_TEST_KEY")
    return test if test and os.environ.get("OMISSIS_TEST") == "1" else PUBLIC_KEY


def _verify(sheet, signature):
    """Il foglio e' autentico? Restituisce il contenuto, o solleva Errore."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        raise Error(i18n.t("updates.error.library")) from None
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(_key())).verify(base64.b64decode(signature.strip(), validate=True), sheet)
        d = json.loads(sheet.decode("utf-8"))
    except (InvalidSignature, ValueError):
        raise Error(i18n.t("updates.error.signature")) from None
    rx_file = RX_FILE if target() == "windows" else RX_PACKAGE[target().split("-")[0]]
    if (not isinstance(d, dict) or d.get("product") != "omissis" or not RX_VERSION.match(str(d.get("version", "")))
            or not rx_file.match(str(d.get("file", ""))) or not re.fullmatch(r"[0-9a-f]{64}", str(d.get("sha256", "")))
            or not isinstance(d.get("byte"), int) or not 0 < d["byte"] < 2_000_000_000):
        raise Error(i18n.t("updates.error.fmt"))
    # fuori da Windows il foglio dice per quale sistema e': quello di un altro processore non si installa qui
    if target() != "windows" and d.get("platform") != target():
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
    if STATUS["phase"] in ("downloading", "check", "preparing"):
        return STATUS
    before = STATUS["phase"]
    STATUS.update(phase="check", error="")
    try:
        sheet, signature = _read(sheet_name(), 65536), _read(sheet_name() + ".sig", 4096)
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
            if old.name not in (d["file"], d["file"] + ".part") and (sistema.WINDOWS or old.name not in _NOTES):
                old.unlink(missing_ok=True)
        weights.un_file(f"{ORIGIN}/{d['file']}", FOLDER / d["file"], {"byte": d["byte"], "sha256": d["sha256"]}, STATUS, "update")
        (FOLDER / "update.json").write_bytes(_sheet["sheet"])
        (FOLDER / "update.json.sig").write_bytes(_sheet["signature"])
        if not sistema.WINDOWS:   # sul Mac la versione nuova si scompatta e si controlla subito: lo scambio sara' un attimo
            STATUS.update(phase="preparing")
            _prepare(FOLDER / d["file"], d)
        STATUS.update(phase="ready_now")
    except (weights.Error, OSError) as ex:
        STATUS.update(phase="error", error=str(ex))
    except macapp.Error as ex:
        STATUS.update(phase="error", error=_mac_error(ex))
    finally:
        _lock.release()
    return STATUS


# fuori da Windows, accanto al pacchetto: l'esito dell'ultimo scambio e cio' che serve a farlo (non si cancellano a ogni scaricamento)
_NOTES = ("result.txt", "attempted.txt", "started.txt", "swap.sh", "relaunch.sh", "relaunch.log")


def _mac_error(ex):
    return i18n.t(f"updates.error.mac.{ex.code if ex.code in ('space', 'package', 'python', 'swap') else 'swap'}")


def _prepare(file, d):
    """Sul Mac: la versione nuova scompattata e controllata accanto a quella in uso (se non c'e' gia')."""
    b = macapp.bundle()
    if b is None:
        raise macapp.Error("swap", "not_an_app")
    if not macapp.prepared(b, d["version"], d["sha256"]):
        macapp.unpack(file, b, d["version"], d["sha256"])


def relaunch_arguments():
    """Con che opzioni riaprire il programma dopo lo scambio: quelle di adesso, e senza aprire il browser."""
    return [*[a for a in sys.argv[1:] if a.startswith("--") and a != "--no-browser"], "--no-browser"]


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
                if sistema.WINDOWS or old.name not in _NOTES:   # sul Mac chi ha fatto lo scambio sta ancora scrivendo l'esito
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
    if not sistema.WINDOWS:
        # Mac: la versione nuova e' gia' scompattata accanto a quella in uso (se manca, la si rifa' adesso). Lo scambio
        # lo fa un piccolo programma a parte, che aspetta la chiusura di questo e poi riapre l'app.
        try:
            _prepare(file, json.loads((FOLDER / "update.json").read_bytes()))
            # quanto aspettare che la versione nuova parta, prima di rimettere quella di prima: due minuti (le prove
            # automatiche ne chiedono meno, e solo a una copia di prova)
            wait = os.environ.get("OMISSIS_SWAP_WAIT", "") if os.environ.get("OMISSIS_TEST") == "1" else ""
            macapp.swap(macapp.bundle(), version, FOLDER, relaunch_arguments(), seconds=int(wait) if wait.isdigit() else 120)
        except macapp.Error as ex:
            STATUS.update(phase="error", error=_mac_error(ex))
            return None
        return version
    detached = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP: deve sopravvivere a questo programma
    subprocess.Popen([str(file), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RIAVVIA=1"], creationflags=detached, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return version


def started():
    """Sul Mac la versione appena partita lo scrive: chi ha fatto lo scambio (macapp.swap) aspetta questo file per
    decidere se tenerla o rimettere quella di prima."""
    if sistema.WINDOWS or not installable():
        return
    try:
        FOLDER.mkdir(parents=True, exist_ok=True)
        (FOLDER / "started.txt").write_text(VERSION + "\n", encoding="utf-8")
    except OSError:
        pass


def failed():
    """Sul Mac: la versione il cui scambio non e' riuscito (e' rimasta quella di prima), o ""."""
    if sistema.WINDOWS:
        return ""
    found = macapp.outcome(FOLDER)
    if not found or found[0] == "ok" or not RX_VERSION.match(found[1]):
        return ""
    return found[1] if numbers(found[1]) > numbers(VERSION) else ""


def status():
    return {**STATUS, "current": VERSION, "channel": channel(), "mode": mode(), "installable": installable(), "page": PAGE,
            "platform": target(), "reason": reason(), "failed": failed()}


def loop(after=45, every=86400):
    """Controllo periodico: poco dopo l'avvio e poi una volta al giorno, secondo l'impostazione."""
    time.sleep(after)
    while True:
        m = mode()
        if m in ("automatic", "notify"):
            try:
                check()
                # sul Mac una versione che non e' partita (e' tornata quella di prima) non si riscarica da sola a
                # ogni avvio: resta «disponibile», e si riprova dal pannello
                if m == "automatic" and installable() and STATUS["phase"] == "available" and STATUS["version"] != failed():
                    download()
            except Exception:   # noqa: BLE001  (un controllo fallito non deve mai fermare il programma)
                pass
        time.sleep(every)
