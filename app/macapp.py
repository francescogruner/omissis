# -*- coding: utf-8 -*-
"""Omissis.app sul Mac: dove sta, spostarla in Applicazioni, farla partire all'accesso, sostituirla con una versione
nuova (tornando a quella di prima se la nuova non parte) e toglierla dal Mac.

Su Windows queste cose le fa l'installer. Sul Mac un installer non c'e', quindi le fa il programma, dal pannello.
L'app non ha la firma Apple: non usa i servizi di macOS riservati alle app firmate, ma gli strumenti che ci sono su
ogni Mac (hdiutil, ditto, xattr, launchd, /bin/sh).

  location()            "" (non e' un'app: Windows, copia dai sorgenti) | "ok" | "move" | "locked"
  move(arguments)       copia l'app nella cartella Applicazioni e la riapre da li'
  login_item(action)    l'avvio all'accesso al Mac (un file in ~/Library/LaunchAgents)
  unpack(...)           scompatta e controlla la versione nuova accanto a quella in uso (Contents.new)
  swap(...)             a programma chiuso scambia le due cartelle e riapre; se la nuova non parte rimette la vecchia
  uninstall(...)        toglie cio' che Omissis ha messo nel Mac e sposta l'app nel Cestino

L'aggiornamento cambia solo la cartella Contents dentro Omissis.app: basta poter scrivere nell'app, non nella cartella
Applicazioni. I dati di chi usa il Mac stanno in ~/Library/Application Support/Omissis e non vengono toccati.

Su Linux le stesse funzioni lavorano su una cartella fatta come l'app (Omissis.app, messa dall'installatore in
~/.local/lib/omissis) e il pacchetto e' un archivio tar invece di un'immagine disco. In piu', li':
  linux_entries(action)  la voce nel menu delle applicazioni, l'icona e il comando «omissis»
  login_item(action)     l'avvio all'accesso e' un file in ~/.config/autostart
  trash(path)            il cestino e' quello dei desktop Linux (~/.local/share/Trash)
"""
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

import sistema

HERE = Path(__file__).resolve().parent
IDENT = "eu.omissis.app"
AGENT = Path.home() / "Library" / "LaunchAgents" / f"{IDENT}.plist"
STAMP = ".omissis-update"   # dentro la versione scompattata: da quale pacchetto viene
NEW, OLD, BAD = "Contents.new", "Contents.old", "Contents.bad"
# cio' che il Python della versione nuova deve saper fare prima che le si lasci il posto: partire su questo Mac,
# caricare le librerie compilate e dire la sua versione
PREFLIGHT = ("import sys; sys.path.insert(0, sys.argv[1]); import ssl, sqlite3, version; "
             "import onnxruntime, tokenizers, mitmproxy.version; print(version.VERSION)")


class Error(Exception):
    """code: il perche' in una parola (space | package | python | swap | not_an_app | already_there). La frase per chi
    usa il Mac la sceglie chi chiama."""

    def __init__(self, code, detail=""):
        super().__init__(code + (f": {detail}" if detail else ""))
        self.code, self.detail = code, detail


def _test():
    return os.environ.get("OMISSIS_TEST") == "1"


def bundle():
    """Il pacchetto Omissis.app dentro cui gira questo codice (.../Omissis.app/Contents/Resources/omissis/app), o None:
    una copia lanciata dai sorgenti non e' un'app."""
    if sistema.WINDOWS or len(HERE.parents) < 4:
        return None
    b = HERE.parents[3]
    return b if b.suffix == ".app" and (b / "Contents" / "MacOS" / "Omissis").exists() else None


def location():
    """Come sta l'app rispetto al posto in cui si trova.
      ""        non e' un'app (Windows, copia dai sorgenti)
      "ok"      e' in un posto suo, dove chi usa il Mac puo' scrivere: si aggiorna da sola
      "move"    e' aperta dal disco di installazione o da una copia temporanea di macOS: va spostata in Applicazioni
      "locked"  l'ha installata un altro utente: questa persona non puo' sostituirla"""
    if sistema.FAKE_SYSTEM:
        return str(sistema.fake_value("mac_location") or "")
    b = bundle()
    if b is None:
        return ""
    if "/AppTranslocation/" in str(b):
        return "move"
    try:
        if os.statvfs(b).f_flag & os.ST_RDONLY:
            return "move"
    except OSError:
        pass
    return "ok" if os.access(b, os.W_OK) and os.access(b / "Contents", os.W_OK) else "locked"


