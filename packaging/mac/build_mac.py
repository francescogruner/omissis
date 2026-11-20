# -*- coding: utf-8 -*-
"""Costruisce Omissis per Mac: Omissis.app dentro un file .dmg. Va lanciato su un Mac (o sul Mac di GitHub Actions),
dalla radice del repository.

  python3 packaging/mac/build_mac.py --version 0.1.5 [--arch arm64|x86_64] [--smoke-test]

Come su Windows, il programma non viene «congelato»: l'app porta con se' un Python completo (python-build-standalone,
la distribuzione usata anche da uv), le librerie di requirements-mac.txt e il codice di app/ e model/. Il file
Contents/MacOS/Omissis e' un piccolo lanciatore che avvia panel.py con quel Python. I pesi del modello non ci sono:
il programma li scarica al primo avvio, come su Windows.

L'app non e' firmata ne' notarizzata (serve l'Apple Developer Program): al primo avvio macOS la ferma, e la si apre da
Impostazioni di Sistema > Privacy e sicurezza > «Apri comunque».

Lo stesso .dmg serve anche agli aggiornamenti automatici: le copie installate lo scaricano e ne prendono l'app
(app/macapp.py). Perche' lo accettino va pubblicato insieme al suo foglio firmato, update-mac-<processore>.json: lo
scrive chi pubblica, sul suo computer, dove sta la chiave delle firme.

--smoke-test avvia l'app costruita in modalita' di prova (senza icona e senza browser) e controlla che il pannello
risponda. Con --platform si puo' provare la costruzione anche su Linux (senza .dmg ne' Info.plist).
"""
import argparse
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OUT = REPO / "dist"
PYTHON_SERIES = "3.12"
STANDALONE = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
# il programma ha bisogno di queste cartelle e di questi file del modello (non degli script di addestramento)
MODEL_FILES = ["inference.py", "known.py", "rules.py"]   # gli stessi dell'installer per Windows
SKIP_APP = re.compile(r"^(e2e_.*\.py|mock_service\.py|build_extension\.py|check_languages\.py|check_radar\.py|requirements.*\.txt)$")


