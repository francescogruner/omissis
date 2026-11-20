# -*- coding: utf-8 -*-
"""La configurazione guidata del primo avvio e l'avviso per le app AI aperte per la prima volta.

  scan_source(nome)          una delle sette ricerche del passo «Quali AI ci sono su questo PC?», una alla volta, cosi'
                             la pagina mostra l'avanzamento; finish_scan() le mette insieme e salva l'inventario
  tools(trovati)             le righe del passo «Cosa proteggo?»: una per servizio del catalogo, con dove e' stato
                             trovato, come si protegge e la regola di adesso
  running()                  le app AI aperte adesso, riconosciute dal programma e dal suo percorso (l'avviso)
  antigravity_relaunch(porta)  chiude l'app di Antigravity e la riapre facendola passare dal gateway di Omissis
  claude_plugin(repository)  installa in Claude Code il plugin di Omissis, con i comandi di Claude Code

Sola lettura, tranne le ultime due, che partono solo da un clic di chi usa il PC.
"""
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

import catalog
import connector
import hook_command
import i18n
import inventory
import scan
import settings
import sistema

NO_WINDOW = sistema.NO_WINDOW
SOURCES = ("programs", "processes", "browser", "editor", "commands", "local", "network")
# i comandi da terminale e il servizio la cui regola li riguarda (None: si mostrano soltanto)
COMMANDS = {"claude": "anthropic-api", "codex": "chatgpt", "gemini": "gemini-api", "agy": "antigravity", "antigravity": "antigravity",
            "ollama": "ollama", "lms": "lmstudio", "cursor-agent": "cursor", "copilot": "github-copilot"}
# le voci dei modelli in locale che scan.py scrive per cartella: il nome dello strumento
MODEL_FOLDERS = {"Modelli di Ollama": "Ollama", "Modelli di LM Studio": "LM Studio", "Modelli scaricati da Hugging Face": "Hugging Face"}
RX_GITHUB = re.compile(r"github ?copilot", re.I)   # da guardare prima: «\bcopilot\b» di Microsoft Copilot lo prenderebbe
# senza la ricerca (saltata) si propongono i piu' usati; ChatGPT e Claude ci sono sempre
POPULAR = {"chatgpt": {"browser"}, "claude": {"browser", "app"}, "anthropic-api": {"terminal"}, "gemini": {"browser"},
           "copilot": {"browser"}, "cursor": {"app"}, "github-copilot": {"editor"}}
ORDER = ["chatgpt", "claude", "anthropic-api", "antigravity", "gemini", "copilot", "copilot-365", "perplexity", "deepseek", "mistral"]
# nelle prove la ricerca non guarda questo PC: la pagina e le schermate devono mostrare sempre le stesse cose
FAKE = {"programs": (["ChatGPT", "Claude", "Cursor"], {"chatgpt": "app", "claude": "app", "cursor": "app"}),
        "processes": (["Claude"], {"claude": "app"}),
        "browser": ([], {}),
        "editor": (["GitHub Copilot"], {"github-copilot": "editor"}),
        "commands": (["claude", "agy"], {"anthropic-api": "terminal", "antigravity": "terminal"}),
        "local": (["Ollama"], {"ollama": "local"}),
        "network": (["chatgpt.com", "gemini.google.com"], {"chatgpt": "browser", "gemini": "browser"})}

_LOCK = threading.Lock()
_STATE = {"found": {}, "cli": {}, "raw": {}}


def _service(name):
    """Il servizio (o lo strumento in locale) a cui corrisponde un nome di programma, processo o estensione."""
    if RX_GITHUB.search(name):
        return "github-copilot"
    r = scan._recognize(name)
    if not r:
        return None
    # Claude Code e Codex sono strumenti da terminale: contano le regole dei servizi con cui parlano
    return {"claude-code": "anthropic-api", "codex": "chatgpt"}.get(r["id"], r["id"])


def _add(ident, where, command=None):
    if not ident or (ident not in catalog.PER_ID and not any(x["id"] == ident for x in catalog.LOCAL)):
        return
    _STATE["found"].setdefault(ident, set()).add(where)
    if command:
        _STATE["cli"].setdefault(ident, set()).add(command)


