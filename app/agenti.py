# -*- coding: utf-8 -*-
"""Adattatori per gli strumenti che parlano direttamente con le API (Claude Code, Codex, opencode,
aider e simili), usati dal gateway.

Rispetto a una chat c'e' una differenza che conta: questi strumenti rimandano a ogni richiesta tutta
la conversazione, comprese le azioni che il modello ha chiesto (uso degli strumenti) e i loro
risultati (contenuto di file, uscita di comandi). Quindi:

  - nella richiesta si maschera il testo dell'utente, i risultati degli strumenti e anche gli
    ARGOMENTI delle azioni gia' fatte, che lo strumento rimanda con i valori veri;
  - nella risposta si ripristinano il testo e gli argomenti delle nuove azioni, altrimenti lo
    strumento scriverebbe su disco o eseguirebbe comandi con dentro i segnaposto;
  - i ragionamenti firmati non si toccano ne' all'andata ne' al ritorno: devono tornare al servizio
    identici, altrimenti la firma non corrisponde piu'.
"""
import json

import ripristino as R

SISTEMA_MINIMO = 200   # i blocchi di sistema piu' corti (la riga che identifica lo strumento) non si toccano
# Nel contesto tecnico che lo strumento aggiunge da se' (istruzioni di sistema, promemoria) si sostituiscono solo i
# dati personali: nomi di strumenti, identificativi e percorsi servono al modello cosi' come sono, e il rilevatore
# li scambierebbe spesso per segreti o account.
TECNICHE = ["SEGRETO", "ACCOUNT", "HOSTNAME", "DOMINIO", "URL", "IP", "MAC", "ID_CLOUD", "ID_DISPOSITIVO", "ID_PRATICA"]


def vocabolario(corpo):
    """I nomi degli strumenti dichiarati nella richiesta, interi e a pezzi: sono parole del mestiere dello strumento,
    non dati dell'utente. Compaiono di continuo nel contesto e il rilevatore li scambierebbe per account o segreti."""
    out = set()
    if not isinstance(corpo, dict):
        return []
    for s in corpo.get("tools") or []:
        if not isinstance(s, dict):
            continue
        nome = s.get("name") or (s.get("function") or {}).get("name") if isinstance(s.get("function"), dict) or s.get("name") else None
        if isinstance(nome, str) and nome:
            out.add(nome)
            for pezzo in nome.replace("__", " ").replace(":", " ").split():
                if len(pezzo) >= 3:
                    out.add(pezzo)
    if isinstance(corpo.get("model"), str):
        out.add(corpo["model"])
    return sorted(out)


def foglie(nodo, out, prof=0):
    """Tutte le stringhe non vuote dentro un oggetto JSON, come (contenitore, chiave)."""
    if prof > 12:
        return out
    voci = nodo.items() if isinstance(nodo, dict) else enumerate(nodo) if isinstance(nodo, list) else ()
    for k, v in voci:
        if isinstance(v, str):
            if v.strip():
                out.append((nodo, k))
        elif isinstance(v, (dict, list)):
            foglie(v, out, prof + 1)
    return out


class AnthropicAgente(R.Adattatore):
    """API Messages di Anthropic (/v1/messages) usata da un agente."""
    nome = "anthropic"

    def campi(self, percorso, corpo):
        out = []
        self.tecnici = []   # i campi di contesto tecnico tra quelli restituiti
        if "/v1/messages" not in percorso or not isinstance(corpo, dict):
            return out
        s = corpo.get("system")
        if isinstance(s, str) and len(s) >= SISTEMA_MINIMO:
            out.append((corpo, "system"))
        elif isinstance(s, list):
            out += [(b, "text") for b in s if isinstance(b, dict) and isinstance(b.get("text"), str) and len(b["text"]) >= SISTEMA_MINIMO]
        self.tecnici += out
        for m in corpo.get("messages") or []:
            if not isinstance(m, dict):
                continue
            c = m.get("content")
            if isinstance(c, str):
                out.append((m, "content"))
            elif isinstance(c, list):
                for b in c:
                    self._blocco(b, out)
        return out

    def _blocco(self, b, out):
        if not isinstance(b, dict):
            return
        tipo = b.get("type")
        if tipo == "text" and isinstance(b.get("text"), str):
            out.append((b, "text"))
            if b["text"].lstrip().startswith("<system-reminder>"):
                self.tecnici.append((b, "text"))
        elif tipo == "tool_use":
            foglie(b.get("input"), out)
        elif tipo == "tool_result":
            c = b.get("content")
            if isinstance(c, str):
                out.append((b, "content"))
            elif isinstance(c, list):
                for x in c:
                    self._blocco(x, out)
        # thinking, redacted_thinking, immagini e documenti: non si toccano

    def delta(self, ev):
        if isinstance(ev, dict) and ev.get("type") == "content_block_delta" and isinstance(ev.get("delta"), dict):
            d = ev["delta"]
            if isinstance(d.get("text"), str):
                return [(d, "text")]
            if isinstance(d.get("partial_json"), str):
                return [(d, "partial_json", "json")]
        return []

    def intatto(self, ev):
        if not isinstance(ev, dict):
            return False
        if ev.get("type") == "content_block_delta":
            return (ev.get("delta") or {}).get("type") in ("thinking_delta", "signature_delta")
        if ev.get("type") == "content_block_start":
            return (ev.get("content_block") or {}).get("type") in ("thinking", "redacted_thinking")
        return False

    def fine(self, ev):
        return isinstance(ev, dict) and ev.get("type") in ("content_block_stop", "message_delta", "message_stop")

    def intera(self, tipo, testo, cerca):
        if "event-stream" in tipo:
            return self.flusso(cerca).tutto(testo.encode("utf-8")).decode("utf-8")
        try:
            corpo = json.loads(testo)
        except ValueError:
            return testo
        for b in (corpo.get("content") if isinstance(corpo, dict) else None) or []:
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str):
                b["text"] = R.ripristina(b["text"], cerca)
            elif isinstance(b, dict) and b.get("type") == "tool_use":
                for c, k in foglie(b.get("input"), []):
                    c[k] = R.ripristina(c[k], cerca)
        return json.dumps(corpo, ensure_ascii=False)