def applications():
    """La cartella Applicazioni in cui questa persona puo' scrivere: quella del Mac, altrimenti la sua (~/Applications).
    OMISSIS_APPLICATIONS (solo nelle prove) ne indica un'altra."""
    if _test() and os.environ.get("OMISSIS_APPLICATIONS"):
        return Path(os.environ["OMISSIS_APPLICATIONS"])
    whole = Path("/Applications")
    return whole if os.access(whole, os.W_OK) else Path.home() / "Applications"


def _run(command, timeout=120):
    try:
        r = subprocess.run([str(c) for c in command], capture_output=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.TimeoutExpired) as ex:
        return 1, type(ex).__name__


def _unmark(path):
    """Toglie il segno «scaricata da Internet». Vale solo per copie fatte da Omissis di un'app che chi usa il Mac ha
    gia' scelto di aprire: senza, macOS rifarebbe la stessa domanda per la copia."""
    if sistema.MAC:
        _run(["xattr", "-dr", "com.apple.quarantine", path], 300)


def _copy(origin, destination):
    """Copia una cartella com'e' (collegamenti, permessi, attributi). Sul Mac con ditto, lo strumento del sistema."""
    if sistema.MAC:
        code, out = _run(["ditto", origin, destination], 900)
        if code != 0:
            raise Error("package", out[-200:])
    else:
        shutil.copytree(origin, destination, symlinks=True)


# ------------------------------------------------------------------ ripartenza

def _q(text):
    return shlex.quote(str(text))


def _launch_line(b, arguments, log=None):
    """La riga di shell che riapre l'app. Sul Mac la apre macOS («open»), come un doppio clic, e solo se «open» si
    rifiuta la si avvia direttamente; nelle prove passano anche le variabili OMISSIS_* e l'uscita va in un file.
    Fuori dal Mac (prove) si lancia il programma direttamente."""
    args = " ".join(_q(a) for a in arguments)
    out = f">> {_q(log)} 2>&1" if log else "> /dev/null 2>&1"
    direct = f"{_q(b / 'Contents' / 'MacOS' / 'Omissis')} {args} {out} &"
    if sistema.MAC and not (_test() and os.environ.get("OMISSIS_RELAUNCH") == "direct"):
        before = extra = ""
        if _test():
            extra = "".join(f" --env {_q(k + '=' + v)}" for k, v in sorted(os.environ.items()) if k.startswith(("OMISSIS_", "PLAYWRIGHT_")))
            if log:
                before, extra = f": >> {_q(log)}; ", extra + f" --stdout {_q(log)} --stderr {_q(log)}"
        return f"{before}/usr/bin/open -n {_q(b)}{extra}" + (f" --args {args}" if args else "") + f" || {{ {direct} }}"
    return direct


# aspetta la chiusura del programma (al massimo un minuto, poi lo ferma). Un processo finito ma non ancora «raccolto»
# da chi lo aveva avviato per il sistema c'e' ancora: lo si riconosce dallo stato (Z) e non lo si aspetta
_WAIT = """n=0
while kill -0 {pid} 2>/dev/null && [ $n -lt 300 ]; do
  case "$(ps -o stat= -p {pid} 2>/dev/null)" in Z*) break ;; esac
  sleep 0.2; n=$((n+1))
done
case "$(ps -o stat= -p {pid} 2>/dev/null)" in ""|Z*) ;; *) kill -9 {pid} 2>/dev/null ;; esac
"""


