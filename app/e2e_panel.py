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
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

import catalog
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

                # --- configurazione guidata (qui la si apre a mano: durante le prove non si propone da sola)
                try:
                    today = lambda: call(code, "/api/status")["stats"]["today"]["messages"]   # noqa: E731
                    counted = today()
                    call(code, "/api/settings", {"onboarded": False})
                    pag.goto(PANEL + "/#/welcome")
                    pag.reload()
                    pag.wait_for_selector("#welcome[open] #welcomeTry:not([disabled])", timeout=30000)
                    untranslated = set(RX_KEY.findall(pag.inner_text("#welcome"))) & KEYS
                    pag.click("#welcomeTry")
                    pag.wait_for_selector("#welcomeResult:not([hidden])", timeout=30000)
                    tried = pag.inner_text("#welcomeResult")
                    pag.click("#welcomeNext")
                    pag.wait_for_selector('#welcome[data-step="2"]')
                    pag.check('#welcome input[data-where="app"]')
                    untranslated |= set(RX_KEY.findall(pag.inner_text("#welcome"))) & KEYS
                    pag.click("#welcomeNext")
                    pag.wait_for_selector('#welcome[data-step="3"] #welcomeInstall:not([hidden])')
                    browser = pag.get_attribute("#welcomeExt", "data-status")
                    untranslated |= set(RX_KEY.findall(pag.inner_text("#welcome"))) & KEYS
                    pag.click("#welcomeNext")
                    pag.wait_for_selector('#welcome[data-step="4"] #welcomeMore')
                    untranslated |= set(RX_KEY.findall(pag.inner_text("#welcome"))) & KEYS
                    unnamed = pag.evaluate(WITHOUT_NAME)
                    pag.click("#welcomeNext")
                    wait_until(lambda: call(code, "/api/settings")["onboarded"] is True)
                    closed = not pag.evaluate("document.getElementById('welcome').open") and pag.evaluate("location.hash") == "#/start"
                    # saltata con Esc vale come vista; e dalla Guida la si puo' rivedere
                    call(code, "/api/settings", {"onboarded": False})
                    pag.goto(PANEL + "/#/guide")
                    pag.click("#welcomeAgain")
                    pag.wait_for_selector("#welcome[open]")
                    pag.keyboard.press("Escape")
                    wait_until(lambda: call(code, "/api/settings")["onboarded"] is True)
                    contact = pag.get_attribute("#contact", "href") or ""
                    mark(f"{language}: configurazione guidata, prova con dati inventati (fuori dai conteggi), scelte, estensione, fine; saltarla vale come vista",
                         "[PERSONA_" in tried and "Ferraresi" not in tried and today() == counted and browser == "absent" and closed
                         and not untranslated and not unnamed and not pag.evaluate("document.getElementById('welcome').open")
                         and contact.startswith("https://francescogruner.it/") and bool(pag.inner_text("#contact").strip()),
                         f"sostituiti: {'[PERSONA_' in tried} · conteggi {counted}->{today()} · estensione {browser} · chiusa {closed} · senza traduzione {sorted(untranslated)[:3]} · senza nome {unnamed[:2]}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: configurazione guidata", False, str(ex)[:200])
                    call(code, "/api/settings", {"onboarded": True})
                    pag.goto(PANEL + "/#/start")
                    pag.reload()
                    pag.wait_for_selector("#menu a")
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
                        fixed = wait_until(lambda: call(code, "/api/settings")["managed"] == {"keys": ["updates"], "policies": ["deepseek"]}, timeout=15)
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
                        back = wait_until(lambda: call(code, "/api/settings")["managed"] == {"keys": [], "policies": []}, timeout=15)
                        mark(f"{language}: impostazioni imposte dall'amministratore: ferme nella pagina, rifiutate dal programma, libere quando il vincolo sparisce",
                             fixed and shown and refused == [True, True] and free and back, f"imposte {fixed} · pagina {shown} · rifiuti {refused} · tolte {back}")
                except Exception as ex:   # noqa: BLE001
                    mark(f"{language}: impostazioni imposte dall'amministratore", False, str(ex)[:160])
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
                pag.fill("#archSearch", "ferraresi")
                wait(pag, "() => [...document.querySelectorAll('#tabVault .placeholder')].some(e => e.textContent.startsWith('[PERSONA_'))", timeout=15)
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
