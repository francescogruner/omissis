# -*- coding: utf-8 -*-
"""Il riepilogo di questo PC per la console centrale di un'organizzazione.

Parte SOLO se nelle impostazioni ci sono l'indirizzo della console e la chiave di collegamento (console_url,
console_key): chi usa Omissis per conto proprio non manda nulla a nessuno, e questo modulo non fa niente.

Che cosa viene inviato, una volta all'ora: versione e stato del programma, e per ciascuno degli ultimi giorni
QUANTE richieste avevano dati da sostituire, quanti valori per tipo di dato, verso quali servizi, quante richieste
sono state fermate; i nomi e le versioni degli strumenti AI trovati sul PC. Sono conteggi e nomi di programmi:
mai i testi, mai i valori sostituiti, mai l'archivio. Dal pannello (Impostazioni > Console centrale) si vede il
riepilogo esatto prima che parta.

Con console_names spento il riepilogo non porta il nome del computer ne' quello dell'utente.

Di chi ci si fida: senza altro, del certificato della console come farebbe un browser (un nome pubblico, un
certificato valido). Una console in rete locale non ha ne' l'uno ne' l'altro: si fa il certificato da se' e da' la
sua impronta (console_pin) insieme alla chiave di collegamento. Con l'impronta il programma si collega SOLO al
server che presenta proprio quel certificato, e lo controlla prima di mandare qualsiasi cosa.
"""
import collections
import datetime
import hashlib
import hmac
import http.client
import json
import os
import platform
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import inventory
import paths
import settings
import updates
from version import VERSION

DAYS = 35                 # quanti giorni porta ogni riepilogo: un PC rimasto spento recupera da solo
FORMAT = 1
STATE = {"last": "", "error": "", "sent": 0}
RX_LABEL, RX_SERVICE = re.compile(r"[A-Z][A-Z_]{1,23}"), re.compile(r"[a-z0-9][a-z0-9_.-]{0,39}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """La chiave di collegamento va solo all'indirizzo scelto: un rinvio altrove non viene seguito."""
    def redirect_request(self, *a, **k):
        return None


class _Pinned(http.client.HTTPSConnection):
    """Una connessione che vale solo se il certificato del server ha l'impronta attesa. Il controllo avviene appena
    finita la stretta di mano, prima che parta la richiesta: a un server diverso la chiave non arriva mai."""

    def __init__(self, host, pin="", **more):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.check_hostname, context.verify_mode = False, ssl.CERT_NONE   # al posto dell'autorita' che firma, vale l'impronta
        super().__init__(host, context=context, **more)
        self._pin = pin

    def connect(self):
        super().connect()
        found = hashlib.sha256(self.sock.getpeercert(binary_form=True) or b"").hexdigest()
        if not hmac.compare_digest(found, self._pin):
            self.close()
            raise ssl.SSLCertVerificationError("pin")


class _PinnedHandler(urllib.request.HTTPSHandler):
    def __init__(self, pin):
        super().__init__()
        self._pin = pin

    def https_open(self, req):
        return self.do_open(lambda host, **more: _Pinned(host, pin=self._pin, **more), req)


def _opener(cfg):
    """Con l'impronta: collegamento diretto (niente proxy in mezzo) al solo server con quel certificato."""
    if cfg.get("console_pin") and cfg["console_url"].startswith("https://"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}), _PinnedHandler(cfg["console_pin"]), _NoRedirect)
    return urllib.request.build_opener(_NoRedirect)


def device_id():
    """Un identificativo a caso di questa installazione: non deriva dal PC ne' dall'utente."""
    f = paths.DATA / "device.txt"
    try:
        found = f.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"[0-9a-f]{32}", found):
            return found
    except OSError:
        pass
    fresh = uuid.uuid4().hex
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(fresh, encoding="utf-8")
    return fresh


