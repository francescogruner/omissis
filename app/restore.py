# -*- coding: utf-8 -*-
"""Ripristino dei segnaposto nelle risposte e adattatori per i servizi di chat.

Solo libreria standard: si prova senza proxy.

Un adattatore sa tre cose di un servizio:
  richiesta(percorso, tipo, testo)  dove sta il testo dell'utente nella richiesta
  delta(evento)                     dove sta il pezzo di testo in un evento della risposta in streaming
  flusso(...)                       come riscrivere la risposta mentre arriva
"""
import copy
import json
import re
import urllib.parse

RX_PLACEHOLDER = re.compile(r"\[([A-Z][A-Z_]{1,22})_(\d{1,7})\]")
# coda di testo che potrebbe essere l'inizio di un segnaposto non ancora arrivato per intero
RX_START = re.compile(r"\[(?:[A-Z][A-Z_]{0,23}\d{0,7})?")
_COMPACT = dict(ensure_ascii=False, separators=(",", ":"))


def restore(text, search):
    """Sostituisce i segnaposto completi. cerca(segnaposto) -> valore oppure None."""
    return RX_PLACEHOLDER.sub(lambda m: v if (v := search(m.group())) is not None else m.group(), text)


def restore_json(raw, search):
    """Come ripristina, ma su JSON non interpretato: il valore viene inserito gia' con le sequenze di escape."""
    def f(m):
        v = search(m.group())
        return m.group() if v is None else json.dumps(v, ensure_ascii=False)[1:-1]
    return RX_PLACEHOLDER.sub(f, raw)


class Stream:
    """Testo che arriva a pezzi: trattiene la coda che potrebbe essere un segnaposto spezzato
    ("[PERS" + "ONA_1]") e la rilascia appena e' completa o si capisce che non lo e'."""

    def __init__(self, search):
        self.search, self.rest = search, ""

    def passthrough(self, chunk, end=False):
        t = self.rest + chunk
        self.rest = ""
        i = t.rfind("[")
        if not end and i != -1 and RX_START.fullmatch(t, i):
            self.rest, t = t[i:], t[:i]
        return restore(t, self.search)


class Leaves:
    """Ripristino su un oggetto JSON qualsiasi, senza sapere quale campo porta il testo: lavora su
    tutte le stringhe, ricordando per ciascun percorso la coda trattenuta. Capisce da solo se il
    servizio manda pezzi nuovi o ogni volta il testo intero, ed entra nelle stringhe che
    contengono a loro volta JSON."""

    def __init__(self, search, entire=False):
        self.search, self.entire = search, entire
        self.streams, self.prev, self.changed = {}, {}, False

    @property
    def waiting(self):
        return any(f.rest for f in self.streams.values())

    def apply(self, node, path=()):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, (str, dict, list)):
                    node[k] = self.apply(v, path + (k,))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                if isinstance(v, (str, dict, list)):
                    node[i] = self.apply(v, path + ("*",))
        elif isinstance(node, str):
            return self._string(node, path)
        return node

    def _string(self, s, path):
        if len(s) > 1 and s[0] in "[{":
            try:
                internal = json.loads(s)
            except ValueError:
                internal = None
            if isinstance(internal, (dict, list)):
                before, self.changed = self.changed, False
                fresh = self.apply(internal, path + ("<json>",))
                mod, self.changed = self.changed, before or self.changed
                return json.dumps(fresh, **_COMPACT) if mod else s
        if self.entire:
            out = restore(s, self.search) if "[" in s else s
        else:
            f = self.streams.get(path)
            if f is None:
                if "[" not in s:
                    return s
                f = self.streams[path] = Stream(self.search)
            if f.rest and s.startswith(self.prev.get(path, "\0")):
                f.rest = ""   # il servizio rimanda ogni volta tutto il testo: la coda trattenuta e' gia' dentro
            out = f.passthrough(s)
            if f.rest:
                self.prev[path] = s
        if out != s:
            self.changed = True
        return out


def restore_object(obj, search):
    return Leaves(search, entire=True).apply(obj)


# ------------------------------------------------------------------ adattatori

