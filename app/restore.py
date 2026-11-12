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

RX_SEGNAPOSTO = re.compile(r"\[([A-Z][A-Z_]{1,22})_(\d{1,7})\]")
# coda di testo che potrebbe essere l'inizio di un segnaposto non ancora arrivato per intero
RX_INIZIO = re.compile(r"\[(?:[A-Z][A-Z_]{0,23}\d{0,7})?")
_COMPATTO = dict(ensure_ascii=False, separators=(",", ":"))


def ripristina(testo, cerca):
    """Sostituisce i segnaposto completi. cerca(segnaposto) -> valore oppure None."""
    return RX_SEGNAPOSTO.sub(lambda m: v if (v := cerca(m.group())) is not None else m.group(), testo)


def ripristina_json(grezzo, cerca):
    """Come ripristina, ma su JSON non interpretato: il valore viene inserito gia' con le sequenze di escape."""
    def f(m):
        v = cerca(m.group())
        return m.group() if v is None else json.dumps(v, ensure_ascii=False)[1:-1]
    return RX_SEGNAPOSTO.sub(f, grezzo)


class Flusso:
    """Testo che arriva a pezzi: trattiene la coda che potrebbe essere un segnaposto spezzato
    ("[PERS" + "ONA_1]") e la rilascia appena e' completa o si capisce che non lo e'."""

    def __init__(self, cerca):
        self.cerca, self.resto = cerca, ""

    def passa(self, pezzo, fine=False):
        t = self.resto + pezzo
        self.resto = ""
        i = t.rfind("[")
        if not fine and i != -1 and RX_INIZIO.fullmatch(t, i):
            self.resto, t = t[i:], t[:i]
        return ripristina(t, self.cerca)


class Foglie:
    """Ripristino su un oggetto JSON qualsiasi, senza sapere quale campo porta il testo: lavora su
    tutte le stringhe, ricordando per ciascun percorso la coda trattenuta. Capisce da solo se il
    servizio manda pezzi nuovi o ogni volta il testo intero, ed entra nelle stringhe che
    contengono a loro volta JSON."""

    def __init__(self, cerca, intero=False):
        self.cerca, self.intero = cerca, intero
        self.flussi, self.prec, self.cambiato = {}, {}, False

    @property
    def pendenti(self):
        return any(f.resto for f in self.flussi.values())

    def applica(self, nodo, percorso=()):
        if isinstance(nodo, dict):
            for k, v in nodo.items():
                if isinstance(v, (str, dict, list)):
                    nodo[k] = self.applica(v, percorso + (k,))
        elif isinstance(nodo, list):
            for i, v in enumerate(nodo):
                if isinstance(v, (str, dict, list)):
                    nodo[i] = self.applica(v, percorso + ("*",))
        elif isinstance(nodo, str):
            return self._stringa(nodo, percorso)
        return nodo

    def _stringa(self, s, percorso):
        if len(s) > 1 and s[0] in "[{":
            try:
                interno = json.loads(s)
            except ValueError:
                interno = None
            if isinstance(interno, (dict, list)):
                prima, self.cambiato = self.cambiato, False
                nuovo = self.applica(interno, percorso + ("<json>",))
                mod, self.cambiato = self.cambiato, prima or self.cambiato
                return json.dumps(nuovo, **_COMPATTO) if mod else s
        if self.intero:
            out = ripristina(s, self.cerca) if "[" in s else s
        else:
            f = self.flussi.get(percorso)
            if f is None:
                if "[" not in s:
                    return s
                f = self.flussi[percorso] = Flusso(self.cerca)
            if f.resto and s.startswith(self.prec.get(percorso, "\0")):
                f.resto = ""   # il servizio rimanda ogni volta tutto il testo: la coda trattenuta e' gia' dentro
            out = f.passa(s)
            if f.resto:
                self.prec[percorso] = s
        if out != s:
            self.cambiato = True
        return out


