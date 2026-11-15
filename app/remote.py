# -*- coding: utf-8 -*-
"""Server di inferenza in rete: un PC con Omissis presta il suo modello agli altri PC dell'organizzazione.

Serve dove non tutti i PC reggono il modello (poca memoria, terminali, PC vecchi): uno lo carica, gli altri glielo
chiedono. Si accende dal pannello (Impostazioni > Riconoscimento); di serie e' spento e non ascolta nulla.

Che cosa passa in rete: il testo da controllare va dal PC al server, e tornano SOLO le posizioni dei dati trovati
dal modello. Tutto il resto resta sul PC che ha fatto la richiesta: le regole e gli elenchi personali, i segnaposto
e l'archivio con i valori veri. Il server non scrive i testi da nessuna parte e non li mette nel registro: conta
soltanto quante richieste ha servito, e per chi.

Come ci si riconosce: il server si fa da se' un certificato (HTTPS) e una chiave. Ai PC si danno indirizzo, chiave
e impronta del certificato (engine_url, engine_key, engine_pin): con l'impronta il PC parla solo con quel server
(pinned.py), con la chiave il server risponde solo ai PC dell'organizzazione.

Se il server non risponde, sul PC non viene mascherato nulla e quindi non parte nulla: come quando il modello
locale non risponde. Non c'e' ripiego sul modello locale, che su quel PC puo' non esserci.

  dal lato del server (dentro engine.py)   share(engine, porta, chiave, certificato, chiave privata)
  dal lato del PC (dentro engine.py)       detector(cfg) -> un riconoscitore che chiede al server
  dal pannello                             ensure(cartella), fingerprint(), check(), addresses()
"""
import hashlib
import json
import os
import re
import secrets
import socket
import ssl
import threading
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pinned
from version import VERSION

PORT = 8770
MAX_BODY, MAX_TEXTS = 8_000_000, 256
PER_CALL, PER_CALL_BYTES = 64, 1_500_000   # quanto manda un PC in una chiamata sola
RX_LABEL = re.compile(r"[A-Z][A-Z_]{1,22}")
NAME = re.sub(r"[^\w .-]", "", os.environ.get("COMPUTERNAME") or socket.gethostname())[:40]
SEEN, _lock = {}, threading.Lock()   # sul server: nome del PC -> {requests, texts, last}
LISTENING = {"port": 0}


