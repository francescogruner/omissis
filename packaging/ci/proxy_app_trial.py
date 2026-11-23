# -*- coding: utf-8 -*-
"""Prova su una macchina di GitHub (Mac o Windows): l'app vera di Claude protetta dal pulsante «Proteggi» del pannello.

L'app di Claude rifiuta la porta di debug (vedi packaging/mac/desktop_apps_test.py), ma usa il proxy e i certificati del
sistema, come nelle reti aziendali. Il pannello di Omissis la protegge da lì: mette il suo certificato tra quelli fidati
e dà al sistema un file PAC che manda al proxy solo il traffico verso claude.ai. All'app non si passa nessuna opzione:
la si apre come la apre chiunque, e la si usa con il proprio accesso.

Che cosa fa:
  1. installa l'app di Claude dal sito del produttore (Windows: pacchetto .msix, con la firma controllata; Mac: Homebrew);
  2. accende una copia di prova di Omissis; accanto al suo proxy gira un addon che annota che cosa passa: host, metodo,
     percorso, stato. Mai corpi né cookie;
  3. apre l'app PRIMA di accendere la protezione, poi preme il pulsante del pannello: è il pannello a impostare la rete;
  4. guarda se l'app già aperta comincia a passare dal proxy, la fa riaprire dal pannello e riguarda;
  5. ferma la protezione (il traffico verso claude.ai non deve uscire in chiaro), la riavvia, toglie la protezione,
     chiude Omissis: il sistema deve tornare com'era.

Il certificato qui lo si mette per tutta la macchina, da amministratore: su un computer vero lo mette il pannello per chi
lo usa, e il sistema gli chiede conferma. Quella domanda in una prova automatica non ha nessuno che risponda.

Senza un account si vede solo la finestra d'ingresso dell'app: che un messaggio venga sostituito NON si vede da qui.

Cambia il proxy e i certificati del sistema e chiude l'app di Claude: parte solo con CI=1, mai sul computer di una persona.

  python proxy_app_trial.py <cartella dei risultati>
"""
import collections
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

if not os.environ.get("CI"):
    sys.exit("Questa prova cambia proxy e certificati del sistema e chiude l'app di Claude: solo su una macchina di prova (CI=1).")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = Path(sys.argv[1]).resolve()
WORK = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / "omissis-proxy"
DATA = WORK / "data"
WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"
ENGINE, PANEL, PROXY = 8775, 8776, 8781
FLOWS = OUT / "flussi.jsonl"
FAMILY = "Claude_pzs8sxrjxfjjc"   # la famiglia del pacchetto di Claude per Windows

OUT.mkdir(parents=True, exist_ok=True)
(DATA / "lists").mkdir(parents=True, exist_ok=True)
# le variabili vanno messe prima di caricare il codice di Omissis: dicono dove stanno i dati di questa copia di prova, che
# la macchina e' di prova (il pannello puo' toccarne le impostazioni vere) e quale addon mettere accanto al proxy
os.environ.update(OMISSIS_PORT=str(ENGINE), OMISSIS_TEST="1", OMISSIS_DATA=str(DATA), OMISSIS_LISTS=str(DATA / "lists"), PYTHONUTF8="1",
                  OMISSIS_REAL_SYSTEM="1", OMISSIS_TEST_ADDON=str(HERE / "proxy_log_addon.py"), OMISSIS_TRIAL_LOG=str(FLOWS))
if MAC:
    os.environ["OMISSIS_FAKE_KEYCHAIN"] = str(WORK / "keychain.json")
sys.path[:0] = [str(ROOT / "app")]
import connector   # noqa: E402
import sistema     # noqa: E402

APP = connector.APP["claude"]
OURS = f"http://127.0.0.1:{PANEL}/proxy.pac"
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # le chiamate della prova non passano da nessun proxy
RESULTS, STARTED, CODE = [], [], []
REPORT = (OUT / "esito.txt").open("w", encoding="utf-8")


def say(*parts):
    line = " ".join(str(p) for p in parts)
    print(line, flush=True)
    REPORT.write(line + "\n")
    REPORT.flush()


