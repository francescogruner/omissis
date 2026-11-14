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

FILE = paths.DATA / "inventory.sqlite"
VERDICTS = ("", "approved", "to_remove")
# cio' che va e viene da solo (un programma aperto o chiuso, un sito contattato): se ne annota la comparsa, non la scomparsa
VOLATILE = {"processes", "listening", "contacted"}
EVENTS_DAYS = 365
_lock = threading.Lock()


def _db():
    FILE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(FILE)
    db.execute("CREATE TABLE IF NOT EXISTS scan (stamp TEXT PRIMARY KEY, origin TEXT, seconds REAL, items INTEGER, new_items INTEGER, gone INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS items (key TEXT PRIMARY KEY, category TEXT, name TEXT, detail TEXT, version TEXT, "
               "service TEXT, signal TEXT, first TEXT, last TEXT, present INTEGER, verdict TEXT DEFAULT '', note TEXT DEFAULT '')")
    db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, stamp TEXT, kind TEXT, key TEXT, category TEXT, "
               "name TEXT, detail TEXT)")
    return db


def items_of(pc, network=None):
    """La fotografia di scan.pc() e scan.rete() come elenco piatto: una voce per ogni cosa trovata, con una chiave stabile."""
    out = {}

    def entry(category, key, name, detail="", version="", service="", signal=""):
        out[f"{category}|{key}"] = {"category": category, "name": str(name)[:200], "detail": str(detail)[:300],
                                        "version": str(version)[:60], "service": str(service or ""), "signal": signal}
    for r in pc.get("programs", []):
        entry("programs", r["name"], r["service"]["name"], r["name"], r.get("version", ""), r["service"].get("id"))
    for r in pc.get("processes", []):
        entry("processes", r["name"].lower(), r["service"]["name"], r["name"], "", r["service"].get("id"))
    for r in pc.get("browser_extensions", []):
        entry("browser_extensions", f"{r['browser']}|{r['profile']}|{r['id']}", r["name"], f"{r['browser']} · {r['profile']}", r.get("version", ""),
             signal="all_sites" if r.get("all_sites_access") else "")
    for r in pc.get("editor_extensions", []):
        entry("editor_extensions", f"{r['editor']}|{r['author']}|{r['name']}", r["name"], f"{r['editor']} · {r['author']}", r.get("version", ""))
    for r in pc.get("commands", []):
        entry("commands", r["command"], r["command"], r["path"])
    for r in pc.get("local", []):
        if r.get("gb") is None:
            entry("listening", f"{r['name']}|{r.get('port', '')}", r["name"], f"127.0.0.1:{r.get('port', '')}")
        else:
            entry("local_models", r["name"], r["name"], r["what"], f"{r['gb']} GB")
    for r in (network or {}).get("dns", []) + (network or {}).get("links", []):
        entry("contacted", r["id"], r["service"], r.get("host", ""), "", r["id"])
    return out


