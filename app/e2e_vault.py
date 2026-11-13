# -*- coding: utf-8 -*-
"""Prova l'archivio cifrato, senza bisogno del modello: conversione di un archivio scritto in chiaro da una
versione precedente, segnaposto stabili prima e dopo, nessun valore leggibile nel file, riapertura.

  python e2e_vault.py
"""
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import engine

VALORI = [("PERSONA", "Giulia Ferraresi"), ("EMAIL", "giulia.ferraresi@nevatek.example"), ("TELEFONO", "347 5551234"), ("PERSONA", "Aldo Bruschi"),
          ("IBAN", "IT60X0542811101000000123456")]
ok = True


def controlla(cosa, esito, nota=""):
    global ok
    ok &= bool(esito)
    print(f"{'OK    ' if esito else 'ERRORE'} {cosa}" + (f"   {nota}" if nota else ""))


def in_chiaro(cartella):
    """Quanti valori si leggono nei file dell'archivio (anche in codifica a 16 bit)."""
    grezzo = b"".join(f.read_bytes() for f in Path(cartella).iterdir() if f.is_file())
    return sum(v.encode("utf-8") in grezzo or v.encode("utf-16-le") in grezzo for _, v in VALORI)


sys.stdout.reconfigure(encoding="utf-8")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cartella:
    file = Path(cartella) / "vault.sqlite"
    # --- un archivio come lo scriveva la versione precedente: valori e chiavi in chiaro
    db = sqlite3.connect(file)
    db.execute("CREATE TABLE voci (etichetta TEXT, n INTEGER, chiave TEXT, valore TEXT, creato REAL, PRIMARY KEY (etichetta, n))")
    db.execute("CREATE UNIQUE INDEX per_chiave ON voci (etichetta, chiave)")
    conta = {}
    for etichetta, valore in VALORI[:4]:
        conta[etichetta] = conta.get(etichetta, 0) + 1
        db.execute("INSERT INTO voci VALUES (?, ?, ?, ?, ?)", (etichetta, conta[etichetta], re.sub(r"\s+", " ", valore).strip().casefold(), valore, time.time()))
    db.commit()
    db.close()
    controlla("archivio di partenza: i valori si leggono nel file", in_chiaro(cartella) == 4)

    a = engine.Archivio(file)
    controlla("la cifratura è attiva", a.sigillo.attivo)
    controlla("conversione alla prima apertura", a.convertiti == 4, f"{a.convertiti} voci")
    controlla("i segnaposto restano gli stessi", a.segnaposto("PERSONA", "Giulia Ferraresi") == "[PERSONA_1]" and a.segnaposto("PERSONA", "aldo  BRUSCHI") == "[PERSONA_2]"
              and a.segnaposto("EMAIL", "giulia.ferraresi@nevatek.example") == "[EMAIL_1]")
    controlla("i valori si rileggono", a.valore("[PERSONA_1]") == "Giulia Ferraresi" and a.valore("[TELEFONO_1]") == "347 5551234" and a.valore("[PERSONA_99]") is None)
    controlla("un valore nuovo prende il numero successivo", a.segnaposto("IBAN", VALORI[4][1]) == "[IBAN_1]" and a.segnaposto("PERSONA", "Marta Colonna") == "[PERSONA_3]")
    elenco = a.elenco(in_chiaro=True)
    controlla("elenco per il pannello", elenco["cifrato"] and {v["valore"] for v in elenco["voci"]} >= {"Giulia Ferraresi", "Marta Colonna"}
              and all("•" in v["valore"] or len(v["valore"]) < 2 for v in a.elenco()["voci"]))
    a.db.close()
    controlla("nel file non si legge più alcun valore", in_chiaro(cartella) == 0, f"leggibili {in_chiaro(cartella)}")

    b = engine.Archivio(file)
    controlla("riapertura: nulla da convertire, stessi segnaposto e valori", b.convertiti == 0 and b.valore("[IBAN_1]") == VALORI[4][1]
              and b.segnaposto("PERSONA", "Marta Colonna") == "[PERSONA_3]" and b.voci() == 6)
    t0 = time.perf_counter()
    for i in range(300):
        b.segnaposto("ID_PRATICA", f"PRT-{i:05}")
    ms = (time.perf_counter() - t0) * 1000 / 300
    controlla("tempo per ogni valore nuovo", ms < 20, f"{ms:.2f} ms")
    # --- ricerca: per segnaposto e per valore vero, anche quando i valori restano nascosti
    r = b.elenco(cerca="ferraresi")
    controlla("ricerca per valore, senza mostrarlo", r["trovate"] == 2 and {v["segnaposto"] for v in r["voci"]} == {"[PERSONA_1]", "[EMAIL_1]"}
              and all("•" in v["valore"] for v in r["voci"]), f"{r['trovate']} trovate di {r['totale']}")
    r = b.elenco(cerca="[iban_", in_chiaro=True)
    controlla("ricerca per segnaposto e filtro per tipo", [v["valore"] for v in r["voci"]] == [VALORI[4][1]] and b.elenco(etichetta="PERSONA")["trovate"] == 3)
    controlla("limite: poche voci mostrate, il conto è di tutte", len(b.elenco(limite=10)["voci"]) == 10 and b.elenco(limite=10)["trovate"] == 306)
    # --- ultimo uso: una voce vecchia mai più usata, e una vecchia usata adesso
    b.db.execute("UPDATE voci SET creato = creato - 86400 * 200, usato = usato - 86400 * 200 WHERE etichetta IN ('PERSONA', 'TELEFONO')")
    b.db.commit()
    b.valore("[PERSONA_1]")           # ripristinata adesso: non è più «ferma»
    b.segnaposto("PERSONA", "Aldo Bruschi")   # rivista in un testo adesso
    conta = b.elimina(fermi_da_giorni=90, solo_conta=True)
    controlla("pulizia: prima dice quante, senza toccare nulla", conta["eliminate"] == 2 and b.voci() == 306, f"{conta['eliminate']} ferme da più di 90 giorni")
    fatto = b.elimina(fermi_da_giorni=90)
    controlla("pulizia: tolte solo le voci non usate da tempo", fatto["eliminate"] == 2 and b.valore("[PERSONA_3]") is None and b.valore("[TELEFONO_1]") is None
              and b.valore("[PERSONA_1]") == "Giulia Ferraresi" and b.valore("[PERSONA_2]") == "Aldo Bruschi")
    controlla("un numero eliminato non viene riusato", b.segnaposto("PERSONA", "Nuova Persona") == "[PERSONA_4]" and b.segnaposto("PERSONA", "Marta Colonna") == "[PERSONA_5]")
    fatto = b.elimina(segnaposto=["[EMAIL_1]", "[NON_ESISTE_9]"])
    controlla("eliminazione di una voce scelta", fatto["eliminate"] == 1 and b.valore("[EMAIL_1]") is None and b.elimina()["eliminate"] == 0)
    controlla("eliminazione per tipo", b.elimina(etichetta="ID_PRATICA")["eliminate"] == 300 and b.voci() == 5, f"restano {b.voci()}")
    b.svuota()
    controlla("svuotato", b.voci() == 0 and b.valore("[PERSONA_1]") is None)
    controlla("anche dopo lo svuotamento i numeri non ripartono da 1", b.segnaposto("PERSONA", "Dopo Lo Svuotamento") == "[PERSONA_6]")
    b.db.close()
print("\nTUTTO OK" if ok else "\nERRORI")
sys.exit(0 if ok else 1)
