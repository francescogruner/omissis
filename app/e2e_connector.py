# -*- coding: utf-8 -*-
"""Prova il connettore per le app desktop su un'app di prova: un Chromium avviato con la porta di
debug e SENZA estensione (e' cio' che sono, sotto, Claude Desktop e l'app di OpenAI), contro il
servizio finto. Non prova le app vere: quelle vanno chiuse e riaperte dal pannello.

Prima:  panel.py --test --no-tray --no-browser      e      mock_service.py
"""
import json
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

import connector
import paths

HERE = Path(__file__).resolve().parent
CHROME = paths.test_browser()
PORT, FAKE = 9562, "http://localhost:9911"
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


class Guide:
    """Un secondo collegamento, che fa la parte dell'utente: apre la pagina e ci scrive."""

    def __init__(self):
        self.cdp = connector.Cdp(PORT, lambda m: None)
        self.sid = None

    def open_up(self, address, wait_for_code=True):
        t = self.cdp.send("Target.createTarget", {"url": address})["targetId"]
        self.sid = self.cdp.send("Target.attachToTarget", {"targetId": t, "flatten": True})["sessionId"]
        for _ in range(50):
            if self.evaluate("document.readyState") == "complete" and self.evaluate("typeof test") == "function":
                break
            time.sleep(0.2)
        else:
            raise TimeoutError("la pagina di prova non si è caricata")
        if wait_for_code:   # il codice dentro la pagina diventa attivo un attimo dopo: le prove sui formati lo aspettano
            for _ in range(40):
                if self.evaluate("!window.fetch.toString().includes('fetch')"):
                    return
                time.sleep(0.1)

    def evaluate(self, expression, timeout=60):
        r = self.cdp.send("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True}, self.sid, timeout=timeout)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", "errore nella pagina")[:160])
        return r["result"].get("value")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    log = paths.DATA / "activity.jsonl"
    lines_before = len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        app = subprocess.Popen([str(CHROME), f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}", "--headless=new",
                                "--no-first-run", "--no-default-browser-check", "about:blank"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(60):
                if connector.opened_port(PORT):
                    break
                time.sleep(0.25)
            time.sleep(1)
            # --- una finestra gia' aperta e caricata PRIMA che il connettore si colleghi
            old_one = Guide()
            old_one.open_up(FAKE + "/page", wait_for_code=False)
            con = connector.Connector(PORT, "app di prova", test=True, site="localhost")
            time.sleep(1.5)
            try:
                response = old_one.evaluate(f"test('claude', {json.dumps(TEXT)})")
                arrived = json.dumps(seen()["body"], ensure_ascii=False)
                mark("finestra già aperta al momento del collegamento", not any(s in arrived for s in SENSITIVE) and "[PERSONA_" in arrived
                      and all(s in response for s in SENSITIVE))
            except Exception as ex:   # noqa: BLE001
                mark("finestra già aperta al momento del collegamento", False, str(ex)[:150])
            guide = Guide()
            guide.open_up(FAKE + "/page")
            mark("codice portato nella finestra", not con.errors and con.counts["pages"] >= 1, f"{con.cdp.product} · {'; '.join(con.errors)}")
            mark("controllo in rete acceso sull'intero browser (vale anche per le finestre non ancora agganciate)", con.browser_guard, "; ".join(con.notices))
            for fmt in ("claude", "openai", "chatgpt", "cumulative", "lines", "prefix", "whole", "request"):
                try:
                    response = guide.evaluate(f"test({json.dumps(fmt)}, {json.dumps(TEXT)})")
                except Exception as ex:   # noqa: BLE001
                    mark(fmt, False, str(ex)[:150])
                    continue
                arrived = json.dumps(seen()["body"], ensure_ascii=False)
                outside = [s for s in SENSITIVE if s in arrived]
                returned = [s for s in SENSITIVE if s in (response or "")]
                mark(fmt, not outside and "[PERSONA_" in arrived and len(returned) == len(SENSITIVE) and "[PERSONA_" not in response,
                      f"al servizio in chiaro: {len(outside)} · tornati alla pagina: {len(returned)}/{len(SENSITIVE)}")
            guide.evaluate(f"test('claude', {json.dumps(TEXT)})")
            response = guide.evaluate("test('history')")
            mark("cronologia (risposta JSON a una GET)", all(s in response for s in SENSITIVE))
            guide.evaluate(f"test('gemini', {json.dumps(TEXT)})")
            arrived = json.dumps(seen()["body"], ensure_ascii=False)
            time.sleep(0.7)
            shown = guide.evaluate("document.getElementById('outcome').innerText")
            mark("XMLHttpRequest: richiesta mascherata", not any(s in arrived for s in SENSITIVE) and "[PERSONA_" in arrived)
            mark("XMLHttpRequest: valori veri nel testo della pagina", all(s in shown for s in SENSITIVE) and "[PERSONA_" not in shown)
            mark("il sito non vede il canale con il programma", guide.evaluate(f"typeof window.{connector.CALL}") == "undefined"
                  and guide.evaluate("typeof window.__msp_response") == "undefined")
            mark("conteggi del connettore", con.counts["messages"] >= 9 and con.counts["replacements"] >= 36, json.dumps(con.counts))
            mark("nessun errore del connettore", not con.errors, "; ".join(con.errors)[:150])
            import activity
            sightings = [g for g in activity.compatibility() if g["via"] == "app desktop" and g["client"]]
            mark("registro delle versioni: l'app e la sua versione annotate accanto alle sostituzioni riuscite", any(g["ok"] >= 1 and "[" in g["client"] for g in sightings),
                  "; ".join(sorted({g["client"] for g in sightings}))[:120] or "nessun programma annotato")

            # --- come nelle app vere (1): una finestra che il browser tiene FERMA finche' il connettore non da' il via
            t0 = time.perf_counter()
            stop = con.cdp.send("Target.createTarget", {"url": FAKE + "/page"})["targetId"]
            kept = Guide()
            kept.sid = kept.cdp.send("Target.attachToTarget", {"targetId": stop, "flatten": True})["sessionId"]
            ready = False
            for _ in range(60):
                try:
                    if kept.evaluate("document.readyState == 'complete' && typeof test == 'function' && !window.fetch.toString().includes('fetch')", timeout=3):
                        ready = True
                        break
                except Exception:   # noqa: BLE001
                    pass
                time.sleep(0.1)
            timeout_ms = round((time.perf_counter() - t0) * 1000)
            response = kept.evaluate(f"test('claude', {json.dumps(TEXT)})") if ready else ""
            arrived = json.dumps(seen()["body"], ensure_ascii=False)
            mark("finestra tenuta ferma all'avvio: parte subito e protetta", ready and timeout_ms < 5000 and not con.errors
                  and not any(s in arrived for s in SENSITIVE) and all(s in response for s in SENSITIVE), f"{timeout_ms} ms · {'; '.join(con.errors)[:120]}")

            # --- come nelle app vere (2): una finestra con indirizzo interno (qui un file locale) che parla con il servizio
            locale = Path(tempfile.mkdtemp()) / "finestra_interna.html"
            locale.write_bytes(urllib.request.urlopen(FAKE + "/page", timeout=10).read())
            internal = Guide()
            internal.open_up(locale.as_uri())
            try:
                response = internal.evaluate(f"test('claude', {json.dumps(TEXT)})")
                arrived = json.dumps(seen()["body"], ensure_ascii=False)
                mark("finestra con indirizzo interno dell'app", not any(s in arrived for s in SENSITIVE) and "[PERSONA_" in arrived
                      and all(s in response for s in SENSITIVE), f"al servizio in chiaro: {sum(s in arrived for s in SENSITIVE)}")
            except Exception as ex:   # noqa: BLE001
                mark("finestra con indirizzo interno dell'app", False, str(ex)[:150])
            mark("stato dichiarato dal connettore", con.outcome == "yes", con.outcome)

            # --- come nell'app di ChatGPT: la finestra parla con un indirizzo INTERNO dell'app, non con il servizio.
            # Qui l'indirizzo "interno" e' 127.0.0.1 (che non e' un servizio protetto) e il servizio dell'app e' localhost.
            con2 = connector.Connector(PORT, "app con indirizzo interno", test=True, site="localhost", internals=["http://127.0.0.1:9911"])
            time.sleep(1)
            inside = Guide()
            inside.open_up("http://127.0.0.1:9911/page")
            try:
                response = inside.evaluate(f"test('chatgpt', {json.dumps(TEXT)})")
                arrived = json.dumps(seen()["body"], ensure_ascii=False)
                mark("la finestra parla con un indirizzo interno dell'app (come ChatGPT)", not any(s in arrived for s in SENSITIVE) and "[PERSONA_" in arrived
                      and all(s in response for s in SENSITIVE) and con2.counts["messages"] >= 1,
                      f"al servizio in chiaro: {sum(s in arrived for s in SENSITIVE)} · tornati {sum(s in response for s in SENSITIVE)}/4 · {con2.counts['messages']} messaggi")
            except Exception as ex:   # noqa: BLE001
                mark("la finestra parla con un indirizzo interno dell'app (come ChatGPT)", False, str(ex)[:150])
            # --- come nell'app di ChatGPT davvero: la chat non usa la rete della finestra. Si scrive nella casella con
            # tasti veri e si guarda che cosa la "app" ha letto dalla casella (__inviati) e che cosa si vede a schermo.
            def write_and_send(text, with_button=False):
                inside.evaluate("document.getElementById('write').focus()")
                inside.cdp.send("Input.insertText", {"text": text}, inside.sid)
                if with_button:
                    inside.evaluate("document.getElementById('post').click()")
                else:
                    for kind in ("rawKeyDown", "char", "keyUp"):
                        inside.cdp.send("Input.dispatchKeyEvent", {"type": kind, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13,
                                                                    "nativeVirtualKeyCode": 13, "text": "\r" if kind == "char" else ""}, inside.sid)
                for _ in range(40):
                    if inside.evaluate("window.__sent.length") and not inside.evaluate("document.getElementById('write').innerText.trim()"):
                        break
                    time.sleep(0.1)
                time.sleep(0.7)
                return inside.evaluate("window.__sent[window.__sent.length - 1] || ''"), inside.evaluate("document.getElementById('chat').innerText")

            for name, button in (("casella di scrittura: Invio", False), ("casella di scrittura: pulsante di invio", True)):
                inside.evaluate("window.__sent.length = 0; document.getElementById('chat').textContent = ''")
                try:
                    read_back, screen = write_and_send(TEXT, button)
                    mark(name, read_back and not any(s in read_back for s in SENSITIVE) and "[PERSONA_" in read_back and all(s in screen for s in SENSITIVE)
                          and "[PERSONA_" not in screen, f"letti dall'app in chiaro: {sum(s in read_back for s in SENSITIVE)} · a schermo {sum(s in screen for s in SENSITIVE)}/4")
                except Exception as ex:   # noqa: BLE001
                    mark(name, False, str(ex)[:150])
            # --- la "app" scrive la risposta a pezzetti, spezzando ogni segnaposto in tre (come fa l'app di ChatGPT)
            import re as _re
            segn = _re.findall(r"\[[A-Z_]+_\d+\]", read_back or "")[:3]
            inside.evaluate("""(async s => { const p = document.createElement('p'); p.id = 'split'; document.getElementById('chat').appendChild(p);
              const aggiungi = async x => { const e = document.createElement('span'); e.textContent = x; p.appendChild(e); await new Promise(r => setTimeout(r, 25)); };
              for (const x of s) { await aggiungi('Gentile '); const i = x.lastIndexOf('_'); const b = document.createElement('strong'); p.appendChild(b);
                for (const chunk of [x.slice(0, i), '_', x.slice(i + 1)]) { const e = document.createElement('span'); e.textContent = chunk; b.appendChild(e); await new Promise(r => setTimeout(r, 25)); }
                await aggiungi(', confermo. '); } })(%s)""" % json.dumps(segn))
            time.sleep(1.0)
            split = inside.evaluate("document.getElementById('split').innerText")
            mark("segnaposto scritti a pezzi nella risposta: tornano i valori veri", len(segn) >= 2 and "[" not in split and "Giulia Ferraresi" in split
                  and split.count("Gentile") == len(segn), split[:70])
            inside.evaluate("window.__sent.length = 0")
            read_back, _ = write_and_send("Quanto fa dodici per otto? Rispondi solo con il numero.")
            mark("casella di scrittura: un testo senza dati parte com'è", read_back == "Quanto fa dodici per otto? Rispondi solo con il numero.", read_back[:40])
            # --- allegati: un file trascinato nella finestra dell'app arriva alla "app" gia' anonimizzato
            inside.evaluate("window.__file.length = 0")
            inside.evaluate("""(() => { const dt = new DataTransfer();
                dt.items.add(new File([%s], 'appunti.txt', {type: 'text/plain'}));
                document.getElementById('zone').dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt})); return true; })()""" % json.dumps(TEXT))
            for _ in range(150):
                if inside.evaluate("window.__file.length"):
                    break
                time.sleep(0.2)
            arrived = inside.evaluate("window.__file[0] || null") or {}
            mark("allegato trascinato nell'app: arriva la copia anonimizzata", arrived.get("name") == "appunti.anon.txt" and "[PERSONA_" in arrived.get("text", "")
                  and "Giulia Ferraresi" not in arrived.get("text", ""), arrived.get("name", "nothing"))
            con.engine_port = con2.engine_port = 1   # entrambi i connettori di questa prova rispondono alla stessa finestra
            inside.evaluate("window.__sent.length = 0")
            write_and_send(TEXT)
            mark("casella di scrittura: se la protezione non risponde il messaggio non parte", inside.evaluate("window.__sent.length") == 0)
            con.engine_port = con2.engine_port = connector.ENGINE_PORT
            inside.evaluate("document.getElementById('write').textContent = ''")
            con2.close()
            time.sleep(0.5)

            # --- il caso difficile: finestre nuove che mandano un messaggio nell'istante in cui si aprono
            light = masked = idle = 0
            for lap in range(1, 21):
                address = f"{FAKE}/page?at_once={lap}"
                req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{urllib.parse.quote(address, safe=':/?=&%')}", method="PUT")
                ident = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8"))["id"]
                arrived = None
                for _ in range(40):
                    body = seen()["body"]
                    if isinstance(body, dict) and body.get("lap") == lap:
                        arrived = json.dumps(body, ensure_ascii=False)
                        break
                    time.sleep(0.1)
                if arrived is None:
                    idle += 1
                elif any(s in arrived for s in SENSITIVE):
                    light += 1
                else:
                    masked += 1
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/close/{ident}", timeout=10).read()
            mark("messaggio inviato nell'istante in cui la finestra si apre (20 finestre)", light == 0 and masked + idle == 20,
                  f"in chiaro {light} · mascherati {masked} · non partiti {idle} · fermati dal controllo in rete {con.counts['at_network']}")

            # --- il programma non risponde: il messaggio non deve partire
            con.engine_port = 1
            before = json.dumps(seen())
            try:
                guide.evaluate(f"test('claude', {json.dumps(TEXT)})")
                mark("protezione che non risponde: richiesta bloccata", False, "la richiesta è partita")
            except Exception:   # noqa: BLE001
                mark("protezione che non risponde: richiesta bloccata", json.dumps(seen()) == before)
            con.engine_port = connector.ENGINE_PORT

            # --- connettore staccato: la pagina resta con il codice dentro e non lascia uscire nulla
            con.close()
            time.sleep(0.5)
            before = json.dumps(seen())
            try:
                guide.evaluate(f"Promise.race([test('whole', {json.dumps(TEXT)}), new Promise((_, no) => setTimeout(() => no(new Error('stop')), 4000))])")
                mark("connettore staccato: nulla esce in chiaro", False, "la richiesta è partita")
            except Exception:   # noqa: BLE001
                mark("connettore staccato: nulla esce in chiaro", json.dumps(seen()) == before)
        finally:
            app.terminate()
    new_ones = [json.loads(r) for r in log.read_text(encoding="utf-8").splitlines()[lines_before:]]
    my = [v for v in new_ones if v.get("via") == "app desktop"]
    mark("registro: righe «via app desktop» senza testi", len([v for v in my if v.get("event") == "masked"]) >= 9
          and not any(s in json.dumps(my, ensure_ascii=False) for s in SENSITIVE), f"{len(my)} righe")
    print("\nTUTTO OK" if all(outcomes) else f"\n{outcomes.count(False)} ERRORI")
    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
