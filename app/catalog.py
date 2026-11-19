# -*- coding: utf-8 -*-
"""Catalogo dei servizi di intelligenza artificiale: domini, tipo e modo di trattarli.

Serve a tre cose: decidere quale traffico il proxy apre e maschera, riconoscere i servizi AI
contattati dal PC (Shadow AI in rete) e riconoscere app, estensioni e strumenti installati.

adattatore  come il proxy sa leggere il servizio:
              claude / chatgpt / anthropic / openai   formato noto e provato con il servizio finto
              gemini                                   formato particolare, scritto a memoria: SPERIMENTALE
              generico                                 riconosce i campi di testo dal nome: da verificare caso per caso
              None                                     il proxy non lo sa leggere: si puo' solo registrare o bloccare
casella     (box=True) le richieste non si leggono, ma nel browser l'estensione protegge la casella di scrittura: il testo
            viene mascherato nella casella prima dell'invio, gli allegati prima che la pagina li riceva. Solo per i
            servizi provati dal vivo; nel proxy e nel gateway questi servizi restano non leggibili.
hook        (hook=True) le richieste non si leggono, ma l'app del servizio chiama Omissis prima di ogni messaggio (il
            comando «omissis-hook», vedi ai_hook.py) e su «Proteggi» il messaggio con dati da sostituire viene fermato.
            Nel browser e nel proxy questi servizi restano non leggibili.
Politiche:  proteggi (apre e maschera) | registra (conta i contatti) | blocca | ignora

Oltre ai servizi scritti qui sotto c'e' il RADAR: servizi che il programma non sa leggere e che servono solo a
rilevare, registrare e bloccare. Sono file di dati, cosi' l'elenco si allunga senza toccare il codice:
  radar.json accanto a questo file      il radar di base, con i servizi piu' noti (fa parte del programma)
  radar.json nella cartella dei dati    un elenco esteso, se c'e' (stesso formato; si aggiunge a quello di base)
Hanno radar=True: l'estensione del browser non chiede l'accesso ai loro siti (li puo' solo bloccare), e non
compaiono tra quelli protetti.
"""
import json
import re
from pathlib import Path

import paths

KINDS = {"chat": "Assistente in chat", "api": "API per sviluppatori", "code": "Assistente per il codice",
        "media": "Immagini, audio e video", "text": "Scrittura e traduzione", "meetings": "Trascrizione di riunioni",
        "research": "Ricerca", "office": "AI dentro le suite da ufficio", "agents": "Agenti e automazione"}


def _s(id, name, vendor, kind, domains, adapter=None, app=None, box=False, hook=False):
    return dict(id=id, name=name, vendor=vendor, kind=kind, domains=domains.split(), adapter=adapter, app=app, radar=False, box=box, hook=hook)


