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

QUI = Path(__file__).resolve().parent
CHROME = paths.browser_di_prova()
PORTA, FINTO = 9562, "http://localhost:9911"
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


class Guida:
    """Un secondo collegamento, che fa la parte dell'utente: apre la pagina e ci scrive."""

    def __init__(self):
        self.cdp = connector.Cdp(PORTA, lambda m: None)
        self.sid = None

    def apri(self, indirizzo, attendi_codice=True):
        t = self.cdp.invia("Target.createTarget", {"url": indirizzo})["targetId"]
        self.sid = self.cdp.invia("Target.attachToTarget", {"targetId": t, "flatten": True})["sessionId"]
        for _ in range(50):
            if self.valuta("document.readyState") == "complete" and self.valuta("typeof prova") == "function":
                break
            time.sleep(0.2)
        else:
            raise TimeoutError("la pagina di prova non si è caricata")
        if attendi_codice:   # il codice dentro la pagina diventa attivo un attimo dopo: le prove sui formati lo aspettano
            for _ in range(40):
                if self.valuta("!window.fetch.toString().includes('fetch')"):
                    return
                time.sleep(0.1)

    def valuta(self, espressione, attesa=60):
        r = self.cdp.invia("Runtime.evaluate", {"expression": espressione, "awaitPromise": True, "returnByValue": True}, self.sid, attesa=attesa)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", "errore nella pagina")[:160])
        return r["result"].get("value")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    registro = paths.DATI / "activity.jsonl"
    righe_prima = len(registro.read_text(encoding="utf-8").splitlines()) if registro.exists() else 0
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profilo:
        app = subprocess.Popen([str(CHROME), f"--remote-debugging-port={PORTA}", f"--user-data-dir={profilo}", "--headless=new",
                                "--no-first-run", "--no-default-browser-check", "about:blank"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(60):
                if connector.porta_aperta(PORTA):
                    break
                time.sleep(0.25)
            time.sleep(1)
            # --- una finestra gia' aperta e caricata PRIMA che il connettore si colleghi
            vecchia = Guida()
            vecchia.apri(FINTO + "/pagina", attendi_codice=False)
            con = connector.Connettore(PORTA, "app di prova", prova=True, sito="localhost")
            time.sleep(1.5)
            try:
                risposta = vecchia.valuta(f"prova('claude', {json.dumps(TESTO)})")
                arrivato = json.dumps(visto()["corpo"], ensure_ascii=False)
                segna("finestra già aperta al momento del collegamento", not any(s in arrivato for s in SENSIBILI) and "[PERSONA_" in arrivato
                      and all(s in risposta for s in SENSIBILI))
            except Exception as ex:   # noqa: BLE001
                segna("finestra già aperta al momento del collegamento", False, str(ex)[:150])
            guida = Guida()
            guida.apri(FINTO + "/pagina")
            segna("codice portato nella finestra", not con.errori and con.conteggi["pagine"] >= 1, f"{con.cdp.prodotto} · {'; '.join(con.errori)}")
            for formato in ("claude", "openai", "chatgpt", "cumulativo", "righe", "prefisso", "intera", "richiesta"):
                try:
                    risposta = guida.valuta(f"prova({json.dumps(formato)}, {json.dumps(TESTO)})")
                except Exception as ex:   # noqa: BLE001
                    segna(formato, False, str(ex)[:150])
                    continue
                arrivato = json.dumps(visto()["corpo"], ensure_ascii=False)
                fuori = [s for s in SENSIBILI if s in arrivato]
                tornati = [s for s in SENSIBILI if s in (risposta or "")]
                segna(formato, not fuori and "[PERSONA_" in arrivato and len(tornati) == len(SENSIBILI) and "[PERSONA_" not in risposta,
                      f"al servizio in chiaro: {len(fuori)} · tornati alla pagina: {len(tornati)}/{len(SENSIBILI)}")
            guida.valuta(f"prova('claude', {json.dumps(TESTO)})")
            risposta = guida.valuta("prova('cronologia')")
            segna("cronologia (risposta JSON a una GET)", all(s in risposta for s in SENSIBILI))
            guida.valuta(f"prova('gemini', {json.dumps(TESTO)})")
            arrivato = json.dumps(visto()["corpo"], ensure_ascii=False)
            time.sleep(0.7)
            mostrato = guida.valuta("document.getElementById('esito').innerText")
            segna("XMLHttpRequest: richiesta mascherata", not any(s in arrivato for s in SENSIBILI) and "[PERSONA_" in arrivato)
            segna("XMLHttpRequest: valori veri nel testo della pagina", all(s in mostrato for s in SENSIBILI) and "[PERSONA_" not in mostrato)
            segna("il sito non vede il canale con il programma", guida.valuta(f"typeof window.{connector.CHIAMATA}") == "undefined"
                  and guida.valuta("typeof window.__msp_risposta") == "undefined")
            segna("conteggi del connettore", con.conteggi["messaggi"] >= 9 and con.conteggi["sostituzioni"] >= 36, json.dumps(con.conteggi))
            segna("nessun errore del connettore", not con.errori, "; ".join(con.errori)[:150])
            import activity
            visti = [g for g in activity.compatibilita() if g["via"] == "app desktop" and g["cliente"]]
            segna("registro delle versioni: l'app e la sua versione annotate accanto alle sostituzioni riuscite", any(g["ok"] >= 1 and "[" in g["cliente"] for g in visti),
                  "; ".join(sorted({g["cliente"] for g in visti}))[:120] or "nessun programma annotato")

            # --- come nelle app vere (1): una finestra che il browser tiene FERMA finche' il connettore non da' il via
            t0 = time.perf_counter()
            ferma = con.cdp.invia("Target.createTarget", {"url": FINTO + "/pagina"})["targetId"]
            tenuta = Guida()
            tenuta.sid = tenuta.cdp.invia("Target.attachToTarget", {"targetId": ferma, "flatten": True})["sessionId"]
            pronta = False
            for _ in range(60):
                try:
                    if tenuta.valuta("document.readyState == 'complete' && typeof prova == 'function' && !window.fetch.toString().includes('fetch')", attesa=3):
                        pronta = True
                        break
                except Exception:   # noqa: BLE001
                    pass
                time.sleep(0.1)
            attesa_ms = round((time.perf_counter() - t0) * 1000)
            risposta = tenuta.valuta(f"prova('claude', {json.dumps(TESTO)})") if pronta else ""
            arrivato = json.dumps(visto()["corpo"], ensure_ascii=False)
            segna("finestra tenuta ferma all'avvio: parte subito e protetta", pronta and attesa_ms < 5000 and not con.errori
                  and not any(s in arrivato for s in SENSIBILI) and all(s in risposta for s in SENSIBILI), f"{attesa_ms} ms · {'; '.join(con.errori)[:120]}")

            # --- come nelle app vere (2): una finestra con indirizzo interno (qui un file locale) che parla con il servizio
            locale = Path(tempfile.mkdtemp()) / "finestra_interna.html"
            locale.write_bytes(urllib.request.urlopen(FINTO + "/pagina", timeout=10).read())
            interna = Guida()
            interna.apri(locale.as_uri())
            try:
                risposta = interna.valuta(f"prova('claude', {json.dumps(TESTO)})")
                arrivato = json.dumps(visto()["corpo"], ensure_ascii=False)
                segna("finestra con indirizzo interno dell'app", not any(s in arrivato for s in SENSIBILI) and "[PERSONA_" in arrivato
                      and all(s in risposta for s in SENSIBILI), f"al servizio in chiaro: {sum(s in arrivato for s in SENSIBILI)}")
            except Exception as ex:   # noqa: BLE001
                segna("finestra con indirizzo interno dell'app", False, str(ex)[:150])
            segna("stato dichiarato dal connettore", con.esito == "si", con.esito)

            # --- come nell'app di ChatGPT: la finestra parla con un indirizzo INTERNO dell'app, non con il servizio.
            # Qui l'indirizzo "interno" e' 127.0.0.1 (che non e' un servizio protetto) e il servizio dell'app e' localhost.
            con2 = connector.Connettore(PORTA, "app con indirizzo interno", prova=True, sito="localhost", interni=["http://127.0.0.1:9911"])
            time.sleep(1)
            dentro = Guida()
            dentro.apri("http://127.0.0.1:9911/pagina")
            try:
                risposta = dentro.valuta(f"prova('chatgpt', {json.dumps(TESTO)})")
                arrivato = json.dumps(visto()["corpo"], ensure_ascii=False)
                segna("la finestra parla con un indirizzo interno dell'app (come ChatGPT)", not any(s in arrivato for s in SENSIBILI) and "[PERSONA_" in arrivato
                      and all(s in risposta for s in SENSIBILI) and con2.conteggi["messaggi"] >= 1,
                      f"al servizio in chiaro: {sum(s in arrivato for s in SENSIBILI)} · tornati {sum(s in risposta for s in SENSIBILI)}/4 · {con2.conteggi['messaggi']} messaggi")
            except Exception as ex:   # noqa: BLE001
                segna("la finestra parla con un indirizzo interno dell'app (come ChatGPT)", False, str(ex)[:150])
            # --- come nell'app di ChatGPT davvero: la chat non usa la rete della finestra. Si scrive nella casella con
            # tasti veri e si guarda che cosa la "app" ha letto dalla casella (__inviati) e che cosa si vede a schermo.
            def scrivi_e_invia(testo, con_il_pulsante=False):
                dentro.valuta("document.getElementById('scrivi').focus()")
                dentro.cdp.invia("Input.insertText", {"text": testo}, dentro.sid)
                if con_il_pulsante:
                    dentro.valuta("document.getElementById('manda').click()")
                else:
                    for tipo in ("rawKeyDown", "char", "keyUp"):
                        dentro.cdp.invia("Input.dispatchKeyEvent", {"type": tipo, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13,
                                                                    "nativeVirtualKeyCode": 13, "text": "\r" if tipo == "char" else ""}, dentro.sid)
                for _ in range(40):
                    if dentro.valuta("window.__inviati.length") and not dentro.valuta("document.getElementById('scrivi').innerText.trim()"):
                        break
                    time.sleep(0.1)
                time.sleep(0.7)
                return dentro.valuta("window.__inviati[window.__inviati.length - 1] || ''"), dentro.valuta("document.getElementById('chat').innerText")

            for nome, pulsante in (("casella di scrittura: Invio", False), ("casella di scrittura: pulsante di invio", True)):
                dentro.valuta("window.__inviati.length = 0; document.getElementById('chat').textContent = ''")
                try:
                    letto, schermo = scrivi_e_invia(TESTO, pulsante)
                    segna(nome, letto and not any(s in letto for s in SENSIBILI) and "[PERSONA_" in letto and all(s in schermo for s in SENSIBILI)
                          and "[PERSONA_" not in schermo, f"letti dall'app in chiaro: {sum(s in letto for s in SENSIBILI)} · a schermo {sum(s in schermo for s in SENSIBILI)}/4")
                except Exception as ex:   # noqa: BLE001
                    segna(nome, False, str(ex)[:150])
            # --- la "app" scrive la risposta a pezzetti, spezzando ogni segnaposto in tre (come fa l'app di ChatGPT)
            import re as _re
            segn = _re.findall(r"\[[A-Z_]+_\d+\]", letto or "")[:3]
            dentro.valuta("""(async s => { const p = document.createElement('p'); p.id = 'spezzata'; document.getElementById('chat').appendChild(p);
              const aggiungi = async x => { const e = document.createElement('span'); e.textContent = x; p.appendChild(e); await new Promise(r => setTimeout(r, 25)); };
              for (const x of s) { await aggiungi('Gentile '); const i = x.lastIndexOf('_'); const b = document.createElement('strong'); p.appendChild(b);
                for (const pezzo of [x.slice(0, i), '_', x.slice(i + 1)]) { const e = document.createElement('span'); e.textContent = pezzo; b.appendChild(e); await new Promise(r => setTimeout(r, 25)); }
                await aggiungi(', confermo. '); } })(%s)""" % json.dumps(segn))
            time.sleep(1.0)
            spezzata = dentro.valuta("document.getElementById('spezzata').innerText")
            segna("segnaposto scritti a pezzi nella risposta: tornano i valori veri", len(segn) >= 2 and "[" not in spezzata and "Giulia Ferraresi" in spezzata
                  and spezzata.count("Gentile") == len(segn), spezzata[:70])
            dentro.valuta("window.__inviati.length = 0")
            letto, _ = scrivi_e_invia("Quanto fa dodici per otto? Rispondi solo con il numero.")
            segna("casella di scrittura: un testo senza dati parte com'è", letto == "Quanto fa dodici per otto? Rispondi solo con il numero.", letto[:40])
            # --- allegati: un file trascinato nella finestra dell'app arriva alla "app" gia' anonimizzato
            dentro.valuta("window.__file.length = 0")
            dentro.valuta("""(() => { const dt = new DataTransfer();
                dt.items.add(new File([%s], 'appunti.txt', {type: 'text/plain'}));
                document.getElementById('zona').dispatchEvent(new DragEvent('drop', {bubbles: true, cancelable: true, dataTransfer: dt})); return true; })()""" % json.dumps(TESTO))
            for _ in range(150):
                if dentro.valuta("window.__file.length"):
                    break
                time.sleep(0.2)
            arrivato = dentro.valuta("window.__file[0] || null") or {}
            segna("allegato trascinato nell'app: arriva la copia anonimizzata", arrivato.get("nome") == "appunti.anon.txt" and "[PERSONA_" in arrivato.get("testo", "")
                  and "Giulia Ferraresi" not in arrivato.get("testo", ""), arrivato.get("nome", "nulla"))
            con.porta_motore = con2.porta_motore = 1   # entrambi i connettori di questa prova rispondono alla stessa finestra
            dentro.valuta("window.__inviati.length = 0")
            scrivi_e_invia(TESTO)
            segna("casella di scrittura: se la protezione non risponde il messaggio non parte", dentro.valuta("window.__inviati.length") == 0)
            con.porta_motore = con2.porta_motore = connector.PORTA_MOTORE
            dentro.valuta("document.getElementById('scrivi').textContent = ''")
            con2.chiudi()
            time.sleep(0.5)

            # --- il caso difficile: finestre nuove che mandano un messaggio nell'istante in cui si aprono
            chiaro = mascherati = fermi = 0
            for giro in range(1, 21):
                indirizzo = f"{FINTO}/pagina?subito={giro}"
                rich = urllib.request.Request(f"http://127.0.0.1:{PORTA}/json/new?{urllib.parse.quote(indirizzo, safe=':/?=&%')}", method="PUT")
                ident = json.loads(urllib.request.urlopen(rich, timeout=10).read().decode("utf-8"))["id"]
                arrivato = None
                for _ in range(40):
                    corpo = visto()["corpo"]
                    if isinstance(corpo, dict) and corpo.get("giro") == giro:
                        arrivato = json.dumps(corpo, ensure_ascii=False)
                        break
                    time.sleep(0.1)
                if arrivato is None:
                    fermi += 1
                elif any(s in arrivato for s in SENSIBILI):
                    chiaro += 1
                else:
                    mascherati += 1
                urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/json/close/{ident}", timeout=10).read()
            segna("messaggio inviato nell'istante in cui la finestra si apre (20 finestre)", chiaro == 0 and mascherati + fermi == 20,
                  f"in chiaro {chiaro} · mascherati {mascherati} · non partiti {fermi} · fermati dal controllo in rete {con.conteggi['in_rete']}")

            # --- il programma non risponde: il messaggio non deve partire
            con.porta_motore = 1
            prima = json.dumps(visto())
            try:
                guida.valuta(f"prova('claude', {json.dumps(TESTO)})")
                segna("protezione che non risponde: richiesta bloccata", False, "la richiesta è partita")
            except Exception:   # noqa: BLE001
                segna("protezione che non risponde: richiesta bloccata", json.dumps(visto()) == prima)
            con.porta_motore = connector.PORTA_MOTORE

            # --- connettore staccato: la pagina resta con il codice dentro e non lascia uscire nulla
            con.chiudi()
            time.sleep(0.5)
            prima = json.dumps(visto())
            try:
                guida.valuta(f"Promise.race([prova('intera', {json.dumps(TESTO)}), new Promise((_, no) => setTimeout(() => no(new Error('ferma')), 4000))])")
                segna("connettore staccato: nulla esce in chiaro", False, "la richiesta è partita")
            except Exception:   # noqa: BLE001
                segna("connettore staccato: nulla esce in chiaro", json.dumps(visto()) == prima)
        finally:
            app.terminate()
    nuove = [json.loads(r) for r in registro.read_text(encoding="utf-8").splitlines()[righe_prima:]]
    mie = [v for v in nuove if v.get("via") == "app desktop"]
    segna("registro: righe «via app desktop» senza testi", len([v for v in mie if v.get("evento") == "mascherata"]) >= 9
          and not any(s in json.dumps(mie, ensure_ascii=False) for s in SENSIBILI), f"{len(mie)} righe")
    print("\nTUTTO OK" if all(esiti) else f"\n{esiti.count(False)} ERRORI")
    sys.exit(0 if all(esiti) else 1)


if __name__ == "__main__":
    main()