def ripristina_oggetto(oggetto, cerca):
    return Foglie(cerca, intero=True).applica(oggetto)


# ------------------------------------------------------------------ adattatori

def _chiavi(nodo, nomi, out, prof=0):
    """Tutti i (contenitore, chiave) il cui nome e' in `nomi` e il cui valore e' una stringa."""
    if prof > 8:
        return out
    if isinstance(nodo, dict):
        for k, v in nodo.items():
            if k in nomi and isinstance(v, str):
                out.append((nodo, k))
            elif isinstance(v, (dict, list)):
                _chiavi(v, nomi, out, prof + 1)
    elif isinstance(nodo, list):
        for v in nodo:
            if isinstance(v, (dict, list)):
                _chiavi(v, nomi, out, prof + 1)
    return out


def _blocchi(contenuto, contenitore, chiave, out):
    """Contenuto di un messaggio in stile API: stringa, oppure lista di blocchi con testo."""
    if isinstance(contenuto, str):
        out.append((contenitore, chiave))
    elif isinstance(contenuto, list):
        for b in contenuto:
            if isinstance(b, dict):
                if isinstance(b.get("text"), str):
                    out.append((b, "text"))
                if b.get("type") == "tool_result":
                    _blocchi(b.get("content"), b, "content", out)


class Adattatore:
    nome = "?"

    def campi(self, percorso, corpo):
        return []

    def delta(self, ev):
        return []

    def fine(self, ev):
        return False

    def intatto(self, ev):
        """Eventi della risposta da non toccare affatto (es. ragionamenti firmati, che devono tornare identici)."""
        return False

    def richiesta(self, percorso, tipo, testo):
        """-> (riferimenti al testo, funzione che ricompone il corpo, corpo interpretato) oppure None."""
        if "json" not in tipo:
            return None
        try:
            corpo = json.loads(testo)
        except ValueError:
            return None
        return self.campi(percorso, corpo), (lambda: json.dumps(corpo, ensure_ascii=False)), corpo

    def in_streaming(self, tipo, percorso):
        return "text/event-stream" in tipo

    def flusso(self, cerca, precarica=None):
        return FlussoSSE(self, cerca, precarica)

    def intera(self, tipo, testo, cerca):
        """Riscrive una risposta arrivata per intero."""
        if "event-stream" in tipo:
            return self.flusso(cerca).tutto(testo.encode("utf-8")).decode("utf-8")
        try:
            return json.dumps(ripristina_oggetto(json.loads(testo), cerca), ensure_ascii=False)
        except ValueError:
            return ripristina_json(testo, cerca)


class Claude(Adattatore):
    """claude.ai nel browser e in Claude Desktop (stessa API privata)."""
    nome = "claude"
    CAMPI = {"prompt", "message_content", "extracted_content"}

    def campi(self, percorso, corpo):
        return _chiavi(corpo, self.CAMPI, [])

    def delta(self, ev):
        if isinstance(ev, dict):
            d = ev.get("delta")
            if ev.get("type") == "content_block_delta" and isinstance(d, dict):
                return [(d, k) for k in ("text", "thinking") if isinstance(d.get(k), str)]
            if isinstance(ev.get("completion"), str):
                return [(ev, "completion")]
        return []

    def fine(self, ev):
        return isinstance(ev, dict) and ev.get("type") in ("content_block_stop", "message_delta", "message_stop", "message_limit")


class Anthropic(Claude):
    """API ufficiale di Anthropic (/v1/messages): per i client che usano l'API."""
    nome = "anthropic"

    def campi(self, percorso, corpo):
        out = []
        if "/v1/messages" in percorso and isinstance(corpo, dict):
            for m in corpo.get("messages") or []:
                if isinstance(m, dict):
                    _blocchi(m.get("content"), m, "content", out)
        return out


