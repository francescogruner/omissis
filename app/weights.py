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
from version import VERSIONE

QUI = Path(__file__).resolve().parent
PEZZO = 1 << 20
STATO = {"fase": "fermo", "nome": "", "fatti": 0, "totale": 0, "errore": ""}   # fermo | scarico | verifica | pronto | errore
_ferma = threading.Event()
_lucchetto = threading.Lock()


class Errore(Exception):
    pass


class Annullato(Errore):
    pass


def elenco():
    try:
        return json.loads((QUI / "weights.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"origine": "", "modelli": {}}


def manca(nome):
    """True se i pesi non ci sono (ne' in formato ONNX ne', per chi lavora dai sorgenti, in quello di PyTorch)."""
    c = paths.modello(nome)
    return not ((c / "config.json").exists() and (c / "tokenizer.json").exists()
                and ((c / "model.onnx").exists() or (c / "model.safetensors").exists()))


def scaricabile(nome):
    return nome in elenco()["modelli"]


def dimensione(nome):
    return sum(v["byte"] for v in elenco()["modelli"].get(nome, {}).get("file", {}).values())


def annulla():
    _ferma.set()


def _impronta(f):
    h, letti = hashlib.sha256(), 0
    with f.open("rb") as s:
        while True:
            pezzo = s.read(PEZZO)
            if not pezzo:
                break
            h.update(pezzo)
            letti += len(pezzo)
    return h, letti


def _indirizzo(origine, nome, voce, file):
    base = os.environ.get("OMISSIS_MODELS_URL")
    if base:
        return f"{base.rstrip('/')}/{nome}/{file}"
    return origine.format(nome=nome, revisione=voce.get("revisione", "main"), file=file)


def un_file(indirizzo, destinazione, atteso, STATO=STATO, cosa="modello", ferma=None):
    """Scarica un file riprendendo la parte gia' presente; lo consegna solo se dimensione e impronta coincidono.
    L'avanzamento va in STATO["fatti"]. Lo usa anche il controllo degli aggiornamenti."""
    if destinazione.exists() and destinazione.stat().st_size == atteso["byte"] and _impronta(destinazione)[0].hexdigest() == atteso["sha256"]:
        STATO["fatti"] += atteso["byte"]
        return
    parte = destinazione.with_name(destinazione.name + ".parte")
    if parte.exists() and parte.stat().st_size > atteso["byte"]:
        parte.unlink()
    h, gia = _impronta(parte) if parte.exists() else (hashlib.sha256(), 0)
    STATO["fatti"] += gia
    if gia < atteso["byte"]:
        if not indirizzo.startswith("https://") and not indirizzo.startswith("http://127.0.0.1"):
            raise Errore(i18n.t("modelli.errore.indirizzo"))
        rich = urllib.request.Request(indirizzo, headers={"User-Agent": f"Omissis/{VERSIONE}", **({"Range": f"bytes={gia}-"} if gia else {})})
        try:
            with urllib.request.urlopen(rich, timeout=60) as r, parte.open("ab" if gia and r.status == 206 else "wb") as s:
                if gia and r.status != 206:   # il servizio non riprende: si ricomincia da capo
                    STATO["fatti"] -= gia
                    h, gia = hashlib.sha256(), 0
                while True:
                    if ferma is not None and ferma.is_set():
                        raise Annullato(i18n.t("modelli.errore.interrotto"))
                    pezzo = r.read(PEZZO)
                    if not pezzo:
                        break
                    s.write(pezzo)
                    h.update(pezzo)
                    gia += len(pezzo)
                    STATO["fatti"] += len(pezzo)
                    if gia > atteso["byte"]:
                        raise Errore(i18n.t("modelli.errore.troppo_grande", file=destinazione.name))
        except urllib.error.HTTPError as ex:
            if ex.code == 404:
                raise Errore(i18n.t("modelli.errore.non_disponibile", cosa=i18n.t(f"modelli.cosa.{cosa}"))) from None
            raise Errore(i18n.t("modelli.errore.risposta", codice=ex.code)) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as ex:
            raise Errore(i18n.t("modelli.errore.collegamento", motivo=getattr(ex, "reason", ex))) from None
    if gia != atteso["byte"] or h.hexdigest() != atteso["sha256"]:
        parte.unlink(missing_ok=True)
        STATO["fatti"] -= gia
        raise Errore(i18n.t("modelli.errore.impronta", file=destinazione.name))
    parte.replace(destinazione)


def scarica(nome):
    """Porta i pesi di <nome> nella cartella dei dati. Si blocca finche' non ha finito; l'avanzamento e' in STATO."""
    voce = elenco()["modelli"].get(nome)
    if voce is None:
        raise Errore(i18n.t("modelli.errore.fuori_elenco", nome=nome))
    if not _lucchetto.acquire(blocking=False):
        raise Errore(i18n.t("modelli.errore.in_corso"))
    try:
        _ferma.clear()
        STATO.update(fase="scarico", nome=nome, fatti=0, totale=sum(v["byte"] for v in voce["file"].values()), errore="")
        cartella = paths.DATI / "models" / nome
        cartella.mkdir(parents=True, exist_ok=True)
        # i file piccoli prima: se l'indirizzo e' sbagliato lo si scopre subito
        for file, atteso in sorted(voce["file"].items(), key=lambda kv: kv[1]["byte"]):
            un_file(_indirizzo(elenco()["origine"], nome, voce, file), cartella / file, atteso, ferma=_ferma)
        STATO["fase"] = "pronto"
        return cartella
    except Errore as ex:
        STATO.update(fase="fermo" if isinstance(ex, Annullato) else "errore", errore="" if isinstance(ex, Annullato) else str(ex))
        raise
    except OSError as ex:
        STATO.update(fase="errore", errore=i18n.t("modelli.errore.scrittura", motivo=ex.strerror or ex))
        raise Errore(STATO["errore"]) from None
    finally:
        _lucchetto.release()


def stato(nome):
    return {**STATO, "manca": manca(nome), "scaricabile": scaricabile(nome), "byte": dimensione(nome)}
