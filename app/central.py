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

Che cosa torna indietro: la console risponde con le regole che vorrebbe imporre ai PC di quell'organizzazione. Questo
PC le applica SOLO se nelle impostazioni c'e' console_rules (di serie spento); altrimenti le ignora e non le conserva.
Sono regole e basta (quali servizi proteggere o bloccare, i file, gli aggiornamenti: l'elenco e' in settings.py):
la console non puo' cambiare a chi il PC manda qualcosa. Le regole dell'amministratore del PC vincono sempre.

Di chi ci si fida: senza altro, del certificato della console come farebbe un browser (un nome pubblico, un
certificato valido). Una console in rete locale non ha ne' l'uno ne' l'altro: si fa il certificato da se' e da' la
sua impronta (console_pin) insieme alla chiave di collegamento. Con l'impronta il programma si collega SOLO al
server che presenta proprio quel certificato, e lo controlla prima di mandare qualsiasi cosa.
"""
import collections
import datetime
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
import pinned
import settings
import updates
from version import VERSION

DAYS = 35                 # quanti giorni porta ogni riepilogo: un PC rimasto spento recupera da solo
FORMAT = 1
STATE = {"last": "", "error": "", "sent": 0, "again": False}
RX_LABEL, RX_SERVICE = re.compile(r"[A-Z][A-Z_]{1,23}"), re.compile(r"[a-z0-9][a-z0-9_.-]{0,39}")


def _opener(cfg):
    """Con l'impronta: collegamento diretto (niente proxy in mezzo) al solo server con quel certificato (pinned.py)."""
    return pinned.opener(cfg["console_pin"] if cfg.get("console_pin") and cfg["console_url"].startswith("https://") else "")


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
           "updates": updates.mode(), "groups_off": settings.reduced(cfg),
           "managed": lock["keys"] + [f"policies.{s}" for s in lock["policies"]],
           "rules_accept": cfg.get("console_rules") is True, "rules_version": rules()["version"],
           "days": days(), "tools": tools()}
    if cfg.get("console_names", True):
        out["computer"] = (os.environ.get("COMPUTERNAME") or socket.gethostname())[:64]
        out["user"] = (os.environ.get("USERNAME") or "")[:64]
    return out


def rules():
    """Le regole della console in vigore su questo PC: quante sono e che versione hanno (0 = nessuna)."""
    found = settings.from_console()
    n = len([k for k in found if k != "policies"]) + len(found.get("policies") or {})
    received, cfg = settings.console_file(), settings.read()
    mine = cfg.get("console_rules") is True and received.get("url") == cfg.get("console_url")
    return {"version": int(received.get("version") or 0) if mine else 0, "count": n}


def receive(cfg, answer):
    """Cio' che la console ha risposto al riepilogo. Se questo PC accetta le regole, quelle arrivate vengono messe da
    parte (settings.py le legge da li'); se non le accetta, non resta nulla. Una console che non parla di regole (una
    versione di prima) lascia tutto com'e'."""
    if cfg.get("console_rules") is not True:
        settings.CONSOLE_FILE.unlink(missing_ok=True)
        return
    try:
        data = json.loads(answer.decode("utf-8"))
        new, version = data["rules"], int(data.get("rules_version") or 0)
    except (ValueError, KeyError, TypeError, AttributeError):
        return
    if not isinstance(new, dict):
        return
    before = settings.console_file()
    if (before.get("url"), before.get("version"), before.get("rules")) == (cfg["console_url"], version, new):
        return
    settings.CONSOLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    settings.CONSOLE_FILE.write_text(json.dumps({"url": cfg["console_url"], "version": version, "rules": new, "received": time.strftime("%Y-%m-%d %H:%M")},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    STATE["again"] = True   # tra poco un altro riepilogo dice alla console che le regole nuove sono in vigore


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
            answer = r.read(512 * 1024)
        STATE.update(last=time.strftime("%Y-%m-%d %H:%M"), error="", sent=STATE["sent"] + 1)
        receive(cfg, answer)
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
            "rules": {"accept": cfg.get("console_rules") is True, "managed": "console_rules" in lock, **rules(),
                      "received": settings.console_file().get("received", "") if cfg.get("console_rules") is True else ""},
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
        again, STATE["again"] = STATE["again"], False
        time.sleep(60 if again else every if not STATE["error"] else 600)