def run(cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def triple(arch, plat):
    if plat == "mac":
        return f"{'aarch64' if arch == 'arm64' else 'x86_64'}-apple-darwin"
    return f"{'aarch64' if arch == 'arm64' else 'x86_64'}-unknown-linux-gnu"


def download_python(target, arch, plat):
    """Scarica e scompatta l'ultima python-build-standalone della serie 3.12 per questa macchina."""
    req = urllib.request.Request(STANDALONE, headers={"Accept": "application/vnd.github+json", "User-Agent": "omissis-build"})
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    release = json.loads(urllib.request.urlopen(req, timeout=60).read())
    rx = re.compile(rf"^cpython-{re.escape(PYTHON_SERIES)}\.\d+\+\d+-{re.escape(triple(arch, plat))}-install_only_stripped\.tar\.gz$")
    asset = next((a for a in release["assets"] if rx.match(a["name"])), None)
    if asset is None:
        sys.exit(f"nessun Python {PYTHON_SERIES} per {triple(arch, plat)} nella versione {release.get('tag_name')}")
    archive = OUT / asset["name"]
    if not archive.exists():
        print("scarico", asset["name"], flush=True)
        urllib.request.urlretrieve(asset["browser_download_url"], archive)
    with tarfile.open(archive) as t:
        t.extractall(target.parent, filter="data")   # dentro c'e' una cartella «python»
    if target.name != "python":
        (target.parent / "python").rename(target)
    return target / "bin" / "python3"


def copy_code(dest):
    """app/ (senza le prove) e la parte del modello che serve al programma, piu' installed.json."""
    shutil.copytree(REPO / "app", dest / "app", ignore=lambda folder, names: [n for n in names if SKIP_APP.match(n)
                                                                         or n in ("__pycache__", "data", ".venv", "screenshots")])
    (dest / "model").mkdir(parents=True)
    for f in MODEL_FILES:
        if (REPO / "model" / f).exists():
            shutil.copy2(REPO / "model" / f, dest / "model" / f)
    shutil.copytree(REPO / "model" / "lists", dest / "model" / "lists")


def icon(resources):
    """Omissis.icns dalla PNG da 1024 pixel, con gli strumenti del Mac (sips e iconutil)."""
    src, iconset = HERE / "icon.png", OUT / "Omissis.iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            run(["sips", "-z", size * scale, size * scale, src, "--out", iconset / name], stdout=subprocess.DEVNULL)
    run(["iconutil", "-c", "icns", iconset, "-o", resources / "Omissis.icns"])


LAUNCHER = """#!/bin/sh
# Avvia Omissis con il Python che sta dentro l'app. Gli argomenti passano a panel.py.
HERE="$(cd "$(dirname "$0")/../Resources" && pwd)"
export PYTHONNOUSERSITE=1
exec "$HERE/python/bin/python3" "$HERE/omissis/app/panel.py" "$@"
"""


def build(version, arch, plat):
    app = OUT / "Omissis.app"
    shutil.rmtree(app, ignore_errors=True)
    contents = app / "Contents"
    resources = contents / "Resources"
    (contents / "MacOS").mkdir(parents=True)
    resources.mkdir(parents=True)
    python = download_python(resources / "python", arch, plat)
    run([python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--no-compile", "--only-binary=:all:",
         "-r", HERE / "requirements-mac.txt"])
    copy_code(resources / "omissis")
    # come l'installer per Windows: il programma dice la versione con cui e' stato costruito (la leggono il pannello e
    # il controllo degli aggiornamenti)
    stated = resources / "omissis" / "app" / "version.py"
    text, found = re.subn(r'VERSION = "[^"]*"', f'VERSION = "{version}"', stated.read_text(encoding="utf-8"))
    if found != 1:
        sys.exit("app/version.py: non trovo la riga della versione")
    stated.write_text(text, encoding="utf-8")
    (resources / "omissis" / "installed.json").write_text(json.dumps({"version": version, "channel": "github"}), encoding="utf-8")
    launcher = contents / "MacOS" / "Omissis"
    launcher.write_text(LAUNCHER, encoding="utf-8")
    launcher.chmod(0o755)
    if plat == "mac":
        icon(resources)
        with open(contents / "Info.plist", "wb") as f:
            plistlib.dump({"CFBundleName": "Omissis", "CFBundleDisplayName": "Omissis", "CFBundleIdentifier": "eu.omissis.app",
                           "CFBundleExecutable": "Omissis", "CFBundlePackageType": "APPL", "CFBundleIconFile": "Omissis.icns",
                           "CFBundleShortVersionString": version, "CFBundleVersion": version,
                           "LSMinimumSystemVersion": "12.0", "LSUIElement": True,   # vive nella barra dei menu, non nel Dock
                           "NSHumanReadableCopyright": "Apache License 2.0"}, f)
    return app, python


def dmg(app, version, arch):
    folder = OUT / "dmg"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir()
    shutil.copytree(app, folder / "Omissis.app", symlinks=True)
    (folder / "Applications").symlink_to("/Applications")
    out = OUT / f"Omissis-{version}-mac-{arch}.dmg"
    out.unlink(missing_ok=True)
    run(["hdiutil", "create", "-volname", "Omissis", "-srcfolder", folder, "-ov", "-format", "UDZO", out])
    return out


def smoke_test(app):
    """Avvia l'app costruita come una copia di prova e controlla che il pannello risponda."""
    data = OUT / "smoke-data"
    shutil.rmtree(data, ignore_errors=True)
    env = {**os.environ, "OMISSIS_PORT": "8795", "OMISSIS_TEST": "1", "OMISSIS_DATA": str(data), "OMISSIS_LISTS": str(data / "lists")}
    p = subprocess.Popen([app / "Contents" / "MacOS" / "Omissis", "--test", "--no-tray", "--no-browser", "--no-start"], env=env)
    try:
        for _ in range(60):
            try:
                page = urllib.request.urlopen("http://127.0.0.1:8796/", timeout=2).read().decode("utf-8")
                if "Omissis" in page:
                    print("prova: il pannello risponde")
                    return True
            except OSError:
                pass
            time.sleep(1)
        print("prova: il pannello NON risponde")
        return False
    finally:
        p.terminate()
        p.wait(timeout=20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--arch", default="arm64" if platform.machine() in ("arm64", "aarch64") else "x86_64", choices=["arm64", "x86_64"])
    ap.add_argument("--platform", default="mac" if sys.platform == "darwin" else "linux", choices=["mac", "linux"])
    ap.add_argument("--smoke-test", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"\d{1,4}(\.\d{1,4}){1,3}", a.version):
        sys.exit("versione non valida: solo numeri separati da punti (per esempio 0.1.5)")
    OUT.mkdir(exist_ok=True)
    app, _ = build(a.version, a.arch, a.platform)
    print("costruita", app)
    if a.platform == "mac":
        print("immagine", dmg(app, a.version, a.arch))
    if a.smoke_test and not smoke_test(app):
        sys.exit(1)


if __name__ == "__main__":
    main()
