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
  - le chiamate in formato binario (protobuf) dei servizi che le usano vengono lette senza schema (wire.py) e i testi
    sostituiti come negli altri formati; una che non si riesce a leggere non passa in silenzio: finisce nel registro
    con la sua forma e, se l'adattatore del servizio lo chiede, viene fermata invece di partire in chiaro;
  - nelle pagine dei servizi che lo chiedono (oggi claude.ai, per la sua app) il proxy mette il codice della casella di
    scrittura dell'estensione (inpage.py): il testo viene sostituito prima ancora che l'app lo legga.

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
import inpage
import wire
from activity import shape, written

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


# codifiche binarie delle chiamate ai servizi: gli adattatori leggono JSON, queste no
RX_BINARY = re.compile(r"(?i)proto|grpc|msgpack|cbor|thrift")


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
        if flow.request.path.startswith(inpage.PREFIX):   # una chiamata del codice messo nella pagina: risponde il proxy
            await self.page_call(flow)
            return
        ad, service = self.adapter(flow)
        if ad is None:
            return
        flow.metadata["msp"], flow.metadata["msp_service"] = ad, service
        cfg = settings.read()
        rq = flow.request
        # chi sta passando da qui (per esempio l'app di Claude dietro il proxy del sistema): il pannello lo mostra
        self.reg.seen(service, activity.client_from_ua(rq.headers.get("User-Agent", "")))
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
            # Un corpo che l'adattatore non sa leggere. Se e' una chiamata in formato binario (protobuf: dal novembre 2026
            # claude.ai manda cosi' i messaggi, ConversationService/PerformAction) dentro puo' esserci il testo di chi
            # scrive: non deve passare in silenzio. Dove l'adattatore lo chiede (RPC) si legge senza schema e i testi si
            # sostituiscono; se non si riesce, nel registro va la forma (mai i valori) e, se l'adattatore lo chiede
            # (UNREADABLE), la richiesta viene fermata invece di partire in chiaro.
            if RX_BINARY.search(kind) and len(rq.raw_content) > 8:
                rpc = getattr(ad, "RPC", None)
                if rpc is not None and rpc.search(rq.path) and await self.rpc(flow, entry, kind):
                    return
                message = None
                if len(rq.raw_content) <= 400_000:
                    message = wire.unwrap(rq.get_content(strict=False) or b"", kind, rq.headers.get("connect-content-encoding", ""))[1]
                form = wire.shape(message) if message else None
                stop, quiet = getattr(ad, "UNREADABLE", None), getattr(ad, "QUIET", None)
                blocked = bool(stop is not None and stop.search(rq.path))
                if not blocked and quiet is not None and quiet.search(rq.path):
                    return   # chiamate di servizio (nell'app di Claude: le sessioni di codice), fuori dal registro come le altre
                if blocked:
                    flow.response = http.Response.make(
                        415, json.dumps({"error": {"type": "omissis", "message": "Omissis: richiesta in un formato che non so leggere, "
                                                                               "fermata per non inviare dati in chiaro"}}),
                        {"content-type": "application/json"})
                self.write(**entry, event="blocked_rpc_not_read" if blocked else "rpc_not_read",
                           kind=kind.split(";")[0].strip()[:60], structure=form if form is not None else "non letto")
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
        # misure d'uso e controlli del sito non sono messaggi: nel registro direbbero «formato non letto». Restano fuori,
        # a meno che dentro non ci sia un valore in chiaro. Lo stesso vale per ogni richiesta in cui non c'e' nulla di
        # scritto (la lingua, un orario, un contatore): le app ne aggiungono a ogni versione
        quiet = getattr(ad, "QUIET", None)
        if entry.get("event") == "no_text_field" and not outside and (not written(body) or (quiet is not None and quiet.search(rq.path))):
            return
        self.write(**entry)

    async def rpc(self, flow, entry, kind):
        """Una chiamata in protobuf (protocollo Connect) verso un servizio protetto: i testi che puo' aver scritto una
        persona passano dal motore come negli altri formati, e il messaggio viene ricomposto con le lunghezze giuste.
        Se nella pagina ha gia' lavorato la casella (inpage.py) qui arrivano solo segnaposto e non cambia nulla.
        True se la chiamata e' stata letta (anche quando non c'era nulla da sostituire), False se non si legge."""
        rq = flow.request
        if len(rq.raw_content) > MAX_BODY:
            return False
        enveloped, message = wire.unwrap(rq.get_content(strict=False) or b"", kind, rq.headers.get("connect-content-encoding", ""))
        found = wire.texts(message) if message else None
        if found is None:
            return False
        chosen = [x for x in dict.fromkeys(found) if wire.prose(x)]
        if not chosen:
            return True
        try:
            outcome = await self.mask(chosen)
        except Exception as ex:   # noqa: BLE001
            flow.response = http.Response.make(
                503, json.dumps({"error": {"type": "omissis", "message": "Omissis: motore di protezione non raggiungibile, "
                                                                       "richiesta bloccata per non inviare dati in chiaro"}}),
                {"content-type": "application/json"})
            self.write(**entry, event="blocked_engine_unreachable", error=type(ex).__name__)
            return True
        changes = {old: new for old, new in zip(chosen, outcome["texts"]) if new != old}
        if changes:
            rq.set_content(wire.wrap(enveloped, wire.rebuild(message, changes)))
            listing = wire.places(message) or []
            where = [f"{place}:{len(text)}" for place, text in listing if text in changes][:30]
            # e dove stavano i testi rimasti com'erano (il messaggio gia' sostituito dalla casella, per esempio)
            kept = [f"{place}:{len(text)}" for place, text in listing if text not in changes and wire.prose(text)][:12]
            self.write(**entry, event="masked", fields=len(changes), characters=sum(len(x) for x in changes.values()),
                       replacements=outcome["counts"], ms=outcome["ms"], kind="protobuf", where=where, kept=kept, texts=len(chosen))
        return True

    # ---------------------------------------------------------------- il codice della casella, portato nella pagina
    async def page_call(self, flow):
        """Una chiamata del codice che il proxy ha messo nella pagina (inpage.py): trova risposta qui e non parte MAI
        verso il sito, nemmeno se il servizio non e' (piu') tra quelli protetti."""
        rq = flow.request

        def answer(code, data):
            flow.response = http.Response.make(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                                               {"content-type": "application/json", "cache-control": "no-store", "x-omissis": "1"})
        try:
            ad, service = self.adapter(flow)
            if ad is None or not getattr(ad, "PAGE", False):
                return answer(404, {})
            what = rq.path[len(inpage.PREFIX):].split("?")[0]
            if what == "here":   # «chi risponde?»: la pagina lo chiede senza chiave, prima di mandare qualunque cosa
                return answer(200, {})
            if rq.headers.get("x-omissis-key", "") != inpage.key():
                return answer(403, {})
            client = activity.client_from_ua(rq.headers.get("User-Agent", ""))
            if rq.headers.get("x-omissis-hello") == "1":   # il codice si presenta appena parte: gira davvero dentro quel programma
                self.write(service=service, via="app desktop", client=client, event="page_active", path="(codice nella pagina)")
            if what == "status":
                return answer(200, await asyncio.to_thread(inpage.status, ENGINE, client, TEST))
            if what == "call" and rq.method == "POST":
                m = json.loads(rq.get_text(strict=False) or "{}").get("m")
                return answer(200, await asyncio.to_thread(inpage.handle, ENGINE, m, client))
            answer(404, {})
        except Exception:   # noqa: BLE001
            answer(500, {})

    async def page_insert(self, flow):
        """Mette in cima alla pagina di un servizio protetto il codice della casella di scrittura."""
        rs, service = flow.response, flow.metadata.get("msp_service")
        client = activity.client_from_ua(flow.request.headers.get("User-Agent", ""))
        try:
            if not rs.raw_content or len(rs.raw_content) > inpage.MAX_PAGE:
                return
            html = rs.get_text(strict=False) or ""
            if "<" not in html[:4000]:
                return
            state = await asyncio.to_thread(inpage.status, ENGINE, client, TEST)
            page, digest = inpage.inject(html, inpage.source(state))
            rs.set_text(page)
            rules = rs.headers.get_all("content-security-policy")
            if rules:
                rs.headers.set_all("content-security-policy", [inpage.allow(r, digest) for r in rules])
            rs.headers["cache-control"] = "no-store"
            self.write(service=service, path=self.path(flow), client=client, event="page_prepared")
        except Exception as ex:   # noqa: BLE001  (la pagina passa com'era: resta la barriera del proxy)
            self.write(service=service, path=self.path(flow), client=client, event="page_not_prepared", error=type(ex).__name__)

    # ---------------------------------------------------------------- risposta
    def responseheaders(self, flow: http.HTTPFlow):
        """Decide come consegnare la risposta. Una risposta che resta aperta (un canale di eventi) non va mai trattenuta:
        mitmproxy aspetterebbe la fine prima di consegnarla, e l'app resterebbe senza connessione. Visto il 21/11/2026 con
        l'app di Claude dietro il proxy del sistema: il suo canale di eventi arriva compresso, non veniva consegnato e
        l'app diceva «Connessione non riuscita»."""
        rs, ad = flow.response, flow.metadata.get("msp")
        kind = rs.headers.get("content-type", "")
        coding = rs.headers.get("content-encoding", "identity").strip().lower() or "identity"
        # la pagina di un servizio che vuole il codice della casella: resta intera, response() ce lo mette in cima
        if (ad is not None and getattr(ad, "PAGE", False) and flow.request.method == "GET" and rs.status_code == 200
                and "text/html" in kind and flow.request.headers.get("sec-fetch-dest", "document") == "document"):
            flow.metadata["msp_page"] = True
            return
        # una zona del servizio dove le risposte non si toccano (in claude.ai le sessioni di codice: li' un segnaposto
        # scritto in un programma o in un registro deve restare com'e')
        outside = getattr(ad, "OUTSIDE", None) if ad is not None else None
        if outside is not None and outside.search(flow.request.path):
            flow.metadata["msp"] = None
            rs.stream = True
            return
        if ad is not None and settings.read()["restore"] and ad.in_streaming(kind, flow.request.path):
            stream = ad.stream(self.search, self.preload)
            if coding != "identity":
                try:   # compressa: la apriamo a pezzi, cosi' le etichette si rimettono lo stesso
                    opened = R.Unpack(coding, stream)
                except ValueError:   # compressione che non conosciamo: passa com'e', senza essere letta, e lo scriviamo
                    rs.stream = True
                    self.write(service=flow.metadata.get("msp_service"), path=self.path(flow), event="stream_not_read", coding=coding[:20])
                    return
                del rs.headers["content-encoding"]
                if "content-length" in rs.headers:
                    del rs.headers["content-length"]
                rs.stream = opened
            else:
                rs.stream = stream
            flow.metadata["msp_stream"] = stream
            return
        # cio' che non riscriviamo passa a pezzi, com'e': canali di eventi, pagine, file. Restano intere solo le risposte
        # che response() puo' dover riscrivere (json e testo dei servizi protetti, quando il ripristino e' acceso)
        if ad is None or not settings.read()["restore"] or not any(x in kind for x in ("json", "text/plain")):
            rs.stream = True

    async def response(self, flow: http.HTTPFlow):
        if flow.metadata.get("msp_page"):
            await self.page_insert(flow)
            return
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
                if len(msg.content) > 200 and (obj is None or written(obj)):
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
