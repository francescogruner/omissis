# -*- coding: utf-8 -*-
"""Apre le pagine VERE dei servizi nel browser di prova con l'estensione caricata, senza accedere e
senza scrivere nulla: serve solo a vedere se la pagina si carica ancora con l'estensione attiva e
se le sue richieste passano dall'estensione (righe «via estensione» nel registro).

  .venv\\Scripts\\python.exe e2e_sites.py [indirizzo ...]        (richiede la protezione attiva)
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
import paths   # noqa: E402
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(HERE / ".playwright"))
from playwright.sync_api import sync_playwright   # noqa: E402

SITES = sys.argv[1:] or ["https://claude.ai/login", "https://chatgpt.com/", "https://gemini.google.com/", "https://www.perplexity.ai/",
                        "https://copilot.microsoft.com/", "https://chat.mistral.ai/", "https://chat.deepseek.com/"]


def lines():
    f = paths.DATA / "activity.jsonl"
    return f.read_text(encoding="utf-8").splitlines() if f.exists() else []


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    with sync_playwright() as pw, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        est = str(HERE / "extension")
        ctx = pw.chromium.launch_persistent_context(profile, channel="chromium", headless=True,
                                                    args=[f"--disable-extensions-except={est}", f"--load-extension={est}"])
        if not ctx.service_workers:
            ctx.wait_for_event("serviceworker", timeout=20000)
        pan = ctx.new_page()
        pan.goto("http://127.0.0.1:8766/")
        pan.click("nav button[data-s=browser]")
        pan.wait_for_function("document.getElementById('estStatus').textContent.includes('version')", timeout=10000)
        pan.click("#estConnect")
        pan.wait_for_function("/collegata$/.test(document.getElementById('estStatus').textContent)", timeout=15000)
        for site in SITES:
            before = len(lines())
            p = ctx.new_page()
            errors, console = [], []
            p.on("pageerror", lambda e: errors.append(str(e)[:160]))
            p.on("console", lambda m: console.append(m.text[:160]) if m.type == "error" else None)
            try:
                p.goto(site, timeout=40000, wait_until="domcontentloaded")
                p.wait_for_timeout(7000)
                title, arrival = p.title()[:50], p.url.split("?")[0][:70]
                text = len(p.inner_text("body"))
            except Exception as ex:   # noqa: BLE001
                title, arrival, text = "NON CARICATA: " + str(ex).splitlines()[0][:90], "", 0
            new_ones = [json.loads(r) for r in lines()[before:]]
            my = [v for v in new_ones if v.get("via") == "extension"]
            events = {}
            for v in my:
                events[v.get("event", "")] = events.get(v.get("event", ""), 0) + 1
            ours = [e for e in errors + console if "msp" in e.lower() or "chrome-extension" in e]
            print(f"{site}\n   arrivo: {arrival} · titolo: {title} · caratteri di testo: {text}"
                  f"\n   errori della pagina: {len(errors)} · errori in console: {len(console)} · riferiti all'estensione: {len(ours)}"
                  f"\n   richieste passate dall'estensione: {len(my)} {events if events else ''}", flush=True)
            for e in ours[:3]:
                print("      ", e)
            p.close()
        ctx.close()
    db = sqlite3.connect(paths.DATA / "contacts.sqlite")
    print("\ncontatti registrati oggi:", db.execute("SELECT service, outcome, n FROM contacts WHERE day = date('now','localtime') ORDER BY service").fetchall())


if __name__ == "__main__":
    main()