def check(ok, text, detail=""):
    RESULTS.append(bool(ok))
    say(("OK    " if ok else "NO    ") + text + (f"   [{detail}]" if detail else ""))
    return bool(ok)


def run(command, timeout=120, **how):
    try:
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, **how)
    except (OSError, subprocess.TimeoutExpired) as ex:
        return subprocess.CompletedProcess(command, 999, "", f"{type(ex).__name__}: {ex}")


def wait(condition, seconds):
    for _ in range(int(seconds * 2)):
        if condition():
            return True
        time.sleep(0.5)
    return bool(condition())


def shot(name):
    target = OUT / f"{name}.png"
    try:
        if MAC:
            subprocess.run(["screencapture", "-x", str(target)], timeout=30, check=False)
        else:
            from PIL import ImageGrab
            ImageGrab.grab(all_screens=True).save(target)
    except Exception as ex:   # noqa: BLE001
        say(f"      schermata {name} non riuscita: {type(ex).__name__}: {ex}")


def running():
    return connector.processes(APP.get("process"))


# ---------------------------------------------------------------- l'app di Claude

def install_app():
    say("### installazione dell'app di Claude")
    if WINDOWS:
        latest = json.loads(DIRECT.open("https://downloads.claude.ai/releases/win32/x64/.latest", timeout=60).read().decode("utf-8"))
        address = f"https://downloads.claude.ai/releases/win32/x64/{latest['version']}/Claude-{latest['hash']}.msix"
        target = WORK / "Claude.msix"
        say("pacchetto:", address)
        with DIRECT.open(address, timeout=120) as r, open(target, "wb") as f:
            shutil.copyfileobj(r, f, 4 << 20)
        say(f"scaricati {target.stat().st_size / 1e6:.0f} MB")
        script = (f"$s = Get-AuthenticodeSignature -FilePath '{target}'; "
                  "Write-Output ('firma: ' + $s.Status + ' | ' + $s.SignerCertificate.Subject); "
                  "if ($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Anthropic') { Write-Output 'FIRMA NON VALIDA'; exit 3 }; "
                  f"Add-AppxPackage -Path '{target}'; "
                  "Get-AppxPackage -Name Claude | ForEach-Object { 'installata: ' + $_.PackageFullName }")
        # senza PSModulePath: quello di PowerShell 7 (la shell del lavoro) farebbe caricare a Windows PowerShell i moduli sbagliati
        clean = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
        r = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=900, env=clean)
        say((r.stdout + r.stderr).strip()[:600])
    else:
        env = {**os.environ, "HOMEBREW_NO_ANALYTICS": "1", "HOMEBREW_NO_ENV_HINTS": "1", "HOMEBREW_NO_INSTALL_CLEANUP": "1"}
        run(["brew", "update"], timeout=600, env=env)
        r = run(["brew", "install", "--cask", "claude"], timeout=900, env=env)
        if r.returncode:
            say((r.stdout + r.stderr).strip()[-800:])
        run(["xattr", "-dr", "com.apple.quarantine", "/Applications/Claude.app"])
        say("versione:", run(["defaults", "read", "/Applications/Claude.app/Contents/Info", "CFBundleShortVersionString"]).stdout.strip())
    command = connector.find_command(APP)
    check(command is not None, "l'app di Claude è installata dove Omissis la cerca", str(command))
    return command


