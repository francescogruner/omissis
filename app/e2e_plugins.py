# -*- coding: utf-8 -*-
"""Prova il comando «omissis-hook» e i plugin di Omissis per le app AI che hanno un sistema di hook (Kimi, Claude Code,
Codex, Gemini CLI, Antigravity).

  python e2e_plugins.py

Serve la copia di prova accesa (OMISSIS_DATA, OMISSIS_PORT, OMISSIS_TEST) e OMISSIS_MANAGED_FILE per cambiare le regole.
Il comando viene chiamato come lo chiamano le app: per nome, trovato nel PATH, da ognuna delle shell che usano (cmd,
PowerShell, bash), con il messaggio in JSON sullo standard input. I dati sono inventati.

Nessuna app vera viene aperta e nessun plugin viene installato. Il PATH di Windows non viene toccato (nelle prove al
posto del registro c'e' un file), e nemmeno gli appunti veri. Dove sono installati, si usano i controlli ufficiali dei
plugin (quello di Kimi, «claude plugin validate») sul repository preparato da pubblicazione\\prepara_plugin.py.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import hook_command
import paths

ok = True
NAME, CODE, IBAN, MAIL = "Ottavio Marchesini", "MRCTTV75D12L219K", "IT60X0542811101000000123456", "ottavio.marchesini@officina-esempio.it"
PERSONAL = f"Prepara un sollecito per {NAME}, codice fiscale {CODE}, IBAN {IBAN}, mail {MAIL}: la fattura scade venerdi."
PLAIN = "Elenca tre buone pratiche per scrivere i test di un programma."
VALUES = (NAME, "Marchesini", CODE, IBAN, MAIL)
REPO = paths.ROOT / "pubblico" / "omissis-plugin"


def check(what, outcome, note=""):
    global ok
    ok &= bool(outcome)
    print(f"{'OK    ' if outcome else 'ERRORE'} {what}" + (f"   {note}" if note else ""))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if not os.environ.get("OMISSIS_MANAGED_FILE") or os.environ.get("OMISSIS_TEST") != "1":
        sys.exit("servono OMISSIS_TEST=1 (il PATH vero non va toccato) e OMISSIS_MANAGED_FILE (per cambiare le regole dei servizi)")
    work = Path(tempfile.mkdtemp(prefix="omissis_plugin_"))
    clip = work / "appunti.txt"

    # --- il comando: due file nella cartella di Omissis, e la cartella nel PATH (qui, un file al posto del registro)
    hook_command.remove()
    before = hook_command.state()
    state = hook_command.install()
    folder = Path(state["folder"])
    files = {f.name: f.read_bytes() for f in folder.iterdir() if f.name.startswith("omissis-hook")}
    secrets_here = [(paths.DATA / n).read_text(encoding="utf-8").strip() for n in ("token.txt", "token_extension.txt") if (paths.DATA / n).exists()]
    check("«Installa il comando»: due file (per cmd/PowerShell e per bash) che chiamano il controllo con il Python di Omissis; nessun codice segreto dentro",
          {k: before[k] for k in ("ready", "on_path", "folder")} == {"ready": False, "on_path": False, "folder": str(folder)} and state["ready"] and state["on_path"] and set(files) == {"omissis-hook", "omissis-hook.cmd"}
          and all(b"ai_hook.py" in c and b"--data" in c for c in files.values()) and files["omissis-hook.cmd"].startswith(b"@echo off\r\n")
          and files["omissis-hook"].startswith(b"#!/bin/sh\n") and b"\r" not in files["omissis-hook"]
          and secrets_here and not any(s.encode() in c for s in secrets_here for c in files.values()), str(sorted(files)))

    env = {**os.environ, "PATH": str(folder) + os.pathsep + os.environ.get("PATH", ""), "OMISSIS_HOOK_CLIPBOARD": str(clip)}
    for name in ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "GOOGLE_GEMINI_BASE_URL"):   # questa prova non passa dal gateway
        env.pop(name, None)
    shells = {"cmd": lambda app: dict(args=f"omissis-hook {app}", shell=True)}
    for exe in ("powershell", "pwsh"):
        if shutil.which(exe):   # come fa chi «passa il JSON al comando»: lo standard input di PowerShell inoltrato al programma
            shells[exe] = lambda app, exe=exe: dict(args=[exe, "-NoProfile", "-NonInteractive", "-Command", f"$input | omissis-hook {app}; exit $LASTEXITCODE"])
    bash = shutil.which("bash")
    if bash:
        posix = subprocess.run([bash, "-c", 'cygpath -u "$1" 2>/dev/null || printf %s "$1"', "_", str(folder)], capture_output=True, text=True).stdout.strip()
        shells["bash"] = lambda app: dict(args=[bash, "-c", f'PATH="{posix}:$PATH" omissis-hook {app}'])

    def run(app, event, shell="cmd", **changes):
        """Chiama il comando per nome, da una shell, come fa l'app. Restituisce (uscita, spiegazione, appunti)."""
        clip.unlink(missing_ok=True)
        r = subprocess.run(**shells[shell](app), input=json.dumps(event).encode("utf-8"), capture_output=True, cwd=str(work), env={**env, **changes}, timeout=120)
        return r.returncode, r.stderr.decode("utf-8", errors="replace"), clip.read_text(encoding="utf-8") if clip.exists() else None

    def rule(policies):
        target = Path(os.environ["OMISSIS_MANAGED_FILE"])
        target.unlink(missing_ok=True) if policies is None else target.write_text(json.dumps({"policies": policies}), encoding="utf-8")
        time.sleep(3.5)

    prompt = lambda text, event="UserPromptSubmit": {"hook_event_name": event, "session_id": "prova", "cwd": str(work), "prompt": text}
    try:
        rule({"kimi": "protect", "gemini-api": "protect", "anthropic-api": "protect", "chatgpt": "protect", "antigravity": "protect"})
        # --- ogni shell trova il comando e gli passa il messaggio
        seen = {}
        for shell in shells:
            code, why, held = run("claude", prompt(PERSONAL), shell)
            seen[shell] = (code, bool(held) and not any(v in held for v in VALUES) and len(re.findall(r"\[[A-Z][A-Z_]+_\d+\]", held)) >= 3, run("claude", prompt(PLAIN), shell)[0])
        check(f"il comando si trova per nome da ogni shell ({', '.join(shells)}): messaggio con dati personali fermato, versione protetta negli appunti, messaggio pulito lasciato partire",
              len(shells) >= 2 and all(v == (2, True, 0) for v in seen.values()), str(seen))

        # --- ogni app col suo modo di passare il messaggio; la regola e' quella del suo servizio
        each = {}
        for app, event in (("kimi", {"hook_event_name": "UserPromptSubmit", "prompt": [{"type": "text", "text": PERSONAL}]}), ("claude", prompt(PERSONAL)),
                           ("codex", {**prompt(PERSONAL), "model": "esempio", "turn_id": "1"}), ("gemini", prompt(PERSONAL, "BeforeAgent"))):
            code, why, held = run(app, event)
            pasted = run(app, {**event, "prompt": held} if app != "kimi" else {**event, "prompt": [{"type": "text", "text": held or ""}]})[0] if held else None
            each[app] = (code, len(why) > 40 and not any(v in why for v in VALUES), pasted)
        check("Kimi, Claude Code, Codex e Gemini CLI: fermato il messaggio con dati personali (uscita 2, con la spiegazione), e la versione protetta, incollata, parte",
              all(v == (2, True, 0) for v in each.values()), str(each))
        # --- Antigravity: evento PreInvocation, e la risposta non e' l'uscita ma un JSON sullo standard output
        def ag(text, number=0, **changes):
            clip.unlink(missing_ok=True)
            event = {"hookEventName": "PreInvocation", "conversationId": "prova", "invocationNum": number, "initialNumSteps": 1, "lastUserInput": text, "workspacePaths": [str(work)]}
            r = subprocess.run(**shells["cmd"]("antigravity"), input=json.dumps(event).encode("utf-8"), capture_output=True, cwd=str(work), env={**env, **changes}, timeout=120)
            try:
                said = json.loads(r.stdout.decode("utf-8") or "null")
            except ValueError:
                said = r.stdout.decode("utf-8", errors="replace")
            return r.returncode, said, clip.read_text(encoding="utf-8") if clip.exists() else None
        code, said, held = ag(PERSONAL)
        stopped = isinstance(said, dict) and said.get("terminationBehavior") == "terminate" and said.get("injectSteps", [{}])[0].get("errorMessage", {}).get("userMessage", "")
        pasted = ag(held)[:2] if held else None
        check("Antigravity: messaggio con dati personali fermato prima del modello (terminate, con la spiegazione per chi scrive), versione protetta negli appunti; incollata, parte",
              code == 0 and len(stopped or "") > 40 and not any(v in json.dumps(said, ensure_ascii=False) for v in VALUES)
              and bool(held) and not any(v in held for v in VALUES) and pasted == (0, {}), f"{code} {str(said)[:120]} · incollata {pasted}")
        later = [ag(PERSONAL, 1)[:2], ag(PLAIN)[:2], ag(PERSONAL, OMISSIS_PORT="9")[1].get("terminationBehavior") if isinstance(ag(PERSONAL, OMISSIS_PORT="9")[1], dict) else None]
        check("Antigravity: le chiamate successive dello stesso turno e i messaggi puliti passano ({}); a Omissis spento il messaggio da proteggere resta fermo",
              later == [(0, {}), (0, {}), "terminate"], str(later))

        log = [json.loads(x) for x in (paths.DATA / "activity.jsonl").read_text(encoding="utf-8").splitlines()[-80:] if x.strip()]
        mine = {(x.get("service"), x.get("client")) for x in log if x.get("method") == "hook"}
        check("nel registro ogni app compare col suo servizio e il suo nome; mai il testo né i valori",
              {("kimi", "Kimi (plugin)"), ("anthropic-api", "Claude Code (plugin)"), ("chatgpt", "Codex (plugin)"), ("gemini-api", "Gemini CLI (plugin)"), ("antigravity", "Antigravity (hook)")} <= mine
              and not any(v in json.dumps(log, ensure_ascii=False) for v in VALUES), str(sorted(mine))[:200])

        # --- dove lo strumento passa gia' dal gateway di Omissis, il plugin non interviene: li' i dati vengono sostituiti davvero
        via = [run("claude", prompt(PERSONAL), ANTHROPIC_BASE_URL="http://127.0.0.1:8777")[0], run("codex", prompt(PERSONAL), OPENAI_BASE_URL="http://localhost:8777/v1")[0],
               run("claude", prompt(PERSONAL), ANTHROPIC_BASE_URL="https://api.altrove.example")[0]]
        check("strumento mandato al gateway di Omissis: il plugin lascia fare; mandato altrove: controlla come sempre", via == [0, 0, 2], str(via))

        # --- cio' che non e' da controllare, e un'app che il comando non conosce
        quiet = [run("claude", prompt("   "))[0], run("claude", {"hook_event_name": "PreToolUse", "prompt": PERSONAL})[0], run("sconosciuta", prompt(PERSONAL))[0],
                 run("gemini", {"hook_event_name": "BeforeModel", "llm_request": {"messages": [{"role": "user", "content": PERSONAL}]}})[0]]
        check("messaggio vuoto, un altro evento, un'app sconosciuta: il comando lascia fare", quiet == [0, 0, 0, 0], str(quiet))

        # --- le regole dei servizi, una per app
        rule({"anthropic-api": "block", "chatgpt": "ignore", "gemini-api": "record", "kimi": "protect"})
        ruled = [run("claude", prompt(PLAIN))[0], run("codex", prompt(PERSONAL))[0], run("gemini", prompt(PERSONAL, "BeforeAgent"))[0], run("kimi", prompt(PERSONAL))[0]]
        off = [run(app, prompt(PERSONAL), OMISSIS_PORT="9")[0] for app in ("claude", "codex", "gemini", "kimi")]
        check("ogni app segue la regola del suo servizio (Blocca, Ignora, Registra, Proteggi); a Omissis spento resta fermo solo ciò che era da bloccare o da proteggere",
              ruled == [2, 0, 0, 2] and off == [2, 0, 0, 2], f"acceso {ruled} · spento {off}")
    finally:
        rule(None)

    # --- Antigravity: la voce di Omissis nel suo file degli hook, accanto a quelle che ci sono gia'
    hook_command.install()
    f = hook_command.antigravity_file()
    other = {"altro": {"PreToolUse": [{"matcher": "run_command", "hooks": [{"type": "command", "command": "controllo-altrui"}]}]}}
    f.write_text(json.dumps(other), encoding="utf-8")
    linked = hook_command.antigravity_link()["antigravity"]
    inside = json.loads(f.read_text(encoding="utf-8"))
    unlinked = hook_command.antigravity_unlink()["antigravity"]
    left = json.loads(f.read_text(encoding="utf-8"))
    f.write_text("{ non è JSON", encoding="utf-8")
    try:
        hook_command.antigravity_link()
        refused = False
    except ValueError:
        refused = True
    untouched = f.read_text(encoding="utf-8") == "{ non è JSON" and hook_command.antigravity_state()["unreadable"]
    f.write_text(json.dumps(other), encoding="utf-8")
    hook_command.antigravity_link()
    hook_command.remove()
    after_remove = json.loads(f.read_text(encoding="utf-8"))
    f.unlink(missing_ok=True)
    hook_command.install()   # la prova finale, qui sotto, toglie il comando
    check("Antigravity: «Collega» aggiunge la voce di Omissis (PreInvocation, «omissis-hook antigravity», senza percorsi) e lascia le altre; «Scollega» e «Togli il comando» la tolgono; un file illeggibile non viene riscritto",
          linked["linked"] and inside.get("altro") == other["altro"] and inside["omissis"] == {"PreInvocation": [{"type": "command", "command": "omissis-hook antigravity", "timeout": 60}]}
          and not unlinked["linked"] and left == other and refused and untouched and after_remove == other, f"{linked} · {sorted(inside)} · rifiuto {refused}")

    # --- il repository pubblico dei plugin: ogni app chiama il comando per nome, e dentro non c'e' nulla di questo PC
    if not (REPO / "kimi.plugin.json").exists():
        print("SALTATO il repository dei plugin: lanciare prima pubblicazione\\prepara_plugin.py")
    else:
        read = lambda name: json.loads((REPO / name).read_text(encoding="utf-8"))
        commands = {"kimi": read("kimi.plugin.json")["hooks"][0]["command"], "gemini": read("hooks/hooks.json")["hooks"]["BeforeAgent"][0]["hooks"][0]["command"],
                    "claude": read("claude-code/hooks/hooks.json")["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"],
                    "codex": read("codex/hooks/hooks.json")["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]}
        everything = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in REPO.rglob("*") if f.is_file() and ".git" not in f.parts and f.suffix != ".svg")
        check("repository dei plugin: ogni app chiama «omissis-hook» col suo nome; i due mercati puntano alle loro cartelle; dentro nessun percorso di questo PC né codici",
              commands == {a: f"omissis-hook {a}" for a in commands} and read(".claude-plugin/marketplace.json")["plugins"][0]["source"] == "./claude-code"
              and read(".agents/plugins/marketplace.json")["plugins"][0]["source"]["path"] == "./codex" and read("gemini-extension.json")["name"] == "omissis"
              and not re.search(r"(?i)[A-Z]:\\\\|Users[\\/]|Privacy AI", everything) and not any(s in everything for s in secrets_here), str(commands))
        validator = Path(os.environ.get("APPDATA", "")) / "kimi-desktop" / "daimon-bundle" / "app" / "daimon" / "assets" / "builtin-skills" / "plugin-builder" / "scripts" / "validate_plugin.py"
        if validator.exists():
            r = subprocess.run([sys.executable, "-I", str(validator), str(REPO)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            check("il controllo dei plugin di Kimi accetta il repository (0 errori)", r.returncode == 0 and "0 error" in r.stdout, (r.stdout.strip().splitlines() or [""])[-1][:80])
        else:
            print("SALTATO il controllo di Kimi: Kimi per Windows non è installata su questo PC")
        claude = shutil.which("claude")
        if claude:
            done = [subprocess.run([claude, "plugin", "validate", str(p)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120) for p in (REPO / "claude-code", REPO)]
            check("«claude plugin validate» accetta il plugin di Claude Code e il mercato", all(r.returncode == 0 and "Validation passed" in r.stdout for r in done),
                  " · ".join((r.stdout.strip().splitlines() or [r.stderr.strip()[:60]])[-1][:40] for r in done))
        else:
            print("SALTATO «claude plugin validate»: Claude Code non è installato su questo PC")

    # --- togliere il comando
    gone = hook_command.remove()
    check("«Togli il comando»: spariscono i file e la cartella esce dal PATH; i plugin, da lì, non trovano più nulla",
          {k: gone[k] for k in ("ready", "on_path", "folder")} == {"ready": False, "on_path": False, "folder": str(folder)} and not any(f.name.startswith("omissis-hook") for f in folder.iterdir())
          and subprocess.run("omissis-hook claude", shell=True, input=b"{}", capture_output=True, env=env).returncode not in (0, 2))
    print("\nTUTTO BENE" if ok else "\nQUALCOSA NON VA")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
