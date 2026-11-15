# -*- coding: utf-8 -*-
"""Prova l'estensione in un browser vero (il Chromium di Playwright), contro il servizio finto.

Prima:  build_extension.py --test          (aggiunge localhost ai siti dell'estensione)
        panel.py --test --no-tray --no-browser
        mock_service.py
Dopo:   build_extension.py                  (toglie localhost)

Controlla, formato per formato, che al "servizio" arrivino solo segnaposto e che la pagina riceva i
valori veri; poi il collegamento dal pannello, il blocco quando la protezione non risponde, la
sospensione, i file, il ripristino nel testo della pagina e il blocco di un servizio.
"""
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# il browser di prova sta nella cartella del progetto (python -m playwright install chromium, con questa variabile)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(HERE / ".playwright"))
from playwright.sync_api import sync_playwright   # noqa: E402

import paths   # noqa: E402

FAKE, PANEL = "http://localhost:9911", f"http://127.0.0.1:{paths.PANEL_PORT}"
CALL_SERVICES = "(d) => fetch('/api/services', {method: 'POST', headers: {'X-Panel': document.querySelector('meta[name=omissis-code]').content, 'Content-Type': 'application/json'}, body: JSON.stringify(d)}).then(r => r.json())"
# --lang=en avvia il browser in inglese: l'estensione segue la lingua del browser
LANGUAGE = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--lang=")), "it")
BROWSER = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--browser=")), None)
OTHER_COPY = paths.PANEL_PORT != 8766   # seconda copia di prova: il pannello non e' sulla porta che l'estensione riconosce
TEXT = ("Scrivi una mail a Giulia Ferraresi (giulia.ferraresi@nevatek.example, cell. 347 5551234) della Nevatek S.r.l. "
         "per confermare l'appuntamento con Aldo Bruschi.")
SENSITIVE = ["Giulia Ferraresi", "giulia.ferraresi@nevatek.example", "347 5551234", "Aldo Bruschi"]
outcomes = []


