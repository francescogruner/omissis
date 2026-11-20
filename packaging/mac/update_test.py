# -*- coding: utf-8 -*-
"""Prova, con l'app vera costruita in dist/, cio' che sul Mac fa il programma al posto di un installer: l'aggiornamento
(riuscito, fallito con ritorno alla versione di prima, fatto all'avvio), l'apertura dal disco di installazione con lo
spostamento in Applicazioni, l'avvio all'accesso e la disinstallazione.

  dist/Omissis.app/Contents/Resources/python/bin/python3 packaging/mac/update_test.py [parti...]

Va lanciata con il Python dell'app costruita (ha le librerie per firmare) dopo build_mac.py. Parti: update rollback
auto move login uninstall (senza argomenti: tutte quelle che il sistema permette). Su Linux (prove senza Mac) girano
le prime tre, con un archivio tar al posto dell'immagine disco.

Non usa la chiave vera degli aggiornamenti: ne crea una usa e getta, che la copia di prova accetta perche' e' una copia
di prova (OMISSIS_TEST=1 e OMISSIS_UPDATES_TEST_KEY). Le versioni «nuove» sono copie dell'app costruita con un numero di
versione piu' alto; quella che non deve partire ha il pannello rotto apposta. Tutto resta su questa macchina: i
pacchetti li serve un piccolo servizio su 127.0.0.1.

NON va lanciata sul Mac di una persona: le parti login e uninstall scrivono in ~/Library/LaunchAgents e avviano una
copia normale di Omissis. Per questo partono solo con CI=1.
"""
import base64
import functools
import hashlib
import http.server
import json
import os
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
BUILT = ROOT / "dist" / "Omissis.app"
MAC = sys.platform == "darwin"
WORK = Path(os.environ.get("RUNNER_TEMP") or "/tmp") / "omissis-update"
OUT = ROOT / "dist" / "update"
PORT = int(os.environ.get("OMISSIS_UPDATE_TEST_PORT") or 8815)   # la copia di prova: motore, pannello (+1), gateway (+2). Porte solo sue
PANEL, SERVED_PORT = f"http://127.0.0.1:{PORT + 1}", PORT + 150
TARGET = f"{'mac' if MAC else 'linux'}-{'arm64' if os.uname().machine.lower() in ('arm64', 'aarch64') else 'x86_64'}"
KEY = Ed25519PrivateKey.generate()   # usa e getta: vive quanto questa prova
outcomes = []


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(("OK   " if ok else "NO   ") + name + (f"  ({note})" if note else ""), flush=True)


def say(text):
    print(f"--- {text}", flush=True)


def run(command, timeout=600, check=True):
    r = subprocess.run([str(c) for c in command], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"{Path(str(command[0])).name}: {(r.stdout + r.stderr).strip()[-300:]}")
    return r


# ------------------------------------------------------------------ il pannello della copia di prova

def page_code():
    with urllib.request.urlopen(PANEL + "/", timeout=5) as r:
        return re.search(r'name="omissis-code" content="([^"]+)"', r.read().decode("utf-8")).group(1)


