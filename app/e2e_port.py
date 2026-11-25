# -*- coding: utf-8 -*-
"""Prova, senza rete e senza browser, l'avvio della protezione quando la porta del proxy non e' libera, e che cosa dice il
programma quando uno dei suoi processi si chiude. Motore finto (un processo che aspetta), proxy vero, dati in una cartella
provvisoria.

Controlla che: con la porta libera il proxy parta li' e nulla cambi; con la porta presa da un altro programma (solo su
questo PC, o su tutte le interfacce) il proxy parta da solo su una porta di riserva, la scelta venga salvata, lo stato lo
dica e l'altro programma resti dov'era; valga anche se la porta viene presa all'ultimo momento; una porta stabilita da
chi amministra il PC non venga cambiata e l'errore la nomini; un processo che si chiude a protezione accesa venga
annotato per nome, con il codice di uscita, e la protezione riparta da sola (fino a tre volte in pochi minuti: poi resta
ferma e dice perche'); i messaggi dicano quale programma sta usando la porta; la segnalazione racconti in breve che cosa
e' successo; dal motivo della chiusura escano solo tipi di errore e codici, mai il testo.
Poi i processi rimasti accesi: se il pannello si chiude di colpo, motore e proxy si chiudono da soli; quelli rimasti da
un avvio precedente (di una versione che non lo faceva) vengono riconosciuti e chiusi all'avvio, senza cambiare porta e
senza toccare quelli di un'altra copia; se la porta del motore e' di un altro programma l'errore la nomina. Qui il
motore e' il servizio vero del motore con un modello finto, che non si carica.
Poi i processi vivi che non rispondono piu': alla domanda «ci sei?» il motore e il proxy rispondono senza aspettare
nessuno; un motore al lavoro su un testo lungo che avanza non viene toccato; uno con una richiesta che non avanza, uno
sospeso e un proxy sospeso vengono chiusi e la protezione riparte. E la porta del pannello: se e' di un altro programma
Omissis non parte e dice quale; se c'e' gia' un Omissis acceso apre il suo; se e' il suo pannello rimasto bloccato lo
chiude e parte.
Non ha bisogno della copia di prova accesa: gira uguale su Windows, Mac e Linux.

   Uso: python e2e_port.py
"""
import collections
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def nobody_on(port):
    """Nessuno ascolta e la porta si lascia prendere (prima di caricare il programma, che ha la sua funzione)."""
    with socket.socket() as s:
        s.settimeout(0.3)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return False
    with socket.socket() as s:
        if os.name != "nt":   # come fa un server: una porta appena lasciata si riprende subito
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


# porte tutte nostre: tre per il programma, una per il proxy, venti di riserva. Lontane da quelle di una copia accesa
BASE = next(b for b in range(8975, 9975, 200) if all(nobody_on(p) for p in [b, b + 1, b + 2, b + 20, *range(b + 100, b + 120)]))
PORT = BASE + 20
data = Path(tempfile.mkdtemp(prefix="omissis-e2e-port-"))
imposed = data / "imposte.json"
os.environ.update(OMISSIS_DATA=str(data), OMISSIS_PORT=str(BASE), OMISSIS_TEST="1", OMISSIS_MANAGED_FILE=str(imposed))
for name in ("OMISSIS_FAKE_SYSTEM", "OMISSIS_REAL_SYSTEM", "OMISSIS_TEST_ADDON"):   # le impostazioni del computer non si toccano
    os.environ.pop(name, None)
(data / "token.txt").write_text("x", encoding="utf-8")
(data / "token_extension.txt").write_text("segreto-di-prova", encoding="utf-8")
sys.path.insert(0, str(HERE))

import i18n        # noqa: E402
import managed     # noqa: E402
import panel       # noqa: E402
import paths       # noqa: E402
import settings    # noqa: E402
import sistema     # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
outcomes = []
SPARE = list(panel.spare_ports())
HAS_PSUTIL = importlib.util.find_spec("psutil") is not None   # senza, il programma non sa dire chi usa una porta
CAUSE = re.compile(r"(proxy|engine) exit \S+( (\[(Errno|WinError) -?\d+\]|_?[A-Z]\w*(Error|Exception)))*")


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(f"{'OK    ' if ok else 'ERRORE'} {name}{'   ' + str(note) if note and not ok else ''}", flush=True)


