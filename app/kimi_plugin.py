# -*- coding: utf-8 -*-
"""Kimi per Windows: la protezione passa dal sistema di plugin dell'app, non dalla porta di collegamento.

Kimi, a differenza di Claude e ChatGPT, si chiude da sola se viene avviata con la porta di collegamento. Pero' il motore
di «Kimi Work» e' Kimi Code (aperto: github.com/MoonshotAI/kimi-code), che ha un sistema di plugin documentato: un
plugin puo' dichiarare degli «hook», programmi che Kimi chiama a certi eventi. UserPromptSubmit scatta prima che un
messaggio parta, e puo' fermarlo. E' la strada che Kimi stessa mette a disposizione: non si tocca nessun file dell'app.

Qui si prepara la cartella del plugin (manifest + una copia di ai_hook.py); installarlo in Kimi resta un gesto di chi usa il PC,
dalla pagina dei plugin di Kimi. Omissis legge soltanto, tra i file di Kimi, l'elenco dei plugin installati, per dire
nel pannello se il suo c'e'.

Limiti, detti anche nel pannello:
  - un hook non puo' riscrivere il messaggio: dove ci sono dati da sostituire il messaggio viene fermato e la versione
    protetta va negli appunti, da incollare;
  - vale per cio' che la persona scrive; i file che Kimi legge da solo sul PC mentre lavora non passano da qui;
  - nelle risposte restano i segnaposto: i valori veri si rivedono dal pannello di Omissis.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import i18n
import paths

ID = "omissis"
VERSION = "1.0.0"
HOOK = paths.HERE / "ai_hook.py"   # lo stesso controllo dei plugin delle altre app: qui viene copiato dentro la cartella
# Detto al modello di Kimi, in inglese perche' vale in qualunque lingua scriva la persona
SYSTEM = ("Messages may contain placeholders in square brackets, such as [NAME_1] or [EMAIL_2]. They are put there by Omissis, "
          "a privacy tool on the user's computer, in place of personal data. They are not mistakes. Treat each placeholder as the real value: "
          "repeat it exactly as written in answers, files and commands, keep the same placeholder for the same thing, and never try to guess "
          "or ask what it stands for.")


def folder():
    return paths.DATA / "kimi-plugin" / ID


def _python():
    """L'interprete con cui gira Omissis: il plugin lo chiama col percorso completo, cosi' non serve altro sul PC."""
    exe = Path(sys.executable)
    plain = exe.with_name("python.exe")
    return plain if exe.name.lower() == "pythonw.exe" and plain.exists() else exe


def _digest(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def manifest():
    return {
        "name": ID, "version": VERSION, "description": i18n.t("kimi.plugin.short"), "keywords": ["privacy", "gdpr", "pii", "omissis"],
        "author": "Omissis", "license": "Apache-2.0",
        "systemPrompt": SYSTEM,
        # Kimi esegue il comando con la cartella del plugin come cartella di lavoro: il percorso dell'hook e' relativo
        "hooks": [{"event": "UserPromptSubmit", "command": f'"{_python()}" ./hooks/omissis_hook.py kimi', "timeout": 60}],
        "interface": {"displayName": "Omissis", "shortDescription": i18n.t("kimi.plugin.short"), "longDescription": i18n.t("kimi.plugin.long"),
                      "developerName": "Omissis", "category": "PRODUCTIVITY", "hostKind": "local"},
    }


def write():
    """Scrive (o aggiorna) la cartella del plugin tra i dati di Omissis. Dentro non c'e' nessun codice segreto."""
    root = folder()
    (root / "hooks").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HOOK, root / "hooks" / "omissis_hook.py")
    (root / "hooks" / "omissis.json").write_text(json.dumps({"data": str(paths.DATA), "port": paths.ENGINE_PORT, "language": i18n.active()}, indent=1), encoding="utf-8")
    (root / "kimi.plugin.json").write_text(json.dumps(manifest(), ensure_ascii=False, indent=2), encoding="utf-8")
    icon = paths.HERE / "panel" / "icon.svg"
    if icon.exists():
        shutil.copyfile(icon, root / "icon.svg")
    return state()


def homes():
    """Dove Kimi tiene l'elenco dei plugin installati: l'app per Windows ha una cartella sua, Kimi Code da terminale un'altra.
    Nelle prove e' una cartella tra i dati di prova: quello che c'e' in Kimi vera non deve cambiare l'esito."""
    if os.environ.get("OMISSIS_TEST") == "1":
        return [paths.DATA / "kimi-home"]
    roaming = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return [roaming / "kimi-desktop" / "daimon-share" / "daimon" / "runtime" / "kimi-code" / "home", Path.home() / ".kimi-code"]


def installed():
    """Il plugin di Omissis risulta installato e acceso in Kimi? Si legge soltanto, e solo quell'elenco."""
    for home in homes():
        try:
            listed = json.loads((home / "plugins" / "installed.json").read_text(encoding="utf-8")).get("plugins") or []
        except (OSError, ValueError, AttributeError):
            continue
        for p in listed:
            if isinstance(p, dict) and str(p.get("id", "")).split("@")[0].lower() == ID and p.get("enabled", True):
                return True
    return False


def state():
    root = folder()
    ready = (root / "kimi.plugin.json").exists() and _digest(root / "hooks" / "omissis_hook.py") == _digest(HOOK)
    return {"ready": ready, "folder": str(root), "installed": installed(), "sentence": i18n.t("kimi.plugin.sentence", folder=str(root))}
