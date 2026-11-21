# -*- coding: utf-8 -*-
"""Ciò che cambia da un sistema operativo all'altro: Windows, macOS e Linux.

Il resto del programma chiede qui invece di chiamare direttamente le API di un sistema. Su Windows queste funzioni
fanno esattamente quello che il programma faceva già; dove un sistema non ha una cosa lo dicono (False, None o un
elenco vuoto) invece di fingere.
"""
import os
import plistlib
import re
import secrets
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"
LINUX = not WINDOWS and not MAC
NAME = "windows" if WINDOWS else "mac" if MAC else "linux"
NO_WINDOW = 0x08000000 if WINDOWS else 0   # CREATE_NO_WINDOW; fuori da Windows creationflags deve restare 0
KEYCHAIN = Path.home() / "Library" / "Keychains" / "login.keychain-db"
# solo per le prove: un file che fa da impostazioni del computer (certificati fidati, proxy), per non toccare quelle vere
FAKE_SYSTEM = os.environ.get("OMISSIS_FAKE_SYSTEM")


def detached():
    """Argomenti di Popen per un programma che deve sopravvivere a Omissis (un'app riaperta, l'aggiornamento)."""
    if WINDOWS:
        return {"creationflags": 0x00000008 | 0x00000200}   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    return {"start_new_session": True}


def user_data():
    """Dove una copia installata tiene i dati dell'utente."""
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Omissis"
    if MAC:
        return Path.home() / "Library" / "Application Support" / "Omissis"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "omissis"


