# -*- coding: utf-8 -*-
"""Prova il plugin di Omissis per Kimi: la cartella che Omissis prepara e il controllo sui messaggi (hook UserPromptSubmit).

  python e2e_kimi.py

Serve la copia di prova accesa (OMISSIS_DATA, OMISSIS_PORT, OMISSIS_TEST e, per cambiare le regole, OMISSIS_MANAGED_FILE).
L'hook viene lanciato come lo lancia Kimi: un processo a parte, il messaggio in JSON sullo standard input, l'esito nel
codice di uscita (0 parte, 2 fermato) e la spiegazione sull'errore standard. I dati sono inventati.

Kimi vera non viene toccata: non si apre, non le si scrive nulla, non si installa nessun plugin. Se e' installata si usa
solo il suo controllo dei plugin (validate_plugin.py) sulla cartella preparata. Gli appunti veri non vengono toccati: nelle
prove la versione protetta finisce in un file.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import kimi_plugin
import paths

ok = True
NAME, CODE, IBAN, MAIL = "Giovanna Bellandi", "BLLGNN82C45F205X", "IT60X0542811101000000123456", "giovanna.bellandi@studio-esempio.it"
PERSONAL = f"Scrivi una lettera a {NAME}, codice fiscale {CODE}, che ha l'IBAN {IBAN} e la mail {MAIL}, per ricordarle la scadenza di venerdì."
PLAIN = "Riassumi in tre punti i vantaggi del lavoro da remoto per una piccola azienda."


def check(what, outcome, note=""):
    global ok
    ok &= bool(outcome)
    print(f"{'OK    ' if outcome else 'ERRORE'} {what}" + (f"   {note}" if note else ""))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    state = kimi_plugin.write()
    root = Path(state["folder"])
    manifest = json.loads((root / "kimi.plugin.json").read_text(encoding="utf-8"))
    hook = manifest["hooks"][0]
    python = re.match(r'"([^"]+)" \./hooks/omissis_hook\.py kimi$', hook["command"])
    secrets_here = [(paths.DATA / n).read_text(encoding="utf-8").strip() for n in ("token.txt", "token_extension.txt") if (paths.DATA / n).exists()]
    everything = b"".join(f.read_bytes() for f in root.rglob("*") if f.is_file())
    check("cartella del plugin: manifest con l'hook sul messaggio, comando che chiama il Python di Omissis, nessun codice segreto dentro",
          state["ready"] and manifest["name"] == "omissis" and hook["event"] == "UserPromptSubmit" and set(hook) == {"event", "command", "timeout"}
          and python is not None and Path(python.group(1)).exists() and (root / "hooks" / "omissis_hook.py").exists()
          and secrets_here and not any(s.encode() in everything for s in secrets_here) and "placeholder" in manifest["systemPrompt"], hook["command"][:80])
    validator = Path(os.environ.get("APPDATA", "")) / "kimi-desktop" / "daimon-bundle" / "app" / "daimon" / "assets" / "builtin-skills" / "plugin-builder" / "scripts" / "validate_plugin.py"
    if validator.exists():
        r = subprocess.run([sys.executable, "-I", str(validator), str(root)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        check("il controllo dei plugin di Kimi stessa accetta la cartella (0 errori)", r.returncode == 0 and "0 error" in r.stdout, r.stdout.strip().splitlines()[-1][:80] if r.stdout.strip() else r.stderr[:80])
    else:
        print("SALTATO il controllo dei plugin di Kimi: Kimi per Windows non è installata su questo PC")

    listed = paths.DATA / "kimi-home" / "plugins" / "installed.json"   # nelle prove l'elenco dei plugin di Kimi e' questo file
    listed.parent.mkdir(parents=True, exist_ok=True)
    seen = []
    for plugins in ([], [{"id": "kimi-pdf", "enabled": True}], [{"id": "omissis", "enabled": False}], [{"id": "omissis@personal", "enabled": True}]):
        listed.write_text(json.dumps({"version": 1, "plugins": plugins}), encoding="utf-8")
        seen.append(kimi_plugin.installed())
    listed.unlink()
    check("Omissis riconosce il suo plugin tra quelli installati in Kimi: non c'è, c'è un altro, c'è ma spento, c'è e acceso", seen == [False, False, False, True] and not kimi_plugin.installed(), str(seen))

    work = Path(tempfile.mkdtemp(prefix="omissis_kimi_"))
    clip = work / "appunti.txt"

    def run(event, **changes):
        """Lancia l'hook come fa Kimi. Restituisce (codice di uscita, spiegazione, cio' che e' finito negli appunti)."""
        clip.unlink(missing_ok=True)
        env = {**os.environ, "OMISSIS_HOOK_CLIPBOARD": str(clip), **changes}
        # proprio come fa Kimi: il comando del manifest cosi' com'e' scritto, dato all'interprete dei comandi, dalla cartella del plugin
        r = subprocess.run(hook["command"], shell=True, input=(event if isinstance(event, bytes) else json.dumps(event).encode("utf-8")),
                           capture_output=True, cwd=str(root), env=env, timeout=90)
        return r.returncode, r.stderr.decode("utf-8", errors="replace"), clip.read_text(encoding="utf-8") if clip.exists() else None

    def message(text, **more):
        return {"hook_event_name": "UserPromptSubmit", "session_id": "prova", "cwd": str(work), "prompt": [{"type": "text", "text": text}], **more}

    def rule(policy):
        """Impone la regola per Kimi come farebbe chi amministra il PC, e aspetta che il motore la veda."""
        target = os.environ.get("OMISSIS_MANAGED_FILE")
        if policy is None:
            Path(target).unlink(missing_ok=True)
        else:
            Path(target).write_text(json.dumps({"policies": {"kimi": policy}}), encoding="utf-8")
        time.sleep(3.5)

    if not os.environ.get("OMISSIS_MANAGED_FILE"):
        sys.exit("serve OMISSIS_MANAGED_FILE: Kimi di serie è su «Registra», e per provare «Proteggi» la regola va imposta")
    # --- di serie Kimi, come ogni servizio non ancora provato dal vivo, è su «Registra»: il plugin lascia partire e conta la visita
    # la regola si impone «Registra» invece di toglierla: nella copia di prova chi la usa puo' aver gia' scelto «Proteggi»
    rule("record")
    default = run(message(PERSONAL))
    check("regola di serie («Registra»): il messaggio parte anche con dati personali; per fermarli il servizio va messo su «Proteggi»", default == (0, "", None), str(default[0]))

    # --- servizio su «Proteggi»
    rule("protect")
    code, why, held = run(message(PERSONAL))
    values = (NAME, "Bellandi", CODE, IBAN, MAIL)
    check("messaggio con dati personali: fermato (uscita 2), con la spiegazione e quanti dati c'erano", code == 2 and len(why) > 40 and re.search(r"\d", why) is not None
          and not any(v in why for v in values), why[:110])
    check("la versione protetta va negli appunti: segnaposto al posto dei dati, nessun valore vero", held is not None and len(re.findall(r"\[[A-Z][A-Z_]+_\d+\]", held)) >= 3
          and not any(v in held for v in values) and "venerdì" in held, (held or "")[:110])
    again, why_again, clip_again = run(message(held or PLAIN))
    check("incollata la versione protetta, il messaggio parte (uscita 0) e gli appunti non vengono toccati", again == 0 and why_again == "" and clip_again is None, why_again[:80])
    plain, why_plain, clip_plain = run(message(PLAIN))
    check("messaggio senza dati personali: parte, senza dire nulla", plain == 0 and why_plain == "" and clip_plain is None, why_plain[:80])
    as_text = run({"prompt": PERSONAL})[0]
    check("il testo arriva come elenco di parti o come frase sola: in tutti e due i casi viene controllato", as_text == 2)
    log = [json.loads(x) for x in (paths.DATA / "activity.jsonl").read_text(encoding="utf-8").splitlines()[-40:] if x.strip()]
    mine = [x for x in log if x.get("service") == "kimi" and x.get("method") == "hook"]
    written = json.dumps(log, ensure_ascii=False)
    check("nel registro di Omissis: il servizio, «app desktop», il programma e i conteggi; mai il testo né i valori",
          len(mine) >= 3 and all(x.get("via") == "app desktop" and x.get("client") == "Kimi (plugin)" for x in mine) and any(sum((x.get("replacements") or {}).values()) >= 3 for x in mine)
          and not any(v in written for v in values), str({k: v for k, v in mine[0].items() if k != "ts"})[:150] if mine else "nessuna riga")

    # --- cio' che non e' un messaggio da controllare
    quiet = [run(b"non e' JSON")[0], run({"prompt": [{"type": "text", "text": "   "}]})[0], run({"hook_event_name": "PreToolUse", "prompt": PERSONAL})[0],
             run({"prompt": [{"type": "image_url", "imageUrl": {"url": "data:,"}}]})[0]]
    check("dati non leggibili, messaggio vuoto, un altro evento, una sola immagine: l'hook lascia fare", quiet == [0, 0, 0, 0], str(quiet))

    # --- Omissis non risponde, oppure non c'e' piu'
    off, why_off, clip_off = run(message(PERSONAL), OMISSIS_PORT="9")
    gone = run(message(PERSONAL), OMISSIS_DATA=str(work / "non-esiste"))[0]
    check("Omissis spento, con il servizio su «Proteggi»: il messaggio viene fermato, mai mandato senza protezione, e la spiegazione dice che cosa fare",
          off == 2 and "Omissis" in why_off and clip_off is None, why_off[:90])
    check("Omissis tolto dal PC (cartella dei dati sparita): il plugin rimasto non decide nulla", gone == 0)

    # --- le altre regole del servizio
    try:
        rule("block")
        blocked, why_blocked, clip_blocked = run(message(PLAIN))
        off_blocked = run(message(PLAIN), OMISSIS_PORT="9")[0]
        rule("ignore")
        ignored = run(message(PERSONAL))
        off_ignored = run(message(PERSONAL), OMISSIS_PORT="9")[0]
        check("servizio su «Blocca»: fermato qualunque messaggio, senza appunti; su «Ignora»: parte anche con dati personali",
              blocked == 2 and "Kimi" in why_blocked and clip_blocked is None and ignored == (0, "", None),
              f"blocca {blocked} · ignora {ignored[0]} · {why_blocked[:60]}")
        check("Omissis spento: resta fermo ciò che era da bloccare; dove il servizio non era da proteggere il messaggio parte", off_blocked == 2 and off_ignored == 0,
              f"era «Blocca» {off_blocked} · era «Ignora» {off_ignored}")
    finally:
        rule(None)
    print("\nTUTTO BENE" if ok else "\nQUALCOSA NON VA")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
