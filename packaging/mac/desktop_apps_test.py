# -*- coding: utf-8 -*-
"""Prova sul Mac: Omissis e le app vere di Claude e di ChatGPT, con la porta di debug.

Senza accedere a nessun account: delle app si vede solo la finestra d'ingresso. Si controlla che
  - l'app sia dove Omissis la cerca e che Omissis ne riconosca i processi;
  - un'app che accetta la porta (ChatGPT) venga avviata protetta e il codice di Omissis entri nelle sue finestre;
  - un'app già aperta senza protezione venga riconosciuta, lasciata stare, e poi chiusa e riaperta su richiesta;
  - un'app che rifiuta la porta (Claude) la rifiuti davvero, e che Omissis lo dica senza chiuderla.
Che un messaggio vero venga sostituito NON si può vedere da qui: serve un account, quindi una persona.

La prova chiude le app: va lanciata solo su una macchina di prova (lo fa desktop_apps_test.sh).

  python3 desktop_apps_test.py <cartella delle schermate> [claude chatgpt]      (con Omissis acceso)
"""
import json
import os
import plistlib
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# il codice di Omissis sta in app/ (nel repository) o nella cartella da cui si lancia la prova
sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "app"), os.getcwd()]
import connector   # noqa: E402

if not os.environ.get("CI"):
    sys.exit("Questa prova chiude le app di Claude e di ChatGPT: va lanciata solo su una macchina di prova (CI=1).")
OUT = Path(sys.argv[1])
KEYS = sys.argv[2:] or ["claude", "chatgpt"]
OUT.mkdir(parents=True, exist_ok=True)
RESULTS = []


def check(ok, text, detail=""):
    RESULTS.append(bool(ok))
    print(("OK    " if ok else "NO    ") + text + (f"   [{detail}]" if detail else ""), flush=True)
    return bool(ok)


def shot(name):
    try:
        subprocess.run(["screencapture", "-x", str(OUT / f"{name}.png")], timeout=30, check=False)
    except Exception as ex:   # noqa: BLE001
        print(f"      schermata {name} non riuscita: {ex}", flush=True)


def describe(command):
    app = Path(command).parents[2]
    info = plistlib.loads((app / "Contents" / "Info.plist").read_bytes())
    frameworks = sorted(p.name for p in (app / "Contents" / "Frameworks").glob("*.framework"))
    return app, info, frameworks, (app / "Contents" / "Resources" / "app.asar").exists()


def debug_port(port, what):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/{what}", timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def wait(condition, seconds):
    for _ in range(seconds * 2):
        if condition():
            return True
        time.sleep(0.5)
    return bool(condition())


def running(app):
    return connector.processes(app.get("process"))


