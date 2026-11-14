# -*- coding: utf-8 -*-
"""Verifica le politiche per servizio sul traffico che passa dal proxy, senza inviare alcun dato:
un servizio impostato su "blocca" deve essere rifiutato, uno su "registra" deve passare ed essere
contato.   Uso: python e2e_policies.py <host bloccato> <host registrato>
"""
import http.client
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
blocked, recorded = sys.argv[1], sys.argv[2]
for host, expected in ((blocked, "refused"), (recorded, "opened")):
    c = http.client.HTTPSConnection("127.0.0.1", 8080, timeout=30)
    c.set_tunnel(host, 443)
    try:
        c.connect()
        outcome = "opened"
        c.close()
    except OSError as ex:
        outcome = "refused" if "403" in str(ex) else f"errore: {ex}"
    print(f"{'OK    ' if outcome == expected else 'ERRORE'} {host}: {outcome} (atteso: {expected})")
db = sqlite3.connect(Path(__file__).resolve().parent / "data" / "contacts.sqlite")
for line in db.execute("SELECT service, host, outcome, n FROM contacts ORDER BY last DESC LIMIT 6"):
    print("  contatto registrato:", line)
