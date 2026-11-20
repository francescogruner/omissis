# -*- coding: utf-8 -*-
"""Connettore per le app desktop costruite con tecnologia web (Claude, ChatGPT/Codex e simili).

Queste app sono un browser Chromium con dentro il sito del servizio. Se l'app viene avviata con la
porta di debug (--remote-debugging-port), il connettore ci si collega e porta dentro la finestra lo
stesso codice dell'estensione del browser (extension\\page.js, channel.js, content.js): il testo
viene sostituito PRIMA di essere cifrato, quindi non servono certificato ne' proxy e non conta se
l'app controlla i certificati. Il lavoro vero lo fa sempre il motore (bridge.py).

Le barriere sono due. Quella dentro la pagina (page.js) sostituisce i dati e riscrive le risposte
mentre arrivano. Quella a livello di rete (il dominio "Fetch" della porta di debug) ferma ogni invio
verso un servizio protetto prima che parta e lo controlla di nuovo: serve per le richieste che la
pagina fa nei primissimi istanti, quando il codice al suo interno puo' non essere ancora attivo, e
per quelle che non passano da fetch o XMLHttpRequest.

  .venv\\Scripts\\python.exe connector.py --start claude        avvia l'app con la porta e si collega
  .venv\\Scripts\\python.exe connector.py --start claude --close   se e' gia' aperta la chiude e la riapre protetta
  .venv\\Scripts\\python.exe connector.py --port 9551          si collega a un'app gia' avviata cosi'

SPERIMENTALE. Da sapere:
  - l'app va chiusa del tutto e riaperta da qui (lo puo' fare il connettore, se glielo si chiede);
  - finche' e' aperta in questo modo, qualunque programma di questo PC puo' comandarla dalla porta;
  - il produttore puo' disattivare funzioni quando vede la porta di debug, o togliere la possibilita'.
"""
import argparse
import base64
import ctypes
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from ctypes import wintypes
from pathlib import Path

import websocket

import catalog
import activity
import i18n
import paths
import sistema

