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

  .venv\\Scripts\\python.exe gateway.py [--port 8767]         (richiede la protezione attiva)
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

import agents
import catalog
import settings
import paths
import activity
import restore as R

HERE = Path(__file__).resolve().parent
MAX_BODY = 32_000_000
JUMP = {"host", "content-length", "connection", "keep-alive", "proxy-connection", "proxy-authorization", "transfer-encoding",
         "accept-encoding", "upgrade", "te", "trailer"}
JUMP_RESPONSE = {"content-length", "connection", "keep-alive", "transfer-encoding", "content-encoding"}
# modelli che girano su questo PC: i dati non escono, ma si possono far passare lo stesso dal gateway
LOCAL = {"ollama": ("http://127.0.0.1:11434", "openai", "Ollama"), "lmstudio": ("http://127.0.0.1:1234", "openai", "LM Studio")}


def routes():
    """nome usato nell'indirizzo -> (indirizzo del servizio vero, adattatore, servizio del catalogo o None, nome)."""
    out = {}
    for s in catalog.SERVICES:
        if s["adapter"] in agents.CLASSES and s["kind"] == "api":
            name = s["id"][:-4] if s["id"].endswith("-api") else s["id"]
            out[name] = ("https://" + s["domains"][0], s["adapter"], s, s["name"])
    for name, (address, adapter, label) in LOCAL.items():
        out[name] = (address, adapter, None, label)
    return out


