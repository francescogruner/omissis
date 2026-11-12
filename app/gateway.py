# -*- coding: utf-8 -*-
"""Gateway locale per gli strumenti che parlano con le API: Claude Code, Codex, opencode, aider e
qualunque programma a cui si puo' dire "il servizio sta a questo indirizzo".

Lo strumento parla con http://127.0.0.1:8767/<servizio>/... invece che con il servizio vero; il
gateway sostituisce i dati sensibili nella richiesta, la inoltra in HTTPS al servizio e rimette i
valori veri nella risposta (testo e argomenti delle azioni). Niente certificato e niente proxy:
basta una variabile d'ambiente.

  Claude Code     ANTHROPIC_BASE_URL=http://127.0.0.1:8767/anthropic
  OpenAI e simili OPENAI_BASE_URL=http://127.0.0.1:8767/openai/v1

Le credenziali (chiave o accesso con abbonamento) passano cosi' come sono e non vengono mai scritte.
Se il motore non risponde la richiesta viene fermata (503), mai inoltrata in chiaro.

  .venv\\Scripts\\python.exe gateway.py [--porta 8767]         (richiede la protezione attiva)
"""
import argparse
import http.client
import json
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import agenti
import catalogo
import impostazioni
import percorsi
import registro
import ripristino as R

QUI = Path(__file__).resolve().parent
MAX_CORPO = 32_000_000
SALTO = {"host", "content-length", "connection", "keep-alive", "proxy-connection", "proxy-authorization", "transfer-encoding",
         "accept-encoding", "upgrade", "te", "trailer"}
SALTO_RISPOSTA = {"content-length", "connection", "keep-alive", "transfer-encoding", "content-encoding"}
# modelli che girano su questo PC: i dati non escono, ma si possono far passare lo stesso dal gateway
LOCALI = {"ollama": ("http://127.0.0.1:11434", "openai", "Ollama"), "lmstudio": ("http://127.0.0.1:1234", "openai", "LM Studio")}


def rotte():
    """nome usato nell'indirizzo -> (indirizzo del servizio vero, adattatore, servizio del catalogo o None, nome)."""
    out = {}
    for s in catalogo.SERVIZI:
        if s["adattatore"] in agenti.CLASSI and s["tipo"] == "api":
            nome = s["id"][:-4] if s["id"].endswith("-api") else s["id"]
            out[nome] = ("https://" + s["domini"][0], s["adattatore"], s, s["nome"])
    for nome, (indirizzo, adattatore, etichetta) in LOCALI.items():
        out[nome] = (indirizzo, adattatore, None, etichetta)
    return out


