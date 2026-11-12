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

QUI = Path(__file__).resolve().parent
# il browser di prova sta nella cartella del progetto (python -m playwright install chromium, con questa variabile)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(QUI / ".playwright"))
from playwright.sync_api import sync_playwright   # noqa: E402

import paths   # noqa: E402

FINTO, PANNELLO = "http://localhost:9911", f"http://127.0.0.1:{paths.PORTA_PANNELLO}"
CHIAMA_SERVIZI = "(d) => fetch('/api/servizi', {method: 'POST', headers: {'X-Pannello': document.querySelector('meta[name=omissis-codice]').content, 'Content-Type': 'application/json'}, body: JSON.stringify(d)}).then(r => r.json())"
# --lang=en avvia il browser in inglese: l'estensione segue la lingua del browser
LINGUA = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--lang=")), "it")
BROWSER = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--browser=")), None)
ALTRA_COPIA = paths.PORTA_PANNELLO != 8766   # seconda copia di prova: il pannello non e' sulla porta che l'estensione riconosce
TESTO = ("Scrivi una mail a Giulia Ferraresi (giulia.ferraresi@nevatek.example, cell. 347 5551234) della Nevatek S.r.l. "
         "per confermare l'appuntamento con Aldo Bruschi.")
SENSIBILI = ["Giulia Ferraresi", "giulia.ferraresi@nevatek.example", "347 5551234", "Aldo Bruschi"]
esiti = []


