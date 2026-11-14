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
import json
import os
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import updates
import clipboard
import activity
import catalog
import connector
import documents
import folders
import gateway
import inventory
import mcp_server
import settings
import i18n
import weights
import paths
import restore
import scan
from version import VERSION

HERE = Path(__file__).resolve().parent
DATA = paths.DATA
PY_MODEL = paths.python_model()
LISTS = paths.lists()
PANEL_PORT, ENGINE_PORT = paths.PANEL_PORT, paths.ENGINE_PORT
NO_WINDOW = 0x08000000
CODE = secrets.token_urlsafe(24)
PAGE = HERE / "panel"   # i file della pagina: index.html, style.css, app.js, icon.svg, locales\<codice>.json
STATIC = {"/style.css": "text/css; charset=utf-8", "/app.js": "text/javascript; charset=utf-8", "/icon.svg": "image/svg+xml"}
RX_LANGUAGE = re.compile(r"/locales/[a-z]{2,3}(-[A-Za-z]{2,4})?\.json")
# la pagina carica solo file suoi: niente script o stili scritti dentro l'HTML, nessuna risorsa da fuori
POLICY_PAGE = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; "
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


def opened_port(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def engine(path, data=None, timeout=60):
    token = (DATA / "token.txt").read_text(encoding="utf-8").strip()
    req = urllib.request.Request(f"http://127.0.0.1:{ENGINE_PORT}{path}", headers={"X-Token": token, "Content-Type": "application/json"},
                                  data=json.dumps(data).encode("utf-8") if data is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


class Supervisor:
    """Tiene in vita i due processi: il motore (modello) e il proxy (mitmproxy)."""

    def __init__(self, test=False):
        self.engine = self.proxy = self.gateway = None
        self.gateway_error = ""
        self.test, self.phase, self.error = test, "stop", ""
        self.lock = threading.Lock()
        self.launched_with = None

    def _alive(self, p):
        return p is not None and p.poll() is None

    def launch(self):
        with self.lock:
            if self.phase in ("startup", "model"):
                return
            self.phase, self.error = "startup", ""
        threading.Thread(target=self._launch, daemon=True).start()

    def _launch(self):
        cfg = settings.read()
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            env = {**os.environ, "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                   "OMISSIS_ENGINE_URL": f"http://127.0.0.1:{ENGINE_PORT}"}
            if self.test:
                env["OMISSIS_TEST"] = "1"
            if not self._alive(self.engine) or self.launched_with is None or self.launched_with[:2] != (cfg["model"], cfg["device"]):
                self._stop(self.engine)
                if weights.missing(cfg["model"]):   # primo avvio di una copia installata: i pesi si scaricano una volta
                    self.phase = "model"
                    weights.download(cfg["model"])
                    self.phase = "startup"
                model = str(paths.model(cfg["model"]))
                command = [str(PY_MODEL), str(HERE / "engine.py"), "--model", model, "--port", str(ENGINE_PORT)]
                if cfg["device"] in ("cpu", "cuda"):
                    command += ["--device", cfg["device"]]
                self.engine = subprocess.Popen(command, env=env, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                               creationflags=NO_WINDOW)
                for _ in range(180):
                    if not self._alive(self.engine):
                        raise RuntimeError(i18n.t("program.engine_closed"))
                    try:
                        engine("/status", timeout=2)
                        break
                    except Exception:   # noqa: BLE001
                        time.sleep(1)
                else:
                    raise RuntimeError(i18n.t("program.engine_silent"))
            self._stop(self.proxy)
            command = [*paths.mitmdump(), "-q", "-s", str(HERE / "addon.py"), "--listen-host", "127.0.0.1",
                       "-p", str(cfg["port"]), "--set", f"confdir={DATA / 'ca'}"]
            for h in catalog.expressions_host(settings.guarded(cfg)):
                command += ["--allow-hosts", h]
            self.proxy = subprocess.Popen(command, env=env, cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                          creationflags=NO_WINDOW)
            for _ in range(40):
                if opened_port(cfg["port"]):
                    break
                if not self._alive(self.proxy):
                    raise RuntimeError(i18n.t("program.proxy_not_starting", port=cfg["port"]))
                time.sleep(0.5)
            self.launched_with = (cfg["model"], cfg["device"], cfg["port"], tuple(s["id"] for s in settings.guarded(cfg)))
            if self.gateway is None:   # per gli strumenti da terminale; se la porta e' occupata il resto funziona lo stesso
                try:
                    self.gateway, self.gateway_error = gateway.Gateway().launch(), ""
                except OSError:
                    self.gateway_error = i18n.t("program.gateway_port", port=paths.GATEWAY_PORT)
            self.phase = "active"
        except weights.Cancelled:
            self.phase = "stop"
        except Exception as ex:   # noqa: BLE001
            self._stop(self.proxy)
            self.phase, self.error = "error", str(ex)

    @staticmethod
    def _stop(p):
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(8)
            except subprocess.TimeoutExpired:
                p.kill()

    def stop(self):
        if self.phase == "model":
            weights.cancel()
        if self.gateway is not None:
            self.gateway.stop()
            self.gateway = None
        self._stop(self.proxy)
        self._stop(self.engine)
        self.proxy = self.engine = self.launched_with = None
        self.phase = "stop"

    def restart_needed(self):
        """Le impostazioni salvate richiedono un riavvio per avere effetto?"""
        if self.phase != "active" or self.launched_with is None:
            return False
        cfg = settings.read()
        return self.launched_with != (cfg["model"], cfg["device"], cfg["port"], tuple(s["id"] for s in settings.guarded(cfg)))

    def status(self):
        if self.phase == "active" and not (self._alive(self.engine) and self._alive(self.proxy)):
            self.phase, self.error = "error", i18n.t("program.process_closed")
        info = {}
        if self._alive(self.engine) and self.phase == "active":
            try:
                info = engine("/status", timeout=3)
            except Exception:   # noqa: BLE001
                info = {}
        return {"phase": self.phase, "error": self.error, "restart_needed": self.restart_needed(), "version": VERSION,
                "downloading": weights.status(settings.read()["model"]) if self.phase in ("model", "error") else None,
                "update": updates.status(),
                "model": Path(info["model"]).name if info.get("model") else None, "device": info.get("device"),
                "threshold": info.get("threshold"), "entries": info.get("entries"), "port": settings.read()["port"]}


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
        except Exception:   # noqa: BLE001
            pass


def mcp_state():
    """Il server MCP: se e' registrato in Claude Desktop, che cosa incollare nelle altre app, quali cartelle puo' usare."""
    file = DATA / "claude_desktop_config.json" if SUP.test else None   # nelle prove un file di prova, mai la configurazione vera
    return {"claude_desktop": mcp_server.claude_desktop_state(file), "snippets": mcp_server.snippets(),
            "folders": [str(x) for x in mcp_server._known_folders()], "extra": list(settings.read().get("mcp_folders") or [])}


def app_desktop():
    out = []
    for key, a in connector.APP.items():
        c = CONNECTORS.get(key)
        if c is not None and not c.alive:   # l'app e' stata chiusa
            CONNECTORS.pop(key, None)
            c = None
        service = catalog.PER_ID.get(a.get("service", ""))
        out.append({"id": key, "name": a["name"], "installed": connector.find_command(a) is not None,
                    "connected": c is not None, "outcome": c.outcome if c else None, "counts": dict(c.counts) if c else None,
                    "errors": (c.notices + c.errors)[-3:] if c else [],
                    # aperta ma non da qui: dentro non c'e' nessuna protezione
                    # (nelle prove no: pagina e schermate non devono dipendere da cio' che e' aperto su questo PC)
                    "open_unprotected": c is None and not SUP.test and connector.open_unprotected(key),
                    "own_profile": bool(a.get("own_profile")), "refuses": bool(a.get("refuses")),
                    # la politica del servizio decide se i messaggi vengono mascherati: con «registra» l'app si collega e basta
                    "service": service["name"] if service else "", "policy": settings.policy(service) if service else "protect"})
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
        if v.get("VALORI_IN_CHIARO"):
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
    cfg, cont = settings.read(), contacts()
    return [{"id": s["id"], "name": s["name"], "vendor": s["vendor"], "kind": s["kind"], "domains": s["domains"],
             "reading": "radar" if s["radar"] else READING_STATUS[s["adapter"]], "radar": s["radar"], "readable": bool(s["adapter"]),
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


def certificate(action=None):
    cer = DATA / "ca" / "mitmproxy-ca-cert.cer"
    if action == "install" and cer.exists():
        subprocess.run(["certutil", "-user", "-addstore", "Root", str(cer)], capture_output=True, timeout=120, creationflags=NO_WINDOW)
    elif action == "remove":
        subprocess.run(["certutil", "-user", "-delstore", "Root", "mitmproxy"], capture_output=True, timeout=120, creationflags=NO_WINDOW)
    r = subprocess.run(["certutil", "-user", "-store", "Root", "mitmproxy"], capture_output=True, timeout=30, creationflags=NO_WINDOW)
    return {"exists": cer.exists(), "installed": r.returncode == 0 and b"mitmproxy" in r.stdout}


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
                                     "updated": verified_ones.get("updated", "")})
            elif u.path == "/api/languages":
                self._respond(200, {"choice": i18n.choice(), "active": i18n.active(), "available": i18n.available()})
            elif u.path == "/api/status":
                self._respond(200, {**SUP.status(), "stats": stats()})
            elif u.path == "/api/activity":
                self._respond(200, read_log(int(q.get("n", 300)))[::-1])
            elif u.path == "/api/services":
                self._respond(200, services())
            elif u.path == "/api/settings":
                self._respond(200, {**settings.read(), "certificate": certificate()})
            elif u.path == "/api/lists":
                self._respond(200, read_lists())
            elif u.path == "/api/app":
                self._respond(200, app_desktop())
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
                self._respond(200, {"folder": str(HERE / "extension"), "port": ENGINE_PORT,
                                     "token": f.read_text(encoding="utf-8").strip() if f.exists() else ""})
            elif u.path == "/api/categories":   # le categorie in piu' che il modello in uso conosce, e quelle accese
                try:
                    self._respond(200, engine("/profile", {}))
                except Exception:   # noqa: BLE001
                    self._respond(200, {"known": [], "enabled": settings.read().get("categories", [])})
            elif u.path == "/api/shortcuts":
                self._respond(200, shortcuts())
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
                    SUP.stop()
                else:
                    if data.get("action") == "restart":
                        SUP.stop()
                    SUP.launch()
                self._respond(200, SUP.status())
            elif p == "/api/settings":
                new_ones = settings.write({**settings.read(), **{k: v for k, v in data.items() if k in settings.DEFAULTS}})
                if "shortcuts" in data and SHORTCUTS is not None:
                    SHORTCUTS.configure(clipboard.choices(new_ones))
                if "categories" in data:   # il motore rilegge quali categorie in piu' sostituire
                    try:
                        engine("/profile", {})
                    except Exception:   # noqa: BLE001  (motore spento: le leggera' all'avvio)
                        pass
                self._respond(200, {**new_ones, "restart_needed": SUP.restart_needed()})
            elif p == "/api/services":
                cfg = settings.read()
                policies = dict(cfg["policies"])
                policies[str(data["id"])] = str(data["policy"])
                settings.write({**cfg, "policies": policies})
                self._respond(200, {"restart_needed": SUP.restart_needed()})
            elif p == "/api/lists":
                self._respond(200, write_lists(data))
            elif p == "/api/gateway":   # chi ha gia' un proprio gateway: dove inoltrare, servizio per servizio (vuoto = il servizio vero)
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
                    chosen = [str(x).strip().strip('"') for x in data.get("folders") or [] if str(x).strip()]
                    missing = [x for x in chosen if not Path(x).is_dir()]
                    if missing:
                        raise Refusal(i18n.t("mcp.error.folder", folder=missing[0]))
                    settings.write({**settings.read(), "mcp_folders": chosen})
                self._respond(200, mcp_state())
            elif p == "/api/app":
                key = str(data.get("id", ""))
                if key not in connector.APP:
                    raise Refusal(i18n.t("program.app_unknown"))
                action = data.get("action")
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
                        raise Refusal(i18n.t("program.update_nothing_ready"))
                    turn_off()
                self._respond(200, updates.status())
            elif p == "/api/try":
                text = str(data.get("text", ""))
                if len(text) > clipboard.MAX_TEXT:   # mai tagliare in silenzio: il pezzo tagliato sembrerebbe controllato
                    raise Refusal(i18n.t("program.text_too_long", n=clipboard.MAX_TEXT))
                # le correzioni fatte a mano su questo testo: cosa lasciare in chiaro e cosa mascherare comunque
                never = [str(x)[:200] for x in data.get("never") or []][:200]
                also = {str(k)[:200]: str(v) for k, v in list((data.get("also") or {}).items())[:200]}
                self._respond(200, engine("/mask", {"texts": [text], "never": never, "also": also}))
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
                self._respond(200, {"outcome": clipboard.transform("restore" if data.get("action") == "restore" else "mask", engine)})
            elif p == "/api/documents/path":
                action = "restore" if data.get("action") == "restore" else "anonymize"
                outcome = documents.path(str(data.get("path", "")), action)
                FOLDERS.add(os.path.normcase(os.path.abspath(str(outcome.get("destination", "")))))
                self._respond(200, outcome)
            elif p == "/api/documents/file":
                action = data.get("action") if data.get("action") in ("anonymize", "restore") else "auto"
                action, name, fresh, counts = documents.work_on_auto(Path(str(data.get("name", "file"))).name, base64.b64decode(data.get("content", "")), action)
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


def icon(server):
    """Icona vicino all'orologio. Se le librerie mancano il programma funziona lo stesso dalla pagina."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
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

    def change(ic, _):
        SUP.stop() if SUP.phase == "active" else SUP.launch()

    def exit_app(ic, _):
        SUP.stop()
        ic.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    def with_keystrokes(name):   # «Maschera gli appunti  (Ctrl+Alt+M)»: la combinazione compare solo se e' attiva
        entry = (SHORTCUTS.status if SHORTCUTS else {}).get(name, {})
        return i18n.t(f"icon.{name}") + (f"  ({clipboard.caption(entry['combo'])})" if entry.get("active") else "")

    def on_clipboard(action):
        def run(icon_, _):
            try:
                notify(clipboard.transform(action, engine))
            except Exception:   # noqa: BLE001
                notify(i18n.t("program.protection_not_active"))
        return run

    ic = pystray.Icon("omissis", drawing(False), "Omissis", menu=pystray.Menu(
        # i testi sono funzioni: il menu segue la lingua scelta nelle Impostazioni senza riavviare il programma
        pystray.MenuItem(lambda _: i18n.t("icon.open_up"), open_up, default=True),
        pystray.MenuItem(lambda _: with_keystrokes("mask"), on_clipboard("mask")),
        pystray.MenuItem(lambda _: with_keystrokes("restore"), on_clipboard("restore")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda _: i18n.t("icon.stop" if SUP.phase == "active" else "icon.launch"), change),
        pystray.MenuItem(lambda _: i18n.t("icon.exit_app"), exit_app)))

    def refresh():
        latest, notified = None, ""
        while ic.visible or latest is None:
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

    def notify(message):   # esito delle scorciatoie sugli appunti, come notifica di Windows
        try:
            ic.notify(message, "Omissis")
        except Exception:   # noqa: BLE001
            pass

    global SHORTCUTS, NOTIFY
    NOTIFY = notify
    SHORTCUTS = clipboard.shortcuts(engine, notify)
    in_use, changed = clipboard.system(SHORTCUTS, clipboard.choices(settings.read()))
    if changed:   # una combinazione era gia' di un altro programma: si tiene quella libera e lo si dice, a icona comparsa
        settings.write({**settings.read(), "shortcuts": in_use})
        listing = ", ".join(f"{clipboard.caption(old_one)} → {clipboard.caption(new_one)}" for old_one, new_one in changed.values())
        threading.Timer(8, lambda: notify(i18n.t("shortcuts.changed", listing=listing))).start()
    return ic


def main():
    global SUP
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tray", dest="without_icon", action="store_true")
    ap.add_argument("--no-browser", dest="without_browser", action="store_true")
    ap.add_argument("--no-start", dest="do_not_launch", action="store_true", help="apre il pannello senza avviare la protezione")
    ap.add_argument("--test", dest="test", action="store_true", help="accetta anche il servizio finto in locale")
    a = ap.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    if opened_port(PANEL_PORT):   # gia' acceso: si apre solo il pannello
        print(f"Omissis è già acceso: apro il pannello su http://127.0.0.1:{PANEL_PORT}/", flush=True)
        if not a.without_browser:
            webbrowser.open(f"http://127.0.0.1:{PANEL_PORT}/")
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
        allow_reuse_address = False   # una seconda copia del programma deve accorgersi che la prima e' gia' accesa

    try:
        server = Service(("127.0.0.1", PANEL_PORT), Handler)
    except OSError:
        print(f"Omissis è già acceso: apro il pannello su http://127.0.0.1:{PANEL_PORT}/", flush=True)
        if not a.without_browser:
            webbrowser.open(f"http://127.0.0.1:{PANEL_PORT}/")
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=updates.loop, daemon=True).start()
    if not a.test:   # nelle prove niente lavoro in sottofondo: i risultati devono dipendere solo da cio' che la prova fa
        threading.Thread(target=watch, daemon=True).start()
        threading.Thread(target=watch_apps, daemon=True).start()
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
        SUP.stop()


if __name__ == "__main__":
    main()
