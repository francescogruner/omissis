# -*- coding: utf-8 -*-
"""Ponte tra il motore e l'estensione del browser.

L'estensione intercetta le richieste DENTRO la pagina (prima che vengano cifrate) e le passa qui:
il lavoro vero lo fanno gli stessi adattatori del proxy (restore.py), cosi' c'e' un solo posto
in cui si decide dove sta il testo e come si riscrive una risposta. Gira dentro engine.py.

  POST /bridge/status      politiche dei servizi (cosa proteggere, registrare, bloccare) e impostazioni che servono nella pagina
  POST /bridge/request     {url, method, kind, body}         -> {action: passthrough | replace | block, body}
  POST /bridge/text        {host, text}                      il testo nella casella di scrittura, prima dell'invio
  POST /bridge/prompt      {service, text}                   -> {action: allow | block, message, text}: il messaggio visto dall'hook
                                                             di un'app (Kimi), che puo' solo lasciarlo partire o fermarlo
  POST /bridge/attachment  {host, name, byte, data (base64)} -> la copia anonimizzata del file
  POST /bridge/open_up     {url, kind}                       -> {id} se la risposta va riscritta mentre arriva
  POST /bridge/chunk       {id, data (base64), end}          -> {data (base64)}
  POST /bridge/whole       {url, kind, text}                 -> {text}
  POST /bridge/values      {placeholder: [...]}              -> i valori veri (ripristino nel testo della pagina)
  POST /bridge/visit       {host}                            contatto con un servizio AI (Shadow AI)
  POST /bridge/websocket   {url}                             canale che l'estensione non sa leggere

Stesse regole del proxy: se il modello non risponde la richiesta viene bloccata; nel registro solo
conteggi e struttura.
"""
import base64
import collections
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import catalog
import i18n
import managed
import settings
import paths
import activity
import restore as R

MAX_BODY = 8_000_000
MAX_ATTACHMENT = 20_000_000
FILE_KINDS = {".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
             ".txt": "text/plain", ".md": "text/markdown", ".csv": "text/csv", ".json": "application/json", ".html": "text/html",
             ".htm": "text/html", ".xml": "application/xml"}


class _WithClient:
    """Il registro, con in piu' su ogni riga il programma che ha fatto la richiesta (se lo ha dichiarato)."""

    def __init__(self, log, locale):
        self._log, self._locale = log, locale

    def write(self, **entry):
        client = getattr(self._locale, "client", "")
        return self._log.write(**({**entry, "client": client} if client else entry))

    def __getattr__(self, name):
        return getattr(self._log, name)


class NotDone(Exception):
    """Un allegato che non si e' potuto anonimizzare; codice dice perche' (vedi documenti.Errore)."""

    def __init__(self, code=""):
        super().__init__(code)
        self.code = code
VERSION = 1


