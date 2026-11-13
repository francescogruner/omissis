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

MAX_TESTO = 200_000     # oltre, il testo non viene elaborato (mai tagliato in silenzio)
PREDEFINITE = {"sostituisci": "ctrl+alt+s", "maschera": "ctrl+alt+m", "ripristina": "ctrl+alt+r"}
CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x4000
VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN = 0x10, 0x11, 0x12, 0x5B, 0x5C
WM_HOTKEY, WM_APP, WM_QUIT = 0x0312, 0x8000, 0x0012
# finestre in cui Ctrl+C non copia ma interrompe il programma in corso: li' la selezione non si tocca
TERMINALI = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty", "PuTTY", "VirtualConsoleClass", "Alacritty",
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
    if len(testo) > MAX_TESTO:
        return i18n.t("appunti.troppo_lungo", n=MAX_TESTO)
    try:
        if azione == "maschera":
            r = motore("/mask", {"testi": [testo]})
            n = sum(r["conteggi"].values())
            if n and not scrivi(r["testi"][0]):
                return i18n.t("appunti.non_scrivibili")
            return i18n.t("appunti.mascherati", n=n) if n else i18n.t("appunti.nessun_dato")
        trovati = sorted({m.group() for m in R.RX_SEGNAPOSTO.finditer(testo)})
        if not trovati:
            return i18n.t("appunti.senza_segnaposto")
        mappa = motore("/values", {"segnaposto": trovati})["mappa"]
        if mappa and not scrivi(R.ripristina(testo, mappa.get)):
            return i18n.t("appunti.non_scrivibili")
        return i18n.t("appunti.ripristinati", n=len(mappa)) + (" " + i18n.t("appunti.non_riconosciuti", n=len(trovati) - len(mappa)) if len(mappa) < len(trovati) else "")
    except Exception:   # noqa: BLE001
        return i18n.t("appunti.protezione_ferma")


# ------------------------------------------------------------------ il testo selezionato, sul posto

class _TASTO(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class _MOUSE(ctypes.Structure):   # serve solo a dare alla struttura la dimensione che Windows si aspetta
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _UNIONE(ctypes.Union):
    _fields_ = [("ki", _TASTO), ("mi", _MOUSE)]


class _INGRESSO(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNIONE)]


def premi(*tasti):
    """Preme insieme i tasti dati (codici virtuali) e li rilascia: premi(VK_CONTROL, ord("C"))."""
    giu = [_INGRESSO(1, _UNIONE(ki=_TASTO(t, 0, 0, 0, 0))) for t in tasti]
    su = [_INGRESSO(1, _UNIONE(ki=_TASTO(t, 0, 2, 0, 0))) for t in reversed(tasti)]
    serie = (_INGRESSO * (len(giu) + len(su)))(*giu, *su)
    return u32.SendInput(len(serie), serie, ctypes.sizeof(_INGRESSO)) == len(serie)


def in_primo_piano():
    """(finestra, classe) della finestra che riceve i tasti."""
    h = u32.GetForegroundWindow()
    classe = ctypes.create_unicode_buffer(200)
    u32.GetClassNameW(h, classe, 200)
    return h, classe.value


def _tasti_rilasciati(attesa=2.0):
    """Aspetta che Ctrl, Alt, Maiusc e Windows siano rilasciati: ancora premuti cambierebbero Ctrl+C in un'altra combinazione."""
    fine = time.time() + attesa
    while time.time() < fine:
        if not any(u32.GetAsyncKeyState(t) & 0x8000 for t in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN)):
            return True
        time.sleep(0.02)
    return False