def open_app(command):
    """L'app aperta come la apre chi usa il computer: nessuna opzione."""
    if WINDOWS and command.startswith("package:"):
        subprocess.Popen(["explorer.exe", rf"shell:AppsFolder\{FAMILY}!Claude"])
    elif MAC:   # come dal Dock: la avvia il sistema, non questa prova
        subprocess.run(["open", "-a", str(Path(command).parents[2])], timeout=60, check=False)
    else:
        subprocess.Popen([command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **sistema.detached())


def app_log(since):
    """Che cosa dice l'app, nei suoi registri, di proxy e certificati."""
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA") or home)
    places = [home / "Library" / "Logs" / "Claude", local / "Claude-Data", local / "Packages" / FAMILY,
              Path(os.environ.get("APPDATA") or home) / "Claude"]
    rx = re.compile(r"(?i)proxy|certificat|distrust|refused the connection|net::err")
    shown = 0
    for place in places:
        if not place.exists():
            continue
        for f in sorted(place.rglob("*.log")):
            try:
                if f.stat().st_mtime < since:
                    continue
                lines = [line for line in f.read_text(encoding="utf-8", errors="replace").splitlines() if rx.search(line)]
            except OSError:
                continue
            for line in lines[-8:]:
                say("      registro dell'app:", f.name, "|", line[:240])
                shown += 1
    if not shown:
        say("      nei registri dell'app non c'è niente su proxy e certificati")


# ---------------------------------------------------------------- Omissis di prova e il suo pannello

def panel(path, data=None):
    """Una chiamata al pannello, come le fa la sua pagina. Un rifiuto torna come {"error": frase}."""
    try:
        if not CODE:
            page = DIRECT.open(f"http://127.0.0.1:{PANEL}/", timeout=20).read().decode("utf-8")
            CODE.append(re.search(r'name="omissis-code" content="([^"]+)"', page).group(1))
        req = urllib.request.Request(f"http://127.0.0.1:{PANEL}{path}", headers={"X-Panel": CODE[0], "Content-Type": "application/json"},
                                     data=json.dumps(data).encode("utf-8") if data is not None else None)
        with DIRECT.open(req, timeout=200) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        try:
            return {"error": json.loads(ex.read().decode("utf-8")).get("error", str(ex.code))}
        except ValueError:
            return {"error": str(ex.code)}
    except OSError as ex:
        return {"error": f"{type(ex).__name__}: {ex}"}


def card():
    """Lo stato della strada del proxy per l'app di Claude, come lo mostra il pannello."""
    listing = panel("/api/app")
    mine = next((a for a in listing if a["id"] == "claude"), {}) if isinstance(listing, list) else {}
    return mine.get("proxy") or {}


def active():
    return panel("/api/status").get("phase") == "active"


def start_omissis():
    say("### Omissis di prova")
    for f in (ROOT / "model" / "lists").glob("*.txt"):
        shutil.copy2(f, DATA / "lists" / f.name)
    (DATA / "settings.json").write_text(json.dumps({"port": PROXY, "onboarded": True, "ask_apps": False}), encoding="utf-8")
    log = open(WORK / "panel.log", "wb")
    p = subprocess.Popen([sys.executable, str(ROOT / "app" / "panel.py"), "--test", "--no-tray", "--no-browser"],
                         cwd=ROOT / "app", stdout=log, stderr=subprocess.STDOUT)
    STARTED.append(p)
    began = time.time()
    ok = wait(lambda: p.poll() is not None or (connector.opened_port(PANEL) and active()), 600) and p.poll() is None
    check(ok, "la protezione di Omissis è attiva (motore, modello e proxy)", f"dopo {time.time() - began:.0f} s")
    if not ok:
        say((WORK / "panel.log").read_text(encoding="utf-8", errors="replace")[-1500:])
    return ok


def flows(since=0):
    out = []
    try:
        for line in FLOWS.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("t", 0) >= since:
                out.append(e)
    except OSError:
        pass
    return out


def of_claude(host):
    return host == "claude.ai" or host.endswith(".claude.ai")


def passing(since):
    """Dal momento dato, il proxy ha letto almeno una richiesta dell'app verso claude.ai?"""
    return any(e["event"] == "request" and of_claude(e.get("host", "")) for e in flows(since))


def trust(install):
    """Il certificato del proxy tra quelli di cui si fida tutta la macchina, da amministratore e senza domande (su un
    computer vero lo mette il pannello per chi lo usa, e il sistema gli chiede conferma)."""
    if WINDOWS:
        cer = DATA / "ca" / "mitmproxy-ca-cert.cer"
        run(["certutil", "-addstore", "-f", "Root", str(cer)] if install else ["certutil", "-delstore", "Root", "mitmproxy"])
        r = run(["certutil", "-store", "Root", "mitmproxy"])
        return r.returncode == 0 and "mitmproxy" in r.stdout
    pem = DATA / "ca" / "mitmproxy-ca-cert.pem"
    if install:
        r = run(["sudo", "security", "add-trusted-cert", "-d", "-r", "trustRoot", "-k", "/Library/Keychains/System.keychain", str(pem)], timeout=60)
        if r.returncode:
            say("      security:", (r.stdout + r.stderr).strip()[:300])
    return run(["security", "verify-cert", "-c", str(pem)]).returncode == 0


def report(name, since):
    events = flows(since)
    by = {}
    for e in events:
        c = by.setdefault(e.get("host") or "?", collections.Counter())
        c[e["event"]] += 1
        if e["event"] == "response":
            c[f"stato {e['status']}"] += 1
            if e.get("mitigated"):
                c[f"cloudflare {e['mitigated']}"] += 1
    say("      che cosa è passato dal proxy di Omissis, per host:")
    for host, c in sorted(by.items()):
        say("        ", host, "|", ", ".join(f"{k} {v}" for k, v in sorted(c.items())))
    mine = [e for e in events if of_claude(e.get("host", ""))]
    connects = sum(e["event"] == "connect" for e in mine)
    requests = [e for e in mine if e["event"] == "request"]
    answers = [e for e in mine if e["event"] == "response"]
    say("      programmi che chiamano claude.ai:", ", ".join(sorted({e["program"] for e in requests if e.get("program")})) or "non detto")
    for e in answers[:12]:
        say("        ", e["method"], e["path"], "->", e["status"], e["kind"], ("| cloudflare: " + e["mitigated"]) if e["mitigated"] else "",
            "| visto da Omissis" if e.get("omissis") else "")
    # Una stretta di mano non finita non e' per forza un certificato rifiutato: Chromium apre due connessioni insieme e ne
    # abbandona una appena l'altra e' pronta. Un rifiuto vero viene invece da un programma di tipo diverso da quelli le cui
    # connessioni riescono (o dice perche': un avviso TLS).
    hellos = {e.get("client"): e for e in events if e["event"] == "hello"}
    failed = [e for e in events if e["event"] == "tls_failed"]

    def kind(e):
        h = hellos.get(e.get("client"))
        return (h["grease"], tuple(h["alpn"]), h["suites"]) if h else None
    done = [e for e in events if e["event"] == "tls_ok"]
    kinds = {kind(e) for e in done} - {None}
    refused = []
    for e in failed:
        # «connection closed early»: chi chiama ha chiuso prima ancora che il proxy gli mostrasse il certificato. Non lo ha
        # visto, quindi non puo' averlo rifiutato (mitmproxy stesso non lo segna tra le strette di mano fallite)
        if "connection closed early" in e["error"]:
            continue
        dropped = "disconnected during the handshake" in e["error"]
        same = kind(e) in kinds
        # su Windows chi non si fida chiude senza dirlo, come chi abbandona: fa fede il tipo. Solo Chromium, che ha una
        # sola idea dei certificati per tutta l'app, puo' aver chiuso una connessione uguale a quelle riuscite
        if not (dropped and same and kind(e)[0]):
            refused.append(e)
            say("         certificato rifiutato:", e["host"], "|", e["error"][:160])
    for e in [e for e in events if e["event"] == "error"][:5]:
        say("         errore:", e["host"], e["path"], "|", e["error"])
    check(connects > 0, f"{name}: l'app manda al proxy di Omissis il traffico verso claude.ai", f"collegamenti {connects}")
    read = bool(requests) and any(of_claude(e["host"]) for e in done)
    check(read, f"{name}: l'app accetta il certificato di Omissis, il proxy legge le richieste", f"richieste lette {len(requests)}, strette di mano riuscite {len(done)}")
    check(not refused, f"{name}: nessuna parte dell'app rifiuta il certificato", f"rifiuti {len(refused)}, connessioni doppie abbandonate {len(failed) - len(refused)}")
    good = [e for e in answers if e["status"] < 400]
    check(bool(good), f"{name}: claude.ai risponde attraverso il proxy", f"risposte buone {len(good)} su {len(answers)}")
    check(any(e.get("omissis") for e in answers), f"{name}: Omissis riconosce quelle richieste come servizio da proteggere")
    others = sorted(h for h in by if not of_claude(h))
    check(not others, f"{name}: dal proxy passa solo claude.ai, il resto del computer esce come prima", ", ".join(others)[:200])


def contacts():
    try:
        db = sqlite3.connect(DATA / "contacts.sqlite", timeout=10)
        rows = db.execute("SELECT service, host, outcome, n FROM contacts ORDER BY service, host, outcome").fetchall()
        seen = db.execute("SELECT service, via, client, last FROM clients").fetchall()
        db.close()
    except sqlite3.Error as ex:
        rows = seen = []
        say("      registro dei contatti non letto:", ex)
    for r in rows + seen:
        say("      registro di Omissis:", " | ".join(str(x) for x in r))
    check(any(r[0] == "claude" and r[2] == "guarded" for r in rows), "nel registro di Omissis Claude risulta contattato e sotto protezione")
    check(any(r[0] == "claude" and r[1] == "proxy" and r[2].startswith("Claude ") for r in seen), "nel registro di Omissis c'è l'app di Claude tra i programmi visti dal proxy")


def quit_omissis(p):
    """Chiude Omissis come lo chiude chi lo usa (qui con il segnale di interruzione). True se si e' chiuso da solo."""
    try:
        p.send_signal(signal.SIGINT)
        p.wait(40)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    return p.poll() is not None


def main():
    say("### macchina:", sys.platform, "|", run(["sw_vers", "-productVersion"]).stdout.strip() if MAC else run(["cmd", "/c", "ver"]).stdout.strip())
    command = install_app()
    try:
        if command is None or not start_omissis():
            return
        say("proxy del sistema prima:", sistema.system_proxy())
        state = card()
        check(state.get("available") is True and state.get("on") is False, "il pannello offre «Proteggi Claude»", str(state)[:200])
        check(state.get("certificate") is False, "prima: per il pannello il certificato non è tra quelli fidati")

        say("\n=================== 1 l'app aperta prima, senza protezione")
        began = time.time()
        open_app(command)
        check(wait(lambda: bool(running()), 45), "1: l'app di Claude parte, senza nessuna opzione", f"processi {len(running())}")
        time.sleep(40)
        shot("1-senza-protezione")
        first = set(running())
        check(not passing(began), "1: senza protezione niente passa dal proxy di Omissis")

        say("\n=================== 2 «Proteggi Claude» dal pannello, con l'app già aperta")
        check(trust(True), "2: il certificato è tra quelli fidati della macchina (qui messo da amministratore)")
        check(wait(lambda: card().get("certificate") is True, 20), "2: il pannello riconosce che il sistema si fida del certificato")
        pressed = time.time()
        answer = panel("/api/app", {"id": "claude", "action": "proxy_on"})
        check(isinstance(answer, list), "2: il pulsante «Proteggi Claude» riesce", "" if isinstance(answer, list) else answer.get("error", "")[:200])
        now = sistema.system_proxy()
        check(now["pac"].startswith(OURS) and not now["proxy"], "2: il sistema ha il file PAC del pannello", str(now))
        try:
            pac = DIRECT.open(now["pac"] or OURS, timeout=10).read().decode("utf-8")
            check('"claude.ai"' in pac and f"PROXY 127.0.0.1:{PROXY}" in pac, "2: il file PAC manda al proxy solo claude.ai", " ".join(pac.split())[:170])
        except OSError as ex:
            check(False, "2: il file PAC si legge", str(ex))
        live = wait(lambda: passing(pressed), 80)
        say(("SÌ    " if live else "NO    ") + "2: l'app già aperta comincia a passare dal proxy senza essere riaperta (solo per sapere: non conta tra i controlli)")
        expected = "protected" if live else "reopen"   # aperta da prima: non ha letto le impostazioni nuove, e il pannello lo deve dire
        check(wait(lambda: card().get("state") == expected, 70),
              "2: il pannello dice la verità sull'app già aperta: " + ("passa da Omissis" if live else "è senza protezione e va riaperta"), str(card())[:230])
        shot("2-protetta-con-app-aperta")

        say("\n=================== 3 il pannello chiude e riapre Claude")
        reopened = time.time()
        answer = panel("/api/app", {"id": "claude", "action": "reopen"})
        check(isinstance(answer, list), "3: «Chiudi e riapri Claude» riesce", "" if isinstance(answer, list) else answer.get("error", "")[:200])
        if not isinstance(answer, list):
            say("      processi dell'app:", run(["ps", "-axo", "pid,ppid,stat,etime,comm"]).stdout.count("Claude") if MAC else len(running()))
        check(wait(lambda: bool(running()) and not (set(running()) & first), 45), "3: l'app è ripartita", f"processi {len(running())}")
        wait(lambda: passing(reopened), 90)
        time.sleep(25)
        shot("3-riaperta-dal-pannello")
        report("3", reopened)
        check(wait(lambda: card().get("state") == "protected", 60), "3: il pannello dice che l'app è protetta", str(card())[:230])
        app_log(began)

        say("\n=================== 4 protezione ferma e riavviata")
        panel("/api/protection", {"action": "stop"})
        wait(lambda: not connector.opened_port(PROXY), 30)
        now = sistema.system_proxy()
        check(not connector.opened_port(PROXY) and now["pac"].startswith(OURS),
              "4: a protezione ferma il file PAC resta e il proxy è chiuso: il traffico verso claude.ai non esce in chiaro", str(now))
        check(card().get("problem") == "paused", "4: il pannello dice che la protezione è ferma e che l'app non si collega", str(card())[:200])
        time.sleep(20)
        resumed = time.time()
        panel("/api/protection", {"action": "start"})
        check(wait(active, 180), "4: la protezione riparte")
        check(wait(lambda: card().get("state") == "protected", 30), "4: ripartita, il pannello dà di nuovo l'app per protetta (era partita con la protezione)", str(card())[:200])
        alone = wait(lambda: passing(resumed), 240 if WINDOWS else 60)
        say(("SÌ    " if alone else "NO    ") + f"4: l'app torna da sola a passare da Omissis entro {240 if WINDOWS else 60} secondi (solo per sapere: non conta tra i controlli)")
        if not alone:
            again = time.time()
            answer = panel("/api/app", {"id": "claude", "action": "reopen"})
            check(isinstance(answer, list) and wait(lambda: passing(again), 100), "4: riaperta dal pannello, l'app torna a passare da Omissis",
                  "" if isinstance(answer, list) else answer.get("error", "")[:200])
        app_log(resumed - 25)

        say("\n=================== 5 «Togli la protezione», e la chiusura di Omissis")
        answer = panel("/api/app", {"id": "claude", "action": "proxy_off"})
        now = sistema.system_proxy()
        check(isinstance(answer, list) and not now["pac"] and not now["proxy"], "5: «Togli la protezione» lascia il sistema senza file PAC", str(now))
        answer = panel("/api/app", {"id": "claude", "action": "proxy_on"})
        check(isinstance(answer, list) and sistema.system_proxy()["pac"].startswith(OURS), "5: riaccesa, il file PAC torna")
        contacts()
        if MAC:
            closed = quit_omissis(STARTED[0])
            now = sistema.system_proxy()
            check(closed and not now["pac"], "5: chiudendo Omissis il file PAC viene tolto: nessuna impostazione resta appesa", str(now))
        else:
            say("      la chiusura di Omissis qui non si prova: su Windows il segnale di interruzione non arriva a un programma senza console")
    finally:
        say("\n### rimetto com'era")
        if sistema.system_proxy()["pac"].startswith(OURS):
            say("file PAC tolto:", sistema.system_pac(""))
        connector.close_app("claude", grace=10)
        for p in reversed(STARTED):
            if p.poll() is None:
                p.terminate()
        if WINDOWS and (DATA / "ca" / "mitmproxy-ca-cert.cer").exists():
            say("certificato ancora tra quelli fidati:", trust(False))
        try:
            say("--- registro di Omissis (ultime righe)")
            say((WORK / "panel.log").read_text(encoding="utf-8", errors="replace")[-1200:])
        except OSError:
            pass
    say(f"\n{'TUTTO OK' if RESULTS and all(RESULTS) else 'NON TUTTO OK'}: {sum(RESULTS)}/{len(RESULTS)} controlli")


main()
sys.exit(0 if RESULTS and all(RESULTS) else 1)