def _detached(script):
    """Avvia uno script di shell che deve sopravvivere a Omissis."""
    subprocess.Popen(["/bin/sh", str(script)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     cwd="/", close_fds=True, start_new_session=True)


def _script(path, text):
    """Scrive uno script di shell tutto in una volta: se ce n'e' gia' uno con quel nome in esecuzione, non lo tocca."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)
    return path


def relaunch(b, arguments, folder):
    """Riapre l'app appena questo processo e' uscito. Chi chiama deve poi chiudere il programma."""
    folder.mkdir(parents=True, exist_ok=True)
    _detached(_script(folder / "relaunch.sh", "#!/bin/sh\n# Omissis: riapre l'app appena la copia di prima e' uscita.\n" + _WAIT.format(pid=os.getpid())
                      + _launch_line(b, arguments, folder / "relaunch.log" if _test() else None) + "\n"))


# ------------------------------------------------------------------ spostarla in Applicazioni

def _linux_trash(path):
    """Il cestino dei desktop Linux: il file va in Trash/files e accanto, in Trash/info, c'e' scritto da dove viene e
    quando, cosi' dal cestino lo si puo' rimettere al suo posto. True se e' andata."""
    from urllib.parse import quote
    base = _xdg("XDG_DATA_HOME", ".local", "share") / "Trash"
    try:
        (base / "files").mkdir(parents=True, exist_ok=True)
        (base / "info").mkdir(parents=True, exist_ok=True)
        name, n = path.name, 1
        while (base / "files" / name).exists() or (base / "info" / f"{name}.trashinfo").exists():
            n += 1
            name = f"{path.stem} {n}{path.suffix}"
        (base / "info" / f"{name}.trashinfo").write_text(
            f"[Trash Info]\nPath={quote(str(path.resolve()))}\nDeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n", encoding="utf-8", newline="\n")
        try:
            shutil.move(str(path), str(base / "files" / name))
        except OSError:
            (base / "info" / f"{name}.trashinfo").unlink(missing_ok=True)
            raise
        return True
    except OSError:
        return False


def trash(path):
    """Sposta nel Cestino (non cancella). True se e' andata."""
    path = Path(path)
    if sistema.LINUX:
        return _linux_trash(path)
    if sistema.MAC:
        try:
            from Foundation import NSURL, NSFileManager
            ok, _, _ = NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(NSURL.fileURLWithPath_(str(path)), None, None)
            if ok:
                return True
        except Exception:   # noqa: BLE001  (senza le librerie di macOS si prova a mano)
            pass
    bin_ = Path.home() / ".Trash"
    try:
        bin_.mkdir(exist_ok=True)
        shutil.move(str(path), str(bin_ / f"{path.stem} {time.strftime('%H.%M.%S')}{path.suffix}"))
        return True
    except OSError:
        return False


def move(arguments, folder):
    """Copia l'app nella cartella Applicazioni e la fa ripartire da li'. Una copia piu' vecchia che fosse gia' li' va
    nel Cestino. Restituisce il percorso nuovo. Chi chiama deve poi chiudere il programma."""
    b = bundle()
    if b is None:
        raise Error("not_an_app")
    target = applications()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as ex:
        raise Error("space", str(ex)) from ex
    destination, temporary = target / b.name, target / f".{b.stem}-copia.app"
    if destination.exists() and destination.resolve() == b.resolve():
        raise Error("already_there")
    shutil.rmtree(temporary, ignore_errors=True)
    try:
        _copy(b, temporary)
        _unmark(temporary)
        if destination.exists() and not trash(destination):
            raise Error("swap", "trash")
        os.rename(temporary, destination)
    except OSError as ex:
        shutil.rmtree(temporary, ignore_errors=True)
        raise Error("swap", str(ex)) from ex
    except Error:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    relaunch(destination, arguments, folder)
    return destination


# ------------------------------------------------------------------ Linux: menu delle applicazioni, comando, avvio all'accesso

LINUX_ENTRY = "omissis.desktop"
LINUX_MARK = "X-Omissis=1"   # le voci scritte da Omissis: solo quelle vengono corrette o tolte


def _xdg(variable, *default):
    return Path(os.environ.get(variable) or Path.home().joinpath(*default))


def linux_places():
    """Dove Omissis mette le sue cose nel profilo di chi usa Linux, senza diritti di amministratore: la voce nel menu
    delle applicazioni, l'icona, il comando «omissis» e la voce di avvio all'accesso (lo standard dei desktop Linux)."""
    share, config = _xdg("XDG_DATA_HOME", ".local", "share"), _xdg("XDG_CONFIG_HOME", ".config")
    return {"menu": share / "applications" / LINUX_ENTRY, "icon": share / "icons" / "hicolor" / "256x256" / "apps" / "omissis.png",
            "command": Path.home() / ".local" / "bin" / "omissis", "login": config / "autostart" / LINUX_ENTRY}


def _desktop_quote(text):
    """Un argomento per la riga Exec di un file .desktop."""
    text = str(text)
    for char in ("\\", '"', "`", "$"):
        text = text.replace(char, "\\" + char)
    return '"' + text.replace("%", "%%") + '"'


def _desktop_text(b, arguments=(), login=False):
    icon = linux_places()["icon"]
    lines = ["[Desktop Entry]", "Type=Application", "Name=Omissis",
             "Comment=Replaces personal data before it reaches AI services", "Comment[it]=Sostituisce i dati personali prima che arrivino ai servizi AI",
             "Exec=" + " ".join([_desktop_quote(b / "Contents" / "MacOS" / "Omissis"), *arguments]),
             f"Icon={icon if icon.exists() else b / 'Contents' / 'Resources' / 'omissis.png'}", "Terminal=false", "StartupNotify=false"]
    lines += ["X-GNOME-Autostart-enabled=true"] if login else ["Categories=Utility;Security;"]
    return "\n".join([*lines, LINUX_MARK]) + "\n"


def _ours(path):
    try:
        return LINUX_MARK in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def linux_entries(action=True):
    """Su Linux: la voce nel menu delle applicazioni, l'icona e il comando «omissis» (in ~/.local/bin). Con action True li
    scrive, o li corregge se l'app è stata spostata; con False toglie quelli scritti da Omissis. Un file con quel nome
    messo da qualcun altro non viene toccato. Restituisce i nomi di ciò che ha scritto o tolto."""
    b = bundle()
    if not sistema.LINUX or (action and (b is None or location() != "ok")):
        return []
    places, done = linux_places(), []
    command = "#!/bin/sh\n# Omissis: apre il programma (se è già acceso, il suo pannello). " + LINUX_MARK + "\n" \
              + (f"exec {_q(b / 'Contents' / 'MacOS' / 'Omissis')} \"$@\"\n" if b else "")
    try:
        if not action:
            for name in ("menu", "command"):
                if _ours(places[name]):
                    places[name].unlink()
                    done.append(name)
            if places["icon"].exists() and "menu" in done:
                places["icon"].unlink()
                done.append("icon")
            return done
        source = b / "Contents" / "Resources" / "omissis.png"
        if source.exists() and (not places["icon"].exists() or places["icon"].read_bytes() != source.read_bytes()):
            places["icon"].parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, places["icon"])
            done.append("icon")
        for name, text, mode in (("menu", _desktop_text(b), 0o644), ("command", command, 0o755)):
            f = places[name]
            if f.exists() and not _ours(f):
                continue
            if not f.exists() or f.read_text(encoding="utf-8", errors="replace") != text:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(text, encoding="utf-8", newline="\n")
                f.chmod(mode)
                done.append(name)
    except OSError:
        pass
    return done