class Gateway:
    def __init__(self, porta=None, a_monte=None):
        """a_monte: per le prove, manda tutto a questo indirizzo invece che ai servizi veri."""
        self.porta = porta or percorsi.PORTA_GATEWAY
        self.porta_motore = percorsi.PORTA_MOTORE
        self.a_monte = a_monte
        self.rotte = rotte()
        self.reg = registro.Registro()
        self.valori, self.assenti, self.lucchetto = {}, set(), threading.Lock()
        self.conteggi = {"richieste": 0, "messaggi": 0, "sostituzioni": 0, "bloccate": 0}
        self.server = None

    # ---------------------------------------------------------------- motore
    def motore(self, percorso, dati, attesa=180):
        token = (percorsi.DATI / "token.txt").read_text(encoding="utf-8").strip()
        rich = urllib.request.Request(f"http://127.0.0.1:{self.porta_motore}{percorso}", data=json.dumps(dati).encode("utf-8"),
                                      headers={"Content-Type": "application/json", "X-Token": token})
        with urllib.request.urlopen(rich, timeout=attesa) as r:
            return json.loads(r.read().decode("utf-8"))

    def precarica(self, segnaposto):
        with self.lucchetto:
            mancanti = [s for s in set(segnaposto) if s not in self.valori and s not in self.assenti]
        if mancanti:
            try:
                trovati = self.motore("/valori", {"segnaposto": mancanti}, 30)["mappa"]
            except Exception:   # noqa: BLE001  (senza motore i segnaposto restano tali: nessun danno)
                return
            with self.lucchetto:
                self.valori.update(trovati)
                self.assenti.update(s for s in mancanti if s not in trovati)
                if len(self.valori) > 50000:
                    self.valori.clear()

    def cerca(self, segnaposto):
        if segnaposto not in self.valori and segnaposto not in self.assenti:
            self.precarica([segnaposto])
        return self.valori.get(segnaposto)

    # ---------------------------------------------------------------- servizio
    def avvia(self):
        gw = self

        class Gestore(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _errore(self, codice, messaggio):
                corpo = json.dumps({"type": "error", "error": {"type": "omissis", "message": "Omissis: " + messaggio}}, ensure_ascii=False).encode("utf-8")
                self.send_response(codice)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

            def _tutto(self):
                try:
                    gw.servi(self)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    self.close_connection = True   # lo strumento ha chiuso
                except Exception as ex:   # noqa: BLE001
                    self.close_connection = True
                    try:
                        self._errore(502, f"errore del gateway ({type(ex).__name__})")
                    except Exception:   # noqa: BLE001  (risposta gia' iniziata)
                        pass

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _tutto

        class Servizio(ThreadingHTTPServer):
            allow_reuse_address = False   # su Windows, altrimenti, due copie potrebbero aprire la stessa porta senza errore

            def handle_error(self, request, client_address):   # lo strumento ha chiuso il collegamento: non e' un errore
                pass

        self.server = Servizio(("127.0.0.1", self.porta), Gestore)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def ferma(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def servi(self, h):
        self.conteggi["richieste"] += 1
        if h.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            return h._errore(403, "host non ammesso")
        nome, _, resto = h.path.lstrip("/").partition("/")
        rotta = self.rotte.get(nome)
        if rotta is None:
            return h._errore(404, "indirizzo non riconosciuto. Usare http://127.0.0.1:%d/<servizio>/... con uno di: %s"
                             % (self.porta, ", ".join(sorted(self.rotte))))
        indirizzo, adattatore, servizio, etichetta = rotta
        percorso = "/" + resto
        politica = impostazioni.politica(servizio) if servizio else "proteggi"
        chi = servizio["id"] if servizio else nome
        if politica == "blocca":
            if servizio:
                self.reg.contatto(servizio["id"], servizio["domini"][0], "bloccato")
            self.conteggi["bloccate"] += 1
            return h._errore(403, f"{etichetta} è bloccato dalle impostazioni")
        if servizio and politica != "ignora":
            self.reg.contatto(servizio["id"], servizio["domini"][0], "protetto" if politica == "proteggi" else "non protetto")

        if h.headers.get("Transfer-Encoding", "").lower() == "chunked":
            return h._errore(411, "richiesta senza lunghezza dichiarata: non gestita")
        lunghezza = int(h.headers.get("Content-Length") or 0)
        if lunghezza > MAX_CORPO:
            return h._errore(413, "richiesta troppo grande per essere controllata")
        corpo = h.rfile.read(lunghezza) if lunghezza else b""
        tipo = h.headers.get("Content-Type", "")
        ad, voce = None, {"servizio": chi, "via": "gateway", "metodo": h.command, "percorso": registro.percorso_pulito(percorso), "byte": len(corpo)}

        if politica == "proteggi" and h.command in ("POST", "PUT", "PATCH") and corpo:
            ad = agenti.CLASSI[adattatore]()
            if "multipart/" in tipo or "octet-stream" in tipo:
                if impostazioni.leggi()["blocca_file"]:
                    self.reg.scrivi(**voce, evento="file bloccato")
                    self.conteggi["bloccate"] += 1
                    return h._errore(403, "caricamento di file bloccato dalle impostazioni")
                self.reg.scrivi(**voce, evento="file NON mascherato")
            else:
                aperta = ad.richiesta(percorso, tipo or "application/json", corpo.decode("utf-8", errors="replace"))
                if aperta is not None:
                    rif, ricomponi, interpretato = aperta
                    rif = [(c, k) for c, k in rif if c[k].strip()]
                    if rif:
                        originali = [c[k] for c, k in rif]
                        tecnici = {(id(c), k) for c, k in getattr(ad, "tecnici", [])}
                        gruppi = [[i for i, (c, k) in enumerate(rif) if ((id(c), k) in tecnici) == t] for t in (False, True)]
                        esito = {"testi": list(originali), "mappa": {}, "conteggi": {}, "ms": 0}
                        try:
                            for indici, escludi in zip(gruppi, ([], agenti.TECNICHE)):
                                if not indici:
                                    continue
                                parte = self.motore("/maschera", {"testi": [originali[i] for i in indici], "escludi": escludi,
                                                                 "mai": agenti.vocabolario(interpretato)})
                                for i, nuovo in zip(indici, parte["testi"]):
                                    esito["testi"][i] = nuovo
                                esito["mappa"].update(parte["mappa"])
                                esito["ms"] += parte["ms"]
                                for e, n in parte["conteggi"].items():
                                    esito["conteggi"][e] = esito["conteggi"].get(e, 0) + n
                        except Exception as ex:   # noqa: BLE001  (mai inoltrare in chiaro)
                            self.reg.scrivi(**voce, evento="BLOCCATA: motore non raggiungibile", errore=type(ex).__name__)
                            self.conteggi["bloccate"] += 1
                            return h._errore(503, "il motore di protezione non risponde: richiesta fermata per non inviare dati in chiaro")
                        with self.lucchetto:
                            self.valori.update(esito["mappa"])
                        if esito["testi"] != originali:
                            for (c, k), nuovo in zip(rif, esito["testi"]):
                                c[k] = nuovo
                            corpo = ricomponi().encode("utf-8")
                            self.conteggi["messaggi"] += 1
                            self.conteggi["sostituzioni"] += sum(esito["conteggi"].values())
                        self.reg.scrivi(**voce, evento="mascherata", campi=len(rif), caratteri=sum(len(t) for t in esito["testi"]),
                                        sostituzioni=esito["conteggi"], ms=esito["ms"])
                    elif len(corpo) > 200:
                        self.reg.scrivi(**voce, evento="nessun campo di testo riconosciuto", struttura=registro.forma(interpretato))

        # ---- inoltro al servizio vero
        u = urllib.parse.urlsplit(self.a_monte or indirizzo)
        Classe = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        conn = Classe(u.hostname, u.port, timeout=900)
        intestazioni = {k: v for k, v in h.headers.items() if k.lower() not in SALTO}
        intestazioni["Accept-Encoding"] = "identity"   # la risposta va letta e riscritta mentre arriva
        try:
            conn.request(h.command, u.path.rstrip("/") + percorso, body=corpo or None, headers=intestazioni)
            risposta = conn.getresponse()
        except Exception as ex:   # noqa: BLE001
            conn.close()
            return h._errore(502, f"{etichetta} non è raggiungibile ({type(ex).__name__})")
        try:
            self._rispondi(h, risposta, ad, percorso, voce)
        finally:
            conn.close()

    def _rispondi(self, h, risposta, ad, percorso, voce):
        tipo = risposta.getheader("Content-Type", "")
        ripristina = ad is not None and impostazioni.leggi()["ripristina"] and h.command != "HEAD"
        h.send_response(risposta.status, risposta.reason)
        for k, v in risposta.getheaders():
            if k.lower() not in SALTO_RISPOSTA:
                h.send_header(k, v)

        def pezzo(dati):
            if dati:
                h.wfile.write(f"{len(dati):x}\r\n".encode("ascii") + dati + b"\r\n")
                h.wfile.flush()

        if ripristina and ad.in_streaming(tipo, percorso):
            flusso = ad.flusso(self.cerca, self.precarica)
            h.send_header("Transfer-Encoding", "chunked")
            h.end_headers()
            while True:
                dati = risposta.read1(65536)
                if not dati:
                    break
                for x in flusso(dati):
                    pezzo(x)
            for x in flusso(b""):
                pezzo(x)
            h.wfile.write(b"0\r\n\r\n")
            if flusso.ripristinati:
                self.reg.scrivi(servizio=voce["servizio"], via="gateway", percorso=voce["percorso"], evento="risposta in streaming",
                                ripristinati=flusso.ripristinati)
            return
        if ripristina and any(x in tipo for x in ("json", "text/plain")):
            intero = risposta.read()
            testo = intero.decode("utf-8", errors="replace")
            trovati = [m.group() for m in R.RX_SEGNAPOSTO.finditer(testo)] if len(intero) <= MAX_CORPO else []
            if trovati:
                self.precarica(trovati)
                intero = ad.intera(tipo, testo, self.cerca).encode("utf-8")
                self.reg.scrivi(servizio=voce["servizio"], via="gateway", percorso=voce["percorso"], evento="risposta", ripristinati=len(trovati))
            h.send_header("Content-Length", str(len(intero)))
            h.end_headers()
            h.wfile.write(intero)
            return
        # tutto il resto passa com'e', a mano a mano che arriva
        h.send_header("Transfer-Encoding", "chunked")
        h.end_headers()
        if h.command != "HEAD":
            while True:
                dati = risposta.read1(65536)
                if not dati:
                    break
                pezzo(dati)
        h.wfile.write(b"0\r\n\r\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--porta", type=int, default=None)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    g = Gateway(a.porta).avvia()
    print(f"gateway su http://127.0.0.1:{g.porta} · servizi: {', '.join(sorted(g.rotte))}")
    print(f"   Claude Code:  ANTHROPIC_BASE_URL=http://127.0.0.1:{g.porta}/anthropic")
    print(f"   OpenAI:       OPENAI_BASE_URL=http://127.0.0.1:{g.porta}/openai/v1")
    try:
        ultimo = None
        while True:
            time.sleep(2)
            if g.conteggi != ultimo:
                ultimo = dict(g.conteggi)
                print(f"   richieste {ultimo['richieste']} · con sostituzioni {ultimo['messaggi']} · dati sostituiti {ultimo['sostituzioni']} · fermate {ultimo['bloccate']}")
    except KeyboardInterrupt:
        g.ferma()
