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
import catalog
import connector
import documents
import gateway
import settings
import i18n
import weights
import paths
import restore
import scan
from version import VERSIONE

QUI = Path(__file__).resolve().parent
DATI = paths.DATI
PY_MODELLO = paths.python_modello()
LISTE = paths.liste()
PORTA_PANNELLO, PORTA_MOTORE = paths.PORTA_PANNELLO, paths.PORTA_MOTORE
SENZA_FINESTRA = 0x08000000
CODICE = secrets.token_urlsafe(24)
PAGINA = QUI / "panel"   # i file della pagina: index.html, style.css, app.js, icon.svg, locales\<codice>.json
STATICI = {"/style.css": "text/css; charset=utf-8", "/app.js": "text/javascript; charset=utf-8", "/icon.svg": "image/svg+xml"}
RX_LINGUA = re.compile(r"/locales/[a-z]{2,3}(-[A-Za-z]{2,4})?\.json")
# la pagina carica solo file suoi: niente script o stili scritti dentro l'HTML, nessuna risorsa da fuori
POLITICA_PAGINA = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self'; "
                   "base-uri 'none'; frame-ancestors 'none'")
# quanto e' provata la lettura di ciascun servizio: la pagina traduce il codice (servizi.lettura.<codice>)
STATO_LETTURA = {"claude": "provato", "chatgpt": "provato", "anthropic": "provato", "openai": "provato",
                 "gemini": "sperimentale", "generico": "generico", None: "no"}


class Rifiuto(Exception):
    """Una richiesta della pagina che non si puo' esaudire: il messaggio e' per l'utente, nella sua lingua."""


def porta_aperta(porta):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", porta)) == 0


def motore(percorso, dati=None, attesa=60):
    token = (DATI / "token.txt").read_text(encoding="utf-8").strip()
    rich = urllib.request.Request(f"http://127.0.0.1:{PORTA_MOTORE}{percorso}", headers={"X-Token": token, "Content-Type": "application/json"},
                                  data=json.dumps(dati).encode("utf-8") if dati is not None else None)
    with urllib.request.urlopen(rich, timeout=attesa) as r:
        return json.loads(r.read().decode("utf-8"))


