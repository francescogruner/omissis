# -*- coding: utf-8 -*-
"""Appunti di Windows: maschera o ripristina il testo copiato, per usare l'AI dentro qualsiasi app
senza che il programma debba leggerne il traffico.

  Ctrl+Alt+M   il testo negli appunti viene sostituito dalla versione mascherata (poi si incolla)
  Ctrl+Alt+R   il testo negli appunti (una risposta dell'AI copiata) torna con i valori veri

Le scorciatoie si attivano con il programma di gestione (panel.py). Solo testo: file e immagini
copiati negli appunti non vengono toccati.
"""
import ctypes
from ctypes import wintypes

import i18n
import restore as R

CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
u32, k32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
u32.OpenClipboard.argtypes, u32.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
u32.GetClipboardData.argtypes, u32.GetClipboardData.restype = [wintypes.UINT], ctypes.c_void_p
u32.SetClipboardData.argtypes, u32.SetClipboardData.restype = [wintypes.UINT, ctypes.c_void_p], ctypes.c_void_p
k32.GlobalAlloc.argtypes, k32.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], ctypes.c_void_p
k32.GlobalLock.argtypes, k32.GlobalLock.restype = [ctypes.c_void_p], ctypes.c_void_p
k32.GlobalUnlock.argtypes = [ctypes.c_void_p]


def _apri():
    for _ in range(10):   # un altro programma puo' averli aperti in questo istante
        if u32.OpenClipboard(None):
            return True
        ctypes.windll.kernel32.Sleep(30)
    return False


def leggi():
    if not _apri():
        return None
    try:
        h = u32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = k32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p) if p else None
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()


def scrivi(testo):
    dati = ctypes.create_unicode_buffer(testo)
    if not _apri():
        return False
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(dati))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, dati, ctypes.sizeof(dati))
        k32.GlobalUnlock(h)
        return bool(u32.SetClipboardData(CF_UNICODETEXT, h))
    finally:
        u32.CloseClipboard()


def trasforma(azione, motore):
    """Maschera o ripristina il testo negli appunti. motore(percorso, dati) chiama il motore.
    Restituisce il messaggio da mostrare all'utente."""
    testo = leggi()
    if not testo or not testo.strip():
        return i18n.t("appunti.vuoti")
    try:
        if azione == "maschera":
            r = motore("/maschera", {"testi": [testo[:200000]]})
            n = sum(r["conteggi"].values())
            if n and not scrivi(r["testi"][0]):
                return i18n.t("appunti.non_scrivibili")
            return i18n.t("appunti.mascherati", n=n) if n else i18n.t("appunti.nessun_dato")
        trovati = sorted({m.group() for m in R.RX_SEGNAPOSTO.finditer(testo)})
        if not trovati:
            return i18n.t("appunti.senza_segnaposto")
        mappa = motore("/valori", {"segnaposto": trovati})["mappa"]
        if mappa and not scrivi(R.ripristina(testo, mappa.get)):
            return i18n.t("appunti.non_scrivibili")
        return i18n.t("appunti.ripristinati", n=len(mappa)) + (" " + i18n.t("appunti.non_riconosciuti", n=len(trovati) - len(mappa)) if len(mappa) < len(trovati) else "")
    except Exception:   # noqa: BLE001
        return i18n.t("appunti.protezione_ferma")


def scorciatoie(motore, avvisa):
    """Attiva Ctrl+Alt+M e Ctrl+Alt+R. avvisa(messaggio) mostra l'esito. Restituisce l'ascoltatore, o None."""
    try:
        from pynput import keyboard
    except ImportError:
        return None
    ascolto = keyboard.GlobalHotKeys({"<ctrl>+<alt>+m": lambda: avvisa(trasforma("maschera", motore)),
                                      "<ctrl>+<alt>+r": lambda: avvisa(trasforma("ripristina", motore))})
    ascolto.daemon = True
    ascolto.start()
    return ascolto
