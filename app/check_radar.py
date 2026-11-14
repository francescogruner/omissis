# -*- coding: utf-8 -*-
"""Controlla un file del radar: forma delle voci, doppioni, domini troppo generici, e (con --network) che ogni dominio esista.

  python check_radar.py [file] [--network]        senza file: radar.json, quello di base

--network chiede al DNS ogni dominio: un nome che non esiste e' quasi sempre un errore di battitura o un servizio
chiuso, e va tolto. Che un dominio esista non dimostra che sia un servizio AI: quello resta un giudizio di chi
compila l'elenco. Esce con errore se trova qualcosa da sistemare.
"""
import json
import re
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import catalog

HERE = Path(__file__).resolve().parent
# piattaforme generali: un servizio AI che vive sotto uno di questi nomi va indicato con il suo sottodominio, mai col nome intero
GENERAL = {"google.com", "microsoft.com", "amazonaws.com", "amazon.com", "apple.com", "github.com", "adobe.com", "notion.so", "canva.com",
            "baidu.com", "tencent.com", "naver.com", "azure.com", "googleapis.com", "cloudflare.com", "vercel.sh", "vercel.app", "proton.me",
            "huggingface.co", "x.com", "meta.com", "facebook.com", "langchain.com", "nvidia.com", "jetbrains.ai", "xfyun.cn", "aliyun.com"}
# nomi che esistono solo con un sottodominio davanti (uno per cliente): il DNS non conosce il nome nudo, ma va bene così
ONLY_SUBDOMAINS = {"services.ai.azure.com"}
RX_DOMAIN = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def exists(domain):
    for name in (domain, "www." + domain):
        try:
            socket.getaddrinfo(name, 443)
            return True
        except OSError:
            pass
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    file = next((Path(a) for a in sys.argv[1:] if not a.startswith("--")), HERE / "radar.json")
    data = json.loads(file.read_text(encoding="utf-8"))
    problems, seen_ids, seen_domains = [], set(), {}
    of_catalog = {d: s["id"] for s in catalog.SERVICES if not s.get("radar") for d in s["domains"]}
    for entry in data["services"]:
        if len(entry) != 5 or not all(isinstance(x, str) and x.strip() for x in entry):
            problems.append(f"voce malformata: {entry}")
            continue
        ident, name, _, kind, domains = entry
        if ident in seen_ids:
            problems.append(f"{ident}: identificativo ripetuto")
        seen_ids.add(ident)
        if kind not in catalog.KINDS:
            problems.append(f"{ident}: tipo sconosciuto «{kind}»")
        for d in domains.split():
            if not RX_DOMAIN.match(d):
                problems.append(f"{ident}: «{d}» non è un nome di dominio")
            if d in GENERAL:
                problems.append(f"{ident}: «{d}» è una piattaforma generale, bloccarla fermerebbe tutto il resto")
            if d in seen_domains:
                problems.append(f"{ident}: «{d}» è già di {seen_domains[d]}")
            seen_domains[d] = ident
            above = next((c for c in of_catalog if d == c or d.endswith("." + c)), None)
            if above:
                problems.append(f"{ident}: «{d}» è già nel catalogo ({of_catalog[above]})")
    print(f"{file.name} del {data.get('version', '?')}: {len(data['services'])} servizi, {len(seen_domains)} domini; nel programma ne risultano "
          f"{sum(1 for s in catalog.SERVICES if s.get('radar'))} oltre ai {sum(1 for s in catalog.SERVICES if not s.get('radar'))} del catalogo")
    if "--network" in sys.argv:
        with ThreadPoolExecutor(24) as group:
            absent = [d for d, c in zip(seen_domains, group.map(exists, seen_domains)) if not c and d not in ONLY_SUBDOMAINS]
        print(f"domini che il DNS non conosce: {len(absent)}" + (": " + ", ".join(absent) if absent else ""))
        problems += [f"{seen_domains[d]}: «{d}» non esiste" for d in absent]
    for p in problems:
        print("  -", p)
    print("tutto a posto" if not problems else f"{len(problems)} cose da sistemare")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