def sostituisci(motore, solo_finestra=None):
    """Copia il testo selezionato nel programma in primo piano, lo maschera e lo incolla al posto dell'originale.
    solo_finestra: se dato, i tasti partono solo se in primo piano c'e' quella finestra (per le prove).
    Restituisce il messaggio da mostrare all'utente. Se qualcosa non va la selezione resta com'era."""
    finestra, classe = in_primo_piano()
    if classe in TERMINALI:
        return i18n.t("appunti.sul_posto.terminale")
    if not _tasti_rilasciati():
        return i18n.t("appunti.sul_posto.tasti_premuti")

    def stessa():
        return u32.GetForegroundWindow() == finestra and (solo_finestra is None or finestra == solo_finestra)
    if not stessa():
        return i18n.t("appunti.sul_posto.finestra_cambiata")
    prima = u32.GetClipboardSequenceNumber()
    premi(VK_CONTROL, ord("C"))
    fine = time.time() + 1.0
    while u32.GetClipboardSequenceNumber() == prima and time.time() < fine:
        time.sleep(0.02)
    if u32.GetClipboardSequenceNumber() == prima:
        return i18n.t("appunti.sul_posto.niente_selezionato")
    time.sleep(0.05)   # chi copia scrive piu' formati uno dopo l'altro
    testo = leggi()
    if not testo or not testo.strip():
        return i18n.t("appunti.sul_posto.niente_selezionato")
    if len(testo) > MAX_TESTO:
        return i18n.t("appunti.troppo_lungo", n=MAX_TESTO)
    try:
        r = motore("/mask", {"testi": [testo]})
    except Exception:   # noqa: BLE001
        return i18n.t("appunti.sul_posto.protezione_ferma")
    n = sum(r["conteggi"].values())
    if not n:
        return i18n.t("appunti.sul_posto.nessun_dato")
    if not scrivi(r["testi"][0]):
        return i18n.t("appunti.non_scrivibili")
    if not stessa():   # nel frattempo si e' passati a un'altra finestra: li' non si incolla nulla
        return i18n.t("appunti.sul_posto.solo_appunti", n=n)
    time.sleep(0.05)
    premi(VK_CONTROL, ord("V"))
    return i18n.t("appunti.sul_posto.fatto", n=n)


# ------------------------------------------------------------------ scorciatoie

def combinazione(testo):
    """«ctrl+alt+m» -> (modificatori, codice del tasto); None se vuota o non valida. Serve almeno Ctrl o Alt."""
    mod, tasto = 0, None
    for p in (x.strip().lower() for x in str(testo or "").split("+")):
        if p in ("ctrl", "control"):
            mod |= MOD_CONTROL
        elif p == "alt":
            mod |= MOD_ALT
        elif p in ("shift", "maiusc"):
            mod |= MOD_SHIFT
        elif len(p) == 1 and p.isascii() and p.isalnum() and tasto is None:
            tasto = ord(p.upper())
        elif re.fullmatch(r"f([1-9]|1\d|2[0-4])", p) and tasto is None:
            tasto = 0x6F + int(p[1:])
        else:
            return None
    return (mod, tasto) if tasto and mod & (MOD_CONTROL | MOD_ALT) else None


def scritta(testo):
    """«ctrl+alt+m» -> «Ctrl+Alt+M», come si scrive sui tasti."""
    return "+".join(p.strip().capitalize() if len(p.strip()) > 1 else p.strip().upper() for p in str(testo or "").split("+") if p.strip())


def scelte(imp):
    """Le combinazioni in uso: quelle delle impostazioni sopra le predefinite. Vuota = scorciatoia spenta."""
    date = imp.get("scorciatoie") if isinstance(imp.get("scorciatoie"), dict) else {}
    return {nome: str(date.get(nome, predefinita)).strip().lower()[:40] for nome, predefinita in PREDEFINITE.items()}


