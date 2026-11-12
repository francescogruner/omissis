# -*- coding: utf-8 -*-
"""Scrive i file dell'estensione che dipendono dal catalogo dei servizi: manifest.json (su quali
siti gira), predefiniti.js (le politiche di partenza, usate finche' l'estensione non e' collegata
al programma) e le icone.   Va rilanciato quando cambia catalogo.py.

  .venv\\Scripts\\python.exe genera_estensione.py [--prova]

--prova aggiunge http://localhost (il servizio finto) ai siti su cui l'estensione gira.
"""
import json
import sys
from pathlib import Path

import catalogo

QUI = Path(__file__).resolve().parent
EST = QUI / "estensione"
VERSIONE = "0.1.0"


def modelli(servizi):
    out = []
    for s in servizi:
        for d in s["domini"]:
            out += [f"*://{d}/*", f"*://*.{d}/*"]
    return out


def manifesto(prova):
    leggibili = modelli(s for s in catalogo.SERVIZI if s["adattatore"])
    altri = modelli(s for s in catalogo.SERVIZI if not s["adattatore"])
    if prova:
        leggibili.append("http://localhost/*")
    comuni = {"run_at": "document_start", "all_frames": True, "match_origin_as_fallback": True}
    return {
        "manifest_version": 3,
        # nome e descrizione stanno in _locales/<lingua>/messages.json, come tutte le frasi dell'estensione
        "name": "Omissis (prova)" if prova else "__MSG_est_nome__",
        "version": VERSIONE,
        "description": "__MSG_est_descrizione__",
        "default_locale": "en",
        "minimum_chrome_version": "111",
        "permissions": ["storage", "alarms", "declarativeNetRequestWithHostAccess"],
        "host_permissions": ["http://127.0.0.1/*"] + leggibili + altri,
        "background": {"service_worker": "sfondo.js"},
        "action": {"default_popup": "finestra.html", "default_title": "Omissis",
                   "default_icon": {str(n): f"icone/{n}.png" for n in (16, 32, 48)}},
        "icons": {str(n): f"icone/{n}.png" for n in (16, 48, 128)},
        "content_scripts": [
            {"matches": leggibili, "js": ["pagina.js"], "world": "MAIN", **comuni},
            {"matches": leggibili, "js": ["predefiniti.js", "canale.js", "contenuto.js"], **comuni},
            {"matches": altri, "js": ["predefiniti.js", "contenuto.js"], "run_at": "document_start"},
            {"matches": ["http://127.0.0.1/*", "http://localhost/*"] if not prova else ["http://127.0.0.1/*"],
             "js": ["collega.js"], "run_at": "document_start"},
        ],
        "web_accessible_resources": [{"resources": ["bloccato.html"], "matches": ["<all_urls>"]}],
    }


def predefiniti(prova):
    servizi = [{"id": s["id"], "nome": s["nome"], "domini": s["domini"], "politica": catalogo.politica_predefinita(s),
                "leggibile": bool(s["adattatore"])} for s in catalogo.SERVIZI]
    if prova:
        servizi.append({"id": "prova", "nome": "Servizio finto", "domini": ["localhost"], "politica": "proteggi", "leggibile": True})
    return ("// generato da genera_estensione.py: politiche di partenza, finche' il programma non manda le sue\n"
            "globalThis.MSP_PREDEFINITI = " + json.dumps({"servizi": servizi, "ripristina": True, "blocca_file": False},
                                                         ensure_ascii=False, separators=(",", ":")) + ";\n")


def icone():
    from PIL import Image, ImageDraw
    (EST / "icone").mkdir(exist_ok=True)
    grande = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(grande)
    d.polygon([(256, 32), (464, 112), (464, 272), (256, 480), (48, 272), (48, 112)], fill=(16, 122, 107, 255))
    d.line([(160, 256), (232, 328), (360, 184)], fill=(255, 255, 255, 255), width=48, joint="curve")
    for n in (16, 32, 48, 128):
        grande.resize((n, n), Image.LANCZOS).save(EST / "icone" / f"{n}.png")


if __name__ == "__main__":
    prova = "--prova" in sys.argv
    EST.mkdir(exist_ok=True)
    (EST / "manifest.json").write_text(json.dumps(manifesto(prova), ensure_ascii=False, indent=1), encoding="utf-8")
    (EST / "predefiniti.js").write_text(predefiniti(prova), encoding="utf-8")
    icone()
    print(f"estensione scritta in {EST}" + (" (con il servizio finto)" if prova else ""))
