# -*- coding: utf-8 -*-
"""Prova lo scambio di versione dell'app per Mac (macapp.py) con un'app finta, piccola, costruita al momento.

  python3 e2e_macapp.py

Gira su un Mac e, per le prove senza Mac, su Linux (su Windows non ha nulla da provare e lo dice). Non tocca nessuna
app vera: lavora in una cartella temporanea. L'app finta ha la stessa forma di Omissis.app (lanciatore, Python,
installed.json, version.py) e un «pannello» che scrive soltanto di essere partito. Sul Mac il pacchetto della versione
nuova e' una vera immagine disco (.dmg) e l'app viene riaperta da macOS; su Linux e' un archivio tar.

Che cosa controlla: il pacchetto viene scompattato accanto alla versione in uso e controllato; un pacchetto di un'altra
versione, di un altro canale o rovinato viene rifiutato senza lasciare nulla; lo scambio avviene a programma chiuso e
ferma i processi rimasti; se la versione nuova parte, quella di prima sparisce; se non parte, torna quella di prima e
viene riaperta.
"""
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

if sys.platform == "win32":
    print("SALTATO: lo scambio di versione dell'app per Mac si prova su un Mac o su Linux")
    sys.exit(0)

os.environ["OMISSIS_TEST"] = "1"
TEMP = Path(tempfile.mkdtemp(prefix="omissis_macapp_")).resolve()
os.environ["OMISSIS_DATA"] = str(TEMP / "data")

import macapp    # noqa: E402
import sistema   # noqa: E402

FOLDER = TEMP / "data" / "updates"
MAC = sistema.MAC
outcomes = []
# l'app finta non porta le librerie di Omissis: al suo Python si chiede solo di partire e di dire la versione
macapp.PREFLIGHT = "import sys; sys.path.insert(0, sys.argv[1]); import version; print(version.VERSION)"

PANEL = '''# pannello finto: dice di essere partito e resta acceso
import os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import version
if {broken!r}:
    sys.exit(3)
folder = Path(os.environ["OMISSIS_DATA"]) / "updates"
folder.mkdir(parents=True, exist_ok=True)
(folder / "started.txt").write_text(version.VERSION + "\\n" + " ".join(sys.argv[1:]) + "\\n", encoding="utf-8")
time.sleep(600)
'''
LAUNCHER = '''#!/bin/sh
HERE="$(cd "$(dirname "$0")/../Resources" && pwd)"
exec "$HERE/python/bin/python3" "$HERE/omissis/app/panel.py" "$@"
'''


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(("OK   " if ok else "NO   ") + name + (f"  ({note})" if note else ""), flush=True)


def make_app(where, version, broken=False, channel="github"):
    """Un'app finta con la forma di Omissis.app. Restituisce la cartella .app."""
    app = where / "Omissis.app"
    shutil.rmtree(app, ignore_errors=True)
    contents = app / "Contents"
    code = contents / "Resources" / "omissis" / "app"
    code.mkdir(parents=True)
    (contents / "MacOS").mkdir()
    (contents / "MacOS" / "Omissis").write_text(LAUNCHER, encoding="utf-8")
    (contents / "MacOS" / "Omissis").chmod(0o755)
    (contents / "Resources" / "python" / "bin").mkdir(parents=True)
    (contents / "Resources" / "python" / "bin" / "python3").symlink_to(sys.executable)
    (contents / "Resources" / "omissis" / "installed.json").write_text(json.dumps({"version": version, "channel": channel}), encoding="utf-8")
    (code / "version.py").write_text(f'VERSION = "{version}"\n', encoding="utf-8")
    (code / "panel.py").write_text(PANEL.format(broken=broken), encoding="utf-8")
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump({"CFBundleName": "Omissis", "CFBundleIdentifier": macapp.IDENT, "CFBundleExecutable": "Omissis", "CFBundlePackageType": "APPL",
                       "CFBundleShortVersionString": version, "CFBundleVersion": version, "LSUIElement": True}, f)
    return app


def package(version, **how):
    """Il pacchetto di una versione, come lo scarica il programma: .dmg sul Mac, archivio tar su Linux. (file, impronta)"""
    source = TEMP / "source" / version
    shutil.rmtree(source, ignore_errors=True)
    source.mkdir(parents=True)
    make_app(source, version, **how)
    if MAC:
        out = TEMP / f"Omissis-{version}.dmg"
        out.unlink(missing_ok=True)
        subprocess.run(["hdiutil", "create", "-volname", "Omissis", "-srcfolder", str(source), "-ov", "-format", "UDZO", str(out)], check=True, capture_output=True, timeout=300)
    else:
        out = TEMP / f"Omissis-{version}.tar.gz"
        with tarfile.open(out, "w:gz") as t:
            t.add(source / "Omissis.app", arcname="Omissis.app")
    return out, hashlib.sha256(out.read_bytes()).hexdigest()


