# -*- coding: utf-8 -*-
"""Costruisce l'installer di Omissis per Windows: Omissis-<versione>-setup.exe. Va lanciato su Windows (o sul Windows
di GitHub Actions), dalla radice del repository, con Python 3.12 e Pillow.

  python packaging\\windows\\build_windows.py --version 0.1.10 [--out dist] [--reuse-python] [--smoke-test]

Cosa fa, in ordine:
  1. prepara in build\\windows\\Omissis il programma completo: il Python ufficiale in versione "embeddable" (scaricato
     da python.org, stessa versione di quello che lancia questo script), le librerie di requirements-windows.txt, il
     codice di app\\ e la parte di model\\ che serve a riconoscere i dati. I pesi del modello NON ci sono: il
     programma li scarica al primo avvio;
  2. compila omissis.iss con Inno Setup 6 -> <out>\\Omissis-<versione>-setup.exe;
  3. stampa dimensione e impronta SHA-256 dell'installer.

Il foglio degli aggiornamenti (update.json) e la sua firma non li scrive questo script: li scrive chi pubblica, sul suo
computer, dove sta la chiave delle firme. Nemmeno la firma del codice si fa qui: se c'e', la mette il servizio di
firma sul file uscito da questa costruzione (vedi README.md in questa cartella).

--smoke-test fa partire il Python del pacchetto e controlla che librerie e codice si carichino.
Serve Inno Setup 6: winget install JRSoftware.InnoSetup (sui Windows di GitHub: choco install innosetup).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
BUILD = ROOT / "build" / "windows"
PACKAGE = BUILD / "Omissis"
# cio' che serve solo a chi sviluppa (prove, servizio finto, costruzione dell'estensione, controlli): non va a chi installa
NOT_SHIPPED = re.compile(r"^(e2e_.*\.py|mock_service\.py|build_extension\.py|check_languages\.py|check_radar\.py|requirements.*\.txt)$")
MODEL = ["inference.py", "known.py", "rules.py", "lists/never.txt", "lists/always.txt"]
ISCC = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe"]


def run(command, **k):
    r = subprocess.run([str(c) for c in command], capture_output=True, text=True, encoding="utf-8", errors="replace", **k)
    if r.returncode:
        sys.exit(f"comando fallito: {Path(str(command[0])).name}\n{(r.stdout + r.stderr)[-3000:]}")
    return r.stdout


def embedded_python(reuse):
    """Il Python ufficiale "embeddable" con le librerie del pacchetto, in PACKAGE\\python."""
    where = PACKAGE / "python"
    if reuse and (where / "Omissis.exe").exists():
        return
    version = ".".join(str(x) for x in sys.version_info[:3])
    archive = BUILD / "cache" / f"python-{version}-embed-amd64.zip"
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        address = f"https://www.python.org/ftp/python/{version}/{archive.name}"
        print("scarico", address, flush=True)
        with urllib.request.urlopen(address, timeout=120) as r:
            archive.write_bytes(r.read())
    shutil.rmtree(where, ignore_errors=True)
    where.mkdir(parents=True)
    with zipfile.ZipFile(archive) as z:
        z.extractall(where)
    tag = f"python{sys.version_info[0]}{sys.version_info[1]}"
    # i percorsi di ricerca: solo roba del pacchetto (niente variabili d'ambiente ne' cartelle dell'utente)
    (where / f"{tag}._pth").write_text(f"{tag}.zip\n.\nLib\\site-packages\n..\\app\nimport site\n", encoding="ascii")
    shutil.copyfile(where / "pythonw.exe", where / "Omissis.exe")   # cosi' nell'elenco dei processi compare col suo nome
    libraries = where / "Lib" / "site-packages"
    print("installo le librerie del pacchetto", flush=True)
    run([sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "--no-compile", "--only-binary=:all:",
         "--target", libraries, "-r", HERE / "requirements-windows.txt"])
    shutil.rmtree(libraries / "bin", ignore_errors=True)   # lanciatori con il percorso di chi costruisce dentro: non servono
    listing = run([sys.executable, "-m", "pip", "list", "--path", libraries, "--format=freeze", "--disable-pip-version-check"])
    (PACKAGE / "libraries.txt").write_text(listing, encoding="utf-8")
    cpp_runtime(where)


def cpp_runtime(where):
    """Le librerie di Visual C++ che i componenti chiedono al sistema (il motore ONNX vuole msvcp140*.dll): su un PC
    appena installato possono mancare, quindi viaggiano accanto all'eseguibile, prese dal computer che costruisce. Se
    una libreria richiesta non si trova, niente installer: su un PC pulito il motore non partirebbe."""
    rx = re.compile(rb"(?i)\b(msvcp140[\w]*\.dll|vcruntime140[\w]*\.dll|vcomp140\.dll|concrt140\.dll)")
    wanted = set()
    for f in [*where.rglob("*.pyd"), *where.rglob("*.dll")]:
        wanted |= {m.decode().lower() for m in rx.findall(f.read_bytes())}
    system = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    for name in sorted(wanted - {f.name.lower() for f in where.glob("*.dll")}):
        if not (system / name).exists():
            sys.exit(f"manca {name} su questo computer: installare il runtime di Visual C++ (vc_redist.x64) e riprovare")
        shutil.copyfile(system / name, where / name)
        print("aggiunta al pacchetto la libreria di sistema", name, flush=True)


def program(version, channel):
    for name in ("app", "model"):
        shutil.rmtree(PACKAGE / name, ignore_errors=True)
    for f in sorted((ROOT / "app").rglob("*")):
        rel = f.relative_to(ROOT / "app")
        # da una cartella di lavoro usata per sviluppare non devono entrare i dati di chi sviluppa, ne' ambienti e browser di prova
        if rel.parts[0] in ("data", "models", ".venv", ".playwright") or "__pycache__" in rel.parts:
            continue
        if f.is_file() and not NOT_SHIPPED.match(rel.parts[0]):
            (PACKAGE / "app" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, PACKAGE / "app" / rel)
    for f in MODEL:
        (PACKAGE / "model" / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "model" / f, PACKAGE / "model" / f)
    for f in ("LICENSE", "NOTICE", "THIRD_PARTY.md"):
        shutil.copyfile(ROOT / f, PACKAGE / f)
    f = PACKAGE / "app" / "version.py"
    t = f.read_text(encoding="utf-8")
    assert t.count('VERSION = "') == 1
    f.write_text(re.sub(r'VERSION = "[^"]*"', f'VERSION = "{version}"', t), encoding="utf-8")
    (PACKAGE / "installed.json").write_text(json.dumps({"version": version, "channel": channel}), encoding="utf-8")


def icon():
    from PIL import Image
    Image.open(ROOT / "app" / "extension" / "icons" / "128.png").convert("RGBA").save(
        PACKAGE / "omissis.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128)])


def fingerprint(f):
    h = hashlib.sha256()
    with f.open("rb") as s:
        for piece in iter(lambda: s.read(1 << 20), b""):
            h.update(piece)
    return h.hexdigest()


def smoke_test():
    """Il Python del pacchetto carica le librerie e il codice che servono al primo avvio."""
    code = ("import ssl, sqlite3, onnxruntime, tokenizers, mitmproxy.version, docx, openpyxl, pptx, pypdf, PIL; "
            "import version, paths, settings, weights, updates; print('pacchetto in ordine, versione', version.VERSION)")
    print(run([PACKAGE / "python" / "python.exe", "-I", "-B", "-c", code], cwd=PACKAGE / "app").strip(), flush=True)


def build(version, out, channel="github", reuse=False, smoke=False):
    """Costruisce l'installer e ne restituisce il percorso."""
    if not re.fullmatch(r"\d{1,4}(\.\d{1,4}){1,3}", version):
        sys.exit("versione non valida")
    iscc = next((p for p in ISCC if p.exists()), None)
    if iscc is None:
        sys.exit("manca Inno Setup 6: winget install JRSoftware.InnoSetup")
    PACKAGE.mkdir(parents=True, exist_ok=True)
    embedded_python(reuse)
    program(version, channel)
    icon()
    # Se il pacchetto e' stato fatto girare per provarlo, Python ha lasciato accanto ai sorgenti i file compilati, che
    # portano dentro i percorsi di chi costruisce e pesano: nell'installer non devono entrare.
    for folder in [c for c in PACKAGE.rglob("__pycache__") if c.is_dir()]:
        shutil.rmtree(folder, ignore_errors=True)
    if smoke:
        smoke_test()
        for folder in [c for c in PACKAGE.rglob("__pycache__") if c.is_dir()]:
            shutil.rmtree(folder, ignore_errors=True)
    files = [f for f in PACKAGE.rglob("*") if f.is_file()]
    print(f"pacchetto pronto: {len(files)} file, {sum(f.stat().st_size for f in files) / 1e6:.0f} MB", flush=True)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    run([iscc, "/Qp", f"/DVersione={version}", f"/DSorgente={PACKAGE}", f"/DUscita={out}", f"/DIcona={PACKAGE / 'omissis.ico'}", HERE / "omissis.iss"])
    return out / f"Omissis-{version}-setup.exe"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--channel", default="github", choices=["github", "store"])
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--reuse-python", action="store_true", help="non riscarica e non reinstalla Python e librerie")
    ap.add_argument("--smoke-test", action="store_true")
    a = ap.parse_args()
    installer = build(a.version, a.out, a.channel, a.reuse_python, a.smoke_test)
    print(f"installer: {installer.name}  {installer.stat().st_size} byte  sha256 {fingerprint(installer)}")
