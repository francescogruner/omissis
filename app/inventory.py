# -*- coding: utf-8 -*-
"""Inventario degli strumenti AI trovati su questo PC (Shadow AI), tenuto nel tempo.

scan.py fotografa il PC; qui ogni fotografia viene salvata e confrontata con la precedente, cosi' si vede cosa e'
comparso, cosa e' sparito e da quando una cosa c'e'. Per ogni voce chi gestisce il PC puo' annotare un giudizio
(approvato, da rimuovere) e una nota. Tutto resta in data\\inventory.sqlite: nomi di programmi ed estensioni,
versioni e date; nessun contenuto, nessuna cronologia di navigazione.

  registra(pc, rete, origine)   salva un'analisi e restituisce le novita'
  riepilogo()                   cio' che serve al pannello
  giudica(chiave, giudizio, nota), dimentica(), svuota(), csv()
"""
import csv as _csv
import io
import sqlite3
import threading
import time

import paths

FILE = paths.DATI / "inventory.sqlite"
GIUDIZI = ("", "approvato", "da_rimuovere")
# cio' che va e viene da solo (un programma aperto o chiuso, un sito contattato): se ne annota la comparsa, non la scomparsa
VOLATILI = {"processi", "in_ascolto", "contattati"}
EVENTI_GIORNI = 365
_lucchetto = threading.Lock()


def _db():
    FILE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(FILE)
    db.execute("CREATE TABLE IF NOT EXISTS analisi (ora TEXT PRIMARY KEY, origine TEXT, secondi REAL, elementi INTEGER, nuovi INTEGER, spariti INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS elementi (chiave TEXT PRIMARY KEY, categoria TEXT, nome TEXT, dettaglio TEXT, versione TEXT, "
               "servizio TEXT, segnale TEXT, primo TEXT, ultimo TEXT, presente INTEGER, giudizio TEXT DEFAULT '', nota TEXT DEFAULT '')")
    db.execute("CREATE TABLE IF NOT EXISTS eventi (id INTEGER PRIMARY KEY AUTOINCREMENT, ora TEXT, tipo TEXT, chiave TEXT, categoria TEXT, "
               "nome TEXT, dettaglio TEXT)")
    return db


def elementi_di(pc, rete=None):
    """La fotografia di scan.pc() e scan.rete() come elenco piatto: una voce per ogni cosa trovata, con una chiave stabile."""
    out = {}

    def voce(categoria, chiave, nome, dettaglio="", versione="", servizio="", segnale=""):
        out[f"{categoria}|{chiave}"] = {"categoria": categoria, "nome": str(nome)[:200], "dettaglio": str(dettaglio)[:300],
                                        "versione": str(versione)[:60], "servizio": str(servizio or ""), "segnale": segnale}
    for r in pc.get("programmi", []):
        voce("programmi", r["nome"], r["servizio"]["nome"], r["nome"], r.get("versione", ""), r["servizio"].get("id"))
    for r in pc.get("processi", []):
        voce("processi", r["nome"].lower(), r["servizio"]["nome"], r["nome"], "", r["servizio"].get("id"))
    for r in pc.get("estensioni_browser", []):
        voce("estensioni_browser", f"{r['browser']}|{r['profilo']}|{r['id']}", r["nome"], f"{r['browser']} · {r['profilo']}", r.get("versione", ""),
             segnale="tutti_i_siti" if r.get("accesso_a_tutti_i_siti") else "")
    for r in pc.get("estensioni_editor", []):
        voce("estensioni_editor", f"{r['editor']}|{r['autore']}|{r['nome']}", r["nome"], f"{r['editor']} · {r['autore']}", r.get("versione", ""))
    for r in pc.get("comandi", []):
        voce("comandi", r["comando"], r["comando"], r["percorso"])
    for r in pc.get("locali", []):
        if r.get("gb") is None:
            voce("in_ascolto", f"{r['nome']}|{r.get('porta', '')}", r["nome"], f"127.0.0.1:{r.get('porta', '')}")
        else:
            voce("modelli_locali", r["nome"], r["nome"], r["cosa"], f"{r['gb']} GB")
    for r in (rete or {}).get("dns", []) + (rete or {}).get("connessioni", []):
        voce("contattati", r["id"], r["servizio"], r.get("host", ""), "", r["id"])
    return out


