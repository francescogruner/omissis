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

VALUES = [("PERSONA", "Giulia Ferraresi"), ("EMAIL", "giulia.ferraresi@nevatek.example"), ("TELEFONO", "347 5551234"), ("PERSONA", "Aldo Bruschi"),
          ("IBAN", "IT60X0542811101000000123456")]
ok = True


def check(what, outcome, note=""):
    global ok
    ok &= bool(outcome)
    print(f"{'OK    ' if outcome else 'ERRORE'} {what}" + (f"   {note}" if note else ""))


def reveal(folder):
    """Quanti valori si leggono nei file dell'archivio (anche in codifica a 16 bit)."""
    raw = b"".join(f.read_bytes() for f in Path(folder).iterdir() if f.is_file())
    return sum(v.encode("utf-8") in raw or v.encode("utf-16-le") in raw for _, v in VALUES)


sys.stdout.reconfigure(encoding="utf-8")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    file = Path(folder) / "vault.sqlite"
    # --- un archivio come lo scriveva la versione precedente: valori e chiavi in chiaro
    db = sqlite3.connect(file)
    db.execute("CREATE TABLE entries (label TEXT, n INTEGER, key TEXT, value TEXT, created REAL, PRIMARY KEY (label, n))")
    db.execute("CREATE UNIQUE INDEX by_key ON entries (label, key)")
    count = {}
    for label, value in VALUES[:4]:
        count[label] = count.get(label, 0) + 1
        db.execute("INSERT INTO entries VALUES (?, ?, ?, ?, ?)", (label, count[label], re.sub(r"\s+", " ", value).strip().casefold(), value, time.time()))
    db.commit()
    db.close()
    check("archivio di partenza: i valori si leggono nel file", reveal(folder) == 4)

    a = engine.Vault(file)
    check("la cifratura è attiva", a.seal.is_active)
    check("conversione alla prima apertura", a.converted_ones == 4, f"{a.converted_ones} voci")
    check("i segnaposto restano gli stessi", a.placeholder("PERSONA", "Giulia Ferraresi") == "[PERSONA_1]" and a.placeholder("PERSONA", "aldo  BRUSCHI") == "[PERSONA_2]"
              and a.placeholder("EMAIL", "giulia.ferraresi@nevatek.example") == "[EMAIL_1]")
    check("i valori si rileggono", a.value("[PERSONA_1]") == "Giulia Ferraresi" and a.value("[TELEFONO_1]") == "347 5551234" and a.value("[PERSONA_99]") is None)
    check("un valore nuovo prende il numero successivo", a.placeholder("IBAN", VALUES[4][1]) == "[IBAN_1]" and a.placeholder("PERSONA", "Marta Colonna") == "[PERSONA_3]")
    listing = a.listing(reveal=True)
    check("elenco per il pannello", listing["encrypted"] and {v["value"] for v in listing["entries"]} >= {"Giulia Ferraresi", "Marta Colonna"}
              and all("•" in v["value"] or len(v["value"]) < 2 for v in a.listing()["entries"]))
    a.db.close()
    check("nel file non si legge più alcun valore", reveal(folder) == 0, f"leggibili {reveal(folder)}")

    b = engine.Vault(file)
    check("riapertura: nulla da convertire, stessi segnaposto e valori", b.converted_ones == 0 and b.value("[IBAN_1]") == VALUES[4][1]
              and b.placeholder("PERSONA", "Marta Colonna") == "[PERSONA_3]" and b.entries() == 6)
    t0 = time.perf_counter()
    for i in range(300):
        b.placeholder("ID_PRATICA", f"PRT-{i:05}")
    ms = (time.perf_counter() - t0) * 1000 / 300
    check("tempo per ogni valore nuovo", ms < 20, f"{ms:.2f} ms")
    # --- ricerca: per segnaposto e per valore vero, anche quando i valori restano nascosti
    r = b.listing(search="ferraresi")
    check("ricerca per valore, senza mostrarlo", r["matches"] == 2 and {v["placeholder"] for v in r["entries"]} == {"[PERSONA_1]", "[EMAIL_1]"}
              and all("•" in v["value"] for v in r["entries"]), f"{r['matches']} trovate di {r['total']}")
    r = b.listing(search="[iban_", reveal=True)
    check("ricerca per segnaposto e filtro per tipo", [v["value"] for v in r["entries"]] == [VALUES[4][1]] and b.listing(label="PERSONA")["matches"] == 3)
    check("limite: poche voci mostrate, il conto è di tutte", len(b.listing(limit=10)["entries"]) == 10 and b.listing(limit=10)["matches"] == 306)
    # --- ultimo uso: una voce vecchia mai più usata, e una vecchia usata adesso
    b.db.execute("UPDATE entries SET created = created - 86400 * 200, used = used - 86400 * 200 WHERE label IN ('PERSONA', 'TELEFONO')")
    b.db.commit()
    b.value("[PERSONA_1]")           # ripristinata adesso: non è più «ferma»
    b.placeholder("PERSONA", "Aldo Bruschi")   # rivista in un testo adesso
    count = b.remove(idle_days=90, count_only=True)
    check("pulizia: prima dice quante, senza toccare nulla", count["removed"] == 2 and b.entries() == 306, f"{count['removed']} ferme da più di 90 giorni")
    done = b.remove(idle_days=90)
    check("pulizia: tolte solo le voci non usate da tempo", done["removed"] == 2 and b.value("[PERSONA_3]") is None and b.value("[TELEFONO_1]") is None
              and b.value("[PERSONA_1]") == "Giulia Ferraresi" and b.value("[PERSONA_2]") == "Aldo Bruschi")
    check("un numero eliminato non viene riusato", b.placeholder("PERSONA", "Nuova Persona") == "[PERSONA_4]" and b.placeholder("PERSONA", "Marta Colonna") == "[PERSONA_5]")
    done = b.remove(placeholder=["[EMAIL_1]", "[NON_ESISTE_9]"])
    check("eliminazione di una voce scelta", done["removed"] == 1 and b.value("[EMAIL_1]") is None and b.remove()["removed"] == 0)
    check("eliminazione per tipo", b.remove(label="ID_PRATICA")["removed"] == 300 and b.entries() == 5, f"restano {b.entries()}")
    b.clear()
    check("svuotato", b.entries() == 0 and b.value("[PERSONA_1]") is None)
    check("anche dopo lo svuotamento i numeri non ripartono da 1", b.placeholder("PERSONA", "Dopo Lo Svuotamento") == "[PERSONA_6]")
    # --- valori in sospeso: chi maschera un testo scrive sul disco una volta sola, prima di rispondere
    t0 = time.perf_counter()
    for i in range(300):
        b.placeholder("ID_PRATICA", f"SOS-{i:05}", commit=False)
    ms = (time.perf_counter() - t0) * 1000 / 300
    other = sqlite3.connect(file)
    before = other.execute("SELECT COUNT(*) FROM entries WHERE label = 'ID_PRATICA'").fetchone()[0]
    b.flush()
    after = other.execute("SELECT COUNT(*) FROM entries WHERE label = 'ID_PRATICA'").fetchone()[0]
    other.close()
    check("valori in sospeso: sul disco dopo una sola scrittura, e prima non ci sono", before == 0 and after == 300 and not b.pending
              and b.value("[ID_PRATICA_301]") == "SOS-00000", f"{ms:.2f} ms per valore · prima {before}, dopo {after}")
    b.db.close()
print("\nTUTTO OK" if ok else "\nERRORI")
sys.exit(0 if ok else 1)