def visto():
    with urllib.request.urlopen("http://127.0.0.1:9911/visto", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def segna(nome, ok, nota=""):
    esiti.append(ok)
    print(f"{'OK    ' if ok else 'ERRORE'} {nome}" + (f"   {nota}" if nota else ""), flush=True)


def attendi(pagina, selettore, testo, secondi=10):
    """Le pagine dell'estensione non ammettono codice valutato al volo: si legge il testo a intervalli."""
    for _ in range(secondi * 5):
        if (pagina.get_attribute(selettore, "data-stato") or pagina.inner_text(selettore)) == testo:   # il codice dello stato, uguale in ogni lingua
            return
        pagina.wait_for_timeout(200)
    raise TimeoutError(f"{selettore} non è diventato «{testo}»: è «{pagina.inner_text(selettore)}»")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    righe_prima = len((paths.DATI / "activity.jsonl").read_text(encoding="utf-8").splitlines()) if (paths.DATI / "activity.jsonl").exists() else 0
    with sync_playwright() as pw, tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profilo:
        est = str(QUI / "extension")
        # il browser: quello di prova, oppure uno vero installato (--browser=<percorso>), sempre con un profilo vuoto e a parte.
        # Chrome di marca ignora --load-extension se non gli si toglie il blocco apposito.
        quale = {"executable_path": BROWSER} if BROWSER else {"channel": "chromium"}
        ctx = pw.chromium.launch_persistent_context(profilo, **quale, headless="--headed" not in sys.argv,
                                                    args=[f"--disable-extensions-except={est}", f"--load-extension={est}", f"--lang={LINGUA}",
                                                          "--disable-features=DisableLoadExtensionCommandLineSwitch", "--no-first-run", "--no-default-browser-check"])
        try:
            sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=20000)
        except Exception:   # noqa: BLE001
            ctx.close()
            sys.exit("Il browser non ha caricato l'estensione. Chrome di marca non accetta più estensioni dalla riga di comando: lì va caricata "
                     "a mano da chrome://extensions. Edge, Brave e il Chromium di prova la caricano.")
        ident = sw.url.split("/")[2]

        # --- prima del collegamento: su un servizio protetto il messaggio non deve partire
        pagina = ctx.new_page()
        pagina.goto(FINTO + "/pagina")
        prima = json.dumps(visto())
        try:
            pagina.evaluate("t => prova('claude', t)", TESTO)
            segna("non collegata: richiesta bloccata", False, "la richiesta è partita")
        except Exception:   # noqa: BLE001
            segna("non collegata: richiesta bloccata", json.dumps(visto()) == prima)

        # --- collegamento con un clic dal pannello
        pan = ctx.new_page()
        pan.goto(PANNELLO + "/")
        if ALTRA_COPIA:
            codice = (paths.DATI / "token_extension.txt").read_text(encoding="utf-8").strip()
            sw.evaluate("([t, p]) => chrome.storage.local.set({token: t, porta: p}).then(() => aggiorna(true))", [codice, paths.PORTA_MOTORE])
            segna("collegamento (consegnato direttamente: seconda copia di prova)", sw.evaluate("chrome.storage.local.get('salute').then(d => !!(d.salute && d.salute.ok))"))
        else:
            pan.wait_for_selector("#menu a", timeout=10000)
            pan.evaluate("document.getElementById('avanzata').checked || document.getElementById('avanzata').click()")
            pan.goto(PANNELLO + "/#/collegamenti/browser")
            # niente wait_for_function sul pannello: valuta il testo con eval, che quella pagina vieta apposta
            for stati in (("da_collegare", "collegata", "senza_risposta"), ("collegata",)):
                for _ in range(100):
                    if pan.evaluate("() => (document.getElementById('estStato') || {dataset: {}}).dataset.stato") in stati:
                        break
                    pan.wait_for_timeout(150)
                else:
                    raise RuntimeError(f"il pannello non arriva a uno di questi stati: {stati}")
                if len(stati) > 1:
                    pan.click("#estCollega")
            segna("collegamento dal pannello", True, pan.inner_text("#estStato"))

        # --- formati: richiesta mascherata, risposta ripristinata
        pagina.reload()
        for formato in ("claude", "openai", "chatgpt", "cumulativo", "righe", "prefisso", "intera", "richiesta"):
            try:
                risposta = pagina.evaluate("([f, t]) => prova(f, t)", [formato, TESTO])
            except Exception as ex:   # noqa: BLE001
                segna(formato, False, str(ex)[:150])
                continue
            arrivato = json.dumps(visto()["corpo"], ensure_ascii=False)
            fuori = [s for s in SENSIBILI if s in arrivato]
            tornati = [s for s in SENSIBILI if s in risposta]
            segna(formato, not fuori and "[PERSONA_" in arrivato and len(tornati) == len(SENSIBILI) and "[PERSONA_" not in risposta,
                  f"al servizio in chiaro: {len(fuori)} · tornati alla pagina: {len(tornati)}/{len(SENSIBILI)}")
        pagina.evaluate("t => prova('claude', t)", TESTO)
        risposta = pagina.evaluate("prova('cronologia')")
        segna("cronologia (risposta JSON a una GET)", all(s in risposta for s in SENSIBILI), "")

        # --- il caso difficile: pagine che mandano un messaggio nell'istante in cui si aprono
        chiaro = mascherati = fermi = 0
        for giro in range(1, 16):
            subito = ctx.new_page()
            subito.goto(f"{FINTO}/pagina?subito={giro}")
            arrivato = None
            for _ in range(40):
                corpo = visto()["corpo"]
                if isinstance(corpo, dict) and corpo.get("giro") == giro:
                    arrivato = json.dumps(corpo, ensure_ascii=False)
                    break
                subito.wait_for_timeout(100)
            if arrivato is None:
                fermi += 1
            elif any(s in arrivato for s in SENSIBILI):
                chiaro += 1
            else:
                mascherati += 1
            subito.close()
        segna("messaggio inviato nell'istante in cui la pagina si apre (15 pagine)", chiaro == 0 and mascherati == 15,
              f"in chiaro {chiaro} · mascherati {mascherati} · non partiti {fermi}")

        # --- la casella di scrittura: prima difesa, non dipende dal formato delle richieste. La "chat" della pagina di
        # prova non usa la rete: cio' che legge dalla casella finisce in __inviati.
        pagina.evaluate("window.__inviati.length = 0; document.getElementById('chat').textContent = ''")
        pagina.click("#scrivi")
        pagina.keyboard.insert_text(TESTO)
        pagina.keyboard.press("Enter")
        pagina.wait_for_function("window.__inviati.length > 0", timeout=15000)
        pagina.wait_for_timeout(800)
        letto, schermo = pagina.evaluate("window.__inviati[0]"), pagina.inner_text("#chat")
        segna("casella di scrittura: la pagina legge solo segnaposto, a schermo i valori veri", not any(s in letto for s in SENSIBILI) and "[PERSONA_" in letto
              and all(s in schermo for s in SENSIBILI) and "[PERSONA_" not in schermo, f"letti in chiaro: {sum(s in letto for s in SENSIBILI)} · a schermo {sum(s in schermo for s in SENSIBILI)}/4")

        # --- allegati: il file scelto, trascinato o incollato arriva alla pagina gia' anonimizzato
        cartella = Path(tempfile.mkdtemp(prefix="omissis_allegati_"))
        (cartella / "lettera.txt").write_text(TESTO, encoding="utf-8")
        import docx
        d = docx.Document()
        d.add_paragraph(TESTO)
        d.save(str(cartella / "verbale.docx"))
        (cartella / "archivio.bin").write_bytes(b"\x00\x01" + TESTO.encode("utf-8"))

        def ricevuti(quanti, secondi=40):
            for _ in range(secondi * 5):
                if pagina.evaluate("window.__file.length") >= quanti:
                    return pagina.evaluate("window.__file")
                pagina.wait_for_timeout(200)
            return pagina.evaluate("window.__file")

        pagina.evaluate("window.__file.length = 0; window.__primi.length = 0")
        pagina.set_input_files("#allega", str(cartella / "lettera.txt"))
        r = ricevuti(1)
        with urllib.request.urlopen("http://127.0.0.1:9911/visto_file", timeout=10) as risposta:
            caricato = json.loads(risposta.read().decode("utf-8"))["ultimo"]
        segna("allegato di testo: la pagina riceve la copia anonimizzata, e carica quella",
              len(r) == 1 and r[0]["nome"] == "lettera.anon.txt" and "[PERSONA_" in r[0]["testo"] and not any(s in r[0]["testo"] for s in SENSIBILI)
              and r[0]["caricato"] and "[PERSONA_" in caricato and not any(s in caricato for s in SENSIBILI)
              and "lettera.txt" not in pagina.evaluate("window.__primi"), f"{r[0]['nome'] if r else 'nulla'} · al primo evento la pagina ha visto: {pagina.evaluate('window.__primi')}")

        pagina.evaluate("window.__file.length = 0")
        pagina.set_input_files("#allega", str(cartella / "verbale.docx"))
        r = ricevuti(1)
        testo_docx = ""
        if r and r[0]["dati"]:
            import base64
            import io
            testo_docx = "\n".join(p.text for p in docx.Document(io.BytesIO(base64.b64decode(r[0]["dati"]))).paragraphs)
        segna("allegato Word: resta un Word, con i dati sostituiti", len(r) == 1 and r[0]["nome"] == "verbale.anon.docx" and "[PERSONA_" in testo_docx
              and not any(s in testo_docx for s in SENSIBILI), r[0]["nome"] if r else "nulla")

        pagina.evaluate("window.__file.length = 0")
        pagina.set_input_files("#allega", str(cartella / "archivio.bin"))
        r = ricevuti(1)
        segna("formato non coperto: passa com'è (finché non si sceglie di bloccare i file)", len(r) == 1 and r[0]["nome"] == "archivio.bin")

        for come, evento, dove in (("trascinamento", "drop", "#zona"), ("incolla", "paste", "#scrivi")):
            pagina.evaluate("window.__file.length = 0")
            pagina.evaluate("""([evento, dove, testo]) => {
                const dt = new DataTransfer();
                dt.items.add(new File([testo], 'appunti.txt', {type: 'text/plain'}));
                const e = evento === 'drop' ? new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt})
                                            : new ClipboardEvent('paste', {bubbles: true, cancelable: true, clipboardData: dt});
                document.querySelector(dove).dispatchEvent(e);
            }""", [evento, dove, TESTO])
            r = ricevuti(1)
            segna(f"allegato per {come}: arriva la copia anonimizzata", len(r) == 1 and r[0]["come"] == come and r[0]["nome"] == "appunti.anon.txt"
                  and "[PERSONA_" in r[0]["testo"] and not any(s in r[0]["testo"] for s in SENSIBILI), r[0]["nome"] if r else "nulla")

        # --- XMLHttpRequest (come Gemini): richiesta mascherata, risposta sistemata nel testo della pagina
        grezza = pagina.evaluate("t => prova('gemini', t)", TESTO)
        arrivato = json.dumps(visto()["corpo"], ensure_ascii=False)
        pagina.wait_for_timeout(600)
        mostrato = pagina.inner_text("#esito")
        segna("XMLHttpRequest: richiesta mascherata", not any(s in arrivato for s in SENSIBILI) and "[PERSONA_" in arrivato
              and visto()["corpo"].get("at") == "gettone")
        segna("XMLHttpRequest: valori veri nel testo della pagina", all(s in mostrato for s in SENSIBILI) and "[PERSONA_" not in mostrato,
              "la risposta letta dal sito resta con i segnaposto" if "[PERSONA_" in grezza else "")

        # --- testo gia' mascherato incollato nella pagina; le caselle di scrittura non si toccano
        segnaposto = json.dumps(visto()["corpo"], ensure_ascii=False)
        segnaposto = segnaposto[segnaposto.index("[PERSONA_"):].split("]")[0] + "]"
        pagina.evaluate("s => { document.getElementById('incollato').textContent = 'Gentile ' + s + ', confermo.'; "
                        "document.getElementById('casella').value = s; }", segnaposto)
        pagina.wait_for_timeout(600)
        segna("segnaposto nel testo della pagina", "[PERSONA_" not in pagina.inner_text("#incollato"), pagina.inner_text("#incollato")[:12] + "…")
        segna("casella di scrittura lasciata com'è", pagina.input_value("#casella") == segnaposto)
        segna("avviso mostrato nella pagina", pagina.locator("[data-msp-pii]").count() == 1)

        # --- file
        n = visto()["file"]
        stato = pagina.evaluate("prova('file')")
        segna("file: passa e viene segnalato", stato == 200 and visto()["file"] == n + 1)

        # --- sospensione dalla finestrella
        fin = ctx.new_page()
        fin.goto(f"chrome-extension://{ident}/popup.html")
        attendi(fin, "#titolo", "attiva")
        attesa = {"it": ("attiva", "Sito aperto"), "en": ("on", "Open site")}.get(LINGUA)
        if attesa:
            segna(f"finestrella nella lingua del browser ({LINGUA})", fin.inner_text("#titoloTesto") == attesa[0] and attesa[1] in fin.inner_text("#sito")
                  and fin.evaluate("document.documentElement.lang").startswith(LINGUA), fin.inner_text("#titoloTesto"))
        fin.check("#sospesa")
        attendi(fin, "#titolo", "sospesa")
        pagina.wait_for_timeout(300)
        pagina.evaluate("t => prova('intera', t)", TESTO)
        segna("sospesa: il messaggio parte senza sostituzioni", SENSIBILI[0] in json.dumps(visto()["corpo"], ensure_ascii=False))
        fin.uncheck("#sospesa")
        attendi(fin, "#titolo", "attiva")
        pagina.wait_for_timeout(300)

        # --- codice sbagliato (come se il programma non rispondesse): la richiesta non parte
        buono = sw.evaluate("chrome.storage.local.get('token').then(d => d.token)")
        sw.evaluate("chrome.storage.local.set({token: 'sbagliato'})")
        prima = json.dumps(visto())
        try:
            pagina.evaluate("t => prova('claude', t)", TESTO)
            segna("protezione che non risponde: richiesta bloccata", False, "la richiesta è partita")
        except Exception:   # noqa: BLE001
            segna("protezione che non risponde: richiesta bloccata", json.dumps(visto()) == prima)
        try:
            pagina.evaluate("t => prova('gemini', t)", TESTO)
            segna("protezione che non risponde: XMLHttpRequest bloccata", False, "la richiesta è partita")
        except Exception:   # noqa: BLE001
            segna("protezione che non risponde: XMLHttpRequest bloccata", json.dumps(visto()) == prima)
        sw.evaluate("t => chrome.storage.local.set({token: t})", buono)

        # --- blocco di un servizio (politica scelta nel pannello): la pagina non viene nemmeno contattata
        pan.evaluate(CHIAMA_SERVIZI, {"id": "pi", "politica": "blocca"})
        fin.reload()   # aprire la finestrella fa rileggere le politiche
        attendi(fin, "#titolo", "attiva")
        regole = sw.evaluate("chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)")
        blocco = ctx.new_page()
        try:
            blocco.goto("https://pi.ai/", timeout=15000)
        except Exception:   # noqa: BLE001  (la navigazione viene deviata)
            pass
        blocco.wait_for_timeout(500)
        segna("servizio bloccato", blocco.url.startswith(f"chrome-extension://{ident}/blocked.html") and "Pi" in blocco.inner_text("h1"),
              f"{regole} regole · {blocco.url[:60]}")
        pan.evaluate(CHIAMA_SERVIZI, {"id": "pi", "politica": "registra"})

        # --- un servizio del radar: l'estensione non ha accesso al suo sito (non lo chiede), ma lo sa bloccare lo stesso
        pan.evaluate(CHIAMA_SERVIZI, {"id": "replika", "politica": "blocca"})
        fin.reload()
        attendi(fin, "#titolo", "attiva")
        fin.wait_for_timeout(500)
        radar = sw.evaluate("chrome.declarativeNetRequest.getDynamicRules()")
        accessi = sw.evaluate("chrome.runtime.getManifest().host_permissions")
        fermato = ctx.new_page()
        try:
            fermato.goto("https://replika.com/", timeout=15000)
            partita = True
        except Exception as ex:   # noqa: BLE001  (il browser rifiuta la richiesta: e' il blocco)
            partita = "ERR_BLOCKED_BY_CLIENT" not in str(ex)
        fermato.close()
        segna("servizio del radar bloccato, senza accesso al suo sito", len(radar) == 1 and radar[0]["action"]["type"] == "block"
              and "main_frame" in radar[0]["condition"]["resourceTypes"] and "replika.com" in radar[0]["condition"]["requestDomains"]
              and not any("replika" in h for h in accessi) and not partita, f"{len(radar)} regole · richiesta partita: {partita}")
        pan.evaluate(CHIAMA_SERVIZI, {"id": "replika", "politica": "registra"})
        fin.reload()
        attendi(fin, "#titolo", "attiva")
        segna("blocco tolto", sw.evaluate("chrome.declarativeNetRequest.getDynamicRules().then(r => r.length)") == 0)
        if "--screenshots" in sys.argv:
            fin.set_viewport_size({"width": 336, "height": 420})
            fin.screenshot(path=str(QUI / "screenshots" / f"estensione_finestrella-{LINGUA}.png"))
            blocco.screenshot(path=str(QUI / "screenshots" / f"estensione_bloccato-{LINGUA}.png"))
            pan.set_viewport_size({"width": 1180, "height": 820})
            pan.screenshot(path=str(QUI / "screenshots" / "browser.png"))
        ctx.close()

    # --- registro: solo conteggi, con l'indicazione "via estensione"
    nuove = [json.loads(r) for r in (paths.DATI / "activity.jsonl").read_text(encoding="utf-8").splitlines()[righe_prima:]]
    mie = [v for v in nuove if v.get("via") == "estensione"]
    testo = json.dumps(mie, ensure_ascii=False)
    segna("registro: righe dell'estensione senza testi", len([v for v in mie if v.get("evento") == "mascherata"]) >= 9
          and not any(s in testo for s in SENSIBILI), f"{len(mie)} righe: " + ", ".join(sorted({v.get('evento', '') for v in mie})))
    # --- il registro delle versioni: il browser di questa prova deve risultare, con il suo nome e la sua versione
    import activity
    visti = [g for g in activity.compatibilita() if g["via"] == "estensione" and g["cliente"]]
    segna("registro delle versioni: browser e versione annotati accanto alle sostituzioni riuscite", any(g["ok"] >= 1 and g["stato"] == "funziona"
          and any(c.isdigit() for c in g["cliente"]) for g in visti), "; ".join(sorted({g["cliente"] for g in visti}))[:120] or "nessun programma annotato")
    print("\nTUTTO OK" if all(esiti) else f"\n{esiti.count(False)} ERRORI")
    sys.exit(0 if all(esiti) else 1)


if __name__ == "__main__":
    main()