def _keys(node, names, out, prof=0):
    """Tutti i (contenitore, chiave) il cui nome e' in `nomi` e il cui valore e' una stringa."""
    if prof > 8:
        return out
    if isinstance(node, dict):
        for k, v in node.items():
            if k in names and isinstance(v, str):
                out.append((node, k))
            elif isinstance(v, (dict, list)):
                _keys(v, names, out, prof + 1)
    elif isinstance(node, list):
        for v in node:
            if isinstance(v, (dict, list)):
                _keys(v, names, out, prof + 1)
    return out


def _blocks(content, container, key, out):
    """Contenuto di un messaggio in stile API: stringa, oppure lista di blocchi con testo."""
    if isinstance(content, str):
        out.append((container, key))
    elif isinstance(content, list):
        for b in content:
            if isinstance(b, dict):
                if isinstance(b.get("text"), str):
                    out.append((b, "text"))
                if b.get("type") == "tool_result":
                    _blocks(b.get("content"), b, "content", out)


class Unpack:
    """Apre a pezzi una risposta compressa che arriva a pezzi (gzip, deflate, br, zstd) e passa il testo a «then», lo stream
    che rimette le etichette. ValueError se la compressione non e' tra quelle note: chi chiama lascia passare la risposta
    com'e'."""

    def __init__(self, coding, then):
        import zlib
        self.then = then
        try:
            if coding in ("gzip", "x-gzip"):
                self._feed = zlib.decompressobj(wbits=31).decompress
            elif coding == "deflate":
                self._feed = zlib.decompressobj().decompress
            elif coding == "br":
                import brotli
                d = brotli.Decompressor()
                self._feed = getattr(d, "process", None) or d.decompress
            elif coding == "zstd":
                import zstandard
                self._feed = zstandard.ZstdDecompressor().decompressobj().decompress
            else:
                raise ValueError(coding)
        except ImportError as ex:
            raise ValueError(coding) from ex

    def __call__(self, data):
        if not data:
            return self.then(b"")
        clear = self._feed(data)
        return self.then(clear) if clear else b""


class Adapter:
    name = "?"

    def fields(self, path, body):
        return []

    def delta(self, ev):
        return []

    def end(self, ev):
        return False

    def intact(self, ev):
        """Eventi della risposta da non toccare affatto (es. ragionamenti firmati, che devono tornare identici)."""
        return False

    def request(self, path, kind, text):
        """-> (riferimenti al testo, funzione che ricompone il corpo, corpo interpretato) oppure None."""
        if "json" not in kind:
            return None
        try:
            body = json.loads(text)
        except ValueError:
            return None
        return self.fields(path, body), (lambda: json.dumps(body, ensure_ascii=False)), body

    def in_streaming(self, kind, path):
        return "text/event-stream" in kind

    def stream(self, search, preload=None):
        return SSEStream(self, search, preload)

    def whole(self, kind, text, search):
        """Riscrive una risposta arrivata per intero."""
        if "event-stream" in kind:
            return self.stream(search).everything(text.encode("utf-8")).decode("utf-8")
        try:
            return json.dumps(restore_object(json.loads(text), search), ensure_ascii=False)
        except ValueError:
            return restore_json(text, search)


class Claude(Adapter):
    """claude.ai nel browser e in Claude Desktop (stessa API privata)."""
    name = "claude"
    FIELDS = {"prompt", "message_content", "extracted_content"}
    # richieste del sito che non sono messaggi (misure d'uso, controlli): non vanno contate come «formato non letto»
    # (dal 21/11/2026 anche quelle di servizio dell'app desktop: dispositivi, connettori, stato dei rami del codice)
    QUIET = re.compile(r"/event_logging/|/browser-reports|/cdn-cgi/|/client-health/|/cowork/|/remote_devices|/v1/toolbox/|/v1/code/")

    def fields(self, path, body):
        return _keys(body, self.FIELDS, [])

    def delta(self, ev):
        if isinstance(ev, dict):
            d = ev.get("delta")
            if ev.get("type") == "content_block_delta" and isinstance(d, dict):
                return [(d, k) for k in ("text", "thinking") if isinstance(d.get(k), str)]
            if isinstance(ev.get("completion"), str):
                return [(ev, "completion")]
        return []

    def end(self, ev):
        return isinstance(ev, dict) and ev.get("type") in ("content_block_stop", "message_delta", "message_stop", "message_limit")