def version_of(app):
    try:
        return json.loads((app / "Contents" / "Resources" / "omissis" / "installed.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return "?"


def running(app):
    """I processi partiti da dentro l'app."""
    out = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout
    return [int(line.split(None, 1)[0]) for line in out.splitlines() if f"{app}/Contents/" in line]


def stop(app):
    for pid in running(app):
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    time.sleep(0.5)


def swap_from_child(app, version, seconds):
    """Lo scambio va chiesto dal programma che sta per chiudersi: qui un processo a parte, che lo chiede ed esce."""
    code = ("import sys; from pathlib import Path; import macapp; "
            "macapp.swap(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), ['--no-browser'], seconds=int(sys.argv[4]))")
    subprocess.run([sys.executable, "-c", code, str(app), version, str(FOLDER), str(seconds)], check=True, cwd=Path(__file__).resolve().parent, timeout=60)


def wait_for(condition, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.3)
    return False


def started():
    try:
        return (FOLDER / "started.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def main():
    print(f"sistema: {sistema.NAME} · cartella di prova {TEMP}", flush=True)
    apps = TEMP / "Applications"
    apps.mkdir()
    app = make_app(apps, "1.0.0")
    try:
        # ---------------------------------------------------- scompattare e controllare
        good, mark_good = package("1.0.1")
        macapp.unpack(good, app, "1.0.1", mark_good)
        mark("il pacchetto viene scompattato accanto alla versione in uso, che resta com'era",
              macapp.prepared(app, "1.0.1", mark_good) and version_of(app) == "1.0.0" and (app / "Contents.new" / "MacOS" / "Omissis").exists())
        mark("una versione scompattata da un altro pacchetto non viene presa per buona", not macapp.prepared(app, "1.0.1", "0" * 64) and not macapp.prepared(app, "1.0.9", mark_good))

        def refused(file, version, mark_file):
            try:
                macapp.unpack(file, app, version, mark_file)
                return ""
            except macapp.Error as ex:
                return ex.code
        why = refused(good, "1.0.7", mark_good)
        mark("un pacchetto che dentro ha un'altra versione viene rifiutato, senza lasciare nulla", why == "package" and not (app / "Contents.new").exists(), why)
        other, mark_other = package("1.0.3", channel="store")
        why = refused(other, "1.0.3", mark_other)
        mark("un pacchetto di un altro canale viene rifiutato", why == "package" and not (app / "Contents.new").exists(), why)
        ruined = TEMP / ("rovinato.dmg" if MAC else "rovinato.tar.gz")
        whole = good.read_bytes()
        ruined.write_bytes(whole[:len(whole) // 2] + os.urandom(len(whole)))
        why = refused(ruined, "1.0.1", "0" * 64)
        mark("un pacchetto rovinato viene rifiutato", why == "package" and not (app / "Contents.new").exists() and version_of(app) == "1.0.0", why)
        try:
            macapp.swap(app, "1.0.1", FOLDER, ["--no-browser"])
            nothing = False
        except macapp.Error:
            nothing = True
        mark("senza una versione scompattata lo scambio non parte", nothing and version_of(app) == "1.0.0")

        # ---------------------------------------------------- lo scambio riuscito
        macapp.unpack(good, app, "1.0.1", mark_good)
        stray = subprocess.Popen([str(app / "Contents" / "Resources" / "python" / "bin" / "python3"), "-c", "import time; time.sleep(600)"])
        swap_from_child(app, "1.0.1", 40)
        done = wait_for(lambda: macapp.outcome(FOLDER) is not None, 70)
        mark("lo scambio avviene a programma chiuso e la versione nuova parte", done and macapp.outcome(FOLDER) == ("ok", "1.0.1") and version_of(app) == "1.0.1"
              and started()[:1] == ["1.0.1"], f"esito {macapp.outcome(FOLDER)} · installata {version_of(app)} · partita {started()[:1]}")
        mark("riparte con le stesse opzioni, senza aprire il browser", started()[1:2] == ["--no-browser"], str(started()[1:2]))
        mark("un processo rimasto acceso dentro l'app viene fermato prima dello scambio", stray.poll() is not None)
        mark("della versione di prima non resta nulla", not any((app / n).exists() for n in ("Contents.old", "Contents.new", "Contents.bad")))
        if stray.poll() is None:
            stray.kill()
        stop(app)

        # ---------------------------------------------------- la versione nuova non parte: torna quella di prima
        bad, mark_bad = package("1.0.2", broken=True)
        macapp.unpack(bad, app, "1.0.2", mark_bad)
        swap_from_child(app, "1.0.2", 8)
        done = wait_for(lambda: macapp.outcome(FOLDER) is not None, 60)
        back = wait_for(lambda: started()[:1] == ["1.0.1"], 30)
        mark("se la versione nuova non parte, torna quella di prima e viene riaperta", done and macapp.outcome(FOLDER) == ("rolled_back", "1.0.2")
              and version_of(app) == "1.0.1" and back, f"esito {macapp.outcome(FOLDER)} · installata {version_of(app)} · partita {started()[:1]}")
        mark("della versione che non e' partita non resta nulla", not any((app / n).exists() for n in ("Contents.old", "Contents.new", "Contents.bad")))
        stop(app)
    finally:
        stop(app)
        for f in sorted(FOLDER.glob("*.log")) if FOLDER.exists() else []:
            print(f"--- {f.name}\n{f.read_text(encoding='utf-8', errors='replace')[-800:]}")
        shutil.rmtree(TEMP, ignore_errors=True)
    print(f"\n{sum(outcomes)}/{len(outcomes)} controlli superati")
    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