def record(pc, network=None, origin="manual"):
    """Salva l'analisi. Restituisce {"prima": bool, "nuovi": [...], "spariti": [...]} rispetto a quella di prima."""
    stamp, found_items = time.strftime("%Y-%m-%d %H:%M:%S"), items_of(pc, network)
    with _lock:
        db = _db()
        before = db.execute("SELECT COUNT(*) FROM scan").fetchone()[0] == 0
        well_known = {r[0]: {"category": r[1], "name": r[2], "detail": r[3], "present": r[4]}
                for r in db.execute("SELECT key, category, name, detail, present FROM items")}
        new_items, gone = [], []
        for key, v in found_items.items():
            n = well_known.get(key)
            if n is None:
                db.execute("INSERT INTO items (key, category, name, detail, version, service, signal, first, last, present) "
                           "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)", (key, v["category"], v["name"], v["detail"], v["version"], v["service"], v["signal"], stamp, stamp))
            else:
                db.execute("UPDATE items SET name=?, detail=?, version=?, service=?, signal=?, last=?, present=1 WHERE key=?",
                           (v["name"], v["detail"], v["version"], v["service"], v["signal"], stamp, key))
            if n is None or (not n["present"] and v["category"] not in VOLATILE):
                new_items.append({"key": key, **v})
        for key, n in well_known.items():
            if n["present"] and key not in found_items:
                db.execute("UPDATE items SET present=0 WHERE key=?", (key,))
                if n["category"] not in VOLATILE:
                    gone.append({"key": key, **n})
        if not before:   # la prima analisi e' il punto di partenza: non e' «comparso» tutto quel giorno
            db.executemany("INSERT INTO events (stamp, kind, key, category, name, detail) VALUES (?, ?, ?, ?, ?, ?)",
                           [(stamp, kind, e["key"], e["category"], e["name"], e["detail"]) for kind, listing in (("appeared", new_items), ("gone", gone))
                            for e in listing])
        db.execute("INSERT OR REPLACE INTO scan VALUES (?, ?, ?, ?, ?, ?)", (stamp, origin, float(pc.get("seconds") or 0), len(found_items),
                                                                              0 if before else len(new_items), 0 if before else len(gone)))
        db.execute("DELETE FROM events WHERE stamp < ?", (time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * EVENTS_DAYS)),))
        db.execute("DELETE FROM scan WHERE stamp NOT IN (SELECT stamp FROM scan ORDER BY stamp DESC LIMIT 400)")
        db.commit()
        db.close()
    return {"before": before, "new_items": [] if before else new_items, "gone": [] if before else gone}


def latest():
    """Quando e' stata fatta l'ultima analisi (testo «AAAA-MM-GG HH:MM:SS»), o "" se mai."""
    if not FILE.exists():
        return ""
    with _lock:
        db = _db()
        r = db.execute("SELECT MAX(stamp) FROM scan").fetchone()[0]
        db.close()
    return r or ""


def summary(events=200):
    with _lock:
        db = _db()
        names = ("key", "category", "name", "detail", "version", "service", "signal", "first", "last", "present", "verdict", "note")
        items = [dict(zip(names, r)) for r in db.execute(f"SELECT {', '.join(names)} FROM items ORDER BY category, name COLLATE NOCASE")]
        scan = [dict(zip(("stamp", "origin", "seconds", "items", "new_items", "gone"), r))
                   for r in db.execute("SELECT stamp, origin, seconds, items, new_items, gone FROM scan ORDER BY stamp DESC LIMIT 30")]
        completed = [dict(zip(("stamp", "kind", "key", "category", "name", "detail"), r))
                 for r in db.execute("SELECT stamp, kind, key, category, name, detail FROM events ORDER BY id DESC LIMIT ?", (int(events),))]
        total = db.execute("SELECT COUNT(*) FROM scan").fetchone()[0]
        db.close()
    return {"items": items, "scan": scan, "events": completed, "scan_count": total}


def judge(key, verdict, note=None):
    with _lock:
        db = _db()
        if verdict in VERDICTS:
            db.execute("UPDATE items SET verdict=? WHERE key=?", (verdict, str(key)))
        if note is not None:
            db.execute("UPDATE items SET note=? WHERE key=?", (str(note).strip()[:300], str(key)))
        db.commit()
        db.close()


def forget():
    """Toglie dall'inventario cio' che non c'e' piu'. Restituisce quante voci ha tolto."""
    with _lock:
        db = _db()
        n = db.execute("DELETE FROM items WHERE present=0").rowcount
        db.commit()
        db.close()
    return n


def clear():
    with _lock:
        db = _db()
        for table in ("items", "events", "scan"):
            db.execute(f"DELETE FROM {table}")
        db.commit()
        db.execute("VACUUM")
        db.close()


def csv(headers, category=lambda c: c, verdict=lambda g: g):
    """L'inventario come testo CSV (separatore ;) da aprire con Excel. intestazioni: i nomi delle colonne, gia' tradotti."""
    output = io.StringIO()
    w = _csv.writer(output, delimiter=";", lineterminator="\r\n")
    w.writerow(headers)
    for e in summary(0)["items"]:
        w.writerow([category(e["category"]), e["name"], e["detail"], e["version"], e["first"][:16], e["last"][:16],
                    "1" if e["present"] else "0", verdict(e["verdict"]), e["note"]])
    return "﻿" + output.getvalue()   # il segno iniziale fa leggere a Excel le lettere accentate