class Anthropic(Claude):
    """API ufficiale di Anthropic (/v1/messages): per i client che usano l'API."""
    name = "anthropic"

    def fields(self, path, body):
        out = []
        if "/v1/messages" in path and isinstance(body, dict):
            for m in body.get("messages") or []:
                if isinstance(m, dict):
                    _blocks(m.get("content"), m, "content", out)
        return out


class OpenAI(Adapter):
    """API di OpenAI e compatibili (/chat/completions e /responses): DeepSeek, Mistral, Groq, OpenRouter..."""
    name = "openai"

    def fields(self, path, body):
        out = []
        if not isinstance(body, dict):
            return out
        if "/chat/completions" in path:
            for m in body.get("messages") or []:
                if isinstance(m, dict) and m.get("role") != "system" and m.get("role") != "developer":
                    _blocks(m.get("content"), m, "content", out)
        elif "/responses" in path:
            if isinstance(body.get("input"), str):
                out.append((body, "input"))
            for m in body.get("input") if isinstance(body.get("input"), list) else []:
                if isinstance(m, dict) and m.get("role") not in ("system", "developer"):
                    _blocks(m.get("content"), m, "content", out)
                    if isinstance(m.get("output"), str):
                        out.append((m, "output"))
        return out

    def delta(self, ev):
        out = []
        if isinstance(ev, dict):
            for c in ev.get("choices") or []:
                d = c.get("delta") if isinstance(c, dict) else None
                if isinstance(d, dict) and isinstance(d.get("content"), str):
                    out.append((d, "content"))
            if ev.get("type") == "response.output_text.delta" and isinstance(ev.get("delta"), str):
                out.append((ev, "delta"))
        return out

    def end(self, ev):
        if not isinstance(ev, dict):
            return False
        return ev.get("type") in ("response.output_text.done", "response.completed") or \
            any(isinstance(c, dict) and c.get("finish_reason") for c in ev.get("choices") or [])


class ChatGPT(Adapter):
    """chatgpt.com nel browser e nell'app desktop (API privata, a "patch" successive)."""
    name = "chatgpt"

    def __init__(self):
        self.text = False   # l'ultimo percorso indicato era il testo del messaggio

    def fields(self, path, body):
        out = []
        if isinstance(body, dict):
            for m in body.get("messages") or []:
                parts = (m.get("content") or {}).get("parts") if isinstance(m, dict) and isinstance(m.get("content"), dict) else None
                if isinstance(parts, list) and (m.get("author") or {}).get("role", "user") == "user":
                    out += [(parts, i) for i, p in enumerate(parts) if isinstance(p, str)]
        return out

    @staticmethod
    def _is_text(p):
        return isinstance(p, str) and re.search(r"/content/(parts/\d+|text)$", p) is not None

    def delta(self, ev):
        if not isinstance(ev, dict) or "v" not in ev:
            return []
        if "p" in ev:
            self.text = self._is_text(ev["p"]) and ev.get("o", "append") == "append"
        if isinstance(ev["v"], str):
            return [(ev, "v")] if self.text else []
        if isinstance(ev["v"], list):   # piu' patch nello stesso evento
            out = []
            for x in ev["v"]:
                if isinstance(x, dict) and self._is_text(x.get("p")) and x.get("o") == "append" and isinstance(x.get("v"), str):
                    out.append((x, "v"))
            self.text = bool(out)
            return out
        self.text = False
        return []

    def end(self, ev):
        return isinstance(ev, dict) and ev.get("type") in ("message_stream_complete", "conversation_detail_metadata")


