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
prima = clipboard.leggi()
if prima is None and ctypes.windll.user32.CountClipboardFormats() > 0:
    sys.exit("negli appunti c'è qualcosa che non è testo: prova saltata per non cancellarlo")
TESTO = "Scrivi una mail a Giulia Ferraresi (giulia.ferraresi@nevatek.example) per confermare l'appuntamento con Aldo Bruschi."
try:
    clipboard.scrivi(TESTO)
    print("maschera:  ", clipboard.trasforma("maschera", documents.motore))
    mascherato = clipboard.leggi()
    print("  negli appunti:", mascherato)
    risposta = "Ecco la bozza per " + mascherato.split("a ", 1)[1].split(" (")[0] + ": gentile collega, confermo l'appuntamento."
    clipboard.scrivi(risposta)
    print("ripristina:", clipboard.trasforma("ripristina", documents.motore))
    tornato = clipboard.leggi()
    print("  negli appunti:", tornato)
    ok = "Ferraresi" not in mascherato and "[PERSONA_" in mascherato and "Giulia Ferraresi" in tornato and "[" not in tornato
    print("OK" if ok else "ERRORE")
finally:
    clipboard.scrivi(prima) if prima is not None else None
sys.exit(0 if ok else 1)
