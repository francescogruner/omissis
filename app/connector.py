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
import i18n
import paths

QUI = Path(__file__).resolve().parent
DATI, EST = paths.DATI, QUI / "extension"
PORTA_MOTORE = paths.PORTA_MOTORE
MONDO, CHIAMATA = "msp_pii", "__msp_ponte"
APP = {
    "claude": {"nome": "Claude", "comando": r"%LOCALAPPDATA%\Microsoft\WindowsApps\claude-desktop.exe", "porta": 9551, "sito": "claude.ai"},
    "chatgpt": {"nome": "ChatGPT / Codex", "comando": r"%LOCALAPPDATA%\Microsoft\WindowsApps\chatgpt-desktop.exe", "porta": 9552,
                "sito": "chatgpt.com"},
}


class Errore(Exception):
    pass


def porta_aperta(porta):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", porta)) == 0


class Cdp:
    """Collegamento alla porta di debug: comandi con risposta ed eventi."""

    def __init__(self, porta, su_evento):
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/version", timeout=5) as r:
            info = json.loads(r.read().decode("utf-8"))
        self.prodotto = info.get("Browser", "")
        self.ws = websocket.create_connection(info["webSocketDebuggerUrl"], suppress_origin=True, timeout=None)
        self.su_evento, self.vivo = su_evento, True
        self.lucchetto, self.n, self.attese = threading.Lock(), 0, {}
        threading.Thread(target=self._leggi, daemon=True).start()

    def _leggi(self):
        try:
            while True:
                m = json.loads(self.ws.recv())
                if "id" in m:
                    a = self.attese.pop(m["id"], None)
                    if a:
                        a[1] = m
                        a[0].set()
                else:
                    self.su_evento(m)
        except Exception:   # noqa: BLE001  (app chiusa)
            pass
        finally:
            self.vivo = False
            for a in list(self.attese.values()):
                a[0].set()

    def manda(self, metodo, parametri=None, sessione=None, senza_risposta=False):
        """Spedisce un comando senza aspettare: la risposta si raccoglie con attendi()."""
        msg = {"method": metodo, "params": parametri or {}}
        if sessione:
            msg["sessionId"] = sessione
        voce = [threading.Event(), None, metodo]
        with self.lucchetto:
            self.n += 1
            msg["id"] = self.n
            if not senza_risposta:
                self.attese[self.n] = voce
            self.ws.send(json.dumps(msg, ensure_ascii=False))
        return voce

    @staticmethod
    def attendi(voce, attesa=15):
        if not voce[0].wait(attesa) or voce[1] is None:
            raise ConnectionError(f"nessuna risposta a {voce[2]}")
        if "error" in voce[1]:
            raise RuntimeError(f"{voce[2]}: {voce[1]['error'].get('message')}")
        return voce[1].get("result", {})

    def invia(self, metodo, parametri=None, sessione=None, attesa=15):
        voce = self.manda(metodo, parametri, sessione, senza_risposta=not attesa)
        return self.attendi(voce, attesa) if attesa else None

    def chiudi(self):
        try:
            self.ws.close()
        except Exception:   # noqa: BLE001
            pass


GUSCIO = r"""
const chrome = (() => {
  const attese = new Map(), ascoltatori = [];
  let n = 0;
  const dati = {stato: __STATO__, sospesa: false, avvisi: true};
  const chiama = globalThis.__CHIAMATA__;
  globalThis.__msp_risposta = (k, r) => { const a = attese.get(k); if (a) { attese.delete(k); a(r); } };
  globalThis.__msp_stato = nuovo => { dati.stato = nuovo; for (const f of ascoltatori) f({stato: {newValue: nuovo}}, 'local'); };
  return {
    runtime: {id: 'omissis-connettore', sendMessage: m => new Promise((ok, no) => {
      const k = ++n;
      attese.set(k, ok);
      try { chiama(JSON.stringify({k, m})); } catch (e) { attese.delete(k); no(e); }
    })},
    storage: {local: {get: async () => ({...dati})}, onChanged: {addListener: f => { ascoltatori.push(f); }}}
  };
})();
"""


