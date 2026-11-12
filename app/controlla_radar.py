# -*- coding: utf-8 -*-
"""Controlla un file del radar: forma delle voci, doppioni, domini troppo generici, e (con --rete) che ogni dominio esista.

  python controlla_radar.py [file] [--rete]        senza file: radar.json, quello di base

--rete chiede al DNS ogni dominio: un nome che non esiste e' quasi sempre un errore di battitura o un servizio
chiuso, e va tolto. Che un dominio esista non dimostra che sia un servizio AI: quello resta un giudizio di chi
compila l'elenco. Esce con errore se trova qualcosa da sistemare.
"""
import json
import re
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import catalogo

QUI = Path(__file__).resolve().parent
# piattaforme generali: un servizio AI che vive sotto uno di questi nomi va indicato con il suo sottodominio, mai col nome intero
GENERALI = {"google.com", "microsoft.com", "amazonaws.com", "amazon.com", "apple.com", "github.com", "adobe.com", "notion.so", "canva.com",
            "baidu.com", "tencent.com", "naver.com", "azure.com", "googleapis.com", "cloudflare.com", "vercel.sh", "vercel.app", "proton.me",
            "huggingface.co", "x.com", "meta.com", "facebook.com", "langchain.com", "nvidia.com", "jetbrains.ai", "xfyun.cn", "aliyun.com"}
# nomi che esistono solo con un sottodominio davanti (uno per cliente): il DNS non conosce il nome nudo, ma va bene così
SOLO_SOTTODOMINI = {"services.ai.azure.com"}
RX_DOMINIO = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def esiste(dominio):
    for nome in (dominio, "www." + dominio):
        try:
            socket.getaddrinfo(nome, 443)
            return True
        except OSError:
            pass
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    file = next((Path(a) for a in sys.argv[1:] if not a.startswith("--")), QUI / "radar.json")
    dati = json.loads(file.read_text(encoding="utf-8"))
    problemi, visti_id, visti_dom = [], set(), {}
    del_catalogo = {d: s["id"] for s in catalogo.SERVIZI if not s.get("radar") for d in s["domini"]}
    for voce in dati["servizi"]:
        if len(voce) != 5 or not all(isinstance(x, str) and x.strip() for x in voce):
            problemi.append(f"voce malformata: {voce}")
            continue
        ident, nome, _, tipo, domini = voce
        if ident in visti_id:
            problemi.append(f"{ident}: identificativo ripetuto")
        visti_id.add(ident)
        if tipo not in catalogo.TIPI:
            problemi.append(f"{ident}: tipo sconosciuto «{tipo}»")
        for d in domini.split():
            if not RX_DOMINIO.match(d):
                problemi.append(f"{ident}: «{d}» non è un nome di dominio")
            if d in GENERALI:
                problemi.append(f"{ident}: «{d}» è una piattaforma generale, bloccarla fermerebbe tutto il resto")
            if d in visti_dom:
                problemi.append(f"{ident}: «{d}» è già di {visti_dom[d]}")
            visti_dom[d] = ident
            sopra = next((c for c in del_catalogo if d == c or d.endswith("." + c)), None)
            if sopra:
                problemi.append(f"{ident}: «{d}» è già nel catalogo ({del_catalogo[sopra]})")
    print(f"{file.name} del {dati.get('versione', '?')}: {len(dati['servizi'])} servizi, {len(visti_dom)} domini; nel programma ne risultano "
          f"{sum(1 for s in catalogo.SERVIZI if s.get('radar'))} oltre ai {sum(1 for s in catalogo.SERVIZI if not s.get('radar'))} del catalogo")
    if "--rete" in sys.argv:
        with ThreadPoolExecutor(24) as gruppo:
            assenti = [d for d, c in zip(visti_dom, gruppo.map(esiste, visti_dom)) if not c and d not in SOLO_SOTTODOMINI]
        print(f"domini che il DNS non conosce: {len(assenti)}" + (": " + ", ".join(assenti) if assenti else ""))
        problemi += [f"{visti_dom[d]}: «{d}» non esiste" for d in assenti]
    for p in problemi:
        print("  -", p)
    print("tutto a posto" if not problemi else f"{len(problemi)} cose da sistemare")
    sys.exit(1 if problemi else 0)


if __name__ == "__main__":
    main()
