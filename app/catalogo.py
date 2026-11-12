# -*- coding: utf-8 -*-
"""Catalogo dei servizi di intelligenza artificiale: domini, tipo e modo di trattarli.

Serve a tre cose: decidere quale traffico il proxy apre e maschera, riconoscere i servizi AI
contattati dal PC (Shadow AI in rete) e riconoscere app, estensioni e strumenti installati.

adattatore  come il proxy sa leggere il servizio:
              claude / chatgpt / anthropic / openai   formato noto e provato con il servizio finto
              gemini                                   formato particolare, scritto a memoria: SPERIMENTALE
              generico                                 riconosce i campi di testo dal nome: da verificare caso per caso
              None                                     il proxy non lo sa leggere: si puo' solo registrare o bloccare
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

import percorsi

TIPI = {"chat": "Assistente in chat", "api": "API per sviluppatori", "codice": "Assistente per il codice",
        "media": "Immagini, audio e video", "testo": "Scrittura e traduzione", "riunioni": "Trascrizione di riunioni",
        "ricerca": "Ricerca", "ufficio": "AI dentro le suite da ufficio", "agenti": "Agenti e automazione"}


def _s(id, nome, fornitore, tipo, domini, adattatore=None, app=None):
    return dict(id=id, nome=nome, fornitore=fornitore, tipo=tipo, domini=domini.split(), adattatore=adattatore, app=app, radar=False)


SERVIZI = [
    _s("claude", "Claude", "Anthropic", "chat", "claude.ai", "claude", r"\bclaude\b"),
    _s("chatgpt", "ChatGPT", "OpenAI", "chat", "chatgpt.com chat.openai.com", "chatgpt", r"chatgpt|openai"),
    _s("anthropic-api", "API Anthropic", "Anthropic", "api", "api.anthropic.com", "anthropic"),
    _s("openai-api", "API OpenAI", "OpenAI", "api", "api.openai.com", "openai"),
    _s("gemini", "Gemini", "Google", "chat", "gemini.google.com", "gemini", r"\bgemini\b"),
    _s("gemini-api", "API Gemini", "Google", "api", "generativelanguage.googleapis.com", "generico"),
    _s("copilot", "Microsoft Copilot", "Microsoft", "chat", "copilot.microsoft.com copilot.com", "generico", r"microsoft\.?copilot|\bcopilot\b"),
    _s("copilot-365", "Copilot per Microsoft 365", "Microsoft", "ufficio", "m365.cloud.microsoft copilot.cloud.microsoft"),
    _s("perplexity", "Perplexity", "Perplexity", "chat", "perplexity.ai", "generico", r"perplexity"),
    _s("deepseek", "DeepSeek", "DeepSeek", "chat", "chat.deepseek.com", "generico", r"deepseek"),
    _s("deepseek-api", "API DeepSeek", "DeepSeek", "api", "api.deepseek.com", "openai"),
    _s("kimi", "Kimi", "Moonshot AI", "chat", "kimi.com kimi.moonshot.cn kimi.ai", "generico", r"\bkimi\b"),
    _s("kimi-api", "API Moonshot", "Moonshot AI", "api", "api.moonshot.cn api.moonshot.ai", "openai"),
    _s("mistral", "Le Chat", "Mistral AI", "chat", "chat.mistral.ai", "generico", r"le ?chat|mistral"),
    _s("mistral-api", "API Mistral", "Mistral AI", "api", "api.mistral.ai", "openai"),
    _s("grok", "Grok", "xAI", "chat", "grok.com", "generico", r"\bgrok\b"),
    _s("grok-api", "API xAI", "xAI", "api", "api.x.ai", "openai"),
    _s("meta-ai", "Meta AI", "Meta", "chat", "meta.ai", "generico"),
    _s("poe", "Poe", "Quora", "chat", "poe.com", "generico", r"\bpoe\b"),
    _s("you", "You.com", "You.com", "chat", "you.com", "generico"),
    _s("qwen", "Qwen", "Alibaba", "chat", "chat.qwen.ai tongyi.aliyun.com qianwen.aliyun.com", "generico"),
    # formato OpenAI su /compatible-mode/v1; il primo indirizzo (Singapore) e' quello usato fuori dalla Cina
    _s("qwen-api", "API Qwen (Alibaba Cloud)", "Alibaba", "api", "dashscope-intl.aliyuncs.com dashscope.aliyuncs.com dashscope-us.aliyuncs.com", "openai"),
    _s("doubao", "Doubao", "ByteDance", "chat", "doubao.com", "generico"),
    _s("zai", "Z.ai / ChatGLM", "Zhipu AI", "chat", "chat.z.ai chatglm.cn", "generico"),
    _s("manus", "Manus", "Manus", "chat", "manus.im", "generico", r"\bmanus\b"),
    _s("genspark", "Genspark", "Genspark", "chat", "genspark.ai", "generico"),
    _s("huggingchat", "Hugging Face", "Hugging Face", "chat", "huggingface.co hf.co"),
    _s("notebooklm", "NotebookLM", "Google", "ricerca", "notebooklm.google.com"),
    _s("aistudio", "Google AI Studio", "Google", "api", "aistudio.google.com"),
    _s("character", "Character.AI", "Character.AI", "chat", "character.ai"),
    _s("pi", "Pi", "Inflection", "chat", "pi.ai"),
    _s("openrouter", "OpenRouter", "OpenRouter", "api", "openrouter.ai", "openai"),
    _s("groq", "Groq", "Groq", "api", "api.groq.com groq.com", "openai"),
    _s("together", "Together AI", "Together", "api", "api.together.xyz api.together.ai", "openai"),
    _s("fireworks", "Fireworks AI", "Fireworks", "api", "api.fireworks.ai", "openai"),
    _s("cohere", "Cohere", "Cohere", "api", "api.cohere.com api.cohere.ai cohere.com"),
    _s("replicate", "Replicate", "Replicate", "api", "replicate.com api.replicate.com"),
    _s("github-copilot", "GitHub Copilot", "GitHub", "codice", "githubcopilot.com copilot-proxy.githubusercontent.com", None, r"github ?copilot"),
    _s("cursor", "Cursor", "Anysphere", "codice", "cursor.sh cursor.com", None, r"\bcursor\b"),
    _s("windsurf", "Windsurf / Codeium", "Codeium", "codice", "codeium.com windsurf.com", None, r"windsurf|codeium"),
    _s("antigravity", "Antigravity", "Google", "codice", "antigravity.google", None, r"antigravity"),
    _s("tabnine", "Tabnine", "Tabnine", "codice", "tabnine.com", None, r"tabnine"),
    _s("replit", "Replit", "Replit", "codice", "replit.com"),
    _s("lovable", "Lovable", "Lovable", "codice", "lovable.dev"),
    _s("bolt", "Bolt", "StackBlitz", "codice", "bolt.new"),
    _s("v0", "v0", "Vercel", "codice", "v0.dev v0.app"),
    _s("midjourney", "Midjourney", "Midjourney", "media", "midjourney.com"),
    _s("leonardo", "Leonardo", "Leonardo.Ai", "media", "leonardo.ai"),
    _s("runway", "Runway", "Runway", "media", "runwayml.com"),
    _s("elevenlabs", "ElevenLabs", "ElevenLabs", "media", "elevenlabs.io"),
    _s("suno", "Suno", "Suno", "media", "suno.com"),
    _s("heygen", "HeyGen", "HeyGen", "media", "heygen.com"),
    _s("synthesia", "Synthesia", "Synthesia", "media", "synthesia.io"),
    _s("ideogram", "Ideogram", "Ideogram", "media", "ideogram.ai"),
    _s("stability", "Stability AI", "Stability AI", "media", "stability.ai"),
    _s("deepl", "DeepL", "DeepL", "testo", "deepl.com", None, r"deepl"),
    _s("grammarly", "Grammarly", "Grammarly", "testo", "grammarly.com grammarly.io", None, r"grammarly"),
    _s("quillbot", "QuillBot", "QuillBot", "testo", "quillbot.com"),
    _s("jasper", "Jasper", "Jasper", "testo", "jasper.ai"),
    _s("copyai", "Copy.ai", "Copy.ai", "testo", "copy.ai"),
    _s("writesonic", "Writesonic", "Writesonic", "testo", "writesonic.com"),
    _s("otter", "Otter", "Otter.ai", "riunioni", "otter.ai", None, r"\botter\b"),
    _s("fireflies", "Fireflies", "Fireflies.ai", "riunioni", "fireflies.ai", None, r"fireflies"),
    _s("tldv", "tl;dv", "tl;dv", "riunioni", "tldv.io"),
    _s("readai", "Read AI", "Read AI", "riunioni", "read.ai"),
    _s("fathom", "Fathom", "Fathom", "riunioni", "fathom.video"),
    _s("phind", "Phind", "Phind", "ricerca", "phind.com"),
    _s("consensus", "Consensus", "Consensus", "ricerca", "consensus.app"),
    _s("elicit", "Elicit", "Elicit", "ricerca", "elicit.com"),
]


def _radar():
    """Le voci del radar (di base, piu' quello esteso se c'e') che non ripetono un servizio o un dominio gia' presente."""
    voci = []
    for f in (Path(__file__).resolve().parent / "radar.json", percorsi.DATI / "radar.json"):
        try:
            voci += json.loads(f.read_text(encoding="utf-8"))["servizi"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    presi, nomi, out = {d for s in SERVIZI for d in s["domini"]}, {s["id"] for s in SERVIZI}, []
    for voce in voci:
        if len(voce) != 5 or voce[0] in nomi or voce[3] not in TIPI:
            continue
        ident, nome, fornitore, tipo, domini = voce
        liberi = [d for d in domini.lower().split() if d not in presi and not any(d.endswith("." + p) for p in presi)]
        if liberi:
            out.append({**_s(ident, nome, fornitore, tipo, " ".join(liberi)), "radar": True})
            nomi.add(ident)
            presi.update(liberi)
    return out


SERVIZI += _radar()
PER_ID = {s["id"]: s for s in SERVIZI}
_PER_DOMINIO = {d: s for s in SERVIZI for d in s["domini"]}

# Strumenti AI che girano sul PC (non hanno un dominio proprio): riconosciuti da nome, processo o porta locale
# cosa: il codice della descrizione, tradotta nelle lingue (rilevati.cosa.<codice>)
LOCALI = [
    dict(id="ollama", nome="Ollama", cosa="modelli", app=r"\bollama\b", porte=[11434]),
    dict(id="lmstudio", nome="LM Studio", cosa="modelli", app=r"lm ?studio", porte=[1234]),
    dict(id="jan", nome="Jan", cosa="modelli", app=r"^jan$|\bjan\.ai\b|^jan \d", porte=[1337]),
    dict(id="gpt4all", nome="GPT4All", cosa="modelli", app=r"gpt4all", porte=[4891]),
    dict(id="anythingllm", nome="AnythingLLM", cosa="modelli", app=r"anythingllm", porte=[3001]),
    dict(id="msty", nome="Msty", cosa="modelli", app=r"\bmsty\b", porte=[]),
    dict(id="comfyui", nome="ComfyUI", cosa="immagini", app=r"comfyui", porte=[8188]),
    dict(id="codex", nome="Codex", cosa="agente", app=r"\bcodex\b", porte=[]),
    dict(id="claude-code", nome="Claude Code", cosa="agente", app=r"claude[- ]code", porte=[]),
    dict(id="hermes", nome="Hermes Agent", cosa="agente_personale", app=r"hermes[- ]agent|^hermes$", porte=[]),
    dict(id="openclaw", nome="OpenClaw", cosa="agente_personale", app=r"openclaw|clawdbot|moltbot", porte=[]),
]
# Estensioni del browser e dell'editor: parole che indicano una funzione AI
RX_ESTENSIONE = re.compile(r"(?i)chat ?gpt|\bgpt\b|claude|copilot|gemini|perplexity|deepseek|\bai\b|a\.i\.|assistant|grammarly|deepl|"
                           r"monica|sider|merlin|maxai|harpa|wiseone|jasper|quillbot|otter|fireflies|tl;?dv|read ai|compose|"
                           r"codeium|tabnine|cline|continue|cody|roo|kilo|windsurf|amazon q|llm|ollama|whisper|transcri|summar|riassun")
RX_CLI = ["claude", "codex", "gemini", "ollama", "aider", "llm", "opencode", "qwen", "cursor-agent", "copilot", "goose", "lms", "hermes", "openclaw", "antigravity"]

POLITICHE = ("proteggi", "registra", "blocca", "ignora")


def trova(host):
    """Servizio a cui appartiene un nome host (o None)."""
    host = host.lower().split(":")[0].rstrip(".")
    parti = host.split(".")
    for i in range(len(parti) - 1):
        s = _PER_DOMINIO.get(".".join(parti[i:]))
        if s:
            return s
    return None


def politica_predefinita(servizio):
    """Si protegge da subito solo cio' che e' stato provato; il resto si registra finche' non viene verificato."""
    return "proteggi" if servizio["adattatore"] in ("claude", "chatgpt", "anthropic", "openai") and \
        servizio["id"] in ("claude", "chatgpt", "anthropic-api", "openai-api") else "registra"


def espressioni_host(servizi):
    """Espressioni per --allow-hosts di mitmproxy: solo questi host vengono aperti."""
    return [rf"(^|\.){re.escape(d)}(:\d+)?$" for s in servizi for d in s["domini"]]