def days(n=DAYS):
    """Il registro delle attivita' riassunto giorno per giorno. Il registro contiene gia' solo conteggi."""
    since = (datetime.date.today() - datetime.timedelta(days=n - 1)).isoformat()   # con il calendario: al cambio dell'ora un giorno non dura 24 ore
    out = {}
    try:
        with (paths.DATA / "activity.jsonl").open(encoding="utf-8", errors="replace") as f:
            for row in f:
                try:
                    v = json.loads(row)
                except ValueError:
                    continue
                day, event = str(v.get("stamp", ""))[:10], str(v.get("event") or "")
                if not re.fullmatch(r"\d{4}-\d\d-\d\d", day) or day < since:
                    continue
                d = out.setdefault(day, {"requests": 0, "blocked": 0, "replacements": collections.Counter(), "services": collections.Counter()})
                found = {k: int(x) for k, x in (v.get("replacements") or {}).items() if RX_LABEL.fullmatch(str(k)) and isinstance(x, int) and x > 0}
                if event in ("masked", "attachment_masked") and found:
                    d["requests"] += 1
                    d["replacements"].update(found)
                    service = str(v.get("service") or "")
                    if RX_SERVICE.fullmatch(service):
                        d["services"][service] += 1
                elif event.startswith("blocked") or event == "file_blocked":
                    d["blocked"] += 1
    except OSError:
        pass
    return [{"day": day, "requests": d["requests"], "blocked": d["blocked"], "replacements": dict(d["replacements"]),
             "services": dict(d["services"])} for day, d in sorted(out.items()) if d["requests"] or d["blocked"]]


def tools():
    """Gli strumenti AI presenti sul PC secondo l'ultima analisi: categoria, nome, versione."""
    try:
        items = inventory.summary(events=0)["items"]
    except Exception:   # noqa: BLE001  (inventario mai fatto o illeggibile: il riepilogo parte lo stesso)
        return []
    return [{"category": str(e["category"])[:30], "name": str(e["name"])[:80], "version": str(e["version"] or "")[:40]}
            for e in items if e.get("present")][:300]


def summary(phase):
    """Tutto e solo cio' che viene inviato."""
    cfg, lock = settings.read(), settings.locked()
    out = {"v": FORMAT, "device": device_id(), "sent": time.strftime("%Y-%m-%d %H:%M:%S"), "version": VERSION,
           "channel": updates.channel(), "os": platform.platform()[:80], "protection": str(phase), "model": str(cfg.get("model"))[:40],
           "updates": updates.mode(), "groups_off": list(cfg.get("groups_off") or []),
           "managed": lock["keys"] + [f"policies.{s}" for s in lock["policies"]],
           "days": days(), "tools": tools()}
    if cfg.get("console_names", True):
        out["computer"] = (os.environ.get("COMPUTERNAME") or socket.gethostname())[:64]
        out["user"] = (os.environ.get("USERNAME") or "")[:64]
    return out


def configured(cfg=None):
    cfg = cfg or settings.read()
    return bool(cfg.get("console_url") and cfg.get("console_key"))


def send(phase):
    """Invia il riepilogo adesso. Restituisce lo stato; non solleva mai."""
    cfg = settings.read()
    if not configured(cfg):
        return state()
    try:
        if not settings.console_address_ok(cfg["console_url"]):
            raise ValueError("indirizzo non valido")
        req = urllib.request.Request(cfg["console_url"] + "/api/v1/report", data=json.dumps(summary(phase)).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + cfg["console_key"],
                                              "User-Agent": f"Omissis/{VERSION}"})
        with _opener(cfg).open(req, timeout=20) as r:
            r.read(4096)
        STATE.update(last=time.strftime("%Y-%m-%d %H:%M"), error="", sent=STATE["sent"] + 1)
    except urllib.error.HTTPError as ex:
        STATE.update(error=f"http_{ex.code}")
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as ex:
        if isinstance(ex, ssl.SSLCertVerificationError) or isinstance(getattr(ex, "reason", None), ssl.SSLCertVerificationError):
            STATE.update(error="certificate")   # non e' il server atteso (impronta diversa) o il certificato non e' valido
        else:
            STATE.update(error="address" if isinstance(ex, ValueError) and not isinstance(ex, OSError) else "unreachable")
    return state()


def state():
    cfg, lock = settings.read(), settings.locked()["keys"]
    host = urllib.parse.urlsplit(cfg.get("console_url") or "").netloc
    return {"configured": configured(cfg), "host": host, "url": cfg.get("console_url") or "", "has_key": bool(cfg.get("console_key")),
            "names": bool(cfg.get("console_names", True)), "pinned": bool(cfg.get("console_pin")), "managed": "console_url" in lock or "console_key" in lock,
            "last": STATE["last"], "error": STATE["error"]}


def loop(phase, after=90, every=3600):
    """In sottofondo: poco dopo l'avvio e poi una volta all'ora. phase() dice lo stato della protezione in quel momento."""
    time.sleep(after)
    while True:
        try:
            if configured():
                send(phase())
        except Exception:   # noqa: BLE001  (un invio andato male non deve mai fermare il programma)
            STATE.update(error="unreachable")
        time.sleep(every if not STATE["error"] else 600)
