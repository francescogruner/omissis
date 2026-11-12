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

PROXY, FINTO = ("127.0.0.1", int(settings.leggi()["porta"])), "127.0.0.1:9911"   # la porta scelta nelle impostazioni
TESTO = ("Buongiorno, sono Giulia Ferraresi della Nevatek S.r.l.: il mio collega Aldo Bruschi (aldo.bruschi@nevatek.example, "
         "cell. 347 5551234) non riesce ad accedere. La password provvisoria è Tramonto!2026 e l'IBAN per il rimborso è "
         "IT60X0542811101000000123456. Il PC è NVT-PC014.")
ORIGINALI = ["Giulia Ferraresi", "Nevatek", "Aldo Bruschi", "aldo.bruschi@nevatek.example", "347 5551234", "Tramonto!2026",
             "IT60X0542811101000000123456", "NVT-PC014"]
ETICHETTE = ("PERSONA", "ORG", "EMAIL", "TELEFONO", "SEGRETO", "IBAN", "HOSTNAME")


def chiama(metodo, percorso, corpo=None, via_proxy=True):
    c = http.client.HTTPConnection(*(PROXY if via_proxy else FINTO.split(":")), timeout=120)
    tipo = "application/json"
    if isinstance(corpo, str):   # modulo gia' codificato (Gemini)
        dati, tipo = corpo.encode("utf-8"), "application/x-www-form-urlencoded;charset=UTF-8"
    else:
        dati = json.dumps(corpo, ensure_ascii=False).encode("utf-8") if corpo is not None else None
    c.request(metodo, f"http://{FINTO}{percorso}" if via_proxy else percorso, body=dati, headers={"Content-Type": tipo, "Host": FINTO})
    r = c.getresponse()
    return r.status, r.read().decode("utf-8")


def eventi(grezzo):
    return [json.loads(r[5:]) for r in grezzo.splitlines() if r.startswith("data:") and r[5:].strip() not in ("", "[DONE]")]


def claude(g):
    return "".join(e["delta"]["text"] for e in eventi(g) if e.get("type") == "content_block_delta")


def openai(g):
    return "".join(c.get("delta", {}).get("content") or "" for e in eventi(g) for c in e.get("choices", []))


def chatgpt(g):
    out = []
    for e in eventi(g):
        v = e.get("v")
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            out += [x["v"] for x in v if x.get("o") == "append"]
    return "".join(out)


def intero(g):
    return json.dumps(json.loads(g), ensure_ascii=False)


def cumulativo(g):
    return eventi(g)[-1]["text"]


def righe(g):
    return "".join(json.loads(r)["result"]["response"]["token"] for r in g.splitlines() if r.startswith("{"))


def prefisso(g):
    return "".join(json.loads(r[2:]) for r in g.splitlines() if r.startswith('0:"'))


def gemini(g):
    """Ultimo blocco (il testo cresce a ogni blocco); controlla anche che le lunghezze dichiarate tornino."""
    r, ultimo = g.split("\n"), ""
    for i, riga in enumerate(r):
        if riga.isdigit():
            assert int(riga) == len((r[i + 1] + "\n").encode("utf-16-le")) // 2 + 1, "lunghezza del blocco sbagliata"
            ultimo = json.loads(json.loads(r[i + 1])[0][2])[4][0][1][0]
    return ultimo


F_REQ = json.dumps([None, json.dumps([[TESTO, 0, None, None, None, None, 0], ["it"], ["c_1", "r_1", "rc_1"]], ensure_ascii=False)], ensure_ascii=False)
MODULO = "f.req=" + urllib.parse.quote(F_REQ, safe="") + "&at=" + urllib.parse.quote("AbC:123", safe="") + "&"
CASI = [
    ("claude.ai (streaming)", "POST", "/api/organizations/o1/chat_conversations/c1/completion",
     {"prompt": TESTO, "attachments": [], "rendering_mode": "messages"}, claude),
    ("claude.ai (cronologia)", "GET", "/api/organizations/o1/chat_conversations/c1", None, intero),
    ("API OpenAI e compatibili (streaming)", "POST", "/v1/chat/completions",
     {"model": "x", "stream": True, "messages": [{"role": "system", "content": "Sei un assistente."}, {"role": "user", "content": TESTO}]}, openai),
    ("chatgpt.com (streaming)", "POST", "/backend-api/conversation",
     {"action": "next", "messages": [{"author": {"role": "user"}, "content": {"content_type": "text", "parts": [TESTO]}}]}, chatgpt),
    ("API Anthropic (senza streaming)", "POST", "/v1/messages",
     {"model": "x", "max_tokens": 100, "messages": [{"role": "user", "content": [{"type": "text", "text": TESTO}]}]}, intero),
    ("generico: testo intero a ogni evento", "POST", "/generico/cumulativo", {"query_str": TESTO, "params": {"source": "default"}}, cumulativo),
    ("generico: un oggetto per riga", "POST", "/generico/righe", {"message": TESTO, "modelName": "x"}, righe),
    ("generico: righe con prefisso", "POST", "/generico/prefisso", {"messageInput": TESTO, "chatId": "0123456789abcdef0123456789abcdef"}, prefisso),
    ("Gemini (modulo e blocchi con lunghezza)", "POST", "/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate?bl=x", MODULO, gemini),
]

sys.stdout.reconfigure(encoding="utf-8")
tutto_ok = True
for nome, metodo, percorso, corpo, estrai in CASI:
    stato, grezzo = chiama(metodo, percorso, corpo)
    try:
        ricevuto = estrai(grezzo)
    except Exception as ex:   # noqa: BLE001
        ricevuto = f"<<{type(ex).__name__}: {ex}>> {grezzo}"
    visto = chiama("GET", "/visto", via_proxy=False)[1]
    fuori = [v for v in ORIGINALI if v in visto]                     # arrivati in chiaro al servizio
    persi = [v for v in ORIGINALI if v not in ricevuto]              # non ripristinati per il client
    segnaposto = any(f"[{e}_" in ricevuto for e in ETICHETTE)
    ok = stato == 200 and not fuori and not persi and not segnaposto
    tutto_ok &= ok
    print(f"{'OK    ' if ok else 'ERRORE'} {nome}: stato {stato}, in chiaro al servizio {len(fuori)}/{len(ORIGINALI)}, "
          f"non ripristinati {len(persi)}, segnaposto rimasti: {'sì' if segnaposto else 'no'}")
    if not ok:
        print("   in chiaro:", fuori, "| non ripristinati:", persi)
        print("   ricevuto dal client:", ricevuto[:400])
visto = json.loads(chiama("GET", "/visto", via_proxy=False)[1])["corpo"]
print("\nUltimo testo arrivato al servizio:\n  ", json.dumps(visto, ensure_ascii=False)[:420])
sys.exit(0 if tutto_ok else 1)
