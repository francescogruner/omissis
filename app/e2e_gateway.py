# -*- coding: utf-8 -*-
"""Prova il gateway per gli strumenti da terminale contro un servizio finto che si comporta come le
API di Anthropic e di OpenAI quando le usa un agente: testo, azioni (uso degli strumenti) con gli
argomenti scritti a rate, ragionamenti firmati. Il gateway gira dentro questa prova, su una porta
sua; serve solo il motore acceso (la protezione attiva).

Controlla che al servizio non arrivi nulla in chiaro (nemmeno negli argomenti delle azioni gia'
fatte e nei risultati degli strumenti), che allo strumento tornino i valori veri (anche dentro gli
argomenti delle nuove azioni), che i ragionamenti firmati viaggino identici in entrambi i sensi.
"""
import json
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import gateway
import paths
import restore as R

QUI = Path(__file__).resolve().parent
PORTA_FINTO, PORTA_GW = paths.PORTA_MOTORE + 147, paths.PORTA_MOTORE + 148
TESTO = ("Scrivi una mail a Giulia Ferraresi (giulia.ferraresi@nevatek.example, cell. 347 5551234) della Nevatek S.r.l. "
         "per confermare l'appuntamento con Aldo Bruschi.")
SENSIBILI = ["Giulia Ferraresi", "giulia.ferraresi@nevatek.example", "347 5551234", "Aldo Bruschi"]
RAGIONAMENTO = {"type": "thinking", "thinking": "L'utente [PERSONA_1] vuole una mail.", "signature": "firma-che-deve-tornare-identica=="}
VISTO = {"corpo": None, "chiave": None, "n": 0}
esiti = []


def pezzi(t, n):
    return [t[i:i + n] for i in range(0, len(t), n)]


def ultimo_testo(corpo):
    """L'ultimo testo dell'utente cosi' come e' arrivato al servizio."""
    if "messages" in corpo:
        c = corpo["messages"][-1]["content"]
        if isinstance(c, str):
            return c
        return next((b.get("text") or b.get("content") for b in reversed(c) if isinstance(b, dict) and isinstance(b.get("text") or b.get("content"), str)), "")
    ingresso = corpo.get("input")
    return ingresso if isinstance(ingresso, str) else ingresso[-1]["content"][0]["text"]