HERE = Path(__file__).resolve().parent
DATA, EST = paths.DATA, HERE / "extension"
ENGINE_PORT = paths.ENGINE_PORT
WORLD, CALL = "omissis", "__omissis_bridge"
_STORE = r"%LOCALAPPDATA%\Microsoft\WindowsApps" "\\"
# Le app che sappiamo avviare con la porta di debug.
#   commands     dove puo' trovarsi il programma: vale il primo che esiste
#   process      nome del programma e, per non confonderlo con altri dallo stesso nome (il Claude da terminale si chiama
#                anche lui claude.exe), un'espressione che il suo percorso completo deve soddisfare
#   service      il servizio del catalogo a cui l'app parla: la sua politica decide se i messaggi vengono mascherati
#   refuses      l'app si chiude da sola se avviata con la porta di debug: da qui non la si avvia, e il pannello lo dice
#   plugin       l'app ha un sistema di plugin suo, con cui Omissis controlla i messaggi prima dell'invio (kimi_plugin.py)
#   package      app dello Store senza un comando da lanciare (Perplexity): (nome del pacchetto, id dell'app). Si avvia
#                chiedendo a Windows di aprirla con gli argomenti (IApplicationActivationManager), come fa il menu Start
#   internals    indirizzi http con cui l'app chiama le proprie finestre (Perplexity: perplexity.localhost): sono sue, non siti
#   own_profile  l'app e' un browser Chromium vero e proprio (Copilot e' un Edge): dalla versione 136 Chromium ignora la porta
#                di debug sul profilo predefinito, quindi l'app protetta gira con un profilo suo, tenuto nei dati di Omissis.
#                Vuol dire rifare l'accesso la prima volta; la copia normale dell'app puo' restare aperta, e NON e' protetta.
APP = {
    "claude": {"name": "Claude", "commands": [_STORE + "claude-desktop.exe", _STORE + "claude-desktop-msstore.exe"],
               "process": ("claude.exe", r"\\app\\claude\.exe$"), "port": 9551, "site": "claude.ai", "service": "claude",
               # provato il 20/11/2026 su Mac (5.11492.5 e 6.28899.2) e su Windows (6.28899.2): avviata con la porta di debug
               # esce subito, codice 1, e scrive «Claude: refusing to start — a debugging or network-override switch is
               # present on the command line». La ammette solo con un permesso firmato da Anthropic (CLAUDE_CDP_AUTH).
               # Usa pero' il proxy e i certificati del sistema, come nelle reti aziendali (provato lo stesso giorno, Windows
               # e Mac, 6.28899.2): la si protegge da li', con un file PAC e il certificato del proxy di Omissis.
               "refuses": True, "proxy": True},
    "chatgpt": {"name": "ChatGPT / Codex", "commands": [_STORE + "chatgpt-desktop.exe"],
                "process": ("chatgpt.exe", r"\\app\\chatgpt\.exe$"), "port": 9552, "site": "chatgpt.com", "service": "chatgpt"},
    "kimi": {"name": "Kimi", "commands": [r"%LOCALAPPDATA%\Programs\Kimi\Kimi.exe"],
             "process": ("kimi.exe", r"\\kimi\\kimi\.exe$"), "port": 9553, "site": "kimi.com", "service": "kimi",
             # provato il 14/11/2026 sulla 3.2.24: avviata con la porta di debug (anche 0) esce da sola in un secondo, codice 1
             # la protezione passa dal sistema di plugin dell'app (hook UserPromptSubmit): vedi kimi_plugin.py
             "refuses": True, "plugin": True},
    # dalla 157 (novembre 2026) il programma si chiama copilotapp.exe; prima mscopilot.exe
    "copilot": {"name": "Microsoft Copilot", "commands": [r"%ProgramFiles(x86)%\Microsoft\Copilot\Application\copilotapp.exe",
                                                           r"%ProgramFiles%\Microsoft\Copilot\Application\copilotapp.exe",
                                                           r"%ProgramFiles(x86)%\Microsoft\Copilot\Application\mscopilot.exe",
                                                           r"%ProgramFiles%\Microsoft\Copilot\Application\mscopilot.exe"],
                "process": ("copilotapp.exe|mscopilot.exe", r"\\copilot\\application\\(copilotapp|mscopilot)\.exe$"), "port": 9554, "site": "copilot.microsoft.com",
                # dalla 157 e' l'app di Microsoft 365 Copilot: la casella sta su m365copilotapp.svc.cloud.microsoft
                "service": "copilot-365", "own_profile": True},
    # provata il 17/11/2026 sulla 26.11 (Electron 45, dallo Store): aperta con la porta di debug la tiene aperta
    "perplexity": {"name": "Perplexity", "package": ("PerplexityAI.PerplexityApp", "ai.perplexity.PerplexityPersonalComputer.Electron"),
                   "process": ("perplexity.exe", r"\\perplexityai\.perplexityapp_[^\\]+\\app\\perplexity\.exe$"), "port": 9555,
                   "site": "www.perplexity.ai", "service": "perplexity", "internals": ["http://perplexity.localhost"]},
}
# Sul Mac: solo le app fatte con Chromium/Electron accettano la porta di debug.
# ChatGPT: dal 9/7/2026 l'app per Mac e' la stessa di Windows (Electron, com.openai.codex, programma «ChatGPT» dentro
# /Applications/ChatGPT.app; letto il 19/11/2026 in seanthegeek/doubleagent#121, prova su un Mac del 15/10/2026). L'app
# nativa di prima si chiama «ChatGPT Classic»: niente porta e certificati fissati, quindi resta fuori.
# Perplexity e Copilot per Mac sono app native: fuori anche loro.
# Provato il 20/11/2026 su un Mac di GitHub (macOS 26): ChatGPT (26.1111.21308 e 26.1117.31558) accetta la porta e il codice entra nella
# finestra (app://-/index.html); percorsi e nomi dei processi sono giusti. Claude rifiuta la porta, come su Windows.
APP_MAC = {
    "claude": {"commands": ["/Applications/Claude.app/Contents/MacOS/Claude", "~/Applications/Claude.app/Contents/MacOS/Claude"],
               "process": ("claude", r"/Claude\.app/Contents/MacOS/Claude$")},
    "chatgpt": {"commands": ["/Applications/ChatGPT.app/Contents/MacOS/ChatGPT", "~/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"],
                "process": ("chatgpt", r"/ChatGPT\.app/Contents/MacOS/ChatGPT$")},
    "kimi": {"commands": ["/Applications/Kimi.app/Contents/MacOS/Kimi", "~/Applications/Kimi.app/Contents/MacOS/Kimi"],
             "process": ("kimi", r"/Kimi\.app/Contents/MacOS/Kimi$")},
}
if not sistema.WINDOWS:
    APP = {key: {**APP[key], **APP_MAC[key]} for key in APP_MAC} if sistema.MAC else {}


class Error(Exception):
    pass


class AlreadyOpen(Error):
    """L'app e' aperta senza la porta di debug: va chiusa, e a deciderlo e' chi la sta usando."""


def opened_port(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


# ------------------------------------------------------------------ i processi delle app (Windows)

class _Entry(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


if sistema.WINDOWS:
    _k32, _u32 = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("user32", use_last_error=True)
    _k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _k32.Process32FirstW.argtypes = _k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Entry)]
    _k32.OpenProcess.restype = wintypes.HANDLE
    _k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    _k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _WINDOWS = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _u32.EnumWindows.argtypes = [_WINDOWS, wintypes.LPARAM]
    _u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _u32.IsWindowVisible.argtypes = [wintypes.HWND]


def _kill(pid):
    """Ferma subito un processo (uno nostro)."""
    if not sistema.WINDOWS:
        sistema.terminate([pid], grace=2)
        return
    h = _k32.OpenProcess(0x0001, False, pid)   # PROCESS_TERMINATE
    if h:
        _k32.TerminateProcess(h, 0)
        _k32.CloseHandle(h)


