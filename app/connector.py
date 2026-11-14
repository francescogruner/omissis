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

  .venv\\Scripts\\python.exe connector.py --avvia claude        avvia l'app con la porta e si collega
  .venv\\Scripts\\python.exe connector.py --port 9551          si collega a un'app gia' avviata cosi'

SPERIMENTALE. Da sapere:
  - l'app va chiusa del tutto e riaperta da qui;
  - finche' e' aperta in questo modo, qualunque programma di questo PC puo' comandarla dalla porta;
  - il produttore puo' disattivare funzioni quando vede la porta di debug, o togliere la possibilita'.
"""
import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import websocket

import catalog
import activity
import i18n
import paths

HERE = Path(__file__).resolve().parent
DATA, EST = paths.DATA, HERE / "extension"
ENGINE_PORT = paths.ENGINE_PORT
WORLD, CALL = "msp_pii", "__msp_bridge"
APP = {
    "claude": {"name": "Claude", "command": r"%LOCALAPPDATA%\Microsoft\WindowsApps\claude-desktop.exe", "port": 9551, "site": "claude.ai"},
    "chatgpt": {"name": "ChatGPT / Codex", "command": r"%LOCALAPPDATA%\Microsoft\WindowsApps\chatgpt-desktop.exe", "port": 9552,
                "site": "chatgpt.com"},
}


class Error(Exception):
    pass


def opened_port(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


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
  const waits = new Map(), ascoltatori = [];
  let n = 0;
  const data = {status: __STATUS__, suspended: false, notices: true};
  const call = globalThis.__CALL__;
  globalThis.__msp_response = (k, r) => { const a = waits.get(k); if (a) { waits.delete(k); a(r); } };
  globalThis.__msp_status = fresh => { data.status = fresh; for (const f of ascoltatori) f({status: {newValue: fresh}}, 'local'); };
  return {
    runtime: {id: 'omissis-connettore', sendMessage: m => new Promise((ok, no) => {
      const k = ++n;
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
                        "readable": bool(s["adapter"])} for s in catalog.SERVICES if not s["radar"]]
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
                        self.cdp.send("Runtime.evaluate", {"expression": f"__msp_status({json.dumps(fresh, ensure_ascii=False)})",
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
                  "  __internal = (!__web && !/^(about|chrome|devtools|chrome-extension|chrome-untrusted|data|blob):$/.test(location.protocol))"
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
        r = self._handle(m if isinstance(m, dict) else {})
        try:
            self.cdp.send("Runtime.evaluate", {"expression": f"__msp_response({k}, {json.dumps(r, ensure_ascii=False)})", "contextId": ctx},
                           sid, timeout=0)
        except Exception:   # noqa: BLE001
            pass

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


def launch_app(key, timeout=40):
    """Avvia l'app con la porta di debug e ci si collega. L'app deve essere chiusa."""
    app = APP[key]
    command = os.path.expandvars(app["command"])
    if not Path(command).exists():
        raise Error(i18n.t("connector.error.not_installed", name=app["name"]))
    if opened_port(app["port"]):
        return Connector(app["port"], app["name"], site=app.get("site", ""))
    subprocess.Popen([command, f"--remote-debugging-port={app['port']}", *app.get("arguments", [])],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(timeout * 2):
        if opened_port(app["port"]):
            for _ in range(20):   # la porta risponde un attimo prima del servizio di debug
                try:
                    return Connector(app["port"], app["name"], site=app.get("site", ""))
                except Exception:   # noqa: BLE001
                    time.sleep(0.5)
        time.sleep(0.5)
    raise Error(i18n.t("connector.error.port", name=app["name"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", dest="launch", choices=sorted(APP))
    ap.add_argument("--port", dest="port", type=int)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    try:
        c = launch_app(a.launch) if a.launch else Connector(a.port or 9551)
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
