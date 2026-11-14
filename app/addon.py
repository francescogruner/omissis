# -*- coding: utf-8 -*-
"""Addon di mitmproxy: maschera i dati sensibili nelle richieste ai servizi di chat e li
ripristina nelle risposte, cosi' l'utente vede il testo originale e il servizio solo segnaposto.
Registra inoltre i contatti verso i servizi AI del catalogo (Shadow AI) e applica le politiche
scelte nel pannello: proteggi | registra | blocca | ignora.

Regole di sicurezza:
  - se il motore non risponde la richiesta viene BLOCCATA (503), mai inoltrata in chiaro;
  - nel registro (data\\activity.jsonl) finiscono solo conteggi e nomi dei campi, mai i testi;
  - i file caricati (PDF, immagini) NON vengono mascherati: sono segnalati nel registro e,
    se impostato, bloccati.

Le impostazioni si leggono da data\\settings.json a ogni richiesta (vedi settings.py).
OMISSIS_TEST=1 accetta anche il servizio finto in locale.
"""
import asyncio
import json
import os
import re
import urllib.request
from pathlib import Path

from mitmproxy import http

import catalog
import settings
import paths
import activity
import restore as R
from activity import shape

HERE = Path(__file__).resolve().parent
ENGINE = os.environ.get("OMISSIS_ENGINE_URL", "http://127.0.0.1:8765")
TEST = os.environ.get("OMISSIS_TEST") == "1"
MAX_BODY = 8_000_000


def engine(path, data):
    token = (paths.DATA / "token.txt").read_text(encoding="utf-8").strip()
    req = urllib.request.Request(ENGINE + path, data=json.dumps(data).encode("utf-8"),
                                  headers={"Content-Type": "application/json", "X-Token": token})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