class other_program:
    """Un altro programma che ascolta su una porta e accetta chi si collega, contandolo."""

    def __init__(self, host, port):
        self.socket, self.accepted = socket.socket(), 0
        if os.name != "nt":   # su Linux e Mac, senza, la porta di un programma appena chiuso resta negata per un minuto
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((host, port))
        self.socket.listen(16)
        self.socket.settimeout(0.2)
        self.closing = False
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self):
        while not self.closing:
            try:
                self.socket.accept()[0].close()
            except socket.timeout:
                continue
            except OSError:   # chiuso
                return
            self.accepted += 1

    def close(self):
        self.closing = True
        self.thread.join(3)   # su Linux e Mac chi sta aspettando un collegamento terrebbe la porta anche dopo la chiusura
        self.socket.close()


def reaches(listener, port):
    """Chi si collega alla porta arriva proprio a quel programma."""
    before = listener.accepted
    try:
        socket.create_connection(("127.0.0.1", port), timeout=3).close()
    except OSError:
        return False
    for _ in range(30):
        if listener.accepted > before:
            return True
        time.sleep(0.1)
    return False


def supervisor(port, engine=True):
    """La protezione con il motore gia' «acceso» (un processo che aspetta): parte solo il proxy, sulla porta scelta.
    Con engine=False l'avvio fa partire anche il motore: quello finto (vedi FAKE_ENGINE)."""
    if panel.SUP is not None:
        panel.SUP.stop()
    settings.write({**settings.read(), "port": port})
    sup = panel.Supervisor(test=True)
    panel.SUP = sup
    if engine:
        sup.engine = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)"])
        sup.launched_with = (sup._engine_choices(settings.read()), None, ())
    return sup


# Un motore finto: il servizio vero del motore (engine.serve: le domande del pannello, il conto di cio' che e' in
# lavorazione) con dietro un modello finto. Prende la porta solo dopo un po', come quello vero che prima carica il
# modello, e avviato dal pannello si chiude con lui (sistema.follow_parent)
FAKE_ENGINE = '''# -*- coding: utf-8 -*-
import itertools, os, sys, threading, time, types
sys.path.insert(0, {here!r})
import sistema
sistema.follow_parent()
import engine
port = int(sys.argv[sys.argv.index("--port") + 1])
token = open(os.path.join(os.environ["OMISSIS_DATA"], "token.txt"), encoding="utf-8").read().strip()
time.sleep(1.5)


class Fake(engine.Engine):
    """Il motore vero senza modello. Un testo che contiene FERMO non finisce mai e non avanza; uno che contiene LUNGO dura
    sei secondi e avanza ogni mezzo secondo, come un documento lungo."""
    remote = None
    det = types.SimpleNamespace(mod=types.SimpleNamespace(name_or_path="finto"), device="cpu", threshold=0.9, state={{}})
    vault = types.SimpleNamespace(entries=lambda: 0, seal=types.SimpleNamespace(is_active=False))

    def __init__(self):
        self.progress, self.masking, self.numbers = time.monotonic(), {{}}, itertools.count()

    def _mask(self, texts, *a, **k):
        if any("FERMO" in t for t in texts):
            threading.Event().wait()
        if any("LUNGO" in t for t in texts):
            for _ in range(12):
                time.sleep(0.5)
                self.progress = time.monotonic()
        return {{"texts": list(texts), "positions": [[] for _ in texts], "mapping": {{}}, "counts": {{}}, "ms": 0}}


engine.serve(Fake(), port, token, "estensione", None)
'''
# Un pannello di prova in un processo a parte: accende la protezione (motore finto, proxy vero) e resta li'
STAND_IN = '''# -*- coding: utf-8 -*-
import os, sys, time
from pathlib import Path
sys.path.insert(0, {here!r})
import panel, settings
panel.ENGINE_SCRIPT = Path(sys.argv[1])
panel.weights.missing = lambda model: False
settings.write({{**settings.read(), "port": int(sys.argv[2])}})
panel.SUP = panel.Supervisor(test=True)
panel.SUP._launch()
print("PRONTO", os.getpid(), panel.SUP.phase, panel.SUP.error, flush=True)
time.sleep(600)
'''


STARTED = []   # i processi avviati dalla prova: alla fine non ne deve restare nessuno, comunque sia andata


def alive():
    """La risposta del motore alla domanda «ci sei?»."""
    return panel.engine("/alive", timeout=5)


def work(word):
    """Chiede al motore di mascherare un testo (da un altro thread: puo' non finire mai)."""
    def ask():
        try:
            panel.engine("/mask", {"texts": [f"prova {word}"]}, timeout=600)
        except Exception:   # noqa: BLE001  (il motore viene chiuso mentre lavora: e' la prova)
            pass
    threading.Thread(target=ask, daemon=True).start()


