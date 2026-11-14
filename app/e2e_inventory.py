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


def check(what, outcome, note=""):
    global ok
    ok &= bool(outcome)
    print(f"{'OK    ' if outcome else 'ERRORE'} {what}" + (f"   {note}" if note else ""))


def program(name, version="1.0", service="chatgpt"):
    return {"name": name, "version": version, "origin": "program", "service": {"id": service, "name": name.split()[0]}}


def scan(programs=(), extensions=(), processes=(), commands=()):
    return {"programs": list(programs), "processes": [{"name": p, "instances": 1, "service": {"id": "", "name": p}} for p in processes],
            "browser_extensions": [{"browser": "Edge", "profile": "default", "name": n, "version": "2.0", "id": n.lower().replace(" ", ""),
                                    "all_sites_access": everyone} for n, everyone in extensions],
            "editor_extensions": [], "commands": [{"command": c, "path": f"C:\\Strumenti\\{c}.exe"} for c in commands], "local": [], "seconds": 0.1}


sys.stdout.reconfigure(encoding="utf-8")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    os.environ["OMISSIS_DATA"] = folder
    import inventory   # dopo aver scelto la cartella dei dati: l'inventario di questo PC non viene toccato

    check("senza analisi: inventario vuoto", inventory.latest() == "" and inventory.summary()["items"] == [])
    r = inventory.record(scan([program("Assistente Alfa")], [("Scrivi Meglio AI", True)], ["alfa.exe"], ["alpha"]), None, "manual")
    v = inventory.summary()
    check("prima analisi: punto di partenza, nessuna «novità»", r["before"] and not r["new_items"] and not v["events"] and len(v["items"]) == 4,
              f"{len(v['items'])} voci")
    check("estensione che legge tutti i siti: segnalata", any(e["signal"] == "all_sites" for e in v["items"]))

    time.sleep(1.1)   # le analisi hanno l'ora al secondo
    r = inventory.record(scan([program("Assistente Alfa", "1.1"), program("Chiacchiera Beta", service="claude")], [("Scrivi Meglio AI", True)], [], ["alpha"]),
                           {"dns": [{"id": "deepseek", "service": "DeepSeek", "host": "chat.deepseek.com"}], "links": []}, "automatic")
    check("seconda analisi: il programma nuovo e il servizio contattato sono novità", sorted(e["name"] for e in r["new_items"]) == ["Chiacchiera", "DeepSeek"],
              str([e["name"] for e in r["new_items"]]))
    check("un programma chiuso non è «sparito» (va e viene da solo)", not r["gone"])
    v = inventory.summary()
    alpha = next(e for e in v["items"] if e["name"] == "Assistente")
    check("la versione si aggiorna, la data della prima volta resta", alpha["version"] == "1.1" and alpha["first"] < alpha["last"])
    check("le novità restano scritte negli eventi", sorted(e["kind"] for e in v["events"]) == ["appeared", "appeared"])

    beta = next(e for e in v["items"] if e["name"] == "Chiacchiera")
    inventory.judge(beta["key"], "to_remove", "non autorizzato dall'ufficio")
    inventory.judge(alpha["key"], "approved")
    time.sleep(1.1)
    r = inventory.record(scan([program("Assistente Alfa", "1.1")], [], [], ["alpha"]), None, "manual")
    check("terza analisi: programma ed estensione tolti risultano «non più presenti»", sorted(e["name"] for e in r["gone"]) == ["Chiacchiera", "Scrivi Meglio AI"],
              str([e["name"] for e in r["gone"]]))
    v = inventory.summary()
    beta = next(e for e in v["items"] if e["name"] == "Chiacchiera")
    check("giudizio e nota restano anche su ciò che non c'è più", beta["verdict"] == "to_remove" and "ufficio" in beta["note"] and not beta["present"])
    check("tre analisi salvate, l'ultima per prima", v["scan_count"] == 3 and v["scan"][0]["origin"] == "manual" and v["scan"][0]["gone"] == 2)

    text = inventory.csv(["Cosa", "Nome", "Dettaglio", "Versione", "Prima", "Ultima", "Presente", "Giudizio", "Nota"])
    lines = text.lstrip("\ufeff").strip().split("\r\n")
    check("esportazione: una riga per voce più l'intestazione", len(lines) == len(v["items"]) + 1 and lines[0].startswith("Cosa;Nome"), f"{len(lines)} righe")

    time.sleep(1.1)
    r = inventory.record(scan([program("Assistente Alfa", "1.1"), program("Chiacchiera Beta", service="claude")], [], [], ["alpha"]), None, "manual")
    check("ciò che torna viene segnalato di nuovo", [e["name"] for e in r["new_items"]] == ["Chiacchiera"])
    dropped = inventory.forget()
    check("«dimentica ciò che non c'è più» toglie solo gli assenti", dropped >= 1 and all(e["present"] for e in inventory.summary()["items"]), f"{dropped} tolte")
    inventory.clear()
    check("svuotato", inventory.latest() == "" and not inventory.summary()["items"])

print("\nTUTTO OK" if ok else "\nQUALCOSA NON VA")
sys.exit(0 if ok else 1)
