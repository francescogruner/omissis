# -*- coding: utf-8 -*-
"""Il controllo di Omissis sui messaggi, per le app e gli strumenti AI che hanno un sistema di «hook» loro.

Kimi, Claude Code, Codex, Gemini CLI e Antigravity (app e CLI) chiamano un programma subito prima di mandare un
messaggio, passandogli il testo in JSON sullo standard input, e gli lasciano decidere se il messaggio parte. Questo e'
quel programma, uno per tutti:

  omissis-hook kimi | claude | codex | gemini | antigravity

Antigravity lo chiama all'evento PreInvocation, prima di ogni chiamata al modello: conta solo la prima di ogni turno
(invocationNum 0), quando parte il messaggio scritto dalla persona. Antigravity non guarda l'uscita del programma ma
quello che scrive sullo standard output: per fermare il messaggio un JSON con «terminationBehavior: terminate» e un
«errorMessage», che Antigravity mostra a chi scrive senza mandarlo al modello.

Un hook puo' solo lasciar partire il messaggio o fermarlo: non puo' riscriverlo. Quindi:

  - non c'e' nulla da sostituire, o il servizio non e' su «Proteggi»  -> il messaggio parte (uscita 0)
  - ci sono dati da sostituire                                       -> il messaggio viene fermato (uscita 2), la versione
                                                                        protetta finisce negli appunti e l'app mostra perche'
  - il servizio e' su «Blocca»                                       -> il messaggio viene fermato (uscita 2)
  - Omissis non risponde, e l'ultima regola nota era «Proteggi»
    o «Blocca»                                                       -> il messaggio viene fermato (uscita 2): mai in chiaro
  - Omissis non risponde, e il servizio non era da proteggere        -> il messaggio parte: non c'era nulla da proteggere
  - lo strumento passa gia' dal gateway di Omissis                   -> il messaggio parte: li' i dati vengono sostituiti davvero

Decide tutto il motore di Omissis, su questo stesso PC (POST /bridge/prompt): qui non c'e' nessuna regola e nessun
codice segreto. Il codice per parlare col motore viene letto ogni volta dalla cartella dei dati di Omissis. Dove sta
quella cartella lo dice chi lancia questo programma (--data, lo fa il comando «omissis-hook» che Omissis installa),
oppure il file omissis.json accanto a questo, nella cartella che Omissis prepara per Kimi.

Solo libreria standard: gira con il Python di Omissis, senza nient'altro. Se Omissis viene tolto dal PC il comando non
c'e' piu', e le app in quel caso lasciano passare i messaggi (un hook che non si avvia non ferma nulla).
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Per ogni app: il servizio del catalogo di Omissis la cui regola decide, come la si chiama nel registro, e le variabili
# d'ambiente con cui lo strumento viene mandato al gateway di Omissis (se puntano a questo PC, sostituisce gia' lui).
PLATFORMS = {
    "kimi": {"service": "kimi", "client": "Kimi (plugin)", "gateway": ()},
    "claude": {"service": "anthropic-api", "client": "Claude Code (plugin)", "gateway": ("ANTHROPIC_BASE_URL",)},
    "codex": {"service": "chatgpt", "client": "Codex (plugin)", "gateway": ("OPENAI_BASE_URL",)},
    "gemini": {"service": "gemini-api", "client": "Gemini CLI (plugin)", "gateway": ("GOOGLE_GEMINI_BASE_URL",)},
    "antigravity": {"service": "antigravity", "client": "Antigravity (hook)", "gateway": ("CLOUD_CODE_URL",), "json": True},
}
EVENTS = ("UserPromptSubmit", "BeforeAgent", "PreInvocation")   # come ogni app chiama il momento «il messaggio sta per partire»
OFF = {"it": "Omissis non risponde: il messaggio non è partito, per non mandarlo senza protezione. Avvia Omissis e riprova. "
             "Per lavorare senza Omissis, disattiva il plugin «Omissis» in questa app.",
       "en": "Omissis is not answering: the message was not sent, so that it does not leave unprotected. Start Omissis and try again. "
             "To work without Omissis, disable the “Omissis” plugin in this app."}


def config(args):
    """Dove sono i dati di Omissis e su che porta ascolta il motore. Le variabili d'ambiente servono alle prove."""
    try:
        found = json.loads((HERE / "omissis.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        found = {}
    language = args.language or found.get("language")
    return {"data": os.environ.get("OMISSIS_DATA") or args.data or found.get("data") or "",
            "port": int(os.environ.get("OMISSIS_PORT") or args.port or found.get("port") or 8765), "language": language if language in OFF else "en"}


def read_event():
    """Il JSON che l'app scrive sullo standard input. Di norma e' UTF-8; una shell di Windows puo' averlo ricodificato."""
    raw = sys.stdin.buffer.read()
    for encoding in ("utf-8-sig", "utf-16", "mbcs" if os.name == "nt" else "latin-1"):
        try:
            return json.loads(raw.decode(encoding))
        except (ValueError, LookupError):
            continue
    return None


def text_of(prompt):
    """Il testo scritto dalla persona: una frase, oppure (Kimi) un elenco di parti ({type: "text", text: ...})."""
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, list):
        return "\n".join(p["text"] for p in prompt if isinstance(p, dict) and p.get("type", "text") == "text" and isinstance(p.get("text"), str))
    return ""


def through_gateway(names):
    """Lo strumento e' gia' mandato a un indirizzo di questo PC (il gateway di Omissis)? Allora i dati li sostituisce lui."""
    for name in names:
        host = (urllib.parse.urlsplit(os.environ.get(name, "")).hostname or "").lower()
        if host in ("127.0.0.1", "localhost", "::1"):
            return True
    return False


def to_clipboard(text):
    """Mette il testo negli appunti di Windows. Nelle prove lo scrive in un file, per non toccare gli appunti di chi lavora."""
    target = os.environ.get("OMISSIS_HOOK_CLIPBOARD")
    if target:
        Path(target).write_text(text, encoding="utf-8")
        return True
    if sys.platform == "darwin":   # appunti del Mac
        try:
            return subprocess.run(["pbcopy"], input=text.encode("utf-8"), timeout=10,
                                  env={**os.environ, "LANG": "en_US.UTF-8"}).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    if os.name != "nt":
        return False
    user, kernel = ctypes.windll.user32, ctypes.windll.kernel32
    kernel.GlobalAlloc.restype = kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel.GlobalLock.argtypes = kernel.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user.SetClipboardData.restype = ctypes.c_void_p
    data = text.encode("utf-16-le") + b"\0\0"
    for _ in range(20):   # gli appunti possono essere occupati un istante da un altro programma
        if user.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user.EmptyClipboard()
        handle = kernel.GlobalAlloc(0x0002, len(data))   # GMEM_MOVEABLE
        if not handle:
            return False
        where = kernel.GlobalLock(handle)
        ctypes.memmove(where, data, len(data))
        kernel.GlobalUnlock(handle)
        return bool(user.SetClipboardData(13, handle))   # CF_UNICODETEXT
    finally:
        user.CloseClipboard()


def remembered(data, service, policy=None):
    """L'ultima regola di un servizio detta dal motore, tenuta tra i dati di Omissis: serve solo quando il motore non risponde."""
    note = data / "hook-state.json"
    try:
        known = json.loads(note.read_text(encoding="utf-8"))
        known = known if isinstance(known, dict) else {}
    except (OSError, ValueError):
        known = {}
    if policy is not None and known.get(service) != policy:
        try:
            note.write_text(json.dumps({**known, service: policy}), encoding="utf-8")
        except OSError:
            pass
    return known.get(service) if policy is None else policy


def stop(message, platform=None):
    """Uscita 2: per quasi tutte queste app vuol dire «ferma il messaggio»; cio' che sta nell'errore standard lo mostrano
    a chi scrive. Antigravity invece legge un JSON dallo standard output: un messaggio d'errore e l'ordine di fermarsi."""
    if platform and platform.get("json"):
        sys.stdout.buffer.write(json.dumps({"injectSteps": [{"errorMessage": {"userMessage": message}}], "terminationBehavior": "terminate"}).encode("utf-8"))
        sys.stdout.buffer.flush()
        return 0
    sys.stderr.buffer.write(message.encode("utf-8"))
    sys.stderr.buffer.flush()
    return 2


def go(platform):
    """Il messaggio parte. Ad Antigravity serve comunque un JSON, anche vuoto."""
    if platform and platform.get("json"):
        sys.stdout.write("{}")
        sys.stdout.flush()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("platform", nargs="?", default="kimi")
    ap.add_argument("--data")
    ap.add_argument("--port")
    ap.add_argument("--language")
    args, _ = ap.parse_known_args(argv)
    platform = PLATFORMS.get(str(args.platform).lower())
    event = read_event()
    if platform is None or not isinstance(event, dict):
        return go(platform)
    if event.get("hook_event_name", event.get("hookEventName", EVENTS[0])) not in EVENTS:
        return go(platform)
    if event.get("invocationNum", 0) != 0:   # Antigravity: una chiamata successiva dello stesso turno, il messaggio e' gia' passato di qui
        return go(platform)
    text = text_of(event.get("prompt", event.get("lastUserInput")))
    if not text.strip() or through_gateway(platform["gateway"]):
        return go(platform)
    cfg = config(args)
    data = Path(cfg["data"]) if cfg["data"] else None
    if data is None or not data.is_dir():   # Omissis non c'e' piu' su questo PC: il plugin e' rimasto solo, non decide nulla
        return go(platform)
    service = platform["service"]
    try:
        token = (data / "token_extension.txt").read_text(encoding="utf-8").strip()
        request = urllib.request.Request(f"http://127.0.0.1:{cfg['port']}/bridge/prompt", method="POST",
                                         data=json.dumps({"service": service, "text": text, "via": "app", "client": platform["client"]}).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "X-Token": token})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=50) as answer:   # mai attraverso un proxy
            outcome = json.loads(answer.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        # Omissis non risponde: dove il servizio era da proteggere o da bloccare il messaggio non parte; altrove non c'era nulla da fermare
        return stop(OFF[cfg["language"]], platform) if remembered(data, service) in ("protect", "block") else go(platform)
    if not isinstance(outcome, dict):
        return go(platform)
    if isinstance(outcome.get("policy"), str):
        remembered(data, service, outcome["policy"])
    if outcome.get("action") != "block":
        return go(platform)
    copied = isinstance(outcome.get("text"), str) and to_clipboard(outcome["text"])
    message = outcome.get("message_copied" if copied else "message") or outcome.get("message") or OFF[cfg["language"]]
    return stop(str(message), platform)


if __name__ == "__main__":
    sys.exit(main())
