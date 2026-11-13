# -*- coding: utf-8 -*-
"""La finestra di Windows per scegliere una cartella, aperta dal programma al posto del browser.

Una pagina web non puo' conoscere il percorso di una cartella del disco: per questo il pannello, che gira su questo PC,
chiede a Windows la sua finestra «Seleziona cartella» e restituisce alla pagina il percorso scelto.

  scegli(titolo, iniziale="")   -> percorso scelto, oppure "" se si annulla
  apri(percorso)                -> apre la cartella in Esplora file
"""
import ctypes
import os
import threading
import uuid
from ctypes import wintypes

_una_per_volta = threading.Lock()
CLSID_FINESTRA = "{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}"    # FileOpenDialog
IID_FINESTRA = "{D57C7288-D4AD-4768-BE02-9D969532D960}"      # IFileOpenDialog
IID_ELEMENTO = "{43826D1E-E718-42EE-BC55-A1E261C37BFE}"      # IShellItem
SOLO_CARTELLE, SOLO_DISCO = 0x20, 0x40
PERCORSO_SUL_DISCO = 0x80058000
# posizione dei metodi nelle interfacce di Windows (IUnknown occupa le prime tre)
RILASCIA, MOSTRA, OPZIONI, CARTELLA, TITOLO, RISULTATO, NOME = 2, 3, 9, 12, 17, 20, 5


class _GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    def __init__(self, testo):
        super().__init__()
        ctypes.memmove(ctypes.byref(self), uuid.UUID(testo).bytes_le, 16)


def _metodo(oggetto, posizione, *tipi):
    tabella = ctypes.cast(ctypes.cast(oggetto, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    funzione = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *tipi)(tabella[posizione])
    return lambda *argomenti: funzione(oggetto, *argomenti)


def scegli(titolo, iniziale="", davanti=True):
    """Apre «Seleziona cartella» e aspetta la scelta. davanti: la finestra si lega a quella in primo piano (il browser),
    cosi' non resta nascosta dietro. Una finestra per volta: se ce n'e' gia' una aperta restituisce None."""
    if not _una_per_volta.acquire(blocking=False):
        return None
    ole32, shell32, user32 = ctypes.OleDLL("ole32"), ctypes.WinDLL("shell32"), ctypes.WinDLL("user32")
    user32.GetForegroundWindow.restype = wintypes.HWND
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    finestra, elemento, avviato = ctypes.c_void_p(), ctypes.c_void_p(), False
    try:
        ole32.CoInitialize(None)
        avviato = True
        ole32.CoCreateInstance(ctypes.byref(_GUID(CLSID_FINESTRA)), None, 1, ctypes.byref(_GUID(IID_FINESTRA)), ctypes.byref(finestra))
        _metodo(finestra, OPZIONI, wintypes.DWORD)(SOLO_CARTELLE | SOLO_DISCO)
        _metodo(finestra, TITOLO, wintypes.LPCWSTR)(titolo)
        if iniziale and os.path.isdir(iniziale):
            partenza = ctypes.c_void_p()
            if shell32.SHCreateItemFromParsingName(iniziale, None, ctypes.byref(_GUID(IID_ELEMENTO)), ctypes.byref(partenza)) == 0:
                _metodo(finestra, CARTELLA, ctypes.c_void_p)(partenza)
                _metodo(partenza, RILASCIA)()
        if _metodo(finestra, MOSTRA, wintypes.HWND)(user32.GetForegroundWindow() if davanti else None) != 0:
            return ""   # annullato
        if _metodo(finestra, RISULTATO, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(elemento)) != 0:
            return ""
        nome = ctypes.c_void_p()
        if _metodo(elemento, NOME, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(PERCORSO_SUL_DISCO, ctypes.byref(nome)) != 0:
            return ""
        try:
            return ctypes.wstring_at(nome.value)
        finally:
            ole32.CoTaskMemFree(nome)
    except OSError:
        return ""
    finally:
        for oggetto in (elemento, finestra):
            if oggetto:
                _metodo(oggetto, RILASCIA)()
        if avviato:
            ole32.CoUninitialize()
        _una_per_volta.release()


def apri(percorso):
    """Apre la cartella in Esplora file. Solo cartelle che esistono."""
    if not os.path.isdir(percorso):
        return False
    os.startfile(percorso)   # noqa: S606  (una cartella, non un programma)
    return True
