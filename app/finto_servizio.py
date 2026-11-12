# -*- coding: utf-8 -*-
"""Servizio finto per provare il proxy senza account veri: imita il formato delle risposte di
Claude, ChatGPT, delle API e di altri servizi, e ripete nella risposta il testo che ha ricevuto.

GET /visto restituisce l'ultimo corpo ricevuto: serve a verificare che al "servizio" siano
arrivati solo segnaposto.   Uso: python finto_servizio.py [porta=9911]

GET /pagina e' una pagina che fa le stesse richieste dal browser (fetch e XMLHttpRequest): serve a
provare l'estensione (prova_estensione.py).
"""
import json
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VISTO = {"corpo": None, "file": 0}
PAGINA = r"""<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Servizio finto</title></head><body>
<h1>Servizio finto</h1><div id="esito"></div><div id="incollato"></div><textarea id="casella"></textarea>
<div id="chat"></div><div id="scrivi" contenteditable="true" style="border:1px solid #888;min-height:2em"></div><button id="manda" aria-label="Invia messaggio">&gt;</button>
<script>
async function tutto(r){const l=r.body.getReader(),d=new TextDecoder();let t="";for(;;){const {done,value}=await l.read();if(done)break;t+=d.decode(value,{stream:true})}return t}
const eventi=t=>t.split(/\r?\n\r?\n/).map(e=>(e.split("\n").find(r=>r.startsWith("data:"))||"").slice(5).trim()).filter(x=>x&&x!="[DONE]").map(x=>JSON.parse(x));
const BASE=location.protocol=="file:"?"http://localhost:9911":"";
const invia=(p,corpo)=>fetch(BASE+p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(corpo)});
const FORMATI={
 claude:async t=>eventi(await tutto(await invia("/api/organizations/o1/chat_conversations/c1/completion",{prompt:t}))).filter(e=>e.type=="content_block_delta").map(e=>e.delta.text).join(""),
 openai:async t=>eventi(await tutto(await invia("/v1/chat/completions",{messages:[{role:"user",content:t}],stream:true}))).map(e=>e.choices[0].delta.content||"").join(""),
 chatgpt:async t=>{let o="";for(const e of eventi(await tutto(await invia("/backend-api/f/conversation",{messages:[{author:{role:"user"},content:{content_type:"text",parts:[t]}}]})))){if(typeof e.v=="string")o+=e.v;else if(Array.isArray(e.v))for(const x of e.v)if(x.o=="append")o+=x.v}return o},
 cumulativo:async t=>eventi(await tutto(await invia("/generico/cumulativo",{query_str:t}))).pop().text,
 righe:async t=>(await tutto(await invia("/generico/righe",{message:t}))).trim().split("\n").map(r=>JSON.parse(r).result.response.token).join(""),
 prefisso:async t=>(await tutto(await invia("/generico/prefisso",{messageInput:t}))).trim().split("\n").filter(r=>r.startsWith("0:")).map(r=>JSON.parse(r.slice(2))).join(""),
 intera:async t=>(await (await invia("/v1/messages",{messages:[{role:"user",content:t}]})).json()).content[0].text,
 richiesta:async t=>(await (await fetch(new Request("/v1/messages",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({messages:[{role:"user",content:t}]})}))).json()).content[0].text,
 cronologia:async()=>(await (await fetch("/api/organizations/o1/chat_conversations/c1")).json()).chat_messages[0].text,
 gemini:t=>new Promise((ok,no)=>{const x=new XMLHttpRequest();x.open("POST","/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate?bl=1");
   x.setRequestHeader("Content-Type","application/x-www-form-urlencoded;charset=UTF-8");x.onerror=()=>no(new Error("rete"));
   x.onload=()=>{const righe=x.responseText.split("\n").filter(r=>r.startsWith("[["));ok(JSON.parse(JSON.parse(righe.pop())[0][2])[4][0][1][0])};
   x.send("f.req="+encodeURIComponent(JSON.stringify([null,JSON.stringify([[t],null,["c","r","rc"]])]))+"&at=gettone")}),
 file:async()=>{const m=new FormData();m.append("file",new Blob(["contenuto"],{type:"application/pdf"}),"doc.pdf");return (await fetch("/api/organizations/o1/upload",{method:"POST",body:m})).status},
};
async function prova(formato,testo){const t=await FORMATI[formato](testo);document.getElementById("esito").textContent=t;return t}
// Una chat che NON usa la rete della finestra, come le app che consegnano il messaggio al proprio processo principale:
// quello che la "app" legge dalla casella finisce in __inviati (e' cio' che partirebbe) e la "risposta" lo ripete.
window.__inviati=[];
function mandaChat(){const c=document.getElementById("scrivi"),t=c.innerText.trim();if(!t)return;window.__inviati.push(t);
  for(const [classe,testo] of [["mia",t],["sua","Ho ricevuto: "+t]]){const b=document.createElement("div");b.className=classe;b.textContent=testo;document.getElementById("chat").appendChild(b)}c.textContent=""}
document.getElementById("scrivi").addEventListener("keydown",e=>{if(e.key=="Enter"&&!e.shiftKey){e.preventDefault();mandaChat()}});
document.getElementById("manda").addEventListener("click",mandaChat);
// ?subito=N&t=testo : la pagina manda un messaggio nel momento stesso in cui si apre (il caso piu' difficile da proteggere)
const q=new URLSearchParams(location.search);
const SUBITO="Scrivi una mail a Giulia Ferraresi (giulia.ferraresi@nevatek.example, cell. 347 5551234) della Nevatek S.r.l. per confermare l'appuntamento con Aldo Bruschi.";
if(q.get("subito"))fetch("/api/organizations/o1/chat_conversations/c1/completion",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt:q.get("t")||SUBITO,giro:+q.get("subito")})}).then(tutto).then(()=>{document.title="partito"},()=>{document.title="bloccato"});
</script></body></html>"""
INIZIO_GEMINI = ")]}" + "'"


