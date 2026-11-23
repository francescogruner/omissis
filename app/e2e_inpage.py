# -*- coding: utf-8 -*-
"""Prova in un browser vero il codice della casella portato nella pagina DAL PROXY (inpage.py), cioe' la strada che
protegge l'app desktop di Claude: browser -> proxy di Omissis -> «app finta» (mock_service.py, /claude-app).

L'app finta manda il messaggio come fa claude.ai dal novembre 2026 (una chiamata in protobuf) ed e' servita con una
Content-Security-Policy a nonce. Controlla che: il codice entri nella pagina e giri nonostante quella regola; all'Invio
il testo venga sostituito nella casella prima che la pagina lo legga; al servizio arrivino solo segnaposto; i valori
veri tornino nel testo della pagina; se la casella viene saltata, i dati li sostituisca il proxy leggendo il protobuf.
Con --vera apre anche la pagina d'ingresso vera di claude.ai dal proxy (senza accesso) per vedere che il codice giri
con la regola di sicurezza vera.

Richiede la copia di prova accesa (panel.py --test, con le sue variabili) e mock_service.py 9911.
   Uso: python e2e_inpage.py [--headed] [--vera]
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(HERE / ".playwright"))
from playwright.sync_api import sync_playwright   # noqa: E402

import paths      # noqa: E402
import settings   # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
FAKE = "http://localhost:9911"
PROXY = f"http://127.0.0.1:{int(settings.read()['port'])}"
TEXT = ("Buongiorno, sono Giulia Ferraresi della Nevatek S.r.l.: scrivi ad Aldo Bruschi (aldo.bruschi@nevatek.example, "
        "cell. 347 5551234), l'IBAN per il rimborso è IT60X0542811101000000123456.")
ORIGINALS = ["Giulia Ferraresi", "Nevatek", "Aldo Bruschi", "aldo.bruschi@nevatek.example", "347 5551234", "IT60X0542811101000000123456"]
outcomes = []


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(("OK     " if ok else "ERRORE ") + name + (f"   {note}" if note else ""))


def seen():
    with urllib.request.urlopen(f"{FAKE.replace('localhost', '127.0.0.1')}/seen", timeout=10) as r:
        return json.loads(r.read().decode("utf-8")).get("rpc") or []


def log():
    p = paths.DATA / "activity.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.startswith("{")] if p.exists() else []


def wait(test, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        if test():
            return True
        time.sleep(0.25)
    return False


def main():
    before = len(log())
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless="--headed" not in sys.argv, proxy={"server": PROXY, "bypass": "<-loopback>"})
        ctx = browser.new_context(ignore_https_errors=True, permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        console = []
        page.on("console", lambda m: console.append(m.text))
        page.goto(f"{FAKE}/claude-app", wait_until="load")
        refused = [c for c in console if "Content Security Policy" in c or "Refused to" in c]
        mark("il codice gira nella pagina, con la regola di sicurezza a nonce", wait(lambda: page.evaluate("globalThis.MSP_COPY === true"), 8) and not refused,
             (refused[0][:120] if refused else ""))
        mark("lo script si e' tolto dalla pagina", page.evaluate("[...document.scripts].every(s => !s.textContent.includes('__omissis__'))"))
        mark("la pagina e' stata annotata nel registro", any(e.get("event") == "page_prepared" for e in log()[before:]))
        mark("il codice si e' presentato al proxy, che ha annotato in quale programma gira",
             wait(lambda: any(e.get("event") == "page_active" and e.get("client") for e in log()[before:]), 10))

        # 1. la strada normale: si scrive nella casella e si preme Invio
        page.click("#write")
        page.keyboard.type(TEXT, delay=0)
        page.keyboard.press("Enter")
        mark("il messaggio parte", wait(lambda: page.evaluate("window.__sent.length") == 1), str(page.evaluate("window.__sent.length")))
        sent = page.evaluate("window.__sent[0] || ''")
        mark("la pagina ha letto dalla casella solo segnaposto", bool(sent) and not any(o in sent for o in ORIGINALS) and "[" in sent, sent[:90])
        arrived = " | ".join(seen())
        mark("al servizio sono arrivati solo segnaposto", bool(arrived) and not any(o in arrived for o in ORIGINALS) and "[PERSONA_" in arrived, arrived[:110])
        shown = wait(lambda: all(o in page.inner_text("#chat") for o in ORIGINALS), 10)
        mark("nel testo della pagina tornano i valori veri", shown, page.inner_text("#chat")[:110])
        entries = log()[before:]
        box = [e for e in entries if e.get("event") == "masked" and e.get("method") == "box"]
        mark("nel registro: sostituito nella casella, dall'app", bool(box) and box[-1].get("via") == "app desktop" and not any(o in json.dumps(box[-1], ensure_ascii=False) for o in ORIGINALS),
             json.dumps({k: box[-1].get(k) for k in ("service", "via", "client", "method", "replacements")}, ensure_ascii=False) if box else "nessuna voce")
        mark("il proxy non ha dovuto rifare nulla e non ha letto male", not any(e.get("kind") == "protobuf" or "rpc_not_read" in str(e.get("event")) for e in entries))

        # 1b. la bozza: un campo che l'app tiene nella sua memoria e che parte con i segnaposto. I valori veri tornano NEL
        #     CAMPO (e quindi nella memoria dell'app); cio' che un pulsante copia dalla memoria riprende i valori veri
        field = lambda: page.evaluate("document.getElementById('draft').value")   # noqa: E731
        mark("la bozza: nel campo tornano i valori veri", wait(lambda: all(o in field() for o in ORIGINALS), 12), field()[:90])
        mark("la bozza: anche la memoria dell'app ha i valori veri", all(o in page.evaluate("window.__draft") for o in ORIGINALS))
        page.click("#copyraw")
        paper = lambda: page.evaluate("navigator.clipboard.readText()")   # noqa: E731
        mark("«Copia» dalla memoria dell'app: negli appunti i valori veri", wait(lambda: all(o in paper() for o in ORIGINALS), 6), paper()[:90])
        page.click("#draft")
        page.keyboard.press("Control+End")
        page.keyboard.press("Enter")
        page.keyboard.type("riga nuova", delay=0)
        mark("nella bozza Invio va a capo e non manda nulla", wait(lambda: "\nriga nuova" in page.evaluate("window.__draft"), 4)
             and page.evaluate("window.__sent.length") == 1)

        # 1c. un segnaposto spezzato in due pezzi di testo. Poi la pagina rifa' da capo solo il secondo pezzo, lungo: la coda
        #     del segnaposto non deve restare accanto al valore (visto dal vivo nella scheda Code: «Nevatek S.r.l.ORG_1]»)
        ph = re.search(r"\[PERSONA_\d+\]", sent).group()   # il segnaposto di Giulia Ferraresi, il primo nome del testo
        page.evaluate("""ph => {
            const p = document.createElement('p');
            p.id = 'spezzato';
            p.append(document.createTextNode('Scrive ['), document.createTextNode(ph.slice(1) + ' oggi'));
            document.getElementById('chat').append(p);
        }""", ph)
        mark("segnaposto spezzato: a schermo il valore vero", wait(lambda: page.inner_text("#spezzato") == "Scrive Giulia Ferraresi oggi", 6), page.inner_text("#spezzato"))
        page.evaluate("""ph => {
            const p = document.getElementById('spezzato');
            p.lastChild.replaceWith(document.createTextNode(ph.slice(1) + ' oggi, e poi un pezzo rifatto da capo e ben piu lungo di quaranta caratteri'));
        }""", ph)
        mark("segnaposto spezzato: se la pagina rifa' il secondo pezzo, la coda non resta a schermo",
             wait(lambda: "]" not in page.inner_text("#spezzato") and "Giulia Ferraresi oggi, e poi" in page.inner_text("#spezzato"), 6), page.inner_text("#spezzato")[:70])

        # 2. con il pulsante di invio
        page.click("#write")
        page.keyboard.type("Chiama Aldo Bruschi al 347 5551234 domani.", delay=0)
        page.click("#post")
        mark("con il pulsante: parte, e al servizio arrivano segnaposto", wait(lambda: page.evaluate("window.__sent.length") == 2)
             and not any(o in " | ".join(seen()) for o in ORIGINALS), " | ".join(seen())[:90])

        # 3. la casella saltata: la pagina manda il testo com'e'. Lo sostituisce il proxy, leggendo il protobuf
        n = len(log())
        page.evaluate("t => send(t)", TEXT)
        mark("casella saltata: il messaggio parte lo stesso", wait(lambda: page.evaluate("window.__sent.length") == 3))
        arrived = " | ".join(seen())
        mark("casella saltata: al servizio arrivano comunque solo segnaposto", bool(arrived) and not any(o in arrived for o in ORIGINALS) and "[PERSONA_" in arrived, arrived[:110])
        late = [e for e in log()[n:] if e.get("event") == "masked"]
        mark("casella saltata: nel registro lo ha sostituito il proxy", bool(late) and late[-1].get("kind") == "protobuf",
             json.dumps({k: late[-1].get(k) for k in ("via", "kind", "fields", "replacements")}, ensure_ascii=False) if late else "nessuna voce")
        mark("casella saltata: nella pagina tornano i valori veri", wait(lambda: page.inner_text("#chat").count("Giulia Ferraresi") >= 2, 10))

        # 4. la zona «Code»: il testo si sostituisce come in chat; i file allegati restano quelli scelti (li' un agente li
        #    prende dal loro percorso). Fuori da quella zona il file allegato diventa la copia anonimizzata
        note = {"name": "nota.txt", "mimeType": "text/plain", "buffer": TEXT.encode("utf-8")}
        n = len(log())
        page.click("#codebox")
        page.keyboard.type(TEXT, delay=0)
        page.keyboard.press("Enter")
        got = lambda: page.evaluate("window.__code[0] || ''")   # noqa: E731
        mark("zona Code: il testo viene sostituito nella casella", wait(lambda: page.evaluate("window.__code.length") == 1) and "[PERSONA_" in got()
             and not any(o in got() for o in ORIGINALS), got()[:60])
        mark("zona Code: nel registro la sostituzione nella casella", any(e.get("event") == "masked" and e.get("method") == "box" for e in log()[n:]))
        page.set_input_files("#codefile", note)
        mark("zona Code: il file allegato resta quello scelto", wait(lambda: page.evaluate("window.__files.length") == 1) and page.evaluate("window.__files[0]") == "nota.txt",
             str(page.evaluate("window.__files")))
        page.set_input_files("#chatfile", note)
        mark("fuori dalla zona Code: il file allegato diventa la copia anonimizzata", wait(lambda: page.evaluate("window.__chatfiles.length") == 1, 40)
             and ".anon." in page.evaluate("window.__chatfiles[0] || ''"), str(page.evaluate("window.__chatfiles")))
        other = ctx.new_page()
        other.goto(f"{FAKE}/claude-app/code", wait_until="load")
        wait(lambda: other.evaluate("globalThis.MSP_COPY === true"), 8)
        other.set_input_files("#chatfile", note)
        mark("percorso della zona Code: il file allegato resta quello scelto", wait(lambda: other.evaluate("window.__chatfiles.length") == 1)
             and other.evaluate("window.__chatfiles[0]") == "nota.txt", str(other.evaluate("window.__chatfiles")))
        other.click("#write")
        other.keyboard.type(TEXT, delay=0)
        other.keyboard.press("Enter")
        mark("percorso della zona Code: il testo della casella viene sostituito", wait(lambda: other.evaluate("window.__sent.length") == 1)
             and "Giulia Ferraresi" not in other.evaluate("window.__sent[0] || ''"), other.evaluate("window.__sent[0] || ''")[:50])
        other.close()

        # 5. Omissis chiuso da chi usa il computer: a quell'indirizzo risponde il sito vero. La finestra non resta bloccata:
        #    la prima volta il messaggio si ferma con l'avviso, ripetendo parte. Al sito non arrivano ne' chiave ne' testo
        calls = []

        def site(route):
            calls.append((route.request.headers.get("x-omissis-key"), route.request.post_data or ""))
            route.fulfill(status=404, body="non c'e'")
        page.route("**/__omissis__/**", site)
        sent = page.evaluate("window.__sent.length")
        page.click("#write")
        page.keyboard.type(TEXT, delay=0)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        mark("Omissis chiuso: la prima volta il messaggio si ferma", page.evaluate("window.__sent.length") == sent)
        page.keyboard.press("Enter")
        mark("Omissis chiuso: ripetendo, il messaggio parte com'e'", wait(lambda: page.evaluate("window.__sent.length") == sent + 1)
             and "Giulia Ferraresi" in page.evaluate("window.__sent[window.__sent.length - 1]"))
        mark("Omissis chiuso: al sito vero non arrivano la chiave né il testo", bool(calls) and not any(k or "Giulia" in b for k, b in calls), f"{len(calls)} chiamate")
        page.unroute("**/__omissis__/**")
        page.click("#write")
        page.keyboard.type("Chiama Aldo Bruschi al 347 5551234 domani.", delay=0)
        page.keyboard.press("Enter")
        mark("Omissis tornato: la casella ricomincia a sostituire", wait(lambda: page.evaluate("window.__sent.length") == sent + 2)
             and "Aldo Bruschi" not in page.evaluate("window.__sent[window.__sent.length - 1]"), page.evaluate("window.__sent[window.__sent.length - 1]")[:50])
        # Omissis fermo ma la rete passa ancora da lui (protezione in pausa): non risponde nessuno, e non parte nulla
        page.route("**/__omissis__/**", lambda route: route.abort())
        page.click("#write")
        page.keyboard.type("Chiama Aldo Bruschi.", delay=0)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1200)
        page.keyboard.press("Enter")
        page.wait_for_timeout(900)
        mark("Omissis fermo: il messaggio non parte, nemmeno ripetendo", page.evaluate("window.__sent.length") == sent + 2)
        page.unroute("**/__omissis__/**")
        page.evaluate("document.getElementById('write').innerText = ''")

        # 6. le chiamate al proxy: senza la chiave non rispondono, e non arrivano mai al servizio
        here = page.evaluate("fetch('/__omissis__/here').then(r => r.status + ' ' + r.headers.get('x-omissis'))")
        mark("«chi risponde?» non vuole la chiave", here == "200 1", here)
        code = page.evaluate("fetch('/__omissis__/call', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({m: {t: 'values', placeholder: ['[PERSONA_1]']}})}).then(r => r.status)")
        mark("una chiamata senza la chiave viene rifiutata dal proxy", code == 403, str(code))

        if "--vera" in sys.argv:
            console.clear()
            try:
                page.goto("https://claude.ai/login", wait_until="domcontentloaded", timeout=45000)
                time.sleep(4)
                title, body = page.title(), page.inner_text("body")[:300]
                if "Just a moment" in title or "Verifying you are human" in body or "challenge" in page.url:
                    print("NON PROVATO  pagina vera di claude.ai: il sito chiede una verifica a questo browser di prova (non si aggira)")
                else:
                    refused = [c for c in console if "Content Security Policy" in c or "Refused to" in c]
                    mark("pagina vera di claude.ai: il codice gira con la sua regola di sicurezza", page.evaluate("globalThis.MSP_COPY === true") and not refused,
                         (refused[0][:140] if refused else title[:60]))
            except Exception as ex:   # noqa: BLE001
                print("NON PROVATO  pagina vera di claude.ai:", type(ex).__name__, str(ex)[:120])
        browser.close()
    print(f"\n{'TUTTO OK' if all(outcomes) else 'ERRORI'}: {sum(outcomes)}/{len(outcomes)}")
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
