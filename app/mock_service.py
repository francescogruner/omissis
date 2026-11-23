# -*- coding: utf-8 -*-
"""Servizio finto per provare il proxy senza account veri: imita il formato delle risposte di
Claude, ChatGPT, delle API e di altri servizi, e ripete nella risposta il testo che ha ricevuto.

GET /visto restituisce l'ultimo corpo ricevuto: serve a verificare che al "servizio" siano
arrivati solo segnaposto.   Uso: python mock_service.py [porta=9911]

GET /pagina e' una pagina che fa le stesse richieste dal browser (fetch e XMLHttpRequest): serve a
provare l'estensione (e2e_extension.py).

GET /claude-app e' l'«app finta»: manda il messaggio come fa claude.ai dal novembre 2026 (una chiamata in protobuf a
/claudeai-rpc/...ConversationService/PerformAction) ed e' servita con una Content-Security-Policy a nonce, come la pagina
vera. Serve a provare il codice della casella portato nella pagina dal proxy (e2e_inpage.py). Il servizio risponde con i
testi che ha ricevuto: la pagina li mostra, e li' si vede se i valori veri tornano.
"""
import json
import sys
import time
import zlib
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import wire

SEEN = {"body": None, "file": 0, "rpc": None}
PAGE_APP = r"""<!doctype html><html lang="it"><head><meta charset="utf-8"><title>App finta</title>
<script nonce="N0nce">window.__sent = []; window.__code = []; window.__files = []; window.__chatfiles = []; window.__raw = window.__draft = '';</script></head><body>
<h1>App finta</h1><div id="chat"></div>
<textarea id="draft" data-copy-as-text aria-label="Bozza" rows="3" style="width:100%"></textarea>
<button id="copydraft">Copia la bozza</button><button id="copyraw">Copia il messaggio</button>
<div id="write" contenteditable="true" style="border:1px solid #888;min-height:2em"></div><button id="post" aria-label="Invia messaggio">&gt;</button><input type="file" id="chatfile">
<div class="epitaxy-prompt"><div id="codebox" contenteditable="true" style="border:1px dashed #888;min-height:2em"></div><input type="file" id="codefile"></div>
<script nonce="N0nce">
const enc = n => { const o = []; do { const b = n % 128; n = Math.floor(n / 128); o.push(b | (n ? 128 : 0)); } while (n); return o; };
const field = (n, bytes) => [...enc(n * 8 + 2), ...enc(bytes.length), ...bytes];
const utf8 = s => [...new TextEncoder().encode(s)];
async function send(text) {
  const body = new Uint8Array([...field(1, utf8('0199f0aa-7d0c-7c1e-9d59-3f4a6f6a1b2c')), ...field(2, field(1, field(1, utf8(text)))), ...field(3, utf8('it-IT'))]);
  let texts;
  try {
    const r = await fetch('/claudeai-rpc/anthropic.bard.api.v1alpha.ConversationService/PerformAction',
      {method: 'POST', headers: {'content-type': 'application/proto', 'connect-protocol-version': '1'}, body});
    texts = r.ok ? JSON.parse(new TextDecoder().decode(await r.arrayBuffer())).texts : ['', 'ERRORE ' + r.status];
  } catch (e) { texts = ['', 'ERRORE di rete']; }
  const d = document.createElement('div');
  d.className = 'msg';
  d.textContent = texts[1] || '';
  document.getElementById('chat').appendChild(d);
  // la bozza: un campo che l'app tiene nella sua memoria, come quella di un'email in claude.ai. «Copia» copia dalla memoria
  window.__raw = texts[1] || '';
  draft.value = window.__draft = window.__raw;
  window.__sent.push(text);
}
const draft = document.getElementById('draft');
draft.addEventListener('input', () => { window.__draft = draft.value; });
document.getElementById('copydraft').addEventListener('click', () => navigator.clipboard.writeText(window.__draft));
document.getElementById('copyraw').addEventListener('click', () => navigator.clipboard.writeText(window.__raw));
// la zona «Code»: li' il testo serve com'e' a un agente che lavora sui file, e non passa dalla chat
const codebox = document.getElementById('codebox');
codebox.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.defaultPrevented) { e.preventDefault(); window.__code.push(codebox.innerText); codebox.innerText = ''; } });
document.getElementById('codefile').addEventListener('change', e => { for (const f of e.target.files) window.__files.push(f.name); });
document.getElementById('chatfile').addEventListener('change', e => { for (const f of e.target.files) window.__chatfiles.push(f.name); });
const box = document.getElementById('write');
box.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.defaultPrevented) { e.preventDefault(); const t = box.innerText; box.innerText = ''; send(t); } });
document.getElementById('post').addEventListener('click', () => { const t = box.innerText; box.innerText = ''; send(t); });
</script></body></html>"""
FILE = {"last": ""}   # il corpo dell'ultimo caricamento: a parte, perche' /visto deve restare il solo ultimo messaggio
PAGE = r"""<!doctype html><html lang="it"><head><meta charset="utf-8"><title>Servizio finto</title></head><body>
<h1>Servizio finto</h1><div id="outcome"></div><div id="incollato"></div><textarea id="box"></textarea>
<div id="chat"></div><div id="write" contenteditable="true" style="border:1px solid #888;min-height:2em"></div><button id="post" aria-label="Invia messaggio">&gt;</button>
<input type="file" id="allega" multiple><div id="zone" style="border:1px dashed #888;padding:1em">trascina qui un file</div>
<script>
// gli allegati: la "app" legge ogni file che riceve (finisce in __file) e lo carica al servizio, come fanno le chat vere
window.__file=[];window.__first=[];
const b64=async f=>{let s="";const u=new Uint8Array(await f.arrayBuffer());for(let i=0;i<u.length;i+=0x8000)s+=String.fromCharCode.apply(null,u.subarray(i,i+0x8000));return btoa(s)};
async function ricevi(list_name,how){for(const f of list_name){const entry={how,name:f.name,kind:f.type,weight:f.size,text:await f.text(),data:f.size<3e6?await b64(f):""};
  const fd=new FormData();fd.append("file",f,f.name);
  try{entry.loaded=(await fetch("/generic/load",{method:"POST",body:fd})).ok}catch(e){entry.loaded=false}
  window.__file.push(entry)}}
const allega=document.getElementById("allega"),zone=document.getElementById("zone");
allega.addEventListener("input",e=>window.__first.push(...[...e.target.files].map(f=>f.name)));   // cio' che la pagina vede al primo evento
allega.addEventListener("change",e=>ricevi([...e.target.files],"choice"));
zone.addEventListener("dragover",e=>e.preventDefault());
zone.addEventListener("drop",e=>{e.preventDefault();ricevi([...e.dataTransfer.files],"dragging")});
document.getElementById("write").addEventListener("paste",e=>{if(e.clipboardData&&e.clipboardData.files.length){e.preventDefault();ricevi([...e.clipboardData.files],"paste")}});
</script>
<script>
async function everything(r){const l=r.body.getReader(),d=new TextDecoder();let t="";for(;;){const {done,value}=await l.read();if(done)break;t+=d.decode(value,{stream:true})}return t}
const events=t=>t.split(/\r?\n\r?\n/).map(e=>(e.split("\n").find(r=>r.startsWith("data:"))||"").slice(5).trim()).filter(x=>x&&x!="[DONE]").map(x=>JSON.parse(x));
const BASE=location.protocol=="file:"?"http://localhost:9911":"";
const send=(p,body)=>fetch(BASE+p,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
const FORMATI={
 claude:async t=>events(await everything(await send("/api/organizations/o1/chat_conversations/c1/completion",{prompt:t}))).filter(e=>e.type=="content_block_delta").map(e=>e.delta.text).join(""),
 openai:async t=>events(await everything(await send("/v1/chat/completions",{messages:[{role:"user",content:t}],stream:true}))).map(e=>e.choices[0].delta.content||"").join(""),
 chatgpt:async t=>{let o="";for(const e of events(await everything(await send("/backend-api/f/conversation",{messages:[{author:{role:"user"},content:{content_type:"text",parts:[t]}}]})))){if(typeof e.v=="string")o+=e.v;else if(Array.isArray(e.v))for(const x of e.v)if(x.o=="append")o+=x.v}return o},
 cumulative:async t=>events(await everything(await send("/generic/cumulative",{query_str:t}))).pop().text,
 lines:async t=>(await everything(await send("/generic/lines",{message:t}))).trim().split("\n").map(r=>JSON.parse(r).result.response.token).join(""),
 prefix:async t=>(await everything(await send("/generic/prefix",{messageInput:t}))).trim().split("\n").filter(r=>r.startsWith("0:")).map(r=>JSON.parse(r.slice(2))).join(""),
 whole:async t=>(await (await send("/v1/messages",{messages:[{role:"user",content:t}]})).json()).content[0].text,
 request:async t=>(await (await fetch(new Request("/v1/messages",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({messages:[{role:"user",content:t}]})}))).json()).content[0].text,
 history:async()=>(await (await fetch("/api/organizations/o1/chat_conversations/c1")).json()).chat_messages[0].text,
 gemini:t=>new Promise((ok,no)=>{const x=new XMLHttpRequest();x.open("POST","/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate?bl=1");
   x.setRequestHeader("Content-Type","application/x-www-form-urlencoded;charset=UTF-8");x.onerror=()=>no(new Error("network"));
   x.onload=()=>{const lines=x.responseText.split("\n").filter(r=>r.startsWith("[["));ok(JSON.parse(JSON.parse(lines.pop())[0][2])[4][0][1][0])};
   x.send("f.req="+encodeURIComponent(JSON.stringify([null,JSON.stringify([[t],null,["c","r","rc"]])]))+"&at=gettone")}),
 file:async()=>{const m=new FormData();m.append("file",new Blob(["content"],{type:"application/pdf"}),"doc.pdf");return (await fetch("/api/organizations/o1/upload",{method:"POST",body:m})).status},
};
async function test(fmt,text){const t=await FORMATI[fmt](text);document.getElementById("outcome").textContent=t;return t}
// Una chat che NON usa la rete della finestra, come le app che consegnano il messaggio al proprio processo principale:
// quello che la "app" legge dalla casella finisce in __inviati (e' cio' che partirebbe) e la "risposta" lo ripete.
window.__sent=[];
function postChat(){const c=document.getElementById("write"),t=c.innerText.trim();if(!t)return;window.__sent.push(t);
  for(const [cls,text] of [["mia",t],["sua","Ho ricevuto: "+t]]){const b=document.createElement("div");b.className=cls;b.textContent=text;document.getElementById("chat").appendChild(b)}c.textContent=""}
document.getElementById("write").addEventListener("keydown",e=>{if(e.key=="Enter"&&!e.shiftKey){e.preventDefault();postChat()}});
document.getElementById("post").addEventListener("click",postChat);
// ?subito=N&t=testo : la pagina manda un messaggio nel momento stesso in cui si apre (il caso piu' difficile da proteggere)
const q=new URLSearchParams(location.search);
const AT_ONCE="Scrivi una mail a Giulia Ferraresi (giulia.ferraresi@nevatek.example, cell. 347 5551234) della Nevatek S.r.l. per confermare l'appuntamento con Aldo Bruschi.";
if(q.get("at_once"))fetch("/api/organizations/o1/chat_conversations/c1/completion",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt:q.get("t")||AT_ONCE,lap:+q.get("at_once")})}).then(everything).then(()=>{document.title="partito"},()=>{document.title="blocked"});
</script></body></html>"""
START_GEMINI = ")]}" + "'"


