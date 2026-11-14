# -*- coding: utf-8 -*-
"""Prova il gateway per gli strumenti da terminale contro un servizio finto che si comporta come le
API di Anthropic e di OpenAI quando le usa un agente: testo, azioni (uso degli strumenti) con gli
argomenti scritti a rate, ragionamenti firmati. Il gateway gira dentro questa prova, su una porta
sua; serve solo il motore acceso (la protezione attiva).

Controlla che al servizio non arrivi nulla in chiaro (nemmeno negli argomenti delle azioni gia'
fatte e nei risultati degli strumenti), che allo strumento tornino i valori veri (anche dentro gli
argomenti delle nuove azioni), che i ragionamenti firmati viaggino identici in entrambi i sensi.
"""
import base64
import gzip
import json
import re
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import agents
import gateway
import paths
import settings
import restore as R

HERE = Path(__file__).resolve().parent
FAKE_PORT, GW_PORT = paths.ENGINE_PORT + 147, paths.ENGINE_PORT + 148
TEXT = ("Scrivi una mail a Giulia Ferraresi (giulia.ferraresi@nevatek.example, cell. 347 5551234) della Nevatek S.r.l. "
         "per confermare l'appuntamento con Aldo Bruschi.")
SENSITIVE = ["Giulia Ferraresi", "giulia.ferraresi@nevatek.example", "347 5551234", "Aldo Bruschi"]
REASONING = {"type": "thinking", "thinking": "L'utente [PERSONA_1] vuole una mail.", "signature": "firma-che-deve-tornare-identica=="}
SEEN = {"body": None, "key": None, "n": 0}
outcomes = []


def chunks(t, n):
    return [t[i:i + n] for i in range(0, len(t), n)]


def last_text(body):
    """L'ultimo testo dell'utente cosi' come e' arrivato al servizio."""
    if "messages" in body:
        c = body["messages"][-1]["content"]
        if isinstance(c, str):
            return c
        return next((b.get("text") or b.get("content") for b in reversed(c) if isinstance(b, dict) and isinstance(b.get("text") or b.get("content"), str)), "")
    inbound = body.get("input")
    return inbound if isinstance(inbound, str) else inbound[-1]["content"][0]["text"]