class OpenAI(Adattatore):
    """API di OpenAI e compatibili (/chat/completions e /responses): DeepSeek, Mistral, Groq, OpenRouter..."""
    nome = "openai"

    def campi(self, percorso, corpo):
        out = []
        if not isinstance(corpo, dict):
            return out
        if "/chat/completions" in percorso:
            for m in corpo.get("messages") or []:
                if isinstance(m, dict) and m.get("role") != "system" and m.get("role") != "developer":
                    _blocchi(m.get("content"), m, "content", out)
        elif "/responses" in percorso:
            if isinstance(corpo.get("input"), str):
                out.append((corpo, "input"))
            for m in corpo.get("input") if isinstance(corpo.get("input"), list) else []:
                if isinstance(m, dict) and m.get("role") not in ("system", "developer"):
                    _blocchi(m.get("content"), m, "content", out)
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

    def fine(self, ev):
        if not isinstance(ev, dict):
            return False
        return ev.get("type") in ("response.output_text.done", "response.completed") or \
            any(isinstance(c, dict) and c.get("finish_reason") for c in ev.get("choices") or [])


class ChatGPT(Adattatore):
    """chatgpt.com nel browser e nell'app desktop (API privata, a "patch" successive)."""
    nome = "chatgpt"

    def __init__(self):
        self.testo = False   # l'ultimo percorso indicato era il testo del messaggio

    def campi(self, percorso, corpo):
        out = []
        if isinstance(corpo, dict):
            for m in corpo.get("messages") or []:
                parti = (m.get("content") or {}).get("parts") if isinstance(m, dict) and isinstance(m.get("content"), dict) else None
                if isinstance(parti, list) and (m.get("author") or {}).get("role", "user") == "user":
                    out += [(parti, i) for i, p in enumerate(parti) if isinstance(p, str)]
        return out

    @staticmethod
    def _e_testo(p):
        return isinstance(p, str) and re.search(r"/content/(parts/\d+|text)$", p) is not None

    def delta(self, ev):
        if not isinstance(ev, dict) or "v" not in ev:
            return []
        if "p" in ev:
            self.testo = self._e_testo(ev["p"]) and ev.get("o", "append") == "append"
        if isinstance(ev["v"], str):
            return [(ev, "v")] if self.testo else []
        if isinstance(ev["v"], list):   # piu' patch nello stesso evento
            out = []
            for x in ev["v"]:
                if isinstance(x, dict) and self._e_testo(x.get("p")) and x.get("o") == "append" and isinstance(x.get("v"), str):
                    out.append((x, "v"))
            self.testo = bool(out)
            return out
        self.testo = False
        return []

    def fine(self, ev):
        return isinstance(ev, dict) and ev.get("type") in ("message_stream_complete", "conversation_detail_metadata")