def open_path(path):
    """Apre una cartella (o un file) con il programma predefinito del sistema."""
    if WINDOWS:
        os.startfile(path)   # noqa: S606  (una cartella, non un programma)
    else:
        subprocess.Popen(["open" if MAC else "xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _quoted(text):
    """Una stringa per AppleScript."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify(message, title="Omissis"):
    """Notifica del sistema: sul Mac con AppleScript, su Linux con notify-send, se c'è (su Windows la fa l'icona
    vicino all'orologio). True se è partita."""
    if WINDOWS:
        return False
    try:
        if MAC:
            command = ["osascript", "-e", f"display notification {_quoted(message)} with title {_quoted(title)}"]
        else:
            tool = shutil.which("notify-send")
            if not tool:
                return False
            command = [tool, "--app-name=Omissis", "--icon=omissis", str(title), str(message)]
        subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def choose_folder(title):
    """Finestra del sistema per scegliere una cartella: il percorso, o None se si annulla. Sul Mac la apre AppleScript;
    su Linux zenity (GNOME e simili) o kdialog (KDE), se uno dei due c'è."""
    if WINDOWS:
        return None
    if MAC:
        command = ["osascript", "-e", f"POSIX path of (choose folder with prompt {_quoted(title)})"]
    elif shutil.which("zenity"):
        command = ["zenity", "--file-selection", "--directory", f"--title={title}"]
    elif shutil.which("kdialog"):
        command = ["kdialog", "--title", str(title), "--getexistingdirectory", str(Path.home())]
    else:
        return None
    try:
        r = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() or None if r.returncode == 0 else None


# ------------------------------------------------------------------ finestre del pannello

def _mac_browser():
    """Un browser Chromium installato sul Mac (serve per le finestre senza barre): il suo eseguibile, o None."""
    for app, binary in (("Microsoft Edge", "Microsoft Edge"), ("Google Chrome", "Google Chrome"), ("Brave Browser", "Brave Browser"),
                        ("Chromium", "Chromium")):
        for base in (Path("/Applications"), Path.home() / "Applications"):
            exe = base / f"{app}.app" / "Contents" / "MacOS" / binary
            if exe.exists():
                return exe
    return None


def _linux_browser():
    """Un browser Chromium installato su Linux (Chrome, Edge, Brave, Chromium, anche da Snap): il suo comando, o None."""
    for name in ("google-chrome", "google-chrome-stable", "microsoft-edge", "microsoft-edge-stable", "brave-browser", "brave",
                 "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def chromium_browser():
    """Un browser Chromium installato su questo computer, fuori da Windows: il suo eseguibile, o None."""
    return _mac_browser() if MAC else _linux_browser() if LINUX else None


def app_window(address, size=(520, 720)):
    """Apre l'indirizzo in una finestra piccola senza barra degli indirizzi (Edge o Chrome come app); se non ce n'è
    uno, nel browser predefinito."""
    exe = None
    if WINDOWS:
        for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
            edge = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if base and edge.exists():
                exe = edge
                break
    else:
        exe = chromium_browser()
    if exe:
        subprocess.Popen([str(exe), f"--app={address}", f"--window-size={size[0]},{size[1]}"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **({} if WINDOWS else {"start_new_session": True}))
    else:
        webbrowser.open(address)


# ------------------------------------------------------------------ processi (fuori da Windows)

def processes(names, path):
    """I numeri dei processi che hanno uno dei nomi (minuscoli) e un percorso completo che soddisfa l'espressione."""
    import psutil
    found = []
    for p in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name, exe = (p.info["name"] or "").lower(), p.info["exe"] or ""
        except (psutil.Error, KeyError):
            continue
        if name in names and exe and path.search(exe):
            found.append(p.info["pid"])
    return found


def running_names():
    """I nomi (minuscoli) dei programmi in esecuzione, con il percorso completo quando si può leggere."""
    import psutil
    out = []
    for p in psutil.process_iter(["name", "exe"]):
        try:
            out.append(((p.info["name"] or "").lower(), p.info["exe"] or ""))
        except (psutil.Error, KeyError):
            continue
    return out


def terminate(pids, grace=8):
    """Chiede ai processi di chiudersi (le app del Mac, ricevuto SIGTERM, chiudono come da menu), poi ferma i rimasti.
    True se alla fine non ne resta nessuno."""
    import psutil
    procs = []
    for pid in pids:
        try:
            procs.append(psutil.Process(pid))
        except psutil.Error:
            pass
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(procs, timeout=grace)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(alive, timeout=5)

    def gone(p):   # un processo finito ma non ancora «raccolto» da chi lo aveva avviato non gira piu'
        try:
            return not p.is_running() or p.status() == psutil.STATUS_ZOMBIE
        except psutil.Error:
            return True
    return all(gone(p) for p in alive)


def started(pids):
    """Da quando gira il piu' vecchio di questi processi (secondi dall'epoca); 0 se non ce n'e' nessuno."""
    import psutil
    times = []
    for pid in pids:
        try:
            times.append(psutil.Process(pid).create_time())
        except psutil.Error:
            pass
    return min(times) if times else 0.0


def command_line_pids(fragment):
    """I processi la cui riga di comando contiene il testo (escluso questo)."""
    import psutil
    out = []
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            if p.info["pid"] != os.getpid() and fragment in " ".join(p.info["cmdline"] or []):
                out.append(p.info["pid"])
        except (psutil.Error, KeyError):
            continue
    return out


# ------------------------------------------------------------------ programmi installati sul Mac

def mac_applications():
    """[(nome, versione)] delle app in /Applications e ~/Applications (anche una cartella più giù, come Utility)."""
    out = []
    for base in (Path("/Applications"), Path.home() / "Applications"):
        if not base.is_dir():
            continue
        for app in [*base.glob("*.app"), *base.glob("*/*.app")]:
            name, version = app.stem, ""
            try:
                with open(app / "Contents" / "Info.plist", "rb") as f:
                    info = plistlib.load(f)
                name = str(info.get("CFBundleDisplayName") or info.get("CFBundleName") or name)
                version = str(info.get("CFBundleShortVersionString") or "")
            except (OSError, ValueError, plistlib.InvalidFileException):
                pass
            out.append((name, version))
    return out


def linux_applications():
    """[(nome, versione)] dei programmi con una voce nel menu delle applicazioni di Linux (file .desktop): pacchetti del
    sistema, Flatpak, Snap e voci dell'utente. La versione lì non c'è: resta vuota."""
    share = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    folders = [Path("/usr/share/applications"), Path("/usr/local/share/applications"), Path("/var/lib/flatpak/exports/share/applications"),
               Path("/var/lib/snapd/desktop/applications"), share / "applications", share / "flatpak" / "exports" / "share" / "applications"]
    names = set()
    for folder in folders:
        try:
            files = sorted(folder.glob("*.desktop"))
        except OSError:
            continue
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            entry = text.split("[Desktop Entry]", 1)[-1].split("\n[", 1)[0]   # solo la voce principale, non le sue azioni
            name = re.search(r"^Name=(.+)$", entry, re.M)
            if name and re.search(r"^Type=Application\s*$", entry, re.M) and not re.search(r"^Hidden=true\s*$", entry, re.M):
                names.add(name.group(1).strip())
    return [(name, "") for name in sorted(names, key=str.lower)]


def mac_app(name):
    """Il percorso di un'app del Mac («Claude» → /Applications/Claude.app), o None."""
    for base in (Path("/Applications"), Path.home() / "Applications"):
        if (base / f"{name}.app").is_dir():
            return base / f"{name}.app"
    return None


# ------------------------------------------------------------------ lingua

def language():
    """Il codice della lingua in cui l'utente usa il sistema (es. "it"), o None."""
    try:
        if WINDOWS:
            import ctypes
            import locale
            name = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage())
            return name.split("_")[0].lower() if name else None
        if MAC:
            r = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=10)
            m = re.search(r"[\"\s(]([a-z]{2,3})[-_\"]", r.stdout)
            return m.group(1) if m else None
        value = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
        return value.split("_")[0].split(".")[0].lower() or None
    except Exception:   # noqa: BLE001
        return None


# ------------------------------------------------------------------ segreti e certificato

def keychain_secret(account):
    """Un segreto di 32 byte nel portachiavi dell'utente (servizio «Omissis»), creato al primo uso. None dove non c'è.
    Sul Mac è il Portachiavi; su Linux il «Secret Service» del desktop (GNOME Keyring, KWallet, KeePassXC), che la
    libreria keyring raggiunge senza altri programmi. Se è chiuso a chiave lo fa aprire lui, con la sua finestra.
    OMISSIS_FAKE_KEYCHAIN (solo per le prove) indica un file che fa da portachiavi."""
    fake = os.environ.get("OMISSIS_FAKE_KEYCHAIN")
    if fake and not WINDOWS:
        import json
        f = Path(fake)
        data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        if account not in data:
            data[account] = secrets.token_hex(32)
            f.write_text(json.dumps(data), encoding="utf-8")
        return bytes.fromhex(data[account])
    if WINDOWS:
        return None
    try:
        import keyring
        value = keyring.get_password("Omissis", account)
        if not value:
            value = secrets.token_hex(32)
            keyring.set_password("Omissis", account, value)
        return bytes.fromhex(value)
    except Exception:   # noqa: BLE001  (niente Portachiavi: l'archivio resta come fuori da Windows, e lo dice)
        return None


def keychain_forget(account):
    """Toglie dal Portachiavi il segreto creato da keychain_secret: serve quando chi usa il Mac cancella i dati di
    Omissis (senza l'archivio quella chiave non apre piu' nulla)."""
    fake = os.environ.get("OMISSIS_FAKE_KEYCHAIN")
    try:
        if fake and not WINDOWS:
            import json
            f = Path(fake)
            data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
            if data.pop(account, None) is not None:
                f.write_text(json.dumps(data), encoding="utf-8")
        elif not WINDOWS:
            import keyring
            keyring.delete_password("Omissis", account)
    except Exception:   # noqa: BLE001  (non c'era, o il Portachiavi non risponde: non c'e' altro da fare)
        pass


def _fake_system(change=None):
    """Solo per le prove (OMISSIS_FAKE_SYSTEM): un file che fa da impostazioni del computer, per non toccare quelle vere."""
    import json
    f = Path(FAKE_SYSTEM)
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if change:
        data.update(change)
        f.write_text(json.dumps(data), encoding="utf-8")
    return data


def fake_value(name, default=None):
    """Una voce del sistema finto delle prove (per esempio da quando «gira» un'app); default se non c'e'."""
    return _fake_system().get(name, default) if FAKE_SYSTEM else default


def _thumbprint(cer):
    """L'impronta SHA-1 del certificato, come la chiama Windows: riconosce proprio questo, non uno con lo stesso nome."""
    import base64
    import hashlib
    raw = Path(cer).read_bytes()
    m = re.search(rb"-----BEGIN CERTIFICATE-----(.+?)-----END CERTIFICATE-----", raw, re.S)
    return hashlib.sha1(base64.b64decode(m.group(1)) if m else raw).hexdigest()


def certificate(cer, action=None):
    """Il certificato del proxy tra quelli di cui il sistema si fida: action None (solo guardare), "install" o "remove".
    True se adesso il sistema si fida. Su Windows va nell'archivio dell'utente e Windows chiede conferma; sul Mac nel
    portachiavi di login, dove macOS chiede la password a chi usa il Mac. Sono scelte sue: non si fanno al suo posto."""
    if FAKE_SYSTEM:
        data = _fake_system()
        if action == "install" and not data.get("refuse_certificate"):
            data = _fake_system({"certificate": True})
        elif action == "remove":
            data = _fake_system({"certificate": False})
        return bool(data.get("certificate"))
    if WINDOWS:
        if not Path(cer).exists():
            return False
        mark = _thumbprint(cer)

        def there(*where):   # nell'archivio dell'utente o in quello del computer (dove lo mette chi amministra i PC)
            r = subprocess.run(["certutil", *where, "-store", "Root", mark], capture_output=True, timeout=30, creationflags=NO_WINDOW)
            return r.returncode == 0 and b"mitmproxy" in r.stdout
        if action == "install" and not (there("-user") or there()):
            subprocess.run(["certutil", "-user", "-addstore", "Root", str(cer)], capture_output=True, timeout=120, creationflags=NO_WINDOW)
        elif action == "remove":
            subprocess.run(["certutil", "-user", "-delstore", "Root", mark], capture_output=True, timeout=120, creationflags=NO_WINDOW)
        return there("-user") or there()
    if MAC:
        pem = Path(cer).with_suffix(".pem")
        if not pem.exists():
            return False

        def trusted():   # che il certificato sia nel portachiavi non basta: conta che il sistema se ne fidi
            return subprocess.run(["security", "verify-cert", "-c", str(pem)], capture_output=True, timeout=60).returncode == 0
        try:
            if action == "install" and not trusted():
                subprocess.run(["security", "add-trusted-cert", "-r", "trustRoot", "-k", str(KEYCHAIN), str(pem)],
                               capture_output=True, timeout=300)
            elif action == "remove":
                subprocess.run(["security", "remove-trusted-cert", str(pem)], capture_output=True, timeout=300)
                subprocess.run(["security", "delete-certificate", "-c", "mitmproxy", str(KEYCHAIN)], capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:   # la domanda di macOS e' rimasta senza risposta
            pass
        return trusted()
    return False


# ------------------------------------------------------------------ proxy del sistema (file PAC)

def _windows_proxy(pac=None, change=False):
    """Le impostazioni di proxy dell'utente (quelle di «Opzioni Internet», che usano i browser e le app fatte con
    Chromium). Con change mette l'indirizzo del file PAC (o lo toglie, con pac vuoto) e non tocca il resto."""
    import ctypes
    from ctypes import wintypes

    class Value(ctypes.Union):
        _fields_ = [("number", wintypes.DWORD), ("text", wintypes.LPWSTR), ("time", wintypes.FILETIME)]

    class Option(ctypes.Structure):
        _fields_ = [("option", wintypes.DWORD), ("value", Value)]

    class Options(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("connection", wintypes.LPWSTR), ("count", wintypes.DWORD),
                    ("error", wintypes.DWORD), ("options", ctypes.POINTER(Option))]

    class Seen(ctypes.Structure):
        _fields_ = [("auto", wintypes.BOOL), ("pac", ctypes.c_void_p), ("proxy", ctypes.c_void_p), ("bypass", ctypes.c_void_p)]
    wininet, winhttp = ctypes.WinDLL("wininet", use_last_error=True), ctypes.WinDLL("winhttp", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    wininet.InternetSetOptionW.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    wininet.InternetSetOptionW.restype = wintypes.BOOL
    wininet.InternetQueryOptionW.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    wininet.InternetQueryOptionW.restype = wintypes.BOOL
    if change:
        one = (Option * 1)()
        one[0].option = 1   # il tipo di collegamento: 1 diretto, 2 proxy fisso, 4 file PAC, 8 ricerca automatica
        listing, size = Options(ctypes.sizeof(Options), None, 1, 0, one), wintypes.DWORD(ctypes.sizeof(Options))
        kind = one[0].value.number if wininet.InternetQueryOptionW(None, 75, ctypes.byref(listing), ctypes.byref(size)) else 1
        two = (Option * 2)()
        two[0].option, two[0].value.number = 1, ((kind | 4) if pac else (kind & ~4)) | 1
        two[1].option, two[1].value.text = 4, pac or ""
        listing = Options(ctypes.sizeof(Options), None, 2, 0, two)
        if not wininet.InternetSetOptionW(None, 75, ctypes.byref(listing), ctypes.sizeof(listing)):
            raise OSError(ctypes.get_last_error(), "InternetSetOption")
        wininet.InternetSetOptionW(None, 39, None, 0)   # «le impostazioni sono cambiate»: i programmi aperti le rileggono
        wininet.InternetSetOptionW(None, 37, None, 0)
    seen = Seen()
    if not winhttp.WinHttpGetIEProxyConfigForCurrentUser(ctypes.byref(seen)):
        return {"supported": True, "pac": "", "proxy": ""}
    out = {"supported": True, "pac": ctypes.wstring_at(seen.pac) if seen.pac else "", "proxy": ctypes.wstring_at(seen.proxy) if seen.proxy else ""}
    for pointer in (seen.pac, seen.proxy, seen.bypass):
        if pointer:
            kernel32.GlobalFree(pointer)
    return out


def _mac_proxy():
    """Il proxy in vigore sul Mac (quello del collegamento di rete in uso)."""
    r = subprocess.run(["scutil", "--proxy"], capture_output=True, text=True, timeout=30)
    seen = dict(re.findall(r"^\s*(\w+) : (\S+)\s*$", r.stdout, re.M))
    pac = seen.get("ProxyAutoConfigURLString", "") if seen.get("ProxyAutoConfigEnable") == "1" else ""
    fixed = [f"{seen.get(k + 'Proxy', '')}:{seen.get(k + 'Port', '')}" for k in ("HTTPS", "HTTP", "SOCKS") if seen.get(k + "Enable") == "1"]
    return {"supported": True, "pac": pac, "proxy": fixed[0] if fixed else ""}


def _mac_pac(pac, ask):
    """Mette (o toglie) il file PAC su tutti i collegamenti di rete attivi. Chi amministra il Mac lo puo' fare senza
    password (provato su macOS 26); per gli altri, e solo con ask, lo chiede macOS con la sua finestra."""
    import shlex
    r = subprocess.run(["networksetup", "-listallnetworkservices"], capture_output=True, text=True, timeout=30)
    services = [line.strip() for line in r.stdout.splitlines()[1:] if line.strip() and not line.startswith("*")]
    commands = [["networksetup", "-setautoproxyurl", s, pac] if pac else ["networksetup", "-setautoproxystate", s, "off"] for s in services]

    def done():
        return _mac_proxy()["pac"] == pac
    for c in commands:
        try:
            subprocess.run(c, capture_output=True, timeout=20)
        except subprocess.TimeoutExpired:
            break
    if done() or not ask:
        return done()
    script = "; ".join(" ".join(shlex.quote(x) for x in c) for c in commands)
    quoted = script.replace("\\", "\\\\").replace('"', '\\"')
    try:
        subprocess.run(["osascript", "-e", f'do shell script "{quoted}" with administrator privileges'], capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        pass
    return done()


def system_proxy():
    """Il proxy impostato nel sistema per chi usa il computer: {"supported", "pac", "proxy"}. Serve a non toccare quello
    che una persona, o la sua azienda, ha gia' messo."""
    if FAKE_SYSTEM:
        data = _fake_system()
        return {"supported": True, "pac": str(data.get("pac") or ""), "proxy": str(data.get("proxy") or "")}
    try:
        if WINDOWS:
            return _windows_proxy()
        if MAC:
            return _mac_proxy()
    except Exception:   # noqa: BLE001
        pass
    return {"supported": False, "pac": "", "proxy": ""}


def system_pac(address, ask=False):
    """Mette nel sistema l'indirizzo di un file PAC, o lo toglie (address vuoto). True se adesso il sistema ha quello
    chiesto. Su Windows vale per l'utente e non chiede nulla; sul Mac, se serve chi lo amministra, lo chiede solo con ask."""
    address = address or ""
    if FAKE_SYSTEM:
        if _fake_system().get("refuse_network"):
            return False
        _fake_system({"pac": address})
        return True
    try:
        if WINDOWS:
            return _windows_proxy(address, change=True)["pac"] == address
        if MAC:
            return _mac_pac(address, ask)
    except Exception:   # noqa: BLE001
        pass
    return False


def mac_profile(domain):
    """Le impostazioni di un profilo di configurazione del Mac (quelle che manda chi amministra i Mac, con un MDM)."""
    if not MAC:
        return {}
    for path in (Path("/Library/Managed Preferences") / f"{domain}.plist",
                 Path("/Library/Managed Preferences") / os.environ.get("USER", "") / f"{domain}.plist"):
        try:
            with open(path, "rb") as f:
                data = plistlib.load(f)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue
    return {}


def which(name):
    """Un comando nel PATH; sul Mac anche nei posti dove li mettono gli installatori ma che le app non vedono nel PATH."""
    found = shutil.which(name)
    if found or WINDOWS:
        return found
    for base in (Path.home() / ".local" / "bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path.home() / ".npm-global" / "bin",
                 Path.home() / ".claude" / "local"):
        if (base / name).exists():
            return str(base / name)
    return None