class Generic(Adapter):
    """Servizi di cui non si conosce il formato esatto: il testo dell'utente si riconosce dal nome
    del campo, la risposta si ripristina su tutte le stringhe. Da verificare servizio per servizio:
    se nessun campo viene riconosciuto il registro lo segnala con la struttura della richiesta."""
    name = "generic"
    KEYS = {"prompt", "query", "query_str", "message", "content", "text", "input", "question", "q", "messageInput",
              "user_input", "userInput", "msg", "inputs", "user_message", "userMessage", "message_content",
              "extracted_content", "instruction", "user_prompt", "userPrompt", "search_query", "dsl_query"}
    RX_CODE = re.compile(r"[A-Za-z0-9_\-=.+/:]{20,}")   # identificativi e gettoni: non sono testo dell'utente
    # I nomi cambiano da un servizio all'altro: ogni campo il cui nome parla di testo viene controllato (visto dal vivo su
    # Poe il 17/11/2026: la bozza parte a ogni tasto nel campo «fullChatInput», prima dell'Invio). Un campo che non contiene
    # dati personali resta com'e', quindi controllarne qualcuno in piu' non cambia nulla.
    RX_KEY = re.compile(r"(?i)input|message|prompt|query|question|text|content|msg|instruction")

    @classmethod
    def _is_text(cls, v):
        return isinstance(v, str) and v.strip() != "" and not cls.RX_CODE.fullmatch(v)

    def _search(self, node, out, prof=0):
        if prof > 10:
            return
        if isinstance(node, dict):
            author = node.get("author")
            role = node.get("role") or (author.get("role") if isinstance(author, dict) else None)
            if role in ("system", "developer"):
                return
            for k, v in node.items():
                if k in self.KEYS or k == "parts" or (isinstance(k, str) and self.RX_KEY.search(k)):
                    if self._is_text(v):
                        out.append((node, k))
                    elif isinstance(v, list):
                        out += [(v, i) for i, x in enumerate(v) if self._is_text(x)]
                        self._search([x for x in v if isinstance(x, (dict, list))], out, prof + 1)
                    elif isinstance(v, dict):
                        self._search(v, out, prof + 1)
                elif isinstance(v, (dict, list)):
                    self._search(v, out, prof + 1)
        elif isinstance(node, list):
            for v in node:
                if isinstance(v, (dict, list)):
                    self._search(v, out, prof + 1)

    def fields(self, path, body):
        out = []
        self._search(body, out)
        return out

    def in_streaming(self, kind, path):
        return any(x in kind for x in ("text/event-stream", "ndjson", "text/plain", "stream"))

    def stream(self, search, preload=None):
        return GenericStream(search, preload)

    def whole(self, kind, text, search):
        if self.in_streaming(kind, ""):
            return self.stream(search).everything(text.encode("utf-8")).decode("utf-8")
        return super().whole(kind, text, search)


class Gemini(Generic):
    """gemini.google.com. SPERIMENTALE: formato scritto a memoria e mai provato con il servizio vero.
    La richiesta e' un modulo con dentro JSON che contiene altro JSON; la risposta arriva a blocchi
    preceduti dalla loro lunghezza, che va ricalcolata quando si rimettono i valori."""
    name = "gemini"
    SAFE = "-_.!~*'()"

    def request(self, path, kind, text):
        if "x-www-form-urlencoded" not in kind:
            return super().request(path, kind, text)
        pairs = urllib.parse.parse_qsl(text, keep_blank_values=True)
        pos = next((i for i, (k, _) in enumerate(pairs) if k == "f.req"), None)
        if pos is None:
            return None
        try:
            external = json.loads(pairs[pos][1])
            where = next(i for i, x in enumerate(external) if isinstance(x, str) and x[:1] == "[")
            internal = json.loads(external[where])
        except (ValueError, StopIteration, TypeError):
            return None
        ref = []
        if "StreamGenerate" in path and isinstance(internal, list) and internal and isinstance(internal[0], list) \
                and internal[0] and isinstance(internal[0][0], str):
            ref.append((internal[0], 0))

        def reassemble():
            external[where] = json.dumps(internal, **_COMPACT)
            pairs[pos] = ("f.req", json.dumps(external, **_COMPACT))
            return "&".join(f"{urllib.parse.quote(k, safe=self.SAFE)}={urllib.parse.quote(v, safe=self.SAFE)}" for k, v in pairs)
        return ref, reassemble, {"f.req": internal}

    def in_streaming(self, kind, path):
        return "StreamGenerate" in path

    def stream(self, search, preload=None):
        return GeminiStream(search, preload)

    def whole(self, kind, text, search):
        return self.stream(search).everything(text.encode("utf-8")).decode("utf-8")


