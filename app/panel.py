# -*- coding: utf-8 -*-
"""Programma di gestione di Omissis: avvia e ferma motore e proxy, mostra cosa succede e permette
di cambiare le impostazioni da una pagina locale (http://127.0.0.1:8766) e da un'icona vicino
all'orologio.

  .venv\\Scripts\\python.exe panel.py [--no-tray] [--no-browser] [--no-start] [--test]

La pagina risponde solo a questo PC e solo a chi presenta il codice generato all'avvio (e' dentro
la pagina stessa): un altro sito aperto nel browser non puo' comandare il programma.
"""
import argparse
import base64
import collections
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import updates
import clipboard
import activity
import catalog
import central
import connector
import documents
import folders
import gateway
import inventory
import hook_command
import kimi_plugin
import macapp
import mcp_server
import onboarding
import settings
import i18n
import weights
import paths
import report
import remote
import restore
import scan
import sistema
from version import VERSION

HERE = Path(__file__).resolve().parent
DATA = paths.DATA
PY_MODEL = paths.python_model()
LISTS = paths.lists()
PANEL_PORT, ENGINE_PORT = paths.PANEL_PORT, paths.ENGINE_PORT
NO_WINDOW = sistema.NO_WINDOW   # niente finestra nera per i programmi avviati (solo Windows)
CODE = secrets.token_urlsafe(24)
PAGE = HERE / "panel"   # i file della pagina: index.html, style.css, app.js, icon.svg, locales\<codice>.json
ENGINE_SCRIPT = HERE / "engine.py"   # il programma del motore (le prove ne mettono uno finto, che non carica un modello)
RESTARTS, WINDOW = 3, 600   # un processo caduto a protezione accesa: quante volte si riparte da soli, e in quanti secondi
# Un processo puo' essere vivo e non rispondere piu'. A protezione accesa si chiede a motore e proxy se ci sono: ogni PROBE
# secondi, aspettando la risposta PROBE_TIMEOUT secondi; dopo SILENT silenzi di fila li si da' per bloccati (oltre un minuto)
PROBE, PROBE_TIMEOUT, SILENT = 15, 5, 4
# Il motore risponde, ha richieste in lavorazione, e da STALL secondi non finisce nemmeno un giro del modello. Conta se il
# lavoro avanza, non quanto dura: un documento lungo sono tanti giri brevi, e su un PC lento puo' durare quanto serve
STALL = 600
ALIVE = "http://omissis.invalid/__omissis__/here"   # a questo indirizzo il nostro proxy risponde da solo, senza uscire in rete
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # per parlare con questo computer senza passare da un proxy
STATIC = {"/style.css": "text/css; charset=utf-8", "/app.js": "text/javascript; charset=utf-8", "/icon.svg": "image/svg+xml",
          "/welcome.mp4": "video/mp4", "/welcome.jpg": "image/jpeg"}   # il video del primo avvio e la sua copertina
RX_LANGUAGE = re.compile(r"/locales/[a-z]{2,3}(-[A-Za-z]{2,4})?\.json")
# la pagina carica solo file suoi: niente script o stili scritti dentro l'HTML, nessuna risorsa da fuori
POLICY_PAGE = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; media-src 'self'; connect-src 'self'; "
                   "base-uri 'none'; frame-ancestors 'none'")
# quanto e' provata la lettura di ciascun servizio: la pagina traduce il codice (servizi.lettura.<codice>)
READING_STATUS = {"claude": "tested", "chatgpt": "tested", "anthropic": "tested", "openai": "tested",
                 "gemini": "experimental", "generic": "generic", None: "no"}


SHORTCUTS = None        # le scorciatoie da tastiera (clipboard.Scorciatoie), quando c'e' l'icona vicino all'orologio
NOTIFY = None             # funzione che mostra una notifica di Windows, quando c'e' l'icona
FOLDERS = set()          # cartelle scelte o prodotte in questa sessione: le sole che la pagina puo' far aprire
EVERY = {"daily": 86400, "weekly": 7 * 86400}   # ogni quanto si ripete l'analisi degli strumenti AI


class Refusal(Exception):
    """Una richiesta della pagina che non si puo' esaudire: il messaggio e' per l'utente, nella sua lingua."""


def guard(*keys, changes=None):
    """Ferma il cambio di un'impostazione imposta da chi amministra il PC (managed.py)."""
    lock, current = settings.locked()["keys"], settings.read()
    for k in keys:
        if k in lock and (changes is None or changes.get(k) != current.get(k)):
            raise Refusal(i18n.t("managed.locked"))


def opened_port(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port(port):
    """La porta e' libera su questo PC: nessuno risponde e la si puo' prendere. Chi risponde va guardato per primo: su
    Windows un programma che ascolta su tutte le interfacce lascia prendere la stessa porta su 127.0.0.1, e il proxy
    partirebbe portandogli via il traffico."""
    if opened_port(port):
        return False
    with socket.socket() as s:
        if os.name != "nt":   # come fa il proxy: una porta appena lasciata si riprende subito
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def spare_ports():
    """Le porte di riserva del proxy, per quando quella scelta e' occupata: venti porte poco usate, cento sopra quelle di
    Omissis (con le porte di serie, da 8865 a 8884)."""
    return range(ENGINE_PORT + 100, ENGINE_PORT + 120)


def leftovers(kind):
    """I processi di questa copia rimasti accesi da un avvio precedente, quando il pannello si e' chiuso senza poterli
    fermare: il motore sulla nostra porta ("engine"), o il proxy che usa la nostra cartella dei dati ("proxy"). Si
    riconoscono dagli argomenti con cui sono stati avviati, uguali a quelli che usa questa copia: il programma del motore
    con la nostra porta, il proxy con il nostro addon e la nostra cartella. Quelli di un'altra copia non c'entrano, e
    nemmeno un programma che questi percorsi li nomina soltanto (una finestra del terminale, un editor)."""
    def same(a, b):
        return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))

    def ours(a):
        if kind == "engine":
            return len(a) > 1 and same(a[1], ENGINE_SCRIPT) and any(x == "--port" and y == str(ENGINE_PORT) for x, y in zip(a, a[1:]))
        return ("mitmdump" in " ".join(a[:3]).lower() and any(x == "-s" and same(y, HERE / "addon.py") for x, y in zip(a, a[1:]))
                and any(x.startswith("confdir=") and same(x[8:], DATA / "ca") for x in a))
    return [pid for pid, arguments in sistema.command_lines(ENGINE_SCRIPT if kind == "engine" else HERE / "addon.py") if ours(arguments)]


def _by(name):
    """Il nome di un programma dentro il motivo in breve di un errore (finisce nella segnalazione): lettere, cifre e pochi segni."""
    return " by " + re.sub(r"[^\w.+-]", "_", name)[:40] if name else ""


def close_leftovers(kind):
    """Chiude i processi rimasti da un avvio precedente e dice quanti erano."""
    pids = leftovers(kind)
    for pid in pids:
        try:
            connector._kill(pid)
        except Exception:   # noqa: BLE001  (chi chiama guarda se la porta si e' liberata)
            pass
    return len(pids)


class Output:
    """Le ultime righe di errore scritte da un processo, tenute solo in memoria finche' il programma e' acceso: servono a
    capire perche' si e' chiuso. Non vanno su disco e non escono mai cosi' come sono: vedi closed_for."""

    def __init__(self, stream):
        self.lines = collections.deque(maxlen=40)
        threading.Thread(target=self._read, args=(stream,), daemon=True).start()

    def _read(self, stream):
        try:
            for raw in stream:
                self.lines.append(raw.decode("utf-8", "replace").strip())
        except (OSError, ValueError):   # il processo e' stato chiuso
            pass


_ERROR_KIND = re.compile(r"(?:[A-Za-z_]\w*\.)*(_?[A-Z]\w{0,40}?(?:Error|Exception))(?=:|$)")
_ERROR_CODE = re.compile(r"\[(errno|winerror) (-?\d{1,6})\]", re.I)


def closed_for(process):
    """Perche' un processo si e' chiuso, per quanto si puo' dire senza riportare cio' che ha scritto: (codice di uscita,
    [tipi di errore di Python a inizio riga e codici di sistema come «[Errno 10048]»]). Mai il testo dei messaggi."""
    code = process.poll() if process is not None else None
    if code is not None:
        time.sleep(0.2)   # il tempo di leggere le sue ultime righe
    if isinstance(code, int) and code > 0xFFFF:   # su Windows i guasti gravi hanno codici che si leggono in esadecimale
        code = f"0x{code:08X}"
    kinds = []
    for line in list(getattr(getattr(process, "output", None), "lines", ())):
        found = _ERROR_KIND.match(line)
        codes = [f"[{'WinError' if k.lower() == 'winerror' else 'Errno'} {n}]" for k, n in _ERROR_CODE.findall(line)]
        for kind in ([found.group(1)] if found else []) + codes:
            if kind not in kinds:
                kinds.append(kind)
    return code, kinds[-4:]


class Failure(RuntimeError):
    """Un avvio non riuscito: il testo per chi usa il programma e, a parte, il motivo in breve per la segnalazione."""

    def __init__(self, text, cause=""):
        super().__init__(text)
        self.cause = cause