SERVICES = [
    _s("claude", "Claude", "Anthropic", "chat", "claude.ai", "claude", r"\bclaude\b"),
    _s("chatgpt", "ChatGPT", "OpenAI", "chat", "chatgpt.com chat.openai.com", "chatgpt", r"chatgpt|openai"),
    _s("anthropic-api", "API Anthropic", "Anthropic", "api", "api.anthropic.com", "anthropic"),
    _s("openai-api", "API OpenAI", "OpenAI", "api", "api.openai.com", "openai"),
    _s("gemini", "Gemini", "Google", "chat", "gemini.google.com", "gemini", r"\bgemini\b"),
    _s("gemini-api", "API Gemini", "Google", "api", "generativelanguage.googleapis.com", "generic"),
    _s("copilot", "Microsoft Copilot", "Microsoft", "chat", "copilot.microsoft.com copilot.com", "generic", r"microsoft\.?copilot|\bcopilot\b|^mscopilot$|^copilotapp$|^m365copilot$"),
    _s("copilot-365", "Copilot per Microsoft 365", "Microsoft", "office", "m365.cloud.microsoft copilot.cloud.microsoft m365copilotapp.svc.cloud.microsoft", box=True),
    _s("perplexity", "Perplexity", "Perplexity", "chat", "perplexity.ai", "generic", r"perplexity"),
    _s("deepseek", "DeepSeek", "DeepSeek", "chat", "chat.deepseek.com", "generic", r"deepseek"),
    _s("deepseek-api", "API DeepSeek", "DeepSeek", "api", "api.deepseek.com", "openai"),
    _s("kimi", "Kimi", "Moonshot AI", "chat", "kimi.com kimi.moonshot.cn kimi.ai", "generic", r"\bkimi\b"),
    _s("kimi-api", "API Moonshot", "Moonshot AI", "api", "api.moonshot.cn api.moonshot.ai", "openai"),
    _s("mistral", "Le Chat", "Mistral AI", "chat", "chat.mistral.ai", "generic", r"le ?chat|mistral"),
    _s("mistral-api", "API Mistral", "Mistral AI", "api", "api.mistral.ai", "openai"),
    _s("grok", "Grok", "xAI", "chat", "grok.com", "generic", r"\bgrok\b"),
    _s("grok-api", "API xAI", "xAI", "api", "api.x.ai", "openai"),
    _s("meta-ai", "Meta AI", "Meta", "chat", "meta.ai", "generic"),
    _s("poe", "Poe", "Quora", "chat", "poe.com", "generic", r"\bpoe\b"),
    _s("you", "You.com", "You.com", "chat", "you.com", "generic"),
    _s("qwen", "Qwen", "Alibaba", "chat", "chat.qwen.ai tongyi.aliyun.com qianwen.aliyun.com", "generic"),
    # formato OpenAI su /compatible-mode/v1; il primo indirizzo (Singapore) e' quello usato fuori dalla Cina
    _s("qwen-api", "API Qwen (Alibaba Cloud)", "Alibaba", "api", "dashscope-intl.aliyuncs.com dashscope.aliyuncs.com dashscope-us.aliyuncs.com", "openai"),
    _s("doubao", "Doubao", "ByteDance", "chat", "doubao.com", "generic"),
    _s("zai", "Z.ai / ChatGLM", "Zhipu AI", "chat", "chat.z.ai chatglm.cn", "generic"),
    _s("manus", "Manus", "Manus", "chat", "manus.im", "generic", r"\bmanus\b"),
    _s("genspark", "Genspark", "Genspark", "chat", "genspark.ai", "generic"),
    _s("huggingchat", "Hugging Face", "Hugging Face", "chat", "huggingface.co hf.co"),
    _s("notebooklm", "NotebookLM", "Google", "research", "notebooklm.google.com notebook.google.com"),
    _s("aistudio", "Google AI Studio", "Google", "api", "aistudio.google.com"),
    _s("character", "Character.AI", "Character.AI", "chat", "character.ai"),
    _s("pi", "Pi", "Inflection", "chat", "pi.ai"),
    _s("openrouter", "OpenRouter", "OpenRouter", "api", "openrouter.ai", "openai"),
    _s("groq", "Groq", "Groq", "api", "api.groq.com groq.com", "openai"),
    _s("together", "Together AI", "Together", "api", "api.together.xyz api.together.ai", "openai"),
    _s("fireworks", "Fireworks AI", "Fireworks", "api", "api.fireworks.ai", "openai"),
    _s("cohere", "Cohere", "Cohere", "api", "api.cohere.com api.cohere.ai cohere.com"),
    _s("replicate", "Replicate", "Replicate", "api", "replicate.com api.replicate.com"),
    _s("github-copilot", "GitHub Copilot", "GitHub", "code", "githubcopilot.com copilot-proxy.githubusercontent.com", None, r"github ?copilot"),
    _s("cursor", "Cursor", "Anysphere", "code", "cursor.sh cursor.com", None, r"\bcursor\b"),
    _s("windsurf", "Windsurf / Codeium", "Codeium", "code", "codeium.com windsurf.com", None, r"windsurf|codeium"),
    _s("antigravity", "Antigravity", "Google", "code", "antigravity.google", None, r"antigravity", hook=True),
    _s("tabnine", "Tabnine", "Tabnine", "code", "tabnine.com", None, r"tabnine"),
    _s("replit", "Replit", "Replit", "code", "replit.com"),
    _s("lovable", "Lovable", "Lovable", "code", "lovable.dev"),
    _s("bolt", "Bolt", "StackBlitz", "code", "bolt.new"),
    _s("v0", "v0", "Vercel", "code", "v0.dev v0.app"),
    _s("midjourney", "Midjourney", "Midjourney", "media", "midjourney.com"),
    _s("leonardo", "Leonardo", "Leonardo.Ai", "media", "leonardo.ai"),
    _s("runway", "Runway", "Runway", "media", "runwayml.com"),
    _s("elevenlabs", "ElevenLabs", "ElevenLabs", "media", "elevenlabs.io"),
    _s("suno", "Suno", "Suno", "media", "suno.com"),
    _s("heygen", "HeyGen", "HeyGen", "media", "heygen.com"),
    _s("synthesia", "Synthesia", "Synthesia", "media", "synthesia.io"),
    _s("ideogram", "Ideogram", "Ideogram", "media", "ideogram.ai"),
    _s("stability", "Stability AI", "Stability AI", "media", "stability.ai"),
    _s("deepl", "DeepL", "DeepL", "text", "deepl.com", None, r"deepl"),
    _s("grammarly", "Grammarly", "Grammarly", "text", "grammarly.com grammarly.io", None, r"grammarly"),
    _s("quillbot", "QuillBot", "QuillBot", "text", "quillbot.com"),
    _s("jasper", "Jasper", "Jasper", "text", "jasper.ai"),
    _s("copyai", "Copy.ai", "Copy.ai", "text", "copy.ai"),
    _s("writesonic", "Writesonic", "Writesonic", "text", "writesonic.com"),
    _s("otter", "Otter", "Otter.ai", "meetings", "otter.ai", None, r"\botter\b"),
    _s("fireflies", "Fireflies", "Fireflies.ai", "meetings", "fireflies.ai", None, r"fireflies"),
    _s("tldv", "tl;dv", "tl;dv", "meetings", "tldv.io"),
    _s("readai", "Read AI", "Read AI", "meetings", "read.ai"),
    _s("fathom", "Fathom", "Fathom", "meetings", "fathom.video"),
    _s("phind", "Phind", "Phind", "research", "phind.com"),
    _s("consensus", "Consensus", "Consensus", "research", "consensus.app"),
    _s("elicit", "Elicit", "Elicit", "research", "elicit.com"),
]