class Supervisore:
    """Tiene in vita i due processi: il motore (modello) e il proxy (mitmproxy)."""

    def __init__(self, prova=False):
        self.motore = self.proxy = self.gateway = None
        self.errore_gateway = ""
        self.prova, self.fase, self.errore = prova, "ferma", ""
        self.lucchetto = threading.Lock()
        self.avviato_con = None

    def _vivo(self, p):
        return p is not None and p.poll() is None

    def avvia(self):
        with self.lucchetto:
            if self.fase in ("avvio", "modello"):
                return
            self.fase, self.errore = "avvio", ""
        threading.Thread(target=self._avvia, daemon=True).start()

    def _avvia(self):
        imp = settings.leggi()
        try:
            DATI.mkdir(parents=True, exist_ok=True)
            amb = {**os.environ, "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                   "OMISSIS_ENGINE_URL": f"http://127.0.0.1:{PORTA_MOTORE}"}
            if self.prova:
                amb["OMISSIS_TEST"] = "1"
            if not self._vivo(self.motore) or self.avviato_con is None or self.avviato_con[:2] != (imp["modello"], imp["device"]):
                self._ferma(self.motore)
                if weights.manca(imp["modello"]):   # primo avvio di una copia installata: i pesi si scaricano una volta
                    self.fase = "modello"
                    weights.scarica(imp["modello"])
                    self.fase = "avvio"
                modello = str(paths.modello(imp["modello"]))
                comando = [str(PY_MODELLO), str(QUI / "engine.py"), "--model", modello, "--port", str(PORTA_MOTORE)]
                if imp["device"] in ("cpu", "cuda"):
                    comando += ["--device", imp["device"]]
                self.motore = subprocess.Popen(comando, env=amb, cwd=QUI, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                               creationflags=SENZA_FINESTRA)
                for _ in range(180):
                    if not self._vivo(self.motore):
                        raise RuntimeError(i18n.t("programma.motore_chiuso"))
                    try:
                        motore("/stato", attesa=2)
                        break
                    except Exception:   # noqa: BLE001
                        time.sleep(1)
                else:
                    raise RuntimeError(i18n.t("programma.motore_muto"))
            self._ferma(self.proxy)
            comando = [*paths.mitmdump(), "-q", "-s", str(QUI / "addon.py"), "--listen-host", "127.0.0.1",
                       "-p", str(imp["porta"]), "--set", f"confdir={DATI / 'ca'}"]
            for h in catalog.espressioni_host(settings.protetti(imp)):
                comando += ["--allow-hosts", h]
            self.proxy = subprocess.Popen(comando, env=amb, cwd=QUI, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                          creationflags=SENZA_FINESTRA)
            for _ in range(40):
                if porta_aperta(imp["porta"]):
                    break
                if not self._vivo(self.proxy):
                    raise RuntimeError(i18n.t("programma.proxy_non_parte", porta=imp["porta"]))
                time.sleep(0.5)
            self.avviato_con = (imp["modello"], imp["device"], imp["porta"], tuple(s["id"] for s in settings.protetti(imp)))
            if self.gateway is None:   # per gli strumenti da terminale; se la porta e' occupata il resto funziona lo stesso
                try:
                    self.gateway, self.errore_gateway = gateway.Gateway().avvia(), ""
                except OSError:
                    self.errore_gateway = i18n.t("programma.gateway_porta", porta=paths.PORTA_GATEWAY)
            self.fase = "attiva"
        except weights.Annullato:
            self.fase = "ferma"
        except Exception as ex:   # noqa: BLE001
            self._ferma(self.proxy)
            self.fase, self.errore = "errore", str(ex)

    @staticmethod
    def _ferma(p):
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(8)
            except subprocess.TimeoutExpired:
                p.kill()

    def ferma(self):
        if self.fase == "modello":
            weights.annulla()
        if self.gateway is not None:
            self.gateway.ferma()
            self.gateway = None
        self._ferma(self.proxy)
        self._ferma(self.motore)
        self.proxy = self.motore = self.avviato_con = None
        self.fase = "ferma"

    def da_riavviare(self):
        """Le impostazioni salvate richiedono un riavvio per avere effetto?"""
        if self.fase != "attiva" or self.avviato_con is None:
            return False
        imp = settings.leggi()
        return self.avviato_con != (imp["modello"], imp["device"], imp["porta"], tuple(s["id"] for s in settings.protetti(imp)))

    def stato(self):
        if self.fase == "attiva" and not (self._vivo(self.motore) and self._vivo(self.proxy)):
            self.fase, self.errore = "errore", i18n.t("programma.processo_chiuso")
        info = {}
        if self._vivo(self.motore) and self.fase == "attiva":
            try:
                info = motore("/stato", attesa=3)
            except Exception:   # noqa: BLE001
                info = {}
        return {"fase": self.fase, "errore": self.errore, "da_riavviare": self.da_riavviare(), "versione": VERSIONE,
                "scaricamento": weights.stato(settings.leggi()["modello"]) if self.fase in ("modello", "errore") else None,
                "aggiornamento": updates.stato(),
                "modello": Path(info["modello"]).name if info.get("modello") else None, "device": info.get("device"),
                "soglia": info.get("soglia"), "voci": info.get("voci"), "porta": settings.leggi()["porta"]}


SUP = None
ICONA = None
CONNETTORI = {}   # app desktop avviate da qui: chiave -> Connettore


def spegni(dopo=1.5):
    """Chiude tutto il programma (lo usa l'aggiornamento: l'installer lo sostituisce e lo riapre)."""
    def esegui():
        time.sleep(dopo)   # il tempo di rispondere alla pagina
        try:
            for c in list(CONNETTORI.values()):
                c.chiudi()
            SUP.ferma()
            if ICONA is not None:
                ICONA.stop()
        finally:
            os._exit(0)
    threading.Thread(target=esegui, daemon=True).start()


def app_desktop():
    out = []
    for chiave, a in connector.APP.items():
        c = CONNETTORI.get(chiave)
        if c is not None and not c.vivo:   # l'app e' stata chiusa
            CONNETTORI.pop(chiave, None)
            c = None
        out.append({"id": chiave, "nome": a["nome"], "installata": Path(os.path.expandvars(a["comando"])).exists(),
                    "collegata": c is not None, "esito": c.esito if c else None, "conteggi": dict(c.conteggi) if c else None,
                    "errori": c.errori[-3:] if c else []})
    return out


# ------------------------------------------------------------------ dati per la pagina

def leggi_registro(n=20000):
    f = DATI / "activity.jsonl"
    if not f.exists():
        return []
    out = []
    for riga in f.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(riga))
        except ValueError:
            pass
    return out