def engine(path, data=None, timeout=60):
    token = (DATA / "token.txt").read_text(encoding="utf-8").strip()
    req = urllib.request.Request(f"http://127.0.0.1:{ENGINE_PORT}{path}", headers={"X-Token": token, "Content-Type": "application/json"},
                                  data=json.dumps(data).encode("utf-8") if data is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


_MANUAL = {"log": None, "last": ""}
_manual_lock = threading.Lock()


def record_manual(via, counts, text=None):
    """L'uso manuale (sezione Testo, appunti e scorciatoie, documenti) entra nel registro come ogni altra richiesta:
    solo i conteggi, mai il testo. Lo stesso testo mascherato piu' volte di fila (succede a ogni correzione fatta a mano)
    conta una volta: se ne ricorda l'impronta, in memoria e basta."""
    counts = {str(k): int(n) for k, n in (counts or {}).items() if isinstance(n, int) and n > 0}
    if not counts:
        return
    with _manual_lock:
        if text is not None:
            mark = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
            if mark == _MANUAL["last"]:
                return
            _MANUAL["last"] = mark
        try:
            if _MANUAL["log"] is None:
                _MANUAL["log"] = activity.Log()
            _MANUAL["log"].write(service="manual", via=via, event="masked", replacements=counts)
        except Exception:   # noqa: BLE001  (il registro non deve mai fermare il lavoro)
            pass


def manual(via):
    """Il motore, per l'uso manuale: ogni mascheramento riuscito viene segnato nel registro."""
    def call(path, data=None, timeout=60):
        r = engine(path, data, timeout)
        if path == "/mask":
            record_manual(via, r.get("counts"))
        return r
    return call


class Supervisor:
    """Tiene in vita i due processi: il motore (modello) e il proxy (mitmproxy)."""

    def __init__(self, test=False):
        self.engine = self.proxy = self.gateway = None
        self.gateway_error = ""
        self.test, self.phase, self.error = test, "stop", ""
        self.cause = ""           # perche' la protezione e' in errore, in breve e senza testi: finisce nella segnalazione
        self.port_moved = None    # {"from", "to"}: la porta scelta per il proxy era occupata e ne e' stata presa un'altra
        self.proxy_port = 0       # la porta su cui il proxy e' partito l'ultima volta
        self.falls = collections.deque(maxlen=RESTARTS)   # quando la protezione e' ripartita da sola (vedi check)
        self.events = collections.deque(maxlen=20)        # che cosa le e' successo, in breve e senza testi: per la segnalazione
        self.lock, self.watching = threading.Lock(), threading.Lock()
        self.silent = {"engine": 0, "proxy": 0}   # quante volte di fila non hanno risposto (vedi probe)
        self.stuck = 0                            # quante volte di fila il motore ha mostrato una richiesta ferma da troppo
        self.probed = 0.0                         # l'ultima volta che glielo si e' chiesto
        self.unblocked = None                     # (processo, motivo) dell'ultimo chiuso perche' non rispondeva: lo legge check
        self.launched_with = None

    def _alive(self, p):
        return p is not None and p.poll() is None

    def note(self, what):
        """Annota un fatto della protezione: in memoria, in breve, senza testi. Lo si legge nella segnalazione."""
        self.events.append((time.strftime("%H:%M:%S"), str(what)[:120]))

    def summary(self):
        """I fatti annotati, in una riga."""
        return " · ".join(f"{stamp} {what}" for stamp, what in list(self.events))

    @staticmethod
    def _who(port):
        """Chi sta usando una porta: (come dirlo nella lingua attiva, il nome del programma o "" se non si sa)."""
        name = sistema.port_owner(port)[:60]
        return (i18n.t("program.someone", name=name) if name else i18n.t("program.another")), name

    def _start(self, command, env):
        """Avvia uno dei due processi tenendo in memoria le sue ultime righe di errore (vedi Output). Cio' che scrive di
        solito continua a non andare da nessuna parte: cosi' non dipende mai da chi lo ha avviato. In piu' riceve un capo
        di un tubo su cui non si scrive mai (sistema.tie): quando questo programma sparisce, comunque sia finito, il tubo
        si chiude e il processo si chiude da solo (sistema.follow_parent) invece di restare acceso a tenere la porta."""
        keep, give, more, value = sistema.tie()
        try:
            p = subprocess.Popen(command, env={**env, "OMISSIS_PARENT": value}, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                 creationflags=NO_WINDOW, **more)
        except BaseException:
            os.close(keep)
            raise
        finally:
            os.close(give)
        p.tie = keep
        p.output = Output(p.stderr)
        return p

    @staticmethod
    def _wait_free(port, seconds):
        """Aspetta, al piu' per quei secondi, che la porta sia libera."""
        for _ in range(int(seconds * 5)):
            if free_port(port):
                return True
            time.sleep(0.2)
        return free_port(port)

    def _engine_port(self, just_stopped):
        """Prima di avviare il motore la sua porta dev'essere libera: se risponde gia' qualcuno, il motore nuovo non
        riesce a prenderla e si chiude poco dopo, mentre l'altro risponde al posto suo. Di solito e' un motore di questa
        copia rimasto acceso da un avvio precedente: viene chiuso. La porta del motore e' fissa (la conosce l'estensione
        del browser): se la tiene un altro programma lo si dice. True se sono stati chiusi processi rimasti."""
        if self._wait_free(ENGINE_PORT, 3 if just_stopped else 0):
            return False
        closed = close_leftovers("engine")
        if closed:
            self.note(f"leftover engine closed x{closed}")
        if self._wait_free(ENGINE_PORT, 8 if closed else 2):   # anche senza trovarne: uno che si stava gia' chiudendo da solo
            return bool(closed)
        who, name = self._who(ENGINE_PORT)
        raise Failure(i18n.t("program.engine_port_busy", port=ENGINE_PORT, who=who),
                      "engine port busy" + _by(name) + (", leftover not closed" if closed else ""))

    @staticmethod
    def _port_lost(port):
        """Il proxy si e' chiuso e la sua porta non e' libera: l'ha presa un altro programma, o il sistema non la da'.
        Si aspetta un attimo, perche' chiudendosi il proxy puo' tenerla ancora per qualche istante."""
        for _ in range(10):
            if free_port(port):
                return False
            time.sleep(0.2)
        return True

    def _stop_proxy(self):
        """Ferma il proxy e aspetta che la sua porta sia libera: il programma lanciato puo' averne un altro sotto, che la
        lascia un attimo dopo. Senza aspettare, un riavvio troverebbe occupata la propria porta e ne cercherebbe un'altra."""
        was_alive = self._alive(self.proxy)
        self._stop(self.proxy)
        if was_alive and self.proxy_port:
            for _ in range(25):
                if not opened_port(self.proxy_port):
                    break
                time.sleep(0.2)

    @staticmethod
    def _details(which, process):
        """Per un processo che si e' chiuso: (la frase da aggiungere al messaggio, il motivo in breve per la segnalazione)."""
        code, kinds = closed_for(process)
        return (i18n.t("program.closed.details", code=code, kinds="".join(" · " + k for k in kinds)),
                " ".join([which, "exit", str(code), *kinds]))

    @staticmethod
    def _proxy_port(wanted, skip):
        """La porta su cui far partire il proxy: quella scelta se e' libera, altrimenti la prima libera tra quelle di
        riserva (e, se sono tutte prese, una qualunque che il sistema da' per libera). Una porta stabilita da chi
        amministra il PC non si cambia: se e' occupata lo si dice."""
        if wanted not in skip and free_port(wanted):
            return wanted
        if "port" in settings.locked()["keys"]:
            who, name = Supervisor._who(wanted)
            raise Failure(i18n.t("program.proxy_port_locked", port=wanted, who=who), f"proxy port {wanted} busy, imposed" + _by(name))
        for port in spare_ports():
            if port != wanted and port not in skip and free_port(port):
                return port
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def launch(self, automatic=False):
        """Avvia la protezione. automatic=True: e' la sorveglianza che la fa ripartire dopo un processo caduto (vedi check).
        Chi la avvia a mano ricomincia da capo: il conto delle ripartenze vale solo per quelle fatte da sole."""
        with self.lock:
            if self.phase in ("startup", "model"):
                return
            if not automatic:
                self.falls.clear()
            self.phase, self.error, self.cause = "startup", "", ""
        threading.Thread(target=self._launch, args=(automatic,), daemon=True).start()

    def _launch(self, automatic=False):
        cfg = settings.read()
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            env = {**os.environ, "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                   "OMISSIS_ENGINE_URL": f"http://127.0.0.1:{ENGINE_PORT}"}
            if self.test:
                env["OMISSIS_TEST"] = "1"
            leftover = False
            if not self._alive(self.engine) or self.launched_with is None or self.launched_with[0] != self._engine_choices(cfg):
                just_stopped = self._alive(self.engine)
                self._stop(self.engine)
                if cfg["serve"]:   # presta il modello (anche per un'impostazione imposta da chi amministra): certificato e chiave devono esserci
                    try:
                        remote.ensure(DATA / "server")
                    except Exception:   # noqa: BLE001  (senza, il motore parte lo stesso e la scheda dice che non e' in ascolto)
                        pass
                # primo avvio di una copia installata: i pesi si scaricano una volta. Non a chi usa il modello di un server della rete
                if not remote.configured(cfg) and weights.missing(cfg["model"]):
                    self.phase = "model"
                    weights.download(cfg["model"])
                    self.phase = "startup"
                leftover = self._engine_port(just_stopped)
                model = str(paths.model(cfg["model"]))
                command = [str(PY_MODEL), str(ENGINE_SCRIPT), "--model", model, "--port", str(ENGINE_PORT)]
                if cfg["device"] in ("cpu", "cuda"):
                    command += ["--device", cfg["device"]]
                self.engine = self._start(command, env)
                for _ in range(180):
                    if not self._alive(self.engine):
                        details, cause = self._details("engine", self.engine)
                        raise Failure(i18n.t("program.engine_closed") + " " + details, cause)
                    try:
                        engine("/status", timeout=2)
                        break
                    except Exception:   # noqa: BLE001
                        time.sleep(1)
                else:
                    raise Failure(i18n.t("program.engine_silent"), "engine silent")
            # Dopo un processo caduto riparte solo cio' che manca: se e' caduto il motore e il proxy e' vivo, con la stessa
            # porta e gli stessi servizi, resta dov'e' (intanto le richieste le ferma: non le lascia passare in chiaro)
            same = self.launched_with is not None and self.launched_with[1:] == (cfg["port"], tuple(s["id"] for s in settings.guarded(cfg)))
            if not (automatic and same and self._alive(self.proxy)):
                self._stop_proxy()
                # Il proxy parte sulla porta scelta. Se un altro programma la sta gia' usando ne prende da solo una libera: prima
                # di lanciarlo, e di nuovo se nel frattempo qualcuno gliel'ha portata via
                wanted, skip = cfg["port"], []
                # Un proxy di questa copia rimasto da un avvio precedente (resta insieme al motore) tiene la porta: lo si
                # chiude, invece di prenderlo per un altro programma e cambiare porta
                if leftover or not free_port(wanted):
                    closed = close_leftovers("proxy")
                    if closed:
                        self.note(f"leftover proxy closed x{closed}")
                        self._wait_free(wanted, 5)
                for attempt in range(3):
                    port = self._proxy_port(wanted, skip)
                    command = [*paths.mitmdump(), "-q", "-s", str(HERE / "addon.py"), "--listen-host", "127.0.0.1",
                               "-p", str(port), "--set", f"confdir={DATA / 'ca'}"]
                    for h in catalog.expressions_host(settings.guarded(cfg)):
                        command += ["--allow-hosts", h]
                    if self.test and os.environ.get("OMISSIS_TEST_ADDON"):   # solo nelle prove: un addon in piu', che annota che cosa passa
                        command += ["-s", os.environ["OMISSIS_TEST_ADDON"]]
                    self.proxy = self._start(command, env)
                    for _ in range(40):
                        if opened_port(port) or not self._alive(self.proxy):
                            break
                        time.sleep(0.5)
                    time.sleep(0.3)   # la porta puo' rispondere per conto di un altro programma arrivato un attimo prima: conta che il proxy sia vivo
                    if self._alive(self.proxy):
                        self.proxy_port = port
                        break
                    if attempt == 2 or not self._port_lost(port):   # non e' la porta: inutile cambiarla
                        details, cause = self._details("proxy", self.proxy)
                        raise Failure(i18n.t("program.proxy_closed") + " " + details, cause)
                    skip.append(port)
                if port != wanted:   # da ora la porta scelta e' questa: la usano anche il file PAC e le finestre protette
                    who, name = self._who(wanted)
                    cfg = settings.write({**settings.read(), "port": port})
                    self.port_moved = {"from": wanted, "to": port, "by": name}
                    self.note(f"proxy port {wanted}>{port}" + _by(name))
                    if NOTIFY is not None and not self.test:
                        NOTIFY(i18n.t("start.port_moved", who=who, **{"from": wanted, "to": port}))
            self.launched_with = (self._engine_choices(cfg), cfg["port"], tuple(s["id"] for s in settings.guarded(cfg)))
            if self.gateway is None:   # per gli strumenti da terminale; se la porta e' occupata il resto funziona lo stesso
                try:
                    self.gateway, self.gateway_error = gateway.Gateway().launch(), ""
                except OSError:
                    self.gateway_error = i18n.t("program.gateway_port", port=paths.GATEWAY_PORT)
            self.silent, self.stuck, self.unblocked, self.probed = {"engine": 0, "proxy": 0}, 0, None, time.time()   # la sorveglianza riparte da zero
            self.phase = "active"
            self.note("active")
            threading.Thread(target=pac_apply, daemon=True).start()   # le app protette dal proxy del sistema
        except weights.Cancelled:
            self.phase = "stop"
        except Exception as ex:   # noqa: BLE001
            self._stop(self.proxy)
            code = f"[WinError {ex.winerror}]" if getattr(ex, "winerror", None) else f"[Errno {ex.errno}]" if getattr(ex, "errno", None) else ""
            self.cause = getattr(ex, "cause", "") or " ".join(x for x in ("launch", type(ex).__name__, code) if x)
            self.note(self.cause)
            self.phase, self.error = "error", str(ex)
            if NOTIFY is not None and not self.test:   # a pannello chiuso non lo si verrebbe a sapere
                NOTIFY(i18n.t("program.error_notice", error=self.error))

    @staticmethod
    def _engine_choices(cfg):
        """Le scelte che, cambiate, chiedono di riavviare il motore: il modello e dove gira, qui o su un server della rete."""
        return (cfg["model"], cfg["device"], cfg["engine_url"], cfg["engine_key"], cfg["engine_pin"], cfg["serve"], cfg["serve_port"])

    @staticmethod
    def _stop(p):
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(8)
            except subprocess.TimeoutExpired:
                p.kill()
        if getattr(p, "tie", None) is not None:   # il processo e' fermo: il capo del tubo che lo legava non serve piu'
            try:
                os.close(p.tie)
            except OSError:
                pass
            p.tie = None

    def stop(self):
        with self.watching:   # da qui la sorveglianza non deve prendere per caduti i processi che fermiamo noi
            was, self.phase = self.phase, "stop"
        if was == "model":
            weights.cancel()
        if self.gateway is not None:
            self.gateway.stop()
            self.gateway = None
        self._stop_proxy()
        self._stop(self.engine)
        self.proxy = self.engine = self.launched_with = None
        self.phase = "stop"

    def restart_needed(self):
        """Le impostazioni salvate richiedono un riavvio per avere effetto?"""
        if self.phase != "active" or self.launched_with is None:
            return False
        cfg = settings.read()
        return self.launched_with != (self._engine_choices(cfg), cfg["port"], tuple(s["id"] for s in settings.guarded(cfg)))

    def check(self):
        """A protezione accesa, guarda se il motore e il proxy sono vivi. Lo fa la sorveglianza ogni due secondi (watch), che
        il pannello sia aperto o no, e ogni richiesta dello stato. Se uno dei due e' caduto la protezione riparte da sola:
        l'avvio rimette in piedi quello che manca, e se il proxy aveva perso la porta ne sceglie un'altra. Al piu'
        RESTARTS volte in WINDOW secondi: oltre, resta ferma, dice perche' e manda un avviso, invece di ripetersi."""
        if self.phase != "active" or not self.watching.acquire(blocking=False):
            return
        try:
            if self.phase != "active" or (self._alive(self.engine) and self._alive(self.proxy)):
                return
            which, process = ("engine", self.engine) if not self._alive(self.engine) else ("proxy", self.proxy)
            if self.unblocked and self.unblocked[0] is process:   # lo abbiamo chiuso noi, perche' non rispondeva piu' (vedi probe)
                text, cause, now = i18n.t(f"program.blocked.{which}"), self.unblocked[1], time.time()
            else:
                details, cause = self._details(which, process)
                self.note(cause)
                text, now = i18n.t(f"program.closed.{which}") + " " + details, time.time()
            self.unblocked = None
            recent = [t for t in self.falls if now - t < WINDOW]
            if len(recent) < RESTARTS:
                self.falls.append(now)
                self.note(f"restart {len(recent) + 1}/{RESTARTS}")
                self.launch(automatic=True)   # da «attiva» a «in avvio», senza passare per l'errore
                return
            self.note("gave up")
            self.phase, self.error, self.cause = "error", text + " " + i18n.t("program.closed.again", n=len(recent)), cause
            if NOTIFY is not None and not self.test:
                NOTIFY(i18n.t("program.stopped_notice"))
        finally:
            self.watching.release()

    def probe(self):
        """A protezione accesa, chiede al motore e al proxy se ci sono davvero: un processo puo' essere vivo e non
        rispondere piu', e allora check non lo vedrebbe mai. Il motore si da' per bloccato dopo SILENT domande di fila
        senza risposta, oppure se risponde ma con richieste in lavorazione non finisce un giro del modello da STALL secondi
        (visto due volte di fila, cosi' un PC appena uscito dalla sospensione non inganna). Il proxy dopo SILENT silenzi di fila,
        contati solo mentre il motore risponde: puo' essere fermo ad aspettare lui. Chi e' bloccato viene chiuso, e check lo
        fa ripartire come un processo caduto, con lo stesso limite di ripartenze."""
        if self.phase != "active" or not (self._alive(self.engine) and self._alive(self.proxy)):
            return
        process, why = self.engine, ""
        try:
            with DIRECT.open(urllib.request.Request(f"http://127.0.0.1:{ENGINE_PORT}/alive", headers={"X-Token": (DATA / "token.txt").read_text(encoding="utf-8").strip()}),
                             timeout=PROBE_TIMEOUT) as r:
                a = json.loads(r.read().decode("utf-8"))
            self.silent["engine"] = 0
            late = bool(a.get("busy")) and a.get("idle") is not None and a["idle"] > STALL
            self.stuck = self.stuck + 1 if late else 0
            if self.stuck >= 2:
                why = f"engine stuck {int(a['idle'])}s busy {a.get('busy')}"
        except urllib.error.HTTPError:   # risponde, ma non a questa domanda: c'e'
            self.silent["engine"] = self.stuck = 0
        except Exception:   # noqa: BLE001  (nessuna risposta nel tempo dato)
            self.silent["engine"] += 1
            if self.silent["engine"] >= SILENT:
                why = "engine silent"
        if not why and not self.silent["engine"]:
            process = self.proxy
            try:
                with urllib.request.build_opener(urllib.request.ProxyHandler({"http": f"http://127.0.0.1:{self.proxy_port}"})).open(ALIVE, timeout=PROBE_TIMEOUT):
                    pass
                self.silent["proxy"] = 0
            except urllib.error.HTTPError:   # ha risposto il proxy (a quell'indirizzo risponde lui, con «non trovato»): c'e'
                self.silent["proxy"] = 0
            except Exception:   # noqa: BLE001
                self.silent["proxy"] += 1
                if self.silent["proxy"] >= SILENT:
                    why = "proxy silent"
        if why and self.phase == "active" and self._alive(process):
            which = "engine" if process is self.engine else "proxy"
            self.note(why)
            self.silent[which], self.stuck, self.unblocked = 0, 0, (process, why)
            try:
                process.kill()
            except OSError:
                pass
            close_leftovers(which)   # anche il processo vero, dove quello avviato da noi ne ha un altro sotto

    def watch(self, every=2):
        """La sorveglianza in sottofondo: vedi check e probe."""
        while True:
            time.sleep(every)
            try:
                self.check()
                if time.time() - self.probed >= PROBE:
                    self.probed = time.time()
                    self.probe()
            except Exception:   # noqa: BLE001  (un giro andato male non deve fermare i successivi)
                pass

    def status(self):
        self.check()
        info = {}
        if self._alive(self.engine) and self.phase == "active":
            try:
                info = engine("/status", timeout=3)
            except Exception:   # noqa: BLE001
                info = {}
        return {"phase": self.phase, "error": self.error, "restart_needed": self.restart_needed(), "version": VERSION,
                "downloading": weights.status(settings.read()["model"]) if self.phase in ("model", "error") and not remote.configured(settings.read()) else None,
                "remote": info.get("remote"), "shared": bool(info.get("shared")),
                "update": updates.status(),
                "light": light_status(),   # il modello leggero da proporre a chi usa omissis-small, e a che punto e' il passaggio
                "model": Path(info["model"]).name if info.get("model") else None, "device": info.get("device"),
                "threshold": info.get("threshold"), "entries": info.get("entries"), "port": settings.read()["port"],
                "port_moved": self.port_moved,   # la porta del proxy era occupata e ne e' stata presa un'altra: la pagina iniziale lo dice
                "groups_off": settings.reduced(),   # gruppi accesi di serie e spenti a mano: la pagina iniziale lo dice
                "always_on": settings.read()["always_on"]}   # la protezione non si puo' fermare: la pagina tiene fermo il pulsante


LIGHT = {"phase": "", "error": "", "freed": 0}   # il passaggio a omissis-light: "" | downloading | switching | done | error


def light_offer():
    """Va proposto il modello leggero? A chi usa omissis-small per scelta sua (non imposta da chi amministra il PC), ha finito
    il primo avvio e non ha ancora risposto. Chi usa il modello di un server della rete non ha nulla da cambiare."""
    cfg = settings.read()
    return (cfg["model"] == "omissis-small" and cfg["light_offer"] == "" and cfg["onboarded"] and "model" not in settings.locked()["keys"]
            and not remote.configured(cfg) and weights.downloadable(paths.DEFAULT_MODEL))


def light_status():
    return {"offer": LIGHT["phase"] in ("", "error") and light_offer(), "phase": LIGHT["phase"], "error": LIGHT["error"],
            "completed": weights.STATUS["completed"] if LIGHT["phase"] == "downloading" else 0,
            "total": weights.size(paths.DEFAULT_MODEL), "old": weights.size("omissis-small"), "freed": LIGHT["freed"]}


def light_switch():
    """Passa a omissis-light senza lasciare il PC scoperto: prima scarica il modello nuovo, mentre la protezione continua con
    quello di adesso; poi cambia e riavvia, e se con il nuovo la protezione non riparte torna al modello di adesso. Solo alla
    fine cancella i pesi che non servono piu', e solo quelli scaricati dal programma (mai quelli accanto ai sorgenti)."""
    old, new = settings.read()["model"], paths.DEFAULT_MODEL
    try:
        LIGHT.update(phase="downloading", error="", freed=0)
        if weights.missing(new):
            weights.download(new)
        LIGHT["phase"] = "switching"
        was_active = SUP.phase == "active"
        settings.write({**settings.read(), "model": new, "light_offer": "done"})
        if was_active:
            SUP.stop()
            SUP.launch()
            for _ in range(300):
                time.sleep(1)
                if SUP.phase in ("active", "error", "stop"):
                    break
            if SUP.phase != "active":
                reason = SUP.error
                settings.write({**settings.read(), "model": old, "light_offer": ""})
                SUP.stop()
                SUP.launch()
                raise RuntimeError(reason or i18n.t("program.engine_silent"))
        folder = paths.DATA / "models" / old
        if old in weights.listing()["models"] and folder.is_dir():
            LIGHT["freed"] = sum(x.stat().st_size for x in folder.iterdir() if x.is_file())
            shutil.rmtree(folder, ignore_errors=True)
        LIGHT["phase"] = "done"
    except Exception as ex:   # noqa: BLE001
        LIGHT.update(phase="error", error=str(ex))


def server_state():
    """Il server di inferenza in rete, visto da questo PC: lo usa, lo fa, oppure nessuna delle due (remote.py)."""
    cfg, lock = settings.read(), settings.locked()["keys"]
    info = {}
    if SUP is not None and SUP.phase == "active":
        try:
            info = engine("/status", timeout=3)
        except Exception:   # noqa: BLE001
            info = {}
    mode = "client" if remote.configured(cfg) else "server" if cfg["serve"] else "local"
    out = {"mode": mode, "managed": any(k in lock for k in ("engine_url", "engine_key", "engine_pin", "serve", "serve_port")),
           "active": SUP is not None and SUP.phase == "active"}
    if mode == "client":
        out["client"] = {"host": urllib.parse.urlsplit(cfg["engine_url"]).netloc, "pinned": bool(cfg["engine_pin"]),
                         **{k: v for k, v in (info.get("remote") or {}).items() if k in ("ok", "error", "model", "device", "ms")}}
    elif mode == "server":
        shared = info.get("shared") or {}
        out["server"] = {"port": cfg["serve_port"], "addresses": remote.addresses(cfg["serve_port"]), "pin": remote.fingerprint(DATA / "server" / "cert.pem"),
                         "listening": bool(shared), "clients": shared.get("clients") or []}
    return out


SUP = None
ICON = None
CONNECTORS = {}   # app desktop avviate da qui: chiave -> Connettore


def turn_off(after=1.5):
    """Chiude tutto il programma (lo usa l'aggiornamento: l'installer lo sostituisce e lo riapre)."""
    def run():
        time.sleep(after)   # il tempo di rispondere alla pagina
        try:
            for c in list(CONNECTORS.values()):
                c.close()
            pac_apply(leaving=True)
            SUP.stop()
            if ICON is not None:
                ICON.stop()
        finally:
            os._exit(0)
    threading.Thread(target=run, daemon=True).start()


APP_LOCK = threading.Lock()   # un solo avvio o aggancio alla volta: due collegamenti alla stessa app si pesterebbero i piedi
DETACHED = set()              # le app staccate a mano con «Stacca»: non vanno riagganciate da sole


def reattach():
    """Un'app avviata protetta e rimasta aperta mentre Omissis era spento (un aggiornamento, un riavvio del programma) ha
    ancora la porta aperta ma nessuno dall'altra parte: al suo interno i messaggi restano bloccati. Qui la si riaggancia."""
    if SUP is None or SUP.phase != "active":
        return
    for key in list(connector.APP):
        c = CONNECTORS.get(key)
        if key in DETACHED or (c is not None and c.alive):
            continue
        with APP_LOCK:
            if CONNECTORS.get(key) is not None and CONNECTORS[key].alive:
                continue
            try:
                fresh = connector.attach(key)
            except Exception:   # noqa: BLE001  (porta aperta da qualcos'altro, o app che si sta chiudendo)
                fresh = None
            if fresh is not None:
                CONNECTORS[key] = fresh


def watch_apps():
    while True:
        time.sleep(10)
        try:
            reattach()
            check_proxy_apps()
            check_reports()
        except Exception:   # noqa: BLE001
            pass


# ------------------------------------------------------------------ l'avviso per le app AI aperte per la prima volta

# app in attesa di una risposta (id -> nome), app aperte al giro prima, l'app dell'ultima notifica (il clic apre la sua finestrella)
ASK = {"pending": {}, "seen": set(), "last": ""}


def ask_entry(ident):
    """Cio' che la finestrella dell'avviso deve sapere di un'app: come si protegge e la regola di adesso."""
    s = catalog.PER_ID[ident]
    key = onboarding.watched().get(ident, (None, None))[1]
    a = connector.APP.get(key) if key else None
    how = ("antigravity" if ident == "antigravity" else "plugin" if a and a.get("plugin") else "profile" if a and a.get("own_profile")
           else "app" if a else "other")
    return {"id": ident, "name": a["name"] if a else s["name"], "protectable": catalog.protectable(s), "how": how,
            "policy": settings.policy(s), "locked": ident in settings.locked()["policies"]}


def check_apps():
    """Un giro dell'avviso: le app AI aperte da poco (al giro prima non c'erano) per cui chi usa il PC non ha ancora scelto
    una regola. Si chiede con una notifica; il clic apre la finestrella con le scelte. Mai durante la configurazione guidata."""
    now = onboarding.running()
    before, ASK["seen"] = ASK["seen"], set(now)
    cfg = settings.read()
    if not cfg["onboarded"] or not cfg["ask_apps"] or NOTIFY is None:
        return
    fixed, own = settings.locked()["policies"], settings.own_policies()
    for ident in sorted(set(now) - before):
        key = now[ident]
        if ident in cfg["ask_never"] or ident in own or ident in ASK["pending"]:
            continue
        if key and CONNECTORS.get(key) is not None and CONNECTORS[key].alive:   # aperta da Omissis: e' gia' protetta
            continue
        name = ask_entry(ident)["name"]
        if ident in fixed:   # la regola l'ha decisa chi amministra il PC: lo si dice una volta, senza chiedere nulla
            p = settings.policy(catalog.PER_ID[ident], cfg)
            NOTIFY(i18n.t(f"ask.managed.{p if p in ('protect', 'block') else 'other'}", app=name))
            settings.write({**cfg, "ask_never": sorted(set(cfg["ask_never"]) | {ident})})
            cfg = settings.read()
            continue
        ASK["pending"][ident] = name
        NOTIFY(i18n.t("ask.toast", app=name))
        ASK["last"] = ident


def watch_new_apps(every=15):
    time.sleep(30)   # non subito: all'avvio il PC ha gia' da fare
    while True:
        try:
            check_apps()
        except Exception:   # noqa: BLE001  (un giro andato male non deve fermare i successivi)
            pass
        time.sleep(every)


def open_window(address):
    """Una finestrella del pannello senza barra degli indirizzi (Edge o Chrome come app), per rispondere all'avviso."""
    sistema.app_window(address, (520, 720))


def balloon_click():
    """Clic su una notifica di Omissis: quella di un'app nuova apre la finestrella per rispondere, le altre il pannello."""
    ident = ASK["last"]
    if ident in ASK["pending"]:
        open_window(f"http://127.0.0.1:{PANEL_PORT}/#/ask/{ident}")
    else:
        webbrowser.open(f"http://127.0.0.1:{PANEL_PORT}/")


def _quietly(f, *a):
    """Per il lavoro in sottofondo chiesto da un clic: se va male lo dice una notifica, invece di sparire."""
    try:
        f(*a)
    except Exception as ex:   # noqa: BLE001
        if NOTIFY:
            NOTIFY(str(ex))


def relaunch_kind(ident):
    """Che cosa fa «Proteggi» su un'app aperta adesso: «relaunch» (si chiude e si riapre protetta) oppure niente."""
    if SUP.test or SUP.phase != "active":
        return ""
    if ident == "antigravity":
        return "relaunch" if SUP.gateway is not None and onboarding.antigravity_exe().exists() else ""
    key = onboarding.watched().get(ident, (None, None))[1]
    a = connector.APP.get(key) if key else None
    if a is None or a.get("refuses") or a.get("plugin") or (key in CONNECTORS and CONNECTORS[key].alive):
        return ""
    return "relaunch" if a.get("own_profile") or connector.open_unprotected(key) else ""


def relaunch_protected(ident):
    """Chiude l'app e la riapre protetta: Antigravity passando dal gateway, le altre con la porta di debug."""
    if ident == "antigravity":
        onboarding.antigravity_relaunch(paths.GATEWAY_PORT)
        return
    key = onboarding.watched()[ident][1]
    with APP_LOCK:
        old = CONNECTORS.pop(key, None)
        if old is not None:
            old.close()
        DETACHED.discard(key)
        CONNECTORS[key] = connector.launch_app(key, close_first=True)


def apply_protection(ident):
    """Dopo «Proteggi» (dall'avviso): Antigravity si collega al comando di Omissis; se la regola nuova chiede di riavviare
    la protezione la si riavvia, poi l'app aperta senza protezione si riapre protetta. Tutto in sottofondo."""
    if ident == "antigravity":
        if not hook_command.state()["ready"]:
            hook_command.install()
        try:
            hook_command.antigravity_link()
        except ValueError:   # file degli hook che non si legge: non si tocca, e il pannello lo segnala in Collegamenti
            pass
    restart, kind = SUP.restart_needed(), relaunch_kind(ident)

    def run():
        if restart:
            SUP.stop()
            SUP.launch()
            for _ in range(240):
                if SUP.phase == "active":
                    break
                time.sleep(0.5)
        if kind:
            relaunch_protected(ident)
    if restart or kind:
        threading.Thread(target=_quietly, args=(run,), daemon=True).start()
    return {"relaunch": kind, "restart": restart}


def mcp_state():
    """Il server MCP: se e' registrato in Claude Desktop, che cosa incollare nelle altre app, quali cartelle puo' usare."""
    file = DATA / "claude_desktop_config.json" if SUP.test else None   # nelle prove un file di prova, mai la configurazione vera
    return {"claude_desktop": mcp_server.claude_desktop_state(file), "snippets": mcp_server.snippets(),
            "folders": [str(x) for x in mcp_server._known_folders()], "extra": list(settings.read().get("mcp_folders") or [])}


# Il repository pubblico con i plugin di Omissis per le app AI: i comandi mostrati nel pannello installano da li'
PLUGIN_REPO = "francescogruner/omissis"   # i plugin stanno nello stesso repository del programma


def hook_state():
    """Il comando «omissis-hook» (c'e'? e' nel PATH?) e, per ogni app, come si installa il plugin che lo chiama."""
    link = f"https://github.com/{PLUGIN_REPO}"
    antigravity = catalog.PER_ID["antigravity"]
    return {**hook_command.state(), "repository": link, "antigravity_policy": settings.policy(antigravity), "platforms": [
        {"id": "kimi", "name": "Kimi", "commands": [f"/plugins install {link}"]},
        {"id": "claude", "name": "Claude Code", "commands": [f"claude plugin marketplace add {PLUGIN_REPO}", "claude plugin install omissis@omissis"]},
        {"id": "codex", "name": "Codex", "commands": [f"codex plugin marketplace add {PLUGIN_REPO}"]},
        {"id": "gemini", "name": "Gemini CLI", "commands": [f"gemini extensions install {link}"]}]}


# ------------------------------------------------------------------ app protette dal proxy del sistema (file PAC)
# Un'app che rifiuta la porta di collegamento (Claude) si protegge dalla rete: il sistema manda al proxy di Omissis il
# traffico verso il suo sito, con un file PAC servito da questo pannello, e si fida del certificato del proxy.

PAC = f"http://127.0.0.1:{PANEL_PORT}/proxy.pac"
STARTED = int(time.time())   # nell'indirizzo del file PAC: a ogni avvio cambia, cosi' le app gia' aperte lo rileggono
_SYSTEM = {"until": 0.0, "proxy": {"supported": False, "pac": "", "proxy": ""}, "certificate": False}
_SYSTEM_LOCK = threading.Lock()


def system_allowed():
    """Nelle prove le impostazioni vere del computer non si toccano: o c'e' il file che fa da sistema (OMISSIS_FAKE_SYSTEM),
    o chi lancia la prova ha detto che la macchina e' di prova (OMISSIS_REAL_SYSTEM=1)."""
    return not SUP.test or bool(sistema.FAKE_SYSTEM) or os.environ.get("OMISSIS_REAL_SYSTEM") == "1"


def pac_apps():
    """Le app scelte per passare dal proxy del sistema: chiavi di connector.APP."""
    return [k for k in settings.read().get("app_proxy") or [] if connector.APP.get(k, {}).get("proxy")]


def pac_text():
    """Il file PAC: al proxy di Omissis vanno solo i siti delle app scelte, tutto il resto esce come prima. Per quei siti
    non c'e' «oppure diretto»: se la protezione e' ferma non si collegano, invece di uscire in chiaro."""
    domains = sorted({d for k in pac_apps() for d in (catalog.PER_ID.get(connector.APP[k].get("service", "")) or {}).get("domains", [])})
    return ("function FindProxyForURL(url, host) {\n  host = host.toLowerCase();\n  var d = " + json.dumps(domains) + ";\n"
            "  for (var i = 0; i < d.length; i++) {\n"
            "    if (host == d[i] || dnsDomainIs(host, \".\" + d[i])) return \"PROXY 127.0.0.1:" + str(settings.read()["port"]) + "\";\n"
            "  }\n  return \"DIRECT\";\n}\n")


def pac_address():
    """L'indirizzo da dare al sistema: cambia con il contenuto (e a ogni avvio), cosi' chi lo aveva gia' letto lo rilegge."""
    return f"{PAC}?v={hashlib.sha256(pac_text().encode('utf-8')).hexdigest()[:8]}&s={STARTED}"


def system_now():
    """Che cosa c'e' adesso nel sistema: il proxy impostato e se il certificato e' tra quelli fidati. Vale per qualche
    secondo, perche' la pagina lo chiede spesso."""
    with _SYSTEM_LOCK:
        if _SYSTEM["until"] < time.time():
            proxy = sistema.system_proxy() if system_allowed() else {"supported": False, "pac": "", "proxy": ""}
            _SYSTEM.update(until=time.time() + 5, proxy=proxy, certificate=certificate()["installed"])
        return _SYSTEM["proxy"], _SYSTEM["certificate"]


def real_machine():
    """Si puo' guardare che cosa e' aperto su questo computer? Nelle prove no (pagina e schermate non devono dipendere
    da questo PC), a meno che la macchina sia tutta di prova."""
    return not SUP.test or os.environ.get("OMISSIS_REAL_SYSTEM") == "1"


def _proxy_marks(**change):
    """I momenti che servono a giudicare un'app sotto il proxy (secondi dall'epoca): quando e' stata scelta (la sua
    chiave) e quando il file PAC e' entrato nel sistema l'ultima volta («_applied»). None toglie la voce."""
    f = DATA / "app_proxy.json"
    try:
        data = {k: float(v) for k, v in json.loads(f.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError, TypeError, AttributeError):
        data = {}
    if change:
        for k, v in change.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = float(v)
        f.write_text(json.dumps(data), encoding="utf-8")
    return data


def version_since():
    """Da quando lavora questa versione di Omissis (secondi dall'epoca). Cio' che una versione precedente non leggeva non
    dice nulla di questa, che puo' averlo corretto: gli avvisi contano da qui in poi."""
    key, marks = "_version " + VERSION, _proxy_marks()
    if key not in marks:
        marks = _proxy_marks(**{key: time.time()}, **{k: None for k in marks if k.startswith("_version ")})
    return marks[key]


def pac_apply(leaving=False, ask=False):
    """Mette nel sistema il file PAC se ci sono app scelte; lo toglie se non ce ne sono piu' o se il programma si chiude.
    Un proxy che non e' il nostro non si tocca mai. True se alla fine il sistema e' come lo vogliamo."""
    if not system_allowed():
        return False
    try:
        now = sistema.system_proxy()
        if not now["supported"]:
            return False
        ours = now["pac"].startswith(PAC)
        want = "" if leaving or not pac_apps() else pac_address()
        if not want:
            done = not ours or sistema.system_pac("", ask=ask)
        elif now["proxy"] or (now["pac"] and not ours):
            done = False
        elif now["pac"] == want:
            done = True
        else:
            done = sistema.system_pac(want, ask=ask)
            if done:   # da adesso: un'app partita prima non lo ha letto, e va riaperta
                _proxy_marks(_applied=time.time())
        _SYSTEM["until"] = 0
        return done
    except Exception:   # noqa: BLE001
        return False


def app_started(a):
    """Da quando gira l'app aperta adesso (secondi dall'epoca), 0 se e' chiusa. Nelle prove lo dice il sistema finto."""
    if sistema.FAKE_SYSTEM:
        return float(sistema.fake_value("app_started") or 0)
    return connector.started(a.get("process")) if real_machine() else 0.0


def _epoch(stamp):
    try:
        return time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))
    except (TypeError, ValueError):
        return 0.0


def proxy_state(key):
    """Come sta, per un'app, la strada del proxy del sistema. L'app legge le impostazioni di rete solo quando parte: conta
    quindi se quella aperta adesso e' partita dopo che il file PAC e' entrato nel sistema, e se da allora la si e' vista
    passare dal proxy. «state»: off | problem | closed | waiting | reopen | protected."""
    a = connector.APP[key]
    now, cert = system_now()
    on, ours = key in pac_apps(), now["pac"].startswith(PAC)
    service, client = a.get("service", ""), a["name"] + " "
    # dietro il proxy l'app lavora per due strade: le richieste lette dal proxy e la casella di scrittura, con il codice
    # che il proxy mette nella pagina (inpage.py) e che il registro segna come "app desktop"
    mine = lambda g: g["service"] == service and g["via"] in ("proxy", "app desktop") and g["client"].startswith(client)   # noqa: E731
    known = [c for c in activity.clients() if mine(c)]
    seen = max((_epoch(c["last"]) for c in known), default=0.0)
    groups = [g for g in activity.compatibility() if mine(g)]
    # «da ricontrollare» riguarda la versione dell'app vista per ultima e questa versione di Omissis: cio' che una versione
    # vecchia dell'una o dell'altro non leggeva non dice nulla di quelle in uso. Le due strade si guardano insieme, e
    # decide l'ultima cosa successa: dopo l'ultima sostituzione riuscita c'e' stato un messaggio non letto?
    current = max(known, key=lambda c: c["last"])["client"] if known else ""
    last_ok = max((g["last_ok"] for g in groups if g["client"] == current), default="")
    last_unread = max((g["last_unread"] for g in groups if g["client"] == current), default="")
    fresh = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(version_since()))
    marks, started = _proxy_marks(), app_started(a)
    store = updates.channel() == "store"   # la copia dello Store non puo' cambiare le impostazioni del PC
    foreign = now["proxy"] or ("" if ours else now["pac"])
    problem = "" if not on else "paused" if SUP.phase != "active" else "foreign" if foreign else "certificate" if not cert else "network" if not ours else ""
    # da quando l'app puo' aver letto il file PAC: da quando e' partita, se e' partita dopo; altrimenti non lo ha letto affatto
    since = max(marks.get("_applied", 0.0), marks.get(key, 0.0), started)
    passing = bool(started) and seen >= since - 1
    grace = float(sistema.fake_value("grace", 90)) if sistema.FAKE_SYSTEM else 90.0   # il tempo che l'app ha per farsi vedere
    state = ("off" if not on else "problem" if problem else "closed" if not started else "protected" if passing
             else "waiting" if time.time() - since <= grace else "reopen")
    return {"available": now["supported"] and not store, "store": store, "on": on, "network": ours, "certificate": cert,
            "foreign": foreign[:80], "active": SUP.phase == "active", "problem": problem, "state": state, "open": bool(started),
            "seen": passing, "messages": sum(g["ok"] for g in groups), "last_ok": max((g["last_ok"] for g in groups), default=""),
            "to_recheck": bool(last_unread) and last_unread >= max(last_ok, fresh), "report": True}


