# -*- coding: utf-8 -*-
"""Prova da capo a capo con il servizio finto: client -> proxy -> servizio finto.

Per ogni formato controlla che (1) al servizio siano arrivati solo segnaposto e (2) il client
riveda i valori originali. I dati sono inventati.   Uso: python e2e_proxy.py
Richiede in esecuzione la protezione in modalita' di prova (panel.py --test oppure
start.py --test) e mock_service.py.
"""
import http.client
import json
import sys
import urllib.parse

import settings   # noqa: E402

PROXY, FAKE = ("127.0.0.1", int(settings.read()["port"])), "127.0.0.1:9911"   # la porta scelta nelle impostazioni
TEXT = ("Buongiorno, sono Giulia Ferraresi della Nevatek S.r.l.: il mio collega Aldo Bruschi (aldo.bruschi@nevatek.example, "
         "cell. 347 5551234) non riesce ad accedere. La password provvisoria è Tramonto!2026 e l'IBAN per il rimborso è "
         "IT60X0542811101000000123456. Il PC è NVT-PC014.")
ORIGINALS = ["Giulia Ferraresi", "Nevatek", "Aldo Bruschi", "aldo.bruschi@nevatek.example", "347 5551234", "Tramonto!2026",
             "IT60X0542811101000000123456", "NVT-PC014"]
LABELS = ("PERSONA", "ORG", "EMAIL", "TELEFONO", "SEGRETO", "IBAN", "HOSTNAME")


def call(method, path, body=None, via_proxy=True):
    c = http.client.HTTPConnection(*(PROXY if via_proxy else FAKE.split(":")), timeout=120)
    kind = "application/json"
    if isinstance(body, str):   # modulo gia' codificato (Gemini)
        data, kind = body.encode("utf-8"), "application/x-www-form-urlencoded;charset=UTF-8"
    else:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    c.request(method, f"http://{FAKE}{path}" if via_proxy else path, body=data, headers={"Content-Type": kind, "Host": FAKE})
    r = c.getresponse()
    return r.status, r.read().decode("utf-8")


def events(raw):
    return [json.loads(r[5:]) for r in raw.splitlines() if r.startswith("data:") and r[5:].strip() not in ("", "[DONE]")]


def claude(g):
    return "".join(e["delta"]["text"] for e in events(g) if e.get("type") == "content_block_delta")


def openai(g):
    return "".join(c.get("delta", {}).get("content") or "" for e in events(g) for c in e.get("choices", []))


def chatgpt(g):
    out = []
    for e in events(g):
        v = e.get("v")
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            out += [x["v"] for x in v if x.get("o") == "append"]
    return "".join(out)


def entire(g):
    return json.dumps(json.loads(g), ensure_ascii=False)


def cumulative(g):
    return events(g)[-1]["text"]


def lines(g):
    return "".join(json.loads(r)["result"]["response"]["token"] for r in g.splitlines() if r.startswith("{"))


def prefix(g):
    return "".join(json.loads(r[2:]) for r in g.splitlines() if r.startswith('0:"'))


def gemini(g):
    """Ultimo blocco (il testo cresce a ogni blocco); controlla anche che le lunghezze dichiarate tornino."""
    r, last = g.split("\n"), ""
    for i, line in enumerate(r):
        if line.isdigit():
            assert int(line) == len((r[i + 1] + "\n").encode("utf-16-le")) // 2 + 1, "lunghezza del blocco sbagliata"
            last = json.loads(json.loads(r[i + 1])[0][2])[4][0][1][0]
    return last


F_REQ = json.dumps([None, json.dumps([[TEXT, 0, None, None, None, None, 0], ["it"], ["c_1", "r_1", "rc_1"]], ensure_ascii=False)], ensure_ascii=False)
MODULE = "f.req=" + urllib.parse.quote(F_REQ, safe="") + "&at=" + urllib.parse.quote("AbC:123", safe="") + "&"
CASES = [
    ("claude.ai (streaming)", "POST", "/api/organizations/o1/chat_conversations/c1/completion",
     {"prompt": TEXT, "attachments": [], "rendering_mode": "messages"}, claude),
    ("claude.ai (cronologia)", "GET", "/api/organizations/o1/chat_conversations/c1", None, entire),
    ("API OpenAI e compatibili (streaming)", "POST", "/v1/chat/completions",
     {"model": "x", "stream": True, "messages": [{"role": "system", "content": "Sei un assistente."}, {"role": "user", "content": TEXT}]}, openai),
    ("chatgpt.com (streaming)", "POST", "/backend-api/conversation",
     {"action": "next", "messages": [{"author": {"role": "user"}, "content": {"content_type": "text", "parts": [TEXT]}}]}, chatgpt),
    ("API Anthropic (senza streaming)", "POST", "/v1/messages",
     {"model": "x", "max_tokens": 100, "messages": [{"role": "user", "content": [{"type": "text", "text": TEXT}]}]}, entire),
    ("generico: testo intero a ogni evento", "POST", "/generic/cumulative", {"query_str": TEXT, "params": {"source": "default"}}, cumulative),
    ("generico: un oggetto per riga", "POST", "/generic/lines", {"message": TEXT, "modelName": "x"}, lines),
    ("generico: righe con prefisso", "POST", "/generic/prefix", {"messageInput": TEXT, "chatId": "0123456789abcdef0123456789abcdef"}, prefix),
    ("Gemini (modulo e blocchi con lunghezza)", "POST", "/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate?bl=x", MODULE, gemini),
]

sys.stdout.reconfigure(encoding="utf-8")
all_ok = True
for name, method, path, body, extract in CASES:
    status, raw = call(method, path, body)
    try:
        received = extract(raw)
    except Exception as ex:   # noqa: BLE001
        received = f"<<{type(ex).__name__}: {ex}>> {raw}"
    seen = call("GET", "/seen", via_proxy=False)[1]
    outside = [v for v in ORIGINALS if v in seen]                     # arrivati in chiaro al servizio
    lost = [v for v in ORIGINALS if v not in received]              # non ripristinati per il client
    placeholder = any(f"[{e}_" in received for e in LABELS)
    ok = status == 200 and not outside and not lost and not placeholder
    all_ok &= ok
    print(f"{'OK    ' if ok else 'ERRORE'} {name}: stato {status}, in chiaro al servizio {len(outside)}/{len(ORIGINALS)}, "
          f"non ripristinati {len(lost)}, segnaposto rimasti: {'sì' if placeholder else 'no'}")
    if not ok:
        print("   in chiaro:", outside, "| non ripristinati:", lost)
        print("   ricevuto dal client:", received[:400])
seen = json.loads(call("GET", "/seen", via_proxy=False)[1])["body"]
print("\nUltimo testo arrivato al servizio:\n  ", json.dumps(seen, ensure_ascii=False)[:420])
sys.exit(0 if all_ok else 1)