class Generico(Adattatore):
    """Servizi di cui non si conosce il formato esatto: il testo dell'utente si riconosce dal nome
    del campo, la risposta si ripristina su tutte le stringhe. Da verificare servizio per servizio:
    se nessun campo viene riconosciuto il registro lo segnala con la struttura della richiesta."""
    nome = "generico"
    CHIAVI = {"prompt", "query", "query_str", "message", "content", "text", "input", "question", "q", "messageInput",
              "user_input", "userInput", "msg", "inputs", "user_message", "userMessage", "message_content",
              "extracted_content", "instruction", "user_prompt", "userPrompt", "search_query", "dsl_query"}
    RX_CODICE = re.compile(r"[A-Za-z0-9_\-=.+/:]{20,}")   # identificativi e gettoni: non sono testo dell'utente

    @classmethod
    def _e_testo(cls, v):
        return isinstance(v, str) and v.strip() != "" and not cls.RX_CODICE.fullmatch(v)

    def _cerca(self, nodo, out, prof=0):
        if prof > 10:
            return
        if isinstance(nodo, dict):
            autore = nodo.get("author")
            ruolo = nodo.get("role") or (autore.get("role") if isinstance(autore, dict) else None)
            if ruolo in ("system", "developer"):
                return
            for k, v in nodo.items():
                if k in self.CHIAVI or k == "parts":
                    if self._e_testo(v):
                        out.append((nodo, k))
                    elif isinstance(v, list):
                        out += [(v, i) for i, x in enumerate(v) if self._e_testo(x)]
                        self._cerca([x for x in v if isinstance(x, (dict, list))], out, prof + 1)
                    elif isinstance(v, dict):
                        self._cerca(v, out, prof + 1)
                elif isinstance(v, (dict, list)):
                    self._cerca(v, out, prof + 1)
        elif isinstance(nodo, list):
            for v in nodo:
                if isinstance(v, (dict, list)):
                    self._cerca(v, out, prof + 1)

    def campi(self, percorso, corpo):
        out = []
        self._cerca(corpo, out)
        return out

    def in_streaming(self, tipo, percorso):
        return any(x in tipo for x in ("text/event-stream", "ndjson", "text/plain", "stream"))

    def flusso(self, cerca, precarica=None):
        return FlussoGenerico(cerca, precarica)

    def intera(self, tipo, testo, cerca):
        if self.in_streaming(tipo, ""):
            return self.flusso(cerca).tutto(testo.encode("utf-8")).decode("utf-8")
        return super().intera(tipo, testo, cerca)


class Gemini(Generico):
    """gemini.google.com. SPERIMENTALE: formato scritto a memoria e mai provato con il servizio vero.
    La richiesta e' un modulo con dentro JSON che contiene altro JSON; la risposta arriva a blocchi
    preceduti dalla loro lunghezza, che va ricalcolata quando si rimettono i valori."""
    nome = "gemini"
    SICURI = "-_.!~*'()"

    def richiesta(self, percorso, tipo, testo):
        if "x-www-form-urlencoded" not in tipo:
            return super().richiesta(percorso, tipo, testo)
        coppie = urllib.parse.parse_qsl(testo, keep_blank_values=True)
        pos = next((i for i, (k, _) in enumerate(coppie) if k == "f.req"), None)
        if pos is None:
            return None
        try:
            esterno = json.loads(coppie[pos][1])
            dove = next(i for i, x in enumerate(esterno) if isinstance(x, str) and x[:1] == "[")
            interno = json.loads(esterno[dove])
        except (ValueError, StopIteration, TypeError):
            return None
        rif = []
        if "StreamGenerate" in percorso and isinstance(interno, list) and interno and isinstance(interno[0], list) \
                and interno[0] and isinstance(interno[0][0], str):
            rif.append((interno[0], 0))

        def ricomponi():
            esterno[dove] = json.dumps(interno, **_COMPATTO)
            coppie[pos] = ("f.req", json.dumps(esterno, **_COMPATTO))
            return "&".join(f"{urllib.parse.quote(k, safe=self.SICURI)}={urllib.parse.quote(v, safe=self.SICURI)}" for k, v in coppie)
        return rif, ricomponi, {"f.req": interno}

    def in_streaming(self, tipo, percorso):
        return "StreamGenerate" in percorso

    def flusso(self, cerca, precarica=None):
        return FlussoGemini(cerca, precarica)

    def intera(self, tipo, testo, cerca):
        return self.flusso(cerca).tutto(testo.encode("utf-8")).decode("utf-8")


CLASSI = {"claude": Claude, "anthropic": Anthropic, "openai": OpenAI, "chatgpt": ChatGPT, "generico": Generico, "gemini": Gemini}
# per le prove con il servizio finto in locale: l'adattatore si sceglie dal percorso
PER_PERCORSO = [("/api/organizations/", Claude), ("/v1/messages", Anthropic), ("/v1/chat/completions", OpenAI),
                ("/v1/responses", OpenAI), ("/backend-api/", ChatGPT), ("/_/BardChatUi/", Gemini), ("/generico/", Generico)]