CLASSES = {"claude": Claude, "anthropic": Anthropic, "openai": OpenAI, "chatgpt": ChatGPT, "generic": Generic, "gemini": Gemini}
# per le prove con il servizio finto in locale: l'adattatore si sceglie dal percorso
BY_PATH = [("/api/organizations/", Claude), ("/v1/messages", Anthropic), ("/v1/chat/completions", OpenAI),
                ("/v1/responses", OpenAI), ("/backend-api/", ChatGPT), ("/_/BardChatUi/", Gemini), ("/generic/", Generic)]


def for_test(path):
    for start, a in BY_PATH:
        if path.startswith(start):
            return a()
    return None


# ------------------------------------------------------------------ risposta in streaming

class _BaseStream:
    restored = 0

    def everything(self, body):
        """Riscrive una risposta arrivata per intero."""
        return b"".join(self(body) + self(b""))


class SSEStream(_BaseStream):
    """Riscrive al volo una risposta text/event-stream di formato noto: ripristina i segnaposto nei
    pezzi di testo (anche se spezzati tra un evento e l'altro) e in ogni altro evento JSON."""

    def __init__(self, adapter, search, preload=None):
        self.ad, self.search, self.preload = adapter, search, preload
        self.buf, self.text, self.restored = b"", Stream(self._search), 0
        # secondo flusso per i pezzi che sono JSON scritto a rate (argomenti degli strumenti): il valore
        # va inserito con le sequenze di escape, altrimenti il JSON finale non si legge piu'
        self.json = Stream(self._search_json)
        self.last = {}   # id del flusso -> (ultimo evento che lo ha usato, percorso del campo)

    def _search(self, seg):
        v = self.search(seg)
        self.restored += v is not None
        return v

    def _search_json(self, seg):
        v = self._search(seg)
        return None if v is None else json.dumps(v, ensure_ascii=False)[1:-1]

    def __call__(self, chunk):
        self.buf += chunk
        out = []
        while True:
            m = re.search(rb"\r?\n\r?\n", self.buf)
            if not m:
                break
            event, self.buf = self.buf[:m.end()], self.buf[m.end():]
            out.append(self._event(event))
        if chunk == b"":   # fine del flusso
            if self.buf:
                out.append(self._event(self.buf))
                self.buf = b""
            out.append(self._clear())
        # una lista, mai un blocco vuoto: per mitmproxy un blocco vuoto chiuderebbe la risposta
        return [x for x in out if x]

    def _clear(self):
        """Rilascia le code trattenute, ciascuna dentro una copia dell'ultimo evento che portava quel testo."""
        out = b""
        for f in (self.text, self.json):
            queue = f.passthrough("", end=True)
            if not queue or id(f) not in self.last:
                continue
            ev, path = copy.deepcopy(self.last[id(f)])
            node = ev
            for k in path[:-1]:
                node = node[k]
            node[path[-1]] = queue
            out += b"data: " + json.dumps(ev, **_COMPACT).encode("utf-8") + b"\n\n"
        return out

    @staticmethod
    def _path(root, container, key, trace=()):
        """Percorso (lista di chiavi) di contenitore[chiave] dentro radice, per poter clonare l'evento."""
        if root is container:
            return list(trace) + [key]
        children = root.items() if isinstance(root, dict) else enumerate(root) if isinstance(root, list) else ()
        for k, v in children:
            if isinstance(v, (dict, list)):
                p = SSEStream._path(v, container, key, trace + (k,))
                if p:
                    return p
        return None

    def _event(self, raw):
        text = raw.decode("utf-8", errors="surrogateescape")
        if self.preload and "[" in text:
            self.preload([m.group() for m in RX_PLACEHOLDER.finditer(text)])
        lines = text.split("\n")
        data = [i for i, r in enumerate(lines) if r.startswith("data:")]
        if len(data) != 1:
            return restore_json(text, self._search).encode("utf-8", errors="surrogateescape")
        i = data[0]
        loading = lines[i][5:].strip()
        before = b""
        try:
            ev = json.loads(loading)
        except ValueError:
            if loading == "[DONE]":
                before = self._clear()
            return before + text.encode("utf-8", errors="surrogateescape")
        if self.ad.intact(ev):
            return before + text.encode("utf-8", errors="surrogateescape")
        ref = self.ad.delta(ev)
        if ref:
            for r in ref:   # (contenitore, chiave) oppure (contenitore, chiave, "json")
                container, key = r[0], r[1]
                f = self.json if len(r) > 2 else self.text
                container[key] = f.passthrough(container[key])
                self.last[id(f)] = (ev, self._path(ev, container, key))
            fresh = json.dumps(ev, **_COMPACT)
        else:
            if self.ad.end(ev):
                before = self._clear()
            # Un evento senza pezzi di testo ma con dei segnaposto (es. l'azione completa, che Codex legge da qui e non
            # dai pezzi): si ripristina campo per campo, entrando anche nelle stringhe che contengono a loro volta JSON
            # (gli argomenti di un'azione). Farlo sul testo grezzo romperebbe quel JSON interno quando il valore ha
            # virgolette, barre rovesciate o a capo.
            fresh = json.dumps(Leaves(self._search, entire=True).apply(ev), **_COMPACT) if RX_PLACEHOLDER.search(loading) else loading
        lines[i] = "data: " + fresh + ("\r" if lines[i].endswith("\r") else "")
        return before + "\n".join(lines).encode("utf-8", errors="surrogateescape")