def scan_source(name, test=False):
    """Fa una delle ricerche e restituisce i nomi da mostrare. La prima della serie ricomincia da zero."""
    if name not in SOURCES:
        raise ValueError(name)
    with _LOCK:
        if name == SOURCES[0]:
            _STATE.update(found={}, cli={}, raw={})
        if test:
            show, ids = FAKE[name]
            for ident, where in ids.items():
                _add(ident, where, {"anthropic-api": "claude", "antigravity": "agy"}.get(ident) if where == "terminal" else None)
            return {"show": list(show)}
    if name == "programs":
        data = scan.programs()
        items = [(e["service"]["name"], e["service"]["id"]) for e in data]
    elif name == "processes":
        data = scan.processes()
        items = [(e["service"]["name"], e["service"]["id"]) for e in data]
    elif name == "browser":
        data = scan.browser_extensions()
        items = [(e["name"], None) for e in data]
    elif name == "editor":
        data = scan.editor_extensions()
        items = [(e["name"], _service(e["name"])) for e in data]
    elif name == "commands":
        data = scan.commands()
        items = [(e["command"], COMMANDS.get(e["command"])) for e in data]
    elif name == "local":
        data = scan.local_models()
        items = [(MODEL_FOLDERS.get(e["name"], e["name"]), _service(MODEL_FOLDERS.get(e["name"], e["name"]))) for e in data]
    else:
        data = scan.network()
        items = [(e["host"], e["id"]) for e in data["dns"]] + [(e["service"]["name"], e["service"]["id"]) for e in data["connected_programs"]]
    where = {"programs": "app", "processes": "app", "browser": "browser", "editor": "editor", "commands": "terminal", "local": "local", "network": "browser"}[name]
    with _LOCK:
        _STATE["raw"][name] = data
        for shown, ident in items:
            if name == "commands":
                _add(ident, "terminal", shown)
            else:
                _add({"claude-code": "anthropic-api", "codex": "chatgpt"}.get(ident, ident), where)
    return {"show": list(dict.fromkeys(shown for shown, _ in items))}


def finish_scan(test=False):
    """Le ricerche fatte finora diventano un'analisi dell'inventario (come quella a mano) e le righe del passo dopo."""
    with _LOCK:
        raw, found, cli = dict(_STATE["raw"]), {k: set(v) for k, v in _STATE["found"].items()}, {k: set(v) for k, v in _STATE["cli"].items()}
    if not test and all(k in raw for k in SOURCES):
        pc = {"programs": raw["programs"], "processes": raw["processes"], "browser_extensions": raw["browser"],
              "editor_extensions": raw["editor"], "commands": raw["commands"], "local": raw["local"]}
        inventory.record(pc, raw["network"], "manual")
    return {"tools": tools(found, cli), "total": len(found)}


def tools(found=None, cli=None):
    """Le righe del passo «Cosa proteggo?». Senza ricerca (found=None) si propongono gli strumenti piu' usati."""
    if found is None:
        found, cli = {k: set(v) for k, v in POPULAR.items()}, {"anthropic-api": {"claude"}}
    found = {k: set(v) for k, v in found.items()}
    cli = cli or {}
    for ident in ("chatgpt", "claude"):
        found.setdefault(ident, {"browser"})
    cfg, fixed = settings.read(), settings.locked()["policies"]
    own = settings.own_policies()
    apps = {a["service"] for a in connector.APP.values() if not a.get("refuses")}
    rows = []
    for ident, where in found.items():
        local = next((x for x in catalog.LOCAL if x["id"] == ident), None)
        if local is not None:
            if local["what"] in ("models", "images"):
                rows.append({"id": ident, "name": local["name"], "group": "local", "where": ["local"], "how": "local", "trial": False,
                             "policy": None, "locked": False, "explicit": False, "commands": []})
            continue
        s = catalog.PER_ID[ident]
        commands = sorted(cli.get(ident, ()))
        name = {"anthropic-api": "Claude Code", "gemini-api": "Gemini CLI"}.get(ident, s["name"]) if commands else s["name"]
        group = "protect" if catalog.protectable(s) else "count"
        if group == "count":
            how = "count"
        elif ident == "antigravity":
            how = "antigravity"
        elif commands and ident in ("anthropic-api", "gemini-api"):
            how = "plugin"
        elif s.get("box") and not s["adapter"]:
            how = "box"
        elif s["kind"] == "api":
            how = "api"
        elif "app" in where and ident in apps:
            how = "app"
        else:
            how = "browser"
        rows.append({"id": ident, "name": name, "group": group, "where": sorted(where - {"local"}), "how": how,
                     "trial": s["adapter"] in ("gemini", "generic") and not s.get("hook") and not s.get("box"),
                     "policy": settings.policy(s, cfg), "locked": ident in fixed, "explicit": ident in own, "commands": commands})
    rank = {k: i for i, k in enumerate(ORDER)}
    return sorted(rows, key=lambda r: (("protect", "count", "local").index(r["group"]), rank.get(r["id"], 99), r["name"].lower()))