def freeze(port):
    """Sospende il processo che ascolta sulla porta: resta vivo, ma non risponde piu'. Torna il suo numero."""
    import psutil
    pid = sistema.port_process(port)["pid"]
    psutil.Process(pid).suspend()
    return pid


def real_panel():
    """Il pannello vero in un processo a parte, senza avviare la protezione: (processo, che cosa ha scritto finora)."""
    p = subprocess.Popen([sys.executable, str(HERE / "panel.py"), "--test", "--no-tray", "--no-browser", "--no-start"], env={**os.environ, "PYTHONUTF8": "1"},
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=panel.NO_WINDOW)
    STARTED.append(p)
    return p


def quiet(command, **more):
    """Un processo avviato come lo avrebbe avviato una versione di prima: senza il tubo che lo lega al pannello."""
    env = {k: v for k, v in {**os.environ, **more.pop("env", {})}.items() if k != "OMISSIS_PARENT"}
    STARTED.append(subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=panel.NO_WINDOW, **more))
    return STARTED[-1]


def answers(port, seconds=30):
    """Aspetta che sulla porta risponda qualcuno."""
    for _ in range(seconds * 5):
        if panel.opened_port(port):
            return True
        time.sleep(0.2)
    return False


def left_engine(port):
    """Un motore (finto) rimasto acceso: stessi argomenti di quello avviato dal pannello."""
    p = quiet([str(panel.PY_MODEL), str(panel.ENGINE_SCRIPT), "--model", "x", "--port", str(port)])
    answers(port)
    return p


def left_proxy(port):
    """Un proxy (vero) rimasto acceso: stessi argomenti di quello avviato dal pannello, sulla nostra cartella dei dati."""
    p = quiet([*paths.mitmdump(), "-q", "-s", str(panel.HERE / "addon.py"), "--listen-host", "127.0.0.1", "-p", str(port),
               "--set", f"confdir={panel.DATA / 'ca'}"], cwd=panel.HERE,
              env={"PYTHONUTF8": "1", "OMISSIS_TEST": "1", "OMISSIS_ENGINE_URL": f"http://127.0.0.1:{BASE}"})
    answers(port)
    return p


def gone(*processes, seconds=10):
    """I processi sono finiti (si aspetta un po')."""
    for _ in range(seconds * 5):
        if all(p.poll() is not None for p in processes):
            return True
        time.sleep(0.2)
    return False


def freed(*ports, seconds=15):
    """Le porte tornano libere (si aspetta un po')."""
    for _ in range(seconds * 5):
        if all(nobody_on(p) for p in ports):
            return True
        time.sleep(0.2)
    return False


def impose(values):
    """Cio' che chi amministra il PC ha stabilito (il file delle prove), da subito."""
    if values is None:
        imposed.unlink(missing_ok=True)
    else:
        imposed.write_text(json.dumps(values), encoding="utf-8")
    managed._cache["until"] = 0.0
    settings._cache["data"] = None


def back(sup, seconds=60):
    """Aspetta che la protezione sia di nuovo accesa (False se resta in errore, o non riparte)."""
    for _ in range(seconds * 4):
        if sup.phase == "active":
            return True
        if sup.phase in ("error", "stop"):
            return False
        time.sleep(0.25)
    return False


def moved(sup, old, new):
    """Lo spostamento di porta annotato e' quello, e dice chi teneva la porta: qui questa stessa prova, cioe' un Python."""
    m = sup.port_moved or {}
    return (m.get("from"), m.get("to")) == (old, new) and (not HAS_PSUTIL or "python" in str(m.get("by")).lower())


def closed(wait=5):
    """Aspetta che lo stato si accorga del processo chiuso."""
    for _ in range(wait * 4):
        now = panel.SUP.status()
        if now["phase"] != "active":
            return now
        time.sleep(0.25)
    return panel.SUP.status()


class Ended:
    """Un processo gia' finito, con cio' che aveva scritto."""

    def __init__(self, code, lines):
        self.code, self.output = code, collections.namedtuple("Output", "lines")(collections.deque(lines))

    def poll(self):
        return self.code