NOTIFIED_REOPEN = set()   # (app, da quando gira): l'avviso «va riaperta» si da' una volta sola per ogni apertura dell'app


def check_proxy_apps():
    """Un'app protetta dal proxy ma aperta prima che la protezione fosse pronta esce senza protezione: lo si dice con una
    notifica, una volta, cosi' chi usa il computer la riapre."""
    if NOTIFY is None or SUP.test:
        return
    for key in pac_apps():
        a = connector.APP[key]
        if proxy_state(key)["state"] == "reopen":
            mark = (key, int(app_started(a)))
            if mark not in NOTIFIED_REOPEN:
                NOTIFIED_REOPEN.add(mark)
                NOTIFY(i18n.t("app.proxy.notify.reopen", name=a["name"]))


REPORT_MARK = {"at": None, "told": {}}   # fin dove si e' letto il registro, e di che cosa si e' gia' avvisato


def check_reports():
    """Un messaggio fermato perche' Omissis non riesce a leggerlo, o il codice della casella che non entra nella pagina:
    di solito e' l'app che e' cambiata con un aggiornamento. Chi usa il computer lo deve sapere subito, e dal pannello
    lo puo' segnalare (report.py). Un avviso ogni sei ore per programma basta."""
    fresh, REPORT_MARK["at"] = report.news(REPORT_MARK["at"])
    names = {s["id"]: s["name"] for s in catalog.SERVICES}
    for kind, service, client in fresh:
        if time.time() - REPORT_MARK["told"].get((kind, service, client), 0) < 6 * 3600:
            continue
        REPORT_MARK["told"][(kind, service, client)] = time.time()
        if NOTIFY is not None and not SUP.test:
            NOTIFY(i18n.t(f"report.notify.{kind}", name=client or names.get(service, service)))


