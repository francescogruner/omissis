# -*- coding: utf-8 -*-
"""Scrive i file dell'estensione che dipendono dal catalogo dei servizi: manifest.json (su quali
siti gira), defaults.js (le politiche di partenza, usate finche' l'estensione non e' collegata
al programma), build.json (l'impronta dei file) e le icone.   Va rilanciato quando cambia catalog.py
e ogni volta che si tocca un file dell'estensione: e' dall'impronta che una copia gia' caricata in
un browser si accorge che sul disco i file sono cambiati, e si ricarica da sola.

  .venv\\Scripts\\python.exe build_extension.py [--test | --check]

--test aggiunge http://localhost (il servizio finto) ai siti su cui l'estensione gira.
--check non scrive nulla: esce con 1 se build.json non corrisponde ai file (va rilanciato senza opzioni).
"""
import hashlib
import json
import sys
from pathlib import Path

import catalog

HERE = Path(__file__).resolve().parent
EST = HERE / "extension"
VERSION = "0.1.0"


def models(services):
    out = []
    for s in services:
        for d in s["domains"]:
            out += [f"*://{d}/*", f"*://*.{d}/*"]
    return out


def manifest(test):
    # i servizi del radar restano fuori: l'estensione non chiede l'accesso ai loro siti, li puo' solo bloccare
    readable = models(s for s in catalog.SERVICES if s["adapter"])
    others = models(s for s in catalog.SERVICES if not s["adapter"] and not s["radar"])
    if test:
        readable.append("http://localhost/*")
    common = {"run_at": "document_start", "all_frames": True, "match_origin_as_fallback": True}
    return {
        "manifest_version": 3,
        # nome e descrizione stanno in _locales/<lingua>/messages.json, come tutte le frasi dell'estensione
        "name": "Omissis (prova)" if test else "__MSG_est_name__",
        "version": VERSION,
        "description": "__MSG_est_description__",
        "default_locale": "en",
        "minimum_chrome_version": "111",
        # declarativeNetRequest (e non ...WithHostAccess): serve a bloccare anche i servizi del radar, sui cui siti non si chiede l'accesso
        "permissions": ["storage", "alarms", "declarativeNetRequest"],
        "host_permissions": ["http://127.0.0.1/*"] + readable + others,
        "background": {"service_worker": "background.js"},
        "action": {"default_popup": "popup.html", "default_title": "Omissis",
                   "default_icon": {str(n): f"icons/{n}.png" for n in (16, 32, 48)}},
        "icons": {str(n): f"icons/{n}.png" for n in (16, 48, 128)},
        "content_scripts": [
            {"matches": readable, "js": ["page.js"], "world": "MAIN", **common},
            {"matches": readable, "js": ["defaults.js", "channel.js", "content.js"], **common},
            {"matches": others, "js": ["defaults.js", "content.js"], "run_at": "document_start"},
            {"matches": ["http://127.0.0.1/*", "http://localhost/*"] if not test else ["http://127.0.0.1/*"],
             "js": ["pair.js"], "run_at": "document_start"},
        ],
        "web_accessible_resources": [{"resources": ["blocked.html"], "matches": ["<all_urls>"]}],
    }


def stamp(folder=None):
    """L'impronta dell'estensione cosi' come la riceve chi la installa. Quella di prova ha la stessa impronta: cambia
    solo l'elenco dei siti, e un browser che ha gia' caricato l'estensione vera non deve passare a quella di prova."""
    folder = Path(folder) if folder else EST
    h = hashlib.sha256()
    h.update(json.dumps(manifest(False), sort_keys=True).encode("utf-8"))
    h.update(defaults(False, "").encode("utf-8"))
    generated = {"manifest.json", "defaults.js", "build.json"}
    for f in sorted(folder.rglob("*"), key=lambda f: f.relative_to(folder).as_posix()):
        rel = f.relative_to(folder)
        if f.is_file() and rel.as_posix() not in generated and rel.parts[0] != "icons" and not rel.name.startswith("."):
            h.update(rel.as_posix().encode("utf-8") + b"\0" + f.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()[:16]


def defaults(test, build=None):
    services = [{"id": s["id"], "name": s["name"], "domains": s["domains"], "policy": catalog.default_policy(s),
                "readable": bool(s["adapter"])} for s in catalog.SERVICES if not s["radar"]]
    if test:
        services.append({"id": "test", "name": "Servizio finto", "domains": ["localhost"], "policy": "protect", "readable": True})
    return ("// generato da build_extension.py: politiche di partenza, finche' il programma non manda le sue\n"
            "globalThis.MSP_DEFAULTS = " + json.dumps({"services": services, "restore": True, "block_files": False},
                                                         ensure_ascii=False, separators=(",", ":")) + ";\n"
            # l'impronta dei file con cui questa copia e' stata scritta: il browser la tiene in memoria insieme al codice
            + "globalThis.MSP_BUILD = " + json.dumps(stamp() if build is None else build) + ";\n")


def icons():
    from PIL import Image, ImageDraw
    (EST / "icons").mkdir(exist_ok=True)
    large = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(large)
    d.polygon([(256, 32), (464, 112), (464, 272), (256, 480), (48, 272), (48, 112)], fill=(16, 122, 107, 255))
    d.line([(160, 256), (232, 328), (360, 184)], fill=(255, 255, 255, 255), width=48, joint="curve")
    for n in (16, 32, 48, 128):
        large.resize((n, n), Image.LANCZOS).save(EST / "icons" / f"{n}.png")


if __name__ == "__main__":
    test = "--test" in sys.argv
    if "--check" in sys.argv:
        try:
            written = json.loads((EST / "build.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            written = {}
        if written.get("build") != stamp() or f'"{stamp()}"' not in (EST / "defaults.js").read_text(encoding="utf-8"):
            sys.exit("build.json non corrisponde ai file dell'estensione: rilanciare build_extension.py")
        print(f"impronta dell'estensione: {stamp()}" + (" (estensione di prova)" if written.get("test") else ""))
        sys.exit(0)
    EST.mkdir(exist_ok=True)
    (EST / "manifest.json").write_text(json.dumps(manifest(test), ensure_ascii=False, indent=1), encoding="utf-8")
    (EST / "defaults.js").write_text(defaults(test), encoding="utf-8")
    (EST / "build.json").write_text(json.dumps({"build": stamp(), "test": test}) + "\n", encoding="utf-8")
    icons()
    print(f"estensione scritta in {EST}" + (" (con il servizio finto)" if test else ""))
