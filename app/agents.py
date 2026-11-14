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

import restore as R

MINIMUM_SYSTEM = 200   # i blocchi di sistema piu' corti (la riga che identifica lo strumento) non si toccano
# Nel contesto tecnico che lo strumento aggiunge da se' (istruzioni di sistema, promemoria) si sostituiscono solo i
# dati personali: nomi di strumenti, identificativi e percorsi servono al modello cosi' come sono, e il rilevatore
# li scambierebbe spesso per segreti o account.
TECHNICAL = ["SEGRETO", "ACCOUNT", "HOSTNAME", "DOMINIO", "URL", "IP", "MAC", "ID_CLOUD", "ID_DISPOSITIVO", "ID_PRATICA"]


def vocabulary(body):
    """I nomi degli strumenti dichiarati nella richiesta, interi e a pezzi: sono parole del mestiere dello strumento,
    non dati dell'utente. Compaiono di continuo nel contesto e il rilevatore li scambierebbe per account o segreti."""
    out = set()
    if not isinstance(body, dict):
        return []
    for s in body.get("tools") or []:
        if not isinstance(s, dict):
            continue
        name = s.get("name") or (s.get("function") or {}).get("name") if isinstance(s.get("function"), dict) or s.get("name") else None
        if isinstance(name, str) and name:
            out.add(name)
            for chunk in name.replace("__", " ").replace(":", " ").split():
                if len(chunk) >= 3:
                    out.add(chunk)
    if isinstance(body.get("model"), str):
        out.add(body["model"])
    return sorted(out)


def leaves(node, out, prof=0):
    """Tutte le stringhe non vuote dentro un oggetto JSON, come (contenitore, chiave)."""
    if prof > 12:
        return out
    entries = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()
    for k, v in entries:
        if isinstance(v, str):
            if v.strip():
                out.append((node, k))
        elif isinstance(v, (dict, list)):
            leaves(v, out, prof + 1)
    return out


class AnthropicAgent(R.Adapter):
    """API Messages di Anthropic (/v1/messages) usata da un agente."""
    name = "anthropic"

    def fields(self, path, body):
        out = []
        self.technical = []   # i campi di contesto tecnico tra quelli restituiti
        if "/v1/messages" not in path or not isinstance(body, dict):
            return out
        s = body.get("system")
        if isinstance(s, str) and len(s) >= MINIMUM_SYSTEM:
            out.append((body, "system"))
        elif isinstance(s, list):
            out += [(b, "text") for b in s if isinstance(b, dict) and isinstance(b.get("text"), str) and len(b["text"]) >= MINIMUM_SYSTEM]
        self.technical += out
        for m in body.get("messages") or []:
            if not isinstance(m, dict):
                continue
            c = m.get("content")
            if isinstance(c, str):
                out.append((m, "content"))
            elif isinstance(c, list):
                for b in c:
                    self._block(b, out)
        return out

    def _block(self, b, out):
        if not isinstance(b, dict):
            return
        kind = b.get("type")
        if kind == "text" and isinstance(b.get("text"), str):
            out.append((b, "text"))
            if b["text"].lstrip().startswith("<system-reminder>"):
                self.technical.append((b, "text"))
        elif kind == "tool_use":
            leaves(b.get("input"), out)
        elif kind == "tool_result":
            c = b.get("content")
            if isinstance(c, str):
                out.append((b, "content"))
            elif isinstance(c, list):
                for x in c:
                    self._block(x, out)
        # thinking, redacted_thinking, immagini e documenti: non si toccano

    def delta(self, ev):
        if isinstance(ev, dict) and ev.get("type") == "content_block_delta" and isinstance(ev.get("delta"), dict):
            d = ev["delta"]
            if isinstance(d.get("text"), str):
                return [(d, "text")]
            if isinstance(d.get("partial_json"), str):
                return [(d, "partial_json", "json")]
        return []

    def intact(self, ev):
        if not isinstance(ev, dict):
            return False
        if ev.get("type") == "content_block_delta":
            return (ev.get("delta") or {}).get("type") in ("thinking_delta", "signature_delta")
        if ev.get("type") == "content_block_start":
            return (ev.get("content_block") or {}).get("type") in ("thinking", "redacted_thinking")
        return False

    def end(self, ev):
        return isinstance(ev, dict) and ev.get("type") in ("content_block_stop", "message_delta", "message_stop")

    def whole(self, kind, text, search):
        if "event-stream" in kind:
            return self.stream(search).everything(text.encode("utf-8")).decode("utf-8")
        try:
            body = json.loads(text)
        except ValueError:
            return text
        for b in (body.get("content") if isinstance(body, dict) else None) or []:
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str):
                b["text"] = R.restore(b["text"], search)
            elif isinstance(b, dict) and b.get("type") == "tool_use":
                for c, k in leaves(b.get("input"), []):
                    c[k] = R.restore(c[k], search)
        return json.dumps(body, ensure_ascii=False)


class OpenAIAgent(R.OpenAI):
    """API di OpenAI e compatibili (/chat/completions e /responses) usate da un agente."""
    name = "openai"

    @staticmethod
    def _arguments(container, key, ref, nested):
        """Argomenti di un'azione: una stringa che contiene JSON. Si maschera stringa per stringa."""
        v = container.get(key)
        if not isinstance(v, str) or not v.strip():
            return
        try:
            inside = json.loads(v)
        except ValueError:
            inside = None
        if isinstance(inside, (dict, list)):
            leaves(inside, ref)
            nested.append((container, key, inside))
        else:
            ref.append((container, key))

    def request(self, path, kind, text):
        if "json" not in kind:
            return None
        try:
            body = json.loads(text)
        except ValueError:
            return None
        ref, nested = [], []
        if isinstance(body, dict) and "/chat/completions" in path:
            for m in body.get("messages") or []:
                if not isinstance(m, dict) or m.get("role") in ("system", "developer"):
                    continue
                R._blocks(m.get("content"), m, "content", ref)
                for a in m.get("tool_calls") or []:
                    if isinstance(a, dict) and isinstance(a.get("function"), dict):
                        self._arguments(a["function"], "arguments", ref, nested)
        elif isinstance(body, dict) and "/responses" in path:
            inbound = body.get("input")
            if isinstance(inbound, str):
                ref.append((body, "input"))
            for m in inbound if isinstance(inbound, list) else []:
                if not isinstance(m, dict) or m.get("role") in ("system", "developer"):
                    continue
                R._blocks(m.get("content"), m, "content", ref)
                if m.get("type") == "function_call":
                    self._arguments(m, "arguments", ref, nested)
                if isinstance(m.get("output"), str):
                    ref.append((m, "output"))

        def reassemble():
            for container, key, inside in nested:
                container[key] = json.dumps(inside, ensure_ascii=False)
            return json.dumps(body, ensure_ascii=False)
        return ref, reassemble, body

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

    def end(self, ev):
        if not isinstance(ev, dict):
            return False
        return ev.get("type") in ("response.output_text.done", "response.function_call_arguments.done", "response.output_item.done",
                                  "response.completed") or \
            any(isinstance(c, dict) and c.get("finish_reason") for c in ev.get("choices") or [])


CLASSES = {"anthropic": AnthropicAgent, "openai": OpenAIAgent}