# ------------------------------------------------------------------ l'avviso per le app AI aperte

# Le app da guardare: quelle che il connettore sa aprire (con il loro percorso, per non confondere l'app di Claude con il
# Claude da terminale, che si chiama anche lui claude.exe) e qualche altra app AI diffusa.
OTHERS = {"antigravity": ("antigravity.exe", r"\\programs\\antigravity\\antigravity\.exe$"),
          "cursor": ("cursor.exe", r"\\cursor\\cursor\.exe$"),
          "windsurf": ("windsurf.exe", r"\\windsurf\\windsurf\.exe$"),
          "deepl": ("deepl.exe", r"\\deepl\.exe$")}
if sistema.MAC:   # sul Mac i programmi stanno dentro le app: /Applications/Cursor.app/Contents/MacOS/Cursor
    OTHERS = {"antigravity": ("antigravity|electron", r"/Antigravity\.app/Contents/MacOS/"),
              "cursor": ("cursor", r"/Cursor\.app/Contents/MacOS/Cursor$"),
              "windsurf": ("windsurf|electron", r"/Windsurf\.app/Contents/MacOS/"),
              "deepl": ("deepl", r"/DeepL\.app/Contents/MacOS/DeepL$")}


def watched():
    """servizio -> (programma, chiave del connettore o None)"""
    out = {a["service"]: (a["process"], key) for key, a in connector.APP.items() if a.get("process")}
    out.update({k: (v, None) for k, v in OTHERS.items() if k not in out})
    return out


def running():
    """Le app AI aperte adesso: servizio -> chiave del connettore (o None)."""
    return {ident: key for ident, (process, key) in watched().items() if connector.processes(process)}


def antigravity_exe():
    if sistema.MAC:   # il programma vero dentro l'app: lanciato cosi' riceve CLOUD_CODE_URL (con «open» non arriverebbe)
        app = sistema.mac_app("Antigravity")
        found = sorted((app / "Contents" / "MacOS").glob("*")) if app else []
        return found[0] if found else Path("/Applications/Antigravity.app/Contents/MacOS/Antigravity")
    return Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "antigravity" / "Antigravity.exe"


def antigravity_relaunch(port):
    """Chiude l'app di Antigravity (se e' aperta) e la riapre con CLOUD_CODE_URL rivolto al gateway: i messaggi passano
    da Omissis, che sostituisce i dati invece di fermarli. Quello che nell'app non era stato inviato si perde."""
    exe = antigravity_exe()
    if not exe.exists():
        raise connector.Error(i18n.t("connector.error.not_installed", name="Antigravity"))
    if not connector.close_process(OTHERS["antigravity"]):
        raise connector.Error(i18n.t("connector.error.not_closed", name="Antigravity"))
    env = {**os.environ, "CLOUD_CODE_URL": f"http://127.0.0.1:{port}/antigravity"}
    # staccata da Omissis: chiudere o aggiornare Omissis non deve chiudere anche l'app
    subprocess.Popen([str(exe)], env=env, cwd=str(exe.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     **sistema.detached())


def claude_plugin(repository, test=False):
    """Il comando omissis-hook e il plugin di Omissis in Claude Code. Il plugin vale per le sessioni aperte da adesso."""
    hook_command.install()
    if test:   # nelle prove non si tocca il Claude Code di questo PC
        return
    exe = sistema.which("claude")
    if exe is None:
        raise connector.Error(i18n.t("welcome.cc.no_claude"))
    # aggiungere il catalogo una seconda volta da' errore: conta solo l'installazione del plugin
    subprocess.run([exe, "plugin", "marketplace", "add", repository], capture_output=True, timeout=180, creationflags=NO_WINDOW)
    r = subprocess.run([exe, "plugin", "install", "omissis@omissis"], capture_output=True, timeout=180, creationflags=NO_WINDOW)
    if r.returncode != 0:
        detail = (r.stderr or r.stdout).decode("utf-8", errors="replace").strip().splitlines()
        raise connector.Error(i18n.t("welcome.cc.failed", detail=(detail[-1] if detail else str(r.returncode))[:200]))