def _linux_login(b, action):
    """L'avvio all'accesso su Linux: un file in ~/.config/autostart, che GNOME, KDE, Xfce e gli altri desktop leggono.
    Si vede e si spegne anche dalle impostazioni del desktop («Applicazioni d'avvio»): se lì è stato spento, per Omissis
    è spento."""
    f, wanted = linux_places()["login"], _desktop_text(b, ["--no-browser"], login=True)
    try:
        if action is True:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(wanted, encoding="utf-8", newline="\n")
        elif action is False and (not f.exists() or _ours(f)):
            f.unlink(missing_ok=True)
    except OSError:
        pass
    try:
        return {"supported": True, "on": f.read_text(encoding="utf-8") == wanted}
    except OSError:
        return {"supported": True, "on": False}


# ------------------------------------------------------------------ avvio all'accesso

def _agent(b):
    """Cio' che si chiede a macOS: aprire l'app, come con un doppio clic, senza portarla davanti e senza aprire il
    browser. AssociatedBundleIdentifiers serve a mostrarla col suo nome tra gli elementi di login."""
    return {"Label": IDENT, "ProgramArguments": ["/usr/bin/open", "-g", str(b), "--args", "--no-browser"], "RunAtLoad": True,
            "ProcessType": "Interactive", "AssociatedBundleIdentifiers": [IDENT]}


