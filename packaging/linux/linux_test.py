# -*- coding: utf-8 -*-
"""Prova di Omissis su Linux, con il programma costruito (dist/Omissis.app): installazione con install.sh, primo avvio,
voce nel menu delle applicazioni, comando «omissis», avvio all'accesso, chiusura, aggiornamento sopra una copia accesa,
disinstallazione con il cestino. In piu', pezzo per pezzo: ricerca dei programmi AI, comando omissis-hook nel PATH,
portachiavi che non c'e', archivio cifrato che non si apre senza la sua chiave, lettura delle scansioni.

  python3 packaging/linux/linux_test.py [--model <cartella dei pesi>]

Tutto avviene in una cartella utente finta (HOME temporanea): quella vera non viene toccata. Va lanciata da un utente
normale, non da root (l'installatore lo rifiuta, ed e' una delle cose provate). Con --model la prova accende anche la
protezione e controlla che alla chiusura si fermino motore, proxy e collegamento.
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
APP = ROOT / "dist" / "Omissis.app"
PORT = 8785   # motore; il pannello e' sulla porta dopo
outcomes = []


def mark(name, ok, note=""):
    outcomes.append(bool(ok))
    print(("OK   " if ok else "NO   ") + name + (f"  ({note})" if note and not ok else ""), flush=True)


def skipped(name, why):
    print(f"SALTATO {name}: {why}", flush=True)


def opened(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait(condition, seconds=40):
    end = time.time() + seconds
    while time.time() < end:
        if condition():
            return True
        time.sleep(0.3)
    return False


class Copy:
    """Una copia installata nella cartella utente finta."""

    def __init__(self, home):
        self.home = home
        self.dest = home / ".local" / "lib" / "omissis"
        self.bin = self.dest / "Omissis.app" / "Contents" / "MacOS" / "Omissis"
        self.python = self.dest / "Omissis.app" / "Contents" / "Resources" / "python" / "bin" / "python3"
        self.code_folder = self.dest / "Omissis.app" / "Contents" / "Resources" / "omissis" / "app"
        self.data = home / ".local" / "share" / "omissis"
        keep = {k: v for k, v in os.environ.items() if k in ("PATH", "LANG", "TERM", "TMPDIR")}
        # niente desktop e niente portachiavi veri: senza DISPLAY non c'e' icona, senza D-Bus non c'e' Secret Service
        self.env = {**keep, "HOME": str(home), "LANG": "it_IT.UTF-8", "OMISSIS_PORT": str(PORT), "OMISSIS_UPDATES_URL": "http://127.0.0.1:9/nessuno",
                    "PATH": f"{home / '.local' / 'bin'}:{keep.get('PATH', '/usr/bin:/bin')}"}
        self.process = None

    def install(self, package, **more):
        return subprocess.run(["sh", str(HERE / "install.sh"), str(package)], env={**self.env, "OMISSIS_NO_START": "1", **more},
                              capture_output=True, text=True, timeout=900)

    def start(self, *arguments):
        self.process = subprocess.Popen([str(self.bin), "--no-browser", *arguments], env=self.env, stdout=open(self.home / "panel.log", "ab"),
                                        stderr=subprocess.STDOUT, start_new_session=True)
        return wait(lambda: opened(PORT + 1), 60)

    def code(self):
        page = urllib.request.urlopen(f"http://127.0.0.1:{PORT + 1}/", timeout=10).read().decode("utf-8")
        return re.search(r'name="omissis-code" content="([^"]+)"', page).group(1)

    def api(self, path, data=None):
        r = urllib.request.Request(f"http://127.0.0.1:{PORT + 1}{path}", headers={"X-Panel": self.code(), "Content-Type": "application/json"},
                                   data=json.dumps(data).encode("utf-8") if data is not None else None)
        with urllib.request.urlopen(r, timeout=60) as x:
            return json.loads(x.read().decode("utf-8"))

    def run(self, snippet, **more):
        """Un pezzo di Python con l'interprete e il codice del programma installato. -> (uscita, testo)"""
        r = subprocess.run([str(self.python), "-B", "-c", f"import sys; sys.path.insert(0, {str(self.code_folder)!r})\n{snippet}"],
                           env={**self.env, **more}, capture_output=True, text=True, timeout=300, cwd=str(self.home))
        return r.returncode, (r.stdout + r.stderr).strip()

    def alive(self):
        r = subprocess.run(["pgrep", "-f", str(self.dest / "Omissis.app")], capture_output=True, text=True)
        return [int(p) for p in r.stdout.split()]

    def stop(self):
        for pid in self.alive():
            try:
                os.kill(pid, 9)
            except OSError:
                pass