def registra(pc, rete=None, origine="manuale"):
    """Salva l'analisi. Restituisce {"prima": bool, "nuovi": [...], "spariti": [...]} rispetto a quella di prima."""
    ora, trovati = time.strftime("%Y-%m-%d %H:%M:%S"), elementi_di(pc, rete)
    with _lucchetto:
        db = _db()
        prima = db.execute("SELECT COUNT(*) FROM analisi").fetchone()[0] == 0
        noti = {r[0]: {"categoria": r[1], "nome": r[2], "dettaglio": r[3], "presente": r[4]}
                for r in db.execute("SELECT chiave, categoria, nome, dettaglio, presente FROM elementi")}
        nuovi, spariti = [], []
        for chiave, v in trovati.items():
            n = noti.get(chiave)
            if n is None:
                db.execute("INSERT INTO elementi (chiave, categoria, nome, dettaglio, versione, servizio, segnale, primo, ultimo, presente) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)", (chiave, v["categoria"], v["nome"], v["dettaglio"], v["versione"], v["servizio"], v["segnale"], ora, ora))
            else:
                db.execute("UPDATE elementi SET nome=?, dettaglio=?, versione=?, servizio=?, segnale=?, ultimo=?, presente=1 WHERE chiave=?",
                           (v["nome"], v["dettaglio"], v["versione"], v["servizio"], v["segnale"], ora, chiave))
            if n is None or (not n["presente"] and v["categoria"] not in VOLATILI):
                nuovi.append({"chiave": chiave, **v})
        for chiave, n in noti.items():
            if n["presente"] and chiave not in trovati:
                db.execute("UPDATE elementi SET presente=0 WHERE chiave=?", (chiave,))
                if n["categoria"] not in VOLATILI:
                    spariti.append({"chiave": chiave, **n})
        if not prima:   # la prima analisi e' il punto di partenza: non e' «comparso» tutto quel giorno
            db.executemany("INSERT INTO eventi (ora, tipo, chiave, categoria, nome, dettaglio) VALUES (?, ?, ?, ?, ?, ?)",
                           [(ora, tipo, e["chiave"], e["categoria"], e["nome"], e["dettaglio"]) for tipo, elenco in (("comparso", nuovi), ("sparito", spariti))
                            for e in elenco])
        db.execute("INSERT OR REPLACE INTO analisi VALUES (?, ?, ?, ?, ?, ?)", (ora, origine, float(pc.get("secondi") or 0), len(trovati),
                                                                              0 if prima else len(nuovi), 0 if prima else len(spariti)))
        db.execute("DELETE FROM eventi WHERE ora < ?", (time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * EVENTI_GIORNI)),))
        db.execute("DELETE FROM analisi WHERE ora NOT IN (SELECT ora FROM analisi ORDER BY ora DESC LIMIT 400)")
        db.commit()
        db.close()
    return {"prima": prima, "nuovi": [] if prima else nuovi, "spariti": [] if prima else spariti}


def ultima():
    """Quando e' stata fatta l'ultima analisi (testo «AAAA-MM-GG HH:MM:SS»), o "" se mai."""
    if not FILE.exists():
        return ""
    with _lucchetto:
        db = _db()
        r = db.execute("SELECT MAX(ora) FROM analisi").fetchone()[0]
        db.close()
    return r or ""


def riepilogo(eventi=200):
    with _lucchetto:
        db = _db()
        nomi = ("chiave", "categoria", "nome", "dettaglio", "versione", "servizio", "segnale", "primo", "ultimo", "presente", "giudizio", "nota")
        elementi = [dict(zip(nomi, r)) for r in db.execute(f"SELECT {', '.join(nomi)} FROM elementi ORDER BY categoria, nome COLLATE NOCASE")]
        analisi = [dict(zip(("ora", "origine", "secondi", "elementi", "nuovi", "spariti"), r))
                   for r in db.execute("SELECT ora, origine, secondi, elementi, nuovi, spariti FROM analisi ORDER BY ora DESC LIMIT 30")]
        fatti = [dict(zip(("ora", "tipo", "chiave", "categoria", "nome", "dettaglio"), r))
                 for r in db.execute("SELECT ora, tipo, chiave, categoria, nome, dettaglio FROM eventi ORDER BY id DESC LIMIT ?", (int(eventi),))]
        totale = db.execute("SELECT COUNT(*) FROM analisi").fetchone()[0]
        db.close()
    return {"elementi": elementi, "analisi": analisi, "eventi": fatti, "n_analisi": totale}


def giudica(chiave, giudizio, nota=None):
    with _lucchetto:
        db = _db()
        if giudizio in GIUDIZI:
            db.execute("UPDATE elementi SET giudizio=? WHERE chiave=?", (giudizio, str(chiave)))
        if nota is not None:
            db.execute("UPDATE elementi SET nota=? WHERE chiave=?", (str(nota).strip()[:300], str(chiave)))
        db.commit()
        db.close()


def dimentica():
    """Toglie dall'inventario cio' che non c'e' piu'. Restituisce quante voci ha tolto."""
    with _lucchetto:
        db = _db()
        n = db.execute("DELETE FROM elementi WHERE presente=0").rowcount
        db.commit()
        db.close()
    return n


def svuota():
    with _lucchetto:
        db = _db()
        for tabella in ("elementi", "eventi", "analisi"):
            db.execute(f"DELETE FROM {tabella}")
        db.commit()
        db.execute("VACUUM")
        db.close()


def csv(intestazioni, categoria=lambda c: c, giudizio=lambda g: g):
    """L'inventario come testo CSV (separatore ;) da aprire con Excel. intestazioni: i nomi delle colonne, gia' tradotti."""
    uscita = io.StringIO()
    w = _csv.writer(uscita, delimiter=";", lineterminator="\r\n")
    w.writerow(intestazioni)
    for e in riepilogo(0)["elementi"]:
        w.writerow([categoria(e["categoria"]), e["nome"], e["dettaglio"], e["versione"], e["primo"][:16], e["ultimo"][:16],
                    "1" if e["presente"] else "0", giudizio(e["giudizio"]), e["nota"]])
    return "﻿" + uscita.getvalue()   # il segno iniziale fa leggere a Excel le lettere accentate