def login_item(action=None):
    """Omissis parte da solo quando si accede al Mac? action None (solo guardare), True (si') o False (no).
    Restituisce {"supported", "on"}. E' un file in ~/Library/LaunchAgents: si vede e si spegne anche da Impostazioni di
    Sistema > Generali > Elementi login. Solo per l'app in un posto suo (non dal disco di installazione)."""
    if sistema.FAKE_SYSTEM:
        if action is not None:
            sistema._fake_system({"login_item": bool(action)})
        return {"supported": bool(sistema.fake_value("mac_location")), "on": bool(sistema.fake_value("login_item"))}
    b = bundle()
    if sistema.WINDOWS or b is None or location() != "ok":
        return {"supported": False, "on": False}
    if sistema.LINUX:
        return _linux_login(b, action)
    wanted = _agent(b)
    try:
        if action is True:
            AGENT.parent.mkdir(parents=True, exist_ok=True)
            with open(AGENT, "wb") as f:
                plistlib.dump(wanted, f)
        elif action is False:
            AGENT.unlink(missing_ok=True)
            _run(["launchctl", "bootout", f"gui/{os.getuid()}/{IDENT}"], 20)
    except OSError:
        pass
    return {"supported": True, "on": _agent_now().get("ProgramArguments") == wanted["ProgramArguments"]}


def _agent_now():
    try:
        with open(AGENT, "rb") as f:
            data = plistlib.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, plistlib.InvalidFileException):
        return {}


def login_item_follow():
    """Se l'app e' stata spostata, la voce di avvio all'accesso indica ancora il posto di prima: la si corregge.
    Non la accende se era spenta."""
    b = bundle()
    if sistema.WINDOWS or sistema.FAKE_SYSTEM or b is None or location() != "ok":
        return
    if sistema.LINUX:   # stessa cosa: se la voce e' di Omissis e accesa ma indica un altro posto, la si riscrive
        f = linux_places()["login"]
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            return
        off = "Hidden=true" in text or "X-GNOME-Autostart-enabled=false" in text
        if LINUX_MARK in text and not off and text != _desktop_text(b, ["--no-browser"], login=True):
            login_item(True)
        return
    now = _agent_now()
    if now.get("Label") == IDENT and now.get("ProgramArguments") != _agent(b)["ProgramArguments"]:
        login_item(True)


# ------------------------------------------------------------------ versione nuova

def prepared(b, version, sha256):
    """La versione scompattata accanto a quella in uso viene proprio da questo pacchetto?"""
    try:
        return json.loads((b / NEW / STAMP).read_text(encoding="utf-8")) == {"version": version, "sha256": sha256}
    except (OSError, ValueError):
        return False