class GenericStream(_BaseStream):
    """Riscrive al volo una risposta a righe di formato non noto (SSE, JSON per riga, "0:testo"...):
    ogni riga che contiene JSON passa da Foglie, le altre ricevono il ripristino semplice."""
    RX_LINE = re.compile(r"(data:[ ]?|[0-9a-z]{1,2}:)?(.*?)(\r?\n?)\Z", re.S)

    def __init__(self, search, preload=None):
        self.search, self.preload = search, preload
        self.buf, self.restored = b"", 0
        self.leaves = Leaves(self._search)

    def _search(self, seg):
        v = self.search(seg)
        self.restored += v is not None
        return v

    def __call__(self, chunk):
        self.buf += chunk
        *lines, self.buf = self.buf.split(b"\n")
        out = [self._line(r + b"\n") for r in lines]
        if chunk == b"" and self.buf:
            out.append(self._line(self.buf))
            self.buf = b""
        return [x for x in out if x]

    def _line(self, line):
        if b"[" not in line and not self.leaves.waiting:
            return line
        text = line.decode("utf-8", errors="surrogateescape")
        if self.preload:
            self.preload([m.group() for m in RX_PLACEHOLDER.finditer(text)])
        pref, loading, queue = self.RX_LINE.match(text).groups()
        if loading[:1] in ('[', '{', '"'):
            try:
                obj = json.loads(loading)
            except ValueError:
                obj = None
            if obj is not None:
                self.leaves.changed = False
                fresh = self.leaves.apply(obj) if not isinstance(obj, str) else self.leaves._string(obj, ())
                if not self.leaves.changed:
                    return line
                return ((pref or "") + json.dumps(fresh, **_COMPACT) + queue).encode("utf-8", errors="surrogateescape")
        return restore(text, self._search).encode("utf-8", errors="surrogateescape")


class GeminiStream(GenericStream):
    """Come il generico, ma ogni blocco e' preceduto da una riga con la sua lunghezza: la riga viene
    trattenuta e corretta della differenza dopo il ripristino."""

    def __init__(self, search, preload=None):
        super().__init__(search, preload)
        self.timeout = None

    @staticmethod
    def _unit(b):
        return len(b.decode("utf-8", errors="replace").encode("utf-16-le")) // 2

    def _line(self, line):
        body = line.rstrip(b"\r\n")
        if self.timeout is None and body.isdigit():
            self.timeout = (int(body), line[len(body):])
            return b""
        fresh = super()._line(line)
        if self.timeout is None:
            return fresh
        n, end_line = self.timeout
        self.timeout = None
        return str(n + self._unit(fresh) - self._unit(line)).encode() + end_line + fresh