def statistiche():
    oggi = time.strftime("%Y-%m-%d")
    giorni = [time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * i)) for i in range(6, -1, -1)]
    per_giorno = {g: 0 for g in giorni}
    tipi, servizi, avvisi = collections.Counter(), collections.Counter(), collections.Counter()
    conta = collections.Counter()
    for v in leggi_registro():
        g, ev = v.get("ora", "")[:10], v.get("evento", "")
        if g not in per_giorno:
            continue
        sost = sum((v.get("sostituzioni") or {}).values())
        if ev == "mascherata":
            per_giorno[g] += 1
            servizi[v.get("servizio", "?")] += 1
            tipi.update(v.get("sostituzioni") or {})
            if g == oggi:
                conta["messaggi"] += 1
                conta["sostituzioni"] += sost
        elif ev.startswith("BLOCCAT") or ev == "file bloccato":
            conta["bloccate"] += g == oggi
            avvisi["bloccate"] += 1
        elif "nessun campo" in ev:
            avvisi["non_riconosciute"] += 1
        elif ev == "file NON mascherato":
            avvisi["file_non_mascherati"] += 1
        if v.get("VALORI_IN_CHIARO"):
            avvisi["valori_in_chiaro"] += 1
    return {"oggi": {"messaggi": conta["messaggi"], "sostituzioni": conta["sostituzioni"], "bloccate": conta["bloccate"]},
            "giorni": [{"giorno": g, "n": per_giorno[g]} for g in giorni], "tipi": tipi.most_common(), "servizi": servizi.most_common(),
            "avvisi": [{"codice": k, "n": n} for k, n in avvisi.most_common()]}


def contatti(giorni=30):
    f = DATI / "contacts.sqlite"
    if not f.exists():
        return {}
    da = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * giorni))
    try:
        db = sqlite3.connect(f"file:{f.as_posix()}?mode=ro", uri=True)
        righe = db.execute("SELECT servizio, esito, SUM(n), MAX(ultimo) FROM contatti WHERE giorno >= ? GROUP BY servizio, esito", (da,)).fetchall()
        db.close()
    except sqlite3.Error:
        return {}
    out = {}
    for servizio, esito, n, ultimo in righe:
        v = out.setdefault(servizio, {"n": 0, "ultimo": "", "esiti": {}})
        v["n"] += n
        v["ultimo"] = max(v["ultimo"], ultimo or "")
        v["esiti"][esito] = n
    return out


def servizi():
    imp, cont = settings.leggi(), contatti()
    return [{"id": s["id"], "nome": s["nome"], "fornitore": s["fornitore"], "tipo": s["tipo"], "domini": s["domini"],
             "lettura": "radar" if s["radar"] else STATO_LETTURA[s["adattatore"]], "radar": s["radar"], "leggibile": bool(s["adattatore"]),
             "politica": settings.politica(s, imp),
             "predefinita": catalog.politica_predefinita(s), "contatti": cont.get(s["id"], {}).get("n", 0),
             "ultimo": cont.get(s["id"], {}).get("ultimo", "")} for s in catalog.SERVIZI]


def leggi_liste():
    def f(nome):
        p = LISTE / nome
        return [r.strip() for r in p.read_text(encoding="utf-8").splitlines() if r.strip() and not r.lstrip().startswith("#")] if p.exists() else []
    return {"sempre": f("always.txt"), "mai": f("never.txt")}