def _extract(package, b):
    """Il contenuto dell'app nuova in <app>/Contents.new. Sul Mac il pacchetto e' un'immagine disco (.dmg), montata in
    sola lettura e senza farla comparire nel Finder; fuori dal Mac (prove) un archivio tar."""
    staged = b / NEW
    if sistema.MAC:
        point = Path(tempfile.mkdtemp(prefix="omissis-dmg-"))
        try:
            code, out = _run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-noverify", "-mountpoint", point, package], 300)
            if code != 0:
                raise Error("package", out[-200:])
            try:
                inside = next((p for p in sorted(point.glob("*.app")) if (p / "Contents" / "MacOS" / "Omissis").exists()), None)
                if inside is None:
                    raise Error("package", "app")
                _copy(inside / "Contents", staged)
            finally:
                _run(["hdiutil", "detach", point, "-force"], 120)
        finally:
            try:
                point.rmdir()
            except OSError:
                pass
        _unmark(staged)
    else:
        temporary = b / ".unpack"
        shutil.rmtree(temporary, ignore_errors=True)
        try:
            with tarfile.open(package) as t:
                t.extractall(temporary, filter="tar")
            inside = next((p for p in sorted(temporary.glob("*.app")) if (p / "Contents" / "MacOS" / "Omissis").exists()), None)
            if inside is None:
                raise Error("package", "app")
            os.rename(inside / "Contents", staged)
        except Error:
            raise
        except Exception as ex:   # noqa: BLE001  (un archivio rovinato si rompe in molti modi: e' sempre «pacchetto non buono»)
            raise Error("package", str(ex)[:200]) from ex
        finally:
            shutil.rmtree(temporary, ignore_errors=True)


def _check(staged, version):
    """E' proprio Omissis, in quella versione, e parte su questo computer? Solleva Error."""
    launcher = staged / "MacOS" / "Omissis"
    if not launcher.is_file() or not os.access(launcher, os.X_OK):
        raise Error("package", "launcher")
    try:
        if sistema.MAC:
            with open(staged / "Info.plist", "rb") as f:
                info = plistlib.load(f)
            if info.get("CFBundleIdentifier") != IDENT or str(info.get("CFBundleShortVersionString")) != version:
                raise Error("package", "info")
        installed = json.loads((staged / "Resources" / "omissis" / "installed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, plistlib.InvalidFileException) as ex:
        raise Error("package", type(ex).__name__) from ex
    if installed.get("version") != version or installed.get("channel") != "github":
        raise Error("package", "installed")
    python = staged / "Resources" / "python" / "bin" / "python3"
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "OMISSIS_"))}
    try:
        r = subprocess.run([str(python), "-I", "-B", "-c", PREFLIGHT, str(staged / "Resources" / "omissis" / "app")],
                           capture_output=True, text=True, timeout=240, env=env, cwd="/")
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise Error("python", type(ex).__name__) from ex
    if r.returncode != 0 or r.stdout.strip().splitlines()[-1:] != [version]:
        raise Error("python", (r.stderr or r.stdout).strip()[-200:])


def unpack(package, b, version, sha256):
    """Scompatta il pacchetto (gia' verificato da chi chiama: firma e impronta) accanto alla versione in uso e lo
    controlla. Alla fine in <app>/Contents.new c'e' la versione nuova pronta per lo scambio. Solleva Error e non
    lascia nulla a meta'."""
    package, staged = Path(package), b / NEW
    for leftover in (NEW, OLD, BAD):
        shutil.rmtree(b / leftover, ignore_errors=True)
    need = max(4 * package.stat().st_size, 400_000_000)   # la versione nuova scompattata, accanto alla vecchia
    if shutil.disk_usage(b).free < need:
        raise Error("space", str(need))
    try:
        _extract(package, b)
        _check(staged, version)
        (staged / STAMP).write_text(json.dumps({"version": version, "sha256": sha256}), encoding="utf-8")
    except Error:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    except OSError as ex:
        shutil.rmtree(staged, ignore_errors=True)
        raise Error("swap", str(ex)[:200]) from ex