def _radar():
    """Le voci del radar (di base, piu' quello esteso se c'e') che non ripetono un servizio o un dominio gia' presente."""
    entries = []
    for f in (Path(__file__).resolve().parent / "radar.json", paths.DATA / "radar.json"):
        try:
            entries += json.loads(f.read_text(encoding="utf-8"))["services"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    taken, names, out = {d for s in SERVICES for d in s["domains"]}, {s["id"] for s in SERVICES}, []
    for entry in entries:
        if len(entry) != 5 or entry[0] in names or entry[3] not in KINDS:
            continue
        ident, name, vendor, kind, domains = entry
        free = [d for d in domains.lower().split() if d not in taken and not any(d.endswith("." + p) for p in taken)]
        if free:
            out.append({**_s(ident, name, vendor, kind, " ".join(free)), "radar": True})
            names.add(ident)
            taken.update(free)
    return out


SERVICES += _radar()
PER_ID = {s["id"]: s for s in SERVICES}
_BY_DOMAIN = {d: s for s in SERVICES for d in s["domains"]}

# Strumenti AI che girano sul PC (non hanno un dominio proprio): riconosciuti da nome, processo o porta locale
# cosa: il codice della descrizione, tradotta nelle lingue (rilevati.cosa.<codice>)
LOCAL = [
    dict(id="ollama", name="Ollama", what="models", app=r"\bollama\b", ports=[11434]),
    dict(id="lmstudio", name="LM Studio", what="models", app=r"lm ?studio", ports=[1234]),
    dict(id="jan", name="Jan", what="models", app=r"^jan$|\bjan\.ai\b|^jan \d", ports=[1337]),
    dict(id="gpt4all", name="GPT4All", what="models", app=r"gpt4all", ports=[4891]),
    dict(id="anythingllm", name="AnythingLLM", what="models", app=r"anythingllm", ports=[3001]),
    dict(id="msty", name="Msty", what="models", app=r"\bmsty\b", ports=[]),
    dict(id="comfyui", name="ComfyUI", what="images", app=r"comfyui", ports=[8188]),
    dict(id="codex", name="Codex", what="agent", app=r"\bcodex\b", ports=[]),
    dict(id="claude-code", name="Claude Code", what="agent", app=r"claude[- ]code", ports=[]),
    dict(id="hermes", name="Hermes Agent", what="agent_personal", app=r"hermes[- ]agent|^hermes$", ports=[]),
    dict(id="openclaw", name="OpenClaw", what="agent_personal", app=r"openclaw|clawdbot|moltbot", ports=[]),
]
# Estensioni del browser e dell'editor: parole che indicano una funzione AI
RX_EXTENSION = re.compile(r"(?i)chat ?gpt|\bgpt\b|claude|copilot|gemini|perplexity|deepseek|\bai\b|a\.i\.|assistant|grammarly|deepl|"
                           r"monica|sider|merlin|maxai|harpa|wiseone|jasper|quillbot|otter|fireflies|tl;?dv|read ai|compose|"
                           r"codeium|tabnine|cline|continue|cody|roo|kilo|windsurf|amazon q|llm|ollama|whisper|transcri|summar|riassun")
RX_CLI = ["claude", "codex", "gemini", "ollama", "aider", "llm", "opencode", "qwen", "cursor-agent", "copilot", "goose", "lms", "hermes", "openclaw", "antigravity", "agy"]

POLICIES = ("protect", "record", "block", "ignore")


def find(host):
    """Servizio a cui appartiene un nome host (o None)."""
    host = host.lower().split(":")[0].rstrip(".")
    parts = host.split(".")
    for i in range(len(parts) - 1):
        s = _BY_DOMAIN.get(".".join(parts[i:]))
        if s:
            return s
    return None


def protectable(service, browser=False):
    """Si puo' scegliere «proteggi»: le richieste si leggono, nel browser si protegge la casella di scrittura, o l'app
    del servizio chiama Omissis prima di ogni messaggio. Con browser=True conta solo cio' che vale dentro il browser."""
    return bool(service["adapter"] or service.get("box") or (service.get("hook") and not browser))


def default_policy(service):
    """Si protegge da subito solo cio' che e' stato provato; il resto si registra finche' non viene verificato."""
    return "protect" if service["adapter"] in ("claude", "chatgpt", "anthropic", "openai") and \
        service["id"] in ("claude", "chatgpt", "anthropic-api", "openai-api") else "record"


def expressions_host(services):
    """Espressioni per --allow-hosts di mitmproxy: solo questi host vengono aperti."""
    return [rf"(^|\.){re.escape(d)}(:\d+)?$" for s in services for d in s["domains"]]