def app_proxy(key, on):
    """«Proteggi» e «Togli la protezione» per un'app che passa dal proxy del sistema: fa tutto da solo, e dice che cosa manca."""
    a = connector.APP[key]
    if not a.get("proxy"):
        raise Refusal(i18n.t("program.app_unknown"))
    if not system_allowed():
        raise Refusal(i18n.t("app.proxy.error.test"))
    chosen = set(pac_apps())
    if not on:
        settings.write({**settings.read(), "app_proxy": sorted(chosen - {key})})
        _proxy_marks(**{key: None})
        pac_apply(ask=True)   # se il sistema non lascia togliere il file PAC, resta li' ma manda tutto diretto
        return
    if updates.channel() == "store":
        raise Refusal(i18n.t("app.proxy.error.store"))
    if SUP.phase != "active":
        raise Refusal(i18n.t("program.app_needs_protection"))
    now = sistema.system_proxy()
    if not now["supported"]:
        raise Refusal(i18n.t("app.proxy.error.unsupported"))
    foreign = now["proxy"] or ("" if now["pac"].startswith(PAC) else now["pac"])
    if foreign:   # un proxy messo da chi usa il computer, o dalla sua azienda: non lo si tocca
        raise Refusal(i18n.t("app.proxy.error.foreign", what=foreign[:80]))
    if not certificate("install")["installed"]:   # il sistema chiede conferma a chi usa il computer: senza il suo si' ci si ferma
        raise Refusal(i18n.t("app.proxy.error.certificate"))
    settings.write({**settings.read(), "app_proxy": sorted(chosen | {key})})
    _proxy_marks(**{key: time.time()})
    if not pac_apply(ask=True):
        settings.write({**settings.read(), "app_proxy": sorted(chosen)})
        _proxy_marks(**{key: None})
        raise Refusal(i18n.t("app.proxy.error.network"))


def app_desktop():
    out = []
    for key, a in connector.APP.items():
        c = CONNECTORS.get(key)
        if c is not None and not c.alive:   # l'app e' stata chiusa
            CONNECTORS.pop(key, None)
            c = None
        service = catalog.PER_ID.get(a.get("service", ""))
        px = proxy_state(key) if a.get("proxy") else None   # l'app si protegge dal proxy del sistema
        # nelle prove l'app che si protegge con un plugin risulta installata comunque: la pagina non deve dipendere da questo PC
        out.append({"id": key, "name": a["name"],
                    "installed": connector.find_command(a) is not None or bool(SUP.test and (a.get("plugin") or a.get("proxy"))),
                    "connected": c is not None, "outcome": c.outcome if c else None, "counts": dict(c.counts) if c else None,
                    "errors": (c.notices + c.errors)[-3:] if c else [],
                    # aperta ma non da qui: dentro non c'e' nessuna protezione
                    # (nelle prove no: pagina e schermate non devono dipendere da cio' che e' aperto su questo PC)
                    "open_unprotected": (px["open"] and px["state"] in ("off", "problem", "reopen")) if px and px["available"]
                    else c is None and not SUP.test and connector.open_unprotected(key),
                    "own_profile": bool(a.get("own_profile")), "refuses": bool(a.get("refuses")),
                    # l'app si protegge dal proxy del sistema: se la strada e' accesa e come sta
                    "proxy": px,
                    # l'app si protegge con un suo plugin: se la cartella e' pronta, dove sta, e se in Kimi risulta installato
                    "plugin": kimi_plugin.state() if a.get("plugin") else None,
                    # la politica del servizio decide se i messaggi vengono mascherati: con «registra» l'app si collega e basta
                    "service": service["name"] if service else "", "service_id": service["id"] if service else "",
                    "policy": settings.policy(service) if service else "protect"})
    return out


