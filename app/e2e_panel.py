# -*- coding: utf-8 -*-
"""Prova il pannello in un browser vero (il Chromium di Playwright) e ne scatta le schermate.

  .venv\\Scripts\\python.exe e2e_panel.py [--screenshots <cartella>]

Serve la protezione attiva (panel.py). In italiano e in inglese apre ogni sezione e controlla che:
non ci siano errori nella pagina, nessuna frase resti senza traduzione, ogni pulsante e ogni campo
abbia un nome leggibile da chi usa uno schermo parlante, la pagina dichiari la lingua giusta e si
possa usare tutta dalla tastiera. Poi il giro completo della parte manuale, con dati inventati:
  testo      incolla -> mascherato e copiato da solo -> incolla di nuovo -> tornano i valori veri
  documento  file trascinato -> copia anonimizzata scaricata da sola -> rimessa dentro -> ripristinata
Alla fine rimette lingua, tema e modalità com'erano. Le schermate (dati inventati) servono al sito
e ai documenti.
"""
import argparse
import base64
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

import activity
import catalog
import report
import connector
import inventory
import paths

HERE = Path(__file__).resolve().parent
PANEL = f"http://127.0.0.1:{paths.PANEL_PORT}"
TEXT = ("Buongiorno, sono Giulia Ferraresi della Nevatek S.r.l. Il mio collega Aldo Bruschi (aldo.bruschi@nevatek.example, "
         "cell. 347 5551234) non riesce ad accedere al gestionale: potete richiamarlo oggi?")
SENSITIVE = ["Giulia Ferraresi", "Aldo Bruschi", "aldo.bruschi@nevatek.example", "347 5551234"]
VIEWS = ["start", "text", "documents", "guide", "settings/general", "settings/recognition", "connections/browser",
         "connections/app", "connections/terminal", "connections/mcp", "connections/proxy", "connections/compatibility", "services/rules", "services/detected", "activity", "vault"]
# una chiave rimasta a schermo al posto della frase ("menu.inizio", "testo.sotto"...): si cercano quelle vere, dal file di riferimento
KEYS = set(json.loads((HERE / "panel" / "locales" / "it.json").read_text(encoding="utf-8")))
RX_KEY = re.compile(r"[a-z_]+(?:\.[a-z_0-9]+)+")
WITHOUT_NAME = """() => [...document.querySelectorAll('button, a[href], input, select, textarea, [role=tab], [role=switch]')]
  .filter(e => e.offsetParent !== null || e.classList.contains('vh') || e.closest('.toggle'))
  .filter(e => !(e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || (e.labels && e.labels.length) || e.textContent.trim() || e.placeholder))
  .map(e => e.outerHTML.slice(0, 90))"""
outcomes = []


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(("OK   " if ok else "NO   ") + name + (f"  ({note})" if note else ""))


