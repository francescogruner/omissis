# -*- coding: utf-8 -*-
"""Apre le pagine VERE dei servizi nel browser di prova con l'estensione caricata, senza accedere e
senza scrivere nulla: serve solo a vedere se la pagina si carica ancora con l'estensione attiva e
se le sue richieste passano dall'estensione (righe «via estensione» nel registro).

  .venv\\Scripts\\python.exe prova_siti.py [indirizzo ...]        (richiede la protezione attiva)
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

QUI = Path(__file__).resolve().parent
import percorsi   # noqa: E402
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(QUI / ".playwright"))
from playwright.sync_api import sync_playwright   # noqa: E402

SITI = sys.argv[1:] or ["https://claude.ai/login", "https://chatgpt.com/", "https://gemini.google.com/", "https://www.perplexity.ai/",
                        "https://copilot.microsoft.com/", "https://chat.mistral.ai/", "https://chat.deepseek.com/"]


def righe():
    f = percorsi.DATI / "registro.jsonl"
    return f.read_text(encoding="utf-8").splitlines() if f.exists() else []


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with sync_playwright() as pw, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profilo:
        est = str(QUI / "estensione")
        ctx = pw.chromium.launch_persistent_context(profilo, channel="chromium", headless=True,
                                                    args=[f"--disable-extensions-except={est}", f"--load-extension={est}"])
        if not ctx.service_workers:
            ctx.wait_for_event("serviceworker", timeout=20000)
        pan = ctx.new_page()
        pan.goto("http://127.0.0.1:8766/")
        pan.click("nav button[data-s=browser]")
        pan.wait_for_function("document.getElementById('estStato').textContent.includes('versione')", timeout=10000)
        pan.click("#estCollega")
        pan.wait_for_function("/collegata$/.test(document.getElementById('estStato').textContent)", timeout=15000)
        for sito in SITI:
            prima = len(righe())
            p = ctx.new_page()
            errori, console = [], []
            p.on("pageerror", lambda e: errori.append(str(e)[:160]))
            p.on("console", lambda m: console.append(m.text[:160]) if m.type == "error" else None)
            try:
                p.goto(sito, timeout=40000, wait_until="domcontentloaded")
                p.wait_for_timeout(7000)
                titolo, arrivo = p.title()[:50], p.url.split("?")[0][:70]
                testo = len(p.inner_text("body"))
            except Exception as ex:   # noqa: BLE001
                titolo, arrivo, testo = "NON CARICATA: " + str(ex).splitlines()[0][:90], "", 0
            nuove = [json.loads(r) for r in righe()[prima:]]
            mie = [v for v in nuove if v.get("via") == "estensione"]
            eventi = {}
            for v in mie:
                eventi[v.get("evento", "")] = eventi.get(v.get("evento", ""), 0) + 1
            nostri = [e for e in errori + console if "msp" in e.lower() or "chrome-extension" in e]
            print(f"{sito}\n   arrivo: {arrivo} · titolo: {titolo} · caratteri di testo: {testo}"
                  f"\n   errori della pagina: {len(errori)} · errori in console: {len(console)} · riferiti all'estensione: {len(nostri)}"
                  f"\n   richieste passate dall'estensione: {len(mie)} {eventi if eventi else ''}", flush=True)
            for e in nostri[:3]:
                print("      ", e)
            p.close()
        ctx.close()
    db = sqlite3.connect(percorsi.DATI / "contatti.sqlite")
    print("\ncontatti registrati oggi:", db.execute("SELECT servizio, esito, n FROM contatti WHERE giorno = date('now','localtime') ORDER BY servizio").fetchall())


if __name__ == "__main__":
    main()