def processes(process):
    """I numeri dei processi di un'app: process = (nome del programma, espressione per il percorso completo). Il nome
    puo' essere piu' d'uno, separati da «|»: un'app che cambia nome al suo programma (Copilot: mscopilot.exe, poi
    copilotapp.exe) va riconosciuta in tutte e due le versioni."""
    if not process:
        return []
    names, path = set(process[0].lower().split("|")), re.compile(process[1], re.I)
    if not sistema.WINDOWS:
        return sistema.processes(names, path)
    snapshot = _k32.CreateToolhelp32Snapshot(0x2, 0)
    if snapshot in (None, wintypes.HANDLE(-1).value):
        return []
    found, entry = [], _Entry()
    entry.dwSize = ctypes.sizeof(_Entry)
    try:
        more = _k32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.szExeFile.lower() in names:
                h = _k32.OpenProcess(0x1000, False, entry.th32ProcessID)   # solo il diritto di leggerne il percorso
                if h:
                    try:
                        text, n = ctypes.create_unicode_buffer(1024), wintypes.DWORD(1024)
                        if _k32.QueryFullProcessImageNameW(h, 0, text, ctypes.byref(n)) and path.search(text.value):
                            found.append(entry.th32ProcessID)
                    finally:
                        _k32.CloseHandle(h)
            more = _k32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snapshot)
    return found


def _package(name):
    """Il nome completo di un pacchetto dello Store installato per questo utente (con la versione), o None."""
    import winreg
    key = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            for i in range(winreg.QueryInfoKey(k)[0]):
                full = winreg.EnumKey(k, i)
                if full.lower().startswith(name.lower() + "_"):
                    return full
    except OSError:
        pass
    return None


# Apre un'app dello Store con degli argomenti: lo fa Windows, come dal menu Start (non si puo' lanciare il suo .exe)
_ACTIVATE = r"""
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
[ComImport, Guid("2e941141-7f97-4756-ba1d-9decde894a3d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IApplicationActivationManager { int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string id, [MarshalAs(UnmanagedType.LPWStr)] string args, int options, out uint pid); }
[ComImport, Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C")] public class ApplicationActivationManager {}
public static class OmissisActivate { public static uint Open(string id, string args) { uint pid; ((IApplicationActivationManager)new ApplicationActivationManager()).ActivateApplication(id, args, 0, out pid); return pid; } }
'@
[OmissisActivate]::Open($env:OMISSIS_AUMID, $env:OMISSIS_ARGS) | Out-Null
"""


def started(process):
    """Da quando gira l'app (secondi dall'epoca): il piu' vecchio dei suoi processi; 0 se e' chiusa. Serve per le app che
    leggono le impostazioni di rete solo alla partenza: dice se sono partite prima o dopo un cambio."""
    pids = processes(process)
    if not pids:
        return 0.0
    if not sistema.WINDOWS:
        return sistema.started(pids)
    times = []
    for pid in pids:
        h = _k32.OpenProcess(0x1000, False, pid)   # solo il diritto di leggerne i dati di base
        if h:
            try:
                made, ended, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
                if _k32.GetProcessTimes(h, ctypes.byref(made), ctypes.byref(ended), ctypes.byref(kernel), ctypes.byref(user)):
                    times.append(((made.dwHighDateTime << 32) + made.dwLowDateTime) / 1e7 - 11644473600)   # da FILETIME (dal 1601)
            finally:
                _k32.CloseHandle(h)
    return min(times) if times else 0.0


def find_command(app):
    if app.get("package"):
        full = _package(app["package"][0])
        # l'id con cui Windows apre l'app: famiglia del pacchetto (nome e firma dell'editore, senza versione) e id dell'app
        return f"package:{full.split('_')[0]}_{full.split('_')[-1]}!{app['package'][1]}" if full else None
    for c in app.get("commands", []):
        c = os.path.expanduser(os.path.expandvars(c))
        if Path(c).exists():
            return c
    return None


def open_unprotected(key):
    """L'app e' aperta ma non l'abbiamo avviata noi: dentro non c'e' nessuna protezione."""
    app = APP[key]
    return not app.get("own_profile") and not opened_port(app["port"]) and bool(processes(app.get("process")))


def close_app(key, grace=8):
    """Chiude l'app: prima chiede alle sue finestre di chiudersi, poi ferma cio' che resta (molte app, chiusa la finestra,
    restano accese vicino all'orologio, e finche' sono accese non si possono riavviare con la porta). Va chiamata solo quando
    chi usa il PC lo ha chiesto: quello che nell'app non era stato inviato o salvato si perde."""
    return close_process(APP[key].get("process"), grace)


def close_process(process, grace=8):
    """Come close_app, per un programma qualsiasi: (nome, espressione per il percorso completo)."""
    mine = set(processes(process))
    if not mine:
        return True
    if not sistema.WINDOWS:
        return sistema.terminate(mine, grace)

    def ask(window, _):
        pid = wintypes.DWORD()
        _u32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        if pid.value in mine and _u32.IsWindowVisible(window):
            _u32.PostMessageW(window, 0x0010, 0, 0)   # WM_CLOSE
        return True

    _u32.EnumWindows(_WINDOWS(ask), 0)
    for _ in range(grace * 4):
        if not processes(process):
            return True
        time.sleep(0.25)
    for pid in processes(process):
        h = _k32.OpenProcess(0x0001, False, pid)   # PROCESS_TERMINATE
        if h:
            _k32.TerminateProcess(h, 0)
            _k32.CloseHandle(h)
    for _ in range(20):
        if not processes(process):
            return True
        time.sleep(0.25)
    return False