def seen():
    with urllib.request.urlopen("http://127.0.0.1:9911/seen", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def mark(name, ok, note=""):
    outcomes.append(ok)
    print(f"{'OK    ' if ok else 'ERRORE'} {name}" + (f"   {note}" if note else ""), flush=True)


def wait_for(page, selector, text, seconds=10):
    """Le pagine dell'estensione non ammettono codice valutato al volo: si legge il testo a intervalli."""
    for _ in range(seconds * 5):
        if (page.get_attribute(selector, "data-status") or page.inner_text(selector)) == text:   # il codice dello stato, uguale in ogni lingua
            return
        page.wait_for_timeout(200)
    raise TimeoutError(f"{selector} non è diventato «{text}»: è «{page.inner_text(selector)}»")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    lines_before = len((paths.DATA / "activity.jsonl").read_text(encoding="utf-8").splitlines()) if (paths.DATA / "activity.jsonl").exists() else 0
    with sync_playwright() as pw, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        est = str(HERE / "extension")
        # il browser: quello di prova, oppure uno vero installato (--browser=<percorso>), sempre con un profilo vuoto e a parte.
        # Chrome di marca ignora --load-extension se non gli si toglie il blocco apposito.
        which = {"executable_path": BROWSER} if BROWSER else {"channel": "chromium"}
        ctx = pw.chromium.launch_persistent_context(profile, **which, headless="--headed" not in sys.argv,
                                                    args=[f"--disable-extensions-except={est}", f"--load-extension={est}", f"--lang={LANGUAGE}",
                                                          "--disable-features=DisableLoadExtensionCommandLineSwitch", "--no-first-run", "--no-default-browser-check"])
        try:
            sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=20000)
        except Exception:   # noqa: BLE001
            ctx.close()
            sys.exit("Il browser non ha caricato l'estensione. Chrome di marca non accetta più estensioni dalla riga di comando: lì va caricata "
                     "a mano da chrome://extensions. Edge, Brave e il Chromium di prova la caricano.")
        ident = sw.url.split("/")[2]

        # --- prima del collegamento: su un servizio protetto il messaggio non deve partire
        page = ctx.new_page()
        page.goto(FAKE + "/page")
        before = json.dumps(seen())
        try:
            page.evaluate("t => test('claude', t)", TEXT)
            mark("non collegata: richiesta bloccata", False, "la richiesta è partita")
        except Exception:   # noqa: BLE001
            mark("non collegata: richiesta bloccata", json.dumps(seen()) == before)

        # --- collegamento con un clic dal pannello
        pan = ctx.new_page()
        pan.goto(PANEL + "/")
        if OTHER_COPY:
            code = (paths.DATA / "token_extension.txt").read_text(encoding="utf-8").strip()
            sw.evaluate("([t, p]) => chrome.storage.local.set({token: t, port: p}).then(() => refresh(true))", [code, paths.ENGINE_PORT])
            mark("collegamento (consegnato direttamente: seconda copia di prova)", sw.evaluate("chrome.storage.local.get('health').then(d => !!(d.health && d.health.ok))"))
        else:
            pan.wait_for_selector("#menu a", timeout=10000)
            pan.evaluate("document.getElementById('advanced').checked || document.getElementById('advanced').click()")
            pan.goto(PANEL + "/#/connections/browser")
            # niente wait_for_function sul pannello: valuta il testo con eval, che quella pagina vieta apposta
            for states in (("to_connect", "connected", "no_response"), ("connected",)):
                for _ in range(100):
                    if pan.evaluate("() => (document.getElementById('estStatus') || {dataset: {}}).dataset.status") in states:
                        break
                    pan.wait_for_timeout(150)
                else:
                    raise RuntimeError(f"il pannello non arriva a uno di questi stati: {states}")
                if len(states) > 1:
                    pan.click("#estConnect")
            mark("collegamento dal pannello", True, pan.inner_text("#estStatus"))

        # --- formati: richiesta mascherata, risposta ripristinata
        page.reload()
        for fmt in ("claude", "openai", "chatgpt", "cumulative", "lines", "prefix", "whole", "request"):
            try:
                response = page.evaluate("([f, t]) => test(f, t)", [fmt, TEXT])
            except Exception as ex:   # noqa: BLE001
                mark(fmt, False, str(ex)[:150])
                continue
            arrived = json.dumps(seen()["body"], ensure_ascii=False)
            outside = [s for s in SENSITIVE if s in arrived]
            returned = [s for s in SENSITIVE if s in response]
            mark(fmt, not outside and "[PERSONA_" in arrived and len(returned) == len(SENSITIVE) and "[PERSONA_" not in response,
                  f"al servizio in chiaro: {len(outside)} · tornati alla pagina: {len(returned)}/{len(SENSITIVE)}")
        page.evaluate("t => test('claude', t)", TEXT)
        response = page.evaluate("test('history')")
        mark("cronologia (risposta JSON a una GET)", all(s in response for s in SENSITIVE), "")

        # --- il caso difficile: pagine che mandano un messaggio nell'istante in cui si aprono
        light = masked = idle = 0
        for lap in range(1, 16):
            at_once = ctx.new_page()
            at_once.goto(f"{FAKE}/page?at_once={lap}")
            arrived = None
            for _ in range(40):
                body = seen()["body"]
                if isinstance(body, dict) and body.get("lap") == lap:
                    arrived = json.dumps(body, ensure_ascii=False)
                    break
                at_once.wait_for_timeout(100)
            if arrived is None:
                idle += 1
            elif any(s in arrived for s in SENSITIVE):
                light += 1
            else:
                masked += 1
            at_once.close()
        mark("messaggio inviato nell'istante in cui la pagina si apre (15 pagine)", light == 0 and masked == 15,
              f"in chiaro {light} · mascherati {masked} · non partiti {idle}")

        # --- la casella di scrittura: prima difesa, non dipende dal formato delle richieste. La "chat" della pagina di
        # prova non usa la rete: cio' che legge dalla casella finisce in __inviati.
        page.evaluate("window.__sent.length = 0; document.getElementById('chat').textContent = ''")
        page.click("#write")
        page.keyboard.insert_text(TEXT)
        page.keyboard.press("Enter")
        page.wait_for_function("window.__sent.length > 0", timeout=15000)
        page.wait_for_timeout(800)
        read_back, screen = page.evaluate("window.__sent[0]"), page.inner_text("#chat")
        mark("casella di scrittura: la pagina legge solo segnaposto, a schermo i valori veri", not any(s in read_back for s in SENSITIVE) and "[PERSONA_" in read_back
              and all(s in screen for s in SENSITIVE) and "[PERSONA_" not in screen, f"letti in chiaro: {sum(s in read_back for s in SENSITIVE)} · a schermo {sum(s in screen for s in SENSITIVE)}/4")

        # --- allegati: il file scelto, trascinato o incollato arriva alla pagina gia' anonimizzato
        folder = Path(tempfile.mkdtemp(prefix="omissis_attachments_"))
        (folder / "lettera.txt").write_text(TEXT, encoding="utf-8")
        import docx
        d = docx.Document()
        d.add_paragraph(TEXT)
        d.save(str(folder / "verbale.docx"))
        (folder / "archivio.bin").write_bytes(b"\x00\x01" + TEXT.encode("utf-8"))

        def received(how_many, seconds=40):
            for _ in range(seconds * 5):
                if page.evaluate("window.__file.length") >= how_many:
                    return page.evaluate("window.__file")
                page.wait_for_timeout(200)
            return page.evaluate("window.__file")

        page.evaluate("window.__file.length = 0; window.__first.length = 0")
        page.set_input_files("#allega", str(folder / "lettera.txt"))
        r = received(1)
        with urllib.request.urlopen("http://127.0.0.1:9911/seen_file", timeout=10) as response:
            loaded = json.loads(response.read().decode("utf-8"))["last"]
        mark("allegato di testo: la pagina riceve la copia anonimizzata, e carica quella",
              len(r) == 1 and r[0]["name"] == "lettera.anon.txt" and "[PERSONA_" in r[0]["text"] and not any(s in r[0]["text"] for s in SENSITIVE)
              and r[0]["loaded"] and "[PERSONA_" in loaded and not any(s in loaded for s in SENSITIVE)
              and "lettera.txt" not in page.evaluate("window.__first"), f"{r[0]['name'] if r else 'nothing'} · al primo evento la pagina ha visto: {page.evaluate('window.__first')}")

        page.evaluate("window.__file.length = 0")
        page.set_input_files("#allega", str(folder / "verbale.docx"))
        r = received(1)
        text_docx = ""
        if r and r[0]["data"]:
            import base64
            import io
            text_docx = "\n".join(p.text for p in docx.Document(io.BytesIO(base64.b64decode(r[0]["data"]))).paragraphs)
        mark("allegato Word: resta un Word, con i dati sostituiti", len(r) == 1 and r[0]["name"] == "verbale.anon.docx" and "[PERSONA_" in text_docx
              and not any(s in text_docx for s in SENSITIVE), r[0]["name"] if r else "nothing")

        page.evaluate("window.__file.length = 0")
        page.set_input_files("#allega", str(folder / "archivio.bin"))
        r = received(1)
        mark("formato non coperto: passa com'è (finché non si sceglie di bloccare i file)", len(r) == 1 and r[0]["name"] == "archivio.bin")

        for how, event, where in (("dragging", "drop", "#zone"), ("paste", "paste", "#write")):
            page.evaluate("window.__file.length = 0")
            page.evaluate("""([event, where, text]) => {
                const dt = new DataTransfer();
                dt.items.add(new File([text], 'appunti.txt', {type: 'text/plain'}));
                const e = event === 'drop' ? new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt})
                                            : new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt});
                document.querySelector(where).dispatchEvent(e);
            }""", [event, where, TEXT])
            r = received(1)
            mark(f"allegato per {how}: arriva la copia anonimizzata", len(r) == 1 and r[0]["how"] == how and r[0]["name"] == "appunti.anon.txt"
                  and "[PERSONA_" in r[0]["text"] and not any(s in r[0]["text"] for s in SENSITIVE), r[0]["name"] if r else "nothing")

        # --- allegati spenti nelle impostazioni del programma: l'estensione lo viene a sapere e lascia stare i file
        call_settings = CALL_SERVICES.replace("/api/services", "/api/settings")
        pan.evaluate(call_settings, {"attachments": False})
        sw.evaluate("refresh(true)")
        page.wait_for_timeout(800)
        page.evaluate("window.__file.length = 0")
        page.set_input_files("#allega", str(folder / "lettera.txt"))
        r = received(1, seconds=15)
        known = sw.evaluate("chrome.storage.local.get('status').then(d => d.status.attachments)")
        mark("allegati spenti nelle impostazioni: il file passa com'è", known is False and len(r) == 1 and r[0]["name"] == "lettera.txt",
              f"l'estensione sa che sono spenti: {known is False} · alla pagina: {r[0]['name'] if r else 'nothing'}")
        pan.evaluate(call_settings, {"attachments": True})
        sw.evaluate("refresh(true)")
        page.wait_for_timeout(800)

        # --- XMLHttpRequest (come Gemini): richiesta mascherata, risposta sistemata nel testo della pagina
        raw = page.evaluate("t => test('gemini', t)", TEXT)
        arrived = json.dumps(seen()["body"], ensure_ascii=False)
        page.wait_for_timeout(600)
        shown = page.inner_text("#outcome")
        mark("XMLHttpRequest: richiesta mascherata", not any(s in arrived for s in SENSITIVE) and "[PERSONA_" in arrived
              and seen()["body"].get("at") == "gettone")
        mark("XMLHttpRequest: valori veri nel testo della pagina", all(s in shown for s in SENSITIVE) and "[PERSONA_" not in shown,
              "la risposta letta dal sito resta con i segnaposto" if "[PERSONA_" in raw else "")

        # --- testo gia' mascherato incollato nella pagina; le caselle di scrittura non si toccano
        placeholder = json.dumps(seen()["body"], ensure_ascii=False)
        placeholder = placeholder[placeholder.index("[PERSONA_"):].split("]")[0] + "]"
        page.evaluate("s => { document.getElementById('incollato').textContent = 'Gentile ' + s + ', confermo.'; "
                        "document.getElementById('box').value = s; }", placeholder)
        page.wait_for_timeout(600)
        mark("segnaposto nel testo della pagina", "[PERSONA_" not in page.inner_text("#incollato"), page.inner_text("#incollato")[:12] + "…")
        mark("casella di scrittura lasciata com'è", page.input_value("#box") == placeholder)
        mark("avviso mostrato nella pagina", page.locator("[data-omissis]").count() == 1)

        # --- file
        n = seen()["file"]
        status = page.evaluate("test('file')")
        mark("file: passa e viene segnalato", status == 200 and seen()["file"] == n + 1)

        # --- sospensione dalla finestrella
        fin = ctx.new_page()
        fin.goto(f"chrome-extension://{ident}/popup.html")
        wait_for(fin, "#title", "active")
        timeout = {"it": ("attiva", "Sito aperto"), "en": ("on", "Open site")}.get(LANGUAGE)
        if timeout:
            mark(f"finestrella nella lingua del browser ({LANGUAGE})", fin.inner_text("#textTitle") == timeout[0] and timeout[1] in fin.inner_text("#site")
                  and fin.evaluate("document.documentElement.lang").startswith(LANGUAGE), fin.inner_text("#textTitle"))
        fin.check("#suspended")
        wait_for(fin, "#title", "suspended")
        page.wait_for_timeout(300)
        page.evaluate("t => test('whole', t)", TEXT)
        mark("sospesa: il messaggio parte senza sostituzioni", SENSITIVE[0] in json.dumps(seen()["body"], ensure_ascii=False))

        # --- la regola del servizio e' imposta da chi amministra il PC: li' la sospensione non vale
        imposed = Path(os.environ.get("OMISSIS_MANAGED_FILE") or paths.DATA / "imposte.json")
        known = "chrome.storage.local.get('status').then(d => !!(d.status.services.find(s => s.id === 'test') || {}).locked)"
        try:
            imposed.write_text(json.dumps({"policies": {"test": "protect"}}), encoding="utf-8")
            page.wait_for_timeout(2600)   # nelle prove il programma rilegge le impostazioni imposte ogni due secondi
            sw.evaluate("refresh(true)")
            if not sw.evaluate(known):
                print("SALTATO regola imposta: questo programma non legge le impostazioni imposte da un file (manca OMISSIS_MANAGED_FILE)")
            else:
                page.wait_for_timeout(500)
                page.bring_to_front()   # la finestrella, qui aperta come scheda, guarda il sito della scheda in primo piano
                fin.reload()
                wait_for(fin, "#title", "active")
                note = fin.is_visible("#managed")
                page.evaluate("t => test('whole', t)", TEXT)
                held = json.dumps(seen()["body"], ensure_ascii=False)
                imposed.unlink()
                page.wait_for_timeout(2600)
                sw.evaluate("refresh(true)")
                page.wait_for_timeout(500)
                fin.reload()
                wait_for(fin, "#title", "suspended")
                page.evaluate("t => test('whole', t)", TEXT)
                free = SENSITIVE[0] in json.dumps(seen()["body"], ensure_ascii=False)
                mark("regola imposta dall'amministratore: la sospensione lì non vale, e torna a valere quando il vincolo sparisce",
                      note and "[PERSONA_" in held and not any(s in held for s in SENSITIVE) and free and not fin.is_visible("#managed"),
                      f"avviso nella finestrella: {note} · in chiaro con il vincolo: {sum(s in held for s in SENSITIVE)} · senza vincolo passa: {free}")
        finally:
            imposed.unlink(missing_ok=True)
            fin.bring_to_front()
        fin.uncheck("#suspended")
        wait_for(fin, "#title", "active")
        page.wait_for_timeout(300)

        # --- codice sbagliato (come se il programma non rispondesse): la richiesta non parte
        good = sw.evaluate("chrome.storage.local.get('token').then(d => d.token)")
        sw.evaluate("chrome.storage.local.set({token: 'sbagliato'})")
        before = json.dumps(seen())
        try:
            page.evaluate("t => test('claude', t)", TEXT)
            mark("protezione che non risponde: richiesta bloccata", False, "la richiesta è partita")
        except Exception:   # noqa: BLE001
            mark("protezione che non risponde: richiesta bloccata", json.dumps(seen()) == before)
        try:
            page.evaluate("t => test('gemini', t)", TEXT)
            mark("protezione che non risponde: XMLHttpRequest bloccata", False, "la richiesta è partita")
        except Exception:   # noqa: BLE001
            mark("protezione che non risponde: XMLHttpRequest bloccata", json.dumps(seen()) == before)
        sw.evaluate("t => chrome.storage.local.set({token: t})", good)

        # --- blocco di un servizio (politica scelta nel pannello): la pagina non viene nemmeno contattata
        pan.evaluate(CALL_SERVICES, {"id": "pi", "policy": "block"})
        fin.reload()   # aprire la finestrella fa rileggere le politiche
        wait_for(fin, "#title", "active")
        rules = sw.evaluate("chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)")
        block = ctx.new_page()
        try:
            block.goto("https://pi.ai/", timeout=15000)
        except Exception:   # noqa: BLE001  (la navigazione viene deviata)
            pass
        block.wait_for_timeout(500)
        mark("servizio bloccato", block.url.startswith(f"chrome-extension://{ident}/blocked.html") and "Pi" in block.inner_text("h1"),
              f"{rules} regole · {block.url[:60]}")
        pan.evaluate(CALL_SERVICES, {"id": "pi", "policy": "record"})

        # --- un servizio del radar: l'estensione non ha accesso al suo sito (non lo chiede), ma lo sa bloccare lo stesso
        pan.evaluate(CALL_SERVICES, {"id": "replika", "policy": "block"})
        fin.reload()
        wait_for(fin, "#title", "active")
        fin.wait_for_timeout(500)
        radar = sw.evaluate("chrome.declarativeNetRequest.getDynamicRules()")
        accesses = sw.evaluate("chrome.runtime.getManifest().host_permissions")
        stopped = ctx.new_page()
        try:
            stopped.goto("https://replika.com/", timeout=15000)
            partita = True
        except Exception as ex:   # noqa: BLE001  (il browser rifiuta la richiesta: e' il blocco)
            partita = "ERR_BLOCKED_BY_CLIENT" not in str(ex)
        stopped.close()
        mark("servizio del radar bloccato, senza accesso al suo sito", len(radar) == 1 and radar[0]["action"]["type"] == "block"
              and "main_frame" in radar[0]["condition"]["resourceTypes"] and "replika.com" in radar[0]["condition"]["requestDomains"]
              and not any("replika" in h for h in accesses) and not partita, f"{len(radar)} regole · richiesta partita: {partita}")
        pan.evaluate(CALL_SERVICES, {"id": "replika", "policy": "record"})
        fin.reload()
        wait_for(fin, "#title", "active")
        mark("blocco tolto", sw.evaluate("chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)") == 0)
        # --- la pagina di benvenuto, a estensione collegata, lo dice e non chiede altro
        hello = ctx.new_page()
        hello.goto(f"chrome-extension://{ident}/welcome.html")
        try:
            hello.wait_for_selector('#state[data-status="connected"]', timeout=15000)
            mark("pagina di benvenuto: a estensione collegata lo dice e non chiede altro", hello.is_visible("#done") and not hello.is_visible("#steps"))
        except Exception as ex:   # noqa: BLE001
            mark("pagina di benvenuto: a estensione collegata lo dice e non chiede altro", False, str(ex)[:160])
        if "--screenshots" in sys.argv:
            hello.set_viewport_size({"width": 900, "height": 640})
            hello.screenshot(path=str(HERE / "screenshots" / f"extension-welcome-{LANGUAGE}.png"))
        hello.close()
        if "--screenshots" in sys.argv:
            fin.set_viewport_size({"width": 336, "height": 420})
            fin.screenshot(path=str(HERE / "screenshots" / f"extension-popup-{LANGUAGE}.png"))
            block.screenshot(path=str(HERE / "screenshots" / f"extension-blocked-{LANGUAGE}.png"))
            pan.set_viewport_size({"width": 1180, "height": 820})
            pan.screenshot(path=str(HERE / "screenshots" / "browser.png"))
        ctx.close()

        # --- i file cambiano sul disco (il programma si e' aggiornato): l'estensione gia' caricata se ne accorge da sola
        import shutil
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as second, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile2:
            copy = Path(shutil.copytree(est, Path(second) / "extension"))
            ctx = pw.chromium.launch_persistent_context(profile2, **which, headless="--headed" not in sys.argv,
                                                        args=[f"--disable-extensions-except={copy}", f"--load-extension={copy}", f"--lang={LANGUAGE}",
                                                              "--disable-features=DisableLoadExtensionCommandLineSwitch", "--no-first-run", "--no-default-browser-check"])
            sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=20000)
            before = sw.evaluate("BUILD")
            # chi carica l'estensione da una cartella ha per forza la modalita' sviluppatore accesa; il browser di prova no, e
            # senza quella una ricarica la lascerebbe spenta: la si accende, come nel caso vero
            dev = ctx.new_page()
            dev.goto("chrome://extensions")
            dev.evaluate("() => new Promise(r => chrome.developerPrivate.updateProfileConfiguration({inDeveloperMode: true}, r))")
            # sul disco compare una copia di prova: quella caricata non deve passarci da sola
            (copy / "build.json").write_text(json.dumps({"build": "0" * 16, "test": True}), encoding="utf-8")
            stays = sw.evaluate("outdated()") is False
            fresh, after = "f" * 16, ""
            (copy / "defaults.js").write_text((copy / "defaults.js").read_text(encoding="utf-8").replace(before, fresh), encoding="utf-8")
            (copy / "build.json").write_text(json.dumps({"build": fresh, "test": False}), encoding="utf-8")
            try:
                with ctx.expect_event("serviceworker", timeout=30000) as arrived:
                    try:
                        sw.evaluate("refresh(true)")
                    except Exception:   # noqa: BLE001  (il servizio in background si chiude mentre risponde: e' la ricarica)
                        pass
                after = arrived.value.evaluate("BUILD")
                quiet = arrived.value.evaluate("outdated()") is False   # ricaricata, non deve ricominciare
            except Exception as ex:   # noqa: BLE001
                quiet = False
                after = f"nessuna ricarica ({type(ex).__name__})"
            mark("file cambiati sul disco: l'estensione si ricarica da sola e riparte con quelli nuovi",
                  len(before) == 16 and stays and after == fresh and quiet, f"{before} -> {after} · alla copia di prova non passa: {stays}")

            # --- appena installata (e non di prova, non ancora collegata) apre la pagina di benvenuto, una volta sola
            try:
                now = ctx.service_workers[-1]
                already = [p.url for p in ctx.pages if p.url.endswith("/welcome.html")]   # una ricarica non deve averla aperta
                not_on_update = now.evaluate("greet({reason: 'update'})") is False
                with ctx.expect_page(timeout=15000) as opening:
                    opened_now = now.evaluate("greet({reason: 'install'})")
                hello = opening.value
                hello.wait_for_selector('#state[data-status="to_connect"]', timeout=10000)
                link = hello.get_attribute("#connect", "href")
                words = hello.inner_text("main")
                once = now.evaluate("greet({reason: 'install'})") is False
                mark("appena installata: si apre la pagina di benvenuto, una volta sola, con il collegamento al pannello",
                      not already and not_on_update and opened_now and once and link == "http://127.0.0.1:8766/#/connect"
                      and hello.is_visible("#steps") and "welcome_" not in words and len(words) > 200, f"dopo una ricarica: {len(already)} · collegamento: {link}")
                hello.close()
            except Exception as ex:   # noqa: BLE001
                mark("appena installata: si apre la pagina di benvenuto", False, str(ex)[:200])

            # --- la finestrella (letta dal disco ogni volta) davanti a un servizio in background rimasto a una versione che non
            # la capisce: ricarica l'estensione da sola, una volta; se nemmeno cosi' si capiscono, lo dice
            told, reloads = "", 0
            try:
                js = (copy / "background.js").read_text(encoding="utf-8")
                (copy / "background.js").write_text(js.replace("case 'win': {", "case 'win_di_prima': {"), encoding="utf-8")
                ident2 = sw.url.split("/")[2]
                for attempt in (1, 2):
                    with ctx.expect_event("serviceworker", timeout=30000):
                        if attempt == 1:   # il browser carica il servizio «vecchio»
                            try:
                                ctx.service_workers[-1].evaluate("chrome.runtime.reload()")
                            except Exception:   # noqa: BLE001
                                pass
                        else:              # la finestrella non riceve risposta sensata: deve ricaricare lei
                            win = ctx.new_page()
                            try:
                                win.goto(f"chrome-extension://{ident2}/popup.html")
                            except Exception:   # noqa: BLE001  (la pagina si chiude con la ricarica)
                                pass
                    reloads += 1
                win = ctx.new_page()
                win.goto(f"chrome-extension://{ident2}/popup.html")
                wait_for(win, "#title", "not_active")
                told = win.inner_text("#fault")
            except Exception as ex:   # noqa: BLE001
                told = told or f"({type(ex).__name__}: {str(ex)[:80]})"
            mark("finestrella e servizio in background di versioni diverse: una ricarica da sola, poi l'avviso",
                  reloads == 2 and len(told) > 30 and not told.startswith("("), f"ricariche: {reloads} · «{told[:70]}»")
            ctx.close()

    # --- registro: solo conteggi, con l'indicazione "via estensione"
    new_ones = [json.loads(r) for r in (paths.DATA / "activity.jsonl").read_text(encoding="utf-8").splitlines()[lines_before:]]
    my = [v for v in new_ones if v.get("via") == "extension"]
    text = json.dumps(my, ensure_ascii=False)
    mark("registro: righe dell'estensione senza testi", len([v for v in my if v.get("event") == "masked"]) >= 9
          and not any(s in text for s in SENSITIVE), f"{len(my)} righe: " + ", ".join(sorted({v.get('event', '') for v in my})))
    # --- il registro delle versioni: il browser di questa prova deve risultare, con il suo nome e la sua versione
    import activity
    sightings = [g for g in activity.compatibility() if g["via"] == "extension" and g["client"]]
    mark("registro delle versioni: browser e versione annotati accanto alle sostituzioni riuscite", any(g["ok"] >= 1 and g["status"] == "works"
          and any(c.isdigit() for c in g["client"]) for g in sightings), "; ".join(sorted({g["client"] for g in sightings}))[:120] or "nessun programma annotato")
    print("\nTUTTO OK" if all(outcomes) else f"\n{outcomes.count(False)} ERRORI")
    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
