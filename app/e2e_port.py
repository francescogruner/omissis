# -*- coding: utf-8 -*-
"""Prova, senza rete e senza browser, l'avvio della protezione quando la porta del proxy non e' libera, e che cosa dice il
programma quando uno dei suoi processi si chiude. Motore finto (un processo che aspetta), proxy vero, dati in una cartella
provvisoria.

Controlla che: con la porta libera il proxy parta li' e nulla cambi; con la porta presa da un altro programma (solo su
questo PC, o su tutte le interfacce) il proxy parta da solo su una porta di riserva, la scelta venga salvata, lo stato lo
dica e l'altro programma resti dov'era; valga anche se la porta viene presa all'ultimo momento; una porta stabilita da
chi amministra il PC non venga cambiata e l'errore la nomini; un processo che si chiude a protezione accesa venga
chiamato per nome, con il codice di uscita; dal motivo della chiusura escano solo tipi di errore e codici, mai il testo.
Non ha bisogno della copia di prova accesa: gira uguale su Windows, Mac e Linux.

   Uso: python e2e_port.py
"""
import collections
import json
import os
import re
import shutil
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
import settings    # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
outcomes = []
SPARE = list(panel.spare_ports())
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


def supervisor(port):
    """La protezione con il motore gia' «acceso» (un processo che aspetta): parte solo il proxy, sulla porta scelta."""
    if panel.SUP is not None:
        panel.SUP.stop()
    settings.write({**settings.read(), "port": port})
    sup = panel.Supervisor(test=True)
    panel.SUP = sup
    sup.engine = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(900)"])
    sup.launched_with = (sup._engine_choices(settings.read()), None, ())
    return sup


def impose(values):
    """Cio' che chi amministra il PC ha stabilito (il file delle prove), da subito."""
    if values is None:
        imposed.unlink(missing_ok=True)
    else:
        imposed.write_text(json.dumps(values), encoding="utf-8")
    managed._cache["until"] = 0.0
    settings._cache["data"] = None


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

    # --- la porta scelta e' libera
    sup = supervisor(PORT)
    sup._launch()
    now = sup.status()
    mark("porta libera: il proxy parte sulla porta scelta e nulla cambia", sup.phase == "active" and panel.opened_port(PORT) and settings.read()["port"] == PORT
         and sup.port_moved is None and now["phase"] == "active" and now["port_moved"] is None, (sup.phase, sup.error))
    mark("porta libera: nessun riavvio richiesto", not sup.restart_needed() and sup.launched_with[1] == PORT)

    # --- un processo che si chiude a protezione accesa
    sup.proxy.kill()
    now = closed()
    mark("proxy chiuso a protezione accesa: lo stato dice che e' il proxy, con il codice di uscita",
         now["phase"] == "error" and now["error"].startswith(i18n.t("program.closed.proxy")) and str(sup.proxy.returncode) in now["error"], now["error"])
    mark("proxy chiuso: il motivo per la segnalazione ha solo nomi, codici e tipi di errore", bool(CAUSE.fullmatch(sup.cause)) and sup.cause.startswith("proxy exit"), sup.cause)
    sup.stop()
    mark("dopo la chiusura la porta torna libera", any(nobody_on(PORT) or time.sleep(0.5) for _ in range(20)))

    sup = supervisor(PORT)
    sup._launch()
    sup.engine.kill()
    now = closed()
    mark("motore chiuso a protezione accesa: lo stato dice che e' il motore", now["phase"] == "error" and now["error"].startswith(i18n.t("program.closed.engine"))
         and sup.cause.startswith("engine exit"), (now["error"], sup.cause))
    sup._launch = lambda: None   # qui interessa solo che cosa viene azzerato: il motore vero non deve partire
    sup.launch()
    mark("un nuovo avvio azzera il motivo dell'errore", sup.phase == "startup" and sup.cause == "" and sup.error == "")
    sup.stop()

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
    mark("porta occupata: lo stato dice da quale porta a quale", sup.port_moved == {"from": PORT, "to": new} and now["port_moved"] == sup.port_moved and now["port"] == new)
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
         and sup.port_moved == {"from": PORT, "to": SPARE[0]} and sup._alive(sup.proxy) and reaches(other, PORT),
         (now["phase"], now["error"], sup.cause, settings.read()["port"], sup.port_moved, sup._alive(sup.proxy)))
    sup.proxy.kill()
    now = closed()
    mark("un proxy che si chiude per un altro motivo non fa ripartire nulla da solo", now["phase"] == "error" and sup.status()["phase"] == "error", now["phase"])
    sup.stop()

    # --- la porta e' stabilita da chi amministra il PC: non si cambia
    impose({"port": PORT})
    sup = supervisor(PORT)
    sup._launch()
    mark("porta imposta e occupata: non viene cambiata", settings.read()["port"] == PORT and sup.port_moved is None and not sup._alive(sup.proxy))
    mark("porta imposta e occupata: l'errore nomina la porta", sup.phase == "error" and str(PORT) in sup.error and sup.cause.startswith("proxy port"), (sup.phase, sup.error, sup.cause))
    sup.stop()
    impose(None)
    other.close()

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
        shutil.rmtree(data, ignore_errors=True)
    sys.exit(code)
