# -*- coding: utf-8 -*-
"""Prova lo scaricamento del modello e il controllo degli aggiornamenti contro un servizio finto in locale.

  .venv\\Scripts\\python.exe e2e_install.py

Non tocca il programma in uso: lavora in una cartella di dati temporanea, non scarica nulla da fuori e non lancia
nessun installer (il lancio e' sostituito da un finto che annota soltanto). La chiave delle firme e' creata al
momento, quindi la prova gira anche senza la chiave vera.
"""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TEMP = Path(tempfile.mkdtemp(prefix="omissis_prova_"))
PORTA = 9917
os.environ["OMISSIS_DATA"] = str(TEMP / "data")
os.environ["OMISSIS_LANG"] = "it"   # i controlli guardano anche i messaggi
os.environ["OMISSIS_MODELS_URL"] = f"http://127.0.0.1:{PORTA}/models"
os.environ["OMISSIS_UPDATES_URL"] = f"http://127.0.0.1:{PORTA}/versioni"

import updates   # noqa: E402
import weights         # noqa: E402
import paths        # noqa: E402
from cryptography.hazmat.primitives import serialization                         # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

SERVITI = {}      # percorso -> contenuto
RICHIESTE = []    # (percorso, intestazione Range)
esiti = []


def segna(nome, ok, nota=""):
    esiti.append(ok)
    print(("OK   " if ok else "NO   ") + nome + (f"  ({nota})" if nota else ""))


class Finto(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        dati = SERVITI.get(self.path)
        RICHIESTE.append((self.path, self.headers.get("Range")))
        if dati is None:
            self.send_response(404)
            self.end_headers()
            return
        intervallo, inizio = self.headers.get("Range"), 0
        if intervallo:
            inizio = int(intervallo.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {inizio}-{len(dati) - 1}/{len(dati)}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(dati) - inizio))
        self.end_headers()
        self.wfile.write(dati[inizio:])