class Finto(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _manda(self, codice, tipo, corpo):
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("request-id", "req_finto")
        self.end_headers()
        self.wfile.write(corpo)

    def _sse(self, eventi):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for nome, dati in eventi:
            b = ((f"event: {nome}\n" if nome else "") + "data: " + (dati if isinstance(dati, str) else json.dumps(dati, ensure_ascii=False)) + "\n\n").encode("utf-8")
            for parte in (b[:len(b) // 2], b[len(b) // 2:]):
                self.wfile.write(f"{len(parte):x}\r\n".encode() + parte + b"\r\n")
                self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")

    def do_GET(self):
        self._manda(200, "application/json", json.dumps({"data": [{"id": "modello-finto"}], "percorso": self.path}).encode())

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
        VISTO.update(corpo=corpo, chiave=self.headers.get("x-api-key") or self.headers.get("Authorization"), n=VISTO["n"] + 1,
                     codifica=self.headers.get("Accept-Encoding"))
        if VISTO["chiave"] in ("sbagliata", "Bearer sbagliata"):
            return self._manda(401, "application/json", b'{"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}')
        ricevuto = ultimo_testo(corpo)
        testo = "Ho ricevuto: " + ricevuto
        posta = re.search(r"\[EMAIL_\d+\]", ricevuto)   # il numero dipende da cio' che l'archivio contiene gia'
        argomenti = json.dumps({"comando": "scrivi_file", "percorso": "bozze/mail.txt", "contenuto": ricevuto, "destinatari": [posta.group() if posta else "[EMAIL_1]"]}, ensure_ascii=False)
        flusso = bool(corpo.get("stream"))
        if self.path.startswith("/v1/messages"):
            if not flusso:
                return self._manda(200, "application/json", json.dumps({"type": "message", "role": "assistant", "content": [
                    RAGIONAMENTO, {"type": "text", "text": testo}, {"type": "tool_use", "id": "tu_1", "name": "scrivi", "input": json.loads(argomenti)}]},
                    ensure_ascii=False).encode("utf-8"))
            ev = [("message_start", {"type": "message_start", "message": {"id": "m1"}}),
                  ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}),
                  ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": RAGIONAMENTO["thinking"]}}),
                  ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": RAGIONAMENTO["signature"]}}),
                  ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                  ("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}})]
            ev += [("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": x}}) for x in pezzi(testo, 7)]
            ev += [("content_block_stop", {"type": "content_block_stop", "index": 1}),
                   ("content_block_start", {"type": "content_block_start", "index": 2, "content_block": {"type": "tool_use", "id": "tu_1", "name": "scrivi", "input": {}}})]
            ev += [("content_block_delta", {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": x}}) for x in pezzi(argomenti, 5)]
            ev += [("content_block_stop", {"type": "content_block_stop", "index": 2}), ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"}}),
                   ("message_stop", {"type": "message_stop"})]
            return self._sse(ev)
        if self.path.startswith("/v1/chat/completions"):
            if not flusso:
                return self._manda(200, "application/json", json.dumps({"choices": [{"message": {"role": "assistant", "content": testo, "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "scrivi", "arguments": argomenti}}]}, "finish_reason": "tool_calls"}]}, ensure_ascii=False).encode("utf-8"))
            ev = [("", {"choices": [{"index": 0, "delta": {"content": x}, "finish_reason": None}]}) for x in pezzi(testo, 6)]
            ev += [("", {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": x}}]}, "finish_reason": None}]}) for x in pezzi(argomenti, 5)]
            ev += [("", {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}), ("", "[DONE]")]
            return self._sse(ev)
        if self.path.startswith("/v1/responses"):
            ev = [("response.output_text.delta", {"type": "response.output_text.delta", "delta": x}) for x in pezzi(testo, 6)]
            ev += [("response.output_text.done", {"type": "response.output_text.done", "text": testo})]
            ev += [("response.function_call_arguments.delta", {"type": "response.function_call_arguments.delta", "delta": x}) for x in pezzi(argomenti, 5)]
            ev += [("response.function_call_arguments.done", {"type": "response.function_call_arguments.done", "arguments": argomenti}),
                   ("response.completed", {"type": "response.completed", "response": {"output": [{"type": "message", "content": [{"type": "output_text", "text": testo}]}]}})]
            return self._sse(ev)
        self._manda(404, "application/json", b"{}")


def chiama(percorso, corpo=None, intestazioni=None):
    rich = urllib.request.Request(f"http://127.0.0.1:{PORTA_GW}{percorso}", data=json.dumps(corpo).encode("utf-8") if corpo is not None else None,
                                  headers={"Content-Type": "application/json", **(intestazioni or {})})
    try:
        with urllib.request.urlopen(rich, timeout=120) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode("utf-8")


def eventi(grezzo):
    out = []
    for blocco in grezzo.split("\n\n"):
        riga = next((x for x in blocco.split("\n") if x.startswith("data:")), None)
        if riga and riga[5:].strip() != "[DONE]":
            out.append(json.loads(riga[5:]))
    return out


def segna(nome, ok, nota=""):
    esiti.append(bool(ok))
    print(f"{'OK    ' if ok else 'ERRORE'} {nome}" + (f"   {nota}" if nota else ""), flush=True)


def in_chiaro(oggetto):
    t = json.dumps(oggetto, ensure_ascii=False)
    return sum(s in t for s in SENSIBILI)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    registro = paths.DATI / "activity.jsonl"
    righe_prima = len(registro.read_text(encoding="utf-8").splitlines()) if registro.exists() else 0
    finto = ThreadingHTTPServer(("127.0.0.1", PORTA_FINTO), Finto)
    threading.Thread(target=finto.serve_forever, daemon=True).start()
    gw = gateway.Gateway(PORTA_GW, a_monte=f"http://127.0.0.1:{PORTA_FINTO}").avvia()
    sistema = "Sei un assistente che lavora per conto di Giulia Ferraresi. " + "Rispondi sempre in italiano e con precisione. " * 6
    cronologia = [
        {"role": "user", "content": [{"type": "text", "text": TESTO}]},
        {"role": "assistant", "content": [dict(RAGIONAMENTO), {"type": "text", "text": "Leggo il file dei contatti."},
                                         {"type": "tool_use", "id": "tu_0", "name": "leggi", "input": {"percorso": "contatti/Giulia Ferraresi.txt", "righe": 20}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_0", "content": "Giulia Ferraresi; giulia.ferraresi@nevatek.example; 347 5551234; referente Aldo Bruschi"},
                                     {"type": "text", "text": TESTO}]},
    ]

    # --- Anthropic, risposta intera
    stato, grezzo = chiama("/anthropic/v1/messages?beta=true", {"model": "x", "system": sistema, "messages": cronologia, "max_tokens": 100}, {"x-api-key": "chiave-di-prova"})
    arrivato = VISTO["corpo"]
    risposta = json.loads(grezzo)
    segna("Anthropic: nulla in chiaro al servizio (testo, sistema, azioni fatte, risultati degli strumenti)", stato == 200 and in_chiaro(arrivato) == 0
          and "[PERSONA_" in json.dumps(arrivato), f"in chiaro {in_chiaro(arrivato)}")
    segna("Anthropic: l'argomento dell'azione già fatta è stato mascherato", "Ferraresi" not in arrivato["messages"][1]["content"][2]["input"]["percorso"]
          and arrivato["messages"][1]["content"][2]["input"]["righe"] == 20)
    segna("Anthropic: il ragionamento firmato arriva al servizio identico", arrivato["messages"][1]["content"][0] == RAGIONAMENTO)
    segna("Anthropic: credenziale inoltrata, risposta non compressa", VISTO["chiave"] == "chiave-di-prova" and VISTO["codifica"] == "identity")
    testo = next(b["text"] for b in risposta["content"] if b["type"] == "text")
    azione = next(b["input"] for b in risposta["content"] if b["type"] == "tool_use")
    segna("Anthropic: testo e argomenti della nuova azione tornano con i valori veri", all(s in testo for s in SENSIBILI) and all(s in azione["contenuto"] for s in SENSIBILI)
          and azione["destinatari"] == ["giulia.ferraresi@nevatek.example"], f"testo {sum(s in testo for s in SENSIBILI)}/4")
    segna("Anthropic: il ragionamento firmato torna allo strumento identico", risposta["content"][0] == RAGIONAMENTO)

    # --- Anthropic, risposta mentre arriva
    stato, grezzo = chiama("/anthropic/v1/messages", {"model": "x", "system": [{"type": "text", "text": "Sei Claude Code."}, {"type": "text", "text": sistema}],
                                                      "messages": cronologia, "stream": True}, {"x-api-key": "chiave-di-prova"})
    ev = eventi(grezzo)
    testo = "".join(e["delta"].get("text", "") for e in ev if e.get("type") == "content_block_delta")
    rate = "".join(e["delta"].get("partial_json", "") for e in ev if e.get("type") == "content_block_delta")
    pensiero = "".join(e["delta"].get("thinking", "") for e in ev if e.get("type") == "content_block_delta")
    firma = "".join(e["delta"].get("signature", "") for e in ev if e.get("type") == "content_block_delta")
    try:
        azione = json.loads(rate)
    except ValueError:
        azione = {}
    segna("Anthropic in streaming: nulla in chiaro al servizio, riga di identità lasciata com'è", in_chiaro(VISTO["corpo"]) == 0
          and VISTO["corpo"]["system"][0]["text"] == "Sei Claude Code.")
    segna("Anthropic in streaming: testo ripristinato", all(s in testo for s in SENSIBILI) and "[PERSONA_" not in testo)
    segna("Anthropic in streaming: argomenti dell'azione leggibili e con i valori veri", all(s in azione.get("contenuto", "") for s in SENSIBILI)
          and azione.get("destinatari") == ["giulia.ferraresi@nevatek.example"])
    segna("Anthropic in streaming: ragionamento e firma non toccati", pensiero == RAGIONAMENTO["thinking"] and firma == RAGIONAMENTO["signature"])

    # --- OpenAI, chat completions
    messaggi = [{"role": "system", "content": "Sei un assistente."}, {"role": "user", "content": TESTO},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "c0", "type": "function", "function": {"name": "leggi", "arguments": json.dumps({"percorso": "contatti/Giulia Ferraresi.txt"})}}]},
                {"role": "tool", "tool_call_id": "c0", "content": "Giulia Ferraresi; giulia.ferraresi@nevatek.example; 347 5551234; Aldo Bruschi"},
                {"role": "user", "content": TESTO}]
    stato, grezzo = chiama("/openai/v1/chat/completions", {"model": "x", "messages": messaggi}, {"Authorization": "Bearer chiave-di-prova"})
    arrivato, risposta = VISTO["corpo"], json.loads(grezzo)
    msg = risposta["choices"][0]["message"]
    segna("OpenAI: nulla in chiaro al servizio (compresi argomenti e risultati degli strumenti)", in_chiaro(arrivato) == 0
          and "Ferraresi" not in arrivato["messages"][2]["tool_calls"][0]["function"]["arguments"] and VISTO["chiave"] == "Bearer chiave-di-prova")
    segna("OpenAI: testo e argomenti tornano con i valori veri", all(s in msg["content"] for s in SENSIBILI)
          and all(s in json.loads(msg["tool_calls"][0]["function"]["arguments"])["contenuto"] for s in SENSIBILI))
    stato, grezzo = chiama("/openai/v1/chat/completions", {"model": "x", "messages": messaggi, "stream": True}, {"Authorization": "Bearer chiave-di-prova"})
    ev = eventi(grezzo)
    testo = "".join(c["delta"].get("content") or "" for e in ev for c in e.get("choices", []))
    rate = "".join(a["function"]["arguments"] for e in ev for c in e.get("choices", []) for a in c["delta"].get("tool_calls", []))
    try:
        azione = json.loads(rate)
    except ValueError:
        azione = {}
    segna("OpenAI in streaming: testo e argomenti dell'azione con i valori veri", in_chiaro(VISTO["corpo"]) == 0 and all(s in testo for s in SENSIBILI)
          and all(s in azione.get("contenuto", "") for s in SENSIBILI))

    # --- OpenAI, responses (il formato di Codex)
    stato, grezzo = chiama("/openai/v1/responses", {"model": "x", "stream": True, "instructions": "Sei Codex.", "input": [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": TESTO}]},
        {"type": "function_call", "call_id": "c0", "name": "leggi", "arguments": json.dumps({"percorso": "contatti/Giulia Ferraresi.txt"})},
        {"type": "function_call_output", "call_id": "c0", "output": "Giulia Ferraresi; giulia.ferraresi@nevatek.example; 347 5551234; Aldo Bruschi"},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": TESTO}]}]}, {"Authorization": "Bearer chiave-di-prova"})
    ev = eventi(grezzo)
    testo = "".join(e["delta"] for e in ev if e["type"] == "response.output_text.delta")
    rate = "".join(e["delta"] for e in ev if e["type"] == "response.function_call_arguments.delta")
    finale = next(e for e in ev if e["type"] == "response.completed")["response"]["output"][0]["content"][0]["text"]
    try:
        azione = json.loads(rate)
    except ValueError:
        azione = {}
    segna("OpenAI responses in streaming: nulla in chiaro, testo, argomenti ed evento finale ripristinati", in_chiaro(VISTO["corpo"]) == 0
          and all(s in testo for s in SENSIBILI) and all(s in azione.get("contenuto", "") for s in SENSIBILI) and all(s in finale for s in SENSIBILI))

    # --- il resto
    stato, grezzo = chiama("/anthropic/v1/models")
    segna("richieste senza testo: passano", stato == 200 and json.loads(grezzo)["percorso"] == "/v1/models")
    stato, grezzo = chiama("/anthropic/v1/messages", {"messages": cronologia}, {"x-api-key": "sbagliata"})
    segna("errore del servizio inoltrato com'è", stato == 401 and "authentication_error" in grezzo)
    stato, grezzo = chiama("/servizio-che-non-esiste/v1/messages", {"messages": cronologia})
    segna("indirizzo sconosciuto: rifiutato", stato == 404)
    n = VISTO["n"]
    gw.porta_motore = 1
    stato, grezzo = chiama("/anthropic/v1/messages", {"messages": [{"role": "user", "content": TESTO + " Variante mai vista."}]}, {"x-api-key": "chiave-di-prova"})
    segna("motore che non risponde: richiesta fermata, nulla inoltrato", stato == 503 and VISTO["n"] == n, f"stato {stato}")
    gw.porta_motore = paths.PORTA_MOTORE
    gw.ferma()
    finto.shutdown()
    nuove = [json.loads(r) for r in registro.read_text(encoding="utf-8").splitlines()[righe_prima:]] if registro.exists() else []
    mie = [v for v in nuove if v.get("via") == "gateway"]
    segna("registro: righe «via gateway» senza testi né credenziali", len([v for v in mie if v.get("evento") == "mascherata"]) >= 6
          and in_chiaro(mie) == 0 and "chiave-di-prova" not in json.dumps(mie), f"{len(mie)} righe")
    assert R.RX_SEGNAPOSTO
    print("\nTUTTO OK" if all(esiti) else f"\n{esiti.count(False)} ERRORI")
    sys.exit(0 if all(esiti) else 1)


if __name__ == "__main__":
    main()