def di_prova(percorso):
    for inizio, a in PER_PERCORSO:
        if percorso.startswith(inizio):
            return a()
    return None


# ------------------------------------------------------------------ risposta in streaming

class _FlussoBase:
    ripristinati = 0

    def tutto(self, corpo):
        """Riscrive una risposta arrivata per intero."""
        return b"".join(self(corpo) + self(b""))


class FlussoSSE(_FlussoBase):
    """Riscrive al volo una risposta text/event-stream di formato noto: ripristina i segnaposto nei
    pezzi di testo (anche se spezzati tra un evento e l'altro) e in ogni altro evento JSON."""

    def __init__(self, adattatore, cerca, precarica=None):
        self.ad, self.cerca, self.precarica = adattatore, cerca, precarica
        self.buf, self.testo, self.ripristinati = b"", Flusso(self._cerca), 0
        # secondo flusso per i pezzi che sono JSON scritto a rate (argomenti degli strumenti): il valore
        # va inserito con le sequenze di escape, altrimenti il JSON finale non si legge piu'
        self.json = Flusso(self._cerca_json)
        self.ultimo = {}   # id del flusso -> (ultimo evento che lo ha usato, percorso del campo)

    def _cerca(self, seg):
        v = self.cerca(seg)
        self.ripristinati += v is not None
        return v

    def _cerca_json(self, seg):
        v = self._cerca(seg)
        return None if v is None else json.dumps(v, ensure_ascii=False)[1:-1]

    def __call__(self, pezzo):
        self.buf += pezzo
        out = []
        while True:
            m = re.search(rb"\r?\n\r?\n", self.buf)
            if not m:
                break
            evento, self.buf = self.buf[:m.end()], self.buf[m.end():]
            out.append(self._evento(evento))
        if pezzo == b"":   # fine del flusso
            if self.buf:
                out.append(self._evento(self.buf))
                self.buf = b""
            out.append(self._svuota())
        # una lista, mai un blocco vuoto: per mitmproxy un blocco vuoto chiuderebbe la risposta
        return [x for x in out if x]

    def _svuota(self):
        """Rilascia le code trattenute, ciascuna dentro una copia dell'ultimo evento che portava quel testo."""
        out = b""
        for f in (self.testo, self.json):
            coda = f.passa("", fine=True)
            if not coda or id(f) not in self.ultimo:
                continue
            ev, percorso = copy.deepcopy(self.ultimo[id(f)])
            nodo = ev
            for k in percorso[:-1]:
                nodo = nodo[k]
            nodo[percorso[-1]] = coda
            out += b"data: " + json.dumps(ev, **_COMPATTO).encode("utf-8") + b"\n\n"
        return out

    @staticmethod
    def _percorso(radice, contenitore, chiave, traccia=()):
        """Percorso (lista di chiavi) di contenitore[chiave] dentro radice, per poter clonare l'evento."""
        if radice is contenitore:
            return list(traccia) + [chiave]
        figli = radice.items() if isinstance(radice, dict) else enumerate(radice) if isinstance(radice, list) else ()
        for k, v in figli:
            if isinstance(v, (dict, list)):
                p = FlussoSSE._percorso(v, contenitore, chiave, traccia + (k,))
                if p:
                    return p
        return None

    def _evento(self, grezzo):
        testo = grezzo.decode("utf-8", errors="surrogateescape")
        if self.precarica and "[" in testo:
            self.precarica([m.group() for m in RX_SEGNAPOSTO.finditer(testo)])
        righe = testo.split("\n")
        dati = [i for i, r in enumerate(righe) if r.startswith("data:")]
        if len(dati) != 1:
            return ripristina_json(testo, self._cerca).encode("utf-8", errors="surrogateescape")
        i = dati[0]
        carico = righe[i][5:].strip()
        prima = b""
        try:
            ev = json.loads(carico)
        except ValueError:
            if carico == "[DONE]":
                prima = self._svuota()
            return prima + testo.encode("utf-8", errors="surrogateescape")
        if self.ad.intatto(ev):
            return prima + testo.encode("utf-8", errors="surrogateescape")
        rif = self.ad.delta(ev)
        if rif:
            for r in rif:   # (contenitore, chiave) oppure (contenitore, chiave, "json")
                contenitore, chiave = r[0], r[1]
                f = self.json if len(r) > 2 else self.testo
                contenitore[chiave] = f.passa(contenitore[chiave])
                self.ultimo[id(f)] = (ev, self._percorso(ev, contenitore, chiave))
            nuovo = json.dumps(ev, **_COMPATTO)
        else:
            if self.ad.fine(ev):
                prima = self._svuota()
            nuovo = ripristina_json(carico, self._cerca)
        righe[i] = "data: " + nuovo + ("\r" if righe[i].endswith("\r") else "")
        return prima + "\n".join(righe).encode("utf-8", errors="surrogateescape")