def _profile_owners(folder):
    """I processi che tengono aperto il profilo che diamo a un'app con profilo suo (li abbiamo avviati noi)."""
    if not sistema.WINDOWS:
        return sistema.command_line_pids(str(folder))
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*' + $env:OMISSIS_PROFILE + '*' } | "
                              "ForEach-Object { $_.ProcessId }"], capture_output=True, timeout=30, creationflags=0x08000000,
                             env={**os.environ, "OMISSIS_PROFILE": str(folder)}).stdout
        return [int(x) for x in out.decode("ascii", errors="replace").split() if x.isdigit() and int(x) != os.getpid()]
    except Exception:   # noqa: BLE001
        return []


class Cdp:
    """Collegamento alla porta di debug: comandi con risposta ed eventi."""

    def __init__(self, port, on_event):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as r:
            info = json.loads(r.read().decode("utf-8"))
        self.product = info.get("Browser", "")
        self.ws = websocket.create_connection(info["webSocketDebuggerUrl"], suppress_origin=True, timeout=None)
        self.on_event, self.alive = on_event, True
        self.lock, self.n, self.waits = threading.Lock(), 0, {}
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            while True:
                m = json.loads(self.ws.recv())
                if "id" in m:
                    a = self.waits.pop(m["id"], None)
                    if a:
                        a[1] = m
                        a[0].set()
                else:
                    self.on_event(m)
        except Exception:   # noqa: BLE001  (app chiusa)
            pass
        finally:
            self.alive = False
            for a in list(self.waits.values()):
                a[0].set()

    def post(self, method, params=None, session=None, no_response=False):
        """Spedisce un comando senza aspettare: la risposta si raccoglie con attendi()."""
        msg = {"method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        entry = [threading.Event(), None, method]
        with self.lock:
            self.n += 1
            msg["id"] = self.n
            if not no_response:
                self.waits[self.n] = entry
            self.ws.send(json.dumps(msg, ensure_ascii=False))
        return entry

    @staticmethod
    def wait_for(entry, timeout=15):
        if not entry[0].wait(timeout) or entry[1] is None:
            raise ConnectionError(f"nessuna risposta a {entry[2]}")
        if "error" in entry[1]:
            raise RuntimeError(f"{entry[2]}: {entry[1]['error'].get('message')}")
        return entry[1].get("result", {})

    def send(self, method, params=None, session=None, timeout=15):
        entry = self.post(method, params, session, no_response=not timeout)
        return self.wait_for(entry, timeout) if timeout else None

    def close(self):
        try:
            self.ws.close()
        except Exception:   # noqa: BLE001
            pass


SHELL = r"""
const chrome = (() => {
  // attese e numeri delle richieste sono di tutta la pagina, non di questa copia: se il codice viene portato due volte
  // nello stesso documento, ogni risposta arriva comunque a chi l'ha chiesta
  const waits = globalThis.__omissis_waits || (globalThis.__omissis_waits = new Map()), ascoltatori = [];
  const data = {status: __STATUS__, suspended: false, notices: true};
  const call = globalThis.__CALL__;
  globalThis.__omissis_response = (k, r) => { const a = waits.get(k); if (a) { waits.delete(k); a(r); } };
  globalThis.__omissis_status = fresh => { data.status = fresh; for (const f of ascoltatori) f({status: {newValue: fresh}}, 'local'); };
  return {
    runtime: {id: 'omissis-connettore', sendMessage: m => new Promise((ok, no) => {
      const k = globalThis.__omissis_n = (globalThis.__omissis_n || 0) + 1;
      waits.set(k, ok);
      try { call(JSON.stringify({k, m})); } catch (e) { waits.delete(k); no(e); }
    })},
    storage: {local: {get: async () => ({...data})}, onChanged: {addListener: f => { ascoltatori.push(f); }}}
  };
})();
"""


class Connector:
    def __init__(self, port, name="app", test=None, site="", internals=()):
        """sito: il servizio a cui appartiene l'app (es. chatgpt.com), per le finestre con indirizzo interno.
        interni: altre origini da trattare come finestre interne dell'app (serve alle prove)."""
        self.port, self.name, self.site, self.internals = port, name, site, list(internals)
        self.test = os.environ.get("OMISSIS_TEST") == "1" if test is None else test
        self.engine_port = ENGINE_PORT
        self.client = name   # nome dell'app e versione, per il registro delle versioni compatibili
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as r:
                self.client = f"{name} [{activity.client_from_ua(json.loads(r.read().decode('utf-8')).get('User-Agent', ''))}]"
        except Exception:   # noqa: BLE001
            pass
        self.pool = ThreadPoolExecutor(8)
        self.sessions = {}      # sessione -> {"script": [...], "contesti": set(), "indirizzo": str}
        self.counts = {"messages": 0, "replacements": 0, "blocked": 0, "pages": 0, "at_network": 0, "checked_count": 0}
        self.errors, self.notices = [], []
        self.status = self._read_status()
        self.cdp = Cdp(port, self._event)
        # Il controllo in rete va acceso anche sul browser intero, e PRIMA di chiedere le finestre. Una finestra che l'app
        # crea gia' con il suo indirizzo comincia a caricarsi subito: la notizia che esiste ci arriva qualche millisecondo
        # dopo, e una pagina veloce in quel tempo ha gia' mandato il suo primo messaggio (visto: da 1 a 5 finestre su 20,
        # con il controllo acceso solo finestra per finestra). Sul browser intero la richiesta della pagina stessa resta
        # ferma finche' non rispondiamo noi, e a quel punto l'aggancio e' completo.
        self.browser_guard = True
        if self._models():      # senza servizi da proteggere non c'e' nulla da accendere: lo si fara' quando cambiano
            try:
                self.cdp.wait_for(self._guard(None), 5)
            except Exception as ex:   # noqa: BLE001  (un'app il cui browser non lo permette: resta il controllo finestra per finestra)
                self.browser_guard = False
                self.notices.append(f"controllo in rete sul browser intero non disponibile: {type(ex).__name__}: {ex}"[:200])
        self.cdp.send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True})
        threading.Thread(target=self._keep_updated, daemon=True).start()

    @property
    def alive(self):
        return self.cdp.alive

    @property
    def outcome(self):
        """Quanto si puo' affermare, senza promettere piu' di cio' che si e' visto:
        "no"       il codice non e' entrato in nessuna finestra, o ci sono errori: l'app NON e' protetta
        "attesa"   il codice e' entrato, ma nessun messaggio e' ancora passato da qui: non si sa se l'app manda
                   i messaggi dalle finestre (dove li vediamo) o da un'altra sua parte (dove non li vediamo)
        "si"       almeno un messaggio e' stato sostituito o controllato"""
        if self.errors or not self.counts["pages"]:
            return "no"
        return "yes" if self.counts["messages"] or self.counts["checked_count"] else "waiting"

    def close(self):
        self.cdp.close()

    # ---------------------------------------------------------------- motore
    def _bridge(self, action, data, timeout=90):
        token = (DATA / "token_extension.txt").read_text(encoding="utf-8").strip()
        req = urllib.request.Request(f"http://127.0.0.1:{self.engine_port}/bridge/{action}",
                                      data=json.dumps({**data, "via": "app", "client": self.client}).encode("utf-8"),
                                      headers={"Content-Type": "application/json", "X-Token": token})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _read_status(self):
        """Politiche dal motore; se non risponde, quelle di partenza (e i messaggi verranno bloccati)."""
        try:
            r = self._bridge("status", {}, 5)
            return {"services": r["services"], "restore": bool(r["restore"]), "block_files": bool(r["block_files"])}
        except Exception:   # noqa: BLE001
            services = [{"id": s["id"], "name": s["name"], "domains": s["domains"], "policy": catalog.default_policy(s),
                        "readable": bool(s["adapter"]), **({"box": True} if s["box"] else {})} for s in catalog.SERVICES if not s["radar"]]
            if self.test:
                services.append({"id": "test", "name": "Servizio finto", "domains": ["localhost"], "policy": "protect", "readable": True})
            return {"services": services, "restore": True, "block_files": False}

    def _keep_updated(self):
        while self.cdp.alive:
            time.sleep(15)
            fresh = self._read_status()
            if fresh == self.status:
                continue
            self.status = fresh
            if self.browser_guard:
                try:
                    self._guard(None)
                except Exception:   # noqa: BLE001
                    pass
            for sid, s in list(self.sessions.items()):
                try:
                    self._inject(sid, at_once=False)
                    self.cdp.wait_for(self._guard(sid))
                    for ctx in list(s["contexts"]):
                        self.cdp.send("Runtime.evaluate", {"expression": f"__omissis_status({json.dumps(fresh, ensure_ascii=False)})",
                                                            "contextId": ctx}, sid, timeout=0)
                except Exception:   # noqa: BLE001  (finestra chiusa nel frattempo)
                    pass

    # ---------------------------------------------------------------- codice portato nella pagina
    def _source_code(self):
        read = lambda name: (EST / name).read_text(encoding="utf-8")   # noqa: E731
        everyone = [d for s in self.status["services"] for d in s["domains"]]
        readable = [d for s in self.status["services"] if s["readable"] for d in s["domains"]]
        # Nelle pagine web conta il sito; le finestre proprie dell'app (app://, file://) si prendono tutte:
        # li' e' l'indirizzo di destinazione di ogni richiesta a dire se va protetta.
        filt = ("const __h = location.hostname, __web = /^https?:$/.test(location.protocol),\n"
                  "  __internal = (!__web && !/^(about|chrome|edge|devtools|chrome-extension|chrome-untrusted|data|blob):$/.test(location.protocol))"
                  f" || {json.dumps(self.internals)}.includes(location.origin),\n"
                  "  __in = l => __internal || (__web && l.some(d => __h === d || __h.endsWith('.' + d)));\n")
        # nelle finestre interne il codice va inserito sempre: dove mandano le richieste lo decide poi page.js
        page = "(() => {\n" + filt + f"if (!__in({json.dumps(readable)})) return;\n" + read("page.js") + "\n})();"
        shell = SHELL.replace("__STATUS__", json.dumps(self.status, ensure_ascii=False)).replace("__CALL__", CALL)
        host_site = f"if (__internal) globalThis.MSP_HOST_SITE = {json.dumps(self.site)};\n" if self.site else ""
        # le frasi degli avvisi: nell'estensione le da' il browser, qui le portiamo noi, nella lingua del programma
        language = i18n.active() if (EST / "_locales" / i18n.active() / "messages.json").exists() else "en"
        phrases = {k: v["message"] for k, v in json.loads((EST / "_locales" / language / "messages.json").read_text(encoding="utf-8")).items()}
        host_site += f"globalThis.MSP_TEXTS = {json.dumps(phrases, ensure_ascii=False)};\n"
        host_site += "globalThis.MSP_IN_APP = true;\n"   # dentro un'app, anche nelle pagine web: il connettore sa digitare (vedi _type)
        isolated = ("(() => {\n" + filt + f"if (!__in({json.dumps(everyone)}) || typeof globalThis.{CALL} !== 'function') return;\n"
                   + host_site + shell + f"if (__in({json.dumps(readable)})) {{\n" + read("channel.js") + "\n}\n" + read("content.js") + "\n})();")
        return page, isolated

    def _inject(self, sid, at_once=True, wait=True):
        """Registra il codice da eseguire in ogni documento. Con aspetta=False restituisce i comandi in corso."""
        s = self.sessions.setdefault(sid, {"script": [], "contexts": set(), "address": ""})
        for ident in s["script"]:
            self.cdp.post("Page.removeScriptToEvaluateOnNewDocument", {"identifier": ident}, sid, no_response=True)
        s["script"] = []
        page, isolated = self._source_code()
        pending = [self.cdp.post("Page.addScriptToEvaluateOnNewDocument", {"source": page, "runImmediately": at_once}, sid),
                    self.cdp.post("Page.addScriptToEvaluateOnNewDocument", {"source": isolated, "worldName": WORLD, "runImmediately": at_once}, sid)]
        if wait:
            self._collect(sid, pending)
        return pending

    def _collect(self, sid, pending):
        ident = [self.cdp.wait_for(v)["identifier"] for v in pending]
        if sid in self.sessions:
            self.sessions[sid]["script"] = ident

    # ---------------------------------------------------------------- barriera a livello di rete
    def _guard(self, sid):
        """Fa fermare dal browser ogni richiesta verso i servizi protetti, prima che parta. sid None: sul browser intero,
        cioe' anche per le finestre a cui non siamo ancora agganciati (vedi __init__)."""
        models = self._models()
        if models:
            return self.cdp.post("Fetch.enable", {"patterns": models}, sid)
        return self.cdp.post("Fetch.disable", None, sid)   # un elenco vuoto fermerebbe tutte le richieste

    def _models(self):
        models = []
        for s in self.status["services"]:
            if s["policy"] == "protect" and s["readable"]:
                for d in s["domains"]:
                    models += [{"urlPattern": f"*://{d}*", "requestStage": "Request"}, {"urlPattern": f"*://*.{d}*", "requestStage": "Request"}]
        return models

    def _at_network(self, sid, p):
        rq, rid, body = p.get("request", {}), p.get("requestId"), None
        try:
            body = rq.get("postData")
            if body is None and rq.get("hasPostData"):
                try:
                    r = self.cdp.send("Fetch.getRequestPostData", {"requestId": rid}, sid, timeout=10)
                    body = base64.b64decode(r["postData"]).decode("utf-8") if r.get("base64Encoded") else r.get("postData")
                except Exception:   # noqa: BLE001  (corpo binario o troppo grande: lo decide il ponte)
                    body = None
            kind = next((v for k, v in (rq.get("headers") or {}).items() if k.lower() == "content-type"), "")
            m = {"url": rq.get("url", ""), "method": rq.get("method", "POST"), "kind": kind, "network": True}
            if isinstance(body, str):
                m["body"] = body
            else:
                m.update(binary=True, byte=201)
            outcome = self._bridge("request", m)
        except Exception:   # noqa: BLE001  (mai inoltrare in chiaro)
            outcome = {"action": "block"}
        try:
            if outcome.get("action") == "replace" and isinstance(outcome.get("body"), str):
                self.counts["at_network"] += 1
                self.counts["messages"] += 1
                self.counts["replacements"] += int(outcome.get("replacements") or 0)
                self.cdp.send("Fetch.continueRequest", {"requestId": rid, "postData": base64.b64encode(outcome["body"].encode("utf-8")).decode("ascii")},
                               sid, timeout=0)
            elif outcome.get("action") == "passthrough":
                self.counts["checked_count"] += isinstance(body, str) and len(body) > 2
                self.cdp.send("Fetch.continueRequest", {"requestId": rid}, sid, timeout=0)
            else:
                self.counts["blocked"] += 1
                self.cdp.send("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"}, sid, timeout=0)
        except Exception:   # noqa: BLE001  (finestra chiusa nel frattempo)
            pass

    def _prepare(self, p):
        """Una finestra nuova arriva FERMA: i comandi vanno spediti tutti in fila, poi si da' il via, e solo dopo
        si raccolgono le risposte. Aspettare una risposta prima del via blocca tutto: la parte dell'app che deve
        rispondere e' proprio quella ferma (visto sull'app vera di ChatGPT)."""
        sid, info = p["sessionId"], p.get("targetInfo", {})
        kind, pending, script = info.get("type"), [], []
        try:
            if kind in ("page", "webview", "iframe"):
                self.sessions.setdefault(sid, {"script": [], "contexts": set(), "address": info.get("url", "")})
                pending.append(self._guard(sid))   # per prima: vale dal momento in cui il browser la riceve
                pending.append(self.cdp.post("Page.enable", None, sid))
                # senza Runtime.enable Chromium non consegna le chiamate fatte dal mondo isolato (provato). E' il punto
                # piu' delicato: un sito puo' accorgersi che il debug e' attivo, e una verifica anti-automazione potrebbe rifiutarlo.
                pending.append(self.cdp.post("Runtime.enable", None, sid))
                pending.append(self.cdp.post("Runtime.addBinding", {"name": CALL, "executionContextName": WORLD}, sid))
                script = self._inject(sid, wait=False)
                # finestre figlie (riquadri e viste web dentro la pagina)
                pending.append(self.cdp.post("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True}, sid))
        except Exception as ex:   # noqa: BLE001
            self.errors.append(f"{kind}: {type(ex).__name__}: {ex}"[:200])
        finally:
            if p.get("waitingForDebugger"):
                try:
                    self.cdp.post("Runtime.runIfWaitingForDebugger", None, sid, no_response=True)
                except Exception:   # noqa: BLE001
                    pass
        try:
            for v in pending:
                self.cdp.wait_for(v)
            if script:
                self._collect(sid, script)
                self.counts["pages"] += 1
        except Exception as ex:   # noqa: BLE001
            self.errors.append(f"{kind}: {type(ex).__name__}: {ex}"[:200])

    # ---------------------------------------------------------------- eventi
    def _event(self, m):
        method, p = m.get("method"), m.get("params", {})
        if method == "Target.attachedToTarget":
            self.pool.submit(self._prepare, p)
        elif method == "Target.detachedFromTarget":
            self.sessions.pop(p.get("sessionId"), None)
        elif method == "Fetch.requestPaused":
            if p.get("request", {}).get("method", "GET").upper() in ("POST", "PUT", "PATCH"):
                self.pool.submit(self._at_network, m.get("sessionId"), p)
            else:   # le letture non portano testo dell'utente: ripartono subito
                try:
                    self.cdp.send("Fetch.continueRequest", {"requestId": p.get("requestId")}, m.get("sessionId"), timeout=0)
                except Exception:   # noqa: BLE001
                    pass
        elif method == "Runtime.bindingCalled" and p.get("name") == CALL:
            self.pool.submit(self._call, m.get("sessionId"), p)

    def _call(self, sid, p):
        try:
            loading = json.loads(p["payload"])
            k, m = int(loading["k"]), loading["m"]
        except (ValueError, KeyError, TypeError):
            return
        ctx = p.get("executionContextId")
        if sid in self.sessions:
            self.sessions[sid]["contexts"].add(ctx)
        m = m if isinstance(m, dict) else {}
        r = self._type(sid, str(m.get("text", ""))) if m.get("t") == "type" else self._handle(m)
        try:
            self.cdp.send("Runtime.evaluate", {"expression": f"__omissis_response({k}, {json.dumps(r, ensure_ascii=False)})", "contextId": ctx},
                           sid, timeout=0)
        except Exception:   # noqa: BLE001
            pass

    def _type(self, sid, text):
        """Scrive la versione protetta nella casella come farebbe una persona: seleziona tutto e digita. Alcuni editor
        tengono il testo in un loro modello e ignorano cio' che la pagina cambia da sola: lo aggiorna solo chi digita
        davvero (visto dal vivo il 17/11/2026 sull'app di Copilot 157: nella casella c'era la versione protetta, ma partiva
        l'originale). La casella deve gia' avere il fuoco; se non torna uguale, chi chiama prova le altre strade."""
        try:
            self.cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65,
                                                     "modifiers": 2, "commands": ["selectAll"]}, sid)
            self.cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "modifiers": 2}, sid)
            self.cdp.send("Input.insertText", {"text": text}, sid)
            return {"ok": True}
        except Exception:   # noqa: BLE001
            return {"ok": False}

    def _handle(self, m):
        """Lo stesso lavoro che nell'estensione fa background.js."""
        t = m.get("t")
        if t in ("request", "text"):
            try:
                r = self._bridge(t, m)
            except Exception:   # noqa: BLE001  (mai inoltrare in chiaro)
                r = {"action": "block", "reason": "engine"}
            if r.get("action") == "replace":
                self.counts["messages"] += 1
                self.counts["replacements"] += int(r.get("replacements") or 0)
            elif r.get("action") == "block":
                self.counts["blocked"] += 1
            elif t == "text":
                self.counts["checked_count"] += 1
            return r
        if t == "attachment":
            try:
                r = self._bridge(t, m, 300)
            except Exception:   # noqa: BLE001  (mai lasciar partire il file in chiaro)
                r = {"action": "block", "reason": "engine"}
            if r.get("action") == "replace":
                self.counts["replacements"] += int(r.get("replacements") or 0)
            elif r.get("action") == "block":
                self.counts["blocked"] += 1
            return r
        if t in ("open_up", "chunk", "whole", "values", "websocket"):
            try:
                return self._bridge(t, m, 30)
            except Exception:   # noqa: BLE001  (restano i segnaposto)
                return {}
        if t == "visit":
            try:
                return self._bridge("visit", {"host": str(m.get("host", ""))}, 5)
            except Exception:   # noqa: BLE001
                return {}
        return {}