class Gateway:
    def __init__(self, port=None, upstream=None):
        """a_monte: per le prove, manda tutto a questo indirizzo invece che ai servizi veri."""
        self.port = port or paths.GATEWAY_PORT
        self.engine_port = paths.ENGINE_PORT
        self.upstream = upstream
        self.routes = routes()
        self.reg = activity.Log()
        self.values, self.absent, self.lock = {}, set(), threading.Lock()
        self.counts = {"requests": 0, "messages": 0, "replacements": 0, "blocked": 0}
        self.server = None

    # ---------------------------------------------------------------- motore
    def engine(self, path, data, timeout=180):
        token = (paths.DATA / "token.txt").read_text(encoding="utf-8").strip()
        req = urllib.request.Request(f"http://127.0.0.1:{self.engine_port}{path}", data=json.dumps(data).encode("utf-8"),
                                      headers={"Content-Type": "application/json", "X-Token": token})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def preload(self, placeholder):
        with self.lock:
            missing = [s for s in set(placeholder) if s not in self.values and s not in self.absent]
        if missing:
            try:
                found_items = self.engine("/values", {"placeholder": missing}, 30)["mapping"]
            except Exception:   # noqa: BLE001  (senza motore i segnaposto restano tali: nessun danno)
                return
            with self.lock:
                self.values.update(found_items)
                self.absent.update(s for s in missing if s not in found_items)
                if len(self.values) > 50000:
                    self.values.clear()

    def search(self, placeholder):
        if placeholder not in self.values and placeholder not in self.absent:
            self.preload([placeholder])
        return self.values.get(placeholder)

    # ---------------------------------------------------------------- servizio
    def launch(self):
        gw = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _error(self, code, message):
                body = json.dumps({"type": "error", "error": {"type": "omissis", "message": "Omissis: " + message}}, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _everything(self):
                try:
                    gw.serve(self)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    self.close_connection = True   # lo strumento ha chiuso
                except Exception as ex:   # noqa: BLE001
                    self.close_connection = True
                    try:
                        self._error(502, f"errore del gateway ({type(ex).__name__})")
                    except Exception:   # noqa: BLE001  (risposta gia' iniziata)
                        pass

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _everything

        class Service(ThreadingHTTPServer):
            allow_reuse_address = False   # su Windows, altrimenti, due copie potrebbero aprire la stessa porta senza errore

            def handle_error(self, request, client_address):   # lo strumento ha chiuso il collegamento: non e' un errore
                pass

        self.server = Service(("127.0.0.1", self.port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def serve(self, h):
        self.counts["requests"] += 1
        if h.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            return h._error(403, "host non ammesso")
        name, _, rest = h.path.lstrip("/").partition("/")
        route = self.routes.get(name)
        if route is None:
            return h._error(404, "indirizzo non riconosciuto. Usare http://127.0.0.1:%d/<servizio>/... con uno di: %s"
                             % (self.port, ", ".join(sorted(self.routes))))
        address, adapter, service, label = route
        path = "/" + rest
        policy = settings.policy(service) if service else "protect"
        who = service["id"] if service else name
        if policy == "block":
            if service:
                self.reg.contact(service["id"], service["domains"][0], "blocked")
            self.counts["blocked"] += 1
            return h._error(403, f"{label} è bloccato dalle impostazioni")
        if service and policy != "ignore":
            self.reg.contact(service["id"], service["domains"][0], "guarded" if policy == "protect" else "not_protected")

        if h.headers.get("Transfer-Encoding", "").lower() == "chunked":
            return h._error(411, "richiesta senza lunghezza dichiarata: non gestita")
        length = int(h.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return h._error(413, "richiesta troppo grande per essere controllata")
        body = h.rfile.read(length) if length else b""
        kind = h.headers.get("Content-Type", "")
        ad, entry = None, {"service": who, "via": "gateway", "method": h.command, "path": activity.clean_path(path), "byte": len(body),
                          "client": activity.client_from_ua(h.headers.get("User-Agent", ""))}

        if policy == "protect" and h.command in ("POST", "PUT", "PATCH") and body:
            ad = agents.CLASSES[adapter]()
            if "multipart/" in kind or "octet-stream" in kind:
                if settings.read()["block_files"]:
                    self.reg.write(**entry, event="file_blocked")
                    self.counts["blocked"] += 1
                    return h._error(403, "caricamento di file bloccato dalle impostazioni")
                self.reg.write(**entry, event="file_not_masked")
            else:
                opened = ad.request(path, kind or "application/json", body.decode("utf-8", errors="replace"))
                if opened is not None:
                    ref, reassemble, parsed = opened
                    ref = [(c, k) for c, k in ref if c[k].strip()]
                    if ref:
                        originals = [c[k] for c, k in ref]
                        technical = {(id(c), k) for c, k in getattr(ad, "technical", [])}
                        groups = [[i for i, (c, k) in enumerate(ref) if ((id(c), k) in technical) == t] for t in (False, True)]
                        outcome = {"texts": list(originals), "mapping": {}, "counts": {}, "ms": 0}
                        try:
                            for indexes, exclude in zip(groups, ([], agents.TECHNICAL)):
                                if not indexes:
                                    continue
                                part = self.engine("/mask", {"texts": [originals[i] for i in indexes], "exclude": exclude,
                                                                 "never": agents.vocabulary(parsed)})
                                for i, fresh in zip(indexes, part["texts"]):
                                    outcome["texts"][i] = fresh
                                outcome["mapping"].update(part["mapping"])
                                outcome["ms"] += part["ms"]
                                for e, n in part["counts"].items():
                                    outcome["counts"][e] = outcome["counts"].get(e, 0) + n
                        except Exception as ex:   # noqa: BLE001  (mai inoltrare in chiaro)
                            self.reg.write(**entry, event="blocked_engine_unreachable", error=type(ex).__name__)
                            self.counts["blocked"] += 1
                            return h._error(503, "il motore di protezione non risponde: richiesta fermata per non inviare dati in chiaro")
                        with self.lock:
                            self.values.update(outcome["mapping"])
                        if outcome["texts"] != originals:
                            for (c, k), fresh in zip(ref, outcome["texts"]):
                                c[k] = fresh
                            body = reassemble().encode("utf-8")
                            self.counts["messages"] += 1
                            self.counts["replacements"] += sum(outcome["counts"].values())
                        self.reg.write(**entry, event="masked", fields=len(ref), characters=sum(len(t) for t in outcome["texts"]),
                                        replacements=outcome["counts"], ms=outcome["ms"])
                    elif len(body) > 200:
                        self.reg.write(**entry, event="no_text_field", structure=activity.shape(parsed))

        # ---- inoltro al servizio vero
        u = urllib.parse.urlsplit(self.upstream or address)
        Cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
        conn = Cls(u.hostname, u.port, timeout=900)
        headers = {k: v for k, v in h.headers.items() if k.lower() not in JUMP}
        headers["Accept-Encoding"] = "identity"   # la risposta va letta e riscritta mentre arriva
        try:
            conn.request(h.command, u.path.rstrip("/") + path, body=body or None, headers=headers)
            response = conn.getresponse()
        except Exception as ex:   # noqa: BLE001
            conn.close()
            return h._error(502, f"{label} non è raggiungibile ({type(ex).__name__})")
        try:
            self._respond(h, response, ad, path, entry)
        finally:
            conn.close()

    def _respond(self, h, response, ad, path, entry):
        kind = response.getheader("Content-Type", "")
        restore = ad is not None and settings.read()["restore"] and h.command != "HEAD"
        h.send_response(response.status, response.reason)
        for k, v in response.getheaders():
            if k.lower() not in JUMP_RESPONSE:
                h.send_header(k, v)

        def chunk(data):
            if data:
                h.wfile.write(f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n")
                h.wfile.flush()

        if restore and ad.in_streaming(kind, path):
            stream = ad.stream(self.search, self.preload)
            h.send_header("Transfer-Encoding", "chunked")
            h.end_headers()
            while True:
                data = response.read1(65536)
                if not data:
                    break
                for x in stream(data):
                    chunk(x)
            for x in stream(b""):
                chunk(x)
            h.wfile.write(b"0\r\n\r\n")
            if stream.restored:
                self.reg.write(service=entry["service"], via="gateway", client=entry.get("client", ""), path=entry["path"], event="response_streaming",
                                restored=stream.restored)
            return
        if restore and any(x in kind for x in ("json", "text/plain")):
            entire = response.read()
            text = entire.decode("utf-8", errors="replace")
            found_items = [m.group() for m in R.RX_PLACEHOLDER.finditer(text)] if len(entire) <= MAX_BODY else []
            if found_items:
                self.preload(found_items)
                entire = ad.whole(kind, text, self.search).encode("utf-8")
                self.reg.write(service=entry["service"], via="gateway", client=entry.get("client", ""), path=entry["path"], event="response", restored=len(found_items))
            h.send_header("Content-Length", str(len(entire)))
            h.end_headers()
            h.wfile.write(entire)
            return
        # tutto il resto passa com'e', a mano a mano che arriva
        h.send_header("Transfer-Encoding", "chunked")
        h.end_headers()
        if h.command != "HEAD":
            while True:
                data = response.read1(65536)
                if not data:
                    break
                chunk(data)
        h.wfile.write(b"0\r\n\r\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", dest="port", type=int, default=None)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    g = Gateway(a.port).launch()
    print(f"gateway su http://127.0.0.1:{g.port} · servizi: {', '.join(sorted(g.routes))}")
    print(f"   Claude Code:  ANTHROPIC_BASE_URL=http://127.0.0.1:{g.port}/anthropic")
    print(f"   OpenAI:       OPENAI_BASE_URL=http://127.0.0.1:{g.port}/openai/v1")
    try:
        last = None
        while True:
            time.sleep(2)
            if g.counts != last:
                last = dict(g.counts)
                print(f"   richieste {last['requests']} · con sostituzioni {last['messages']} · dati sostituiti {last['replacements']} · fermate {last['blocked']}")
    except KeyboardInterrupt:
        g.stop()