class FlussoGenerico(_FlussoBase):
    """Riscrive al volo una risposta a righe di formato non noto (SSE, JSON per riga, "0:testo"...):
    ogni riga che contiene JSON passa da Foglie, le altre ricevono il ripristino semplice."""
    RX_RIGA = re.compile(r"(data:[ ]?|[0-9a-z]{1,2}:)?(.*?)(\r?\n?)\Z", re.S)

    def __init__(self, cerca, precarica=None):
        self.cerca, self.precarica = cerca, precarica
        self.buf, self.ripristinati = b"", 0
        self.foglie = Foglie(self._cerca)

    def _cerca(self, seg):
        v = self.cerca(seg)
        self.ripristinati += v is not None
        return v

    def __call__(self, pezzo):
        self.buf += pezzo
        *righe, self.buf = self.buf.split(b"\n")
        out = [self._riga(r + b"\n") for r in righe]
        if pezzo == b"" and self.buf:
            out.append(self._riga(self.buf))
            self.buf = b""
        return [x for x in out if x]

    def _riga(self, riga):
        if b"[" not in riga and not self.foglie.pendenti:
            return riga
        testo = riga.decode("utf-8", errors="surrogateescape")
        if self.precarica:
            self.precarica([m.group() for m in RX_SEGNAPOSTO.finditer(testo)])
        pref, carico, coda = self.RX_RIGA.match(testo).groups()
        if carico[:1] in ('[', '{', '"'):
            try:
                oggetto = json.loads(carico)
            except ValueError:
                oggetto = None
            if oggetto is not None:
                self.foglie.cambiato = False
                nuovo = self.foglie.applica(oggetto) if not isinstance(oggetto, str) else self.foglie._stringa(oggetto, ())
                if not self.foglie.cambiato:
                    return riga
                return ((pref or "") + json.dumps(nuovo, **_COMPATTO) + coda).encode("utf-8", errors="surrogateescape")
        return ripristina(testo, self._cerca).encode("utf-8", errors="surrogateescape")


class FlussoGemini(FlussoGenerico):
    """Come il generico, ma ogni blocco e' preceduto da una riga con la sua lunghezza: la riga viene
    trattenuta e corretta della differenza dopo il ripristino."""

    def __init__(self, cerca, precarica=None):
        super().__init__(cerca, precarica)
        self.attesa = None

    @staticmethod
    def _unita(b):
        return len(b.decode("utf-8", errors="replace").encode("utf-16-le")) // 2

    def _riga(self, riga):
        corpo = riga.rstrip(b"\r\n")
        if self.attesa is None and corpo.isdigit():
            self.attesa = (int(corpo), riga[len(corpo):])
            return b""
        nuovo = super()._riga(riga)
        if self.attesa is None:
            return nuovo
        n, fine_riga = self.attesa
        self.attesa = None
        return str(n + self._unita(nuovo) - self._unita(riga)).encode() + fine_riga + nuovo
