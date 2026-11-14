# -*- coding: utf-8 -*-
"""Appunti di Windows e scorciatoie: per usare l'AI dentro qualsiasi app senza che il programma debba leggerne il traffico.

  Ctrl+Alt+S   il testo SELEZIONATO nel programma in primo piano viene mascherato e rimesso al suo posto
  Ctrl+Alt+M   il testo negli appunti viene sostituito dalla versione mascherata (poi si incolla)
  Ctrl+Alt+R   il testo negli appunti (una risposta dell'AI copiata) torna con i valori veri

Le combinazioni si cambiano o si spengono nelle impostazioni («scorciatoie»). Sono registrate con RegisterHotKey:
Windows consegna al programma solo quelle combinazioni, gli altri tasti premuti non li vede nessuno.
Solo testo: file e immagini copiati negli appunti non vengono toccati.
"""
import ctypes
import re
import threading
import time
from ctypes import wintypes

import i18n
import restore as R

MAX_TEXT = 200_000     # oltre, il testo non viene elaborato (mai tagliato in silenzio)
DEFAULTS = {"replace": "ctrl+alt+s", "mask": "ctrl+alt+m", "restore": "ctrl+alt+r"}
CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000
VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x10, 0x11, 0x12, 0x5B, 0x5C
WM_HOTKEY, WM_APP, WM_QUIT = 0x0312, 0x8000, 0x0012
# finestre in cui Ctrl+C non copia ma interrompe il programma in corso: li' la selezione non si tocca
TERMINALS = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "PuTTY", "VirtualConsoleClass", "Alacritty",
             "org.wezfurlong.wezterm", "kitty", "TMobaXtermForm"}

u32, k32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
u32.OpenClipboard.argtypes, u32.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
u32.GetClipboardData.argtypes, u32.GetClipboardData.restype = [wintypes.UINT], ctypes.c_void_p
u32.SetClipboardData.argtypes, u32.SetClipboardData.restype = [wintypes.UINT, ctypes.c_void_p], ctypes.c_void_p
u32.GetForegroundWindow.restype = wintypes.HWND
u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
u32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
u32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
k32.GlobalAlloc.argtypes, k32.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], ctypes.c_void_p
k32.GlobalLock.argtypes, k32.GlobalLock.restype = [ctypes.c_void_p], ctypes.c_void_p
k32.GlobalUnlock.argtypes = [ctypes.c_void_p]


# ------------------------------------------------------------------ appunti

def _open_up():
    for _ in range(10):   # un altro programma puo' averli aperti in questo istante
        if u32.OpenClipboard(None):
            return True
        ctypes.windll.kernel32.Sleep(30)
    return False


def read():
    if not _open_up():
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


def write(text):
    data = ctypes.create_unicode_buffer(text)
    if not _open_up():
        return False
    try:
        u32.EmptyClipboard()
        h = k32.GlobalAlloc(GMEM_MOVEABLE, ctypes.sizeof(data))
        p = k32.GlobalLock(h)
        ctypes.memmove(p, data, ctypes.sizeof(data))
        k32.GlobalUnlock(h)
        return bool(u32.SetClipboardData(CF_UNICODETEXT, h))
    finally:
        u32.CloseClipboard()


def transform(action, engine):
    """Maschera o ripristina il testo negli appunti. motore(percorso, dati) chiama il motore.
    Restituisce il messaggio da mostrare all'utente."""
    text = read()
    if not text or not text.strip():
        return i18n.t("clipboard.empty")
    if len(text) > MAX_TEXT:
        return i18n.t("clipboard.too_long", n=MAX_TEXT)
    try:
        if action == "mask":
            r = engine("/mask", {"texts": [text]})
            n = sum(r["counts"].values())
            if n and not write(r["texts"][0]):
                return i18n.t("clipboard.not_writable")
            return i18n.t("clipboard.masked", n=n) if n else i18n.t("clipboard.no_data")
        found_items = sorted({m.group() for m in R.RX_PLACEHOLDER.finditer(text)})
        if not found_items:
            return i18n.t("clipboard.without_placeholder")
        mapping = engine("/values", {"placeholder": found_items})["mapping"]
        if mapping and not write(R.restore(text, mapping.get)):
            return i18n.t("clipboard.not_writable")
        return i18n.t("clipboard.restored", n=len(mapping)) + (" " + i18n.t("clipboard.not_recognized", n=len(found_items) - len(mapping)) if len(mapping) < len(found_items) else "")
    except Exception:   # noqa: BLE001
        return i18n.t("clipboard.protection_stopped")


# ------------------------------------------------------------------ il testo selezionato, sul posto

