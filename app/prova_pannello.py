# -*- coding: utf-8 -*-
"""Prova il pannello in un browser vero (il Chromium di Playwright) e ne scatta le schermate.

  .venv\\Scripts\\python.exe prova_pannello.py [--schermate <cartella>]

Serve la protezione attiva (pannello.py). In italiano e in inglese apre ogni sezione e controlla che:
non ci siano errori nella pagina, nessuna frase resti senza traduzione, ogni pulsante e ogni campo
abbia un nome leggibile da chi usa uno schermo parlante, la pagina dichiari la lingua giusta e si
possa usare tutta dalla tastiera. Poi il giro completo della parte manuale, con dati inventati:
  testo      incolla -> mascherato e copiato da solo -> incolla di nuovo -> tornano i valori veri
  documento  file trascinato -> copia anonimizzata scaricata da sola -> rimessa dentro -> ripristinata
Alla fine rimette lingua, tema e modalità com'erano. Le schermate (dati inventati) servono al sito
e ai documenti.
"""
import argparse
import json
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

import percorsi

QUI = Path(__file__).resolve().parent
PANNELLO = f"http://127.0.0.1:{percorsi.PORTA_PANNELLO}"
TESTO = ("Buongiorno, sono Giulia Ferraresi della Nevatek S.r.l. Il mio collega Aldo Bruschi (aldo.bruschi@nevatek.example, "
         "cell. 347 5551234) non riesce ad accedere al gestionale: potete richiamarlo oggi?")
SENSIBILI = ["Giulia Ferraresi", "Aldo Bruschi", "aldo.bruschi@nevatek.example", "347 5551234"]
VISTE = ["inizio", "testo", "documenti", "guida", "impostazioni/generali", "impostazioni/riconoscimento", "collegamenti/browser",
         "collegamenti/app", "collegamenti/terminale", "collegamenti/proxy", "servizi/regole", "servizi/rilevati", "attivita", "archivio"]
# una chiave rimasta a schermo al posto della frase ("menu.inizio", "testo.sotto"...): si cercano quelle vere, dal file di riferimento
CHIAVI = set(json.loads((QUI / "pannello" / "lingue" / "it.json").read_text(encoding="utf-8")))
RX_CHIAVE = re.compile(r"[a-z_]+(?:\.[a-z_0-9]+)+")
SENZA_NOME = """() => [...document.querySelectorAll('button, a[href], input, select, textarea, [role=tab], [role=switch]')]
  .filter(e => e.offsetParent !== null || e.classList.contains('vh') || e.closest('.levetta'))
  .filter(e => !(e.getAttribute('aria-label') || e.getAttribute('aria-labelledby') || (e.labels && e.labels.length) || e.textContent.trim() || e.placeholder))
  .map(e => e.outerHTML.slice(0, 90))"""
esiti = []


def segna(nome, ok, nota=""):
    esiti.append(bool(ok))
    print(("OK   " if ok else "NO   ") + nome + (f"  ({nota})" if nota else ""))


def aspetta(pag, espressione, arg=None, attesa=30):
    """Attende che un'espressione diventi vera nella pagina. Non si usa wait_for_function: valuta il testo con eval, che la
    pagina vieta apposta (niente codice che non venga dai suoi file)."""
    fine = time.time() + attesa
    while time.time() < fine:
        if pag.evaluate(espressione, arg):
            return True
        pag.wait_for_timeout(150)
    return False


