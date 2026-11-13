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
import inventory
import paths

QUI = Path(__file__).resolve().parent
PANNELLO = f"http://127.0.0.1:{paths.PORTA_PANNELLO}"
TESTO = ("Buongiorno, sono Giulia Ferraresi della Nevatek S.r.l. Il mio collega Aldo Bruschi (aldo.bruschi@nevatek.example, "
         "cell. 347 5551234) non riesce ad accedere al gestionale: potete richiamarlo oggi?")
SENSIBILI = ["Giulia Ferraresi", "Aldo Bruschi", "aldo.bruschi@nevatek.example", "347 5551234"]
VISTE = ["inizio", "testo", "documenti", "guida", "impostazioni/generali", "impostazioni/riconoscimento", "collegamenti/browser",
         "collegamenti/app", "collegamenti/terminale", "collegamenti/proxy", "collegamenti/compatibilita", "servizi/regole", "servizi/rilevati", "attivita", "archivio"]
# una chiave rimasta a schermo al posto della frase ("menu.inizio", "testo.sotto"...): si cercano quelle vere, dal file di riferimento
CHIAVI = set(json.loads((QUI / "panel" / "locales" / "it.json").read_text(encoding="utf-8")))
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


def inventario_finto():
    """Tre analisi inventate al posto di quelle di questo PC: la pagina e le schermate mostrano sempre le stesse cose."""
    if not os.environ.get("OMISSIS_DATA"):
        sys.exit("questa prova scrive un inventario inventato: va lanciata su una copia di prova (OMISSIS_DATA), non sui dati veri")
    servizio = lambda nome: next(({"id": s["id"], "nome": s["nome"]} for s in catalog.SERVIZI if s["nome"] == nome), {"id": "", "nome": nome})   # noqa: E731
    programma = lambda nome, versione, s: {"nome": nome, "versione": versione, "servizio": servizio(s)}   # noqa: E731

    def analisi(programmi, estensioni, editor, comandi, locali):
        return {"programmi": programmi, "processi": [], "secondi": 4.2, "comandi": [{"comando": c, "percorso": f"D:\\Strumenti\\npm\\{c}.cmd"} for c in comandi],
                "estensioni_browser": [{"browser": "Edge", "profilo": "predefinito", "nome": n, "versione": v, "id": n.lower().replace(" ", "-"), "accesso_a_tutti_i_siti": True}
                                       for n, v in estensioni],
                "estensioni_editor": [{"editor": "VS Code", "nome": n, "autore": a, "versione": v} for n, a, v in editor],
                "locali": [{"nome": n, "cosa": c, "gb": gb} for n, c, gb in locali]}
    inventory.svuota()
    chatgpt, claude = programma("ChatGPT", "1.2025.139", "ChatGPT"), programma("Claude", "1.1.2685", "Claude")
    passi = [analisi([chatgpt], [("Scrivi Meglio AI", "3.1")], [("GitHub Copilot", "GitHub", "1.300.0")], [], []),
             analisi([chatgpt, claude], [("Scrivi Meglio AI", "3.1")], [("GitHub Copilot", "GitHub", "1.302.0")], ["claude"], []),
             analisi([chatgpt, claude], [], [("GitHub Copilot", "GitHub", "1.302.0")], ["claude"], [("Ollama", "D:\\Modelli\\ollama", 12.4)])]
    for i, passo in enumerate(passi):
        inventory.registra(passo, None, "automatica" if i < 2 else "manuale")
        time.sleep(1.1)   # le analisi hanno l'ora al secondo


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--screenshots", dest="schermate", default=str(QUI / "screenshots"))
    a = ap.parse_args()
    foto = Path(a.schermate)
    foto.mkdir(parents=True, exist_ok=True)
    pagina_grezza = urllib.request.urlopen(PANNELLO + "/", timeout=20).read().decode("utf-8")
    codice = re.search(r'name="omissis-codice" content="([^"]+)"', pagina_grezza).group(1)
    prima = chiama(codice, "/api/settings")
    if chiama(codice, "/api/status")["fase"] != "attiva":
        sys.exit("la protezione non è attiva: avviarla prima")
    lavoro = Path(tempfile.mkdtemp(prefix="omissis_pannello_"))
    inventario_finto()

    with sync_playwright() as p:
        exe = paths.browser_di_prova()
        br = p.chromium.launch(executable_path=str(exe) if exe else None)
        ctx = br.new_context(viewport={"width": 1280, "height": 860}, permissions=["clipboard-read", "clipboard-write"], accept_downloads=True)
        pag = ctx.new_page()
        errori = []
        pag.on("console", lambda m: errori.append(m.text) if m.type == "error" else None)
        pag.on("pageerror", lambda e: errori.append(str(e)))
        try:
            for lingua in ("it", "en"):
                chiama(codice, "/api/settings", {"lingua": lingua, "tema": "chiaro", "vista": "avanzata"})
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

                # --- correzioni a mano: un segnaposto di troppo torna in chiaro, un dato sfuggito viene mascherato
                pag.click('#esito button[data-s^="[ORG_"]')
                pag.click('#suSegnaposto button[data-fai="chiaro"]')
                aspetta(pag, "() => document.getElementById('esito').textContent.includes('Nevatek S.r.l') && !document.getElementById('esito').textContent.includes('[ORG_')")
                pag.wait_for_timeout(400)
                appunti = pag.evaluate("navigator.clipboard.readText()")
                segna(f"{lingua}: correzione «lascia in chiaro» -> il testo è rifatto e ricopiato", "Nevatek S.r.l" in appunti and "[PERSONA_" in appunti and "Giulia Ferraresi" not in appunti)
                pag.fill("#daMascherare", "gestionale")
                pag.click("#mascheraAnche")
                aspetta(pag, "() => document.getElementById('esito').textContent.includes('[ELENCO_') && !document.getElementById('esito').textContent.includes('gestionale')")
                pag.wait_for_timeout(400)
                appunti = pag.evaluate("navigator.clipboard.readText()")
                segna(f"{lingua}: correzione «maschera anche questo» -> il dato sfuggito è sostituito", "[ELENCO_" in appunti and "gestionale" not in appunti and "Nevatek S.r.l" in appunti)
                pag.screenshot(path=str(foto / f"testo-correzioni-{lingua}.png"))
                pag.click('#correzioniFatte button[data-cosa="mai"]')
                tolta = aspetta(pag, "() => document.getElementById('esito').textContent.includes('[ORG_')", attesa=10)
                segna(f"{lingua}: una correzione si annulla con un clic", tolta and pag.locator("#correzioniFatte button").count() == 1)
                pag.wait_for_timeout(400)
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

                # --- cartella intera: scritto il percorso, la copia nasce accanto e si può aprire dal pannello
                pratica = lavoro / f"pratica-{lingua}"
                pratica.mkdir()
                (pratica / "nota.txt").write_text(TESTO, encoding="utf-8")
                pag.fill("#percorsoCartella", str(pratica))
                pag.click('button[data-cartella="anonimizza"]')
                fatta = aspetta(pag, "() => !!document.getElementById('apriCartella')", attesa=60)
                copia_ = lavoro / f"pratica-{lingua}.anon" / "nota.anon.txt"
                segna(f"{lingua}: cartella intera -> copia anonimizzata accanto, con il pulsante per aprirla", fatta and copia_.exists()
                      and not any(s in copia_.read_text(encoding="utf-8") for s in SENSIBILI))

                # --- archivio: si cerca per valore vero senza mostrarlo, si elimina una voce scelta
                pag.goto(f"{PANNELLO}/#/archivio")
                pag.wait_for_selector("#archCerca")
                pag.fill("#archCerca", "ferraresi")
                aspetta(pag, "() => [...document.querySelectorAll('#tabArchivio .segnaposto')].some(e => e.textContent.startsWith('[PERSONA_'))", attesa=15)
                righe = pag.evaluate("[...document.querySelectorAll('#tabArchivio tr')].map(r => r.innerText)")
                segna(f"{lingua}: archivio -> ricerca per valore vero, che resta nascosto", 1 <= len(righe) <= 30 and all("•" in r and "erraresi" not in r for r in righe), f"{len(righe)} voci")
                pag.wait_for_timeout(300)
                pag.screenshot(path=str(foto / f"archivio-{lingua}.png"))
                prima_n = chiama(codice, "/api/vault", {"cerca": "gestionale", "etichetta": "ELENCO"})["trovate"]
                pag.fill("#archCerca", "gestionale")
                aspetta(pag, "() => [...document.querySelectorAll('#tabArchivio .segnaposto')].some(e => e.textContent.startsWith('[ELENCO_'))", attesa=15)
                pag.check("#tabArchivio tr:has(.segnaposto:text-matches('ELENCO_')) input[type=checkbox]")
                pag.click("#archElimina")
                pag.click("#confermaSi")
                pag.wait_for_timeout(1200)
                dopo_n = chiama(codice, "/api/vault", {"cerca": "gestionale", "etichetta": "ELENCO"})["trovate"]
                segna(f"{lingua}: archivio -> eliminata la voce scelta, dopo la conferma", prima_n >= 1 and dopo_n == prima_n - 1, f"{prima_n} -> {dopo_n}")

                # --- inventario Shadow AI: analisi salvate, novità, giudizio, esportazione
                pag.goto(f"{PANNELLO}/#/servizi/rilevati")
                pag.wait_for_selector("#invTabella tr")
                pag.wait_for_timeout(500)
                viste = pag.locator("#invTabella tr").count()
                novita = pag.locator("#invNovita li").count()
                segna(f"{lingua}: inventario -> le analisi salvate si vedono senza rifarle, con le novità", viste == 5 and novita == 4, f"{viste} voci presenti, {novita} novità")
                pag.select_option("#invTabella tr:has-text('Ollama') select", "approvato")
                pag.fill("#invTabella tr:has-text('Ollama') input", "prova in laboratorio")
                pag.keyboard.press("Tab")
                pag.wait_for_timeout(600)
                ollama = next(e for e in chiama(codice, "/api/inventory")["elementi"] if e["nome"] == "Ollama")
                segna(f"{lingua}: inventario -> giudizio e nota salvati", ollama["giudizio"] == "approvato" and ollama["nota"] == "prova in laboratorio")
                pag.evaluate("document.activeElement.blur(); scrollTo(0, 0)")
                pag.wait_for_timeout(5500)   # gli avvisi delle prove precedenti spariscono dalla schermata
                pag.screenshot(path=str(foto / f"rilevati-{lingua}.png"))
                with pag.expect_download(timeout=30000) as d:
                    pag.click("#invEsporta")
                esportato = lavoro / f"inventario-{lingua}.csv"
                d.value.save_as(str(esportato))
                righe = esportato.read_text(encoding="utf-8-sig").strip().splitlines()
                segna(f"{lingua}: inventario -> esportazione per Excel", d.value.suggested_filename.endswith(".csv") and len(righe) == 7 and righe[0].count(";") == 8, f"{len(righe)} righe")
                inventory.giudica(ollama["chiave"], "", "")

                # --- le schermate: ciò che vede l'utente normale, poi le sezioni del tecnico
                chiama(codice, "/api/settings", {"vista": "semplice"})
                pag.goto(f"{PANNELLO}/#/inizio")
                pag.reload()
                pag.wait_for_selector("#statoTitolo")
                pag.wait_for_timeout(1200)
                pag.screenshot(path=str(foto / f"inizio-{lingua}.png"))
                pag.goto(f"{PANNELLO}/#/guida")
                pag.wait_for_timeout(600)
                pag.screenshot(path=str(foto / f"guida-{lingua}.png"))
                chiama(codice, "/api/settings", {"vista": "avanzata"})
                pag.reload()
                for vista in ("collegamenti/terminale", "servizi/regole", "impostazioni/generali"):
                    pag.goto(f"{PANNELLO}/#/{vista}")
                    pag.wait_for_selector("#pannello > *")
                    pag.wait_for_timeout(1200)
                    pag.screenshot(path=str(foto / f"{vista.split('/')[-1] if vista.startswith('coll') else vista.split('/')[0]}-{lingua}.png"))
                segna(f"{lingua}: nessun errore durante il giro completo", not errori, "; ".join(errori[:3]))
                errori.clear()

            # --- scorciatoie: la lettera scelta nella pagina arriva nelle impostazioni
            pag.goto(f"{PANNELLO}/#/impostazioni/generali")
            pag.wait_for_selector('select[data-sc="maschera"]')
            pag.select_option('select[data-sc="maschera"]', "ctrl+alt+k")
            pag.wait_for_timeout(800)
            pag.select_option('select[data-sc="ripristina"]', "")
            pag.wait_for_timeout(800)
            scelte = chiama(codice, "/api/settings")["scorciatoie"]
            segna("scorciatoie: lettera cambiata e scorciatoia spenta dalla pagina", scelte == {"sostituisci": "ctrl+alt+s", "maschera": "ctrl+alt+k", "ripristina": ""}, str(scelte))

            # --- elenchi personali da Testo e testi troppo lunghi (solo se gli elenchi sono quelli della copia di prova)
            if os.environ.get("OMISSIS_LISTS"):
                elenchi = chiama(codice, "/api/lists")
                try:
                    chiama(codice, "/api/lists/add", {"lista": "mai", "termine": "aldo.bruschi@nevatek.example"})
                    chiama(codice, "/api/lists/add", {"lista": "sempre", "termine": "gestionale"})
                    r = chiama(codice, "/api/try", {"testo": TESTO})["testi"][0]
                    segna("elenchi: «non mascherare mai» vale anche per ciò che trovano le regole, «maschera sempre» aggiunge",
                          "aldo.bruschi@nevatek.example" in r and "[ELENCO_" in r and "gestionale" not in r and "[PERSONA_" in r, r[:120])
                finally:
                    chiama(codice, "/api/lists", elenchi)
            else:
                print("SALTATO elenchi personali: senza OMISSIS_LISTS toccherebbe gli elenchi veri")
            try:
                chiama(codice, "/api/try", {"testo": "parola " * 40000})
                segna("testo troppo lungo: rifiutato, non tagliato in silenzio", False)
            except urllib.error.HTTPError as ex:
                segna("testo troppo lungo: rifiutato, non tagliato in silenzio", ex.code == 422)

            # --- l'analisi vera di questo PC, dal pulsante: viene salvata come una in più (i nomi restano su questo PC)
            pag.goto(f"{PANNELLO}/#/servizi/rilevati")
            pag.wait_for_selector("#analizza")
            salvate = chiama(codice, "/api/inventory")["n_analisi"]
            pag.click("#analizza")
            fatta = aspetta(pag, "() => !document.getElementById('analizza').disabled", attesa=180)
            dopo = chiama(codice, "/api/inventory")
            segna("inventario: «Analizza ora» fotografa il PC e salva l'analisi", fatta and dopo["n_analisi"] == salvate + 1 and dopo["analisi"][0]["origine"] == "manuale",
                  f"{dopo['analisi'][0]['secondi']} s, {dopo['analisi'][0]['elementi']} voci")
            segna("nessun errore nelle prove finali", not errori, "; ".join(errori[:3]))
            errori.clear()

            # --- tema scuro e schermo stretto
            chiama(codice, "/api/settings", {"lingua": "it", "tema": "scuro", "vista": "avanzata"})
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
            chiama(codice, "/api/settings", {k: prima[k] for k in ("lingua", "tema", "vista", "scorciatoie") if k in prima})
            inventory.svuota()
            br.close()

    print(f"\n{sum(esiti)}/{len(esiti)} controlli superati · schermate in {foto}")
    sys.exit(0 if all(esiti) else 1)


if __name__ == "__main__":
    main()