def chunks(text, n=7):
    return [text[i:i + n] for i in range(0, len(text), n)]


class Handler(BaseHTTPRequestHandler):
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

    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _to_blocks(self, kind, unit):
        """Invia ogni unita' spezzata in due blocchi di rete, a meta' di un carattere se capita."""
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for b in unit:
            for part in (b[:len(b) // 2], b[len(b) // 2:]):
                if part:
                    self.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
                    self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")

    def _sse(self, events):
        self._to_blocks("text/event-stream; charset=utf-8", [
            ((f"event: {name}\n" if name else "") + "data: " + (data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)) + "\n\n").encode("utf-8")
            for name, data in events])

    def _lines(self, lines, kind="text/plain; charset=utf-8"):
        self._to_blocks(kind, [(r + "\n").encode("utf-8") for r in lines])

    def _open_channel(self, packed):
        """Un canale di eventi che resta aperto (venti secondi: per chi ascolta non finisce), compresso se chiesto. Nel
        proxy non deve fermarsi: l'app di Claude ne tiene uno cosi', e senza resta «senza connessione»."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Transfer-Encoding", "chunked")
        if packed:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        z = zlib.compressobj(wbits=31) if packed else None
        try:
            for i in range(40):
                part = f'event: tick\ndata: {{"n": {i}, "testo": "ciao"}}\n\n'.encode("utf-8")
                if z:
                    part = z.compress(part) + z.flush(zlib.Z_SYNC_FLUSH)
                self.wfile.write(f"{len(part):x}\r\n".encode() + part + b"\r\n")
                self.wfile.flush()
                time.sleep(0.5)
            self.wfile.write(b"0\r\n\r\n")
        except OSError:   # chi ascoltava se n'e' andato
            pass

    def do_GET(self):
        if "/open_channel" in self.path:
            self._open_channel("gz=1" in self.path)
        elif self.path == "/seen_file":
            self._json(FILE)
        elif self.path == "/seen":
            self._json(SEEN)
        elif self.path.split("?")[0] == "/page":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.split("?")[0] in ("/claude-app", "/claude-app/code"):   # il secondo e' la «zona Code» della stessa app
            body = PAGE_APP.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "script-src 'nonce-N0nce' 'strict-dynamic'; object-src 'none'; base-uri 'none'")
            self.send_header("Cache-Control", "private, no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/organizations/"):   # cronologia di una conversazione
            self._json({"chat_messages": [{"sender": "human", "text": (SEEN["body"] or {}).get("prompt", "")}]})
        else:
            self._json({})

    def do_POST(self):
        binary = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        p = self.path
        if "multipart/" in self.headers.get("Content-Type", ""):   # caricamento di un file
            SEEN["file"] += 1
            FILE["last"] = binary.decode("utf-8", errors="replace")[:20000]
            self._json({"file": SEEN["file"]})
            return
        if p.startswith("/claudeai-rpc/"):   # la chiamata in protobuf dell'app finta: risponde con i testi che ha ricevuto
            SEEN["rpc"] = wire.texts(binary)
            # la risposta e' dichiarata binaria, come quelle vere: il proxy non la riscrive, e i valori veri nella pagina
            # li puo' rimettere solo il codice della casella
            body = json.dumps({"texts": SEEN["rpc"] or []}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/proto")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        raw = binary.decode("utf-8")
        if p.startswith("/_/BardChatUi/"):   # Gemini: modulo con JSON dentro JSON, risposta a blocchi con lunghezza
            fields = dict(urllib.parse.parse_qsl(raw, keep_blank_values=True))
            internal = json.loads(json.loads(fields["f.req"])[1])
            SEEN["body"] = {"prompt": internal[0][0], "at": fields.get("at"), "rest": internal[1:]}
            text = "Ho ricevuto: " + internal[0][0]
            lines, step = [START_GEMINI, ""], max(1, len(text) // 3)
            for k in range(step, len(text) + step, step):   # il testo cresce a ogni blocco
                inside = json.dumps([None, ["c_1", "r_1"], None, None, [["rc_1", [text[:k]]]]], ensure_ascii=False)
                block = json.dumps([["wrb.fr", None, inside]], ensure_ascii=False)
                lines += [str(len((block + "\n").encode("utf-16-le")) // 2 + 1), block]
            self._lines(lines, "application/json; charset=utf-8")
            return
        body = json.loads(raw)
        SEEN["body"] = body
        if p == "/generic/cumulative":       # come Perplexity: ogni evento porta tutto il testo fin li'
            text = "Ho ricevuto: " + body["query_str"]
            self._sse([("message", {"text": text[:k], "final": k >= len(text)}) for k in range(9, len(text) + 9, 9)])
        elif p == "/generic/lines":          # come Grok: un oggetto JSON per riga
            text = "Ho ricevuto: " + body["message"]
            self._lines([json.dumps({"result": {"response": {"token": x}}}, ensure_ascii=False) for x in chunks(text, 6)], "application/x-ndjson")
        elif p == "/generic/prefix":       # come Le Chat: righe 0:"pezzo"
            text = "Ho ricevuto: " + body["messageInput"]
            self._lines(["0:" + json.dumps(x, ensure_ascii=False) for x in chunks(text, 5)] + ['d:{"finishReason":"stop"}'])
        elif p.startswith("/api/organizations/"):
            text = "Ho ricevuto: " + body["prompt"] + " Fine."
            ev = [("message_start", {"type": "message_start", "message": {"id": "m1"}}),
                  ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})]
            for i, x in enumerate(chunks(text)):
                ev.append(("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": x}}))
                if i % 4 == 1:
                    ev.append(("ping", {"type": "ping"}))
            ev += [("content_block_stop", {"type": "content_block_stop", "index": 0}),
                   ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}),
                   ("message_stop", {"type": "message_stop"})]
            self._sse(ev)
        elif p.startswith("/v1/chat/completions"):
            text = "Ho ricevuto: " + body["messages"][-1]["content"]
            ev = [("", {"choices": [{"index": 0, "delta": {"content": x}, "finish_reason": None}]}) for x in chunks(text, 5)]
            ev += [("", {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}), ("", "[DONE]")]
            self._sse(ev)
        elif p.startswith("/backend-api/"):
            text = "Ho ricevuto: " + body["messages"][-1]["content"]["parts"][0]
            x = chunks(text, 6)
            ev = [("delta", {"p": "", "o": "add", "v": {"message": {"author": {"role": "assistant"}, "content": {"content_type": "text", "parts": [""]}}}}),
                  ("delta", {"p": "/message/content/parts/0", "o": "append", "v": x[0]})]
            ev += [("delta", {"v": y}) for y in x[1:-2]]
            ev += [("delta", {"p": "", "o": "patch", "v": [{"p": "/message/content/parts/0", "o": "append", "v": "".join(x[-2:])},
                                                           {"p": "/message/status", "o": "replace", "v": "finished_successfully"}]}),
                   ("", {"type": "message_stream_complete"}), ("", "[DONE]")]
            self._sse(ev)
        elif p.startswith("/v1/messages"):
            last = body["messages"][-1]["content"]
            text = last if isinstance(last, str) else last[0]["text"]
            self._json({"type": "message", "role": "assistant", "content": [{"type": "text", "text": "Ho ricevuto: " + text}]})
        else:
            self._json({})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9911
    print(f"servizio finto su http://127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