def voce(dati):
    return {"byte": len(dati), "sha256": hashlib.sha256(dati).hexdigest()}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", PORTA), Finto)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # ------------------------------------------------------------ il modello
    pesi = {"config.json": b'{"id2label": {}}', "tokenizer.json": os.urandom(40_000), "model.onnx": os.urandom(3_500_000)}
    elenco = {"origine": "", "modelli": {"finto": {"revisione": "main", "file": {k: voce(v) for k, v in pesi.items()}}}}
    weights.elenco = lambda: elenco
    for k, v in pesi.items():
        SERVITI[f"/models/finto/{k}"] = v
    cartella = paths.DATI / "models" / "finto"

    segna("un modello che manca viene riconosciuto", weights.manca("finto") and weights.scaricabile("finto"))
    weights.scarica("finto")
    segna("scaricamento: file identici agli originali, modello pronto",
          all((cartella / k).read_bytes() == v for k, v in pesi.items()) and not weights.manca("finto") and weights.STATO["fase"] == "pronto"
          and weights.STATO["fatti"] == weights.STATO["totale"], f"{weights.STATO['fatti']} byte")

    RICHIESTE.clear()
    weights.scarica("finto")
    segna("file già presenti e integri: non si riscarica nulla", not RICHIESTE)

    (cartella / "model.onnx").unlink()
    (cartella / "model.onnx.parte").write_bytes(pesi["model.onnx"][:1_200_000])
    RICHIESTE.clear()
    weights.scarica("finto")
    segna("ripresa: si chiede solo la parte mancante e il file risulta integro",
          RICHIESTE == [("/models/finto/model.onnx", "bytes=1200000-")] and (cartella / "model.onnx").read_bytes() == pesi["model.onnx"], str(RICHIESTE))

    (cartella / "model.onnx").unlink()
    SERVITI["/models/finto/model.onnx"] = pesi["model.onnx"][:-1] + b"X"   # stesso peso, un byte diverso
    try:
        weights.scarica("finto")
        scartato = False
    except weights.Errore as ex:
        scartato = "non corrisponde" in str(ex)
    segna("file manomesso: scartato, il modello resta mancante", scartato and not (cartella / "model.onnx").exists()
          and not (cartella / "model.onnx.parte").exists() and weights.manca("finto") and weights.STATO["fase"] == "errore")

    SERVITI["/models/finto/model.onnx"] = pesi["model.onnx"] + b"in piu'"
    try:
        weights.scarica("finto")
        scartato = False
    except weights.Errore:
        scartato = True
    segna("file più grande del previsto: scartato", scartato and weights.manca("finto"))

    del SERVITI["/models/finto/model.onnx"]
    try:
        weights.scarica("finto")
        messaggio = ""
    except weights.Errore as ex:
        messaggio = str(ex)
    segna("modello non ancora pubblicato: errore chiaro", "non è ancora disponibile" in messaggio, messaggio)
    try:
        weights.scarica("sconosciuto")
        messaggio = ""
    except weights.Errore as ex:
        messaggio = str(ex)
    segna("modello fuori elenco: non si scarica nulla", "non è tra quelli" in messaggio)

    # ------------------------------------------------------------ gli aggiornamenti
    chiave, estranea = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    updates.CHIAVE_PUBBLICA = base64.b64encode(chiave.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode("ascii")
    attuale = updates.VERSIONE
    nuova = ".".join(str(x) for x in (*updates.numeri(attuale)[:-1], updates.numeri(attuale)[-1] + 1))
    installer = os.urandom(900_000)

    def pubblica(versione=nuova, file=None, con=chiave, ritocco=None, contenuto=installer):
        file = file or f"Omissis-{versione}-setup.exe"
        foglio = json.dumps({"prodotto": "omissis", "versione": versione, "file": file, **{"byte": len(installer), "sha256": hashlib.sha256(installer).hexdigest()},
                             "note": "prova"}).encode("utf-8")
        SERVITI["/versioni/update.json.sig"] = base64.b64encode(con.sign(foglio))
        SERVITI["/versioni/update.json"] = ritocco(foglio) if ritocco else foglio
        SERVITI[f"/versioni/{file}"] = contenuto
        updates.STATO.update(fase="mai", versione="", errore="")

    pubblica()
    updates.controlla()
    segna("versione nuova con firma valida: disponibile", updates.STATO["fase"] == "disponibile" and updates.STATO["versione"] == nuova)
    pubblica(versione=attuale)
    segna("stessa versione: nessun aggiornamento", updates.controlla()["fase"] == "aggiornato")
    pubblica(versione="0.0.1")
    segna("versione più vecchia: mai accettata", updates.controlla()["fase"] == "aggiornato")
    pubblica(con=estranea)
    segna("foglio firmato con un'altra chiave: ignorato", updates.controlla()["fase"] == "errore" and "firma" in updates.STATO["errore"])
    pubblica(ritocco=lambda f: f.replace(nuova.encode(), b"9.9.9"))
    segna("foglio ritoccato dopo la firma: ignorato", updates.controlla()["fase"] == "errore" and updates.STATO["versione"] == "")
    pubblica(file="..\\..\\fuori.exe")
    segna("nome di file con un percorso dentro: ignorato", updates.controlla()["fase"] == "errore")
    del SERVITI["/versioni/update.json"]
    updates.STATO.update(fase="mai")
    segna("nessuna versione pubblicata: nessun errore", updates.controlla()["fase"] == "aggiornato")

    pubblica()
    updates.controlla()
    try:
        updates.scarica()
        rifiutato = False
    except updates.Errore:
        rifiutato = True
    segna("copia dai sorgenti: avvisa ma non scarica e non installa", rifiutato and updates.pronto() is None and not updates.installabile())

    paths.INSTALLATA = {"versione": attuale, "canale": "github"}   # da qui in poi come una copia installata
    pubblica(contenuto=installer[:-1] + b"X")
    updates.controlla()
    updates.scarica()
    segna("installer manomesso: scartato", updates.STATO["fase"] == "errore" and updates.pronto() is None
          and not list(updates.CARTELLA.glob("*.exe")))
    pubblica()
    updates.controlla()
    updates.scarica()
    trovato = updates.pronto()
    segna("installer integro: scaricato e pronto, riconosciuto anche senza rete", updates.STATO["fase"] == "pronto" and trovato is not None
          and trovato[1] == nuova and trovato[0].read_bytes() == installer)

    lanciati = []
    vero = subprocess.Popen
    subprocess.Popen = lambda comando, **k: lanciati.append(comando)   # non si lancia nulla davvero
    try:
        prima = updates.installa(automatico=True)
        seconda = updates.installa(automatico=True)
        a_mano = updates.installa()
    finally:
        subprocess.Popen = vero
    segna("installazione: in silenzio, con riapertura; all'avvio una volta sola per versione, dal pannello sempre",
          prima == nuova and seconda is None and a_mano == nuova and len(lanciati) == 2
          and lanciati[0][1:] == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RIAVVIA=1"], str(lanciati[0][1:]) if lanciati else "")

    trovato[0].write_bytes(installer[:-1] + b"X")
    segna("installer sostituito sul disco dopo lo scaricamento: non viene lanciato", updates.pronto() is None and updates.installa() is None)

    impostazioni_vere = updates.settings.leggi
    updates.settings.leggi = lambda: {**impostazioni_vere(), "aggiornamenti": "mai"}
    segna("impostazione «mai»: nessuna installazione", updates.modalita() == "mai" and updates.pronto() is None)
    updates.settings.leggi = impostazioni_vere
    paths.INSTALLATA = {"versione": attuale, "canale": "store"}
    segna("copia dello Store: nessun controllo, ci pensa lo Store", updates.modalita() == "store" and not updates.installabile())

    server.shutdown()
    shutil.rmtree(TEMP, ignore_errors=True)
    print(f"\n{sum(esiti)}/{len(esiti)} controlli superati")
    sys.exit(0 if all(esiti) else 1)


if __name__ == "__main__":
    main()
