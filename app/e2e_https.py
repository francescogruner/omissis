# -*- coding: utf-8 -*-
"""Verifica l'intercettazione HTTPS vera, senza account: manda all'API di Anthropic una richiesta
SENZA chiave (dati inventati) e controlla che il proxy l'abbia aperta e mascherata; poi controlla
che un sito qualsiasi passi dal proxy senza essere aperto.   Uso: python e2e_https.py
"""
import http.client
import json
import ssl
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
import paths   # noqa: E402
sys.stdout.reconfigure(encoding="utf-8")


def through_proxy(host, context):
    c = http.client.HTTPSConnection("127.0.0.1", 8080, timeout=60, context=context)
    c.set_tunnel(host, 443)
    return c


# 1) servizio in elenco: deve presentarsi con il certificato del proxy (e solo con quello)
only_proxy = ssl.create_default_context(cafile=str(paths.DATA / "ca" / "mitmproxy-ca-cert.pem"))
c = through_proxy("api.anthropic.com", only_proxy)
body = {"model": "claude-haiku-5-5", "max_tokens": 16, "messages": [{"role": "user", "content": "Sono Ilaria Montefusco, scrivimi a ilaria.montefusco@nevatek.example"}]}
c.request("POST", "/v1/messages", body=json.dumps(body).encode(), headers={"content-type": "application/json", "anthropic-version": "2023-06-01"})
r = c.getresponse()
print(f"api.anthropic.com tramite proxy: stato {r.status} (atteso 401: manca la chiave) | {r.read().decode()[:110]}")
latest = [json.loads(x) for x in (paths.DATA / "activity.jsonl").read_text(encoding="utf-8").splitlines()[-3:]]
masch = [v for v in latest if v.get("service") == "anthropic-api" and v.get("event") == "masked"]
print("  richiesta aperta e mascherata dal proxy:", "sì " + json.dumps(masch[-1]["replacements"]) if masch else "NO")

# 2) sito non in elenco: deve arrivare con il suo certificato vero (il proxy non lo apre)
normal = ssl.create_default_context()
c = through_proxy("example.com", normal)
c.request("GET", "/")
print(f"example.com tramite proxy con i certificati normali: stato {c.getresponse().status} -> non intercettato")
try:
    c = through_proxy("example.com", only_proxy)
    c.request("GET", "/")
    c.getresponse()
    print("  ERRORE: example.com risulta firmato dal proxy")
except ssl.SSLError:
    print("  confermato: il certificato del proxy non compare su example.com")