# ------------------------------------------------------------------ dati per la pagina

def read_log(n=20000):
    f = DATA / "activity.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def stats():
    today = time.strftime("%Y-%m-%d")
    days = [time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * i)) for i in range(6, -1, -1)]
    by_day = {g: 0 for g in days}
    kinds, services, notices = collections.Counter(), collections.Counter(), collections.Counter()
    count = collections.Counter()
    for v in read_log():
        g, ev = v.get("stamp", "")[:10], v.get("event", "")
        if g not in by_day:
            continue
        sost = sum((v.get("replacements") or {}).values())
        if ev == "masked":
            by_day[g] += 1
            services[v.get("service", "?")] += 1
            kinds.update(v.get("replacements") or {})
            if g == today:
                count["messages"] += 1
                count["replacements"] += sost
        elif ev.startswith("blocked") or ev == "file_blocked":
            count["blocked"] += g == today
            notices["blocked"] += 1
        elif "nessun campo" in ev:
            notices["unrecognized"] += 1
        elif ev == "file_not_masked":
            notices["unmasked_files"] += 1
        if v.get("VALUES_IN_CLEAR"):
            notices["clear_values"] += 1
    return {"today": {"messages": count["messages"], "replacements": count["replacements"], "blocked": count["blocked"]},
            "days": [{"day": g, "n": by_day[g]} for g in days], "kinds": kinds.most_common(), "services": services.most_common(),
            "notices": [{"code": k, "n": n} for k, n in notices.most_common()]}


def contacts(days=30):
    f = DATA / "contacts.sqlite"
    if not f.exists():
        return {}
    da = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * days))
    try:
        db = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True)
        lines = db.execute("SELECT service, outcome, SUM(n), MAX(last) FROM contacts WHERE day >= ? GROUP BY service, outcome", (da,)).fetchall()
        db.close()
    except sqlite3.Error:
        return {}
    out = {}
    for service, outcome, n, last in lines:
        v = out.setdefault(service, {"n": 0, "last": "", "outcomes": {}})
        v["n"] += n
        v["last"] = max(v["last"], last or "")
        v["outcomes"][outcome] = n
    return out


def services():
    cfg, cont, fixed = settings.read(), contacts(), settings.locked()["policies"]
    return [{"id": s["id"], "name": s["name"], "vendor": s["vendor"], "kind": s["kind"], "domains": s["domains"], "locked": s["id"] in fixed,
             "reading": "radar" if s["radar"] else "box" if s["box"] and not s["adapter"] else "hook" if s.get("hook") and not s["adapter"] else READING_STATUS[s["adapter"]],
             "radar": s["radar"], "readable": bool(s["adapter"]), "protectable": catalog.protectable(s),
             "policy": settings.policy(s, cfg),
             "default": catalog.default_policy(s), "contacts": cont.get(s["id"], {}).get("n", 0),
             "last": cont.get(s["id"], {}).get("last", "")} for s in catalog.SERVICES]


def inventory_status():
    """L'inventario degli strumenti AI con, per ogni voce legata a un servizio del catalogo, la scelta fatta nelle Regole."""
    r, cfg = inventory.summary(), settings.read()
    for e in r["items"]:
        s = catalog.PER_ID.get(e["service"])
        e["policy"] = settings.policy(s, cfg) if s else None
    every, latest = EVERY.get(cfg.get("scan")), r["scan"][0]["stamp"] if r["scan"] else ""
    upcoming = ""
    if every and latest:
        upcoming = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.mktime(time.strptime(latest, "%Y-%m-%d %H:%M:%S")) + every))
    return {**r, "every": cfg.get("scan"), "upcoming": upcoming}


def analyze(origin):
    """Fotografa il PC e la rete, salva l'analisi e restituisce le novita' rispetto alla precedente."""
    return inventory.record(scan.pc(), scan.network(), origin)


def keep_on(every=30):
    """Dove e' stabilito che la protezione resti accesa (always_on): se e' ferma, la riaccende. Un errore di avvio resta
    com'e', cosi' si legge nel pannello invece di ripetersi all'infinito."""
    while True:
        time.sleep(every)
        try:
            if SUP.phase == "stop" and settings.read()["always_on"]:
                SUP.launch()
        except Exception:   # noqa: BLE001
            pass


def watch():
    """In sottofondo: ripete l'analisi degli strumenti AI con la cadenza scelta e, se chiesto, alleggerisce l'archivio."""
    time.sleep(120)   # non subito: all'avvio il PC ha gia' da fare
    clean = ""
    while True:
        try:
            cfg = settings.read()
            every, latest = EVERY.get(cfg.get("scan")), inventory.latest()
            passed = time.time() - time.mktime(time.strptime(latest, "%Y-%m-%d %H:%M:%S")) if latest else None
            if every and (passed is None or passed >= every):
                news = analyze("automatic")
                if news["new_items"] and NOTIFY:
                    names = ", ".join(sorted({e["name"] for e in news["new_items"]})[:3])
                    NOTIFY(i18n.t("inventory.new_notice", n=len(news["new_items"]), names=names))
            days, today = int(cfg.get("vault_days") or 0), time.strftime("%Y-%m-%d")
            if days > 0 and clean != today and SUP.phase == "active":
                engine("/vault/delete", {"idle_days": days})
                clean = today
        except Exception:   # noqa: BLE001  (un giro andato male non deve fermare i successivi)
            pass
        time.sleep(600)


def shortcuts():
    """Le scorciatoie da tastiera e il loro stato (attiva, oppure presa da un altro programma)."""
    wanted = clipboard.choices(settings.read())
    status = SHORTCUTS.status if SHORTCUTS is not None else {}
    return {"available": SHORTCUTS is not None, "defaults": clipboard.DEFAULTS,
            "entries": [{"name": name, "combo": c, "caption": clipboard.caption(c), "active": bool(status.get(name, {}).get("active")),
                      "error": status.get(name, {}).get("error", "") if c else ""} for name, c in wanted.items()]}


def read_lists():
    def f(name):
        p = LISTS / name
        return [r.strip() for r in p.read_text(encoding="utf-8").splitlines() if r.strip() and not r.lstrip().startswith("#")] if p.exists() else []
    return {"always": f("always.txt"), "never": f("never.txt")}


def write_lists(data):
    tested = {"always.txt": "# Termini da mascherare SEMPRE, uno per riga (maiuscole e minuscole non contano).\n",
               "never.txt": "# Termini da NON mascherare mai, uno per riga (maiuscole e minuscole non contano).\n"}
    LISTS.mkdir(parents=True, exist_ok=True)
    for name, key in (("always.txt", "always"), ("never.txt", "never")):
        entries = [str(x).strip()[:200] for x in data.get(key, []) if str(x).strip() and not str(x).lstrip().startswith("#")][:5000]
        (LISTS / name).write_text(tested[name] + "\n".join(entries) + ("\n" if entries else ""), encoding="utf-8")
    try:
        engine("/lists", {})
    except Exception:   # noqa: BLE001  (motore spento: le leggera' al prossimo avvio)
        pass
    return read_lists()


