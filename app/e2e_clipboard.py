# -*- coding: utf-8 -*-
"""Prova le funzioni sugli appunti (quelle dietro Ctrl+Alt+M e Ctrl+Alt+R) senza premere tasti.
Salva il testo che c'e' negli appunti e lo rimette alla fine; se negli appunti c'e' altro
(un'immagine, dei file) non fa nulla, per non cancellarlo.   Richiede la protezione attiva.
"""
import ctypes
import sys

import clipboard
import documents

sys.stdout.reconfigure(encoding="utf-8")
before = clipboard.read()
if before is None and ctypes.windll.user32.CountClipboardFormats() > 0:
    sys.exit("negli appunti c'è qualcosa che non è testo: prova saltata per non cancellarlo")
TEXT = "Scrivi una mail a Giulia Ferraresi (giulia.ferraresi@nevatek.example) per confermare l'appuntamento con Aldo Bruschi."
try:
    clipboard.write(TEXT)
    print("maschera:  ", clipboard.transform("mask", documents.engine))
    masked = clipboard.read()
    print("  negli appunti:", masked)
    response = "Ecco la bozza per " + masked.split("a ", 1)[1].split(" (")[0] + ": gentile collega, confermo l'appuntamento."
    clipboard.write(response)
    print("ripristina:", clipboard.transform("restore", documents.engine))
    returned = clipboard.read()
    print("  negli appunti:", returned)
    ok = "Ferraresi" not in masked and "[PERSONA_" in masked and "Giulia Ferraresi" in returned and "[" not in returned
    print("OK" if ok else "ERRORE")
finally:
    clipboard.write(before) if before is not None else None
sys.exit(0 if ok else 1)