class OpenAIAgente(R.OpenAI):
    """API di OpenAI e compatibili (/chat/completions e /responses) usate da un agente."""
    nome = "openai"

    @staticmethod
    def _argomenti(contenitore, chiave, rif, annidati):
        """Argomenti di un'azione: una stringa che contiene JSON. Si maschera stringa per stringa."""
        v = contenitore.get(chiave)
        if not isinstance(v, str) or not v.strip():
            return
        try:
            dentro = json.loads(v)
        except ValueError:
            dentro = None
        if isinstance(dentro, (dict, list)):
            foglie(dentro, rif)
            annidati.append((contenitore, chiave, dentro))
        else:
            rif.append((contenitore, chiave))

    def richiesta(self, percorso, tipo, testo):
        if "json" not in tipo:
            return None
        try:
            corpo = json.loads(testo)
        except ValueError:
            return None
        rif, annidati = [], []
        if isinstance(corpo, dict) and "/chat/completions" in percorso:
            for m in corpo.get("messages") or []:
                if not isinstance(m, dict) or m.get("role") in ("system", "developer"):
                    continue
                R._blocchi(m.get("content"), m, "content", rif)
                for a in m.get("tool_calls") or []:
                    if isinstance(a, dict) and isinstance(a.get("function"), dict):
                        self._argomenti(a["function"], "arguments", rif, annidati)
        elif isinstance(corpo, dict) and "/responses" in percorso:
            ingresso = corpo.get("input")
            if isinstance(ingresso, str):
                rif.append((corpo, "input"))
            for m in ingresso if isinstance(ingresso, list) else []:
                if not isinstance(m, dict) or m.get("role") in ("system", "developer"):
                    continue
                R._blocchi(m.get("content"), m, "content", rif)
                if m.get("type") == "function_call":
                    self._argomenti(m, "arguments", rif, annidati)
                if isinstance(m.get("output"), str):
                    rif.append((m, "output"))

        def ricomponi():
            for contenitore, chiave, dentro in annidati:
                contenitore[chiave] = json.dumps(dentro, ensure_ascii=False)
            return json.dumps(corpo, ensure_ascii=False)
        return rif, ricomponi, corpo

    def delta(self, ev):
        out = []
        if not isinstance(ev, dict):
            return out
        for c in ev.get("choices") or []:
            d = c.get("delta") if isinstance(c, dict) else None
            if not isinstance(d, dict):
                continue
            if isinstance(d.get("content"), str):
                out.append((d, "content"))
            for a in d.get("tool_calls") or []:
                f = a.get("function") if isinstance(a, dict) else None
                if isinstance(f, dict) and isinstance(f.get("arguments"), str):
                    out.append((f, "arguments", "json"))
        if isinstance(ev.get("delta"), str):
            if ev.get("type") == "response.output_text.delta":
                out.append((ev, "delta"))
            elif ev.get("type") == "response.function_call_arguments.delta":
                out.append((ev, "delta", "json"))
        return out

    def fine(self, ev):
        if not isinstance(ev, dict):
            return False
        return ev.get("type") in ("response.output_text.done", "response.function_call_arguments.done", "response.output_item.done",
                                  "response.completed") or \
            any(isinstance(c, dict) and c.get("finish_reason") for c in ev.get("choices") or [])


CLASSI = {"anthropic": AnthropicAgente, "openai": OpenAIAgente}
