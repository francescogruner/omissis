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

TEMP = Path(tempfile.mkdtemp(prefix="omissis_test_"))
PORT = 9917
os.environ["OMISSIS_DATA"] = str(TEMP / "data")
os.environ["OMISSIS_LANG"] = "it"   # i controlli guardano anche i messaggi
os.environ["OMISSIS_MODELS_URL"] = f"http://127.0.0.1:{PORT}/models"
os.environ["OMISSIS_UPDATES_URL"] = f"http://127.0.0.1:{PORT}/versioni"

import updates   # noqa: E402
import weights         # noqa: E402
import paths        # noqa: E402
from cryptography.hazmat.primitives import serialization                         # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

SERVED = {}      # percorso -> contenuto
REQUESTS = []    # (percorso, intestazione Range)
outcomes = []


def mark(name, ok, note=""):
    outcomes.append(ok)
    print(("OK   " if ok else "NO   ") + name + (f"  ({note})" if note else ""))


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        data = SERVED.get(self.path)
        REQUESTS.append((self.path, self.headers.get("Range")))
        if data is None:
            self.send_response(404)
            self.end_headers()
            return
        interval, start = self.headers.get("Range"), 0
        if interval:
            start = int(interval.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            self.send_response(200)
        self.send_header("Content-Length", str(len(data) - start))
        self.end_headers()
        self.wfile.write(data[start:])


def entry(data):
    return {"byte": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # ------------------------------------------------------------ il modello
    model_files = {"config.json": b'{"id2label": {}}', "tokenizer.json": os.urandom(40_000), "model.onnx": os.urandom(3_500_000)}
    listing = {"origin": "", "models": {"finto": {"revision": "main", "file": {k: entry(v) for k, v in model_files.items()}}}}
    weights.listing = lambda: listing
    for k, v in model_files.items():
        SERVED[f"/models/finto/{k}"] = v
    folder = paths.DATA / "models" / "finto"

    mark("un modello che manca viene riconosciuto", weights.missing("finto") and weights.downloadable("finto"))
    weights.download("finto")
    mark("scaricamento: file identici agli originali, modello pronto",
          all((folder / k).read_bytes() == v for k, v in model_files.items()) and not weights.missing("finto") and weights.STATUS["phase"] == "ready_now"
          and weights.STATUS["completed"] == weights.STATUS["total"], f"{weights.STATUS['completed']} byte")

    REQUESTS.clear()
    weights.download("finto")
    mark("file già presenti e integri: non si riscarica nulla", not REQUESTS)

    (folder / "model.onnx").unlink()
    (folder / "model.onnx.part").write_bytes(model_files["model.onnx"][:1_200_000])
    REQUESTS.clear()
    weights.download("finto")
    mark("ripresa: si chiede solo la parte mancante e il file risulta integro",
          REQUESTS == [("/models/finto/model.onnx", "bytes=1200000-")] and (folder / "model.onnx").read_bytes() == model_files["model.onnx"], str(REQUESTS))

    (folder / "model.onnx").unlink()
    SERVED["/models/finto/model.onnx"] = model_files["model.onnx"][:-1] + b"X"   # stesso peso, un byte diverso
    try:
        weights.download("finto")
        discarded = False
    except weights.Error as ex:
        discarded = "non corrisponde" in str(ex)
    mark("file manomesso: scartato, il modello resta mancante", discarded and not (folder / "model.onnx").exists()
          and not (folder / "model.onnx.part").exists() and weights.missing("finto") and weights.STATUS["phase"] == "error")

    SERVED["/models/finto/model.onnx"] = model_files["model.onnx"] + b"in piu'"
    try:
        weights.download("finto")
        discarded = False
    except weights.Error:
        discarded = True
    mark("file più grande del previsto: scartato", discarded and weights.missing("finto"))

    del SERVED["/models/finto/model.onnx"]
    try:
        weights.download("finto")
        message = ""
    except weights.Error as ex:
        message = str(ex)
    mark("modello non ancora pubblicato: errore chiaro", "non è ancora disponibile" in message, message)
    try:
        weights.download("unknown")
        message = ""
    except weights.Error as ex:
        message = str(ex)
    mark("modello fuori elenco: non si scarica nulla", "non è tra quelli" in message)

    # ------------------------------------------------------------ gli aggiornamenti
    key, foreign = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    updates.PUBLIC_KEY = base64.b64encode(key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode("ascii")
    current = updates.VERSION
    new_one = ".".join(str(x) for x in (*updates.numbers(current)[:-1], updates.numbers(current)[-1] + 1))
    installer = os.urandom(900_000)

    def public(version=new_one, file=None, con=key, tweak=None, content=installer):
        file = file or f"Omissis-{version}-setup.exe"
        sheet = json.dumps({"product": "omissis", "version": version, "file": file, **{"byte": len(installer), "sha256": hashlib.sha256(installer).hexdigest()},
                             "notes": "test"}).encode("utf-8")
        SERVED["/versioni/update.json.sig"] = base64.b64encode(con.sign(sheet))
        SERVED["/versioni/update.json"] = tweak(sheet) if tweak else sheet
        SERVED[f"/versioni/{file}"] = content
        updates.STATUS.update(phase="never", version="", error="")

    public()
    updates.check()
    mark("versione nuova con firma valida: disponibile", updates.STATUS["phase"] == "available" and updates.STATUS["version"] == new_one)
    public(version=current)
    mark("stessa versione: nessun aggiornamento", updates.check()["phase"] == "updated")
    public(version="0.0.1")
    mark("versione più vecchia: mai accettata", updates.check()["phase"] == "updated")
    public(con=foreign)
    mark("foglio firmato con un'altra chiave: ignorato", updates.check()["phase"] == "error" and "firma" in updates.STATUS["error"])
    public(tweak=lambda f: f.replace(new_one.encode(), b"9.9.9"))
    mark("foglio ritoccato dopo la firma: ignorato", updates.check()["phase"] == "error" and updates.STATUS["version"] == "")
    public(file="..\\..\\fuori.exe")
    mark("nome di file con un percorso dentro: ignorato", updates.check()["phase"] == "error")
    del SERVED["/versioni/update.json"]
    updates.STATUS.update(phase="never")
    mark("nessuna versione pubblicata: nessun errore", updates.check()["phase"] == "updated")

    public()
    updates.check()
    try:
        updates.download()
        refused = False
    except updates.Error:
        refused = True
    mark("copia dai sorgenti: avvisa ma non scarica e non installa", refused and updates.ready_now() is None and not updates.installable())

    paths.INSTALLED = {"version": current, "channel": "github"}   # da qui in poi come una copia installata
    public(content=installer[:-1] + b"X")
    updates.check()
    updates.download()
    mark("installer manomesso: scartato", updates.STATUS["phase"] == "error" and updates.ready_now() is None
          and not list(updates.FOLDER.glob("*.exe")))
    public()
    updates.check()
    updates.download()
    found = updates.ready_now()
    mark("installer integro: scaricato e pronto, riconosciuto anche senza rete", updates.STATUS["phase"] == "ready_now" and found is not None
          and found[1] == new_one and found[0].read_bytes() == installer)

    launched = []
    real = subprocess.Popen
    subprocess.Popen = lambda command, **k: launched.append(command)   # non si lancia nulla davvero
    try:
        before = updates.install(automatic=True)
        second = updates.install(automatic=True)
        by_hand = updates.install()
    finally:
        subprocess.Popen = real
    mark("installazione: in silenzio, con riapertura; all'avvio una volta sola per versione, dal pannello sempre",
          before == new_one and second is None and by_hand == new_one and len(launched) == 2
          and launched[0][1:] == ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RIAVVIA=1"], str(launched[0][1:]) if launched else "")

    found[0].write_bytes(installer[:-1] + b"X")
    mark("installer sostituito sul disco dopo lo scaricamento: non viene lanciato", updates.ready_now() is None and updates.install() is None)

    real_settings = updates.settings.read
    updates.settings.read = lambda: {**real_settings(), "updates": "never"}
    mark("impostazione «mai»: nessuna installazione", updates.mode() == "never" and updates.ready_now() is None)
    updates.settings.read = real_settings
    paths.INSTALLED = {"version": current, "channel": "store"}
    mark("copia dello Store: nessun controllo, ci pensa lo Store", updates.mode() == "store" and not updates.installable())

    # ------------------------------------------------------------ il foglio per il Mac
    # Qui non c'e' un Mac: si guarda solo cio' che non dipende dal sistema, cioe' quale foglio si legge e che cosa si
    # accetta. Lo scambio delle due versioni dentro l'app lo provano e2e_macapp.py e, sul Mac vero, packaging/mac.
    paths.INSTALLED = {"version": current, "channel": "github"}
    real_target = updates.target
    updates.target = lambda: "mac-arm64"
    try:
        image = os.urandom(300_000)

        def mac_sheet(platform="mac-arm64", file=None, name=None, con=key):
            file = file or f"Omissis-{new_one}-mac-arm64.dmg"
            sheet = json.dumps({"product": "omissis", "version": new_one, "platform": platform, "file": file, "byte": len(image),
                                "sha256": hashlib.sha256(image).hexdigest(), "notes": "test"}).encode("utf-8")
            for k in [k for k in SERVED if k.startswith("/versioni/")]:
                del SERVED[k]
            name = name or "update-mac-arm64.json"
            SERVED[f"/versioni/{name}.sig"] = base64.b64encode(con.sign(sheet))
            SERVED[f"/versioni/{name}"] = sheet
            SERVED[f"/versioni/{file}"] = image
            updates.STATUS.update(phase="never", version="", error="")
            REQUESTS.clear()

        mac_sheet()
        updates.check()
        mark("Mac: legge il suo foglio (update-mac-arm64.json), non quello di Windows",
              updates.STATUS["phase"] == "available" and updates.STATUS["version"] == new_one and [p for p, _ in REQUESTS][:1] == ["/versioni/update-mac-arm64.json"],
              str([p for p, _ in REQUESTS]))
        mac_sheet(name="update.json")
        mark("Mac: il foglio di Windows da solo non vale (nessuna versione per il Mac: nessun errore)", updates.check()["phase"] == "updated")
        mac_sheet(platform="mac-x86_64")
        mark("Mac: un foglio per un altro processore viene ignorato", updates.check()["phase"] == "error" and updates.STATUS["version"] == "")
        mac_sheet(file=f"Omissis-{new_one}-setup.exe")
        mark("Mac: un foglio che indica un installer di Windows viene ignorato", updates.check()["phase"] == "error")
        mac_sheet(con=foreign)
        mark("Mac: foglio firmato con un'altra chiave: ignorato", updates.check()["phase"] == "error" and "firma" in updates.STATUS["error"])
        mac_sheet()
        updates.check()
        mark("Mac: lo stato per la pagina dice per quale sistema si cercano le versioni e l'esito dell'ultimo scambio",
              updates.status()["platform"] == "mac-arm64" and updates.status()["failed"] == "" and "reason" in updates.status(),
              str({k: updates.status()[k] for k in ("platform", "reason", "failed")}))
    finally:
        updates.target = real_target

    # la chiave usa e getta delle prove vale solo in una copia di prova
    throwaway = base64.b64encode(foreign.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode("ascii")
    os.environ["OMISSIS_UPDATES_TEST_KEY"] = throwaway
    os.environ.pop("OMISSIS_TEST", None)
    ignored = updates._key() == updates.PUBLIC_KEY
    os.environ["OMISSIS_TEST"] = "1"
    taken = updates._key() == throwaway
    del os.environ["OMISSIS_UPDATES_TEST_KEY"], os.environ["OMISSIS_TEST"]
    mark("chiave di prova per le firme: accettata solo da una copia di prova, ignorata da una copia normale", ignored and taken)

    server.shutdown()
    shutil.rmtree(TEMP, ignore_errors=True)
    print(f"\n{sum(outcomes)}/{len(outcomes)} controlli superati")
    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