class Fake(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _post(self, code, kind, body):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("request-id", "req_fake")
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for name, data in events:
            b = ((f"event: {name}\n" if name else "") + "data: " + (data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)) + "\n\n").encode("utf-8")
            for part in (b[:len(b) // 2], b[len(b) // 2:]):
                self.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
                self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")

    def do_GET(self):
        SEEN["get"] = SEEN.get("get", 0) + 1
        self._post(200, "application/json", json.dumps({"data": [{"id": "model-fake"}], "path": self.path}).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
        SEEN.update(body=body, key=self.headers.get("x-api-key") or self.headers.get("Authorization"), n=SEEN["n"] + 1,
                     encoding=self.headers.get("Accept-Encoding"), path=self.path, account=self.headers.get("ChatGPT-Account-ID"))
        # un gateway proprio davanti al servizio: stessi formati, sotto un suo percorso
        route = self.path[4:] if self.path.startswith(("/llm/", "/api/v1/")) else self.path
        if SEEN["key"] in ("wrong", "Bearer sbagliata"):
            return self._post(401, "application/json", b'{"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}')
        received = last_text(body)
        text = "Ho ricevuto: " + received
        mail = re.search(r"\[EMAIL_\d+\]", received)   # il numero dipende da cio' che l'archivio contiene gia'
        arguments = json.dumps({"command": "write_file", "path": "bozze/mail.txt", "content": received, "recipients": [mail.group() if mail else "[EMAIL_1]"]}, ensure_ascii=False)
        stream = bool(body.get("stream"))
        if route.startswith("/v1/messages"):
            if not stream:
                return self._post(200, "application/json", json.dumps({"type": "message", "role": "assistant", "content": [
                    REASONING, {"type": "text", "text": text}, {"type": "tool_use", "id": "tu_1", "name": "write", "input": json.loads(arguments)}]},
                    ensure_ascii=False).encode("utf-8"))
            ev = [("message_start", {"type": "message_start", "message": {"id": "m1"}}),
                  ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}}),
                  ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": REASONING["thinking"]}}),
                  ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": REASONING["signature"]}}),
                  ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                  ("content_block_start", {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}})]
            ev += [("content_block_delta", {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": x}}) for x in chunks(text, 7)]
            ev += [("content_block_stop", {"type": "content_block_stop", "index": 1}),
                   ("content_block_start", {"type": "content_block_start", "index": 2, "content_block": {"type": "tool_use", "id": "tu_1", "name": "write", "input": {}}})]
            ev += [("content_block_delta", {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": x}}) for x in chunks(arguments, 5)]
            ev += [("content_block_stop", {"type": "content_block_stop", "index": 2}), ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use"}}),
                   ("message_stop", {"type": "message_stop"})]
            return self._sse(ev)
        if route.startswith("/v1/chat/completions"):
            if not stream:
                return self._post(200, "application/json", json.dumps({"choices": [{"message": {"role": "assistant", "content": text, "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "write", "arguments": arguments}}]}, "finish_reason": "tool_calls"}]}, ensure_ascii=False).encode("utf-8"))
            ev = [("", {"choices": [{"index": 0, "delta": {"content": x}, "finish_reason": None}]}) for x in chunks(text, 6)]
            ev += [("", {"choices": [{"index": 0, "delta": {"tool_calls": [{"index": 0, "function": {"arguments": x}}]}, "finish_reason": None}]}) for x in chunks(arguments, 5)]
            ev += [("", {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}), ("", "[DONE]")]
            return self._sse(ev)
        if route.startswith("/backend-api/codex/responses"):   # Codex con l'accesso di ChatGPT: l'azione completa sta in output_item.done
            ev = [("response.output_text.delta", {"type": "response.output_text.delta", "delta": x}) for x in chunks(text, 6)]
            ev += [("response.output_text.done", {"type": "response.output_text.done", "text": text})]
            ev += [("response.custom_tool_call_input.delta", {"type": "response.custom_tool_call_input.delta", "delta": x}) for x in chunks(received, 7)]
            ev += [("response.custom_tool_call_input.done", {"type": "response.custom_tool_call_input.done", "input": received}),
                   ("response.output_item.done", {"type": "response.output_item.done", "item": {"type": "function_call", "name": "shell", "call_id": "c1", "arguments": arguments}}),
                   ("response.completed", {"type": "response.completed", "response": {"output": []}})]
            return self._sse(ev)
        if route.startswith("/v1/responses"):
            ev = [("response.output_text.delta", {"type": "response.output_text.delta", "delta": x}) for x in chunks(text, 6)]
            ev += [("response.output_text.done", {"type": "response.output_text.done", "text": text})]
            ev += [("response.function_call_arguments.delta", {"type": "response.function_call_arguments.delta", "delta": x}) for x in chunks(arguments, 5)]
            ev += [("response.function_call_arguments.done", {"type": "response.function_call_arguments.done", "arguments": arguments}),
                   ("response.completed", {"type": "response.completed", "response": {"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}})]
            return self._sse(ev)
        self._post(404, "application/json", b"{}")


def call(path, body=None, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{GW_PORT}{path}", data=json.dumps(body).encode("utf-8") if body is not None else None,
                                  headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read().decode("utf-8")


def events(raw):
    out = []
    for block in raw.split("\n\n"):
        line = next((x for x in block.split("\n") if x.startswith("data:")), None)
        if line and line[5:].strip() != "[DONE]":
            out.append(json.loads(line[5:]))
    return out


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(f"{'OK    ' if ok else 'ERRORE'} {name}" + (f"   {note}" if note else ""), flush=True)


def reveal(obj):
    t = json.dumps(obj, ensure_ascii=False)
    return sum(s in t for s in SENSITIVE)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    log = paths.DATA / "activity.jsonl"
    lines_before = len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0
    fake = ThreadingHTTPServer(("127.0.0.1", FAKE_PORT), Fake)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    gw = gateway.Gateway(GW_PORT, upstream=f"http://127.0.0.1:{FAKE_PORT}").launch()
    system = "Sei un assistente che lavora per conto di Giulia Ferraresi. " + "Rispondi sempre in italiano e con precisione. " * 6
    history = [
        {"role": "user", "content": [{"type": "text", "text": TEXT}]},
        {"role": "assistant", "content": [dict(REASONING), {"type": "text", "text": "Leggo il file dei contatti."},
                                         {"type": "tool_use", "id": "tu_0", "name": "read", "input": {"path": "contatti/Giulia Ferraresi.txt", "lines": 20}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_0", "content": "Giulia Ferraresi; giulia.ferraresi@nevatek.example; 347 5551234; referente Aldo Bruschi"},
                                     {"type": "text", "text": TEXT}]},
    ]

    # --- Anthropic, risposta intera
    status, raw = call("/anthropic/v1/messages?beta=true", {"model": "x", "system": system, "messages": history, "max_tokens": 100}, {"x-api-key": "chiave-di-prova"})
    arrived = SEEN["body"]
    response = json.loads(raw)
    mark("Anthropic: nulla in chiaro al servizio (testo, sistema, azioni fatte, risultati degli strumenti)", status == 200 and reveal(arrived) == 0
          and "[PERSONA_" in json.dumps(arrived), f"in chiaro {reveal(arrived)}")
    mark("Anthropic: l'argomento dell'azione già fatta è stato mascherato", "Ferraresi" not in arrived["messages"][1]["content"][2]["input"]["path"]
          and arrived["messages"][1]["content"][2]["input"]["lines"] == 20)
    mark("Anthropic: il ragionamento firmato arriva al servizio identico", arrived["messages"][1]["content"][0] == REASONING)
    mark("Anthropic: credenziale inoltrata, risposta non compressa", SEEN["key"] == "chiave-di-prova" and SEEN["encoding"] == "identity")
    text = next(b["text"] for b in response["content"] if b["type"] == "text")
    action = next(b["input"] for b in response["content"] if b["type"] == "tool_use")
    mark("Anthropic: testo e argomenti della nuova azione tornano con i valori veri", all(s in text for s in SENSITIVE) and all(s in action["content"] for s in SENSITIVE)
          and action["recipients"] == ["giulia.ferraresi@nevatek.example"], f"testo {sum(s in text for s in SENSITIVE)}/4")
    mark("Anthropic: il ragionamento firmato torna allo strumento identico", response["content"][0] == REASONING)

    # --- Anthropic, risposta mentre arriva
    status, raw = call("/anthropic/v1/messages", {"model": "x", "system": [{"type": "text", "text": "Sei Claude Code."}, {"type": "text", "text": system}],
                                                      "messages": history, "stream": True}, {"x-api-key": "chiave-di-prova"})
    ev = events(raw)
    text = "".join(e["delta"].get("text", "") for e in ev if e.get("type") == "content_block_delta")
    rate = "".join(e["delta"].get("partial_json", "") for e in ev if e.get("type") == "content_block_delta")
    thinking = "".join(e["delta"].get("thinking", "") for e in ev if e.get("type") == "content_block_delta")
    signature = "".join(e["delta"].get("signature", "") for e in ev if e.get("type") == "content_block_delta")
    try:
        action = json.loads(rate)
    except ValueError:
        action = {}
    mark("Anthropic in streaming: nulla in chiaro al servizio, riga di identità lasciata com'è", reveal(SEEN["body"]) == 0
          and SEEN["body"]["system"][0]["text"] == "Sei Claude Code.")
    mark("Anthropic in streaming: testo ripristinato", all(s in text for s in SENSITIVE) and "[PERSONA_" not in text)
    mark("Anthropic in streaming: argomenti dell'azione leggibili e con i valori veri", all(s in action.get("content", "") for s in SENSITIVE)
          and action.get("recipients") == ["giulia.ferraresi@nevatek.example"])
    mark("Anthropic in streaming: ragionamento e firma non toccati", thinking == REASONING["thinking"] and signature == REASONING["signature"])

    # --- OpenAI, chat completions
    messages = [{"role": "system", "content": "Sei un assistente."}, {"role": "user", "content": TEXT},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "c0", "type": "function", "function": {"name": "read", "arguments": json.dumps({"path": "contatti/Giulia Ferraresi.txt"})}}]},
                {"role": "tool", "tool_call_id": "c0", "content": "Giulia Ferraresi; giulia.ferraresi@nevatek.example; 347 5551234; Aldo Bruschi"},
                {"role": "user", "content": TEXT}]
    status, raw = call("/openai/v1/chat/completions", {"model": "x", "messages": messages}, {"Authorization": "Bearer chiave-di-prova"})
    arrived, response = SEEN["body"], json.loads(raw)
    msg = response["choices"][0]["message"]
    mark("OpenAI: nulla in chiaro al servizio (compresi argomenti e risultati degli strumenti)", reveal(arrived) == 0
          and "Ferraresi" not in arrived["messages"][2]["tool_calls"][0]["function"]["arguments"] and SEEN["key"] == "Bearer chiave-di-prova")
    mark("OpenAI: testo e argomenti tornano con i valori veri", all(s in msg["content"] for s in SENSITIVE)
          and all(s in json.loads(msg["tool_calls"][0]["function"]["arguments"])["content"] for s in SENSITIVE))
    status, raw = call("/openai/v1/chat/completions", {"model": "x", "messages": messages, "stream": True}, {"Authorization": "Bearer chiave-di-prova"})
    ev = events(raw)
    text = "".join(c["delta"].get("content") or "" for e in ev for c in e.get("choices", []))
    rate = "".join(a["function"]["arguments"] for e in ev for c in e.get("choices", []) for a in c["delta"].get("tool_calls", []))
    try:
        action = json.loads(rate)
    except ValueError:
        action = {}
    mark("OpenAI in streaming: testo e argomenti dell'azione con i valori veri", reveal(SEEN["body"]) == 0 and all(s in text for s in SENSITIVE)
          and all(s in action.get("content", "") for s in SENSITIVE))

    # --- OpenAI, responses (il formato di Codex)
    status, raw = call("/openai/v1/responses", {"model": "x", "stream": True, "instructions": "Sei Codex.", "input": [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": TEXT}]},
        {"type": "function_call", "call_id": "c0", "name": "read", "arguments": json.dumps({"path": "contatti/Giulia Ferraresi.txt"})},
        {"type": "function_call_output", "call_id": "c0", "output": "Giulia Ferraresi; giulia.ferraresi@nevatek.example; 347 5551234; Aldo Bruschi"},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": TEXT}]}]}, {"Authorization": "Bearer chiave-di-prova"})
    ev = events(raw)
    text = "".join(e["delta"] for e in ev if e["type"] == "response.output_text.delta")
    rate = "".join(e["delta"] for e in ev if e["type"] == "response.function_call_arguments.delta")
    final = next(e for e in ev if e["type"] == "response.completed")["response"]["output"][0]["content"][0]["text"]
    try:
        action = json.loads(rate)
    except ValueError:
        action = {}
    mark("OpenAI responses in streaming: nulla in chiaro, testo, argomenti ed evento finale ripristinati", reveal(SEEN["body"]) == 0
          and all(s in text for s in SENSITIVE) and all(s in action.get("content", "") for s in SENSITIVE) and all(s in final for s in SENSITIVE)
          and SEEN["path"] == "/v1/responses" and SEEN["account"] is None)

    # --- Codex con l'accesso di ChatGPT (abbonamento): stesso formato, ma va all'indirizzo di ChatGPT e non a quello delle chiavi
    def token(claims):
        b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode("utf-8")).decode("ascii").rstrip("=")   # noqa: E731
        return f"Bearer {b({'alg': 'none'})}.{b(claims)}.firma-finta"
    subscription = token({"https://api.openai.com/auth": {"chatgpt_account_id": "account-di-prova-123"}})
    codex = {"model": "x", "stream": True, "instructions": "Sei Codex.", "input": [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": TEXT}]},
        {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Devo scrivere a Giulia Ferraresi."}], "encrypted_content": "cifrato-che-non-si-tocca=="},
        {"type": "custom_tool_call", "call_id": "p0", "name": "apply_patch", "input": "*** Add File: contatti.txt\n+Aldo Bruschi 347 5551234"},
        {"type": "custom_tool_call_output", "call_id": "p0", "output": "scritto contatti.txt per Aldo Bruschi"},
        {"type": "local_shell_call", "call_id": "s0", "action": {"type": "exec", "command": ["grep", "Giulia Ferraresi", "contatti.txt"]}},
        {"type": "function_call_output", "call_id": "s0", "output": [{"type": "input_text", "text": "Giulia Ferraresi; giulia.ferraresi@nevatek.example"}]},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": TEXT}]}]}
    status, raw = call("/openai/v1/responses", codex, {"Authorization": subscription})
    ev, arrived = events(raw), SEEN["body"]
    text = "".join(e["delta"] for e in ev if e["type"] == "response.output_text.delta")
    patch = "".join(e["delta"] for e in ev if e["type"] == "response.custom_tool_call_input.delta")
    try:
        action = json.loads(next(e for e in ev if e["type"] == "response.output_item.done")["item"]["arguments"])
    except (ValueError, StopIteration):
        action = {}
    mark("Codex in abbonamento: riconosciuto dal gettone e mandato all'indirizzo di ChatGPT, con l'account", status == 200
          and SEEN["path"] == "/backend-api/codex/responses" and SEEN["account"] == "account-di-prova-123" and SEEN["key"] == subscription, f"{status} {SEEN['path']}")
    mark("Codex: nulla in chiaro (messaggi, modifiche ai file, comandi eseguiti, risultati, riassunto del ragionamento)", reveal(arrived) == 0
          and arrived["input"][1]["encrypted_content"] == "cifrato-che-non-si-tocca==" and arrived["instructions"] == "Sei Codex."
          and "[PERSONA_" in arrived["input"][2]["input"] and "[PERSONA_" in arrived["input"][4]["action"]["command"][1], f"in chiaro {reveal(arrived)}")
    mark("Codex: testo, modifica al file e azione completa tornano con i valori veri", all(s in text for s in SENSITIVE) and all(s in patch for s in SENSITIVE)
          and all(s in action.get("content", "") for s in SENSITIVE))
    status, raw = call("/codex/responses", codex, {"Authorization": "Bearer gettone-opaco", "chatgpt-account-id": "account-di-prova-456"})
    mark("Codex puntato sull'indirizzo dedicato: stessa strada", status == 200 and SEEN["path"] == "/backend-api/codex/responses"
          and SEEN["account"] == "account-di-prova-456" and reveal(SEEN["body"]) == 0)
    # l'azione completa porta gli argomenti come JSON dentro una stringa: un valore con virgolette, barre e a capo non deve romperlo
    hard = 'Aldo "il Rosso" Bruschi\\ufficio\nsede'
    stream = R.SSEStream(agents.OpenAIAgent(), {"[PERSONA_1]": hard}.get)
    out = b"".join(stream(("data: " + json.dumps({"type": "response.output_item.done", "item": {"type": "function_call", "arguments": json.dumps(
        {"path": "[PERSONA_1]", "note": ["per [PERSONA_1]"]})}}) + "\n\n").encode("utf-8")) + stream(b"")).decode("utf-8")
    try:
        inner = json.loads(json.loads(out[5:])["item"]["arguments"])
    except ValueError:
        inner = {}
    mark("argomenti di un'azione con un valore «difficile»: il JSON resta valido", inner == {"path": hard, "note": ["per " + hard]})

    # --- chi ha gia' un proprio gateway lo tiene: Omissis gli sta davanti
    before = settings.FILE.read_bytes() if settings.FILE.exists() else None
    settings.write({**settings.read(), "gateway_upstreams": {"anthropic": "https://gateway.azienda.example/llm/", "openai": "https://gateway.azienda.example/api/v1",
                                                               "codex": "https://altrove.example", "non valido": "x", "deepseek": "ftp://no"}})
    kept = settings.read()["gateway_upstreams"]
    status, raw = call("/anthropic/v1/messages", {"model": "x", "max_tokens": 100, "messages": [{"role": "user", "content": TEXT}]}, {"x-api-key": "chiave-di-prova"})
    path_a, clear_a = SEEN["path"], reveal(SEEN["body"])
    status2, raw = call("/openai/v1/chat/completions", {"model": "x", "messages": [{"role": "user", "content": TEXT}]}, {"Authorization": "Bearer chiave-di-prova"})
    path_o, clear_o = SEEN["path"], reveal(SEEN["body"])
    mark("gateway proprio: le richieste vanno al suo indirizzo, già mascherate, senza ripetere /v1", status == 200 and status2 == 200 and path_a == "/llm/v1/messages"
          and path_o == "/api/v1/chat/completions" and clear_a == 0 and clear_o == 0 and all(s in json.loads(raw)["choices"][0]["message"]["content"] for s in SENSITIVE)
          and kept == {"anthropic": "https://gateway.azienda.example/llm", "openai": "https://gateway.azienda.example/api/v1"}, f"{path_a} · {path_o} · {sorted(kept)}")
    status, raw = call("/openai/v1/responses", codex, {"Authorization": subscription})
    mark("l'accesso in abbonamento non va mai al gateway proprio: sempre a ChatGPT", status == 200 and SEEN["path"] == "/backend-api/codex/responses")
    # --- un gruppo di dati spento a mano (Impostazioni > Cosa sostituire): quei dati partono in chiaro, tutti gli altri no
    technical = TEXT + " Il server SRV-ALPI-04 (indirizzo 10.20.30.40) non risponde al ping."
    ask = lambda: call("/anthropic/v1/messages", {"model": "x", "max_tokens": 100, "messages": [{"role": "user", "content": technical}]}, {"x-api-key": "chiave-di-prova"})   # noqa: E731
    ask()
    with_all = json.dumps(SEEN["body"], ensure_ascii=False)
    settings.write({**settings.read(), "groups_off": ["it", "records", "gruppo-inventato", "people"]})
    chosen = settings.read()["groups_off"]
    status, raw = ask()
    reduced = json.dumps(SEEN["body"], ensure_ascii=False)
    mark("gruppo «dati informatici» spento: indirizzi e nomi di server partono, persone e contatti restano sostituiti", status == 200
          and "10.20.30.40" not in with_all and "10.20.30.40" in reduced and "SRV-ALPI-04" in reduced and reveal(SEEN["body"]) == 0 and "[PERSONA_" in reduced
          and chosen == ["it", "records"], f"spenti {chosen}")
    # --- le caselle generiche (info@...) sono un dato dell'azienda: seguono il gruppo «aziende», le caselle personali mai
    mails = TEXT + " Per i preventivi scrivere a info@nevatek.example o ad amministrazione.vendite@nevatek.example; privato: info@gmail.com."
    ask = lambda: call("/anthropic/v1/messages", {"model": "x", "max_tokens": 100, "messages": [{"role": "user", "content": mails}]}, {"x-api-key": "chiave-di-prova"})   # noqa: E731
    settings.write({**settings.read(), "groups_off": []})
    ask()
    with_all = json.dumps(SEEN["body"], ensure_ascii=False)
    settings.write({**settings.read(), "groups_off": ["organizations"]})
    status, raw = ask()
    reduced = json.dumps(SEEN["body"], ensure_ascii=False)
    mark("gruppo «aziende» spento: nome dell'azienda e caselle generiche in chiaro; caselle personali e di servizi per privati sempre sostituite",
          status == 200 and "info@nevatek.example" not in with_all and "amministrazione.vendite@nevatek.example" not in with_all
          and "info@nevatek.example" in reduced and "amministrazione.vendite@nevatek.example" in reduced and "Nevatek" in reduced
          and "giulia.ferraresi@nevatek.example" not in reduced and "info@gmail.com" not in reduced and "Giulia Ferraresi" not in reduced
          and settings.role_mailbox("Ufficio.Acquisti2@azienda.example") and not settings.role_mailbox("mario.rossi@azienda.example")
          and not settings.role_mailbox("info.rossi@azienda.example") and not settings.role_mailbox("info@libero.it"))
    if before is None:
        settings.FILE.unlink()
    else:
        settings.FILE.write_bytes(before)
    settings._cache.update(mtime=None, data=None)

    # --- un collegamento WebSocket non si saprebbe controllare: rifiutato, lo strumento ripiega sulle richieste normali
    n, gets = SEEN["n"], SEEN.get("get", 0)
    req = urllib.request.Request(f"http://127.0.0.1:{GW_PORT}/openai/v1/responses", headers={"Upgrade": "websocket", "Connection": "Upgrade", "Authorization": subscription})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status = r.status
    except urllib.error.HTTPError as ex:
        status = ex.code
    mark("WebSocket: rifiutato, nulla inoltrato", status == 426 and SEEN["n"] == n and SEEN.get("get", 0) == gets, f"stato {status}")

    # --- il resto
    status, raw = call("/anthropic/v1/models")
    mark("richieste senza testo: passano", status == 200 and json.loads(raw)["path"] == "/v1/models")
    status, raw = call("/anthropic/v1/messages", {"messages": history}, {"x-api-key": "wrong"})
    mark("errore del servizio inoltrato com'è", status == 401 and "authentication_error" in raw)
    status, raw = call("/servizio-che-non-esiste/v1/messages", {"messages": history})
    mark("indirizzo sconosciuto: rifiutato", status == 404)

    # --- richiesta compressa (alcuni strumenti lo fanno): va aperta e mascherata; se non si sa aprire, non parte
    def packed(encoding, data):
        req = urllib.request.Request(f"http://127.0.0.1:{GW_PORT}/anthropic/v1/messages", data=data,
                                      headers={"Content-Type": "application/json", "Content-Encoding": encoding, "x-api-key": "chiave-di-prova"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status
        except urllib.error.HTTPError as ex:
            return ex.code
    message = json.dumps({"model": "x", "messages": [{"role": "user", "content": TEXT}], "max_tokens": 100}).encode("utf-8")
    status = packed("gzip", gzip.compress(message))
    mark("richiesta compressa (gzip): aperta e mascherata", status == 200 and reveal(SEEN["body"]) == 0 and "[PERSONA_" in json.dumps(SEEN["body"]),
          f"stato {status} · in chiaro {reveal(SEEN['body'])}")
    import zstandard
    status = packed("zstd", zstandard.ZstdCompressor().compress(message))
    mark("richiesta compressa (zstd, come fa Codex): aperta e mascherata", status == 200 and reveal(SEEN["body"]) == 0 and "[PERSONA_" in json.dumps(SEEN["body"]),
          f"stato {status}")
    # --- le istruzioni che lo strumento inserisce a metà conversazione sono contesto tecnico: le parole del mestiere restano
    environment = "# Environment\nYou are Claude, running inside Claude Code by Anthropic. Use the Bash tool and the Git tool when needed. " * 4
    status, raw = call("/anthropic/v1/messages", {"model": "x", "max_tokens": 100, "messages": [{"role": "system", "content": environment},
                                                                                              {"role": "user", "content": TEXT}]}, {"x-api-key": "chiave-di-prova"})
    arrived = SEEN["body"]
    mark("Anthropic: istruzioni a metà conversazione lasciate leggibili, dati dell'utente mascherati", status == 200 and arrived["messages"][0]["content"] == environment
          and reveal(arrived) == 0 and "[PERSONA_" in json.dumps(arrived["messages"][1]), f"stato {status} · in chiaro {reveal(arrived)}")
    n = SEEN["n"]
    status = packed("compressione-sconosciuta", message)
    mark("richiesta compressa in un modo sconosciuto: fermata, nulla inoltrato", status == 415 and SEEN["n"] == n, f"stato {status}")
    n = SEEN["n"]
    gw.engine_port = 1
    status, raw = call("/anthropic/v1/messages", {"messages": [{"role": "user", "content": TEXT + " Variante mai vista."}]}, {"x-api-key": "chiave-di-prova"})
    mark("motore che non risponde: richiesta fermata, nulla inoltrato", status == 503 and SEEN["n"] == n, f"stato {status}")
    gw.engine_port = paths.ENGINE_PORT
    gw.stop()
    fake.shutdown()
    new_ones = [json.loads(r) for r in log.read_text(encoding="utf-8").splitlines()[lines_before:]] if log.exists() else []
    my = [v for v in new_ones if v.get("via") == "gateway"]
    mark("registro: righe «via gateway» senza testi né credenziali", len([v for v in my if v.get("event") == "masked"]) >= 6
          and reveal(my) == 0 and "chiave-di-prova" not in json.dumps(my), f"{len(my)} righe")
    assert R.RX_PLACEHOLDER
    print("\nTUTTO OK" if all(outcomes) else f"\n{outcomes.count(False)} ERRORI")
    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