def places(home):
    return {"menu": home / ".local/share/applications/omissis.desktop", "icon": home / ".local/share/icons/hicolor/256x256/apps/omissis.png",
            "command": home / ".local/bin/omissis", "login": home / ".config/autostart/omissis.desktop"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="", help="cartella dei pesi di omissis-small: con questa si prova anche la protezione accesa")
    a = ap.parse_args()
    if not sys.platform.startswith("linux"):
        sys.exit("questa prova gira su Linux")
    if os.getuid() == 0:
        sys.exit("questa prova va lanciata da un utente normale: l'installatore rifiuta root")
    if not (APP / "Contents" / "MacOS" / "Omissis").exists():
        sys.exit("manca dist/Omissis.app: prima packaging/linux/build_linux.py")
    work = Path(tempfile.mkdtemp(prefix="omissis-linux-"))
    home = work / "home"
    home.mkdir()
    c = Copy(home)
    print(f"cartella di prova {work}", flush=True)
    try:
        # ------------------------------------------------------------ l'archivio e l'installatore
        package = next(iter(sorted((ROOT / "dist").glob("Omissis-*-linux-*.tar.gz"))), None)
        if package is None:   # costruito senza archivio: se ne fa uno al volo, compresso poco
            package = work / "Omissis-0.0.1-linux-x86_64.tar.gz"
            subprocess.run(["tar", "-I", "gzip -1", "-cf", str(package), "-C", str(APP.parent), "Omissis.app"], check=True)
        r = c.install(package)
        mark("install.sh mette il programma in ~/.local/lib/omissis", r.returncode == 0 and c.bin.exists() and not (c.dest / ".nuova").exists(), r.stdout + r.stderr)
        mark("l'installatore parla italiano a chi usa il sistema in italiano", "Omissis è installato" in r.stdout, r.stdout)
        r = subprocess.run(["sh", str(HERE / "install.sh"), str(package)], env={**c.env, "LANG": "en_US.UTF-8", "OMISSIS_NO_START": "1", "OMISSIS_HOME": str(work / "altrove")},
                           capture_output=True, text=True, timeout=900)
        mark("e inglese agli altri; OMISSIS_HOME sceglie un'altra cartella", r.returncode == 0 and "Omissis is installed" in r.stdout
             and (work / "altrove" / "Omissis.app").is_dir(), r.stdout + r.stderr)
        shutil.rmtree(work / "altrove", ignore_errors=True)
        bad = work / "rotto.tar.gz"
        bad.write_bytes(b"questo non e' un archivio")
        r = c.install(bad)
        mark("un archivio rovinato viene rifiutato e la copia installata resta", r.returncode != 0 and c.bin.exists() and not (c.dest / ".nuova").exists(), r.stdout + r.stderr)
        mark("prima dell'avvio non c'è nulla nel profilo: né voci di menu né dati", not any(p.exists() for p in places(home).values()) and not c.data.exists())

        # ------------------------------------------------------------ primo avvio
        if a.model:
            (c.data / "models").mkdir(parents=True)
            (c.data / "models" / "omissis-small").symlink_to(Path(a.model).resolve())
        mark("il programma installato parte e il pannello risponde", c.start(*([] if a.model else ["--no-start"])), (home / "panel.log").read_text(errors="replace")[-600:])
        p = places(home)
        card = c.api("/api/settings")["system"]
        mark("il pannello sa di essere su Linux, in un posto suo", card.get("name") == "linux" and card.get("location") == "ok" and card.get("uninstall") is True
             and card.get("quit") is True, json.dumps(card))
        menu = p["menu"].read_text(encoding="utf-8") if p["menu"].exists() else ""
        mark("al primo avvio compare la voce nel menu delle applicazioni, con la sua icona", f'Exec="{c.bin}"' in menu and p["icon"].exists() and f"Icon={p['icon']}" in menu, menu)
        if shutil.which("desktop-file-validate"):
            v = subprocess.run(["desktop-file-validate", str(p["menu"])], capture_output=True, text=True)
            mark("la voce di menu è scritta secondo le regole dei desktop Linux", v.returncode == 0, v.stdout + v.stderr)
        else:
            skipped("controllo della voce di menu", "manca desktop-file-validate")
        mark("c'è il comando «omissis» in ~/.local/bin", p["command"].exists() and os.access(p["command"], os.X_OK))
        login = p["login"].read_text(encoding="utf-8") if p["login"].exists() else ""
        mark("al primo avvio Omissis si mette tra i programmi che partono all'accesso, senza aprire il browser",
             f'Exec="{c.bin}" --no-browser' in login and card["login_item"] == {"supported": True, "on": True}, login + json.dumps(card))
        mark("la cartella dei dati la può leggere solo chi usa il computer", c.data.is_dir() and (c.data.stat().st_mode & 0o777) == 0o700, oct(c.data.stat().st_mode))
        now = c.api("/api/system", {"action": "login_off"})
        mark("l'avvio all'accesso si spegne dal pannello", now["login_item"] == {"supported": True, "on": False} and not p["login"].exists())
        now = c.api("/api/system", {"action": "login_on"})
        mark("e si riaccende", now["login_item"]["on"] is True and p["login"].exists())
        p["login"].write_text(login.replace("X-GNOME-Autostart-enabled=true", "X-GNOME-Autostart-enabled=false"), encoding="utf-8")
        mark("spento dalle impostazioni del desktop, per Omissis è spento", c.api("/api/settings")["system"]["login_item"]["on"] is False)
        c.api("/api/system", {"action": "login_on"})
        r = subprocess.run(["omissis", "--no-browser"], env=c.env, capture_output=True, text=True, timeout=60)
        mark("lanciato una seconda volta non parte un doppione: dice che è già acceso", r.returncode == 0 and "già acceso" in r.stdout and len(c.alive()) >= 1, r.stdout + r.stderr)

        # ------------------------------------------------------------ pezzo per pezzo, con il Python del programma
        apps = home / ".local/share/applications"
        (apps / "chatgpt.desktop").write_text("[Desktop Entry]\nType=Application\nName=ChatGPT\nExec=chatgpt\n", encoding="utf-8")
        (apps / "nascosta.desktop").write_text("[Desktop Entry]\nType=Application\nName=Cursor\nHidden=true\nExec=cursor\n", encoding="utf-8")
        ext = home / ".config/google-chrome/Default/Extensions/abcdefghijklmnopabcdefghijklmnop/1.0_0"
        ext.mkdir(parents=True)
        (ext / "manifest.json").write_text(json.dumps({"name": "ChatGPT Sidebar", "version": "1.0", "host_permissions": ["<all_urls>"]}), encoding="utf-8")
        code, out = c.run("import json, scan, sistema\nprint(json.dumps({'apps': sistema.linux_applications(), 'programs': scan.programs(), 'ext': scan.browser_extensions()}))")
        found = json.loads(out.splitlines()[-1]) if code == 0 else {}
        mark("la ricerca trova i programmi AI nel menu delle applicazioni (non quelli nascosti)",
             ["ChatGPT", ""] in found.get("apps", []) and ["Cursor", ""] not in found.get("apps", [])
             and any(x["name"] == "ChatGPT" and x["service"]["id"] == "chatgpt" for x in found.get("programs", [])), out[-600:])
        mark("e le estensioni AI dei browser", any(x["browser"] == "Chrome" and x["name"] == "ChatGPT Sidebar" and x["all_sites_access"] for x in found.get("ext", [])), out[-600:])
        code, out = c.run("import hook_command\nprint(hook_command.install()['on_path'])\nprint(open(hook_command._profiles()[0]).read())")
        profile = (home / ".profile").read_text(encoding="utf-8") if (home / ".profile").exists() else ""
        mark("il comando omissis-hook entra nel PATH di chi usa il computer (~/.profile)", code == 0 and out.splitlines()[0] == "True"
             and f'export PATH="{c.data / "bin"}:$PATH"' in profile and (c.data / "bin" / "omissis-hook").exists(), out)
        code, out = c.run("import hook_command\nprint(hook_command.remove()['on_path'])")
        mark("e ne esce quando lo si toglie", code == 0 and out.splitlines()[-1] == "False" and "omissis-hook" not in (home / ".profile").read_text(encoding="utf-8"), out)
        victim = home / "da buttare"
        victim.mkdir()
        (victim / "file.txt").write_text("x", encoding="utf-8")
        code, out = c.run(f"import macapp\nprint(macapp.trash({str(victim)!r}))")
        info = home / ".local/share/Trash/info/da buttare.trashinfo"
        mark("il cestino è quello dei desktop Linux: il file si può rimettere al suo posto", code == 0 and out.splitlines()[-1] == "True" and not victim.exists()
             and (home / ".local/share/Trash/files/da buttare/file.txt").exists() and info.exists() and "Path=" in info.read_text(encoding="utf-8"), out)
        begun = time.time()
        code, out = c.run("import sistema\nprint(sistema.keychain_secret('prova'))")
        mark("dove il portachiavi non c'è il programma lo dice subito, senza restare ad aspettare", code == 0 and out.splitlines()[-1] == "None" and time.time() - begun < 30, out[-300:])
        sealed = work / "sigillato"
        sealed.mkdir()
        (sealed / "vault_key.bin").write_bytes(os.urandom(60))
        code, out = c.run(f"import engine\ntry:\n    engine.Seal({str(sealed)!r})\n    print('aperto')\nexcept OSError as ex:\n    print('rifiutato:', ex)")
        mark("un archivio cifrato con il portachiavi non viene aperto senza la sua chiave", code == 0 and out.splitlines()[-1].startswith("rifiutato:") and "portachiavi" in out, out[-400:])
        picture = ("from PIL import Image, ImageDraw, ImageFont\nimport io, ocr\nim = Image.new('RGB', (1500, 300), 'white')\n"
                   "font = next((ImageFont.truetype(f, 64) for f in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/dejavu/DejaVuSans.ttf') if __import__('os').path.exists(f)), None)\n"
                   "ImageDraw.Draw(im).text((40, 100), 'Mario Rossi telefono 333 1234567', fill='black', font=font)\n"
                   "png, pdf = io.BytesIO(), io.BytesIO()\nim.save(png, 'PNG'); im.save(pdf, 'PDF')\n")
        if shutil.which("tesseract"):
            code, out = c.run(picture + "print(ocr.image(png.getvalue()))\nprint('---')\nprint(ocr.pdf(pdf.getvalue()))")
            mark("le scansioni si leggono con Tesseract: un'immagine e un PDF fatto di immagini", code == 0 and out.count("Mario Rossi") == 2 and "1234567" in out, out[-500:])
        else:
            code, out = c.run(picture + "try:\n    ocr.image(png.getvalue())\n    print('letta')\nexcept ocr.Unavailable as ex:\n    print('non disponibile:', ex)")
            mark("senza Tesseract la lettura delle scansioni dice che cosa installare", code == 0 and "non disponibile:" in out and "tesseract-ocr" in out, out[-400:])
            skipped("lettura vera delle scansioni", "Tesseract non è installato su questo computer")

        # ------------------------------------------------------------ chiusura
        if a.model:
            token = lambda: (c.data / "token.txt").read_text(encoding="utf-8").strip()   # noqa: E731

            def active():
                try:
                    r = urllib.request.Request(f"http://127.0.0.1:{PORT}/status", headers={"X-Token": token()})
                    return urllib.request.urlopen(r, timeout=3).status == 200
                except OSError:
                    return False
            mark("con il modello sul disco la protezione si accende", wait(active, 240), (home / "panel.log").read_text(errors="replace")[-600:])
            mark("pannello, motore e proxy sono processi del programma installato", wait(lambda: len(c.alive()) >= 3, 60), str(c.alive()))
        else:
            skipped("protezione accesa e chiusura di motore e proxy", "senza --model la prova non scarica il modello")
        r = subprocess.run(["omissis", "--quit"], env=c.env, capture_output=True, text=True, timeout=120)
        mark("«omissis --quit» chiude il programma e non lascia processi accesi", r.returncode == 0 and "chiuso" in r.stdout
             and wait(lambda: not opened(PORT + 1) and not c.alive(), 30), r.stdout + r.stderr + str(c.alive()))
        r = subprocess.run(["omissis", "--quit"], env=c.env, capture_output=True, text=True, timeout=60)
        mark("a programma spento lo dice e basta", r.returncode == 0 and "non è acceso" in r.stdout, r.stdout + r.stderr)

        # ------------------------------------------------------------ installare sopra una copia accesa, chiusura dal pannello
        c.start("--no-start")
        r = c.install(package)
        mark("installare di nuovo sopra una copia accesa la chiude e la sostituisce, senza resti",
             r.returncode == 0 and c.bin.exists() and not (c.dest / "Omissis.app.old").exists() and wait(lambda: not opened(PORT + 1), 30), r.stdout + r.stderr)
        mark("i dati e le voci di chi usa il computer restano", c.data.is_dir() and p["menu"].exists() and p["login"].exists())
        c.stop()
        c.start("--no-start")
        r = c.api("/api/system", {"action": "quit"})
        mark("il programma si chiude anche dal pannello", r == {"quit": True} and wait(lambda: not opened(PORT + 1) and not c.alive(), 30), json.dumps(r))

        # ------------------------------------------------------------ disinstallazione
        c.start("--no-start")
        r = c.api("/api/system", {"action": "uninstall", "data": False})
        gone = wait(lambda: not opened(PORT + 1) and not c.alive(), 40)
        binned = home / ".local/share/Trash/files/Omissis.app"
        mark("la disinstallazione toglie voce di menu, icona, comando e avvio all'accesso", r.get("trashed") is True and gone and not any(x.exists() for x in p.values()),
             json.dumps(r) + str([str(x) for x in p.values() if x.exists()]))
        mark("il programma va nel cestino, non viene cancellato", binned.is_dir() and not c.bin.exists())
        mark("i dati restano dove sono", c.data.is_dir() and any(c.data.iterdir()))
        shutil.rmtree(binned, ignore_errors=True)
        r = c.install(package)
        c.start("--no-start")
        p["command"].unlink()
        p["command"].write_text("#!/bin/sh\necho di un altro\n", encoding="utf-8")   # un comando «omissis» messo da qualcun altro
        r = c.api("/api/system", {"action": "uninstall", "data": True})
        gone = wait(lambda: not opened(PORT + 1) and not c.alive(), 40)
        mark("con «elimina anche i miei dati» sparisce anche la cartella dei dati", r.get("data") is True and gone and wait(lambda: not c.data.exists(), 30))
        mark("un comando «omissis» messo da qualcun altro non viene toccato", p["command"].exists() and "di un altro" in p["command"].read_text(encoding="utf-8"))
    finally:
        c.stop()
        shutil.rmtree(work, ignore_errors=True)
    print(f"\n{sum(outcomes)}/{len(outcomes)} controlli superati", flush=True)
    sys.exit(0 if all(outcomes) else 1)


if __name__ == "__main__":
    main()
