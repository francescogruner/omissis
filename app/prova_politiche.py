# -*- coding: utf-8 -*-
"""Verifica le politiche per servizio sul traffico che passa dal proxy, senza inviare alcun dato:
un servizio impostato su "blocca" deve essere rifiutato, uno su "registra" deve passare ed essere
contato.   Uso: python prova_politiche.py <host bloccato> <host registrato>
"""
import http.client
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
bloccato, registrato = sys.argv[1], sys.argv[2]
for host, atteso in ((bloccato, "rifiutato"), (registrato, "aperto")):
    c = http.client.HTTPSConnection("127.0.0.1", 8080, timeout=30)
    c.set_tunnel(host, 443)
    try:
        c.connect()
        esito = "aperto"
        c.close()
    except OSError as ex:
        esito = "rifiutato" if "403" in str(ex) else f"errore: {ex}"
    print(f"{'OK    ' if esito == atteso else 'ERRORE'} {host}: {esito} (atteso: {atteso})")
db = sqlite3.connect(Path(__file__).resolve().parent / "dati" / "contatti.sqlite")
for riga in db.execute("SELECT servizio, host, esito, n FROM contatti ORDER BY ultimo DESC LIMIT 6"):
    print("  contatto registrato:", riga)
