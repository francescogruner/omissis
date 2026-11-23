# -*- coding: utf-8 -*-
"""Prova, senza rete e senza browser, la strada che protegge l'app desktop di Claude (addon.py, inpage.py, wire.py):
richieste finte verso claude.ai come le fa l'app, motore finto, dati in una cartella provvisoria.

Controlla che: il messaggio in protobuf venga letto e riscritto (anche compresso, anche nella busta di Connect); quello
che non si legge venga fermato; a motore fermo il messaggio non parta; le chiamate del codice messo nella pagina trovino
risposta nel proxy e non partano mai verso il sito; il codice entri in cima alla pagina con la regola di sicurezza
aggiornata; il resto resti com'era. Non ha bisogno della copia di prova accesa: gira uguale su Windows, Mac e Linux.

   Uso: python e2e_rpc.py
"""
import asyncio
import base64
import gzip
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
data = Path(tempfile.mkdtemp(prefix="omissis-e2e-rpc-"))
os.environ["OMISSIS_DATA"] = str(data)
os.environ.pop("OMISSIS_TEST", None)
(data / "token.txt").write_text("x", encoding="utf-8")
(data / "token_extension.txt").write_text("segreto-di-prova", encoding="utf-8")
sys.path.insert(0, str(HERE))

from mitmproxy import http             # noqa: E402
from mitmproxy.test import tflow       # noqa: E402
import addon                           # noqa: E402
import inpage                          # noqa: E402
import wire                            # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
outcomes = []
AGENT = "Mozilla/5.0 Claude/6.28899.2 Electron/45.0"
CLIENT = "Claude 6.28899.2"


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(("OK     " if ok else "ERRORE ") + name + (f"   {note}" if note else ""))


def field(n, v):
    if isinstance(v, int):
        return wire._encode(n << 3) + wire._encode(v)
    if isinstance(v, str):
        v = v.encode("utf-8")
    return wire._encode(n << 3 | 2) + wire._encode(len(v)) + v


TEXT = "Scrivi a Giulia Ferraresi (giulia.ferraresi@nevatek.example, cell. +39 347 5551234) della Nevatek S.r.l."
MESSAGE = field(1, "0199f0aa-7d0c-7c1e-9d59-3f4a6f6a1b2c") + field(2, field(1, field(1, TEXT) + field(2, 7)) + field(3, "it-IT"))
FAKE = {"Giulia Ferraresi": "[PERSONA_1]", "giulia.ferraresi@nevatek.example": "[EMAIL_1]", "+39 347 5551234": "[TELEFONO_1]", "Nevatek S.r.l.": "[ORG_1]"}
RPC = "/claudeai-rpc/anthropic.bard.api.v1alpha.ConversationService/"


def request(method, path, kind="", body=b"", more=None):
    f = tflow.tflow()
    headers = {"User-Agent": AGENT, **(more or {})}
    if kind:
        headers["content-type"] = kind
    f.request = http.Request.make(method, "https://claude.ai" + path, b"", headers)
    f.request.raw_content = body   # cosi' com'e': Request.make lo ricomprimerebbe
    return f