def main():
    print(f"porte della prova: programma {BASE}-{BASE + 2}, proxy {PORT}, riserva {SPARE[0]}-{SPARE[-1]}")
    # quando l'avvio fa partire il motore, e' quello finto; e i pesi del modello non si scaricano
    panel.ENGINE_SCRIPT = data / "motore" / "engine.py"
    panel.ENGINE_SCRIPT.parent.mkdir()
    panel.ENGINE_SCRIPT.write_text(FAKE_ENGINE.format(here=str(HERE)), encoding="utf-8")
    panel.weights.missing = lambda model: False

    # --- la porta scelta e' libera
    sup = supervisor(PORT)
    sup._launch()
    now = sup.status()
    mark("porta libera: il proxy parte sulla porta scelta e nulla cambia", sup.phase == "active" and panel.opened_port(PORT) and settings.read()["port"] == PORT
         and sup.port_moved is None and now["phase"] == "active" and now["port_moved"] is None, (sup.phase, sup.error))
    mark("porta libera: nessun riavvio richiesto", not sup.restart_needed() and sup.launched_with[1] == PORT)

    # --- un processo che si chiude a protezione accesa: il programma se ne accorge, annota quale, e la protezione riparte
    first = sup.proxy
    first.kill()
    closed()
    fell = [what for _, what in sup.events if what.startswith("proxy exit")]
    mark("proxy chiuso a protezione accesa: il programma annota che e' il proxy, con il codice di uscita", len(fell) == 1 and bool(CAUSE.fullmatch(fell[0]))
         and str(first.returncode) in fell[0], list(sup.events))
    mark("proxy chiuso: la protezione riparte da sola, con un proxy nuovo sulla stessa porta", back(sup) and sup.proxy is not first and sup._alive(sup.proxy)
         and panel.opened_port(PORT) and settings.read()["port"] == PORT and sup.port_moved is None and len(sup.falls) == 1, (sup.phase, sup.error, len(sup.falls)))
    for _ in range(panel.RESTARTS - 1):   # ancora, fino a esaurire le ripartenze
        sup.proxy.kill()
        closed()
        back(sup)
    mark("proxy chiuso piu' volte: la protezione riparte da sola fino a tre volte in pochi minuti", sup.phase == "active" and len(sup.falls) == panel.RESTARTS
         and sup._alive(sup.proxy), (sup.phase, sup.error, len(sup.falls)))
    last = sup.proxy
    last.kill()
    now = closed()
    time.sleep(1)
    mark("proxy chiuso una volta di troppo: la protezione resta ferma e lo stato dice perche'", now["phase"] == "error" and sup.status()["phase"] == "error"
         and now["error"].startswith(i18n.t("program.closed.proxy")) and str(last.returncode) in now["error"]
         and i18n.t("program.closed.again", n=panel.RESTARTS) in now["error"], now["error"])
    mark("proxy chiuso: il motivo per la segnalazione ha solo nomi, codici e tipi di errore", bool(CAUSE.fullmatch(sup.cause)) and sup.cause.startswith("proxy exit"), sup.cause)
    sup.launch()   # a mano: il conto delle ripartenze ricomincia
    mark("un avvio a mano azzera l'errore e il conto delle ripartenze", sup.cause == "" and sup.error == "" and len(sup.falls) == 0 and back(sup), (sup.phase, sup.error))
    told = sup.summary()
    mark("la segnalazione racconta in breve che cosa e' successo alla protezione, senza testi", "proxy exit" in told and "restart 1/3" in told and "gave up" in told
         and bool(re.fullmatch(r"[\x20-\x7e·]*", told)), told)
    sup.stop()
    mark("dopo la chiusura la porta torna libera", any(nobody_on(PORT) or time.sleep(0.5) for _ in range(20)))

    sup = supervisor(PORT)
    sup._launch()
    first, same_proxy = sup.engine, sup.proxy
    first.kill()
    closed()
    mark("motore chiuso a protezione accesa: il programma annota che e' il motore, e la protezione riparte da sola con un motore nuovo",
         any(what.startswith("engine exit") for _, what in sup.events) and back(sup) and sup.engine is not first and sup._alive(sup.engine)
         and panel.engine("/status", timeout=5).get("model") == "finto", (sup.phase, sup.error, list(sup.events)))
    mark("motore chiuso: riparte solo lui, il proxy resta quello di prima", sup.proxy is same_proxy and sup._alive(sup.proxy) and panel.opened_port(PORT))
    sup.stop()
    freed(BASE, PORT)

    # --- la porta scelta e' di un altro programma, su questo PC soltanto
    other = other_program("127.0.0.1", PORT)
    sup = supervisor(PORT)
    sup._launch()
    new = settings.read()["port"]
    now = sup.status()
    mark("porta occupata: la protezione parte lo stesso", sup.phase == "active" and sup._alive(sup.proxy), (sup.phase, sup.error))
    mark("porta occupata: il proxy ha preso da solo la prima porta di riserva", new == SPARE[0] and panel.opened_port(new), new)
    mark("porta occupata: la nuova porta e' la scelta salvata, senza riavvii da fare", json.loads(settings.FILE.read_text(encoding="utf-8"))["port"] == new
         and sup.launched_with[1] == new and not sup.restart_needed())
    mark("porta occupata: lo stato dice da quale porta a quale, e quale programma la teneva", moved(sup, PORT, new) and now["port_moved"] == sup.port_moved
         and now["port"] == new, sup.port_moved)
    mark("porta occupata: l'altro programma resta sulla sua porta", reaches(other, PORT))
    time.sleep(2)
    mark("porta occupata: la protezione resta accesa", sup.status()["phase"] == "active")
    sup.stop()

    # --- anche la prima di riserva e' presa
    second = other_program("127.0.0.1", SPARE[0])
    sup = supervisor(PORT)
    sup._launch()
    mark("porta e prima riserva occupate: il proxy prende la seconda", sup.phase == "active" and settings.read()["port"] == SPARE[1] and panel.opened_port(SPARE[1]), (sup.phase, sup.error))
    sup.stop()
    second.close()
    other.close()

    # --- la porta e' di un altro programma che ascolta su tutte le interfacce
    other = other_program("0.0.0.0", PORT)
    sup = supervisor(PORT)
    sup._launch()
    mark("porta presa su tutte le interfacce: il proxy va su una di riserva e non porta via il traffico", sup.phase == "active" and settings.read()["port"] == SPARE[0]
         and reaches(other, PORT), (sup.phase, sup.error, settings.read()["port"]))
    sup.stop()
    other.close()

    # --- la porta viene presa all'ultimo momento, dopo il controllo: il proxy non riesce a prenderla, e la protezione riparte da sola
    # (al primo controllo la porta risulta libera, poi si vede com'e' davvero. Dove il proxy si accorge subito di non
    # poterla prendere, la porta di riserva arriva nello stesso avvio; dove ci mette di piu', al controllo dello stato)
    other = other_program("127.0.0.1", PORT)
    sup = supervisor(PORT)
    real, first = panel.free_port, [True]
    panel.free_port = lambda port: first.pop() if port == PORT and first else real(port)
    sup._launch()
    for _ in range(120):
        now = sup.status()
        if now["phase"] == "active" and now["port"] != PORT or now["phase"] == "error":
            break
        time.sleep(0.5)
    panel.free_port = real
    mark("porta presa all'ultimo momento: la protezione riparte da sola su una porta di riserva", now["phase"] == "active" and settings.read()["port"] == SPARE[0]
         and moved(sup, PORT, SPARE[0]) and sup._alive(sup.proxy) and reaches(other, PORT),
         (now["phase"], now["error"], sup.cause, settings.read()["port"], sup.port_moved, sup._alive(sup.proxy)))
    sup.stop()

    # --- la porta e' stabilita da chi amministra il PC: non si cambia
    impose({"port": PORT})
    sup = supervisor(PORT)
    sup._launch()
    mark("porta imposta e occupata: non viene cambiata", settings.read()["port"] == PORT and sup.port_moved is None and not sup._alive(sup.proxy))
    mark("porta imposta e occupata: l'errore nomina la porta e il programma che la tiene", sup.phase == "error" and str(PORT) in sup.error
         and sup.cause.startswith("proxy port") and (not HAS_PSUTIL or "python" in sup.error.lower()), (sup.phase, sup.error, sup.cause))
    sup.stop()
    impose(None)
    other.close()

    # --- processi rimasti accesi
    if panel.SUP is not None:
        panel.SUP.stop()
    if not sistema.WINDOWS and importlib.util.find_spec("psutil") is None:
        print("SALTATO: i processi rimasti da un avvio precedente (qui manca psutil, che serve a ritrovarli)")
    else:
        # --- quali processi sono nostri: gli argomenti di questa copia, con la nostra porta e la nostra cartella dei dati
        mention = "import time; time.sleep(120)  # mitmdump"
        mine = [left_engine(BASE), quiet([sys.executable, "-c", mention, "-s", str(panel.HERE / "addon.py"), "--set", f"confdir={panel.DATA / 'ca'}"])]
        others = [left_engine(BASE + 60),   # il motore di un'altra copia: stesso programma, un'altra porta
                  quiet([sys.executable, "-c", mention, "-s", str(panel.HERE / "addon.py"), "--set", f"confdir={panel.DATA / 'ca'}-altra"]),   # un proxy con un'altra cartella dei dati
                  quiet([sys.executable, "-c", mention, str(panel.ENGINE_SCRIPT), "--port", str(BASE)])]   # un programma che i nostri percorsi li nomina soltanto
        time.sleep(1)
        engines, proxies = panel.leftovers("engine"), panel.leftovers("proxy")
        mark("processi rimasti: si riconoscono il motore sulla nostra porta e il proxy sulla nostra cartella dei dati",
             mine[0].pid in engines and mine[1].pid in proxies, (mine[0].pid, engines, mine[1].pid, proxies))
        mark("processi rimasti: quelli di un'altra copia, e chi i nostri percorsi li nomina soltanto, non sono nostri",
             not {p.pid for p in others} & set(engines + proxies) and len(engines) <= 2 and len(proxies) <= 2, (engines, proxies, [p.pid for p in others]))
        shut = panel.close_leftovers("engine") + panel.close_leftovers("proxy")
        mark("processi rimasti: i nostri vengono chiusi, gli altri restano accesi", shut >= 2 and gone(*mine) and all(p.poll() is None for p in others)
             and freed(BASE), (shut, [p.poll() for p in mine], [p.poll() for p in others]))
        for p in others:
            p.kill()
        gone(*others)

        # --- motore e proxy rimasti da un avvio precedente (una versione che non li chiudeva): l'avvio li chiude e parte
        old_engine, old_proxy = left_engine(BASE), left_proxy(PORT)
        old = alive()["pid"]
        sup = supervisor(PORT, engine=False)
        sup._launch()
        now = sup.status()
        mark("motore e proxy rimasti da un avvio precedente: la protezione parte lo stesso", sup.phase == "active" and now["phase"] == "active", (sup.phase, sup.error, sup.cause))
        new = alive()["pid"] if sup.phase == "active" else None
        mark("motore e proxy rimasti: risponde il motore nuovo, e i due processi di prima sono stati chiusi", bool(old) and bool(new) and new != old and gone(old_engine, old_proxy),
             (old, new, old_engine.poll(), old_proxy.poll()))
        mark("motore e proxy rimasti: il proxy resta sulla porta scelta, senza avvisi di porta cambiata", settings.read()["port"] == PORT and sup.port_moved is None
             and sup._alive(sup.proxy) and panel.opened_port(PORT), (settings.read()["port"], sup.port_moved))
        time.sleep(2)
        mark("motore e proxy rimasti: la protezione resta accesa", sup.status()["phase"] == "active", (sup.error, sup.cause))
        sup.stop()
        freed(BASE, PORT)

    # --- la porta del motore e' di un altro programma: non si puo' cambiare (la conosce l'estensione), l'errore la nomina
    other = other_program("127.0.0.1", BASE)
    sup = supervisor(PORT, engine=False)
    sup._launch()
    mark("porta del motore presa da un altro programma: l'errore nomina la porta e il programma, che resta dov'era", sup.phase == "error" and str(BASE) in sup.error
         and sup.cause.startswith("engine port") and (not HAS_PSUTIL or "python" in sup.error.lower() and " by " in sup.cause) and not sup._alive(sup.engine)
         and not sup._alive(sup.proxy) and reaches(other, BASE), (sup.phase, sup.error, sup.cause))
    sup.stop()
    other.close()

    # --- un processo vivo che non risponde piu'. Tempi stretti, solo per la prova: due silenzi di un secondo, due secondi senza avanzare
    panel.PROBE_TIMEOUT, panel.SILENT, panel.STALL = 1, 2, 2
    sup = supervisor(PORT, engine=False)
    sup._launch()
    a, same_proxy = alive(), sup.proxy
    mark("domanda «ci sei?»: il motore risponde con il suo numero e nulla in lavorazione", sup.phase == "active" and a["pid"] > 0 and a["busy"] == 0 and a["idle"] is None, a)
    sup.probe()
    mark("domanda «ci sei?» con tutto a posto: rispondono motore e proxy, nessuno viene toccato", sup.silent == {"engine": 0, "proxy": 0} and sup.stuck == 0
         and sup.status()["phase"] == "active" and not sup.falls, (sup.silent, sup.stuck, sup.error))
    work("LUNGO")
    time.sleep(1)
    seen = []
    for _ in range(4):
        sup.probe()
        seen.append((alive()["busy"], alive()["idle"], sup.stuck))
        time.sleep(1)
    mark("motore al lavoro su un testo lungo che avanza: non viene preso per bloccato", all(busy == 1 and idle is not None and idle < 2 and stuck == 0 for busy, idle, stuck in seen)
         and sup._alive(sup.engine) and not sup.falls, seen)
    aspetta = [time.sleep(0.5) for _ in range(20) if alive()["busy"]]   # il lavoro lungo finisce
    half = socket.create_connection(("127.0.0.1", BASE))   # una richiesta che non finisce di arrivare: non e' un lavoro fermo
    half.sendall(b"POST /mask HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Token: x\r\nContent-Length: 500\r\n\r\n{")
    time.sleep(2.5)
    sup.probe()
    sup.probe()
    mark("richiesta che non finisce di arrivare: il motore non viene preso per bloccato", sup.stuck == 0 and sup._alive(sup.engine) and alive()["busy"] == 0, (sup.stuck, alive()))
    half.close()
    first = alive()["pid"]
    work("FERMO")
    time.sleep(3.5)
    sup.probe()
    once = (sup.stuck, sup._alive(sup.engine), alive()["busy"], alive()["idle"])
    sup.probe()
    mark("motore con una richiesta che non avanza: visto una volta resta, alla conferma viene chiuso", once[0] == 1 and once[1] and once[2] == 1 and once[3] > 2
         and gone(sup.engine, seconds=5) and any(what.startswith("engine stuck") for _, what in sup.events), (once, list(sup.events)[-3:]))
    closed()
    mark("motore che non avanzava: la protezione riparte da sola con un motore nuovo, il proxy resta quello", back(sup) and alive()["pid"] != first and alive()["busy"] == 0
         and sup.proxy is same_proxy and len(sup.falls) == 1, (sup.phase, sup.error, len(sup.falls)))
    if not HAS_PSUTIL:
        print("SALTATO: i processi sospesi (qui manca psutil, che serve a sospenderli)")
    else:
        first = freeze(BASE)
        sup.probe()
        once = (dict(sup.silent), sup._alive(sup.engine))
        sup.probe()
        mark("motore vivo ma sospeso: dopo due silenzi viene chiuso; intanto il proxy non viene giudicato", once == ({"engine": 1, "proxy": 0}, True) and gone(sup.engine, seconds=5)
             and any(what == "engine silent" for _, what in sup.events), (once, list(sup.events)[-3:]))
        closed()
        mark("motore sospeso: la protezione riparte da sola con un motore nuovo", back(sup) and alive()["pid"] != first and len(sup.falls) == 2, (sup.phase, sup.error, len(sup.falls)))
        frozen = sup.proxy
        freeze(PORT)
        sup.probe()
        sup.probe()
        mark("proxy vivo ma sospeso: dopo due silenzi viene chiuso", gone(frozen, seconds=5) and any(what == "proxy silent" for _, what in sup.events), list(sup.events)[-3:])
        closed()
        mark("proxy sospeso: la protezione riparte da sola con un proxy nuovo sulla stessa porta", back(sup) and sup.proxy is not frozen and panel.opened_port(PORT)
             and settings.read()["port"] == PORT and len(sup.falls) == 3, (sup.phase, sup.error, len(sup.falls)))
        freeze(PORT)   # una volta di troppo
        sup.probe()
        sup.probe()
        now = closed()
        mark("bloccato una volta di troppo: la protezione resta ferma e dice che non rispondeva piu'", now["phase"] == "error" and now["error"].startswith(i18n.t("program.blocked.proxy"))
             and i18n.t("program.closed.again", n=panel.RESTARTS) in now["error"] and sup.cause == "proxy silent", (now["error"], sup.cause))
    sup.stop()
    freed(BASE, PORT)

    # --- la porta del pannello: prima di dirsi «gia' acceso», Omissis guarda chi risponde davvero
    panel.SUP = None
    other = other_program("127.0.0.1", BASE + 1)
    p = real_panel()
    said = p.communicate(timeout=60)[0].decode("utf-8", "replace")
    mark("porta del pannello di un altro programma: Omissis non parte, e dice quale porta e quale programma", p.returncode == 3 and str(BASE + 1) in said
         and (not HAS_PSUTIL or "python" in said.lower()) and reaches(other, BASE + 1), (p.returncode, said.strip()[-200:]))
    other.close()
    freed(BASE + 1)
    first = real_panel()
    up = any(panel.running() == "omissis" or time.sleep(0.5) for _ in range(60))
    p = real_panel()
    said = p.communicate(timeout=60)[0].decode("utf-8", "replace")
    mark("pannello gia' acceso: la seconda copia lo riconosce, lo dice ed esce senza toccarlo", up and p.returncode == 0 and str(BASE + 1) in said and first.poll() is None
         and panel.running() == "omissis", (up, p.returncode, said.strip()[-200:]))
    if not HAS_PSUTIL:
        print("SALTATO: il pannello sospeso (qui manca psutil)")
    else:
        old = freeze(BASE + 1)
        p = real_panel()
        taken = any((panel.opened_port(BASE + 1) and (sistema.port_process(BASE + 1) or {}).get("pid") not in (None, old) and panel.running() == "omissis") or time.sleep(0.5)
                    for _ in range(80))
        mark("pannello di questa copia rimasto bloccato: la copia nuova lo chiude e parte al suo posto", taken and p.poll() is None and gone(first, seconds=5),
             (taken, p.poll(), first.poll()))
    for started in STARTED:
        if started.poll() is None:
            started.kill()
    freed(BASE + 1)

    # --- il pannello si chiude di colpo: motore e proxy si chiudono da soli, e le porte tornano libere
    panel.SUP = None
    stand_in = data / "pannello_di_prova.py"
    stand_in.write_text(STAND_IN.format(here=str(HERE)), encoding="utf-8")
    a = subprocess.Popen([sys.executable, str(stand_in), str(panel.ENGINE_SCRIPT), str(PORT)], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, creationflags=panel.NO_WINDOW)
    STARTED.append(a)
    line = a.stdout.readline().decode("utf-8", "replace").split()
    mark("pannello in un processo a parte: la protezione e' accesa, con il suo motore e il suo proxy", line[:1] == ["PRONTO"] and line[2:3] == ["active"]
         and panel.opened_port(BASE) and panel.opened_port(PORT), line)
    try:   # si chiude di colpo proprio quel processo (su Windows l'interprete dell'ambiente ne avvia un altro: e' quello)
        os.kill(int(line[1]), getattr(signal, "SIGKILL", signal.SIGTERM))
    except (OSError, ValueError, IndexError):
        pass
    a.kill()
    a.wait()
    mark("pannello chiuso di colpo: motore e proxy si chiudono da soli e le porte tornano libere", freed(BASE, PORT), (panel.opened_port(BASE), panel.opened_port(PORT)))
    if not freed(BASE, PORT, seconds=1):   # non lasciare nulla acceso dopo la prova
        panel.close_leftovers("engine")
        panel.close_leftovers("proxy")

    # --- che cosa esce dal motivo di una chiusura: tipi e codici, mai il testo
    secret = "Mario Rossi, IBAN IT60X0542811101000000123456"
    code, kinds = panel.closed_for(Ended(1, ["Traceback (most recent call last):", '  File "x.py", line 3, in f', f"    raise ValueError('{secret}')",
                                              f"ValueError: {secret}",
                                              "[12:00:00.000] [Errno 10048] HTTP(S) proxy failed to listen on 127.0.0.1:8080 with [Errno 10048] error "
                                              f"while attempting to bind on address ('127.0.0.1', 8080): [winerror 10048] {secret}"]))
    mark("motivo della chiusura: tipo di errore e codici di sistema", code == 1 and kinds == ["ValueError", "[Errno 10048]", "[WinError 10048]"], (code, kinds))
    details, cause = panel.Supervisor._details("proxy", Ended(1, [f"OSError: [Errno 98] {secret}", f"numpy._core._exceptions._ArrayMemoryError: {secret}"]))
    mark("motivo della chiusura: del testo scritto dal processo non esce nulla", "Mario" not in details + cause and "IT60" not in details + cause
         and cause == "proxy exit 1 OSError [Errno 98] _ArrayMemoryError" and bool(CAUSE.fullmatch(cause)), (details, cause))
    mark("motivo della chiusura: i codici dei guasti gravi di Windows in esadecimale", panel.closed_for(Ended(3221225477, []))[0] == "0xC0000005")
    mark("motivo della chiusura: una riga qualunque che finisce in Error non conta", panel.closed_for(Ended(0, ["il signor Error: non pervenuto", "Error logged during startup"]))[1] == [])

    print(f"\n{'TUTTO OK' if all(outcomes) else 'ERRORI'}: {sum(outcomes)}/{len(outcomes)}")
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        if panel.SUP is not None:
            panel.SUP.stop()
        for started in STARTED:
            if started.poll() is None:
                started.kill()
        if STARTED:   # anche i processi che quelli avevano sotto (su Windows l'interprete dell'ambiente ne avvia un altro)
            panel.close_leftovers("engine")
            panel.close_leftovers("proxy")
        shutil.rmtree(data, ignore_errors=True)
    sys.exit(code)