class Failure(Exception):
    """Il server non ha dato una risposta utilizzabile. code: refused | certificate | unreachable | answer."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def configured(cfg):
    """Questo PC chiede il riconoscimento a un server della rete?"""
    return bool(cfg.get("engine_url") and cfg.get("engine_key"))


# ---------------------------------------------------------------- certificato e chiave del server (dal pannello)
def ensure(folder):
    """Certificato, chiave privata e chiave di accesso del server: creati una volta e poi sempre quelli, perche' i PC
    riconoscono il server dall'impronta. Restituisce (certificato, chiave privata, chiave di accesso)."""
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cert, key, access = folder / "cert.pem", folder / "key.pem", folder / "access.txt"
    if not (cert.exists() and key.exists()):
        private = ec.generate_private_key(ec.SECP256R1())
        who = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Omissis")])
        now = datetime.datetime.now(datetime.timezone.utc)
        made = (x509.CertificateBuilder().subject_name(who).issuer_name(who).public_key(private.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=3650)).sign(private, hashes.SHA256()))
        key.write_bytes(private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        cert.write_bytes(made.public_bytes(serialization.Encoding.PEM))
    if not access.exists() or len(access.read_text(encoding="utf-8").strip()) < 20:
        access.write_text("oms_" + secrets.token_urlsafe(32).replace("-", "A").replace("_", "B"), encoding="utf-8")
    return cert, key, access.read_text(encoding="utf-8").strip()


def fingerprint(cert):
    """L'impronta SHA-256 del certificato: e' cio' che i PC confrontano prima di parlare con il server."""
    try:
        return hashlib.sha256(ssl.PEM_cert_to_DER_cert(Path(cert).read_text(encoding="ascii"))).hexdigest()
    except (OSError, ValueError):
        return ""


def addresses(port):
    """Gli indirizzi con cui gli altri PC possono raggiungere questo: prima il nome, poi i numeri."""
    name, found = socket.gethostname().lower(), []
    try:
        found = [a for a in socket.gethostbyname_ex(socket.gethostname())[2] if not a.startswith(("127.", "169.254."))]
    except OSError:
        pass
    return [f"https://{h}:{port}" for h in [name, *found]]


def _open(url, key, pin, path, data=None, timeout=20):
    req = urllib.request.Request(url.rstrip("/") + path, data=None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": f"Omissis/{VERSION}"})
    try:
        with pinned.opener(pin if url.startswith("https://") else "").open(req, timeout=timeout) as r:
            out = json.loads(r.read(MAX_BODY * 2).decode("utf-8"))
    except urllib.error.HTTPError as ex:
        raise Failure("refused" if ex.code in (401, 403) else "answer") from None
    except ssl.SSLCertVerificationError:
        raise Failure("certificate") from None
    except urllib.error.URLError as ex:
        raise Failure("certificate" if isinstance(ex.reason, ssl.SSLCertVerificationError) else "unreachable") from None
    except (OSError, ValueError):
        raise Failure("unreachable") from None
    if not isinstance(out, dict):
        raise Failure("answer")
    return out


def check(url, key, pin):
    """Chiede al server chi e'. Solleva Failure se non risponde come deve."""
    out = _open(url, key, pin, "/omissis/info", timeout=8)
    if out.get("product") != "omissis":
        raise Failure("answer")
    return {"model": str(out.get("model") or "")[:80], "device": str(out.get("device") or "")[:20], "version": str(out.get("version") or "")[:20]}


# ---------------------------------------------------------------- dal lato del PC: un riconoscitore che chiede al server
def detector(cfg):
    """Come il riconoscitore locale, ma la parte del modello la fa il server. Regole ed elenchi restano qui."""
    from inference import Detector   # solo Python per questa parte: il modello non viene caricato
    import settings

    class Remote(Detector):
        def __init__(self):
            self.url, self.key, self.pin = cfg["engine_url"], cfg["engine_key"], cfg.get("engine_pin") or ""
            self.rules, self.well_known, self.threshold = True, True, None
            self.off, self._off_model, self._asked = [], None, 0.0
            self.device, self.mod = "server", types.SimpleNamespace(name_or_path="server")
            self.state = {"host": urllib.parse.urlsplit(self.url).netloc, "ok": False, "error": "", "model": "", "device": "", "ms": None}
            self.configure_lists()
            self._info()

        def _call(self, path, data=None, timeout=120):
            t0 = time.perf_counter()
            try:
                out = _open(self.url, self.key, self.pin, path, data, timeout)
            except Failure as ex:
                self.state.update(ok=False, error=ex.code)
                raise
            self.state.update(ok=True, error="", ms=round((time.perf_counter() - t0) * 1000))
            return out

        def _info(self):
            """Che modello ha il server e quali categorie in piu' conosce. Se non risponde lo si richiede piu' tardi."""
            if self._off_model is not None or time.time() - self._asked < 20:
                return
            self._asked = time.time()
            try:
                d = self._call("/omissis/info", timeout=8)
            except Failure:
                return
            self._off_model = [str(x) for x in d.get("off_model") or [] if RX_LABEL.fullmatch(str(x))]
            self.threshold = d.get("threshold")
            self.mod = types.SimpleNamespace(name_or_path=str(d.get("model") or "server")[:80])
            self.state.update(model=self.mod.name_or_path, device=str(d.get("device") or "")[:20])

        @property
        def off_model(self):
            self._info()
            return list(self._off_model or [])

        def configure_off(self, labels):
            self.off = sorted(set(labels or []))

        def model(self, texts):
            # le categorie in piu' accese su QUESTO PC: il server le accende per questa richiesta e basta
            on = [str(e) for e in settings.read().get("categories") or []]
            out, i = [], 0
            while i < len(texts):
                j, size = i, 0
                while j < len(texts) and j - i < PER_CALL and (j == i or size + len(texts[j]) * 2 < PER_CALL_BYTES):
                    size += len(texts[j]) * 2
                    j += 1
                r = self._call("/omissis/detect", {"texts": texts[i:j], "on": on, "client": NAME})
                spans = r.get("spans")
                if not isinstance(spans, list) or len(spans) != j - i:
                    self.state.update(ok=False, error="answer")
                    raise Failure("answer")
                for t, sp in zip(texts[i:j], spans):   # di cio' che arriva dalla rete ci si fida solo dopo averlo controllato
                    clean = []
                    for x in sp if isinstance(sp, list) else []:
                        if (isinstance(x, list) and len(x) == 3 and isinstance(x[0], int) and isinstance(x[1], int)
                                and 0 <= x[0] < x[1] <= len(t) and isinstance(x[2], str) and RX_LABEL.fullmatch(x[2])):
                            clean.append([x[0], x[1], x[2]])
                    out.append(clean)
                i = j
            return out

    return Remote()


# ---------------------------------------------------------------- dal lato del server
def shared():
    """Che cosa sta servendo questo PC, per il suo pannello: la porta e i PC che hanno chiesto qualcosa (solo conteggi)."""
    if not LISTENING["port"]:
        return None
    with _lock:
        clients = [{"name": n, **v} for n, v in sorted(SEEN.items(), key=lambda x: -x[1]["last"])][:200]
    return {"port": LISTENING["port"], "clients": clients}


def share(engine, port, key, cert, private):
    """Ascolta in rete (HTTPS) e risponde ai PC che portano la chiave. Non torna: va lanciata in un filo a parte."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(cert), str(private))
    wrong = {}   # indirizzo -> momenti dei tentativi con la chiave sbagliata

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):   # niente righe di log: ne' percorsi ne' indirizzi
            pass

        def _respond(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _allowed(self):
            who, now = self.client_address[0], time.time()
            with _lock:
                recent = wrong[who] = [t for t in wrong.get(who, []) if now - t < 60]
                if len(recent) >= 10:   # chi prova chiavi a caso viene lasciato fuori per un minuto
                    busy = True
                else:
                    busy = False
                    given = self.headers.get("Authorization", "")
                    if not secrets.compare_digest(given.encode("utf-8"), ("Bearer " + key).encode("utf-8")):
                        recent.append(now)
                        if len(wrong) > 5000:
                            wrong.clear()
                        self._respond(401, {"error": "key"})
                        return False
            if busy:
                self._respond(429, {"error": "wait"})
                return False
            return True

        def do_GET(self):
            if not self._allowed():
                return
            if self.path == "/omissis/info":
                self._respond(200, {"product": "omissis", "version": VERSION, "model": Path(str(engine.det.mod.name_or_path)).name,
                                    "device": engine.det.device, "threshold": engine.det.threshold, "off_model": list(engine.det.off_model)})
            else:
                self._respond(404, {"error": "path"})

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", 0))
            except ValueError:
                size = -1
            if size < 0 or size > MAX_BODY:
                self._respond(413, {"error": "size"})
                return
            raw = self.rfile.read(size)   # si legge prima di rispondere, anche per rifiutare: altrimenti chi scrive vede cadere la linea
            if not self._allowed():
                return
            if self.path != "/omissis/detect":
                self._respond(404, {"error": "path"})
                return
            try:
                data = json.loads(raw.decode("utf-8"))
                texts = data["texts"]
                if not isinstance(texts, list) or len(texts) > MAX_TEXTS or not all(isinstance(t, str) for t in texts):
                    raise ValueError
                on = [str(e) for e in data.get("on") or [] if RX_LABEL.fullmatch(str(e))][:60]
            except (ValueError, KeyError, TypeError):
                self._respond(400, {"error": "request"})
                return
            try:
                out = engine.detect(texts, on)
            except Exception as ex:   # noqa: BLE001  (chi ha chiesto deve sapere che NON e' stato controllato nulla)
                self._respond(500, {"error": type(ex).__name__})
                return
            name = re.sub(r"[^\w .-]", "", str(data.get("client") or ""))[:40] or self.client_address[0]
            with _lock:
                if name in SEEN or len(SEEN) < 500:
                    c = SEEN.setdefault(name, {"requests": 0, "texts": 0, "last": 0})
                    c["requests"] += 1
                    c["texts"] += len(texts)
                    c["last"] = round(time.time())
            self._respond(200, out)

    class Service(ThreadingHTTPServer):
        daemon_threads = True
        allow_reuse_address = False

        def finish_request(self, request, client_address):
            # la stretta di mano TLS si fa qui, nel filo della singola richiesta: chi apre la porta e tace non blocca gli altri
            try:
                request.settimeout(15)
                safe = context.wrap_socket(request, server_side=True)
                safe.settimeout(180)
            except (OSError, ssl.SSLError):
                return
            try:
                self.RequestHandlerClass(safe, client_address, self)
            except (OSError, ssl.SSLError):
                pass
            finally:
                try:
                    safe.close()
                except OSError:
                    pass

    service = Service(("0.0.0.0", port), Handler)
    LISTENING["port"] = port
    try:
        service.serve_forever()
    finally:
        LISTENING["port"] = 0
