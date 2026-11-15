# -*- coding: utf-8 -*-
"""Prova il server di inferenza in rete (remote.py) con due copie del programma su questo PC e dati inventati.

Il «server» e' la copia di prova gia' accesa (panel.py --test, come per le altre prove): le si fa prestare il modello.
Il «PC» e' un secondo motore lanciato qui, con una cartella di dati provvisoria e SENZA modello: chiede il
riconoscimento al primo, attraverso HTTPS su 127.0.0.1, con la chiave e l'impronta del certificato.

  python e2e_remote.py [--no-page]

Controlla che dal PC escano solo segnaposto, che regole, elenchi e archivio restino sul PC, che il server non scriva
nulla di cio' che riceve, che chiave e impronta sbagliate vengano rifiutate, e che a server spento non parta nulla.
Alla fine il server torna com'era. --no-page salta i controlli sulla pagina (italiano e inglese).
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
import paths   # noqa: E402
import remote   # noqa: E402

PANEL = f"http://127.0.0.1:{paths.PANEL_PORT}"
TEXT = ("Buongiorno, sono Giulia Ferraresi della Nevatek S.r.l. Per il Progetto Zefiro mi può scrivere a "
        "giulia.ferraresi@nevatek.example o chiamare il 347 5551234.")
outcomes = []


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(f"{'OK    ' if ok else 'ERRORE'} {name}" + (f"   {note}" if note else ""), flush=True)


def call(url, headers, data=None, timeout=120):
    req = urllib.request.Request(url, headers={**headers, "Content-Type": "application/json"},
                                 data=None if data is None else json.dumps(data).encode("utf-8"))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_until(condition, timeout=240, every=1.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if condition():
                return True
        except Exception:   # noqa: BLE001  (durante un riavvio il motore non risponde: si riprova)
            pass
        time.sleep(every)
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    code = re.search(r'name="omissis-code" content="([^"]+)"', urllib.request.urlopen(PANEL + "/", timeout=20).read().decode("utf-8")).group(1)
    panel = lambda path, data=None: call(PANEL + path, {"X-Panel": code}, data)   # noqa: E731
    if panel("/api/status")["phase"] != "active":
        sys.exit("la protezione della copia di prova non è attiva: avviarla prima")
    before = panel("/api/server")
    if before["mode"] != "local":
        sys.exit("la copia di prova sta già usando o facendo un server di inferenza: riportarla com'era prima")
    log = paths.DATA / "activity.jsonl"
    log_lines = len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0
    client = None
    try:
        # ---- il server: presta il modello
        mark("di serie nessun PC presta il modello: la porta del server è chiusa", not remote.shared() and socket.socket().connect_ex(("127.0.0.1", remote.PORT)) != 0)
        panel("/api/server", {"action": "share", "on": True})
        up = wait_until(lambda: panel("/api/status")["phase"] == "active" and panel("/api/server")["server"]["listening"])
        state = panel("/api/server")
        given = panel("/api/server", {"action": "config"})["config"]
        url, key, pin = f"https://127.0.0.1:{state['server']['port']}", given["engine_key"], given["engine_pin"]
        mark("acceso dal pannello: il motore riparte e ascolta in HTTPS, con il suo certificato e una chiave",
             up and state["mode"] == "server" and len(pin) == 64 and pin == state["server"]["pin"] and key.startswith("oms_") and given["engine_url"].startswith("https://"),
             f"porta {state['server']['port']}")
        who = remote.check(url, key, pin)
        refused = []
        for wrong_key, wrong_pin in ((key[:-3] + "xyz", pin), (key, "0" * 64)):
            try:
                remote.check(url, wrong_key, wrong_pin)
                refused.append("accettato")
            except remote.Failure as ex:
                refused.append(ex.code)
        mark("il server dice chi è solo a chi ha la chiave; con un'impronta diversa il PC non gli parla nemmeno",
             bool(who["model"]) and refused == ["refused", "certificate"], f"{who['model']} · {refused}")
        try:
            call(url.replace("https://", "http://") + "/omissis/info", {"Authorization": "Bearer " + key}, timeout=8)
            plain = "ha risposto"
        except Exception as ex:   # noqa: BLE001
            plain = type(ex).__name__
        mark("in chiaro il server non risponde", plain != "ha risposto", plain)

        # ---- il PC: un secondo motore senza modello, con dati suoi
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            folder = Path(folder)
            (folder / "lists").mkdir()
            (folder / "lists" / "never.txt").write_text("Nevatek S.r.l.\n", encoding="utf-8")
            (folder / "lists" / "always.txt").write_text("Progetto Zefiro\n", encoding="utf-8")
            (folder / "settings.json").write_text(json.dumps({"engine_url": url, "engine_key": key, "engine_pin": pin}), encoding="utf-8")
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            env = {k: v for k, v in os.environ.items() if k not in ("OMISSIS_MANAGED_FILE", "OMISSIS_TEST", "OMISSIS_PORT")}
            env.update(OMISSIS_DATA=str(folder), OMISSIS_LISTS=str(folder / "lists"), PYTHONUTF8="1")
            client = subprocess.Popen([str(paths.python_model()), str(HERE / "engine.py"), "--model", str(folder / "nessun-modello"), "--port", str(port)],
                                      env=env, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            pc = lambda path, data=None: call(f"http://127.0.0.1:{port}{path}", {"X-Token": (folder / "token.txt").read_text(encoding="utf-8").strip()}, data)   # noqa: E731
            started = wait_until(lambda: pc("/status")["remote"]["ok"], timeout=120)
            status = pc("/status") if started else {}
            mark("un PC senza modello parte lo stesso e trova il server", started and status.get("device") == "server"
                 and Path(str(status.get("model"))).name == who["model"] and status.get("entries") == 0 and not (folder / "nessun-modello").exists(),
                 f"{status.get('model')} · {(status.get('remote') or {}).get('ms')} ms")

            entries_server = panel("/api/status")["entries"]
            r = pc("/mask", {"texts": [TEXT]})
            out = r["texts"][0]
            mark("dal PC escono solo segnaposto: il nome e la mail li trova il modello del server",
                 "[PERSONA_" in out and "[EMAIL_" in out and "Ferraresi" not in out and "347 5551234" not in out, out[:110])
            mark("regole ed elenchi restano sul PC: «maschera sempre» e «non mascherare mai» valgono con le liste di quel PC",
                 "[ELENCO_" in out and "Progetto Zefiro" not in out and "Nevatek S.r.l." in out, str(r["counts"]))
            back = pc("/values", {"placeholder": list(r["mapping"])})["mapping"]
            mark("l'archivio resta sul PC: i valori veri tornano da lì, e in quello del server non entra nulla",
                 back == r["mapping"] and "Giulia Ferraresi" in back.values() and (folder / "vault.sqlite").exists()
                 and pc("/status")["entries"] == len(back) and panel("/api/status")["entries"] == entries_server,
                 f"voci sul PC {len(back)} · sul server {entries_server} -> {panel('/api/status')['entries']}")

            # ---- le categorie in piu' accese su un PC valgono per quel PC, non per il server ne' per gli altri
            (folder / "settings.json").write_text(json.dumps({"engine_url": url, "engine_key": key, "engine_pin": pin, "categories": ["DATA"]}), encoding="utf-8")
            profile = pc("/profile", {})
            dated = pc("/mask", {"texts": ["La riunione con il fornitore è fissata per il 14 marzo 2025 in sede."]})["texts"][0]
            at_server = panel("/api/try", {"text": "La riunione con il fornitore è fissata per il 14 marzo 2025 in sede.", "demo": True})["texts"][0]
            mark("una categoria in più accesa su un PC vale per quel PC e basta",
                 "DATA" in profile["known"] and profile["enabled"] == ["DATA"] and "[DATA_" in dated and "[DATA_" not in at_server, f"sul PC: {dated[:60]}")

            # ---- che cosa resta sul server: conteggi, mai i testi
            seen = panel("/api/server")["server"]["clients"]
            log_now = log.read_text(encoding="utf-8").splitlines()[log_lines:] if log.exists() else []
            kept = json.dumps(seen, ensure_ascii=False) + "\n".join(log_now)
            mark("il server tiene solo il conto di chi ha chiesto: nel suo registro non entra nulla di ciò che riceve",
                 len(seen) == 1 and seen[0]["texts"] >= 2 and seen[0]["name"] == remote.NAME and "Ferraresi" not in kept and "Zefiro" not in kept
                 and "14 marzo" not in kept and not log_now, f"{seen[0]['name'] if seen else '-'}: {seen[0]['texts'] if seen else 0} testi · righe nuove nel registro del server: {len(log_now)}")

            # ---- a server spento dal PC non parte nulla
            panel("/api/server", {"action": "share", "on": False})
            down = wait_until(lambda: panel("/api/status")["phase"] == "active" and panel("/api/server")["mode"] == "local"
                              and socket.socket().connect_ex(("127.0.0.1", state["server"]["port"])) != 0)
            try:
                pc("/mask", {"texts": ["Chiamare Aldo Bruschi al 333 1112223."]})
                closed = "mascherato o passato"
            except urllib.error.HTTPError as ex:
                closed = ex.code
            after = pc("/status")["remote"]
            mark("server spento: sul PC il testo non viene restituito (né mascherato né in chiaro), e lo stato lo dice",
                 down and closed == 500 and after["ok"] is False and after["error"] == "unreachable", f"risposta {closed} · {after['error']}")
            client.terminate()
            client.wait(15)
            client = None

        # ---- la pagina, nelle due lingue
        if "--no-page" not in sys.argv:
            page_checks(code, panel)
    finally:
        if client is not None:
            client.kill()
        try:
            now = panel("/api/server")
            if now["mode"] == "client":
                panel("/api/server", {"action": "leave"})
            elif now["mode"] == "server":
                panel("/api/server", {"action": "share", "on": False})
            wait_until(lambda: panel("/api/status")["phase"] == "active", timeout=240)
        except Exception as ex:   # noqa: BLE001
            print("ATTENZIONE: non sono riuscito a riportare la copia di prova com'era:", type(ex).__name__)
    print("\nTUTTO OK" if all(outcomes) else f"\n{outcomes.count(False)} ERRORI")
    sys.exit(0 if all(outcomes) else 1)


def page_checks(code, panel):
    """La scheda «Server di inferenza» nella pagina delle impostazioni, in italiano e in inglese."""
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(HERE / ".playwright"))
    from playwright.sync_api import sync_playwright
    keys = set(json.loads((HERE / "panel" / "locales" / "it.json").read_text(encoding="utf-8")))
    rx_key = re.compile(r"[a-z_]+(?:\.[a-z_0-9]+)+")
    language_before, view_before = panel("/api/settings")["language"], panel("/api/settings")["view"]
    with sync_playwright() as p:
        exe = paths.test_browser()
        br = p.chromium.launch(executable_path=str(exe) if exe else None)
        pag = br.new_context(viewport={"width": 1280, "height": 900}).new_page()
        errors = []
        pag.on("pageerror", lambda e: errors.append(str(e)))
        try:
            for language in ("it", "en"):
                panel("/api/settings", {"language": language, "view": "advanced"})
                pag.goto(PANEL + "/#/settings/recognition")
                pag.reload()
                pag.wait_for_selector('#server[data-mode="local"]', timeout=20000)
                untranslated = set(rx_key.findall(pag.inner_text("#server"))) & keys
                # una configurazione che non porta a nessun server viene rifiutata, e nulla cambia
                pag.fill("#srvConfig", json.dumps({"engine_url": "https://127.0.0.1:9", "engine_key": "oms_inventata", "engine_pin": "0" * 64}))
                pag.click("#srvUse")
                pag.wait_for_selector("#notices .notice.error, #notices [role=alert], #notices > *", timeout=20000)
                refused = panel("/api/server")["mode"] == "local"
                # prestare il modello: conferma, riavvio del motore, poi la pagina mostra che cosa dare agli altri PC
                pag.click("#srvShare")
                pag.wait_for_selector("#confirm[open]")
                pag.click("#confirmYes")
                pag.wait_for_selector('#server[data-mode="server"] #srvPin', timeout=240000)
                wait_until(lambda: panel("/api/status")["phase"] == "active" and panel("/api/server")["server"]["listening"])
                pag.reload()
                pag.wait_for_selector('#server[data-mode="server"][data-listening="yes"]', timeout=60000)
                shown = pag.inner_text("#srvPin").replace(" ", "")
                untranslated |= set(rx_key.findall(pag.inner_text("#server"))) & keys
                pag.click("#srvShow")
                pag.wait_for_selector("#srvData:not([hidden])")
                config = json.loads(pag.inner_text("#srvData"))
                pag.click("#srvStop")
                pag.wait_for_selector("#confirm[open]")
                pag.click("#confirmYes")
                pag.wait_for_selector('#server[data-mode="local"]', timeout=240000)
                wait_until(lambda: panel("/api/status")["phase"] == "active" and panel("/api/server")["mode"] == "local")
                mark(f"{language}: la scheda del server di inferenza, rifiuto di una configurazione che non porta a nessun server, modello prestato e ritirato",
                     refused and shown == panel_pin(config) and config["engine_key"].startswith("oms_") and not untranslated and not errors,
                     f"rifiutata {refused} · impronta mostrata {len(shown)} caratteri · senza traduzione {sorted(untranslated)[:3]} · errori {errors[:2]}")
        finally:
            panel("/api/settings", {"language": language_before, "view": view_before})
            br.close()


def panel_pin(config):
    return str(config.get("engine_pin") or "")


if __name__ == "__main__":
    main()