def log():
    p = data / "activity.jsonl"
    return [json.loads(r) for r in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


async def fake_engine(texts):
    out = []
    for t in texts:
        for k, v in FAKE.items():
            t = t.replace(k, v)
        out.append(t)
    return {"texts": out, "mapping": {v: k for k, v in FAKE.items()}, "counts": {"PERSONA": 1, "EMAIL": 1, "TELEFONO": 1, "ORG": 1}, "ms": 3}


async def broken(texts):
    raise OSError("fermo")


def main():
    a = addon.MspPii()
    a.mask = fake_engine

    # 1. il messaggio in protobuf viene letto e riscritto
    f = request("POST", RPC + "PerformAction", "application/proto", MESSAGE)
    asyncio.run(a.request(f))
    r, arrived = log(), f.request.get_content()
    mark("protobuf: sostituito dal proxy", f.response is None and b"Giulia" not in arrived and b"nevatek" not in arrived and "[PERSONA_1]" in wire.texts(arrived)[1],
         wire.texts(arrived)[1][:70])
    mark("protobuf: gli altri campi restano com'erano", wire.texts(arrived)[0] == "0199f0aa-7d0c-7c1e-9d59-3f4a6f6a1b2c" and wire.texts(arrived)[2] == "it-IT"
         and wire.shape(arrived)["2"]["1"]["2"] == "int")
    mark("protobuf: nel registro «masked», senza valori", len(r) == 1 and r[0]["event"] == "masked" and "Giulia" not in json.dumps(r[0]),
         json.dumps({k: r[0].get(k) for k in ("event", "fields", "replacements", "kind")}) if r else "")
    mark("protobuf: il registro dice dove stava il testo (numeri dei campi e lunghezza)", bool(r) and r[0].get("where") == [f"2.1.1:{len(TEXT)}"]
         and r[0].get("texts") == 1 and r[0].get("kept") == [], str(r[0].get("where")) if r else "")

    # 2. compresso: resta compresso e cambia dentro
    f = request("POST", RPC + "PerformAction", "application/proto", gzip.compress(MESSAGE), {"content-encoding": "gzip"})
    asyncio.run(a.request(f))
    mark("protobuf compresso: sostituito e ancora compresso", f.request.raw_content[:2] == b"\x1f\x8b" and b"Giulia" not in f.request.get_content()
         and "[EMAIL_1]" in wire.texts(f.request.get_content())[1])

    # 3. gia' sostituito dalla casella: non cambia e non scrive nulla
    done = field(1, "x") + field(2, field(1, field(1, "Scrivi a [PERSONA_1] ([EMAIL_1]) della [ORG_1]")))
    f = request("POST", RPC + "PerformAction", "application/proto", done)
    n = len(log())
    asyncio.run(a.request(f))
    mark("gia' sostituito dalla casella: passa uguale, niente nel registro", f.request.raw_content == done and len(log()) == n and f.response is None)

    # 4. la busta di Connect
    f = request("POST", RPC + "StreamTimeline", "application/connect+proto", wire.wrap(True, field(1, "0199f0aa-7d0c") + field(2, "it-IT")))
    n = len(log())
    asyncio.run(a.request(f))
    mark("canale degli eventi: letto, nulla da fare", f.response is None and len(log()) == n)
    f = request("POST", RPC + "PerformAction", "application/connect+proto", wire.wrap(True, MESSAGE))
    asyncio.run(a.request(f))
    enveloped, inside = wire.unwrap(f.request.get_content(), "application/connect+proto")
    mark("messaggio nella busta: sostituito, busta rifatta", enveloped and b"Giulia" not in inside and "[PERSONA_1]" in wire.texts(inside)[1])

    # 5. byte illeggibili sul messaggio: fermati
    f = request("POST", RPC + "PerformAction", "application/proto", bytes(range(200, 256)) * 3)
    asyncio.run(a.request(f))
    last = log()[-1]
    mark("messaggio illeggibile: fermato (415) e annotato con il programma", f.response is not None and f.response.status_code == 415
         and last["event"] == "blocked_rpc_not_read" and last.get("client") == CLIENT, str(last.get("client")))

    # 6. il motore non risponde: il messaggio non parte
    a.mask = broken
    f = request("POST", RPC + "PerformAction", "application/proto", MESSAGE)
    asyncio.run(a.request(f))
    mark("motore fermo: il messaggio non parte (503)", f.response is not None and f.response.status_code == 503)
    a.mask = fake_engine

    # 7. le chiamate del codice nella pagina: risponde il proxy, non partono mai
    seen = []
    inpage.handle = lambda engine, m, client: (seen.append((m, client)), {"action": "replace", "text": "x", "replacements": 1})[1]
    inpage.status = lambda engine, client, test=False: {"services": [{"id": "claude", "name": "Claude", "domains": ["claude.ai"], "policy": "protect", "readable": True}],
                                                        "restore": True, "block_files": False}
    body = json.dumps({"m": {"t": "text", "host": "claude.ai", "text": TEXT}}).encode()
    f = request("POST", "/__omissis__/call", "application/json", body)
    asyncio.run(a.request(f))
    mark("chiamata senza chiave: rifiutata qui (403), non inoltrata", f.response is not None and f.response.status_code == 403 and not seen)
    f = request("POST", "/__omissis__/call", "application/json", body, {"x-omissis-key": inpage.key()})
    asyncio.run(a.request(f))
    mark("chiamata con la chiave: risponde il proxy", f.response is not None and f.response.status_code == 200 and f.response.headers.get("x-omissis") == "1"
         and json.loads(f.response.content)["action"] == "replace" and bool(seen) and seen[0][1] == CLIENT, seen[0][1] if seen else "")
    n = len(log())
    f = request("GET", "/__omissis__/status", more={"x-omissis-key": inpage.key()})
    asyncio.run(a.request(f))
    mark("stato per la pagina, senza righe nel registro", f.response is not None and f.response.status_code == 200
         and json.loads(f.response.content)["services"][0]["id"] == "claude" and len(log()) == n)
    f = request("GET", "/__omissis__/here")
    asyncio.run(a.request(f))
    mark("«chi risponde?»: senza chiave, risponde il proxy", f.response is not None and f.response.status_code == 200
         and f.response.headers.get("x-omissis") == "1" and len(log()) == n)
    f = request("GET", "/__omissis__/status", more={"x-omissis-key": inpage.key(), "x-omissis-hello": "1"})
    asyncio.run(a.request(f))
    r = log()
    mark("il codice che si presenta viene annotato, con il programma in cui gira", len(r) == n + 1 and r[-1]["event"] == "page_active"
         and r[-1].get("client") == CLIENT and r[-1].get("via") == "app desktop", json.dumps({k: r[-1].get(k) for k in ("event", "client", "via")}))
    f = tflow.tflow()
    f.request = http.Request.make("POST", "https://example.org/__omissis__/call", b"{}", {"x-omissis-key": inpage.key()})
    asyncio.run(a.request(f))
    mark("su un sito non protetto: risposta locale (404), mai inoltrata", f.response is not None and f.response.status_code == 404)

    # 8. la pagina: lo script va in cima, con il nonce, e la regola di sicurezza lo ammette
    html = ('<!doctype html><html lang="en"><head data-x="1"><meta charset="utf-8"><script nonce="AbC123">window.x=1</script></head>'
            '<body><div contenteditable="true"></div></body></html>')
    rule = "script-src 'nonce-AbC123' 'strict-dynamic' 'sha256-aaaa'; object-src 'none'"
    f = request("GET", "/new", more={"sec-fetch-dest": "document"})
    asyncio.run(a.request(f))
    f.response = http.Response.make(200, html.encode(), {"content-type": "text/html; charset=utf-8", "content-security-policy": rule})
    a.responseheaders(f)
    mark("pagina: trattenuta intera", f.metadata.get("msp_page") is True and not f.response.stream)
    asyncio.run(a.response(f))
    new, csp = f.response.get_text(), f.response.headers["content-security-policy"]
    m = re.search(r'<head data-x="1"><script nonce="AbC123">(.*?)</script><meta', new, re.S)
    mark("pagina: script in cima a <head>, con il nonce della pagina", bool(m), f"{len(new)} caratteri")
    digest = base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode() if m else "?"
    mark("pagina: l'impronta dello script e' tra le sorgenti ammesse", f"'sha256-{digest}'" in csp and "object-src 'none'" in csp, csp[:80])
    mark("pagina: dentro ci sono guscio, chiave e codice della casella", bool(m) and inpage.key() in m.group(1) and "barriera sulla casella" in m.group(1)
         and "__omissis__" in m.group(1) and "x-omissis-hello" in m.group(1) and "</script" not in m.group(1))
    mark("pagina: annotata nel registro", log()[-1]["event"] == "page_prepared")

    f = request("GET", "/isolated-segment.html", more={"sec-fetch-dest": "iframe"})
    asyncio.run(a.request(f))
    f.response = http.Response.make(200, html.encode(), {"content-type": "text/html; charset=utf-8"})
    a.responseheaders(f)
    mark("un riquadro interno della pagina non viene toccato", not f.metadata.get("msp_page"))

    # 9. la pagina che non si riesce a preparare passa com'era, e nel registro resta scritto con quale programma
    kept, inpage.source = inpage.source, lambda state: 1 / 0
    f = request("GET", "/new", more={"sec-fetch-dest": "document"})
    asyncio.run(a.request(f))
    f.response = http.Response.make(200, html.encode(), {"content-type": "text/html; charset=utf-8", "content-security-policy": rule})
    a.responseheaders(f)
    asyncio.run(a.response(f))
    inpage.source = kept
    last = log()[-1]
    mark("pagina non preparata: passa com'era, annotata con il programma", f.response.get_text() == html and f.response.headers["content-security-policy"] == rule
         and last["event"] == "page_not_prepared" and last.get("client") == CLIENT, json.dumps({k: last.get(k) for k in ("event", "client", "error")}))

    # 10. il resto come prima
    f = request("GET", "/api/organizations/o1/chat_conversations_v2")
    asyncio.run(a.request(f))
    f.response = http.Response.make(200, b'{"a": 1}', {"content-type": "application/json"})
    a.responseheaders(f)
    asyncio.run(a.response(f))
    mark("risposta JSON: come prima", f.response.content == b'{"a": 1}' and not f.metadata.get("msp_page"))
    f = request("POST", "/api/organizations/o1/dust/generate_title_and_branch", "application/json",
                json.dumps({"first_session_message": TEXT, "title_style": "default", "model": "m"}).encode())
    asyncio.run(a.request(f))
    title = json.loads(f.request.get_text())
    mark("titolo di una sessione di codice: il primo messaggio parte sostituito", "Giulia" not in title["first_session_message"]
         and "[PERSONA_1]" in title["first_session_message"] and title["model"] == "m", title["first_session_message"][:50])
    f = request("GET", "/v1/code/sessions/s1")
    asyncio.run(a.request(f))
    f.response = http.Response.make(200, b'{"riga": "[PERSONA_1] nel codice"}', {"content-type": "application/json"})
    n = len(log())
    a.responseheaders(f)
    asyncio.run(a.response(f))
    mark("sessioni di codice: la risposta non si tocca", f.response.content == b'{"riga": "[PERSONA_1] nel codice"}' and len(log()) == n)
    f = request("POST", "/api/organizations/o1/experiences/track", "application/json", json.dumps({"action": "x"}).encode())
    n = len(log())
    asyncio.run(a.request(f))
    mark("richiesta di servizio: fuori dal registro", len(log()) == n)
    mark("regole: 'unsafe-inline' senza nonce non si tocca; default-src fa da script-src",
         inpage.allow("script-src 'self' 'unsafe-inline'", "H") == "script-src 'self' 'unsafe-inline'" and "'sha256-H'" in inpage.allow("default-src 'self'", "H"))

    print(f"\n{'TUTTO OK' if all(outcomes) else 'ERRORI'}: {sum(outcomes)}/{len(outcomes)}")
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