class _KEYSTROKE(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSE(ctypes.Structure):   # serve solo a dare alla struttura la dimensione che Windows si aspetta
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _UNION(ctypes.Union):
    _fields_ = [("ki", _KEYSTROKE), ("mi", _MOUSE)]


class _INBOUND(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


def press(*keystrokes):
    """Preme insieme i tasti dati (codici virtuali) e li rilascia: premi(VK_CONTROL, ord("C"))."""
    down = [_INBOUND(1, _UNION(ki=_KEYSTROKE(t, 0, 0, 0, 0))) for t in keystrokes]
    su = [_INBOUND(1, _UNION(ki=_KEYSTROKE(t, 0, 2, 0, 0))) for t in reversed(keystrokes)]
    series = (_INBOUND * (len(down) + len(su)))(*down, *su)
    return u32.SendInput(len(series), series, ctypes.sizeof(_INBOUND)) == len(series)


def in_foreground():
    """(finestra, classe) della finestra che riceve i tasti."""
    h = u32.GetForegroundWindow()
    cls = ctypes.create_unicode_buffer(200)
    u32.GetClassNameW(h, cls, 200)
    return h, cls.value


def _keystrokes_released(timeout=2.0):
    """Aspetta che Ctrl, Alt, Maiusc e Windows siano rilasciati: ancora premuti cambierebbero Ctrl+C in un'altra combinazione."""
    end = time.time() + timeout
    while time.time() < end:
        if not any(u32.GetAsyncKeyState(t) & 0x8000 for t in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN)):
            return True
        time.sleep(0.02)
    return False


def replace(engine, only_window=None):
    """Copia il testo selezionato nel programma in primo piano, lo maschera e lo incolla al posto dell'originale.
    solo_finestra: se dato, i tasti partono solo se in primo piano c'e' quella finestra (per le prove).
    Restituisce il messaggio da mostrare all'utente. Se qualcosa non va la selezione resta com'era."""
    win, cls = in_foreground()
    if cls in TERMINALS:
        return i18n.t("clipboard.in_place.terminal")
    if not _keystrokes_released():
        return i18n.t("clipboard.in_place.keystrokes_pressed")

    def same():
        return u32.GetForegroundWindow() == win and (only_window is None or win == only_window)
    if not same():
        return i18n.t("clipboard.in_place.window_changed")
    before = u32.GetClipboardSequenceNumber()
    press(VK_CONTROL, ord("C"))
    end = time.time() + 1.0
    while u32.GetClipboardSequenceNumber() == before and time.time() < end:
        time.sleep(0.02)
    if u32.GetClipboardSequenceNumber() == before:
        return i18n.t("clipboard.in_place.nothing_selected")
    time.sleep(0.05)   # chi copia scrive piu' formati uno dopo l'altro
    text = read()
    if not text or not text.strip():
        return i18n.t("clipboard.in_place.nothing_selected")
    if len(text) > MAX_TEXT:
        return i18n.t("clipboard.too_long", n=MAX_TEXT)
    try:
        r = engine("/mask", {"texts": [text]})
    except Exception:   # noqa: BLE001
        return i18n.t("clipboard.in_place.protection_stopped")
    n = sum(r["counts"].values())
    if not n:
        return i18n.t("clipboard.in_place.no_data")
    if not write(r["texts"][0]):
        return i18n.t("clipboard.not_writable")
    if not same():   # nel frattempo si e' passati a un'altra finestra: li' non si incolla nulla
        return i18n.t("clipboard.in_place.only_clipboard", n=n)
    time.sleep(0.05)
    press(VK_CONTROL, ord("V"))
    return i18n.t("clipboard.in_place.done", n=n)


# ------------------------------------------------------------------ scorciatoie

def combo(text):
    """«ctrl+alt+m» -> (modificatori, codice del tasto); None se vuota o non valida. Serve almeno Ctrl o Alt."""
    mod, keystroke = 0, None
    for p in (x.strip().lower() for x in str(text or "").split("+")):
        if p in ("ctrl", "control"):
            mod |= MOD_CONTROL
        elif p == "alt":
            mod |= MOD_ALT
        elif p in ("shift", "upper"):
            mod |= MOD_SHIFT
        elif len(p) == 1 and p.isascii() and p.isalnum() and keystroke is None:
            keystroke = ord(p.upper())
        elif re.fullmatch(r"f([1-9]|1\d|2[0-4])", p) and keystroke is None:
            keystroke = 0x6F + int(p[1:])
        else:
            return None
    return (mod, keystroke) if keystroke and mod & (MOD_CONTROL | MOD_ALT) else None


def caption(text):
    """«ctrl+alt+m» -> «Ctrl+Alt+M», come si scrive sui tasti."""
    return "+".join(p.strip().capitalize() if len(p.strip()) > 1 else p.strip().upper() for p in str(text or "").split("+") if p.strip())


def choices(cfg):
    """Le combinazioni in uso: quelle delle impostazioni sopra le predefinite. Vuota = scorciatoia spenta."""
    date = cfg.get("shortcuts") if isinstance(cfg.get("shortcuts"), dict) else {}
    return {name: str(date.get(name, default)).strip().lower()[:40] for name, default in DEFAULTS.items()}


class Shortcuts:
    """Tiene registrate le scorciatoie e chiama l'azione di ciascuna. azioni: {nome: funzione senza argomenti}."""

    def __init__(self, actions):
        self.actions = actions
        self.wanted = {}
        self.status = {}        # nome -> {"combinazione": "ctrl+alt+m", "attiva": bool, "errore": "" | "occupata" | "non_valida"}
        self.thread = None       # identificativo del thread con il ciclo dei messaggi
        self.ready_now, self.recorded = threading.Event(), threading.Event()
        self.busy = threading.Lock()

    def configure(self, wanted):
        """Registra queste combinazioni al posto di quelle di prima e restituisce lo stato."""
        self.wanted = dict(wanted)
        self.recorded.clear()
        if self.thread is None:
            threading.Thread(target=self._loop, daemon=True).start()
            self.ready_now.wait(5)
        else:
            u32.PostThreadMessageW(self.thread, WM_APP, 0, 0)
        self.recorded.wait(5)
        return self.status

    def stop(self):
        if self.thread is not None:
            u32.PostThreadMessageW(self.thread, WM_QUIT, 0, 0)

    def _record(self, names):
        for i in range(len(names)):
            u32.UnregisterHotKey(None, i + 1)
        status = {}
        for i, name in enumerate(names):
            choice = self.wanted.get(name, "")
            entry = {"combo": choice, "active": False, "error": ""}
            if choice:
                c = combo(choice)
                if c is None:
                    entry["error"] = "not_valid"
                elif any(combo(v["combo"]) == c for v in status.values() if v["active"]):
                    entry["error"] = "busy"
                elif u32.RegisterHotKey(None, i + 1, c[0] | MOD_NOREPEAT, c[1]):
                    entry["active"] = True
                else:
                    entry["error"] = "busy"   # un altro programma (o un'altra copia di Omissis) l'ha gia' presa
            status[name] = entry
        self.status = status
        self.recorded.set()

    def _run(self, name):
        if not self.busy.acquire(blocking=False):   # una per volta: una scorciatoia premuta due volte non si accavalla
            return
        try:
            self.actions[name]()
        except Exception:   # noqa: BLE001  (un errore in un'azione non deve spegnere le scorciatoie)
            pass
        finally:
            self.busy.release()

    def _loop(self):
        names, msg = list(self.actions), wintypes.MSG()
        u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)   # crea la coda dei messaggi di questo thread
        self.thread = k32.GetCurrentThreadId()
        self.ready_now.set()
        self._record(names)
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and 1 <= msg.wParam <= len(names):
                threading.Thread(target=self._run, args=(names[msg.wParam - 1],), daemon=True).start()
            elif msg.message == WM_APP:
                self._record(names)
        for i in range(len(names)):
            u32.UnregisterHotKey(None, i + 1)
        self.thread = None


