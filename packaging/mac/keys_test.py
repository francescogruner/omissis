# -*- coding: utf-8 -*-
"""Prova le scorciatoie da tastiera sul Mac: sono registrate? E premendole gli appunti vengono mascherati e ripristinati?

  dist/Omissis.app/Contents/Resources/python/bin/python3 packaging/mac/keys_test.py

Serve la copia di prova accesa CON l'icona nella barra dei menu e con la protezione attiva (la avvia ci_tests.sh): le
scorciatoie arrivano al ciclo degli eventi dell'icona. I tasti li preme, per finta, «System Events» di macOS: sulle
macchine di prova di GitHub ha il permesso di farlo; dove non lo ha, la prova lo dice e controlla solo la registrazione.
Usa dati inventati e rimette negli appunti cio' che c'era.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

PANEL = f"http://127.0.0.1:{int(os.environ.get('OMISSIS_PORT') or 8765) + 1}"
TEXT = "Buongiorno, sono Giulia Ferraresi della Nevatek S.r.l., il mio numero e' 347 5551234 e scrivo da giulia.ferraresi@nevatek.example."
outcomes = []


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(("OK   " if ok else "NO   ") + name + (f"  ({note})" if note else ""), flush=True)


def call(path):
    with urllib.request.urlopen(PANEL + "/", timeout=10) as r:
        code = re.search(r'name="omissis-code" content="([^"]+)"', r.read().decode("utf-8")).group(1)
    with urllib.request.urlopen(urllib.request.Request(PANEL + path, headers={"X-Panel": code}), timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def clipboard(text=None):
    env = {**os.environ, "LANG": "en_US.UTF-8"}
    if text is None:
        return subprocess.run(["pbpaste"], capture_output=True, timeout=10, env=env).stdout.decode("utf-8", errors="replace")
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), timeout=10, env=env)
    return text


def press(key_code):
    """Control+Option+tasto, premuti da «System Events». (codice di uscita, cio' che ha scritto)"""
    r = subprocess.run(["osascript", "-e", f'tell application "System Events" to key code {key_code} using {{control down, option down}}'],
                       capture_output=True, text=True, timeout=30)
    return r.returncode, (r.stdout + r.stderr).strip()


def wait_for(condition, seconds=10):
    end = time.time() + seconds
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.3)
    return False


def main():
    if sys.platform != "darwin":
        print("SALTATO: le scorciatoie del Mac si provano su un Mac")
        return
    s = call("/api/shortcuts")
    entries = {e["name"]: e for e in s["entries"]}
    mark("le due scorciatoie sugli appunti sono registrate nel sistema", s.get("available") and entries["mask"]["active"] and entries["restore"]["active"],
         json.dumps({k: [v["combo"], v["active"], v["error"]] for k, v in entries.items()}))
    mark("i tasti hanno i nomi del Mac, e la sostituzione sul posto risulta «non c'e' sul Mac»", entries["mask"]["caption"] == "Control+Option+M"
         and entries["replace"]["error"] == "not_here" and not entries["replace"]["active"], f"{entries['mask']['caption']} · {entries['replace']['error']}")
    before = clipboard()
    try:
        clipboard(TEXT)
        code, said = press(46)   # il tasto M
        masked = False
        if code != 0:
            print(f"NON VERIFICABILE QUI: «System Events» non puo' premere i tasti su questa macchina ({said[:160]})")
        else:
            masked = wait_for(lambda: "[PERSONA_" in clipboard())
            now = clipboard()
            mark("Control+Option+M: il testo copiato viene sostituito negli appunti dalla versione mascherata", masked and "Giulia Ferraresi" not in now and "347 5551234" not in now,
                 now[:110].replace("\n", " "))
        if masked:
            code, said = press(15)   # il tasto R
            back = wait_for(lambda: clipboard() == TEXT)
            mark("Control+Option+R: negli appunti tornano i valori veri", code == 0 and back, clipboard()[:110].replace("\n", " "))
    finally:
        clipboard(before)
    print(f"\n{sum(outcomes)}/{len(outcomes)} controlli superati")
    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