def call(path, data=None, timeout=60):
    req = urllib.request.Request(PANEL + path, headers={"X-Panel": page_code(), "Content-Type": "application/json"},
                                 data=json.dumps(data).encode("utf-8") if data is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        return {"refused": json.loads(ex.read().decode("utf-8")).get("error", str(ex.code))}


def wait_panel(timeout=120, version=None, gone_first=False):
    """Aspetta che il pannello risponda (se chiesto: prima che il programma di adesso si chiuda, poi che risponda uno
    nuovo, con quella versione). Lo stato, o None. Un programma ripartito si riconosce dal codice nuovo della sua pagina."""
    end = time.time() + timeout
    if gone_first:
        try:
            first = page_code()
        except (OSError, AttributeError):
            first = None
        while first and time.time() < end:
            try:
                if page_code() != first:
                    break
                time.sleep(0.3)
            except (OSError, AttributeError):
                break
    while time.time() < end:
        try:
            s = call("/api/status", timeout=5)
            if "version" in s and (version is None or s["version"] == version):
                return s
        except (OSError, AttributeError, ValueError):
            pass
        time.sleep(0.5)
    return None


def env_for(data, **more):
    public = base64.b64encode(KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode("ascii")
    env = {k: v for k, v in os.environ.items() if not k.startswith("OMISSIS_")}
    # OMISSIS_SWAP_WAIT: quanto aspettare la versione nuova prima di rimettere la vecchia (di serie due minuti)
    env.update(OMISSIS_PORT=str(PORT), OMISSIS_TEST="1", OMISSIS_DATA=str(data), OMISSIS_LISTS=str(data / "lists"), OMISSIS_SWAP_WAIT="45",
               OMISSIS_FAKE_KEYCHAIN=str(WORK / "keychain.json"), OMISSIS_UPDATES_URL=f"http://127.0.0.1:{SERVED_PORT}/versioni",
               OMISSIS_UPDATES_TEST_KEY=public, **more)
    return env


def start(app, env, log):
    """Avvia l'app come una copia di prova: senza icona, senza browser, senza protezione (qui non serve il modello)."""
    # avviata da una shell che esce subito: cosi' l'app non resta «figlia» di questa prova, come quando la apre macOS
    subprocess.run(["/bin/sh", "-c", '"$0" "$@" >> "$LOG" 2>&1 &', str(app / "Contents" / "MacOS" / "Omissis"), "--test", "--no-tray", "--no-browser", "--no-start"],
                   env={**env, "LOG": str(log)}, start_new_session=True, check=True)


def processes(app):
    out = run(["ps", "-axo", "pid=,command="], check=False).stdout
    return [(int(line.split(None, 1)[0]), line.split(None, 1)[1]) for line in out.splitlines() if f"{app}/Contents/" in line]


def stop(app):
    for sig in (15, 9):
        for pid, _ in processes(app):
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        time.sleep(1.5)


def leftovers(app):
    return [n for n in ("Contents.new", "Contents.old", "Contents.bad") if (app / n).exists()]


def result(data):
    try:
        return (data / "updates" / "result.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# ------------------------------------------------------------------ versioni finte e pacchetti

def copy_app(origin, destination):
    shutil.rmtree(destination, ignore_errors=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if MAC:   # copia «a costo zero» sui dischi del Mac (APFS); se non si puo', copia normale
        if run(["cp", "-Rc", origin, destination], check=False).returncode != 0:
            shutil.rmtree(destination, ignore_errors=True)
            run(["cp", "-R", origin, destination])
    else:
        run(["cp", "-a", origin, destination])


def set_version(app, version, broken=False):
    base = app / "Contents" / "Resources" / "omissis"
    (base / "installed.json").write_text(json.dumps({"version": version, "channel": "github"}), encoding="utf-8")
    f = base / "app" / "version.py"
    text, n = re.subn(r'VERSION = "[^"]*"', f'VERSION = "{version}"', f.read_text(encoding="utf-8"))
    assert n == 1, "version.py"
    f.write_text(text, encoding="utf-8")
    if (app / "Contents" / "Info.plist").exists():
        with open(app / "Contents" / "Info.plist", "rb") as s:
            info = plistlib.load(s)
        info["CFBundleShortVersionString"] = info["CFBundleVersion"] = version
        with open(app / "Contents" / "Info.plist", "wb") as s:
            plistlib.dump(info, s)
    if broken:   # un pannello che non parte: le librerie ci sono, la versione e' giusta, ma il programma esce subito
        f = base / "app" / "panel.py"
        f.write_text("raise SystemExit('versione rotta apposta per la prova')\n" + f.read_text(encoding="utf-8"), encoding="utf-8")


def package(version, broken=False):
    """Una «versione nuova»: copia dell'app costruita con un altro numero, impacchettata come la scarica il programma."""
    folder = WORK / "versions" / version
    copy_app(BUILT, folder / "Omissis.app")
    set_version(folder / "Omissis.app", version, broken)
    began = time.time()
    if MAC:
        out = WORK / "served" / "versioni" / f"Omissis-{version}-{TARGET}.dmg"
        out.unlink(missing_ok=True)
        run(["hdiutil", "create", "-volname", "Omissis", "-srcfolder", folder, "-ov", "-format", "UDRO", out], timeout=900)   # senza compressione: piu' veloce
    else:
        out = WORK / "served" / "versioni" / f"Omissis-{version}-{TARGET}.tar.gz"
        with tarfile.open(out, "w:gz", compresslevel=1) as t:
            t.add(folder / "Omissis.app", arcname="Omissis.app")
    shutil.rmtree(folder, ignore_errors=True)
    say(f"pacchetto {out.name}: {out.stat().st_size / 1e6:.0f} MB in {time.time() - began:.0f} s")
    return out


def publish(version, file):
    h = hashlib.sha256()
    with open(file, "rb") as s:
        for chunk in iter(lambda: s.read(1 << 20), b""):
            h.update(chunk)
    sheet = json.dumps({"product": "omissis", "version": version, "platform": TARGET, "file": file.name, "byte": file.stat().st_size,
                        "sha256": h.hexdigest(), "notes": "prova"}).encode("utf-8")
    folder = WORK / "served" / "versioni"
    (folder / f"update-{TARGET}.json").write_bytes(sheet)
    (folder / f"update-{TARGET}.json.sig").write_bytes(base64.b64encode(KEY.sign(sheet)))


def bump(version, by):
    parts = [int(x) for x in version.split(".")]
    return ".".join(str(x) for x in (*parts[:-1], parts[-1] + by))


def get_ready(version, timeout=600):
    """Dal pannello: controlla, scarica e aspetta che la versione sia pronta (sul Mac: scompattata e controllata)."""
    s = call("/api/updates", {"action": "check"})
    if s.get("phase") != "available" or s.get("version") != version:
        return s
    call("/api/updates", {"action": "download"})
    end = time.time() + timeout
    while time.time() < end:
        s = call("/api/status")["update"]
        if s["phase"] in ("ready_now", "error"):
            break
        time.sleep(1)
    return s


# ------------------------------------------------------------------ le parti

def part_update(ctx):
    app, data, v0 = ctx["app"], ctx["data"], ctx["v0"]
    start(app, env_for(data), WORK / "panel.log")
    s = wait_panel(90)
    mark("l'app in un posto suo parte e sa di potersi aggiornare da sola", bool(s) and s["version"] == v0 and s["update"].get("installable") is True
          and s["update"].get("reason") == "" and s["update"].get("platform") == TARGET, str(s and {k: s["update"].get(k) for k in ("installable", "reason", "platform")}))
    v1 = ctx["v1"] = bump(v0, 1)
    publish(v1, package(v1))
    call("/api/settings", {"theme": "dark"})   # un'impostazione di chi usa il Mac: deve restare dopo l'aggiornamento
    began = time.time()
    s = get_ready(v1)
    mark(f"versione {v1}: trovata, scaricata, scompattata accanto a quella in uso e controllata", s.get("phase") == "ready_now" and s.get("version") == v1
          and (app / "Contents.new" / ".omissis-update").exists(), f"{s.get('phase')} {s.get('error', '')} · {time.time() - began:.0f} s")
    if s.get("phase") != "ready_now":
        ctx.pop("v1")
        return
    began = time.time()
    r = call("/api/updates", {"action": "install"})
    s = wait_panel(150, version=v1, gone_first=True)
    took = time.time() - began
    time.sleep(3)   # chi ha fatto lo scambio scrive l'esito appena vede partita la versione nuova
    mark(f"«Installa ora»: l'app si chiude, viene sostituita e si riapre da sola con la versione {v1}", bool(s) and result(data) == f"ok {v1}" and not r.get("refused"),
          f"{took:.0f} s · esito «{result(data)}» · {r.get('refused', '')}")
    mark("della versione di prima non resta nulla, e i dati di chi usa il Mac sono gli stessi", not leftovers(app) and call("/api/settings").get("theme") == "dark", str(leftovers(app)))
    s = call("/api/updates", {"action": "check"})
    mark("dopo l'aggiornamento il programma risulta all'ultima versione, senza errori", s.get("phase") == "updated" and s.get("failed") == "", f"{s.get('phase')} {s.get('failed')}")


def part_rollback(ctx):
    app, data, v1 = ctx["app"], ctx["data"], ctx.get("v1") or ctx["v0"]
    if not wait_panel(5):
        start(app, env_for(data), WORK / "panel.log")
        wait_panel(90)
    v2 = ctx["v2"] = bump(v1, 1)
    publish(v2, package(v2, broken=True))
    s = get_ready(v2)
    mark(f"versione {v2} (rotta apposta: il pannello non parte): passa i controlli prima dello scambio", s.get("phase") == "ready_now", f"{s.get('phase')} {s.get('error', '')}")
    if s.get("phase") != "ready_now":
        ctx.pop("v2")
        return
    began = time.time()
    call("/api/updates", {"action": "install"})
    s = wait_panel(180, version=v1, gone_first=True)
    took = time.time() - began
    time.sleep(2)
    mark(f"la versione nuova non parte: torna la {v1} e si riapre da sola", bool(s) and result(data) == f"rolled_back {v2}" and not leftovers(app),
          f"{took:.0f} s · esito «{result(data)}» · resti {leftovers(app)}")
    mark("il pannello dice quale versione non e' partita", bool(s) and s["update"].get("failed") == v2, str(s and s["update"].get("failed")))
    # si chiude e si riapre il programma: la versione fallita non va ritentata da sola a ogni avvio
    stop(app)
    start(app, env_for(data), WORK / "panel.log")
    s = wait_panel(90, version=v1)
    time.sleep(8)
    mark("al riavvio la versione che non e' partita non viene ritentata da sola", bool(s) and bool(wait_panel(20, version=v1)) and result(data) == f"rolled_back {v2}")


def part_auto(ctx):
    app, data = ctx["app"], ctx["data"]
    base = ctx.get("v2") or ctx.get("v1") or ctx["v0"]
    if not wait_panel(5):
        start(app, env_for(data), WORK / "panel.log")
        wait_panel(90)
    v3 = ctx["v3"] = bump(base, 1)
    publish(v3, package(v3))
    s = get_ready(v3)
    mark(f"versione {v3}: pronta", s.get("phase") == "ready_now", f"{s.get('phase')} {s.get('error', '')}")
    if s.get("phase") != "ready_now":
        return
    stop(app)   # come uscire dal programma (o spegnere il Mac) con un aggiornamento pronto
    began = time.time()
    start(app, env_for(data), WORK / "panel.log")
    s = wait_panel(150, version=v3)
    time.sleep(3)
    mark(f"al successivo avvio la versione {v3} viene installata da sola, e il programma si riapre", bool(s) and result(data) == f"ok {v3}" and not leftovers(app),
          f"{time.time() - began:.0f} s · esito «{result(data)}»")


def part_move(ctx):
    """Aperta dal disco di installazione (sola lettura): lo dice, e si sposta in Applicazioni con una chiamata."""
    stop(ctx["app"])
    image = next(iter(sorted((ROOT / "dist").glob("Omissis-*-mac-*.dmg"))), None)
    if image is None:
        mark("immagine disco costruita da build_mac.py", False, "manca dist/Omissis-*.dmg")
        return
    volume, data, apps = WORK / "volume", WORK / "data2", WORK / "Applications2"
    volume.mkdir(exist_ok=True)
    run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", volume, image], timeout=300)
    ctx["volume"] = volume
    env = env_for(data, OMISSIS_APPLICATIONS=str(apps), OMISSIS_REAL_SYSTEM="1")
    start(volume / "Omissis.app", env, WORK / "panel2.log")
    s = wait_panel(120)
    system = call("/api/settings").get("system") or {}
    mark("aperta dal disco di installazione: parte, dice che da li' non si aggiorna e propone di spostarla",
          bool(s) and s["update"].get("installable") is False and s["update"].get("reason") == "move" and system.get("location") == "move"
          and system.get("login_item", {}).get("supported") is False, str({"update": s and s["update"].get("reason"), **system}))
    if system.get("location") != "move":
        return
    began = time.time()
    r = call("/api/system", {"action": "move"}, timeout=600)
    s = wait_panel(180, gone_first=True)
    system = call("/api/settings").get("system") or {}
    moved = apps / "Omissis.app"
    here = [c for _, c in processes(moved)]
    marked = run(["xattr", "-p", "com.apple.quarantine", moved], check=False).returncode == 0
    mark("«Sposta in Applicazioni»: l'app si copia, si chiude e si riapre dal posto nuovo, dove si aggiorna da sola",
          bool(s) and not r.get("refused") and system.get("location") == "ok" and bool(here) and s["update"].get("installable") is True and not marked,
          f"{time.time() - began:.0f} s · {r.get('refused', '')} · processi dal posto nuovo {len(here)} · segno di quarantena {marked}")
    ctx["moved"], ctx["data2"] = moved, data


def part_login(ctx):
    moved, data = ctx.get("moved"), ctx.get("data2")
    if moved is None:
        mark("avvio all'accesso: serve la parte «move»", False)
        return
    agent = Path.home() / "Library" / "LaunchAgents" / "eu.omissis.app.plist"

    def now():
        try:
            with open(agent, "rb") as f:
                return plistlib.load(f)
        except OSError:
            return {}
    first = now()
    mark("al primo avvio dal posto suo Omissis si mette tra i programmi che partono all'accesso",
          str(moved.resolve()) in first.get("ProgramArguments", []) and first.get("RunAtLoad") is True and run(["plutil", "-lint", agent], check=False).returncode == 0,
          str(first.get("ProgramArguments")))
    off = call("/api/system", {"action": "login_off"})
    gone = not agent.exists()
    on = call("/api/system", {"action": "login_on"})
    mark("dal pannello l'avvio all'accesso si spegne e si riaccende", off.get("login_item") == {"supported": True, "on": False} and gone
          and on.get("login_item") == {"supported": True, "on": True} and agent.exists(), f"{off.get('login_item')} · {on.get('login_item')}")
    # la prova vera: si spegne la copia di prova e si chiede a macOS di far partire la voce, come fa all'accesso.
    # Parte una copia normale (porte 8765-8767): basta vedere che il suo pannello risponde, poi la si ferma.
    stop(moved)
    domain = f"gui/{os.getuid()}"
    r = run(["launchctl", "bootstrap", domain, agent], check=False)
    up = False
    for _ in range(90):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8766/", timeout=2) as page:
                up = "Omissis" in page.read().decode("utf-8", errors="replace")
            break
        except OSError:
            time.sleep(1)
    here = [c for _, c in processes(moved)]
    mark("macOS, eseguendo la voce di avvio all'accesso, fa partire Omissis davvero", up and bool(here), f"launchctl {r.returncode} {(r.stdout + r.stderr).strip()[:120]} · processi {len(here)}")
    run(["launchctl", "bootout", f"{domain}/eu.omissis.app"], check=False)
    stop(moved)
    shutil.rmtree(Path.home() / "Library" / "Application Support" / "Omissis", ignore_errors=True)   # i dati della copia normale appena avviata


def part_uninstall(ctx):
    moved, data = ctx.get("moved"), ctx.get("data2")
    if moved is None:
        mark("disinstallazione: serve la parte «move»", False)
        return
    agent = Path.home() / "Library" / "LaunchAgents" / "eu.omissis.app.plist"
    if not wait_panel(5):
        start(moved, env_for(data, OMISSIS_APPLICATIONS=str(moved.parent), OMISSIS_REAL_SYSTEM="1"), WORK / "panel2.log")
        wait_panel(90)
    call("/api/system", {"action": "login_on"})
    r = call("/api/system", {"action": "uninstall", "data": True}, timeout=300)
    gone = False
    for _ in range(60):
        if not processes(moved) and not moved.exists() and not data.exists() and not agent.exists():
            gone = True
            break
        time.sleep(1)
    mark("«Togli Omissis» (con i dati): l'app va nel Cestino, la voce di avvio sparisce, i dati vengono cancellati e il programma si chiude",
          gone and r.get("trashed") is True and r.get("data") is True,
          f"{r} · app {moved.exists()} · dati {data.exists()} · voce {agent.exists()} · processi {len(processes(moved))}")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


PARTS = {"update": part_update, "rollback": part_rollback, "auto": part_auto, "move": part_move, "login": part_login, "uninstall": part_uninstall}
ONLY_MAC, ONLY_CI = {"move", "login", "uninstall"}, {"login", "uninstall"}


def main():
    wanted = [p for p in sys.argv[1:] if p in PARTS] or list(PARTS)
    if not BUILT.exists():
        sys.exit("manca dist/Omissis.app: lanciare prima build_mac.py")
    for port in (PORT, PORT + 1, PORT + 2, SERVED_PORT):   # un altro programma su queste porte risponderebbe al posto della copia di prova
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                sys.exit(f"la porta {port} e' occupata: questa prova vuole porte solo sue (OMISSIS_UPDATE_TEST_PORT ne indica altre)")
    shutil.rmtree(WORK, ignore_errors=True)
    (WORK / "served" / "versioni").mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", SERVED_PORT), functools.partial(Quiet, directory=str(WORK / "served")))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    v0 = json.loads((BUILT / "Contents" / "Resources" / "omissis" / "installed.json").read_text(encoding="utf-8"))["version"]
    app, data = WORK / "Applications" / "Omissis.app", WORK / "data"
    copy_app(BUILT, app)
    ctx = {"app": app, "data": data, "v0": v0}
    size = sum(f.stat().st_size for f in BUILT.rglob("*") if f.is_file() and not f.is_symlink())
    say(f"sistema {TARGET} · versione costruita {v0} · app scompattata {size / 1e6:.0f} MB · parti: {' '.join(wanted)}")
    try:
        for name in wanted:
            if name in ONLY_MAC and not MAC:
                print(f"SALTATO {name}: solo sul Mac", flush=True)
                continue
            if name in ONLY_CI and not os.environ.get("CI"):
                print(f"SALTATO {name}: solo su una macchina di prova (CI=1)", flush=True)
                continue
            say(name)
            try:
                PARTS[name](ctx)
            except Exception as ex:   # noqa: BLE001
                mark(f"parte «{name}»", False, f"{type(ex).__name__}: {ex}"[:300])
    finally:
        for target in (app, ctx.get("moved"), WORK / "volume" / "Omissis.app"):
            if target is not None:
                stop(target)
        if ctx.get("volume"):
            run(["hdiutil", "detach", ctx["volume"], "-force"], check=False)
        for log, name in ((WORK / "panel.log", "panel.log"), (WORK / "panel2.log", "panel2.log"), (data / "updates" / "relaunch.log", "relaunch.log"),
                          (WORK / "data2" / "updates" / "relaunch.log", "relaunch2.log"), (data / "updates" / "swap.sh", "swap.sh")):
            if log.exists():
                shutil.copyfile(log, OUT / name)
                if name != "swap.sh":
                    print(f"--- {name} (ultime righe)\n" + "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]), flush=True)
        server.shutdown()
    print(f"\n{sum(outcomes)}/{len(outcomes)} controlli superati")
    (OUT / "esito.txt").write_text(f"{sum(outcomes)}/{len(outcomes)}\n", encoding="utf-8")
    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