class Scorciatoie:
    """Tiene registrate le scorciatoie e chiama l'azione di ciascuna. azioni: {nome: funzione senza argomenti}."""

    def __init__(self, azioni):
        self.azioni = azioni
        self.volute = {}
        self.stato = {}        # nome -> {"combinazione": "ctrl+alt+m", "attiva": bool, "errore": "" | "occupata" | "non_valida"}
        self.filo = None       # identificativo del thread con il ciclo dei messaggi
        self.pronto, self.registrate = threading.Event(), threading.Event()
        self.occupato = threading.Lock()

    def imposta(self, volute):
        """Registra queste combinazioni al posto di quelle di prima e restituisce lo stato."""
        self.volute = dict(volute)
        self.registrate.clear()
        if self.filo is None:
            threading.Thread(target=self._ciclo, daemon=True).start()
            self.pronto.wait(5)
        else:
            u32.PostThreadMessageW(self.filo, WM_APP, 0, 0)
        self.registrate.wait(5)
        return self.stato

    def ferma(self):
        if self.filo is not None:
            u32.PostThreadMessageW(self.filo, WM_QUIT, 0, 0)

    def _registra(self, nomi):
        for i in range(len(nomi)):
            u32.UnregisterHotKey(None, i + 1)
        stato = {}
        for i, nome in enumerate(nomi):
            scelta = self.volute.get(nome, "")
            voce = {"combinazione": scelta, "attiva": False, "errore": ""}
            if scelta:
                c = combinazione(scelta)
                if c is None:
                    voce["errore"] = "non_valida"
                elif any(combinazione(v["combinazione"]) == c for v in stato.values() if v["attiva"]):
                    voce["errore"] = "occupata"
                elif u32.RegisterHotKey(None, i + 1, c[0] | MOD_NOREPEAT, c[1]):
                    voce["attiva"] = True
                else:
                    voce["errore"] = "occupata"   # un altro programma (o un'altra copia di Omissis) l'ha gia' presa
            stato[nome] = voce
        self.stato = stato
        self.registrate.set()

    def _esegui(self, nome):
        if not self.occupato.acquire(blocking=False):   # una per volta: una scorciatoia premuta due volte non si accavalla
            return
        try:
            self.azioni[nome]()
        except Exception:   # noqa: BLE001  (un errore in un'azione non deve spegnere le scorciatoie)
            pass
        finally:
            self.occupato.release()

    def _ciclo(self):
        nomi, msg = list(self.azioni), wintypes.MSG()
        u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)   # crea la coda dei messaggi di questo thread
        self.filo = k32.GetCurrentThreadId()
        self.pronto.set()
        self._registra(nomi)
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and 1 <= msg.wParam <= len(nomi):
                threading.Thread(target=self._esegui, args=(nomi[msg.wParam - 1],), daemon=True).start()
            elif msg.message == WM_APP:
                self._registra(nomi)
        for i in range(len(nomi)):
            u32.UnregisterHotKey(None, i + 1)
        self.filo = None


def sistema(s, volute):
    """Se una combinazione Ctrl+Alt+lettera e' gia' presa da un altro programma (succede: le sovrapposizioni delle schede
    grafiche ne usano diverse) ne registra un'altra libera. Restituisce (combinazioni in uso, {nome: (vecchia, nuova)})."""
    volute, cambiate = dict(volute), {}
    for _ in range(len(volute) + 1):
        stato = s.imposta(volute)
        prese = [n for n, v in stato.items() if v["errore"] == "occupata" and re.fullmatch(r"ctrl\+alt\+[a-z]", v["combinazione"])]
        if not prese:
            break
        nome = prese[0]
        for lettera in ALTERNATIVE.get(nome, "") + "kjhxzdtyugbvqwopilfacn":   # mai la E: con AltGr scrive il simbolo dell'euro
            nuova = f"ctrl+alt+{lettera}"
            if nuova not in volute.values() and s.imposta({**volute, nome: nuova})[nome]["attiva"]:
                cambiate[nome] = (cambiate.get(nome, (volute[nome],))[0], nuova)
                volute[nome] = nuova
                break
        else:
            break
    return volute, cambiate


ALTERNATIVE = {"sostituisci": "xzd", "maschera": "kjh", "ripristina": "tyu"}   # le lettere vicine, provate per prime


def scorciatoie(motore, avvisa):
    """Le scorciatoie sugli appunti e sul testo selezionato, ancora da registrare. avvisa(messaggio) mostra l'esito."""
    return Scorciatoie({"sostituisci": lambda: avvisa(sostituisci(motore)),
                        "maschera": lambda: avvisa(trasforma("maschera", motore)),
                        "ripristina": lambda: avvisa(trasforma("ripristina", motore))})