class MspPii:
    def __init__(self):
        self.values = {}        # segnaposto -> valore (cache; i valori restano in memoria e nell'archivio del motore)
        self.absent = set()
        self.originals = {}     # valore -> segnaposto, per accorgersi di un valore che esce in chiaro altrove
        self.reg = activity.Log()

    # ---------------------------------------------------------------- utilita'
    def write(self, **entry):
        entry = self.reg.write(**entry)
        extra = ", ".join(f"{k} {v}" for k, v in (entry.get("replacements") or {}).items())
        if "restored" in entry:
            extra = f"{entry['restored']} segnaposto riportati al valore originale"
        if "VALUES_IN_CLEAR" in entry:
            extra += f" | ATTENZIONE: {entry['VALUES_IN_CLEAR']} valori già mascherati compaiono in chiaro"
        print(f"{entry['stamp'][11:]}  {entry.get('service', ''):14} {entry.get('event', '')}  {entry.get('path', '')[:60]}  {extra}", flush=True)

    def contact(self, service, host, outcome):
        self.reg.contact(service["id"], host, outcome)

    def preload(self, placeholder):
        missing = [s for s in set(placeholder) if s not in self.values and s not in self.absent]
        if missing:
            try:
                found_items = engine("/values", {"placeholder": missing})["mapping"]
            except Exception:   # noqa: BLE001  (senza motore i segnaposto restano tali: nessun danno)
                return
            self.values.update(found_items)
            self.absent.update(s for s in missing if s not in found_items)

    def search(self, placeholder):
        if placeholder not in self.values and placeholder not in self.absent:
            self.preload([placeholder])
        return self.values.get(placeholder)

    @staticmethod
    def path(flow):
        return activity.clean_path(flow.request.path)

    def adapter(self, flow):
        """(adattatore, nome del servizio) per una richiesta da proteggere, altrimenti (None, None)."""
        host = flow.request.pretty_host
        s = catalog.find(host)
        if s is not None:
            if s["adapter"] and settings.policy(s) == "protect":
                return R.CLASSES[s["adapter"]](), s["id"]
            return None, None
        if TEST and host in ("127.0.0.1", "localhost"):
            ad = R.for_test(flow.request.path)
            return ad, (ad.name if ad else None)
        return None, None

    async def mask(self, texts):
        outcome = await asyncio.to_thread(engine, "/mask", {"texts": texts})
        self.values.update(outcome["mapping"])
        for seg, val in outcome["mapping"].items():
            if len(val) >= 5:
                self.originals[val] = seg
        while len(self.originals) > 20000:
            self.originals.pop(next(iter(self.originals)))
        return outcome

    # ---------------------------------------------------------------- contatti verso i servizi AI
    def http_connect(self, flow: http.HTTPFlow):
        s = catalog.find(flow.request.host)
        if s is None:
            return
        pol = settings.policy(s)
        if pol == "ignore":
            return
        if pol == "block":
            flow.response = http.Response.make(403, f"Omissis: {s['name']} è bloccato dalle impostazioni".encode("utf-8"),
                                               {"content-type": "text/plain; charset=utf-8"})
            self.contact(s, flow.request.host, "blocked")
            return
        self.contact(s, flow.request.host, "guarded" if pol == "protect" and s["adapter"] else "not_protected")

    # ---------------------------------------------------------------- richiesta
    async def request(self, flow: http.HTTPFlow):
        ad, service = self.adapter(flow)
        if ad is None:
            return
        flow.metadata["msp"], flow.metadata["msp_service"] = ad, service
        cfg = settings.read()
        rq = flow.request
        if rq.method not in ("POST", "PUT", "PATCH") or not rq.raw_content:
            return
        kind = rq.headers.get("content-type", "")
        entry = {"service": service, "method": rq.method, "path": self.path(flow), "byte": len(rq.raw_content),
                "client": activity.client_from_ua(rq.headers.get("User-Agent", ""))}
        if "multipart/" in kind or "octet-stream" in kind or re.search(r"(?i)upload|/files?(/|$)", rq.path):
            if cfg["block_files"]:
                flow.response = http.Response.make(403, b'{"error":"Omissis: caricamento di file bloccato"}',
                                                   {"content-type": "application/json"})
            self.write(**entry, event="file_blocked" if cfg["block_files"] else "file_not_masked")
            return
        if len(rq.raw_content) > MAX_BODY:
            return
        opened = ad.request(rq.path, kind, rq.get_text(strict=False) or "")
        if opened is None:
            return
        ref, reassemble, body = opened
        ref = [(c, k) for c, k in ref if c[k].strip()]
        if ref:
            try:
                outcome = await self.mask([c[k] for c, k in ref])
            except Exception as ex:   # noqa: BLE001
                flow.response = http.Response.make(
                    503, json.dumps({"error": {"type": "omissis", "message": "Omissis: motore di protezione non raggiungibile, "
                                                                           "richiesta bloccata per non inviare dati in chiaro"}}),
                    {"content-type": "application/json"})
                self.write(**entry, event="blocked_engine_unreachable", error=type(ex).__name__)
                return
            for (c, k), fresh in zip(ref, outcome["texts"]):
                c[k] = fresh
            rq.set_text(reassemble())
            rq.headers["accept-encoding"] = "identity"   # la risposta in streaming deve arrivare non compressa
            entry.update(event="masked", fields=len(ref), characters=sum(len(t) for t in outcome["texts"]),
                        replacements=outcome["counts"], ms=outcome["ms"])
        else:
            entry.update(event="no_text_field", structure=shape(body))
        # controllo di tenuta: un valore gia' mascherato compare in chiaro in questa richiesta?
        text = rq.get_text(strict=False) or ""
        outside = sum(1 for v in self.originals if v in text)
        if outside:
            entry["VALUES_IN_CLEAR"] = outside
            entry.setdefault("structure", shape(body))
        self.write(**entry)

    # ---------------------------------------------------------------- risposta
    def responseheaders(self, flow: http.HTTPFlow):
        ad = flow.metadata.get("msp")
        if ad is None or not settings.read()["restore"]:
            return
        rs = flow.response
        if ad.in_streaming(rs.headers.get("content-type", ""), flow.request.path) and \
                rs.headers.get("content-encoding", "identity") == "identity":
            stream = ad.stream(self.search, self.preload)
            flow.metadata["msp_stream"] = stream
            rs.stream = stream

    def response(self, flow: http.HTTPFlow):
        ad = flow.metadata.get("msp")
        if ad is None or not settings.read()["restore"]:
            return
        rs, service = flow.response, flow.metadata.get("msp_service")
        stream = flow.metadata.get("msp_stream")
        if stream is not None:
            if stream.restored:
                self.write(service=service, path=self.path(flow), event="response_streaming", restored=stream.restored)
            return
        kind = rs.headers.get("content-type", "")
        if not rs.raw_content or len(rs.raw_content) > MAX_BODY or not any(x in kind for x in ("json", "event-stream", "text/plain")):
            return
        text = rs.get_text(strict=False) or ""
        found_items = [m.group() for m in R.RX_PLACEHOLDER.finditer(text)]
        if not found_items:
            return
        self.preload(found_items)
        rs.set_text(ad.whole(kind, text, self.search))
        self.write(service=service, path=self.path(flow), event="response", restored=len(found_items))

    # ---------------------------------------------------------------- websocket (es. Copilot)
    def websocket_message(self, flow: http.HTTPFlow):
        ad = flow.metadata.get("msp")
        msg = flow.websocket.messages[-1]
        if ad is None or not msg.is_text:
            return
        service = flow.metadata.get("msp_service")
        try:
            obj = json.loads(msg.content.decode("utf-8"))
        except ValueError:
            obj = None
        if msg.from_client:
            ref = [(c, k) for c, k in ad.fields(flow.request.path, obj) if c[k].strip()] if obj is not None else []
            if not ref:
                if len(msg.content) > 200:
                    self.write(service=service, path=self.path(flow), event="websocket_no_text_field",
                                byte=len(msg.content), structure=shape(obj) if obj is not None else "non JSON")
                return
            try:
                outcome = engine("/mask", {"texts": [c[k] for c, k in ref]})
            except Exception as ex:   # noqa: BLE001
                msg.drop()
                self.write(service=service, path=self.path(flow), event="blocked_websocket_engine_unreachable",
                            error=type(ex).__name__)
                return
            self.values.update(outcome["mapping"])
            for (c, k), fresh in zip(ref, outcome["texts"]):
                c[k] = fresh
            msg.content = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.write(service=service, path=self.path(flow), event="masked", fields=len(ref), via="websocket",
                        replacements=outcome["counts"], ms=outcome["ms"])
        elif settings.read()["restore"] and (b"[" in msg.content or flow.metadata.get("msp_ws_waiting")):
            leaves = flow.metadata.setdefault("msp_ws", R.Leaves(self.search))
            self.preload([m.group() for m in R.RX_PLACEHOLDER.finditer(msg.content.decode("utf-8", errors="replace"))])
            if obj is None:
                msg.content = R.restore(msg.content.decode("utf-8", errors="replace"), self.search).encode("utf-8")
            else:
                leaves.changed = False
                fresh = leaves.apply(obj)
                if leaves.changed:
                    msg.content = json.dumps(fresh, ensure_ascii=False).encode("utf-8")
            flow.metadata["msp_ws_waiting"] = leaves.waiting


addons = [MspPii()]