def scrivi_liste(dati):
    testate = {"always.txt": "# Termini da mascherare SEMPRE, uno per riga (maiuscole e minuscole non contano).\n",
               "never.txt": "# Termini da NON mascherare mai, uno per riga (maiuscole e minuscole non contano).\n"}
    LISTE.mkdir(parents=True, exist_ok=True)
    for nome, chiave in (("always.txt", "sempre"), ("never.txt", "mai")):
        voci = [str(x).strip()[:200] for x in dati.get(chiave, []) if str(x).strip() and not str(x).lstrip().startswith("#")][:5000]
        (LISTE / nome).write_text(testate[nome] + "\n".join(voci) + ("\n" if voci else ""), encoding="utf-8")
    try:
        motore("/liste", {})
    except Exception:   # noqa: BLE001  (motore spento: le leggera' al prossimo avvio)
        pass
    return leggi_liste()


def certificato(azione=None):
    cer = DATI / "ca" / "mitmproxy-ca-cert.cer"
    if azione == "installa" and cer.exists():
        subprocess.run(["certutil", "-user", "-addstore", "Root", str(cer)], capture_output=True, timeout=120, creationflags=SENZA_FINESTRA)
    elif azione == "rimuovi":
        subprocess.run(["certutil", "-user", "-delstore", "Root", "mitmproxy"], capture_output=True, timeout=120, creationflags=SENZA_FINESTRA)
    r = subprocess.run(["certutil", "-user", "-store", "Root", "mitmproxy"], capture_output=True, timeout=30, creationflags=SENZA_FINESTRA)
    return {"esiste": cer.exists(), "installato": r.returncode == 0 and b"mitmproxy" in r.stdout}


# ------------------------------------------------------------------ servizio web locale

