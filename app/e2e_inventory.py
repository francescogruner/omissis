# -*- coding: utf-8 -*-
"""Prova l'inventario degli strumenti AI nel tempo, con analisi inventate (non guarda questo PC e non ha bisogno di nulla acceso).

  python e2e_inventory.py

La prima analisi fa da punto di partenza; dalla seconda si vedono le novita' e cio' che non c'e' piu'; cio' che va e viene
da solo (programmi aperti, siti contattati) non genera «non c'e' piu'»; giudizi e note restano; pulizie ed esportazione.
"""
import os
import sys
import tempfile
import time

ok = True


def controlla(cosa, esito, nota=""):
    global ok
    ok &= bool(esito)
    print(f"{'OK    ' if esito else 'ERRORE'} {cosa}" + (f"   {nota}" if nota else ""))


def programma(nome, versione="1.0", servizio="chatgpt"):
    return {"nome": nome, "versione": versione, "origine": "programma", "servizio": {"id": servizio, "nome": nome.split()[0]}}


def analisi(programmi=(), estensioni=(), processi=(), comandi=()):
    return {"programmi": list(programmi), "processi": [{"nome": p, "istanze": 1, "servizio": {"id": "", "nome": p}} for p in processi],
            "estensioni_browser": [{"browser": "Edge", "profilo": "predefinito", "nome": n, "versione": "2.0", "id": n.lower().replace(" ", ""),
                                    "accesso_a_tutti_i_siti": tutti} for n, tutti in estensioni],
            "estensioni_editor": [], "comandi": [{"comando": c, "percorso": f"C:\\Strumenti\\{c}.exe"} for c in comandi], "locali": [], "secondi": 0.1}


sys.stdout.reconfigure(encoding="utf-8")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cartella:
    os.environ["OMISSIS_DATA"] = cartella
    import inventory   # dopo aver scelto la cartella dei dati: l'inventario di questo PC non viene toccato

    controlla("senza analisi: inventario vuoto", inventory.ultima() == "" and inventory.riepilogo()["elementi"] == [])
    r = inventory.registra(analisi([programma("Assistente Alfa")], [("Scrivi Meglio AI", True)], ["alfa.exe"], ["alfa"]), None, "manuale")
    v = inventory.riepilogo()
    controlla("prima analisi: punto di partenza, nessuna «novità»", r["prima"] and not r["nuovi"] and not v["eventi"] and len(v["elementi"]) == 4,
              f"{len(v['elementi'])} voci")
    controlla("estensione che legge tutti i siti: segnalata", any(e["segnale"] == "tutti_i_siti" for e in v["elementi"]))

    time.sleep(1.1)   # le analisi hanno l'ora al secondo
    r = inventory.registra(analisi([programma("Assistente Alfa", "1.1"), programma("Chiacchiera Beta", servizio="claude")], [("Scrivi Meglio AI", True)], [], ["alfa"]),
                           {"dns": [{"id": "deepseek", "servizio": "DeepSeek", "host": "chat.deepseek.com"}], "connessioni": []}, "automatica")
    controlla("seconda analisi: il programma nuovo e il servizio contattato sono novità", sorted(e["nome"] for e in r["nuovi"]) == ["Chiacchiera", "DeepSeek"],
              str([e["nome"] for e in r["nuovi"]]))
    controlla("un programma chiuso non è «sparito» (va e viene da solo)", not r["spariti"])
    v = inventory.riepilogo()
    alfa = next(e for e in v["elementi"] if e["nome"] == "Assistente")
    controlla("la versione si aggiorna, la data della prima volta resta", alfa["versione"] == "1.1" and alfa["primo"] < alfa["ultimo"])
    controlla("le novità restano scritte negli eventi", sorted(e["tipo"] for e in v["eventi"]) == ["comparso", "comparso"])

    beta = next(e for e in v["elementi"] if e["nome"] == "Chiacchiera")
    inventory.giudica(beta["chiave"], "da_rimuovere", "non autorizzato dall'ufficio")
    inventory.giudica(alfa["chiave"], "approvato")
    time.sleep(1.1)
    r = inventory.registra(analisi([programma("Assistente Alfa", "1.1")], [], [], ["alfa"]), None, "manuale")
    controlla("terza analisi: programma ed estensione tolti risultano «non più presenti»", sorted(e["nome"] for e in r["spariti"]) == ["Chiacchiera", "Scrivi Meglio AI"],
              str([e["nome"] for e in r["spariti"]]))
    v = inventory.riepilogo()
    beta = next(e for e in v["elementi"] if e["nome"] == "Chiacchiera")
    controlla("giudizio e nota restano anche su ciò che non c'è più", beta["giudizio"] == "da_rimuovere" and "ufficio" in beta["nota"] and not beta["presente"])
    controlla("tre analisi salvate, l'ultima per prima", v["n_analisi"] == 3 and v["analisi"][0]["origine"] == "manuale" and v["analisi"][0]["spariti"] == 2)

    testo = inventory.csv(["Cosa", "Nome", "Dettaglio", "Versione", "Prima", "Ultima", "Presente", "Giudizio", "Nota"])
    righe = testo.lstrip("\ufeff").strip().split("\r\n")
    controlla("esportazione: una riga per voce più l'intestazione", len(righe) == len(v["elementi"]) + 1 and righe[0].startswith("Cosa;Nome"), f"{len(righe)} righe")

    time.sleep(1.1)
    r = inventory.registra(analisi([programma("Assistente Alfa", "1.1"), programma("Chiacchiera Beta", servizio="claude")], [], [], ["alfa"]), None, "manuale")
    controlla("ciò che torna viene segnalato di nuovo", [e["nome"] for e in r["nuovi"]] == ["Chiacchiera"])
    tolte = inventory.dimentica()
    controlla("«dimentica ciò che non c'è più» toglie solo gli assenti", tolte >= 1 and all(e["presente"] for e in inventory.riepilogo()["elementi"]), f"{tolte} tolte")
    inventory.svuota()
    controlla("svuotato", inventory.ultima() == "" and not inventory.riepilogo()["elementi"])

print("\nTUTTO OK" if ok else "\nQUALCOSA NON VA")
sys.exit(0 if ok else 1)