def _connect(app, wait=6):
    """Si collega e aspetta un momento che la prima finestra sia agganciata: subito dopo il collegamento il conto delle
    finestre e' ancora a zero, e chi guarda lo stato leggerebbe «non protetta» per un'app che lo sta per diventare."""
    c = Connector(app["port"], app["name"], site=app.get("site", ""), internals=app.get("internals", ()))
    for _ in range(wait * 10):
        if c.counts["pages"] or c.errors or not c.alive:
            break
        time.sleep(0.1)
    return c


def attach(key):
    """Si collega a un'app che ha gia' la porta aperta (avviata da qui in precedenza): None se non c'e'."""
    app = APP[key]
    if not opened_port(app["port"]):
        return None
    return _connect(app)


def reopen_app(key):
    """Chiude l'app e la riapre com'e', senza porta di collegamento: per un'app protetta dal proxy del sistema, che deve
    solo rileggere le impostazioni di rete. Va chiamata solo quando chi usa il computer lo ha chiesto."""
    app = APP[key]
    command = find_command(app)
    if command is None:
        raise Error(i18n.t("connector.error.not_installed", name=app["name"]))
    if processes(app.get("process")):
        if not close_app(key, grace=20):   # con calma: l'app deve salvare cio' che ha aperto
            raise Error(i18n.t("connector.error.not_closed", name=app["name"]))
        time.sleep(1)   # il tempo che l'app lasci andare i suoi file
    if command.startswith("package:"):
        env = {**os.environ, "OMISSIS_AUMID": command[len("package:"):], "OMISSIS_ARGS": ""}
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _ACTIVATE], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        subprocess.Popen([command, *app.get("arguments", [])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **sistema.detached())


def launch_app(key, timeout=40, close_first=False):
    """Avvia l'app con la porta di debug e ci si collega. Se l'app e' gia' aperta senza porta non la tocca e lo dice
    (AlreadyOpen), a meno che close_first non dica che chi la usa ha chiesto di chiuderla e riaprirla."""
    app = APP[key]
    command = find_command(app)
    if command is None:
        raise Error(i18n.t("connector.error.not_installed", name=app["name"]))
    if app.get("refuses"):   # provato: chiuderla per riaprirla cosi' lascerebbe solo chi la usa senza l'app
        raise Error(i18n.t("connector.error.refuses", name=app["name"]))
    if opened_port(app["port"]):
        return _connect(app)
    arguments = [f"--remote-debugging-port={app['port']}", *app.get("arguments", [])]
    if app.get("own_profile"):
        folder = DATA / "app_profiles" / key
        folder.mkdir(parents=True, exist_ok=True)
        # una copia rimasta accesa in sottofondo con questo profilo (senza porta) prenderebbe lei la finestra nuova,
        # che sarebbe senza protezione: e' roba nostra, la fermiamo prima
        for pid in _profile_owners(folder):
            _kill(pid)
        arguments.append(f"--user-data-dir={folder}")
    elif processes(app.get("process")):
        # avviarla ora porterebbe solo in primo piano la finestra che c'e' gia', senza protezione
        if not close_first:
            raise AlreadyOpen(i18n.t("connector.error.already_open", name=app["name"]))
        if not close_app(key):
            raise Error(i18n.t("connector.error.not_closed", name=app["name"]))
        time.sleep(1)   # il tempo che l'app lasci andare i suoi file
    if command.startswith("package:"):
        env = {**os.environ, "OMISSIS_AUMID": command[len("package:"):], "OMISSIS_ARGS": subprocess.list2cmdline(arguments)}
        started = subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _ACTIVATE], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        started = subprocess.Popen([command, *arguments], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   **({} if sistema.WINDOWS else {"start_new_session": True}))
    for i in range(timeout * 2):
        if opened_port(app["port"]):
            for _ in range(20):   # la porta risponde un attimo prima del servizio di debug
                try:
                    return _connect(app)
                except Exception:   # noqa: BLE001
                    time.sleep(0.5)
        # un'app che non vuole la porta di debug si chiude da sola appena la vede (lo fa Kimi): inutile aspettare, e chi
        # la usava deve sapere che ora e' chiusa. Il programma avviato puo' essere solo un lanciatore (le app dello Store):
        # conta che dopo qualche secondo non ci sia piu' nessun processo dell'app.
        if i >= 10 and app.get("process") and started.poll() is not None and not processes(app["process"]) and not opened_port(app["port"]):
            raise Error(i18n.t("connector.error.refused_now", name=app["name"]))
        time.sleep(0.5)
    raise Error(i18n.t("connector.error.port", name=app["name"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", dest="launch", choices=sorted(APP))
    ap.add_argument("--close", dest="close_first", action="store_true", help="se l'app è già aperta la chiude e la riapre protetta")
    ap.add_argument("--port", dest="port", type=int)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    try:
        c = launch_app(a.launch, close_first=a.close_first) if a.launch else Connector(a.port or 9551)
    except Error as ex:
        sys.exit(str(ex))
    print(f"collegato a {c.name} ({c.cdp.product}) sulla porta {c.port}. Ctrl+C per staccare: nell'app i messaggi verso i servizi protetti restano bloccati finché non la si riavvia.")
    try:
        last = None
        while c.alive:
            time.sleep(2)
            if c.counts != last:
                last = dict(c.counts)
                print(f"   finestre seguite {last['pages']} · messaggi protetti {last['messages']} (di cui {last['at_network']} fermati in rete)"
                      f" · dati sostituiti {last['replacements']}"
                      f" · richieste bloccate {last['blocked']}")
            for e in c.errors:
                print("   errore:", e)
            c.errors.clear()
        print("l'app è stata chiusa")
    except KeyboardInterrupt:
        c.close()