def extension_store():
    """Le pagine degli store da cui installare l'estensione con un clic (store.json). Finche' l'estensione non e' pubblicata
    sono vuote, e la pagina mostra l'installazione a mano dalla cartella."""
    try:
        found = json.loads((HERE / "store.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        found = {}
    return {k: v for k in ("chrome", "edge") if isinstance(v := found.get(k), str) and v.startswith("https://")}


def extension_folder():
    """La cartella dell'estensione da indicare al browser. La copia arrivata dal Microsoft Store sta in una cartella di
    sistema che il browser non puo' leggere: se ne tiene una copia aggiornata tra i documenti dell'utente."""
    origin = HERE / "extension"
    if updates.channel() != "store":
        return origin
    target = mcp_server._known_folders()[0] / "Omissis" / "extension"
    try:
        stamp = target / ".version"
        if not stamp.exists() or stamp.read_text(encoding="utf-8") != VERSION:
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(origin, target)
            stamp.write_text(VERSION, encoding="utf-8")
        return target
    except OSError:
        return origin


def certificate(action=None):
    cer = DATA / "ca" / "mitmproxy-ca-cert.cer"
    if action in ("install", "remove") and not system_allowed():
        raise Refusal(i18n.t("app.proxy.error.test"))
    if action == "install" and updates.channel() == "store":
        # un programma arrivato dallo Store scrive in una copia privata delle impostazioni di Windows: il certificato
        # risulterebbe installato solo per Omissis stesso, e nessun altro programma si fiderebbe del proxy
        raise Refusal(i18n.t("proxy.certificate.store"))
    _SYSTEM["until"] = 0
    return {"exists": cer.exists(), "installed": sistema.certificate(cer, action if action in ("install", "remove") else None)}


# ------------------------------------------------------------------ l'app sul Mac

def system_card():
    """Cio' che la pagina deve sapere del sistema su cui gira. Sul Mac: dove sta l'app (da li' dipende se si aggiorna da
    sola), se parte all'accesso, se dal pannello si puo' togliere. Su Windows queste cose le fa l'installer."""
    where = macapp.location()
    return {"name": sistema.NAME if sistema.LINUX or not where else "mac", "location": where,
            "login_item": macapp.login_item() if where else {"supported": False, "on": False},
            "uninstall": where in ("ok", "move"), "applications": str(macapp.applications()) if where == "move" else "",
            # su Linux l'icona c'e' solo dove il desktop la mostra: la chiusura del programma si offre anche dal pannello
            "quit": bool(where) and sistema.LINUX and not settings.read()["always_on"]}


def move_app():
    """Sul Mac: copia l'app nella cartella Applicazioni e la riapre da li' (questa copia si chiude)."""
    if sistema.FAKE_SYSTEM:   # nelle prove senza Mac: come se fosse andata
        sistema._fake_system({"mac_location": "ok"})
        return
    try:
        macapp.move(updates.relaunch_arguments(), DATA / "updates")
    except macapp.Error as ex:
        raise Refusal(i18n.t("mac.move.error.there" if ex.code == "already_there" else "mac.move.error")) from ex
    turn_off()


def uninstall_app(remove_data):
    """Sul Mac: toglie cio' che Omissis ha messo nel sistema (avvio all'accesso, comando da terminale, proxy e
    certificato, voce in Claude Desktop), sposta l'app nel Cestino e chiude il programma. I dati restano, a meno che chi
    usa il Mac abbia chiesto di cancellarli: allora spariscono anche l'archivio e la sua chiave nel Portachiavi."""
    macapp.login_item(False)
    for remove in (hook_command.remove,
                   lambda: mcp_server.claude_desktop_install(DATA / "claude_desktop_config.json" if SUP.test else None, remove=True)):
        try:
            remove()
        except Exception:   # noqa: BLE001  (una voce che non si riesce a togliere non deve fermare il resto)
            pass
    settings.write({**settings.read(), "app_proxy": []})
    pac_apply(leaving=True)
    cer = DATA / "ca" / "mitmproxy-ca-cert.cer"
    if sistema.certificate(cer):
        sistema.certificate(cer, "remove")   # macOS chiede conferma a chi usa il Mac
    if remove_data:
        sistema.keychain_forget("vault")
    if sistema.FAKE_SYSTEM:   # nelle prove senza Mac: si annota soltanto
        sistema._fake_system({"mac_location": "", "uninstalled": {"data": bool(remove_data)}})
        return {"trashed": True, "data": bool(remove_data)}
    out = macapp.uninstall(DATA if remove_data else None)
    turn_off()
    return {**out, "data": bool(remove_data)}


def first_login_item(test):
    """Al primo avvio dell'app in un posto suo, Omissis si mette tra i programmi che partono all'accesso al Mac (su
    Windows lo fa l'installer, con la casella gia' spuntata). Si spegne dalle Impostazioni. Se l'app e' stata spostata,
    la voce viene corretta."""
    if macapp.location() != "ok" or (test and os.environ.get("OMISSIS_REAL_SYSTEM") != "1"):
        return
    macapp.linux_entries()   # solo su Linux: voce nel menu delle applicazioni, icona e comando «omissis»
    macapp.login_item_follow()
    note = DATA / "login_item.txt"
    if not note.exists():
        note.write_text("1", encoding="utf-8")
        macapp.login_item(True)


# ------------------------------------------------------------------ servizio web locale

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _respond(self, code, obj, kind="application/json; charset=utf-8"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", POLICY_PAGE)
        self.end_headers()
        self.wfile.write(body)

    def _allowed(self):
        """Solo questo PC (niente nomi host estranei) e, per i dati, solo chi ha il codice della pagina."""
        if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            self._respond(403, {"error": "host non ammesso"})
            return False
        if self.path.startswith("/api/") and not secrets.compare_digest(self.headers.get("X-Panel", ""), CODE):
            self._respond(403, {"error": "codice mancante"})
            return False
        if self.path.startswith("/internal/"):   # chiamate del motore (stesso PC), con il suo codice
            try:
                expected = (DATA / "token.txt").read_text(encoding="utf-8").strip()
            except OSError:
                expected = ""
            if not expected or not secrets.compare_digest(self.headers.get("X-Token", ""), expected):
                self._respond(403, {"error": "codice mancante"})
                return False
        return True

    def do_GET(self):
        if not self._allowed():
            return
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        try:
            if u.path == "/":
                page = (PAGE / "index.html").read_text(encoding="utf-8").replace("__CODICE__", CODE).replace("__LINGUA__", i18n.active())
                self._respond(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif u.path == "/proxy.pac":   # lo leggono il sistema e le app, non la pagina: dentro non c'e' nessun dato
                self._respond(200, pac_text().encode("utf-8"), "application/x-ns-proxy-autoconfig")
            elif u.path in STATIC or RX_LANGUAGE.fullmatch(u.path):
                self._respond(200, (PAGE / u.path.lstrip("/")).read_bytes(), STATIC.get(u.path, "application/json; charset=utf-8"))
            elif u.path == "/api/compatibility":
                try:
                    verified_ones = json.loads((HERE / "compatibility.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    verified_ones = {"entries": []}
                names = {s["id"]: s["name"] for s in catalog.SERVICES}
                self._respond(200, {"sightings": [{**g, "name": names.get(g["service"], g["service"])} for g in activity.compatibility()],
                                     "verified_ones": [{**v, "name": names.get(v.get("service"), v.get("service"))} for v in verified_ones.get("entries", [])],
                                     "updated": verified_ones.get("updated", ""), "report": True})
            elif u.path == "/api/report":   # la segnalazione di un problema: il testo che si vede, e che parte solo se lo si invia
                now = SUP.status()
                phase = now["phase"] + (f" ({SUP.cause})" if now["phase"] == "error" and SUP.cause else "")
                self._respond(200, report.build(q.get("what", ""), phase, now.get("model") or "", SUP.summary()))
            elif u.path == "/api/languages":
                self._respond(200, {"choice": i18n.choice(), "active": i18n.active(), "available": i18n.available()})
            elif u.path == "/api/status":
                self._respond(200, {**SUP.status(), "stats": stats()})
            elif u.path == "/api/activity":
                self._respond(200, read_log(int(q.get("n", 300)))[::-1])
            elif u.path == "/api/services":
                self._respond(200, services())
            elif u.path == "/api/settings":
                # la chiave di collegamento alla console non torna alla pagina: le basta sapere se c'e' (/api/console)
                self._respond(200, {**{k: v for k, v in settings.read().items() if k not in ("console_key", "engine_key")}, "certificate": certificate(),
                                     "groups": settings.GROUPS, "groups_always": settings.ALWAYS_ON, "groups_optional": list(settings.OPTIONAL),
                                     "profile_now": settings.profile_of(), "profiles": settings.PROFILES, "managed": settings.locked(),
                                     "first_run": settings.first_run(SUP.test), "system": system_card()})
            elif u.path == "/api/console":
                self._respond(200, central.state())
            elif u.path == "/api/server":
                self._respond(200, server_state())
            elif u.path == "/api/lists":
                self._respond(200, read_lists())
            elif u.path == "/api/app":
                self._respond(200, app_desktop())
            elif u.path == "/api/hook":
                self._respond(200, hook_state())
            elif u.path == "/api/view":
                self._respond(200, {"view": settings.read().get("view", "simple")})
            elif u.path == "/api/mcp":
                self._respond(200, mcp_state())
            elif u.path == "/api/gateway":
                g = SUP.gateway
                self._respond(200, {"is_active": g is not None, "port": paths.GATEWAY_PORT, "error": SUP.gateway_error,
                                     "counts": dict(g.counts) if g else None, "routes": sorted(gateway.routes()),
                                     "upstreams": dict(settings.read().get("gateway_upstreams") or {})})
            elif u.path == "/api/extension":
                f = DATA / "token_extension.txt"
                self._respond(200, {"folder": str(extension_folder()), "port": ENGINE_PORT, "store": extension_store(),
                                     "token": f.read_text(encoding="utf-8").strip() if f.exists() else ""})
            elif u.path == "/api/categories":   # le categorie in piu' che il modello in uso conosce, e quelle accese
                try:
                    self._respond(200, engine("/profile", {}))
                except Exception:   # noqa: BLE001
                    self._respond(200, {"known": [], "enabled": settings.read().get("categories", [])})
            elif u.path == "/api/shortcuts":
                self._respond(200, shortcuts())
            elif u.path == "/api/ask":   # le app AI in attesa di una risposta e, con ?id=, quella da mostrare nella finestrella
                ident = q.get("id", "")
                self._respond(200, {"pending": [ask_entry(i) for i in list(ASK["pending"]) if i in catalog.PER_ID],
                                     "entry": ask_entry(ident) if ident in catalog.PER_ID else None})
            elif u.path == "/api/welcome/tools":   # il passo «Cosa proteggo?» senza la ricerca: gli strumenti piu' usati
                self._respond(200, {"tools": onboarding.tools()})
            elif u.path == "/api/inventory":
                self._respond(200, inventory_status())
            elif u.path == "/api/inventory/csv":
                text = inventory.csv([i18n.t(f"inventory.column.{c}") for c in ("category", "name", "detail", "version", "first", "last", "present", "verdict", "note")],
                                      lambda c: i18n.t(f"inventory.category.{c}"), lambda g: i18n.t(f"inventory.verdict.{g or 'to_review'}"))
                self._respond(200, text.encode("utf-8"), "text/csv; charset=utf-8")
            elif u.path == "/api/shadow/pc":
                self._respond(200, scan.pc())
            elif u.path == "/api/shadow/network":
                names = {s["id"]: s["name"] for s in catalog.SERVICES}
                self._respond(200, {**scan.network(), "proxy": [{"service": names.get(k, k), **v} for k, v in
                                                                   sorted(contacts().items(), key=lambda kv: -kv[1]["n"])]})
            else:
                self._respond(404, {"error": i18n.t("program.not_found")})
        except FileNotFoundError:
            self._respond(404, {"error": i18n.t("program.not_found")})
        except Exception as ex:   # noqa: BLE001
            self._respond(500, {"error": f"{type(ex).__name__}: {ex}"})

    def do_POST(self):
        if not self._allowed():
            return
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8") or "{}")
            p = self.path
            if p == "/internal/attachment":   # il motore non ha le librerie per i documenti: li legge questo processo
                try:
                    name, fresh, counts = documents.work_on(Path(str(data.get("name", "file"))).name, base64.b64decode(data.get("data", "")), "anonymize")
                except documents.Error as ex:
                    self._respond(422, {"error": str(ex), "code": ex.code})
                    return
                self._respond(200, {"name": name, "data": base64.b64encode(fresh).decode("ascii"), "counts": counts})
            elif p == "/api/protection":
                if data.get("action") == "stop":
                    if settings.read()["always_on"]:   # deciso da chi amministra il PC o dalla console: da qui non si spegne
                        raise Refusal(i18n.t("managed.always_on"))
                    SUP.stop()
                else:
                    if data.get("action") == "restart":
                        SUP.stop()
                    SUP.launch()
                self._respond(200, SUP.status())
            elif p == "/api/model/light":   # la risposta alla proposta del modello leggero
                if data.get("accept"):
                    if light_offer() and LIGHT["phase"] in ("", "error"):
                        LIGHT.update(phase="downloading", error="", freed=0)
                        threading.Thread(target=light_switch, daemon=True).start()
                elif settings.read()["light_offer"] == "":
                    settings.write({**settings.read(), "light_offer": "no"})
                self._respond(200, SUP.status())
            elif p == "/api/settings":
                # la console e il server di inferenza hanno le loro chiamate: qui non si toccano. always_on si puo' solo imporre
                changes = {k: v for k, v in data.items() if k in settings.DEFAULTS and not k.startswith(("console_", "engine_", "serve")) and k not in ("always_on", "profile", "app_proxy")}
                # un profilo, per chi usa il PC, e' un modo rapido di scegliere gruppi e categorie tutti insieme
                if data.get("profile") in settings.PROFILES:
                    changes.update({k: list(v) for k, v in settings.PROFILES[data["profile"]].items()})
                guard(*changes, changes=changes)
                new_ones = {k: v for k, v in settings.write({**settings.read(), **changes}).items() if k not in ("console_key", "engine_key")}
                if "port" in changes:
                    SUP.port_moved = None
                if "shortcuts" in data and SHORTCUTS is not None:
                    SHORTCUTS.configure(clipboard.choices(new_ones))
                if "categories" in changes:   # il motore rilegge quali categorie in piu' sostituire
                    try:
                        engine("/profile", {})
                    except Exception:   # noqa: BLE001  (motore spento: le leggera' all'avvio)
                        pass
                self._respond(200, {**new_ones, "restart_needed": SUP.restart_needed()})
            elif p == "/api/services":
                cfg = settings.read()
                if str(data["id"]) in settings.locked()["policies"]:
                    raise Refusal(i18n.t("managed.locked"))
                policies = dict(cfg["policies"])
                policies[str(data["id"])] = str(data["policy"])
                settings.write({**cfg, "policies": policies})
                self._respond(200, {"restart_needed": SUP.restart_needed()})
            elif p == "/api/lists":
                self._respond(200, write_lists(data))
            elif p == "/api/gateway":   # chi ha gia' un proprio gateway: dove inoltrare, servizio per servizio (vuoto = il servizio vero)
                guard("gateway_upstreams")
                wanted = {str(k): str(v).strip() for k, v in (data.get("upstreams") or {}).items() if str(v).strip()}
                wrong = [v for k, v in wanted.items() if k not in gateway.routes() or k == "codex" or not settings.address_ok(v)]
                if wrong:
                    raise Refusal(i18n.t("terminal.own.error", address=wrong[0]))
                self._respond(200, {"upstreams": settings.write({**settings.read(), "gateway_upstreams": wanted})["gateway_upstreams"]})
            elif p == "/api/mcp":
                action = data.get("action")
                if action in ("install", "uninstall"):   # scrive (o toglie) Omissis nella configurazione di Claude Desktop
                    try:
                        mcp_server.claude_desktop_install(DATA / "claude_desktop_config.json" if SUP.test else None, remove=action == "uninstall")
                    except (OSError, ValueError) as ex:
                        raise Refusal(i18n.t("mcp.error.config")) from ex
                elif action == "folders":
                    guard("mcp_folders")
                    chosen = [str(x).strip().strip('"') for x in data.get("folders") or [] if str(x).strip()]
                    missing = [x for x in chosen if not Path(x).is_dir()]
                    if missing:
                        raise Refusal(i18n.t("mcp.error.folder", folder=missing[0]))
                    settings.write({**settings.read(), "mcp_folders": chosen})
                self._respond(200, mcp_state())
            elif p == "/api/server":   # il server di inferenza in rete: prestare il modello di questo PC, o usare quello di un altro
                action, cfg = data.get("action"), settings.read()
                if action in ("share", "use", "leave"):
                    guard("engine_url", "engine_key", "engine_pin", "serve", "serve_port")
                if action == "share":
                    on = data.get("on") is not False
                    if on and remote.configured(cfg):
                        raise Refusal(i18n.t("server.error.both"))
                    if on:
                        remote.ensure(DATA / "server")
                    settings.write({**cfg, "serve": on})
                elif action == "config":   # cio' che va dato ai PC: indirizzo, chiave e impronta. Resta in questa pagina
                    if not cfg["serve"]:
                        raise Refusal(i18n.t("server.error.not_sharing"))
                    cert, _, access = remote.ensure(DATA / "server")
                    self._respond(200, {"config": {"engine_url": remote.addresses(cfg["serve_port"])[0], "engine_key": access,
                                                    "engine_pin": remote.fingerprint(cert)}})
                    return
                elif action == "use":
                    given = data.get("config")
                    if isinstance(given, str) and given.strip():   # incollata cosi' come la da' il server
                        try:
                            given = json.loads(given)
                        except ValueError:
                            raise Refusal(i18n.t("server.error.config")) from None
                    if not isinstance(given, dict):
                        given = {"engine_url": data.get("url"), "engine_key": data.get("key"), "engine_pin": data.get("pin")}
                    address, key = str(given.get("engine_url") or "").strip().rstrip("/"), str(given.get("engine_key") or "").strip()
                    pin = re.sub(r"(?i)^sha-?256[:=]|[\s:]", "", str(given.get("engine_pin") or "")).lower()
                    if not settings.console_address_ok(address) or not key:
                        raise Refusal(i18n.t("server.error.address"))
                    try:   # prima si prova: una configurazione sbagliata lascerebbe questo PC senza riconoscimento
                        remote.check(address, key, pin)
                    except remote.Failure as ex:
                        raise Refusal(i18n.t(f"server.error.{ex.code}")) from None
                    settings.write({**cfg, "engine_url": address, "engine_key": key, "engine_pin": pin, "serve": False})
                elif action == "leave":
                    settings.write({**cfg, "engine_url": "", "engine_key": "", "engine_pin": ""})
                elif action == "test":
                    try:
                        self._respond(200, {**server_state(), "test": {"ok": True, **remote.check(cfg["engine_url"], cfg["engine_key"], cfg["engine_pin"])}})
                    except remote.Failure as ex:
                        self._respond(200, {**server_state(), "test": {"ok": False, "error": ex.code}})
                    return
                if action in ("share", "use", "leave") and SUP.phase == "active":
                    SUP.launch()   # il motore riparte con la scelta nuova: per qualche secondo la protezione e' in avvio
                self._respond(200, server_state())
            elif p == "/api/console":   # la console centrale di un'organizzazione: collegare, vedere che cosa parte, inviare ora
                action = data.get("action")
                if action in ("connect", "disconnect"):
                    guard("console_url", "console_key", "console_names", "console_pin")
                    address, key = str(data.get("url") or "").strip().rstrip("/"), str(data.get("key") or "").strip()
                    if action == "connect" and not settings.console_address_ok(address):
                        raise Refusal(i18n.t("console.error.address"))
                    if action == "connect" and not key and not settings.read().get("console_key"):
                        raise Refusal(i18n.t("console.error.key"))
                    cfg = settings.read()
                    settings.write({**cfg, "console_url": address if action == "connect" else "",
                                    "console_key": (key or cfg.get("console_key")) if action == "connect" else "",
                                    "console_pin": str(data.get("pin") or "") if action == "connect" else "",
                                    "console_names": data.get("names", True) is not False})
                    central.STATE.update(last="", error="")
                    if action == "connect":
                        central.send(SUP.phase)
                elif action == "rules":   # accettare o no le regole che la console manda: lo sceglie chi usa il PC, o chi lo amministra
                    guard("console_rules")
                    settings.write({**settings.read(), "console_rules": data.get("accept") is True})
                    central.send(SUP.phase)   # accettandole arrivano subito; rifiutandole spariscono subito
                elif action == "send":
                    central.send(SUP.phase)
                elif action == "preview":
                    self._respond(200, {"preview": central.summary(SUP.phase)})
                    return
                self._respond(200, central.state())
            elif p == "/api/hook":   # il comando che i plugin delle app AI chiamano: lo mette, o lo toglie, chi usa il PC
                action = data.get("action")
                if action == "antigravity_link":   # la voce di Omissis nel file degli hook di Antigravity
                    if not hook_command.state()["ready"]:
                        raise Refusal(i18n.t("hooks.antigravity.needs"))
                    try:
                        hook_command.antigravity_link()
                    except ValueError:
                        raise Refusal(i18n.t("hooks.antigravity.unreadable", file=str(hook_command.antigravity_file())))
                elif action == "antigravity_relaunch":   # dalla configurazione guidata: collegata, e riaperta dal gateway se c'e'
                    if not hook_command.state()["ready"]:
                        hook_command.install()
                    try:
                        hook_command.antigravity_link()
                    except ValueError:
                        raise Refusal(i18n.t("hooks.antigravity.unreadable", file=str(hook_command.antigravity_file())))
                    kind = relaunch_kind("antigravity")
                    if kind:
                        relaunch_protected("antigravity")
                    self._respond(200, {**hook_state(), "relaunched": bool(kind)})
                    return
                elif action == "claude_plugin":   # dalla configurazione guidata: il comando e il plugin di Claude Code
                    onboarding.claude_plugin(PLUGIN_REPO, SUP.test)
                elif action == "antigravity_unlink":
                    hook_command.antigravity_unlink()
                elif action == "remove":
                    hook_command.remove()
                else:
                    hook_command.install()
                self._respond(200, hook_state())
            elif p == "/api/app":
                key = str(data.get("id", ""))
                if key not in connector.APP:
                    raise Refusal(i18n.t("program.app_unknown"))
                action = data.get("action")
                if action == "plugin":   # prepara la cartella del plugin; installarlo nell'app resta un gesto di chi usa il PC
                    if not connector.APP[key].get("plugin"):
                        raise Refusal(i18n.t("program.app_unknown"))
                    kimi_plugin.write()
                    self._respond(200, app_desktop())
                    return
                if action in ("proxy_on", "proxy_off"):   # l'app si protegge dal proxy del sistema: certificato e file PAC
                    app_proxy(key, action == "proxy_on")
                    self._respond(200, app_desktop())
                    return
                if action == "reopen":   # chi usa il PC ha chiesto di chiudere l'app e riaprirla com'e', per farle rileggere la rete
                    # nelle prove le app vere di questo PC non si chiudono (sulle macchine di prova si': lo dice chi lancia la prova)
                    if SUP.test and key != "test" and os.environ.get("OMISSIS_REAL_SYSTEM") != "1":
                        raise Refusal(i18n.t("app.proxy.error.test"))
                    connector.reopen_app(key)
                    self._respond(200, app_desktop())
                    return
                if action in ("launch", "relaunch") and SUP.phase != "active":
                    raise Refusal(i18n.t("program.app_needs_protection"))
                with APP_LOCK:
                    old = CONNECTORS.pop(key, None)
                    if old is not None:
                        old.close()
                    DETACHED.add(key) if action == "detach" else DETACHED.discard(key)
                    if action in ("launch", "relaunch"):
                        # "relaunch": chi usa il PC ha chiesto di chiudere l'app aperta senza protezione e riaprirla protetta
                        CONNECTORS[key] = connector.launch_app(key, close_first=action == "relaunch")
                self._respond(200, app_desktop())
            elif p == "/api/updates":
                action = data.get("action")
                if action == "check":
                    updates.check()
                elif action == "download":
                    if updates.STATUS["phase"] != "available":
                        raise Refusal(i18n.t("program.update_nothing_to_download"))
                    threading.Thread(target=updates.download, daemon=True).start()
                    time.sleep(0.3)
                elif action == "install":
                    version = updates.install()
                    if version is None:
                        why = updates.STATUS["error"] if updates.STATUS["phase"] == "error" else ""
                        raise Refusal(why or i18n.t("program.update_nothing_ready"))
                    turn_off()
                self._respond(200, updates.status())
            elif p == "/api/system":   # sul Mac, cio' che su Windows fa l'installer
                action = data.get("action")
                if action not in ("login_on", "login_off", "move", "uninstall", "quit") or not macapp.location():
                    raise Refusal(i18n.t("program.not_found"))
                if action == "quit":   # solo su Linux, dove l'icona con «Esci» puo' non esserci
                    if not sistema.LINUX:
                        raise Refusal(i18n.t("program.not_found"))
                    if settings.read()["always_on"]:
                        raise Refusal(i18n.t("managed.always_on"))
                    self._respond(200, {"quit": True})
                    turn_off()
                    return
                if not system_allowed():
                    raise Refusal(i18n.t("app.proxy.error.test"))
                if action in ("login_on", "login_off"):
                    macapp.login_item(action == "login_on")
                elif action == "move":
                    move_app()
                else:
                    self._respond(200, uninstall_app(bool(data.get("data"))))
                    return
                self._respond(200, system_card())
            elif p == "/api/try":
                text = str(data.get("text", ""))
                if len(text) > clipboard.MAX_TEXT:   # mai tagliare in silenzio: il pezzo tagliato sembrerebbe controllato
                    raise Refusal(i18n.t("program.text_too_long", n=clipboard.MAX_TEXT))
                # le correzioni fatte a mano su questo testo: cosa lasciare in chiaro e cosa mascherare comunque
                never = [str(x)[:200] for x in data.get("never") or []][:200]
                also = {str(k)[:200]: str(v) for k, v in list((data.get("also") or {}).items())[:200]}
                # l'esempio della configurazione guidata non e' uso vero: non entra nei conteggi ne' nell'archivio
                r = engine("/mask", {"texts": [text], "never": never, "also": also, **({"demo": True} if data.get("demo") else {})})
                if not data.get("demo"):
                    record_manual("text", r.get("counts"), text)
                self._respond(200, r)
            elif p == "/api/lists/add":   # da Testo: «non mascherare mai» e «maschera sempre», senza passare dalle Impostazioni
                list_name, term = ("never" if data.get("list_name") == "never" else "always"), str(data.get("term", "")).strip()[:200]
                if len(term) < 2 or "\n" in term or term.startswith("#"):
                    raise Refusal(i18n.t("program.term_not_valid"))
                lists = read_lists()
                if term.casefold() not in {x.casefold() for x in lists[list_name]}:
                    lists[list_name].append(term)
                    lists = write_lists(lists)
                self._respond(200, lists)
            elif p == "/api/restore":
                text = str(data.get("text", ""))
                if len(text) > clipboard.MAX_TEXT:
                    raise Refusal(i18n.t("program.text_too_long", n=clipboard.MAX_TEXT))
                found_items = sorted({m.group() for m in restore.RX_PLACEHOLDER.finditer(text)})
                mapping = engine("/values", {"placeholder": found_items})["mapping"] if found_items else {}
                self._respond(200, {"text": restore.restore(text, mapping.get), "restored": len(mapping),
                                     "unknown": len(found_items) - len(mapping)})
            elif p == "/api/clipboard":
                self._respond(200, {"outcome": clipboard.transform("restore" if data.get("action") == "restore" else "mask", manual("clipboard"))})
            elif p == "/api/documents/path":
                action = "restore" if data.get("action") == "restore" else "anonymize"
                outcome = documents.path(str(data.get("path", "")), action)
                if action == "anonymize":
                    for done in outcome.get("completed") or []:
                        record_manual("document", done.get("counts"))
                FOLDERS.add(os.path.normcase(os.path.abspath(str(outcome.get("destination", "")))))
                self._respond(200, outcome)
            elif p == "/api/documents/file":
                action = data.get("action") if data.get("action") in ("anonymize", "restore") else "auto"
                action, name, fresh, counts = documents.work_on_auto(Path(str(data.get("name", "file"))).name, base64.b64decode(data.get("content", "")), action)
                if action == "anonymize":
                    record_manual("document", counts)
                self._respond(200, {"action": action, "name": name, "content": base64.b64encode(fresh).decode("ascii"), "counts": counts})
            elif p == "/api/vault":
                self._respond(200, engine("/vault", {"limit": 500, "reveal": bool(data.get("reveal")), "search": str(data.get("search") or "")[:200],
                                                         "label": str(data.get("label") or "")[:40], "order": str(data.get("order") or "recent")}))
            elif p == "/api/vault/delete":   # voci scelte una per una, oppure per tipo e/o non usate da N giorni
                days = data.get("idle_days")
                self._respond(200, engine("/vault/delete", {"placeholder": [str(s) for s in data.get("placeholder") or []][:500],
                                                                 "label": str(data.get("label") or "")[:40],
                                                                 "idle_days": None if days in (None, "") else max(0.0, float(days)),
                                                                 "count_only": bool(data.get("count_only"))}))
            elif p == "/api/welcome/scan":   # le ricerche del primo avvio, una alla volta; «done» le mette insieme
                source = str(data.get("source", ""))
                if source != "done" and source not in onboarding.SOURCES:
                    raise Refusal(i18n.t("program.not_found"))
                self._respond(200, onboarding.finish_scan(SUP.test) if source == "done" else onboarding.scan_source(source, SUP.test))
            elif p == "/api/welcome/rules":   # il passo «Cosa proteggo?»: le regole scelte, solo per i servizi non imposti
                cfg, fixed = settings.read(), settings.locked()["policies"]
                wanted = {k: v for k, v in ((str(k), str(v)) for k, v in (data.get("policies") or {}).items())
                          if k in catalog.PER_ID and v in catalog.POLICIES and k not in fixed
                          and (v != "protect" or catalog.protectable(catalog.PER_ID[k]))}
                if wanted:
                    settings.write({**cfg, "policies": {**cfg["policies"], **wanted}})
                self._respond(200, {"restart_needed": SUP.restart_needed(), "applied": sorted(wanted)})
            elif p == "/api/ask":   # la risposta all'avviso per un'app AI aperta: una regola, «Non ora» o «Non chiederlo piu'»
                ident, choice, cfg = str(data.get("id", "")), str(data.get("choice", "")), settings.read()
                s = catalog.PER_ID.get(ident)
                if s is None:
                    raise Refusal(i18n.t("program.app_unknown"))
                outcome = {}
                if choice == "never":
                    settings.write({**cfg, "ask_never": sorted(set(cfg["ask_never"]) | {ident})})
                elif choice in catalog.POLICIES:
                    if ident in settings.locked()["policies"]:
                        raise Refusal(i18n.t("managed.locked"))
                    if choice == "protect" and not catalog.protectable(s):
                        raise Refusal(i18n.t("ask.not_protectable", app=s["name"]))
                    settings.write({**cfg, "policies": {**cfg["policies"], ident: choice}})
                    if choice == "protect":
                        outcome = apply_protection(ident)
                elif choice != "later":
                    raise Refusal(i18n.t("program.not_found"))
                ASK["pending"].pop(ident, None)
                self._respond(200, outcome)
            elif p == "/api/inventory/scan":
                news = analyze("manual")
                self._respond(200, {"news": news, **inventory_status()})
            elif p == "/api/inventory/verdict":
                inventory.judge(str(data.get("key", "")), data.get("verdict"), data.get("note"))
                self._respond(200, {})
            elif p == "/api/inventory/forget":
                self._respond(200, {"dropped": inventory.forget(), **inventory_status()})
            elif p == "/api/inventory/clear":
                inventory.clear()
                self._respond(200, inventory_status())
            elif p == "/api/folder/choose":   # la finestra di Windows per scegliere una cartella, al posto del percorso scritto a mano
                choice = folders.choose(i18n.t("documents.folder.win"), str(data.get("initial") or ""))
                if choice is None:
                    raise Refusal(i18n.t("program.window_already_opened"))
                if choice:
                    FOLDERS.add(os.path.normcase(os.path.abspath(choice)))
                self._respond(200, {"path": choice})
            elif p == "/api/folder/open":
                path = os.path.normcase(os.path.abspath(str(data.get("path", ""))))
                if path not in FOLDERS or not folders.open_up(path):
                    raise Refusal(i18n.t("program.folder_not_openable"))
                self._respond(200, {})
            elif p == "/api/vault/clear":
                self._respond(200, engine("/vault/clear", {}))
            elif p == "/api/certificate":
                self._respond(200, certificate(data.get("action")))
            elif p == "/api/browser":
                address = str(data.get("address", "https://claude.ai"))
                if not address.startswith("https://") or catalog.find(urllib.parse.urlparse(address).hostname or "") is None:
                    raise Refusal(i18n.t("program.address_outside_catalog"))
                r = subprocess.run([sys.executable, str(HERE / "browser_window.py"), address], capture_output=True, timeout=30,
                                   creationflags=NO_WINDOW)
                self._respond(200, {"outcome": r.stdout.decode("utf-8", errors="replace").strip() or r.stderr.decode("utf-8", errors="replace").strip()})
            else:
                self._respond(404, {"error": i18n.t("program.not_found")})
        except (documents.Error, connector.Error, Refusal) as ex:
            self._respond(422, {"error": str(ex)})
        except urllib.error.URLError:
            self._respond(503, {"error": i18n.t("program.protection_not_active")})
        except Exception as ex:   # noqa: BLE001
            self._respond(500, {"error": f"{type(ex).__name__}: {ex}"})


def linux_tray():
    """Su Linux l'icona si puo' mostrare solo dove il desktop ha un'area per le icone dei programmi raggiungibile da X11
    (KDE, Xfce, Cinnamon, MATE; GNOME solo con un'estensione; in una sessione solo Wayland no). Si guarda prima, per
    non lasciare un'icona che non compare e riempie il registro di errori."""
    try:
        import Xlib.X
        import Xlib.display
        display = Xlib.display.Display()
        try:
            atom = display.intern_atom(f"_NET_SYSTEM_TRAY_S{display.get_default_screen()}")
            return display.get_selection_owner(atom) != Xlib.X.NONE
        finally:
            display.close()
    except Exception:   # noqa: BLE001  (niente X11, o libreria assente)
        return False


def notify_only():
    """Senza icona (Linux, dove il desktop non la mostra) gli avvisi arrivano lo stesso, come notifiche del sistema, se
    c'e' notify-send. Il pannello si riapre dal menu delle applicazioni o con il comando «omissis»."""
    global NOTIFY
    if shutil.which("notify-send"):
        def notify(message):
            ASK["last"] = ""
            sistema.notify(message)
        NOTIFY = notify


def icon(server):
    """Icona vicino all'orologio. Se le librerie mancano il programma funziona lo stesso dalla pagina."""
    if sistema.LINUX:
        # avviato all'accesso, il desktop puo' non avere ancora pronta l'area delle icone: la si aspetta per un po'
        for _ in range(20 if "--no-browser" in sys.argv and not SUP.test else 1):
            if linux_tray():
                break
            time.sleep(1)
        else:
            notify_only()
            return None
    try:
        import pystray
        from PIL import Image, ImageDraw
    except (Exception if sistema.LINUX else ImportError):   # noqa: BLE001  (su Linux pystray, senza un desktop, si rompe in altri modi)
        return None

    def drawing(active):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        color = (16, 122, 107, 255) if active else (140, 140, 140, 255)
        d.polygon([(32, 4), (58, 14), (58, 34), (32, 60), (6, 34), (6, 14)], fill=color)
        d.line([(20, 32), (29, 41), (45, 23)], fill=(255, 255, 255, 255), width=6)
        return im

    def open_up(*_):
        webbrowser.open(f"http://127.0.0.1:{PANEL_PORT}/")

    def stays_on():   # chi amministra il PC, o la console, ha stabilito che la protezione non si spenga
        return settings.read()["always_on"]

    def change(ic, _):
        if SUP.phase != "active":
            SUP.launch()
        elif stays_on():
            notify(i18n.t("managed.always_on"))
        else:
            SUP.stop()

    def exit_app(ic, _):
        if stays_on():
            notify(i18n.t("managed.always_on"))
            return
        pac_apply(leaving=True)
        SUP.stop()
        ic.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    def answer_asks(*_):   # la prima app AI nuova ancora senza risposta: si apre la finestrella per decidere
        waiting = list(ASK["pending"])
        if waiting:
            open_window(f"http://127.0.0.1:{PANEL_PORT}/#/ask/{waiting[0]}")

    def with_keystrokes(name):   # «Maschera gli appunti  (Ctrl+Alt+M)»: la combinazione compare solo se e' attiva
        entry = (SHORTCUTS.status if SHORTCUTS else {}).get(name, {})
        return i18n.t(f"icon.{name}") + (f"  ({clipboard.caption(entry['combo'])})" if entry.get("active") else "")

    def on_clipboard(action):
        def run(icon_, _):
            try:
                notify(clipboard.transform(action, manual("clipboard")))
            except Exception:   # noqa: BLE001
                notify(i18n.t("program.protection_not_active"))
        return run

    ic = pystray.Icon("omissis", drawing(False), "Omissis", menu=pystray.Menu(
        # i testi sono funzioni: il menu segue la lingua scelta nelle Impostazioni senza riavviare il programma
        pystray.MenuItem(lambda _: i18n.t("icon.open_up"), open_up, default=True),
        pystray.MenuItem(lambda _: i18n.t("icon.ask", n=len(ASK["pending"])), answer_asks, visible=lambda _: bool(ASK["pending"])),
        pystray.MenuItem(lambda _: with_keystrokes("mask"), on_clipboard("mask")),
        pystray.MenuItem(lambda _: with_keystrokes("restore"), on_clipboard("restore")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda _: i18n.t("icon.stop" if SUP.phase == "active" else "icon.launch"), change,
                         enabled=lambda _: not (SUP.phase == "active" and stays_on())),
        pystray.MenuItem(lambda _: i18n.t("icon.exit_app"), exit_app, enabled=lambda _: not stays_on())))

    def refresh():
        latest, notified, waiting, told, begun = None, "", 0, False, time.time()
        while ic.visible or latest is None:
            if not told and time.time() - begun > 15:   # sul Mac: l'ultimo cambio di versione non e' riuscito
                told, failed = True, updates.failed()
                if failed:
                    notify(i18n.t("updates.failed", v=failed))
            if len(ASK["pending"]) != waiting:   # compare o sparisce la voce per le app AI nuove
                waiting = len(ASK["pending"])
                try:
                    ic.update_menu()
                except Exception:   # noqa: BLE001
                    pass
            if SUP.phase != latest:
                latest = SUP.phase
                ic.icon = drawing(latest == "active")
                ic.title = i18n.t(f"icon.status.{latest if latest in ('active', 'startup', 'error', 'model') else 'stop'}")
            agg = updates.STATUS
            if agg["phase"] == "ready_now" and notified != agg["version"]:
                notified = agg["version"]
                notify(i18n.t("icon.update_ready", v=notified))
            time.sleep(1)

    threading.Thread(target=refresh, daemon=True).start()

    # Il clic su una notifica arriva all'icona come NIN_BALLOONUSERCLICK, che pystray non gestisce: lo si intercetta qui.
    # Se pystray cambia e la voce non c'e', le notifiche restano come prima (senza clic).
    try:
        handlers = ic._message_handlers
        message = next(k for k, v in handlers.items() if getattr(v, "__name__", "") == "_on_notify")
        original = handlers[message]

        def on_notify(wparam, lparam):
            if lparam == 0x0405:   # NIN_BALLOONUSERCLICK
                threading.Thread(target=balloon_click, daemon=True).start()
            return original(wparam, lparam)
        handlers[message] = on_notify
    except Exception:   # noqa: BLE001
        pass

    def notify(message):   # esito delle scorciatoie sugli appunti e avvisi, come notifica di Windows
        ASK["last"] = ""   # il clic su questa notifica apre il pannello (l'avviso per un'app nuova lo rimette dopo)
        if sistema.notify(message):   # sul Mac la notifica la fa il sistema: l'icona di pystray non le sa fare
            return
        try:
            ic.notify(message, "Omissis")
        except Exception:   # noqa: BLE001
            pass

    global SHORTCUTS, NOTIFY
    NOTIFY = notify
    SHORTCUTS = clipboard.shortcuts(manual("clipboard"), notify)
    in_use, changed = clipboard.system(SHORTCUTS, clipboard.choices(settings.read()))
    if changed:   # una combinazione era gia' di un altro programma: si tiene quella libera e lo si dice, a icona comparsa
        settings.write({**settings.read(), "shortcuts": in_use})
        listing = ", ".join(f"{clipboard.caption(old_one)} → {clipboard.caption(new_one)}" for old_one, new_one in changed.values())
        threading.Timer(8, lambda: notify(i18n.t("shortcuts.changed", listing=listing))).start()
    return ic


def quit_running():
    """«omissis --quit» (Linux): chiede alla copia accesa di chiudersi. Dove e' stabilito che la protezione resti sempre
    accesa non lo fa. Restituisce il codice di uscita."""
    if settings.read()["always_on"]:
        print(i18n.t("managed.always_on"), flush=True)
        return 1
    try:
        pid = int((DATA / "omissis.pid").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid = 0
    ours = [p for p in sistema.command_line_pids("panel.py") if p == pid]
    if not ours or not opened_port(PANEL_PORT):
        print("Omissis non è acceso", flush=True)
        return 0
    os.kill(pid, signal.SIGTERM)
    for _ in range(100):
        if not opened_port(PANEL_PORT):
            print("Omissis è stato chiuso", flush=True)
            return 0
        time.sleep(0.2)
    print("Omissis non si è chiuso", flush=True)
    return 1


def running():
    """Chi risponde sulla porta del pannello: "" nessuno; "omissis" una copia gia' accesa (si apre il suo pannello);
    "frozen" il pannello di questa copia, che pero' non risponde piu'; "other" un altro programma. Che la porta sia presa
    lo dice free_port, non un collegamento riuscito: un programma bloccato con la coda piena non ne accetta piu'."""
    if free_port(PANEL_PORT):
        return ""
    for _ in range(3):   # con calma: all'accesso al computer un pannello che sta bene puo' metterci qualche secondo
        try:
            with DIRECT.open(f"http://127.0.0.1:{PANEL_PORT}/", timeout=5) as r:
                return "omissis" if b'name="omissis-code"' in r.read(20000) else "other"
        except urllib.error.HTTPError:
            return "other"
        except Exception:   # noqa: BLE001  (non risponde, o non parla come una pagina: si guarda di chi e' il processo)
            pass
    if free_port(PANEL_PORT):   # nel frattempo si e' liberata: era una copia che si stava chiudendo
        return ""
    who = sistema.port_process(PANEL_PORT) or {}
    mine = os.path.normcase(str(HERE / "panel.py"))
    for x in who.get("arguments", []):
        try:
            if os.path.normcase(os.path.abspath(os.path.join(who.get("folder") or "", x))) == mine:
                return "frozen"
        except (OSError, ValueError):
            pass
    return "other"


def greet(a):
    """All'avvio, con la porta del pannello che risponde gia'. True se questa copia non deve partire: c'e' gia' un Omissis
    acceso (si apre il suo pannello). Se e' il pannello di questa copia rimasto bloccato lo si chiude e si parte (False).
    Se la porta e' di un altro programma Omissis non puo' partire: lo dice, con il nome di quel programma, ed esce."""
    state = running()
    if state == "frozen":
        who = sistema.port_process(PANEL_PORT)
        if who:
            try:
                connector._kill(who["pid"])
            except Exception:   # noqa: BLE001
                pass
        if Supervisor._wait_free(PANEL_PORT, 10):
            print("il pannello di prima non rispondeva più: l'ho chiuso", flush=True)
            return False
        state = "other"
    if state == "omissis":
        print(f"Omissis è già acceso: apro il pannello su http://127.0.0.1:{PANEL_PORT}/", flush=True)
        if not a.without_browser:
            webbrowser.open(f"http://127.0.0.1:{PANEL_PORT}/")
        return True
    if state == "other":
        who = Supervisor._who(PANEL_PORT)[0]
        if Supervisor._wait_free(PANEL_PORT, 3):   # un programma che si stava chiudendo: la porta e' tornata libera
            return False
        text = i18n.t("program.panel_port_busy", port=PANEL_PORT, who=who)
        print(text, flush=True)
        if not a.test:
            sistema.alert(text)
        sys.exit(3)
    return False


def main():
    global SUP
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tray", dest="without_icon", action="store_true")
    ap.add_argument("--no-browser", dest="without_browser", action="store_true")
    ap.add_argument("--no-start", dest="do_not_launch", action="store_true", help="apre il pannello senza avviare la protezione")
    ap.add_argument("--test", dest="test", action="store_true", help="accetta anche il servizio finto in locale")
    ap.add_argument("--quit", dest="quit", action="store_true", help="su Linux: chiude la copia accesa (la protezione si ferma)")
    a = ap.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    if sistema.LINUX:
        try:
            os.chmod(DATA, 0o700)   # archivio, registro e impostazioni: solo di chi usa il computer, anche su un PC con piu' utenti
        except OSError:
            pass
        if a.quit:
            sys.exit(quit_running())
    if greet(a):   # gia' acceso: si apre solo il pannello
        return
    if updates.mode() == "automatic":
        version = updates.install(automatic=True)   # un aggiornamento gia' scaricato e verificato si installa ora
        if version:
            print(f"installo la versione {version}: il programma si riapre da solo", flush=True)
            return
    if paths.INSTALLED is not None and not LISTS.exists():   # le liste personali partono da quelle di esempio
        shutil.copytree(paths.model_folder() / "lists", LISTS)
    SUP = Supervisor(test=a.test)
    if a.test:   # un'app di prova per il connettore: il Chromium usato dalle prove, senza estensione
        chrome = paths.test_browser()
        if chrome:
            os.environ["OMISSIS_TEST"] = "1"
            connector.APP["test"] = {"name": "App di prova", "commands": [str(chrome)], "port": 9560, "service": "claude",
                                       "arguments": ["--headless=new", "--no-first-run", f"--user-data-dir={DATA / 'test_app'}",
                                                     "about:blank"]}
    class Service(ThreadingHTTPServer):
        # Una seconda copia del programma deve accorgersi che la prima e' gia' accesa: su Windows «riusare l'indirizzo»
        # lascerebbe aprire due servizi sulla stessa porta. Sul Mac e su Linux no: li' serve solo a ripartire subito
        # dopo una chiusura (un aggiornamento, un riavvio), quando il sistema tiene la porta ancora per mezzo minuto
        allow_reuse_address = not sistema.WINDOWS

    try:
        server = Service(("127.0.0.1", PANEL_PORT), Handler)
    except OSError:   # la porta non si lascia prendere: un'altra copia arrivata un attimo prima, oppure un altro programma
        if greet(a):
            return
        text = i18n.t("program.panel_port_busy", port=PANEL_PORT, who=Supervisor._who(PANEL_PORT)[0])
        print(text, flush=True)
        if not a.test:
            sistema.alert(text)
        sys.exit(3)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if sistema.LINUX:
        # alla chiusura della sessione (o con «omissis --quit») il programma riceve SIGTERM: deve fermare motore e proxy,
        # non lasciarli accesi senza pannello. Il numero del processo sta in un file, per «omissis --quit»
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        (DATA / "omissis.pid").write_text(str(os.getpid()), encoding="utf-8")
    updates.started()   # sul Mac: chi ha appena messo questa versione al posto della vecchia aspetta di saperla partita
    first_login_item(a.test)
    threading.Thread(target=updates.loop, daemon=True).start()
    threading.Thread(target=keep_on, args=(3 if a.test else 30,), daemon=True).start()   # non fa nulla finche' always_on e' spento
    threading.Thread(target=SUP.watch, daemon=True).start()   # un processo caduto si vede subito, anche a pannello chiuso
    if not a.test:   # nelle prove niente lavoro in sottofondo: i risultati devono dipendere solo da cio' che la prova fa
        threading.Thread(target=watch, daemon=True).start()
        threading.Thread(target=watch_apps, daemon=True).start()
        threading.Thread(target=watch_new_apps, daemon=True).start()
        threading.Thread(target=central.loop, args=(lambda: SUP.phase,), daemon=True).start()
    if not a.do_not_launch:
        SUP.launch()
    address = f"http://127.0.0.1:{PANEL_PORT}/"
    print(f"pannello su {address}", flush=True)
    if not a.without_browser:
        webbrowser.open(address)
    try:
        global ICON
        ICON = ic = None if a.without_icon else icon(server)
        if ic is not None:
            ic.run()
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        pac_apply(leaving=True)
        SUP.stop()


if __name__ == "__main__":
    main()
