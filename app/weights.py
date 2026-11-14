# -*- coding: utf-8 -*-
"""Scarica i pesi del modello quando sul PC non ci sono (primo avvio di una copia installata).

I file arrivano dalla pagina pubblica del modello e vengono accettati solo se dimensione e impronta
SHA-256 sono quelle scritte in weights.json, che viaggia con il programma: un file diverso da quello
con cui questa versione e' stata provata non viene usato, da qualunque parte arrivi.
Lo scaricamento riprende da dove si era fermato. Non viene inviato nulla: sono semplici letture.

  OMISSIS_MODELS_URL   altro indirizzo da cui scaricare (per le prove, o per una copia interna aziendale).
                        Le impronte valgono lo stesso.
"""
import hashlib
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path

import i18n
import paths
from version import VERSION

HERE = Path(__file__).resolve().parent
CHUNK = 1 << 20
STATUS = {"phase": "stopped", "name": "", "completed": 0, "total": 0, "error": ""}   # fermo | scarico | verifica | pronto | errore
_stop = threading.Event()
_lock = threading.Lock()


class Error(Exception):
    pass


class Cancelled(Error):
    pass


def listing():
    try:
        return json.loads((HERE / "weights.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"origin": "", "models": {}}


def missing(name):
    """True se i pesi non ci sono (ne' in formato ONNX ne', per chi lavora dai sorgenti, in quello di PyTorch)."""
    c = paths.model(name)
    return not ((c / "config.json").exists() and (c / "tokenizer.json").exists()
                and ((c / "model.onnx").exists() or (c / "model.safetensors").exists()))


def downloadable(name):
    return name in listing()["models"]


def size(name):
    return sum(v["byte"] for v in listing()["models"].get(name, {}).get("file", {}).values())


def cancel():
    _stop.set()


def _fingerprint(f):
    h, read_items = hashlib.sha256(), 0
    with f.open("rb") as s:
        while True:
            chunk = s.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            read_items += len(chunk)
    return h, read_items


def _address(origin, name, entry, file):
    base = os.environ.get("OMISSIS_MODELS_URL")
    if base:
        return f"{base.rstrip('/')}/{name}/{file}"
    return origin.format(name=name, revision=entry.get("revision", "main"), file=file)


def un_file(address, destination, expected, STATUS=STATUS, what="model", stop=None):
    """Scarica un file riprendendo la parte gia' presente; lo consegna solo se dimensione e impronta coincidono.
    L'avanzamento va in STATO["fatti"]. Lo usa anche il controllo degli aggiornamenti."""
    if destination.exists() and destination.stat().st_size == expected["byte"] and _fingerprint(destination)[0].hexdigest() == expected["sha256"]:
        STATUS["completed"] += expected["byte"]
        return
    part = destination.with_name(destination.name + ".part")
    if part.exists() and part.stat().st_size > expected["byte"]:
        part.unlink()
    h, already = _fingerprint(part) if part.exists() else (hashlib.sha256(), 0)
    STATUS["completed"] += already
    if already < expected["byte"]:
        if not address.startswith("https://") and not address.startswith("http://127.0.0.1"):
            raise Error(i18n.t("models.error.address"))
        req = urllib.request.Request(address, headers={"User-Agent": f"Omissis/{VERSION}", **({"Range": f"bytes={already}-"} if already else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as r, part.open("ab" if already and r.status == 206 else "wb") as s:
                if already and r.status != 206:   # il servizio non riprende: si ricomincia da capo
                    STATUS["completed"] -= already
                    h, already = hashlib.sha256(), 0
                while True:
                    if stop is not None and stop.is_set():
                        raise Cancelled(i18n.t("models.error.interrupted"))
                    chunk = r.read(CHUNK)
                    if not chunk:
                        break
                    s.write(chunk)
                    h.update(chunk)
                    already += len(chunk)
                    STATUS["completed"] += len(chunk)
                    if already > expected["byte"]:
                        raise Error(i18n.t("models.error.too_large", file=destination.name))
        except urllib.error.HTTPError as ex:
            if ex.code == 404:
                raise Error(i18n.t("models.error.not_available", what=i18n.t(f"models.what.{what}"))) from None
            raise Error(i18n.t("models.error.response", code=ex.code)) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as ex:
            raise Error(i18n.t("models.error.connection", reason=getattr(ex, "reason", ex))) from None
    if already != expected["byte"] or h.hexdigest() != expected["sha256"]:
        part.unlink(missing_ok=True)
        STATUS["completed"] -= already
        raise Error(i18n.t("models.error.fingerprint", file=destination.name))
    part.replace(destination)


def download(name):
    """Porta i pesi di <nome> nella cartella dei dati. Si blocca finche' non ha finito; l'avanzamento e' in STATO."""
    entry = listing()["models"].get(name)
    if entry is None:
        raise Error(i18n.t("models.error.outside_listing", name=name))
    if not _lock.acquire(blocking=False):
        raise Error(i18n.t("models.error.pending"))
    try:
        _stop.clear()
        STATUS.update(phase="downloading", name=name, completed=0, total=sum(v["byte"] for v in entry["file"].values()), error="")
        folder = paths.DATA / "models" / name
        folder.mkdir(parents=True, exist_ok=True)
        # i file piccoli prima: se l'indirizzo e' sbagliato lo si scopre subito
        for file, expected in sorted(entry["file"].items(), key=lambda kv: kv[1]["byte"]):
            un_file(_address(listing()["origin"], name, entry, file), folder / file, expected, stop=_stop)
        STATUS["phase"] = "ready_now"
        return folder
    except Error as ex:
        STATUS.update(phase="stopped" if isinstance(ex, Cancelled) else "error", error="" if isinstance(ex, Cancelled) else str(ex))
        raise
    except OSError as ex:
        STATUS.update(phase="error", error=i18n.t("models.error.writing", reason=ex.strerror or ex))
        raise Error(STATUS["error"]) from None
    finally:
        _lock.release()


def status(name):
    return {**STATUS, "missing": missing(name), "downloadable": downloadable(name), "byte": size(name)}