def wait_until(condition, timeout=10):
    """Attende che una condizione letta da qui (un file scritto dal pannello, per esempio) diventi vera."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if condition():
                return True
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    return False


def wait(pag, expression, arg=None, timeout=30):
    """Attende che un'espressione diventi vera nella pagina. Non si usa wait_for_function: valuta il testo con eval, che la
    pagina vieta apposta (niente codice che non venga dai suoi file)."""
    end = time.time() + timeout
    while time.time() < end:
        if pag.evaluate(expression, arg):
            return True
        pag.wait_for_timeout(150)
    return False


def call(code, path, data=None):
    r = urllib.request.Request(PANEL + path, headers={"X-Panel": code, "Content-Type": "application/json"},
                               data=json.dumps(data).encode("utf-8") if data is not None else None)
    with urllib.request.urlopen(r, timeout=60) as x:
        return json.loads(x.read().decode("utf-8"))


def fake_inventory():
    """Tre analisi inventate al posto di quelle di questo PC: la pagina e le schermate mostrano sempre le stesse cose."""
    if not os.environ.get("OMISSIS_DATA"):
        sys.exit("questa prova scrive un inventario inventato: va lanciata su una copia di prova (OMISSIS_DATA), non sui dati veri")
    service = lambda name: next(({"id": s["id"], "name": s["name"]} for s in catalog.SERVICES if s["name"] == name), {"id": "", "name": name})   # noqa: E731
    program = lambda name, version, s: {"name": name, "version": version, "service": service(s)}   # noqa: E731

    def scan(programs, extensions, editor, commands, local):
        return {"programs": programs, "processes": [], "seconds": 4.2, "commands": [{"command": c, "path": f"D:\\Strumenti\\npm\\{c}.cmd"} for c in commands],
                "browser_extensions": [{"browser": "Edge", "profile": "default", "name": n, "version": v, "id": n.lower().replace(" ", "-"), "all_sites_access": True}
                                       for n, v in extensions],
                "editor_extensions": [{"editor": "VS Code", "name": n, "author": a, "version": v} for n, a, v in editor],
                "local": [{"name": n, "what": c, "gb": gb} for n, c, gb in local]}
    inventory.clear()
    chatgpt, claude = program("ChatGPT", "1.2025.139", "ChatGPT"), program("Claude", "1.1.2685", "Claude")
    steps = [scan([chatgpt], [("Scrivi Meglio AI", "3.1")], [("GitHub Copilot", "GitHub", "1.300.0")], [], []),
             scan([chatgpt, claude], [("Scrivi Meglio AI", "3.1")], [("GitHub Copilot", "GitHub", "1.302.0")], ["claude"], []),
             scan([chatgpt, claude], [], [("GitHub Copilot", "GitHub", "1.302.0")], ["claude"], [("Ollama", "D:\\Modelli\\ollama", 12.4)])]
    for i, step in enumerate(steps):
        inventory.record(step, None, "automatic" if i < 2 else "manual")
        time.sleep(1.1)   # le analisi hanno l'ora al secondo


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshots", dest="screenshots", default=str(HERE / "screenshots"))
    a = ap.parse_args()
    photo = Path(a.screenshots)
    photo.mkdir(parents=True, exist_ok=True)
    raw_page = urllib.request.urlopen(PANEL + "/", timeout=20).read().decode("utf-8")
    code = re.search(r'name="omissis-code" content="([^"]+)"', raw_page).group(1)
    before = call(code, "/api/settings")
    if call(code, "/api/status")["phase"] != "active":
        sys.exit("la protezione non è attiva: avviarla prima")
    work = Path(tempfile.mkdtemp(prefix="omissis_panel_"))
    fake_inventory()

    with sync_playwright() as p:
        exe = paths.test_browser()
        br = p.chromium.launch(executable_path=str(exe) if exe else None)
        ctx = br.new_context(viewport={"width": 1280, "height": 860}, permissions=["clipboard-read", "clipboard-write"], accept_downloads=True)
        pag = ctx.new_page()
        errors = []
        pag.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pag.on("pageerror", lambda e: errors.append(str(e)))
        try:
            for language in ("it", "en"):
                call(code, "/api/settings", {"language": language, "theme": "light", "view": "advanced"})
                pag.goto(PANEL + "/#/start")
                pag.reload()
                pag.wait_for_selector("#menu a")
                mark(f"{language}: la pagina dichiara la sua lingua", pag.evaluate("document.documentElement.lang") == language)
                remaining, anonymous_ones, without_title = set(), [], []
                for view in VIEWS:
                    pag.goto(f"{PANEL}/#/{view}")
                    pag.wait_for_selector("#panel > *")
                    pag.wait_for_timeout(700)
                    remaining |= set(RX_KEY.findall(pag.inner_text("body"))) & KEYS
                    anonymous_ones += [f"{view}: {x}" for x in pag.evaluate(WITHOUT_NAME)]
                    if pag.locator("main h1").count() != 1 or not pag.title().endswith("· Omissis"):
                        without_title.append(view)
                mark(f"{language}: {len(VIEWS)} pagine aperte senza errori", not errors, "; ".join(errors[:3]))
                mark(f"{language}: nessuna frase senza traduzione", not remaining, ", ".join(sorted(remaining)[:6]))
                mark(f"{language}: ogni pulsante e ogni campo ha un nome", not anonymous_ones, " | ".join(anonymous_ones[:3]))
                mark(f"{language}: ogni pagina ha un titolo solo e il titolo della scheda", not without_title, ", ".join(without_title))
                errors.clear()

                # --- configurazione guidata (qui la si apre a mano: durante le prove non si propone da sola). Nella copia di
                # prova la ricerca non guarda il PC: trova sempre ChatGPT, Claude, Cursor, GitHub Copilot, claude, agy e Ollama
                try:
                    today = lambda: call(code, "/api/status")["stats"]["today"]["messages"]   # noqa: E731
                    counted, stored = today(), call(code, "/api/status")["entries"]
                    kept = {k: call(code, "/api/settings")[k] for k in ("policies", "groups_off", "categories", "ask_apps", "scan")}
                    call(code, "/api/settings", {"onboarded": False})
                    pag.goto(PANEL + "/#/welcome")
                    pag.reload()
                    pag.wait_for_selector("#welcome[open] #welcomeTry:not([disabled])", timeout=30000)
                    video = pag.evaluate("(() => { const v = document.querySelector('#welcome video'); return !!v && v.getAttribute('src') === '/welcome.mp4'; })()")
                    video_ok = urllib.request.urlopen(PANEL + "/welcome.mp4", timeout=20).headers.get("Content-Type") == "video/mp4"
                    untranslated = set(RX_KEY.findall(pag.inner_text("#welcome"))) & KEYS
                    pag.click("#welcomeTry")
                    pag.wait_for_selector("#welcomeResult:not([hidden])", timeout=30000)
                    tried = pag.inner_text("#welcomeResult")
                    pag.click("#welcomeNext")
                    pag.wait_for_selector('#welcome[data-step="2"] #welcomeScan')
                    pag.click("#welcomeScan")
                    pag.wait_for_selector("#welcomeTotal", timeout=30000)
                    found = pag.inner_text("#welcome .sources")
                    untranslated |= set(RX_KEY.findall(pag.inner_text("#welcome"))) & KEYS
                    pag.click("#welcomeNext")
                    pag.wait_for_selector('#welcome[data-step="3"] [data-pick="claude"]')
                    rows = pag.evaluate("[...document.querySelectorAll('#welcome [data-pick]')].map(x => x.dataset.pick + (x.checked ? '+' : '-')).join(' ')")
                    counted_rows = pag.evaluate("[...document.querySelectorAll('#welcome [data-rule]')].map(x => x.dataset.rule).join(' ')")
                    pag.uncheck('#welcome [data-pick="gemini"]')
                    pag.select_option('#welcome [data-rule="cursor"]', "block")
                    untranslated |= set(RX_KEY.findall(pag.inner_text("#welcome"))) & KEYS
                    pag.click("#welcomeNext")
                    pag.wait_for_selector('#welcome[data-step="4"] #welcomeExt')
                    policies = call(code, "/api/settings")["policies"]
                    browser = pag.get_attribute("#welcomeExt", "data-status")
                    pag.click("#conn-cc-cc")
                    pag.wait_for_selector('[data-conn-row="cc"] .label.ok')
                    pag.click("#conn-ag-later")
                    pag.wait_for_selector('[data-conn-row="ag"] .label.warning')
                    if pag.locator("#conn-app-test-later").count():   # l'app di prova resta chiusa: la prova delle app la apre dopo
                        pag.click("#conn-app-test-later")
                    untranslated |= set(RX_KEY.findall(pag.inner_text("#welcome"))) & KEYS
                    unnamed = pag.evaluate(WITHOUT_NAME)
                    pag.click("#welcomeNext")
                    pag.wait_for_selector('#welcome[data-step="5"] input[value="confidential"]')
                    pag.check('#welcome input[name="welcomeProfile"][value="confidential"]')
                    wait_until(lambda: call(code, "/api/settings")["groups_off"] == [])
                    untranslated |= set(RX_KEY.findall(pag.inner_text("#welcome"))) & KEYS
                    pag.click("#welcomeNext")
                    pag.wait_for_selector('#welcome[data-step="6"] #welcomeAsk')
                    pag.click("#welcomeAsk")
                    wait_until(lambda: call(code, "/api/settings")["ask_apps"] is False)
                    unnamed += pag.evaluate(WITHOUT_NAME)
                    pag.click("#welcomeNext")
                    pag.wait_for_selector('#welcome[data-step="7"]')
                    pag.check('#welcome input[name="welcomeOthers"][value="many"]')
                    pag.wait_for_selector("#welcomeAct-share")
                    untranslated |= set(RX_KEY.findall(pag.inner_text("#welcome"))) & KEYS
                    unnamed += pag.evaluate(WITHOUT_NAME)
                    pag.click("#welcomeNext")
                    pag.wait_for_selector('#welcome[data-step="8"] #welcomeTodo')
                    summary = pag.inner_text("#welcome")
                    untranslated |= set(RX_KEY.findall(summary)) & KEYS
                    unnamed += pag.evaluate(WITHOUT_NAME)
                    pag.click("#welcomeNext")
                    wait_until(lambda: call(code, "/api/settings")["onboarded"] is True)
                    # la pagina cambia indirizzo un attimo dopo che l'impostazione e' salvata: la si aspetta, non la si coglie al volo
                    closed = wait(pag, "() => !document.getElementById('welcome').open && location.hash === '#/start'", timeout=5)
                    # saltata con Esc vale come vista; e dalla Guida la si puo' rivedere
                    call(code, "/api/settings", {"onboarded": False})
                    pag.goto(PANEL + "/#/guide")
                    pag.click("#welcomeAgain")
                    pag.wait_for_selector("#welcome[open]")
                    pag.keyboard.press("Escape")
                    wait_until(lambda: call(code, "/api/settings")["onboarded"] is True)
                    contact = pag.get_attribute("#contact", "href") or ""
                    call(code, "/api/settings", kept)
                    mark(f"{language}: configurazione guidata, prova con dati inventati (fuori dai conteggi e dall'archivio), video, ricerca, scelte, collegamenti, dati, controlli, altri PC, riepilogo; saltarla vale come vista",
                         "[PERSONA_1]" in tried and "Ferraresi" not in tried and today() == counted and call(code, "/api/status")["entries"] == stored
                         and video and video_ok and "Cursor" in found and "agy" in found
                         and rows.startswith("chatgpt+ claude+ anthropic-api+ antigravity+ gemini+") and counted_rows == "cursor github-copilot"
                         and policies.get("cursor") == "block" and policies.get("antigravity") == "protect" and policies.get("gemini", "record") == "record"
                         and browser == "absent" and "Antigravity" in summary and "Cursor" in summary and closed
                         and not untranslated and not unnamed and not pag.evaluate("document.getElementById('welcome').open")
                         and contact.startswith("https://francescogruner.it/") and bool(pag.inner_text("#contact").strip()),
                         f"sostituiti: {'[PERSONA_' in tried} · conteggi {counted}->{today()} · video {video}/{video_ok} · righe {rows} | {counted_rows} · "
                         f"regole {policies} · estensione {browser} · chiusa {closed} · senza traduzione {sorted(untranslated)[:3]} · senza nome {unnamed[:2]}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: configurazione guidata", False, str(ex)[:200])
                    call(code, "/api/settings", {"onboarded": True, **kept})
                    pag.goto(PANEL + "/#/start")
                    pag.reload()
                    pag.wait_for_selector("#menu a")
                errors.clear()

                # --- l'avviso per un'app AI aperta: la finestrella con le scelte per quell'app
                try:
                    kept = {k: call(code, "/api/settings")[k] for k in ("policies", "ask_never")}
                    pag.goto(PANEL + "/#/ask/cursor")
                    pag.reload()
                    pag.wait_for_selector("#askTitle")
                    title, menu = pag.inner_text("#askTitle"), pag.is_visible("#menu")
                    protect_off = pag.is_disabled('#content input[value="protect"]')
                    unnamed = pag.evaluate(WITHOUT_NAME)
                    untranslated = set(RX_KEY.findall(pag.inner_text("#content"))) & KEYS
                    pag.check('#content input[value="block"]')
                    pag.click("#askApply")
                    pag.wait_for_selector("#askClose")
                    blocked = call(code, "/api/settings")["policies"].get("cursor")
                    pag.goto(PANEL + "/#/ask/claude")
                    pag.reload()
                    pag.wait_for_selector("#askNever")
                    claude_options = pag.evaluate("[...document.querySelectorAll('#content input[name=askChoice]')].map(x => x.value + (x.disabled ? '-' : '')).join(' ')")
                    pag.click("#askNever")
                    pag.wait_for_selector("#askClose")
                    never = call(code, "/api/settings")["ask_never"]
                    call(code, "/api/settings", kept)
                    pag.goto(PANEL + "/#/start")
                    pag.reload()
                    pag.wait_for_selector("#menu a")
                    mark(f"{language}: avviso per un'app AI aperta (finestrella senza menu, «Proteggi» solo dove si può, regola applicata, «Non chiederlo più»)",
                         "Cursor" in title and not menu and protect_off and blocked == "block" and claude_options == "protect record ignore" and "claude" in never
                         and not unnamed and not untranslated and not errors,
                         f"titolo {title} · menu {menu} · proteggi spento {protect_off} · regola {blocked} · scelte {claude_options} · mai {never} · {errors[:2]}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: avviso per un'app AI aperta", False, str(ex)[:200])
                    pag.goto(PANEL + "/#/start")
                    pag.reload()
                    pag.wait_for_selector("#menu a")
                errors.clear()

                # --- quando l'estensione e' pubblicata (store.json), la guida propone lo store al posto dell'installazione a mano
                if language == "it":
                    try:
                        def published(route):
                            answer = route.fetch()
                            route.fulfill(response=answer, json={**answer.json(), "store": {"chrome": "https://chromewebstore.google.com/detail/esempio"}})
                        pag.route("**/api/extension", published)
                        pag.goto(PANEL + "/#/welcome")
                        pag.reload()
                        pag.wait_for_selector("#welcome[open] #welcomeNext")
                        pag.click("#welcomeNext")
                        pag.wait_for_selector('#welcome[data-step="2"]')
                        pag.click("#welcomeSkip")
                        pag.wait_for_selector('#welcome[data-step="3"]')
                        pag.click("#welcomeNext")
                        pag.wait_for_selector('#welcome[data-step="4"] #welcomeStoreBox:not([hidden])')
                        mark("estensione pubblicata: la guida propone lo store e nasconde l'installazione a mano",
                             pag.get_attribute("#welcomeStore", "href") == "https://chromewebstore.google.com/detail/esempio" and not pag.is_visible("#welcomeManual")
                             and call(code, "/api/extension")["store"] == {})
                        pag.click("#welcomeExit")
                    except Exception as ex:   # noqa: BLE001
                        mark("estensione pubblicata: la guida propone lo store", False, str(ex)[:200])
                    finally:
                        pag.unroute("**/api/extension")
                        call(code, "/api/settings", {"onboarded": True})
                    errors.clear()

                # --- aperta dalla pagina di benvenuto dell'estensione, la pagina consegna da sola il codice di collegamento
                if language == "it":
                    try:
                        other = ctx.new_page()
                        other.add_init_script("window.__posted = []; window.addEventListener('message', e => { if (e.data && e.data.omissis === 'connect') window.__posted.push({token: typeof e.data.token === 'string' && e.data.token.length > 10, port: e.data.port}); });")
                        other.goto(PANEL + "/#/connect")
                        other.wait_for_selector("#menu a")
                        quiet = other.evaluate("window.__posted.length") == 0   # senza estensione non parte nulla
                        other.evaluate("window.postMessage({omissis: 'extension', version: '0', connected: false, ok: false}, location.origin)")
                        wait_until(lambda: other.evaluate("window.__posted.length") >= 1)
                        other.evaluate("window.postMessage({omissis: 'extension', version: '0', connected: false, ok: false}, location.origin)")
                        other.wait_for_timeout(600)
                        posted = other.evaluate("window.__posted")
                        mark("pagina aperta dall'estensione appena installata: il codice di collegamento parte da solo, una volta",
                             quiet and len(posted) == 1 and posted[0]["token"] and other.evaluate("location.hash") == "#/start", f"consegne: {len(posted)}")
                        other.close()
                    except Exception as ex:   # noqa: BLE001
                        mark("pagina aperta dall'estensione appena installata", False, str(ex)[:200])

                # --- dalla tastiera: il primo Tab porta al collegamento "vai al contenuto", le linguette si scorrono con le frecce
                pag.goto(f"{PANEL}/#/connections/browser")
                pag.wait_for_selector("[role=tab]")
                pag.reload()
                pag.wait_for_selector("[role=tab]")
                pag.keyboard.press("Tab")
                jump = pag.evaluate("document.activeElement.id")
                pag.focus("#tab-browser")
                pag.keyboard.press("ArrowRight")
                sweep = wait(pag, "() => location.hash.endsWith('/app') && document.getElementById('tab-app')?.getAttribute('aria-selected') === 'true'", timeout=5)
                mark(f"{language}: si usa dalla tastiera (salto al contenuto, linguette con le frecce)", jump == "skip" and sweep, f"primo Tab su «{jump}» · freccia {sweep}")

                # --- app desktop: l'app di prova si avvia protetta dal pannello e si stacca; il suo servizio è su «Proteggi», quindi nessun avviso
                try:
                    pag.wait_for_selector("[data-app-line=test] button[data-action=launch]", timeout=15000)
                    pag.click("[data-app-line=test] button[data-action=launch]")
                    on = wait(pag, "() => !!document.querySelector('[data-app-line=test] button[data-action=detach]')", timeout=45)
                    state = pag.evaluate("(() => { const r = document.querySelector('[data-app-line=test]'); return r.dataset.outcome + '|' + r.dataset.open + '|' + document.querySelectorAll('[data-app-line=test] + [data-app-note]').length; })()")
                    pag.click("[data-app-line=test] button[data-action=detach]")
                    off = wait(pag, "() => !!document.querySelector('[data-app-line=test] button[data-action=launch]')", timeout=15)
                    mark(f"{language}: app desktop avviata protetta e staccata dal pannello", on and off and state == "waiting||0", state)
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: app desktop avviata protetta e staccata dal pannello", False, str(ex)[:160])

                # --- Kimi: non si avvia con il collegamento, si protegge con un plugin che Omissis prepara e chi usa il PC installa
                try:
                    listed = paths.DATA / "kimi-home" / "plugins" / "installed.json"
                    listed.unlink(missing_ok=True)
                    pag.reload()
                    pag.wait_for_selector("[data-app-line=kimi] button[data-action=plugin]", timeout=15000)
                    before = pag.evaluate("document.querySelectorAll('[data-app-line=kimi] button[data-action=launch], [data-app-line=kimi] button[data-action=relaunch]').length")
                    pag.click("[data-app-line=kimi] button[data-action=plugin]")
                    steps = wait(pag, "() => !!document.querySelector('[data-app-note=plugin-steps] #pluginSentence')", timeout=15)
                    sentence = pag.inner_text("#pluginSentence") if steps else ""
                    notes = pag.inner_text("[data-app-note=plugin]") + (pag.inner_text("[data-app-note=plugin-steps]") if steps else "")
                    made = (paths.DATA / "kimi-plugin" / "omissis" / "kimi.plugin.json").exists()
                    listed.parent.mkdir(parents=True, exist_ok=True)
                    listed.write_text(json.dumps({"version": 1, "plugins": [{"id": "omissis", "enabled": True}]}), encoding="utf-8")
                    there = wait(pag, "() => !!document.querySelector('[data-app-line=kimi] .label.ok') && !document.querySelector('[data-app-note=plugin-steps]')", timeout=20)
                    listed.unlink()
                    mark(f"{language}: Kimi: niente «Avvia protetta», ma il plugin; il pannello prepara la cartella, dice come installarlo e riconosce quando in Kimi c'è",
                         before == 0 and steps and made and str(paths.DATA / "kimi-plugin" / "omissis") in sentence and there and "app.plugin" not in notes and len(notes) > 200,
                         f"altri pulsanti {before} · passi {steps} · cartella {made} · riconosciuto {there} · {sentence[:60]}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: Kimi protetta con il plugin", False, str(ex)[:160])

                # --- l'app di Claude: rifiuta la porta di collegamento, quindi si protegge dal proxy del sistema (certificato e
                # file PAC). Le impostazioni del computer qui sono finte: le fa un file (OMISSIS_FAKE_SYSTEM), quelle vere non si toccano
                fake = os.environ.get("OMISSIS_FAKE_SYSTEM")
                if not fake:
                    print("SALTATO app protetta dal proxy: senza OMISSIS_FAKE_SYSTEM toccherebbe le impostazioni vere del PC")
                else:
                    try:
                        def system(change=None):   # che cosa c'e' nel «sistema»; con change lo si riscrive
                            if change is not None:
                                Path(fake).write_text(json.dumps(change), encoding="utf-8")
                            return json.loads(Path(fake).read_text(encoding="utf-8")) if Path(fake).exists() else {}

                        def refusal(action):   # la frase con cui il pannello rifiuta, oppure "" se accetta
                            try:
                                call(code, "/api/app", {"id": "claude", "action": action})
                                return ""
                            except urllib.error.HTTPError as ex:
                                return json.loads(ex.read().decode("utf-8")).get("error", "?")
                        refusal("proxy_off")
                        system({})
                        pag.reload()
                        pag.wait_for_selector("[data-app-line=claude] button[data-action=proxy_on]", timeout=15000)
                        about = pag.inner_text("[data-app-line=claude] [data-app-note=proxy]")
                        launch = pag.evaluate("document.querySelectorAll('[data-app-line=claude] button[data-action=launch], [data-app-line=claude] button[data-action=relaunch]').length")
                        mark(f"{language}: app di Claude: niente «Avvia protetta», ma un solo pulsante «Proteggi» e la spiegazione",
                             launch == 0 and len(about) > 60 and "app.proxy" not in about, about[:70])
                        # un altro proxy gia' impostato sul computer: non lo si tocca, e lo si dice con il suo indirizzo
                        system({"proxy": "10.1.2.3:3128"})
                        said = refusal("proxy_on")
                        mark(f"{language}: app di Claude: un proxy già impostato non viene toccato", "10.1.2.3:3128" in said and not system().get("pac")
                             and "claude" not in call(code, "/api/settings")["app_proxy"], said[:90])
                        # chi usa il computer dice no alla domanda sul certificato: ci si ferma, niente resta a metà
                        system({"refuse_certificate": True})
                        said = refusal("proxy_on")
                        mark(f"{language}: app di Claude: senza il sì al certificato non cambia nulla", bool(said) and not system().get("pac")
                             and not system().get("certificate") and "claude" not in call(code, "/api/settings")["app_proxy"], said[:90])
                        # tutto a posto: un clic e una conferma, e il sistema ha certificato e file PAC
                        system({})
                        pag.reload()
                        pag.wait_for_selector("[data-app-line=claude] button[data-action=proxy_on]", timeout=15000)
                        pag.click("[data-app-line=claude] button[data-action=proxy_on]")
                        pag.wait_for_selector("#confirm[open]", timeout=5000)
                        asked = pag.inner_text("#confirmText")
                        pag.click("#confirmYes")
                        on = wait(pag, "() => !!document.querySelector('[data-app-line=claude] button[data-action=proxy_off]')", timeout=20)
                        now, port = system(), call(code, "/api/settings")["port"]
                        with urllib.request.urlopen(now.get("pac") or PANEL + "/nessuno", timeout=10) as r:
                            pac, kind = r.read().decode("utf-8"), r.headers.get("Content-Type", "")
                        status = pag.inner_text("[data-app-line=claude] .label")
                        mark(f"{language}: app di Claude: un clic e una conferma mettono certificato e file PAC",
                             on and len(asked) > 100 and now.get("certificate") is True and now.get("pac", "").startswith(PANEL + "/proxy.pac?v=")
                             and call(code, "/api/settings")["app_proxy"] == ["claude"], f"{now.get('pac', '')[:60]} · stato «{status}»")
                        mark(f"{language}: app di Claude: il file PAC manda al proxy solo claude.ai", '"claude.ai"' in pac and f"PROXY 127.0.0.1:{port}" in pac
                             and "chatgpt" not in pac and 'return "DIRECT"' in pac and "ns-proxy-autoconfig" in kind, kind)
                        # l'app era gia' aperta quando la protezione e' stata accesa: legge le impostazioni di rete solo alla partenza,
                        # quindi esce senza protezione. Il pannello lo dice e offre di riaprirla (qui l'app «aperta» la fa il sistema finto)
                        system({**now, "app_started": time.time() - 600, "grace": 0})
                        stale = wait(pag, "() => !!document.querySelector('[data-app-line=claude] .label.error') && !!document.querySelector('[data-app-line=claude] button[data-action=reopen]')", timeout=20)
                        said = pag.inner_text("[data-app-line=claude] .label") if stale else ""
                        mark(f"{language}: app di Claude: aperta da prima, il pannello dice che è senza protezione e offre di riaprirla", stale and "app.proxy" not in said, said)
                        # una versione vecchia dell'app, vista mesi fa, che il proxy non leggeva: non pesa su quella in uso
                        past = sqlite3.connect(paths.DATA / "contacts.sqlite", timeout=10)
                        past.execute("INSERT OR REPLACE INTO clients VALUES ('claude', 'proxy', 'Claude 1.0.0', '2026-01-01 10:00:00', '2026-01-01 10:00:05')")
                        past.commit()
                        past.close()
                        activity.Log().write(service="claude", client="Claude 1.0.0", event="rpc_not_read", method="POST",
                                             path="/rpc/Vecchia/Invia", kind="application/proto", structure="non letto")
                        # riaperta, passa dal proxy e manda un messaggio con dati inventati: il pannello dice che funziona
                        system({**now, "app_started": time.time() - 1, "grace": 90})
                        try:
                            body = json.dumps({"prompt": TEXT, "attachments": [], "rendering_mode": "messages"}, ensure_ascii=False).encode("utf-8")
                            via = urllib.request.build_opener(urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{port}"}))
                            req = urllib.request.Request("http://127.0.0.1:9911/api/organizations/o1/chat_conversations/c1/completion", data=body, headers={
                                "Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 (KHTML, like Gecko) Claude/9.9.9 Chrome/156.0 Electron/45.3 Safari/537.36"})
                            answer = via.open(req, timeout=120).read().decode("utf-8")
                            works = wait(pag, "() => !!document.querySelector('[data-app-line=claude] .label.ok') && !!document.querySelector('[data-app-note=proxy-numbers]')", timeout=20)
                            mark(f"{language}: app di Claude: quando passa dal proxy e manda un messaggio, il pannello dice che funziona",
                                 works and len(answer) > 20, pag.inner_text("[data-app-line=claude] .label"))

                            # le chiamate di servizio dell'app (la lingua, un orario) non sono messaggi non letti; un campo
                            # sconosciuto con una frase dentro si': il pannello lo dice e offre di segnalarlo
                            def send(path, content):
                                r = urllib.request.Request("http://127.0.0.1:9911" + path, data=json.dumps(content, ensure_ascii=False).encode("utf-8"),
                                                           headers={"Content-Type": "application/json", "User-Agent": req.get_header("User-agent")})
                                try:
                                    via.open(r, timeout=120).read()
                                except urllib.error.HTTPError:
                                    pass   # il servizio finto non conosce l'indirizzo: conta che la richiesta sia passata dal proxy

                            def state():
                                return next(a for a in call(code, "/api/app") if a["id"] == "claude")["proxy"]
                            time.sleep(1.2)   # il registro segna i secondi: ogni passo in un secondo diverso
                            send("/api/organizations/o1/preferences", {"displayLanguage": "it-IT", "timezone": "Europe/Rome", "ms": 1200})
                            time.sleep(1.2)
                            calm = state()
                            mark(f"{language}: app di Claude: una chiamata di servizio e una versione vecchia non letta non la fanno «da ricontrollare»",
                                 calm["state"] == "protected" and not calm["to_recheck"] and not pag.locator("[data-app-note=proxy-recheck]").count()
                                 and pag.locator("[data-app-line=claude] .label.ok").count() == 1, f"stato {calm['state']}")
                            send("/api/organizations/o1/notes", {"note": "Buongiorno, vorrei spostare l'appuntamento di domani mattina"})
                            doubt = wait(pag, "() => !!document.querySelector('[data-app-note=proxy-recheck] button[data-report]')", timeout=20)
                            mark(f"{language}: app di Claude: un testo in un campo sconosciuto la fa «da ricontrollare», con «Segnala il problema»",
                                 doubt and state()["to_recheck"], pag.inner_text("[data-app-line=claude] .label"))
                            # dopo un aggiornamento di Omissis gli avvisi di prima non restano: contano da quando lavora la versione nuova
                            marks = paths.DATA / "app_proxy.json"
                            before_marks = marks.read_text(encoding="utf-8")
                            marks.write_text(json.dumps({**json.loads(before_marks), "_version " + report.VERSION: time.time() + 5}), encoding="utf-8")
                            gone = wait(pag, "() => !document.querySelector('[data-app-note=proxy-recheck]') && !!document.querySelector('[data-app-line=claude] .label.ok')", timeout=20)
                            marks.write_text(before_marks, encoding="utf-8")
                            back = wait(pag, "() => !!document.querySelector('[data-app-note=proxy-recheck]')", timeout=20)
                            mark(f"{language}: app di Claude: un avviso nato prima di questa versione di Omissis non resta", gone and back and "_version " + report.VERSION in before_marks,
                                 f"sparito {gone} · tornato {back}")
                            time.sleep(1.2)
                            send("/api/organizations/o1/chat_conversations/c1/completion", {"prompt": TEXT, "attachments": [], "rendering_mode": "messages"})
                            clear = wait(pag, "() => !document.querySelector('[data-app-note=proxy-recheck]') && !!document.querySelector('[data-app-line=claude] .label.ok')", timeout=20)
                            mark(f"{language}: app di Claude: dopo un messaggio sostituito torna «funziona»", clear and not state()["to_recheck"],
                                 pag.inner_text("[data-app-line=claude] .label"))
                        except OSError as ex:
                            print(f"SALTATO app di Claude vista dal proxy: serve mock_service.py 9911 ({type(ex).__name__})")
                        # qualcuno toglie il certificato o cambia la rete: il pannello lo dice e offre «Sistema»
                        system({**now, "certificate": False})
                        broken = wait(pag, "() => !!document.querySelector('[data-app-note=proxy-problem]') && !!document.querySelector('[data-app-line=claude] button[data-action=proxy_on]')", timeout=20)
                        problem = pag.inner_text("[data-app-note=proxy-problem]") if broken else ""
                        mark(f"{language}: app di Claude: se il certificato sparisce il pannello lo dice e offre di sistemare", broken and "app.proxy" not in problem and len(problem) > 30, problem[:70])
                        pag.click("[data-app-line=claude] button[data-action=proxy_on]")
                        pag.wait_for_selector("#confirm[open]", timeout=5000)
                        pag.click("#confirmYes")
                        fixed = wait(pag, "() => !document.querySelector('[data-app-note=proxy-problem]')", timeout=20) and system().get("certificate") is True
                        # si toglie: il sistema torna com'era
                        pag.click("[data-app-line=claude] button[data-action=proxy_off]")
                        pag.wait_for_selector("#confirm[open]", timeout=5000)
                        pag.click("#confirmYes")
                        off = wait(pag, "() => !!document.querySelector('[data-app-line=claude] button[data-action=proxy_on]') && !document.querySelector('[data-app-line=claude] button[data-action=proxy_off]')", timeout=20)
                        mark(f"{language}: app di Claude: «Sistema» rimette a posto e «Togli la protezione» lascia il sistema com'era",
                             fixed and off and not system().get("pac") and call(code, "/api/settings")["app_proxy"] == [], f"sistemato {fixed} · tolto {off}")
                    except Exception as ex:   # noqa: BLE001
                        mark(f"{language}: app di Claude protetta dal proxy del sistema", False, f"{type(ex).__name__}: {ex}"[:200])
                    finally:
                        try:
                            call(code, "/api/app", {"id": "claude", "action": "proxy_off"})
                        except Exception:   # noqa: BLE001
                            pass
                        Path(fake).write_text("{}", encoding="utf-8")

                # --- il Mac: cio' che su Windows fa l'installer (spostare l'app in Applicazioni, avvio all'accesso, toglierla).
                # Senza un Mac: il file che fa da sistema dice dove «sta» l'app, e annota cio' che il pannello chiede di fare
                if fake:
                    try:
                        def system(change=None):
                            if change is not None:
                                Path(fake).write_text(json.dumps(change), encoding="utf-8")
                            return json.loads(Path(fake).read_text(encoding="utf-8")) if Path(fake).exists() else {}
                        system({"mac_location": "move"})
                        pag.goto(PANEL + "/#/start")
                        pag.reload()
                        pag.wait_for_selector("#update button[data-system=move]", timeout=15000)
                        wait(pag, "() => document.querySelector('#sideText').textContent.trim().length > 0", timeout=10)
                        said = pag.inner_text("#update")
                        blind = pag.evaluate(WITHOUT_NAME)
                        pag.click("#update button[data-system=move]")
                        pag.wait_for_selector("#confirm[open]", timeout=5000)
                        asked = pag.inner_text("#confirm")
                        pag.click("#confirmYes")
                        moved = wait_until(lambda: system().get("mac_location") == "ok", 10)
                        gone = wait(pag, "() => !document.querySelector('#update button[data-system=move]')", timeout=15)
                        mark(f"{language}: Mac: l'app aperta dal disco di installazione si sposta in Applicazioni con un clic e una conferma",
                             moved and gone and not blind and "mac.move" not in said + asked and len(said) > 60 and len(asked) > 80, said[:90].replace("\n", " "))

                        pag.goto(PANEL + "/#/settings/general")
                        pag.reload()
                        pag.wait_for_selector("#macLogin", state="attached", timeout=15000)
                        wait(pag, "() => document.querySelector('#sideText').textContent.trim().length > 0", timeout=10)
                        card = pag.inner_text("#macCard")
                        blind = pag.evaluate(WITHOUT_NAME)
                        pag.click("#macLogin")
                        on = wait_until(lambda: system().get("login_item") is True, 10)
                        pag.wait_for_timeout(600)
                        pag.click("#macLogin")
                        off = wait_until(lambda: system().get("login_item") is False, 10)
                        mark(f"{language}: Mac: nelle impostazioni l'avvio all'accesso si accende e si spegne con un interruttore",
                             on and off and not blind and "mac." not in card and len(card) > 120, f"acceso {on} · spento {off} · senza nome {blind[:2]}")

                        pag.wait_for_timeout(600)
                        pag.click("#macRemove")
                        pag.wait_for_selector("#confirm[open]", timeout=5000)
                        kept = pag.inner_text("#confirm")
                        pag.click("#confirmNo")
                        still = not system().get("uninstalled")
                        pag.check("#macData")
                        pag.click("#macRemove")
                        pag.wait_for_selector("#confirm[open]", timeout=5000)
                        deleted = pag.inner_text("#confirm")
                        pag.click("#confirmYes")
                        pag.wait_for_selector("#goodbye", timeout=15000)
                        bye = pag.inner_text("#goodbye")
                        mark(f"{language}: Mac: «Togli Omissis» chiede conferma, dice che fine fanno i dati e poi saluta",
                             still and kept != deleted and system().get("uninstalled") == {"data": True} and "mac.remove" not in kept + deleted + bye and len(bye) > 30,
                             bye[:80])

                        # nella configurazione guidata: al primo passo l'avviso di spostamento, tra i controlli l'avvio all'accesso
                        system({"mac_location": "move"})
                        pag.goto(PANEL + "/#/welcome")
                        pag.reload()
                        pag.wait_for_selector("#welcome[open] button[data-system=move]", timeout=30000)
                        first = pag.inner_text("#welcome")
                        system({"mac_location": "ok", "login_item": False})
                        for step in (2, 3, 4, 5, 6):
                            pag.click("#welcomeSkip")
                            pag.wait_for_selector(f'#welcome[data-step="{step}"]', timeout=15000)
                        pag.wait_for_selector("#welcomeLogin", state="attached", timeout=5000)
                        wait(pag, "() => document.querySelector('#sideText').textContent.trim().length > 0", timeout=10)
                        blind = pag.evaluate(WITHOUT_NAME)
                        sixth = pag.inner_text("#welcome")
                        pag.click("#welcomeLogin")
                        guided = wait_until(lambda: system().get("login_item") is True, 10)
                        pag.click("#welcomeExit")
                        wait(pag, "() => !document.getElementById('welcome').open", timeout=5)
                        mark(f"{language}: Mac: la configurazione guidata propone di spostare l'app e, tra i controlli, l'avvio all'accesso",
                             guided and not blind and "mac." not in first + sixth, f"acceso {guided} · senza nome {blind[:2]}")

                        # su un Mac la pagina parla del Mac: tasti, barra dei menu, Portachiavi (e mai «questo PC»)
                        system({"mac_location": "ok"})
                        mac = ctx.new_page()
                        mac.add_init_script("Object.defineProperty(Navigator.prototype, 'platform', {get: () => 'MacIntel'})")
                        seen, wrong = {}, []
                        for view in ("start", "guide", "settings/general", "vault", "connections/proxy"):
                            mac.goto(f"{PANEL}/#/{view}")
                            mac.reload()
                            mac.wait_for_selector("#panel > *")
                            mac.wait_for_timeout(900)
                            seen[view] = mac.inner_text("main")
                            # nella Guida i nomi dei tasti delle scorciatoie li scrive il programma, che qui gira su Windows
                            wrong += [f"{view}: {w}" for w in ("Windows", "orologio", "clock", "questo PC", "this PC", "Ctrl", "AltGr")
                                      if w in seen[view] and not (w == "Ctrl" and view == "guide")]
                        mac.close()
                        mark(f"{language}: Mac: su un Mac la pagina nomina i tasti, la barra dei menu e il Portachiavi del Mac, non quelli di Windows",
                             not wrong and "Control" in seen["settings/general"] and "Cmd" in seen["guide"]
                             and ("Portachiavi" if language == "it" else "Keychain") in seen["vault"] and "Mac" in seen["start"], "; ".join(wrong[:5]))
                    except Exception as ex:   # noqa: BLE001
                        mark(f"{language}: Mac: spostamento, avvio all'accesso e disinstallazione dal pannello", False, f"{type(ex).__name__}: {ex}"[:200])
                    finally:
                        Path(fake).write_text("{}", encoding="utf-8")
                        pag.goto(PANEL + "/#/connections/app")   # dove stavano le prove di prima e dove riprendono quelle dopo
                        pag.reload()
                        pag.wait_for_selector("#menu a")

                # --- il comando per i plugin delle app AI: si installa e si toglie dal pannello (nelle prove il PATH vero non viene toccato)
                try:
                    import hook_command
                    hook_command.remove()
                    pag.reload()
                    pag.wait_for_selector("[data-hook=off] #hookToggle", timeout=15000)
                    how = pag.inner_text("[data-hook-note=how]")
                    waiting = pag.is_disabled("#antigravityToggle")   # senza il comando, Antigravity non si collega
                    pag.click("#hookToggle")
                    on = wait(pag, "() => !!document.querySelector('[data-hook=on] .label.ok')", timeout=15)
                    there = hook_command.state()
                    pag.click("#antigravityToggle")
                    linked = wait(pag, "() => !!document.querySelector('[data-hook-antigravity=on] .label.ok')", timeout=15)
                    in_file = hook_command.antigravity_state()["linked"]
                    shown = pag.inner_text("#hookCommand")
                    pag.click("#antigravityToggle")
                    unlinked = wait(pag, "() => !!document.querySelector('[data-hook-antigravity=off]')", timeout=15) and not hook_command.antigravity_state()["linked"]
                    mark(f"{language}: Antigravity: «Collega» si può solo col comando installato, scrive la voce di Omissis nel file degli hook di Antigravity, «Scollega» la toglie",
                         waiting and linked and in_file and unlinked and "Antigravity" in shown and "hooks." not in shown, f"in attesa {waiting} · collegato {linked}/{in_file} · scollegato {unlinked}")
                    pag.click("#hookToggle")
                    off = wait(pag, "() => !!document.querySelector('[data-hook=off]')", timeout=15)
                    mark(f"{language}: comando per i plugin delle app AI: il pannello lo installa e lo toglie, e dice come installare il plugin in Kimi, Claude Code, Codex e Gemini CLI",
                         on and there["ready"] and there["on_path"] and off and not hook_command.state()["ready"] and all(x in how for x in ("Kimi", "Claude Code", "Codex", "Gemini CLI"))
                         and how.count("francescogruner/omissis") >= 4 and "hooks." not in how + pag.inner_text("#hookCommand"), f"installato {on} · tolto {off} · {how[:70]}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: comando per i plugin delle app AI", False, str(ex)[:160])

                # --- server MCP: si registra e si toglie dalla configurazione di Claude Desktop (nelle prove, un file tra i dati di prova)
                try:
                    cfg = paths.DATA / "claude_desktop_config.json"
                    cfg.write_text(json.dumps({"mcpServers": {"altro": {"command": "x"}}}), encoding="utf-8")
                    pag.goto(f"{PANEL}/#/connections/mcp")
                    pag.wait_for_selector("button[data-mcp=install]", timeout=15000)
                    pag.click("button[data-mcp=install]")
                    on = wait(pag, "() => document.getElementById('mcpStatus').classList.contains('ok') && !!document.querySelector('button[data-mcp=uninstall]')", timeout=15)
                    written = json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]
                    pag.click("button[data-mcp=uninstall]")
                    off = wait(pag, "() => !!document.querySelector('button[data-mcp=install]') && !document.querySelector('button[data-mcp=uninstall]')", timeout=15)
                    left = json.loads(cfg.read_text(encoding="utf-8"))["mcpServers"]
                    mark(f"{language}: server MCP registrato e tolto dal pannello, senza toccare gli altri server", on and off and set(written) == {"altro", "omissis"}
                         and written["omissis"]["args"][0].endswith("mcp_server.py") and left == {"altro": {"command": "x"}}
                         and pag.locator("button[data-copy]").count() == 3)
                    cfg.unlink()
                    cfg.with_name(cfg.name + ".omissis-backup").unlink(missing_ok=True)
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: server MCP registrato e tolto dal pannello, senza toccare gli altri server", False, str(ex)[:160])

                # --- terminale: le righe per Codex in abbonamento, e l'indirizzo di un gateway proprio salvato e tolto
                try:
                    stored = lambda: json.loads((paths.DATA / "settings.json").read_text(encoding="utf-8")).get("gateway_upstreams")   # noqa: E731
                    pag.goto(f"{PANEL}/#/connections/terminal")
                    pag.wait_for_selector("input[data-own=anthropic]", timeout=15000)
                    wait(pag, "() => document.querySelectorAll('#gwLines pre').length >= 4", timeout=15)
                    codex = pag.evaluate("[...document.querySelectorAll('#gwLines pre')].map(p => p.textContent).find(t => t.includes('model_providers')) || ''")
                    pag.fill("input[data-own=anthropic]", "https://gateway.azienda.example/llm")
                    pag.click("#ownSave")
                    saved = wait_until(lambda: stored() == {"anthropic": "https://gateway.azienda.example/llm"})
                    known = len(errors)
                    pag.fill("input[data-own=anthropic]", "non-un-indirizzo")
                    pag.click("#ownSave")
                    pag.wait_for_timeout(600)
                    refused = stored() == {"anthropic": "https://gateway.azienda.example/llm"} and len(errors) == known + 1 and "422" in errors[-1]
                    del errors[known:]   # il rifiuto era voluto: non e' un errore del giro
                    pag.fill("input[data-own=anthropic]", "")
                    pag.click("#ownSave")
                    cleared = wait_until(lambda: stored() == {})
                    mark(f"{language}: terminale, righe per Codex in abbonamento e gateway proprio salvato, rifiutato se non valido, tolto",
                         "requires_openai_auth = true" in codex and "/openai/v1" in codex and saved and refused and cleared, f"salvato {saved} · rifiutato {refused} · tolto {cleared}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: terminale, righe per Codex in abbonamento e gateway proprio salvato, rifiutato se non valido, tolto", False, str(ex)[:160])

                # --- l'uso manuale entra nel registro (solo conteggi): un testo conta una volta anche se corretto a mano, un documento una volta
                try:
                    def manual_rows():
                        rows = [json.loads(x) for x in (paths.DATA / "activity.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
                        return [r for r in rows if r.get("service") == "manual"]
                    start = len(manual_rows())
                    sample = f"Prova {language}: scrivere a Ottavio Bellandi, ottavio.bellandi@nevatek.example, cellulare 347 5550199."
                    first = call(code, "/api/try", {"text": sample})
                    call(code, "/api/try", {"text": sample})                                     # di nuovo lo stesso testo
                    call(code, "/api/try", {"text": sample, "never": ["Ottavio Bellandi"]})        # una correzione a mano
                    after_text = manual_rows()[start:]
                    doc = call(code, "/api/documents/file", {"name": "nota.txt", "action": "anonymize",
                                                             "content": base64.b64encode(sample.encode("utf-8")).decode("ascii")})
                    after_doc = manual_rows()[start:]
                    leaked = any("Bellandi" in json.dumps(r, ensure_ascii=False) or "nevatek" in json.dumps(r) for r in after_doc)
                    summary = call(code, "/api/console", {"action": "preview"})["preview"]["days"][-1]
                    shown = dict(call(code, "/api/status")["stats"]["services"]).get("manual", 0)
                    mark(f"{language}: l'uso manuale entra nel registro con i soli conteggi e finisce nel riepilogo per la console",
                         len(after_text) == 1 and after_text[0]["via"] == "text" and after_text[0]["replacements"] == first["counts"]
                         and len(after_doc) == 2 and after_doc[1]["via"] == "document" and doc["counts"] == after_doc[1]["replacements"]
                         and not leaked and summary["services"].get("manual", 0) >= 2 and shown >= 2,
                         f"testo {len(after_text)} · documento {len(after_doc) - len(after_text)} · nel riepilogo {summary['services'].get('manual')}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: l'uso manuale entra nel registro", False, str(ex)[:160])

                # --- impostazioni decise da chi amministra il PC: nella pagina si vedono ferme, e il programma rifiuta di cambiarle
                try:
                    imposed = os.environ.get("OMISSIS_MANAGED_FILE")
                    if not imposed:
                        print("SALTATO impostazioni imposte: senza OMISSIS_MANAGED_FILE la prova non può imporre nulla")
                    else:
                        Path(imposed).write_text(json.dumps({"updates": "never", "policies": {"deepseek": "block"}}), encoding="utf-8")
                        fixed = wait_until(lambda: call(code, "/api/settings")["managed"] == {"keys": ["updates"], "policies": ["deepseek"], "console": []}, timeout=15)
                        pag.goto(f"{PANEL}/#/settings/general")
                        pag.wait_for_selector("#updates", state="attached", timeout=15000)
                        shown = wait(pag, "() => document.getElementById('updates').disabled && document.getElementById('updates').value === 'never' && !!document.getElementById('managedNote')", timeout=10)
                        refused = []
                        for path, data in (("/api/settings", {"updates": "automatic"}), ("/api/services", {"id": "deepseek", "policy": "ignore"})):
                            try:
                                call(code, path, data)
                                refused.append(False)
                            except urllib.error.HTTPError as ex:
                                refused.append(ex.code == 422)
                        free = call(code, "/api/settings", {"theme": "light"})["updates"] == "never"   # il resto si cambia come sempre
                        Path(imposed).unlink()
                        back = wait_until(lambda: call(code, "/api/settings")["managed"] == {"keys": [], "policies": [], "console": []}, timeout=15)
                        mark(f"{language}: impostazioni imposte dall'amministratore: ferme nella pagina, rifiutate dal programma, libere quando il vincolo sparisce",
                             fixed and shown and refused == [True, True] and free and back, f"imposte {fixed} · pagina {shown} · rifiuti {refused} · tolte {back}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: impostazioni imposte dall'amministratore", False, str(ex)[:160])
                finally:
                    if os.environ.get("OMISSIS_MANAGED_FILE"):
                        Path(os.environ["OMISSIS_MANAGED_FILE"]).unlink(missing_ok=True)

                # --- protezione che non si puo' spegnere (imposta da chi amministra il PC, o dalla console): pulsante fermo, richiesta rifiutata
                try:
                    imposed = os.environ.get("OMISSIS_MANAGED_FILE")
                    if not imposed:
                        print("SALTATO protezione sempre accesa: senza OMISSIS_MANAGED_FILE la prova non può imporre nulla")
                    else:
                        try:   # da sola non si accende dal pannello: si puo' solo imporre
                            own = call(code, "/api/settings", {"always_on": True}).get("always_on") is False
                        except urllib.error.HTTPError:
                            own = False
                        Path(imposed).write_text(json.dumps({"always_on": True}), encoding="utf-8")
                        fixed = wait_until(lambda: call(code, "/api/status").get("always_on") is True, timeout=15)
                        pag.goto(f"{PANEL}/#/start")
                        pag.wait_for_selector("#main_switch")
                        shown = wait(pag, "() => document.getElementById('main_switch').disabled && !!document.getElementById('main_switch').title "
                                          "&& document.getElementById('belowStatus').textContent.includes(document.getElementById('main_switch').title)", timeout=15)
                        try:
                            call(code, "/api/protection", {"action": "stop"})
                            refused = False
                        except urllib.error.HTTPError as ex:
                            refused = ex.code == 422
                        still = call(code, "/api/status")["phase"] == "active"
                        Path(imposed).unlink()
                        back = wait_until(lambda: call(code, "/api/status").get("always_on") is False, timeout=15)
                        released = wait(pag, "() => !document.getElementById('main_switch').disabled && !document.getElementById('main_switch').title", timeout=15)
                        relit = True
                        if language == "it":   # il vincolo arriva mentre la protezione e' ferma: il programma la riaccende da solo
                            call(code, "/api/protection", {"action": "stop"})
                            stopped = call(code, "/api/status")["phase"] == "stop"
                            Path(imposed).write_text(json.dumps({"always_on": True}), encoding="utf-8")
                            relit = stopped and wait_until(lambda: call(code, "/api/status")["phase"] == "active", timeout=120)
                            Path(imposed).unlink()
                            wait_until(lambda: call(code, "/api/status").get("always_on") is False, timeout=15)
                        mark(f"{language}: protezione che non si può spegnere: non si sceglie dal pannello; imposta, il pulsante è fermo e la richiesta è rifiutata; ferma, si riaccende; tolta, torna libero",
                             own and fixed and shown and refused and still and back and released and relit,
                             f"dal pannello {own} · imposta {fixed} · pagina {shown} · rifiuto {refused} · ancora attiva {still} · tolta {back} · libero {released} · riaccesa {relit}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: protezione che non si può spegnere", False, str(ex)[:160])
                finally:
                    if os.environ.get("OMISSIS_MANAGED_FILE"):
                        Path(os.environ["OMISSIS_MANAGED_FILE"]).unlink(missing_ok=True)

                # --- console centrale: di serie il PC non manda nulla; un indirizzo non https è rifiutato; si vede che cosa partirebbe
                try:
                    pag.goto(f"{PANEL}/#/settings/general")
                    card = wait(pag, "() => !!document.getElementById('conUrl') && !!document.getElementById('conKey') && !!document.getElementById('conPin')", timeout=15)
                    state = call(code, "/api/console")
                    try:
                        call(code, "/api/console", {"action": "connect", "url": "http://console.example.test", "key": "chiave-di-prova"})
                        bad = False
                    except urllib.error.HTTPError as ex:
                        bad = ex.code == 422
                    preview = call(code, "/api/console", {"action": "preview"})["preview"]
                    hidden_key = "console_key" not in call(code, "/api/settings")
                    mark(f"{language}: console centrale: non collegata di serie, indirizzo non https rifiutato, anteprima di ciò che partirebbe",
                         card and not state["configured"] and bad and {"device", "days", "tools", "version"} <= set(preview) and hidden_key
                         and not call(code, "/api/console")["configured"], f"scheda {card} · rifiuto {bad}")
                    # collegato a una console (qui spenta): le sue regole si accettano solo per scelta, con l'interruttore
                    call(code, "/api/console", {"action": "connect", "url": "http://127.0.0.1:9", "key": "chiave-di-prova"})
                    pag.reload()
                    shown = wait(pag, "() => !!document.getElementById('conRules')", timeout=15)
                    before = call(code, "/api/console")["rules"]
                    pag.evaluate("document.getElementById('conRules').click()")
                    accepted = wait_until(lambda: call(code, "/api/console")["rules"]["accept"] is True, timeout=30)
                    text = pag.inner_text("#console")
                    call(code, "/api/console", {"action": "rules", "accept": False})
                    call(code, "/api/console", {"action": "disconnect"})
                    mark(f"{language}: console centrale: le regole della console si accettano solo per scelta, con un interruttore nel pannello",
                         shown and before == {"accept": False, "managed": False, "version": 0, "count": 0, "received": ""} and accepted and "console.rules" not in text
                         and not call(code, "/api/console")["configured"] and call(code, "/api/console")["rules"]["accept"] is False, f"{before} · {text[:80]!r}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: console centrale", False, str(ex)[:160])

                # --- gruppi di dati: spegnerne uno chiede conferma, la pagina iniziale lo ricorda, riaccenderlo toglie l'avviso
                try:
                    off = lambda: json.loads((paths.DATA / "settings.json").read_text(encoding="utf-8")).get("groups_off")   # noqa: E731
                    pag.goto(f"{PANEL}/#/settings/recognition")
                    pag.wait_for_selector("#grp-it", state="attached", timeout=15000)
                    locked = pag.evaluate("!document.getElementById('grp-people') && !document.getElementById('grp-secrets') && document.getElementById('grp-it').checked")
                    pag.evaluate("document.getElementById('grp-it').click()")
                    pag.wait_for_selector("#confirm[open]", timeout=5000)
                    pag.click("#confirmNo")                            # ci ripensa: non cambia nulla
                    pag.wait_for_timeout(500)
                    kept = pag.evaluate("document.getElementById('grp-it').checked") and not off()
                    pag.evaluate("document.getElementById('grp-it').click()")
                    pag.wait_for_selector("#confirm[open]", timeout=5000)
                    pag.click("#confirmYes")
                    stored = wait_until(lambda: off() == ["it"])
                    pag.goto(f"{PANEL}/#/start")
                    warned = wait(pag, "() => !!document.querySelector('#reduced .note.warning')", timeout=15)
                    pag.goto(f"{PANEL}/#/settings/recognition")
                    pag.wait_for_selector("#grp-it", state="attached", timeout=15000)
                    wait(pag, "() => document.getElementById('grp-it').checked === false", timeout=10)
                    pag.evaluate("document.getElementById('grp-it').click()")   # riaccendere non chiede nulla
                    back = wait_until(lambda: off() == [])
                    pag.goto(f"{PANEL}/#/start")
                    pag.wait_for_selector("#main_switch")
                    cleared = wait(pag, "() => !document.querySelector('#reduced .note')", timeout=15)
                    mark(f"{language}: gruppi di dati, spegnere chiede conferma e la pagina iniziale lo ricorda; persone e segreti non si spengono",
                         locked and kept and stored and warned and back and cleared, f"fissi {locked} · ripensamento {kept} · spento {stored} · avviso {warned} · riacceso {back} · tolto {cleared}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: gruppi di dati, spegnere chiede conferma e la pagina iniziale lo ricorda; persone e segreti non si spengono", False, str(ex)[:160])

                # --- profilo dei dati: una scelta sola accende e spegne insieme gruppi e categorie; con «Essenziale» i nomi delle
                # aziende restano in chiaro senza che sia «protezione ridotta», e toccando una voce il profilo diventa «personalizzato»
                try:
                    cfg = lambda: json.loads((paths.DATA / "settings.json").read_text(encoding="utf-8"))   # noqa: E731
                    pag.goto(f"{PANEL}/#/settings/recognition")
                    pag.wait_for_selector("#profile", timeout=15000)
                    first = pag.input_value("#profile")   # la copia di prova parte con tutti i gruppi accesi
                    pag.select_option("#profile", "standard")
                    essential = wait_until(lambda: cfg().get("groups_off") == ["organizations"] and cfg().get("categories") == [])
                    shown = wait(pag, "() => document.getElementById('grp-organizations')?.checked === false && document.getElementById('profile')?.value === 'standard'", timeout=10)
                    pag.goto(f"{PANEL}/#/start")
                    pag.wait_for_selector("#main_switch")
                    pag.wait_for_timeout(1500)
                    quiet = pag.locator("#reduced .note").count() == 0
                    pag.goto(f"{PANEL}/#/settings/recognition")
                    pag.wait_for_selector("#profile", timeout=15000)
                    pag.select_option("#profile", "special")
                    special = wait_until(lambda: cfg().get("groups_off") == [] and len(cfg().get("categories") or []) == 5)
                    wait(pag, "() => document.getElementById('grp-organizations')?.checked === true && document.getElementById('profile')?.value === 'special'", timeout=10)
                    pag.evaluate("document.getElementById('grp-organizations').click()")   # un gruppo facoltativo: spegnerlo non chiede conferma
                    custom = wait_until(lambda: cfg().get("groups_off") == ["organizations"]) and wait(pag, "() => document.getElementById('profile')?.value === 'custom'", timeout=10)
                    asked = pag.locator("#confirm[open]").count()
                    words = pag.inner_text("#grpTitle") + pag.evaluate("document.getElementById('profile').closest('.setting').innerText")
                    pag.select_option("#profile", "confidential")
                    back = wait_until(lambda: cfg().get("groups_off") == [] and cfg().get("categories") == [])
                    mark(f"{language}: profilo dei dati: «Essenziale» lascia in chiaro solo i nomi delle aziende, senza avviso di protezione ridotta; gli altri accendono insieme gruppi e categorie; una voce toccata a mano lo rende «personalizzato»",
                         first == "confidential" and essential and shown and quiet and special and custom and asked == 0 and back and "profile." not in words,
                         f"all'inizio {first} · essenziale {essential} · mostrato {shown} · nessun avviso {quiet} · dati particolari {special} · personalizzato {custom} · conferme {asked} · ripristinato {back}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: profilo dei dati", False, str(ex)[:160])

                # --- testo: incolla -> mascherato e copiato; incolla di nuovo -> valori veri
                pag.goto(f"{PANEL}/#/text")
                pag.wait_for_selector("#paste")
                pag.evaluate("t => navigator.clipboard.writeText(t)", TEXT)
                pag.click("#paste")
                wait(pag, "() => document.getElementById('outcome').textContent.includes('[PERSONA_')")
                pag.wait_for_timeout(500)
                clipboard = pag.evaluate("navigator.clipboard.readText()")
                mark(f"{language}: testo incollato -> mascherato e copiato da solo", "[PERSONA_" in clipboard and not any(s in clipboard for s in SENSITIVE),
                      f"in chiaro negli appunti: {sum(s in clipboard for s in SENSITIVE)}")
                pag.wait_for_timeout(600)
                pag.screenshot(path=str(photo / f"text-{language}.png"))

                # --- correzioni a mano: un segnaposto di troppo torna in chiaro, un dato sfuggito viene mascherato
                pag.click('#outcome button[data-s^="[ORG_"]')
                pag.click('#onPlaceholder button[data-make="light"]')
                wait(pag, "() => document.getElementById('outcome').textContent.includes('Nevatek S.r.l') && !document.getElementById('outcome').textContent.includes('[ORG_')")
                pag.wait_for_timeout(400)
                clipboard = pag.evaluate("navigator.clipboard.readText()")
                mark(f"{language}: correzione «lascia in chiaro» -> il testo è rifatto e ricopiato", "Nevatek S.r.l" in clipboard and "[PERSONA_" in clipboard and "Giulia Ferraresi" not in clipboard)
                pag.fill("#daMascherare", "gestionale")
                pag.click("#maskAlso")
                wait(pag, "() => document.getElementById('outcome').textContent.includes('[ELENCO_') && !document.getElementById('outcome').textContent.includes('gestionale')")
                pag.wait_for_timeout(400)
                clipboard = pag.evaluate("navigator.clipboard.readText()")
                mark(f"{language}: correzione «maschera anche questo» -> il dato sfuggito è sostituito", "[ELENCO_" in clipboard and "gestionale" not in clipboard and "Nevatek S.r.l" in clipboard)
                pag.screenshot(path=str(photo / f"text-corrections-{language}.png"))
                pag.click('#correctionsDone button[data-what="never"]')
                dropped = wait(pag, "() => document.getElementById('outcome').textContent.includes('[ORG_')", timeout=10)
                mark(f"{language}: una correzione si annulla con un clic", dropped and pag.locator("#correctionsDone button").count() == 1)
                pag.wait_for_timeout(400)
                pag.click("#paste")
                wait(pag, "t => document.getElementById('outcome').textContent === t", TEXT)
                pag.wait_for_timeout(500)
                mark(f"{language}: risposta incollata -> tornano i valori veri, già negli appunti", pag.evaluate("navigator.clipboard.readText()") == TEXT)

                # --- documento: trascinato -> anonimizzato e scaricato da solo; rimesso dentro -> ripristinato
                original = work / f"lettera-{language}.txt"
                original.write_text(TEXT, encoding="utf-8")
                pag.goto(f"{PANEL}/#/documents")
                pag.wait_for_selector("#choose", state="attached")
                with pag.expect_download(timeout=60000) as d:
                    pag.set_input_files("#choose", str(original))
                anonymous = work / d.value.suggested_filename
                d.value.save_as(str(anonymous))
                read_back = anonymous.read_text(encoding="utf-8")
                mark(f"{language}: documento -> copia anonimizzata scaricata da sola", ".anon" in anonymous.name and "[PERSONA_" in read_back
                      and not any(s in read_back for s in SENSITIVE), anonymous.name)
                pag.wait_for_timeout(400)
                pag.screenshot(path=str(photo / f"documents-{language}.png"))
                with pag.expect_download(timeout=60000) as d:
                    pag.set_input_files("#choose", str(anonymous))
                returned = work / d.value.suggested_filename
                d.value.save_as(str(returned))
                mark(f"{language}: documento con i segnaposto -> riconosciuto e ripristinato", ".restored" in returned.name
                      and returned.read_text(encoding="utf-8") == TEXT, returned.name)

                # --- cartella intera: scritto il percorso, la copia nasce accanto e si può aprire dal pannello
                case_file = work / f"pratica-{language}"
                case_file.mkdir()
                (case_file / "nota.txt").write_text(TEXT, encoding="utf-8")
                pag.fill("#folderPath", str(case_file))
                pag.click('button[data-folder="anonymize"]')
                done_one = wait(pag, "() => !!document.getElementById('openFolder')", timeout=60)
                copy_ = work / f"pratica-{language}.anon" / "nota.anon.txt"
                mark(f"{language}: cartella intera -> copia anonimizzata accanto, con il pulsante per aprirla", done_one and copy_.exists()
                      and not any(s in copy_.read_text(encoding="utf-8") for s in SENSITIVE))

                # --- archivio: si cerca per valore vero senza mostrarlo, si elimina una voce scelta
                pag.goto(f"{PANEL}/#/vault")
                pag.wait_for_selector("#archSearch")
                # prima l'archivio intero, poi la ricerca: le righe si leggono solo quando la tabella si e' ristretta
                wait(pag, "() => document.querySelectorAll('#tabVault tr').length > 0", timeout=15)
                everything = pag.evaluate("document.querySelectorAll('#tabVault tr').length")
                pag.fill("#archSearch", "ferraresi")
                wait(pag, f"() => {{ const r = document.querySelectorAll('#tabVault tr'); return r.length > 0 && r.length < {everything} && "
                          "[...document.querySelectorAll('#tabVault .placeholder')].some(e => e.textContent.startsWith('[PERSONA_')); }", timeout=15)
                lines = pag.evaluate("[...document.querySelectorAll('#tabVault tr')].map(r => r.innerText)")
                mark(f"{language}: archivio -> ricerca per valore vero, che resta nascosto", 1 <= len(lines) <= 30 and all("•" in r and "erraresi" not in r for r in lines), f"{len(lines)} voci")
                pag.wait_for_timeout(300)
                pag.screenshot(path=str(photo / f"vault-{language}.png"))
                before_n = call(code, "/api/vault", {"search": "gestionale", "label": "ELENCO"})["matches"]
                pag.fill("#archSearch", "gestionale")
                wait(pag, "() => [...document.querySelectorAll('#tabVault .placeholder')].some(e => e.textContent.startsWith('[ELENCO_'))", timeout=15)
                pag.check("#tabVault tr:has(.placeholder:text-matches('ELENCO_')) input[type=checkbox]")
                pag.click("#archRemove")
                pag.click("#confirmYes")
                pag.wait_for_timeout(1200)
                after_n = call(code, "/api/vault", {"search": "gestionale", "label": "ELENCO"})["matches"]
                mark(f"{language}: archivio -> eliminata la voce scelta, dopo la conferma", before_n >= 1 and after_n == before_n - 1, f"{before_n} -> {after_n}")

                # --- inventario Shadow AI: analisi salvate, novità, giudizio, esportazione
                pag.goto(f"{PANEL}/#/services/detected")
                pag.wait_for_selector("#invTable tr")
                pag.wait_for_timeout(500)
                views = pag.locator("#invTable tr").count()
                news = pag.locator("#invNews li").count()
                mark(f"{language}: inventario -> le analisi salvate si vedono senza rifarle, con le novità", views == 5 and news == 4, f"{views} voci presenti, {news} novità")
                pag.select_option("#invTable tr:has-text('Ollama') select", "approved")
                pag.fill("#invTable tr:has-text('Ollama') input", "prova in laboratorio")
                pag.keyboard.press("Tab")
                pag.wait_for_timeout(600)
                ollama = next(e for e in call(code, "/api/inventory")["items"] if e["name"] == "Ollama")
                mark(f"{language}: inventario -> giudizio e nota salvati", ollama["verdict"] == "approved" and ollama["note"] == "prova in laboratorio")
                pag.evaluate("document.activeElement.blur(); scrollTo(0, 0)")
                pag.wait_for_timeout(5500)   # gli avvisi delle prove precedenti spariscono dalla schermata
                pag.screenshot(path=str(photo / f"detected-{language}.png"))
                with pag.expect_download(timeout=30000) as d:
                    pag.click("#invExport")
                exported = work / f"inventario-{language}.csv"
                d.value.save_as(str(exported))
                lines = exported.read_text(encoding="utf-8-sig").strip().splitlines()
                mark(f"{language}: inventario -> esportazione per Excel", d.value.suggested_filename.endswith(".csv") and len(lines) == 7 and lines[0].count(";") == 8, f"{len(lines)} righe")
                inventory.judge(ollama["key"], "", "")

                # --- le schermate: ciò che vede l'utente normale, poi le sezioni del tecnico
                call(code, "/api/settings", {"view": "simple"})
                pag.goto(f"{PANEL}/#/start")
                pag.reload()
                pag.wait_for_selector("#titleStatus")
                pag.wait_for_timeout(1200)
                pag.screenshot(path=str(photo / f"start-{language}.png"))
                pag.goto(f"{PANEL}/#/guide")
                pag.wait_for_timeout(600)
                pag.screenshot(path=str(photo / f"guide-{language}.png"))
                call(code, "/api/settings", {"view": "advanced"})
                pag.reload()
                for view in ("connections/terminal", "services/rules", "settings/general"):
                    pag.goto(f"{PANEL}/#/{view}")
                    pag.wait_for_selector("#panel > *")
                    pag.wait_for_timeout(1200)
                    pag.screenshot(path=str(photo / f"{view.split('/')[-1] if view.startswith('conn') else view.split('/')[0]}-{language}.png"))
                mark(f"{language}: nessun errore durante il giro completo", not errors, "; ".join(errors[:3]))
                errors.clear()

            # --- scorciatoie: la lettera scelta nella pagina arriva nelle impostazioni
            pag.goto(f"{PANEL}/#/settings/general")
            pag.wait_for_selector('select[data-sc="mask"]')
            pag.select_option('select[data-sc="mask"]', "ctrl+alt+k")
            pag.wait_for_timeout(800)
            pag.select_option('select[data-sc="restore"]', "")
            pag.wait_for_timeout(800)
            choices = call(code, "/api/settings")["shortcuts"]
            mark("scorciatoie: lettera cambiata e scorciatoia spenta dalla pagina", choices == {"replace": "ctrl+alt+s", "mask": "ctrl+alt+k", "restore": ""}, str(choices))

            # --- elenchi personali da Testo e testi troppo lunghi (solo se gli elenchi sono quelli della copia di prova)
            if os.environ.get("OMISSIS_LISTS"):
                listings = call(code, "/api/lists")
                try:
                    call(code, "/api/lists/add", {"list_name": "never", "term": "aldo.bruschi@nevatek.example"})
                    call(code, "/api/lists/add", {"list_name": "always", "term": "gestionale"})
                    r = call(code, "/api/try", {"text": TEXT})["texts"][0]
                    mark("elenchi: «non mascherare mai» vale anche per ciò che trovano le regole, «maschera sempre» aggiunge",
                          "aldo.bruschi@nevatek.example" in r and "[ELENCO_" in r and "gestionale" not in r and "[PERSONA_" in r, r[:120])
                finally:
                    call(code, "/api/lists", listings)
            else:
                print("SALTATO elenchi personali: senza OMISSIS_LISTS toccherebbe gli elenchi veri")
            try:
                call(code, "/api/try", {"text": "parola " * 40000})
                mark("testo troppo lungo: rifiutato, non tagliato in silenzio", False)
            except urllib.error.HTTPError as ex:
                mark("testo troppo lungo: rifiutato, non tagliato in silenzio", ex.code == 422)

            # --- l'analisi vera di questo PC, dal pulsante: viene salvata come una in più (i nomi restano su questo PC)
            pag.goto(f"{PANEL}/#/services/detected")
            pag.wait_for_selector("#analyze")
            saved = call(code, "/api/inventory")["scan_count"]
            pag.click("#analyze")
            done_one = wait(pag, "() => !document.getElementById('analyze').disabled", timeout=180)
            after = call(code, "/api/inventory")
            mark("inventario: «Analizza ora» fotografa il PC e salva l'analisi", done_one and after["scan_count"] == saved + 1 and after["scan"][0]["origin"] == "manual",
                  f"{after['scan'][0]['seconds']} s, {after['scan'][0]['items']} voci")
            # --- la segnalazione di un problema: si vede per intero prima di partire, e dentro non c'e' nulla di chi usa il PC
            _, at = report.news(None)
            activity.Log().write(service="test", via="proxy", client="AppDiProva 9.9", event="blocked_rpc_not_read", method="POST", path="/rpc/Servizio/Invia",
                                 kind="application/proto", structure={"1": "str36", "2": {"1": "str120"}, "mario rossi@esempio": "str5"})
            fresh, _ = report.news(at)
            mark("segnalazione: un messaggio fermato perché non letto fa partire l'avviso", ("blocked", "test", "AppDiProva 9.9") in fresh, str(fresh)[:80])
            r = call(code, "/api/report?what=AppDiProva")
            hidden = [p.read_text(encoding="utf-8").strip() for p in paths.DATA.glob("token*.txt")] + [code, str(Path.home())]
            mark("segnalazione: dice versione, sistema e programma", report.VERSION in r["title"] and "AppDiProva 9.9" in r["title"] and report.system() in r["text"], r["title"])
            mark("segnalazione: porta la forma della richiesta non letta, senza i nomi di campo sospetti", "blocked_rpc_not_read" in r["text"]
                 and "/rpc/Servizio/Invia" in r["text"] and '"(…)"' in r["text"] and "mario rossi" not in r["text"])
            mark("segnalazione: dentro non ci sono codici né cartelle di questo PC", not any(s and s in r["text"] + r["title"] for s in hidden))
            pag.goto(f"{PANEL}/#/connections/compatibility")
            pag.wait_for_selector("#reportCompatibility")
            pag.evaluate("() => { window.open = u => { window.__opened = u; }; }")
            pag.click("#reportCompatibility")
            shown = wait(pag, "() => !!document.querySelector('dialog#report[open]') && document.getElementById('reportText').textContent.includes('Omissis')", timeout=10)
            pag.fill("#reportNote", "prova")
            pag.click("#reportGithub")
            wait(pag, "() => !!window.__opened", timeout=8)   # se il testo e' lungo prima lo copia negli appunti, poi apre
            opened = pag.evaluate("() => window.__opened || ''")
            mark("segnalazione: la finestra mostra il testo intero e apre GitHub con il testo già scritto", shown and opened.startswith(report.ISSUES + "?title=")
                 and "prova" in urllib.parse.unquote(opened) and len(opened) < 7600, f"{len(opened)} caratteri")
            pag.click("#reportCopy")
            copied = pag.evaluate("() => navigator.clipboard.readText()")
            mark("segnalazione: «Copia» mette negli appunti la nota e il testo", copied.startswith("prova") and "blocked_rpc_not_read" in copied)
            narrow = pag.evaluate("() => { const d = document.querySelector('dialog#report'); return d.scrollWidth <= d.clientWidth + 1; }")
            pag.click("#reportClose")
            mark("segnalazione: la finestra si chiude e non esce dai bordi", narrow and not pag.evaluate("() => document.querySelector('dialog#report').open"))
            mark("nessun errore nelle prove finali", not errors, "; ".join(errors[:3]))
            errors.clear()

            # --- tema scuro e schermo stretto
            call(code, "/api/settings", {"language": "it", "theme": "dark", "view": "advanced"})
            pag.goto(f"{PANEL}/#/start")
            pag.reload()
            pag.wait_for_selector("#titleStatus")
            pag.wait_for_timeout(1200)
            pag.screenshot(path=str(photo / "start-dark.png"))
            dark = pag.evaluate("getComputedStyle(document.body).backgroundColor")
            pag.set_viewport_size({"width": 390, "height": 800})
            pag.wait_for_timeout(500)
            width = pag.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            pag.screenshot(path=str(photo / "start-phone.png"))
            mark("tema scuro applicato, e su uno schermo stretto la pagina non esce dai bordi", dark == "rgb(10, 10, 10)" and width, f"{dark} · {width}")
        finally:
            call(code, "/api/settings", {k: before[k] for k in ("language", "theme", "view", "shortcuts") if k in before})
            inventory.clear()
            br.close()
            try:   # l'app di prova avviata dal pannello resta accesa dopo «Stacca»: la si chiude qui
                app = connector.Cdp(connector.APP.get("test", {}).get("port", 9560), lambda m: None)
                app.send("Browser.close", timeout=5)
                app.close()
            except Exception:   # noqa: BLE001  (non era stata avviata)
                pass

    print(f"\n{sum(outcomes)}/{len(outcomes)} controlli superati · schermate in {photo}")
    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
