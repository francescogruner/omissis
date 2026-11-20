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

import sistema

_one_at_a_time = threading.Lock()
CLSID_WINDOW = "{DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7}"    # FileOpenDialog
IID_WINDOW = "{D57C7288-D4AD-4768-BE02-9D969532D960}"      # IFileOpenDialog
IID_ITEM = "{43826D1E-E718-42EE-BC55-A1E261C37BFE}"      # IShellItem
ONLY_FOLDERS, ONLY_DISK = 0x20, 0x40
PATH_ON_DISK = 0x80058000
# posizione dei metodi nelle interfacce di Windows (IUnknown occupa le prime tre)
RELEASE, SHOW, OPTIONS, FOLDER, TITLE, RESULT, NAME = 2, 3, 9, 12, 17, 20, 5


class _GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        ctypes.memmove(ctypes.byref(self), uuid.UUID(text).bytes_le, 16)


def _method(obj, position, *kinds):
    table = ctypes.cast(ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    func = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *kinds)(table[position])
    return lambda *arguments: func(obj, *arguments)


def choose(title, initial="", front=True):
    """Apre «Seleziona cartella» e aspetta la scelta. davanti: la finestra si lega a quella in primo piano (il browser),
    cosi' non resta nascosta dietro. Una finestra per volta: se ce n'e' gia' una aperta restituisce None."""
    if not _one_at_a_time.acquire(blocking=False):
        return None
    if not sistema.WINDOWS:   # sul Mac la finestra «Scegli la cartella» del sistema, chiesta ad AppleScript
        try:
            return sistema.choose_folder(title) or ""
        finally:
            _one_at_a_time.release()
    ole32, shell32, user32 = ctypes.OleDLL("ole32"), ctypes.WinDLL("shell32"), ctypes.WinDLL("user32")
    user32.GetForegroundWindow.restype = wintypes.HWND
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    shell32.SHCreateItemFromParsingName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(_GUID), ctypes.POINTER(ctypes.c_void_p)]
    win, item, launched = ctypes.c_void_p(), ctypes.c_void_p(), False
    try:
        ole32.CoInitialize(None)
        launched = True
        ole32.CoCreateInstance(ctypes.byref(_GUID(CLSID_WINDOW)), None, 1, ctypes.byref(_GUID(IID_WINDOW)), ctypes.byref(win))
        _method(win, OPTIONS, wintypes.DWORD)(ONLY_FOLDERS | ONLY_DISK)
        _method(win, TITLE, wintypes.LPCWSTR)(title)
        if initial and os.path.isdir(initial):
            start_point = ctypes.c_void_p()
            if shell32.SHCreateItemFromParsingName(initial, None, ctypes.byref(_GUID(IID_ITEM)), ctypes.byref(start_point)) == 0:
                _method(win, FOLDER, ctypes.c_void_p)(start_point)
                _method(start_point, RELEASE)()
        if _method(win, SHOW, wintypes.HWND)(user32.GetForegroundWindow() if front else None) != 0:
            return ""   # annullato
        if _method(win, RESULT, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(item)) != 0:
            return ""
        name = ctypes.c_void_p()
        if _method(item, NAME, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))(PATH_ON_DISK, ctypes.byref(name)) != 0:
            return ""
        try:
            return ctypes.wstring_at(name.value)
        finally:
            ole32.CoTaskMemFree(name)
    except OSError:
        return ""
    finally:
        for obj in (item, win):
            if obj:
                _method(obj, RELEASE)()
        if launched:
            ole32.CoUninitialize()
        _one_at_a_time.release()


def open_up(path):
    """Apre la cartella in Esplora file. Solo cartelle che esistono."""
    if not os.path.isdir(path):
        return False
    sistema.open_path(path)
    return True
