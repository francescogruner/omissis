# -*- coding: utf-8 -*-
"""Variante da terminale di panel.py: stessa protezione, senza pagina. Mostra una riga per
ogni richiesta, utile per vedere subito cosa succede durante una prova. Ctrl+C ferma tutto.

  .venv\\Scripts\\python.exe start.py [--test]

Modello, porta, servizi protetti e le altre scelte si leggono da data\\settings.json
(le stesse del pannello). --test accetta anche il servizio finto in locale (per e2e_proxy.py).
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import catalog
import settings
import paths

HERE = Path(__file__).resolve().parent
PY_MODEL = paths.python_model()
ENGINE_PORT = paths.ENGINE_PORT


def status():
    token = (paths.DATA / "token.txt").read_text(encoding="utf-8").strip()
    req = urllib.request.Request(f"http://127.0.0.1:{ENGINE_PORT}/status", headers={"X-Token": token})
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", dest="test", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    paths.DATA.mkdir(parents=True, exist_ok=True)
    cfg = settings.read()
    model = str(paths.model(cfg["model"]))
    env = {**os.environ, "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
           "OMISSIS_ENGINE_URL": f"http://127.0.0.1:{ENGINE_PORT}"}
    if a.test:
        env["OMISSIS_TEST"] = "1"
    print("avvio il motore (carica il modello, qualche secondo)...")
    engine = subprocess.Popen([str(PY_MODEL), str(HERE / "engine.py"), "--model", model, "--port", str(ENGINE_PORT)]
                              + (["--device", cfg["device"]] if cfg["device"] in ("cpu", "cuda") else []),
                              env=env, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(180):
            if engine.poll() is not None:
                sys.exit("il motore non è partito: avviarlo a mano con engine.py per vedere l'errore")
            try:
                s = status()
                break
            except Exception:   # noqa: BLE001
                time.sleep(1)
        else:
            sys.exit("il motore non risponde")
        guarded = settings.guarded(cfg)
        print(f"motore pronto: {Path(s['model']).name} su {s['device']}, soglia {s['threshold']}")
        print("servizi protetti:", ", ".join(x["name"] for x in guarded))
        command = [*paths.mitmdump(), "-q", "-s", str(HERE / "addon.py"),
                   "--listen-host", "127.0.0.1", "-p", str(cfg["port"]), "--set", f"confdir={paths.DATA / 'ca'}"]
        for h in catalog.expressions_host(guarded):
            command += ["--allow-hosts", h]
        print(f"proxy in ascolto su 127.0.0.1:{cfg['port']} - Ctrl+C per fermare\n")
        subprocess.run(command, env=env, cwd=HERE)
    except KeyboardInterrupt:
        pass
    finally:
        engine.terminate()


if __name__ == "__main__":
    main()