_SWAP = """#!/bin/sh
# Omissis: mette al suo posto la versione nuova, gia' scompattata e controllata. Se non parte, rimette quella di prima.
APP={app}
CUR="$APP/Contents"; NEW="$APP/{new}"; OLD="$APP/{old}"; BAD="$APP/{bad}"
MARK={mark}; OUT={out}; V={version}
say() {{ printf '%s\\n' "$1" > "$OUT.tmp" && mv -f "$OUT.tmp" "$OUT"; }}
launch() {{
  {launch}
}}
# i processi partiti da dentro l'app (pannello, motore, proxy): i loro file stanno per essere sostituiti
ours() {{
  ps -axo pid=,command= | while read -r p c; do
    case "$c" in *"$APP/Contents/"*) [ "$p" != "$$" ] && kill "$1" "$p" 2>/dev/null ;; esac
  done
}}
{wait}ours -TERM; sleep 1; ours -KILL
[ -d "$NEW" ] || {{ say "failed $V"; launch; exit 1; }}
rm -f "$MARK"
rm -rf "$OLD" "$BAD"
mv "$CUR" "$OLD" || {{ say "failed $V"; launch; exit 1; }}
if ! mv "$NEW" "$CUR"; then mv "$OLD" "$CUR"; say "failed $V"; launch; exit 1; fi
touch "$APP"
launch
# la versione nuova, appena il suo pannello risponde, scrive la sua versione in questo file
n=0; ok=0
while [ $n -lt {seconds} ]; do
  if [ -f "$MARK" ] && [ "$(sed -n 1p "$MARK")" = "$V" ]; then ok=1; break; fi
  sleep 1; n=$((n+1))
done
if [ $ok = 1 ]; then rm -rf "$OLD"; say "ok $V"; exit 0; fi
# non e' partita: si torna alla versione di prima
ours -TERM; sleep 2; ours -KILL; sleep 1
if mv "$CUR" "$BAD" && mv "$OLD" "$CUR"; then rm -rf "$BAD"; touch "$APP"; say "rolled_back $V"; else say "broken $V"; fi
launch
exit 2
"""


def swap(b, version, folder, arguments, seconds=120):
    """Avvia, staccato da Omissis, lo scambio tra la versione in uso e quella scompattata. Chi chiama deve poi chiudere
    il programma: lo scambio aspetta che questo processo sia uscito. L'esito finisce in <folder>/result.txt
    («ok 0.1.6», «rolled_back 0.1.6», «failed 0.1.6»)."""
    if not (b / NEW / "MacOS" / "Omissis").exists():
        raise Error("swap", "nothing")
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("result.txt", "result.txt.tmp", "started.txt"):
        (folder / name).unlink(missing_ok=True)
    text = _SWAP.format(app=_q(b), new=NEW, old=OLD, bad=BAD, mark=_q(folder / "started.txt"), out=_q(folder / "result.txt"), version=_q(version),
                        launch=_launch_line(b, arguments, folder / "relaunch.log" if _test() else None),
                        wait=_WAIT.format(pid=os.getpid()), seconds=int(seconds))
    _detached(_script(folder / "swap.sh", text))


def outcome(folder):
    """L'esito dell'ultimo scambio: ("ok" | "rolled_back" | "failed" | "broken", versione), o None."""
    try:
        how, _, version = (folder / "result.txt").read_text(encoding="utf-8").strip().partition(" ")
    except OSError:
        return None
    return (how, version) if how in ("ok", "rolled_back", "failed", "broken") and version else None


# ------------------------------------------------------------------ toglierla dal Mac

def uninstall(data=None):
    """L'ultimo passo della disinstallazione, da chiamare quando il resto e' gia' stato tolto (avvio all'accesso,
    certificato, proxy, comando da terminale): sposta l'app nel Cestino e, se chi usa il Mac lo ha chiesto, cancella
    la cartella dei dati appena il programma e' uscito. Restituisce {"trashed": bool}."""
    b = bundle()
    linux_entries(False)   # solo su Linux: voce di menu, icona e comando messi da Omissis
    trashed = bool(b) and location() != "move" and trash(b)
    if data is not None:
        folder = Path(tempfile.mkdtemp(prefix="omissis-via-"))
        _detached(_script(folder / "remove.sh", "#!/bin/sh\n# Omissis: cancella i dati appena il programma e' uscito.\n" + _WAIT.format(pid=os.getpid())
                          + f"sleep 1\nrm -rf {_q(data)}\nrm -rf {_q(folder)}\n"))
    return {"trashed": trashed}