def open_plain(command, app):
    """L'app aperta come la apre chi usa il Mac: senza porta."""
    subprocess.Popen([command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    wait(lambda: bool(running(app)), 30)
    time.sleep(10)


def protected(key, app, label, **how):
    """Avvia l'app con Omissis e dice che cosa si vede."""
    try:
        c = connector.launch_app(key, timeout=90, **how)
    except connector.Error as ex:
        check(False, f"{label}: Omissis avvia l'app con la porta di debug", f"{type(ex).__name__}: {ex}"[:300])
        return None
    check(True, f"{label}: l'app accetta la porta di debug {app['port']}", c.cdp.product)
    wait(lambda: c.counts["pages"] > 0 or c.errors, 40)
    time.sleep(8)   # il tempo che la finestra d'ingresso finisca di caricarsi
    try:
        version = debug_port(app["port"], "version")
        print("      motore:", version.get("Browser"), "|", (version.get("User-Agent") or "")[:160], flush=True)
        for t in debug_port(app["port"], "list"):
            print("      finestra:", t.get("type"), "|", (t.get("url") or "")[:110], "|", (t.get("title") or "")[:50], flush=True)
    except Exception as ex:   # noqa: BLE001
        print("      elenco delle finestre non letto:", ex, flush=True)
    check(c.counts["pages"] > 0, f"{label}: il codice di Omissis entra nelle finestre", f"finestre {c.counts['pages']}")
    check(not c.errors, f"{label}: nessun errore del connettore", "; ".join(c.errors)[:300])
    print("      controllo in rete sul browser intero:", "sì" if c.browser_guard else "no", "| avvisi:", "; ".join(c.notices)[:300] or "nessuno")
    print("      esito dichiarato:", c.outcome, "| conteggi:", c.counts, "| versione letta:", c.client)
    print("      indirizzi seguiti:", sorted({(s.get("address") or "")[:90] for s in c.sessions.values()}), flush=True)
    check(bool(running(app)), f"{label}: Omissis riconosce i processi dell'app", f"processi {len(running(app))}")
    return c


def close(key, app, c, label):
    if c is not None:
        try:
            c.close()
        except Exception:   # noqa: BLE001
            pass
    check(connector.close_app(key, grace=15), f"{label}: Omissis sa chiudere l'app")
    check(wait(lambda: not running(app), 10), f"{label}: dopo la chiusura non resta nessun processo", f"processi {len(running(app))}")
    wait(lambda: not connector.opened_port(app["port"]), 10)


def accepts(key, app, command):
    """Un'app che accetta la porta: avviata protetta da chiusa, e da già aperta."""
    c = protected(key, app, f"{key}, app chiusa")
    shot(f"{key}-1-avviata-da-omissis")
    close(key, app, c, f"{key}, app chiusa")

    open_plain(command, app)
    check(connector.open_unprotected(key), f"{key}, app già aperta: Omissis si accorge che è aperta senza protezione")
    try:
        other = connector.launch_app(key, timeout=20)
        check(False, f"{key}, app già aperta: Omissis non la tocca senza chiedere", "l'ha avviata lo stesso")
        other.close()
    except connector.AlreadyOpen as ex:
        check(True, f"{key}, app già aperta: Omissis non la tocca e lo dice", str(ex)[:140])
    except connector.Error as ex:
        check(False, f"{key}, app già aperta: Omissis non la tocca e lo dice", f"{type(ex).__name__}: {ex}"[:300])
    c = protected(key, app, f"{key}, chiusa e riaperta su richiesta", close_first=True)
    shot(f"{key}-2-riaperta-protetta")
    close(key, app, c, f"{key}, chiusa e riaperta su richiesta")


def refuses(key, app, command):
    """Un'app che Omissis sa di non poter avviare con la porta: la rifiuta davvero, e Omissis lo dice senza chiuderla."""
    said = OUT / f"{key}-rifiuto.txt"
    with open(said, "wb") as f:
        p = subprocess.Popen([command, f"--remote-debugging-port={app['port']}"], stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        wait(lambda: p.poll() is not None or connector.opened_port(app["port"]), 25)
    accepted = connector.opened_port(app["port"])
    lines = said.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    check(p.poll() is not None and not accepted, f"{key}: avviata a mano con la porta di debug, l'app si chiude da sola",
          f"codice {p.returncode}; ha scritto: {lines[-1][:170] if lines else 'niente'}")
    if accepted:
        print("      ATTENZIONE: ora l'app accetta la porta. In connector.py «refuses» va tolto, e l'app va provata come le altre.", flush=True)
    connector.close_app(key, grace=10)
    wait(lambda: not running(app), 10)

    open_plain(command, app)
    check(bool(running(app)), f"{key}, aperta normalmente: Omissis ne riconosce i processi", f"processi {len(running(app))}")
    check(connector.open_unprotected(key), f"{key}, aperta normalmente: Omissis sa che è aperta senza protezione")
    try:
        c = connector.launch_app(key, timeout=20, close_first=True)
        check(False, f"{key}: Omissis dice che da qui non si può proteggere", "l'ha avviata con la porta")
        c.close()
    except connector.Error as ex:
        check(not isinstance(ex, connector.AlreadyOpen), f"{key}: Omissis dice che da qui non si può proteggere", str(ex)[:170])
    check(bool(running(app)), f"{key}: Omissis non ha chiuso l'app di chi la usa", f"processi {len(running(app))}")
    shot(f"{key}-1-aperta-non-protetta")
    close(key, app, None, key)


for key in KEYS:
    print(f"\n=================== {key}", flush=True)
    app = connector.APP.get(key)
    if not check(app is not None, f"{key}: è tra le app che Omissis conosce su questo sistema"):
        continue
    command = connector.find_command(app)
    if not check(command is not None, f"{key}: l'app è dove Omissis la cerca", str(command)):
        continue
    bundle, info, frameworks, asar = describe(command)
    print("      app:", bundle, "|", info.get("CFBundleIdentifier"), "|", info.get("CFBundleShortVersionString"), "| programma:", info.get("CFBundleExecutable"))
    print("      dentro:", ", ".join(frameworks) or "nessun framework", "| app.asar:", "sì" if asar else "no", flush=True)
    check(not running(app), f"{key}: prima della prova l'app è chiusa")
    if app.get("refuses"):
        refuses(key, app, command)
    else:
        accepts(key, app, command)

print(f"\n{'TUTTO OK' if all(RESULTS) else 'NON TUTTO OK'}: {sum(RESULTS)}/{len(RESULTS)} controlli", flush=True)
sys.exit(0 if RESULTS and all(RESULTS) else 1)