def chiama(codice, percorso, dati=None):
    r = urllib.request.Request(PANNELLO + percorso, headers={"X-Pannello": codice, "Content-Type": "application/json"},
                               data=json.dumps(dati).encode("utf-8") if dati is not None else None)
    with urllib.request.urlopen(r, timeout=60) as x:
        return json.loads(x.read().decode("utf-8"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--schermate", default=str(QUI / "schermate"))
    a = ap.parse_args()
    foto = Path(a.schermate)
    foto.mkdir(parents=True, exist_ok=True)
    pagina_grezza = urllib.request.urlopen(PANNELLO + "/", timeout=20).read().decode("utf-8")
    codice = re.search(r'name="omissis-codice" content="([^"]+)"', pagina_grezza).group(1)
    prima = chiama(codice, "/api/impostazioni")
    if chiama(codice, "/api/stato")["fase"] != "attiva":
        sys.exit("la protezione non è attiva: avviarla prima")
    lavoro = Path(tempfile.mkdtemp(prefix="omissis_pannello_"))

    with sync_playwright() as p:
        exe = percorsi.browser_di_prova()
        br = p.chromium.launch(executable_path=str(exe) if exe else None)
        ctx = br.new_context(viewport={"width": 1280, "height": 860}, permissions=["clipboard-read", "clipboard-write"], accept_downloads=True)
        pag = ctx.new_page()
        errori = []
        pag.on("console", lambda m: errori.append(m.text) if m.type == "error" else None)
        pag.on("pageerror", lambda e: errori.append(str(e)))
        try:
            for lingua in ("it", "en"):
                chiama(codice, "/api/impostazioni", {"lingua": lingua, "tema": "chiaro", "vista": "avanzata"})
                pag.goto(PANNELLO + "/#/inizio")
                pag.reload()
                pag.wait_for_selector("#menu a")
                segna(f"{lingua}: la pagina dichiara la sua lingua", pag.evaluate("document.documentElement.lang") == lingua)
                rimaste, anonimi, senza_titolo = set(), [], []
                for vista in VISTE:
                    pag.goto(f"{PANNELLO}/#/{vista}")
                    pag.wait_for_selector("#pannello > *")
                    pag.wait_for_timeout(700)
                    rimaste |= set(RX_CHIAVE.findall(pag.inner_text("body"))) & CHIAVI
                    anonimi += [f"{vista}: {x}" for x in pag.evaluate(SENZA_NOME)]
                    if pag.locator("main h1").count() != 1 or not pag.title().endswith("· Omissis"):
                        senza_titolo.append(vista)
                segna(f"{lingua}: {len(VISTE)} pagine aperte senza errori", not errori, "; ".join(errori[:3]))
                segna(f"{lingua}: nessuna frase senza traduzione", not rimaste, ", ".join(sorted(rimaste)[:6]))
                segna(f"{lingua}: ogni pulsante e ogni campo ha un nome", not anonimi, " | ".join(anonimi[:3]))
                segna(f"{lingua}: ogni pagina ha un titolo solo e il titolo della scheda", not senza_titolo, ", ".join(senza_titolo))
                errori.clear()

                # --- dalla tastiera: il primo Tab porta al collegamento "vai al contenuto", le linguette si scorrono con le frecce
                pag.goto(f"{PANNELLO}/#/collegamenti/browser")
                pag.wait_for_selector("[role=tab]")
                pag.reload()
                pag.wait_for_selector("[role=tab]")
                pag.keyboard.press("Tab")
                salto = pag.evaluate("document.activeElement.id")
                pag.focus("#linguetta-browser")
                pag.keyboard.press("ArrowRight")
                passata = aspetta(pag, "() => location.hash.endsWith('/app') && document.getElementById('linguetta-app')?.getAttribute('aria-selected') === 'true'", attesa=5)
                segna(f"{lingua}: si usa dalla tastiera (salto al contenuto, linguette con le frecce)", salto == "salta" and passata, f"primo Tab su «{salto}» · freccia {passata}")

                # --- testo: incolla -> mascherato e copiato; incolla di nuovo -> valori veri
                pag.goto(f"{PANNELLO}/#/testo")
                pag.wait_for_selector("#incolla")
                pag.evaluate("t => navigator.clipboard.writeText(t)", TESTO)
                pag.click("#incolla")
                aspetta(pag, "() => document.getElementById('esito').textContent.includes('[PERSONA_')")
                pag.wait_for_timeout(500)
                appunti = pag.evaluate("navigator.clipboard.readText()")
                segna(f"{lingua}: testo incollato -> mascherato e copiato da solo", "[PERSONA_" in appunti and not any(s in appunti for s in SENSIBILI),
                      f"in chiaro negli appunti: {sum(s in appunti for s in SENSIBILI)}")
                pag.wait_for_timeout(600)
                pag.screenshot(path=str(foto / f"testo-{lingua}.png"))
                pag.click("#incolla")
                aspetta(pag, "t => document.getElementById('esito').textContent === t", TESTO)
                pag.wait_for_timeout(500)
                segna(f"{lingua}: risposta incollata -> tornano i valori veri, già negli appunti", pag.evaluate("navigator.clipboard.readText()") == TESTO)

                # --- documento: trascinato -> anonimizzato e scaricato da solo; rimesso dentro -> ripristinato
                originale = lavoro / f"lettera-{lingua}.txt"
                originale.write_text(TESTO, encoding="utf-8")
                pag.goto(f"{PANNELLO}/#/documenti")
                pag.wait_for_selector("#scegli", state="attached")
                with pag.expect_download(timeout=60000) as d:
                    pag.set_input_files("#scegli", str(originale))
                anonimo = lavoro / d.value.suggested_filename
                d.value.save_as(str(anonimo))
                letto = anonimo.read_text(encoding="utf-8")
                segna(f"{lingua}: documento -> copia anonimizzata scaricata da sola", ".anon" in anonimo.name and "[PERSONA_" in letto
                      and not any(s in letto for s in SENSIBILI), anonimo.name)
                pag.wait_for_timeout(400)
                pag.screenshot(path=str(foto / f"documenti-{lingua}.png"))
                with pag.expect_download(timeout=60000) as d:
                    pag.set_input_files("#scegli", str(anonimo))
                tornato = lavoro / d.value.suggested_filename
                d.value.save_as(str(tornato))
                segna(f"{lingua}: documento con i segnaposto -> riconosciuto e ripristinato", ".ripristinato" in tornato.name
                      and tornato.read_text(encoding="utf-8") == TESTO, tornato.name)

                # --- le schermate: ciò che vede l'utente normale, poi le sezioni del tecnico
                chiama(codice, "/api/impostazioni", {"vista": "semplice"})
                pag.goto(f"{PANNELLO}/#/inizio")
                pag.reload()
                pag.wait_for_selector("#statoTitolo")
                pag.wait_for_timeout(1200)
                pag.screenshot(path=str(foto / f"inizio-{lingua}.png"))
                pag.goto(f"{PANNELLO}/#/guida")
                pag.wait_for_timeout(600)
                pag.screenshot(path=str(foto / f"guida-{lingua}.png"))
                chiama(codice, "/api/impostazioni", {"vista": "avanzata"})
                pag.reload()
                for vista in ("collegamenti/terminale", "servizi/regole", "impostazioni/generali"):
                    pag.goto(f"{PANNELLO}/#/{vista}")
                    pag.wait_for_selector("#pannello > *")
                    pag.wait_for_timeout(1200)
                    pag.screenshot(path=str(foto / f"{vista.split('/')[-1] if vista.startswith('coll') else vista.split('/')[0]}-{lingua}.png"))
                segna(f"{lingua}: nessun errore durante il giro completo", not errori, "; ".join(errori[:3]))
                errori.clear()

            # --- tema scuro e schermo stretto
            chiama(codice, "/api/impostazioni", {"lingua": "it", "tema": "scuro", "vista": "avanzata"})
            pag.goto(f"{PANNELLO}/#/inizio")
            pag.reload()
            pag.wait_for_selector("#statoTitolo")
            pag.wait_for_timeout(1200)
            pag.screenshot(path=str(foto / "inizio-scuro.png"))
            scuro = pag.evaluate("getComputedStyle(document.body).backgroundColor")
            pag.set_viewport_size({"width": 390, "height": 800})
            pag.wait_for_timeout(500)
            largo = pag.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            pag.screenshot(path=str(foto / "inizio-telefono.png"))
            segna("tema scuro applicato, e su uno schermo stretto la pagina non esce dai bordi", scuro == "rgb(10, 10, 10)" and largo, f"{scuro} · {largo}")
        finally:
            chiama(codice, "/api/impostazioni", {k: prima[k] for k in ("lingua", "tema", "vista") if k in prima})
            br.close()

    print(f"\n{sum(esiti)}/{len(esiti)} controlli superati · schermate in {foto}")
    sys.exit(0 if all(esiti) else 1)


if __name__ == "__main__":
    main()