def pezzi(testo, n=7):
    return [testo[i:i + n] for i in range(0, len(testo), n)]


class Gestore(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")   # per la pagina aperta come file locale
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, oggetto):
        corpo = json.dumps(oggetto, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _a_blocchi(self, tipo, unita):
        """Invia ogni unita' spezzata in due blocchi di rete, a meta' di un carattere se capita."""
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for b in unita:
            for parte in (b[:len(b) // 2], b[len(b) // 2:]):
                if parte:
                    self.wfile.write(f"{len(parte):x}\r\n".encode() + parte + b"\r\n")
                    self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")

    def _sse(self, eventi):
        self._a_blocchi("text/event-stream; charset=utf-8", [
            ((f"event: {nome}\n" if nome else "") + "data: " + (dati if isinstance(dati, str) else json.dumps(dati, ensure_ascii=False)) + "\n\n").encode("utf-8")
            for nome, dati in eventi])

    def _righe(self, righe, tipo="text/plain; charset=utf-8"):
        self._a_blocchi(tipo, [(r + "\n").encode("utf-8") for r in righe])

    def do_GET(self):
        if self.path == "/visto":
            self._json(VISTO)
        elif self.path.split("?")[0] == "/pagina":
            corpo = PAGINA.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        elif self.path.startswith("/api/organizations/"):   # cronologia di una conversazione
            self._json({"chat_messages": [{"sender": "human", "text": (VISTO["corpo"] or {}).get("prompt", "")}]})
        else:
            self._json({})

    def do_POST(self):
        binario = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        p = self.path
        if "multipart/" in self.headers.get("Content-Type", ""):   # caricamento di un file
            VISTO["file"] += 1
            self._json({"file": VISTO["file"]})
            return
        grezzo = binario.decode("utf-8")
        if p.startswith("/_/BardChatUi/"):   # Gemini: modulo con JSON dentro JSON, risposta a blocchi con lunghezza
            campi = dict(urllib.parse.parse_qsl(grezzo, keep_blank_values=True))
            interno = json.loads(json.loads(campi["f.req"])[1])
            VISTO["corpo"] = {"prompt": interno[0][0], "at": campi.get("at"), "resto": interno[1:]}
            testo = "Ho ricevuto: " + interno[0][0]
            righe, passo = [INIZIO_GEMINI, ""], max(1, len(testo) // 3)
            for k in range(passo, len(testo) + passo, passo):   # il testo cresce a ogni blocco
                dentro = json.dumps([None, ["c_1", "r_1"], None, None, [["rc_1", [testo[:k]]]]], ensure_ascii=False)
                blocco = json.dumps([["wrb.fr", None, dentro]], ensure_ascii=False)
                righe += [str(len((blocco + "\n").encode("utf-16-le")) // 2 + 1), blocco]
            self._righe(righe, "application/json; charset=utf-8")
            return
        corpo = json.loads(grezzo)
        VISTO["corpo"] = corpo
        if p == "/generico/cumulativo":       # come Perplexity: ogni evento porta tutto il testo fin li'
            testo = "Ho ricevuto: " + corpo["query_str"]
            self._sse([("message", {"text": testo[:k], "final": k >= len(testo)}) for k in range(9, len(testo) + 9, 9)])
        elif p == "/generico/righe":          # come Grok: un oggetto JSON per riga
            testo = "Ho ricevuto: " + corpo["message"]
            self._righe([json.dumps({"result": {"response": {"token": x}}}, ensure_ascii=False) for x in pezzi(testo, 6)], "application/x-ndjson")
        elif p == "/generico/prefisso":       # come Le Chat: righe 0:"pezzo"
            testo = "Ho ricevuto: " + corpo["messageInput"]
            self._righe(["0:" + json.dumps(x, ensure_ascii=False) for x in pezzi(testo, 5)] + ['d:{"finishReason":"stop"}'])
        elif p.startswith("/api/organizations/"):
            testo = "Ho ricevuto: " + corpo["prompt"] + " Fine."
            ev = [("message_start", {"type": "message_start", "message": {"id": "m1"}}),
                  ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})]
            for i, x in enumerate(pezzi(testo)):
                ev.append(("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": x}}))
                if i % 4 == 1:
                    ev.append(("ping", {"type": "ping"}))
            ev += [("content_block_stop", {"type": "content_block_stop", "index": 0}),
                   ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}),
                   ("message_stop", {"type": "message_stop"})]
            self._sse(ev)
        elif p.startswith("/v1/chat/completions"):
            testo = "Ho ricevuto: " + corpo["messages"][-1]["content"]
            ev = [("", {"choices": [{"index": 0, "delta": {"content": x}, "finish_reason": None}]}) for x in pezzi(testo, 5)]
            ev += [("", {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}), ("", "[DONE]")]
            self._sse(ev)
        elif p.startswith("/backend-api/"):
            testo = "Ho ricevuto: " + corpo["messages"][-1]["content"]["parts"][0]
            x = pezzi(testo, 6)
            ev = [("delta", {"p": "", "o": "add", "v": {"message": {"author": {"role": "assistant"}, "content": {"content_type": "text", "parts": [""]}}}}),
                  ("delta", {"p": "/message/content/parts/0", "o": "append", "v": x[0]})]
            ev += [("delta", {"v": y}) for y in x[1:-2]]
            ev += [("delta", {"p": "", "o": "patch", "v": [{"p": "/message/content/parts/0", "o": "append", "v": "".join(x[-2:])},
                                                           {"p": "/message/status", "o": "replace", "v": "finished_successfully"}]}),
                   ("", {"type": "message_stream_complete"}), ("", "[DONE]")]
            self._sse(ev)
        elif p.startswith("/v1/messages"):
            ultimo = corpo["messages"][-1]["content"]
            testo = ultimo if isinstance(ultimo, str) else ultimo[0]["text"]
            self._json({"type": "message", "role": "assistant", "content": [{"type": "text", "text": "Ho ricevuto: " + testo}]})
        else:
            self._json({})


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 9911
    print(f"servizio finto su http://127.0.0.1:{porta}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", porta), Gestore).serve_forever()