class Gestore(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _rispondi(self, codice, oggetto, tipo="application/json; charset=utf-8"):
        corpo = oggetto if isinstance(oggetto, bytes) else json.dumps(oggetto, ensure_ascii=False).encode("utf-8")
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", POLITICA_PAGINA)
        self.end_headers()
        self.wfile.write(corpo)

    def _lecito(self):
        """Solo questo PC (niente nomi host estranei) e, per i dati, solo chi ha il codice della pagina."""
        if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            self._rispondi(403, {"errore": "host non ammesso"})
            return False
        if self.path.startswith("/api/") and not secrets.compare_digest(self.headers.get("X-Pannello", ""), CODICE):
            self._rispondi(403, {"errore": "codice mancante"})
            return False
        if self.path.startswith("/interno/"):   # chiamate del motore (stesso PC), con il suo codice
            try:
                atteso = (DATI / "token.txt").read_text(encoding="utf-8").strip()
            except OSError:
                atteso = ""
            if not atteso or not secrets.compare_digest(self.headers.get("X-Token", ""), atteso):
                self._rispondi(403, {"errore": "codice mancante"})
                return False
        return True

    def do_GET(self):
        if not self._lecito():
            return
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        try:
            if u.path == "/":
                pagina = (PAGINA / "index.html").read_text(encoding="utf-8").replace("__CODICE__", CODICE).replace("__LINGUA__", i18n.attiva())
                self._rispondi(200, pagina.encode("utf-8"), "text/html; charset=utf-8")
            elif u.path in STATICI or RX_LINGUA.fullmatch(u.path):
                self._rispondi(200, (PAGINA / u.path.lstrip("/")).read_bytes(), STATICI.get(u.path, "application/json; charset=utf-8"))
            elif u.path == "/api/lingue":
                self._rispondi(200, {"scelta": i18n.scelta(), "attiva": i18n.attiva(), "disponibili": i18n.disponibili()})
            elif u.path == "/api/stato":
                self._rispondi(200, {**SUP.stato(), "statistiche": statistiche()})
            elif u.path == "/api/registro":
                self._rispondi(200, leggi_registro(int(q.get("n", 300)))[::-1])
            elif u.path == "/api/servizi":
                self._rispondi(200, servizi())
            elif u.path == "/api/impostazioni":
                self._rispondi(200, {**settings.leggi(), "certificato": certificato()})
            elif u.path == "/api/liste":
                self._rispondi(200, leggi_liste())
            elif u.path == "/api/app":
                self._rispondi(200, app_desktop())
            elif u.path == "/api/vista":
                self._rispondi(200, {"vista": settings.leggi().get("vista", "semplice")})
            elif u.path == "/api/gateway":
                g = SUP.gateway
                self._rispondi(200, {"attivo": g is not None, "porta": paths.PORTA_GATEWAY, "errore": SUP.errore_gateway,
                                     "conteggi": dict(g.conteggi) if g else None, "rotte": sorted(gateway.rotte())})
            elif u.path == "/api/estensione":
                f = DATI / "token_extension.txt"
                self._rispondi(200, {"cartella": str(QUI / "extension"), "porta": PORTA_MOTORE,
                                     "token": f.read_text(encoding="utf-8").strip() if f.exists() else ""})
            elif u.path == "/api/shadow/pc":
                self._rispondi(200, scan.pc())
            elif u.path == "/api/shadow/rete":
                nomi = {s["id"]: s["nome"] for s in catalog.SERVIZI}
                self._rispondi(200, {**scan.rete(), "proxy": [{"servizio": nomi.get(k, k), **v} for k, v in
                                                                   sorted(contatti().items(), key=lambda kv: -kv[1]["n"])]})
            else:
                self._rispondi(404, {"errore": i18n.t("programma.non_trovato")})
        except FileNotFoundError:
            self._rispondi(404, {"errore": i18n.t("programma.non_trovato")})
        except Exception as ex:   # noqa: BLE001
            self._rispondi(500, {"errore": f"{type(ex).__name__}: {ex}"})

    def do_POST(self):
        if not self._lecito():
            return
        try:
            dati = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8") or "{}")
            p = self.path
            if p == "/interno/allegato":   # il motore non ha le librerie per i documenti: li legge questo processo
                try:
                    nome, nuovo, conteggi = documents.elabora(Path(str(dati.get("nome", "file"))).name, base64.b64decode(dati.get("dati", "")), "anonimizza")
                except documents.Errore as ex:
                    self._rispondi(422, {"errore": str(ex), "codice": ex.codice})
                    return
                self._rispondi(200, {"nome": nome, "dati": base64.b64encode(nuovo).decode("ascii"), "conteggi": conteggi})
            elif p == "/api/protezione":
                if dati.get("azione") == "ferma":
                    SUP.ferma()
                else:
                    if dati.get("azione") == "riavvia":
                        SUP.ferma()
                    SUP.avvia()
                self._rispondi(200, SUP.stato())
            elif p == "/api/impostazioni":
                nuove = settings.scrivi({**settings.leggi(), **{k: v for k, v in dati.items() if k in settings.PREDEFINITE}})
                self._rispondi(200, {**nuove, "da_riavviare": SUP.da_riavviare()})
            elif p == "/api/servizi":
                imp = settings.leggi()
                politiche = dict(imp["politiche"])
                politiche[str(dati["id"])] = str(dati["politica"])
                settings.scrivi({**imp, "politiche": politiche})
                self._rispondi(200, {"da_riavviare": SUP.da_riavviare()})
            elif p == "/api/liste":
                self._rispondi(200, scrivi_liste(dati))
            elif p == "/api/app":
                chiave = str(dati.get("id", ""))
                if chiave not in connector.APP:
                    raise Rifiuto(i18n.t("programma.app_sconosciuta"))
                vecchio = CONNETTORI.pop(chiave, None)
                if vecchio is not None:
                    vecchio.chiudi()
                if dati.get("azione") == "avvia":
                    if SUP.fase != "attiva":
                        raise Rifiuto(i18n.t("programma.app_serve_protezione"))
                    CONNETTORI[chiave] = connector.avvia_app(chiave)
                self._rispondi(200, app_desktop())
            elif p == "/api/aggiornamenti":
                azione = dati.get("azione")
                if azione == "controlla":
                    updates.controlla()
                elif azione == "scarica":
                    if updates.STATO["fase"] != "disponibile":
                        raise Rifiuto(i18n.t("programma.aggiornamento_niente_da_scaricare"))
                    threading.Thread(target=updates.scarica, daemon=True).start()
                    time.sleep(0.3)
                elif azione == "installa":
                    versione = updates.installa()
                    if versione is None:
                        raise Rifiuto(i18n.t("programma.aggiornamento_niente_pronto"))
                    spegni()
                self._rispondi(200, updates.stato())
            elif p == "/api/prova":
                self._rispondi(200, motore("/maschera", {"testi": [str(dati.get("testo", ""))[:20000]]}))
            elif p == "/api/ripristina":
                testo = str(dati.get("testo", ""))[:200000]
                trovati = sorted({m.group() for m in restore.RX_SEGNAPOSTO.finditer(testo)})
                mappa = motore("/valori", {"segnaposto": trovati})["mappa"] if trovati else {}
                self._rispondi(200, {"testo": restore.ripristina(testo, mappa.get), "ripristinati": len(mappa),
                                     "sconosciuti": len(trovati) - len(mappa)})
            elif p == "/api/appunti":
                self._rispondi(200, {"esito": clipboard.trasforma("ripristina" if dati.get("azione") == "ripristina" else "maschera", motore)})
            elif p == "/api/documenti/percorso":
                azione = "ripristina" if dati.get("azione") == "ripristina" else "anonimizza"
                self._rispondi(200, documents.percorso(str(dati.get("percorso", "")), azione))
            elif p == "/api/documenti/file":
                azione = dati.get("azione") if dati.get("azione") in ("anonimizza", "ripristina") else "auto"
                azione, nome, nuovo, conteggi = documents.elabora_auto(Path(str(dati.get("nome", "file"))).name, base64.b64decode(dati.get("contenuto", "")), azione)
                self._rispondi(200, {"azione": azione, "nome": nome, "contenuto": base64.b64encode(nuovo).decode("ascii"), "conteggi": conteggi})
            elif p == "/api/archivio":
                self._rispondi(200, motore("/archivio", {"limite": 500, "in_chiaro": bool(dati.get("in_chiaro"))}))
            elif p == "/api/archivio/svuota":
                self._rispondi(200, motore("/archivio/svuota", {}))
            elif p == "/api/certificato":
                self._rispondi(200, certificato(dati.get("azione")))
            elif p == "/api/browser":
                indirizzo = str(dati.get("indirizzo", "https://claude.ai"))
                if not indirizzo.startswith("https://") or catalog.trova(urllib.parse.urlparse(indirizzo).hostname or "") is None:
                    raise Rifiuto(i18n.t("programma.indirizzo_fuori_catalogo"))
                r = subprocess.run([sys.executable, str(QUI / "browser_window.py"), indirizzo], capture_output=True, timeout=30,
                                   creationflags=SENZA_FINESTRA)
                self._rispondi(200, {"esito": r.stdout.decode("utf-8", errors="replace").strip() or r.stderr.decode("utf-8", errors="replace").strip()})
            else:
                self._rispondi(404, {"errore": i18n.t("programma.non_trovato")})
        except (documents.Errore, connector.Errore, Rifiuto) as ex:
            self._rispondi(422, {"errore": str(ex)})
        except urllib.error.URLError:
            self._rispondi(503, {"errore": i18n.t("programma.protezione_non_attiva")})
        except Exception as ex:   # noqa: BLE001
            self._rispondi(500, {"errore": f"{type(ex).__name__}: {ex}"})


def icona(server):
    """Icona vicino all'orologio. Se le librerie mancano il programma funziona lo stesso dalla pagina."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    def disegno(attiva):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        colore = (16, 122, 107, 255) if attiva else (140, 140, 140, 255)
        d.polygon([(32, 4), (58, 14), (58, 34), (32, 60), (6, 34), (6, 14)], fill=colore)
        d.line([(20, 32), (29, 41), (45, 23)], fill=(255, 255, 255, 255), width=6)
        return im

    def apri(*_):
        webbrowser.open(f"http://127.0.0.1:{PORTA_PANNELLO}/")

    def cambia(ic, _):
        SUP.ferma() if SUP.fase == "attiva" else SUP.avvia()

    def esci(ic, _):
        SUP.ferma()
        ic.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    def sugli_appunti(azione):
        def esegui(icona_, _):
            try:
                avvisa(clipboard.trasforma(azione, motore))
            except Exception:   # noqa: BLE001
                avvisa(i18n.t("programma.protezione_non_attiva"))
        return esegui

    ic = pystray.Icon("omissis", disegno(False), "Omissis", menu=pystray.Menu(
        # i testi sono funzioni: il menu segue la lingua scelta nelle Impostazioni senza riavviare il programma
        pystray.MenuItem(lambda _: i18n.t("icona.apri"), apri, default=True),
        pystray.MenuItem(lambda _: i18n.t("icona.maschera"), sugli_appunti("maschera")),
        pystray.MenuItem(lambda _: i18n.t("icona.ripristina"), sugli_appunti("ripristina")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda _: i18n.t("icona.ferma" if SUP.fase == "attiva" else "icona.avvia"), cambia),
        pystray.MenuItem(lambda _: i18n.t("icona.esci"), esci)))

    def aggiorna():
        ultima, avvisato = None, ""
        while ic.visible or ultima is None:
            if SUP.fase != ultima:
                ultima = SUP.fase
                ic.icon = disegno(ultima == "attiva")
                ic.title = i18n.t(f"icona.stato.{ultima if ultima in ('attiva', 'avvio', 'errore', 'modello') else 'ferma'}")
            agg = updates.STATO
            if agg["fase"] == "pronto" and avvisato != agg["versione"]:
                avvisato = agg["versione"]
                avvisa(i18n.t("icona.aggiornamento_pronto", v=avvisato))
            time.sleep(1)

    threading.Thread(target=aggiorna, daemon=True).start()

    def avvisa(messaggio):   # esito delle scorciatoie sugli appunti, come notifica di Windows
        try:
            ic.notify(messaggio, "Omissis")
        except Exception:   # noqa: BLE001
            pass

    clipboard.scorciatoie(motore, avvisa)
    return ic


def main():
    global SUP
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tray", dest="senza_icona", action="store_true")
    ap.add_argument("--no-browser", dest="senza_browser", action="store_true")
    ap.add_argument("--no-start", dest="non_avviare", action="store_true", help="apre il pannello senza avviare la protezione")
    ap.add_argument("--test", dest="prova", action="store_true", help="accetta anche il servizio finto in locale")
    a = ap.parse_args()
    DATI.mkdir(parents=True, exist_ok=True)
    if porta_aperta(PORTA_PANNELLO):   # gia' acceso: si apre solo il pannello
        print(f"Omissis è già acceso: apro il pannello su http://127.0.0.1:{PORTA_PANNELLO}/", flush=True)
        if not a.senza_browser:
            webbrowser.open(f"http://127.0.0.1:{PORTA_PANNELLO}/")
        return
    if updates.modalita() == "automatici":
        versione = updates.installa(automatico=True)   # un aggiornamento gia' scaricato e verificato si installa ora
        if versione:
            print(f"installo la versione {versione}: il programma si riapre da solo", flush=True)
            return
    if paths.INSTALLATA is not None and not LISTE.exists():   # le liste personali partono da quelle di esempio
        shutil.copytree(paths.cartella_modello() / "lists", LISTE)
    SUP = Supervisore(prova=a.prova)
    if a.prova:   # un'app di prova per il connettore: il Chromium usato dalle prove, senza estensione
        chrome = paths.browser_di_prova()
        if chrome:
            os.environ["OMISSIS_TEST"] = "1"
            connector.APP["prova"] = {"nome": "App di prova", "comando": str(chrome), "porta": 9560,
                                       "argomenti": ["--headless=new", "--no-first-run", f"--user-data-dir={DATI / 'test_app'}",
                                                     "about:blank"]}
    class Servizio(ThreadingHTTPServer):
        allow_reuse_address = False   # una seconda copia del programma deve accorgersi che la prima e' gia' accesa

    try:
        server = Servizio(("127.0.0.1", PORTA_PANNELLO), Gestore)
    except OSError:
        print(f"Omissis è già acceso: apro il pannello su http://127.0.0.1:{PORTA_PANNELLO}/", flush=True)
        if not a.senza_browser:
            webbrowser.open(f"http://127.0.0.1:{PORTA_PANNELLO}/")
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=updates.ciclo, daemon=True).start()
    if not a.non_avviare:
        SUP.avvia()
    indirizzo = f"http://127.0.0.1:{PORTA_PANNELLO}/"
    print(f"pannello su {indirizzo}", flush=True)
    if not a.senza_browser:
        webbrowser.open(indirizzo)
    try:
        global ICONA
        ICONA = ic = None if a.senza_icona else icona(server)
        if ic is not None:
            ic.run()
        else:
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        SUP.ferma()


if __name__ == "__main__":
    main()