class Connettore:
    def __init__(self, porta, nome="app", prova=None, sito="", interni=()):
        """sito: il servizio a cui appartiene l'app (es. chatgpt.com), per le finestre con indirizzo interno.
        interni: altre origini da trattare come finestre interne dell'app (serve alle prove)."""
        self.porta, self.nome, self.sito, self.interni = porta, nome, sito, list(interni)
        self.prova = os.environ.get("OMISSIS_TEST") == "1" if prova is None else prova
        self.porta_motore = PORTA_MOTORE
        self.pool = ThreadPoolExecutor(8)
        self.sessioni = {}      # sessione -> {"script": [...], "contesti": set(), "indirizzo": str}
        self.conteggi = {"messaggi": 0, "sostituzioni": 0, "bloccate": 0, "pagine": 0, "in_rete": 0, "controllati": 0}
        self.errori = []
        self.stato = self._leggi_stato()
        self.cdp = Cdp(porta, self._evento)
        self.cdp.invia("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True})
        threading.Thread(target=self._tieni_aggiornato, daemon=True).start()

    @property
    def vivo(self):
        return self.cdp.vivo

    @property
    def esito(self):
        """Quanto si puo' affermare, senza promettere piu' di cio' che si e' visto:
        "no"       il codice non e' entrato in nessuna finestra, o ci sono errori: l'app NON e' protetta
        "attesa"   il codice e' entrato, ma nessun messaggio e' ancora passato da qui: non si sa se l'app manda
                   i messaggi dalle finestre (dove li vediamo) o da un'altra sua parte (dove non li vediamo)
        "si"       almeno un messaggio e' stato sostituito o controllato"""
        if self.errori or not self.conteggi["pagine"]:
            return "no"
        return "si" if self.conteggi["messaggi"] or self.conteggi["controllati"] else "attesa"

    def chiudi(self):
        self.cdp.chiudi()

    # ---------------------------------------------------------------- motore
    def _ponte(self, azione, dati, attesa=90):
        token = (DATI / "token_extension.txt").read_text(encoding="utf-8").strip()
        rich = urllib.request.Request(f"http://127.0.0.1:{self.porta_motore}/ponte/{azione}",
                                      data=json.dumps({**dati, "via": "app"}).encode("utf-8"),
                                      headers={"Content-Type": "application/json", "X-Token": token})
        with urllib.request.urlopen(rich, timeout=attesa) as r:
            return json.loads(r.read().decode("utf-8"))

    def _leggi_stato(self):
        """Politiche dal motore; se non risponde, quelle di partenza (e i messaggi verranno bloccati)."""
        try:
            r = self._ponte("stato", {}, 5)
            return {"servizi": r["servizi"], "ripristina": bool(r["ripristina"]), "blocca_file": bool(r["blocca_file"])}
        except Exception:   # noqa: BLE001
            servizi = [{"id": s["id"], "nome": s["nome"], "domini": s["domini"], "politica": catalog.politica_predefinita(s),
                        "leggibile": bool(s["adattatore"])} for s in catalog.SERVIZI if not s["radar"]]
            if self.prova:
                servizi.append({"id": "prova", "nome": "Servizio finto", "domini": ["localhost"], "politica": "proteggi", "leggibile": True})
            return {"servizi": servizi, "ripristina": True, "blocca_file": False}

    def _tieni_aggiornato(self):
        while self.cdp.vivo:
            time.sleep(15)
            nuovo = self._leggi_stato()
            if nuovo == self.stato:
                continue
            self.stato = nuovo
            for sid, s in list(self.sessioni.items()):
                try:
                    self._inietta(sid, subito=False)
                    self.cdp.attendi(self._guardia(sid))
                    for ctx in list(s["contesti"]):
                        self.cdp.invia("Runtime.evaluate", {"expression": f"__msp_stato({json.dumps(nuovo, ensure_ascii=False)})",
                                                            "contextId": ctx}, sid, attesa=0)
                except Exception:   # noqa: BLE001  (finestra chiusa nel frattempo)
                    pass

    # ---------------------------------------------------------------- codice portato nella pagina
    def _sorgenti(self):
        leggi = lambda nome: (EST / nome).read_text(encoding="utf-8")   # noqa: E731
        tutti = [d for s in self.stato["servizi"] for d in s["domini"]]
        leggibili = [d for s in self.stato["servizi"] if s["leggibile"] for d in s["domini"]]
        # Nelle pagine web conta il sito; le finestre proprie dell'app (app://, file://) si prendono tutte:
        # li' e' l'indirizzo di destinazione di ogni richiesta a dire se va protetta.
        filtro = ("const __h = location.hostname, __web = /^https?:$/.test(location.protocol),\n"
                  "  __interna = (!__web && !/^(about|chrome|devtools|chrome-extension|chrome-untrusted|data|blob):$/.test(location.protocol))"
                  f" || {json.dumps(self.interni)}.includes(location.origin),\n"
                  "  __in = l => __interna || (__web && l.some(d => __h === d || __h.endsWith('.' + d)));\n")
        # nelle finestre interne il codice va inserito sempre: dove mandano le richieste lo decide poi page.js
        pagina = "(() => {\n" + filtro + f"if (!__in({json.dumps(leggibili)})) return;\n" + leggi("page.js") + "\n})();"
        guscio = GUSCIO.replace("__STATO__", json.dumps(self.stato, ensure_ascii=False)).replace("__CHIAMATA__", CHIAMATA)
        ospite = f"if (__interna) globalThis.MSP_OSPITE = {json.dumps(self.sito)};\n" if self.sito else ""
        # le frasi degli avvisi: nell'estensione le da' il browser, qui le portiamo noi, nella lingua del programma
        lingua = i18n.attiva() if (EST / "_locales" / i18n.attiva() / "messages.json").exists() else "en"
        frasi = {k: v["message"] for k, v in json.loads((EST / "_locales" / lingua / "messages.json").read_text(encoding="utf-8")).items()}
        ospite += f"globalThis.MSP_TESTI = {json.dumps(frasi, ensure_ascii=False)};\n"
        isolato = ("(() => {\n" + filtro + f"if (!__in({json.dumps(tutti)}) || typeof globalThis.{CHIAMATA} !== 'function') return;\n"
                   + ospite + guscio + f"if (__in({json.dumps(leggibili)})) {{\n" + leggi("channel.js") + "\n}\n" + leggi("content.js") + "\n})();")
        return pagina, isolato

    def _inietta(self, sid, subito=True, aspetta=True):
        """Registra il codice da eseguire in ogni documento. Con aspetta=False restituisce i comandi in corso."""
        s = self.sessioni.setdefault(sid, {"script": [], "contesti": set(), "indirizzo": ""})
        for ident in s["script"]:
            self.cdp.manda("Page.removeScriptToEvaluateOnNewDocument", {"identifier": ident}, sid, senza_risposta=True)
        s["script"] = []
        pagina, isolato = self._sorgenti()
        in_corso = [self.cdp.manda("Page.addScriptToEvaluateOnNewDocument", {"source": pagina, "runImmediately": subito}, sid),
                    self.cdp.manda("Page.addScriptToEvaluateOnNewDocument", {"source": isolato, "worldName": MONDO, "runImmediately": subito}, sid)]
        if aspetta:
            self._raccogli(sid, in_corso)
        return in_corso

    def _raccogli(self, sid, in_corso):
        ident = [self.cdp.attendi(v)["identifier"] for v in in_corso]
        if sid in self.sessioni:
            self.sessioni[sid]["script"] = ident

    # ---------------------------------------------------------------- barriera a livello di rete
    def _guardia(self, sid):
        """Fa fermare dal browser ogni richiesta verso i servizi protetti, prima che parta."""
        modelli = []
        for s in self.stato["servizi"]:
            if s["politica"] == "proteggi" and s["leggibile"]:
                for d in s["domini"]:
                    modelli += [{"urlPattern": f"*://{d}*", "requestStage": "Request"}, {"urlPattern": f"*://*.{d}*", "requestStage": "Request"}]
        if modelli:
            return self.cdp.manda("Fetch.enable", {"patterns": modelli}, sid)
        return self.cdp.manda("Fetch.disable", None, sid)   # un elenco vuoto fermerebbe tutte le richieste

    def _in_rete(self, sid, p):
        rq, rid, corpo = p.get("request", {}), p.get("requestId"), None
        try:
            corpo = rq.get("postData")
            if corpo is None and rq.get("hasPostData"):
                try:
                    r = self.cdp.invia("Fetch.getRequestPostData", {"requestId": rid}, sid, attesa=10)
                    corpo = base64.b64decode(r["postData"]).decode("utf-8") if r.get("base64Encoded") else r.get("postData")
                except Exception:   # noqa: BLE001  (corpo binario o troppo grande: lo decide il ponte)
                    corpo = None
            tipo = next((v for k, v in (rq.get("headers") or {}).items() if k.lower() == "content-type"), "")
            m = {"url": rq.get("url", ""), "metodo": rq.get("method", "POST"), "tipo": tipo, "rete": True}
            if isinstance(corpo, str):
                m["corpo"] = corpo
            else:
                m.update(binario=True, byte=201)
            esito = self._ponte("richiesta", m)
        except Exception:   # noqa: BLE001  (mai inoltrare in chiaro)
            esito = {"azione": "blocca"}
        try:
            if esito.get("azione") == "sostituisci" and isinstance(esito.get("corpo"), str):
                self.conteggi["in_rete"] += 1
                self.conteggi["messaggi"] += 1
                self.conteggi["sostituzioni"] += int(esito.get("sostituzioni") or 0)
                self.cdp.invia("Fetch.continueRequest", {"requestId": rid, "postData": base64.b64encode(esito["corpo"].encode("utf-8")).decode("ascii")},
                               sid, attesa=0)
            elif esito.get("azione") == "passa":
                self.conteggi["controllati"] += isinstance(corpo, str) and len(corpo) > 2
                self.cdp.invia("Fetch.continueRequest", {"requestId": rid}, sid, attesa=0)
            else:
                self.conteggi["bloccate"] += 1
                self.cdp.invia("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"}, sid, attesa=0)
        except Exception:   # noqa: BLE001  (finestra chiusa nel frattempo)
            pass

    def _prepara(self, p):
        """Una finestra nuova arriva FERMA: i comandi vanno spediti tutti in fila, poi si da' il via, e solo dopo
        si raccolgono le risposte. Aspettare una risposta prima del via blocca tutto: la parte dell'app che deve
        rispondere e' proprio quella ferma (visto sull'app vera di ChatGPT)."""
        sid, info = p["sessionId"], p.get("targetInfo", {})
        tipo, in_corso, script = info.get("type"), [], []
        try:
            if tipo in ("page", "webview", "iframe"):
                self.sessioni.setdefault(sid, {"script": [], "contesti": set(), "indirizzo": info.get("url", "")})
                in_corso.append(self._guardia(sid))   # per prima: vale dal momento in cui il browser la riceve
                in_corso.append(self.cdp.manda("Page.enable", None, sid))
                # senza Runtime.enable Chromium non consegna le chiamate fatte dal mondo isolato (provato). E' il punto
                # piu' delicato: un sito puo' accorgersi che il debug e' attivo, e una verifica anti-automazione potrebbe rifiutarlo.
                in_corso.append(self.cdp.manda("Runtime.enable", None, sid))
                in_corso.append(self.cdp.manda("Runtime.addBinding", {"name": CHIAMATA, "executionContextName": MONDO}, sid))
                script = self._inietta(sid, aspetta=False)
                # finestre figlie (riquadri e viste web dentro la pagina)
                in_corso.append(self.cdp.manda("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True, "flatten": True}, sid))
        except Exception as ex:   # noqa: BLE001
            self.errori.append(f"{tipo}: {type(ex).__name__}: {ex}"[:200])
        finally:
            if p.get("waitingForDebugger"):
                try:
                    self.cdp.manda("Runtime.runIfWaitingForDebugger", None, sid, senza_risposta=True)
                except Exception:   # noqa: BLE001
                    pass
        try:
            for v in in_corso:
                self.cdp.attendi(v)
            if script:
                self._raccogli(sid, script)
                self.conteggi["pagine"] += 1
        except Exception as ex:   # noqa: BLE001
            self.errori.append(f"{tipo}: {type(ex).__name__}: {ex}"[:200])

    # ---------------------------------------------------------------- eventi
    def _evento(self, m):
        metodo, p = m.get("method"), m.get("params", {})
        if metodo == "Target.attachedToTarget":
            self.pool.submit(self._prepara, p)
        elif metodo == "Target.detachedFromTarget":
            self.sessioni.pop(p.get("sessionId"), None)
        elif metodo == "Fetch.requestPaused":
            if p.get("request", {}).get("method", "GET").upper() in ("POST", "PUT", "PATCH"):
                self.pool.submit(self._in_rete, m.get("sessionId"), p)
            else:   # le letture non portano testo dell'utente: ripartono subito
                try:
                    self.cdp.invia("Fetch.continueRequest", {"requestId": p.get("requestId")}, m.get("sessionId"), attesa=0)
                except Exception:   # noqa: BLE001
                    pass
        elif metodo == "Runtime.bindingCalled" and p.get("name") == CHIAMATA:
            self.pool.submit(self._chiamata, m.get("sessionId"), p)

    def _chiamata(self, sid, p):
        try:
            carico = json.loads(p["payload"])
            k, m = int(carico["k"]), carico["m"]
        except (ValueError, KeyError, TypeError):
            return
        ctx = p.get("executionContextId")
        if sid in self.sessioni:
            self.sessioni[sid]["contesti"].add(ctx)
        r = self._gestisci(m if isinstance(m, dict) else {})
        try:
            self.cdp.invia("Runtime.evaluate", {"expression": f"__msp_risposta({k}, {json.dumps(r, ensure_ascii=False)})", "contextId": ctx},
                           sid, attesa=0)
        except Exception:   # noqa: BLE001
            pass

    def _gestisci(self, m):
        """Lo stesso lavoro che nell'estensione fa background.js."""
        t = m.get("t")
        if t in ("richiesta", "testo"):
            try:
                r = self._ponte(t, m)
            except Exception:   # noqa: BLE001  (mai inoltrare in chiaro)
                r = {"azione": "blocca", "motivo": "motore"}
            if r.get("azione") == "sostituisci":
                self.conteggi["messaggi"] += 1
                self.conteggi["sostituzioni"] += int(r.get("sostituzioni") or 0)
            elif r.get("azione") == "blocca":
                self.conteggi["bloccate"] += 1
            elif t == "testo":
                self.conteggi["controllati"] += 1
            return r
        if t == "allegato":
            try:
                r = self._ponte(t, m, 300)
            except Exception:   # noqa: BLE001  (mai lasciar partire il file in chiaro)
                r = {"azione": "blocca", "motivo": "motore"}
            if r.get("azione") == "sostituisci":
                self.conteggi["sostituzioni"] += int(r.get("sostituzioni") or 0)
            elif r.get("azione") == "blocca":
                self.conteggi["bloccate"] += 1
            return r
        if t in ("apri", "pezzo", "intera", "valori", "websocket"):
            try:
                return self._ponte(t, m, 30)
            except Exception:   # noqa: BLE001  (restano i segnaposto)
                return {}
        if t == "visita":
            try:
                return self._ponte("visita", {"host": str(m.get("host", ""))}, 5)
            except Exception:   # noqa: BLE001
                return {}
        return {}


def avvia_app(chiave, attesa=40):
    """Avvia l'app con la porta di debug e ci si collega. L'app deve essere chiusa."""
    app = APP[chiave]
    comando = os.path.expandvars(app["comando"])
    if not Path(comando).exists():
        raise Errore(i18n.t("connettore.errore.non_installata", nome=app["nome"]))
    if porta_aperta(app["porta"]):
        return Connettore(app["porta"], app["nome"], sito=app.get("sito", ""))
    subprocess.Popen([comando, f"--remote-debugging-port={app['porta']}", *app.get("argomenti", [])],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(attesa * 2):
        if porta_aperta(app["porta"]):
            for _ in range(20):   # la porta risponde un attimo prima del servizio di debug
                try:
                    return Connettore(app["porta"], app["nome"], sito=app.get("sito", ""))
                except Exception:   # noqa: BLE001
                    time.sleep(0.5)
        time.sleep(0.5)
    raise Errore(i18n.t("connettore.errore.porta", nome=app["nome"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", dest="avvia", choices=sorted(APP))
    ap.add_argument("--port", dest="porta", type=int)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    try:
        c = avvia_app(a.avvia) if a.avvia else Connettore(a.porta or 9551)
    except Errore as ex:
        sys.exit(str(ex))
    print(f"collegato a {c.nome} ({c.cdp.prodotto}) sulla porta {c.porta}. Ctrl+C per staccare: nell'app i messaggi verso i servizi protetti restano bloccati finché non la si riavvia.")
    try:
        ultimo = None
        while c.vivo:
            time.sleep(2)
            if c.conteggi != ultimo:
                ultimo = dict(c.conteggi)
                print(f"   finestre seguite {ultimo['pagine']} · messaggi protetti {ultimo['messaggi']} (di cui {ultimo['in_rete']} fermati in rete)"
                      f" · dati sostituiti {ultimo['sostituzioni']}"
                      f" · richieste bloccate {ultimo['bloccate']}")
            for e in c.errori:
                print("   errore:", e)
            c.errori.clear()
        print("l'app è stata chiusa")
    except KeyboardInterrupt:
        c.chiudi()
