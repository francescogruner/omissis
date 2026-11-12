# -*- coding: utf-8 -*-
"""Variante da terminale di pannello.py: stessa protezione, senza pagina. Mostra una riga per
ogni richiesta, utile per vedere subito cosa succede durante una prova. Ctrl+C ferma tutto.

  .venv\\Scripts\\python.exe avvia.py [--prova]

Modello, porta, servizi protetti e le altre scelte si leggono da dati\\impostazioni.json
(le stesse del pannello). --prova accetta anche il servizio finto in locale (per prova.py).
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import catalogo
import impostazioni
import percorsi

QUI = Path(__file__).resolve().parent
PY_MODELLO = percorsi.python_modello()
PORTA_MOTORE = percorsi.PORTA_MOTORE


def stato():
    token = (percorsi.DATI / "token.txt").read_text(encoding="utf-8").strip()
    rich = urllib.request.Request(f"http://127.0.0.1:{PORTA_MOTORE}/stato", headers={"X-Token": token})
    with urllib.request.urlopen(rich, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prova", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    percorsi.DATI.mkdir(parents=True, exist_ok=True)
    imp = impostazioni.leggi()
    modello = str(percorsi.modello(imp["modello"]))
    amb = {**os.environ, "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "MSP_MOTORE": f"http://127.0.0.1:{PORTA_MOTORE}"}
    if a.prova:
        amb["MSP_PROVA"] = "1"
    print("avvio il motore (carica il modello, qualche secondo)...")
    motore = subprocess.Popen([str(PY_MODELLO), str(QUI / "motore.py"), "--modello", modello, "--porta", str(PORTA_MOTORE)]
                              + (["--device", imp["device"]] if imp["device"] in ("cpu", "cuda") else []),
                              env=amb, cwd=QUI, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(180):
            if motore.poll() is not None:
                sys.exit("il motore non è partito: avviarlo a mano con motore.py per vedere l'errore")
            try:
                s = stato()
                break
            except Exception:   # noqa: BLE001
                time.sleep(1)
        else:
            sys.exit("il motore non risponde")
        protetti = impostazioni.protetti(imp)
        print(f"motore pronto: {Path(s['modello']).name} su {s['device']}, soglia {s['soglia']}")
        print("servizi protetti:", ", ".join(x["nome"] for x in protetti))
        comando = [*percorsi.mitmdump(), "-q", "-s", str(QUI / "addon.py"),
                   "--listen-host", "127.0.0.1", "-p", str(imp["porta"]), "--set", f"confdir={percorsi.DATI / 'ca'}"]
        for h in catalogo.espressioni_host(protetti):
            comando += ["--allow-hosts", h]
        print(f"proxy in ascolto su 127.0.0.1:{imp['porta']} - Ctrl+C per fermare\n")
        subprocess.run(comando, env=amb, cwd=QUI)
    except KeyboardInterrupt:
        pass
    finally:
        motore.terminate()


if __name__ == "__main__":
    main()
