# -*- coding: utf-8 -*-
"""Costruisce Omissis per Linux: l'archivio Omissis-<versione>-linux-<processore>.tar.gz. Va lanciato su Linux (o
sull'Ubuntu di GitHub Actions), dalla radice del repository.

  python3 packaging/linux/build_linux.py --version 0.1.7 [--arch x86_64|arm64] [--smoke-test]

Dentro l'archivio c'e' una cartella sola, Omissis.app, fatta come l'app del Mac (la costruisce lo stesso codice,
packaging/mac/build_mac.py): un Python completo (python-build-standalone), le librerie di requirements-mac.txt (quelle
solo del Mac non vengono scaricate) e il codice di app/ e model/. Il nome della cartella resta quello del Mac di
proposito: cosi' installazione, avvio all'accesso e aggiornamenti usano su Linux lo stesso codice gia' provato sul Mac
(app/macapp.py). Chi usa Linux non la vede: l'installatore (install.sh) la mette in ~/.local/lib/omissis.

Lo stesso archivio serve anche agli aggiornamenti automatici: le copie installate lo scaricano, lo scompattano accanto
alla versione in uso e, se la nuova non parte, tornano a quella di prima. Perche' lo accettino va pubblicato insieme al
suo foglio firmato, update-linux-<processore>.json: lo scrive chi pubblica, sul suo computer, dove sta la chiave delle
firme.

I pesi del modello non ci sono: il programma li scarica al primo avvio, come su Windows e sul Mac.
--smoke-test avvia il programma costruito in modalita' di prova e controlla che il pannello risponda.
"""
import argparse
import hashlib
import platform
import re
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mac"))
import build_mac   # noqa: E402

ICON_SIDE = 256   # la misura che i desktop usano nel menu delle applicazioni


def icon(app, python):
    """L'icona per il menu delle applicazioni: la stessa del Mac, rimpicciolita con il Pillow che viaggia nel programma."""
    target = app / "Contents" / "Resources" / "omissis.png"
    code = ("import sys; from PIL import Image; "
            f"Image.open(sys.argv[1]).convert('RGBA').resize(({ICON_SIDE}, {ICON_SIDE}), Image.LANCZOS).save(sys.argv[2])")
    subprocess.run([str(python), "-I", "-c", code, str(HERE.parent / "mac" / "icon.png"), str(target)], check=True)
    return target


def archive(app, version, arch):
    out = build_mac.OUT / f"Omissis-{version}-linux-{arch}.tar.gz"
    out.unlink(missing_ok=True)
    with tarfile.open(out, "w:gz", compresslevel=6) as t:
        t.add(app, arcname="Omissis.app")
    return out


def fingerprint(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for piece in iter(lambda: f.read(1 << 20), b""):
            h.update(piece)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--arch", default="arm64" if platform.machine() in ("arm64", "aarch64") else "x86_64", choices=["arm64", "x86_64"])
    ap.add_argument("--smoke-test", action="store_true")
    ap.add_argument("--no-archive", action="store_true", help="solo la cartella dist/Omissis.app, senza l'archivio (per le prove)")
    a = ap.parse_args()
    if not sys.platform.startswith("linux"):
        sys.exit("questo si lancia su Linux: per il Mac c'e' packaging/mac/build_mac.py")
    if not re.fullmatch(r"\d{1,4}(\.\d{1,4}){1,3}", a.version):
        sys.exit("versione non valida: solo numeri separati da punti (per esempio 0.1.7)")
    build_mac.OUT.mkdir(exist_ok=True)
    app, python = build_mac.build(a.version, a.arch, "linux")
    icon(app, python)
    print("costruita", app)
    if a.smoke_test and not build_mac.smoke_test(app):
        sys.exit(1)
    if not a.no_archive:
        out = archive(app, a.version, a.arch)
        print(f"archivio {out} · {out.stat().st_size / 1e6:.0f} MB · sha256 {fingerprint(out)}")


if __name__ == "__main__":
    main()