def system(s, wanted):
    """Se una combinazione Ctrl+Alt+lettera e' gia' presa da un altro programma (succede: le sovrapposizioni delle schede
    grafiche ne usano diverse) ne registra un'altra libera. Restituisce (combinazioni in uso, {nome: (vecchia, nuova)})."""
    wanted, changed = dict(wanted), {}
    for _ in range(len(wanted) + 1):
        status = s.configure(wanted)
        taken = [n for n, v in status.items() if v["error"] == "busy" and re.fullmatch(r"ctrl\+alt\+[a-z]", v["combo"])]
        if not taken:
            break
        name = taken[0]
        for letter in ALTERNATIVE.get(name, "") + "kjhxzdtyugbvqwopilfacn":   # mai la E: con AltGr scrive il simbolo dell'euro
            new_one = f"ctrl+alt+{letter}"
            if new_one not in wanted.values() and s.configure({**wanted, name: new_one})[name]["active"]:
                changed[name] = (changed.get(name, (wanted[name],))[0], new_one)
                wanted[name] = new_one
                break
        else:
            break
    return wanted, changed


ALTERNATIVE = {"replace": "xzd", "mask": "kjh", "restore": "tyu"}   # le lettere vicine, provate per prime


def shortcuts(engine, notify):
    """Le scorciatoie sugli appunti e sul testo selezionato, ancora da registrare. avvisa(messaggio) mostra l'esito."""
    return Shortcuts({"replace": lambda: notify(replace(engine)),
                        "mask": lambda: notify(transform("mask", engine)),
                        "restore": lambda: notify(transform("restore", engine))})
