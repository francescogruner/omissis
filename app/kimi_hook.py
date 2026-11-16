# -*- coding: utf-8 -*-
"""Il controllo di Omissis sui messaggi di Kimi per Windows: un «hook» del sistema di plugin dell'app.

Kimi chiama questo programma subito prima di mandare un messaggio (evento UserPromptSubmit), passandogli il testo.
Un hook di Kimi puo' solo lasciar partire il messaggio o fermarlo: non puo' riscriverlo. Quindi:

  - non c'e' nulla da sostituire, o il servizio non e' su «Proteggi»  -> il messaggio parte (uscita 0)
  - ci sono dati da sostituire                                       -> il messaggio viene fermato (uscita 2), la versione
                                                                        protetta finisce negli appunti e Kimi mostra perche'
  - il servizio e' su «Blocca»                                       -> il messaggio viene fermato (uscita 2)
  - Omissis non risponde, e l'ultima regola nota era «Proteggi»
    o «Blocca»                                                       -> il messaggio viene fermato (uscita 2): mai in chiaro
  - Omissis non risponde, e il servizio non era da proteggere        -> il messaggio parte: non c'era nulla da proteggere

Decide tutto il motore di Omissis, su questo stesso PC (POST /bridge/prompt): qui non c'e' nessuna regola e nessun
codice segreto. Il codice per parlare col motore viene letto ogni volta dalla cartella dei dati di Omissis; dove sta
quella cartella lo dice omissis.json, scritto accanto a questo file quando Omissis prepara il plugin.

Solo libreria standard: gira con il Python di Omissis, senza nient'altro. Se Omissis viene disinstallato questo
programma non parte piu', e Kimi in quel caso lascia passare i messaggi (lo dice la sua documentazione).
"""
import ctypes
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICE = "kimi"
OFF = {"it": "Omissis non risponde: il messaggio non è partito, per non mandarlo senza protezione. Avvia Omissis e riprova. "
             "Per usare Kimi senza Omissis, disattiva il plugin «Omissis» nella pagina dei plugin di Kimi.",
       "en": "Omissis is not answering: the message was not sent, so that it does not leave unprotected. Start Omissis and try again. "
             "To use Kimi without Omissis, disable the “Omissis” plugin on Kimi's plugins page."}


def config():
    """Dove sono i dati di Omissis e su che porta ascolta il motore. Le variabili d'ambiente servono alle prove."""
    try:
        found = json.loads((HERE / "omissis.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        found = {}
    return {"data": os.environ.get("OMISSIS_DATA") or found.get("data") or "", "port": int(os.environ.get("OMISSIS_PORT") or found.get("port") or 8765),
            "language": found.get("language") if found.get("language") in OFF else "en"}


def text_of(prompt):
    """Il testo scritto dalla persona: Kimi lo passa come elenco di parti ({type: "text", text: ...}), o come frase sola."""
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, list):
        return "\n".join(p["text"] for p in prompt if isinstance(p, dict) and p.get("type", "text") == "text" and isinstance(p.get("text"), str))
    return ""


def to_clipboard(text):
    """Mette il testo negli appunti di Windows. Nelle prove lo scrive in un file, per non toccare gli appunti di chi lavora."""
    target = os.environ.get("OMISSIS_HOOK_CLIPBOARD")
    if target:
        Path(target).write_text(text, encoding="utf-8")
        return True
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


def remembered(data, policy=None):
    """L'ultima regola del servizio detta dal motore, tenuta tra i dati di Omissis: serve solo quando il motore non risponde."""
    note = data / "kimi-plugin" / "last.json"
    try:
        if policy is None:
            return json.loads(note.read_text(encoding="utf-8")).get("policy")
        if remembered(data) != policy:
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text(json.dumps({"policy": policy}), encoding="utf-8")
    except (OSError, ValueError, AttributeError):
        pass
    return policy


def stop(message):
    """Uscita 2: per Kimi vuol dire «ferma il messaggio»; cio' che sta nell'errore standard lo mostra a chi scrive."""
    sys.stderr.buffer.write(message.encode("utf-8"))
    sys.stderr.buffer.flush()
    return 2


def main():
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (ValueError, OSError):
        return 0
    if not isinstance(event, dict) or event.get("hook_event_name", "UserPromptSubmit") != "UserPromptSubmit":
        return 0
    text = text_of(event.get("prompt"))
    if not text.strip():
        return 0
    cfg = config()
    data = Path(cfg["data"]) if cfg["data"] else None
    if data is None or not data.is_dir():   # Omissis non c'e' piu' su questo PC: il plugin e' rimasto solo, non decide nulla
        return 0
    try:
        token = (data / "token_extension.txt").read_text(encoding="utf-8").strip()
        request = urllib.request.Request(f"http://127.0.0.1:{cfg['port']}/bridge/prompt", method="POST",
                                         data=json.dumps({"service": SERVICE, "text": text, "via": "app", "client": "Kimi (plugin)"}).encode("utf-8"),
                                         headers={"Content-Type": "application/json", "X-Token": token})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=50) as answer:   # mai attraverso un proxy
            outcome = json.loads(answer.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        # Omissis non risponde: dove il servizio era da proteggere o da bloccare il messaggio non parte; altrove non c'era nulla da fermare
        return stop(OFF[cfg["language"]]) if remembered(data) in ("protect", "block") else 0
    if not isinstance(outcome, dict):
        return 0
    if isinstance(outcome.get("policy"), str):
        remembered(data, outcome["policy"])
    if outcome.get("action") != "block":
        return 0
    copied = isinstance(outcome.get("text"), str) and to_clipboard(outcome["text"])
    message = outcome.get("message_copied" if copied else "message") or outcome.get("message") or OFF[cfg["language"]]
    return stop(str(message))


if __name__ == "__main__":
    sys.exit(main())
