# -*- coding: utf-8 -*-
"""Addon di mitmproxy per le prove: annota che cosa passa dal proxy, una riga JSON per evento.

Si carica DOPO addon.py di Omissis (mitmdump -s addon.py -s proxy_log_addon.py): vede le richieste come le lascia Omissis.
Scrive solo host, metodo, percorso senza la parte dopo «?», stato della risposta e il nome del programma che chiama.
Mai corpi, mai cookie, mai le altre intestazioni.

  OMISSIS_TRIAL_LOG   il file dove scrivere (una riga per evento)
"""
import json
import os
import re
import threading
import time

OUT = open(os.environ["OMISSIS_TRIAL_LOG"], "a", encoding="utf-8")
LOCK = threading.Lock()
RX_PROGRAM = re.compile(r"(?:Claude|ChatGPT|Electron|Chrome|Safari|Firefox|Edg)/[\w.]+")


def note(**entry):
    entry["t"] = round(time.time(), 2)
    with LOCK:
        OUT.write(json.dumps(entry, ensure_ascii=False) + "\n")
        OUT.flush()


def path(flow):
    return flow.request.path.split("?", 1)[0][:140]


def http_connect(flow):
    note(event="connect", host=flow.request.host)


def port(conn):
    """La porta da cui arriva chi si collega: serve a riconoscere la stessa connessione in piu' righe."""
    try:
        return conn.peername[1]
    except Exception:   # noqa: BLE001
        return 0


def tls_clienthello(data):
    """Il «ciao» di chi si collega: dice che tipo di programma e' (Chromium manda valori a caso, detti GREASE; Node e
    le librerie di Windows no)."""
    hello = data.client_hello
    suites = list(hello.cipher_suites or [])
    note(event="hello", host=hello.sni or "", client=port(data.context.client), suites=len(suites),
         grease=any((s & 0x0f0f) == 0x0a0a and (s >> 8) == (s & 0xff) for s in suites),
         alpn=[a.decode("ascii", "replace") for a in (hello.alpn_protocols or [])])


def tls_established_client(data):
    note(event="tls_ok", host=data.conn.sni or "", client=port(data.conn))


def tls_failed_client(data):
    note(event="tls_failed", host=data.conn.sni or "", client=port(data.conn), error=str(data.conn.error or "")[:240])


def request(flow):
    programs = " ".join(RX_PROGRAM.findall(flow.request.headers.get("User-Agent", "")))[:120]
    note(event="request", host=flow.request.pretty_host, method=flow.request.method, path=path(flow),
         bytes=len(flow.request.raw_content or b""), program=programs)


def response(flow):
    rs = flow.response
    note(event="response", host=flow.request.pretty_host, method=flow.request.method, path=path(flow), status=rs.status_code,
         kind=rs.headers.get("content-type", "")[:40], mitigated=rs.headers.get("cf-mitigated", ""),
         omissis=bool(flow.metadata.get("msp")))


def error(flow):
    note(event="error", host=flow.request.pretty_host, path=path(flow), error=str(flow.error)[:240])


def websocket_start(flow):
    note(event="websocket", host=flow.request.pretty_host, path=path(flow))