class Bridge:
    def __init__(self, engine):
        self.m = engine
        self.locale = threading.local()   # il programma (nome e versione) della richiesta in corso, per le righe del registro
        self.reg = _WithClient(activity.Log(), self.locale)
        self.recent_attachments = collections.deque(maxlen=40)   # (quando, servizio, peso) delle copie anonimizzate consegnate
        try:   # le librerie per leggere i documenti ci sono solo dove il programma e' un pacchetto unico: si guarda una volta
            import documents as documents
            self.documents = documents
        except ImportError:
            self.documents = None
        self.test = os.environ.get("OMISSIS_TEST") == "1"
        self.streams = {}        # id -> [flusso, servizio, percorso, ultimo uso]
        self.originals = {}     # valore -> segnaposto, per accorgersi di un valore che esce in chiaro altrove
        self.lock = threading.Lock()

    # ---------------------------------------------------------------- utilita'
    @staticmethod
    def _via(data):
        return "app desktop" if data.get("via") == "app" else "extension"

    def _service(self, url):
        """(adattatore, id del servizio, host, percorso) per un indirizzo; adattatore None = non si tocca."""
        u = urllib.parse.urlsplit(str(url))
        host, path = (u.hostname or "").lower(), u.path + ("?" + u.query if u.query else "")
        s = catalog.find(host)
        if s is not None:
            guarded = s["adapter"] and settings.policy(s) == "protect"
            return (R.CLASSES[s["adapter"]]() if guarded else None), s["id"], host, path
        if self.test and host in ("localhost", "127.0.0.1"):
            ad = R.for_test(path)
            return ad, (ad.name if ad else None), host, path
        return None, None, host, path

    def _box(self, host):
        """Id del servizio di cui proteggere la casella e gli allegati, altrimenti None. Vale anche per i servizi
        le cui richieste non si leggono ma la casella si' (box nel catalogo)."""
        ad, service, _, _ = self._service(f"https://{host}/generic/box")
        if ad is not None:
            return service
        s = catalog.find(host)
        return s["id"] if s is not None and s["box"] and settings.policy(s) == "protect" else None

    def handle(self, action, data):
        f = {"status": self.status, "request": self.request, "text": self.text, "prompt": self.prompt, "open_up": self.open_up, "chunk": self.chunk, "whole": self.whole,
             "values": self.values, "visit": self.visit, "websocket": self.websocket, "attachment": self.attachment}.get(action)
        if f is None:
            return None
        client = data.get("client")
        self.locale.client = re.sub(r"[^\w .()\[\]/-]", "", str(client))[:60] if isinstance(client, str) else ""
        return f(data)

    # ---------------------------------------------------------------- politiche
    def status(self, data):
        cfg = settings.read()
        # del radar all'estensione interessano solo i servizi da bloccare: degli altri non puo' fare nulla
        # servizi la cui regola e' imposta da chi amministra il PC: li' la sospensione dalla finestrella dell'estensione non vale.
        # Dove e' stabilito che la protezione non si spenga (always_on) non vale su nessun servizio
        fixed, always = set(settings.locked()["policies"]), cfg["always_on"]
        services = [{"id": s["id"], "name": s["name"], "domains": s["domains"], "policy": settings.policy(s, cfg),
                    "readable": bool(s["adapter"]), **({"box": True} if s["box"] else {}), **({"radar": True} if s["radar"] else {}), **({"locked": True} if always or s["id"] in fixed else {}),
                    **catalog.page(s["id"])}
                   for s in catalog.SERVICES if not s["radar"] or settings.policy(s, cfg) == "block"]
        if self.test:   # il servizio finto non e' nel catalogo: nelle prove lo si impone nominandolo tra le regole imposte
            raw = managed.read().get("policies")
            services.append({"id": "test", "name": "Servizio finto", "domains": ["localhost"], "policy": "protect", "readable": True,
                             **({"locked": True} if always or (isinstance(raw, dict) and "test" in raw) else {}), **catalog.page("test")})
        return {"version": VERSION, "restore": bool(cfg["restore"]), "block_files": bool(cfg["block_files"]),
                "box": bool(cfg.get("box", True)), "attachments": bool(cfg.get("attachments", True)), "services": services}

    def visit(self, data):
        host = str(data.get("host", "")).lower()
        s = catalog.find(host)
        if s is None:
            return {}
        pol = settings.policy(s)
        if pol != "ignore":
            self.reg.contact(s["id"], host, "blocked" if pol == "block" else
                              "guarded" if pol == "protect" and catalog.protectable(s, browser=True) else "not_protected")
        return {"service": s["id"], "policy": pol}

    def websocket(self, data):
        ad, service, _, path = self._service(data.get("url", ""))
        if ad is not None:
            self.reg.write(service=service, via=self._via(data), path=activity.clean_path(path),
                            event="websocket_not_covered")
        return {}

    # ---------------------------------------------------------------- richiesta
    def request(self, data):
        ad, service, _, path = self._service(data.get("url", ""))
        if ad is None:
            return {"action": "passthrough"}
        cfg = settings.read()
        kind, body = str(data.get("kind") or ""), data.get("body")
        # "rete": secondo controllo fatto dal connettore subito prima dell'invio. Di norma la pagina ha gia' sostituito
        # tutto: nel registro va solo cio' che questo controllo ha dovuto sostituire o bloccare.
        network = bool(data.get("network"))
        entry = {"service": service, "via": self._via(data), "method": str(data.get("method", "POST")),
                "path": activity.clean_path(path),
                "byte": len(body.encode("utf-8")) if isinstance(body, str) else int(data.get("byte") or 0)}
        if data.get("file") or "multipart/" in kind or "octet-stream" in kind or re.search(r"(?i)upload|/files?(/|$)", path):
            if self._already_anonymized(service, entry["byte"]):   # e' la copia che abbiamo appena preparato noi: puo' partire
                return {"action": "passthrough"}
            if not network or cfg["block_files"]:
                self.reg.write(**entry, event="file_blocked" if cfg["block_files"] else "file_not_masked")
            return {"action": "block", "reason": "file"} if cfg["block_files"] else {"action": "passthrough"}
        if not isinstance(body, str):
            if entry["byte"] > 200 and not network:
                self.reg.write(**entry, event="body_not_read")
            return {"action": "passthrough"}
        if not body or len(body) > MAX_BODY:
            return {"action": "passthrough"}
        if "json" not in kind and "x-www-form-urlencoded" not in kind and body.lstrip()[:1] in ("{", "["):
            kind = "application/json"   # molte pagine mandano JSON senza dichiararlo
        opened = ad.request(path, kind, body)
        if opened is None:
            return {"action": "passthrough"}
        ref, reassemble, parsed = opened
        ref = [(c, k) for c, k in ref if c[k].strip()]
        outcome_ext = {"action": "passthrough"}
        if ref:
            originals = [c[k] for c, k in ref]
            try:
                outcome = self.m.mask(originals)
            except Exception as ex:   # noqa: BLE001  (mai inoltrare in chiaro)
                self.reg.write(**entry, event="blocked_model_silent", error=type(ex).__name__)
                return {"action": "block", "reason": "engine"}
            with self.lock:
                for seg, val in outcome["mapping"].items():
                    if len(val) >= 5:
                        self.originals[val] = seg
                while len(self.originals) > 20000:
                    self.originals.pop(next(iter(self.originals)))
            entry.update(event="masked", fields=len(ref), characters=sum(len(t) for t in outcome["texts"]),
                        replacements=outcome["counts"], ms=outcome["ms"])
            if outcome["texts"] != originals:   # se non c'e' nulla da sostituire la richiesta resta com'e'
                for (c, k), fresh in zip(ref, outcome["texts"]):
                    c[k] = fresh
                body = reassemble()
                outcome_ext = {"action": "replace", "body": body, "replacements": sum(outcome["counts"].values())}
        else:
            entry.update(event="no_text_field", structure=activity.shape(parsed))
        with self.lock:
            outside = sum(1 for v in self.originals if v in body)
        if outside:
            entry["VALUES_IN_CLEAR"] = outside
            entry.setdefault("structure", activity.shape(parsed))
        if network:
            if outcome_ext["action"] != "replace" and not outside:
                return outcome_ext
            entry["layer"] = "network"   # la pagina non l'aveva fatto: l'ha fermato il controllo prima dell'invio
        self.reg.write(**entry)
        return outcome_ext

    def text(self, data):
        """Il testo della casella di scrittura, sostituito prima che l'app lo legga (dove le richieste non si vedono)."""
        host, t = str(data.get("host", "")).lower(), data.get("text")
        service = self._box(host)
        if service is None or not isinstance(t, str) or not t.strip():
            return {"action": "passthrough"}
        entry = {"service": service, "via": self._via(data), "method": "box", "path": "(casella di scrittura)", "byte": len(t.encode("utf-8"))}
        try:
            outcome = self.m.mask([t])
        except Exception as ex:   # noqa: BLE001  (mai lasciar partire in chiaro)
            self.reg.write(**entry, event="blocked_model_silent", error=type(ex).__name__)
            return {"action": "block", "reason": "engine"}
        self.reg.write(**entry, event="masked", fields=1, characters=len(outcome["texts"][0]), replacements=outcome["counts"], ms=outcome["ms"])
        if outcome["texts"][0] == t:
            return {"action": "passthrough"}
        return {"action": "replace", "text": outcome["texts"][0], "replacements": sum(outcome["counts"].values())}

    def prompt(self, data):
        """Un messaggio che un'app sta per mandare, visto da un suo hook (Kimi: evento UserPromptSubmit del suo sistema di
        plugin). Un hook non puo' riscrivere il messaggio, solo lasciarlo partire o fermarlo: dove il servizio e' su
        «Proteggi» e c'e' qualcosa da sostituire il messaggio viene fermato, e torna la versione protetta, che l'hook mette
        negli appunti perche' chi scrive la incolli. Incollata, non ha piu' nulla da sostituire e parte."""
        s, t = catalog.PER_ID.get(str(data.get("service", ""))), data.get("text")
        if s is None or not isinstance(t, str) or not t.strip():
            return {"action": "allow"}
        pol, host = settings.policy(s), s["domains"][0]
        # la regola torna sempre: l'hook se la ricorda, per sapere che cosa fare il giorno che Omissis non risponde
        if pol == "block":
            self.reg.contact(s["id"], host, "blocked")
            return {"action": "block", "policy": pol, "message": i18n.t("hook.service_blocked", name=s["name"])}
        if pol == "record":
            self.reg.contact(s["id"], host, "not_protected")
        if pol != "protect":
            return {"action": "allow", "policy": pol}
        entry = {"service": s["id"], "via": "app desktop", "method": "hook", "path": "(messaggio)", "byte": len(t.encode("utf-8"))}
        try:
            outcome = self.m.mask([t])
        except Exception as ex:   # noqa: BLE001  (mai lasciar partire in chiaro)
            self.reg.write(**entry, event="blocked_model_silent", error=type(ex).__name__)
            return {"action": "block", "policy": pol, "message": i18n.t("hook.engine")}
        self.reg.write(**entry, event="masked", fields=1, characters=len(outcome["texts"][0]), replacements=outcome["counts"], ms=outcome["ms"])
        if outcome["texts"][0] == t:
            return {"action": "allow", "policy": pol}
        n = sum(outcome["counts"].values())
        return {"action": "block", "policy": pol, "text": outcome["texts"][0], "replacements": n,
                "message": i18n.t("hook.held", n=n), "message_copied": i18n.t("hook.held.copied", n=n)}

    # ---------------------------------------------------------------- allegati
    def _already_anonymized(self, service, weight):
        """Il caricamento che sta partendo e' fatto di copie appena anonimizzate? Si riconoscono dal peso: quello di una
        copia, o la somma delle ultime (piu' file nello stesso invio)."""
        stamp, tally = time.time(), 0
        for when, di, byte in reversed(self.recent_attachments):
            if stamp - when > 180:
                break
            if di == service:
                tally += byte
                if weight in (byte, tally):
                    return True
        return False

    def _anonymize_file(self, name, raw):
        """(nome nuovo, contenuto, conteggi). Leggere Word, Excel, PDF e immagini e' un lavoro del programma di gestione:
        se questo processo ne ha le librerie lo fa da se', altrimenti lo chiede al pannello sullo stesso PC."""
        documents = self.documents
        if documents is not None:
            try:
                return documents.work_on(name, raw, "anonymize")
            except documents.Error as ex:
                raise NotDone(ex.code) from None
        token = (paths.DATA / "token.txt").read_text(encoding="utf-8").strip()
        req = urllib.request.Request(f"http://127.0.0.1:{paths.PANEL_PORT}/internal/attachment",
                                      data=json.dumps({"name": name, "data": base64.b64encode(raw).decode("ascii")}).encode("utf-8"),
                                      headers={"Content-Type": "application/json", "X-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as ex:
            try:
                code = json.loads(ex.read().decode("utf-8")).get("code", "")
            except ValueError:
                code = ""
            raise NotDone(code) from None
        except (urllib.error.URLError, OSError, ValueError):
            raise NotDone("panel") from None
        return d["name"], base64.b64decode(d["data"]), d["counts"]

    def attachment(self, data):
        """Un file che l'utente sta per allegare a un messaggio (scelto, trascinato o incollato): la pagina ricevera' la copia
        anonimizzata. Cio' che non si riesce ad anonimizzare segue la scelta «blocca i file»; un'immagine o un PDF senza
        testo non ha nulla da sostituire e passa; se la protezione non risponde non parte nulla."""
        service = self._box(str(data.get("host", "")).lower())
        if service is None:
            return {"action": "passthrough"}
        cfg = settings.read()
        name = Path(str(data.get("name") or "file")).name[:200]
        est = Path(name).suffix.lower()
        entry = {"service": service, "via": self._via(data), "method": "attachment", "path": f"(allegato {est or 'senza estensione'})",
                "byte": int(data.get("byte") or 0)}

        def not_anonymized():
            self.reg.write(**entry, event="file_blocked" if cfg["block_files"] else "file_not_masked")
            return {"action": "block", "reason": "file"} if cfg["block_files"] else {"action": "passthrough"}

        if not cfg.get("attachments", True):
            return not_anonymized()
        try:
            raw = base64.b64decode(data.get("data") or "")
        except ValueError:
            raw = b""
        if not raw or len(raw) > MAX_ATTACHMENT:
            return not_anonymized()
        entry["byte"] = len(raw)
        start = time.time()
        try:
            new_name, fresh, counts = self._anonymize_file(name, raw)
        except NotDone as ex:
            if ex.code == "without_text":
                self.reg.write(**entry, event="attachment_without_text")
                return {"action": "passthrough"}
            if ex.code == "protection":
                self.reg.write(**entry, event="blocked_engine_unreachable")
                return {"action": "block", "reason": "engine"}
            return not_anonymized()
        except Exception as ex:   # noqa: BLE001  (un file che manda in errore la lettura non deve partire in chiaro per sbaglio)
            entry["error"] = type(ex).__name__
            return not_anonymized()
        self.recent_attachments.append((time.time(), service, len(fresh)))
        replacements = {k: n for k, n in counts.items() if k != "pages_read" and n}
        self.reg.write(**entry, event="attachment_masked", replacements=replacements, ms=round((time.time() - start) * 1000))
        new_est = Path(new_name).suffix.lower()
        return {"action": "replace", "name": new_name, "kind": FILE_KINDS.get(new_est, "application/octet-stream"),
                "data": base64.b64encode(fresh).decode("ascii"), "replacements": sum(replacements.values()), "converted": new_est != est}

    # ---------------------------------------------------------------- risposta
    def open_up(self, data):
        if not settings.read()["restore"]:
            return {"id": None}
        ad, service, _, path = self._service(data.get("url", ""))
        if ad is None or not ad.in_streaming(str(data.get("kind") or ""), path):
            return {"id": None}
        ident, stamp = secrets.token_hex(8), time.time()
        with self.lock:
            for k in [k for k, v in self.streams.items() if stamp - v[3] > 1800]:   # risposte interrotte a meta'
                del self.streams[k]
            self.streams[ident] = [ad.stream(self.m.vault.value), service, activity.clean_path(path), stamp, self._via(data)]
        return {"id": ident}

    def chunk(self, data):
        ident, end = str(data.get("id", "")), bool(data.get("end"))
        with self.lock:
            entry = self.streams.pop(ident, None) if end else self.streams.get(ident)
        if entry is None:   # flusso sconosciuto: i dati tornano come sono (restano i segnaposto, nessun danno)
            return {"data": data.get("data") or "", "lost": True}
        stream, service, path, _, via = entry
        entry[3] = time.time()
        raw = base64.b64decode(data.get("data") or "")
        out = b"".join(stream(raw)) if raw else b""
        if end:
            out += b"".join(stream(b""))
            if stream.restored:
                self.reg.write(service=service, via=via, path=path, event="response_streaming",
                                restored=stream.restored)
        return {"data": base64.b64encode(out).decode("ascii")}

    def whole(self, data):
        text = data.get("text")
        if not isinstance(text, str) or not settings.read()["restore"]:
            return {}
        ad, service, _, path = self._service(data.get("url", ""))
        found_items = len(R.RX_PLACEHOLDER.findall(text))
        if ad is None or not found_items or len(text) > MAX_BODY:
            return {}
        fresh = ad.whole(str(data.get("kind") or ""), text, self.m.vault.value)
        remaining = len(R.RX_PLACEHOLDER.findall(fresh))
        if found_items > remaining:
            self.reg.write(service=service, via=self._via(data), path=activity.clean_path(path), event="response",
                            restored=found_items - remaining)
        return {"text": fresh}

    def values(self, data):
        if not settings.read()["restore"]:
            return {"mapping": {}}
        return self.m.values([str(s) for s in (data.get("placeholder") or [])[:500]])
